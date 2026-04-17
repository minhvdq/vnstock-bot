from __future__ import annotations
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import fetch_intraday_ohlcv_with_rsi, send_signal
from app.services import paper_trading_service
from app.services.intraday_recorder import record_bars
from app.algorithms import STRATEGIES

ICT = timezone(timedelta(hours=7))
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 15

# T+0 instruments: VN30 and VN100 index futures (front month)
INTRADAY_SYMBOLS = ['VN30F1M', 'VN100F1M']

# Once-per-day guard: {strategy_name: {symbol: date_str}}
_intraday_fired: dict[str, dict[str, str]] = {}


async def _poll_once(get_users=get_all_users) -> None:
    """One intraday poll cycle. Runs all intraday strategies on 1-min futures data."""
    now_ict = datetime.now(ICT)
    today = now_ict.date().isoformat()
    is_market_hours = (now_ict.weekday() < 5
                       and MARKET_OPEN_HOUR <= now_ict.hour < MARKET_CLOSE_HOUR)

    print(f'[intraday] poll {now_ict.strftime("%H:%M:%S")} ICT '
          f'weekday={now_ict.weekday()} market_hours={is_market_hours}')

    users = get_users()
    all_user_ids = [u.id for u in users]
    all_chat_ids = [u.chat_id for u in users if u.chat_id]
    intraday_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "intraday"}

    print(f'[intraday] {len(users)} users | symbols={INTRADAY_SYMBOLS} | '
          f'{len(intraday_strategies)} intraday strategies: {list(intraday_strategies)}')

    for symbol in INTRADAY_SYMBOLS:
        try:
            records_list = fetch_intraday_ohlcv_with_rsi(symbol)
            if not records_list:
                print(f'[intraday] {symbol}: no 1m data returned')
                continue
            inserted = record_bars(symbol, records_list)
            if inserted:
                print(f'[intraday] {symbol}: recorded {inserted} new bars')
            df = pd.DataFrame(records_list)

            for strategy_name, StrategyClass in intraday_strategies.items():
                try:
                    fired_today = _intraday_fired.setdefault(strategy_name, {})
                    if fired_today.get(symbol) == today:
                        print(f'[intraday] {symbol}/{strategy_name}: already fired today, skipping')
                        continue

                    strategy = StrategyClass()
                    df_signals = strategy.generate_signals(df.copy())
                    last_signal = int(df_signals.iloc[-1].get('signal', 0))
                    price = float(records_list[-1]['close'])
                    signal_time = now_ict.strftime('%H:%M')

                    print(f'[intraday] {symbol}/{strategy_name}: '
                          f'bars={len(df)} last_signal={last_signal} price={price:,.0f}')

                    if last_signal == 1:
                        fired_today[symbol] = today
                        print(f'[intraday] SIGNAL BUY {symbol} @ {price:,.0f} [{strategy_name}] '
                              f'-> {len(all_chat_ids)} telegram, {len(all_user_ids)} paper-trade users')
                        await send_signal(
                            all_chat_ids, symbol, 'bullish', 'Intraday',
                            price, signal_time, StrategyClass.display_name,
                        )
                        for user_id in all_user_ids:
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

    if is_market_hours:
        try:
            await paper_trading_service.check_positions()
        except Exception as e:
            print(f'[intraday] check_positions error: {e}')
    else:
        print(f'[intraday] outside market hours, skipping check_positions')


async def intraday_worker(get_users=get_all_users) -> None:
    """Background task: poll every 1 minute indefinitely."""
    while True:
        try:
            await _poll_once(get_users)
        except (OperationalError, DisconnectionError) as e:
            print(f'Intraday worker DB error: {e}')
            await asyncio.sleep(10)
            continue
        except Exception as e:
            print(f'Intraday worker error: {e}')
        await asyncio.sleep(60)
