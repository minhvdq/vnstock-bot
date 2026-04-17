# Signal Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Phase 1 RSI divergence algorithm to a live Telegram signal delivery system with an intraday worker (5-min polls) and a daily worker (3:05 PM ICT).

**Architecture:** A shared `signal_service.py` provides four pure functions used by both workers: `build_symbol_map`, `fetch_ohlcv_with_rsi`, `format_signal_message`, and `send_signal`. The intraday worker holds module-level dedup state; the daily worker relies on its sleep schedule for once-per-day enforcement. Both workers use dependency injection for `get_users` so tests never touch the database.

**Tech Stack:** Python 3.11+, FastAPI, asyncio, vnstock (`Quote`), talib, httpx (Telegram), pytest

---

## File Map

**New files:**
- `backend/app/services/signal_service.py` — `build_symbol_map`, `fetch_ohlcv_with_rsi`, `format_signal_message`, `send_signal`
- `backend/app/workers/intraday_worker.py` — `_poll_once`, `intraday_worker`
- `backend/app/workers/daily_worker.py` — `_seconds_until_next_signal`, `_run_daily_check`, `daily_worker`
- `backend/tests/workers/__init__.py`
- `backend/tests/workers/test_intraday_worker.py`
- `backend/tests/workers/test_daily_worker.py`
- `backend/tests/services/test_signal_service.py`

**Modified files:**
- `backend/app/main.py` — swap worker imports and startup tasks

**Deleted:**
- `backend/app/workers/stock_worker.py`

---

## Task 1: Signal Service

**Files:**
- Create: `backend/app/services/signal_service.py`
- Create: `backend/tests/services/test_signal_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/test_signal_service.py`:

```python
import asyncio
import pandas as pd
import pytest
from unittest.mock import patch, AsyncMock
from app.services.signal_service import (
    build_symbol_map,
    fetch_ohlcv_with_rsi,
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/services/test_signal_service.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'build_symbol_map' from 'app.services.signal_service'`

- [ ] **Step 3: Create `backend/app/services/signal_service.py`**

```python
from __future__ import annotations
import asyncio
from datetime import date, timedelta
import talib
import pandas as pd
from vnstock import Quote
from app.utils.telegram import send_message


def build_symbol_map(users: list) -> dict[str, list[str]]:
    """
    Returns {symbol: [chat_id, ...]} for all users with a non-empty chat_id.
    Each symbol appears once; its value is all chat_ids watching it.
    """
    result: dict[str, list[str]] = {}
    for user in users:
        if not user.chat_id:
            continue
        for symbol in user.stocks:
            if symbol not in result:
                result[symbol] = []
            result[symbol].append(user.chat_id)
    return result


def fetch_ohlcv_with_rsi(
    symbol: str,
    interval: str,
    start: str,
    end: str,
) -> list[dict] | None:
    """
    Fetch OHLCV via vnstock, compute RSI via talib, drop NaN rows.
    Returns list[dict] with RSI field, or None if data is empty/insufficient.
    Both intraday and daily workers use this for a consistent data pipeline.
    """
    df: pd.DataFrame = Quote(symbol=symbol, source='VCI').history(
        start=start, end=end, interval=interval
    )
    if df is None or df.empty:
        return None
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df = df.dropna(subset=['RSI']).reset_index(drop=True)
    if len(df) < 2:
        return None
    return df.to_dict(orient='records')


def format_signal_message(
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
) -> str:
    """
    Format a Telegram signal message.

    Example:
        🔴 VGI — SELL signal
        Strategy: RSI Divergence (Bearish) | Intraday
        Price: 24,500 VND
        Time: 14:32 ICT
    """
    emoji = '🔴' if divergence_type == 'bearish' else '🟢'
    action = 'SELL' if divergence_type == 'bearish' else 'BUY'
    direction = 'Bearish' if divergence_type == 'bearish' else 'Bullish'
    return (
        f"{emoji} {symbol} — {action} signal\n"
        f"Strategy: RSI Divergence ({direction}) | {timeframe}\n"
        f"Price: {price:,.0f} VND\n"
        f"Time: {signal_time} ICT"
    )


async def send_signal(
    chat_ids: list[str],
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
) -> None:
    """
    Format the signal message and send to each chat_id.
    50ms delay between sends to stay under Telegram's rate limit.
    If one send fails, logs the error and continues to remaining chat_ids.
    No-op if chat_ids is empty.
    """
    if not chat_ids:
        return
    message = format_signal_message(symbol, divergence_type, timeframe, price, signal_time)
    for chat_id in chat_ids:
        try:
            await send_message(chat_id=chat_id, text=message)
        except Exception as e:
            print(f"Failed to send signal to {chat_id}: {e}")
        await asyncio.sleep(0.05)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/services/test_signal_service.py -v
```

Expected: All 13 tests PASS.

- [ ] **Step 5: Run full suite to confirm nothing broke**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: 46 passed (33 existing + 13 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/signal_service.py backend/tests/services/test_signal_service.py
git commit -m "feat: add signal_service with build_symbol_map, fetch_ohlcv_with_rsi, format and send"
```

---

## Task 2: Intraday Worker

**Files:**
- Create: `backend/app/workers/intraday_worker.py`
- Create: `backend/tests/workers/__init__.py`
- Create: `backend/tests/workers/test_intraday_worker.py`

- [ ] **Step 1: Create test scaffolding**

```bash
touch /Users/damianvu/Desktop/stock-bot-vn/backend/tests/workers/__init__.py
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/workers/test_intraday_worker.py`:

```python
import asyncio
import pytest
from unittest.mock import patch, AsyncMock
import app.workers.intraday_worker as iw


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


@pytest.fixture(autouse=True)
def reset_dedup():
    iw._seen.clear()
    iw._seen_date = ''
    yield
    iw._seen.clear()
    iw._seen_date = ''


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
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/workers/test_intraday_worker.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name '_poll_once' from 'app.workers.intraday_worker'`

- [ ] **Step 4: Create `backend/app/workers/intraday_worker.py`**

```python
from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.algorithms.rsi_divergence import _has_divergence_at

ICT = timezone(timedelta(hours=7))

_seen: set[tuple] = set()    # (symbol, prefix_idx, suffix_idx)
_seen_date: str = ''          # YYYY-MM-DD, cleared when date changes


async def _poll_once(get_users=get_all_users) -> None:
    """One intraday poll cycle. Testable entry point for the worker loop."""
    global _seen, _seen_date

    today = date.today().isoformat()
    if today != _seen_date:
        _seen.clear()
        _seen_date = today

    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '1m', today, today)
            if not records_list:
                continue
            divergence = _has_divergence_at(records_list, len(records_list) - 1)
            if divergence is None:
                continue
            key = (symbol, divergence['prefixIndex'], divergence['suffixIndex'])
            if key in _seen:
                continue
            _seen.add(key)
            price = float(records_list[-1]['close'])
            signal_time = datetime.now(ICT).strftime('%H:%M')
            await send_signal(chat_ids, symbol, divergence['type'], 'Intraday', price, signal_time)
        except Exception as e:
            print(f'Intraday worker error for {symbol}: {e}')


async def intraday_worker(get_users=get_all_users) -> None:
    """Background task: poll every 5 minutes indefinitely."""
    while True:
        try:
            await _poll_once(get_users)
        except (OperationalError, DisconnectionError) as e:
            print(f'Intraday worker DB error: {e}')
            await asyncio.sleep(10)
            continue
        except Exception as e:
            print(f'Intraday worker error: {e}')
        await asyncio.sleep(300)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/workers/test_intraday_worker.py -v
```

Expected: All 9 tests PASS.

- [ ] **Step 6: Run full suite**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: 55 passed (46 + 9 new).

- [ ] **Step 7: Commit**

```bash
git add backend/app/workers/intraday_worker.py \
        backend/tests/workers/__init__.py \
        backend/tests/workers/test_intraday_worker.py
git commit -m "feat: add intraday_worker with 5-min polling and dedup"
```

---

## Task 3: Daily Worker

**Files:**
- Create: `backend/app/workers/daily_worker.py`
- Create: `backend/tests/workers/test_daily_worker.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/workers/test_daily_worker.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/workers/test_daily_worker.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name '_seconds_until_next_signal'`

- [ ] **Step 3: Create `backend/app/workers/daily_worker.py`**

```python
from __future__ import annotations
import asyncio
from datetime import date, datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.algorithms.rsi_divergence import _has_divergence_at

ICT = timezone(timedelta(hours=7))
SIGNAL_HOUR = 15
SIGNAL_MINUTE = 5


def _seconds_until_next_signal() -> float:
    """
    Returns seconds until next 3:05 PM ICT.
    If now >= 3:05 PM ICT today, returns seconds until 3:05 PM tomorrow.
    Exact 3:05 PM counts as past (fires tomorrow, never twice today).
    """
    now = datetime.now(ICT)
    target = now.replace(hour=SIGNAL_HOUR, minute=SIGNAL_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_daily_check(get_users=get_all_users) -> None:
    """One daily signal check. Testable entry point for the worker loop."""
    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    today = date.today().isoformat()
    start = (date.today() - timedelta(days=90)).isoformat()

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '1D', start, today)
            if not records_list:
                continue
            divergence = _has_divergence_at(records_list, len(records_list) - 1)
            if divergence is None:
                continue
            price = float(records_list[-1]['close'])
            signal_time = datetime.now(ICT).strftime('%H:%M')
            await send_signal(chat_ids, symbol, divergence['type'], 'Daily', price, signal_time)
        except Exception as e:
            print(f'Daily worker error for {symbol}: {e}')


async def daily_worker(get_users=get_all_users) -> None:
    """Background task: fire once daily at 3:05 PM ICT indefinitely."""
    while True:
        await asyncio.sleep(_seconds_until_next_signal())
        try:
            await _run_daily_check(get_users)
        except (OperationalError, DisconnectionError) as e:
            print(f'Daily worker DB error: {e}')
            await asyncio.sleep(60)
            continue
        except Exception as e:
            print(f'Daily worker error: {e}')
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/workers/test_daily_worker.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: 63 passed (55 + 8 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/daily_worker.py \
        backend/tests/workers/test_daily_worker.py
git commit -m "feat: add daily_worker firing at 3:05 PM ICT with 90-day OHLCV check"
```

---

## Task 4: Wire Up and Cleanup

**Files:**
- Modify: `backend/app/main.py`
- Delete: `backend/app/workers/stock_worker.py`

- [ ] **Step 1: Update `backend/app/main.py`**

Current import line in `main.py`:
```python
from app.workers.stock_worker import stock_worker
```

Replace with:
```python
from app.workers.intraday_worker import intraday_worker
from app.workers.daily_worker import daily_worker
```

Current startup task in `main.py`:
```python
asyncio.create_task(stock_worker())
```

Replace with:
```python
asyncio.create_task(intraday_worker())
asyncio.create_task(daily_worker())
```

The full updated `startup_event` function:
```python
@app.on_event("startup")
async def startup_event():
    try:
        asyncio.create_task(intraday_worker())
        asyncio.create_task(daily_worker())
        print("Workers started successfully")
    except Exception as e:
        print(f"Error starting workers: {e}")
```

- [ ] **Step 2: Delete `stock_worker.py`**

```bash
git rm backend/app/workers/stock_worker.py
```

- [ ] **Step 3: Verify imports are healthy**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -c "from app.main import app; print('main OK')"
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -c "from app.workers.intraday_worker import intraday_worker; print('intraday OK')"
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -c "from app.workers.daily_worker import daily_worker; print('daily OK')"
```

Expected: All three print OK.

- [ ] **Step 4: Run full test suite one final time**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: 63 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat: wire intraday and daily workers into app startup, retire stock_worker"
```
