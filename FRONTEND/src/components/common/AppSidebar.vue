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

          <li class="nav-item">
            <RouterLink to="/analysis/competitor" class="nav-link" :class="{ active: route.path === '/analysis/competitor' }">
              <i class="nav-icon fas fa-search-dollar"></i>
              <p>Análise de Concorrência</p>
            </RouterLink>
          </li>

          <!-- ══ MENUS DINÂMICOS (perfil de acesso) — recolhíveis ════════════ -->

          <!-- MINHAS CONTAS (GC / AC) -->
          <li v-if="canSee('cmig') || canSee('integrations') || canSee('full_cnpjs')"
              class="nav-item" :class="{ 'menu-open': sections.contas }">
            <a href="#" class="nav-link" @click.prevent="toggle('contas')">
              <i class="nav-icon fas fa-briefcase"></i>
              <p>Minhas Contas <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
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
              <li v-if="canSee('full_cnpjs')" class="nav-item">
                <RouterLink to="/full-cnpjs" class="nav-link" :class="{ active: route.path.startsWith('/full-cnpjs') }">
                  <i class="nav-icon fas fa-warehouse"></i><p>CNPJs FULL</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- RELATÓRIOS -->
          <li v-if="canSee('cmig_reports') || canSee('relatorio_vendas')"
              class="nav-item" :class="{ 'menu-open': sections.relatorios }">
            <a href="#" class="nav-link" @click.prevent="toggle('relatorios')">
              <i class="nav-icon fas fa-chart-line"></i>
              <p>Relatórios <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
              <li v-if="canSee('cmig_reports')" class="nav-item">
                <RouterLink to="/cmig-reports" class="nav-link" :class="{ active: route.path.startsWith('/cmig-reports') }">
                  <i class="nav-icon fas fa-file-pdf"></i><p>Relatórios em PDF</p>
                </RouterLink>
              </li>
              <li v-if="canSee('relatorio_vendas')" class="nav-item">
                <RouterLink to="/relatorios/vendas-mes" class="nav-link" :class="{ active: route.path.startsWith('/relatorios/vendas-mes') }">
                  <i class="nav-icon fas fa-coins"></i><p>Vendas do Mês</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- OPERAÇÕES (GC / AC) -->
          <li v-if="canSee('anuncios') || canSee('campanha_ads') || canSee('atendimento') || canSee('financeiro') || canSee('pedidos') || canSee('catalog') || canSee('pedido_manual') || canSee('devolucoes') || canSee('estoque')"
              class="nav-item" :class="{ 'menu-open': sections.operacoes }">
            <a href="#" class="nav-link" @click.prevent="toggle('operacoes')">
              <i class="nav-icon fas fa-tasks"></i>
              <p>Operações
                <span v-if="unreadMessages > 0 && !sections.operacoes" class="badge badge-danger badge-pill right mr-3">{{ unreadMessages }}</span>
                <i class="right fas fa-angle-left"></i>
              </p>
            </a>
            <ul class="nav nav-treeview">
              <li v-if="canSee('anuncios')" class="nav-item">
                <RouterLink to="/anuncios" class="nav-link" :class="{ active: route.path.startsWith('/anuncios') }">
                  <i class="nav-icon fas fa-tag"></i><p>Anúncios</p>
                </RouterLink>
              </li>
              <li v-if="canSee('campanha_ads')" class="nav-item">
                <RouterLink to="/campanha-ads" class="nav-link" :class="{ active: route.path.startsWith('/campanha-ads') }">
                  <i class="nav-icon fas fa-bullhorn"></i><p>Campanha ADS</p>
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
            </ul>
          </li>

          <!-- OPERAÇÃO GL / UGO -->
          <li v-if="canSee('pg')" class="nav-item" :class="{ 'menu-open': sections.operacao }">
            <a href="#" class="nav-link" @click.prevent="toggle('operacao')">
              <i class="nav-icon fas fa-warehouse"></i>
              <p>Operação <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
              <li class="nav-item">
                <RouterLink to="/pg" class="nav-link" :class="{ active: route.path.startsWith('/pg') }">
                  <i class="nav-icon fas fa-warehouse"></i><p>Produto Geral (PG)</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- SEPARAÇÃO GL -->
          <li v-if="canSee('separacao')" class="nav-item" :class="{ 'menu-open': sections.separacao }">
            <a href="#" class="nav-link" @click.prevent="toggle('separacao')">
              <i class="nav-icon fas fa-dolly"></i>
              <p>Separação <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
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
              <li class="nav-item">
                <RouterLink to="/separacao/armazenaki" class="nav-link" :class="{ active: route.path.startsWith('/separacao/armazenaki') }">
                  <i class="nav-icon fas fa-warehouse"></i><p>Armazenaki</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- ESTOQUE GL -->
          <li v-if="canSee('ag_retorno') || canSee('inventario')" class="nav-item" :class="{ 'menu-open': sections.estoque }">
            <a href="#" class="nav-link" @click.prevent="toggle('estoque')">
              <i class="nav-icon fas fa-boxes"></i>
              <p>Estoque <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
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
            </ul>
          </li>

          <!-- FISCAL -->
          <li v-if="canSee('pessoas') || canSee('fiscal_entradas') || canSee('fiscal_saidas') || canSee('fiscal_cfop') || canSee('fiscal_config') || canSee('fiscal_transicao')"
              class="nav-item" :class="{ 'menu-open': sections.fiscal }">
            <a href="#" class="nav-link" @click.prevent="toggle('fiscal')">
              <i class="nav-icon fas fa-file-invoice-dollar"></i>
              <p>Fiscal <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
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
            </ul>
          </li>

          <!-- INTEGRAÇÃO -->
          <li v-if="canSee('integracao_envio')" class="nav-item" :class="{ 'menu-open': sections.integracao }">
            <a href="#" class="nav-link" @click.prevent="toggle('integracao')">
              <i class="nav-icon fas fa-truck-loading"></i>
              <p>Integração <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
              <li class="nav-item">
                <RouterLink to="/integracao/envio-produtos" class="nav-link" :class="{ active: route.path.startsWith('/integracao/envio-produtos') }">
                  <i class="nav-icon fas fa-box"></i><p>Produtos</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- MONITORAMENTO -->
          <li v-if="canSee('rotinas')" class="nav-item" :class="{ 'menu-open': sections.monitoramento }">
            <a href="#" class="nav-link" @click.prevent="toggle('monitoramento')">
              <i class="nav-icon fas fa-clock"></i>
              <p>Monitoramento <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
              <li class="nav-item">
                <RouterLink to="/monitoring/jobs" class="nav-link" :class="{ active: route.path.startsWith('/monitoring') }">
                  <i class="nav-icon fas fa-clock"></i><p>Rotinas Automatizadas</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- GESTÃO GO -->
          <li v-if="(canSee('go_empresa') && authStore.user?.go_id) || canSee('go_usuarios')" class="nav-item" :class="{ 'menu-open': sections.gestao }">
            <a href="#" class="nav-link" @click.prevent="toggle('gestao')">
              <i class="nav-icon fas fa-sitemap"></i>
              <p>Gestão <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
              <li v-if="canSee('go_empresa') && authStore.user?.go_id" class="nav-item">
                <RouterLink :to="`/goes/${authStore.user?.go_id}/edit`" class="nav-link" :class="{ active: route.path.includes('/goes/') && route.path.includes('/edit') }">
                  <i class="nav-icon fas fa-building"></i><p>Minha Empresa</p>
                </RouterLink>
              </li>
              <li v-if="canSee('go_usuarios')" class="nav-item">
                <RouterLink to="/settings/users" class="nav-link" :class="{ active: route.path === '/settings/users' }">
                  <i class="nav-icon fas fa-users"></i><p>Usuários</p>
                </RouterLink>
              </li>
            </ul>
          </li>

          <!-- ADMINISTRAÇÃO -->
          <li v-if="canSee('config_usuarios') || canSee('config_aprovacoes') || canSee('config_email') || canSee('config_eship') || canSee('config_ncm') || canSee('config_ai') || canSee('config_marketplaces') || canSee('config_galpoes') || canSee('config_api_console') || canSee('config_perfis')"
              class="nav-item" :class="{ 'menu-open': sections.admin }">
            <a href="#" class="nav-link" :class="{ active: route.path.startsWith('/settings') || route.path.startsWith('/admin') }" @click.prevent="toggle('admin')">
              <i class="nav-icon fas fa-cog"></i>
              <p>Administração <i class="right fas fa-angle-left"></i></p>
            </a>
            <ul class="nav nav-treeview">
              <li v-if="canSee('config_aprovacoes')" class="nav-item">
                <RouterLink to="/admin/user-approvals" class="nav-link" :class="{ active: route.path === '/admin/user-approvals' }">
                  <i class="far fa-circle nav-icon"></i><p>Aprovações de Cadastro <span class="badge badge-primary ml-1" style="font-size:9px">Admin</span></p>
                </RouterLink>
              </li>
              <li v-if="canSee('config_usuarios')" class="nav-item">
                <RouterLink to="/settings/users" class="nav-link" :class="{ active: route.path === '/settings/users' }">
                  <i class="far fa-circle nav-icon"></i><p>Usuários</p>
                </RouterLink>
              </li>
              <li v-if="canSee('config_galpoes')" class="nav-item">
                <RouterLink to="/admin/galpoes" class="nav-link" :class="{ active: route.path === '/admin/galpoes' }">
                  <i class="far fa-circle nav-icon"></i>
                  <p>Galpões <span class="badge badge-primary ml-1" style="font-size:9px">Admin</span></p>
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
              <li v-if="canSee('config_marketplaces')" class="nav-item">
                <RouterLink to="/settings/marketplaces" class="nav-link" :class="{ active: route.path === '/settings/marketplaces' }">
                  <i class="far fa-circle nav-icon"></i>
                  <p>Config. de Marketplaces <span class="badge badge-primary ml-1" style="font-size:9px">Admin</span></p>
                </RouterLink>
              </li>
              <li v-if="canSee('config_marketplaces')" class="nav-item">
                <RouterLink to="/settings/marketplace-certificate" class="nav-link" :class="{ active: route.path === '/settings/marketplace-certificate' }">
                  <i class="far fa-circle nav-icon"></i>
                  <p>Certificado do Marketplace <span class="badge badge-primary ml-1" style="font-size:9px">Admin</span></p>
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
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMessagesStore } from '@/stores/messages'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const messagesStore = useMessagesStore()
const unreadMessages = computed(() => messagesStore.unreadTotal)

// ── Estado de abertura/fechamento das seções principais ───────────────
const STORAGE_KEY = 'sidebar_open_sections'

function loadSavedSections() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {} } catch { return {} }
}

const sections = reactive({
  contas: false,
  operacoes: false,
  operacao: false,
  separacao: false,
  estoque: false,
  fiscal: false,
  integracao: false,
  relatorios: false,
  monitoramento: false,
  gestao: false,
  admin: false,
  ...loadSavedSections(),
})

// Persiste o estado para sobreviver a reloads
watch(sections, (v) => {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(v)) } catch { /* ignore */ }
}, { deep: true })

function toggle(key) {
  sections[key] = !sections[key]
}

// Qual seção contém a rota atual — abre automaticamente ao navegar / carregar
function sectionForPath(path) {
  if (/^\/(cmig-reports|relatorios)/.test(path)) return 'relatorios'
  if (/^\/(cmigs|cmig-products|integrations|full-cnpjs)/.test(path)) return 'contas'
  if (/^\/(anuncios|campanha-ads|messages|financial|orders|catalog|manual-orders|estoque)/.test(path)) return 'operacoes'
  if (path.startsWith('/returns')) return path === '/returns/aguardando-retorno' ? 'estoque' : 'operacoes'
  if (path === '/inventario' || path.startsWith('/inventario/')) return 'estoque'
  if (path.startsWith('/pg')) return 'operacao'
  if (path.startsWith('/separacao')) return 'separacao'
  if (path.startsWith('/people') || path.startsWith('/fiscal/')) return 'fiscal'
  if (path.startsWith('/integracao/')) return 'integracao'
  if (path.startsWith('/monitoring')) return 'monitoramento'
  if (path.startsWith('/goes/')) return 'gestao'
  if (path.startsWith('/settings') || path.startsWith('/admin')) return 'admin'
  return null
}

function openActiveSection(path) {
  const sec = sectionForPath(path)
  if (sec) sections[sec] = true
}

watch(() => route.path, (p) => openActiveSection(p))

onMounted(() => {
  openActiveSection(route.path)
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

const roleLabel = computed(() => {
  if (authStore.user?.profile_name) return authStore.user.profile_name
  const map = { admin: 'Administrador', go: 'Gestor Operacional', ugo: 'Gestor Logístico', ac: 'Gestor de Conta' }
  return map[role.value] || role.value
})

// Mapa legado: qual menu_key cada role vê por padrão (sem perfil configurado)
const _legacyMenus = {
  admin: new Set([
    'cmig','integrations','cmig_reports','relatorio_vendas','full_cnpjs','anuncios','campanha_ads','atendimento','financeiro',
    'pedidos','catalog','pedido_manual','devolucoes','estoque',
    'pessoas','fiscal_entradas','fiscal_saidas','fiscal_cfop','fiscal_config','fiscal_transicao',
    'pg','separacao','ag_retorno','inventario','inventario_criar','rotinas',
    'integracao_envio',
    'go_empresa','go_usuarios',
    'config_usuarios','config_aprovacoes','config_email','config_eship','config_ncm','config_ai','config_marketplaces','config_galpoes','config_api_console','config_perfis',
  ]),
  ac: new Set([
    'cmig','integrations','cmig_reports','relatorio_vendas','full_cnpjs','anuncios','campanha_ads','atendimento','financeiro',
    'pedidos','catalog','pedido_manual','devolucoes','estoque',
    'pessoas','fiscal_entradas','fiscal_saidas','fiscal_cfop','fiscal_config','fiscal_transicao',
    'inventario','integracao_envio',
  ]),
  ugo: new Set([
    'pg','cmig','pedidos','estoque','separacao','ag_retorno','inventario','inventario_criar','devolucoes',
    'pessoas','fiscal_entradas','fiscal_saidas','rotinas','config_usuarios','integracao_envio',
  ]),
  go: new Set(['rotinas','go_empresa','go_usuarios','inventario','relatorio_vendas']),
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

<style scoped>
/* ── Hierarquia pai × filho no sidebar (sem cor forte no texto) ───────────────
   Pai (1º nível): branco + semibold. Filho: cinza, menor, recuado e ligado por
   uma linha-guia vertical. Menu aberto: realce sutil + barra fina de acento.
   `>` direto garante que só o 1º nível é "pai". */

/* Menus PAI (1º nível) — branco, semibold */
.main-sidebar .nav-sidebar > .nav-item > .nav-link {
  color: #ffffff;
  font-weight: 600;
}
.main-sidebar .nav-sidebar > .nav-item > .nav-link .nav-icon,
.main-sidebar .nav-sidebar > .nav-item > .nav-link p > .right {
  color: #ffffff;
}

/* "Sair" continua vermelho */
.main-sidebar .nav-sidebar > .nav-item > .nav-link.text-danger,
.main-sidebar .nav-sidebar > .nav-item > .nav-link.text-danger .nav-icon {
  color: #dc3545 !important;
}

/* Menu PAI ABERTO — realce sutil (fundo levíssimo + barra fina de acento à
   esquerda via box-shadow inset, sem deslocar o texto). :not(.active) para o
   item ativo manter o realce azul do AdminLTE. */
.main-sidebar .nav-sidebar > .nav-item.menu-open > .nav-link:not(.active) {
  background-color: rgba(255, 255, 255, 0.06);
  box-shadow: inset 3px 0 0 #20c997;
}

/* Filhos (nav-treeview) — cinza, menores, recuados, com linha-guia vertical
   verde (mesmo acento da barra do menu pai aberto). */
.main-sidebar .nav-sidebar > .nav-item > .nav-treeview {
  margin-left: 1.15rem;
  border-left: 2px solid #20c997;
}
.main-sidebar .nav-sidebar .nav-treeview > .nav-item > .nav-link {
  color: #aeb6c2;
  font-weight: 400;
  font-size: 0.9rem;
  padding-left: 0.85rem;
}
.main-sidebar .nav-sidebar .nav-treeview > .nav-item > .nav-link .nav-icon {
  color: #8a93a2;
  font-size: 0.85rem;
}
.main-sidebar .nav-sidebar .nav-treeview > .nav-item > .nav-link:hover {
  color: #ffffff;
}
.main-sidebar .nav-sidebar .nav-treeview > .nav-item > .nav-link:hover .nav-icon {
  color: #ffffff;
}

/* Filho ATIVO (rota atual) — fundo com contraste claro (verde água) + barra de
   acento à esquerda e texto branco/semibold, para destacar bem o selecionado. */
.main-sidebar .nav-sidebar .nav-treeview > .nav-item > .nav-link.active {
  background-color: rgba(32, 201, 151, 0.28);
  box-shadow: inset 3px 0 0 #20c997;
  color: #ffffff;
  font-weight: 600;
}
.main-sidebar .nav-sidebar .nav-treeview > .nav-item > .nav-link.active .nav-icon {
  color: #ffffff;
}
</style>
