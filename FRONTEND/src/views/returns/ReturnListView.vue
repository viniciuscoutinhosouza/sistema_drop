<template>
  <div>
    <div class="callout callout-warning mb-3">
      <h5><i class="fas fa-info-circle"></i> Como funciona a devolução</h5>
      <p class="mb-1">1. Gerencie a devolução com o marketplace (fora do sistema)</p>
      <p class="mb-1">2. Oriente o cliente a enviar o produto para o fornecedor</p>
      <p class="mb-0">3. Registre aqui com o código de rastreio e aguarde a aprovação</p>
    </div>

    <div class="card">
      <div class="card-header d-flex justify-content-between">
        <h3 class="card-title">Minhas Devoluções</h3>
        <RouterLink to="/returns/new" class="btn btn-sm btn-primary">
          <i class="fas fa-plus mr-1"></i> Nova Devolução
        </RouterLink>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm">
          <thead>
            <tr><th>#</th><th>Pedido</th><th>Motivo</th><th>Rastreio</th><th>Status</th><th>Data</th></tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></td></tr>
            <tr v-else-if="!returns.length"><td colspan="6" class="text-center py-4 text-muted">Nenhuma devolução registrada</td></tr>
            <tr v-for="r in returns" :key="r.id">
              <td>{{ r.id }}</td>
              <td>{{ r.order_id || '—' }}</td>
              <td>{{ r.reason }}</td>
              <td>{{ r.tracking_code || '—' }}</td>
              <td>
                <span :class="`badge badge-${statusColor(r.status)}`">{{ r.status }}</span>
              </td>
              <td><small>{{ formatDateTime(r.created_at) }}</small></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatDateTime } from '@/utils/formatters'

const returns = ref([])
const loading = ref(true)

const STATUS_COLORS = { analyzing: 'warning', returned: 'success', rejected: 'danger' }
function statusColor(s) { return STATUS_COLORS[s] || 'secondary' }

onMounted(async () => {
  const { data } = await api.get('/returns')
  returns.value = data.items
  loading.value = false
})
</script>
