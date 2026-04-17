from __future__ import annotations
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.services import paper_trading_service
from app.algorithms import STRATEGIES

ICT = timezone(timedelta(hours=7))
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 15

# Once-per-day guard: {strategy_name: {symbol: date_str}}
# Prevents the same strategy from firing on the same symbol more than once per day.
_intraday_fired: dict[str, dict[str, str]] = {}


def _build_symbol_user_ids_map(users) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for user in users:
        for symbol in user.stocks:
            result.setdefault(symbol, []).append(user.id)
    return result


async def _poll_once(get_users=get_all_users) -> None:
    """One intraday poll cycle. Runs all intraday strategies on 5-min data."""
    now_ict = datetime.now(ICT)
    today = now_ict.date().isoformat()

    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    symbol_to_user_ids = _build_symbol_user_ids_map(users)

    intraday_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "intraday"}

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '5m', today, today)
            if not records_list:
                continue
            df = pd.DataFrame(records_list)

            for strategy_name, StrategyClass in intraday_strategies.items():
                try:
                    # Once-per-day deduplication
                    fired_today = _intraday_fired.setdefault(strategy_name, {})
                    if fired_today.get(symbol) == today:
                        continue

                    strategy = StrategyClass()
                    df_signals = strategy.generate_signals(df.copy())
                    last_signal = int(df_signals.iloc[-1].get('signal', 0))
                    price = float(records_list[-1]['close'])
                    signal_time = now_ict.strftime('%H:%M')

                    if last_signal == 1:
                        fired_today[symbol] = today
                        await send_signal(
                            chat_ids, symbol, 'bullish', 'Intraday',
                            price, signal_time, StrategyClass.display_name,
                        )
                        for user_id in symbol_to_user_ids.get(symbol, []):
                            try:
                                await paper_trading_service.on_signal(
                                    user_id=user_id, symbol=symbol,
                                    entry_price=price, strategy_name=strategy_name,
                                )
                            except Exception as e:
                                print(f'Paper trading on_signal error ({strategy_name}) '
                                      f'user {user_id}/{symbol}: {e}')
                except Exception as e:
                    print(f'Intraday worker strategy error ({strategy_name}/{symbol}): {e}')

        except Exception as e:
            print(f'Intraday worker error for {symbol}: {e}')

    # Check paper positions every cycle during market hours
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
