<template>
  <div class="content-wrapper">
    <section class="content-header">
      <div class="container-fluid">
        <h1 class="m-0"><i class="fas fa-file-signature mr-2"></i>Certificado do Marketplace (DC-e)</h1>
        <p class="text-muted mb-0">
          Certificado A1 <strong>central da MIG</strong> usado para assinar a DC-e (Declaração de Conteúdo)
          das contas de vendedor <strong>pessoa física (CPF)</strong>, por conta e ordem — perfil Marketplace.
        </p>
      </div>
    </section>

    <section class="content">
      <div class="container-fluid">
        <div class="row">
          <div class="col-md-8 col-lg-6">
            <div class="card">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-key mr-1"></i>A1 do assinante (perfil marketplace_dce)</h3>
              </div>
              <div class="card-body">
                <div v-if="loading" class="text-center py-3">
                  <i class="fas fa-spinner fa-spin"></i> Carregando…
                </div>
                <div v-else>
                  <!-- Status -->
                  <div class="alert" :class="status.configured ? 'alert-success' : 'alert-secondary'">
                    <i class="fas mr-1" :class="status.configured ? 'fa-check-circle' : 'fa-exclamation-circle'"></i>
                    <strong>{{ status.configured ? 'Certificado configurado' : 'Nenhum certificado central cadastrado' }}</strong>
                    <div v-if="status.configured" class="small mt-1">
                      <div><b>CNPJ:</b> {{ status.cnpj }}</div>
                      <div v-if="status.company_name"><b>Razão:</b> {{ status.company_name }}</div>
                      <div v-if="status.certificate_subject" class="text-truncate">{{ status.certificate_subject }}</div>
                      <div v-if="status.certificate_expires_at">
                        <b>Expira em:</b> {{ formatDate(status.certificate_expires_at) }}
                        <span v-if="daysToExpire !== null" :class="daysToExpire < 30 ? 'text-danger' : 'text-muted'">
                          ({{ daysToExpire > 0 ? `${daysToExpire} dias` : `vencido há ${-daysToExpire} dias` }})
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- Formulário de upload -->
                  <form @submit.prevent="upload">
                    <div class="form-group">
                      <label class="small">CNPJ da MIG (assinante) <span class="text-danger">*</span></label>
                      <input v-model="form.cnpj" type="text" class="form-control form-control-sm"
                             placeholder="00.000.000/0000-00" required>
                    </div>
                    <div class="form-group">
                      <label class="small">Razão social <span class="text-danger">*</span></label>
                      <input v-model="form.company_name" type="text" class="form-control form-control-sm" required>
                    </div>
                    <div class="form-group">
                      <label class="small">Site (opcional)</label>
                      <input v-model="form.site" type="text" class="form-control form-control-sm"
                             placeholder="migecommerce.com.br">
                    </div>
                    <div class="form-group">
                      <label class="small">Arquivo .pfx <span class="text-danger">*</span></label>
                      <input ref="pfxInput" type="file" accept=".pfx,application/x-pkcs12"
                             class="form-control-file" @change="onPfx" required>
                    </div>
                    <div class="form-group">
                      <label class="small">Senha do certificado <span class="text-danger">*</span></label>
                      <input v-model="form.password" type="password" class="form-control form-control-sm" required>
                    </div>
                    <p class="text-muted small">
                      O arquivo é guardado em diretório restrito no servidor e a senha fica
                      <strong>cifrada</strong> no banco — usada só na transmissão à SEFAZ.
                    </p>
                    <button type="submit" class="btn btn-primary btn-sm" :disabled="!canSubmit || uploading">
                      <i class="fas mr-1" :class="uploading ? 'fa-spinner fa-spin' : 'fa-upload'"></i>
                      {{ uploading ? 'Enviando…' : (status.configured ? 'Substituir certificado' : 'Enviar certificado') }}
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDate as fmtBrDate } from '@/utils/formatters'

const PROFILE = 'marketplace_dce'
const toast = useToast()

const loading = ref(true)
const uploading = ref(false)
const status = reactive({ configured: false })
const form = reactive({ cnpj: '', company_name: '', site: '', password: '' })
const pfxFile = ref(null)
const pfxInput = ref(null)

const canSubmit = computed(
  () => form.cnpj && form.company_name && form.password && pfxFile.value,
)

const daysToExpire = computed(() => {
  if (!status.certificate_expires_at) return null
  const diff = new Date(status.certificate_expires_at) - new Date()
  return Math.round(diff / 86400000)
})

function formatDate(d) { return fmtBrDate(d) }

function onPfx(e) {
  const f = e.target.files && e.target.files[0]
  if (f) pfxFile.value = f
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/marketplace-settings/platform-certificate/${PROFILE}`)
    Object.assign(status, data)
    if (data.cnpj) form.cnpj = data.cnpj
    if (data.company_name) form.company_name = data.company_name
    if (data.site) form.site = data.site
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar o certificado')
  } finally {
    loading.value = false
  }
}

async function upload() {
  if (!canSubmit.value || uploading.value) return
  uploading.value = true
  const fd = new FormData()
  fd.append('cnpj', form.cnpj)
  fd.append('company_name', form.company_name)
  fd.append('site', form.site || '')
  fd.append('password', form.password)
  fd.append('pfx_file', pfxFile.value)
  try {
    await api.post(`/marketplace-settings/platform-certificate/${PROFILE}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    toast.success('Certificado do marketplace armazenado.')
    form.password = ''
    pfxFile.value = null
    if (pfxInput.value) pfxInput.value.value = ''
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar o certificado')
  } finally {
    uploading.value = false
  }
}

onMounted(load)
</script>
