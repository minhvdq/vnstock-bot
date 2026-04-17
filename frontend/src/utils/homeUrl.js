export const backendBase = import.meta.env.DEV
  ? 'http://localhost:8000'
  : (import.meta.env.VITE_API_URL || 'https://vnstock-backend-aged-sunset-8999.fly.dev')

export const frontendBase = import.meta.env.DEV ? 'http://localhost:5173' : ''

export default {backendBase, frontendBase}