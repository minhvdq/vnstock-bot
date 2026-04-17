from __future__ import annotations
import asyncio
import talib
import pandas as pd
from vnstock import Quote
from app.utils.telegram import send_message


def build_symbol_map(users: list) -> dict[str, list[str]]:
    """
    Returns {symbol: [chat_id, ...]} for all users with a non-empty chat_id.
    Each symbol appears once; its value is all chat_ids watching it.
    """
    result: dict[str, list[str]] = {}
    for user in users:
        if not user.chat_id:
            continue
        for symbol in user.stocks:
            if symbol not in result:
                result[symbol] = []
            result[symbol].append(user.chat_id)
    return result


_INTRADAY_SOURCES = ['VCI', 'TCBS']  # fallback chain for non-daily intervals


def fetch_ohlcv_with_rsi(
    symbol: str,
    interval: str,
    start: str,
    end: str,
) -> list[dict] | None:
    """
    Fetch OHLCV via vnstock, compute RSI via talib, drop NaN rows.
    Returns list[dict] with RSI field, or None if data is empty/insufficient.

    For intraday intervals, tries each source in _INTRADAY_SOURCES in order
    since VCI may reject requests from non-VN IPs.
    """
    sources = _INTRADAY_SOURCES if interval != '1D' else ['VCI']

    df: pd.DataFrame | None = None
    for source in sources:
        try:
            result = Quote(symbol=symbol, source=source).history(
                start=start, end=end, interval=interval
            )
            if result is not None and not result.empty:
                df = result
                if source != 'VCI':
                    print(f'[fetch] {symbol} {interval}: VCI empty, using {source}')
                break
            else:
                print(f'[fetch] {symbol} {interval} ({start}→{end}): {source} returned empty/None')
        except Exception as e:
            print(f'[fetch] {symbol} {interval}: {source} exception: {e}')

    if df is None or df.empty:
        return None

    raw_count = len(df)
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df = df.dropna(subset=['RSI']).reset_index(drop=True)

    if len(df) < 2:
        print(f'[fetch] {symbol} {interval}: only {len(df)}/{raw_count} bars after RSI warmup')
        return None

    return df.to_dict(orient='records')


def format_signal_message(
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
    strategy_name: str = 'RSI Divergence',
) -> str:
    emoji = '🔴' if divergence_type == 'bearish' else '🟢'
    action = 'SELL' if divergence_type == 'bearish' else 'BUY'
    direction = 'Bearish' if divergence_type == 'bearish' else 'Bullish'
    return (
        f"{emoji} {symbol} — {action} signal\n"
        f"Strategy: {strategy_name} ({direction}) | {timeframe}\n"
        f"Price: {price:,.0f} VND\n"
        f"Time: {signal_time} ICT"
    )


async def send_signal(
    chat_ids: list[str],
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
    strategy_name: str = 'RSI Divergence',
) -> None:
    if not chat_ids:
        return
    message = format_signal_message(symbol, divergence_type, timeframe, price, signal_time, strategy_name)
    for chat_id in chat_ids:
        try:
            await send_message(chat_id=chat_id, text=message)
        except Exception as e:
            print(f"Failed to send signal to {chat_id}: {e}")
        await asyncio.sleep(0.05)
