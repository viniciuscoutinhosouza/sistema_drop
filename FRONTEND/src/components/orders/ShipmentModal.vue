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
            <i class="fas fa-truck mr-2"></i>
            Envio — Pedido #{{ order?.platform_order_id || order?.id }}
          </h5>
          <button type="button" class="close" @click="$emit('close')">
            <span>&times;</span>
          </button>
        </div>

        <div class="modal-body">
          <!-- Alerta de fraude -->
          <div v-if="hasFraud" class="alert alert-danger d-flex align-items-center mb-3">
            <i class="fas fa-exclamation-triangle fa-2x mr-3"></i>
            <div>
              <strong>Risco de Fraude Detectado!</strong><br>
              O Mercado Livre sinalizou este pedido como suspeito. <strong>NÃO envie a mercadoria</strong> — cancele o pedido imediatamente.
            </div>
          </div>

          <!-- Comprador -->
          <div class="card card-body bg-light p-2 mb-3">
            <div class="d-flex align-items-start" style="gap:.75rem">
              <i class="fas fa-user-circle fa-2x text-muted mt-1"></i>
              <div>
                <strong>{{ order?.buyer_name || '—' }}</strong>
                <div v-if="addressLine" class="text-muted small mt-1">
                  <i class="fas fa-map-marker-alt mr-1"></i>{{ addressLine }}
                </div>
                <div v-if="addressZip" class="text-muted small">
                  <i class="fas fa-envelope mr-1"></i>CEP: {{ addressZip }}
                </div>
              </div>
            </div>
          </div>

          <!-- Loading do tracking -->
          <div v-if="loadingTracking" class="text-center py-3 text-muted">
            <i class="fas fa-spinner fa-spin mr-2"></i>Carregando rastreamento...
          </div>

          <!-- Erro -->
          <div v-else-if="trackingError" class="alert alert-warning small mb-3">
            <i class="fas fa-info-circle mr-1"></i>{{ trackingError }}
          </div>

          <!-- Linha do tempo (vertical, completa) -->
          <div v-else-if="timeline.length" class="mb-3">
            <small class="text-muted text-uppercase font-weight-bold d-block mb-3" style="font-size:.7rem">
              <i class="fas fa-stream mr-1"></i>Estágios do Envio
            </small>
            <div class="shipment-timeline">
              <div
                v-for="(ev, idx) in timeline"
                :key="`${ev.code}-${idx}`"
                class="timeline-row"
                :class="{ 'is-future': ev.future, 'is-active': ev.active }"
              >
                <div class="timeline-marker">
                  <i :class="['fas', ev.icon]"></i>
                </div>
                <div class="timeline-content">
                  <div class="d-flex align-items-center justify-content-between flex-wrap" style="gap:.4rem">
                    <strong :class="ev.future ? 'text-muted' : ''">{{ ev.label }}</strong>
                    <span class="badge" :class="ev.future ? 'badge-light text-muted' : 'badge-secondary'" style="font-size:.72rem">
                      {{ formatDateTime(ev.date) }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Timeline básica (fallback quando ML não retorna histórico) -->
          <div v-else class="mb-3">
            <small class="text-muted text-uppercase font-weight-bold d-block mb-2" style="font-size:.7rem">Linha do Tempo</small>
            <div class="d-flex flex-wrap" style="gap:.5rem">
              <div class="timeline-item">
                <span class="badge badge-secondary"><i class="fas fa-download mr-1"></i>Venda</span>
                <div class="small text-muted mt-1">{{ formatDate(order?.created_at) }}</div>
              </div>
              <div v-if="order?.paid_at" class="timeline-item">
                <span class="badge badge-info"><i class="fas fa-dollar-sign mr-1"></i>Pago</span>
                <div class="small text-muted mt-1">{{ formatDate(order?.paid_at) }}</div>
              </div>
              <div v-if="order?.shipped_at" class="timeline-item">
                <span class="badge badge-primary"><i class="fas fa-truck mr-1"></i>Enviado</span>
                <div class="small text-muted mt-1">{{ formatDate(order?.shipped_at) }}</div>
              </div>
            </div>
          </div>

          <!-- Datas estimadas (do ML) -->
          <div v-if="estimated && hasAnyEstimated" class="border-top pt-3 mb-3">
            <small class="text-muted text-uppercase font-weight-bold d-block mb-2" style="font-size:.7rem">
              <i class="fas fa-calendar-alt mr-1"></i>Prazos Estimados
            </small>
            <div class="row">
              <div v-if="estimated.handling_limit" class="col-md-6 mb-2">
                <small class="text-muted d-block">Limite para Despacho</small>
                <strong :class="handlingUrgent ? 'text-danger' : ''">{{ formatDateTime(estimated.handling_limit) }}</strong>
              </div>
              <div v-if="estimated.delivery_time" class="col-md-6 mb-2">
                <small class="text-muted d-block">Previsão de Entrega</small>
                <strong>{{ formatDateTime(estimated.delivery_time) }}</strong>
              </div>
              <div v-if="estimated.delivery_extended" class="col-md-6 mb-2">
                <small class="text-muted d-block">Entrega Estendida</small>
                <strong>{{ formatDateTime(estimated.delivery_extended) }}</strong>
              </div>
              <div v-if="estimated.delivery_limit" class="col-md-6 mb-2">
                <small class="text-muted d-block">Limite p/ Cancelar c/ Devolução</small>
                <strong>{{ formatDateTime(estimated.delivery_limit) }}</strong>
              </div>
              <div v-if="estimated.delivery_final" class="col-md-6 mb-2">
                <small class="text-muted d-block">Entrega Final</small>
                <strong>{{ formatDateTime(estimated.delivery_final) }}</strong>
              </div>
            </div>
          </div>

          <div class="row">
            <!-- Logística e status -->
            <div class="col-md-6">
              <table class="table table-sm table-borderless mb-0">
                <tbody>
                  <tr>
                    <td class="text-muted" style="width:45%">Logística</td>
                    <td>
                      <span class="badge" :style="logisticStyle">
                        <i :class="[logisticIcon, 'mr-1']"></i>{{ logisticLabel }}
                      </span>
                    </td>
                  </tr>
                  <tr>
                    <td class="text-muted">Status do Envio</td>
                    <td>
                      <span v-if="liveStatus || order?.shipment_status" :class="['badge', shipmentBadge]">
                        <i :class="[shipmentIcon, 'mr-1']"></i>{{ shipmentLabel }}
                      </span>
                      <span v-else class="text-muted">—</span>
                    </td>
                  </tr>
                  <tr v-if="liveSubstatus">
                    <td class="text-muted">Detalhe</td>
                    <td><code style="font-size:.78rem">{{ liveSubstatus }}</code></td>
                  </tr>
                  <tr v-if="liveTrackingNumber || order?.tracking_code">
                    <td class="text-muted">Rastreio</td>
                    <td><code style="font-size:.8rem">{{ liveTrackingNumber || order.tracking_code }}</code></td>
                  </tr>
                  <tr v-if="carrier && carrier.name">
                    <td class="text-muted">Transportadora</td>
                    <td>{{ carrier.name }}</td>
                  </tr>
                  <tr v-if="order?.shipment_id">
                    <td class="text-muted">Shipment ID</td>
                    <td><code style="font-size:.8rem">{{ order.shipment_id }}</code></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- Datas locais (resumo) -->
            <div class="col-md-6">
              <table class="table table-sm table-borderless mb-0">
                <tbody>
                  <tr>
                    <td class="text-muted" style="width:55%">Data da Venda</td>
                    <td>{{ formatDateTime(order?.created_at) }}</td>
                  </tr>
                  <tr v-if="order?.paid_at">
                    <td class="text-muted">Pago em</td>
                    <td>{{ formatDateTime(order.paid_at) }}</td>
                  </tr>
                  <tr v-if="order?.shipped_at">
                    <td class="text-muted">Despachado em</td>
                    <td>{{ formatDateTime(order.shipped_at) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Tags ML -->
          <div v-if="tagList.length" class="mt-3 border-top pt-3">
            <small class="text-muted d-block mb-2">Tags do Mercado Livre</small>
            <div class="d-flex flex-wrap" style="gap:.4rem">
              <span
                v-for="tag in tagList"
                :key="tag"
                :class="['badge', tagBadge(tag)]"
                style="font-size:.8rem;padding:.3rem .6rem"
              >
                <i :class="[tagIcon(tag), 'mr-1']"></i>{{ tagLabel(tag) }}
              </span>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-default" @click="$emit('close')">Fechar</button>
          <button type="button" class="btn btn-outline-secondary" @click="loadTracking" :disabled="loadingTracking">
            <i class="fas fa-sync" :class="{ 'fa-spin': loadingTracking }"></i> Atualizar
          </button>
          <a
            v-if="trackingUrl"
            :href="trackingUrl"
            target="_blank"
            rel="noopener"
            class="btn btn-outline-primary"
          >
            <i class="fas fa-search-location mr-1"></i>Rastrear
          </a>
          <a
            v-if="order?.label_url"
            :href="order.label_url"
            target="_blank"
            rel="noopener"
            class="btn btn-outline-secondary"
          >
            <i class="fas fa-tag mr-1"></i>Etiqueta
          </a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { formatDate as fmtBrDate, formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import api from '@/composables/useApi'
import { shippingModeStyle } from '@/utils/constants'

const props = defineProps({
  show: { type: Boolean, default: false },
  order: { type: Object, default: null },
})
defineEmits(['close'])

// ─── Live tracking from ML ───────────────────────────────────────────────────
const trackingData = ref(null)
const loadingTracking = ref(false)
const trackingError = ref('')

async function loadTracking() {
  if (!props.order?.id || props.order?.platform !== 'mercadolivre' || !props.order?.shipment_id) {
    trackingError.value = 'Pedido sem informações de envio.'
    return
  }
  loadingTracking.value = true
  trackingError.value = ''
  try {
    const { data } = await api.get(`/orders/${props.order.id}/shipment-tracking`)
    if (data.ok) {
      trackingData.value = data
    } else {
      trackingError.value = data.detail || 'Sem dados de rastreamento.'
      trackingData.value = null
    }
  } catch (err) {
    trackingError.value = err.response?.data?.detail || 'Erro ao buscar rastreamento.'
    trackingData.value = null
  } finally {
    loadingTracking.value = false
  }
}

watch(() => props.show, (visible) => {
  if (visible && props.order?.shipment_id && props.order?.platform === 'mercadolivre') {
    loadTracking()
  } else if (!visible) {
    trackingData.value = null
    trackingError.value = ''
  }
})

const liveStatus = computed(() => trackingData.value?.status || '')
const liveSubstatus = computed(() => trackingData.value?.substatus || '')
const liveTrackingNumber = computed(() => trackingData.value?.tracking_number || '')
const carrier = computed(() => trackingData.value?.carrier || null)
const estimated = computed(() => trackingData.value?.estimated || null)
const trackingUrl = computed(() => carrier.value?.tracking_url || props.order?.tracking_url || null)

const hasAnyEstimated = computed(() => {
  if (!estimated.value) return false
  return Object.values(estimated.value).some(v => !!v)
})

// Builds the visual timeline from the ML response
const timeline = computed(() => {
  const events = (trackingData.value?.timeline || []).slice()
  // Add local "Venda" and "Pago" at the start since ML history doesn't include these
  if (props.order?.created_at) {
    events.unshift({
      date: props.order.created_at,
      label: 'Venda Realizada',
      icon: 'fa-shopping-cart',
      code: 'sale',
    })
  }
  if (props.order?.paid_at) {
    events.splice(1, 0, {
      date: props.order.paid_at,
      label: 'Pagamento Aprovado',
      icon: 'fa-dollar-sign',
      code: 'paid',
    })
  }
  // Sort and mark which events are in the past vs future
  const now = new Date()
  events.sort((a, b) => new Date(a.date) - new Date(b.date))
  return events.map((e, i) => ({
    ...e,
    future: new Date(e.date) > now,
    active: i === events.length - 1 || (i < events.length - 1 && new Date(events[i + 1].date) > now && new Date(e.date) <= now),
  }))
})

// ─── Logistic type ────────────────────────────────────────────────────────────
// Usa paleta canonica de utils/constants.js. NAO duplicar cores aqui.
// Mapeamento ML logistic_type -> bucket conforme doc oficial (validado 2026-05-27).
const LEGACY_TO_MODE = {
  fulfillment:   'full',
  self_service:  'flex',
  xd_drop_off:   'agencia',     // Places/Agil — ponto parceiro ML
  drop_off:      'correios',    // vendedor leva nos Correios
  cross_docking: 'coletado',    // ML coleta no vendedor
  xd_pickup:     'coletado',
  not_specified: 'combinado',
}
function resolveMode(method) {
  if (!method) return null
  for (const key of Object.keys(LEGACY_TO_MODE)) {
    if (method.includes(key)) return LEGACY_TO_MODE[key]
  }
  return null
}
const logisticInfo = computed(() => {
  const mode = props.order?.shipping_mode
    || resolveMode(trackingData.value?.logistic_type)
    || resolveMode(props.order?.shipping_method)
    || 'desconhecido'
  return shippingModeStyle(mode)
})
const logisticLabel = computed(() => logisticInfo.value.label)
const logisticIcon  = computed(() => logisticInfo.value.icon)
const logisticStyle = computed(() => ({
  background: logisticInfo.value.bg,
  color: logisticInfo.value.fg,
}))

// ─── Shipment status ──────────────────────────────────────────────────────────
const SHIPMENT_STATUS_MAP = {
  pending:       { label: 'Aguardando',       icon: 'fas fa-clock',                badge: 'badge-secondary' },
  handling:      { label: 'Em Preparação',    icon: 'fas fa-box-open',             badge: 'badge-warning text-dark' },
  ready_to_ship: { label: 'Pronto p/ Envio',  icon: 'fas fa-dolly',                badge: 'badge-info' },
  shipped:       { label: 'A caminho',        icon: 'fas fa-shipping-fast',        badge: 'badge-primary' },
  delivered:     { label: 'Entregue',         icon: 'fas fa-check-circle',         badge: 'badge-success' },
  not_delivered: { label: 'Não Entregue',     icon: 'fas fa-exclamation-triangle', badge: 'badge-danger' },
  cancelled:     { label: 'Cancelado',        icon: 'fas fa-times-circle',         badge: 'badge-dark' },
}
const effectiveStatus = computed(() => liveStatus.value || props.order?.shipment_status || '')
const shipmentInfo   = computed(() => SHIPMENT_STATUS_MAP[effectiveStatus.value] || { label: effectiveStatus.value || '—', icon: 'fas fa-circle', badge: 'badge-secondary' })
const shipmentLabel  = computed(() => shipmentInfo.value.label)
const shipmentIcon   = computed(() => shipmentInfo.value.icon)
const shipmentBadge  = computed(() => shipmentInfo.value.badge)

// ─── Tags ─────────────────────────────────────────────────────────────────────
const TAG_MAP = {
  paid:                  { label: 'Pago',              icon: 'fas fa-check-circle',         badge: 'badge-success' },
  not_paid:              { label: 'Não pago',          icon: 'fas fa-times-circle',         badge: 'badge-warning text-dark' },
  fraud_risk_detected:   { label: 'Risco de Fraude',   icon: 'fas fa-exclamation-triangle', badge: 'badge-danger' },
  cart:                  { label: 'Carrinho',          icon: 'fas fa-shopping-cart',        badge: 'badge-light text-dark' },
  test_order:            { label: 'Pedido de Teste',   icon: 'fas fa-flask',                badge: 'badge-secondary' },
  delivered:             { label: 'Entregue',          icon: 'fas fa-check-circle',         badge: 'badge-success' },
  not_delivered:         { label: 'Não Entregue',      icon: 'fas fa-exclamation-circle',   badge: 'badge-danger' },
}
function tagLabel(t) { return TAG_MAP[t]?.label || t }
function tagIcon(t)  { return TAG_MAP[t]?.icon  || 'fas fa-tag' }
function tagBadge(t) { return TAG_MAP[t]?.badge || 'badge-secondary' }
const tagList = computed(() => (props.order?.order_tags || '').split(',').filter(Boolean))
const hasFraud = computed(() => tagList.value.includes('fraud_risk_detected'))

// ─── SLA urgency ─────────────────────────────────────────────────────────────
const handlingUrgent = computed(() => {
  const limit = estimated.value?.handling_limit || props.order?.estimated_handling_limit
  if (!limit) return false
  return (new Date(limit) - new Date()) / 86400000 < 1
})

// ─── Address ─────────────────────────────────────────────────────────────────
const address = computed(() => props.order?.shipping_address || null)
const addressLine = computed(() => {
  const a = address.value
  if (!a) return ''
  const street = a.address_line || a.street_name || ''
  const num = a.street_number || ''
  const city = a.city?.name || a.city || ''
  const state = a.state?.name || a.state || ''
  return [street, num, city, state].filter(Boolean).join(', ')
})
const addressZip = computed(() => {
  const a = address.value
  if (!a) return ''
  const z = String(a.zip_code || a.zipcode || a.cep || '').replace(/\D/g, '')
  return z.length === 8 ? `${z.slice(0, 5)}-${z.slice(5)}` : z
})

// ─── Date format ──────────────────────────── fonte única (horário do Brasil) ──
function formatDate(d) { return fmtBrDate(d) }
function formatDateTime(d) { return fmtBrDateTime(d) }
</script>

<style scoped>
.timeline-item {
  text-align: center;
  min-width: 80px;
}

/* Vertical timeline */
.shipment-timeline {
  position: relative;
  padding-left: 2rem;
}
.shipment-timeline::before {
  content: '';
  position: absolute;
  left: 12px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #dee2e6;
}
.timeline-row {
  position: relative;
  padding: .35rem 0 .35rem .75rem;
  margin-left: -2rem;
  padding-left: 2.5rem;
}
.timeline-marker {
  position: absolute;
  left: 0;
  top: .35rem;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #007bff;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: .72rem;
  border: 2px solid white;
  box-shadow: 0 0 0 2px #007bff;
  z-index: 1;
}
.timeline-row.is-future .timeline-marker {
  background: #f8f9fa;
  color: #adb5bd;
  box-shadow: 0 0 0 2px #dee2e6;
}
.timeline-row.is-active .timeline-marker {
  background: #28a745;
  box-shadow: 0 0 0 2px #28a745;
}
.timeline-content {
  padding-bottom: .5rem;
  border-bottom: 1px dashed #f1f3f5;
}
.timeline-row:last-child .timeline-content {
  border-bottom: none;
}
</style>
