import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/composables/useApi'

export const useFiscalStore = defineStore('fiscal', () => {
  const invoices = ref([])
  const total = ref(0)
  const loading = ref(false)
  const currentInvoice = ref(null)

  async function fetchInvoices(filters = {}) {
    loading.value = true
    try {
      const { data } = await api.get('/invoices', { params: filters })
      invoices.value = data.items || []
      total.value = data.total || 0
      return data
    } finally {
      loading.value = false
    }
  }

  async function fetchInvoice(id) {
    const { data } = await api.get(`/invoices/${id}`)
    currentInvoice.value = data
    return data
  }

  async function createInvoice(payload) {
    const { data } = await api.post('/invoices', payload)
    return data
  }

  async function updateInvoice(id, payload) {
    const { data } = await api.patch(`/invoices/${id}`, payload)
    return data
  }

  async function deleteInvoice(id) {
    await api.delete(`/invoices/${id}`)
    invoices.value = invoices.value.filter(i => i.id !== id)
  }

  async function addItem(invoiceId, payload) {
    const { data } = await api.post(`/invoices/${invoiceId}/items`, payload)
    return data
  }

  async function updateItem(invoiceId, itemId, payload) {
    const { data } = await api.patch(`/invoices/${invoiceId}/items/${itemId}`, payload)
    return data
  }

  async function deleteItem(invoiceId, itemId) {
    await api.delete(`/invoices/${invoiceId}/items/${itemId}`)
  }

  async function calculateTaxes(invoiceId) {
    const { data } = await api.post(`/invoices/${invoiceId}/calculate-taxes`)
    return data
  }

  async function transmit(invoiceId) {
    const { data } = await api.post(`/invoices/${invoiceId}/transmit`)
    return data
  }

  async function cancel(invoiceId, reason) {
    const { data } = await api.post(`/invoices/${invoiceId}/cancel`, { reason })
    return data
  }

  async function correctionLetter(invoiceId, text) {
    const { data } = await api.post(`/invoices/${invoiceId}/correction-letter`, { text })
    return data
  }

  async function sendEmail(invoiceId, emails) {
    const { data } = await api.post(`/invoices/${invoiceId}/email`, { emails })
    return data
  }

  async function refreshStatus(invoiceId) {
    const { data } = await api.post(`/invoices/${invoiceId}/refresh-status`)
    return data
  }

  async function syncReceived(cmigId) {
    const { data } = await api.post(`/invoices/sync-received/${cmigId}`)
    return data
  }

  async function manifest(invoiceId, payload) {
    const { data } = await api.post(`/invoices/${invoiceId}/manifest`, payload)
    return data
  }

  async function updateStock(invoiceId) {
    const { data } = await api.post(`/invoices/${invoiceId}/update-stock`)
    return data
  }

  return {
    invoices, total, loading, currentInvoice,
    fetchInvoices, fetchInvoice, createInvoice, updateInvoice, deleteInvoice,
    addItem, updateItem, deleteItem,
    calculateTaxes, transmit, cancel, correctionLetter, sendEmail, refreshStatus,
    syncReceived, manifest, updateStock,
  }
})
