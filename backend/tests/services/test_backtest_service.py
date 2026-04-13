import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from app.services.backtest_service import run_backtest
from app.algorithms.base import BacktestResult


def _daily_df(n: int = 60) -> pd.DataFrame:
    prices = [100.0 + i * 0.5 for i in range(n)]
    return pd.DataFrame({
        'time': [f'2024-{i+1:04d}' for i in range(n)],
        'open': prices,
        'high': [p + 1 for p in prices],
        'low': [p - 1 for p in prices],
        'close': prices,
        'volume': [1000] * n,
    })


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_returns_backtest_result(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = _daily_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)

    result = run_backtest('VGI', 'rsi_divergence', '2024-01-01', '2024-12-31')

    assert isinstance(result, BacktestResult)
    assert result.symbol == 'VGI'
    assert result.strategy == 'RSIStrategy'


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_raises_on_empty_df(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = pd.DataFrame()

    with pytest.raises(ValueError, match='No data returned for VGI'):
        run_backtest('VGI', 'rsi_divergence', '2024-01-01', '2024-12-31')


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_raises_on_unknown_strategy(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = _daily_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)

    with pytest.raises(ValueError, match='Unknown strategy: fake_strategy'):
        run_backtest('VGI', 'fake_strategy', '2024-01-01', '2024-12-31')


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_raises_on_insufficient_data(mock_quote_cls, mock_talib):
    # 10 rows from vnstock → all NaN RSI → 0 rows after dropna → < 30 minimum
    mock_quote_cls.return_value.history.return_value = _daily_df(10)
    mock_talib.RSI.return_value = pd.Series([float('nan')] * 10)

    with pytest.raises(ValueError, match='Insufficient data'):
        run_backtest('VGI', 'rsi_divergence', '2024-01-01', '2024-01-10')


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_uses_default_dates_when_omitted(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = _daily_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)

    result = run_backtest('VGI', 'rsi_divergence')  # no start/end

    assert isinstance(result, BacktestResult)
    call_kwargs = mock_quote_cls.return_value.history.call_args.kwargs
    assert 'start' in call_kwargs and 'end' in call_kwargs
