from __future__ import annotations
import math
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.db.database import SessionLocal
from app.models.paper_trading import PaperPortfolio, PaperTrade, TradeStatus, ExitReason
from app.services.stock_api_service import get_current_price
from app.utils.telegram import send_message

ICT = timezone(timedelta(hours=7))
STARTING_BALANCE = 100_000_000  # VND
POSITION_SIZE_PCT = 0.10         # fallback: 10% of portfolio per trade — daily strategies
INTRADAY_POSITION_SIZE_PCT = 0.05  # fallback: 5% — intraday strategies (tighter risk)
MAX_POSITIONS = 10
# Legacy defaults (used when strategy not found in STRATEGIES registry)
STOP_LOSS_PCT = 0.93
TAKE_PROFIT_PCT = 1.15
MAX_HOLD_DAYS = 30


def _get_or_create_portfolio(user_id: int, db) -> PaperPortfolio:
    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.user_id == user_id).first()
    if not portfolio:
        portfolio = PaperPortfolio(
            user_id=user_id,
            starting_balance=STARTING_BALANCE,
            available_cash=STARTING_BALANCE,
        )
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def _close_trade(trade: PaperTrade, exit_price: float, reason: ExitReason, db) -> None:
    """Apply exit to trade and restore cash to portfolio."""
    now = datetime.now(timezone.utc)
    trade.exit_price = exit_price
    trade.exit_time = now
    trade.exit_reason = reason
    pnl_amount = int((exit_price - trade.entry_price) * trade.quantity)
    trade.pnl_amount = pnl_amount
    trade.pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100
    trade.status = TradeStatus.closed

    portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.user_id == trade.user_id).first()
    if portfolio:
        # Return actual exit proceeds (entry cost + P&L), not just entry cost
        portfolio.available_cash += trade.position_value + pnl_amount


async def on_signal(
    user_id: int,
    symbol: str,
    entry_price: float,
    strategy_name: str = "rsi_divergence",
) -> Optional[PaperTrade]:
    """
    Open a virtual long position when a strategy fires a bullish signal.
    Reads exit_rules and position sizing from the strategy class.
    """
    from app.algorithms import STRATEGIES
    strategy_cls = STRATEGIES.get(strategy_name)

    if strategy_cls:
        sl_pct = 1 + strategy_cls.exit_rules["stop_loss_pct"]
        tp_pct = 1 + strategy_cls.exit_rules["take_profit_pct"]
        from app.services.position_sizing import get_strategy_position_pct
        pos_size_pct = get_strategy_position_pct(strategy_name, strategy_cls.timeframe)
    else:
        sl_pct = STOP_LOSS_PCT
        tp_pct = TAKE_PROFIT_PCT
        pos_size_pct = POSITION_SIZE_PCT

    db = SessionLocal()
    try:
        portfolio = _get_or_create_portfolio(user_id, db)

        open_count = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).count()
        if open_count >= MAX_POSITIONS:
            print(f"[paper] SKIP {symbol}/{strategy_name} user={user_id}: "
                  f"max positions reached ({open_count}/{MAX_POSITIONS})")
            return None

        open_positions_value = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).with_entities(PaperTrade.position_value).all()
        total_open = sum(pv[0] for pv in open_positions_value)
        portfolio_total = portfolio.available_cash + total_open

        quantity = math.floor(portfolio_total * pos_size_pct / entry_price)
        if quantity < 1:
            print(f"[paper] SKIP {symbol}/{strategy_name} user={user_id}: "
                  f"quantity<1 (portfolio={portfolio_total:,.0f} "
                  f"pos_size={pos_size_pct*100:.0f}% price={entry_price:,.0f})")
            return None
        position_value = int(entry_price * quantity)

        if portfolio.available_cash < position_value:
            print(f"[paper] SKIP {symbol}/{strategy_name} user={user_id}: "
                  f"insufficient cash (have={portfolio.available_cash:,.0f} "
                  f"need={position_value:,.0f})")
            return None

        print(f"[paper] OPEN {symbol}/{strategy_name} user={user_id} "
              f"qty={quantity} @ {entry_price:,.0f} "
              f"value={position_value:,.0f} "
              f"sl={entry_price * sl_pct:,.0f} tp={entry_price * tp_pct:,.0f}")

        portfolio.available_cash -= position_value

        trade = PaperTrade(
            user_id=user_id,
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            position_value=position_value,
            stop_loss_price=entry_price * sl_pct,
            take_profit_price=entry_price * tp_pct,
            strategy_name=strategy_name,
            status=TradeStatus.open,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)

        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.chat_id:
            display = strategy_cls.display_name if strategy_cls else strategy_name
            msg = (
                f"📈 Paper long {symbol} @ {entry_price:,.0f} [{display}]\n"
                f"SL: {trade.stop_loss_price:,.0f} | TP: {trade.take_profit_price:,.0f}\n"
                f"Size: {position_value / 1_000_000:.1f}M VND"
            )
            try:
                await send_message(chat_id=user.chat_id, text=msg)
            except Exception as e:
                print(f"Paper trading Telegram error: {e}")

        return trade
    finally:
        db.close()


async def check_positions() -> None:
    """
    Evaluate all open paper positions against stop-loss, take-profit, time-stop,
    and end-of-day close rules. Call every 5 minutes during 09:00-15:00 VN time.
    """
    from app.algorithms import STRATEGIES
    db = SessionLocal()
    try:
        open_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.open).all()
        print(f"[paper] check_positions: {len(open_trades)} open trades")
        if not open_trades:
            return

        symbols = list({t.symbol for t in open_trades})
        prices: dict[str, float] = {}
        for symbol in symbols:
            try:
                prices[symbol] = get_current_price(symbol)
            except Exception as e:
                print(f"Paper trading: could not fetch price for {symbol}: {e}")

        now_utc = datetime.now(timezone.utc)
        now_ict = now_utc.astimezone(ICT)
        closed_trades: list[tuple[PaperTrade, ExitReason]] = []

        for trade in open_trades:
            current_price = prices.get(trade.symbol)
            if current_price is None:
                continue

            strategy_cls = STRATEGIES.get(getattr(trade, 'strategy_name', 'rsi_divergence'))
            max_days = strategy_cls.exit_rules["max_days"] if strategy_cls else MAX_HOLD_DAYS
            eod_close = strategy_cls.exit_rules.get("eod_close", False) if strategy_cls else False

            reason: Optional[ExitReason] = None
            if current_price <= trade.stop_loss_price:
                reason = ExitReason.stop_loss
            elif current_price >= trade.take_profit_price:
                reason = ExitReason.take_profit
            elif (now_utc - trade.entry_time.replace(tzinfo=timezone.utc)).days >= max_days:
                reason = ExitReason.time_stop

            # End-of-day close for intraday strategies (14:45 VN time)
            if reason is None and eod_close:
                entry_ict = trade.entry_time.replace(tzinfo=timezone.utc).astimezone(ICT)
                if (entry_ict.date() == now_ict.date()
                        and (now_ict.hour, now_ict.minute) >= (14, 45)):
                    reason = ExitReason.time_stop

            if reason:
                print(f"[paper] CLOSE {trade.symbol} user={trade.user_id} "
                      f"reason={reason.value} price={current_price:,.0f} "
                      f"entry={trade.entry_price:,.0f}")
                _close_trade(trade, current_price, reason, db)
                closed_trades.append((trade, reason))
            else:
                print(f"[paper] HOLD {trade.symbol} user={trade.user_id} "
                      f"price={current_price:,.0f} "
                      f"sl={trade.stop_loss_price:,.0f} tp={trade.take_profit_price:,.0f}")

        if closed_trades:
            db.commit()

        from app.models.user import User
        for trade, reason in closed_trades:
            user = db.query(User).filter(User.id == trade.user_id).first()
            if not user or not user.chat_id:
                continue
            pnl_pct = trade.pnl_pct or 0
            pnl_amt = trade.pnl_amount or 0
            sign = "+" if pnl_pct >= 0 else ""
            strategy_cls = STRATEGIES.get(getattr(trade, 'strategy_name', 'rsi_divergence'))
            display = strategy_cls.display_name if strategy_cls else getattr(trade, 'strategy_name', '')
            if reason == ExitReason.take_profit:
                emoji, label = "✅", "take-profit"
            elif reason == ExitReason.stop_loss:
                emoji, label = "🔴", "stopped out"
            else:
                is_intraday = strategy_cls and strategy_cls.timeframe == "intraday"
                emoji = "⏱"
                label = "end-of-day exit" if is_intraday else "30-day exit"
            msg = f"{emoji} {trade.symbol} {sign}{pnl_pct:.1f}% ({sign}{pnl_amt:,.0f} VND) | {label} [{display}]"
            try:
                await send_message(chat_id=user.chat_id, text=msg)
            except Exception as e:
                print(f"Paper trading Telegram error (close): {e}")
    finally:
        db.close()


def close_position(trade_id: int, user_id: int) -> PaperTrade:
    """Manually close an open position at current market price."""
    db = SessionLocal()
    try:
        trade = db.query(PaperTrade).filter(
            PaperTrade.id == trade_id,
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).first()
        if not trade:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Open position not found")

        current_price = get_current_price(trade.symbol)
        _close_trade(trade, current_price, ExitReason.manual, db)
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db.close()


def get_portfolio_summary(user_id: int) -> dict:
    """Return portfolio stats for the given user."""
    db = SessionLocal()
    try:
        portfolio = _get_or_create_portfolio(user_id, db)

        open_trades = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).all()

        closed_trades = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.closed,
        ).all()

        total_pnl = sum(t.pnl_amount or 0 for t in closed_trades)
        total_closed = len(closed_trades)
        winning = sum(1 for t in closed_trades if (t.pnl_amount or 0) > 0)
        win_rate = (winning / total_closed * 100) if total_closed > 0 else 0.0

        best = max(closed_trades, key=lambda t: t.pnl_pct or 0, default=None)
        worst = min(closed_trades, key=lambda t: t.pnl_pct or 0, default=None)

        return {
            "starting_balance": portfolio.starting_balance,
            "available_cash": portfolio.available_cash,
            "open_positions": len(open_trades),
            "total_pnl_amount": total_pnl,
            "total_pnl_pct": total_pnl / portfolio.starting_balance * 100 if portfolio.starting_balance else 0.0,
            "win_rate": round(win_rate, 1),
            "total_closed_trades": total_closed,
            "best_trade": {"symbol": best.symbol, "pnl_pct": best.pnl_pct} if best else None,
            "worst_trade": {"symbol": worst.symbol, "pnl_pct": worst.pnl_pct} if worst else None,
        }
    finally:
        db.close()
