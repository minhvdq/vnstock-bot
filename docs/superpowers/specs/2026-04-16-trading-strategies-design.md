# Trading Strategies Expansion — Design Spec
**Date:** 2026-04-16  
**Last updated:** 2026-04-17  
**Status:** Implemented

---

## Overview

Add three new trading strategies alongside the existing RSI Divergence strategy. Each strategy is a `BaseStrategy` subclass with a `timeframe` class attribute. Workers route execution by timeframe — `daily_worker` runs daily strategies, `intraday_worker` runs intraday strategies.

---

## Architecture

### Timeframe Routing

Add `timeframe: str = "daily"` to `BaseStrategy`. Workers filter `STRATEGIES` at runtime:

```python
# daily_worker
daily_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "daily"}

# intraday_worker
intraday_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "intraday"}
```

### Strategy Registry (updated)

```python
STRATEGIES = {
    "rsi_divergence":    RSIStrategy,           # timeframe="daily"
    "ema_macd":          EMAMACDStrategy,        # timeframe="daily"
    "donchian_breakout": DonchianStrategy,       # timeframe="daily"
    "volume_breakout":   VolumeBreakoutStrategy, # timeframe="intraday"
}
```

### PaperTrade — strategy_name column

Add `strategy_name: str` column to `PaperTrade` model to tag which strategy opened each trade. Since `create_all(checkfirst=True)` won't add columns to existing tables, apply a safe `ALTER TABLE` migration on startup:

```python
# In startup_event, after create_all:
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS strategy_name VARCHAR DEFAULT 'rsi_divergence'"
    ))
    conn.commit()
```

### Exit Rules Per Strategy

Add `exit_rules` class attribute to `BaseStrategy`:

```python
exit_rules = {
    "stop_loss_pct": -0.07,   # -7% default
    "take_profit_pct": 0.15,  # +15% default
    "max_days": 30,
    "eod_close": False,       # intraday hard close at 14:45
}
```

`check_positions()` reads `trade.strategy_name`, looks up strategy class, applies its `exit_rules`.

---

## Strategy 1: EMA + MACD (Daily Swing)

**File:** `backend/app/algorithms/ema_macd.py`  
**Timeframe:** daily  
**Expected signals:** 3–8/month across 20-stock watchlist  
**Hold period:** 5–15 days

### Parameters
| Param | Default | Description |
|---|---|---|
| `fast` | 12 | Fast EMA period |
| `slow` | 26 | Slow EMA period |
| `signal` | 9 | MACD signal line period |
| `trend_ema` | 50 | Trend filter EMA period |

### Signal Logic
**Buy (signal = 1):** All three conditions on same bar:
1. `close > EMA(50)` — uptrend filter
2. MACD line crosses above signal line (previous bar: MACD < signal; current bar: MACD > signal)
3. MACD histogram flips from negative to positive (avoids late crossovers)

**Sell (signal = -1):**
- MACD line crosses below signal line

### Exit Rules
```python
exit_rules = {
    "stop_loss_pct": -0.07,
    "take_profit_pct": 0.15,
    "max_days": 15,
    "eod_close": False,
}
```

---

## Strategy 2: Donchian Channel Breakout (Daily Swing)

**File:** `backend/app/algorithms/donchian_breakout.py`  
**Timeframe:** daily  
**Expected signals:** 2–5/month across 20-stock watchlist  
**Hold period:** 5–20 days  
**Rationale:** Trend-following, captures institutional accumulation. Fewer false signals than MACD in sideways VN market conditions.

### Parameters
| Param | Default | Description |
|---|---|---|
| `lookback` | 20 | Rolling high lookback (days) |
| `vol_multiplier` | 1.5 | Volume confirmation multiplier |
| `vol_window` | 20 | Volume average window |

### Signal Logic
**Buy (signal = 1):** Both conditions on same bar:
1. `close > max(close, lookback=20)` — price breaks 20-day high
2. `volume > vol_multiplier × avg(volume, 20)` — volume confirms breakout (not a fake-out)

**Sell (signal = -1):**
- `close < min(close, lookback=10)` — price drops below 10-day low (trailing exit)

### Exit Rules
```python
exit_rules = {
    "stop_loss_pct": -0.07,
    "take_profit_pct": 0.20,   # wider TP — trend-following, let winners run
    "max_days": 20,
    "eod_close": False,
}
```

---

## Strategy 3: Volume Breakout (1-min Futures Intraday)

**File:** `backend/app/algorithms/volume_breakout.py`  
**Display name:** `"Volume Breakout (Futures)"`  
**Timeframe:** intraday  
**Symbols:** `VN30F1M`, `VN100F1M` (VN30 and VN100 index futures, front month)  
**Expected signals:** 0–2/day per futures symbol  
**Hold period:** intraday only (T+0 same-day exit — futures are legally T+0 in Vietnam)  
**Data source:** `Quote(symbol, source='KBS').intraday(page_size=10_000)` → resampled to 1-min OHLCV bars

**Why futures, not stocks:** Vietnam individual stocks are T+2.5 settlement — same-day buy-and-sell is not permitted. VN30 and VN100 index futures are T+0 and the only intraday-legal instruments available. Individual stocks have been removed from the intraday worker.

**Why KBS source:** `VCI` returns empty for derivatives symbols. `KBS` is the only vnstock source that provides tick data for VN30F/VN100F. `page_size=10_000` is required — the default 100 ticks covers only ~2 minutes, insufficient for RSI warmup.

### Parameters
| Param | Default | Description |
|---|---|---|
| `lookback` | 20 | Rolling high lookback (1-min bars) |
| `vol_multiplier` | 1.5 | Volume confirmation multiplier |
| `vol_window` | 20 | Volume average window |

### Signal Logic
**Buy (signal = 1):** All conditions on same 1-min bar:
1. `close > max(close, lookback=20)` — price breaks recent 20-bar high
2. `volume > 1.5 × avg(volume, 20)` — volume spike confirms breakout
3. Only fires **once per symbol per calendar day** (flag in worker, reset at midnight)

**No sell signal** — exits handled entirely by `exit_rules`.

**RSI warmup note:** First valid signal possible ~15 minutes after session open (14 bars for RSI + 20 bars for lookback). Polls before that will return data but produce no signal.

### Exit Rules
```python
exit_rules = {
    "stop_loss_pct": -0.02,    # tight 2% SL for intraday
    "take_profit_pct": 0.04,   # 4% TP → 1:2 R:R
    "max_days": 1,
    "eod_close": True,         # hard close at 14:45 VN time
}
```

### End-of-Day Close Logic
In `check_positions()`, if `trade.strategy_name == "volume_breakout"` and `exit_rules["eod_close"] is True`:
- Check current VN time
- If `time >= 14:45` and trade opened today → force close at market price

---

## Data Requirements

| Strategy | Data source | Fetch method | vnstock source |
|---|---|---|---|
| EMA + MACD | Daily OHLCV | `fetch_ohlcv_with_rsi(symbol, '1D', start, end)` | VCI |
| Donchian Breakout | Daily OHLCV | `fetch_ohlcv_with_rsi(symbol, '1D', start, end)` | VCI |
| Volume Breakout | 1-min bars from tick data | `fetch_intraday_ohlcv_with_rsi(symbol)` | KBS (VCI fallback) |

**Note:** `vnstock.Quote.history()` only supports daily/weekly/monthly intervals. Sub-daily intervals require `Quote.intraday()` which returns tick data that must be resampled. The `fetch_intraday_ohlcv_with_rsi` function handles this resampling and RSI computation.

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/algorithms/base.py` | Add `timeframe = "daily"` and `exit_rules = {...}` class attrs |
| `backend/app/algorithms/ema_macd.py` | **NEW** — EMAMACDStrategy |
| `backend/app/algorithms/donchian_breakout.py` | **NEW** — DonchianStrategy |
| `backend/app/algorithms/volume_breakout.py` | **NEW** — VolumeBreakoutStrategy |
| `backend/app/algorithms/__init__.py` | Register 3 new strategies |
| `backend/app/models/paper_trading.py` | Add `strategy_name` column |
| `backend/app/main.py` | ALTER TABLE migration on startup |
| `backend/app/services/paper_trading_service.py` | Pass `strategy_name` on `on_signal()`; read `exit_rules` in `check_positions()` |
| `backend/app/workers/daily_worker.py` | Filter strategies by `timeframe == "daily"` |
| `backend/app/workers/intraday_worker.py` | Replaced watchlist iteration with fixed `INTRADAY_SYMBOLS = ['VN30F1M', 'VN100F1M']`; all users receive signals; poll interval changed from 300s → 60s; uses `fetch_intraday_ohlcv_with_rsi` |

---

## Out of Scope

- Backtest UI changes (new strategies auto-appear in the existing STRATEGIES-driven dropdown)
- Live brokerage execution (paper trading only)
- Parameter tuning (defaults used; optimize after 30+ days of paper trading data)
