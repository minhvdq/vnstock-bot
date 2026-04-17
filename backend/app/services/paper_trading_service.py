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
POSITION_SIZE_PCT = 0.10         # 10% of portfolio per trade
MAX_POSITIONS = 10
STOP_LOSS_PCT = 0.93             # entry × 0.93  (-7%)
TAKE_PROFIT_PCT = 1.15           # entry × 1.15  (+15%)
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
        portfolio.available_cash += trade.position_value


async def on_signal(user_id: int, symbol: str, entry_price: float) -> Optional[PaperTrade]:
    """
    Open a virtual long position when a bullish RSI divergence fires.
    Lazy-creates the PaperPortfolio for the user if it doesn't exist.
    Returns the created PaperTrade or None if position was skipped.
    """
    db = SessionLocal()
    try:
        portfolio = _get_or_create_portfolio(user_id, db)

        # Check max concurrent positions
        open_count = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).count()
        if open_count >= MAX_POSITIONS:
            print(f"Paper trading: user {user_id} has {open_count} open positions, skipping {symbol}")
            return None

        # Compute portfolio total value (cash + open positions)
        open_positions_value = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).with_entities(PaperTrade.position_value).all()
        total_open = sum(pv[0] for pv in open_positions_value)
        portfolio_total = portfolio.available_cash + total_open

        # Compute quantity and position value
        quantity = math.floor(portfolio_total * POSITION_SIZE_PCT / entry_price)
        if quantity < 1:
            print(f"Paper trading: quantity < 1 for {symbol} @ {entry_price}, skipping")
            return None
        position_value = int(entry_price * quantity)

        if portfolio.available_cash < position_value:
            print(f"Paper trading: insufficient cash for {symbol}, skipping")
            return None

        # Deduct cash and create trade
        portfolio.available_cash -= position_value

        trade = PaperTrade(
            user_id=user_id,
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            position_value=position_value,
            stop_loss_price=entry_price * STOP_LOSS_PCT,
            take_profit_price=entry_price * TAKE_PROFIT_PCT,
            status=TradeStatus.open,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)

        # Send Telegram notification (if user has chat_id connected)
        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.chat_id:
            msg = (
                f"📈 Paper long {symbol} @ {entry_price:,.0f}\n"
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
    Evaluate all open paper positions against stop-loss, take-profit, and time-stop rules.
    Call this every 5 minutes during 09:00-15:00 VN time on trading days.
    """
    db = SessionLocal()
    try:
        open_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.open).all()
        if not open_trades:
            return

        # Group by symbol to batch-fetch prices
        symbols = list({t.symbol for t in open_trades})
        prices: dict[str, float] = {}
        for symbol in symbols:
            try:
                prices[symbol] = get_current_price(symbol)
            except Exception as e:
                print(f"Paper trading: could not fetch price for {symbol}: {e}")

        now_utc = datetime.now(timezone.utc)
        closed_trades: list[tuple[PaperTrade, ExitReason]] = []

        for trade in open_trades:
            current_price = prices.get(trade.symbol)
            if current_price is None:
                continue

            reason: Optional[ExitReason] = None
            if current_price <= trade.stop_loss_price:
                reason = ExitReason.stop_loss
            elif current_price >= trade.take_profit_price:
                reason = ExitReason.take_profit
            elif (now_utc - trade.entry_time.replace(tzinfo=timezone.utc)).days >= MAX_HOLD_DAYS:
                reason = ExitReason.time_stop

            if reason:
                _close_trade(trade, current_price, reason, db)
                closed_trades.append((trade, reason))

        if closed_trades:
            db.commit()

        # Send Telegram notifications for closed trades
        from app.models.user import User
        for trade, reason in closed_trades:
            user = db.query(User).filter(User.id == trade.user_id).first()
            if not user or not user.chat_id:
                continue
            pnl_pct = trade.pnl_pct or 0
            pnl_amt = trade.pnl_amount or 0
            sign = "+" if pnl_pct >= 0 else ""
            if reason == ExitReason.take_profit:
                emoji = "✅"
                label = "take-profit"
            elif reason == ExitReason.stop_loss:
                emoji = "🔴"
                label = "stopped out"
            else:
                emoji = "⏱"
                label = "30-day exit"
            msg = f"{emoji} {trade.symbol} {sign}{pnl_pct:.1f}% ({sign}{pnl_amt:,.0f} VND) | {label}"
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
