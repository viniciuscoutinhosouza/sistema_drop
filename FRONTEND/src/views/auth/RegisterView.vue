<template>
  <div class="register-box">
    <div class="register-logo">
      <strong>MIG</strong> ECOMMERCE
    </div>

    <div class="card">
      <div class="card-body register-card-body">
        <p class="login-box-msg">Crie sua conta de dropshipper</p>

        <form @submit.prevent="handleRegister">
          <!-- Personal Info -->
          <div class="mb-2">
            <input v-model="form.full_name" type="text" class="form-control" placeholder="Nome completo" required />
          </div>
          <div class="mb-2">
            <input v-model="form.email" type="email" class="form-control" placeholder="E-mail" required />
          </div>
          <div class="mb-2">
            <input
              v-model="form.whatsapp"
              type="text"
              class="form-control"
              placeholder="WhatsApp (00) 00000-0000"
              @input="form.whatsapp = maskPhone(form.whatsapp)"
              required
            />
          </div>

          <!-- Person Type -->
          <div class="mb-2">
            <select v-model="form.person_type" class="form-control" required>
              <option value="">Tipo de pessoa</option>
              <option value="fisica">Pessoa Física (CPF)</option>
              <option value="juridica">Pessoa Jurídica (CNPJ)</option>
            </select>
          </div>
          <div class="mb-2">
            <input
              v-model="form.cpf_cnpj"
              type="text"
              class="form-control"
              :placeholder="form.person_type === 'juridica' ? 'CNPJ' : 'CPF'"
              @input="applyDocumentMask"
              required
            />
            <small v-if="docError" class="text-danger">{{ docError }}</small>
          </div>

          <!-- Address -->
          <hr class="my-2" />
          <p class="text-muted small mb-2">Endereço</p>
          <div class="input-group mb-2">
            <input
              v-model="form.zip_code"
              type="text"
              class="form-control"
              placeholder="CEP"
              maxlength="9"
              @blur="lookupCEP"
              @input="form.zip_code = maskCEP(form.zip_code)"
              required
            />
            <div class="input-group-append">
              <button type="button" class="btn btn-outline-secondary" @click="lookupCEP" :disabled="cepLoading">
                <i :class="cepLoading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
              </button>
            </div>
          </div>
          <div class="mb-2">
            <input v-model="form.street" type="text" class="form-control" placeholder="Rua / Logradouro" required />
          </div>
          <div class="row mb-2">
            <div class="col-4">
              <input v-model="form.number" type="text" class="form-control" placeholder="Número" required />
            </div>
            <div class="col-8">
              <input v-model="form.complement" type="text" class="form-control" placeholder="Complemento" />
            </div>
          </div>
          <div class="mb-2">
            <input v-model="form.neighborhood" type="text" class="form-control" placeholder="Bairro" required />
          </div>
          <div class="row mb-2">
            <div class="col-8">
              <input v-model="form.city" type="text" class="form-control" placeholder="Cidade" required />
            </div>
            <div class="col-4">
              <select v-model="form.state" class="form-control" required>
                <option value="">UF</option>
                <option v-for="uf in BRAZIL_STATES" :key="uf" :value="uf">{{ uf }}</option>
              </select>
            </div>
          </div>

          <!-- Password -->
          <hr class="my-2" />
          <div class="mb-2">
            <input v-model="form.password" type="password" class="form-control" placeholder="Senha" required />
          </div>
          <div class="mb-3">
            <input v-model="form.password_confirm" type="password" class="form-control" placeholder="Confirmar senha" required />
            <small v-if="passwordMismatch" class="text-danger">As senhas não coincidem</small>
          </div>

          <div v-if="errorMessage" class="alert alert-danger py-2">{{ errorMessage }}</div>

          <button type="submit" class="btn btn-primary btn-block" :disabled="loading">
            <span v-if="loading"><i class="fas fa-spinner fa-spin"></i> Cadastrando...</span>
            <span v-else>Criar conta</span>
          </button>
        </form>

        <p class="mt-3 text-center">
          Já tem conta? <RouterLink to="/login">Entrar</RouterLink>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { maskPhone, maskCPF, maskCNPJ, maskCEP } from '@/utils/formatters'
import { validateCPF, validateCNPJ } from '@/utils/validators'
import { BRAZIL_STATES } from '@/utils/constants'
import api from '@/composables/useApi'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({
  full_name: '', email: '', whatsapp: '', person_type: '', cpf_cnpj: '',
  zip_code: '', street: '', number: '', complement: '', neighborhood: '', city: '', state: '',
  password: '', password_confirm: '',
})

const loading = ref(false)
const cepLoading = ref(false)
const errorMessage = ref('')
const docError = ref('')

const passwordMismatch = computed(() =>
  form.password_confirm && form.password !== form.password_confirm
)

function applyDocumentMask() {
  form.cpf_cnpj = form.person_type === 'juridica'
    ? maskCNPJ(form.cpf_cnpj)
    : maskCPF(form.cpf_cnpj)
  docError.value = ''
}

async function lookupCEP() {
  const digits = form.zip_code.replace(/\D/g, '')
  if (digits.length !== 8) return
  cepLoading.value = true
  try {
    const { data } = await api.get(`/users/address/lookup/${digits}`)
    form.street = data.street
    form.neighborhood = data.neighborhood
    form.city = data.city
    form.state = data.state
    if (data.complement) form.complement = data.complement
  } catch {
    // Silently fail – user can fill manually
  } finally {
    cepLoading.value = false
  }
}

async function handleRegister() {
  errorMessage.value = ''
  docError.value = ''

  // Validate document
  const digits = form.cpf_cnpj.replace(/\D/g, '')
  if (form.person_type === 'fisica' && !validateCPF(digits)) {
    docError.value = 'CPF inválido'
    return
  }
  if (form.person_type === 'juridica' && !validateCNPJ(digits)) {
    docError.value = 'CNPJ inválido'
    return
  }
  if (passwordMismatch.value) return

  loading.value = true
  try {
    await authStore.register(form)
    router.push('/dashboard')
  } catch (err) {
    errorMessage.value = err.response?.data?.detail || 'Erro ao cadastrar'
  } finally {
    loading.value = false
  }
}
</script>
