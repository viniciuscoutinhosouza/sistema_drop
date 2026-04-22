import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const useGoStore = defineStore('go', () => {
  const goes = ref([])
  const loading = ref(false)

  async function fetchGoes() {
    loading.value = true
    try {
      const { data } = await api.get('/goes')
      goes.value = data
    } finally {
      loading.value = false
    }
  }

  async function createGo(payload) {
    const { data } = await api.post('/goes', payload)
    goes.value.unshift(data)
    return data
  }

  async function updateGo(id, payload) {
    const { data } = await api.put(`/goes/${id}`, payload)
    const idx = goes.value.findIndex(g => g.id === id)
    if (idx !== -1) goes.value[idx] = data
    return data
  }

  return { goes, loading, fetchGoes, createGo, updateGo }
})
