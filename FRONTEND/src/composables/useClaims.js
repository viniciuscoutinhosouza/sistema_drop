import api from '@/composables/useApi'

/** Central de Atendimento — Reclamações (claims pós-venda do ML). */
export function useClaims() {
  async function fetchStats() {
    const { data } = await api.get('/claims/stats')
    return data
  }

  async function listClaims(params) {
    const { data } = await api.get('/claims/', { params })
    return data
  }

  async function getClaim(claimId) {
    const { data } = await api.get(`/claims/${claimId}`)
    return data
  }

  async function syncAccount(accountId) {
    const { data } = await api.post(`/claims/sync/${accountId}`)
    return data
  }

  async function sendMessage(claimId, text, aiSuggestion = null) {
    const { data } = await api.post(`/claims/${claimId}/messages`, { text, ai_suggestion: aiSuggestion })
    return data
  }

  async function executeAction(claimId, action, payload = {}) {
    const { data } = await api.post(`/claims/${claimId}/actions/${action}`, payload)
    return data
  }

  async function getReturns(claimId) {
    const { data } = await api.get(`/claims/${claimId}/returns`)
    return data
  }

  return { fetchStats, listClaims, getClaim, syncAccount, sendMessage, executeAction, getReturns }
}
