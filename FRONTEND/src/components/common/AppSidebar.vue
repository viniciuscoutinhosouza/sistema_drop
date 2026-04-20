<template>
  <aside class="main-sidebar sidebar-dark-primary elevation-4">
    <!-- Brand Logo -->
    <RouterLink to="/dashboard" class="brand-link">
      <span class="brand-text font-weight-light"><strong>MIG</strong> ECOMMERCE</span>
    </RouterLink>

    <div class="sidebar">
      <!-- User Panel -->
      <div class="user-panel mt-3 pb-3 mb-3 d-flex">
        <div class="image">
          <img src="https://via.placeholder.com/32" class="img-circle elevation-2" alt="User" />
        </div>
        <div class="info">
          <span class="d-block text-white text-truncate" style="max-width:150px">
            {{ authStore.user?.full_name }}
          </span>
          <small class="text-muted">{{ roleLabel }}</small>
        </div>
      </div>

      <!-- Nav Menu -->
      <nav class="mt-2">
        <ul class="nav nav-pills nav-sidebar flex-column" data-widget="treeview" role="menu" data-accordion="false">

          <li class="nav-item">
            <RouterLink to="/dashboard" class="nav-link" :class="{ active: route.path === '/dashboard' }">
              <i class="nav-icon fas fa-tachometer-alt"></i>
              <p>Dashboard</p>
            </RouterLink>
          </li>

          <!-- Menus visíveis apenas para AC -->
          <template v-if="isAC">
            <li class="nav-item">
              <RouterLink to="/financial" class="nav-link" :class="{ active: route.path.startsWith('/financial') }">
                <i class="nav-icon fas fa-dollar-sign"></i>
                <p>Financeiro</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/orders" class="nav-link" :class="{ active: route.path.startsWith('/orders') }">
                <i class="nav-icon fas fa-shopping-cart"></i>
                <p>Pedidos</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/products" class="nav-link" :class="{ active: route.path.startsWith('/products') }">
                <i class="nav-icon fas fa-box"></i>
                <p>Meus Produtos</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/kits" class="nav-link" :class="{ active: route.path.startsWith('/kits') }">
                <i class="nav-icon fas fa-boxes"></i>
                <p>Kits</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/catalog" class="nav-link" :class="{ active: route.path.startsWith('/catalog') }">
                <i class="nav-icon fas fa-store"></i>
                <p>Catálogo</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/manual-orders" class="nav-link" :class="{ active: route.path.startsWith('/manual-orders') }">
                <i class="nav-icon fas fa-hand-paper"></i>
                <p>Drop Manual</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/integrations" class="nav-link" :class="{ active: route.path.startsWith('/integrations') }">
                <i class="nav-icon fas fa-plug"></i>
                <p>Minhas Contas</p>
              </RouterLink>
            </li>

            <li class="nav-item">
              <RouterLink to="/returns" class="nav-link" :class="{ active: route.path.startsWith('/returns') }">
                <i class="nav-icon fas fa-undo"></i>
                <p>Devoluções</p>
              </RouterLink>
            </li>
          </template>

          <!-- Menus exclusivos para UGO (Operador Logístico) -->
          <template v-if="isUGO">
            <li class="nav-header">OPERAÇÃO</li>

            <li class="nav-item">
              <RouterLink to="/pg" class="nav-link" :class="{ active: route.path.startsWith('/pg') }">
                <i class="nav-icon fas fa-warehouse"></i>
                <p>Produto Geral (PG)</p>
              </RouterLink>
            </li>

            <!-- Pedidos só aparece para UGO puro; admin já vê via bloco AC -->
            <li class="nav-item" v-if="isOnlyUGO">
              <RouterLink to="/orders" class="nav-link" :class="{ active: route.path.startsWith('/orders') }">
                <i class="nav-icon fas fa-shopping-cart"></i>
                <p>Pedidos</p>
              </RouterLink>
            </li>
          </template>

          <!-- Configurações — visível para Admin e UGO -->
          <template v-if="isAdmin || isUGO">
            <li class="nav-header">ADMINISTRAÇÃO</li>

            <li class="nav-item" :class="{ 'menu-open': settingsOpen }">
              <a href="#" class="nav-link" :class="{ active: route.path.startsWith('/settings') }" @click.prevent="settingsOpen = !settingsOpen">
                <i class="nav-icon fas fa-cog"></i>
                <p>
                  Configurações
                  <i class="right fas fa-angle-left"></i>
                </p>
              </a>
              <ul class="nav nav-treeview">
                <li class="nav-item">
                  <RouterLink to="/settings/users" class="nav-link" :class="{ active: route.path === '/settings/users' }">
                    <i class="far fa-circle nav-icon"></i>
                    <p>Usuários</p>
                  </RouterLink>
                </li>
                <li class="nav-item" v-if="isAdmin">
                  <RouterLink to="/settings/warehouse" class="nav-link" :class="{ active: route.path === '/settings/warehouse' }">
                    <i class="far fa-circle nav-icon"></i>
                    <p>Galpão</p>
                  </RouterLink>
                </li>
              </ul>
            </li>
          </template>

          <!-- Sair -->
          <li class="nav-item" style="margin-top: auto">
            <a href="#" class="nav-link text-danger" @click.prevent="handleLogout">
              <i class="nav-icon fas fa-sign-out-alt"></i>
              <p>Sair</p>
            </a>
          </li>

        </ul>
      </nav>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const settingsOpen = ref(false)

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

const role = computed(() => authStore.user?.role)
const isAdmin   = computed(() => role.value === 'admin')
const isUGO     = computed(() => role.value === 'ugo' || role.value === 'admin')
const isOnlyUGO = computed(() => role.value === 'ugo')
const isAC      = computed(() => role.value === 'ac' || role.value === 'admin')

const roleLabel = computed(() => {
  const map = { admin: 'Administrador', ugo: 'Operador Logístico', ac: 'Gestor de Conta' }
  return map[role.value] || role.value
})
</script>
