import asyncio
import pandas as pd
import pytest
from unittest.mock import patch, AsyncMock
from app.services.signal_service import (
    build_symbol_map,
    fetch_ohlcv_with_rsi,
    fetch_intraday_ohlcv_with_rsi,
    format_signal_message,
    send_signal,
)


class _User:
    def __init__(self, chat_id, stocks):
        self.chat_id = chat_id
        self.stocks = stocks


# ── build_symbol_map ──────────────────────────────────────────────────────────

def test_build_symbol_map_excludes_no_chat_id():
    users = [_User(chat_id='', stocks=['VGI']), _User(chat_id=None, stocks=['VNM'])]
    assert build_symbol_map(users) == {}


def test_build_symbol_map_multiple_users_same_stock():
    users = [
        _User(chat_id='111', stocks=['VGI']),
        _User(chat_id='222', stocks=['VGI', 'VNM']),
    ]
    result = build_symbol_map(users)
    assert set(result['VGI']) == {'111', '222'}
    assert result['VNM'] == ['222']


def test_build_symbol_map_empty_users():
    assert build_symbol_map([]) == {}


# ── format_signal_message ─────────────────────────────────────────────────────

def test_format_bearish_intraday():
    msg = format_signal_message('VGI', 'bearish', 'Intraday', 24500.0, '14:32')
    assert '🔴' in msg
    assert 'SELL' in msg
    assert 'VGI' in msg
    assert 'Intraday' in msg
    assert 'Bearish' in msg


def test_format_bullish_daily():
    msg = format_signal_message('VNM', 'bullish', 'Daily', 81200.0, '15:05')
    assert '🟢' in msg
    assert 'BUY' in msg
    assert 'VNM' in msg
    assert 'Daily' in msg
    assert 'Bullish' in msg


def test_format_price_formatting():
    msg = format_signal_message('VGI', 'bearish', 'Intraday', 24500.0, '14:32')
    assert '24,500 VND' in msg


# ── fetch_ohlcv_with_rsi ──────────────────────────────────────────────────────

@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_ohlcv_returns_none_on_empty_df(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = pd.DataFrame()
    assert fetch_ohlcv_with_rsi('VGI', '1D', '2024-01-01', '2024-12-31') is None


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_ohlcv_returns_none_on_insufficient_rsi(mock_quote_cls, mock_talib):
    n = 5
    df = pd.DataFrame({
        'time': [f'2024-01-0{i+1}' for i in range(n)],
        'open': [100.0] * n, 'high': [101.0] * n,
        'low': [99.0] * n, 'close': [100.0] * n,
    })
    mock_quote_cls.return_value.history.return_value = df
    mock_talib.RSI.return_value = pd.Series([float('nan')] * n)
    assert fetch_ohlcv_with_rsi('VGI', '1D', '2024-01-01', '2024-01-05') is None


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_ohlcv_returns_records_with_rsi(mock_quote_cls, mock_talib):
    n = 10
    df = pd.DataFrame({
        'time': [f'2024-01-{i+1:02d}' for i in range(n)],
        'open': [100.0] * n, 'high': [101.0] * n,
        'low': [99.0] * n, 'close': [100.0] * n,
    })
    mock_quote_cls.return_value.history.return_value = df
    mock_talib.RSI.return_value = pd.Series([50.0] * n)
    result = fetch_ohlcv_with_rsi('VGI', '1D', '2024-01-01', '2024-01-10')
    assert result is not None
    assert len(result) == n
    assert result[0]['RSI'] == 50.0


# ── send_signal ───────────────────────────────────────────────────────────────

def test_send_signal_calls_send_message_for_each_chat_id():
    with patch('app.services.signal_service.send_message', new_callable=AsyncMock) as mock_send, \
         patch('asyncio.sleep', new_callable=AsyncMock):
        asyncio.run(send_signal(['111', '222', '333'], 'VGI', 'bearish', 'Intraday', 24500.0, '14:32'))
    assert mock_send.call_count == 3


def test_send_signal_empty_chat_ids():
    with patch('app.services.signal_service.send_message', new_callable=AsyncMock) as mock_send:
        asyncio.run(send_signal([], 'VGI', 'bearish', 'Intraday', 24500.0, '14:32'))
    mock_send.assert_not_called()


def test_send_signal_continues_on_failure():
    with patch('app.services.signal_service.send_message', new_callable=AsyncMock) as mock_send, \
         patch('asyncio.sleep', new_callable=AsyncMock):
        mock_send.side_effect = [Exception('network error'), None, None]
        asyncio.run(send_signal(['111', '222', '333'], 'VGI', 'bearish', 'Intraday', 24500.0, '14:32'))
    assert mock_send.call_count == 3


def test_send_signal_rate_limit_delay():
    with patch('app.services.signal_service.send_message', new_callable=AsyncMock), \
         patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        asyncio.run(send_signal(['111', '222'], 'VGI', 'bearish', 'Intraday', 24500.0, '14:32'))
    assert mock_sleep.call_count == 2
    mock_sleep.assert_called_with(0.05)


# ── fetch_intraday_ohlcv_with_rsi ─────────────────────────────────────────────

def _make_tick_df(n: int = 60, price: float = 1250.0) -> pd.DataFrame:
    """Simulate KBS tick data: time, price, volume columns."""
    times = pd.date_range('2024-01-01 09:00', periods=n, freq='1min')
    return pd.DataFrame({
        'time': times,
        'price': [price] * n,
        'volume': [100] * n,
        'match_type': ['M'] * n,
        'id': range(n),
    })


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_intraday_returns_none_when_all_sources_empty(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.intraday.return_value = pd.DataFrame()
    assert fetch_intraday_ohlcv_with_rsi('VN30F1M') is None


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_intraday_resamples_to_1min_bars(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.intraday.return_value = _make_tick_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)
    result = fetch_intraday_ohlcv_with_rsi('VN30F1M')
    assert result is not None
    assert all('RSI' in r for r in result)
    assert result[0]['close'] == 1250.0
    assert result[0]['open'] == 1250.0


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_intraday_returns_none_after_rsi_warmup_drops_all(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.intraday.return_value = _make_tick_df(5)
    mock_talib.RSI.return_value = pd.Series([float('nan')] * 5)
    assert fetch_intraday_ohlcv_with_rsi('VN30F1M') is None


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_intraday_returns_none_on_unexpected_columns(mock_quote_cls, mock_talib):
    df = pd.DataFrame({'foo': [1, 2, 3], 'bar': [4, 5, 6]})
    mock_quote_cls.return_value.intraday.return_value = df
    assert fetch_intraday_ohlcv_with_rsi('VN30F1M') is None


@patch('app.services.signal_service.talib')
@patch('app.services.signal_service.Quote')
def test_fetch_intraday_falls_back_to_second_source(mock_quote_cls, mock_talib):
    """KBS returns empty → falls back to VCI."""
    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return pd.DataFrame()
        return _make_tick_df(60)

    mock_quote_cls.return_value.intraday.side_effect = side_effect
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)
    result = fetch_intraday_ohlcv_with_rsi('VN30F1M')
    assert result is not None
    assert call_count[0] == 2
