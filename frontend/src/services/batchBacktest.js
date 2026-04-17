import api from './api'

export const runBatchBacktest = (start = '2024-01-01', end = '2025-12-31') =>
  api.post(`/batch-backtest/run?start=${start}&end=${end}`).then(r => r.data)

export const getBatchResults = (start = '2024-01-01', end = '2025-12-31') =>
  api.get(`/batch-backtest/results?start=${start}&end=${end}`).then(r => r.data)
