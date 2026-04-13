export const backendBase = import.meta.env.DEV ? 'http://localhost:8000' : ''
export const frontendBase = import.meta.env.DEV ? 'http://localhost:5173' : ''

export default {backendBase, frontendBase}