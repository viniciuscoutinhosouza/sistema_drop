import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const useCfopStore = defineStore('cfop', () => {
  const cfops = ref([])
  const loaded = ref(false)

  async function fetchAll({ direction = null, activeOnly = true } = {}) {
    const params = { active_only: activeOnly }
    if (direction) params.direction = direction
    const { data } = await api.get('/cfop', { params })
    cfops.value = data
    loaded.value = true
    return data
  }

  function forDirection(direction) {
    return cfops.value.filter(c => c.direction === direction)
  }

  function findByCode(code) {
    return cfops.value.find(c => c.code === code) || null
  }

  async function create(payload) {
    const { data } = await api.post('/cfop', payload)
    cfops.value.push(data)
    return data
  }

  async function update(id, payload) {
    const { data } = await api.patch(`/cfop/${id}`, payload)
    const idx = cfops.value.findIndex(c => c.id === id)
    if (idx !== -1) cfops.value[idx] = data
    return data
  }

  async function remove(id) {
    await api.delete(`/cfop/${id}`)
    cfops.value = cfops.value.filter(c => c.id !== id)
  }

  return { cfops, loaded, fetchAll, forDirection, findByCode, create, update, remove }
})
