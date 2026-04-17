import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
import app.workers.daily_worker as dw

ICT = timezone(timedelta(hours=7))

_next_user_id = 1


class _User:
    def __init__(self, chat_id, stocks):
        global _next_user_id
        self.id = _next_user_id
        _next_user_id += 1
        self.chat_id = chat_id
        self.stocks = stocks


@pytest.fixture(autouse=True)
def patch_paper_trading():
    with patch('app.workers.daily_worker.paper_trading_service.on_signal', new_callable=AsyncMock):
        yield


def _make_records(n=25, close=24500.0):
    return [
        {'time': f'2024-01-{i+1:02d}', 'open': close, 'high': close + 1,
         'low': close - 1, 'close': close, 'volume': 1000, 'RSI': 50.0}
        for i in range(n)
    ]


def _make_stub_strategy(signal: int):
    """Return a strategy class whose generate_signals always returns last bar = signal."""
    import pandas as pd
    from app.algorithms.base import BaseStrategy

    class StubStrategy(BaseStrategy):
        timeframe = "daily"
        display_name = "Stub"
        exit_rules = {"stop_loss_pct": -0.07, "take_profit_pct": 0.15, "max_days": 30, "eod_close": False}

        def generate_signals(self, df):
            df = df.copy()
            df['signal'] = 0
            if len(df) > 0:
                df.iloc[-1, df.columns.get_loc('signal')] = signal
            return df

    return StubStrategy


# ── _seconds_until_next_signal ────────────────────────────────────────────────

def test_seconds_until_next_signal_before_cutoff():
    fake_now = datetime(2024, 1, 15, 14, 0, 0, tzinfo=ICT)
    with patch('app.workers.daily_worker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        secs = dw._seconds_until_next_signal()
    assert 3600 < secs < 3960


def test_seconds_until_next_signal_after_cutoff():
    fake_now = datetime(2024, 1, 15, 15, 6, 0, tzinfo=ICT)
    with patch('app.workers.daily_worker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        secs = dw._seconds_until_next_signal()
    assert 86300 < secs < 86400


def test_seconds_until_next_signal_at_exact_cutoff():
    fake_now = datetime(2024, 1, 15, 15, 5, 0, tzinfo=ICT)
    with patch('app.workers.daily_worker.datetime') as mock_dt:
        mock_dt.now.return_value = fake_now
        secs = dw._seconds_until_next_signal()
    assert secs > 86000


# ── _run_daily_check ──────────────────────────────────────────────────────────

def test_fires_signal_when_strategy_returns_buy():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.daily_worker.STRATEGIES', {'test_strat': _make_stub_strategy(signal=1)}):
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_called_once()


def test_no_signal_when_strategy_returns_zero():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.daily_worker.STRATEGIES', {'test_strat': _make_stub_strategy(signal=0)}):
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()


def test_skips_empty_data():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=None), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()


def test_continues_on_symbol_error():
    records = _make_records()
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi',
               side_effect=[Exception('API error'), records]), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.daily_worker.STRATEGIES', {'test_strat': _make_stub_strategy(signal=1)}):
        users = [_User('111', ['VGI', 'VNM'])]
        asyncio.run(dw._run_daily_check(get_users=lambda: users))
    assert mock_send.call_count == 1


def test_injectable_get_users():
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.daily_worker.STRATEGIES', {'test_strat': _make_stub_strategy(signal=1)}):
        asyncio.run(dw._run_daily_check(get_users=lambda: [_User('999', ['VGI'])]))
    chat_ids = mock_send.call_args[0][0]
    assert '999' in chat_ids
