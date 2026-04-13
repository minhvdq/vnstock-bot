from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.algorithms.rsi_divergence import _has_divergence_at

ICT = timezone(timedelta(hours=7))
SIGNAL_HOUR = 15
SIGNAL_MINUTE = 5


def _seconds_until_next_signal() -> float:
    """
    Returns seconds until next 3:05 PM ICT.
    If now >= 3:05 PM ICT today, returns seconds until 3:05 PM tomorrow.
    Exact 3:05 PM counts as past (fires tomorrow, never twice today).
    """
    now = datetime.now(ICT)
    target = now.replace(hour=SIGNAL_HOUR, minute=SIGNAL_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_daily_check(get_users=get_all_users) -> None:
    """One daily signal check. Testable entry point for the worker loop."""
    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    ict_today = datetime.now(ICT).date()
    today = ict_today.isoformat()
    start = (ict_today - timedelta(days=90)).isoformat()

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '1D', start, today)
            if not records_list:
                continue
            divergence = _has_divergence_at(records_list, len(records_list) - 1)
            if divergence is None:
                continue
            price = float(records_list[-1]['close'])
            signal_time = datetime.now(ICT).strftime('%H:%M')
            await send_signal(chat_ids, symbol, divergence['type'], 'Daily', price, signal_time)
        except Exception as e:
            print(f'Daily worker error for {symbol}: {e}')


async def daily_worker(get_users=get_all_users) -> None:
    """Background task: fire once daily at 3:05 PM ICT indefinitely."""
    while True:
        await asyncio.sleep(_seconds_until_next_signal())
        try:
            await _run_daily_check(get_users)
        except (OperationalError, DisconnectionError) as e:
            print(f'Daily worker DB error: {e}')
            await asyncio.sleep(60)
            continue
        except Exception as e:
            print(f'Daily worker error: {e}')
