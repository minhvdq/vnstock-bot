import api from './api'

export const runBacktest = (symbol, strategy = 'rsi_divergence') =>
  api.get(`/backtest/${encodeURIComponent(symbol)}`, { params: { strategy } }).then(r => r.data)
