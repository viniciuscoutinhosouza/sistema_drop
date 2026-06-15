<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useToast } from '@/composables/useToast'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import { useClaims } from '@/composables/useClaims'
import TemplatesModal from '@/components/atendimento/TemplatesModal.vue'

const props = defineProps({ accounts: { type: Array, default: () => [] } })
const emit = defineEmits(['open-count'])

const toast = useToast()
const { fetchStats, listClaims, getClaim, syncAccount, sendMessage, executeAction, getReturns } = useClaims()

const filters = reactive({ account_id: '', status: 'opened' })
const claims = ref([])
const loading = ref(false)
const syncing = ref(false)
const selected = ref(null) // claim detalhado
const loadingDetail = ref(false)
const msgChannel = ref('complainant')
const replyText = ref('')
const sending = ref(false)
const actionBusy = ref(false)
const showTemplates = ref(false)
// modal de ação: type ∈ partial | return-review | tracking | confirm | returns | details
const modal = reactive({ type: null, amount: '', problem: false, problemNote: '', tracking: '', actionName: '', confirmText: '', returns: null })

const ACTION_LABELS = {
  send_message_to_complainant: 'Enviar Mensagem ao Comprador',
  send_message_to_mediator: 'Enviar Mensagem ao Mediador',
  refund: 'Reembolsar Total',
  open_dispute: 'Solicitar Mediação do ML',
  allow_partial_refund: 'Reembolso Parcial',
  return_review: 'Revisar Devolução',
  allow_return: 'Gerar etiqueta de devolução',
  send_tracking_number: 'Código de Rastreio',
}
// available_action.action → slug do endpoint
const ACTION_SLUG = {
  refund: 'refund',
  open_dispute: 'open-dispute',
  allow_partial_refund: 'partial-refund',
  return_review: 'return-review',
  allow_return: 'allow-return',
  send_tracking_number: 'send-tracking',
}

const channelMessages = computed(() =>
  (selected.value?.messages || []).filter((m) => m.channel === msgChannel.value),
)
const actionButtons = computed(() =>
  (selected.value?.available_actions || [])
    .map((a) => a.action)
    .filter((name) => name !== 'send_message_to_complainant' && name !== 'send_message_to_mediator'),
)
const replyRemaining = computed(() => 350 - replyText.value.length)

async function refreshStats() {
  try {
    const s = await fetchStats()
    emit('open-count', s.total_open || 0)
  } catch { /* silencioso */ }
}

async function load() {
  loading.value = true
  try {
    const params = { status: filters.status, page: 1, page_size: 50 }
    if (filters.account_id) params.account_id = filters.account_id
    const data = await listClaims(params)
    claims.value = data.data || []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao carregar reclamações.')
  } finally {
    loading.value = false
  }
}

async function openClaim(c) {
  loadingDetail.value = true
  selected.value = null
  try {
    const data = await getClaim(c.id)
    selected.value = data
    msgChannel.value = data.stage === 'dispute' && data.messages_mediator?.length ? 'mediator' : 'complainant'
  } catch (e) {
    toast.error('Falha ao abrir a reclamação.')
  } finally {
    loadingDetail.value = false
  }
}

async function doSync() {
  syncing.value = true
  try {
    if (filters.account_id) {
      await syncAccount(filters.account_id)
    } else {
      // Sincroniza todas as contas acessíveis (a busca roda em background no backend).
      const ids = (props.accounts || []).map((a) => a.id)
      await Promise.allSettled(ids.map((id) => syncAccount(id)))
    }
    toast.info('Sincronização iniciada. As reclamações aparecem em instantes…')
    setTimeout(() => { load(); refreshStats() }, 6000)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao sincronizar.')
  } finally {
    syncing.value = false
  }
}

async function doReply() {
  const text = replyText.value.trim()
  if (!text || !selected.value) return
  sending.value = true
  try {
    await sendMessage(selected.value.id, text)
    replyText.value = ''
    toast.success('Mensagem enviada.')
    await openClaim(selected.value)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao enviar mensagem.')
  } finally {
    sending.value = false
  }
}

// Abre o modal apropriado para a ação escolhida.
function runAction(actionName) {
  if (!selected.value || !ACTION_SLUG[actionName]) return
  modal.actionName = actionName
  modal.amount = ''
  modal.problem = false
  modal.problemNote = ''
  modal.tracking = ''
  if (actionName === 'allow_partial_refund') modal.type = 'partial'
  else if (actionName === 'return_review') modal.type = 'return-review'
  else if (actionName === 'send_tracking_number') modal.type = 'tracking'
  else {
    modal.confirmText = actionName === 'refund'
      ? 'Confirmar REEMBOLSO TOTAL? Esta ação é irreversível.'
      : `Confirmar: ${ACTION_LABELS[actionName] || actionName}?`
    modal.type = 'confirm'
  }
}

async function dispatch(slug, payload) {
  const label = ACTION_LABELS[modal.actionName] || modal.actionName
  actionBusy.value = true
  try {
    await executeAction(selected.value.id, slug, payload)
    toast.success(`${label}: executado.`)
    modal.type = null
    setTimeout(() => openClaim(selected.value), 2500)
    refreshStats()
  } catch (e) {
    toast.error(e.response?.data?.detail || `Falha em "${label}".`)
  } finally {
    actionBusy.value = false
  }
}

function confirmModal() {
  const slug = ACTION_SLUG[modal.actionName]
  if (modal.type === 'partial') {
    const amount = Number(String(modal.amount).replace(',', '.'))
    if (!Number.isFinite(amount) || amount <= 0) { toast.error('Valor inválido.'); return }
    return dispatch(slug, { amount })
  }
  if (modal.type === 'return-review') {
    const payload = modal.problem
      ? { result: 'rejected', note: modal.problemNote.trim() }
      : { result: 'approved' }
    return dispatch(slug, payload)
  }
  if (modal.type === 'tracking') {
    if (!modal.tracking.trim()) { toast.error('Informe o código.'); return }
    return dispatch(slug, { tracking_number: modal.tracking.trim() })
  }
  return dispatch(slug, {}) // confirm simples
}

async function viewReturn() {
  modal.returns = null
  modal.type = 'returns'
  try {
    modal.returns = await getReturns(selected.value.id)
  } catch {
    toast.error('Falha ao carregar a devolução.')
  }
}

function viewDetails() {
  modal.type = 'details'
}

function applyTemplate(body) {
  replyText.value = (replyText.value ? replyText.value + '\n' : '') + body
  showTemplates.value = false
}

function copy(txt) {
  if (!txt) return
  navigator.clipboard?.writeText(String(txt))
  toast.info('Copiado.')
}

function repBadge(c) {
  if (c?.affects_reputation === 'affected') return { cls: 'badge-danger', txt: 'Reputação Afetada' }
  if (c?.affects_reputation === 'not_affected') return { cls: 'badge-success', txt: 'Reputação Não Afetada' }
  return null
}
function statusBadge(s) {
  return s === 'opened' ? { cls: 'badge-warning', txt: 'Aberto' } : { cls: 'badge-secondary', txt: 'Fechado' }
}

watch(() => [filters.account_id, filters.status], load)
onMounted(() => { load(); refreshStats() })
</script>

<template>
  <div>
    <!-- Toolbar -->
    <div class="d-flex flex-wrap align-items-center mb-2" style="gap:8px">
      <select v-model="filters.account_id" class="form-control form-control-sm" style="width:220px">
        <option value="">Todas as contas</option>
        <option v-for="a in accounts" :key="a.id" :value="a.id">
          {{ a.description || a.platform_username || `Conta #${a.id}` }}
        </option>
      </select>
      <select v-model="filters.status" class="form-control form-control-sm" style="width:150px">
        <option value="opened">Abertas</option>
        <option value="closed">Fechadas</option>
        <option value="">Todas</option>
      </select>
      <button class="btn btn-sm btn-outline-secondary" :disabled="syncing" @click="doSync">
        <i :class="['fas', syncing ? 'fa-spinner fa-spin' : 'fa-sync-alt', 'mr-1']"></i>Sincronizar
      </button>
    </div>

    <div class="row">
      <!-- Coluna esquerda: lista -->
      <div class="col-md-4">
        <div class="card">
          <div class="card-header py-2"><strong>{{ claims.length }} reclamações</strong></div>
          <div class="card-body p-0" style="max-height:70vh;overflow-y:auto">
            <div v-if="loading" class="text-center text-muted py-4"><i class="fas fa-spinner fa-spin"></i></div>
            <div v-else-if="!claims.length" class="text-center text-muted py-4">Nenhuma reclamação.</div>
            <a v-for="c in claims" :key="c.id" href="#"
              class="list-group-item list-group-item-action border-bottom d-flex"
              :class="{ active: selected && selected.id === c.id }"
              @click.prevent="openClaim(c)">
              <div class="claim-thumb mr-2">
                <img v-if="c.thumbnail" :src="c.thumbnail" alt="" />
                <div v-else class="claim-thumb-ph"><i class="fas fa-image"></i></div>
              </div>
              <div class="flex-grow-1 small" style="min-width:0">
                <div><span class="text-muted">Tipo:</span> {{ c.type_label }}</div>
                <div><span class="text-muted">Estágio:</span> {{ c.stage_label }}</div>
                <div><span class="text-muted">Status:</span>
                  <strong :class="c.status === 'opened' ? 'text-warning' : 'text-muted'">{{ c.status_label }}</strong>
                </div>
                <div class="text-muted">Última Interação: {{ c.last_interaction ? formatDateTime(c.last_interaction) : '—' }}</div>
              </div>
            </a>
          </div>
        </div>
      </div>

      <!-- Coluna central: detalhe -->
      <div class="col-md-5">
        <div v-if="loadingDetail" class="text-center text-muted py-5"><i class="fas fa-spinner fa-spin fa-2x"></i></div>
        <div v-else-if="!selected" class="text-center text-muted py-5">
          <i class="fas fa-gavel fa-2x mb-2"></i><p>Selecione uma reclamação.</p>
        </div>
        <div v-else class="card">
          <div class="card-body">
            <h6 class="mb-1">{{ selected.quantity ? selected.quantity + 'x ' : '' }}{{ selected.item_title || '—' }}</h6>
            <div class="small text-muted mb-1">
              <span v-if="selected.platform_order_id">#{{ selected.platform_order_id }}
                <i class="fas fa-copy ml-1" role="button" @click="copy(selected.platform_order_id)"></i> · </span>
              <span v-if="selected.buyer_nickname">{{ selected.buyer_nickname }} · </span>
              <span v-if="selected.item_id">{{ selected.item_id }}
                <i class="fas fa-copy ml-1" role="button" @click="copy(selected.item_id)"></i> · </span>
              <span v-if="selected.amount != null">{{ formatCurrency(selected.amount) }}</span>
            </div>
            <div class="small text-muted mb-1">
              Reclamação {{ selected.platform_claim_id }}
              <i class="fas fa-copy ml-1" role="button" @click="copy(selected.platform_claim_id)"></i>
              · Aberta em {{ selected.ml_date_created ? formatDateTime(selected.ml_date_created) : '—' }}
            </div>
            <div class="mb-2">
              <span v-if="repBadge(selected)" class="badge mr-1" :class="repBadge(selected).cls">{{ repBadge(selected).txt }}</span>
              <span class="small">Motivo: {{ selected.reason_label || selected.problem || selected.reason_id || '—' }}</span>
            </div>

            <!-- Ações -->
            <div class="mb-2" v-if="actionButtons.length || selected.has_return">
              <button v-for="name in actionButtons" :key="name"
                class="btn btn-sm btn-outline-primary mr-1 mb-1" :disabled="actionBusy"
                @click="runAction(name)">
                {{ ACTION_LABELS[name] || name }}
              </button>
              <button v-if="selected.has_return" class="btn btn-sm btn-outline-info mr-1 mb-1" @click="viewReturn">
                <i class="fas fa-box mr-1"></i>Ver Detalhes da Devolução
              </button>
              <button class="btn btn-sm btn-outline-secondary mr-1 mb-1" @click="viewDetails">
                <i class="fas fa-info-circle mr-1"></i>Resolução Esperada
              </button>
            </div>

            <!-- Sub-abas de mensagens -->
            <ul class="nav nav-pills nav-sm mb-2">
              <li class="nav-item"><a class="nav-link py-1 px-2" :class="{ active: msgChannel === 'complainant' }"
                href="#" @click.prevent="msgChannel = 'complainant'">Comprador</a></li>
              <li class="nav-item"><a class="nav-link py-1 px-2" :class="{ active: msgChannel === 'mediator' }"
                href="#" @click.prevent="msgChannel = 'mediator'">Mediador</a></li>
            </ul>

            <div style="max-height:38vh;overflow-y:auto" class="mb-2">
              <div v-if="!channelMessages.length" class="text-muted small text-center py-3">Sem mensagens neste canal.</div>
              <div v-for="m in channelMessages" :key="m.id" class="mb-2"
                :class="m.sender_role === 'respondent' ? 'text-right' : ''">
                <div class="d-inline-block p-2 rounded small"
                  :class="m.sender_role === 'respondent' ? 'bg-primary text-white' : 'bg-light border'"
                  style="max-width:85%">
                  <div v-if="m.sender_role !== 'respondent'" class="font-weight-bold">
                    {{ m.sender_role === 'mediator' ? 'Mediador' : (selected.buyer_nickname || 'Comprador') }}
                  </div>
                  <div style="white-space:pre-wrap">{{ m.text }}</div>
                  <div v-for="(att, i) in m.attachments" :key="i" class="small font-italic">
                    <i class="fas fa-paperclip"></i> {{ att.filename || att }}
                  </div>
                  <div class="text-muted" style="font-size:10px">{{ m.sent_at ? formatDateTime(m.sent_at) : '' }}</div>
                </div>
              </div>
            </div>

            <!-- Resposta -->
            <div v-if="selected.status === 'opened'">
              <textarea v-model="replyText" class="form-control form-control-sm" rows="2" maxlength="350"
                placeholder="Digite sua mensagem aqui..."></textarea>
              <div class="d-flex justify-content-between align-items-center mt-1">
                <div>
                  <button class="btn btn-sm btn-outline-secondary" title="Mensagens Prontas" @click="showTemplates = true">
                    <i class="fas fa-comment-dots"></i>
                  </button>
                  <small class="text-muted ml-2">{{ replyRemaining }} caracteres restantes</small>
                </div>
                <button class="btn btn-sm btn-success" :disabled="sending || !replyText.trim()" @click="doReply">
                  <i :class="['fas', sending ? 'fa-spinner fa-spin' : 'fa-paper-plane', 'mr-1']"></i>Enviar
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Coluna direita: histórico -->
      <div class="col-md-3">
        <div v-if="selected" class="card">
          <div class="card-header py-2"><strong>Histórico de Ações</strong></div>
          <div class="card-body p-2" style="max-height:70vh;overflow-y:auto">
            <div v-if="!selected.actions_history?.length" class="text-muted small">Sem histórico.</div>
            <div v-for="a in selected.actions_history" :key="a.id" class="border rounded p-2 mb-2 small">
              <div class="font-weight-bold">{{ a.label_pt }}</div>
              <div class="text-muted">Quem: {{ a.player_role_label }}</div>
              <div v-if="a.claim_stage_label" class="text-muted">Estágio: {{ a.claim_stage_label }}</div>
              <div v-if="a.claim_status_label" class="text-muted">Status: {{ a.claim_status_label }}</div>
              <div class="text-muted">Data: {{ a.date_created ? formatDateTime(a.date_created) : '—' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Mensagens Prontas -->
    <TemplatesModal v-if="showTemplates" @close="showTemplates = false" @use="applyTemplate" />

    <!-- Modais de ação -->
    <div v-if="modal.type && modal.type !== 'returns' && modal.type !== 'details'"
      class="cad-overlay" @click.self="modal.type = null">
      <div class="cad-modal-sm card">
        <div class="card-header py-2 d-flex align-items-center">
          <strong>
            <span v-if="modal.type === 'partial'">Reembolso Parcial</span>
            <span v-else-if="modal.type === 'return-review'">Revisar Devolução</span>
            <span v-else-if="modal.type === 'tracking'">Código de Rastreio</span>
            <span v-else>Confirmar ação</span>
          </strong>
          <button class="btn btn-sm btn-light ml-auto" @click="modal.type = null"><i class="fas fa-times"></i></button>
        </div>
        <div class="card-body">
          <!-- Reembolso parcial -->
          <div v-if="modal.type === 'partial'">
            <label class="small mb-1">Valor a reembolsar (R$)</label>
            <input v-model="modal.amount" type="number" min="0" step="0.01" class="form-control form-control-sm" />
          </div>
          <!-- Revisar devolução -->
          <div v-else-if="modal.type === 'return-review'">
            <p class="small mb-2">A devolução chegou conforme esperado?</p>
            <div class="form-check"><input id="rrOk" type="radio" class="form-check-input" :value="false" v-model="modal.problem" />
              <label for="rrOk" class="form-check-label">Tudo Certo</label></div>
            <div class="form-check mb-2"><input id="rrBad" type="radio" class="form-check-input" :value="true" v-model="modal.problem" />
              <label for="rrBad" class="form-check-label">Há um Problema</label></div>
            <textarea v-if="modal.problem" v-model="modal.problemNote" class="form-control form-control-sm"
              rows="3" placeholder="Descreva o problema com a devolução..."></textarea>
          </div>
          <!-- Código de rastreio -->
          <div v-else-if="modal.type === 'tracking'">
            <label class="small mb-1">Código de rastreamento</label>
            <input v-model="modal.tracking" class="form-control form-control-sm" />
          </div>
          <!-- Confirmação simples -->
          <p v-else class="mb-0">{{ modal.confirmText }}</p>
        </div>
        <div class="card-footer text-right">
          <button class="btn btn-sm btn-outline-secondary mr-1" @click="modal.type = null">Cancelar</button>
          <button class="btn btn-sm btn-primary" :disabled="actionBusy" @click="confirmModal">
            <i v-if="actionBusy" class="fas fa-spinner fa-spin mr-1"></i>Confirmar
          </button>
        </div>
      </div>
    </div>

    <!-- Detalhes da Devolução -->
    <div v-if="modal.type === 'returns'" class="cad-overlay" @click.self="modal.type = null">
      <div class="cad-modal-sm card">
        <div class="card-header py-2 d-flex align-items-center">
          <strong>Detalhes da Devolução</strong>
          <button class="btn btn-sm btn-light ml-auto" @click="modal.type = null"><i class="fas fa-times"></i></button>
        </div>
        <div class="card-body">
          <div v-if="!modal.returns" class="text-center text-muted"><i class="fas fa-spinner fa-spin"></i></div>
          <pre v-else class="small mb-0" style="white-space:pre-wrap">{{ JSON.stringify(modal.returns, null, 2) }}</pre>
        </div>
      </div>
    </div>

    <!-- Resolução Esperada / detalhes do claim -->
    <div v-if="modal.type === 'details' && selected" class="cad-overlay" @click.self="modal.type = null">
      <div class="cad-modal-sm card">
        <div class="card-header py-2 d-flex align-items-center">
          <strong>Resolução Esperada</strong>
          <button class="btn btn-sm btn-light ml-auto" @click="modal.type = null"><i class="fas fa-times"></i></button>
        </div>
        <div class="card-body small">
          <p v-if="selected.title"><strong>{{ selected.title }}</strong></p>
          <p v-if="selected.problem"><span class="text-muted">Problema:</span> {{ selected.problem }}</p>
          <p v-if="selected.reason_label"><span class="text-muted">Motivo:</span> {{ selected.reason_label }}</p>
          <p class="mb-0 text-muted">Estágio: {{ selected.stage_label }} · Status: {{ selected.status }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cad-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1085; }
.cad-modal-sm { width: 460px; max-width: 95vw; margin: 0; max-height: 90vh; overflow-y: auto; }
.claim-thumb { width: 56px; height: 56px; flex: 0 0 56px; }
.claim-thumb img { width: 56px; height: 56px; object-fit: cover; border: 1px solid #e3e6ea; border-radius: 6px; }
.claim-thumb-ph {
  width: 56px; height: 56px; border: 1px solid #e3e6ea; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; color: #c4c9d0; background: #f7f8fa;
}
</style>
