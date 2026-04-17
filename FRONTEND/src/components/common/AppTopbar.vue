<template>
  <nav class="main-header navbar navbar-expand navbar-white navbar-light">
    <!-- Left: sidebar toggle -->
    <ul class="navbar-nav">
      <li class="nav-item">
        <a class="nav-link" data-widget="pushmenu" href="#" role="button">
          <i class="fas fa-bars"></i>
        </a>
      </li>
    </ul>

    <!-- Right navbar links -->
    <ul class="navbar-nav ml-auto">

      <!-- Balance -->
      <li class="nav-item">
        <RouterLink to="/financial" class="nav-link">
          <i class="fas fa-dollar-sign text-success"></i>
          <strong class="ml-1">{{ formatCurrency(financialStore.balance) }}</strong>
        </RouterLink>
      </li>

      <!-- Dark mode toggle -->
      <li class="nav-item">
        <a class="nav-link" href="#" @click.prevent="toggleDarkMode">
          <i :class="uiStore.darkMode ? 'fas fa-sun' : 'fas fa-moon'"></i>
        </a>
      </li>

      <!-- Notifications bell -->
      <li class="nav-item dropdown">
        <a class="nav-link" href="#" data-toggle="dropdown">
          <i class="far fa-bell"></i>
          <span
            v-if="notificationsStore.unreadCount > 0"
            class="badge badge-warning navbar-badge"
          >{{ notificationsStore.unreadCount }}</span>
        </a>
        <div class="dropdown-menu dropdown-menu-lg dropdown-menu-right">
          <span class="dropdown-header">
            {{ notificationsStore.unreadCount }} notificações
          </span>
          <div class="dropdown-divider"></div>
          <template v-if="notificationsStore.notifications.length">
            <a
              v-for="n in notificationsStore.notifications.slice(0, 10)"
              :key="n.id"
              href="#"
              class="dropdown-item"
              :class="{ 'font-weight-bold': !n.is_read }"
              @click.prevent="readAndClose(n)"
            >
              <i class="fas fa-bell mr-2 text-warning"></i>
              {{ n.title }}
              <span class="float-right text-muted text-sm">{{ formatDate(n.created_at) }}</span>
            </a>
          </template>
          <span v-else class="dropdown-item text-muted">Sem notificações</span>
          <div class="dropdown-divider"></div>
          <RouterLink to="/notifications" class="dropdown-item dropdown-footer">Ver todas</RouterLink>
        </div>
      </li>

      <!-- User dropdown -->
      <li class="nav-item dropdown user-menu">
        <a href="#" class="nav-link dropdown-toggle" data-toggle="dropdown">
          <span class="d-none d-md-inline">{{ authStore.user?.full_name }}</span>
        </a>
        <ul class="dropdown-menu dropdown-menu-right">
          <li class="dropdown-divider"></li>
          <li>
            <RouterLink to="/profile" class="dropdown-item">
              <i class="fas fa-user mr-2"></i> Perfil
            </RouterLink>
          </li>
          <li>
            <a href="#" class="dropdown-item" @click.prevent="handleLogout">
              <i class="fas fa-sign-out-alt mr-2"></i> Sair
            </a>
          </li>
        </ul>
      </li>

    </ul>
  </nav>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { useFinancialStore } from '@/stores/financial'
import { useNotificationsStore } from '@/stores/notifications'
import { formatCurrency, formatDate } from '@/utils/formatters'
import api from '@/composables/useApi'

const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const financialStore = useFinancialStore()
const notificationsStore = useNotificationsStore()

async function toggleDarkMode() {
  uiStore.toggleDarkMode()
  try {
    await api.put('/users/me/preferences', { dark_mode: uiStore.darkMode })
  } catch {
    // not critical
  }
}

async function readAndClose(notification) {
  await notificationsStore.markAsRead(notification.id)
}

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>
