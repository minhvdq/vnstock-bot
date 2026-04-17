import asyncio
import pytest
from unittest.mock import patch, AsyncMock
import app.workers.intraday_worker as iw


_next_user_id = 1


class _User:
    def __init__(self, chat_id, stocks):
        global _next_user_id
        self.id = _next_user_id
        _next_user_id += 1
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


@pytest.fixture(autouse=True)
def reset_dedup():
    iw._seen.clear()
    iw._seen_date = ''
    yield
    iw._seen.clear()
    iw._seen_date = ''


@pytest.fixture(autouse=True)
def patch_paper_trading():
    """Prevent paper trading service from touching the database in unit tests."""
    with patch('app.workers.intraday_worker.paper_trading_service.on_signal', new_callable=AsyncMock), \
         patch('app.workers.intraday_worker.paper_trading_service.check_positions', new_callable=AsyncMock):
        yield


# ── signal fires ──────────────────────────────────────────────────────────────

def test_fires_signal_on_new_divergence():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_called_once()


def test_suppresses_duplicate_divergence():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        users = lambda: [_User('111', ['VGI'])]
        asyncio.run(iw._poll_once(get_users=users))
        asyncio.run(iw._poll_once(get_users=users))
    mock_send.assert_called_once()


def test_suppresses_when_no_divergence():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=None), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()


def test_dedup_resets_on_date_change():
    iw._seen.add(('VGI', 5, 20))
    iw._seen_date = '2024-01-01'

    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.intraday_worker.date') as mock_date:
        mock_date.today.return_value.isoformat.return_value = '2024-01-02'
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_called_once()


# ── user filtering ────────────────────────────────────────────────────────────

def test_skips_user_with_no_chat_id():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi') as mock_fetch, \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(iw._poll_once(get_users=lambda: [_User('', ['VGI']), _User(None, ['VGI'])]))
    mock_fetch.assert_not_called()
    mock_send.assert_not_called()


def test_multiple_users_same_stock():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        users = [_User('111', ['VGI']), _User('222', ['VGI']), _User('333', ['VGI'])]
        asyncio.run(iw._poll_once(get_users=lambda: users))
    chat_ids = mock_send.call_args[0][0]
    assert set(chat_ids) == {'111', '222', '333'}


def test_no_users():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi') as mock_fetch, \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(iw._poll_once(get_users=lambda: []))
    mock_fetch.assert_not_called()
    mock_send.assert_not_called()


# ── error handling ────────────────────────────────────────────────────────────

def test_continues_on_stock_fetch_error():
    records = _make_records()
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi',
               side_effect=[Exception('API error'), records]), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        users = [_User('111', ['VGI', 'VNM'])]
        asyncio.run(iw._poll_once(get_users=lambda: users))
    assert mock_send.call_count == 1


def test_injectable_get_users():
    custom_users = [_User('999', ['VGI'])]
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker._has_divergence_at', return_value=_mock_divergence()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(iw._poll_once(get_users=lambda: custom_users))
    chat_ids = mock_send.call_args[0][0]
    assert '999' in chat_ids
