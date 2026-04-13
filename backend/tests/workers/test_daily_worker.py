import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
import app.workers.daily_worker as dw

ICT = timezone(timedelta(hours=7))


class _User:
    def __init__(self, chat_id, stocks):
        self.chat_id = chat_id
        self.stocks = stocks


def _mock_divergence(prefix=5, suffix=20, kind='bearish'):
    return {'prefixIndex': prefix, 'suffixIndex': suffix, 'type': kind}


def _make_records(n=25, close=24500.0):
    return [
        {'time': f'2024-01-{i+1:02d}', 'open': close, 'high': close + 1,
         'low': close - 1, 'close': close, 'RSI': 50.0}
        for i in range(n)
    ]


# ── _seconds_until_next_signal ────────────────────────────────────────────────

def test_seconds_until_next_signal_before_cutoff():
    # 2:00 PM ICT → target is 3:05 PM today = 65 minutes away
    fake_now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=ICT)
    with patch('app.workers.daily_worker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        secs = dw._seconds_until_next_signal()
    assert 3600 < secs < 3960  # between 60 and 66 minutes


def test_seconds_until_next_signal_after_cutoff():
    # 3:06 PM ICT → target is 3:05 PM tomorrow = ~23h59m away
    fake_now = datetime(2024, 1, 15, 15, 6, 0, tzinfo=ICT)
    with patch('app.workers.daily_worker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        secs = dw._seconds_until_next_signal()
    assert 86300 < secs < 86400  # ~23h59m


def test_seconds_until_next_signal_at_exact_cutoff():
    # Exactly 3:05 PM ICT → now >= target → wait until tomorrow
    fake_now = datetime(2024, 1, 15, 15, 5, 0, tzinfo=ICT)
    with patch('app.workers.daily_worker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        secs = dw._seconds_until_next_signal()
    assert secs > 86000  # ~24 hours


# ── _run_daily_check ──────────────────────────────────────────────────────────

def test_fires_signal_on_divergence():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.daily_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_called_once()


def test_no_signal_when_no_divergence():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.daily_worker._has_divergence_at', return_value=None), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()


def test_skips_empty_or_insufficient_data():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=None), \
         patch('app.workers.daily_worker._has_divergence_at') as mock_div, \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('111', ['VGI'])]))
    mock_div.assert_not_called()
    mock_send.assert_not_called()


def test_continues_on_symbol_error():
    records = _make_records()
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi',
               side_effect=[Exception('API error'), records]), \
         patch('app.workers.daily_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send:
        users = [_User('111', ['VGI', 'VNM'])]
        asyncio.run(dw._run_daily_check(get_users=lambda: users))
    assert mock_send.call_count == 1


def test_injectable_get_users():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.daily_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('999', ['VGI'])]))
    chat_ids = mock_send.call_args[0][0]
    assert '999' in chat_ids
