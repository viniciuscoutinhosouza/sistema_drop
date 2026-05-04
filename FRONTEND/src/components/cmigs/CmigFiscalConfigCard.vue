<template>
  <div class="card">
    <div class="card-header">
      <h3 class="card-title"><i class="fas fa-file-invoice-dollar mr-2"></i>Configuração Fiscal (NF-e)</h3>
    </div>
    <div class="card-body">
      <div v-if="loading" class="text-center py-4">
        <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
      </div>
      <div v-else>
        <!-- Status do certificado -->
        <div class="alert" :class="certificateAlertClass" role="alert">
          <i class="fas mr-1" :class="certificateIcon"></i>
          <strong>{{ certificateStatusLabel }}</strong>
          <span v-if="config.certificate_subject" class="d-block small">{{ config.certificate_subject }}</span>
          <span v-if="config.certificate_expires_at" class="d-block small">
            Expira em: {{ formatDate(config.certificate_expires_at) }}
            <span v-if="daysToExpire !== null" class="ml-1">
              ({{ daysToExpire > 0 ? `${daysToExpire} dias` : `vencido há ${-daysToExpire} dias` }})
            </span>
          </span>
        </div>

        <form @submit.prevent="save">
          <div class="row">
            <div class="col-md-4">
              <label class="small mb-1">Regime Tributário (CRT) <span class="text-danger">*</span></label>
              <select v-model.number="form.crt" class="form-control" :disabled="!canEdit">
                <option :value="1">1 — Simples Nacional</option>
                <option :value="2">2 — Simples Nacional (excesso de sublimite)</option>
                <option :value="3">3 — Regime Normal (Lucro Presumido/Real)</option>
                <option :value="4">4 — MEI</option>
              </select>
            </div>
            <div class="col-md-4">
              <label class="small mb-1">Ambiente</label>
              <select v-model="form.environment" class="form-control" :disabled="!canEdit">
                <option value="homolog">Homologação (testes)</option>
                <option value="production">Produção</option>
              </select>
            </div>
            <div class="col-md-4">
              <label class="small mb-1">Inscrição Estadual</label>
              <input v-model="form.ie" class="form-control" :disabled="!canEdit">
            </div>
          </div>

          <div class="row mt-3">
            <div class="col-md-3">
              <label class="small mb-1">Inscrição Municipal</label>
              <input v-model="form.im" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-3">
              <label class="small mb-1">CNAE</label>
              <input v-model="form.cnae" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-2">
              <label class="small mb-1">Série NF-e</label>
              <input v-model.number="form.nfe_serie" type="number" min="1" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-2">
              <label class="small mb-1">Próximo número</label>
              <input v-model.number="form.nfe_next_number" type="number" min="1" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-2">
              <label class="small mb-1">E-mail fiscal (cópia)</label>
              <input v-model="form.fiscal_email_copy" type="email" class="form-control" :disabled="!canEdit">
            </div>
          </div>

          <div class="row mt-3">
            <div class="col-12">
              <label class="small mb-1">Natureza da Operação padrão</label>
              <input v-model="form.default_natureza_operacao" class="form-control" :disabled="!canEdit">
            </div>
          </div>

          <div class="text-right mt-3" v-if="canEdit">
            <button type="submit" class="btn btn-primary" :disabled="saving">
              <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ saving ? 'Salvando...' : 'Salvar Configuração' }}
            </button>
          </div>
        </form>

        <hr>

        <!-- Focus NFe -->
        <div class="row">
          <div class="col-md-6">
            <h6 class="text-muted mb-2"><i class="fas fa-shield-alt mr-1"></i>Provedor Focus NFe</h6>
            <p class="mb-2">
              <span class="badge" :class="config.focus_registered ? 'badge-success' : 'badge-secondary'">
                {{ config.focus_registered ? 'Registrado' : 'Não registrado' }}
              </span>
              <small v-if="config.focus_registered_at" class="d-block text-muted mt-1">
                Registrado em {{ formatDate(config.focus_registered_at) }}
              </small>
            </p>
            <button v-if="canEdit" class="btn btn-sm btn-outline-info" @click="showFocusModal = true">
              <i class="fas fa-link mr-1"></i> {{ config.focus_registered ? 'Re-registrar' : 'Registrar no Focus NFe' }}
            </button>
          </div>
          <div class="col-md-6">
            <h6 class="text-muted mb-2"><i class="fas fa-key mr-1"></i>Certificado Digital A1 (.pfx)</h6>
            <p class="mb-2">
              <span class="badge" :class="config.certificate_loaded ? 'badge-success' : 'badge-secondary'">
                {{ config.certificate_loaded ? 'Carregado' : 'Não carregado' }}
              </span>
            </p>
            <button v-if="canEdit" class="btn btn-sm btn-outline-info"
                    :disabled="!config.focus_registered" @click="showCertModal = true"
                    :title="config.focus_registered ? '' : 'Registre a empresa no Focus NFe primeiro'">
              <i class="fas fa-upload mr-1"></i> Enviar Certificado
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Registrar Focus -->
    <div v-if="showFocusModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-link mr-2"></i>Registrar empresa no Focus NFe</h5>
            <button type="button" class="close" @click="showFocusModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small">
              Cole abaixo seu <strong>token mestre</strong> do Focus NFe (do painel da sua conta master).
              O sistema usa esse token para registrar este CNPJ e obter um token específico da empresa.
            </p>
            <div class="form-group">
              <label class="small">Token mestre Focus NFe <span class="text-danger">*</span></label>
              <input v-model="masterTokenFocus" class="form-control" type="password"
                     placeholder="cole aqui o token mestre">
            </div>
            <div v-if="focusError" class="alert alert-danger small">{{ focusError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showFocusModal = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="registering || !masterTokenFocus" @click="registerFocus">
              <i class="fas" :class="registering ? 'fa-spinner fa-spin' : 'fa-link'"></i>
              {{ registering ? 'Registrando...' : 'Registrar' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Upload Certificado -->
    <div v-if="showCertModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-key mr-2"></i>Enviar Certificado A1</h5>
            <button type="button" class="close" @click="showCertModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small">
              Selecione o arquivo .pfx do certificado A1 e informe a senha. O arquivo é enviado
              direto para o cofre do Focus NFe — não fica armazenado no nosso servidor.
            </p>
            <div class="form-group">
              <label class="small">Token mestre Focus NFe <span class="text-danger">*</span></label>
              <input v-model="masterTokenCert" class="form-control" type="password">
            </div>
            <div class="form-group">
              <label class="small">Arquivo .pfx <span class="text-danger">*</span></label>
              <input ref="pfxInput" type="file" accept=".pfx,application/x-pkcs12" class="form-control-file"
                     @change="onPfxChange">
            </div>
            <div class="form-group">
              <label class="small">Senha do certificado <span class="text-danger">*</span></label>
              <input v-model="certPassword" type="password" class="form-control">
            </div>
            <div v-if="certError" class="alert alert-danger small">{{ certError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCertModal = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="!canSubmitCert" @click="uploadCert">
              <i class="fas" :class="uploadingCert ? 'fa-spinner fa-spin' : 'fa-upload'"></i>
              {{ uploadingCert ? 'Enviando...' : 'Enviar' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  cmigId: { type: Number, required: true },
})

const toast = useToast()
const authStore = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const config = ref({})

const showFocusModal = ref(false)
const masterTokenFocus = ref('')
const registering = ref(false)
const focusError = ref('')

const showCertModal = ref(false)
const masterTokenCert = ref('')
const certPassword = ref('')
const pfxFile = ref(null)
const pfxInput = ref(null)
const uploadingCert = ref(false)
const certError = ref('')

const canSubmitCert = computed(() =>
  !!masterTokenCert.value && !!pfxFile.value && !!certPassword.value && !uploadingCert.value
)
const form = reactive({
  crt: 1,
  environment: 'homolog',
  ie: '',
  im: '',
  cnae: '',
  nfe_serie: 1,
  nfe_next_number: 1,
  default_natureza_operacao: 'Venda de mercadoria',
  fiscal_email_copy: '',
})

const canEdit = computed(() => ['ac', 'admin'].includes(authStore.user?.role))

const daysToExpire = computed(() => {
  if (!config.value.certificate_expires_at) return null
  const exp = new Date(config.value.certificate_expires_at)
  const now = new Date()
  return Math.ceil((exp - now) / (1000 * 60 * 60 * 24))
})

const certificateStatusLabel = computed(() => {
  if (!config.value.certificate_loaded) return 'Certificado não carregado'
  if (daysToExpire.value !== null && daysToExpire.value < 0) return 'Certificado VENCIDO'
  if (daysToExpire.value !== null && daysToExpire.value <= 30) return 'Certificado próximo do vencimento'
  return 'Certificado válido'
})

const certificateAlertClass = computed(() => {
  if (!config.value.certificate_loaded) return 'alert-secondary'
  if (daysToExpire.value !== null && daysToExpire.value < 0) return 'alert-danger'
  if (daysToExpire.value !== null && daysToExpire.value <= 30) return 'alert-warning'
  return 'alert-success'
})

const certificateIcon = computed(() => {
  if (!config.value.certificate_loaded) return 'fa-info-circle'
  if (daysToExpire.value !== null && daysToExpire.value < 0) return 'fa-exclamation-triangle'
  if (daysToExpire.value !== null && daysToExpire.value <= 30) return 'fa-exclamation-circle'
  return 'fa-check-circle'
})

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('pt-BR')
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/cmigs/${props.cmigId}/fiscal-config`)
    config.value = data
    Object.assign(form, {
      crt: data.crt ?? 1,
      environment: data.environment ?? 'homolog',
      ie: data.ie ?? '',
      im: data.im ?? '',
      cnae: data.cnae ?? '',
      nfe_serie: data.nfe_serie ?? 1,
      nfe_next_number: data.nfe_next_number ?? 1,
      default_natureza_operacao: data.default_natureza_operacao ?? 'Venda de mercadoria',
      fiscal_email_copy: data.fiscal_email_copy ?? '',
    })
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar configuração fiscal')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const { data } = await api.patch(`/cmigs/${props.cmigId}/fiscal-config`, form)
    config.value = data
    toast.success('Configuração fiscal salva')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

async function registerFocus() {
  registering.value = true
  focusError.value = ''
  try {
    const { data } = await api.post(`/cmigs/${props.cmigId}/fiscal-config/register-focus`, {
      master_token: masterTokenFocus.value,
    })
    config.value = data.config
    toast.success('Empresa registrada no Focus NFe!')
    showFocusModal.value = false
    masterTokenFocus.value = ''
  } catch (e) {
    focusError.value = e.response?.data?.detail || 'Erro ao registrar no Focus'
  } finally {
    registering.value = false
  }
}

function onPfxChange(e) {
  const f = e.target.files?.[0]
  if (f) pfxFile.value = f
}

async function uploadCert() {
  if (!canSubmitCert.value) return
  uploadingCert.value = true
  certError.value = ''
  const formData = new FormData()
  formData.append('master_token', masterTokenCert.value)
  formData.append('password', certPassword.value)
  formData.append('pfx_file', pfxFile.value)
  try {
    await api.post(`/cmigs/${props.cmigId}/fiscal-config/certificate`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    toast.success('Certificado enviado com sucesso!')
    showCertModal.value = false
    masterTokenCert.value = ''
    certPassword.value = ''
    pfxFile.value = null
    if (pfxInput.value) pfxInput.value.value = ''
    await load()
  } catch (e) {
    certError.value = e.response?.data?.detail || 'Erro ao enviar certificado'
  } finally {
    uploadingCert.value = false
  }
}

onMounted(load)
</script>
