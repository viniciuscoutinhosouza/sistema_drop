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
            <button class="btn btn-xs btn-outline-danger ml-2" title="Desconectar" @click="disconnect(acc)">
              <i class="fas fa-unlink"></i>
            </button>
          </div>

          <div class="card-body">
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
            <div v-if="otpError" class="alert alert-danger">{{ otpError }}</div>
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
            <button class="btn btn-success" :disabled="verifyingOtp || otpCode.length !== 6" @click="verifyOtp">
              <i v-if="verifyingOtp" class="fas fa-spinner fa-spin mr-1"></i>
              {{ verifyingOtp ? 'Verificando...' : 'Confirmar' }}
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

const { add: toast } = useToast()

const accounts = ref([])
const loading  = ref(false)

const modal = ref({ newConta: false, otp: false, bling: false })

// Nova CONTA
const newContaForm   = ref({ platform: '', email: '', phone: '', description: '' })
const newContaError  = ref('')
const savingNewConta = ref(false)

// OTP
const otpTarget    = ref(null)
const otpCode      = ref('')
const otpError     = ref('')
const verifyingOtp = ref(false)

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

function openNewContaModal() {
  newContaForm.value = { platform: '', email: '', phone: '', description: '' }
  newContaError.value = ''
  modal.value.newConta = true
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
  modal.value.otp = true
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

onMounted(loadAccounts)
</script>
