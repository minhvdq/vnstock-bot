import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock
import app.workers.intraday_worker as iw

ICT = timezone(timedelta(hours=7))

_next_user_id = 100


class _User:
    def __init__(self, chat_id, stocks):
        global _next_user_id
        self.id = _next_user_id
        _next_user_id += 1
        self.chat_id = chat_id
        self.stocks = stocks


@pytest.fixture(autouse=True)
def patch_paper_trading():
    with patch('app.workers.intraday_worker.paper_trading_service.on_signal', new_callable=AsyncMock), \
         patch('app.workers.intraday_worker.paper_trading_service.check_positions', new_callable=AsyncMock):
        yield


@pytest.fixture(autouse=True)
def reset_intraday_fired():
    """Clear the once-per-day guard between tests."""
    iw._intraday_fired.clear()
    yield
    iw._intraday_fired.clear()


def _make_records(n=30, close=24500.0):
    return [
        {'time': f'2024-01-01 {i:02d}:00', 'open': close, 'high': close + 0.5,
         'low': close - 0.5, 'close': close, 'volume': 1000, 'RSI': 50.0}
        for i in range(n)
    ]


def _make_stub_strategy(signal: int):
    from app.algorithms.base import BaseStrategy

    class StubIntraday(BaseStrategy):
        timeframe = "intraday"
        display_name = "Stub Intraday"
        exit_rules = {"stop_loss_pct": -0.02, "take_profit_pct": 0.04, "max_days": 1, "eod_close": True}

        def generate_signals(self, df):
            df = df.copy()
            df['signal'] = 0
            if len(df) > 0:
                df.iloc[-1, df.columns.get_loc('signal')] = signal
            return df

    return StubIntraday


# ── _poll_once ────────────────────────────────────────────────────────────────

def test_fires_signal_when_intraday_strategy_returns_buy():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.intraday_worker.STRATEGIES', {'vol_break': _make_stub_strategy(1)}):
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_called_once()


def test_no_signal_when_strategy_returns_zero():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.intraday_worker.STRATEGIES', {'vol_break': _make_stub_strategy(0)}):
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()


def test_once_per_day_dedup_prevents_second_fire():
    """Same symbol + strategy fires once; second poll does not re-fire."""
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.intraday_worker.STRATEGIES', {'vol_break': _make_stub_strategy(1)}):
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    assert mock_send.call_count == 1  # fired only on first poll


def test_skips_empty_data():
    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=None), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send:
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()


def test_daily_strategies_ignored_by_intraday_worker():
    """Strategies with timeframe='daily' must not run in intraday_worker."""
    from app.algorithms.base import BaseStrategy

    class DailyStub(BaseStrategy):
        timeframe = "daily"
        display_name = "Daily Stub"
        exit_rules = {"stop_loss_pct": -0.07, "take_profit_pct": 0.15, "max_days": 30, "eod_close": False}
        def generate_signals(self, df):
            df = df.copy()
            df['signal'] = 1
            return df

    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.intraday_worker.STRATEGIES', {'daily_strat': DailyStub}):
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()
