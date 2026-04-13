# Signal Engine Design
**Date:** 2026-04-12
**Phase:** 2 of 3 (Signal Engine)
**Stack:** FastAPI / Python backend, vnstock SDK, talib, Telegram Bot API

---

## Overview

Phase 2 wires the Phase 1 algorithm layer to a live signal delivery system. Two background workers run continuously: one checks intraday 1-minute candles every 5 minutes, one fires once daily at 3:05 PM ICT after market close. When a divergence signal fires on a watched stock, all users watching that stock receive a Telegram message with the signal type, price, and timeframe.

**Explicit product decision:** signals are informational only. The bot sends BUY and SELL alerts but tracks no position state. A user may receive a second BUY before a SELL — that is acceptable in Phase 2. Position tracking is deferred to Phase 3.

---

## Scope

**In scope:**
- Intraday worker: polls every 5 minutes, checks latest 1-minute candle per symbol
- Daily worker: fires once at 3:05 PM ICT, checks latest daily candle per symbol
- Signal service: `build_symbol_map`, `fetch_ohlcv_with_rsi`, `format_signal_message`, `send_signal`
- Deduplication: intraday uses prefix+suffix pair tracking; daily uses schedule-based (fires once per day naturally)
- Stock-first fan-out: fetch each symbol once, send to all watching users
- Rate limiting: 50ms between Telegram sends to stay under API limits
- Dependency injection on `get_users` in both workers for testability
- Retire `stock_worker.py`

**Out of scope (Phase 3):**
- Frontend dashboard
- Position tracking
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
    signal_service.py      ← NEW: shared helpers + format + send
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

Four functions. No module-level state.

### `build_symbol_map`

```python
def build_symbol_map(users: list) -> dict[str, list[str]]:
    """
    Returns {symbol: [chat_id, ...]} for all users with a non-empty chat_id.
    Each symbol appears once; its value is all chat_ids watching it.
    Users without chat_id are excluded entirely.
    Used by both intraday and daily workers.
    """
```

### `fetch_ohlcv_with_rsi`

```python
def fetch_ohlcv_with_rsi(
    symbol: str,
    interval: str,       # '1m' for intraday, '1D' for daily
    start: str,          # YYYY-MM-DD
    end: str,            # YYYY-MM-DD
) -> list[dict] | None:
    """
    Fetch OHLCV via Quote(symbol, source='VCI').history(...),
    compute RSI via talib.RSI(df['close'], timeperiod=14),
    drop NaN rows, return as list[dict] with RSI field.
    Returns None if data is empty or fewer than 2 rows after RSI warmup.

    Both workers use this — consistent data pipeline, easy to mock in tests.
    """
```

### `format_signal_message`

```python
def format_signal_message(
    symbol: str,
    divergence_type: str,   # "bearish" | "bullish"
    timeframe: str,          # "Intraday" | "Daily"
    price: float,
    signal_time: str,        # "HH:MM ICT"
) -> str:
```

Output format:
```
🔴 VGI — SELL signal
Strategy: RSI Divergence (Bearish) | Intraday
Price: 24,500 VND
Time: 14:32 ICT
```
```
🟢 VNM — BUY signal
Strategy: RSI Divergence (Bullish) | Daily
Price: 81,200 VND
Time: 15:05 ICT
```

Rules:
- Bearish → 🔴 SELL
- Bullish → 🟢 BUY
- Price formatted with commas: `f"{price:,.0f}"` → `24,500`

### `send_signal`

```python
async def send_signal(
    chat_ids: list[str],
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
) -> None:
    """
    Format message, send to each chat_id with 50ms delay between sends
    to respect Telegram's rate limit (~20 msg/sec per bot, well under the 30/sec limit).
    If one send fails, log the error and continue to remaining chat_ids.
    No-op if chat_ids is empty.
    """
```

---

## Intraday Worker (`intraday_worker.py`)

Polls every 5 minutes. Stock-first fan-out. Dedup via module-level state.

```python
ICT = timezone(timedelta(hours=7))

_seen: set[tuple] = set()   # (symbol, prefix_idx, suffix_idx)
_seen_date: str = ""         # YYYY-MM-DD, cleared when date changes

async def intraday_worker(get_users=get_all_users):
    while True:
        try:
            # 1. Reset dedup on new day
            today = date.today().isoformat()
            if today != _seen_date:
                _seen.clear()
                _seen_date = today

            # 2. Build symbol map
            users = get_users()
            symbol_to_chat_ids = build_symbol_map(users)

            # 3. Per symbol: fetch 1m candles, check divergence, send
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
                    price = records_list[-1]['close']
                    signal_time = datetime.now(ICT).strftime('%H:%M')
                    await send_signal(chat_ids, symbol, divergence['type'], 'Intraday', price, signal_time)
                except Exception as e:
                    print(f"Intraday worker error for {symbol}: {e}")

        except (OperationalError, DisconnectionError):
            await asyncio.sleep(10)
            continue
        except Exception as e:
            print(f"Intraday worker error: {e}")

        await asyncio.sleep(300)  # 5 minutes
```

---

## Daily Worker (`daily_worker.py`)

Fires once per day at 3:05 PM ICT. No dedup state — schedule is the guard.

```python
ICT = timezone(timedelta(hours=7))
SIGNAL_HOUR = 15
SIGNAL_MINUTE = 5

def _seconds_until_next_signal() -> float:
    """
    Returns seconds until next 3:05 PM ICT.
    If current time >= 3:05 PM ICT today, returns seconds until tomorrow 3:05 PM.
    If current time == exactly 3:05 PM, returns seconds until tomorrow (never fires twice).
    """
    now = datetime.now(ICT)
    target = now.replace(hour=SIGNAL_HOUR, minute=SIGNAL_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_worker(get_users=get_all_users):
    while True:
        await asyncio.sleep(_seconds_until_next_signal())

        try:
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
                    price = records_list[-1]['close']
                    signal_time = datetime.now(ICT).strftime('%H:%M')
                    await send_signal(chat_ids, symbol, divergence['type'], 'Daily', price, signal_time)
                except Exception as e:
                    print(f"Daily worker error for {symbol}: {e}")

        except (OperationalError, DisconnectionError):
            await asyncio.sleep(60)
            continue
        except Exception as e:
            print(f"Daily worker error: {e}")
```

---

## main.py Changes

```python
# Remove:
from app.workers.stock_worker import stock_worker

# Add:
from app.workers.intraday_worker import intraday_worker
from app.workers.daily_worker import daily_worker

# In startup_event — replace stock_worker task with:
asyncio.create_task(intraday_worker())
asyncio.create_task(daily_worker())
```

Both are non-blocking background tasks. App starts immediately.

---

## Test Plan

### `test_signal_service.py`

| Test | What it verifies |
|------|-----------------|
| `test_format_bearish_intraday` | 🔴 SELL, correct symbol, Intraday tag |
| `test_format_bullish_daily` | 🟢 BUY, correct symbol, Daily tag |
| `test_format_price_formatting` | 24500.0 → "24,500 VND" |
| `test_build_symbol_map_excludes_no_chat_id` | Users without chat_id excluded |
| `test_build_symbol_map_multiple_users_same_stock` | Both chat_ids in list for shared symbol |
| `test_build_symbol_map_empty_users` | Empty list → empty dict |
| `test_send_signal_calls_send_message_for_each_chat_id` | 3 chat_ids → 3 send_message calls |
| `test_send_signal_empty_chat_ids` | No send_message calls |
| `test_send_signal_continues_on_failure` | One send raises → rest still sent |
| `test_send_signal_rate_limit_delay` | asyncio.sleep(0.05) called between sends |
| `test_fetch_ohlcv_returns_none_on_empty_df` | Empty vnstock response → None |
| `test_fetch_ohlcv_returns_none_on_insufficient_rsi` | All NaN RSI → None |
| `test_fetch_ohlcv_returns_records_with_rsi` | Valid data → list[dict] with RSI field |

### `test_intraday_worker.py`

| Test | What it verifies |
|------|-----------------|
| `test_fires_signal_on_new_divergence` | New key → send_signal called |
| `test_suppresses_duplicate_divergence` | Same key twice → send_signal called once |
| `test_suppresses_when_no_divergence` | None → no send |
| `test_dedup_resets_on_date_change` | Same key on new date → send_signal called again |
| `test_skips_user_with_no_chat_id` | Excluded from symbol map |
| `test_multiple_users_same_stock` | All 3 chat_ids passed to send_signal |
| `test_no_users` | Empty list → no fetch, no send |
| `test_continues_on_stock_fetch_error` | fetch_ohlcv_with_rsi raises → next symbol processed |
| `test_injectable_get_users` | Custom get_users lambda used instead of real DB |

### `test_daily_worker.py`

| Test | What it verifies |
|------|-----------------|
| `test_fires_signal_on_divergence` | Divergence → send_signal called |
| `test_no_signal_when_no_divergence` | None → no send |
| `test_skips_empty_or_insufficient_data` | fetch_ohlcv_with_rsi returns None → skipped |
| `test_continues_on_symbol_error` | One symbol raises → next still processed |
| `test_injectable_get_users` | Custom get_users lambda used |
| `test_seconds_until_next_signal_before_cutoff` | 2:00 PM ICT → ~65 minutes |
| `test_seconds_until_next_signal_after_cutoff` | 3:06 PM ICT → ~23h59m |
| `test_seconds_until_next_signal_at_exact_cutoff` | 3:05:00 PM ICT → tomorrow |

---

## What Does NOT Change

- Auth, user, stock models and routers — untouched
- Backtest endpoint — untouched
- Algorithm layer (Phase 1) — untouched
- Frontend — untouched (Phase 3)
- Telegram `send_message` utility — untouched
