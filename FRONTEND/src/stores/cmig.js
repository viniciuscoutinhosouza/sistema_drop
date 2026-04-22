import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const useCmigStore = defineStore('cmig', () => {
  const cmigs = ref([])
  const activeCmig = ref(null)
  const loading = ref(false)

  async function fetchCmigs() {
    loading.value = true
    try {
      const { data } = await api.get('/cmigs')
      cmigs.value = data
      if (!activeCmig.value && data.length > 0) {
        activeCmig.value = data[0]
      }
    } finally {
      loading.value = false
    }
  }

  async function createCmig(payload) {
    const { data } = await api.post('/cmigs', payload)
    cmigs.value.unshift(data)
    return data
  }

  async function updateCmig(id, payload) {
    const { data } = await api.put(`/cmigs/${id}`, payload)
    const idx = cmigs.value.findIndex(c => c.id === id)
    if (idx !== -1) cmigs.value[idx] = data
    return data
  }

  function setActiveCmig(cmig) {
    activeCmig.value = cmig
  }

  return { cmigs, activeCmig, loading, fetchCmigs, createCmig, updateCmig, setActiveCmig }
})
