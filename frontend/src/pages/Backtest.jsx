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
