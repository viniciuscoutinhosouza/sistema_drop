<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0">
              <i class="fas mr-2" :class="directionIcon"></i>
              {{ directionLabel }} #{{ invoice?.id || '...' }}
              <span v-if="invoice?.nfe_number" class="text-muted">— Nº {{ invoice.nfe_number }}/{{ invoice.serie }}</span>
            </h1>
            <small v-if="invoice" class="text-muted">
              <span class="badge mr-1" :class="statusClass(invoice.status)">{{ statusLabel(invoice.status) }}</span>
              {{ invoice.access_key ? `Chave: ${invoice.access_key}` : '' }}
            </small>
          </div>
          <div class="col-sm-4 text-right">
            <RouterLink :to="backUrl" class="btn btn-secondary mr-2">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
            <RouterLink v-if="canEdit" :to="`/fiscal/invoices/${invoice?.id}/edit`" class="btn btn-primary">
              <i class="fas fa-edit mr-1"></i> Editar
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content" v-if="invoice">
      <div class="container-fluid">
        <div class="row">
          <!-- Coluna esquerda: dados gerais + pessoa -->
          <div class="col-md-5">
            <div class="card">
              <div class="card-header"><h3 class="card-title">Dados gerais</h3></div>
              <div class="card-body">
                <dl class="row mb-0 small">
                  <dt class="col-sm-5">Finalidade</dt>
                  <dd class="col-sm-7">{{ purposeLabel(invoice.purpose) }}</dd>

                  <dt class="col-sm-5">Natureza</dt>
                  <dd class="col-sm-7">{{ invoice.natureza_operacao || '—' }}</dd>

                  <dt class="col-sm-5">Modelo / Série / Nº</dt>
                  <dd class="col-sm-7">{{ invoice.model }} / {{ invoice.serie || '—' }} / {{ invoice.nfe_number || '—' }}</dd>

                  <dt class="col-sm-5">Emissão</dt>
                  <dd class="col-sm-7">{{ formatDate(invoice.issue_date) }}</dd>

                  <dt class="col-sm-5">Saída</dt>
                  <dd class="col-sm-7">{{ formatDate(invoice.exit_date) }}</dd>

                  <dt class="col-sm-5">Forma pagamento</dt>
                  <dd class="col-sm-7">{{ invoice.payment_method || '—' }}</dd>

                  <dt class="col-sm-5">Frete</dt>
                  <dd class="col-sm-7">{{ freightLabel(invoice.freight_modality) }}</dd>

                  <template v-if="invoice.direction === 'in'">
                    <dt class="col-sm-5">Origem (entrada)</dt>
                    <dd class="col-sm-7">
                      <span class="badge badge-light">{{ inboundSourceLabel(invoice.inbound_source) }}</span>
                    </dd>
                    <dt class="col-sm-5">Manifestação</dt>
                    <dd class="col-sm-7">
                      <span class="badge" :class="manifestationClass(invoice.manifestation)">
                        {{ manifestationLabel(invoice.manifestation) }}
                      </span>
                    </dd>
                  </template>

                  <dt v-if="invoice.order_id" class="col-sm-5">Pedido vinculado</dt>
                  <dd v-if="invoice.order_id" class="col-sm-7">
                    <RouterLink :to="`/orders/${invoice.order_id}`" class="badge badge-info">
                      <i class="fas fa-shopping-cart mr-1"></i>#{{ invoice.order_id }}
                    </RouterLink>
                  </dd>
                </dl>
              </div>
            </div>

            <div class="card">
              <div class="card-header"><h3 class="card-title">{{ invoice.direction === 'in' ? 'Fornecedor' : 'Destinatário' }}</h3></div>
              <div class="card-body">
                <div v-if="invoice.person">
                  <p class="mb-1"><strong>{{ invoice.person.name }}</strong></p>
                  <p v-if="invoice.person.trade_name" class="text-muted small mb-1">{{ invoice.person.trade_name }}</p>
                  <p class="mb-1"><code>{{ invoice.person.document }}</code></p>
                  <p v-if="invoice.person.city" class="mb-0 text-muted small">
                    {{ invoice.person.city }}/{{ invoice.person.state }}
                  </p>
                </div>
                <p v-else class="text-muted mb-0">Nenhuma pessoa selecionada.</p>
              </div>
            </div>
          </div>

          <!-- Coluna direita: itens + totais + ações -->
          <div class="col-md-7">
            <div class="card">
              <div class="card-header"><h3 class="card-title">Itens ({{ invoice.items?.length || 0 }})</h3></div>
              <div class="card-body p-0">
                <table class="table table-sm mb-0">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Descrição</th>
                      <th>Origem</th>
                      <th>NCM</th>
                      <th>CFOP</th>
                      <th class="text-right">Qtd</th>
                      <th class="text-right">Unit.</th>
                      <th class="text-right">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="(invoice.items || []).length === 0">
                      <td colspan="8" class="text-center text-muted py-3">Nenhum item.</td>
                    </tr>
                    <tr v-for="it in invoice.items" :key="it.id">
                      <td>{{ it.item_number }}</td>
                      <td>
                        <strong>{{ it.description }}</strong>
                        <small v-if="it.sku" class="d-block text-muted">SKU: <code>{{ it.sku }}</code></small>
                        <small v-if="it.ean" class="d-block text-muted">EAN: {{ it.ean }}</small>
                      </td>
                      <td>
                        <span v-if="it.source_type === 'cmig'" class="badge badge-secondary" title="Produto do estoque CMIG">CMIG</span>
                        <span v-else-if="it.source_type === 'pg'" class="badge badge-info" title="Produto do estoque PG (Produto Geral)">PG</span>
                        <span v-else-if="it.cmig_product_id" class="badge badge-secondary" title="Produto do estoque CMIG">CMIG</span>
                        <span v-else class="badge badge-light text-muted" title="Item manual sem vínculo com estoque">Manual</span>
                      </td>
                      <td>{{ it.ncm || '—' }}</td>
                      <td>{{ it.cfop || '—' }}</td>
                      <td class="text-right">{{ formatNumber(it.quantity, 4) }}</td>
                      <td class="text-right">{{ formatCurrency(it.unit_value) }}</td>
                      <td class="text-right"><strong>{{ formatCurrency(it.total_value) }}</strong></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="card">
              <div class="card-header"><h3 class="card-title">Totais</h3></div>
              <div class="card-body">
                <dl class="row mb-0 small">
                  <dt class="col-sm-6">Total dos produtos</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_products) }}</dd>

                  <dt class="col-sm-6">Frete</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_freight) }}</dd>

                  <dt class="col-sm-6">Seguro</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_insurance) }}</dd>

                  <dt class="col-sm-6">Outros</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_other) }}</dd>

                  <dt class="col-sm-6">Desconto</dt>
                  <dd class="col-sm-6 text-right text-danger">- {{ formatCurrency(invoice.total_discount) }}</dd>

                  <dt class="col-sm-6">ICMS</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_icms) }}</dd>

                  <dt class="col-sm-6">ICMS ST</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_icms_st) }}</dd>

                  <dt class="col-sm-6">PIS / COFINS</dt>
                  <dd class="col-sm-6 text-right">
                    {{ formatCurrency(Number(invoice.total_pis || 0) + Number(invoice.total_cofins || 0)) }}
                  </dd>

                  <dt class="col-sm-6">IPI</dt>
                  <dd class="col-sm-6 text-right">{{ formatCurrency(invoice.total_ipi) }}</dd>

                  <dt class="col-sm-6 mt-2"><strong>Total da NFe</strong></dt>
                  <dd class="col-sm-6 text-right mt-2"><strong class="h5">{{ formatCurrency(invoice.total_invoice) }}</strong></dd>
                </dl>
              </div>
            </div>

            <!-- Ações -->
            <div class="card">
              <div class="card-header"><h3 class="card-title">Ações</h3></div>
              <div class="card-body">
                <button v-if="invoice.status === 'authorized'" class="btn btn-outline-info mr-2 mb-2"
                        :disabled="downloading" @click="baixar('xml')">
                  <i class="fas fa-file-code mr-1"></i> Baixar XML
                </button>
                <button v-if="invoice.status === 'authorized'" class="btn btn-outline-info mr-2 mb-2"
                        :disabled="downloading" @click="baixar('danfe')">
                  <i class="fas fa-file-pdf mr-1"></i> Baixar DANFE
                </button>
                <button v-if="invoice.status === 'authorized'" class="btn btn-info mr-2 mb-2" @click="showEmailModal = true">
                  <i class="fas fa-envelope mr-1"></i> Enviar por e-mail
                </button>
                <button v-if="invoice.status === 'authorized'" class="btn btn-outline-secondary mr-2 mb-2" @click="showCceModal = true">
                  <i class="fas fa-edit mr-1"></i> Carta de Correção
                </button>
                <button v-if="invoice.status === 'authorized'" class="btn btn-warning mr-2 mb-2" @click="showCancelModal = true">
                  <i class="fas fa-ban mr-1"></i> Cancelar NFe
                </button>
                <button v-if="['queued','processing'].includes(invoice.status)"
                        class="btn btn-outline-info mr-2 mb-2" :disabled="refreshing" @click="refreshStatus">
                  <i class="fas" :class="refreshing ? 'fa-spinner fa-spin' : 'fa-sync'"></i> Reconsultar status
                </button>
                <button v-if="invoice.direction === 'in' && (invoice.manifestation === 'pending' || invoice.manifestation === 'ciencia')"
                        class="btn btn-warning mr-2 mb-2" @click="showManifestModal = true">
                  <i class="fas fa-flag mr-1"></i> Manifestar
                </button>
                <button v-if="invoice.direction === 'in' && !invoice.stock_updated"
                        class="btn btn-outline-success mr-2 mb-2" @click="showStockModal = true">
                  <i class="fas fa-boxes mr-1"></i> Atualizar Estoque
                </button>
                <span v-if="invoice.direction === 'in' && invoice.stock_updated"
                      class="badge badge-success mr-2 mb-2 align-self-center">
                  <i class="fas fa-check mr-1"></i>Estoque atualizado
                </span>
                <button v-if="['finalized','authorized'].includes(invoice.status)"
                        class="btn btn-outline-warning mr-2 mb-2"
                        :disabled="reapplyingStock"
                        title="Recalcula o estoque dos produtos CMIG e PG referenciados nesta NFe. Operação idempotente — pode ser executada várias vezes sem acumular."
                        @click="reapplyStock">
                  <i :class="['fas', reapplyingStock ? 'fa-spinner fa-spin' : 'fa-sync-alt']"></i>
                  Recalcular Estoque
                </button>
                <button v-if="canDelete" class="btn btn-outline-danger mb-2" @click="deleteInvoice">
                  <i class="fas fa-trash mr-1"></i> {{ deleteButtonLabel }}
                </button>

                <div v-if="invoice.focus_message" class="alert alert-info mt-2 small mb-0">
                  <strong>SEFAZ:</strong> {{ invoice.focus_message }}
                </div>
              </div>
            </div>

            <!-- Eventos -->
            <div v-if="(invoice.events || []).length > 0" class="card">
              <div class="card-header"><h3 class="card-title">Eventos</h3></div>
              <div class="card-body p-0">
                <table class="table table-sm mb-0">
                  <thead>
                    <tr>
                      <th>Tipo</th>
                      <th>Quando</th>
                      <th>Motivo</th>
                      <th>Protocolo</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="ev in invoice.events" :key="ev.id">
                      <td>{{ ev.event_type }}</td>
                      <td>{{ formatDateTime(ev.created_at) }}</td>
                      <td>{{ ev.reason || '—' }}</td>
                      <td>{{ ev.sefaz_protocol || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <div v-else-if="loading" class="text-center py-5">
      <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
    </div>

    <!-- Modal: Cancelar -->
    <div v-if="showCancelModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-ban mr-2"></i>Cancelar NFe</h5>
            <button type="button" class="close" @click="showCancelModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small">
              O cancelamento só pode ser feito até <strong>24h após a autorização</strong>.
              Justificativa entre 15 e 255 caracteres.
            </p>
            <textarea v-model="cancelReason" class="form-control" rows="3"
                      placeholder="Motivo do cancelamento..."></textarea>
            <small class="text-muted">{{ cancelReason.length }} / 255</small>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCancelModal = false">Voltar</button>
            <button class="btn btn-danger" :disabled="cancelReason.length < 15 || acting" @click="doCancel">
              <i class="fas" :class="acting ? 'fa-spinner fa-spin' : 'fa-ban'"></i>
              {{ acting ? 'Cancelando...' : 'Confirmar Cancelamento' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: CCe -->
    <div v-if="showCceModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-edit mr-2"></i>Carta de Correção Eletrônica</h5>
            <button type="button" class="close" @click="showCceModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small">
              Texto entre 15 e 1000 caracteres. <strong>Não pode ser usada para corrigir
              valores, datas ou destinatário</strong> — apenas observações e dados não-fiscais.
            </p>
            <textarea v-model="cceText" class="form-control" rows="4"
                      placeholder="Descreva a correção..."></textarea>
            <small class="text-muted">{{ cceText.length }} / 1000</small>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCceModal = false">Voltar</button>
            <button class="btn btn-primary" :disabled="cceText.length < 15 || cceText.length > 1000 || acting" @click="doCce">
              <i class="fas" :class="acting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
              Enviar CCe
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Manifestação -->
    <ManifestationModal
      v-if="showManifestModal && invoice"
      :invoice="invoice"
      @close="showManifestModal = false"
      @manifested="onManifested" />

    <!-- Modal: Atualizar Estoque -->
    <StockUpdateModal
      v-if="showStockModal && invoice"
      :invoice="invoice"
      @close="showStockModal = false"
      @updated="onStockUpdated" />

    <!-- Modal: E-mail -->
    <div v-if="showEmailModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-envelope mr-2"></i>Enviar XML + DANFE por e-mail</h5>
            <button type="button" class="close" @click="showEmailModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <label class="small">Destinatários (separados por vírgula)</label>
            <input v-model="emailList" class="form-control" placeholder="cliente@exemplo.com, copia@exemplo.com">
            <small v-if="invoice?.person?.email" class="text-muted d-block mt-1">
              Sugestão: <a href="#" @click.prevent="emailList = invoice.person.email">{{ invoice.person.email }}</a>
            </small>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showEmailModal = false">Voltar</button>
            <button class="btn btn-primary" :disabled="!emailList.trim() || acting" @click="doEmail">
              <i class="fas" :class="acting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
              Enviar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFiscalStore } from '@/stores/fiscal'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import { fmt } from '@/views/fiscal/_helpers'
import ManifestationModal from '@/components/fiscal/ManifestationModal.vue'
import StockUpdateModal from '@/components/fiscal/StockUpdateModal.vue'

const route = useRoute()
const router = useRouter()
const fiscalStore = useFiscalStore()
const toast = useToast()

const invoice = ref(null)
const loading = ref(true)

const showCancelModal = ref(false)
const showCceModal = ref(false)
const showEmailModal = ref(false)
const showManifestModal = ref(false)
const showStockModal = ref(false)
const cancelReason = ref('')
const cceText = ref('')
const emailList = ref('')
const acting = ref(false)
const refreshing = ref(false)
const reapplyingStock = ref(false)
const downloading = ref(false)

async function baixar(kind) {
  if (!invoice.value) return
  downloading.value = true
  try {
    const { data } = await api.get(`/invoices/${invoice.value.id}/${kind}`, { responseType: 'blob' })
    const ext = kind === 'danfe' ? 'pdf' : 'xml'
    const chave = invoice.value.access_key || invoice.value.id
    const url = URL.createObjectURL(new Blob([data]))
    const link = document.createElement('a')
    link.href = url
    link.download = `${kind === 'danfe' ? 'DANFE' : 'NFe'}-${chave}.${ext}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (e) {
    toast.error(e.response?.data?.detail || `Erro ao baixar ${kind.toUpperCase()}`)
  } finally {
    downloading.value = false
  }
}

const directionIcon = computed(() => invoice.value?.direction === 'in' ? 'fa-arrow-down text-warning' : 'fa-arrow-up text-success')
const directionLabel = computed(() => invoice.value?.direction === 'in' ? 'Entrada' : 'Saída')
const backUrl = computed(() => invoice.value?.direction === 'in' ? '/fiscal/entradas' : '/fiscal/saidas')
const canEdit = computed(() => invoice.value?.status === 'draft')
const canDelete = computed(() => ['draft', 'finalized'].includes(invoice.value?.status))
const deleteButtonLabel = computed(() =>
  invoice.value?.status === 'draft' ? 'Excluir Rascunho' : 'Excluir NFe'
)

const formatDate = fmt.date
const formatDateTime = fmt.datetime
const formatCurrency = fmt.currency
const purposeLabel = fmt.purpose
const statusLabel = fmt.statusLabel
const statusClass = fmt.statusClass
const inboundSourceLabel = fmt.inboundSource
const manifestationLabel = fmt.manifestation
const manifestationClass = fmt.manifestationClass

function formatNumber(v, dec = 2) {
  return v == null ? '—' : Number(v).toLocaleString('pt-BR', {
    minimumFractionDigits: dec, maximumFractionDigits: dec,
  })
}

function freightLabel(m) {
  const map = { 0: '0 — Emitente', 1: '1 — Destinatário', 2: '2 — Terceiros',
                3: '3 — Próprio Remetente', 4: '4 — Próprio Destinatário', 9: '9 — Sem frete' }
  return map[m] ?? '—'
}

async function load() {
  loading.value = true
  try {
    invoice.value = await fiscalStore.fetchInvoice(Number(route.params.id))
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NFe')
    router.back()
  } finally {
    loading.value = false
  }
}

async function deleteInvoice() {
  const isFinalized = invoice.value?.status === 'finalized'
  const direction = invoice.value?.direction
  let msg = 'Excluir este rascunho? Esta ação não pode ser desfeita.'
  if (isFinalized) {
    msg = (
      'Excluir esta NFe?\n\n' +
      (direction === 'in'
        ? '• O estoque dos produtos CMIG/PG será revertido automaticamente.\n'
        : '• Esta NFe será removida dos totalizadores.\n') +
      '• Esta ação não pode ser desfeita.'
    )
  }
  if (!confirm(msg)) return
  try {
    await fiscalStore.deleteInvoice(invoice.value.id)
    toast.success(isFinalized ? 'NFe excluída e estoque recalculado' : 'Rascunho excluído')
    router.push(backUrl.value)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir')
  }
}

async function doCancel() {
  acting.value = true
  try {
    await fiscalStore.cancel(invoice.value.id, cancelReason.value)
    toast.success('NFe cancelada')
    showCancelModal.value = false
    cancelReason.value = ''
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao cancelar')
  } finally {
    acting.value = false
  }
}

async function doCce() {
  acting.value = true
  try {
    await fiscalStore.correctionLetter(invoice.value.id, cceText.value)
    toast.success('Carta de correção enviada')
    showCceModal.value = false
    cceText.value = ''
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar CCe')
  } finally {
    acting.value = false
  }
}

async function doEmail() {
  acting.value = true
  try {
    const emails = emailList.value.split(',').map(e => e.trim()).filter(Boolean)
    await fiscalStore.sendEmail(invoice.value.id, emails)
    toast.success('E-mail enviado')
    showEmailModal.value = false
    emailList.value = ''
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar e-mail')
  } finally {
    acting.value = false
  }
}

function onManifested() {
  toast.success('Manifestação registrada')
  showManifestModal.value = false
  load()
}

function onStockUpdated() {
  toast.success('Estoque atualizado')
  showStockModal.value = false
  load()
}

async function refreshStatus() {
  refreshing.value = true
  try {
    const result = await fiscalStore.refreshStatus(invoice.value.id)
    toast.info(`Status: ${result.status}`)
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao reconsultar')
  } finally {
    refreshing.value = false
  }
}

async function reapplyStock() {
  const msg = (
    'Recalcular o estoque dos produtos referenciados nesta NFe?\n\n' +
    '• Cobre tanto produtos CMIG quanto PG.\n' +
    '• Operação idempotente — pode ser executada várias vezes sem acumular.'
  )
  if (!confirm(msg)) return
  reapplyingStock.value = true
  try {
    const { data } = await api.post(`/invoices/${invoice.value.id}/reapply-stock`)
    const parts = []
    if (data.cmig_recomputed) parts.push(`${data.cmig_recomputed} CMIG`)
    if (data.pg_recomputed)   parts.push(`${data.pg_recomputed} PG`)
    if (parts.length === 0)   parts.push('nenhum produto vinculado')
    toast.success(`Estoque recalculado: ${parts.join(', ')}.`)
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao recalcular estoque.')
  } finally {
    reapplyingStock.value = false
  }
}

onMounted(load)
</script>
