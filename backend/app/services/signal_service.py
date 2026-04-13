from __future__ import annotations
import asyncio
from datetime import date, timedelta
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


def fetch_ohlcv_with_rsi(
    symbol: str,
    interval: str,
    start: str,
    end: str,
) -> list[dict] | None:
    """
    Fetch OHLCV via vnstock, compute RSI via talib, drop NaN rows.
    Returns list[dict] with RSI field, or None if data is empty/insufficient.
    Both intraday and daily workers use this for a consistent data pipeline.
    """
    df: pd.DataFrame = Quote(symbol=symbol, source='VCI').history(
        start=start, end=end, interval=interval
    )
    if df is None or df.empty:
        return None
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df = df.dropna(subset=['RSI']).reset_index(drop=True)
    if len(df) < 2:
        return None
    return df.to_dict(orient='records')


def format_signal_message(
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
) -> str:
    """
    Format a Telegram signal message.

    Example:
        🔴 VGI — SELL signal
        Strategy: RSI Divergence (Bearish) | Intraday
        Price: 24,500 VND
        Time: 14:32 ICT
    """
    emoji = '🔴' if divergence_type == 'bearish' else '🟢'
    action = 'SELL' if divergence_type == 'bearish' else 'BUY'
    direction = 'Bearish' if divergence_type == 'bearish' else 'Bullish'
    return (
        f"{emoji} {symbol} — {action} signal\n"
        f"Strategy: RSI Divergence ({direction}) | {timeframe}\n"
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
) -> None:
    """
    Format the signal message and send to each chat_id.
    50ms delay between sends to stay under Telegram's rate limit.
    If one send fails, logs the error and continues to remaining chat_ids.
    No-op if chat_ids is empty.
    """
    if not chat_ids:
        return
    message = format_signal_message(symbol, divergence_type, timeframe, price, signal_time)
    for chat_id in chat_ids:
        try:
            await send_message(chat_id=chat_id, text=message)
        except Exception as e:
            print(f"Failed to send signal to {chat_id}: {e}")
        await asyncio.sleep(0.05)
