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
          <small class="text-muted">{{ authStore.user?.role }}</small>
        </div>
      </div>

      <!-- Nav Menu -->
      <nav class="mt-2">
        <ul class="nav nav-pills nav-sidebar flex-column" data-widget="treeview" role="menu">

          <li class="nav-item">
            <RouterLink to="/dashboard" class="nav-link" :class="{ active: route.path === '/dashboard' }">
              <i class="nav-icon fas fa-tachometer-alt"></i>
              <p>Dashboard</p>
            </RouterLink>
          </li>

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
              <p>Integrações</p>
            </RouterLink>
          </li>

          <li class="nav-item">
            <RouterLink to="/returns" class="nav-link" :class="{ active: route.path.startsWith('/returns') }">
              <i class="nav-icon fas fa-undo"></i>
              <p>Devoluções</p>
            </RouterLink>
          </li>

          <!-- Supplier only -->
          <template v-if="authStore.user?.role === 'supplier' || authStore.user?.role === 'admin'">
            <li class="nav-header">FORNECEDOR</li>
            <li class="nav-item">
              <RouterLink to="/supplier/products" class="nav-link">
                <i class="nav-icon fas fa-warehouse"></i>
                <p>Gestão do Catálogo</p>
              </RouterLink>
            </li>
          </template>

        </ul>
      </nav>
    </div>
  </aside>
</template>

<script setup>
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const authStore = useAuthStore()
</script>
