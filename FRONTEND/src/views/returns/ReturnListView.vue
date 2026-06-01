<template>
  <div>
    <!-- Callout apenas para AC -->
    <div v-if="!isUgoOrAdmin" class="callout callout-warning mb-3">
      <h5><i class="fas fa-info-circle"></i> Como funciona a devolução</h5>
      <p class="mb-1">1. Gerencie a devolução com o marketplace (fora do sistema)</p>
      <p class="mb-1">2. Oriente o cliente a enviar o produto para o fornecedor</p>
      <p class="mb-0">3. Registre aqui com o código de rastreio e aguarde a aprovação</p>
    </div>

    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h3 class="card-title mb-0">
          {{ isUgoOrAdmin ? 'Devoluções (todos os usuários)' : 'Minhas Devoluções' }}
        </h3>
        <RouterLink v-if="!isUgoOrAdmin" to="/returns/new" class="btn btn-sm btn-primary">
          <i class="fas fa-plus mr-1"></i> Nova Devolução
        </RouterLink>
      </div>

      <!-- Tabs -->
      <div class="card-header p-0 border-bottom-0">
        <ul class="nav nav-tabs" id="returns-tabs">
          <li class="nav-item">
            <a href="#" :class="['nav-link', activeTab === '' ? 'active' : '']" @click.prevent="setTab('')">
              Todas
            </a>
          </li>
          <li class="nav-item">
            <a href="#" :class="['nav-link', activeTab === 'analyzing' ? 'active' : '']" @click.prevent="setTab('analyzing')">
              Em Análise
            </a>
          </li>
          <li v-if="isUgoOrAdmin" class="nav-item">
            <a href="#" :class="['nav-link', activeTab === 'awaiting_validation' ? 'active' : '']" @click.prevent="setTab('awaiting_validation')">
              Ag. Validação
              <span v-if="pendingValidationCount > 0" class="badge badge-warning ml-1">{{ pendingValidationCount }}</span>
            </a>
          </li>
          <li class="nav-item">
            <a href="#" :class="['nav-link', activeTab === 'returned' ? 'active' : '']" @click.prevent="setTab('returned')">
              Devolvidos
            </a>
          </li>
          <li class="nav-item">
            <a href="#" :class="['nav-link', activeTab === 'rejected' ? 'active' : '']" @click.prevent="setTab('rejected')">
              Rejeitados
            </a>
          </li>
          <li class="nav-item">
            <a href="#" :class="['nav-link', activeTab === 'validated_ok' ? 'active' : '']" @click.prevent="setTab('validated_ok')">
              Validados OK
            </a>
          </li>
          <li class="nav-item">
            <a href="#" :class="['nav-link', activeTab === 'validated_unfit' ? 'active' : '']" @click.prevent="setTab('validated_unfit')">
              <span class="text-danger">Inaptos</span>
            </a>
          </li>
        </ul>
      </div>

      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead class="thead-light">
            <tr>
              <th>#</th>
              <th>Pedido</th>
              <th>Motivo</th>
              <th>Rastreio</th>
              <th>Tipo</th>
              <th>Status</th>
              <th>Data</th>
              <th v-if="isUgoOrAdmin">Ação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td :colspan="isUgoOrAdmin ? 8 : 7" class="text-center py-4">
                <i class="fas fa-spinner fa-spin"></i>
              </td>
            </tr>
            <tr v-else-if="!returns.length">
              <td :colspan="isUgoOrAdmin ? 8 : 7" class="text-center py-4 text-muted">
                Nenhuma devolução encontrada
              </td>
            </tr>
            <tr v-for="r in returns" :key="r.id">
              <td>{{ r.id }}</td>
              <td>{{ r.order_id || '—' }}</td>
              <td>{{ r.reason }}</td>
              <td>{{ r.tracking_code || '—' }}</td>
              <td>
                <span :class="r.return_type === 'cancelled_order' ? 'badge badge-secondary' : 'badge badge-light border'">
                  {{ r.return_type === 'cancelled_order' ? 'Ped. Cancelado' : 'Devolução' }}
                </span>
              </td>
              <td>
                <span :class="`badge badge-${statusColor(r.status)}`">{{ statusLabel(r.status) }}</span>
              </td>
              <td><small>{{ formatDateTime(r.created_at) }}</small></td>
              <td v-if="isUgoOrAdmin">
                <RouterLink
                  v-if="r.status === 'awaiting_validation'"
                  :to="`/returns/validar/${r.id}`"
                  class="btn btn-xs btn-warning"
                >
                  <i class="fas fa-clipboard-check mr-1"></i> Validar
                </RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="card-footer d-flex justify-content-between align-items-center" v-if="total > pageSize || total > 0">
        <small class="text-muted">{{ total }} devolução(ões)</small>
        <div v-if="total > pageSize" class="d-flex gap-2">
          <button class="btn btn-sm btn-outline-secondary" :disabled="page <= 1" @click="changePage(page - 1)">
            <i class="fas fa-chevron-left"></i>
          </button>
          <small class="align-self-center">{{ page }} / {{ Math.ceil(total / pageSize) }}</small>
          <button class="btn btn-sm btn-outline-secondary" :disabled="page >= Math.ceil(total / pageSize)" @click="changePage(page + 1)">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatDateTime } from '@/utils/formatters'

const returns = ref([])
const loading = ref(true)
const activeTab = ref('')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const pendingValidationCount = ref(0)

const currentUser = JSON.parse(localStorage.getItem('auth') || '{}').user
const isUgoOrAdmin = computed(() => ['ugo', 'admin'].includes(currentUser?.role))

const STATUS_COLORS = {
  analyzing: 'warning',
  returned: 'success',
  rejected: 'danger',
  awaiting_validation: 'secondary',
  validated_ok: 'success',
  validated_unfit: 'danger',
  awaiting_physical_return: 'info',
}
const STATUS_LABELS = {
  analyzing: 'Em Análise',
  returned: 'Devolvido',
  rejected: 'Rejeitado',
  awaiting_validation: 'Ag. Validação',
  validated_ok: 'Validado OK',
  validated_unfit: 'Inapto',
  awaiting_physical_return: 'Ag. Retorno',
}

function statusColor(s) { return STATUS_COLORS[s] || 'secondary' }
function statusLabel(s) { return STATUS_LABELS[s] || s }

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (activeTab.value) params.status = activeTab.value

    let url = '/returns'
    if (isUgoOrAdmin.value) {
      if (activeTab.value === 'awaiting_validation') {
        // endpoint dedicado retorna todos os usuários + já filtra por status
        url = '/returns/pending-validation'
      } else {
        // passa all=true para ver devoluções de todos os dropshippers
        params.all = true
      }
    }

    const { data } = await api.get(url, { params })
    returns.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadPendingCount() {
  if (!isUgoOrAdmin.value) return
  try {
    const { data } = await api.get('/returns/pending-validation', { params: { page: 1, page_size: 1 } })
    pendingValidationCount.value = data.total
  } catch {
    pendingValidationCount.value = 0
  }
}

function setTab(tab) {
  activeTab.value = tab
  page.value = 1
  load()
}

function changePage(p) {
  page.value = p
  load()
}

onMounted(() => {
  load()
  loadPendingCount()
})
</script>

<style scoped>
.gap-2 { gap: 0.5rem; }
</style>
