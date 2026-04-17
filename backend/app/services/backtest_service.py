from __future__ import annotations
from datetime import date, timedelta
import talib
import pandas as pd
from vnstock import Quote
from app.algorithms import STRATEGIES
from app.algorithms.base import BacktestResult


def run_backtest(
    symbol: str,
    strategy_name: str = 'rsi_divergence',
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100_000_000,
) -> BacktestResult:
    """
    Fetch OHLCV for `symbol`, run the named strategy's backtest,
    and return a BacktestResult with full metrics and trade log.

    Interval and default lookback are derived from strategy.timeframe:
      - daily    → '1D', 365-day default lookback
      - intraday → '5m', 30-day default lookback

    Raises ValueError for: unknown strategy, empty data, insufficient data.
    """
    if not symbol or not symbol.strip():
        raise ValueError('symbol must not be empty')

    if strategy_name not in STRATEGIES:
        raise ValueError(f'Unknown strategy: {strategy_name}')

    strategy_cls = STRATEGIES[strategy_name]
    is_intraday = strategy_cls.timeframe == "intraday"
    interval = '5m' if is_intraday else '1D'
    default_days = 30 if is_intraday else 365

    today = date.today()
    start = start_date or (today - timedelta(days=default_days)).isoformat()
    end = end_date or today.isoformat()

    df: pd.DataFrame = Quote(symbol=symbol, source='VCI').history(start=start, end=end, interval=interval)

    if df is None or df.empty:
        raise ValueError(f'No data returned for {symbol}')

    if strategy_name == 'rsi_divergence':
        df['RSI'] = talib.RSI(df['close'], timeperiod=14)
        df = df.dropna(subset=['RSI']).reset_index(drop=True)
    else:
        df = df.dropna(subset=['close']).reset_index(drop=True)

    if len(df) < 30:
        raise ValueError(
            f'Insufficient data for backtest: only {len(df)} candles (need 30)'
        )

    strategy = strategy_cls()
    return strategy.backtest(df, symbol=symbol, initial_capital=initial_capital)
