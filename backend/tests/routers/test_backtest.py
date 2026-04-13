import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.algorithms.base import BacktestResult, Trade

client = TestClient(app)


def _mock_result(symbol: str = 'VGI') -> BacktestResult:
    return BacktestResult(
        symbol=symbol,
        strategy='RSIStrategy',
        start_date='2024-01-01',
        end_date='2024-12-31',
        initial_capital=100_000_000.0,
        final_value=118_500_000.0,
        pnl=18_500_000.0,
        pnl_pct=18.5,
        win_rate=62.5,
        max_drawdown=-8.3,
        total_trades=8,
        trades=[
            Trade(action='buy', date='2024-02-15', price=24500.0, shares=4081, pnl=None),
            Trade(action='sell', date='2024-03-01', price=26200.0, shares=4081, pnl=6_937_700.0),
        ],
    )


@patch('app.routers.backtest.run_backtest')
def test_backtest_returns_200(mock_run):
    mock_run.return_value = _mock_result()
    response = client.get('/backtest/VGI')
    assert response.status_code == 200
    data = response.json()
    assert data['symbol'] == 'VGI'
    assert data['strategy'] == 'RSIStrategy'
    assert data['pnl'] == 18_500_000.0
    assert len(data['trades']) == 2


@patch('app.routers.backtest.run_backtest')
def test_backtest_passes_all_query_params(mock_run):
    mock_run.return_value = _mock_result()
    client.get('/backtest/VGI?strategy=rsi_divergence&start=2024-01-01&end=2024-06-30&capital=50000000')
    mock_run.assert_called_once_with(
        symbol='VGI',
        strategy_name='rsi_divergence',
        start_date='2024-01-01',
        end_date='2024-06-30',
        initial_capital=50_000_000.0,
    )


@patch('app.routers.backtest.run_backtest')
def test_backtest_returns_400_on_value_error(mock_run):
    mock_run.side_effect = ValueError('No data returned for FAKE')
    response = client.get('/backtest/FAKE')
    assert response.status_code == 400
    assert 'No data returned for FAKE' in response.json()['detail']


@patch('app.routers.backtest.run_backtest')
def test_backtest_default_strategy_is_rsi_divergence(mock_run):
    mock_run.return_value = _mock_result()
    client.get('/backtest/VGI')
    assert mock_run.call_args.kwargs['strategy_name'] == 'rsi_divergence'
