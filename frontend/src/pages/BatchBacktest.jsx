import { useState, useEffect, useRef } from 'react'
import { Button, Spin, Alert, Table, Tag, Progress, Select } from 'antd'
import { startBatchBacktest, getBatchStatus, getBatchResults } from '../services/batchBacktest'

const STRATEGIES = [
  { value: 'rsi_divergence',    label: 'RSI Divergence',    color: 'blue' },
  { value: 'ema_macd',          label: 'EMA + MACD',        color: 'purple' },
  { value: 'donchian_breakout', label: 'Donchian Breakout', color: 'orange' },
]

const PERIODS = [
  { value: '2024-01-01|2025-12-31', label: '2024–2025 (2 years)' },
  { value: '2024-01-01|2024-12-31', label: '2024 only' },
  { value: '2025-01-01|2025-12-31', label: '2025 only' },
]

const strategyMeta = Object.fromEntries(STRATEGIES.map(s => [s.value, s]))

const COLUMNS = [
  { title: 'Symbol', dataIndex: 'symbol', key: 'symbol', width: 80,
    render: v => <strong>{v}</strong> },
  { title: 'Strategy', dataIndex: 'strategy_name', key: 'strategy_name', width: 160,
    render: v => {
      const m = strategyMeta[v]
      return <Tag color={m?.color ?? 'default'}>{m?.label ?? v}</Tag>
    },
    filters: STRATEGIES.map(s => ({ text: s.label, value: s.value })),
    onFilter: (value, record) => record.strategy_name === value,
  },
  {
    title: 'P&L %', dataIndex: 'pnl_pct', key: 'pnl_pct', width: 90,
    sorter: (a, b) => a.pnl_pct - b.pnl_pct,
    defaultSortOrder: 'descend',
    render: v => (
      <span style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f', fontWeight: 600 }}>
        {v >= 0 ? '+' : ''}{v.toFixed(2)}%
      </span>
    ),
  },
  {
    title: 'P&L (VND)', dataIndex: 'pnl', key: 'pnl', width: 130,
    sorter: (a, b) => a.pnl - b.pnl,
    render: v => (
      <span style={{ color: v >= 0 ? '#52c41a' : '#ff4d4f' }}>
        {v >= 0 ? '+' : ''}{v.toLocaleString()}
      </span>
    ),
  },
  {
    title: 'Win Rate', dataIndex: 'win_rate', key: 'win_rate', width: 90,
    sorter: (a, b) => a.win_rate - b.win_rate,
    render: v => `${v.toFixed(1)}%`,
  },
  {
    title: 'Max DD', dataIndex: 'max_drawdown', key: 'max_drawdown', width: 90,
    sorter: (a, b) => a.max_drawdown - b.max_drawdown,
    render: v => <span style={{ color: '#ff4d4f' }}>{v.toFixed(2)}%</span>,
  },
  { title: 'Trades', dataIndex: 'total_trades', key: 'total_trades', width: 70 },
  {
    title: 'Status', dataIndex: 'error', key: 'error', width: 90,
    render: v => v
      ? <Tag color="red" title={v}>Error</Tag>
      : <Tag color="green">OK</Tag>,
  },
]

function summaryStats(results) {
  if (!Array.isArray(results)) return null
  const ok = results.filter(r => !r.error)
  if (!ok.length) return null
  const byStrategy = {}
  for (const r of ok) {
    if (!byStrategy[r.strategy_name]) byStrategy[r.strategy_name] = []
    byStrategy[r.strategy_name].push(r.pnl_pct)
  }
  return Object.entries(byStrategy).map(([k, vals]) => ({
    strategy: strategyMeta[k]?.label ?? k,
    avg: vals.reduce((a, b) => a + b, 0) / vals.length,
    positive: vals.filter(v => v > 0).length,
    total: vals.length,
  }))
}

export default function BatchBacktest() {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)
  const [period, setPeriod] = useState('2024-01-01|2025-12-31')
  const [lastRun, setLastRun] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const pollRef = useRef(null)

  const [start, end] = period.split('|')

  // On mount: check if a job is already running, and load existing results
  useEffect(() => {
    getBatchResults(start, end)
      .then(d => {
        const rows = Array.isArray(d?.results) ? d.results : []
        if (rows.length > 0) { setResults(rows); setLastRun(rows[0]?.run_at) }
      })
      .catch(() => {})
    getBatchStatus()
      .then(s => { if (s.status === 'running') startPolling(start, end) })
      .catch(() => {})
  }, [period])

  // Clean up polling on unmount
  useEffect(() => () => clearInterval(pollRef.current), [])

  const startPolling = (s, e) => {
    clearInterval(pollRef.current)
    pollRef.current = setInterval(() => {
      getBatchStatus().then(status => {
        setJobStatus(status)
        if (status.status === 'done') {
          clearInterval(pollRef.current)
          setLoading(false)
          getBatchResults(s, e).then(d => {
            setResults(Array.isArray(d?.results) ? d.results : [])
            setLastRun(new Date().toISOString())
          }).catch(() => {})
        } else if (status.status === 'error') {
          clearInterval(pollRef.current)
          setLoading(false)
          setError(status.error || 'Batch run failed')
        }
      }).catch(() => {})
    }, 4000)
  }

  const handleRun = () => {
    setLoading(true)
    setError(null)
    setJobStatus({ status: 'running' })
    startBatchBacktest(start, end)
      .then(() => startPolling(start, end))
      .catch(err => {
        setLoading(false)
        setError(err.response?.data?.detail || 'Failed to start batch')
      })
  }

  const stats = summaryStats(results)

  return (
    <div style={{ maxWidth: 1100 }}>
      <h4 className="mb-1">Batch Backtest — 20 VN30 Stocks</h4>
      <p className="text-muted mb-3" style={{ fontSize: 13 }}>
        3 daily strategies × 20 symbols. Uses 100M VND initial capital per run.
      </p>

      <div className="d-flex gap-2 align-items-center mb-4" style={{ flexWrap: 'wrap' }}>
        <Select
          value={period}
          onChange={p => { setPeriod(p); setResults([]) }}
          options={PERIODS}
          style={{ width: 200 }}
          disabled={loading}
        />
        <Button type="primary" onClick={handleRun} loading={loading} disabled={loading}>
          {loading ? 'Running… (~2–3 min)' : results.length ? 'Re-run' : 'Run Batch'}
        </Button>
        {lastRun && !loading && (
          <span className="text-muted" style={{ fontSize: 12 }}>
            Last run: {new Date(lastRun).toLocaleString()}
          </span>
        )}
      </div>

      {error && <Alert type="error" message={error} showIcon className="mb-4" style={{ maxWidth: 500 }} />}

      {loading && (
        <div className="mb-4" style={{ maxWidth: 420 }}>
          <div className="d-flex align-items-center gap-2 mb-2">
            <Spin size="small" />
            <span className="text-muted" style={{ fontSize: 13 }}>
              Running 20 symbols × 3 strategies in parallel…
            </span>
          </div>
          {jobStatus?.total > 0 && (
            <Progress
              percent={Math.round(((jobStatus.ok + jobStatus.failed) / jobStatus.total) * 100)}
              size="small"
              status="active"
              format={p => `${jobStatus.ok + jobStatus.failed}/${jobStatus.total}`}
            />
          )}
        </div>
      )}

      {stats && !loading && (
        <div className="row g-3 mb-4">
          {stats.map(s => (
            <div key={s.strategy} className="col-6 col-md-4">
              <div className="border rounded p-3">
                <div className="fw-semibold mb-1" style={{ fontSize: 13 }}>{s.strategy}</div>
                <div style={{ color: s.avg >= 0 ? '#52c41a' : '#ff4d4f', fontSize: 20, fontWeight: 700 }}>
                  {s.avg >= 0 ? '+' : ''}{s.avg.toFixed(2)}%
                </div>
                <div className="text-muted" style={{ fontSize: 12 }}>
                  avg P&L · {s.positive}/{s.total} stocks profitable
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {Array.isArray(results) && results.length > 0 && !loading && (
        <Table
          dataSource={results.filter(r => !r.error).map((r, i) => ({ ...r, key: i }))}
          columns={COLUMNS}
          size="small"
          pagination={{ pageSize: 30 }}
          scroll={{ x: 800 }}
        />
      )}
    </div>
  )
}
