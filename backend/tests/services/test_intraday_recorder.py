import pytest
from unittest.mock import patch, MagicMock
from app.services.intraday_recorder import record_bars


def _make_records(n: int = 3) -> list[dict]:
    import pandas as pd
    times = pd.date_range('2024-01-02 09:00', periods=n, freq='1min')
    return [
        {
            'time': t,
            'open': 1250.0, 'high': 1255.0, 'low': 1245.0, 'close': 1252.0,
            'volume': 100, 'RSI': 52.0,
        }
        for t in times
    ]


@patch('app.services.intraday_recorder.SessionLocal')
def test_record_bars_inserts_rows(mock_session_cls):
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result
    mock_session_cls.return_value = mock_db

    count = record_bars('VN30F1M', _make_records(3))
    assert count == 3
    mock_db.commit.assert_called_once()
    mock_db.close.assert_called_once()


@patch('app.services.intraday_recorder.SessionLocal')
def test_record_bars_empty_list_skips_db(mock_session_cls):
    count = record_bars('VN30F1M', [])
    mock_session_cls.assert_not_called()
    assert count == 0


@patch('app.services.intraday_recorder.SessionLocal')
def test_record_bars_rolls_back_on_error(mock_session_cls):
    mock_db = MagicMock()
    mock_db.execute.side_effect = Exception('DB down')
    mock_session_cls.return_value = mock_db

    count = record_bars('VN30F1M', _make_records(2))
    assert count == 0
    mock_db.rollback.assert_called_once()
    mock_db.close.assert_called_once()


@patch('app.services.intraday_recorder.SessionLocal')
def test_record_bars_skips_records_missing_time(mock_session_cls):
    bad_records = [{'open': 1.0, 'high': 1.0, 'low': 1.0, 'close': 1.0, 'RSI': 50.0}]
    count = record_bars('VN30F1M', bad_records)
    mock_session_cls.assert_not_called()
    assert count == 0


@patch('app.services.intraday_recorder.SessionLocal')
def test_record_bars_handles_string_time(mock_session_cls):
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result
    mock_session_cls.return_value = mock_db

    records = [{'time': '2024-01-02 09:00:00', 'open': 1.0, 'high': 1.0,
                'low': 1.0, 'close': 1.0, 'volume': 10, 'RSI': 50.0}]
    count = record_bars('VN30F1M', records)
    assert count == 1
