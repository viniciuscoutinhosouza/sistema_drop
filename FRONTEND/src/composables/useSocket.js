import { ref, onUnmounted } from 'vue'
import { io } from 'socket.io-client'
import { useNotificationsStore } from '@/stores/notifications'
import { useFinancialStore } from '@/stores/financial'

let socket = null

export function useSocket() {
  const connected = ref(false)

  function connect() {
    if (socket?.connected) return

    const stored = localStorage.getItem('auth')
    const { accessToken } = stored ? JSON.parse(stored) : {}
    if (!accessToken) return

    socket = io('/', {
      path: '/ws/socket.io',
      auth: { token: accessToken },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: 3000,
    })

    socket.on('connect', () => {
      connected.value = true
    })

    socket.on('disconnect', () => {
      connected.value = false
    })

    socket.on('notification', (data) => {
      useNotificationsStore().addNotification(data)
    })

    socket.on('balance_update', (data) => {
      const store = useFinancialStore()
      store.balance = data.balance
      store.balanceReserved = data.balance_reserved
    })
  }

  function disconnect() {
    socket?.disconnect()
    socket = null
    connected.value = false
  }

  onUnmounted(() => {
    // Don't disconnect on unmount – keep persistent connection
  })

  return { connect, disconnect, connected }
}
