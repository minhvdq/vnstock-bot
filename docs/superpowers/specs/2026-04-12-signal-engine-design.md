# Signal Engine Design
**Date:** 2026-04-12  
**Last updated:** 2026-04-17  
**Phase:** 2 of 3 (Signal Engine)
**Stack:** FastAPI / Python backend, vnstock SDK (KBS source for futures), talib, Telegram Bot API

---

## Overview

Phase 2 wires the Phase 1 algorithm layer to a live signal delivery system. Two background workers run continuously: one polls 1-minute futures candles every minute, one fires once daily at 3:05 PM ICT after market close. When a signal fires, all users receive a Telegram message and a paper trade is opened automatically.

**Explicit product decision:** signals are informational only. The bot sends BUY and SELL alerts but tracks no position state. A user may receive a second BUY before a SELL — that is acceptable in Phase 2. Position tracking is deferred to Phase 3.

---

## Scope

**In scope:**
- Intraday worker: polls every 1 minute, scans fixed futures symbols (`VN30F1M`, `VN100F1M`)
- Daily worker: fires once at 3:05 PM ICT, checks latest daily candle per user-watchlist symbol
- Signal service: `build_symbol_map`, `fetch_ohlcv_with_rsi` (daily), `fetch_intraday_ohlcv_with_rsi` (futures tick → 1m OHLCV), `format_signal_message`, `send_signal`
- Deduplication: intraday uses once-per-day per-symbol guard; daily uses schedule-based (fires once per day naturally)
- Symbol-first fan-out: fetch each symbol once, fan out to all users
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

Five functions. No module-level state.

**Source constants:**
```python
_INTRADAY_SOURCES = ['KBS', 'VCI']
# KBS is required for futures (VN30F1M, VN100F1M) — VCI returns empty for derivatives.
# VCI works for daily stock OHLCV.
```

### `build_symbol_map`

```python
def build_symbol_map(users: list) -> dict[str, list[str]]:
    """
    Returns {symbol: [chat_id, ...]} for all users with a non-empty chat_id.
    Each symbol appears once; its value is all chat_ids watching it.
    Users without chat_id are excluded entirely.
    Used by daily worker only.
    """
```

### `fetch_ohlcv_with_rsi`

```python
def fetch_ohlcv_with_rsi(
    symbol: str,
    interval: str,       # '1D' for daily (only supported interval for history())
    start: str,          # YYYY-MM-DD
    end: str,            # YYYY-MM-DD
) -> list[dict] | None:
    """
    Fetch OHLCV via Quote(symbol, source='VCI').history(...),
    compute RSI via talib.RSI(df['close'], timeperiod=14),
    drop NaN rows, return as list[dict] with RSI field.
    Returns None if data is empty or fewer than 2 rows after RSI warmup.

    Used by daily worker only. vnstock history() only supports 1D/1W/1M intervals.
    """
```

### `fetch_intraday_ohlcv_with_rsi`

```python
def fetch_intraday_ohlcv_with_rsi(symbol: str) -> list[dict] | None:
    """
    Fetch today's tick data via Quote(symbol, source='KBS').intraday(page_size=10_000),
    resample to 1-minute OHLCV bars using pandas resample('1min'),
    compute RSI, and return list[dict] compatible with generate_signals().

    Why a separate function: vnstock's history() does not support sub-daily intervals.
    intraday() returns matched-order tick data (columns: time, price, volume, match_type, id).
    The price column is used for open/high/low/close of each 1-min bar.

    Falls back to VCI if KBS is empty (VCI currently returns empty for futures,
    but kept as fallback for forward compatibility).
    Returns None if fewer than 2 bars remain after RSI warmup.
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

Polls every 1 minute. Iterates a fixed list of T+0-eligible futures symbols — does **not** use per-user watchlists. All registered users receive paper trades and Telegram alerts.

```python
ICT = timezone(timedelta(hours=7))
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 15

# Vietnam T+0-eligible instruments (index futures, front month)
INTRADAY_SYMBOLS = ['VN30F1M', 'VN100F1M']

# Once-per-day guard: {strategy_name: {symbol: date_str}}
_intraday_fired: dict[str, dict[str, str]] = {}

async def _poll_once(get_users=get_all_users):
    users = get_users()
    all_user_ids = [u.id for u in users]
    all_chat_ids = [u.chat_id for u in users if u.chat_id]
    intraday_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "intraday"}

    for symbol in INTRADAY_SYMBOLS:
        records_list = fetch_intraday_ohlcv_with_rsi(symbol)
        if not records_list:
            continue
        df = pd.DataFrame(records_list)

        for strategy_name, StrategyClass in intraday_strategies.items():
            # once-per-day dedup
            fired_today = _intraday_fired.setdefault(strategy_name, {})
            if fired_today.get(symbol) == today:
                continue

            strategy = StrategyClass()
            df_signals = strategy.generate_signals(df.copy())
            last_signal = int(df_signals.iloc[-1].get('signal', 0))
            if last_signal == 1:
                fired_today[symbol] = today
                await send_signal(all_chat_ids, symbol, 'bullish', 'Intraday', price, signal_time, StrategyClass.display_name)
                for user_id in all_user_ids:
                    await paper_trading_service.on_signal(user_id=user_id, symbol=symbol, entry_price=price, strategy_name=strategy_name)

    if is_market_hours:
        await paper_trading_service.check_positions()

async def intraday_worker(get_users=get_all_users):
    while True:
        await _poll_once(get_users)
        await asyncio.sleep(60)  # 1 minute
```

**Why futures only:** Vietnam's T+0 rule does not apply to individual stocks (T+2.5 settlement). VN30 and VN100 index futures settle intraday and are legally tradeable same-day. Individual stocks have been removed from the intraday worker entirely.

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
