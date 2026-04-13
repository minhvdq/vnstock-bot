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
    Fetch daily OHLCV for `symbol`, run the named strategy's backtest,
    and return a BacktestResult with full metrics and trade log.

    Raises ValueError for: unknown strategy, empty data, insufficient data.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f'Unknown strategy: {strategy_name}')

    today = date.today()
    start = start_date or (today - timedelta(days=365)).isoformat()
    end = end_date or today.isoformat()

    df: pd.DataFrame = Quote(symbol=symbol, source='VCI').history(start=start, end=end, interval='1D')

    if df is None or df.empty:
        raise ValueError(f'No data returned for {symbol}')

    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df = df.dropna(subset=['RSI']).reset_index(drop=True)

    if len(df) < 30:
        raise ValueError(
            f'Insufficient data for backtest: only {len(df)} candles after RSI warmup (need 30)'
        )

    strategy = STRATEGIES[strategy_name]()
    return strategy.backtest(df, symbol=symbol, initial_capital=initial_capital)
