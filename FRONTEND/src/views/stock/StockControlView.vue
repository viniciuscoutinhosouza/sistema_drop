<template>
  <div>
    <div class="card">
      <div class="card-header d-flex align-items-center justify-content-between">
        <h3 class="card-title mb-0">Controle de Estoque</h3>
        <div class="d-flex align-items-center gap-2">
          <input
            v-model="search"
            @input="debouncedLoad"
            type="text"
            placeholder="Buscar produto..."
            class="form-control form-control-sm"
            style="width: 220px"
          />
          <button class="btn btn-sm btn-outline-secondary" @click="load">
            <i class="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm table-hover mb-0">
          <thead class="thead-light">
            <tr>
              <th>Produto</th>
              <th class="text-center" style="width:60px">Tipo</th>
              <th class="text-center" title="Estoque físico no galpão">Físico</th>
              <th class="text-center" title="Reservado por pedidos ativos">Reservado</th>
              <th class="text-center text-success" title="Disponível para venda">Disponível</th>
              <th class="text-center text-info" title="Produto em trânsito de volta">Ag. Retorno</th>
              <th class="text-center" title="Devolução recebida, aguardando inspeção">Ag. Validação</th>
              <th class="text-center text-danger" title="Reprovado na inspeção">Inapto</th>
              <th class="text-center text-purple" title="Estoque no ML Fulfillment (FULL)">FULL</th>
              <th style="width:30px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="10" class="text-center py-4">
                <i class="fas fa-spinner fa-spin"></i>
              </td>
            </tr>
            <tr v-else-if="!items.length">
              <td colspan="10" class="text-center py-4 text-muted">
                Nenhum produto com estoque encontrado
              </td>
            </tr>
            <template v-for="item in items" :key="itemKey(item)">
              <tr
                class="cursor-pointer"
                @click="toggleExpand(item)"
                :class="{ 'table-active': expandedKey === itemKey(item) }"
              >
                <td>{{ item.name }}</td>
                <td class="text-center">
                  <span :class="item.product_type === 'pg' ? 'badge badge-primary' : 'badge badge-info'">
                    {{ item.product_type === 'pg' ? 'PG' : 'CMIG' }}
                  </span>
                </td>
                <td class="text-center font-weight-bold">{{ item.physical }}</td>
                <td class="text-center">
                  <span :class="item.reserved > 0 ? 'text-warning font-weight-bold' : 'text-muted'">
                    {{ item.reserved }}
                  </span>
                </td>
                <td class="text-center">
                  <span :class="item.available > 0 ? 'text-success font-weight-bold' : 'text-muted'">
                    {{ item.available }}
                  </span>
                </td>
                <td class="text-center">
                  <span :class="item.awaiting_return > 0 ? 'text-info font-weight-bold' : 'text-muted'">
                    {{ item.awaiting_return }}
                  </span>
                </td>
                <td class="text-center">
                  <span :class="item.pending_validation > 0 ? 'text-secondary font-weight-bold' : 'text-muted'">
                    {{ item.pending_validation }}
                  </span>
                </td>
                <td class="text-center">
                  <span :class="item.unfit > 0 ? 'text-danger font-weight-bold' : 'text-muted'">
                    {{ item.unfit }}
                  </span>
                </td>
                <td class="text-center">
                  <span
                    v-if="item.full_stock_total > 0"
                    class="font-weight-bold"
                    style="color:#6f42c1"
                    :title="fullStockTooltip(item.full_stock)"
                  >
                    {{ item.full_stock_total }}
                  </span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="text-center text-muted">
                  <i :class="expandedKey === itemKey(item) ? 'fas fa-chevron-up' : 'fas fa-chevron-down'" style="font-size:11px"></i>
                </td>
              </tr>
              <tr v-if="expandedKey === itemKey(item)">
                <td colspan="10" class="p-0 bg-light border-top-0">
                  <div class="px-4 py-3">
                    <h6 class="mb-2 text-muted">
                      <i class="fas fa-history mr-1"></i> Histórico de Movimentos
                    </h6>
                    <div v-if="loadingMovements" class="text-center py-2">
                      <i class="fas fa-spinner fa-spin"></i>
                    </div>
                    <div v-else-if="!movements.length" class="text-muted small">
                      Nenhum movimento registrado ainda.
                    </div>
                    <table v-else class="table table-xs table-bordered table-sm mb-0" style="font-size:12px">
                      <thead>
                        <tr>
                          <th>Data</th>
                          <th>Tipo</th>
                          <th>Campo</th>
                          <th class="text-center">Delta</th>
                          <th class="text-center">Pedido</th>
                          <th class="text-center">Devolução</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="m in movements" :key="m.id">
                          <td>{{ formatDateTime(m.created_at) }}</td>
                          <td>
                            <span :class="`badge badge-${movementColor(m.movement_type)}`">
                              {{ movementLabel(m.movement_type) }}
                            </span>
                          </td>
                          <td class="text-muted">{{ m.field_affected }}</td>
                          <td class="text-center" :class="m.delta > 0 ? 'text-success' : 'text-danger'">
                            <strong>{{ m.delta > 0 ? '+' : '' }}{{ m.delta }}</strong>
                          </td>
                          <td class="text-center">{{ m.order_id || '—' }}</td>
                          <td class="text-center">{{ m.return_id || '—' }}</td>
                        </tr>
                      </tbody>
                    </table>
                    <div v-if="movementsTotal > movements.length" class="text-right mt-2">
                      <small class="text-muted">Mostrando {{ movements.length }} de {{ movementsTotal }}</small>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div class="card-footer d-flex justify-content-between align-items-center" v-if="total > 0">
        <small class="text-muted">{{ total }} produto(s) com estoque</small>
        <div v-if="total > pageSize" class="d-flex align-items-center gap-2">
          <button class="btn btn-sm btn-outline-secondary" :disabled="page <= 1" @click="changePage(page - 1)">
            <i class="fas fa-chevron-left"></i>
          </button>
          <small>{{ page }} / {{ Math.ceil(total / pageSize) }}</small>
          <button class="btn btn-sm btn-outline-secondary" :disabled="page >= Math.ceil(total / pageSize)" @click="changePage(page + 1)">
            <i class="fas fa-chevron-right"></i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatDateTime } from '@/utils/formatters'

const items = ref([])
const loading = ref(true)
const search = ref('')
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)

const expandedKey = ref(null)
const movements = ref([])
const movementsTotal = ref(0)
const loadingMovements = ref(false)

let searchTimer = null

function itemKey(item) {
  return `${item.product_type}-${item.product_id}`
}

async function load() {
  loading.value = true
  const params = { page: page.value, page_size: pageSize.value }
  if (search.value) params.search = search.value
  try {
    const { data } = await api.get('/stock/summary', { params })
    items.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function debouncedLoad() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; load() }, 400)
}

async function changePage(p) {
  page.value = p
  expandedKey.value = null
  await load()
}

async function toggleExpand(item) {
  const key = itemKey(item)
  if (expandedKey.value === key) {
    expandedKey.value = null
    return
  }
  expandedKey.value = key
  movements.value = []
  movementsTotal.value = 0
  loadingMovements.value = true
  try {
    const { data } = await api.get(`/stock/${item.product_type}/${item.product_id}/movements`)
    movements.value = data.items
    movementsTotal.value = data.total
  } finally {
    loadingMovements.value = false
  }
}

function fullStockTooltip(fullStock) {
  if (!fullStock || !Object.keys(fullStock).length) return 'Sem estoque FULL'
  return Object.entries(fullStock)
    .map(([acctId, qty]) => `Conta ${acctId}: ${qty} un`)
    .join('\n')
}

const MOVEMENT_COLORS = {
  reserve: 'warning',
  unreserve: 'info',
  dispatch: 'danger',
  await_return: 'secondary',
  confirm_return: 'success',
  receive_return: 'primary',
  validate_ok: 'success',
  validate_unfit: 'danger',
  full_in: 'purple',
  full_out: 'danger',
  full_return_out: 'info',
  manual: 'light',
}
const MOVEMENT_LABELS = {
  reserve: 'Reservado',
  unreserve: 'Reserva liberada',
  dispatch: 'Despachado',
  await_return: 'Ag. Retorno',
  confirm_return: 'Retorno confirmado',
  receive_return: 'Devolução recebida',
  validate_ok: 'Validado OK',
  validate_unfit: 'Reprovado',
  full_in: 'Enviado ao FULL',
  full_out: 'Pedido FULL',
  full_return_out: 'Retorno do FULL',
  manual: 'Manual',
}

function movementColor(type) { return MOVEMENT_COLORS[type] || 'secondary' }
function movementLabel(type) { return MOVEMENT_LABELS[type] || type }

onMounted(load)
</script>

<style scoped>
.cursor-pointer { cursor: pointer; }
.gap-2 { gap: 0.5rem; }
</style>
