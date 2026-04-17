import pytest
from unittest.mock import patch, MagicMock
from app.services.batch_backtest_service import _throttled_run_one as _run_one, get_results


def _mock_result(pnl_pct=10.0):
    r = MagicMock()
    r.initial_capital = 100_000_000.0
    r.final_value = 110_000_000.0
    r.pnl = 10_000_000.0
    r.pnl_pct = pnl_pct
    r.win_rate = 60.0
    r.max_drawdown = -5.0
    r.total_trades = 4
    return r


@patch('app.services.batch_backtest_service.run_backtest')
def test_run_one_success(mock_backtest):
    mock_backtest.return_value = _mock_result(12.5)
    result = _run_one('VCB', 'rsi_divergence', '2024-01-01', '2024-12-31')
    assert result['symbol'] == 'VCB'
    assert result['strategy_name'] == 'rsi_divergence'
    assert result['pnl_pct'] == 12.5
    assert result['error'] is None


@patch('app.services.batch_backtest_service.run_backtest')
def test_run_one_captures_error(mock_backtest):
    mock_backtest.side_effect = ValueError('No data returned for XYZ')
    result = _run_one('XYZ', 'rsi_divergence', '2024-01-01', '2024-12-31')
    assert result['symbol'] == 'XYZ'
    assert result['error'] is not None
    assert 'No data' in result['error']
    assert result['pnl_pct'] == 0.0


@patch('app.services.batch_backtest_service.run_backtest')
def test_run_one_captures_system_exit(mock_backtest):
    """vnstock calls sys.exit() on rate limit — must be caught, not crash batch."""
    mock_backtest.side_effect = SystemExit('Rate limit exceeded.')
    result = _run_one('VCB', 'rsi_divergence', '2024-01-01', '2024-12-31')
    assert result['error'] is not None
    assert result['pnl_pct'] == 0.0


@patch('app.services.batch_backtest_service.SessionLocal')
def test_get_results_returns_sorted_list(mock_session_cls):
    mock_row = MagicMock()
    mock_row.symbol = 'VCB'
    mock_row.strategy_name = 'rsi_divergence'
    mock_row.pnl_pct = 15.3
    mock_row.win_rate = 62.5
    mock_row.max_drawdown = -4.2
    mock_row.total_trades = 5
    mock_row.pnl = 15_300_000.0
    mock_row.run_at = None
    mock_row.error = None

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_row]
    mock_session_cls.return_value = mock_db

    results = get_results('2024-01-01', '2024-12-31')
    assert len(results) == 1
    assert results[0]['symbol'] == 'VCB'
    assert results[0]['pnl_pct'] == 15.3


@patch('app.services.batch_backtest_service.SessionLocal')
def test_get_results_empty(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_session_cls.return_value = mock_db

    results = get_results('2024-01-01', '2024-12-31')
    assert results == []
