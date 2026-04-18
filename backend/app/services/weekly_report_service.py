from __future__ import annotations
from datetime import datetime, timezone, timedelta, date

from app.db.database import SessionLocal
from app.models.paper_trading import PaperTrade, PaperPortfolio, TradeStatus
from app.utils.telegram import send_message
from app.services.user_service import get_all_users

ICT = timezone(timedelta(hours=7))

_STRATEGY_EMOJI = {
    'rsi_divergence': '📈',
    'ema_macd': '📊',
    'donchian_breakout': '🔲',
}
_STRATEGY_LABEL = {
    'rsi_divergence': 'RSI Divergence',
    'ema_macd': 'EMA+MACD',
    'donchian_breakout': 'Donchian',
}


def build_weekly_report(user_id: int, days: int = 7) -> dict:
    """Aggregate closed paper trades for the past N days, grouped by strategy."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        portfolio = db.query(PaperPortfolio).filter(
            PaperPortfolio.user_id == user_id
        ).first()

        recent = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.closed,
            PaperTrade.exit_time >= cutoff,
        ).all()

        open_count = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).count()

        by_strategy: dict[str, dict] = {}
        for t in recent:
            name = getattr(t, 'strategy_name', 'unknown') or 'unknown'
            if name not in by_strategy:
                by_strategy[name] = {'trades': 0, 'wins': 0, 'pnl': 0}
            by_strategy[name]['trades'] += 1
            pnl = t.pnl_amount or 0
            by_strategy[name]['pnl'] += pnl
            if pnl > 0:
                by_strategy[name]['wins'] += 1

        starting = portfolio.starting_balance if portfolio else 100_000_000
        available = portfolio.available_cash if portfolio else starting
        total_pnl = sum(t.pnl_amount or 0 for t in recent)

        best = max(recent, key=lambda t: t.pnl_pct or 0, default=None)
        worst = min(recent, key=lambda t: t.pnl_pct or 0, default=None)

        return {
            'user_id': user_id,
            'period_days': days,
            'starting_balance': starting,
            'available_cash': available,
            'open_positions': open_count,
            'total_pnl': total_pnl,
            'total_trades': len(recent),
            'by_strategy': by_strategy,
            'best_trade': {'symbol': best.symbol, 'pnl_pct': best.pnl_pct} if best else None,
            'worst_trade': {'symbol': worst.symbol, 'pnl_pct': worst.pnl_pct} if worst else None,
        }
    finally:
        db.close()


def format_weekly_report(report: dict) -> str:
    """Render a Telegram-friendly weekly summary."""
    today = date.today()
    week_start = today - timedelta(days=report['period_days'])

    starting = report['starting_balance']
    pnl = report['total_pnl']
    pnl_pct = pnl / starting * 100 if starting else 0
    portfolio_value = starting + pnl
    sign = '+' if pnl >= 0 else ''

    lines = [
        f"📊 Weekly Paper Trade Report",
        f"Week: {week_start} → {today}",
        f"",
        f"💼 Portfolio: {portfolio_value / 1_000_000:.1f}M VND ({sign}{pnl_pct:.2f}%)",
        (f"💰 Cash: {report['available_cash'] / 1_000_000:.1f}M "
         f"| Open: {report['open_positions']} positions"),
        f"📝 Trades this week: {report['total_trades']}",
        f"",
    ]

    if report['by_strategy']:
        lines.append("By Strategy:")
        for name, stats in report['by_strategy'].items():
            emoji = _STRATEGY_EMOJI.get(name, '📉')
            label = _STRATEGY_LABEL.get(name, name)
            win_rate = stats['wins'] / stats['trades'] * 100 if stats['trades'] else 0
            pnl_m = stats['pnl'] / 1_000_000
            s = '+' if pnl_m >= 0 else ''
            lines.append(
                f"{emoji} {label}: {s}{pnl_m:.2f}M | "
                f"{stats['trades']} trades | {win_rate:.0f}% win"
            )
    else:
        lines.append("No closed trades this week.")

    best = report.get('best_trade')
    worst = report.get('worst_trade')
    if best or worst:
        lines.append("")
    if best:
        sb = '+' if (best['pnl_pct'] or 0) >= 0 else ''
        lines.append(f"🏆 Best: {best['symbol']} {sb}{best['pnl_pct']:.1f}%")
    if worst and worst != best:
        sw = '+' if (worst['pnl_pct'] or 0) >= 0 else ''
        lines.append(f"📉 Worst: {worst['symbol']} {sw}{worst['pnl_pct']:.1f}%")

    return '\n'.join(lines)


async def send_weekly_reports(days: int = 7) -> int:
    """Send weekly report to all users with a linked Telegram chat. Returns count sent."""
    users = get_all_users()
    sent = 0
    for user in users:
        if not getattr(user, 'chat_id', None):
            continue
        try:
            report = build_weekly_report(user.id, days=days)
            msg = format_weekly_report(report)
            await send_message(chat_id=user.chat_id, text=msg)
            print(f'[weekly_report] sent to user={user.id} '
                  f'trades={report["total_trades"]} pnl={report["total_pnl"]:+,.0f}')
            sent += 1
        except Exception as e:
            print(f'[weekly_report] error for user={user.id}: {e}')
    return sent
