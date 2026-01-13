export const backendBase = process.env.NODE_ENV === 'development' ? 'http://localhost:8000' : ''
export const frontendBase = process.env.NODE_ENV === 'development' ? 'http://localhost:5173' : ''

export default {backendBase, frontendBase}