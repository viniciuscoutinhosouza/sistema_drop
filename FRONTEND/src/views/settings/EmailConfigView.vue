<template>
  <div>
    <div class="card card-primary card-outline" style="max-width:760px">
      <div class="card-header">
        <h3 class="card-title"><i class="fas fa-envelope mr-2"></i>Servidor de E-mail (SMTP)</h3>
      </div>

      <div v-if="loading" class="card-body text-center py-4">
        <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
      </div>

      <div v-else class="card-body">
        <p class="text-muted small">
          Configure o servidor de envio de e-mail. Ele é usado para enviar o
          <strong>código de verificação (OTP)</strong> quando um usuário cadastra
          uma conta de marketplace.
        </p>

        <div class="custom-control custom-switch mb-3">
          <input id="smtp_active" v-model="form.is_active" type="checkbox" class="custom-control-input">
          <label class="custom-control-label" for="smtp_active">
            Envio de e-mail <strong>{{ form.is_active ? 'ativado' : 'desativado' }}</strong>
          </label>
        </div>

        <form @submit.prevent="save" autocomplete="off">
          <div class="row">
            <div class="col-md-8 form-group">
              <label>Servidor SMTP (host) <span class="text-danger">*</span></label>
              <input v-model="form.host" class="form-control" placeholder="smtp.gmail.com" required>
            </div>
            <div class="col-md-4 form-group">
              <label>Porta</label>
              <input v-model.number="form.port" type="number" class="form-control" placeholder="587">
            </div>
          </div>

          <div class="row">
            <div class="col-md-6 form-group">
              <label>Usuário</label>
              <input v-model="form.username" class="form-control" autocomplete="off"
                     placeholder="seu-email@dominio.com">
            </div>
            <div class="col-md-6 form-group">
              <label>Senha {{ form.password_set ? '(já configurada)' : '' }}</label>
              <input v-model="form.password" type="password" class="form-control" autocomplete="new-password"
                     :placeholder="form.password_set ? '•••••••• (deixe em branco para manter)' : 'senha / app password'">
            </div>
          </div>

          <div class="row">
            <div class="col-md-6 form-group">
              <label>E-mail remetente <span class="text-danger">*</span></label>
              <input v-model="form.from_email" type="email" class="form-control"
                     placeholder="naoresponda@suaempresa.com" required>
            </div>
            <div class="col-md-6 form-group">
              <label>Nome do remetente</label>
              <input v-model="form.from_name" class="form-control" placeholder="MIG ECOMMERCE">
            </div>
          </div>

          <div class="row">
            <div class="col-md-6 form-group">
              <label>Segurança</label>
              <select v-model="security" class="form-control">
                <option value="starttls">STARTTLS (porta 587) — recomendado</option>
                <option value="ssl">SSL/TLS (porta 465)</option>
                <option value="none">Nenhuma</option>
              </select>
            </div>
          </div>

          <div class="d-flex align-items-center mt-2" style="gap:.5rem">
            <button type="submit" class="btn btn-primary" :disabled="saving">
              <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i> Salvar
            </button>
            <span class="text-muted small ml-2" v-if="updatedAt">Salvo em {{ updatedAt }}</span>
          </div>
        </form>

        <hr>

        <h6 class="text-muted"><i class="fas fa-paper-plane mr-1"></i>Testar envio</h6>
        <div class="form-row align-items-center">
          <div class="col-md-6">
            <input v-model="testTo" type="email" class="form-control" placeholder="enviar teste para...">
          </div>
          <div class="col-auto">
            <button class="btn btn-outline-success" :disabled="testing || !testTo" @click="sendTest">
              <i class="fas" :class="testing ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i> Enviar teste
            </button>
          </div>
        </div>
        <p class="small text-muted mt-1">Salve a configuração antes de testar.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const testTo = ref('')
const updatedAt = ref('')

const form = reactive({
  host: '', port: 587, username: '', password: '', password_set: false,
  use_tls: true, use_ssl: false, from_email: '', from_name: '', is_active: false,
})

// Mapeia os dois flags do backend num único seletor amigável.
const security = computed({
  get() {
    if (form.use_ssl) return 'ssl'
    if (form.use_tls) return 'starttls'
    return 'none'
  },
  set(v) {
    form.use_ssl = v === 'ssl'
    form.use_tls = v === 'starttls'
  },
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/settings/email')
    Object.assign(form, {
      host: data.host || '', port: data.port || 587, username: data.username || '',
      password: '', password_set: !!data.password_set,
      use_tls: data.use_tls ?? true, use_ssl: data.use_ssl ?? false,
      from_email: data.from_email || '', from_name: data.from_name || '',
      is_active: !!data.is_active,
    })
    if (data.updated_at) updatedAt.value = fmtBrDateTime(data.updated_at)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar configuração')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = {
      host: form.host, port: form.port, username: form.username,
      use_tls: form.use_tls, use_ssl: form.use_ssl,
      from_email: form.from_email, from_name: form.from_name, is_active: form.is_active,
    }
    if (form.password) payload.password = form.password  // só envia se preenchido
    const { data } = await api.put('/settings/email', payload)
    form.password = ''
    form.password_set = !!data.password_set
    if (data.updated_at) updatedAt.value = fmtBrDateTime(data.updated_at)
    toast.success('Configuração salva')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

async function sendTest() {
  testing.value = true
  try {
    const { data } = await api.post('/settings/email/test', { to: testTo.value })
    toast.success(data.message || 'E-mail de teste enviado')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao enviar e-mail de teste')
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>
