# Algorithm Layer Design
**Date:** 2026-04-12  
**Phase:** 1 of 3 (Algorithm Layer)  
**Stack:** FastAPI / Python backend, vnstock SDK, talib

---

## Overview

This spec covers Phase 1 of the Vietnamese stock trading bot: the algorithm layer. The goal is to define a clean, extensible algorithm interface with RSI Divergence as the reference implementation, backed by a proper backtesting framework that runs on daily OHLCV data and produces meaningful performance metrics.

Later phases (Signal Engine, Dashboard) will build on top of this layer.

---

## Scope

**In scope:**
- Algorithm abstraction (`BaseStrategy` ABC)
- RSI Divergence strategy (`RSIStrategy`) as the sole implementation
- Backtest runner (simulation loop, P&L, win rate, max drawdown, trade log)
- Daily OHLCV data fetching via vnstock
- REST endpoint: `GET /backtest/{symbol}`
- Rename Vietnamese function names to English

**Out of scope (later phases):**
- Additional algorithms (MACD, EMA, Bollinger Bands)
- Per-stock workers and Telegram signal dispatch
- Frontend dashboard

---

## Folder Structure

```
backend/app/
  algorithms/
    __init__.py          ← STRATEGIES registry: name → class mapping
    base.py              ← BaseStrategy ABC, BacktestResult, Trade dataclasses
    rsi_divergence.py    ← RSIStrategy(BaseStrategy) + private helper functions
  services/
    backtest_service.py  ← fetch data, run strategy, return BacktestResult
  routers/
    backtest.py          ← GET /backtest/{symbol}
```

`stock_util.py` is retired. Its responsibilities are split:
- Signal logic → `rsi_divergence.py`
- Simulation loop → `BaseStrategy.backtest()`
- Data fetching → `backtest_service.py`

---

## Data Classes (`base.py`)

```python
@dataclass
class Trade:
    action: str        # "buy" | "sell"
    date: str
    price: float
    shares: int
    pnl: float | None  # None on buy; realized profit/loss on sell

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
    win_rate: float     # % of completed trades where pnl > 0
    max_drawdown: float # worst peak-to-trough % loss during period
    total_trades: int   # number of completed buy+sell pairs
    trades: List[Trade]
```

---

## Algorithm Interface (`base.py`)

```python
class BaseStrategy(ABC):
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Subclass adds a 'signal' column to df:
          1  = buy
         -1  = sell
          0  = hold
        Returns the annotated DataFrame.
        """
        ...

    def backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        initial_capital: float = 100_000_000
    ) -> BacktestResult:
        """
        Shared simulation loop — identical for all strategies.
        Calls self.generate_signals(df) internally, then iterates
        signals to track position, capital, drawdown, and trade log.
        """
        ...
```

**Key rule:** Only `generate_signals` is overridden per strategy. The simulation loop lives once in `BaseStrategy.backtest()` and is never duplicated.

---

## Algorithm Registry (`__init__.py`)

```python
from .rsi_divergence import RSIStrategy

STRATEGIES = {
    "rsi_divergence": RSIStrategy,
}
```

Adding a new strategy later = one new file + one new line here.

---

## RSI Divergence Strategy (`rsi_divergence.py`)

### Private helpers (moved from `stock_util.py`, renamed to English)

| Old name | New name | Purpose |
|----------|----------|---------|
| `tim_phan_ky` | `find_divergences` | Scan full df, return all divergence events |
| `is_divergence` | `has_divergence_at` | Check for divergence at a single candle index |
| `is_peak` | `is_peak` | Unchanged |
| `is_trough` | `is_trough` | Unchanged |
| `is_in_range` | `is_in_range` | Unchanged |

### Signal generation

```python
class RSIStrategy(BaseStrategy):
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # 1. Run find_divergences(df) to get all divergence events
        # 2. For each bullish divergence → signal=1 at suffix index
        # 3. For each bearish divergence → signal=-1 at suffix index
        # 4. All other rows → signal=0
        # 5. Conflict rule: if bearish and bullish land on same candle,
        #    bearish (-1) takes priority
        # 6. Return annotated df
```

`find_divergences` is used in backtesting (full scan). `has_divergence_at` will be used by the live worker in Phase 2 (single candle check per tick).

---

## Backtest Service (`backtest_service.py`)

```python
def run_backtest(
    symbol: str,
    strategy_name: str,
    start_date: str,   # "YYYY-MM-DD"
    end_date: str,     # "YYYY-MM-DD"
    initial_capital: float = 100_000_000
) -> BacktestResult:
    # 1. Fetch daily OHLCV:
    #    Quote(symbol, source='VCI').history(start=start_date, end=end_date, interval='1D')
    # 2. Compute RSI: talib.RSI(df['close'], timeperiod=14), drop NaN rows
    # 3. Look up strategy: STRATEGIES[strategy_name]
    # 4. strategy.generate_signals(df)
    # 5. strategy.backtest(df, symbol, initial_capital)
    # 6. Return BacktestResult
```

**Default date range:** last 365 days from today if caller omits dates.

**Error cases:**
- Empty df from vnstock → `ValueError("No data returned for {symbol}")`
- Unknown strategy name → `ValueError("Unknown strategy: {strategy_name}")`
- Fewer than 30 candles after RSI warmup → `ValueError("Insufficient data for backtest")`

---

## API Endpoint (`routers/backtest.py`)

```
GET /backtest/{symbol}
```

| Param | Type | Required | Default |
|-------|------|----------|---------|
| `symbol` | path string | yes | — |
| `strategy` | query string | no | `rsi_divergence` |
| `start` | query string (YYYY-MM-DD) | no | 365 days ago |
| `end` | query string (YYYY-MM-DD) | no | today |
| `capital` | query float | no | `100_000_000` |

**Success response (200):** Serialized `BacktestResult` JSON.

**Example:**
```json
{
  "symbol": "VGI",
  "strategy": "rsi_divergence",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "initial_capital": 100000000,
  "final_value": 118500000,
  "pnl": 18500000,
  "pnl_pct": 18.5,
  "win_rate": 62.5,
  "max_drawdown": -8.3,
  "total_trades": 8,
  "trades": [
    { "action": "buy", "date": "2024-02-15", "price": 24500, "shares": 4081, "pnl": null },
    { "action": "sell", "date": "2024-03-01", "price": 26200, "shares": 4081, "pnl": 6937700 }
  ]
}
```

**Error responses:**
- `400` for invalid symbol, unknown strategy, insufficient date range
- `422` for malformed query params (FastAPI default validation)

---

## What Does NOT Change

- Auth, user, user_stock models and routers — untouched
- Telegram integration — untouched
- `stock_worker.py` — untouched (Phase 2 will wire it to the new algorithm interface)
- Frontend — untouched (Phase 3)
