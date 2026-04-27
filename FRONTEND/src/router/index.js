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

// Financial
const FinancialView = () => import('@/views/financial/FinancialView.vue')

// Products
const ProductListView = () => import('@/views/products/ProductListView.vue')
const ProductCreateView = () => import('@/views/products/ProductCreateView.vue')
const ProductEditView = () => import('@/views/products/ProductEditView.vue')

// Kits
const KitListView = () => import('@/views/kits/KitListView.vue')
const KitCreateView = () => import('@/views/kits/KitCreateView.vue')
const KitEditView = () => import('@/views/kits/KitEditView.vue')

// Catalog
const CatalogView = () => import('@/views/catalog/CatalogView.vue')
const CatalogProductView = () => import('@/views/catalog/CatalogProductView.vue')

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

// Notifications
const NotificationsView = () => import('@/views/notifications/NotificationsView.vue')

// Supplier / PG
const SupplierProductListView = () => import('@/views/supplier/SupplierProductListView.vue')

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
const CmigProductListView = () => import('@/views/cmig-products/CmigProductListView.vue')
const CmigProductFormView = () => import('@/views/cmig-products/CmigProductFormView.vue')

// Anúncios (AC)
const AnunciosView = () => import('@/views/anuncios/AnunciosView.vue')

// Simulador ML
const SimuladorView = () => import('@/views/simulator/SimuladorView.vue')


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

      { path: 'financial', component: FinancialView, meta: { title: 'Financeiro' } },

      { path: 'products', component: ProductListView, meta: { title: 'Meus Produtos' } },
      { path: 'products/new', component: ProductCreateView, meta: { title: 'Cadastrar Produto' } },
      { path: 'products/:id/edit', component: ProductEditView, meta: { title: 'Editar Produto' } },

      { path: 'kits', component: KitListView, meta: { title: 'Kits' } },
      { path: 'kits/new', component: KitCreateView, meta: { title: 'Criar Kit' } },
      { path: 'kits/:id/edit', component: KitEditView, meta: { title: 'Editar Kit' } },

      { path: 'catalog', component: CatalogView, meta: { title: 'Catálogo' } },
      { path: 'catalog/:id', component: CatalogProductView, meta: { title: 'Produto do Catálogo' } },

      { path: 'orders', component: OrderListView, meta: { title: 'Pedidos' } },
      { path: 'orders/:id', component: OrderDetailView, meta: { title: 'Detalhes do Pedido' } },

      { path: 'manual-orders', component: ManualOrderView, meta: { title: 'Drop Manual' } },

      { path: 'integrations', component: IntegrationsView, meta: { title: 'Integrações' } },

      { path: 'returns', component: ReturnListView, meta: { title: 'Devoluções' } },
      { path: 'returns/new', component: ReturnCreateView, meta: { title: 'Nova Devolução' } },

      { path: 'notifications', component: NotificationsView, meta: { title: 'Notificações' } },

      // UGO-only (Operador Logístico — Produto Geral)
      {
        path: 'pg',
        component: SupplierProductListView,
        meta: { title: 'Produto Geral (PG)', role: 'ugo' },
      },

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
      { path: 'cmig-products', component: CmigProductListView, meta: { title: 'Produtos CMIG' } },
      { path: 'cmig-products/new', component: CmigProductFormView, meta: { title: 'Novo Produto CMIG', role: 'ac' } },
      { path: 'cmig-products/:id/edit', component: CmigProductFormView, meta: { title: 'Editar Produto CMIG', role: 'ac' } },

      // Anúncios — AC
      { path: 'anuncios', component: AnunciosView, meta: { title: 'Anúncios', role: 'ac' } },

      // Simulador ML — todos os usuários
      { path: 'simulator', component: SimuladorView, meta: { title: 'Simulador ML' } },
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

  if (to.meta.role) {
    const user = JSON.parse(stored || '{}').user
    const role = user?.role
    const requiredRole = to.meta.role

    // admin acessa tudo; go acessa rotas de go e ugo; ugo acessa rotas de ugo; ac acessa rotas de ac
    const canAccess = role === 'admin' ||
      role === requiredRole ||
      (requiredRole === 'ugo' && role === 'go') ||
      (requiredRole === 'go' && role === 'go')

    if (!canAccess) {
      return next('/dashboard')
    }
  }

  next()
})

export default router
