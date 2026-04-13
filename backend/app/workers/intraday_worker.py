from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.algorithms.rsi_divergence import _has_divergence_at

ICT = timezone(timedelta(hours=7))

_seen: set[tuple] = set()    # (symbol, prefix_idx, suffix_idx)
_seen_date: str = ''          # YYYY-MM-DD, cleared when date changes


async def _poll_once(get_users=get_all_users) -> None:
    """One intraday poll cycle. Testable entry point for the worker loop."""
    global _seen, _seen_date

    today = datetime.now(ICT).date().isoformat()
    if today != _seen_date:
        _seen.clear()
        _seen_date = today

    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '1m', today, today)
            if not records_list:
                continue
            divergence = _has_divergence_at(records_list, len(records_list) - 1)
            if divergence is None:
                continue
            key = (symbol, divergence['prefixIndex'], divergence['suffixIndex'])
            if key in _seen:
                continue
            _seen.add(key)
            price = float(records_list[-1]['close'])
            signal_time = datetime.now(ICT).strftime('%H:%M')
            await send_signal(chat_ids, symbol, divergence['type'], 'Intraday', price, signal_time)
        except Exception as e:
            print(f'Intraday worker error for {symbol}: {e}')


async def intraday_worker(get_users=get_all_users) -> None:
    """Background task: poll every 5 minutes indefinitely."""
    while True:
        try:
            await _poll_once(get_users)
        except (OperationalError, DisconnectionError) as e:
            print(f'Intraday worker DB error: {e}')
            await asyncio.sleep(10)
            continue
        except Exception as e:
            print(f'Intraday worker error: {e}')
        await asyncio.sleep(300)
