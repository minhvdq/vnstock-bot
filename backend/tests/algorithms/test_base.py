import pandas as pd
import pytest
from app.algorithms.base import BaseStrategy, BacktestResult, Trade


class _BuyFirstSellLast(BaseStrategy):
    """Test strategy: signal=1 on first candle, signal=-1 on last candle."""
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        if len(df) >= 2:
            df.iloc[0, df.columns.get_loc('signal')] = 1
            df.iloc[-1, df.columns.get_loc('signal')] = -1
        return df


class _NoSignals(BaseStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        return df


def _make_df(prices: list) -> pd.DataFrame:
    return pd.DataFrame({
        'time': [f'2024-01-{i+1:02d}' for i in range(len(prices))],
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
    })


def test_backtest_profitable_trade():
    df = _make_df([100.0, 110.0, 120.0, 130.0, 140.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.symbol == 'TST'
    assert result.strategy == '_BuyFirstSellLast'
    assert result.total_trades == 1
    assert result.pnl > 0
    assert result.win_rate == 100.0
    assert result.pnl_pct > 0


def test_backtest_losing_trade():
    df = _make_df([100.0, 90.0, 80.0, 70.0, 60.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.total_trades == 1
    assert result.pnl < 0
    assert result.win_rate == 0.0


def test_backtest_no_signals():
    df = _make_df([100.0, 110.0, 120.0])
    result = _NoSignals().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.total_trades == 0
    assert result.pnl == 0.0
    assert result.win_rate == 0.0
    assert result.trades == []


def test_backtest_max_drawdown_is_negative():
    # Buys at 100, price rises to 150 then crashes — drawdown should be negative
    df = _make_df([100.0, 150.0, 50.0, 80.0, 60.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.max_drawdown < 0


def test_backtest_trade_log_structure():
    df = _make_df([100.0, 110.0, 120.0, 130.0, 140.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    buys = [t for t in result.trades if t.action == 'buy']
    sells = [t for t in result.trades if t.action == 'sell']
    assert len(buys) == 1
    assert len(sells) == 1
    assert buys[0].pnl is None
    assert sells[0].pnl is not None
    assert sells[0].pnl > 0


def test_backtest_pnl_matches_final_value():
    df = _make_df([100.0, 110.0, 120.0, 130.0, 140.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert abs(result.final_value - result.initial_capital - result.pnl) < 0.01
