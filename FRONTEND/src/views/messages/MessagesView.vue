<template>
  <div>
    <!-- Abas: Mensagens | Reclamações -->
    <ul class="nav nav-tabs mb-2">
      <li class="nav-item">
        <a class="nav-link" :class="{ active: activeTab === 'messages' }" href="#" @click.prevent="activeTab = 'messages'">
          <i class="fas fa-comments mr-1"></i>Mensagens
        </a>
      </li>
      <li class="nav-item">
        <a class="nav-link" :class="{ active: activeTab === 'claims' }" href="#" @click.prevent="activeTab = 'claims'">
          <i class="fas fa-gavel mr-1"></i>Reclamações
          <span v-if="claimsOpen > 0" class="badge badge-danger ml-1">{{ claimsOpen }}</span>
        </a>
      </li>
    </ul>

    <div v-show="activeTab === 'messages'">
    <!-- Filtros superiores -->
    <div class="card card-outline card-primary mb-2">
      <div class="card-header py-2 d-flex flex-wrap gap-2 align-items-center">
        <h3 class="card-title mr-3">
          <i class="fas fa-comments mr-1"></i> Central de Atendimento
        </h3>
        <select v-model="filters.account_id" class="form-control form-control-sm" style="width:220px" @change="applyFilters">
          <option value="">Todas as contas</option>
          <option v-for="a in accounts" :key="a.id" :value="a.id">
            {{ a.description || a.platform_username || `Conta #${a.id}` }}
          </option>
        </select>
        <select v-model="filters.thread_type" class="form-control form-control-sm" style="width:160px" @change="applyFilters">
          <option value="">Todos os tipos</option>
          <option value="post_sale">Pós-venda</option>
          <option value="pre_sale_question">Pré-venda (Perguntas)</option>
        </select>
        <select v-model="filters.status" class="form-control form-control-sm" style="width:150px" @change="applyFilters">
          <option value="">Todos os status</option>
          <option value="open">Em aberto</option>
          <option value="pending_reply">Aguardando resposta</option>
          <option value="answered">Respondida</option>
          <option value="closed">Encerrada</option>
        </select>
        <div class="form-check ml-2 mb-0">
          <input id="chkUnread" type="checkbox" class="form-check-input" v-model="filters.unread_only" @change="applyFilters" />
          <label for="chkUnread" class="form-check-label small">Não lidas</label>
        </div>
        <div v-if="filters.account_id" class="ml-auto">
          <div class="btn-group">
            <button
              class="btn btn-sm btn-outline-secondary"
              @click="syncAccount"
              :disabled="syncing || importingHistory"
              title="Busca mensagens dos pedidos recentes e perguntas em aberto"
            >
              <i :class="['fas', syncing ? 'fa-spinner fa-spin' : 'fa-sync-alt', 'mr-1']"></i>
              {{ syncing ? 'Sincronizando...' : 'Sincronizar' }}
            </button>
            <button
              type="button"
              class="btn btn-sm btn-outline-secondary dropdown-toggle dropdown-toggle-split"
              data-toggle="dropdown"
              :disabled="syncing || importingHistory"
            ></button>
            <div class="dropdown-menu dropdown-menu-right">
              <h6 class="dropdown-header">Sincronização</h6>
              <button class="dropdown-item" @click="syncAccount" :disabled="syncing">
                <i class="fas fa-sync-alt mr-2 text-secondary"></i>
                <div>
                  <div class="font-weight-bold">Sincronizar agora</div>
                  <small class="text-muted">Mensagens dos pedidos + perguntas recentes</small>
                </div>
              </button>
              <div class="dropdown-divider"></div>
              <button class="dropdown-item" @click="importHistory" :disabled="importingHistory">
                <i class="fas fa-history mr-2 text-info"></i>
                <div>
                  <div class="font-weight-bold">Histórico de perguntas</div>
                  <small class="text-muted">Importa perguntas dos últimos 30 dias</small>
                </div>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Painel split -->
    <div class="row no-gutters" style="min-height: 75vh">
      <!-- Coluna esquerda: lista de conversas -->
      <div class="col-12 col-md-4 border-right" style="overflow-y:auto; max-height:75vh">
        <div v-if="store.loading && !store.threads.length" class="text-center py-5 text-muted">
          <i class="fas fa-spinner fa-spin fa-2x"></i>
        </div>
        <div v-else-if="!store.threads.length" class="text-center py-5 text-muted">
          <i class="fas fa-inbox fa-3x mb-3 d-block"></i>
          <p>Nenhuma conversa encontrada.</p>
          <p class="small">Sincronize uma conta para carregar as mensagens.</p>
        </div>
        <div v-else>
          <div
            v-for="thread in store.threads"
            :key="thread.id"
            :class="['thread-item px-3 py-2 border-bottom', activeId === thread.id && 'thread-active', thread.unread_count > 0 && 'thread-unread']"
            @click="selectThread(thread)"
            style="cursor:pointer"
          >
            <div class="d-flex justify-content-between align-items-start">
              <div class="d-flex align-items-center" style="gap:6px">
                <span :class="['badge badge-sm', thread.platform === 'mercadolivre' ? 'badge-primary' : 'badge-warning']">
                  {{ platformLabel(thread.platform) }}
                </span>
                <span :class="['badge badge-sm', thread.thread_type === 'post_sale' ? 'badge-secondary' : 'badge-info']">
                  <i :class="thread.thread_type === 'post_sale' ? 'fas fa-lock' : 'fas fa-question-circle'"></i>
                </span>
              </div>
              <span v-if="thread.unread_count > 0" class="badge badge-danger badge-pill">{{ thread.unread_count }}</span>
            </div>
            <div class="mt-1">
              <span :class="['d-block small', thread.unread_count > 0 ? 'font-weight-bold' : '']">
                {{ thread.buyer_nickname || 'Comprador' }}
              </span>
              <span v-if="thread.item_title" class="d-block small text-muted text-truncate" style="max-width:200px">
                {{ thread.item_title }}
              </span>
              <span class="d-block small text-muted text-truncate" style="max-width:200px">
                {{ thread.last_message_preview || '...' }}
              </span>
            </div>
            <div class="d-flex justify-content-between mt-1">
              <small class="text-muted">{{ timeAgo(thread.last_message_at) }}</small>
              <small :class="statusClass(thread.status)">{{ statusLabel(thread.status) }}</small>
            </div>
          </div>
          <!-- Carregar mais -->
          <div v-if="store.hasMore" class="text-center py-2">
            <button class="btn btn-sm btn-outline-secondary" @click="loadMore" :disabled="store.loading">
              <i class="fas fa-chevron-down mr-1"></i> Carregar mais
            </button>
          </div>
        </div>
      </div>

      <!-- Coluna direita: thread ativa -->
      <div class="col-12 col-md-8 d-flex flex-column" style="max-height:75vh">
        <!-- Sem thread selecionada -->
        <div v-if="!activeId" class="flex-grow-1 d-flex flex-column align-items-center justify-content-center text-muted">
          <i class="fas fa-comments fa-4x mb-3"></i>
          <p>Selecione uma conversa para ver as mensagens.</p>
        </div>

        <template v-else>
          <!-- Cabeçalho da thread -->
          <div class="px-3 py-2 border-bottom bg-light d-flex align-items-center" style="gap:10px">
            <div>
              <strong>{{ store.activeThread?.buyer_nickname || 'Comprador' }}</strong>
              <span v-if="store.activeThread?.platform_order_id" class="text-muted small ml-2">
                Pedido #{{ store.activeThread.platform_order_id }}
              </span>
              <span v-if="store.activeThread?.item_title" class="d-block small text-muted">
                {{ store.activeThread.item_title }}
              </span>
            </div>
            <span :class="['badge ml-auto', store.activeThread?.platform === 'mercadolivre' ? 'badge-primary' : 'badge-warning']">
              {{ platformLabel(store.activeThread?.platform) }}
            </span>
            <span :class="['badge', store.activeThread?.thread_type === 'post_sale' ? 'badge-secondary' : 'badge-info']">
              {{ store.activeThread?.thread_type === 'post_sale' ? 'Pós-venda' : 'Pergunta' }}
            </span>
          </div>

          <!-- Mensagens -->
          <div class="flex-grow-1 px-3 py-2 overflow-auto" ref="msgContainer" style="background:#f8f9fa">
            <div v-if="store.loadingThread" class="text-center py-4">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else>
              <div
                v-for="msg in store.activeMessages"
                :key="msg.id"
                :class="['d-flex mb-3', msg.from_role === 'buyer' ? 'justify-content-start' : 'justify-content-end']"
              >
                <div
                  :class="['message-bubble px-3 py-2', msg.from_role === 'buyer' ? 'bubble-buyer' : msg.from_role === 'ai' ? 'bubble-ai' : 'bubble-seller']"
                  style="max-width:80%"
                >
                  <div class="small font-weight-bold mb-1" :class="msg.from_role === 'buyer' ? 'text-primary' : msg.from_role === 'ai' ? 'text-success' : 'text-secondary'">
                    <i v-if="msg.from_role === 'ai'" class="fas fa-robot mr-1"></i>
                    {{ roleLabel(msg.from_role) }}
                  </div>
                  <p class="mb-1" style="white-space:pre-wrap">{{ msg.text }}</p>
                  <small class="text-muted">{{ formatDateTime(msg.sent_at) }}</small>
                </div>
              </div>
            </div>
          </div>

          <!-- Área de resposta -->
          <div class="border-top px-3 py-2 bg-white">
            <!-- Sugestão IA -->
            <div v-if="store.aiSuggestion" class="alert alert-success py-2 mb-2 small">
              <i class="fas fa-robot mr-1"></i>
              <strong>Sugestão da IA</strong> — você pode editar antes de enviar.
            </div>

            <textarea
              v-model="replyText"
              class="form-control form-control-sm mb-2"
              rows="3"
              placeholder="Digite sua resposta aqui..."
              :disabled="store.sendingReply"
            ></textarea>

            <div class="d-flex justify-content-between align-items-center">
              <button
                class="btn btn-sm btn-outline-success"
                @click="requestAISuggestion"
                :disabled="store.loadingAI || store.sendingReply"
              >
                <i :class="['fas', store.loadingAI ? 'fa-spinner fa-spin' : 'fa-robot', 'mr-1']"></i>
                {{ store.loadingAI ? 'Gerando...' : 'Sugerir com IA' }}
              </button>
              <div style="gap:6px" class="d-flex">
                <button class="btn btn-sm btn-outline-secondary" title="Mensagens Prontas" @click="showTemplates = true">
                  <i class="fas fa-comment-dots"></i>
                </button>
                <button v-if="replyText" class="btn btn-sm btn-outline-secondary" @click="replyText = ''; store.aiSuggestion = ''">
                  Limpar
                </button>
                <button
                  class="btn btn-sm btn-primary"
                  @click="sendReply"
                  :disabled="!replyText.trim() || store.sendingReply"
                >
                  <i :class="['fas', store.sendingReply ? 'fa-spinner fa-spin' : 'fa-paper-plane', 'mr-1']"></i>
                  {{ store.sendingReply ? 'Enviando...' : 'Enviar Resposta' }}
                </button>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
    </div><!-- /aba Mensagens -->

    <div v-show="activeTab === 'claims'">
      <ClaimsTab :accounts="accounts" @open-count="claimsOpen = $event" />
    </div>

    <TemplatesModal v-if="showTemplates" @close="showTemplates = false" @use="applyTemplate" />
  </div>
</template>

<script setup>
import { ref, reactive, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useMessagesStore } from '@/stores/messages'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import { formatDateTime } from '@/utils/formatters'
import { useSocket } from '@/composables/useSocket'
import ClaimsTab from '@/components/atendimento/ClaimsTab.vue'
import TemplatesModal from '@/components/atendimento/TemplatesModal.vue'

const store = useMessagesStore()
const toast = useToast()

const activeTab = ref('messages')
const claimsOpen = ref(0)
const showTemplates = ref(false)
function applyTemplate(body) {
  replyText.value = (replyText.value ? replyText.value + '\n' : '') + body
  showTemplates.value = false
}
const accounts = ref([])
const activeId = ref(null)
const replyText = ref('')
const syncing = ref(false)
const importingHistory = ref(false)
const msgContainer = ref(null)

// Sugestão da IA preenche o textarea ao ser gerada
watch(() => store.aiSuggestion, (val) => {
  if (val) replyText.value = val
})

// Scroll automático ao receber novas mensagens
watch(() => store.activeMessages.length, () => {
  nextTick(() => {
    if (msgContainer.value) {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    }
  })
})

const filters = reactive({
  account_id: '',
  thread_type: '',
  status: '',
  unread_only: false,
})

onMounted(async () => {
  await loadAccounts()
  await store.fetchThreads(activeFilters())

  // Socket.IO: recebe novas mensagens em tempo real
  const { socket } = useSocket()
  if (socket) {
    socket.on('new_message', (data) => {
      store.addIncomingMessage(data)
    })
  }
})

onUnmounted(() => {
  const { socket } = useSocket()
  if (socket) socket.off('new_message')
})

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    accounts.value = (data.items || data).filter(a => a.platform === 'mercadolivre' || a.platform === 'shopee')
  } catch (e) {
    toast.error('Erro ao carregar contas de marketplace.')
  }
}

function activeFilters() {
  const f = {}
  if (filters.account_id) f.account_id = filters.account_id
  if (filters.thread_type) f.thread_type = filters.thread_type
  if (filters.status) f.status = filters.status
  if (filters.unread_only) f.unread_only = true
  return f
}

async function applyFilters() {
  activeId.value = null
  store.activeThread = null
  store.activeMessages = []
  await store.fetchThreads(activeFilters())
}

async function loadMore() {
  await store.loadMore(activeFilters())
}

async function selectThread(thread) {
  activeId.value = thread.id
  replyText.value = ''
  await store.fetchThread(thread.id)
}

async function sendReply() {
  if (!replyText.value.trim()) return
  const wasAISuggestion = !!store.aiSuggestion && replyText.value === store.aiSuggestion
  try {
    await store.sendReply(activeId.value, replyText.value, wasAISuggestion ? store.aiSuggestion : null)
    replyText.value = ''
    toast.success('Resposta enviada com sucesso!')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar resposta.')
  }
}

async function requestAISuggestion() {
  try {
    await store.suggestAI(activeId.value)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao gerar sugestão de IA.')
  }
}

async function syncAccount() {
  syncing.value = true
  try {
    await store.syncAccount(filters.account_id)
    toast.info('Sincronização iniciada em background. Atualizando em 5 segundos...')
    setTimeout(() => applyFilters(), 5000)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar conta.')
  } finally {
    syncing.value = false
  }
}

async function importHistory() {
  importingHistory.value = true
  try {
    await api.post(`/messages/sync/${filters.account_id}/questions-history?days=30`)
    toast.info('Importação de perguntas (30 dias) iniciada. Atualizando em 8 segundos...')
    setTimeout(() => applyFilters(), 8000)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao importar histórico de perguntas.')
  } finally {
    importingHistory.value = false
  }
}

// Helpers de formatação
function platformLabel(p) {
  if (p === 'mercadolivre') return 'ML'
  if (p === 'shopee') return 'Shopee'
  if (p === 'amazon') return 'Amazon'
  return p || 'ML'
}

function statusLabel(s) {
  const labels = { open: 'Aberta', pending_reply: 'Aguardando', answered: 'Respondida', closed: 'Encerrada' }
  return labels[s] || s
}

function statusClass(s) {
  const cls = { open: 'text-primary', pending_reply: 'text-warning', answered: 'text-success', closed: 'text-muted' }
  return cls[s] || 'text-muted'
}

function roleLabel(role) {
  if (role === 'buyer') return 'Comprador'
  if (role === 'seller') return 'Você'
  if (role === 'ai') return 'IA'
  return role
}

function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'agora'
  if (m < 60) return `${m}min`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h`
  return `${Math.floor(h / 24)}d`
}
</script>

<style scoped>
.thread-item:hover { background: #f4f6f9; }
.thread-active { background: #e8f0fe !important; border-left: 3px solid #4e73df; }
.thread-unread { background: #fff8e1; }

.message-bubble {
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,.08);
}
.bubble-buyer {
  background: #ffffff;
  border: 1px solid #dee2e6;
}
.bubble-seller {
  background: #d1ecf1;
  border: 1px solid #bee5eb;
}
.bubble-ai {
  background: #d4edda;
  border: 1px solid #c3e6cb;
}
</style>
