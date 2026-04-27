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
            <button class="btn btn-xs btn-outline-danger ml-1" title="Desconectar" @click="disconnect(acc)">
              <i class="fas fa-unlink"></i>
            </button>
          </div>

          <div class="card-body">
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

            <!-- Status OTP -->
            <div v-if="!acc.otp_verified" class="alert alert-warning py-2 mb-2">
              <i class="fas fa-exclamation-triangle mr-1"></i>
              Verificação pendente.
              <button class="btn btn-xs btn-warning ml-2" @click="openOtpModal(acc)">Verificar OTP</button>
            </div>

            <!-- Status OAuth / conexão -->
            <div v-else>
              <div v-if="acc.is_active" class="d-flex align-items-center mb-2">
                <span class="badge badge-success mr-2">Conectado</span>
                <small v-if="acc.platform_username" class="text-muted">@{{ acc.platform_username }}</small>
              </div>
              <div v-else class="alert alert-secondary py-2 mb-2">
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

              <!-- Ações de sincronização (apenas contas conectadas) -->
              <div v-if="acc.is_active" class="mt-2 d-flex gap-1" style="gap:6px">
                <button class="btn btn-sm btn-outline-primary flex-fill"
                        :disabled="syncing[acc.id]"
                        @click="syncOrders(acc)"
                        title="Baixar pedidos agora">
                  <i :class="syncing[acc.id] ? 'fas fa-spinner fa-spin' : 'fas fa-shopping-bag'" class="mr-1"></i>
                  {{ syncing[acc.id] === 'orders' ? 'Baixando...' : 'Baixar Pedidos' }}
                </button>
                <button v-if="acc.platform === 'mercadolivre'"
                        class="btn btn-sm btn-outline-secondary flex-fill"
                        :disabled="syncing[acc.id]"
                        @click="importListings(acc)"
                        title="Importar anúncios ativos do ML">
                  <i :class="syncing[acc.id] === 'listings' ? 'fas fa-spinner fa-spin' : 'fas fa-tag'" class="mr-1"></i>
                  {{ syncing[acc.id] === 'listings' ? 'Importando...' : 'Importar Anúncios' }}
                </button>
              </div>
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
            <p class="text-muted small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              Após cadastrar, você receberá um código OTP para confirmar o vínculo da conta.
            </p>
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

    <!-- ─── Modal: Verificar OTP ──────────────────────────────────────────── -->
    <div v-if="modal.otp" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-shield-alt mr-2"></i> Verificar Código OTP</h5>
            <button class="close" @click="modal.otp = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="otpError" class="alert alert-danger py-2">
              <i class="fas fa-exclamation-circle mr-1"></i>{{ otpError }}
            </div>
            <div v-if="otpResent" class="alert alert-success py-2">
              <i class="fas fa-check-circle mr-1"></i>Novo código gerado! Consulte o terminal do backend (uvicorn).
            </div>
            <p>
              Digite o código de 6 dígitos enviado para
              <strong>{{ otpTarget?.email }}</strong>.
            </p>
            <p class="text-muted small">
              <i class="fas fa-info-circle mr-1"></i>
              Em ambiente de desenvolvimento, consulte o log do backend para obter o código gerado.
            </p>
            <div class="form-group">
              <label>Código OTP <span class="text-danger">*</span></label>
              <input v-model="otpCode" type="text" class="form-control text-center"
                     maxlength="6" placeholder="000000"
                     style="font-size:1.5rem;letter-spacing:.5rem;font-weight:bold" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="modal.otp = false">Cancelar</button>
            <button class="btn btn-outline-warning" :disabled="resendingOtp" @click="resendOtp">
              <i v-if="resendingOtp" class="fas fa-spinner fa-spin mr-1"></i>
              <i v-else class="fas fa-redo mr-1"></i>
              {{ resendingOtp ? 'Reenviando...' : 'Reenviar Código' }}
            </button>
            <button class="btn btn-success" :disabled="verifyingOtp || otpCode.length !== 6" @click="verifyOtp">
              <i v-if="verifyingOtp" class="fas fa-spinner fa-spin mr-1"></i>
              {{ verifyingOtp ? 'Verificando...' : 'Confirmar' }}
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
            <div class="form-group mb-0">
              <div class="custom-control custom-switch">
                <input type="checkbox" class="custom-control-input" id="editIsOfficialStore"
                       v-model="editForm.is_official_store" />
                <label class="custom-control-label" for="editIsOfficialStore">
                  Loja Oficial no Mercado Livre
                </label>
              </div>
              <small class="text-muted">Ative apenas para contas com <em>family_name</em> — permite editar o título do anúncio via API.</small>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const { show: toast } = useToast()

const accounts = ref([])
const cmigs    = ref([])
const loading  = ref(false)

const modal   = ref({ newConta: false, otp: false, bling: false, edit: false })
const syncing = ref({})   // { [account_id]: 'orders' | 'listings' | false }

// Nova CONTA
const newContaForm   = ref({ platform: '', email: '', phone: '', description: '', cmig_id: '' })
const newContaError  = ref('')
const savingNewConta = ref(false)

// Editar CONTA
const editTarget = ref(null)
const editForm   = ref({ cmig_id: '', description: '', is_official_store: false })
const editError  = ref('')
const savingEdit = ref(false)

// OTP
const otpTarget    = ref(null)
const otpCode      = ref('')
const otpError     = ref('')
const otpResent    = ref(false)
const verifyingOtp = ref(false)
const resendingOtp = ref(false)

// Bling
const blingTarget  = ref(null)
const blingApiKey  = ref('')
const blingError   = ref('')
const savingBling  = ref(false)

async function loadAccounts() {
  loading.value = true
  try {
    const { data } = await api.get('/accounts')
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

function openEditModal(acc) {
  editTarget.value = acc
  editForm.value = { cmig_id: acc.cmig_id || '', description: acc.description || '', is_official_store: !!acc.is_official_store }
  editError.value = ''
  modal.value.edit = true
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
    if (data.otp_required) {
      const created = accounts.value.find(a => a.id === data.id)
      if (created) openOtpModal(created)
      toast('Conta criada! Insira o código OTP para ativar.', 'info')
    } else {
      toast('Conta vinculada como co-administrador.', 'success')
    }
  } catch (err) {
    newContaError.value = err.response?.data?.detail || 'Erro ao criar conta'
  } finally {
    savingNewConta.value = false
  }
}

function openOtpModal(account) {
  otpTarget.value = account
  otpCode.value = ''
  otpError.value = ''
  otpResent.value = false
  modal.value.otp = true
}

async function resendOtp() {
  resendingOtp.value = true
  otpError.value = ''
  otpResent.value = false
  try {
    await api.post(`/accounts/${otpTarget.value.id}/resend-otp`)
    otpCode.value = ''
    otpResent.value = true
  } catch (err) {
    otpError.value = err.response?.data?.detail || 'Erro ao reenviar código'
  } finally {
    resendingOtp.value = false
  }
}

async function verifyOtp() {
  verifyingOtp.value = true
  otpError.value = ''
  try {
    await api.post(`/accounts/${otpTarget.value.id}/verify-otp`, { code: otpCode.value })
    modal.value.otp = false
    toast('Conta verificada com sucesso!', 'success')
    await loadAccounts()
  } catch (err) {
    otpError.value = err.response?.data?.detail || 'Código inválido ou expirado'
  } finally {
    verifyingOtp.value = false
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

function formatDateTime(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('pt-BR')
}

onMounted(() => { loadAccounts(); loadCmigs() })
</script>
