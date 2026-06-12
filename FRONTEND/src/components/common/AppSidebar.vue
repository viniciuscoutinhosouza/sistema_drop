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

          <li class="nav-item">
            <RouterLink to="/dashboard/marketplace" class="nav-link" :class="{ active: route.path === '/dashboard/marketplace' }">
              <i class="nav-icon fas fa-store"></i>
              <p>Dashboard Marketplaces</p>
            </RouterLink>
          </li>

          <li class="nav-item">
            <RouterLink to="/simulator" class="nav-link" :class="{ active: route.path === '/simulator' }">
              <i class="nav-icon fas fa-calculator"></i>
              <p>Simulador ML</p>
            </RouterLink>
          </li>

          <!-- ══ MENUS DINÂMICOS (perfil de acesso) ══════════════════════════ -->

          <!-- MINHAS CONTAS (GC / AC) -->
          <template v-if="canSee('cmig') || canSee('integrations') || canSee('cmig_reports') || canSee('full_cnpjs')">
            <li class="nav-header">MINHAS CONTAS</li>
            <li v-if="canSee('cmig')" class="nav-item">
              <RouterLink to="/cmigs" class="nav-link" :class="{ active: route.path.startsWith('/cmigs') || route.path.startsWith('/cmig-products') }">
                <i class="nav-icon fas fa-id-card"></i><p>Contas MIG (CMIG)</p>
              </RouterLink>
            </li>
            <li v-if="canSee('integrations')" class="nav-item">
              <RouterLink to="/integrations" class="nav-link" :class="{ active: route.path.startsWith('/integrations') }">
                <i class="nav-icon fas fa-plug"></i><p>Contas Marketplace (CM)</p>
              </RouterLink>
            </li>
            <li v-if="canSee('cmig_reports')" class="nav-item">
              <RouterLink to="/cmig-reports" class="nav-link" :class="{ active: route.path.startsWith('/cmig-reports') }">
                <i class="nav-icon fas fa-file-pdf"></i><p>Relatórios</p>
              </RouterLink>
            </li>
            <li v-if="canSee('full_cnpjs')" class="nav-item">
              <RouterLink to="/full-cnpjs" class="nav-link" :class="{ active: route.path.startsWith('/full-cnpjs') }">
                <i class="nav-icon fas fa-warehouse"></i><p>CNPJs FULL</p>
              </RouterLink>
            </li>
          </template>

          <!-- OPERAÇÕES (GC / AC) -->
          <template v-if="canSee('anuncios') || canSee('atendimento') || canSee('financeiro') || canSee('pedidos') || canSee('catalog') || canSee('pedido_manual') || canSee('devolucoes') || canSee('estoque')">
            <li class="nav-header">OPERAÇÕES</li>
            <li v-if="canSee('anuncios')" class="nav-item">
              <RouterLink to="/anuncios" class="nav-link" :class="{ active: route.path.startsWith('/anuncios') }">
                <i class="nav-icon fas fa-tag"></i><p>Anúncios</p>
              </RouterLink>
            </li>
            <li v-if="canSee('atendimento')" class="nav-item">
              <RouterLink to="/messages" class="nav-link" :class="{ active: route.path.startsWith('/messages') }">
                <i class="nav-icon fas fa-comments"></i>
                <p>Atendimento <span v-if="unreadMessages > 0" class="badge badge-danger badge-pill right">{{ unreadMessages }}</span></p>
              </RouterLink>
            </li>
            <li v-if="canSee('financeiro')" class="nav-item">
              <RouterLink to="/financial" class="nav-link" :class="{ active: route.path.startsWith('/financial') }">
                <i class="nav-icon fas fa-dollar-sign"></i><p>Financeiro</p>
              </RouterLink>
            </li>
            <li v-if="canSee('pedidos')" class="nav-item">
              <RouterLink to="/orders" class="nav-link" :class="{ active: route.path.startsWith('/orders') }">
                <i class="nav-icon fas fa-shopping-cart"></i><p>Pedidos</p>
              </RouterLink>
            </li>
            <li v-if="canSee('catalog')" class="nav-item">
              <RouterLink to="/catalog" class="nav-link" :class="{ active: route.path.startsWith('/catalog') }">
                <i class="nav-icon fas fa-store"></i><p>Catálogo</p>
              </RouterLink>
            </li>
            <li v-if="canSee('pedido_manual')" class="nav-item">
              <RouterLink to="/manual-orders" class="nav-link" :class="{ active: route.path.startsWith('/manual-orders') }">
                <i class="nav-icon fas fa-hand-paper"></i><p>Pedido Manual</p>
              </RouterLink>
            </li>
            <li v-if="canSee('devolucoes')" class="nav-item">
              <RouterLink to="/returns" class="nav-link" :class="{ active: route.path.startsWith('/returns') && route.path !== '/returns/aguardando-retorno' }">
                <i class="nav-icon fas fa-undo"></i><p>Devoluções</p>
              </RouterLink>
            </li>
            <li v-if="canSee('estoque')" class="nav-item">
              <RouterLink to="/estoque" class="nav-link" :class="{ active: route.path === '/estoque' }">
                <i class="nav-icon fas fa-boxes"></i><p>Controle de Estoque</p>
              </RouterLink>
            </li>
          </template>

          <!-- OPERAÇÃO GL / UGO -->
          <template v-if="canSee('pg')">
            <li class="nav-header">OPERAÇÃO</li>
            <li class="nav-item">
              <RouterLink to="/pg" class="nav-link" :class="{ active: route.path.startsWith('/pg') }">
                <i class="nav-icon fas fa-warehouse"></i><p>Produto Geral (PG)</p>
              </RouterLink>
            </li>
          </template>

          <!-- SEPARAÇÃO GL -->
          <template v-if="canSee('separacao')">
            <li class="nav-header">SEPARAÇÃO</li>
            <li class="nav-item">
              <RouterLink to="/separacao" class="nav-link" :class="{ active: route.path === '/separacao' }">
                <i class="nav-icon fas fa-dolly"></i><p>Separar Pedidos</p>
              </RouterLink>
            </li>
            <li class="nav-item">
              <RouterLink to="/separacao/gaiolas" class="nav-link" :class="{ active: route.path.startsWith('/separacao/gaiolas') }">
                <i class="nav-icon fas fa-shipping-fast"></i><p>Gaiolas / Transportadora</p>
              </RouterLink>
            </li>
          </template>

          <!-- ESTOQUE GL -->
          <template v-if="canSee('ag_retorno') || canSee('inventario')">
            <li class="nav-header">ESTOQUE</li>
            <li v-if="canSee('ag_retorno')" class="nav-item">
              <RouterLink to="/returns/aguardando-retorno" class="nav-link" :class="{ active: route.path === '/returns/aguardando-retorno' }">
                <i class="nav-icon fas fa-undo-alt text-info"></i><p>Ag. Retorno Físico</p>
              </RouterLink>
            </li>
            <li v-if="canSee('inventario')" class="nav-item">
              <RouterLink to="/inventario" class="nav-link" :class="{ active: route.path.startsWith('/inventario') }">
                <i class="nav-icon fas fa-clipboard-list text-success"></i><p>Inventário</p>
              </RouterLink>
            </li>
          </template>

          <!-- FISCAL -->
          <template v-if="canSee('pessoas') || canSee('fiscal_entradas') || canSee('fiscal_saidas') || canSee('fiscal_cfop') || canSee('fiscal_config') || canSee('fiscal_transicao')">
            <li class="nav-header">FISCAL</li>
            <li v-if="canSee('pessoas')" class="nav-item">
              <RouterLink to="/people" class="nav-link" :class="{ active: route.path.startsWith('/people') }">
                <i class="nav-icon fas fa-address-book"></i><p>Pessoas</p>
              </RouterLink>
            </li>
            <li v-if="canSee('fiscal_entradas')" class="nav-item">
              <RouterLink to="/fiscal/entradas" class="nav-link" :class="{ active: route.path.startsWith('/fiscal/entradas') }">
                <i class="nav-icon fas fa-arrow-down"></i><p>Entradas</p>
              </RouterLink>
            </li>
            <li v-if="canSee('fiscal_saidas')" class="nav-item">
              <RouterLink to="/fiscal/saidas" class="nav-link" :class="{ active: route.path.startsWith('/fiscal/saidas') }">
                <i class="nav-icon fas fa-arrow-up"></i><p>Saídas</p>
              </RouterLink>
            </li>
            <li v-if="canSee('fiscal_cfop')" class="nav-item">
              <RouterLink to="/fiscal/cfop" class="nav-link" :class="{ active: route.path === '/fiscal/cfop' }">
                <i class="nav-icon fas fa-list-ol"></i><p>CFOPs</p>
              </RouterLink>
            </li>
            <li v-if="canSee('fiscal_config')" class="nav-item">
              <RouterLink to="/fiscal/config" class="nav-link" :class="{ active: route.path === '/fiscal/config' }">
                <i class="nav-icon fas fa-key"></i><p>Configuração Fiscal</p>
              </RouterLink>
            </li>
            <li v-if="canSee('fiscal_transicao')" class="nav-item">
              <RouterLink to="/fiscal/transicao" class="nav-link" :class="{ active: route.path === '/fiscal/transicao' }">
                <i class="nav-icon fas fa-balance-scale"></i><p>Transição Tributária</p>
              </RouterLink>
            </li>
          </template>

          <!-- MONITORAMENTO -->
          <template v-if="canSee('rotinas')">
            <li class="nav-header">MONITORAMENTO</li>
            <li class="nav-item">
              <RouterLink to="/monitoring/jobs" class="nav-link" :class="{ active: route.path.startsWith('/monitoring') }">
                <i class="nav-icon fas fa-clock"></i><p>Rotinas Automatizadas</p>
              </RouterLink>
            </li>
          </template>

          <!-- GESTÃO GO -->
          <template v-if="canSee('go_empresa') || canSee('go_usuarios')">
            <li class="nav-header">GESTÃO</li>
            <li v-if="canSee('go_empresa')" class="nav-item">
              <RouterLink :to="`/goes/${authStore.user?.go_id}/edit`" class="nav-link" :class="{ active: route.path.includes('/goes/') && route.path.includes('/edit') }">
                <i class="nav-icon fas fa-building"></i><p>Minha Empresa</p>
              </RouterLink>
            </li>
            <li v-if="canSee('go_usuarios')" class="nav-item">
              <RouterLink to="/settings/users" class="nav-link" :class="{ active: route.path === '/settings/users' }">
                <i class="nav-icon fas fa-users"></i><p>Usuários</p>
              </RouterLink>
            </li>
          </template>

          <!-- ADMINISTRAÇÃO -->
          <template v-if="canSee('config_usuarios') || canSee('config_email') || canSee('config_eship') || canSee('config_ncm') || canSee('config_ai') || canSee('config_api_console') || canSee('config_perfis')">
            <li class="nav-header">ADMINISTRAÇÃO</li>
            <li class="nav-item" :class="{ 'menu-open': settingsOpen }">
              <a href="#" class="nav-link" :class="{ active: route.path.startsWith('/settings') || route.path.startsWith('/admin') }" @click.prevent="settingsOpen = !settingsOpen">
                <i class="nav-icon fas fa-cog"></i>
                <p>Configurações <i class="right fas fa-angle-left"></i></p>
              </a>
              <ul class="nav nav-treeview">
                <li v-if="canSee('config_usuarios')" class="nav-item">
                  <RouterLink to="/settings/users" class="nav-link" :class="{ active: route.path === '/settings/users' }">
                    <i class="far fa-circle nav-icon"></i><p>Usuários</p>
                  </RouterLink>
                </li>
                <li v-if="canSee('config_email')" class="nav-item">
                  <RouterLink to="/settings/email" class="nav-link" :class="{ active: route.path === '/settings/email' }">
                    <i class="far fa-circle nav-icon"></i><p>Servidor de E-mail</p>
                  </RouterLink>
                </li>
                <li v-if="canSee('config_eship')" class="nav-item">
                  <RouterLink to="/settings/eship" class="nav-link" :class="{ active: route.path === '/settings/eship' }">
                    <i class="far fa-circle nav-icon"></i><p>Integração eShip</p>
                  </RouterLink>
                </li>
                <li v-if="canSee('config_ncm')" class="nav-item">
                  <RouterLink to="/settings/ncm" class="nav-link" :class="{ active: route.path === '/settings/ncm' }">
                    <i class="far fa-circle nav-icon"></i><p>Tabela NCM</p>
                  </RouterLink>
                </li>
                <li v-if="canSee('config_ai')" class="nav-item">
                  <RouterLink to="/settings/ai-config" class="nav-link" :class="{ active: route.path === '/settings/ai-config' }">
                    <i class="far fa-circle nav-icon"></i><p>Configuração de IA</p>
                  </RouterLink>
                </li>
                <li v-if="canSee('config_api_console')" class="nav-item">
                  <RouterLink to="/admin/api-console" class="nav-link" :class="{ active: route.path === '/admin/api-console' }">
                    <i class="far fa-circle nav-icon"></i>
                    <p>Console de API <span class="badge badge-danger ml-1" style="font-size:9px">Admin</span></p>
                  </RouterLink>
                </li>
                <li v-if="canSee('config_perfis')" class="nav-item">
                  <RouterLink to="/admin/profiles" class="nav-link" :class="{ active: route.path === '/admin/profiles' }">
                    <i class="far fa-circle nav-icon"></i>
                    <p>Gestão de Perfis <span class="badge badge-primary ml-1" style="font-size:9px">Admin</span></p>
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
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMessagesStore } from '@/stores/messages'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const settingsOpen = ref(false)
const messagesStore = useMessagesStore()
const unreadMessages = computed(() => messagesStore.unreadTotal)

onMounted(() => {
  const role = authStore.user?.role
  if (role === 'ac' || role === 'admin') {
    messagesStore.fetchStats()
  }
})

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

const role = computed(() => authStore.user?.role)
const isAdmin   = computed(() => role.value === 'admin')
const isGO      = computed(() => role.value === 'go')
const isUGO     = computed(() => role.value === 'ugo' || role.value === 'admin')
const isOnlyUGO = computed(() => role.value === 'ugo')
const isAC      = computed(() => role.value === 'ac' || role.value === 'admin')

const roleLabel = computed(() => {
  if (authStore.user?.profile_name) return authStore.user.profile_name
  const map = { admin: 'Administrador', go: 'Gestor Operacional', ugo: 'Gestor Logístico', ac: 'Gestor de Conta' }
  return map[role.value] || role.value
})

// Mapa legado: qual menu_key cada role vê por padrão (sem perfil configurado)
const _legacyMenus = {
  admin: new Set([
    'cmig','integrations','cmig_reports','full_cnpjs','anuncios','atendimento','financeiro',
    'pedidos','catalog','pedido_manual','devolucoes','estoque',
    'pessoas','fiscal_entradas','fiscal_saidas','fiscal_cfop','fiscal_config','fiscal_transicao',
    'pg','separacao','ag_retorno','inventario','inventario_criar','rotinas',
    'go_empresa','go_usuarios',
    'config_usuarios','config_email','config_eship','config_ncm','config_ai','config_api_console','config_perfis',
  ]),
  ac: new Set([
    'cmig','integrations','cmig_reports','full_cnpjs','anuncios','atendimento','financeiro',
    'pedidos','catalog','pedido_manual','devolucoes','estoque',
    'pessoas','fiscal_entradas','fiscal_saidas','fiscal_cfop','fiscal_config','fiscal_transicao',
    'inventario',
  ]),
  ugo: new Set([
    'pg','cmig','pedidos','estoque','separacao','ag_retorno','inventario','inventario_criar','devolucoes',
    'pessoas','fiscal_entradas','fiscal_saidas','rotinas','config_usuarios',
  ]),
  go: new Set(['rotinas','go_empresa','go_usuarios','inventario']),
}

function canSee(menuKey) {
  // Super Admin vê tudo — espelha o bypass do backend (require_role/menu_permission).
  if (role.value === 'admin') return true
  const perms = authStore.user?.menu_permissions
  // Se o usuário tem permissões de perfil configuradas, usa elas
  if (perms && perms.length > 0) return perms.includes(menuKey)
  // Fallback para o mapa legado por role
  return _legacyMenus[role.value]?.has(menuKey) ?? false
}
</script>
