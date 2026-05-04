import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const usePeopleStore = defineStore('people', () => {
  const people = ref([])
  const total = ref(0)
  const loading = ref(false)
  const currentPerson = ref(null)

  async function fetchPeople(filters = {}) {
    loading.value = true
    try {
      const { data } = await api.get('/people', { params: filters })
      people.value = data.items || []
      total.value = data.total || 0
      return data
    } finally {
      loading.value = false
    }
  }

  async function fetchPerson(id) {
    const { data } = await api.get(`/people/${id}`)
    currentPerson.value = data
    return data
  }

  async function createPerson(payload) {
    const { data } = await api.post('/people', payload)
    return data
  }

  async function updatePerson(id, payload) {
    const { data } = await api.patch(`/people/${id}`, payload)
    return data
  }

  async function deletePerson(id) {
    await api.delete(`/people/${id}`)
    people.value = people.value.filter(p => p.id !== id)
  }

  async function lookupCnpj(cnpj) {
    const { data } = await api.post('/people/lookup-cnpj', { cnpj })
    return data
  }

  return {
    people, total, loading, currentPerson,
    fetchPeople, fetchPerson, createPerson, updatePerson, deletePerson, lookupCnpj,
  }
})
