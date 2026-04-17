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
    is_market_hours = (now_ict.weekday() < 5
                       and MARKET_OPEN_HOUR <= now_ict.hour < MARKET_CLOSE_HOUR)

    print(f'[intraday] poll {now_ict.strftime("%H:%M:%S")} ICT '
          f'weekday={now_ict.weekday()} market_hours={is_market_hours}')

    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    symbol_to_user_ids = _build_symbol_user_ids_map(users)
    intraday_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "intraday"}

    print(f'[intraday] {len(users)} users | {len(symbol_to_user_ids)} symbols | '
          f'{len(intraday_strategies)} intraday strategies: {list(intraday_strategies)}')

    if not symbol_to_user_ids:
        print('[intraday] no symbols to scan — watchlists empty')

    # Iterate over ALL symbols from all users (not just Telegram-connected users)
    for symbol, user_ids in symbol_to_user_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '5m', today, today)
            if not records_list:
                print(f'[intraday] {symbol}: no 5m data returned')
                continue
            df = pd.DataFrame(records_list)

            for strategy_name, StrategyClass in intraday_strategies.items():
                try:
                    # Once-per-day deduplication
                    fired_today = _intraday_fired.setdefault(strategy_name, {})
                    if fired_today.get(symbol) == today:
                        print(f'[intraday] {symbol}/{strategy_name}: already fired today, skipping')
                        continue

                    strategy = StrategyClass()
                    df_signals = strategy.generate_signals(df.copy())
                    last_signal = int(df_signals.iloc[-1].get('signal', 0))
                    price = float(records_list[-1]['close'])
                    signal_time = now_ict.strftime('%H:%M')
                    chat_ids = symbol_to_chat_ids.get(symbol, [])

                    print(f'[intraday] {symbol}/{strategy_name}: '
                          f'bars={len(df)} last_signal={last_signal} price={price:,.0f}')

                    if last_signal == 1:
                        fired_today[symbol] = today
                        print(f'[intraday] SIGNAL BUY {symbol} @ {price:,.0f} [{strategy_name}] '
                              f'-> {len(chat_ids)} telegram, {len(user_ids)} paper-trade users')
                        await send_signal(
                            chat_ids, symbol, 'bullish', 'Intraday',
                            price, signal_time, StrategyClass.display_name,
                        )
                        for user_id in user_ids:
                            try:
                                await paper_trading_service.on_signal(
                                    user_id=user_id, symbol=symbol,
                                    entry_price=price, strategy_name=strategy_name,
                                )
                            except Exception as e:
                                print(f'[intraday] paper on_signal error '
                                      f'({strategy_name}) user {user_id}/{symbol}: {e}')
                except Exception as e:
                    print(f'[intraday] strategy error ({strategy_name}/{symbol}): {e}')

        except Exception as e:
            print(f'[intraday] fetch error for {symbol}: {e}')

    # Check paper positions every cycle during market hours
    if is_market_hours:
        try:
            await paper_trading_service.check_positions()
        except Exception as e:
            print(f'[intraday] check_positions error: {e}')
    else:
        print(f'[intraday] outside market hours, skipping check_positions')


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
