<template>
  <div class="card" style="max-width:640px">
    <div class="card-header"><h3 class="card-title">Nova Devolução</h3></div>
    <div class="card-body">
      <form @submit.prevent="submit">
        <div class="form-group">
          <label>ID do Pedido</label>
          <input v-model="form.order_id" type="number" class="form-control" placeholder="ID interno do pedido" required />
        </div>
        <div class="form-group">
          <label>Motivo</label>
          <select v-model="form.reason" class="form-control" required>
            <option value="">Selecionar...</option>
            <option value="defeito">Produto com defeito</option>
            <option value="produto_errado">Produto errado</option>
            <option value="desistencia">Desistência da compra</option>
            <option value="outro">Outro</option>
          </select>
        </div>
        <div class="form-group">
          <label>Descrição do ocorrido</label>
          <textarea v-model="form.description" class="form-control" rows="3"></textarea>
        </div>
        <div class="form-group">
          <label>Código de Rastreio</label>
          <input v-model="form.tracking_code" type="text" class="form-control" />
        </div>
        <div class="form-group">
          <label>URL de Rastreio</label>
          <input v-model="form.tracking_url" type="url" class="form-control" />
        </div>
        <div class="form-group">
          <label>Transportadora</label>
          <input v-model="form.carrier" type="text" class="form-control" />
        </div>
        <div class="form-group">
          <label>Código de Segurança (marketplace)</label>
          <input v-model="form.security_code" type="text" class="form-control" />
        </div>

        <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>

        <button type="submit" class="btn btn-primary" :disabled="loading">
          <i v-if="loading" class="fas fa-spinner fa-spin mr-1"></i>
          Registrar Devolução
        </button>
        <RouterLink to="/returns" class="btn btn-secondary ml-2">Cancelar</RouterLink>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/composables/useApi'

const router = useRouter()
const loading = ref(false)
const error = ref('')

const form = reactive({
  order_id: '',
  reason: '',
  description: '',
  tracking_code: '',
  tracking_url: '',
  carrier: '',
  security_code: '',
})

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await api.post('/returns', form)
    router.push('/returns')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao registrar devolução'
  } finally {
    loading.value = false
  }
}
</script>
