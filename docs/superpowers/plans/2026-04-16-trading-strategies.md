# Trading Strategies Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add EMA+MACD (daily swing), Donchian Channel Breakout (daily swing), and Volume Breakout (5-min intraday) as pluggable BaseStrategy subclasses routed automatically to the correct worker by a `timeframe` class attribute.

**Architecture:** Each strategy declares `timeframe = "daily" | "intraday"` and `exit_rules` dict. `daily_worker` iterates all daily strategies; `intraday_worker` iterates all intraday strategies. `paper_trading_service` reads `exit_rules` per-strategy for SL/TP/max_days/eod_close. A `strategy_name` column on `PaperTrade` tags which strategy opened each trade.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pandas (ewm for EMA/MACD), vnstock, pytest

---

## File Map

| File | Action | What changes |
|---|---|---|
| `backend/app/algorithms/base.py` | Modify | Add `timeframe`, `display_name`, `exit_rules` class attrs |
| `backend/app/algorithms/ema_macd.py` | Create | EMAMACDStrategy |
| `backend/app/algorithms/donchian_breakout.py` | Create | DonchianStrategy |
| `backend/app/algorithms/volume_breakout.py` | Create | VolumeBreakoutStrategy |
| `backend/app/algorithms/__init__.py` | Modify | Register 3 new strategies |
| `backend/app/models/paper_trading.py` | Modify | Add `strategy_name` column |
| `backend/app/main.py` | Modify | ALTER TABLE migration on startup |
| `backend/app/services/paper_trading_service.py` | Modify | Accept `strategy_name`, use per-strategy exit_rules |
| `backend/app/services/signal_service.py` | Modify | Add `strategy_name` param to `format_signal_message` + `send_signal` |
| `backend/app/workers/daily_worker.py` | Modify | Iterate all daily strategies, remove RSI-specific imports |
| `backend/app/workers/intraday_worker.py` | Modify | Iterate all intraday strategies, add once-per-day dedup |
| `backend/tests/algorithms/test_ema_macd.py` | Create | EMAMACDStrategy unit tests |
| `backend/tests/algorithms/test_donchian_breakout.py` | Create | DonchianStrategy unit tests |
| `backend/tests/algorithms/test_volume_breakout.py` | Create | VolumeBreakoutStrategy unit tests |

---

### Task 1: Update BaseStrategy with timeframe, display_name, and exit_rules

**Files:**
- Modify: `backend/app/algorithms/base.py`

- [ ] **Step 1: Add class attributes to BaseStrategy**

Open `backend/app/algorithms/base.py`. Add three class-level attributes inside `BaseStrategy`, immediately after the class declaration line, before `generate_signals`:

```python
class BaseStrategy(ABC):
    timeframe: str = "daily"       # "daily" | "intraday" — workers filter by this
    display_name: str = "Strategy" # human-readable name for Telegram messages
    exit_rules: dict = {
        "stop_loss_pct": -0.07,    # relative to entry price, e.g. -0.07 = -7%
        "take_profit_pct": 0.15,
        "max_days": 30,
        "eod_close": False,        # if True, hard-close at 14:45 VN time same day
    }

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        ...
```

- [ ] **Step 2: Add display_name to RSIStrategy**

Open `backend/app/algorithms/rsi_divergence.py`. Add two lines at the top of `RSIStrategy`:

```python
class RSIStrategy(BaseStrategy):
    display_name = "RSI Divergence"
    timeframe = "daily"
    # exit_rules inherits defaults from BaseStrategy (-7% SL, +15% TP, 30d)
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

```bash
cd backend && python -m pytest tests/algorithms/ -v
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app/algorithms/base.py backend/app/algorithms/rsi_divergence.py
git commit -m "feat: add timeframe, display_name, exit_rules to BaseStrategy"
```

---

### Task 2: Implement EMAMACDStrategy

**Files:**
- Create: `backend/app/algorithms/ema_macd.py`
- Create: `backend/tests/algorithms/test_ema_macd.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/algorithms/test_ema_macd.py`:

```python
import pandas as pd
import pytest
from app.algorithms.ema_macd import EMAMACDStrategy


def _make_df(closes: list, volumes: list = None) -> pd.DataFrame:
    n = len(closes)
    if volumes is None:
        volumes = [1000] * n
    return pd.DataFrame({
        'time': [f'2024-01-{i+1:03d}' for i in range(n)],
        'open': closes,
        'high': [c + 1 for c in closes],
        'low': [c - 1 for c in closes],
        'close': closes,
        'volume': volumes,
        'RSI': [50.0] * n,
    })


def _flat_then_surge(flat_val=100.0, n_flat=80, surge_vals=None) -> pd.DataFrame:
    """80 flat bars then a sharp uptrend to force MACD crossover above signal."""
    if surge_vals is None:
        surge_vals = [102, 105, 109, 114, 120, 128, 137, 147, 158, 170]
    closes = [flat_val] * n_flat + [float(v) for v in surge_vals]
    return _make_df(closes)


# ── class attributes ──────────────────────────────────────────────────────────

def test_ema_macd_has_daily_timeframe():
    assert EMAMACDStrategy.timeframe == "daily"


def test_ema_macd_has_exit_rules():
    rules = EMAMACDStrategy.exit_rules
    assert rules["stop_loss_pct"] == -0.07
    assert rules["take_profit_pct"] == 0.15
    assert rules["max_days"] == 15
    assert rules["eod_close"] is False


def test_ema_macd_has_display_name():
    assert EMAMACDStrategy.display_name == "EMA+MACD"


# ── generate_signals ──────────────────────────────────────────────────────────

def test_generate_signals_returns_signal_column():
    df = _make_df([100.0] * 60)
    result = EMAMACDStrategy().generate_signals(df)
    assert 'signal' in result.columns


def test_generate_signals_no_signal_for_flat_data():
    """Flat price → MACD stays near zero, no crossovers."""
    df = _make_df([100.0] * 80)
    result = EMAMACDStrategy().generate_signals(df)
    assert (result['signal'] == 0).all()


def test_generate_signals_buy_signal_on_uptrend():
    """Sharp uptrend after flat base triggers MACD crossover above EMA50."""
    df = _flat_then_surge()
    result = EMAMACDStrategy().generate_signals(df)
    assert (result['signal'] == 1).any(), "Expected at least one buy signal"


def test_generate_signals_no_buy_when_price_below_ema50():
    """Downtrend → price stays below EMA50 trend filter → no buy."""
    closes = [float(100 - i * 0.5) for i in range(90)]  # gradual decline
    df = _make_df(closes)
    result = EMAMACDStrategy().generate_signals(df)
    assert not (result['signal'] == 1).any(), "No buy signal when below EMA50"


def test_generate_signals_does_not_mutate_input():
    df = _flat_then_surge()
    original = df.copy()
    EMAMACDStrategy().generate_signals(df)
    pd.testing.assert_frame_equal(df, original)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/algorithms/test_ema_macd.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `ema_macd` doesn't exist yet.

- [ ] **Step 3: Implement EMAMACDStrategy**

Create `backend/app/algorithms/ema_macd.py`:

```python
from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


class EMAMACDStrategy(BaseStrategy):
    """
    EMA + MACD swing strategy (daily bars).

    Buy when:
      1. close > EMA(50) — uptrend filter
      2. MACD line crosses above signal line (12/26/9)
      3. MACD histogram flips from negative to positive

    Sell when MACD line crosses below signal line.
    """
    timeframe = "daily"
    display_name = "EMA+MACD"
    exit_rules = {
        "stop_loss_pct": -0.07,
        "take_profit_pct": 0.15,
        "max_days": 15,
        "eod_close": False,
    }

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9, trend_ema: int = 50):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.trend_ema = trend_ema

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        close = df['close']
        df['_ema_trend'] = close.ewm(span=self.trend_ema, adjust=False).mean()
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        df['_macd'] = ema_fast - ema_slow
        df['_macd_sig'] = df['_macd'].ewm(span=self.signal_period, adjust=False).mean()
        df['_hist'] = df['_macd'] - df['_macd_sig']

        for i in range(1, len(df)):
            price = df.iloc[i]['close']
            ema_trend = df.iloc[i]['_ema_trend']
            macd_now = df.iloc[i]['_macd']
            sig_now = df.iloc[i]['_macd_sig']
            hist_now = df.iloc[i]['_hist']
            macd_prev = df.iloc[i - 1]['_macd']
            sig_prev = df.iloc[i - 1]['_macd_sig']
            hist_prev = df.iloc[i - 1]['_hist']

            # Buy: price above trend EMA, MACD crosses above signal, histogram flips positive
            if (price > ema_trend
                    and macd_now > sig_now and macd_prev <= sig_prev
                    and hist_now > 0 and hist_prev <= 0):
                df.iloc[i, df.columns.get_loc('signal')] = 1

            # Sell: MACD crosses below signal
            elif macd_now < sig_now and macd_prev >= sig_prev:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        # Drop internal indicator columns to keep output clean
        df.drop(columns=['_ema_trend', '_macd', '_macd_sig', '_hist'], inplace=True)
        return df
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && python -m pytest tests/algorithms/test_ema_macd.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/algorithms/ema_macd.py backend/tests/algorithms/test_ema_macd.py
git commit -m "feat: add EMAMACDStrategy with tests"
```

---

### Task 3: Implement DonchianStrategy

**Files:**
- Create: `backend/app/algorithms/donchian_breakout.py`
- Create: `backend/tests/algorithms/test_donchian_breakout.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/algorithms/test_donchian_breakout.py`:

```python
import pandas as pd
import pytest
from app.algorithms.donchian_breakout import DonchianStrategy


def _make_df(closes: list, volumes: list) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        'time': [f'2024-01-{i+1:03d}' for i in range(n)],
        'open': closes,
        'high': [c + 1 for c in closes],
        'low': [c - 1 for c in closes],
        'close': closes,
        'volume': volumes,
        'RSI': [50.0] * n,
    })


def _flat_base(n=25, price=100.0, volume=1000):
    """n bars of flat price and volume — good baseline for rolling windows."""
    return _make_df([price] * n, [volume] * n)


# ── class attributes ──────────────────────────────────────────────────────────

def test_donchian_has_daily_timeframe():
    assert DonchianStrategy.timeframe == "daily"


def test_donchian_has_exit_rules():
    rules = DonchianStrategy.exit_rules
    assert rules["stop_loss_pct"] == -0.07
    assert rules["take_profit_pct"] == 0.20
    assert rules["max_days"] == 20
    assert rules["eod_close"] is False


def test_donchian_has_display_name():
    assert DonchianStrategy.display_name == "Donchian Breakout"


# ── generate_signals ──────────────────────────────────────────────────────────

def test_donchian_buy_signal_on_price_and_volume_breakout():
    """Price breaks 20-day high AND volume > 1.5x avg → signal=1."""
    df = _flat_base(25, price=100.0, volume=1000)
    # Append breakout bar: close=106 (> max of 100), volume=2000 (> 1.5*1000=1500)
    breakout = _make_df([106.0], [2000])
    df = pd.concat([df, breakout], ignore_index=True)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 1


def test_donchian_no_buy_without_volume_confirmation():
    """Price breaks high but volume is normal → no signal."""
    df = _flat_base(25, price=100.0, volume=1000)
    breakout = _make_df([106.0], [1000])  # volume not elevated
    df = pd.concat([df, breakout], ignore_index=True)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0


def test_donchian_no_buy_without_price_breakout():
    """Volume spikes but price stays below 20-day high → no signal."""
    df = _flat_base(25, price=100.0, volume=1000)
    no_breakout = _make_df([99.0], [3000])  # high volume but price lower
    df = pd.concat([df, no_breakout], ignore_index=True)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0


def test_donchian_sell_signal_when_below_10day_low():
    """After a high, drop well below 10-day rolling low → signal=-1."""
    # 25 bars at 100, then 5 bars at 120, then a crash to 85
    closes = [100.0] * 25 + [120.0] * 5 + [85.0]
    volumes = [1000] * 31
    df = _make_df(closes, volumes)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == -1


def test_donchian_no_signal_for_flat_data():
    df = _flat_base(30)
    result = DonchianStrategy().generate_signals(df)
    assert (result['signal'] == 0).all()


def test_donchian_does_not_mutate_input():
    df = _flat_base(30)
    original = df.copy()
    DonchianStrategy().generate_signals(df)
    pd.testing.assert_frame_equal(df, original)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/algorithms/test_donchian_breakout.py -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement DonchianStrategy**

Create `backend/app/algorithms/donchian_breakout.py`:

```python
from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


class DonchianStrategy(BaseStrategy):
    """
    Donchian Channel Breakout strategy (daily bars).

    Buy when:
      1. close > highest close of previous `lookback` bars (price breakout)
      2. volume > vol_multiplier × avg volume of last vol_window bars

    Sell when close < rolling min of last 10 bars (trailing exit).
    """
    timeframe = "daily"
    display_name = "Donchian Breakout"
    exit_rules = {
        "stop_loss_pct": -0.07,
        "take_profit_pct": 0.20,
        "max_days": 20,
        "eod_close": False,
    }

    def __init__(
        self,
        lookback: int = 20,
        vol_multiplier: float = 1.5,
        vol_window: int = 20,
        exit_lookback: int = 10,
    ):
        self.lookback = lookback
        self.vol_multiplier = vol_multiplier
        self.vol_window = vol_window
        self.exit_lookback = exit_lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        # Previous-bar rolling high (shift(1) excludes current bar from window)
        df['_rolling_high'] = df['close'].shift(1).rolling(self.lookback).max()
        df['_rolling_low'] = df['close'].rolling(self.exit_lookback).min()
        df['_avg_vol'] = df['volume'].rolling(self.vol_window).mean()

        for i in range(self.lookback + 1, len(df)):
            close = df.iloc[i]['close']
            rolling_high = df.iloc[i]['_rolling_high']
            rolling_low = df.iloc[i]['_rolling_low']
            avg_vol = df.iloc[i]['_avg_vol']
            volume = df.iloc[i]['volume']

            if pd.isna(rolling_high) or pd.isna(avg_vol):
                continue

            if close > rolling_high and volume > self.vol_multiplier * avg_vol:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            elif not pd.isna(rolling_low) and close < rolling_low:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        df.drop(columns=['_rolling_high', '_rolling_low', '_avg_vol'], inplace=True)
        return df
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && python -m pytest tests/algorithms/test_donchian_breakout.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/algorithms/donchian_breakout.py backend/tests/algorithms/test_donchian_breakout.py
git commit -m "feat: add DonchianStrategy with tests"
```

---

### Task 4: Implement VolumeBreakoutStrategy

**Files:**
- Create: `backend/app/algorithms/volume_breakout.py`
- Create: `backend/tests/algorithms/test_volume_breakout.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/algorithms/test_volume_breakout.py`:

```python
import pandas as pd
import pytest
from app.algorithms.volume_breakout import VolumeBreakoutStrategy


def _make_df(closes: list, volumes: list) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        'time': [f'2024-01-01 {i:02d}:00' for i in range(n)],
        'open': closes,
        'high': [c + 0.5 for c in closes],
        'low': [c - 0.5 for c in closes],
        'close': closes,
        'volume': volumes,
        'RSI': [50.0] * n,
    })


# ── class attributes ──────────────────────────────────────────────────────────

def test_volume_breakout_has_intraday_timeframe():
    assert VolumeBreakoutStrategy.timeframe == "intraday"


def test_volume_breakout_has_exit_rules():
    rules = VolumeBreakoutStrategy.exit_rules
    assert rules["stop_loss_pct"] == -0.02
    assert rules["take_profit_pct"] == 0.04
    assert rules["max_days"] == 1
    assert rules["eod_close"] is True


def test_volume_breakout_has_display_name():
    assert VolumeBreakoutStrategy.display_name == "Volume Breakout"


# ── generate_signals ──────────────────────────────────────────────────────────

def test_volume_breakout_buy_signal_on_price_and_volume_spike():
    """Price breaks 20-bar high with volume > 1.5x avg → signal=1."""
    closes = [100.0] * 25
    volumes = [1000] * 25
    df = _make_df(closes, volumes)
    # Append breakout bar
    breakout = _make_df([106.0], [2000])
    df = pd.concat([df, breakout], ignore_index=True)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 1


def test_volume_breakout_no_signal_without_volume():
    closes = [100.0] * 25
    volumes = [1000] * 25
    df = _make_df(closes, volumes)
    no_vol = _make_df([106.0], [1000])  # price breaks but volume normal
    df = pd.concat([df, no_vol], ignore_index=True)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0


def test_volume_breakout_no_signal_without_price_breakout():
    closes = [100.0] * 25
    volumes = [1000] * 25
    df = _make_df(closes, volumes)
    no_price = _make_df([99.0], [3000])  # high volume but below 20-bar high
    df = pd.concat([df, no_price], ignore_index=True)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0


def test_volume_breakout_no_sell_signal():
    """VolumeBreakoutStrategy never generates sell signals — exits handled by check_positions."""
    closes = [100.0] * 25 + [106.0, 80.0]  # crash after breakout
    volumes = [1000] * 25 + [2000, 500]
    df = _make_df(closes, volumes)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert not (result['signal'] == -1).any()


def test_volume_breakout_does_not_mutate_input():
    df = _make_df([100.0] * 30, [1000] * 30)
    original = df.copy()
    VolumeBreakoutStrategy().generate_signals(df)
    pd.testing.assert_frame_equal(df, original)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/algorithms/test_volume_breakout.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement VolumeBreakoutStrategy**

Create `backend/app/algorithms/volume_breakout.py`:

```python
from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


class VolumeBreakoutStrategy(BaseStrategy):
    """
    Volume Breakout strategy (5-min intraday bars).

    Buy when:
      1. close > highest close of previous `lookback` bars
      2. volume > vol_multiplier × avg volume of last vol_window bars

    No sell signal — exits managed by check_positions() via exit_rules:
      - SL: -2%, TP: +4%, hard end-of-day close at 14:45 VN time.
    Once-per-day deduplication is enforced in the worker, not here.
    """
    timeframe = "intraday"
    display_name = "Volume Breakout"
    exit_rules = {
        "stop_loss_pct": -0.02,
        "take_profit_pct": 0.04,
        "max_days": 1,
        "eod_close": True,
    }

    def __init__(
        self,
        lookback: int = 20,
        vol_multiplier: float = 1.5,
        vol_window: int = 20,
    ):
        self.lookback = lookback
        self.vol_multiplier = vol_multiplier
        self.vol_window = vol_window

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        df['_rolling_high'] = df['close'].shift(1).rolling(self.lookback).max()
        df['_avg_vol'] = df['volume'].rolling(self.vol_window).mean()

        for i in range(self.lookback + 1, len(df)):
            close = df.iloc[i]['close']
            rolling_high = df.iloc[i]['_rolling_high']
            avg_vol = df.iloc[i]['_avg_vol']
            volume = df.iloc[i]['volume']

            if pd.isna(rolling_high) or pd.isna(avg_vol):
                continue

            if close > rolling_high and volume > self.vol_multiplier * avg_vol:
                df.iloc[i, df.columns.get_loc('signal')] = 1

        df.drop(columns=['_rolling_high', '_avg_vol'], inplace=True)
        return df
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd backend && python -m pytest tests/algorithms/test_volume_breakout.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Run all algorithm tests**

```bash
cd backend && python -m pytest tests/algorithms/ -v
```

Expected: all algorithm tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/algorithms/volume_breakout.py backend/tests/algorithms/test_volume_breakout.py
git commit -m "feat: add VolumeBreakoutStrategy with tests"
```

---

### Task 5: Update STRATEGIES registry

**Files:**
- Modify: `backend/app/algorithms/__init__.py`

- [ ] **Step 1: Register the three new strategies**

Replace the entire contents of `backend/app/algorithms/__init__.py`:

```python
from app.algorithms.rsi_divergence import RSIStrategy
from app.algorithms.ema_macd import EMAMACDStrategy
from app.algorithms.donchian_breakout import DonchianStrategy
from app.algorithms.volume_breakout import VolumeBreakoutStrategy

STRATEGIES: dict = {
    "rsi_divergence":    RSIStrategy,
    "ema_macd":          EMAMACDStrategy,
    "donchian_breakout": DonchianStrategy,
    "volume_breakout":   VolumeBreakoutStrategy,
}
```

- [ ] **Step 2: Verify imports work**

```bash
cd backend && python -c "from app.algorithms import STRATEGIES; print(list(STRATEGIES.keys()))"
```

Expected output: `['rsi_divergence', 'ema_macd', 'donchian_breakout', 'volume_breakout']`

- [ ] **Step 3: Commit**

```bash
git add backend/app/algorithms/__init__.py
git commit -m "feat: register EMAMACDStrategy, DonchianStrategy, VolumeBreakoutStrategy"
```

---

### Task 6: Add strategy_name column to PaperTrade + startup migration

**Files:**
- Modify: `backend/app/models/paper_trading.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add strategy_name column to PaperTrade model**

In `backend/app/models/paper_trading.py`, add one line to the `PaperTrade` class after the `status` column:

```python
    status = Column(Enum(TradeStatus), nullable=False, default=TradeStatus.open)
    strategy_name = Column(String(50), nullable=False, server_default='rsi_divergence')
```

- [ ] **Step 2: Add ALTER TABLE migration in main.py startup**

In `backend/app/main.py`, update the `startup_event` function. Add the import at the top of the file:

```python
from sqlalchemy import text
```

Then update `startup_event`:

```python
@app.on_event("startup")
async def startup_event():
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
        # Add strategy_name column to existing paper_trades table if missing
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE paper_trades "
                "ADD COLUMN IF NOT EXISTS strategy_name VARCHAR(50) NOT NULL DEFAULT 'rsi_divergence'"
            ))
            conn.commit()
        asyncio.create_task(intraday_worker())
        asyncio.create_task(daily_worker())
        print("Workers started successfully")
    except Exception as e:
        print(f"Error starting workers: {e}")
```

- [ ] **Step 3: Verify migration SQL is syntactically valid (dry run)**

```bash
cd backend && python -c "
from sqlalchemy import text
sql = \"ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS strategy_name VARCHAR(50) NOT NULL DEFAULT 'rsi_divergence'\"
print('SQL OK:', sql[:60], '...')
"
```

Expected: prints the SQL without error.

- [ ] **Step 4: Run full test suite to confirm no regressions**

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/routers
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/paper_trading.py backend/app/main.py
git commit -m "feat: add strategy_name column to PaperTrade with startup migration"
```

---

### Task 7: Update paper_trading_service to use per-strategy exit rules

**Files:**
- Modify: `backend/app/services/paper_trading_service.py`

- [ ] **Step 1: Update on_signal to accept strategy_name and use its exit_rules**

In `backend/app/services/paper_trading_service.py`, replace the `on_signal` function signature and body as follows.

Replace the module-level constants block:

```python
STARTING_BALANCE = 100_000_000  # VND
POSITION_SIZE_PCT = 0.10         # 10% of portfolio per trade — daily strategies
INTRADAY_POSITION_SIZE_PCT = 0.05  # 5% — intraday strategies (tighter risk)
MAX_POSITIONS = 10
# Legacy defaults (used when strategy not found in STRATEGIES registry)
STOP_LOSS_PCT = 0.93
TAKE_PROFIT_PCT = 1.15
MAX_HOLD_DAYS = 30
```

Replace the `on_signal` function:

```python
async def on_signal(
    user_id: int,
    symbol: str,
    entry_price: float,
    strategy_name: str = "rsi_divergence",
) -> Optional[PaperTrade]:
    """
    Open a virtual long position when a strategy fires a bullish signal.
    Reads exit_rules and position sizing from the strategy class.
    """
    from app.algorithms import STRATEGIES
    strategy_cls = STRATEGIES.get(strategy_name)

    if strategy_cls:
        sl_pct = 1 + strategy_cls.exit_rules["stop_loss_pct"]
        tp_pct = 1 + strategy_cls.exit_rules["take_profit_pct"]
        pos_size_pct = INTRADAY_POSITION_SIZE_PCT if strategy_cls.timeframe == "intraday" else POSITION_SIZE_PCT
    else:
        sl_pct = STOP_LOSS_PCT
        tp_pct = TAKE_PROFIT_PCT
        pos_size_pct = POSITION_SIZE_PCT

    db = SessionLocal()
    try:
        portfolio = _get_or_create_portfolio(user_id, db)

        open_count = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).count()
        if open_count >= MAX_POSITIONS:
            print(f"Paper trading: user {user_id} has {open_count} open positions, skipping {symbol}")
            return None

        open_positions_value = db.query(PaperTrade).filter(
            PaperTrade.user_id == user_id,
            PaperTrade.status == TradeStatus.open,
        ).with_entities(PaperTrade.position_value).all()
        total_open = sum(pv[0] for pv in open_positions_value)
        portfolio_total = portfolio.available_cash + total_open

        quantity = math.floor(portfolio_total * pos_size_pct / entry_price)
        if quantity < 1:
            print(f"Paper trading: quantity < 1 for {symbol} @ {entry_price}, skipping")
            return None
        position_value = int(entry_price * quantity)

        if portfolio.available_cash < position_value:
            print(f"Paper trading: insufficient cash for {symbol}, skipping")
            return None

        portfolio.available_cash -= position_value

        trade = PaperTrade(
            user_id=user_id,
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            position_value=position_value,
            stop_loss_price=entry_price * sl_pct,
            take_profit_price=entry_price * tp_pct,
            strategy_name=strategy_name,
            status=TradeStatus.open,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)

        from app.models.user import User
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.chat_id:
            display = strategy_cls.display_name if strategy_cls else strategy_name
            msg = (
                f"📈 Paper long {symbol} @ {entry_price:,.0f} [{display}]\n"
                f"SL: {trade.stop_loss_price:,.0f} | TP: {trade.take_profit_price:,.0f}\n"
                f"Size: {position_value / 1_000_000:.1f}M VND"
            )
            try:
                await send_message(chat_id=user.chat_id, text=msg)
            except Exception as e:
                print(f"Paper trading Telegram error: {e}")

        return trade
    finally:
        db.close()
```

- [ ] **Step 2: Update check_positions to use per-strategy max_days and eod_close**

Replace the `check_positions` function. Change the inner loop's exit logic:

```python
async def check_positions() -> None:
    """
    Evaluate all open paper positions against stop-loss, take-profit, time-stop,
    and end-of-day close rules. Call every 5 minutes during 09:00-15:00 VN time.
    """
    from app.algorithms import STRATEGIES
    db = SessionLocal()
    try:
        open_trades = db.query(PaperTrade).filter(PaperTrade.status == TradeStatus.open).all()
        if not open_trades:
            return

        symbols = list({t.symbol for t in open_trades})
        prices: dict[str, float] = {}
        for symbol in symbols:
            try:
                prices[symbol] = get_current_price(symbol)
            except Exception as e:
                print(f"Paper trading: could not fetch price for {symbol}: {e}")

        now_utc = datetime.now(timezone.utc)
        now_ict = now_utc.astimezone(ICT)
        closed_trades: list[tuple[PaperTrade, ExitReason]] = []

        for trade in open_trades:
            current_price = prices.get(trade.symbol)
            if current_price is None:
                continue

            strategy_cls = STRATEGIES.get(getattr(trade, 'strategy_name', 'rsi_divergence'))
            max_days = strategy_cls.exit_rules["max_days"] if strategy_cls else MAX_HOLD_DAYS
            eod_close = strategy_cls.exit_rules.get("eod_close", False) if strategy_cls else False

            reason: Optional[ExitReason] = None
            if current_price <= trade.stop_loss_price:
                reason = ExitReason.stop_loss
            elif current_price >= trade.take_profit_price:
                reason = ExitReason.take_profit
            elif (now_utc - trade.entry_time.replace(tzinfo=timezone.utc)).days >= max_days:
                reason = ExitReason.time_stop

            # End-of-day close for intraday strategies (14:45 VN time)
            if reason is None and eod_close:
                entry_ict = trade.entry_time.replace(tzinfo=timezone.utc).astimezone(ICT)
                if (entry_ict.date() == now_ict.date()
                        and now_ict.hour >= 14 and now_ict.minute >= 45):
                    reason = ExitReason.time_stop

            if reason:
                _close_trade(trade, current_price, reason, db)
                closed_trades.append((trade, reason))

        if closed_trades:
            db.commit()

        from app.models.user import User
        for trade, reason in closed_trades:
            user = db.query(User).filter(User.id == trade.user_id).first()
            if not user or not user.chat_id:
                continue
            pnl_pct = trade.pnl_pct or 0
            pnl_amt = trade.pnl_amount or 0
            sign = "+" if pnl_pct >= 0 else ""
            strategy_cls = STRATEGIES.get(getattr(trade, 'strategy_name', 'rsi_divergence'))
            display = strategy_cls.display_name if strategy_cls else trade.strategy_name
            if reason == ExitReason.take_profit:
                emoji, label = "✅", "take-profit"
            elif reason == ExitReason.stop_loss:
                emoji, label = "🔴", "stopped out"
            else:
                # time_stop is also used for eod_close
                is_intraday = strategy_cls and strategy_cls.timeframe == "intraday"
                emoji = "⏱"
                label = "end-of-day exit" if is_intraday else "30-day exit"
            msg = f"{emoji} {trade.symbol} {sign}{pnl_pct:.1f}% ({sign}{pnl_amt:,.0f} VND) | {label} [{display}]"
            try:
                await send_message(chat_id=user.chat_id, text=msg)
            except Exception as e:
                print(f"Paper trading Telegram error (close): {e}")
    finally:
        db.close()
```

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/routers
```

Expected: all tests pass. (Worker tests patch `on_signal` so signature change is safe.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/paper_trading_service.py
git commit -m "feat: paper_trading_service uses per-strategy exit_rules and strategy_name"
```

---

### Task 8: Update signal_service and refactor daily_worker

**Files:**
- Modify: `backend/app/services/signal_service.py`
- Modify: `backend/app/workers/daily_worker.py`
- Modify: `backend/tests/services/test_signal_service.py` (update format tests)
- Modify: `backend/tests/workers/test_daily_worker.py` (update worker tests)

- [ ] **Step 1: Update format_signal_message to accept strategy_name**

In `backend/app/services/signal_service.py`, update `format_signal_message`:

```python
def format_signal_message(
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
    strategy_name: str = 'RSI Divergence',
) -> str:
    emoji = '🔴' if divergence_type == 'bearish' else '🟢'
    action = 'SELL' if divergence_type == 'bearish' else 'BUY'
    direction = 'Bearish' if divergence_type == 'bearish' else 'Bullish'
    return (
        f"{emoji} {symbol} — {action} signal\n"
        f"Strategy: {strategy_name} ({direction}) | {timeframe}\n"
        f"Price: {price:,.0f} VND\n"
        f"Time: {signal_time} ICT"
    )
```

Update `send_signal` to accept and forward the new parameter:

```python
async def send_signal(
    chat_ids: list[str],
    symbol: str,
    divergence_type: str,
    timeframe: str,
    price: float,
    signal_time: str,
    strategy_name: str = 'RSI Divergence',
) -> None:
    if not chat_ids:
        return
    message = format_signal_message(symbol, divergence_type, timeframe, price, signal_time, strategy_name)
    for chat_id in chat_ids:
        try:
            await send_message(chat_id=chat_id, text=message)
        except Exception as e:
            print(f"Failed to send signal to {chat_id}: {e}")
        await asyncio.sleep(0.05)
```

- [ ] **Step 2: Run existing signal_service tests — confirm they still pass**

```bash
cd backend && python -m pytest tests/services/test_signal_service.py -v
```

Expected: all tests pass (strategy_name defaults to 'RSI Divergence', existing assertions still hold).

- [ ] **Step 3: Rewrite daily_worker to iterate all daily strategies**

Replace the entire contents of `backend/app/workers/daily_worker.py`:

```python
from __future__ import annotations
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.services import paper_trading_service
from app.algorithms import STRATEGIES

ICT = timezone(timedelta(hours=7))
SIGNAL_HOUR = 15
SIGNAL_MINUTE = 5
DATA_LOOKBACK_DAYS = 200  # enough for EMA(50) to stabilize


def _seconds_until_next_signal() -> float:
    now = datetime.now(ICT)
    target = now.replace(hour=SIGNAL_HOUR, minute=SIGNAL_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _build_symbol_user_ids_map(users) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for user in users:
        for symbol in user.stocks:
            result.setdefault(symbol, []).append(user.id)
    return result


async def _run_daily_check(get_users=get_all_users) -> None:
    """Run all daily strategies for every symbol in all users' watchlists."""
    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    symbol_to_user_ids = _build_symbol_user_ids_map(users)
    ict_today = datetime.now(ICT).date()
    today = ict_today.isoformat()
    start = (ict_today - timedelta(days=DATA_LOOKBACK_DAYS)).isoformat()

    daily_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "daily"}

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '1D', start, today)
            if not records_list:
                continue
            df = pd.DataFrame(records_list)

            for strategy_name, StrategyClass in daily_strategies.items():
                try:
                    strategy = StrategyClass()
                    df_signals = strategy.generate_signals(df.copy())
                    last_signal = int(df_signals.iloc[-1].get('signal', 0))
                    price = float(records_list[-1]['close'])
                    signal_time = datetime.now(ICT).strftime('%H:%M')

                    if last_signal == 1:
                        await send_signal(
                            chat_ids, symbol, 'bullish', 'Daily',
                            price, signal_time, StrategyClass.display_name,
                        )
                        for user_id in symbol_to_user_ids.get(symbol, []):
                            try:
                                await paper_trading_service.on_signal(
                                    user_id=user_id, symbol=symbol,
                                    entry_price=price, strategy_name=strategy_name,
                                )
                            except Exception as e:
                                print(f'Paper trading on_signal error ({strategy_name}) '
                                      f'user {user_id}/{symbol}: {e}')

                    elif last_signal == -1:
                        await send_signal(
                            chat_ids, symbol, 'bearish', 'Daily',
                            price, signal_time, StrategyClass.display_name,
                        )
                except Exception as e:
                    print(f'Daily worker strategy error ({strategy_name}/{symbol}): {e}')

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

- [ ] **Step 4: Update daily_worker tests**

Replace `backend/tests/workers/test_daily_worker.py`:

```python
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


def _mock_signals_df(signal_value=0):
    import pandas as pd
    records = _make_records()
    df = pd.DataFrame(records)
    df['signal'] = signal_value
    return df


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
    import pandas as pd
    records = _make_records()
    with patch('app.workers.daily_worker.fetch_ohlcv_with_rsi',
               side_effect=[Exception('API error'), records]), \
         patch('app.workers.daily_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.daily_worker.STRATEGIES', {'test_strat': _make_stub_strategy(signal=1)}):
        users = [_User('111', ['VGI', 'VNM'])]
        asyncio.run(dw._run_daily_check(get_users=lambda: users))
    assert mock_send.call_count == 1


# ── helpers ──────────────────────────────────────────────────────────────────

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
```

- [ ] **Step 5: Run updated worker tests**

```bash
cd backend && python -m pytest tests/workers/test_daily_worker.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/signal_service.py backend/app/workers/daily_worker.py \
        backend/tests/services/test_signal_service.py backend/tests/workers/test_daily_worker.py
git commit -m "feat: refactor daily_worker to iterate all daily strategies via STRATEGIES registry"
```

---

### Task 9: Refactor intraday_worker

**Files:**
- Modify: `backend/app/workers/intraday_worker.py`
- Modify: `backend/tests/workers/test_intraday_worker.py`

- [ ] **Step 1: Rewrite intraday_worker**

Replace the entire contents of `backend/app/workers/intraday_worker.py`:

```python
from __future__ import annotations
import asyncio
import pandas as pd
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.services.user_service import get_all_users
from app.services.signal_service import build_symbol_map, fetch_ohlcv_with_rsi, send_signal
from app.services import paper_trading_service
from app.algorithms import STRATEGIES

ICT = timezone(timedelta(hours=7))
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 15

# Once-per-day guard: {strategy_name: {symbol: date_str}}
# Prevents the same strategy from firing on the same symbol more than once per day.
_intraday_fired: dict[str, dict[str, str]] = {}


def _build_symbol_user_ids_map(users) -> dict[str, list[int]]:
    result: dict[str, list[int]] = {}
    for user in users:
        for symbol in user.stocks:
            result.setdefault(symbol, []).append(user.id)
    return result


async def _poll_once(get_users=get_all_users) -> None:
    """One intraday poll cycle. Runs all intraday strategies on 5-min data."""
    now_ict = datetime.now(ICT)
    today = now_ict.date().isoformat()

    users = get_users()
    symbol_to_chat_ids = build_symbol_map(users)
    symbol_to_user_ids = _build_symbol_user_ids_map(users)

    intraday_strategies = {k: v for k, v in STRATEGIES.items() if v.timeframe == "intraday"}

    for symbol, chat_ids in symbol_to_chat_ids.items():
        try:
            records_list = fetch_ohlcv_with_rsi(symbol, '5m', today, today)
            if not records_list:
                continue
            df = pd.DataFrame(records_list)

            for strategy_name, StrategyClass in intraday_strategies.items():
                try:
                    # Once-per-day deduplication
                    fired_today = _intraday_fired.setdefault(strategy_name, {})
                    if fired_today.get(symbol) == today:
                        continue

                    strategy = StrategyClass()
                    df_signals = strategy.generate_signals(df.copy())
                    last_signal = int(df_signals.iloc[-1].get('signal', 0))
                    price = float(records_list[-1]['close'])
                    signal_time = now_ict.strftime('%H:%M')

                    if last_signal == 1:
                        fired_today[symbol] = today
                        await send_signal(
                            chat_ids, symbol, 'bullish', 'Intraday',
                            price, signal_time, StrategyClass.display_name,
                        )
                        for user_id in symbol_to_user_ids.get(symbol, []):
                            try:
                                await paper_trading_service.on_signal(
                                    user_id=user_id, symbol=symbol,
                                    entry_price=price, strategy_name=strategy_name,
                                )
                            except Exception as e:
                                print(f'Paper trading on_signal error ({strategy_name}) '
                                      f'user {user_id}/{symbol}: {e}')
                except Exception as e:
                    print(f'Intraday worker strategy error ({strategy_name}/{symbol}): {e}')

        except Exception as e:
            print(f'Intraday worker error for {symbol}: {e}')

    # Check paper positions every cycle during market hours
    if now_ict.weekday() < 5 and MARKET_OPEN_HOUR <= now_ict.hour < MARKET_CLOSE_HOUR:
        try:
            await paper_trading_service.check_positions()
        except Exception as e:
            print(f'Paper trading check_positions error: {e}')


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

- [ ] **Step 2: Update intraday_worker tests**

Read `backend/tests/workers/test_intraday_worker.py` first, then replace its contents:

```python
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
            df = df.copy(); df['signal'] = 1; return df

    with patch('app.workers.intraday_worker.fetch_ohlcv_with_rsi', return_value=_make_records()), \
         patch('app.workers.intraday_worker.send_signal', new_callable=AsyncMock) as mock_send, \
         patch('app.workers.intraday_worker.STRATEGIES', {'daily_strat': DailyStub}):
        asyncio.run(iw._poll_once(get_users=lambda: [_User('111', ['VGI'])]))
    mock_send.assert_not_called()
```

- [ ] **Step 3: Run updated intraday_worker tests**

```bash
cd backend && python -m pytest tests/workers/test_intraday_worker.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Run full test suite**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/workers/intraday_worker.py backend/tests/workers/test_intraday_worker.py
git commit -m "feat: refactor intraday_worker to iterate all intraday strategies with once-per-day dedup"
```

---

### Task 10: Deploy

- [ ] **Step 1: Push to main**

```bash
git push origin main
```

- [ ] **Step 2: Deploy backend to Fly.io**

```bash
cd backend && fly deploy
```

Expected: deployment succeeds. Watch logs for startup migration confirmation:

```bash
fly logs --app vnstock-backend-aged-sunset-8999
```

Look for `Workers started successfully` — absence of SQL errors means the `ALTER TABLE` migration ran cleanly.

- [ ] **Step 3: Verify strategies are loaded**

```bash
fly ssh console --app vnstock-backend-aged-sunset-8999 -C \
  "python -c \"from app.algorithms import STRATEGIES; print(list(STRATEGIES.keys()))\""
```

Expected: `['rsi_divergence', 'ema_macd', 'donchian_breakout', 'volume_breakout']`

- [ ] **Step 4: Verify strategy_name column exists**

```bash
fly postgres connect --app <your-pg-app-name> -d <dbname>
```

Then run: `\d paper_trades` — confirm `strategy_name` column is present.

- [ ] **Step 5: Final commit if any fixes needed, then done.**
