import api from './api'

export const getMe = () => api.get('/user/me').then(r => r.data)

export const addStock = (symbol) =>
  api.put('/user/add_stock', { symbol }).then(r => r.data)

export const removeStock = (symbol) =>
  api.delete('/user/remove_stock', { data: { symbol } }).then(r => r.data)

export const getTelegramLink = () =>
  api.get('/user/telegram_connect').then(r => r.data)

export const getCompanies = () =>
  api.get('/company/all-companies').then(r => r.data)
