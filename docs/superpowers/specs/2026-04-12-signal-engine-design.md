# Signal Engine Design
**Date:** 2026-04-12
**Phase:** 2 of 3 (Signal Engine)
**Stack:** FastAPI / Python backend, vnstock SDK, talib, Telegram Bot API

---

## Overview

Phase 2 wires the Phase 1 algorithm layer to a live signal delivery system. Two background workers run continuously: one checks intraday candles every 5 minutes, one fires once daily at 3:05 PM ICT after market close. When a divergence signal fires on a watched stock, all users watching that stock receive a Telegram message with the signal type, price, and timeframe.

---

## Scope

**In scope:**
- Intraday worker: polls every 5 minutes, checks latest intraday candle per symbol
- Daily worker: fires once at 3:05 PM ICT, checks latest daily candle per symbol
- Signal service: pure message formatting + Telegram dispatch
- Deduplication: intraday uses prefix+suffix pair tracking; daily uses schedule-based (fires once per day naturally)
- Stock-first fan-out: fetch each symbol once, send to all watching users
- Retire `stock_worker.py`

**Out of scope (Phase 3):**
- Frontend dashboard
- Multiple strategies per worker
- Per-user strategy configuration
- Signal history persistence

---

## Folder Structure

```
backend/app/
  workers/
    intraday_worker.py     ← NEW: polls every 5 min
    daily_worker.py        ← NEW: fires at 3:05 PM ICT daily
    stock_worker.py        ← DELETED
  services/
    signal_service.py      ← NEW: format_signal_message + send_signal
backend/tests/
  workers/
    __init__.py
    test_intraday_worker.py
    test_daily_worker.py
  services/
    test_signal_service.py  ← add to existing services test dir
```

**Modified:**
- `backend/app/main.py` — swap worker startup tasks

---

## Signal Service (`signal_service.py`)

Purely functional. No state. Two functions.

```python
def format_signal_message(
    symbol: str,
    divergence_type: str,   # "bearish" | "bullish"
    timeframe: str,          # "Intraday" | "Daily"
    price: float,
    signal_time: str,        # "HH:MM ICT"
) -> str:
    """
    Bearish → 🔴 SELL, Bullish → 🟢 BUY.

    Example output:
        🔴 VGI — SELL signal
        Strategy: RSI Divergence (Bearish) | Intraday
        Price: 24,500 VND
        Time: 14:32 ICT
    """

async def send_signal(
    chat_ids: list[str],
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
) -> None:
    """
    Format the message and send to each chat_id.
    If one send fails, log the error and continue to remaining chat_ids.
    No-op if chat_ids is empty.
    """
```

Price formatting: use Python's `f"{price:,.0f}"` to produce `24,500` from `24500.0`.

**Shared helper (also in `signal_service.py`):**

```python
def build_symbol_map(users: list) -> dict[str, list[str]]:
    """
    Returns {symbol: [chat_id, ...]} for all users with a non-empty chat_id.
    Each symbol appears once; its value is the list of all chat_ids watching it.
    Used by both intraday and daily workers.
    """
```

---

## Intraday Worker (`intraday_worker.py`)

Polls every 5 minutes. Stock-first fan-out. Dedup via module-level state.

```python
_seen: set[tuple] = set()     # (symbol, prefix_idx, suffix_idx)
_seen_date: str = ""           # YYYY-MM-DD, resets _seen when date changes

async def intraday_worker():
    while True:
        try:
            # 1. Reset dedup if day has changed
            today = date.today().isoformat()
            if today != _seen_date:
                _seen.clear()
                _seen_date = today

            # 2. Collect unique symbols across all users
            users = get_all_users()
            symbol_to_chat_ids = build_symbol_map(users)  # {symbol: [chat_id, ...]}

            # 3. Per unique symbol: fetch, check, signal
            for symbol, chat_ids in symbol_to_chat_ids.items():
                records_list, _ = get_mock_price(symbol)
                if not records_list:
                    continue
                divergence = _has_divergence_at(records_list, len(records_list) - 1)
                if divergence is None:
                    continue
                key = (symbol, divergence['prefixIndex'], divergence['suffixIndex'])
                if key in _seen:
                    continue
                _seen.add(key)
                price = records_list[-1]['close']
                signal_time = datetime.now(ICT).strftime('%H:%M')
                await send_signal(chat_ids, symbol, divergence['type'], 'Intraday', price, signal_time)

        except (OperationalError, DisconnectionError):
            await asyncio.sleep(10)
            continue
        except Exception as e:
            log error
        await asyncio.sleep(300)  # 5 minutes
```

`build_symbol_map(users)` is a private helper: filters users with a non-empty `chat_id`, returns `dict[str, list[str]]` mapping each unique stock symbol to the list of chat_ids that watch it.

---

## Daily Worker (`daily_worker.py`)

Fires once per day at 3:05 PM ICT (UTC+7). No dedup state needed — schedule enforces once-per-day.

```python
ICT = timezone(timedelta(hours=7))
DAILY_SIGNAL_HOUR = 15
DAILY_SIGNAL_MINUTE = 5

async def daily_worker():
    while True:
        # 1. Sleep until next 3:05 PM ICT
        await sleep_until_next_signal()

        try:
            users = get_all_users()
            symbol_to_chat_ids = build_symbol_map(users)

            for symbol, chat_ids in symbol_to_chat_ids.items():
                try:
                    df = Quote(symbol=symbol, source='VCI').history(
                        start=(date.today() - timedelta(days=90)).isoformat(),
                        end=date.today().isoformat(),
                        interval='1D'
                    )
                    if df is None or df.empty:
                        continue
                    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
                    df = df.dropna(subset=['RSI']).reset_index(drop=True)
                    if len(df) < 2:
                        continue
                    records_list = df.to_dict(orient='records')
                    divergence = _has_divergence_at(records_list, len(records_list) - 1)
                    if divergence is None:
                        continue
                    price = records_list[-1]['close']
                    signal_time = datetime.now(ICT).strftime('%H:%M')
                    await send_signal(chat_ids, symbol, divergence['type'], 'Daily', price, signal_time)
                except Exception as e:
                    log error for symbol, continue to next

        except (OperationalError, DisconnectionError):
            await asyncio.sleep(60)
            continue
        except Exception as e:
            log error


def _seconds_until_next_signal() -> float:
    """
    Returns seconds until next 3:05 PM ICT.
    If current time is past 3:05 PM ICT today, returns seconds until 3:05 PM tomorrow.
    """
    now = datetime.now(ICT)
    target = now.replace(hour=DAILY_SIGNAL_HOUR, minute=DAILY_SIGNAL_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()
```

---

## main.py Changes

```python
# Remove:
from app.workers.stock_worker import stock_worker

# Add:
from app.workers.intraday_worker import intraday_worker
from app.workers.daily_worker import daily_worker

# In startup_event — replace:
asyncio.create_task(intraday_worker())
asyncio.create_task(daily_worker())
```

Both are non-blocking background tasks. App starts immediately.

---

## Test Plan

### `test_signal_service.py`

| Test | What it verifies |
|------|-----------------|
| `test_format_bearish_intraday` | 🔴 SELL, correct symbol, price formatted with commas, Intraday tag |
| `test_format_bullish_daily` | 🟢 BUY, correct symbol, Daily tag |
| `test_format_price_formatting` | 24500.0 → "24,500 VND" |
| `test_send_signal_calls_send_message_for_each_chat_id` | 3 chat_ids → 3 `send_message` calls |
| `test_send_signal_empty_chat_ids` | No `send_message` calls when list is empty |
| `test_send_signal_continues_on_failure` | One send raises, remaining chat_ids still receive message |

### `test_intraday_worker.py`

| Test | What it verifies |
|------|-----------------|
| `test_fires_signal_on_new_divergence` | New (symbol, prefix, suffix) key → `send_signal` called |
| `test_suppresses_duplicate_divergence` | Same key seen twice → `send_signal` called once |
| `test_suppresses_when_no_divergence` | `_has_divergence_at` returns None → no send |
| `test_dedup_resets_on_date_change` | Same key on new date → `send_signal` called again |
| `test_skips_user_with_no_chat_id` | User with empty chat_id excluded from symbol map |
| `test_multiple_users_same_stock` | 3 users watch VGI → all 3 chat_ids in send call |
| `test_no_users` | Empty user list → no fetch, no send |
| `test_continues_on_stock_fetch_error` | `get_mock_price` raises for one symbol → next symbol processed |

### `test_daily_worker.py`

| Test | What it verifies |
|------|-----------------|
| `test_fires_signal_on_divergence` | Divergence on last daily candle → `send_signal` called |
| `test_no_signal_when_no_divergence` | `_has_divergence_at` returns None → no send |
| `test_skips_empty_dataframe` | vnstock returns empty df → symbol skipped, no crash |
| `test_skips_insufficient_rsi_data` | All RSI values NaN → fewer than 2 rows → skipped |
| `test_continues_on_symbol_error` | One symbol raises → next symbol still processed |
| `test_seconds_until_next_signal_before_cutoff` | 2:00 PM ICT → ~65 minutes returned |
| `test_seconds_until_next_signal_after_cutoff` | 3:06 PM ICT → ~23h59m returned |
| `test_seconds_until_next_signal_at_exact_cutoff` | 3:05 PM ICT exactly → next day returned |

---

## What Does NOT Change

- Auth, user, stock models and routers — untouched
- Backtest endpoint — untouched
- Algorithm layer (Phase 1) — untouched
- Frontend — untouched (Phase 3)
- Telegram `send_message` utility — untouched
