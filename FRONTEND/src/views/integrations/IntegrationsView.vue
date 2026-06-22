<template>
  <div>
    <!-- Cabeçalho -->
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h4 class="mb-0"><i class="fas fa-plug mr-2"></i> Minhas Contas de Marketplace</h4>
      <button class="btn btn-primary" @click="openNewContaModal">
        <i class="fas fa-plus mr-1"></i> Nova Conta
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-5">
      <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
    </div>

    <!-- Sem contas -->
    <div v-else-if="accounts.length === 0" class="card">
      <div class="card-body text-center py-5 text-muted">
        <i class="fas fa-unlink fa-3x mb-3 d-block"></i>
        <p class="mb-1">Nenhuma conta cadastrada.</p>
        <small>Clique em "Nova Conta" para cadastrar e conectar uma conta de marketplace.</small>
      </div>
    </div>

    <!-- Lista de CONTAs -->
    <div v-else class="row">
      <div v-for="acc in accounts" :key="acc.id" class="col-md-4 mb-4">
        <div class="card shadow-sm h-100" :class="{ 'border-success': acc.is_active && acc.otp_verified }">
          <div class="card-header d-flex align-items-center">
            <span :class="platformBadge(acc.platform)" class="badge mr-2">{{ platformLabel(acc.platform) }}</span>
            <span class="font-weight-bold text-truncate flex-grow-1" :title="acc.platform_username || acc.description">
              {{ acc.platform_username || acc.description || acc.email }}
            </span>
            <button class="btn btn-xs btn-outline-primary ml-1" title="Editar" @click="openEditModal(acc)">
              <i class="fas fa-edit"></i>
            </button>
            <button v-if="canManage(acc)" class="btn btn-xs btn-outline-secondary ml-1"
                    title="Gerenciar colaboradores" @click="openCollab(acc)">
              <i class="fas fa-user-friends"></i>
            </button>
            <button class="btn btn-xs btn-outline-danger ml-1" title="Desconectar" @click="disconnect(acc)">
              <i class="fas fa-unlink"></i>
            </button>
          </div>

          <div class="card-body">
            <p v-if="acc.platform === 'mercadolivre' && (acc.power_seller_status || acc.level_id)" class="mb-1 small">
              <span v-if="acc.power_seller_status" class="badge mr-1"
                    :style="medalStyle(acc.power_seller_status)"
                    :title="`Mercado Líder ${medalLabel(acc.power_seller_status)}`">
                <i class="fas fa-medal mr-1"></i>{{ medalLabel(acc.power_seller_status) }}
              </span>
              <span v-if="acc.level_id" class="badge"
                    :style="levelStyle(acc.level_id)"
                    :title="`Reputação: ${levelLabel(acc.level_id)}`">
                {{ levelLabel(acc.level_id) }}
              </span>
            </p>
            <p v-if="acc.cmig_id" class="mb-1 small">
              <i class="fas fa-id-card mr-1 text-primary"></i>
              <span class="text-primary font-weight-bold">{{ cmigName(acc.cmig_id) }}</span>
            </p>
            <p v-else class="mb-1 small text-warning">
              <i class="fas fa-exclamation-triangle mr-1"></i>Sem CMIG vinculada
            </p>
            <p v-if="acc.email" class="mb-1 text-muted small"><i class="fas fa-envelope mr-1"></i>{{ acc.email }}</p>
            <p v-if="acc.phone" class="mb-1 text-muted small"><i class="fas fa-phone mr-1"></i>{{ acc.phone }}</p>
            <p v-if="acc.last_sync_at" class="mb-2 text-muted small">
              <i class="fas fa-sync mr-1"></i>Última sinc: {{ formatDateTime(acc.last_sync_at) }}
            </p>

            <!-- Status OAuth / conexão -->
            <div>
              <!-- Alerta: token revogado / precisa reconectar -->
              <div v-if="acc.requires_reauth" class="alert alert-danger py-2 mb-2">
                <i class="fas fa-exclamation-circle mr-1"></i>
                <strong>Token inválido.</strong> Reconecte a conta abaixo para restaurar a integração.
              </div>

              <div v-if="acc.is_active && !acc.requires_reauth" class="d-flex align-items-center mb-2">
                <span class="badge badge-success mr-2">Conectado</span>
                <small v-if="acc.platform_username" class="text-muted">@{{ acc.platform_username }}</small>
              </div>
              <div v-else-if="!acc.is_active" class="alert alert-secondary py-2 mb-2">
                <i class="fas fa-plug mr-1"></i> Não conectado via OAuth.
              </div>

              <!-- Botão de conexão por plataforma -->
              <button v-if="acc.platform === 'mercadolivre'"
                      class="btn btn-sm btn-warning btn-block" @click="connectOAuth(acc)">
                <i class="fas fa-link mr-1"></i>
                {{ acc.is_active ? 'Reconectar Mercado Livre' : 'Conectar Mercado Livre' }}
              </button>
              <button v-else-if="acc.platform === 'shopee'"
                      class="btn btn-sm btn-danger btn-block" @click="connectOAuth(acc)">
                <i class="fas fa-link mr-1"></i>
                {{ acc.is_active ? 'Reconectar Shopee' : 'Conectar Shopee' }}
              </button>
              <button v-else-if="acc.platform === 'bling'"
                      class="btn btn-sm btn-info btn-block" @click="openBlingModal(acc)">
                <i class="fas fa-key mr-1"></i>
                {{ acc.is_active ? 'Atualizar API Key' : 'Configurar Bling' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Modal: Nova Conta ─────────────────────────────────────────────── -->
    <div v-if="modal.newConta" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-plus-circle mr-2"></i> Nova Conta de Marketplace</h5>
            <button class="close" @click="modal.newConta = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="newContaError" class="alert alert-danger">{{ newContaError }}</div>
            <div class="form-group">
              <label>Plataforma <span class="text-danger">*</span></label>
              <select v-model="newContaForm.platform" class="form-control" required>
                <option value="">Selecione...</option>
                <option value="mercadolivre">Mercado Livre</option>
                <option value="shopee">Shopee</option>
                <option value="bling">Bling V3</option>
              </select>
            </div>
            <div class="form-group">
              <label>E-mail da conta <span class="text-danger">*</span></label>
              <input v-model="newContaForm.email" type="email" class="form-control"
                     placeholder="email@marketplace.com" required />
            </div>
            <div class="form-group">
              <label>Telefone / celular da conta <span class="text-danger">*</span></label>
              <input v-model="newContaForm.phone" class="form-control" placeholder="(11) 91234-5678" required />
            </div>
            <div class="form-group">
              <label>Conta MIG (CMIG) <span class="text-danger">*</span></label>
              <select v-model="newContaForm.cmig_id" class="form-control" required>
                <option value="">Selecione a CMIG...</option>
                <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }} ({{ c.cnpj }})</option>
              </select>
            </div>
            <div class="form-group">
              <label>Descrição (opcional)</label>
              <input v-model="newContaForm.description" class="form-control" placeholder="Ex: Loja Principal ML" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="modal.newConta = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="savingNewConta" @click="createConta">
              <i v-if="savingNewConta" class="fas fa-spinner fa-spin mr-1"></i>
              {{ savingNewConta ? 'Cadastrando...' : 'Cadastrar Conta' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Modal: Editar Conta ─────────────────────────────────────────── -->
    <div v-if="modal.edit" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-edit mr-2"></i> Editar Conta de Marketplace</h5>
            <button class="close" @click="modal.edit = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="editError" class="alert alert-danger">{{ editError }}</div>
            <div class="form-group">
              <label>Conta MIG (CMIG) <span class="text-danger">*</span></label>
              <select v-model="editForm.cmig_id" class="form-control">
                <option value="">Selecione a CMIG...</option>
                <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }} ({{ c.cnpj }})</option>
              </select>
            </div>
            <div class="form-group">
              <label>Descrição</label>
              <input v-model="editForm.description" class="form-control" placeholder="Ex: Loja Principal ML" />
            </div>
            <div class="form-group">
              <div class="custom-control custom-switch">
                <input type="checkbox" class="custom-control-input" id="editIsOfficialStore"
                       v-model="editForm.is_official_store" />
                <label class="custom-control-label" for="editIsOfficialStore">
                  Loja Oficial no Mercado Livre
                </label>
              </div>
              <small class="text-muted">Ative apenas para contas com <em>family_name</em> — permite editar o título do anúncio via API.</small>
            </div>

            <!-- Capacidades de Envio (só ML) -->
            <div v-if="editTarget && editTarget.platform === 'mercadolivre'" class="form-group mb-0">
              <hr class="mt-3 mb-2" />
              <label class="d-block mb-2">
                <i class="fas fa-truck text-info mr-1"></i>
                <strong>Capacidades de Envio (Mercado Livre)</strong>
              </label>
              <div v-if="capsLoading" class="text-muted small">
                <i class="fas fa-spinner fa-spin mr-1"></i>Detectando...
              </div>
              <template v-else>
                <div class="small text-muted mb-2">
                  Status detectado automaticamente:
                  <span class="ml-1">
                    Flex
                    <i :class="['fas', capsState.has_flex_detected ? 'fa-check-circle text-success' : 'fa-times-circle text-muted']"></i>
                  </span>
                  <span class="ml-2">
                    Full
                    <i :class="['fas', capsState.has_full_detected ? 'fa-check-circle text-success' : 'fa-times-circle text-muted']"></i>
                  </span>
                  <button type="button" class="btn btn-link btn-sm p-0 ml-2" @click="refreshCaps" :disabled="capsRefreshing">
                    <i :class="['fas', capsRefreshing ? 'fa-spinner fa-spin' : 'fa-sync-alt']" style="font-size:11px"></i>
                    Re-detectar
                  </button>
                </div>

                <!-- Override Flex -->
                <div class="mb-2">
                  <label class="small mb-1">Mercado Envios Flex</label>
                  <div class="btn-group btn-group-sm d-flex">
                    <button type="button"
                            :class="['btn', editForm.has_flex_override === null ? 'btn-secondary' : 'btn-outline-secondary']"
                            @click="editForm.has_flex_override = null">
                      Auto ({{ capsState.has_flex_detected ? 'sim' : 'não' }})
                    </button>
                    <button type="button"
                            :class="['btn', editForm.has_flex_override === true ? 'btn-warning' : 'btn-outline-warning']"
                            @click="editForm.has_flex_override = true">
                      <i class="fas fa-bolt mr-1"></i>Disponível
                    </button>
                    <button type="button"
                            :class="['btn', editForm.has_flex_override === false ? 'btn-dark' : 'btn-outline-dark']"
                            @click="editForm.has_flex_override = false">
                      Indisponível
                    </button>
                  </div>
                </div>

                <!-- Override Full -->
                <div class="mb-0">
                  <label class="small mb-1">Mercado Envios Full</label>
                  <div class="btn-group btn-group-sm d-flex">
                    <button type="button"
                            :class="['btn', editForm.has_full_override === null ? 'btn-secondary' : 'btn-outline-secondary']"
                            @click="editForm.has_full_override = null">
                      Auto ({{ capsState.has_full_detected ? 'sim' : 'não' }})
                    </button>
                    <button type="button"
                            :class="['btn', editForm.has_full_override === true ? 'btn-info' : 'btn-outline-info']"
                            @click="editForm.has_full_override = true">
                      <i class="fas fa-warehouse mr-1"></i>Disponível
                    </button>
                    <button type="button"
                            :class="['btn', editForm.has_full_override === false ? 'btn-dark' : 'btn-outline-dark']"
                            @click="editForm.has_full_override = false">
                      Indisponível
                    </button>
                  </div>
                </div>

                <small class="text-muted d-block mt-2">
                  <i class="fas fa-info-circle"></i>
                  Use "Disponível" se sua conta tem Flex/Full habilitado mas o sistema não detectou
                  (acontece em contas novas sem itens publicados).
                </small>
              </template>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="modal.edit = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="savingEdit" @click="saveEdit">
              <i v-if="savingEdit" class="fas fa-spinner fa-spin mr-1"></i>
              {{ savingEdit ? 'Salvando...' : 'Salvar Alterações' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Modal: Bling API Key ──────────────────────────────────────────── -->
    <div v-if="modal.bling" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-key mr-2"></i> Configurar Bling V3</h5>
            <button class="close" @click="modal.bling = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="blingError" class="alert alert-danger">{{ blingError }}</div>
            <div class="form-group">
              <label>API Key do Bling V3 <span class="text-danger">*</span></label>
              <input v-model="blingApiKey" type="text" class="form-control"
                     placeholder="Cole aqui a chave de API do Bling" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="modal.bling = false">Cancelar</button>
            <button class="btn btn-info" :disabled="savingBling || !blingApiKey" @click="saveBling">
              <i v-if="savingBling" class="fas fa-spinner fa-spin mr-1"></i>
              {{ savingBling ? 'Conectando...' : 'Conectar' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <CollaboratorsModal
      :visible="collabModal.visible"
      entity-type="account"
      :entity-id="collabModal.id"
      :entity-label="collabModal.label"
      @close="collabModal.visible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import CollaboratorsModal from '@/components/common/CollaboratorsModal.vue'

const { show: toast } = useToast()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

const accounts = ref([])
const cmigs    = ref([])
const loading  = ref(false)

const collabModal = ref({ visible: false, id: null, label: '' })
function canManage(acc) {
  return isAdmin.value || acc.is_owner === true
}
function openCollab(acc) {
  const label = acc.platform_username || acc.description || acc.email || `Conta #${acc.id}`
  collabModal.value = { visible: true, id: acc.id, label }
}

const modal   = ref({ newConta: false, bling: false, edit: false })
const syncing = ref({})   // { [account_id]: 'orders' | 'listings' | false }

// Nova CONTA
const newContaForm   = ref({ platform: '', email: '', phone: '', description: '', cmig_id: '' })
const newContaError  = ref('')
const savingNewConta = ref(false)

// Editar CONTA
const editTarget = ref(null)
const editForm   = ref({ cmig_id: '', description: '', is_official_store: false, has_flex_override: null, has_full_override: null })
// Estado das capacidades detectadas (lado direito do override) carregadas ao abrir o modal
const capsState = ref({ has_flex_detected: false, has_full_detected: false })
const capsLoading = ref(false)
const capsRefreshing = ref(false)
const editError  = ref('')
const savingEdit = ref(false)

// OTP

// Bling
const blingTarget  = ref(null)
const blingApiKey  = ref('')
const blingError   = ref('')
const savingBling  = ref(false)

async function loadAccounts() {
  loading.value = true
  try {
    // Gestão de contas vê todas, inclusive as de CMIGs inativas.
    const { data } = await api.get('/accounts', { params: { include_inactive_cmig: true } })
    accounts.value = data
  } catch {
    toast('Erro ao carregar contas', 'danger')
  } finally {
    loading.value = false
  }
}

async function loadCmigs() {
  try {
    const { data } = await api.get('/cmigs')
    cmigs.value = Array.isArray(data) ? data : (data?.items || [])
  } catch { }
}

function cmigName(id) {
  const c = cmigs.value.find(c => c.id === id)
  return c ? c.company_name : `CMIG #${id}`
}

function openNewContaModal() {
  newContaForm.value = { platform: '', email: '', phone: '', description: '', cmig_id: '' }
  newContaError.value = ''
  modal.value.newConta = true
}

async function openEditModal(acc) {
  editTarget.value = acc
  editForm.value = {
    cmig_id: acc.cmig_id || '',
    description: acc.description || '',
    is_official_store: !!acc.is_official_store,
    has_flex_override: null,
    has_full_override: null,
  }
  editError.value = ''
  capsState.value = { has_flex_detected: false, has_full_detected: false }
  modal.value.edit = true
  // Capacidades só fazem sentido pra ML — busca em background
  if (acc.platform === 'mercadolivre') {
    capsLoading.value = true
    try {
      const { data } = await api.get(`/accounts/${acc.id}/shipping-capabilities`)
      capsState.value = {
        has_flex_detected: !!data.has_flex_detected,
        has_full_detected: !!data.has_full_detected,
      }
      editForm.value.has_flex_override = data.has_flex_override
      editForm.value.has_full_override = data.has_full_override
    } catch { /* ignore */ } finally {
      capsLoading.value = false
    }
  }
}

async function refreshCaps() {
  if (!editTarget.value) return
  capsRefreshing.value = true
  try {
    const { data } = await api.post(`/accounts/${editTarget.value.id}/shipping-capabilities/refresh`)
    capsState.value = {
      has_flex_detected: !!data.has_flex_detected,
      has_full_detected: !!data.has_full_detected,
    }
    toast('Capacidades re-detectadas', 'success')
  } catch (err) {
    toast(err.response?.data?.detail || 'Erro ao re-detectar', 'error')
  } finally {
    capsRefreshing.value = false
  }
}

async function saveEdit() {
  savingEdit.value = true
  editError.value = ''
  try {
    await api.put(`/accounts/${editTarget.value.id}`, {
      cmig_id: editForm.value.cmig_id || null,
      description: editForm.value.description,
      is_official_store: editForm.value.is_official_store,
    })
    // Override de capacidades é endpoint separado — só envia se conta é ML
    if (editTarget.value.platform === 'mercadolivre') {
      await api.put(`/accounts/${editTarget.value.id}/shipping-capabilities`, {
        has_flex_override: editForm.value.has_flex_override,
        has_full_override: editForm.value.has_full_override,
      })
    }
    modal.value.edit = false
    toast('Conta atualizada!', 'success')
    await loadAccounts()
  } catch (err) {
    editError.value = err.response?.data?.detail || 'Erro ao salvar'
  } finally {
    savingEdit.value = false
  }
}

async function createConta() {
  const { platform, email, phone } = newContaForm.value
  if (!platform || !email || !phone) {
    newContaError.value = 'Plataforma, e-mail e telefone são obrigatórios.'
    return
  }
  savingNewConta.value = true
  newContaError.value = ''
  try {
    const { data } = await api.post('/accounts', newContaForm.value)
    modal.value.newConta = false
    await loadAccounts()
    toast(data.message || 'Conta criada com sucesso!', 'success')
  } catch (err) {
    newContaError.value = err.response?.data?.detail || 'Erro ao criar conta'
  } finally {
    savingNewConta.value = false
  }
}

async function syncOrders(account) {
  syncing.value[account.id] = 'orders'
  try {
    await api.post(`/accounts/${account.id}/sync-orders`)
    toast('Pedidos sincronizados com sucesso!', 'success')
    await loadAccounts()
  } catch (err) {
    toast(err.response?.data?.detail || 'Erro ao sincronizar pedidos', 'danger')
  } finally {
    syncing.value[account.id] = false
  }
}

async function importListings(account) {
  syncing.value[account.id] = 'listings'
  try {
    const { data } = await api.post(`/accounts/${account.id}/import-listings`)
    toast(data.message || 'Anúncios importados!', 'success')
    await loadAccounts()
  } catch (err) {
    toast(err.response?.data?.detail || 'Erro ao importar anúncios', 'danger')
  } finally {
    syncing.value[account.id] = false
  }
}

async function connectOAuth(account) {
  try {
    const endpoint = account.platform === 'mercadolivre'
      ? `/accounts/${account.id}/ml/authorize`
      : `/accounts/${account.id}/shopee/authorize`
    const { data } = await api.get(endpoint)
    const popup = window.open(data.auth_url, 'oauth_popup', 'width=650,height=750')
    const timer = setInterval(async () => {
      if (popup?.closed) {
        clearInterval(timer)
        await loadAccounts()
      }
    }, 1000)
  } catch (err) {
    toast(err.response?.data?.detail || 'Erro ao iniciar autenticação OAuth', 'danger')
  }
}

function openBlingModal(account) {
  blingTarget.value = account
  blingApiKey.value = ''
  blingError.value = ''
  modal.value.bling = true
}

async function saveBling() {
  savingBling.value = true
  blingError.value = ''
  try {
    await api.post(`/accounts/${blingTarget.value.id}/bling/connect`, { api_key: blingApiKey.value })
    modal.value.bling = false
    toast('Bling conectado com sucesso!', 'success')
    await loadAccounts()
  } catch (err) {
    blingError.value = err.response?.data?.detail || 'Erro ao conectar Bling'
  } finally {
    savingBling.value = false
  }
}

async function disconnect(account) {
  if (!confirm(`Desconectar a conta "${account.platform_username || account.email}"?`)) return
  try {
    await api.delete(`/accounts/${account.id}`)
    toast('Conta desconectada.', 'warning')
    await loadAccounts()
  } catch (err) {
    toast(err.response?.data?.detail || 'Erro ao desconectar', 'danger')
  }
}

function platformLabel(platform) {
  return { mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[platform] || platform
}

function platformBadge(platform) {
  return { mercadolivre: 'badge-warning', shopee: 'badge-danger', bling: 'badge-info' }[platform] || 'badge-secondary'
}

const MEDAL_LABEL = { platinum: 'Platinum', gold: 'Gold', silver: 'Silver' }
const MEDAL_STYLE = {
  platinum: 'background:#e5e4e2;color:#1f2937;border:1px solid #9ca3af',
  gold:     'background:#fde68a;color:#78350f;border:1px solid #f59e0b',
  silver:   'background:#e2e8f0;color:#334155;border:1px solid #94a3b8',
}
function medalLabel(s) { return MEDAL_LABEL[s] || s }
function medalStyle(s) { return MEDAL_STYLE[s] || '' }

const LEVEL_LABEL = {
  '5_green':       'Verde',
  '4_light_green': 'Verde-claro',
  '3_yellow':      'Amarelo',
  '2_orange':      'Laranja',
  '1_red':         'Vermelho',
}
const LEVEL_STYLE = {
  '5_green':       'background:#16a34a;color:#fff',
  '4_light_green': 'background:#86efac;color:#14532d',
  '3_yellow':      'background:#fef08a;color:#78350f',
  '2_orange':      'background:#fb923c;color:#fff',
  '1_red':         'background:#dc2626;color:#fff',
}
function levelLabel(l) { return LEVEL_LABEL[l] || l }
function levelStyle(l) { return LEVEL_STYLE[l] || '' }

function formatDateTime(dt) { return fmtBrDateTime(dt) }   // fonte única (horário do Brasil)

onMounted(() => { loadAccounts(); loadCmigs() })
</script>
