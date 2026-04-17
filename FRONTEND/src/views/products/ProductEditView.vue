<template>
  <div class="card" style="max-width:800px">
    <div class="card-header"><h3 class="card-title">Editar Produto #{{ route.params.id }}</h3></div>
    <div class="card-body">
      <div v-if="!product" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></div>
      <form v-else @submit.prevent="submit">
        <div class="form-group">
          <label>Título Padrão</label>
          <input v-model="form.title" type="text" class="form-control" maxlength="60" required />
        </div>
        <div class="row">
          <div class="col-md-6 form-group">
            <label>Preço ML</label>
            <input v-model="form.sale_price_ml" type="number" step="0.01" class="form-control" />
          </div>
          <div class="col-md-6 form-group">
            <label>Preço Shopee</label>
            <input v-model="form.sale_price_shopee" type="number" step="0.01" class="form-control" />
          </div>
        </div>
        <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
        <button type="submit" class="btn btn-primary" :disabled="loading">Salvar</button>
        <RouterLink to="/products" class="btn btn-secondary ml-2">Cancelar</RouterLink>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const product = ref(null)
const loading = ref(false)
const error = ref('')
const form = reactive({ title: '', title_ml: '', title_shopee: '', sale_price_ml: '', sale_price_shopee: '' })

onMounted(async () => {
  const { data } = await api.get(`/products/${route.params.id}`)
  product.value = data
  Object.assign(form, {
    title: data.title,
    title_ml: data.title_ml || '',
    title_shopee: data.title_shopee || '',
    sale_price_ml: data.sale_price_ml || '',
    sale_price_shopee: data.sale_price_shopee || '',
  })
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
