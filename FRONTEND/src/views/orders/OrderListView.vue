<template>
  <div>
    <!-- Filters -->
    <div class="card mb-3">
      <div class="card-body py-2">
        <div class="row align-items-center g-2">
          <div class="col-md-3">
            <input v-model="filters.search" type="text" class="form-control form-control-sm" placeholder="Buscar por cliente..." @keyup.enter="loadOrders" />
          </div>
          <div class="col-md-2">
            <select v-model="filters.status" class="form-control form-control-sm" @change="loadOrders">
              <option value="">Todos os status</option>
              <option v-for="s in ORDER_STATUSES" :key="s.key" :value="s.key">{{ s.label }}</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.platform" class="form-control form-control-sm" @change="loadOrders">
              <option value="">Todos os canais</option>
              <option v-for="p in PLATFORMS" :key="p.key" :value="p.key">{{ p.label }}</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.payment_status" class="form-control form-control-sm" @change="loadOrders">
              <option value="">Pagamento</option>
              <option value="pending">Não pago</option>
              <option value="paid">Pago</option>
            </select>
          </div>
          <div class="col-md-1">
            <button class="btn btn-sm btn-primary" @click="loadOrders">
              <i class="fas fa-search"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h3 class="card-title">Pedidos</h3>
        <span class="badge badge-primary">{{ total }} total</span>
      </div>
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-sm table-hover mb-0">
            <thead>
              <tr>
                <th>#</th>
                <th>Canal</th>
                <th>Status</th>
                <th>Cliente</th>
                <th>Valor Venda</th>
                <th>Total Débito</th>
                <th>Rastreio</th>
                <th>Data</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="9" class="text-center py-4">
                  <i class="fas fa-spinner fa-spin"></i> Carregando...
                </td>
              </tr>
              <tr v-else-if="!orders.length">
                <td colspan="9" class="text-center py-4 text-muted">Nenhum pedido encontrado</td>
              </tr>
              <tr v-for="order in orders" :key="order.id">
                <td>{{ order.id }}</td>
                <td>
                  <span :class="`badge badge-${platformBadge(order.platform)}`">
                    {{ order.platform }}
                  </span>
                </td>
                <td>
                  <span :class="`badge badge-${statusColor(order.status)}`">
                    {{ statusLabel(order.status) }}
                  </span>
                </td>
                <td>{{ order.buyer_name }}</td>
                <td>{{ formatCurrency(order.sale_amount) }}</td>
                <td>{{ formatCurrency(order.total_debit) }}</td>
                <td>
                  <small v-if="order.tracking_code">{{ order.tracking_code }}</small>
                  <span v-else class="text-muted">—</span>
                </td>
                <td><small>{{ formatDateTime(order.created_at) }}</small></td>
                <td>
                  <div class="btn-group btn-group-sm">
                    <RouterLink :to="`/orders/${order.id}`" class="btn btn-outline-info">
                      <i class="fas fa-eye"></i>
                    </RouterLink>
                    <button
                      v-if="order.payment_status === 'pending' && order.status !== 'cancelled'"
                      class="btn btn-outline-success"
                      @click="payOrder(order)"
                    >
                      <i class="fas fa-dollar-sign"></i>
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card-footer">
        <div class="d-flex justify-content-between align-items-center">
          <span class="text-muted small">{{ total }} registros</span>
          <div>
            <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage <= 1" @click="prevPage">
              <i class="fas fa-chevron-left"></i>
            </button>
            <span class="mx-2">{{ currentPage }} / {{ totalPages }}</span>
            <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage >= totalPages" @click="nextPage">
              <i class="fas fa-chevron-right"></i>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import { ORDER_STATUSES, PLATFORMS } from '@/utils/constants'
import { useSocket } from '@/composables/useSocket'

const route = useRoute()

const orders = ref([])
const total = ref(0)
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)

const filters = reactive({
  search: route.query.search || '',
  status: route.query.status || '',
  platform: route.query.platform || '',
  payment_status: route.query.payment_status || '',
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function statusLabel(key) {
  return ORDER_STATUSES.find(s => s.key === key)?.label || key
}
function statusColor(key) {
  return ORDER_STATUSES.find(s => s.key === key)?.color || 'secondary'
}
function platformBadge(key) {
  const colors = { mercadolivre: 'warning', shopee: 'danger', manual: 'secondary' }
  return colors[key] || 'light'
}

async function loadOrders() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (filters.search) params.search = filters.search
    if (filters.status) params.status = filters.status
    if (filters.platform) params.platform = filters.platform
    if (filters.payment_status) params.payment_status = filters.payment_status

    const { data } = await api.get('/orders', { params })
    orders.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function payOrder(order) {
  if (!confirm(`Pagar pedido #${order.id}? O valor será debitado do seu saldo.`)) return
  try {
    const { data } = await api.post(`/orders/${order.id}/pay`)
    alert(`Pedido pago! Débito: R$ ${data.total_debit}`)
    await loadOrders()
  } catch (err) {
    alert(err.response?.data?.detail || 'Erro ao pagar pedido')
  }
}

function prevPage() { if (currentPage.value > 1) { currentPage.value--; loadOrders() } }
function nextPage() { if (currentPage.value < totalPages.value) { currentPage.value++; loadOrders() } }

onMounted(loadOrders)
</script>
