<template>
  <div>
    <div class="card mb-4" style="max-width:800px">
      <div class="card-header"><h3 class="card-title">Editar Produto #{{ route.params.id }}</h3></div>
      <div class="card-body">
        <div v-if="!product" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></div>
        <form v-else @submit.prevent="submit">
          <div class="form-group">
            <label>Título Padrão</label>
            <input v-model="form.title" type="text" class="form-control" maxlength="60" required />
          </div>
          <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
          <button type="submit" class="btn btn-primary" :disabled="loading">Salvar</button>
          <RouterLink to="/products" class="btn btn-secondary ml-2">Cancelar</RouterLink>
        </form>
      </div>
    </div>

    <!-- Gerenciamento de anúncios por conta/marketplace -->
    <ListingManager v-if="product" :product-id="Number(route.params.id)" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'
import ListingManager from '@/components/products/ListingManager.vue'

const route = useRoute()
const router = useRouter()
const product = ref(null)
const loading = ref(false)
const error = ref('')
const form = reactive({ title: '' })

onMounted(async () => {
  const { data } = await api.get(`/products/${route.params.id}`)
  product.value = data
  form.title = data.title
})

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.put(`/products/${route.params.id}`, form)
    router.push('/products')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao salvar'
  } finally {
    loading.value = false
  }
}
</script>
