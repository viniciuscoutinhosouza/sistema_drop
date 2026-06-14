import { createRouter, createWebHistory } from 'vue-router'

// Layouts
const AuthLayout = () => import('@/layouts/AuthLayout.vue')
const DashboardLayout = () => import('@/layouts/DashboardLayout.vue')

// Auth views
const LoginView = () => import('@/views/auth/LoginView.vue')
const RegisterView = () => import('@/views/auth/RegisterView.vue')
const OAuthSuccessView = () => import('@/views/auth/OAuthSuccessView.vue')

// Dashboard
const DashboardView = () => import('@/views/DashboardView.vue')
const MarketplaceDashboardView = () => import('@/views/MarketplaceDashboardView.vue')

// Financial
const FinancialView = () => import('@/views/financial/FinancialView.vue')

// Products
const ProductListView = () => import('@/views/products/ProductListView.vue')
const ProductCreateView = () => import('@/views/products/ProductCreateView.vue')
const ProductEditView = () => import('@/views/products/ProductEditView.vue')

// Catalog
const CatalogView = () => import('@/views/catalog/CatalogView.vue')
const CatalogProductView = () => import('@/views/catalog/CatalogProductView.vue')
const CatalogVariationsFormView = () => import('@/views/catalog/CatalogVariationsFormView.vue')

// Orders
const OrderListView = () => import('@/views/orders/OrderListView.vue')
const OrderDetailView = () => import('@/views/orders/OrderDetailView.vue')

// Manual Orders
const ManualOrderView = () => import('@/views/manual-orders/ManualOrderView.vue')

// Integrations
const IntegrationsView = () => import('@/views/integrations/IntegrationsView.vue')

// Returns
const ReturnListView = () => import('@/views/returns/ReturnListView.vue')
const ReturnCreateView = () => import('@/views/returns/ReturnCreateView.vue')
const ReturnValidationView = () => import('@/views/returns/ReturnValidationView.vue')
const AwaitingReturnView = () => import('@/views/returns/AwaitingReturnView.vue')

// Stock
const StockControlView = () => import('@/views/stock/StockControlView.vue')

// FULL (ML Fulfillment)
const FullCnpjsView = () => import('@/views/full/FullCnpjsView.vue')

// Notifications
const NotificationsView = () => import('@/views/notifications/NotificationsView.vue')

// Supplier / PG
const SupplierProductListView = () => import('@/views/supplier/SupplierProductListView.vue')
const PgProductFormView       = () => import('@/views/supplier/PgProductFormView.vue')
const PgCompositeFormView     = () => import('@/views/supplier/PgCompositeFormView.vue')

// Inventário (ESTOQUE)
const InventoryListView = () => import('@/views/inventory/InventoryListView.vue')
const InventoryFormView = () => import('@/views/inventory/InventoryFormView.vue')

// Settings
const UsersView     = () => import('@/views/settings/UsersView.vue')
const WarehouseView = () => import('@/views/settings/WarehouseView.vue')

// GOs (admin only)
const GoListView = () => import('@/views/go/GoListView.vue')
const GoFormView = () => import('@/views/go/GoFormView.vue')

// CMIGs (AC + UGO)
const CmigListView   = () => import('@/views/cmig/CmigListView.vue')
const CmigFormView   = () => import('@/views/cmig/CmigFormView.vue')
const CmigDetailView = () => import('@/views/cmig/CmigDetailView.vue')

// Produtos CMIG (AC + UGO)
const CmigProductListView       = () => import('@/views/cmig-products/CmigProductListView.vue')
const CmigProductFormView       = () => import('@/views/cmig-products/CmigProductFormView.vue')
const CmigCompositeFormView     = () => import('@/views/cmig-products/CmigCompositeFormView.vue')

// Anúncios (AC)
const AnunciosView = () => import('@/views/anuncios/AnunciosView.vue')
const CampaignAdsView = () => import('@/views/campanha-ads/CampaignAdsView.vue')

// Relatórios CMIG (AC)
const CmigReportsView = () => import('@/views/cmig-reports/CmigReportsView.vue')

// Simulador ML
const SimuladorView = () => import('@/views/simulator/SimuladorView.vue')

// Pessoas (Clientes / Fornecedores)
const PeopleListView = () => import('@/views/people/PeopleListView.vue')
const PersonFormView = () => import('@/views/people/PersonFormView.vue')

// Settings extras
const NcmView = () => import('@/views/settings/NcmView.vue')

// Fiscal (NF-e)
const EntradasView      = () => import('@/views/fiscal/EntradasView.vue')
const SaidasView        = () => import('@/views/fiscal/SaidasView.vue')
const InvoiceFormView   = () => import('@/views/fiscal/InvoiceFormView.vue')
const InvoiceDetailView = () => import('@/views/fiscal/InvoiceDetailView.vue')
const CfopView                  = () => import('@/views/fiscal/CfopView.vue')
const FiscalConfigView          = () => import('@/views/fiscal/FiscalConfigView.vue')
const TransicaoTributariaView   = () => import('@/views/fiscal/TransicaoTributariaView.vue')

// Atendimento (Mensagens)
const MessagesView = () => import('@/views/messages/MessagesView.vue')

// Configuração IA
const AIConfigView = () => import('@/views/settings/AIConfigView.vue')
const EmailConfigView = () => import('@/views/settings/EmailConfigView.vue')
const MarketplaceSettingsView = () => import('@/views/settings/MarketplaceSettingsView.vue')
const EShipConfigView = () => import('@/views/integrations/eship/EShipConfigView.vue')

// Console de API do Marketplace — Admin only
const ApiConsoleView = () => import('@/views/admin/ApiConsoleView.vue')

// Gestão de Perfis de Acesso — Admin only
const ProfilesView = () => import('@/views/admin/ProfilesView.vue')

// Monitoramento de Rotinas (UGO + GO + Admin)
const SchedulerMonitoringView = () => import('@/views/monitoring/SchedulerMonitoringView.vue')

// Separação (Operador Logístico — pedidos não-FULL)
const SeparationView = () => import('@/views/separation/SeparationView.vue')
const CartsListView  = () => import('@/views/separation/CartsListView.vue')


const routes = [
  // Auth routes (no sidebar)
  {
    path: '/login',
    component: AuthLayout,
    children: [{ path: '', component: LoginView }],
    meta: { guestOnly: true },
  },
  {
    path: '/register',
    component: AuthLayout,
    children: [{ path: '', component: RegisterView }],
    meta: { guestOnly: true },
  },
  {
    path: '/oauth/success',
    component: OAuthSuccessView,
  },

  // Authenticated routes (with AdminLTE layout)
  {
    path: '/',
    component: DashboardLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: DashboardView, meta: { title: 'Dashboard' } },
      {
        path: 'dashboard/marketplace',
        component: MarketplaceDashboardView,
        meta: { title: 'Dashboard de Marketplaces' },
      },

      { path: 'financial', component: FinancialView, meta: { title: 'Financeiro' } },

      { path: 'products', component: ProductListView, meta: { title: 'Meus Produtos' } },
      { path: 'products/new', component: ProductCreateView, meta: { title: 'Cadastrar Produto' } },
      { path: 'products/:id/edit', component: ProductEditView, meta: { title: 'Editar Produto' } },

      { path: 'catalog', component: CatalogView, meta: { title: 'Catálogo' } },
      { path: 'catalog/anuncios-variacoes/new', component: CatalogVariationsFormView, meta: { title: 'Novo Anúncio com Variações' } },
      { path: 'catalog/anuncios-variacoes/:listing_id/edit', component: CatalogVariationsFormView, meta: { title: 'Editar Anúncio com Variações' } },
      { path: 'catalog/:id', component: CatalogProductView, meta: { title: 'Produto do Catálogo' } },

      { path: 'orders', component: OrderListView, meta: { title: 'Pedidos' } },
      { path: 'orders/:id', component: OrderDetailView, meta: { title: 'Detalhes do Pedido' } },

      { path: 'manual-orders', component: ManualOrderView, meta: { title: 'Pedido Manual' } },

      { path: 'integrations', component: IntegrationsView, meta: { title: 'Integrações' } },

      { path: 'returns', component: ReturnListView, meta: { title: 'Devoluções' } },
      { path: 'returns/new', component: ReturnCreateView, meta: { title: 'Nova Devolução' } },
      { path: 'returns/aguardando-validacao', component: ReturnListView, meta: { title: 'Ag. Validação', role: 'ugo' } },
      { path: 'returns/aguardando-retorno', component: AwaitingReturnView, meta: { title: 'Ag. Retorno Físico', role: 'ugo' } },
      { path: 'returns/validar/:id', component: ReturnValidationView, meta: { title: 'Validar Devolução', role: 'ugo' } },

      { path: 'estoque', component: StockControlView, meta: { title: 'Controle de Estoque', role: ['ugo', 'ac'] } },
      { path: 'full-cnpjs', component: FullCnpjsView, meta: { title: 'CNPJs FULL', role: 'ac' } },

      { path: 'notifications', component: NotificationsView, meta: { title: 'Notificações' } },

      // UGO-only (Operador Logístico — Produto Geral)
      { path: 'pg',                    component: SupplierProductListView, meta: { title: 'Produtos Gerais (PG)', menuKey: 'pg' } },
      { path: 'pg/new',                component: PgProductFormView,       meta: { title: 'Novo Produto PG',      menuKey: 'pg' } },
      { path: 'pg/novo-composto',      component: PgCompositeFormView,     meta: { title: 'Novo KIT PG', menuKey: 'pg' } },
      { path: 'pg/:id/edit',           component: PgProductFormView,       meta: { title: 'Editar Produto PG',    menuKey: 'pg' } },
      { path: 'pg/:id/editar-composto', component: PgCompositeFormView,    meta: { title: 'Editar KIT PG', menuKey: 'pg' } },

      // Separação (Operador Logístico — pedidos não-FULL)
      { path: 'separacao',         component: SeparationView, meta: { title: 'Separação', menuKey: 'separacao' } },
      { path: 'separacao/gaiolas', component: CartsListView,  meta: { title: 'Gaiolas / Transportadora', menuKey: 'separacao' } },

      // Inventário (ESTOQUE)
      { path: 'inventario',        component: InventoryListView, meta: { title: 'Inventário', menuKey: 'inventario' } },
      { path: 'inventario/novo',   component: InventoryFormView, meta: { title: 'Novo Inventário', menuKey: 'inventario_criar' } },
      { path: 'inventario/:id',    component: InventoryFormView, meta: { title: 'Inventário', menuKey: 'inventario' } },

      // Configurações — Admin e UGO
      {
        path: 'settings/users',
        component: UsersView,
        meta: { title: 'Usuários', role: 'ugo' },
      },
      {
        path: 'settings/warehouse',
        component: WarehouseView,
        meta: { title: 'Galpão', role: 'go' },
      },

      // GOs — somente admin
      { path: 'goes', component: GoListView, meta: { title: 'Gestores Operacionais', role: 'admin' } },
      { path: 'goes/new', component: GoFormView, meta: { title: 'Novo GO', role: 'admin' } },
      { path: 'goes/:id/edit', component: GoFormView, meta: { title: 'Editar GO', role: 'admin' } },

      // CMIGs — AC e UGO
      { path: 'cmigs', component: CmigListView, meta: { title: 'Contas MIG' } },
      { path: 'cmigs/new', component: CmigFormView, meta: { title: 'Nova CMIG', role: 'ac' } },
      { path: 'cmigs/:id', component: CmigDetailView, meta: { title: 'CMIG' } },
      { path: 'cmigs/:id/edit', component: CmigFormView, meta: { title: 'Editar CMIG', role: 'ac' } },

      // Produtos CMIG
      { path: 'cmig-products',                        component: CmigProductListView,   meta: { title: 'Produtos CMIG' } },
      { path: 'cmig-products/new',                    component: CmigProductFormView,   meta: { title: 'Novo Produto CMIG', role: 'ac' } },
      { path: 'cmig-products/novo-composto',          component: CmigCompositeFormView, meta: { title: 'Novo KIT CMIG', role: 'ac' } },
      { path: 'cmig-products/:id/edit',               component: CmigProductFormView,   meta: { title: 'Editar Produto CMIG', role: ['ac', 'ugo'] } },
      { path: 'cmig-products/:id/editar-composto',    component: CmigCompositeFormView, meta: { title: 'Editar KIT CMIG', role: ['ac', 'ugo'] } },

      // Anúncios — AC
      { path: 'anuncios', component: AnunciosView, meta: { title: 'Anúncios', role: 'ac' } },

      // Campanha ADS — AC
      { path: 'campanha-ads', component: CampaignAdsView, meta: { title: 'Campanha ADS', role: 'ac' } },

      // Relatórios CMIG — AC
      { path: 'cmig-reports', component: CmigReportsView, meta: { title: 'Relatórios CMIG', role: 'ac' } },

      // Atendimento (Mensagens + Perguntas) — AC e Admin
      { path: 'messages', component: MessagesView, meta: { title: 'Central de Atendimento' } },

      // Configuração IA — Admin
      { path: 'settings/ai-config', component: AIConfigView, meta: { title: 'Configuração de IA', role: 'admin' } },

      // Configuração de Marketplaces — Super Admin
      { path: 'settings/marketplaces', component: MarketplaceSettingsView, meta: { title: 'Config. de Marketplaces', role: 'admin' } },

      // Servidor de E-mail (SMTP) — Admin
      { path: 'settings/email', component: EmailConfigView, meta: { title: 'Servidor de E-mail', role: 'admin' } },

      // Integração eShip (WMS) — Admin
      { path: 'settings/eship', component: EShipConfigView, meta: { title: 'Integração eShip', role: 'admin' } },

      // Tabela NCM — Admin
      { path: 'settings/ncm', component: NcmView, meta: { title: 'Tabela NCM', role: 'admin' } },

      // Console de API do Marketplace — Admin only
      { path: 'admin/api-console', component: ApiConsoleView, meta: { title: 'Console de API', role: 'admin' } },
      { path: 'admin/profiles',    component: ProfilesView,   meta: { title: 'Gestão de Perfis', role: 'admin' } },

      // Simulador ML — todos os usuários
      { path: 'simulator', component: SimuladorView, meta: { title: 'Simulador ML' } },

      // Pessoas (Clientes/Fornecedores) — AC, UGO, Admin
      { path: 'people',         component: PeopleListView, meta: { title: 'Pessoas' } },
      { path: 'people/new',     component: PersonFormView, meta: { title: 'Nova Pessoa' } },
      { path: 'people/:id',     component: PersonFormView, meta: { title: 'Editar Pessoa' } },

      // Monitoramento de Rotinas — UGO + GO + Admin (GO/Admin herdam pela lógica do guard)
      { path: 'monitoring/jobs', component: SchedulerMonitoringView, meta: { title: 'Monitoramento de Rotinas', role: 'ugo' } },

      // Fiscal — Entradas / Saídas / Config
      { path: 'fiscal/entradas',          component: EntradasView,      meta: { title: 'Entradas (NF-e)' } },
      { path: 'fiscal/saidas',            component: SaidasView,        meta: { title: 'Saídas (NF-e)' } },
      { path: 'fiscal/invoices/new',      component: InvoiceFormView,   meta: { title: 'Nova NF-e' } },
      { path: 'fiscal/invoices/:id',      component: InvoiceDetailView, meta: { title: 'NF-e' } },
      { path: 'fiscal/invoices/:id/edit', component: InvoiceFormView,   meta: { title: 'Editar NF-e' } },
      { path: 'fiscal/cfop',              component: CfopView,                meta: { title: 'Cadastro de CFOPs' } },
      { path: 'fiscal/config',            component: FiscalConfigView,        meta: { title: 'Configuração Fiscal', role: 'ac' } },
      { path: 'fiscal/transicao',         component: TransicaoTributariaView, meta: { title: 'Transição Tributária' } },
    ],
  },

  // Catch-all
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// Navigation guards
router.beforeEach((to, from, next) => {
  const stored = localStorage.getItem('auth')
  const isAuthenticated = !!stored && !!JSON.parse(stored || '{}').accessToken

  if (to.meta.requiresAuth && !isAuthenticated) {
    return next('/login')
  }

  if (to.meta.guestOnly && isAuthenticated) {
    return next('/dashboard')
  }

  // Gate por menu_permission (novo padrão alinhado com backend require_menu_permission)
  if (to.meta.menuKey) {
    const user = JSON.parse(stored || '{}').user
    const role = user?.role
    // Admin sempre passa
    if (role !== 'admin') {
      const perms = Array.isArray(user?.menu_permissions) ? user.menu_permissions : []
      if (!perms.includes(to.meta.menuKey)) {
        return next('/dashboard')
      }
    }
  }

  if (to.meta.role) {
    const user = JSON.parse(stored || '{}').user
    const role = user?.role
    const requiredRole = to.meta.role

    // admin acessa tudo; go acessa rotas de go e ugo; ugo acessa rotas de ugo; ac acessa rotas de ac
    const roles = Array.isArray(requiredRole) ? requiredRole : [requiredRole]
    const canAccess = role === 'admin' ||
      roles.includes(role) ||
      (roles.includes('ugo') && role === 'go')

    if (!canAccess) {
      return next('/dashboard')
    }
  }

  next()
})

export default router
