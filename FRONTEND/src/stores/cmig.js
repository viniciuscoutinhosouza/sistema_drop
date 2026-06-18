import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const useCmigStore = defineStore('cmig', () => {
  const cmigs = ref([])       // SOMENTE ativas — usado por todos os dropdowns seletores
  const allCmigs = ref([])    // inclui inativas — usado só pela tela de gestão de CMIGs
  const activeCmig = ref(null)
  const loading = ref(false)

  async function fetchCmigs() {
    loading.value = true
    try {
      const { data } = await api.get('/cmigs')  // backend já devolve só ativas por padrão
      cmigs.value = data
      if (!activeCmig.value && data.length > 0) {
        activeCmig.value = data[0]
      }
    } finally {
      loading.value = false
    }
  }

  async function fetchAllCmigs() {
    loading.value = true
    try {
      const { data } = await api.get('/cmigs', { params: { include_inactive: true } })
      allCmigs.value = data
    } finally {
      loading.value = false
    }
  }

  async function createCmig(payload) {
    const { data } = await api.post('/cmigs', payload)
    cmigs.value.unshift(data)
    allCmigs.value.unshift(data)
    return data
  }

  async function updateCmig(id, payload) {
    const { data } = await api.put(`/cmigs/${id}`, payload)
    // Atualiza a gestão (allCmigs)
    const ai = allCmigs.value.findIndex(c => c.id === id)
    if (ai !== -1) allCmigs.value[ai] = data
    // Lista de dropdowns (só ativas): atualiza se ativa, remove se foi desativada
    const idx = cmigs.value.findIndex(c => c.id === id)
    if (data.is_active) {
      if (idx !== -1) cmigs.value[idx] = data
      else cmigs.value.push(data)
    } else if (idx !== -1) {
      cmigs.value.splice(idx, 1)
    }
    return data
  }

  function setActiveCmig(cmig) {
    activeCmig.value = cmig
  }

  return { cmigs, allCmigs, activeCmig, loading, fetchCmigs, fetchAllCmigs, createCmig, updateCmig, setActiveCmig }
})
