import api from '@/composables/useApi'

/** Mensagens Prontas (templates de resposta). */
export function useMessageTemplates() {
  async function list() {
    const { data } = await api.get('/message-templates/')
    return data.data || []
  }
  async function create(payload) {
    const { data } = await api.post('/message-templates/', payload)
    return data
  }
  async function update(id, payload) {
    const { data } = await api.put(`/message-templates/${id}`, payload)
    return data
  }
  async function remove(id) {
    await api.delete(`/message-templates/${id}`)
  }
  return { list, create, update, remove }
}
