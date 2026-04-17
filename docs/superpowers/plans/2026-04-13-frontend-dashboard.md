# Frontend Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-page React dashboard (Watchlist + Backtest) fully wired to the FastAPI backend, with a shared navbar and auth-aware axios layer.

**Architecture:** A shared `api.js` axios instance with a Bearer token interceptor handles all authenticated backend calls. `Layout.jsx` wraps both protected pages with a navbar. The backend gains two new endpoints (`GET /user/me`, `DELETE /user/remove_stock`) backed by a new `remove_stock_from_user` service function.

**Tech Stack:** React 19, Vite, Ant Design 6, Bootstrap 5, React Router v7, axios, FastAPI, pytest (backend tests only — no frontend test suite)

---

## File Map

**New files:**
- `backend/tests/routers/test_user.py` — tests for GET /user/me and DELETE /user/remove_stock
- `frontend/src/services/api.js` — axios instance with auth interceptor
- `frontend/src/services/user.js` — getMe, addStock, removeStock, getTelegramLink
- `frontend/src/services/backtest.js` — runBacktest
- `frontend/src/components/Layout.jsx` — navbar + Outlet wrapper
- `frontend/src/pages/Backtest.jsx` — backtest page

**Modified files:**
- `backend/app/services/user_service.py` — add `remove_stock_from_user`
- `backend/app/routers/user.py` — add GET /user/me, DELETE /user/remove_stock
- `frontend/src/App.jsx` — rewrite routing with Layout wrapper
- `frontend/src/pages/Home.jsx` — rewrite as watchlist page

**Deleted files:**
- `frontend/src/services/stocks.js` — replaced by user.js + api.js

---

## Task 1: Backend — /user/me and /user/remove_stock

**Files:**
- Modify: `backend/app/services/user_service.py`
- Modify: `backend/app/routers/user.py`
- Create: `backend/tests/routers/test_user.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/routers/test_user.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from fastapi import Request
from app.main import app
from app.utils.middlewares import authen_restricted
from app.schemas.user import UserResponse

_MOCK_USER = UserResponse(
    id=1,
    name='Test User',
    email='test@test.com',
    phone='0123456789',
    chat_id='',
    stocks=['VGI', 'VNM'],
)

async def _mock_authen(request: Request):
    request.state.user = _MOCK_USER

app.dependency_overrides[authen_restricted] = _mock_authen
client = TestClient(app)


def test_get_me_returns_current_user():
    response = client.get('/user/me')
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 1
    assert data['email'] == 'test@test.com'
    assert 'VGI' in data['stocks']


@patch('app.routers.user.remove_stock_from_user')
def test_remove_stock_calls_service_with_correct_args(mock_remove):
    mock_remove.return_value = UserResponse(
        id=1, name='Test User', email='test@test.com',
        phone='0123456789', chat_id='', stocks=['VNM'],
    )
    response = client.delete('/user/remove_stock', json={'symbol': 'VGI'})
    assert response.status_code == 200
    mock_remove.assert_called_once_with(user_id=1, stock_symbol='VGI')


@patch('app.routers.user.remove_stock_from_user')
def test_remove_stock_returns_updated_stocks(mock_remove):
    mock_remove.return_value = UserResponse(
        id=1, name='Test User', email='test@test.com',
        phone='0123456789', chat_id='', stocks=['VNM'],
    )
    response = client.delete('/user/remove_stock', json={'symbol': 'VGI'})
    data = response.json()
    assert 'VGI' not in data['stocks']
    assert 'VNM' in data['stocks']
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/routers/test_user.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'remove_stock_from_user'`

- [ ] **Step 3: Add `remove_stock_from_user` to `backend/app/services/user_service.py`**

Add after `add_stock_to_user` (line 170):

```python
def remove_stock_from_user(user_id: int, stock_symbol: str) -> UserResponse:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found"
            )

        stock = db.query(Stock).filter(Stock.symbol == stock_symbol).first()
        if stock:
            stmt = user_stock_association.delete().where(
                (user_stock_association.c.user_id == user.id) &
                (user_stock_association.c.stock_id == stock.id)
            )
            db.execute(stmt)
            db.commit()
            db.refresh(user)

        stocks_str = [s.symbol for s in user.stocks]
        return UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            chat_id=user.chat_id or '',
            stocks=stocks_str,
        )
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing stock from user: {str(e)}",
        )
    finally:
        db.close()
```

- [ ] **Step 4: Add GET /user/me and DELETE /user/remove_stock to `backend/app/routers/user.py`**

Add to the imports at the top of `user.py`:
```python
from app.services.user_service import get_all_users, create_user, add_stock_to_user, remove_stock_from_user
```

Add the two new endpoint functions after the existing `add_stock` endpoint:

```python
@router.get("/me")
def get_me(request: Request):
    return request.state.user


class RemoveStockRequest(BaseModel):
    symbol: str


@router.delete("/remove_stock")
def remove_stock_endpoint(data: RemoveStockRequest, request: Request):
    try:
        user = request.state.user
        return remove_stock_from_user(user_id=user.id, stock_symbol=data.symbol)
    except Exception as e:
        logger.error(f"Error removing stock from user {user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/routers/test_user.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 6: Run full suite to confirm no regressions**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: 66 passed (63 existing + 3 new).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/user_service.py \
        backend/app/routers/user.py \
        backend/tests/routers/test_user.py
git commit -m "feat: add GET /user/me and DELETE /user/remove_stock endpoints"
```

---

## Task 2: Frontend Services

**Files:**
- Create: `frontend/src/services/api.js`
- Create: `frontend/src/services/user.js`
- Create: `frontend/src/services/backtest.js`
- Delete: `frontend/src/services/stocks.js`

- [ ] **Step 1: Create `frontend/src/services/api.js`**

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

- [ ] **Step 2: Create `frontend/src/services/user.js`**

```js
import api from './api'

export const getMe = () => api.get('/user/me').then(r => r.data)

export const addStock = (userId, symbol) =>
  api.put('/user/add_stock', { user_id: userId, symbol }).then(r => r.data)

export const removeStock = (symbol) =>
  api.delete('/user/remove_stock', { data: { symbol } }).then(r => r.data)

export const getTelegramLink = () =>
  api.get('/user/telegram_connect').then(r => r.data)

export const getCompanies = () =>
  api.get('/company/all').then(r => r.data)
```

- [ ] **Step 3: Create `frontend/src/services/backtest.js`**

```js
import api from './api'

export const runBacktest = (symbol) =>
  api.get(`/backtest/${encodeURIComponent(symbol)}`).then(r => r.data)
```

- [ ] **Step 4: Delete the old stocks service**

```bash
git rm frontend/src/services/stocks.js
```

- [ ] **Step 5: Verify the frontend still starts**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/frontend && npm run dev 2>&1 | head -10
```

Expected: `VITE ready` with no errors. (The old `stocks.js` import in `Home.jsx` will break — that's expected and will be fixed in Task 4.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/api.js \
        frontend/src/services/user.js \
        frontend/src/services/backtest.js
git commit -m "feat: add api.js auth interceptor, user.js and backtest.js services"
```

---

## Task 3: App Routing and Layout

**Files:**
- Modify: `frontend/src/App.jsx`
- Create: `frontend/src/components/Layout.jsx`

- [ ] **Step 1: Create `frontend/src/components/Layout.jsx`**

```jsx
import { Outlet, Link, useNavigate } from 'react-router-dom'
import customStorage from '../utils/customStorage'

export default function Layout({ setCurUser }) {
  const navigate = useNavigate()

  const handleLogout = () => {
    customStorage.removeItem('localUser')
    setCurUser(null)
    navigate('/authen')
  }

  return (
    <div>
      <nav className="navbar navbar-expand-lg navbar-dark bg-dark px-4">
        <Link className="navbar-brand fw-bold" to="/">VN Stock Bot</Link>
        <div className="d-flex gap-3 mx-auto">
          <Link className="nav-link text-white" to="/">Watchlist</Link>
          <Link className="nav-link text-white" to="/backtest">Backtest</Link>
        </div>
        <button
          className="btn btn-outline-light btn-sm"
          onClick={handleLogout}
        >
          Logout
        </button>
      </nav>
      <div className="container py-4">
        <Outlet />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Rewrite `frontend/src/App.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import customStorage from './utils/customStorage'
import Authentication from './pages/Authentication'
import Home from './pages/Home'
import Backtest from './pages/Backtest'
import Layout from './components/Layout'

export default function App() {
  const [curUser, setCurUser] = useState(null)

  useEffect(() => {
    const loggedUser = customStorage.getItem('localUser')
    if (loggedUser) {
      setCurUser(JSON.parse(loggedUser))
    }
  }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/authen"
          element={<Authentication curUser={curUser} setCurUser={setCurUser} />}
        />
        <Route element={<Layout curUser={curUser} setCurUser={setCurUser} />}>
          <Route path="/" element={<Home curUser={curUser} />} />
          <Route path="/backtest" element={<Backtest />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 3: Verify routing works**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/frontend && npm run dev
```

Open `http://localhost:5173`. Verify:
- `/authen` shows the login page without navbar
- `/` shows the navbar (even if Home content is broken from the old import — that's fine, it gets fixed in Task 4)
- `/backtest` shows the navbar with an error (Backtest component not yet fully built — that's fine)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/Layout.jsx
git commit -m "feat: add Layout navbar and rewrite App routing"
```

---

## Task 4: Home Page (Watchlist)

**Files:**
- Modify: `frontend/src/pages/Home.jsx`

- [ ] **Step 1: Rewrite `frontend/src/pages/Home.jsx`**

```jsx
import { useState, useEffect } from 'react'
import { Input, Button, message, Tag, Spin } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getMe, addStock, removeStock, getTelegramLink, getCompanies } from '../services/user'

export default function Home({ curUser }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const [watchlist, setWatchlist] = useState([])
  const [companies, setCompanies] = useState([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!curUser) {
      navigate('/authen')
      return
    }
    Promise.all([getMe(), getCompanies()])
      .then(([me, cps]) => {
        setUser(me)
        setWatchlist(me.stocks)
        setCompanies(cps)
      })
      .catch(() => message.error('Failed to load data'))
      .finally(() => setLoading(false))
  }, [curUser])

  const handleAdd = (symbol) => {
    const prev = [...watchlist]
    if (prev.includes(symbol)) return
    setWatchlist([...prev, symbol])
    addStock(curUser.id, symbol)
      .then(updated => setWatchlist(updated.stocks))
      .catch(() => {
        setWatchlist(prev)
        message.error(`Failed to add ${symbol}`)
      })
  }

  const handleRemove = (symbol) => {
    const prev = [...watchlist]
    setWatchlist(prev.filter(s => s !== symbol))
    removeStock(symbol)
      .then(updated => setWatchlist(updated.stocks))
      .catch(() => {
        setWatchlist(prev)
        message.error(`Failed to remove ${symbol}`)
      })
  }

  const handleConnectTelegram = () => {
    getTelegramLink()
      .then(({ link }) => window.open(link, '_blank'))
      .catch(() => message.error('Failed to get Telegram link'))
  }

  const filtered = search.trim()
    ? companies.filter(c =>
        `${c.symbol} ${c.organ_name}`.toLowerCase().includes(search.toLowerCase())
      ).slice(0, 10)
    : []

  if (loading) return <div className="text-center mt-5"><Spin size="large" /></div>

  return (
    <div>
      <div className="d-flex justify-content-between align-items-center mb-4">
        <h4 className="mb-0">My Watchlist</h4>
        {user?.chat_id ? (
          <Tag color="green">Telegram Connected ✓</Tag>
        ) : (
          <Button onClick={handleConnectTelegram}>Connect Telegram</Button>
        )}
      </div>

      <div className="mb-4">
        {watchlist.length === 0 && (
          <p className="text-muted">No stocks yet. Search below to add some.</p>
        )}
        {watchlist.map(symbol => (
          <Tag
            key={symbol}
            closable
            onClose={() => handleRemove(symbol)}
            style={{ fontSize: '14px', padding: '4px 10px', marginBottom: '8px' }}
          >
            {symbol}
          </Tag>
        ))}
      </div>

      <div>
        <Input
          placeholder="Search by symbol or company name..."
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 400 }}
        />
        {filtered.map(c => (
          <div
            key={c.symbol}
            className="d-flex justify-content-between align-items-center border-bottom py-2"
            style={{ maxWidth: 400 }}
          >
            <span><strong>{c.symbol}</strong> — {c.organ_name}</span>
            <Button
              size="small"
              type="primary"
              disabled={watchlist.includes(c.symbol)}
              onClick={() => handleAdd(c.symbol)}
            >
              {watchlist.includes(c.symbol) ? 'Added' : 'Add'}
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Start the backend**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/uvicorn app.main:app --reload
```

- [ ] **Step 3: Start the frontend**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/frontend && npm run dev
```

- [ ] **Step 4: Verify manually**

1. Open `http://localhost:5173/authen` and log in
2. Redirected to `/` — verify navbar shows "Watchlist" and "Backtest" links
3. Watchlist shows your current stocks (fetched from `GET /user/me`)
4. Search for "VGI" — result appears
5. Click Add — "VGI" tag appears in watchlist, `PUT /user/add_stock` fires (check Network tab)
6. Click × on a tag — stock removed, `DELETE /user/remove_stock` fires
7. If `chat_id` is empty: "Connect Telegram" button shows. If set: green "Telegram Connected ✓" badge shows.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Home.jsx
git commit -m "feat: rewrite Home as watchlist page with add/remove/telegram"
```

---

## Task 5: Backtest Page

**Files:**
- Create: `frontend/src/pages/Backtest.jsx`

- [ ] **Step 1: Create `frontend/src/pages/Backtest.jsx`**

```jsx
import { useState } from 'react'
import { Input, Button, Spin, Alert, Statistic, Table } from 'antd'
import { runBacktest } from '../services/backtest'

const TRADE_COLUMNS = [
  { title: 'Date', dataIndex: 'date', key: 'date' },
  {
    title: 'Action',
    dataIndex: 'action',
    key: 'action',
    render: (v) => (
      <span style={{ color: v === 'buy' ? '#52c41a' : '#ff4d4f', fontWeight: 'bold' }}>
        {v.toUpperCase()}
      </span>
    ),
  },
  {
    title: 'Price (VND)',
    dataIndex: 'price',
    key: 'price',
    render: (v) => v.toLocaleString(),
  },
  { title: 'Shares', dataIndex: 'shares', key: 'shares' },
  {
    title: 'P&L (VND)',
    dataIndex: 'pnl',
    key: 'pnl',
    render: (v) =>
      v == null ? '—' : (
        <span style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {v.toLocaleString()}
        </span>
      ),
  },
]

export default function Backtest() {
  const [symbol, setSymbol] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const handleRun = () => {
    if (!symbol.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    runBacktest(symbol.trim())
      .then(data => setResult(data))
      .catch(err => setError(err.response?.data?.detail || 'Backtest failed'))
      .finally(() => setLoading(false))
  }

  return (
    <div style={{ maxWidth: 900 }}>
      <h4 className="mb-4">Backtest — RSI Divergence</h4>

      <div className="d-flex gap-2 mb-4" style={{ maxWidth: 400 }}>
        <Input
          placeholder="Symbol (e.g. VGI)"
          value={symbol}
          onChange={e => setSymbol(e.target.value.toUpperCase())}
          onPressEnter={handleRun}
          disabled={loading}
        />
        <Button type="primary" onClick={handleRun} disabled={loading || !symbol.trim()}>
          Run
        </Button>
      </div>

      {loading && <Spin size="large" />}

      {error && (
        <Alert
          type="error"
          message={error}
          showIcon
          className="mb-4"
          style={{ maxWidth: 500 }}
        />
      )}

      {result && (
        <div>
          <div className="row g-3 mb-4">
            <div className="col-6 col-md-3">
              <Statistic
                title="Total P&L (VND)"
                value={result.pnl}
                precision={0}
                valueStyle={{ color: result.pnl >= 0 ? '#52c41a' : '#ff4d4f' }}
              />
            </div>
            <div className="col-6 col-md-3">
              <Statistic
                title="P&L %"
                value={result.pnl_pct}
                precision={2}
                suffix="%"
                valueStyle={{ color: result.pnl_pct >= 0 ? '#52c41a' : '#ff4d4f' }}
              />
            </div>
            <div className="col-6 col-md-3">
              <Statistic title="Win Rate" value={result.win_rate} precision={1} suffix="%" />
            </div>
            <div className="col-6 col-md-3">
              <Statistic
                title="Max Drawdown"
                value={result.max_drawdown}
                precision={2}
                suffix="%"
                valueStyle={{ color: '#ff4d4f' }}
              />
            </div>
          </div>

          <Table
            dataSource={result.trades.map((t, i) => ({ ...t, key: i }))}
            columns={TRADE_COLUMNS}
            size="small"
            pagination={{ pageSize: 20 }}
          />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify manually**

1. Navigate to `http://localhost:5173/backtest`
2. Type `VGI` and press Enter (or click Run)
3. Spinner appears while loading
4. Results show: 4 metric cards + trade log table
5. Try `FAKEXXX` — error Alert appears with the API's detail message
6. Logout button clears session and redirects to `/authen`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Backtest.jsx
git commit -m "feat: add Backtest page with metrics and trade log"
```

---

## Task 6: Cleanup

**Files:**
- Verify `frontend/src/services/stocks.js` is already deleted (done in Task 2)
- Verify no remaining imports of the deleted file

- [ ] **Step 1: Check for any remaining references to stocks.js**

```bash
grep -r "from.*services/stocks\|require.*services/stocks" /Users/damianvu/Desktop/stock-bot-vn/frontend/src/
```

Expected: no output.

- [ ] **Step 2: Run backend test suite one final time**

```bash
cd /Users/damianvu/Desktop/stock-bot-vn/backend && .venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: 66 passed.

- [ ] **Step 3: Final smoke test**

With both backend and frontend running:
1. Log in at `/authen`
2. Add a stock from watchlist search
3. Remove it
4. Run a backtest on `VGI`
5. Click Logout — redirected to `/authen`, cannot reach `/` without logging in again

- [ ] **Step 4: Commit (if any cleanup changes were made)**

```bash
git add -A
git commit -m "chore: Phase 3 cleanup — remove stale imports"
```
