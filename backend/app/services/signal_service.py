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


_INTRADAY_SOURCES = ['KBS', 'VCI']  # KBS required for futures (VN30F/VN100F); VCI fallback for stocks


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


def fetch_intraday_ohlcv_with_rsi(symbol: str) -> list[dict] | None:
    """
    Fetch today's tick data via Quote.intraday(), resample to 1-min OHLCV bars,
    compute RSI, and return list[dict] compatible with generate_signals().

    Quote.history() does not support sub-daily intervals, so intraday data must
    come from Quote.intraday() which returns matched-order tick data.
    """
    sources = _INTRADAY_SOURCES

    df: pd.DataFrame | None = None
    for source in sources:
        try:
            result = Quote(symbol=symbol, source=source).intraday(page_size=10_000)
            if result is not None and not result.empty:
                df = result
                if source != 'KBS':
                    print(f'[fetch] {symbol} intraday: KBS empty, using {source}')
                break
            else:
                print(f'[fetch] {symbol} intraday: {source} returned empty/None')
        except Exception as e:
            print(f'[fetch] {symbol} intraday: {source} exception: {e}')

    if df is None or df.empty:
        return None

    time_col = next((c for c in ['time', 'datetime', 'date'] if c in df.columns), None)
    price_col = next((c for c in ['close', 'price'] if c in df.columns), None)
    if not time_col or not price_col:
        print(f'[fetch] {symbol} intraday: unexpected columns {list(df.columns)}')
        return None

    df[time_col] = pd.to_datetime(df[time_col])
    df = df.set_index(time_col).sort_index()

    agg = {
        'open': pd.NamedAgg(column=price_col, aggfunc='first'),
        'high': pd.NamedAgg(column=price_col, aggfunc='max'),
        'low': pd.NamedAgg(column=price_col, aggfunc='min'),
        'close': pd.NamedAgg(column=price_col, aggfunc='last'),
    }
    if 'volume' in df.columns:
        agg['volume'] = pd.NamedAgg(column='volume', aggfunc='sum')

    bars = df.resample('1min').agg(**agg).dropna(subset=['close']).reset_index()
    bars = bars.rename(columns={time_col: 'time'})
    if 'volume' not in bars.columns:
        bars['volume'] = 0

    if bars.empty:
        print(f'[fetch] {symbol} intraday: no bars after resampling')
        return None

    raw_count = len(bars)
    bars['RSI'] = talib.RSI(bars['close'], timeperiod=14)
    bars = bars.dropna(subset=['RSI']).reset_index(drop=True)

    if len(bars) < 2:
        print(f'[fetch] {symbol} intraday: only {len(bars)}/{raw_count} bars after RSI warmup')
        return None

    return bars.to_dict(orient='records')


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
