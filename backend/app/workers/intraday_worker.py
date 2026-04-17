from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.algorithms.rsi_divergence import _has_divergence_at
from app.services import paper_trading_service

ICT = timezone(timedelta(hours=7))
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 15

_seen: set[tuple] = set()    # (symbol, prefix_idx, suffix_idx)
_seen_date: str = ''          # YYYY-MM-DD, cleared when date changes


def _build_symbol_user_ids_map(users) -> dict[str, list[int]]:
    """Returns {symbol: [user_id, ...]} for ALL users (regardless of chat_id)."""
    result: dict[str, list[int]] = {}
    for user in users:
        for symbol in user.stocks:
            result.setdefault(symbol, []).append(user.id)
    return result


async def _poll_once(get_users=get_all_users) -> None:
    """One intraday poll cycle. Testable entry point for the worker loop."""
    global _seen, _seen_date

    now_ict = datetime.now(ICT)
    today = now_ict.date().isoformat()
    if today != _seen_date:
        _seen.clear()
        _seen_date = today

    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    symbol_to_user_ids = _build_symbol_user_ids_map(users)

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
            signal_time = now_ict.strftime('%H:%M')
            await send_signal(chat_ids, symbol, divergence['type'], 'Intraday', price, signal_time)

            # Paper trading: open position on bullish divergence
            if divergence['type'] == 'bullish':
                for user_id in symbol_to_user_ids.get(symbol, []):
                    try:
                        await paper_trading_service.on_signal(user_id=user_id, symbol=symbol, entry_price=price)
                    except Exception as e:
                        print(f'Paper trading on_signal error for user {user_id} / {symbol}: {e}')
        except Exception as e:
            print(f'Intraday worker error for {symbol}: {e}')

    # Check paper positions every poll cycle during market hours
    if now_ict.weekday() < 5 and MARKET_OPEN_HOUR <= now_ict.hour < MARKET_CLOSE_HOUR:
        try:
            await paper_trading_service.check_positions()
        except Exception as e:
            print(f'Paper trading check_positions error: {e}')


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
