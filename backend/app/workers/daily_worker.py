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
SIGNAL_HOUR = 15
SIGNAL_MINUTE = 5
DATA_LOOKBACK_DAYS = 200  # enough for EMA(50) to stabilize


def _seconds_until_next_signal() -> float:
    now = datetime.now(ICT)
    target = now.replace(hour=SIGNAL_HOUR, minute=SIGNAL_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _build_symbol_user_ids_map(users) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for user in users:
        for symbol in user.stocks:
            result.setdefault(symbol, []).append(user.id)
    return result


async def _run_daily_check(get_users=get_all_users) -> None:
    """Run all daily strategies for every symbol in all users' watchlists."""
    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    symbol_to_user_ids = _build_symbol_user_ids_map(users)
    ict_today = datetime.now(ICT).date()
    today = ict_today.isoformat()
    start = (ict_today - timedelta(days=DATA_LOOKBACK_DAYS)).isoformat()

    daily_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "daily"}

    print(f'[daily] running check for {today} | {len(users)} users | '
          f'{len(symbol_to_user_ids)} symbols | '
          f'{len(daily_strategies)} daily strategies: {list(daily_strategies)}')

    if not symbol_to_user_ids:
        print('[daily] no symbols to scan — watchlists empty')

    # Iterate over ALL symbols from all users (not just Telegram-connected users)
    for symbol, user_ids in symbol_to_user_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '1D', start, today)
            if not records_list:
                continue
            df = pd.DataFrame(records_list)

            for strategy_name, StrategyClass in daily_strategies.items():
                try:
                    strategy = StrategyClass()
                    df_signals = strategy.generate_signals(df.copy())
                    last_signal = int(df_signals.iloc[-1].get('signal', 0))
                    price = float(records_list[-1]['close'])
                    signal_time = datetime.now(ICT).strftime('%H:%M')
                    chat_ids = symbol_to_chat_ids.get(symbol, [])

                    print(f'[daily] {symbol}/{strategy_name}: '
                          f'bars={len(records_list)} last_signal={last_signal} price={price:,.0f}')

                    if last_signal == 1:
                        print(f'[daily] SIGNAL BUY {symbol} @ {price:,.0f} [{strategy_name}] '
                              f'-> {len(chat_ids)} telegram, {len(user_ids)} paper-trade users')
                        await send_signal(
                            chat_ids, symbol, 'bullish', 'Daily',
                            price, signal_time, StrategyClass.display_name,
                        )
                        for user_id in user_ids:
                            try:
                                await paper_trading_service.on_signal(
                                    user_id=user_id, symbol=symbol,
                                    entry_price=price, strategy_name=strategy_name,
                                )
                            except Exception as e:
                                print(f'[daily] paper on_signal error ({strategy_name}) '
                                      f'user {user_id}/{symbol}: {e}')

                    elif last_signal == -1:
                        print(f'[daily] SIGNAL SELL {symbol} [{strategy_name}]')
                        await send_signal(
                            chat_ids, symbol, 'bearish', 'Daily',
                            price, signal_time, StrategyClass.display_name,
                        )
                except Exception as e:
                    print(f'[daily] strategy error ({strategy_name}/{symbol}): {e}')

        except Exception as e:
            print(f'Daily worker error for {symbol}: {e}')


async def daily_worker(get_users=get_all_users) -> None:
    """Background task: fire once daily at 3:05 PM ICT indefinitely."""
    while True:
        secs = _seconds_until_next_signal()
        next_run = datetime.now(ICT) + timedelta(seconds=secs)
        print(f'[daily] next run at {next_run.strftime("%H:%M:%S")} ICT '
              f'(in {secs/60:.1f} min)')
        await asyncio.sleep(secs)
        try:
            await _run_daily_check(get_users)
        except (OperationalError, DisconnectionError) as e:
            print(f'[daily] DB error: {e}')
            await asyncio.sleep(60)
            continue
        except Exception as e:
            print(f'[daily] error: {e}')
