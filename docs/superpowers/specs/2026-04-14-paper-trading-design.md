# Paper Trading Engine Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-user paper trading engine that automatically opens virtual positions when RSI divergence signals fire, manages exits via stop-loss / take-profit / time-stop rules, notifies via Telegram, and displays results on a new dashboard page.

**Architecture:** A dedicated `paper_trading_service.py` handles all trade logic. Existing signal workers call a single `on_signal()` hook. A new price-check scheduler runs every 5 minutes during market hours (09:00–15:00 VN time) to evaluate open positions. This service boundary is the seam Phase B (semi-auto real orders) will replace with `order_service.py`.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, APScheduler (already used by workers), vnstock via `stock_api_service`, python-telegram-bot, React 19, Ant Design 6, recharts (for P&L curve)

---

## Phase Scope

This is **Phase A (paper trading)** of a two-phase automated trading roadmap:
- **Phase A (this spec):** Simulate trades with virtual capital. No real orders.
- **Phase B (future):** Semi-auto real orders — bot proposes via Telegram button, user confirms.

Phase B will reuse all data models and service interfaces defined here.

---

## Trade Rules

| Parameter | Value |
|-----------|-------|
| Starting virtual balance | 100,000,000 VND per user |
| Position size | 10% of current total portfolio value per trade |
| Max concurrent positions | 10 open positions per user |
| Stop-loss | −7% from entry price |
| Take-profit | +15% from entry price |
| Max hold time | 30 calendar days |
| Direction | Long only (buy on bullish RSI divergence) |

**Quantity calculation:** `quantity = floor((portfolio_total_value × 0.10) / entry_price)`. Minimum 1 share or skip. Skip if `available_cash < position_value`.

**Portfolio total value:** `available_cash + sum(position_value of all open trades)` — used for position sizing so compounding works correctly.

---

## Data Models

### `PaperPortfolio` (one row per user)

| column | type | notes |
|--------|------|-------|
| `id` | int PK | |
| `user_id` | int FK → users | unique |
| `starting_balance` | bigint | VND, default 100,000,000 |
| `available_cash` | bigint | decreases on open, restores on close |
| `created_at` | datetime | |

Lazy-created on the first signal a user receives. No manual setup required.

### `PaperTrade` (one row per trade)

| column | type | notes |
|--------|------|-------|
| `id` | int PK | |
| `user_id` | int FK → users | |
| `symbol` | varchar(20) | e.g. "VNM" |
| `entry_price` | float | VND per share |
| `quantity` | int | shares bought |
| `position_value` | bigint | entry_price × quantity |
| `stop_loss_price` | float | entry_price × 0.93 |
| `take_profit_price` | float | entry_price × 1.15 |
| `entry_time` | datetime | UTC |
| `exit_price` | float | null if open |
| `exit_time` | datetime | null if open |
| `exit_reason` | enum | `stop_loss`, `take_profit`, `time_stop`, `manual` |
| `pnl_amount` | bigint | VND, null if open |
| `pnl_pct` | float | %, null if open |
| `status` | enum | `open`, `closed` |

---

## Service Layer

### `backend/app/services/paper_trading_service.py`

**`on_signal(user_id: int, symbol: str, entry_price: float) -> PaperTrade | None`**

1. Load or lazy-create `PaperPortfolio` for `user_id`
2. Count open trades for user — if ≥ 10, log and return `None`
3. Compute `portfolio_total_value = available_cash + sum(open position_values)`
4. Compute `position_value = floor(portfolio_total_value × 0.10 / entry_price) × entry_price`
5. Compute `quantity = floor(portfolio_total_value × 0.10 / entry_price)`
6. If `quantity < 1` or `available_cash < position_value`, return `None`
7. Deduct `position_value` from `available_cash`
8. Create and persist `PaperTrade` with `status=open`
9. Send Telegram message to user's `chat_id` (if connected):
   `📈 Paper long {symbol} @ {entry_price:,.0f} | SL: {sl:,.0f} | TP: {tp:,.0f} | Size: {position_value/1e6:.1f}M VND`
10. Return the created trade

**`check_positions(db: Session) -> None`**

Called by scheduler every 5 minutes during 09:00–15:00 VN time on trading days.

1. Fetch all `PaperTrade` where `status = open`
2. Group by symbol, batch-fetch current prices via `stock_api_service.get_current_price(symbol)`
3. For each trade, evaluate in this order:
   - `current_price ≤ stop_loss_price` → close with `exit_reason=stop_loss`
   - `current_price ≥ take_profit_price` → close with `exit_reason=take_profit`
   - `now - entry_time ≥ 30 days` → close with `exit_reason=time_stop` using current price
4. On close: set `exit_price`, `exit_time`, `exit_reason`, compute `pnl_amount = (exit_price - entry_price) × quantity`, `pnl_pct = (exit_price - entry_price) / entry_price × 100`, set `status=closed`
5. Restore `available_cash += position_value` on close (return original capital, P&L is separate)
6. Send Telegram per closed trade:
   - Take-profit: `✅ {symbol} +{pnl_pct:.1f}% (+{pnl:,.0f} VND) | take-profit`
   - Stop-loss: `🔴 {symbol} {pnl_pct:.1f}% ({pnl:,.0f} VND) | stopped out`
   - Time-stop: `⏱ {symbol} {pnl_pct:.1f}% ({pnl:,.0f} VND) | 30-day exit`

**`close_position(trade_id: int, user_id: int, db: Session) -> PaperTrade`**

Manual close. Sets `exit_reason=manual`, uses current price from `stock_api_service`. Same close logic as above.

**`get_portfolio_summary(user_id: int, db: Session) -> dict`**

Returns:
```json
{
  "starting_balance": 100000000,
  "available_cash": 73500000,
  "open_positions": 3,
  "total_pnl_amount": 4200000,
  "total_pnl_pct": 4.2,
  "win_rate": 66.7,
  "total_closed_trades": 9,
  "best_trade": { "symbol": "VNM", "pnl_pct": 15.0 },
  "worst_trade": { "symbol": "HPG", "pnl_pct": -7.0 }
}
```

---

## Worker Integration

### `backend/app/workers/daily_worker.py` and `intraday_worker.py`

After generating a signal and sending the Telegram alert, add:

```python
from app.services import paper_trading_service

# existing signal delivery code...
paper_trading_service.on_signal(
    user_id=user.id,
    symbol=symbol,
    entry_price=current_price,
)
```

### New price-check scheduler

Add to the existing APScheduler setup in `main.py`:

```python
scheduler.add_job(
    paper_trading_service.check_positions,
    'cron',
    day_of_week='mon-fri',
    hour='9-15',
    minute='*/5',
    timezone='Asia/Ho_Chi_Minh',
)
```

---

## API Endpoints

New router: `backend/app/routers/paper_trading.py`  
All endpoints require JWT auth via `authen_restricted` dependency.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/paper-trading/portfolio` | Portfolio summary (balance, cash, P&L, win rate) |
| `GET` | `/paper-trading/positions` | Open trades with live unrealized P&L |
| `GET` | `/paper-trading/trades` | Closed trade history, paginated, sorted by exit_time desc |
| `DELETE` | `/paper-trading/positions/{trade_id}` | Manually close an open position |

**`GET /paper-trading/positions`** fetches current prices live at request time so unrealized P&L is fresh. No frontend polling needed.

**`GET /paper-trading/trades`** accepts `?page=1&limit=20` query params.

---

## Frontend

### New page: `frontend/src/pages/PaperTrading.jsx`

Four sections, top to bottom:

**1. Portfolio Summary Strip**
Row of stat cards: Virtual Balance | Available Cash | Open Positions | Total P&L (colored) | Win Rate %

**2. Open Positions Table** (antd Table)
Columns: Symbol | Entry Price | Current Price | Unrealized P&L % | Size (VND) | Days Held | Stop Loss | Take Profit | Action
- Unrealized P&L cell: green if positive, red if negative
- Action: "Close" button → `DELETE /paper-trading/positions/{id}` → refresh table
- Manual refresh button top-right of table

**3. Closed Trades Table** (antd Table, paginated)
Columns: Symbol | Entry Price | Exit Price | P&L % | P&L (VND) | Exit Reason | Exit Date
- Exit reason as antd Tag: `take-profit` green, `stop-loss` red, `time-stop` grey, `manual` grey
- Sorted by exit_time descending

**4. Cumulative P&L Curve** (recharts LineChart)
- x-axis: exit_date of each closed trade
- y-axis: running portfolio value (starting_balance + cumulative pnl_amount)
- Computed client-side from the closed trades list

### Nav update: `frontend/src/components/Layout.jsx`

Add "Paper Trading" link to navbar pointing to `/paper-trading`.

### New route in `frontend/src/App.jsx`

```jsx
<Route path="/paper-trading" element={<PaperTrading curUser={curUser} />} />
```

Inside the `<Layout>` wrapper so it gets the navbar.

### New service: `frontend/src/services/paperTrading.js`

```js
import api from './api'

export const getPortfolio = () => api.get('/paper-trading/portfolio').then(r => r.data)
export const getPositions = () => api.get('/paper-trading/positions').then(r => r.data)
export const getTrades = (page = 1) => api.get(`/paper-trading/trades?page=${page}&limit=20`).then(r => r.data)
export const closePosition = (id) => api.delete(`/paper-trading/positions/${id}`).then(r => r.data)
```

---

## File Summary

**New files:**
- `backend/app/models/paper_trading.py` — SQLAlchemy models for `PaperPortfolio` and `PaperTrade`
- `backend/app/services/paper_trading_service.py` — all trade logic
- `backend/app/routers/paper_trading.py` — API endpoints
- `frontend/src/pages/PaperTrading.jsx` — dashboard page
- `frontend/src/services/paperTrading.js` — API calls

**Modified files:**
- `backend/app/main.py` — register router, add price-check scheduler job
- `backend/app/workers/daily_worker.py` — call `on_signal()` after signal fires
- `backend/app/workers/intraday_worker.py` — call `on_signal()` after signal fires
- `frontend/src/App.jsx` — add `/paper-trading` route
- `frontend/src/components/Layout.jsx` — add "Paper Trading" nav link

---

## Out of Scope (Phase B)

- Real broker API integration (SSI, VPS, TCBS)
- Telegram confirmation buttons for real order placement
- Multiple algorithms or strategy configuration
- Short selling
- Portfolio reset / multiple portfolios per user
