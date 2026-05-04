<template>
  <div class="d-flex align-items-center" style="gap:.3rem">
    <!-- Passos internos -->
    <div
      v-for="step in steps"
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

const props = defineProps({
  status:        { type: String, required: true },
  order:         { type: Object, default: null },
  paymentStatus: { type: String, default: '' },
  labelUrl:      { type: String, default: '' },
  canPay:        { type: Boolean, default: false },
})
const emit = defineEmits(['click:delivery', 'click:pay', 'click:label'])

const steps = [
  { key: 'downloaded',      label: 'Pedido Baixado',      icon: 'fas fa-download' },
  { key: 'paid',            label: 'Pedido Pago',         icon: 'fas fa-dollar-sign' },
  { key: 'label_generated', label: 'Etiqueta Gerada',     icon: 'fas fa-tag' },
  { key: 'label_printed',   label: 'Etiqueta Impressa',   icon: 'fas fa-print' },
  { key: 'separated',       label: 'Pedido Separado',     icon: 'fas fa-box-open' },
  { key: 'shipped',         label: 'Coletado p/ Entrega', icon: 'fas fa-truck' },
]
const stepOrder = steps.map(s => s.key)

function isPast(key) {
  const cur = stepOrder.indexOf(props.status)
  const idx = stepOrder.indexOf(key)
  return idx !== -1 && cur !== -1 && idx < cur
}
function isCurrent(key) { return props.status === key }

function stepClass(key) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) {
    return ['bg-warning', 'text-dark']
  }
  if (key === 'label_generated') {
    return props.labelUrl ? ['bg-success', 'text-white'] : ['bg-secondary', 'text-white']
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
    return props.labelUrl ? 'Ver etiqueta' : 'Etiqueta não gerada'
  }
  return defaultLabel
}

function stepClickable(key) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) return true
  if (key === 'label_generated' && props.labelUrl) return true
  return false
}

function onStepClick(key) {
  if (key === 'paid' && props.paymentStatus === 'pending' && props.canPay) {
    emit('click:pay')
    return
  }
  if (key === 'label_generated' && props.labelUrl) {
    emit('click:label')
  }
}

// ─── Ícone de entrega ─────────────────────────────────────────────────────────
function fmt(d) {
  if (!d) return null
  return new Date(d + 'T12:00:00').toLocaleDateString('pt-BR')
}

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
