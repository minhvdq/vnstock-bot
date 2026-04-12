# Algorithm Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean, extensible algorithm layer with RSI Divergence as the reference implementation, a shared backtest simulation engine, and a REST endpoint for running backtests on daily OHLCV data.

**Architecture:** A `BaseStrategy` ABC owns the simulation loop; subclasses only override `generate_signals()`. `backtest_service.py` fetches daily OHLCV via vnstock, computes RSI, and dispatches to the strategy. A thin FastAPI router exposes the result as JSON.

**Tech Stack:** Python 3.11+, FastAPI, vnstock (`Quote`), talib, pandas, pytest

---

## File Map

**New files:**
- `backend/app/algorithms/__init__.py` — STRATEGIES registry
- `backend/app/algorithms/base.py` — `BaseStrategy` ABC, `Trade`, `BacktestResult` dataclasses
- `backend/app/algorithms/rsi_divergence.py` — `RSIStrategy` + private helpers
- `backend/app/services/backtest_service.py` — `run_backtest()` orchestrator
- `backend/app/routers/backtest.py` — `GET /backtest/{symbol}`
- `backend/conftest.py` — pytest path setup
- `backend/tests/__init__.py`
- `backend/tests/algorithms/__init__.py`
- `backend/tests/algorithms/test_base.py`
- `backend/tests/algorithms/test_rsi_divergence.py`
- `backend/tests/services/__init__.py`
- `backend/tests/services/test_backtest_service.py`
- `backend/tests/routers/__init__.py`
- `backend/tests/routers/test_backtest.py`

**Modified files:**
- `backend/app/main.py` — register backtest router
- `backend/app/services/stock_api_service.py` — remove divergence helpers; update `get_mock_price` to use `_find_divergences` from `rsi_divergence`
- `backend/app/workers/stock_worker.py` — replace `is_divergence` import with `_has_divergence_at`

**Deleted:**
- `backend/app/utils/stock_util.py` — empty stub, safe to remove

---

## Task 1: Data Classes and BaseStrategy

**Files:**
- Create: `backend/app/algorithms/__init__.py`
- Create: `backend/app/algorithms/base.py`
- Create: `backend/conftest.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/algorithms/__init__.py`
- Create: `backend/tests/algorithms/test_base.py`

- [ ] **Step 1: Create test scaffolding**

```bash
mkdir -p backend/app/algorithms
mkdir -p backend/tests/algorithms backend/tests/services backend/tests/routers
touch backend/tests/__init__.py
touch backend/tests/algorithms/__init__.py
touch backend/tests/services/__init__.py
touch backend/tests/routers/__init__.py
```

Create `backend/conftest.py` so pytest can resolve `app.*` imports:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/algorithms/test_base.py`:

```python
import pandas as pd
import pytest
from app.algorithms.base import BaseStrategy, BacktestResult, Trade


class _BuyFirstSellLast(BaseStrategy):
    """Test strategy: signal=1 on first candle, signal=-1 on last candle."""
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        if len(df) >= 2:
            df.iloc[0, df.columns.get_loc('signal')] = 1
            df.iloc[-1, df.columns.get_loc('signal')] = -1
        return df


class _NoSignals(BaseStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0
        return df


def _make_df(prices: list) -> pd.DataFrame:
    return pd.DataFrame({
        'time': [f'2024-01-{i+1:02d}' for i in range(len(prices))],
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
    })


def test_backtest_profitable_trade():
    df = _make_df([100.0, 110.0, 120.0, 130.0, 140.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.symbol == 'TST'
    assert result.strategy == '_BuyFirstSellLast'
    assert result.total_trades == 1
    assert result.pnl > 0
    assert result.win_rate == 100.0
    assert result.pnl_pct > 0


def test_backtest_losing_trade():
    df = _make_df([100.0, 90.0, 80.0, 70.0, 60.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.total_trades == 1
    assert result.pnl < 0
    assert result.win_rate == 0.0


def test_backtest_no_signals():
    df = _make_df([100.0, 110.0, 120.0])
    result = _NoSignals().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.total_trades == 0
    assert result.pnl == 0.0
    assert result.win_rate == 0.0
    assert result.trades == []


def test_backtest_max_drawdown_is_negative():
    # Buys at 100, price rises to 150 then crashes — drawdown should be negative
    df = _make_df([100.0, 150.0, 50.0, 80.0, 60.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert result.max_drawdown < 0


def test_backtest_trade_log_structure():
    df = _make_df([100.0, 110.0, 120.0, 130.0, 140.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    buys = [t for t in result.trades if t.action == 'buy']
    sells = [t for t in result.trades if t.action == 'sell']
    assert len(buys) == 1
    assert len(sells) == 1
    assert buys[0].pnl is None
    assert sells[0].pnl is not None
    assert sells[0].pnl > 0


def test_backtest_pnl_matches_final_value():
    df = _make_df([100.0, 110.0, 120.0, 130.0, 140.0])
    result = _BuyFirstSellLast().backtest(df, symbol='TST', initial_capital=10_000.0)
    assert abs(result.final_value - result.initial_capital - result.pnl) < 0.01
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/algorithms/test_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.algorithms.base'`

- [ ] **Step 4: Create empty `backend/app/algorithms/__init__.py`**

```python
# populated in Task 3
```

- [ ] **Step 5: Implement `backend/app/algorithms/base.py`**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class Trade:
    action: str               # "buy" | "sell"
    date: str
    price: float
    shares: int
    pnl: Optional[float] = None  # None on buy; realized P&L on sell


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    pnl: float          # final_value - initial_capital
    pnl_pct: float      # pnl / initial_capital * 100
    win_rate: float     # % of completed sell trades where pnl > 0
    max_drawdown: float # worst peak-to-trough % loss (negative number)
    total_trades: int   # number of completed buy+sell pairs
    trades: list = field(default_factory=list)  # List[Trade]


class BaseStrategy(ABC):

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add a 'signal' column to df:
          1  = buy
         -1  = sell
          0  = hold
        Return the annotated DataFrame.
        """

    def backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        initial_capital: float = 100_000_000,
    ) -> BacktestResult:
        """
        Shared simulation loop — identical for all strategies.
        Calls generate_signals() internally, then iterates signals to track
        position, capital, drawdown, and trade log.
        """
        df = self.generate_signals(df.copy())

        capital = initial_capital
        shares = 0
        trades: list[Trade] = []
        peak_value = initial_capital
        max_drawdown = 0.0

        for _, row in df.iterrows():
            signal = int(row.get('signal', 0))
            price = float(row['close'])
            date = str(row.get('time', ''))

            if signal == 1 and shares == 0:
                shares = int(capital // price)
                if shares > 0:
                    capital -= shares * price
                    trades.append(Trade(action='buy', date=date, price=price, shares=shares))

            elif signal == -1 and shares > 0:
                proceeds = shares * price
                cost_basis = trades[-1].price * shares
                realized_pnl = proceeds - cost_basis
                capital += proceeds
                trades.append(Trade(action='sell', date=date, price=price, shares=shares, pnl=realized_pnl))
                shares = 0

            current_value = capital + shares * price
            if current_value > peak_value:
                peak_value = current_value
            drawdown = (current_value - peak_value) / peak_value * 100 if peak_value > 0 else 0.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown

        # Value any open position at last close price
        final_value = capital
        if shares > 0 and len(df) > 0:
            final_value += shares * float(df.iloc[-1]['close'])

        # Metrics from completed buy+sell pairs only
        completed = [
            (trades[i], trades[i + 1])
            for i in range(0, len(trades) - 1, 2)
            if trades[i].action == 'buy' and trades[i + 1].action == 'sell'
        ]
        total_trades = len(completed)
        winning = sum(1 for _, sell in completed if (sell.pnl or 0) > 0)
        win_rate = (winning / total_trades * 100) if total_trades > 0 else 0.0
        pnl = final_value - initial_capital
        pnl_pct = pnl / initial_capital * 100 if initial_capital > 0 else 0.0

        start_date = str(df.iloc[0].get('time', df.index[0])) if len(df) > 0 else ''
        end_date = str(df.iloc[-1].get('time', df.index[-1])) if len(df) > 0 else ''

        return BacktestResult(
            symbol=symbol,
            strategy=self.__class__.__name__,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_value=final_value,
            pnl=pnl,
            pnl_pct=pnl_pct,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            total_trades=total_trades,
            trades=trades,
        )
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/algorithms/test_base.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/algorithms/__init__.py backend/app/algorithms/base.py \
        backend/conftest.py \
        backend/tests/__init__.py backend/tests/algorithms/__init__.py \
        backend/tests/algorithms/test_base.py \
        backend/tests/services/__init__.py backend/tests/routers/__init__.py
git commit -m "feat: add BaseStrategy ABC with shared backtest simulation loop"
```

---

## Task 2: RSI Divergence Strategy

**Files:**
- Create: `backend/app/algorithms/rsi_divergence.py`
- Create: `backend/tests/algorithms/test_rsi_divergence.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/algorithms/test_rsi_divergence.py`:

```python
import pandas as pd
import pytest
from app.algorithms.rsi_divergence import (
    RSIStrategy,
    _is_peak,
    _is_trough,
    _is_in_range,
    _find_divergences,
    _has_divergence_at,
)


def _make_candle(high: float, low: float, close: float, rsi: float, time: str) -> dict:
    return {'time': time, 'open': close, 'high': high, 'low': low, 'close': close, 'RSI': rsi}


def _flat_data(n: int = 35) -> list:
    return [_make_candle(50.0, 40.0, 45.0, 50.0, f'2024-01-{i+1:02d}') for i in range(n)]


def _bearish_divergence_data() -> list:
    """
    35-candle series with one guaranteed bearish divergence.

    Peak 1 at index 7 (order=5): high=100, RSI=72 (bearish zone >65).
    Peak 2 at index 22 (order=5): high=110, RSI=68.
      - higher high (110 > 100) + lower RSI (68 < 72) = bearish divergence
      - distance = 22 - 7 = 15  (valid: 10 <= 15 <= 60)
    """
    rows = _flat_data(35)
    # Peak 1 shape: rise through indices 2-7, fall through 8-12
    for idx, val in zip(range(2, 13), [60, 70, 80, 90, 95, 100, 95, 90, 85, 80, 75]):
        rows[idx]['high'] = float(val)
    rows[7]['RSI'] = 72.0

    # Peak 2 shape: rise through indices 17-22, fall through 23-27
    for idx, val in zip(range(17, 28), [70, 80, 90, 100, 105, 110, 105, 100, 90, 80, 70]):
        rows[idx]['high'] = float(val)
    rows[22]['RSI'] = 68.0  # higher high but lower RSI → bearish divergence
    return rows


# ── _is_peak ────────────────────────────────────────────────────────────────

def test_is_peak_detects_local_maximum():
    rows = _flat_data(11)
    for idx, val in zip(range(0, 11), [60, 70, 80, 90, 95, 100, 95, 90, 85, 80, 75]):
        rows[idx]['high'] = float(val)
    assert _is_peak(rows, 5, order=5) is True


def test_is_peak_false_at_left_boundary():
    rows = _flat_data(11)
    assert _is_peak(rows, 0, order=5) is False


def test_is_peak_false_at_right_boundary():
    rows = _flat_data(11)
    assert _is_peak(rows, 10, order=5) is False


def test_is_peak_false_when_not_maximum():
    rows = _flat_data(11)
    for idx, val in zip(range(0, 11), [60, 70, 80, 90, 95, 100, 95, 90, 85, 80, 75]):
        rows[idx]['high'] = float(val)
    assert _is_peak(rows, 3, order=5) is False


# ── _is_trough ───────────────────────────────────────────────────────────────

def test_is_trough_detects_local_minimum():
    rows = _flat_data(11)
    for idx, val in zip(range(0, 11), [90, 80, 70, 60, 55, 50, 55, 60, 65, 70, 75]):
        rows[idx]['low'] = float(val)
    assert _is_trough(rows, 5, order=5) is True


def test_is_trough_false_at_boundary():
    rows = _flat_data(11)
    assert _is_trough(rows, 0, order=5) is False
    assert _is_trough(rows, 10, order=5) is False


# ── _is_in_range ─────────────────────────────────────────────────────────────

def test_is_in_range_bearish_above_threshold():
    assert _is_in_range(70.0, 'bearish') is True
    assert _is_in_range(65.1, 'bearish') is True


def test_is_in_range_bearish_below_threshold():
    assert _is_in_range(50.0, 'bearish') is False


def test_is_in_range_bullish_below_threshold():
    assert _is_in_range(30.0, 'bullish') is True


def test_is_in_range_bullish_above_threshold():
    assert _is_in_range(50.0, 'bullish') is False


# ── _find_divergences ────────────────────────────────────────────────────────

def test_find_divergences_detects_bearish():
    rows = _bearish_divergence_data()
    result = _find_divergences(rows)
    bearish = [d for d in result if d['type'] == 'bearish']
    assert len(bearish) >= 1
    assert bearish[0]['prefixIndex'] == 7
    assert bearish[0]['suffixIndex'] == 22


def test_find_divergences_empty_for_flat_data():
    assert _find_divergences(_flat_data(35)) == []


# ── RSIStrategy.generate_signals ─────────────────────────────────────────────

def test_generate_signals_sets_bearish_signal_at_suffix():
    df = pd.DataFrame(_bearish_divergence_data())
    result = RSIStrategy().generate_signals(df)
    assert result.iloc[22]['signal'] == -1


def test_generate_signals_zero_for_flat_data():
    df = pd.DataFrame(_flat_data(35))
    result = RSIStrategy().generate_signals(df)
    assert (result['signal'] == 0).all()


def test_generate_signals_bearish_overrides_bullish_on_same_candle():
    """Bearish (-1) takes priority when both signal types land on the same index."""
    rows = _bearish_divergence_data()
    df = pd.DataFrame(rows)
    strategy = RSIStrategy()
    result = strategy.generate_signals(df)
    # Index 22 has bearish divergence — it must not be overwritten to 1
    assert result.iloc[22]['signal'] == -1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/algorithms/test_rsi_divergence.py -v
```

Expected: `ImportError: cannot import name 'RSIStrategy' from 'app.algorithms.rsi_divergence'`

- [ ] **Step 3: Implement `backend/app/algorithms/rsi_divergence.py`**

```python
from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


# ── Private helpers ──────────────────────────────────────────────────────────

def _is_in_range(rsi: float, kind: str = 'any') -> bool:
    """Return True if RSI is in the overbought/oversold zone."""
    if kind == 'bearish':
        return rsi > 65
    if kind == 'bullish':
        return rsi < 35
    return rsi < 35 or rsi > 65


def _is_peak(df: list, i: int, order: int = 5) -> bool:
    """Return True if candle i is a local high with `order` strictly lower neighbors on each side."""
    if i < order or i >= len(df) - order:
        return False
    current_high = df[i]['high']
    for j in range(i - order, i):
        if df[j]['high'] > current_high:
            return False
    for j in range(i + 1, i + order + 1):
        if df[j]['high'] > current_high:
            return False
    return True


def _is_trough(df: list, i: int, order: int = 5) -> bool:
    """Return True if candle i is a local low with `order` strictly higher neighbors on each side."""
    if i < order or i >= len(df) - order:
        return False
    current_low = df[i]['low']
    for j in range(i - order, i):
        if df[j]['low'] < current_low:
            return False
    for j in range(i + 1, i + order + 1):
        if df[j]['low'] < current_low:
            return False
    return True


def _find_divergences(df: list) -> list:
    """
    Full-scan divergence detector (renamed from tim_phan_ky).

    Scans the entire candle list and returns every RSI divergence found.
    Each divergence: {'prefixIndex': int, 'suffixIndex': int, 'type': 'bearish'|'bullish'}

    Used by RSIStrategy.generate_signals() for backtesting.
    """
    n = len(df)
    peaks: list[int] = []
    troughs: list[int] = []
    divergences: list[dict] = []

    for i in range(n):
        if _is_peak(df, i):
            for j in range(len(peaks) - 1, -1, -1):
                old_idx = peaks[j]
                distance = i - old_idx
                if distance > 60:
                    break
                if distance < 10:
                    continue
                if _is_in_range(df[i]['RSI'], 'bearish') or _is_in_range(df[old_idx]['RSI'], 'bearish'):
                    if df[i]['high'] > df[old_idx]['high'] and df[i]['RSI'] < df[old_idx]['RSI']:
                        divergences.append({'prefixIndex': old_idx, 'suffixIndex': i, 'type': 'bearish'})
            peaks.append(i)

        if _is_trough(df, i):
            for j in range(len(troughs) - 1, -1, -1):
                old_idx = troughs[j]
                distance = i - old_idx
                if distance > 60:
                    break
                if distance < 10:
                    continue
                if _is_in_range(df[i]['RSI'], 'bullish') or _is_in_range(df[old_idx]['RSI'], 'bullish'):
                    if df[i]['low'] < df[old_idx]['low'] and df[i]['RSI'] > df[old_idx]['RSI']:
                        divergences.append({'prefixIndex': old_idx, 'suffixIndex': i, 'type': 'bullish'})
            troughs.append(i)

    return divergences


def _has_divergence_at(df: list, index: int) -> dict | None:
    """
    Single-candle divergence checker (renamed from is_divergence).

    Requires 2 confirming peak/trough pairs to reduce false positives.
    Used by the live stock worker (Phase 2) for per-tick signal checking.
    Returns a divergence dict or None.
    """
    peaks: list[int] = []
    troughs: list[int] = []
    for i in range(len(df)):
        if _is_peak(df, i):
            peaks.append(i)
        if _is_trough(df, i):
            troughs.append(i)

    bearish_cnt = 0
    if _is_peak(df, index):
        for j in range(len(peaks) - 1, -1, -1):
            old_idx = peaks[j]
            distance = index - old_idx
            if distance > 60:
                break
            if distance < 10:
                continue
            if _is_in_range(df[index]['RSI'], 'bearish') or _is_in_range(df[old_idx]['RSI'], 'bearish'):
                if df[index]['high'] > df[old_idx]['high'] and df[index]['RSI'] < df[old_idx]['RSI']:
                    bearish_cnt += 1
                    if bearish_cnt >= 2:
                        return {'prefixIndex': old_idx, 'suffixIndex': index, 'type': 'bearish'}

    bullish_cnt = 0
    if _is_trough(df, index):
        for j in range(len(troughs) - 1, -1, -1):
            old_idx = troughs[j]
            distance = index - old_idx
            if distance > 60:
                break
            if distance < 10:
                continue
            if _is_in_range(df[index]['RSI'], 'bullish') or _is_in_range(df[old_idx]['RSI'], 'bullish'):
                if df[index]['low'] < df[old_idx]['low'] and df[index]['RSI'] > df[old_idx]['RSI']:
                    bullish_cnt += 1
                    if bullish_cnt >= 2:
                        return {'prefixIndex': old_idx, 'suffixIndex': index, 'type': 'bullish'}

    return None


# ── Strategy ─────────────────────────────────────────────────────────────────

class RSIStrategy(BaseStrategy):
    """
    RSI Divergence strategy.

    Generates buy signals (1) at bullish divergence suffix candles and
    sell signals (-1) at bearish divergence suffix candles.
    Conflict rule: if both types land on the same candle, bearish (-1) wins.
    """

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        records = df.to_dict(orient='records')
        divergences = _find_divergences(records)

        for div in divergences:
            idx = div['suffixIndex']
            if div['type'] == 'bullish':
                # Only set buy if bearish has not already claimed this candle
                if df.iloc[idx]['signal'] != -1:
                    df.iloc[idx, df.columns.get_loc('signal')] = 1
            elif div['type'] == 'bearish':
                # Always overrides — bearish wins conflicts
                df.iloc[idx, df.columns.get_loc('signal')] = -1

        return df
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/algorithms/test_rsi_divergence.py -v
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/algorithms/rsi_divergence.py \
        backend/tests/algorithms/test_rsi_divergence.py
git commit -m "feat: add RSIStrategy with find_divergences and has_divergence_at"
```

---

## Task 3: Algorithm Registry

**Files:**
- Modify: `backend/app/algorithms/__init__.py`

- [ ] **Step 1: Populate the registry**

Replace `backend/app/algorithms/__init__.py` with:

```python
from app.algorithms.rsi_divergence import RSIStrategy

STRATEGIES: dict = {
    "rsi_divergence": RSIStrategy,
}
```

- [ ] **Step 2: Verify import works**

```bash
cd backend && python -c "from app.algorithms import STRATEGIES; print(STRATEGIES)"
```

Expected output: `{'rsi_divergence': <class 'app.algorithms.rsi_divergence.RSIStrategy'>}`

- [ ] **Step 3: Commit**

```bash
git add backend/app/algorithms/__init__.py
git commit -m "feat: add STRATEGIES registry"
```

---

## Task 4: Backtest Service

**Files:**
- Create: `backend/app/services/backtest_service.py`
- Create: `backend/tests/services/test_backtest_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/services/test_backtest_service.py`:

```python
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from app.services.backtest_service import run_backtest
from app.algorithms.base import BacktestResult


def _daily_df(n: int = 60) -> pd.DataFrame:
    prices = [100.0 + i * 0.5 for i in range(n)]
    return pd.DataFrame({
        'time': [f'2024-{i+1:04d}' for i in range(n)],
        'open': prices,
        'high': [p + 1 for p in prices],
        'low': [p - 1 for p in prices],
        'close': prices,
        'volume': [1000] * n,
    })


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_returns_backtest_result(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = _daily_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)

    result = run_backtest('VGI', 'rsi_divergence', '2024-01-01', '2024-12-31')

    assert isinstance(result, BacktestResult)
    assert result.symbol == 'VGI'
    assert result.strategy == 'RSIStrategy'


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_raises_on_empty_df(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = pd.DataFrame()

    with pytest.raises(ValueError, match='No data returned for VGI'):
        run_backtest('VGI', 'rsi_divergence', '2024-01-01', '2024-12-31')


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_raises_on_unknown_strategy(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = _daily_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)

    with pytest.raises(ValueError, match='Unknown strategy: fake_strategy'):
        run_backtest('VGI', 'fake_strategy', '2024-01-01', '2024-12-31')


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_raises_on_insufficient_data(mock_quote_cls, mock_talib):
    # 10 rows from vnstock → all NaN RSI → 0 rows after dropna → < 30 minimum
    mock_quote_cls.return_value.history.return_value = _daily_df(10)
    mock_talib.RSI.return_value = pd.Series([float('nan')] * 10)

    with pytest.raises(ValueError, match='Insufficient data'):
        run_backtest('VGI', 'rsi_divergence', '2024-01-01', '2024-01-10')


@patch('app.services.backtest_service.talib')
@patch('app.services.backtest_service.Quote')
def test_run_backtest_uses_default_dates_when_omitted(mock_quote_cls, mock_talib):
    mock_quote_cls.return_value.history.return_value = _daily_df(60)
    mock_talib.RSI.return_value = pd.Series([50.0] * 60)

    result = run_backtest('VGI', 'rsi_divergence')  # no start/end

    assert isinstance(result, BacktestResult)
    call_kwargs = mock_quote_cls.return_value.history.call_args.kwargs
    assert 'start' in call_kwargs and 'end' in call_kwargs
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/services/test_backtest_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.backtest_service'`

- [ ] **Step 3: Implement `backend/app/services/backtest_service.py`**

```python
from __future__ import annotations
from datetime import date, timedelta
import talib
import pandas as pd
from vnstock import Quote
from app.algorithms import STRATEGIES
from app.algorithms.base import BacktestResult


def run_backtest(
    symbol: str,
    strategy_name: str = 'rsi_divergence',
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 100_000_000,
) -> BacktestResult:
    """
    Fetch daily OHLCV for `symbol`, run the named strategy's backtest,
    and return a BacktestResult with full metrics and trade log.

    Raises ValueError for: unknown strategy, empty data, insufficient data.
    """
    if strategy_name not in STRATEGIES:
        raise ValueError(f'Unknown strategy: {strategy_name}')

    today = date.today()
    start = start_date or (today - timedelta(days=365)).isoformat()
    end = end_date or today.isoformat()

    df: pd.DataFrame = Quote(symbol=symbol, source='VCI').history(start=start, end=end, interval='1D')

    if df is None or df.empty:
        raise ValueError(f'No data returned for {symbol}')

    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df = df.dropna(subset=['RSI']).reset_index(drop=True)

    if len(df) < 30:
        raise ValueError(
            f'Insufficient data for backtest: only {len(df)} candles after RSI warmup (need 30)'
        )

    strategy = STRATEGIES[strategy_name]()
    return strategy.backtest(df, symbol=symbol, initial_capital=initial_capital)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/services/test_backtest_service.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/backtest_service.py \
        backend/tests/services/test_backtest_service.py
git commit -m "feat: add backtest_service with vnstock data fetching and RSI computation"
```

---

## Task 5: Backtest API Endpoint

**Files:**
- Create: `backend/app/routers/backtest.py`
- Create: `backend/tests/routers/test_backtest.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/routers/test_backtest.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.algorithms.base import BacktestResult, Trade

client = TestClient(app)


def _mock_result(symbol: str = 'VGI') -> BacktestResult:
    return BacktestResult(
        symbol=symbol,
        strategy='RSIStrategy',
        start_date='2024-01-01',
        end_date='2024-12-31',
        initial_capital=100_000_000.0,
        final_value=118_500_000.0,
        pnl=18_500_000.0,
        pnl_pct=18.5,
        win_rate=62.5,
        max_drawdown=-8.3,
        total_trades=8,
        trades=[
            Trade(action='buy', date='2024-02-15', price=24500.0, shares=4081, pnl=None),
            Trade(action='sell', date='2024-03-01', price=26200.0, shares=4081, pnl=6_937_700.0),
        ],
    )


@patch('app.routers.backtest.run_backtest')
def test_backtest_returns_200(mock_run):
    mock_run.return_value = _mock_result()
    response = client.get('/backtest/VGI')
    assert response.status_code == 200
    data = response.json()
    assert data['symbol'] == 'VGI'
    assert data['strategy'] == 'RSIStrategy'
    assert data['pnl'] == 18_500_000.0
    assert len(data['trades']) == 2


@patch('app.routers.backtest.run_backtest')
def test_backtest_passes_all_query_params(mock_run):
    mock_run.return_value = _mock_result()
    client.get('/backtest/VGI?strategy=rsi_divergence&start=2024-01-01&end=2024-06-30&capital=50000000')
    mock_run.assert_called_once_with(
        symbol='VGI',
        strategy_name='rsi_divergence',
        start_date='2024-01-01',
        end_date='2024-06-30',
        initial_capital=50_000_000.0,
    )


@patch('app.routers.backtest.run_backtest')
def test_backtest_returns_400_on_value_error(mock_run):
    mock_run.side_effect = ValueError('No data returned for FAKE')
    response = client.get('/backtest/FAKE')
    assert response.status_code == 400
    assert 'No data returned for FAKE' in response.json()['detail']


@patch('app.routers.backtest.run_backtest')
def test_backtest_default_strategy_is_rsi_divergence(mock_run):
    mock_run.return_value = _mock_result()
    client.get('/backtest/VGI')
    assert mock_run.call_args.kwargs['strategy_name'] == 'rsi_divergence'
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && python -m pytest tests/routers/test_backtest.py -v
```

Expected: 404 responses or `ImportError` — router not yet created or registered.

- [ ] **Step 3: Implement `backend/app/routers/backtest.py`**

```python
from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Query
from app.services.backtest_service import run_backtest

router = APIRouter(prefix='/backtest', tags=['backtest'])


@router.get('/{symbol}')
def get_backtest(
    symbol: str,
    strategy: str = Query(default='rsi_divergence'),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    capital: float = Query(default=100_000_000.0),
) -> dict:
    try:
        result = run_backtest(
            symbol=symbol,
            strategy_name=strategy,
            start_date=start,
            end_date=end,
            initial_capital=capital,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return asdict(result)
```

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Add the import at the top with the other router imports:

```python
from app.routers import backtest
```

Add the include after the existing `app.include_router` calls:

```python
app.include_router(backtest.router)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/routers/test_backtest.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Run the full test suite**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/backtest.py \
        backend/tests/routers/test_backtest.py \
        backend/app/main.py
git commit -m "feat: add GET /backtest/{symbol} endpoint"
```

---

## Task 6: Cleanup

**Files:**
- Modify: `backend/app/services/stock_api_service.py`
- Modify: `backend/app/workers/stock_worker.py`
- Delete: `backend/app/utils/stock_util.py`

- [ ] **Step 1: Delete the empty `stock_util.py` stub**

```bash
git rm backend/app/utils/stock_util.py
```

- [ ] **Step 2: Update `stock_api_service.py`**

Remove the divergence helpers (`is_peak`, `is_trough`, `is_in_range`, `is_divergence`, `tim_phan_ky`, `simulate_trading`). Keep `get_price_today` and update `get_mock_price` to import `_find_divergences` from `rsi_divergence`.

Replace `backend/app/services/stock_api_service.py` with:

```python
from datetime import date
import talib
from vnstock import Quote
from app.algorithms.rsi_divergence import _find_divergences


def get_price_today(symbol: str = 'VGI'):
    quote = Quote(symbol=symbol, source='VCI')
    today = date.today()
    if today.weekday() in (5, 6):
        raise ValueError('Date is not a trading day')
    print(f'Getting price records on {today}...')
    try:
        records = quote.intraday()
        return records.to_json(orient='records')
    except Exception as e:
        print(f'Error fetching price today: {e}')
        raise


def get_mock_price(symbol: str = 'VGI'):
    print('Getting mock data...')
    quote = Quote(symbol=symbol, source='VCI')
    df = quote.intraday(symbol=symbol)
    df['RSI'] = talib.RSI(df['close'], timeperiod=14)
    df_filtered = df.dropna(subset=['RSI']).reset_index(drop=True)

    time_col = next((c for c in ['time', 'Time', 'datetime', 'date'] if c in df_filtered.columns), None)
    df_filtered['time'] = df_filtered[time_col].astype(str) if time_col else df_filtered.index.astype(str)

    records_list = df_filtered.to_dict(orient='records')
    print(f'Data loaded: {len(records_list)} candles.')
    divergences = _find_divergences(records_list)
    return records_list, divergences
```

- [ ] **Step 3: Update `stock_worker.py`**

Change the import at the top of `backend/app/workers/stock_worker.py` from:

```python
from app.services.stock_api_service import is_divergence, get_price_today, get_mock_price
```

to:

```python
from app.services.stock_api_service import get_price_today, get_mock_price
from app.algorithms.rsi_divergence import _has_divergence_at
```

- [ ] **Step 4: Verify imports are healthy**

```bash
cd backend && python -c "from app.routers.stock import router; print('stock router OK')"
cd backend && python -c "from app.workers.stock_worker import stock_worker; print('worker OK')"
cd backend && python -c "from app.services.stock_api_service import get_price_today, get_mock_price; print('stock_api_service OK')"
```

Expected: All three print their OK message.

- [ ] **Step 5: Run full test suite one final time**

```bash
cd backend && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/stock_api_service.py \
        backend/app/workers/stock_worker.py
git commit -m "refactor: retire stock_api_service divergence helpers, wire worker to rsi_divergence"
```
