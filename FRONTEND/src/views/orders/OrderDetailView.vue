<template>
  <div v-if="order">
    <!-- Status Stepper -->
    <div class="card mb-3">
      <div class="card-body">
        <div class="d-flex justify-content-between align-items-center flex-wrap">
          <div
            v-for="(step, idx) in steps"
            :key="step.key"
            class="text-center mx-2 mb-2"
          >
            <div
              :class="[
                'rounded-circle d-inline-flex align-items-center justify-content-center',
                stepDone(step.key) ? 'bg-success text-white' : 'bg-light text-muted',
              ]"
              style="width:40px;height:40px;font-size:18px"
            >
              <i :class="stepDone(step.key) ? 'fas fa-check' : step.icon"></i>
            </div>
            <div class="small mt-1" :class="stepDone(step.key) ? 'text-success font-weight-bold' : 'text-muted'">
              {{ step.label }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="row">
      <!-- Order Info -->
      <div class="col-md-6">
        <div class="card">
          <div class="card-header"><h3 class="card-title">Dados do Pedido</h3></div>
          <div class="card-body">
            <table class="table table-sm table-borderless">
              <tr><th>ID Interno</th><td>{{ order.id }}</td></tr>
              <tr><th>Canal</th><td><span class="badge badge-primary">{{ order.platform }}</span></td></tr>
              <tr><th>Ref. Marketplace</th><td>{{ order.platform_order_id }}</td></tr>
              <tr><th>Status</th><td><span :class="`badge badge-${statusColor(order.status)}`">{{ statusLabel(order.status) }}</span></td></tr>
              <tr><th>Pagamento</th><td><span :class="`badge badge-${order.payment_status === 'paid' ? 'success' : 'warning'}`">{{ order.payment_status }}</span></td></tr>
              <tr><th>Rastreio</th><td>{{ order.tracking_code || '—' }}</td></tr>
              <tr><th>Data</th><td>{{ formatDateTime(order.created_at) }}</td></tr>
            </table>
          </div>
        </div>
      </div>

      <!-- Financial Summary -->
      <div class="col-md-6">
        <div class="card">
          <div class="card-header"><h3 class="card-title">Resumo Financeiro</h3></div>
          <div class="card-body">
            <table class="table table-sm">
              <tr><th>Valor de Venda</th><td class="text-right">{{ formatCurrency(order.sale_amount) }}</td></tr>
              <tr><th>Custo Produto</th><td class="text-right text-danger">{{ formatCurrency(order.product_cost) }}</td></tr>
              <tr><th>Taxa Plataforma</th><td class="text-right text-danger">{{ formatCurrency(order.platform_fee) }}</td></tr>
              <tr><th>Frete</th><td class="text-right text-danger">{{ formatCurrency(order.shipping_cost) }}</td></tr>
              <tr class="font-weight-bold">
                <th>Total Débito</th>
                <td class="text-right text-danger">{{ formatCurrency(order.total_debit) }}</td>
              </tr>
            </table>
          </div>
          <!-- Action buttons -->
          <div class="card-footer d-flex gap-2 flex-wrap">
            <button
              v-if="order.payment_status === 'pending' && order.status !== 'cancelled'"
              class="btn btn-success btn-sm"
              :disabled="paying"
              @click="payOrder"
            >
              <i class="fas fa-dollar-sign mr-1"></i>
              {{ paying ? 'Pagando...' : 'Pagar Pedido' }}
            </button>
            <a
              v-if="order.label_url"
              :href="order.label_url"
              target="_blank"
              class="btn btn-info btn-sm"
            >
              <i class="fas fa-print mr-1"></i> Ver Etiqueta
            </a>
            <button
              v-if="order.status === 'label_generated'"
              class="btn btn-warning btn-sm"
              @click="updateStatus('label_printed')"
            >
              Marcar Impressa
            </button>
            <button
              v-if="order.status === 'label_printed'"
              class="btn btn-secondary btn-sm"
              @click="updateStatus('separated')"
            >
              Marcar Separado
            </button>
            <button
              v-if="order.status === 'separated'"
              class="btn btn-primary btn-sm"
              @click="updateStatus('shipped')"
            >
              Marcar Enviado
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Order Items -->
    <div class="card mt-3">
      <div class="card-header"><h3 class="card-title">Itens do Pedido</h3></div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Produto</th>
              <th>Qtd</th>
              <th>Preço Unit.</th>
              <th>Custo Unit.</th>
              <th>Vínculo</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in order.items" :key="item.id">
              <td>{{ item.sku }}</td>
              <td>{{ item.title }}</td>
              <td>{{ item.quantity }}</td>
              <td>{{ formatCurrency(item.unit_price) }}</td>
              <td>{{ formatCurrency(item.unit_cost) }}</td>
              <td>
                <span v-if="item.dropshipper_product_id" class="badge badge-success">Vinculado</span>
                <span v-else class="badge badge-danger">Sem vínculo</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div v-else class="text-center py-5">
    <i class="fas fa-spinner fa-spin fa-3x text-muted"></i>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import { ORDER_STATUSES } from '@/utils/constants'

const route = useRoute()
const router = useRouter()
const order = ref(null)
const paying = ref(false)

const steps = [
  { key: 'downloaded',      label: 'Baixou',     icon: 'fas fa-download' },
  { key: 'paid',            label: 'Pago',       icon: 'fas fa-dollar-sign' },
  { key: 'label_generated', label: 'Etiqueta',   icon: 'fas fa-tag' },
  { key: 'label_printed',   label: 'Impressa',   icon: 'fas fa-print' },
  { key: 'separated',       label: 'Separado',   icon: 'fas fa-boxes' },
  { key: 'shipped',         label: 'Enviado',    icon: 'fas fa-truck' },
]

const STATUS_ORDER = steps.map(s => s.key)

function stepDone(key) {
  if (!order.value) return false
  const currentIdx = STATUS_ORDER.indexOf(order.value.status)
  const stepIdx = STATUS_ORDER.indexOf(key)
  return stepIdx <= currentIdx
}

function statusLabel(key) {
  return ORDER_STATUSES.find(s => s.key === key)?.label || key
}
function statusColor(key) {
  return ORDER_STATUSES.find(s => s.key === key)?.color || 'secondary'
}

async function loadOrder() {
  const { data } = await api.get(`/orders/${route.params.id}`)
  order.value = data
}

async function payOrder() {
  if (!confirm(`Pagar pedido #${order.value.id}? O valor será debitado do seu saldo.`)) return
  paying.value = true
  try {
    const { data } = await api.post(`/orders/${order.value.id}/pay`)
    await loadOrder()
  } catch (err) {
    alert(err.response?.data?.detail || 'Erro ao pagar')
  } finally {
    paying.value = false
  }
}

async function updateStatus(newStatus) {
  await api.put(`/orders/${order.value.id}/status`, { status: newStatus })
  await loadOrder()
}

onMounted(loadOrder)
</script>
