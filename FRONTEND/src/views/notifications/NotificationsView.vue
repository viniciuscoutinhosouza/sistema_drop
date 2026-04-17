<template>
  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      <h3 class="card-title">Notificações</h3>
      <button class="btn btn-sm btn-outline-secondary" @click="markAll">
        <i class="fas fa-check-double mr-1"></i> Marcar todas como lidas
      </button>
    </div>
    <div class="card-body p-0">
      <div v-if="loading" class="text-center py-4">
        <i class="fas fa-spinner fa-spin"></i>
      </div>
      <div v-else>
        <div
          v-for="n in store.notifications"
          :key="n.id"
          :class="['d-flex align-items-start p-3 border-bottom', !n.is_read && 'bg-light']"
          @click="store.markAsRead(n.id)"
          style="cursor: pointer"
        >
          <i :class="typeIcon(n.type)" class="mr-3 mt-1 fa-lg"></i>
          <div>
            <p :class="['mb-0', !n.is_read && 'font-weight-bold']">{{ n.title }}</p>
            <p class="text-muted small mb-0">{{ n.body }}</p>
            <small class="text-muted">{{ formatDateTime(n.created_at) }}</small>
          </div>
          <span v-if="!n.is_read" class="badge badge-primary ml-auto">Nova</span>
        </div>
        <div v-if="!store.notifications.length" class="text-center py-5 text-muted">
          <i class="fas fa-bell-slash fa-3x mb-3"></i>
          <p>Sem notificações</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useNotificationsStore } from '@/stores/notifications'
import { formatDateTime } from '@/utils/formatters'

const store = useNotificationsStore()
const loading = ref(true)

const TYPE_ICONS = {
  new_order: 'fas fa-shopping-cart text-success',
  stock_alert: 'fas fa-exclamation-triangle text-warning',
  price_change: 'fas fa-tag text-info',
  order_cancelled: 'fas fa-times-circle text-danger',
  return_registered: 'fas fa-undo text-warning',
  subscription_overdue: 'fas fa-credit-card text-danger',
}

function typeIcon(type) {
  return TYPE_ICONS[type] || 'fas fa-bell text-secondary'
}

async function markAll() {
  await store.markAllAsRead()
}

onMounted(async () => {
  await store.fetchNotifications()
  loading.value = false
})
</script>
