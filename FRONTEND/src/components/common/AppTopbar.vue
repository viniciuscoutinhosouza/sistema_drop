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
        <a class="nav-link" href="#" data-bs-toggle="dropdown">
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
        <a href="#" class="nav-link dropdown-toggle" data-bs-toggle="dropdown">
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
            <a href="#" class="dropdown-item" @click.prevent="openChangePassword">
              <i class="fas fa-key mr-2"></i> Trocar senha
            </a>
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

  <teleport to="body">
    <div
      v-if="showChangePassword"
      class="modal fade show d-block"
      tabindex="-1"
      role="dialog"
      style="background:rgba(0,0,0,.5)"
      @click.self="closeChangePassword"
    >
      <div class="modal-dialog modal-dialog-centered" role="document">
        <div class="modal-content">
          <form @submit.prevent="submitChangePassword">
            <div class="modal-header">
              <h5 class="modal-title">
                <i class="fas fa-key mr-2"></i> Trocar senha
              </h5>
              <button type="button" class="close" aria-label="Fechar" @click="closeChangePassword">
                <span aria-hidden="true">&times;</span>
              </button>
            </div>
            <div class="modal-body">
              <div class="form-group">
                <label for="cp-current">Senha atual</label>
                <input
                  id="cp-current"
                  v-model="pwForm.current_password"
                  type="password"
                  class="form-control"
                  autocomplete="current-password"
                  required
                  :disabled="pwSubmitting"
                />
              </div>
              <div class="form-group">
                <label for="cp-new">Nova senha</label>
                <input
                  id="cp-new"
                  v-model="pwForm.new_password"
                  type="password"
                  class="form-control"
                  autocomplete="new-password"
                  minlength="6"
                  required
                  :disabled="pwSubmitting"
                />
                <small class="form-text text-muted">Mínimo de 6 caracteres.</small>
              </div>
              <div class="form-group mb-0">
                <label for="cp-confirm">Confirmar nova senha</label>
                <input
                  id="cp-confirm"
                  v-model="pwForm.new_password_confirm"
                  type="password"
                  class="form-control"
                  autocomplete="new-password"
                  minlength="6"
                  required
                  :disabled="pwSubmitting"
                />
              </div>
            </div>
            <div class="modal-footer">
              <button
                type="button"
                class="btn btn-secondary"
                :disabled="pwSubmitting"
                @click="closeChangePassword"
              >
                Cancelar
              </button>
              <button type="submit" class="btn btn-primary" :disabled="pwSubmitting">
                <span v-if="pwSubmitting"><i class="fas fa-spinner fa-spin mr-1"></i> Salvando…</span>
                <span v-else>Salvar</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import { useFinancialStore } from '@/stores/financial'
import { useNotificationsStore } from '@/stores/notifications'
import { formatCurrency, formatDate } from '@/utils/formatters'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const router = useRouter()
const authStore = useAuthStore()
const uiStore = useUiStore()
const financialStore = useFinancialStore()
const notificationsStore = useNotificationsStore()
const toast = useToast()

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

const showChangePassword = ref(false)
const pwSubmitting = ref(false)
const pwForm = reactive({
  current_password: '',
  new_password: '',
  new_password_confirm: '',
})

function resetPwForm() {
  pwForm.current_password = ''
  pwForm.new_password = ''
  pwForm.new_password_confirm = ''
}

function openChangePassword() {
  resetPwForm()
  showChangePassword.value = true
}

function closeChangePassword() {
  if (pwSubmitting.value) return
  showChangePassword.value = false
  resetPwForm()
}

async function submitChangePassword() {
  if (pwForm.new_password !== pwForm.new_password_confirm) {
    toast.error('As senhas não coincidem')
    return
  }
  if (pwForm.new_password.length < 6) {
    toast.error('A nova senha deve ter ao menos 6 caracteres')
    return
  }
  pwSubmitting.value = true
  try {
    await api.post('/auth/change-password', {
      current_password: pwForm.current_password,
      new_password: pwForm.new_password,
      new_password_confirm: pwForm.new_password_confirm,
    })
    toast.success('Senha alterada com sucesso')
    showChangePassword.value = false
    resetPwForm()
  } catch (err) {
    const detail = err?.response?.data?.detail
    toast.error(typeof detail === 'string' ? detail : 'Erro ao trocar senha')
  } finally {
    pwSubmitting.value = false
  }
}
</script>
