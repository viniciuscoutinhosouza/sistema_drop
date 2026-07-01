<template>
  <div class="login-box" style="max-width:420px;margin:5% auto">
    <div class="card card-outline card-primary">
      <div class="card-header text-center">
        <h3 class="mb-0"><strong>MIG</strong> ECOMMERCE</h3>
      </div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-4">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>

        <div v-else-if="invalid" class="text-center py-3">
          <i class="fas fa-exclamation-triangle fa-2x text-warning mb-2 d-block"></i>
          <p class="mb-2">{{ invalidMsg }}</p>
          <RouterLink to="/login" class="btn btn-outline-primary btn-sm">Ir para o login</RouterLink>
        </div>

        <div v-else-if="done" class="text-center py-3">
          <i class="fas fa-check-circle fa-2x text-success mb-2 d-block"></i>
          <p class="mb-2">{{ doneMsg }}</p>
          <RouterLink to="/login" class="btn btn-primary btn-sm">Ir para o login</RouterLink>
        </div>

        <template v-else>
          <p class="login-box-msg">
            Você foi convidado(a) para colaborar
            <span v-if="invite.company_name">em <strong>{{ invite.company_name }}</strong></span>.
            Crie seu cadastro abaixo.
          </p>
          <form @submit.prevent="submit">
            <div class="form-group">
              <label class="small mb-1">E-mail</label>
              <input :value="invite.email" class="form-control bg-light" readonly>
            </div>
            <div class="form-group">
              <label class="small mb-1">Nome completo <span class="text-danger">*</span></label>
              <input v-model="form.full_name" class="form-control" required>
            </div>
            <div class="form-group">
              <label class="small mb-1">WhatsApp</label>
              <input v-model="form.whatsapp" class="form-control" placeholder="(11) 91234-5678">
            </div>
            <div class="form-group">
              <label class="small mb-1">Senha <span class="text-danger">*</span></label>
              <input v-model="form.password" type="password" class="form-control" minlength="6" required>
              <small class="form-text text-muted">Mínimo 6 caracteres.</small>
            </div>
            <div v-if="error" class="alert alert-danger py-2 small">{{ error }}</div>
            <button type="submit" class="btn btn-primary btn-block" :disabled="saving">
              <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
              {{ saving ? 'Cadastrando...' : 'Criar meu cadastro' }}
            </button>
          </form>
          <p class="text-muted small text-center mt-3 mb-0">
            Após o cadastro, o administrador liberará seu acesso.
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/composables/useApi'

const route = useRoute()
const token = route.params.token

const loading = ref(true)
const invalid = ref(false)
const invalidMsg = ref('')
const done = ref(false)
const doneMsg = ref('')
const saving = ref(false)
const error = ref('')
const invite = ref({})
const form = reactive({ full_name: '', whatsapp: '', password: '' })

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/invites/${token}`)
    invite.value = data
  } catch (e) {
    invalid.value = true
    invalidMsg.value = e.response?.data?.detail || 'Convite inválido ou expirado.'
  } finally {
    loading.value = false
  }
}

async function submit() {
  error.value = ''
  if (form.password.length < 6) { error.value = 'A senha deve ter ao menos 6 caracteres'; return }
  saving.value = true
  try {
    const { data } = await api.post(`/invites/${token}/register`, {
      full_name: form.full_name,
      whatsapp: form.whatsapp || null,
      password: form.password,
    })
    done.value = true
    doneMsg.value = data.message || 'Cadastro realizado! Aguarde a liberação do administrador.'
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao concluir o cadastro.'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
