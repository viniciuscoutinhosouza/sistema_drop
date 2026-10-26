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
              <tr>
                <th>Valor dos Produtos</th>
                <td class="text-right">{{ formatCurrency(order.sale_amount) }}</td>
              </tr>
              <tr>
                <th>Taxa Plataforma</th>
                <td class="text-right text-danger">{{ formatCurrency(order.platform_fee) }}</td>
              </tr>
              <tr>
                <th>Frete</th>
                <td class="text-right text-danger">
                  <template v-if="isManual && order.payment_status !== 'paid' && shippingEdit.open">
                    <div class="d-flex justify-content-end" style="gap:.25rem">
                      <input
                        v-model.number="shippingEdit.value"
                        type="number"
                        min="0"
                        step="0.01"
                        class="form-control form-control-sm text-right"
                        style="width:120px"
                      />
                      <button class="btn btn-sm btn-success" :disabled="shippingEdit.saving" @click="saveShipping">
                        <i class="fas" :class="shippingEdit.saving ? 'fa-spinner fa-spin' : 'fa-check'"></i>
                      </button>
                      <button class="btn btn-sm btn-secondary" :disabled="shippingEdit.saving" @click="shippingEdit.open = false">
                        <i class="fas fa-times"></i>
                      </button>
                    </div>
                  </template>
                  <template v-else>
                    {{ formatCurrency(order.shipping_cost) }}
                    <button
                      v-if="isManual && order.payment_status !== 'paid'"
                      class="btn btn-link btn-sm p-0 ml-1"
                      title="Editar frete"
                      @click="openShippingEdit"
                    ><i class="fas fa-pen text-muted" style="font-size:.75rem"></i></button>
                  </template>
                </td>
              </tr>
              <tr class="font-weight-bold">
                <th>Valor da Venda</th>
                <td class="text-right text-success">{{ formatCurrency(saleValueTotal) }}</td>
              </tr>
              <tr><th>Custo Produto</th><td class="text-right text-danger">{{ formatCurrency(order.product_cost) }}</td></tr>
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
              v-if="isManual"
              class="btn btn-info btn-sm"
              :disabled="downloadingLabel"
              @click="downloadManualLabel"
            >
              <i class="fas" :class="downloadingLabel ? 'fa-spinner fa-spin' : 'fa-print'"></i>
              {{ downloadingLabel ? 'Gerando…' : 'Etiqueta de Envio' }}
            </button>
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
            <RouterLink
              v-if="order.invoice_id"
              :to="`/fiscal/invoices/${order.invoice_id}`"
              class="btn btn-outline-info btn-sm"
            >
              <i class="fas fa-file-invoice mr-1"></i> Ver NFe vinculada
            </RouterLink>
            <button
              v-else
              class="btn btn-outline-primary btn-sm"
              :disabled="generatingInvoice"
              @click="generateInvoice"
            >
              <i class="fas" :class="generatingInvoice ? 'fa-spinner fa-spin' : 'fa-file-invoice'"></i>
              {{ generatingInvoice ? 'Gerando...' : 'Gerar NFe a partir do Pedido' }}
            </button>
            <button
              v-if="isManual && order.status !== 'cancelled'"
              class="btn btn-outline-danger btn-sm"
              :disabled="canceling || creatingDevolution"
              @click="cancelOrder"
            >
              <i class="fas" :class="(canceling || creatingDevolution) ? 'fa-spinner fa-spin' : 'fa-ban'"></i>
              {{ canceling ? 'Cancelando…' : (creatingDevolution ? 'Devolução…' : 'Cancelar pedido') }}
            </button>
          </div>
          <div v-if="order.status === 'cancelled'" class="card-footer pt-0 border-0">
            <span class="badge badge-danger"><i class="fas fa-ban mr-1"></i>Pedido cancelado</span>
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
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in order.items" :key="item.id">
              <td>
                {{ item.sku }}
                <span v-if="item.catalog_source === 'pg'" class="badge badge-info ml-1" style="font-size:10px" title="Catálogo Geral (PG)">PG</span>
                <span v-else-if="item.catalog_source === 'cmig'" class="badge badge-warning ml-1" style="font-size:10px" title="Catálogo CMIG">CMIG</span>
              </td>
              <td>{{ item.title }}</td>
              <td>{{ item.quantity }}</td>
              <td>{{ formatCurrency(item.unit_price) }}</td>
              <td>{{ formatCurrency(item.unit_cost) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Pagamento (ASAAS) — pedido manual -->
    <div v-if="isManual" class="card mt-3">
      <div class="card-header"><h3 class="card-title"><i class="fas fa-credit-card mr-2"></i>Pagamento (ASAAS)</h3></div>
      <div class="card-body">
        <div v-if="checkout && checkout.needs_price_review && order.payment_status !== 'paid'" class="alert alert-warning">
          <i class="fas fa-exclamation-triangle mr-1"></i>
          O cliente alterou itens com desconto. Revise o preço do pedido antes de liberar o pagamento.
          <button class="btn btn-sm btn-warning ml-2" :disabled="approvingReview" @click="approvePriceReview">
            <i class="fas" :class="approvingReview ? 'fa-spinner fa-spin' : 'fa-check'"></i> Preço revisado — liberar
          </button>
        </div>
        <div v-if="order.payment_status === 'paid'" class="alert alert-success mb-0">
          <i class="fas fa-check-circle mr-1"></i> Pedido pago.
        </div>
        <template v-else>
          <div class="d-flex flex-wrap align-items-end" style="gap:.5rem">
            <div>
              <label class="small mb-1 d-block">Forma</label>
              <select v-model="billingType" class="form-control form-control-sm" style="width:160px">
                <option value="UNDEFINED">Cliente escolhe</option>
                <option value="PIX">Pix</option>
                <option value="BOLETO">Boleto</option>
                <option value="CREDIT_CARD">Cartão</option>
              </select>
            </div>
            <button class="btn btn-success btn-sm" :disabled="generatingCharge" @click="generateCharge">
              <i class="fas" :class="generatingCharge ? 'fa-spinner fa-spin' : 'fa-link'"></i>
              {{ generatingCharge ? 'Gerando…' : 'Gerar link de pagamento' }}
            </button>
          </div>
          <small class="text-muted d-block mt-1">
            Gera a cobrança na conta ASAAS principal do Galpão desta CMIG. Envie o link ao cliente;
            o pagamento é confirmado automaticamente pelo webhook.
          </small>

          <!-- Link público do cliente (ADR-0033): ver/ajustar itens + pagar sem login -->
          <div class="mt-3 pt-3 border-top">
            <label class="small mb-1 d-block"><i class="fas fa-share-nodes mr-1"></i>Link do cliente</label>
            <div v-if="checkout && checkout.has_public_link" class="input-group input-group-sm" style="max-width:520px">
              <input type="text" class="form-control" :value="checkout.public_url" readonly>
              <div class="input-group-append">
                <button class="btn btn-outline-secondary" @click="copyPublicLink" title="Copiar"><i class="fas fa-copy"></i></button>
                <a class="btn btn-outline-primary" :href="checkout.public_url" target="_blank" rel="noopener" title="Abrir"><i class="fas fa-external-link-alt"></i></a>
                <button class="btn btn-outline-warning" :disabled="generatingLink" @click="generatePublicLink(true)" title="Gerar novo (invalida o anterior)"><i class="fas fa-rotate"></i></button>
              </div>
            </div>
            <button v-else class="btn btn-outline-primary btn-sm" :disabled="generatingLink" @click="generatePublicLink(false)">
              <i class="fas" :class="generatingLink ? 'fa-spinner fa-spin' : 'fa-link'"></i> Gerar link do cliente
            </button>
            <small class="text-muted d-block mt-1">
              O cliente abre o link, confere/ajusta os itens e paga. Reduzir/remover item com desconto
              exige sua revisão de preço antes de liberar o pagamento.
            </small>
          </div>
        </template>

        <div v-if="charges.length" class="table-responsive mt-3">
          <table class="table table-sm mb-0">
            <thead><tr><th>Forma</th><th>Valor</th><th>Status</th><th>Links</th><th></th></tr></thead>
            <tbody>
              <tr v-for="c in charges" :key="c.id">
                <td>{{ billingLabel(c.billing_type) }}</td>
                <td>{{ formatCurrency(c.value) }}</td>
                <td><span class="badge" :class="chargeBadge(c.status)">{{ c.status || '—' }}</span></td>
                <td class="text-nowrap">
                  <a v-if="c.invoice_url" :href="c.invoice_url" target="_blank" rel="noopener" class="btn btn-sm btn-outline-primary">Link</a>
                  <a v-if="c.bank_slip_url" :href="c.bank_slip_url" target="_blank" rel="noopener" class="btn btn-sm btn-outline-secondary ml-1">Boleto</a>
                  <button v-if="c.pix_payload" type="button" class="btn btn-sm btn-outline-info ml-1" @click="copyPix(c.pix_payload)">Copiar Pix</button>
                </td>
                <td class="text-right text-nowrap">
                  <button type="button" class="btn btn-sm btn-outline-dark" title="Atualizar status" :disabled="refreshingId === c.id" @click="refreshCharge(c)">
                    <i class="fas" :class="refreshingId === c.id ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
                  </button>
                  <button v-if="!['CONFIRMED','RECEIVED','RECEIVED_IN_CASH','CANCELLED'].includes((c.status||'').toUpperCase())"
                          type="button" class="btn btn-sm btn-outline-danger ml-1" title="Cancelar cobrança"
                          :disabled="cancelingId === c.id" @click="cancelCharge(c)">
                    <i class="fas" :class="cancelingId === c.id ? 'fa-spinner fa-spin' : 'fa-ban'"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div v-else class="text-center py-5">
    <i class="fas fa-spinner fa-spin fa-3x text-muted"></i>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import { ORDER_STATUSES } from '@/utils/constants'
import { saveBlobResponse } from '@/utils/download'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const order = ref(null)
const paying = ref(false)
const generatingInvoice = ref(false)
const downloadingLabel = ref(false)
const canceling = ref(false)
const creatingDevolution = ref(false)
const shippingEdit = reactive({ open: false, value: 0, saving: false })

const isManual = computed(() => order.value?.platform === 'manual')

// ── Pagamento ASAAS (pedido manual) ──
const charges = ref([])
const billingType = ref('UNDEFINED')
const generatingCharge = ref(false)
const refreshingId = ref(null)

function billingLabel(t) {
  return { PIX: 'Pix', BOLETO: 'Boleto', CREDIT_CARD: 'Cartão', UNDEFINED: 'Cliente escolhe' }[t] || t || '—'
}
function chargeBadge(s) {
  const up = (s || '').toUpperCase()
  if (['CONFIRMED', 'RECEIVED', 'RECEIVED_IN_CASH'].includes(up)) return 'badge-success'
  if (['OVERDUE', 'REFUNDED', 'CHARGEBACK_REQUESTED'].includes(up)) return 'badge-danger'
  return 'badge-warning'
}
async function loadCharges() {
  if (!isManual.value) return
  try {
    const { data } = await api.get(`/manual-orders/${order.value.id}/charges`)
    charges.value = Array.isArray(data) ? data : []
  } catch { /* silencioso */ }
}
async function generateCharge() {
  generatingCharge.value = true
  try {
    await api.post(`/manual-orders/${order.value.id}/create-charge`, { billing_type: billingType.value })
    toast.success('Cobrança gerada no ASAAS.')
    await loadCharges()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao gerar a cobrança')
  } finally {
    generatingCharge.value = false
  }
}
async function refreshCharge(c) {
  refreshingId.value = c.id
  try {
    const { data } = await api.post(`/manual-orders/${order.value.id}/charges/${c.id}/refresh`)
    const i = charges.value.findIndex(x => x.id === c.id)
    if (i >= 0) charges.value[i] = data
    if (['CONFIRMED', 'RECEIVED', 'RECEIVED_IN_CASH'].includes((data.status || '').toUpperCase())) {
      order.value.payment_status = 'paid'
    }
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao atualizar a cobrança')
  } finally {
    refreshingId.value = null
  }
}
function copyPix(payload) {
  try {
    navigator.clipboard.writeText(payload)
    toast.success('Pix copia-e-cola copiado.')
  } catch {
    toast.error('Não foi possível copiar.')
  }
}

// ── Checkout público (link do cliente) + re-análise de desconto (ADR-0033) ──
const checkout = ref(null)
const generatingLink = ref(false)
const approvingReview = ref(false)
const cancelingId = ref(null)

async function loadCheckoutInfo() {
  if (!isManual.value) return
  try {
    const { data } = await api.get(`/manual-orders/${order.value.id}/checkout-info`)
    checkout.value = data
  } catch { /* silencioso */ }
}
async function generatePublicLink(regenerate = false) {
  generatingLink.value = true
  try {
    const { data } = await api.post(`/manual-orders/${order.value.id}/public-link`, { regenerate })
    checkout.value = { ...(checkout.value || {}), has_public_link: true, public_url: data.public_url }
    try { await navigator.clipboard.writeText(data.public_url) } catch { /* ignore */ }
    toast.success(regenerate ? 'Novo link gerado e copiado.' : 'Link gerado e copiado.')
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao gerar o link')
  } finally {
    generatingLink.value = false
  }
}
function copyPublicLink() {
  if (!checkout.value?.public_url) return
  try {
    navigator.clipboard.writeText(checkout.value.public_url)
    toast.success('Link copiado.')
  } catch {
    toast.error('Não foi possível copiar.')
  }
}
async function approvePriceReview() {
  approvingReview.value = true
  try {
    await api.post(`/manual-orders/${order.value.id}/price-review/approve`)
    toast.success('Preço revisado. Pagamento liberado.')
    await loadOrder()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao aprovar')
  } finally {
    approvingReview.value = false
  }
}
async function cancelCharge(c) {
  if (!confirm('Cancelar esta cobrança no ASAAS?')) return
  cancelingId.value = c.id
  try {
    const { data } = await api.post(`/manual-orders/${order.value.id}/charges/${c.id}/cancel`)
    const i = charges.value.findIndex(x => x.id === c.id)
    if (i >= 0) charges.value[i] = data
    toast.success('Cobrança cancelada.')
    await loadCharges()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao cancelar')
  } finally {
    cancelingId.value = null
  }
}

// Valor da Venda = produtos + taxa plataforma + frete (o que o cliente paga)
const saleValueTotal = computed(() => {
  const o = order.value
  if (!o) return 0
  return (Number(o.sale_amount) || 0) + (Number(o.platform_fee) || 0) + (Number(o.shipping_cost) || 0)
})

function openShippingEdit() {
  shippingEdit.value = Number(order.value?.shipping_cost) || 0
  shippingEdit.open = true
}

async function saveShipping() {
  if (!order.value) return
  const v = Number(shippingEdit.value)
  if (!Number.isFinite(v) || v < 0) {
    toast.error('Frete deve ser maior ou igual a zero')
    return
  }
  shippingEdit.saving = true
  try {
    const { data } = await api.put(`/orders/${order.value.id}/shipping-cost`, { shipping_cost: v })
    order.value.shipping_cost = data.shipping_cost
    shippingEdit.open = false
    toast.success('Frete atualizado')
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Falha ao salvar frete')
  } finally {
    shippingEdit.saving = false
  }
}

async function downloadManualLabel() {
  if (!order.value || downloadingLabel.value) return
  downloadingLabel.value = true
  try {
    // Baixa um ZIP com o PDF e o ZPL (sem abrir o PDF).
    const resp = await api.get(`/orders/${order.value.id}/label.zip`, { responseType: 'blob' })
    saveBlobResponse(resp, `Etiqueta-${order.value.platform_order_id || order.value.id}.zip`, 'application/zip')
  } catch (e) {
    toast.error(e?.response?.data?.detail || 'Falha ao gerar etiqueta')
  } finally {
    downloadingLabel.value = false
  }
}

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
  if (isManual.value) {
    await loadCharges()
    await loadCheckoutInfo()
  }
}

async function payOrder() {
  if (!confirm(`Pagar pedido #${order.value.id}? O valor será debitado do seu saldo.`)) return
  paying.value = true
  try {
    await api.post(`/orders/${order.value.id}/pay`)
    await loadOrder()
    toast.success('Pedido pago.')
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao pagar')
  } finally {
    paying.value = false
  }
}

async function updateStatus(newStatus) {
  await api.put(`/orders/${order.value.id}/status`, { status: newStatus })
  await loadOrder()
}

async function generateInvoice() {
  if (!confirm(`Gerar uma NFe de saída a partir deste pedido? Será criado um rascunho que você poderá revisar e transmitir.`)) return
  generatingInvoice.value = true
  try {
    const { data } = await api.post(`/invoices/from-order/${order.value.id}`)
    if (data.warnings?.length) {
      toast.warning(data.warnings.join(' '))
    } else {
      toast.success(`NFe rascunho criada (Invoice #${data.invoice_id})`)
    }
    router.push(`/fiscal/invoices/${data.invoice_id}/edit`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao gerar NFe')
  } finally {
    generatingInvoice.value = false
  }
}

// ── Cancelar pedido / NF-e de devolução (ADR-0037) ──
async function cancelOrder() {
  if (!confirm(`Cancelar o pedido #${order.value.id}? Libera o estoque reservado e cancela cobranças pendentes.`)) return
  canceling.value = true
  try {
    const { data } = await api.post(`/orders/${order.value.id}/cancel`)
    if (data.credit_created) {
      toast.success(`Pedido cancelado. Crédito de ${formatCurrency(data.credit_created.amount)} gerado para o cliente.`)
    } else {
      toast.success('Pedido cancelado.')
    }
    await loadOrder()
  } catch (err) {
    const detail = err.response?.data?.detail
    if (detail && typeof detail === 'object' && detail.code === 'requires_devolution') {
      canceling.value = false
      if (confirm(`${detail.message}\n\nDeseja emitir a NF-e de Devolução agora?`)) {
        await createDevolutionNfe()
      }
      return
    }
    toast.error((typeof detail === 'string' ? detail : null) || 'Erro ao cancelar o pedido')
  } finally {
    canceling.value = false
  }
}

async function createDevolutionNfe() {
  creatingDevolution.value = true
  try {
    const { data } = await api.post(`/orders/${order.value.id}/devolution-nfe`)
    if (data.already) {
      toast.info('Já existe uma NF-e de devolução para este pedido.')
    } else {
      let msg = `NF-e de devolução criada (rascunho #${data.invoice_id}). Revise e transmita.`
      if (data.credit_created) msg += ` Crédito de ${formatCurrency(data.credit_created.amount)} gerado ao cliente.`
      toast.success(msg)
    }
    router.push(`/fiscal/invoices/${data.invoice_id}/edit`)
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao criar a NF-e de devolução')
  } finally {
    creatingDevolution.value = false
  }
}

onMounted(loadOrder)
</script>
