<template>
  <div
    v-if="show"
    class="modal fade show d-block"
    tabindex="-1"
    style="background:rgba(0,0,0,.5)"
    @click.self="$emit('close')"
  >
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-truck mr-2"></i> Informações da Entrega
          </h5>
          <button type="button" class="close" @click="$emit('close')">
            <span>&times;</span>
          </button>
        </div>
        <div class="modal-body">
          <!-- Cabeçalho de rastreio -->
          <div class="row mb-3">
            <div class="col-4">
              <small class="text-muted d-block">ID do Envio</small>
              <strong>{{ order.tracking_code || '—' }}</strong>
            </div>
            <div class="col-4">
              <small class="text-muted d-block">Tipo</small>
              <span :class="shippingTypeBadge">{{ shippingTypeLabel }}</span>
            </div>
            <div class="col-4">
              <small class="text-muted d-block">Status da Plataforma</small>
              <span class="badge badge-info">{{ order.platform_status || '—' }}</span>
            </div>
          </div>

          <hr />

          <!-- Transportadora e rastreio -->
          <div class="row mb-3">
            <div class="col-6">
              <small class="text-muted d-block">Transportadora</small>
              <strong>{{ shippingCarrier }}</strong>
            </div>
            <div class="col-6">
              <small class="text-muted d-block">Código de Rastreamento</small>
              <template v-if="order.tracking_url">
                <a :href="order.tracking_url" target="_blank" rel="noopener">
                  {{ order.tracking_code || 'Ver rastreio' }}
                  <i class="fas fa-external-link-alt ml-1 fa-xs"></i>
                </a>
              </template>
              <span v-else>{{ order.tracking_code || '—' }}</span>
            </div>
          </div>

          <!-- Estimativa de entrega -->
          <div v-if="order.estimated_delivery_date" class="row mb-3">
            <div class="col-6">
              <small class="text-muted d-block">Entrega Prevista</small>
              <strong :class="isDeliveryUrgent ? 'text-danger' : ''">
                {{ formatDate(order.estimated_delivery_date) }}
                <span v-if="isDeliveryUrgent" class="badge badge-danger ml-1">Urgente</span>
              </strong>
            </div>
          </div>

          <hr />

          <!-- Informações do comprador -->
          <div class="row mb-3">
            <div class="col-12 mb-2">
              <strong>Informações do Comprador</strong>
            </div>
            <div class="col-6">
              <small class="text-muted d-block">Nome</small>
              <span>{{ order.buyer_name || '—' }}</span>
            </div>
            <div class="col-6">
              <small class="text-muted d-block">CPF / CNPJ</small>
              <span>{{ formatDocument(order.buyer_document) || '—' }}</span>
            </div>
          </div>

          <hr />

          <!-- Endereço do destinatário -->
          <div class="row">
            <div class="col-12 mb-2">
              <strong>Endereço do Destinatário</strong>
            </div>
            <div class="col-12">
              <address class="mb-0" style="line-height:1.8">
                <span v-if="addressLine1">{{ addressLine1 }}<br /></span>
                <span v-if="addressLine2">{{ addressLine2 }}<br /></span>
                <span v-if="addressCity">{{ addressCity }}<span v-if="addressState"> – {{ addressState }}</span><br /></span>
                <span v-if="addressZip">CEP: {{ addressZip }}</span>
              </address>
              <span v-if="!addressLine1 && !addressCity" class="text-muted">Endereço não disponível</span>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-default" @click="$emit('close')">Fechar</button>
          <a
            v-if="order.tracking_url"
            :href="order.tracking_url"
            target="_blank"
            rel="noopener"
            class="btn btn-info"
          >
            <i class="fas fa-search-location mr-1"></i> Rastrear Envio
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatDate, formatDocument } from '@/utils/formatters'

const props = defineProps({
  show: { type: Boolean, default: false },
  order: { type: Object, default: () => ({}) },
})

defineEmits(['close'])

// ML stores receiver_address as nested object; older orders may use flat structure
const addr = computed(() => {
  const s = props.order?.shipping_address || {}
  return s.receiver_address || s
})

const addressLine1 = computed(() => {
  const a = addr.value
  // ML receiver_address uses address_line (full) or street_name + street_number
  const street = a.address_line || a.street_name || a.address || a.full_address || ''
  const num = street.includes(a.street_number) ? '' : (a.street_number || a.number || '')
  const comp = a.complement || a.comment || ''
  return [street, num, comp].filter(Boolean).join(', ')
})

const addressLine2 = computed(() => {
  const n = addr.value.neighborhood
  return (n && typeof n === 'object' ? n.name : n) || addr.value.district || ''
})
const addressCity = computed(() => addr.value.city?.name || addr.value.city || '')
const addressState = computed(() => addr.value.state?.name || addr.value.state || '')
const addressZip = computed(() => {
  const z = addr.value.zip_code || addr.value.zipcode || addr.value.cep || ''
  const d = String(z).replace(/\D/g, '')
  return d.length === 8 ? `${d.slice(0, 5)}-${d.slice(5)}` : z
})

// Maps ML logistic_type values to human-readable labels
const shippingCarrier = computed(() => {
  const m = props.order?.shipping_method || ''
  if (m === 'fulfillment') return 'Mercado Envios Full'
  if (m === 'self_service') return 'Mercado Flex'
  if (m === 'xd_drop_off' || m === 'cross_docking' || m.includes('me2')) return 'Mercado Envios'
  return m || '—'
})

const shippingTypeLabel = computed(() => {
  const m = props.order?.shipping_method || ''
  if (m === 'fulfillment') return 'FULL'
  if (m === 'self_service') return 'FLEX'
  if (m === 'xd_drop_off' || m === 'cross_docking') return 'ME2'
  return 'Padrão'
})

const shippingTypeBadge = computed(() => {
  const m = props.order?.shipping_method || ''
  if (m === 'fulfillment') return 'badge badge-warning'
  if (m === 'self_service') return 'badge badge-info'
  return 'badge badge-secondary'
})

const isDeliveryUrgent = computed(() => {
  if (!props.order?.estimated_delivery_date) return false
  const diff = (new Date(props.order.estimated_delivery_date) - new Date()) / (1000 * 60 * 60 * 24)
  return diff <= 2
})
</script>
