<template>
  <div>
    <div class="callout callout-info mb-3">
      <h5><i class="fas fa-info-circle"></i> Aguardando Retorno Físico</h5>
      <p class="mb-0">
        Pedidos cancelados <strong>após o despacho</strong>. O produto ainda está em trânsito de volta ao galpão.
        Ao confirmar o recebimento, o estoque físico é restaurado automaticamente.
      </p>
    </div>

    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h3 class="card-title mb-0">
          <i class="fas fa-undo-alt mr-2 text-info"></i> Pedidos Aguardando Retorno
        </h3>
        <button class="btn btn-sm btn-outline-secondary" @click="load">
          <i class="fas fa-sync-alt"></i>
        </button>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead class="thead-light">
            <tr>
              <th>#</th>
              <th>Pedido ML</th>
              <th>Comprador</th>
              <th>Plataforma</th>
              <th>Cancelado em</th>
              <th>Ação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="6" class="text-center py-4">
                <i class="fas fa-spinner fa-spin"></i>
              </td>
            </tr>
            <tr v-else-if="!orders.length">
              <td colspan="6" class="text-center py-4 text-muted">
                <i class="fas fa-check-circle text-success mr-2"></i>
                Nenhum pedido aguardando retorno físico
              </td>
            </tr>
            <tr v-for="o in orders" :key="o.id">
              <td>{{ o.id }}</td>
              <td>
                <strong>{{ o.platform_order_id || '—' }}</strong>
              </td>
              <td>{{ o.buyer_name || '—' }}</td>
              <td>
                <span class="badge badge-secondary">{{ o.platform || '—' }}</span>
              </td>
              <td><small class="text-muted">{{ formatDateTime(o.updated_at) }}</small></td>
              <td>
                <button
                  class="btn btn-sm btn-success"
                  @click="confirmReturn(o)"
                  :disabled="confirming === o.id"
                >
                  <i class="fas fa-box-open mr-1"></i>
                  {{ confirming === o.id ? 'Confirmando...' : 'Confirmar Recebimento' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-footer" v-if="total > pageSize">
        <div class="d-flex justify-content-between align-items-center">
          <small class="text-muted">{{ total }} pedido(s) aguardando retorno</small>
          <div class="d-flex gap-2">
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/formatters'

const orders = ref([])
const loading = ref(true)
const confirming = ref(null)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const toast = useToast()

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/orders/awaiting-return', {
      params: { page: page.value, page_size: pageSize.value },
    })
    orders.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function changePage(p) {
  page.value = p
  await load()
}

async function confirmReturn(order) {
  confirming.value = order.id
  try {
    await api.post(`/orders/${order.id}/confirm-return`, {})
    toast.success('Retorno confirmado! Estoque físico restaurado.')
    orders.value = orders.value.filter(o => o.id !== order.id)
    total.value = Math.max(0, total.value - 1)
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao confirmar retorno.')
  } finally {
    confirming.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.gap-2 { gap: 0.5rem; }
</style>
