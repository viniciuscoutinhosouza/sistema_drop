<template>
  <div class="login-box">
    <div class="login-logo">
      <strong>MIG</strong> ECOMMERCE
    </div>

    <div class="card">
      <div class="card-body login-card-body">
        <p class="login-box-msg">Faça login para continuar</p>

        <form @submit.prevent="handleLogin">
          <div class="input-group mb-3">
            <input
              v-model="form.email"
              type="email"
              class="form-control"
              placeholder="E-mail"
              required
              autocomplete="email"
            />
            <div class="input-group-append">
              <div class="input-group-text"><i class="fas fa-envelope"></i></div>
            </div>
          </div>

          <div class="input-group mb-3">
            <input
              v-model="form.password"
              :type="showPassword ? 'text' : 'password'"
              class="form-control"
              placeholder="Senha"
              required
              autocomplete="current-password"
            />
            <div class="input-group-append">
              <div class="input-group-text" style="cursor:pointer" @click="showPassword = !showPassword">
                <i :class="showPassword ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
              </div>
            </div>
          </div>

          <div v-if="errorMessage" class="alert alert-danger py-2">
            {{ errorMessage }}
          </div>

          <div class="row">
            <div class="col-12">
              <button
                type="submit"
                class="btn btn-primary btn-block"
                :disabled="loading"
              >
                <span v-if="loading">
                  <i class="fas fa-spinner fa-spin"></i> Entrando...
                </span>
                <span v-else>Entrar</span>
              </button>
            </div>
          </div>
        </form>

        <p class="mt-3 mb-0 text-center">
          <RouterLink to="/register">Criar uma conta</RouterLink>
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({ email: '', password: '' })
const loading = ref(false)
const showPassword = ref(false)
const errorMessage = ref('')

async function handleLogin() {
  errorMessage.value = ''
  loading.value = true
  try {
    await authStore.login(form.email, form.password)
    router.push('/dashboard')
  } catch (err) {
    errorMessage.value = err.response?.data?.detail || 'Erro ao fazer login'
  } finally {
    loading.value = false
  }
}
</script>
