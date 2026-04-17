import { useState, useEffect, useCallback } from 'react'
import { Statistic, Table, Tag, Button, Spin, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useNavigate } from 'react-router-dom'
import { getPortfolio, getPositions, getTrades, closePosition } from '../services/paperTrading'

const EXIT_REASON_COLORS = {
  take_profit: 'success',
  stop_loss: 'error',
  time_stop: 'default',
  manual: 'default',
}

const EXIT_REASON_LABELS = {
  take_profit: 'Take Profit',
  stop_loss: 'Stop Loss',
  time_stop: 'Time Stop',
  manual: 'Manual',
}

function fmt(n) {
  return n == null ? '—' : n.toLocaleString('vi-VN')
}

function pnlColor(v) {
  if (v == null) return undefined
  return v >= 0 ? '#52c41a' : '#ff4d4f'
}

export default function PaperTrading({ curUser }) {
  const navigate = useNavigate()
  const [portfolio, setPortfolio] = useState(null)
  const [positions, setPositions] = useState([])
  const [trades, setTrades] = useState([])
  const [tradesTotal, setTradesTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [positionsLoading, setPositionsLoading] = useState(false)
  const [closingId, setClosingId] = useState(null)

  useEffect(() => {
    if (!curUser) {
      navigate('/authen')
    }
  }, [curUser, navigate])

  const loadAll = useCallback(() => {
    setLoading(true)
    Promise.all([getPortfolio(), getPositions(), getTrades(1)])
      .then(([p, pos, t]) => {
        setPortfolio(p)
        setPositions(pos)
        setTrades(t.trades)
        setTradesTotal(t.total)
        setPage(1)
      })
      .catch(() => message.error('Failed to load paper trading data'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (curUser) loadAll()
  }, [curUser, loadAll])

  const loadPositions = () => {
    setPositionsLoading(true)
    Promise.all([getPortfolio(), getPositions()])
      .then(([p, pos]) => {
        setPortfolio(p)
        setPositions(pos)
      })
      .catch(() => message.error('Failed to refresh positions'))
      .finally(() => setPositionsLoading(false))
  }

  const handleClose = (id) => {
    setClosingId(id)
    closePosition(id)
      .then(() => {
        message.success('Position closed')
        loadAll()
      })
      .catch(() => message.error('Failed to close position'))
      .finally(() => setClosingId(null))
  }

  const loadPage = (newPage) => {
    getTrades(newPage)
      .then(t => {
        setTrades(t.trades)
        setTradesTotal(t.total)
        setPage(newPage)
      })
      .catch(() => message.error('Failed to load trades'))
  }

  // Build cumulative P&L curve from closed trades (sorted oldest first for chart)
  const pnlCurve = (() => {
    if (!portfolio || trades.length === 0) return []
    const sorted = [...trades].reverse() // trades come newest-first; reverse for chronological
    let running = portfolio.starting_balance
    return sorted.map(t => {
      running += t.pnl_amount || 0
      return {
        date: t.exit_time ? t.exit_time.slice(0, 10) : '',
        value: running,
      }
    })
  })()

  const POSITION_COLUMNS = [
    { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: v => <strong>{v}</strong> },
    { title: 'Entry Price', dataIndex: 'entry_price', key: 'entry_price', render: fmt },
    { title: 'Current Price', dataIndex: 'current_price', key: 'current_price', render: fmt },
    {
      title: 'Unrealized P&L %',
      dataIndex: 'unrealized_pnl_pct',
      key: 'unrealized_pnl_pct',
      render: v => <span style={{ color: pnlColor(v) }}>{v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—'}</span>,
    },
    {
      title: 'Size (VND)',
      dataIndex: 'position_value',
      key: 'position_value',
      render: fmt,
    },
    { title: 'Days Held', dataIndex: 'days_held', key: 'days_held' },
    { title: 'Stop Loss', dataIndex: 'stop_loss_price', key: 'stop_loss_price', render: fmt },
    { title: 'Take Profit', dataIndex: 'take_profit_price', key: 'take_profit_price', render: fmt },
    {
      title: 'Action',
      key: 'action',
      render: (_, row) => (
        <Button
          size="small"
          danger
          loading={closingId === row.id}
          onClick={() => handleClose(row.id)}
        >
          Close
        </Button>
      ),
    },
  ]

  const TRADE_COLUMNS = [
    { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', render: v => <strong>{v}</strong> },
    { title: 'Entry Price', dataIndex: 'entry_price', key: 'entry_price', render: fmt },
    { title: 'Exit Price', dataIndex: 'exit_price', key: 'exit_price', render: fmt },
    {
      title: 'P&L %',
      dataIndex: 'pnl_pct',
      key: 'pnl_pct',
      render: v => <span style={{ color: pnlColor(v) }}>{v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—'}</span>,
    },
    {
      title: 'P&L (VND)',
      dataIndex: 'pnl_amount',
      key: 'pnl_amount',
      render: v => <span style={{ color: pnlColor(v) }}>{v != null ? `${v >= 0 ? '+' : ''}${fmt(v)}` : '—'}</span>,
    },
    {
      title: 'Exit Reason',
      dataIndex: 'exit_reason',
      key: 'exit_reason',
      render: v => v ? <Tag color={EXIT_REASON_COLORS[v]}>{EXIT_REASON_LABELS[v] || v}</Tag> : '—',
    },
    {
      title: 'Exit Date',
      dataIndex: 'exit_time',
      key: 'exit_time',
      render: v => v ? v.slice(0, 10) : '—',
    },
  ]

  if (loading) {
    return <div className="text-center mt-5"><Spin size="large" /></div>
  }

  return (
    <div>
      <h4 className="mb-4">Paper Trading</h4>

      {/* 1. Portfolio Summary Strip */}
      {portfolio && (
        <div className="row g-3 mb-4">
          <div className="col-6 col-md-2">
            <Statistic title="Virtual Balance" value={portfolio.starting_balance} formatter={fmt} />
          </div>
          <div className="col-6 col-md-2">
            <Statistic title="Available Cash" value={portfolio.available_cash} formatter={fmt} />
          </div>
          <div className="col-6 col-md-2">
            <Statistic title="Open Positions" value={portfolio.open_positions} />
          </div>
          <div className="col-6 col-md-2">
            <Statistic
              title="Total P&L (VND)"
              value={portfolio.total_pnl_amount}
              formatter={v => <span style={{ color: pnlColor(v) }}>{v >= 0 ? '+' : ''}{fmt(v)}</span>}
            />
          </div>
          <div className="col-6 col-md-2">
            <Statistic
              title="Win Rate"
              value={portfolio.win_rate}
              suffix="%"
              precision={1}
            />
          </div>
          <div className="col-6 col-md-2">
            <Statistic title="Closed Trades" value={portfolio.total_closed_trades} />
          </div>
        </div>
      )}

      {/* 2. Open Positions Table */}
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h5 className="mb-0">Open Positions</h5>
        <Button
          icon={<ReloadOutlined />}
          size="small"
          loading={positionsLoading}
          onClick={loadPositions}
        >
          Refresh
        </Button>
      </div>
      <Table
        dataSource={positions.map(p => ({ ...p, key: p.id }))}
        columns={POSITION_COLUMNS}
        size="small"
        pagination={false}
        className="mb-4"
        locale={{ emptyText: 'No open positions' }}
      />

      {/* 3. Closed Trades Table */}
      <h5 className="mb-2">Trade History</h5>
      <Table
        dataSource={trades.map(t => ({ ...t, key: t.id }))}
        columns={TRADE_COLUMNS}
        size="small"
        pagination={{
          current: page,
          total: tradesTotal,
          pageSize: 20,
          onChange: loadPage,
          showTotal: total => `${total} trades`,
        }}
        className="mb-4"
        locale={{ emptyText: 'No closed trades yet' }}
      />

      {/* 4. Cumulative P&L Curve */}
      {pnlCurve.length > 0 && (
        <div>
          <h5 className="mb-2">Cumulative Portfolio Value</h5>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={pnlCurve} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis
                tickFormatter={v => `${(v / 1_000_000).toFixed(1)}M`}
                tick={{ fontSize: 11 }}
              />
              <Tooltip formatter={v => [`${fmt(v)} VND`, 'Portfolio Value']} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="#1890ff"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
