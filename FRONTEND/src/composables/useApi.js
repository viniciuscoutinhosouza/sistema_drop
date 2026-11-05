import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

// Request interceptor: inject JWT access token
api.interceptors.request.use((config) => {
  const stored = localStorage.getItem('auth')
  if (stored) {
    try {
      const { accessToken } = JSON.parse(stored)
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`
      }
    } catch {
      // ignore parse errors
    }
  }
  return config
})

// Track whether a refresh is already in progress to avoid duplicate calls
let refreshing = false
let refreshQueue = []

function processQueue(error, token = null) {
  refreshQueue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  refreshQueue = []
}

// Response interceptor: handle 401 with token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config

    // Um 401 vindo DO PRÓPRIO /auth/refresh significa que o refresh token morreu —
    // nunca tentar "refrescar o refresh". Desloga limpo e para. (Rede de segurança:
    // a chamada de refresh abaixo usa um axios puro que NÃO passa por este interceptor,
    // então normalmente isto nem dispara — mas protege contra qualquer chamador futuro
    // que volte a usar a instância `api` no refresh. Sem isto, o interceptor se
    // reentrava no próprio refresh e travava em deadlock → tela carregando pra sempre.)
    if (error.response?.status === 401 && original?.url?.endsWith('/auth/refresh')) {
      refreshing = false
      processQueue(error)
      localStorage.removeItem('auth')
      window.location.href = '/login'
      return Promise.reject(error)
    }

    // Only handle 401 and only if we haven't already retried
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true

      if (refreshing) {
        // Queue this request until refresh completes
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject })
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      refreshing = true

      try {
        const stored = localStorage.getItem('auth')
        const { refreshToken } = stored ? JSON.parse(stored) : {}

        if (!refreshToken) throw new Error('No refresh token')

        // axios PURO (não a instância `api`) de propósito: o refresh NÃO pode passar
        // pelo interceptor de 401 — se passar e o próprio refresh responder 401, o
        // interceptor se reentra e trava em deadlock. baseURL não se aplica ao axios
        // puro, por isso a URL completa `/api/v1/auth/refresh`.
        const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
        const newAccessToken = data.access_token

        // Update stored auth
        const authData = JSON.parse(localStorage.getItem('auth') || '{}')
        authData.accessToken = newAccessToken
        authData.refreshToken = data.refresh_token
        localStorage.setItem('auth', JSON.stringify(authData))

        processQueue(null, newAccessToken)
        original.headers.Authorization = `Bearer ${newAccessToken}`
        return api(original)
      } catch (refreshError) {
        processQueue(refreshError)
        localStorage.removeItem('auth')
        window.location.href = '/login'
        return Promise.reject(refreshError)
      } finally {
        refreshing = false
      }
    }

    return Promise.reject(error)
  }
)

export default api
