<template>
  <div
    v-if="show"
    class="modal fade show d-block"
    tabindex="-1"
    style="background:rgba(0,0,0,.5);z-index:1055"
    @click.self="$emit('close')"
  >
    <div class="modal-dialog modal-xl">
      <div class="modal-content">

        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-file-invoice-dollar mr-2"></i>
            Notas Fiscais — Pedido #{{ order?.platform_order_id || order?.id }}
          </h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <div v-if="loading" class="text-center py-5 text-muted">
            <i class="fas fa-spinner fa-spin fa-2x"></i>
            <p class="mt-2 mb-0">Consultando ML…</p>
          </div>

          <div v-else-if="error" class="alert alert-danger mb-0">
            <i class="fas fa-exclamation-circle mr-1"></i>{{ error }}
          </div>

          <div v-else-if="!invoices.length" class="text-center py-5 text-muted">
            <i class="fas fa-file-times fa-3x mb-3 d-block"></i>
            <p class="mb-0">Nenhuma nota fiscal encontrada para este pedido.</p>
            <small>Verifique se o pedido está vinculado ao Faturador ML.</small>
          </div>

          <div v-else>
            <div
              v-for="inv in invoices"
              :key="inv.id"
              class="card mb-2 border"
            >
              <div class="card-body p-3">
                <div class="d-flex align-items-start justify-content-between flex-wrap" style="gap:.5rem">

                  <!-- Tipo + Status -->
                  <div>
                    <span class="badge mr-1" :class="typeBadge(inv.transaction_type)" style="font-size:.8rem">
                      {{ inv.transaction_type_label || inv.transaction_type || 'NF-e' }}
                    </span>
                    <span class="badge" :class="statusBadge(inv.status)" style="font-size:.8rem">
                      {{ statusLabel(inv.status) }}
                    </span>
                    <div class="mt-1" style="font-size:.82rem;color:#555">
                      {{ inv.transaction_type_description }}
                    </div>
                  </div>

                  <!-- Número / Série / Data -->
                  <div class="text-right" style="font-size:.82rem">
                    <div v-if="inv.invoice_number">
                      <strong>NF-e {{ inv.invoice_number }}</strong>
                      <span v-if="inv.invoice_series"> / Série {{ inv.invoice_series }}</span>
                    </div>
                    <div class="text-muted">{{ formatDate(inv.issued_date) }}</div>
                    <div v-if="inv.amount" class="font-weight-bold">R$ {{ fmtCurrency(inv.amount) }}</div>
                  </div>
                </div>

                <!-- Chave de acesso -->
                <div v-if="inv.invoice_key" class="mt-2 p-2 rounded" style="background:#f8f9fa;font-size:.75rem;word-break:break-all">
                  <span class="text-muted mr-1">Chave:</span>
                  <code>{{ inv.invoice_key }}</code>
                  <i class="fas fa-copy ml-2 text-muted" style="cursor:pointer" @click="copy(inv.invoice_key)" title="Copiar chave"></i>
                </div>

                <!-- Ações -->
                <div class="mt-2 d-flex align-items-center" style="gap:.4rem">
                  <button
                    v-if="inv.xml_location"
                    class="btn btn-sm btn-outline-secondary"
                    :disabled="downloading[inv.id + '_xml']"
                    @click="downloadXml(inv)"
                    title="Baixar XML da NF-e"
                  >
                    <i class="fas fa-file-code mr-1" :class="{ 'fa-spin': downloading[inv.id + '_xml'] }"></i>
                    {{ downloading[inv.id + '_xml'] ? 'Baixando…' : 'XML' }}
                  </button>
                  <button
                    v-if="inv.danfe_location"
                    class="btn btn-sm btn-outline-primary"
                    :disabled="downloading[inv.id + '_danfe']"
                    @click="openDanfe(inv)"
                    title="Visualizar / Imprimir DANFE"
                  >
                    <i class="fas fa-print mr-1" :class="{ 'fa-spin': downloading[inv.id + '_danfe'] }"></i>
                    {{ downloading[inv.id + '_danfe'] ? 'Abrindo…' : 'DANFE' }}
                  </button>
                  <span v-if="inv.errors?.length" class="text-danger small">
                    <i class="fas fa-exclamation-triangle mr-1"></i>{{ inv.errors[0]?.message || 'Erro na NF-e' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <small class="text-muted mr-auto">{{ invoices.length }} nota(s) fiscal(is) encontrada(s)</small>
          <button class="btn btn-default" @click="$emit('close')">Fechar</button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  show:  { type: Boolean, default: false },
  order: { type: Object,  default: null  },
})
defineEmits(['close'])

const toast = useToast()
const invoices   = ref([])
const loading    = ref(false)
const error      = ref(null)
const downloading = ref({})

watch(() => props.show, async (val) => {
  if (val && props.order) {
    await load()
  } else {
    invoices.value = []
    error.value = null
  }
})

async function load() {
  loading.value = true
  error.value = null
  try {
    const { data } = await api.get(`/orders/${props.order.id}/invoices`)
    invoices.value = data.invoices || []
    // O backend persiste o status real da NF-e ao consultar (importante para
    // pedidos Full, cuja nota o ML emite sozinho). Reflete na lista sem reload.
    if (props.order && data.nfe_status) {
      props.order.nfe_status = data.nfe_status
      props.order.nfe_key = data.nfe_key
      props.order.nfe_url = data.nfe_url
    }
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao consultar notas fiscais'
  } finally {
    loading.value = false
  }
}

async function downloadXml(inv) {
  const key = inv.id + '_xml'
  downloading.value[key] = true
  try {
    const { data } = await api.get(
      `/orders/${props.order.id}/invoices/${inv.id}/xml`,
      { responseType: 'blob' },
    )
    const url = URL.createObjectURL(new Blob([data], { type: 'application/xml' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `NFe_${inv.invoice_number || inv.id}.xml`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao baixar XML')
  } finally {
    downloading.value[key] = false
  }
}

async function openDanfe(inv) {
  const key = inv.id + '_danfe'
  downloading.value[key] = true
  try {
    const { data } = await api.get(
      `/orders/${props.order.id}/invoices/${inv.id}/danfe`,
      { responseType: 'blob' },
    )
    const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
    window.open(url, '_blank')
    // revoke after delay so the new tab can load
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao abrir DANFE')
  } finally {
    downloading.value[key] = false
  }
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast.success('Chave copiada!') }
  catch { toast.error('Não foi possível copiar') }
}

function formatDate(iso) { return fmtBrDateTime(iso) }   // fonte única (horário do Brasil)

function fmtCurrency(v) {
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function typeBadge(type) {
  const map = {
    sale: 'badge-success',
    devolution: 'badge-warning text-dark',
    sale_return: 'badge-secondary',
    inbound: 'badge-info',
    inbound_return: 'badge-secondary',
    symbolic_inbound: 'badge-light border',
    symbolic_inbound_return: 'badge-light border',
    removal: 'badge-secondary',
    cte: 'badge-dark',
    correction_letter: 'badge-secondary',
  }
  return map[type] || 'badge-secondary'
}

function statusBadge(status) {
  const map = {
    authorized: 'badge-success',
    pending: 'badge-warning text-dark',
    in_process: 'badge-info',
    rejected: 'badge-danger',
    cancelled: 'badge-danger',
    forbidden_disablement: 'badge-danger',
  }
  return map[status] || 'badge-secondary'
}

function statusLabel(status) {
  const map = {
    authorized: 'Autorizada',
    pending: 'Pendente',
    in_process: 'Em Processamento',
    rejected: 'Rejeitada',
    cancelled: 'Cancelada',
    forbidden_disablement: 'Inutilizada',
  }
  return map[status] || status || '—'
}
</script>
