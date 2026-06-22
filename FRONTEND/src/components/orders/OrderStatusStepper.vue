<template>
  <div class="d-flex align-items-center" style="gap:.3rem">
    <!-- Passos internos -->
    <div
      v-for="step in visibleSteps"
      :key="step.key"
      class="step-circle"
      :class="stepClass(step.key)"
      :title="stepTooltip(step.key, step.label)"
      :style="stepClickable(step.key) ? 'cursor:pointer' : ''"
      @click="onStepClick(step.key)"
    >
      <i :class="step.icon"></i>
    </div>

    <!-- Separador visual -->
    <span class="text-muted" style="font-size:.65rem;opacity:.4">|</span>

    <!-- Ícone de entrega (clicável) -->
    <div
      class="step-circle step-delivery"
      :class="deliveryClass"
      :title="deliveryTooltip"
      style="cursor:pointer"
      @click.stop="$emit('click:delivery')"
    >
      <i :class="deliveryIcon"></i>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDate as fmtBrDate } from '@/utils/formatters'

const props = defineProps({
  status:        { type: String, required: true },
  order:         { type: Object, default: null },
  paymentStatus: { type: String, default: '' },
  labelUrl:      { type: String, default: '' },
  canPay:        { type: Boolean, default: false },
  canPrintLabel: { type: Boolean, default: false }, // true para manual ou ML com shipment
  hasNfe:        { type: Boolean, default: false }, // true quando ha NFe associada
  isFull:        { type: Boolean, default: false }, // Full ML: oculta etapas geridas pelo ML
})
const emit = defineEmits(['click:delivery', 'click:pay', 'click:label', 'click:nfe', 'click:separated', 'click:shipped'])

const steps = [
  { key: 'downloaded',      label: 'Pedido Baixado',      icon: 'fas fa-download' },
  { key: 'paid',            label: 'Pedido Pago',         icon: 'fas fa-dollar-sign' },
  { key: 'label_generated', label: 'Etiqueta',            icon: 'fas fa-tag' },
  { key: 'nfe',             label: 'NF-e',                icon: 'fas fa-file-invoice-dollar' },
  { key: 'separated',       label: 'Pedido Separado',     icon: 'fas fa-box-open' },
  { key: 'shipped',         label: 'Coletado p/ Entrega', icon: 'fas fa-truck' },
]
// Em pedidos Full o ML gerencia pagamento, etiqueta, NF-e e coleta — o vendedor
// não age nessas etapas, então exibimos só "Pedido Baixado" + o ícone de entrega.
const HIDDEN_WHEN_FULL = ['paid', 'label_generated', 'nfe', 'separated', 'shipped']
const visibleSteps = computed(() =>
  props.isFull ? steps.filter((s) => !HIDDEN_WHEN_FULL.includes(s.key)) : steps
)

// Ordem para isPast/isCurrent (mantém pipeline de status, NFe e label sao acoes paralelas)
const stepOrderForStatus = ['downloaded', 'paid', 'label_generated', 'label_printed', 'separated', 'shipped']

function isPast(key) {
  // 'nfe' nao faz parte da progressao linear; ativo so quando hasNfe
  if (key === 'nfe') return false
  const cur = stepOrderForStatus.indexOf(props.status)
  const idx = stepOrderForStatus.indexOf(key)
  return idx !== -1 && cur !== -1 && idx < cur
}
function isCurrent(key) {
  if (key === 'nfe') return false
  if (key === 'label_generated' && props.status === 'label_printed') return true
  return props.status === key
}

function stepClass(key) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) {
    return ['bg-warning', 'text-dark']
  }
  if (key === 'label_generated') {
    if (props.status === 'label_printed' || props.labelUrl) {
      return ['bg-success', 'text-white', 'step-actionable']
    }
    if (props.canPrintLabel) return ['bg-info', 'text-white', 'step-actionable']
    return ['bg-secondary', 'text-white']
  }
  if (key === 'nfe') {
    return props.hasNfe
      ? ['bg-success', 'text-white', 'step-actionable']
      : ['bg-secondary', 'text-white', 'step-actionable']
  }
  const active = isPast(key) || isCurrent(key)
  return [
    active ? 'bg-success' : 'bg-secondary',
    'text-white',
    ...(isCurrent(key) ? ['step-current'] : []),
  ]
}

function stepTooltip(key, defaultLabel) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) {
    return 'Não Pago — clique para pagar'
  }
  if (key === 'label_generated') {
    if (props.status === 'label_printed') return 'Etiqueta impressa — clique para reimprimir'
    if (props.canPrintLabel) return 'Clique para imprimir etiqueta'
    return 'Etiqueta indisponível para este pedido'
  }
  if (key === 'nfe') {
    return props.hasNfe ? 'NF-e autorizada — clique para detalhes' : 'NF-e — clique para emitir/consultar'
  }
  if (key === 'separated' && reachedSeparated.value) return 'Pedido separado — clique para detalhes'
  if (key === 'shipped' && reachedShipped.value) return 'Pedido coletado — clique para detalhes'
  return defaultLabel
}

// Etapas alcançadas (para liberar o clique de detalhes)
const reachedSeparated = computed(() => isPast('separated') || isCurrent('separated'))
const reachedShipped = computed(() =>
  isCurrent('shipped') || !!(props.order?.dispatched_at || props.order?.shipped_at)
)

function stepClickable(key) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) return true
  if (key === 'label_generated' && props.canPrintLabel) return true
  if (key === 'nfe') return true
  if (key === 'separated') return reachedSeparated.value
  if (key === 'shipped') return reachedShipped.value
  return false
}

function onStepClick(key) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) {
    emit('click:pay')
    return
  }
  if (key === 'label_generated' && props.canPrintLabel) {
    emit('click:label')
    return
  }
  if (key === 'nfe') {
    emit('click:nfe')
    return
  }
  if (key === 'separated' && reachedSeparated.value) {
    emit('click:separated')
    return
  }
  if (key === 'shipped' && reachedShipped.value) {
    emit('click:shipped')
  }
}

// ─── Ícone de entrega ─────────────────────────────────────────────────────────
function fmt(d) { return d ? fmtBrDate(d) : null }   // fonte única (horário do Brasil)

const shipStatus = computed(() => props.order?.shipment_status || '')

const deliveryIcon = computed(() => {
  const s = shipStatus.value
  if (s === 'delivered')     return 'fas fa-home'
  if (s === 'not_delivered') return 'fas fa-exclamation-circle'
  if (s === 'shipped')       return 'fas fa-shipping-fast'
  if (s === 'ready_to_ship') return 'fas fa-dolly'
  return 'fas fa-map-marker-alt'
})

const deliveryClass = computed(() => {
  const s = shipStatus.value
  if (s === 'delivered')     return 'bg-success text-white'
  if (s === 'not_delivered') return 'bg-danger text-white'
  if (s === 'shipped')       return 'bg-primary text-white'
  if (s === 'ready_to_ship') return 'bg-info text-white'
  return 'bg-secondary text-white'
})

const deliveryTooltip = computed(() => {
  const o = props.order
  if (!o) return 'Ver detalhes da entrega'
  const s = shipStatus.value
  const dateDelivery = fmt(o.estimated_delivery_date || o.estimated_delivery_final)
  const dateHandling = fmt(o.estimated_handling_limit)
  if (s === 'delivered')     return 'Pedido entregue — clique para detalhes'
  if (s === 'not_delivered') return 'Entrega não realizada — clique para detalhes'
  if (s === 'shipped')       return dateDelivery ? `Chegada prevista: ${dateDelivery}` : 'Em trânsito — clique para detalhes'
  if (s === 'ready_to_ship') return dateHandling  ? `Enviar até: ${dateHandling}`       : 'Pronto para envio — clique para detalhes'
  if (s === 'handling')      return dateHandling  ? `Limite de envio: ${dateHandling}`  : 'Em preparação — clique para detalhes'
  return dateDelivery ? `Entrega prevista: ${dateDelivery}` : 'Ver detalhes da entrega'
})
</script>

<style scoped>
.step-circle {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}
.step-current {
  box-shadow: 0 0 0 3px rgba(40,167,69,.35);
}
.step-delivery:hover,
.step-circle[style*="cursor:pointer"]:hover {
  filter: brightness(1.15);
  transform: scale(1.1);
  transition: transform .15s;
}
</style>
