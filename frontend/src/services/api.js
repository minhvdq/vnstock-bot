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
