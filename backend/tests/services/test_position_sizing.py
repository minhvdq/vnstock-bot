from unittest.mock import patch, MagicMock
from app.services.position_sizing import (
    get_strategy_position_pct, BASE_DAILY_PCT, BASE_INTRADAY_PCT, MIN_PCT, MAX_PCT
)


def _mock_rows(win_rates):
    rows = []
    for wr in win_rates:
        r = MagicMock()
        r.win_rate = wr
        rows.append(r)
    return rows


@patch('app.services.position_sizing.SessionLocal')
def test_no_backtest_data_returns_base_daily(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_session_cls.return_value = mock_db

    result = get_strategy_position_pct('rsi_divergence', 'daily')
    assert result == BASE_DAILY_PCT


@patch('app.services.position_sizing.SessionLocal')
def test_no_backtest_data_returns_base_intraday(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = []
    mock_session_cls.return_value = mock_db

    result = get_strategy_position_pct('volume_breakout', 'intraday')
    assert result == BASE_INTRADAY_PCT


@patch('app.services.position_sizing.SessionLocal')
def test_high_win_rate_scales_up(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = (
        _mock_rows([70.0, 72.0, 68.0])  # avg 70% >> 55% pivot
    )
    mock_session_cls.return_value = mock_db

    result = get_strategy_position_pct('rsi_divergence', 'daily')
    assert result > BASE_DAILY_PCT
    assert result <= MAX_PCT


@patch('app.services.position_sizing.SessionLocal')
def test_low_win_rate_scales_down(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = (
        _mock_rows([35.0, 40.0, 38.0])  # avg ~37.7% << 55% pivot
    )
    mock_session_cls.return_value = mock_db

    result = get_strategy_position_pct('rsi_divergence', 'daily')
    assert result < BASE_DAILY_PCT
    assert result >= MIN_PCT


@patch('app.services.position_sizing.SessionLocal')
def test_result_capped_at_max(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.all.return_value = (
        _mock_rows([99.0] * 10)  # extremely high win rate
    )
    mock_session_cls.return_value = mock_db

    result = get_strategy_position_pct('rsi_divergence', 'daily')
    assert result == MAX_PCT


@patch('app.services.position_sizing.SessionLocal')
def test_db_error_returns_base(mock_session_cls):
    mock_db = MagicMock()
    mock_db.query.side_effect = Exception('DB connection failed')
    mock_session_cls.return_value = mock_db

    result = get_strategy_position_pct('rsi_divergence', 'daily')
    assert result == BASE_DAILY_PCT
