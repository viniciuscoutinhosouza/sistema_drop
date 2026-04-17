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

// Supplier
const SupplierProductListView = () => import('@/views/supplier/SupplierProductListView.vue')


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

      // Supplier-only
      {
        path: 'supplier/products',
        component: SupplierProductListView,
        meta: { title: 'Gestão do Catálogo', role: 'supplier' },
      },
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
    if (!user || user.role !== to.meta.role) {
      return next('/dashboard')
    }
  }

  next()
})

export default router
