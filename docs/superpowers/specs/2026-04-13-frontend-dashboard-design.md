# Frontend Dashboard Design
**Date:** 2026-04-13
**Phase:** 3 of 3 (Frontend Dashboard)
**Stack:** React 19, Vite, Ant Design 6, Bootstrap 5, React Router v7, axios

---

## Overview

Phase 3 adds a web dashboard that complements the Telegram signal bot. Users can manage their stock watchlist and run backtests against the RSI divergence strategy. The dashboard is wired to the existing FastAPI backend. UI polish is secondary to correctness and wiring.

---

## Scope

**In scope:**
- Shared Layout with navbar (Watchlist / Backtest links + Logout)
- Home page (`/`): view watchlist, add stocks via search, remove stocks, connect Telegram
- Backtest page (`/backtest`): enter symbol, view metrics + trade log
- `services/api.js`: axios instance with auth interceptor (Bearer token + 401 redirect)
- `services/user.js`: getMe, addStock, removeStock, getTelegramLink
- `services/backtest.js`: runBacktest
- Backend: `GET /user/me` and `DELETE /user/remove_stock`

**Out of scope:**
- Registration / password reset
- Signal history display
- Charts or price graphs
- Mobile-specific styling

---

## Backend Additions

### `GET /user/me`

Protected (requires `Authorization: Bearer <token>`). Returns the current user's profile using `request.state.user` (already populated by `authen_restricted` middleware).

```python
@router.get("/me")
def get_me(request: Request):
    user = request.state.user
    return user
```

Response shape (existing `UserResponse`):
```json
{
  "id": 1,
  "email": "user@example.com",
  "chat_id": "123456789",
  "stocks": ["VGI", "VNM"]
}
```

### `DELETE /user/remove_stock`

Protected. Removes a stock symbol from the current user's watchlist.

```python
class RemoveStockRequest(BaseModel):
    symbol: str

@router.delete("/remove_stock")
def remove_stock(data: RemoveStockRequest, request: Request):
    user = request.state.user
    updated = remove_stock_from_user(user_id=user.id, stock_symbol=data.symbol)
    return updated
```

Adds `remove_stock_from_user(user_id, stock_symbol)` to `user_service.py`. Mirrors `add_stock_to_user`: loads the user, filters out the symbol from `user.stocks`, saves, returns `UserResponse`.

---

## Frontend File Structure

```
frontend/src/
  components/
    Layout.jsx              ← navbar + <Outlet /> wrapper
  pages/
    Authentication.jsx      ← existing, unchanged
    Home.jsx                ← rewrite: watchlist page
    Backtest.jsx            ← new: backtest page
  services/
    api.js                  ← axios instance with auth interceptor
    login.js                ← existing, unchanged (unprotected)
    user.js                 ← getMe, addStock, removeStock, getTelegramLink
    backtest.js             ← runBacktest
  utils/
    homeUrl.js              ← existing, unchanged
    customStorage.js        ← existing, unchanged
```

`frontend/src/services/stocks.js` — deleted (replaced by `user.js` + direct company call via `api.js`).

---

## Routing (`App.jsx`)

```jsx
<BrowserRouter>
  <Routes>
    <Route path="/authen" element={<Authentication curUser={curUser} setCurUser={setCurUser} />} />
    <Route element={<Layout curUser={curUser} setCurUser={setCurUser} />}>
      <Route path="/" element={<Home curUser={curUser} />} />
      <Route path="/backtest" element={<Backtest />} />
    </Route>
  </Routes>
</BrowserRouter>
```

`Authentication` sits outside the Layout route so it renders without the navbar.

---

## `services/api.js`

Axios instance that automatically injects the auth token on every request and redirects to `/authen` on 401/400 auth errors.

```js
import axios from 'axios'
import { backendBase } from '../utils/homeUrl'
import customStorage from '../utils/customStorage'

const api = axios.create({ baseURL: backendBase })

api.interceptors.request.use((config) => {
  const localUser = customStorage.getItem('localUser')
  if (localUser) {
    const { token } = JSON.parse(localUser)
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 400 || err.response?.status === 401) {
      const detail = err.response?.data?.detail || ''
      if (detail.includes('authenticated') || detail.includes('Token')) {
        customStorage.removeItem('localUser')
        window.location.href = '/authen'
      }
    }
    return Promise.reject(err)
  }
)

export default api
```

---

## `services/user.js`

```js
import api from './api'

export const getMe = () => api.get('/user/me').then(r => r.data)
export const addStock = (userId, symbol) =>
  api.put('/user/add_stock', { user_id: userId, symbol }).then(r => r.data)
export const removeStock = (symbol) =>
  api.delete('/user/remove_stock', { data: { symbol } }).then(r => r.data)
export const getTelegramLink = () =>
  api.get('/user/telegram_connect').then(r => r.data)
```

---

## `services/backtest.js`

```js
import api from './api'

export const runBacktest = (symbol) =>
  api.get(`/backtest/${symbol}`).then(r => r.data)
```

---

## `components/Layout.jsx`

Renders a top navbar with:
- Left: "VN Stock Bot" brand link (`/`)
- Center: "Watchlist" link (`/`) and "Backtest" link (`/backtest`)
- Right: Logout button — clears `localUser` from localStorage, calls `setCurUser(null)`, redirects to `/authen`

Uses Ant Design `Menu` or simple nav links. Renders `<Outlet />` below the navbar for page content.

---

## `pages/Home.jsx` (Watchlist)

**On mount:**
1. If no `curUser`, redirect to `/authen`
2. `GET /user/me` → set `watchlist` state (array of symbol strings)
3. `GET /company/all` → set `companies` state (fetched once, filtered client-side)

**Watchlist section:**
- Heading: "My Watchlist"
- List of current symbols, each with a Remove button
- Remove calls `DELETE /user/remove_stock`, removes from local state optimistically, reverts on error with `message.error`

**Add stock section:**
- Search input (Ant Design `Input`) — filters `companies` client-side by symbol or name
- Dropdown/list of filtered results, each with an Add button
- Add calls `PUT /user/add_stock`, appends to local `watchlist` optimistically, reverts on error

**Telegram section:**
- If `user.chat_id` is set: show "Telegram Connected ✓" badge
- If not: "Connect Telegram" button → calls `GET /user/telegram_connect` → opens link in new tab

---

## `pages/Backtest.jsx`

**State:** `symbol` (input), `loading`, `result`, `error`

**Form:**
- Ant Design `Input` for symbol (uppercase enforced on change)
- Run button (disabled while loading)

**On submit:**
- Set `loading = true`, clear `error` and `result`
- Call `GET /backtest/{symbol}`
- On success: set `result`, `loading = false`
- On error: extract `error.response.data.detail`, set `error`, `loading = false`

**Results display (shown when `result` is set):**
- 4 Ant Design `Statistic` cards in a row:
  - Total P&L (`result.pnl`, formatted with commas, VND)
  - P&L % (`result.pnl_pct`, 2 decimal places)
  - Win Rate (`result.win_rate`, percentage)
  - Max Drawdown (`result.max_drawdown`, percentage)
- Ant Design `Table` below for trade log (`result.trades`):
  - Columns: Date, Action (BUY/SELL), Price, Shares, P&L (shown only for SELL rows, blank for BUY)

**Error display:** Ant Design `Alert` with `type="error"` showing the detail string.

---

## Error Handling Summary

| Scenario | Behaviour |
|---|---|
| Not logged in (no token) | Redirect to `/authen` |
| Token expired / invalid | Auth interceptor clears storage, redirects to `/authen` |
| Add stock fails | Revert optimistic update, `message.error` with API detail |
| Remove stock fails | Revert optimistic update, `message.error` with API detail |
| Backtest symbol unknown | Show `Alert` with API `detail` string |
| Backtest insufficient data | Show `Alert` with API `detail` string |
| Company list fails to load | `message.error`, search input disabled |

---

## What Does NOT Change

- `Authentication.jsx` — untouched
- `login.js` — untouched (uses plain axios, unprotected endpoint)
- `utils/homeUrl.js`, `utils/customStorage.js` — untouched
- All backend routers except `user.py` — untouched
- All Phase 1 and Phase 2 backend code — untouched
