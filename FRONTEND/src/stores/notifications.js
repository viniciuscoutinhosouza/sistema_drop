import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/composables/useApi'

export const useNotificationsStore = defineStore('notifications', () => {
  const notifications = ref([])
  const total = ref(0)

  const unreadCount = computed(() =>
    notifications.value.filter(n => !n.is_read).length
  )

  async function fetchNotifications(page = 1) {
    const { data } = await api.get('/notifications', { params: { page, page_size: 10 } })
    notifications.value = data.items
    total.value = data.total
  }

  function addNotification(notification) {
    notifications.value.unshift(notification)
    total.value++
  }

  async function markAsRead(id) {
    await api.put(`/notifications/${id}/read`)
    const n = notifications.value.find(n => n.id === id)
    if (n) n.is_read = true
  }

  async function markAllAsRead() {
    await api.put('/notifications/read-all')
    notifications.value.forEach(n => (n.is_read = true))
  }

  return { notifications, total, unreadCount, fetchNotifications, addNotification, markAsRead, markAllAsRead }
})
