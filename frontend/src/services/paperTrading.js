import api from './api'

export const getPortfolio = () => api.get('/paper-trading/portfolio').then(r => r.data)
export const getPositions = () => api.get('/paper-trading/positions').then(r => r.data)
export const getTrades = (page = 1) =>
  api.get(`/paper-trading/trades?page=${page}&limit=20`).then(r => r.data)
export const closePosition = (id) =>
  api.delete(`/paper-trading/positions/${id}`).then(r => r.data)
