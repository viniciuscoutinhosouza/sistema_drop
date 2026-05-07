import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/composables/useApi'

export const useMessagesStore = defineStore('messages', () => {
  const threads = ref([])
  const activeThread = ref(null)
  const activeMessages = ref([])
  const unreadTotal = ref(0)
  const loading = ref(false)
  const loadingThread = ref(false)
  const sendingReply = ref(false)
  const loadingAI = ref(false)
  const aiSuggestion = ref('')
  const total = ref(0)
  const offset = ref(0)
  const limit = ref(25)

  const hasMore = computed(() => threads.value.length < total.value)

  async function fetchStats() {
    try {
      const { data } = await api.get('/messages/stats')
      unreadTotal.value = data.total_unread
    } catch (_) {
      // silently fail — não bloqueia a UI
    }
  }

  async function fetchThreads(filters = {}, append = false) {
    loading.value = true
    try {
      const params = { offset: append ? offset.value : 0, limit: limit.value, ...filters }
      const { data } = await api.get('/messages/', { params })
      if (append) {
        threads.value.push(...data.items)
      } else {
        threads.value = data.items
        offset.value = 0
      }
      total.value = data.total
      offset.value = (params.offset ?? 0) + data.items.length
    } finally {
      loading.value = false
    }
  }

  async function loadMore(filters = {}) {
    if (!hasMore.value || loading.value) return
    await fetchThreads(filters, true)
  }

  async function fetchThread(threadId) {
    loadingThread.value = true
    aiSuggestion.value = ''
    try {
      const { data } = await api.get(`/messages/${threadId}`)
      activeThread.value = data
      activeMessages.value = data.messages || []

      // Zera unread no store local
      const idx = threads.value.findIndex(t => t.id === threadId)
      if (idx !== -1) {
        threads.value[idx].unread_count = 0
      }
      // Recalcula total global
      await fetchStats()
    } finally {
      loadingThread.value = false
    }
  }

  async function sendReply(threadId, text, aiSuggestionText = null) {
    sendingReply.value = true
    try {
      const { data } = await api.post(`/messages/${threadId}/reply`, {
        text,
        ai_suggestion: aiSuggestionText,
      })
      activeMessages.value.push(data)
      aiSuggestion.value = ''
      // Atualiza preview na lista
      const idx = threads.value.findIndex(t => t.id === threadId)
      if (idx !== -1) {
        threads.value[idx].last_message_preview = text.slice(0, 80)
        threads.value[idx].status = 'open'
      }
      return data
    } finally {
      sendingReply.value = false
    }
  }

  async function suggestAI(threadId) {
    loadingAI.value = true
    aiSuggestion.value = ''
    try {
      const { data } = await api.post(`/messages/${threadId}/ai-suggest`)
      aiSuggestion.value = data.suggestion
    } finally {
      loadingAI.value = false
    }
  }

  async function syncAccount(accountId) {
    await api.post(`/messages/sync/${accountId}`)
  }

  function addIncomingMessage(message) {
    // Chamado pelo Socket.IO ao receber nova mensagem em tempo real
    if (activeThread.value && activeThread.value.id === message.thread_id) {
      activeMessages.value.push(message)
    }
    const idx = threads.value.findIndex(t => t.id === message.thread_id)
    if (idx !== -1) {
      threads.value[idx].unread_count = (threads.value[idx].unread_count || 0) + 1
      threads.value[idx].last_message_preview = (message.text || '').slice(0, 80)
    }
    unreadTotal.value = (unreadTotal.value || 0) + 1
  }

  return {
    threads, activeThread, activeMessages, unreadTotal,
    loading, loadingThread, sendingReply, loadingAI,
    aiSuggestion, total, hasMore,
    fetchStats, fetchThreads, loadMore, fetchThread,
    sendReply, suggestAI, syncAccount, addIncomingMessage,
  }
})
