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
            <div class="col-md-3">
              <label class="small mb-1">Série NF-e (marketplace)</label>
              <input v-model.number="form.nfe_serie" type="number" min="1" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-3">
              <label class="small mb-1">E-mail fiscal (cópia)</label>
              <input v-model="form.fiscal_email_copy" type="email" class="form-control" :disabled="!canEdit">
            </div>
          </div>

          <div class="row mt-3">
            <div class="col-md-9">
              <label class="small mb-1">Natureza da Operação padrão</label>
              <input v-model="form.default_natureza_operacao" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-3">
              <label class="small mb-1">
                % Imposto (estimativa DRE)
                <i class="fas fa-info-circle text-muted" title="Percentual usado para estimar a linha 'Imposto ML' na Gestão Financeira (DRE)."></i>
              </label>
              <input v-model.number="form.tax_estimate_pct" type="number" step="0.01" min="0" max="100"
                     class="form-control" :disabled="!canEdit">
            </div>
          </div>

          <!-- Emissão própria SEFAZ: série manual configurável + FECP -->
          <h6 class="text-muted mt-4 mb-2"><i class="fas fa-paper-plane mr-1"></i>Emissão manual via SEFAZ</h6>
          <div class="row">
            <div class="col-md-3">
              <label class="small mb-1">
                Série NF-e manual (SEFAZ)
                <i class="fas fa-info-circle text-muted" title="Série específica dos lançamentos manuais de entrada/saída transmitidos direto à SEFAZ. Deve ser diferente da série do marketplace."></i>
              </label>
              <input v-model.number="form.manual_nfe_serie" type="number" min="1" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-3">
              <label class="small mb-1">Próximo nº (produção)</label>
              <input v-model.number="form.manual_nfe_next_number" type="number" min="1" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-3">
              <label class="small mb-1">Próximo nº (homologação)</label>
              <input v-model.number="form.manual_nfe_next_number_homolog" type="number" min="1" class="form-control" :disabled="!canEdit">
            </div>
            <div class="col-md-3">
              <label class="small mb-1">
                Alíquota FECP %
                <i class="fas fa-info-circle text-muted" title="Fundo de Combate à Pobreza (ex.: RJ 2%). Aplicado por produto conforme a lista do RICMS da UF."></i>
              </label>
              <input v-model.number="form.aliquota_fecp" type="number" step="0.01" min="0" max="100" class="form-control" :disabled="!canEdit">
            </div>
          </div>
          <div class="row mt-2" v-if="canEdit">
            <div class="col-md-12">
              <div class="custom-control custom-switch">
                <input type="checkbox" class="custom-control-input" id="prodReleased"
                       v-model="form.production_released">
                <label class="custom-control-label small" for="prodReleased">
                  <strong>Produção liberada</strong> — emitir NF-e real à SEFAZ (desligado = só homologação).
                  Ligar somente após o credenciamento da empresa na SEFAZ da UF.
                </label>
              </div>
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

        <!-- Certificado A1 (emissão própria SEFAZ) -->
        <div class="row">
          <div class="col-md-12">
            <h6 class="text-muted mb-2"><i class="fas fa-key mr-1"></i>Certificado Digital A1 (.pfx) — emissão SEFAZ</h6>
            <p class="mb-2">
              <span class="badge" :class="config.certificate_loaded ? 'badge-success' : 'badge-secondary'">
                {{ config.certificate_loaded ? 'Carregado' : 'Não carregado' }}
              </span>
              <small class="d-block text-muted mt-1">
                O certificado fica armazenado em diretório restrito no servidor e a senha é
                guardada cifrada no banco. Cada CNPJ exige o seu próprio certificado.
              </small>
            </p>
            <button v-if="canEdit" class="btn btn-sm btn-outline-info" @click="showCertModal = true">
              <i class="fas fa-upload mr-1"></i> {{ config.certificate_loaded ? 'Substituir Certificado' : 'Enviar Certificado' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Upload Certificado A1 -->
    <div v-if="showCertModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-key mr-2"></i>Enviar Certificado A1</h5>
            <button type="button" class="close" @click="showCertModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small">
              Selecione o arquivo .pfx do certificado A1 e informe a senha. O arquivo é armazenado
              em diretório restrito no servidor e a senha fica <strong>cifrada</strong> no banco —
              usada apenas no momento da transmissão à SEFAZ.
            </p>
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
import { formatDate as fmtBrDate } from '@/utils/formatters'
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

const showCertModal = ref(false)
const certPassword = ref('')
const pfxFile = ref(null)
const pfxInput = ref(null)
const uploadingCert = ref(false)
const certError = ref('')

const canSubmitCert = computed(() =>
  !!pfxFile.value && !!certPassword.value && !uploadingCert.value
)
const form = reactive({
  crt: 1,
  environment: 'homolog',
  ie: '',
  im: '',
  cnae: '',
  nfe_serie: 1,
  manual_nfe_serie: null,
  manual_nfe_next_number: 1,
  manual_nfe_next_number_homolog: 1,
  aliquota_fecp: 0,
  production_released: false,
  default_natureza_operacao: 'Venda de mercadoria',
  fiscal_email_copy: '',
  tax_estimate_pct: 0,
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

function formatDate(iso) { return fmtBrDate(iso) }   // fonte única (horário do Brasil)

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
      manual_nfe_serie: data.manual_nfe_serie ?? null,
      manual_nfe_next_number: data.manual_nfe_next_number ?? 1,
      manual_nfe_next_number_homolog: data.manual_nfe_next_number_homolog ?? 1,
      aliquota_fecp: data.aliquota_fecp ?? 0,
      production_released: !!data.production_released,
      default_natureza_operacao: data.default_natureza_operacao ?? 'Venda de mercadoria',
      fiscal_email_copy: data.fiscal_email_copy ?? '',
      tax_estimate_pct: data.tax_estimate_pct ?? 0,
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

function onPfxChange(e) {
  const f = e.target.files?.[0]
  if (f) pfxFile.value = f
}

async function uploadCert() {
  if (!canSubmitCert.value) return
  uploadingCert.value = true
  certError.value = ''
  const formData = new FormData()
  formData.append('password', certPassword.value)
  formData.append('pfx_file', pfxFile.value)
  try {
    await api.post(`/cmigs/${props.cmigId}/fiscal-config/certificate`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    toast.success('Certificado armazenado com sucesso!')
    showCertModal.value = false
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
