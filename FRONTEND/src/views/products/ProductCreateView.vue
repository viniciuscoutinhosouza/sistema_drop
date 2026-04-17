<template>
  <div class="card" style="max-width:800px">
    <div class="card-header"><h3 class="card-title">Cadastrar Produto</h3></div>
    <div class="card-body">
      <form @submit.prevent="submit">
        <!-- Catalog link (pre-filled from catalog) -->
        <div v-if="catalogProduct" class="alert alert-info">
          Baseado no produto do catálogo: <strong>{{ catalogProduct.title }}</strong>
        </div>

        <div class="form-group">
          <label>Título Padrão <small>(máx. 60 chars)</small></label>
          <input v-model="form.title" type="text" class="form-control" maxlength="60" required />
        </div>
        <div class="row">
          <div class="col-md-6 form-group">
            <label>Preço de Venda – Mercado Livre</label>
            <input v-model="form.sale_price_ml" type="number" step="0.01" class="form-control" />
          </div>
          <div class="col-md-6 form-group">
            <label>Preço de Venda – Shopee</label>
            <input v-model="form.sale_price_shopee" type="number" step="0.01" class="form-control" />
          </div>
        </div>
        <div class="form-group">
          <label>Título para Mercado Livre <small>(máx. 60 chars)</small></label>
          <input v-model="form.title_ml" type="text" class="form-control" maxlength="60" />
        </div>
        <div class="form-group">
          <label>Título para Shopee <small>(máx. 100 chars)</small></label>
          <input v-model="form.title_shopee" type="text" class="form-control" maxlength="100" />
        </div>

        <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
        <button type="submit" class="btn btn-primary" :disabled="loading">
          <i v-if="loading" class="fas fa-spinner fa-spin mr-1"></i>
          Salvar Produto
        </button>
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

const loading = ref(false)
const error = ref('')
const catalogProduct = ref(null)

const form = reactive({
  title: '',
  title_ml: '',
  title_shopee: '',
  sale_price_ml: '',
  sale_price_shopee: '',
  catalog_product_id: null,
})

onMounted(async () => {
  const catalogId = route.query.catalog_id
  if (catalogId) {
    const { data } = await api.get(`/catalog/${catalogId}`)
    catalogProduct.value = data
    form.title = data.title.slice(0, 60)
    form.title_ml = data.title.slice(0, 60)
    form.title_shopee = data.title.slice(0, 100)
    form.sale_price_ml = data.suggested_price || ''
    form.sale_price_shopee = data.suggested_price || ''
    form.catalog_product_id = data.id
  }
})

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await api.post('/products', form)
    router.push('/products')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao cadastrar produto'
  } finally {
    loading.value = false
  }
}
</script>
