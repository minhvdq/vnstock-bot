import api from './api'

export const runBacktest = (symbol) =>
  api.get(`/backtest/${encodeURIComponent(symbol)}`).then(r => r.data)
