<template>
  <div class="card" style="max-width:900px">
    <div class="card-header"><h3 class="card-title">Criar Kit</h3></div>
    <div class="card-body">
      <form @submit.prevent="submit">
        <div class="row">
          <div class="col-md-6 form-group">
            <label>SKU do Kit</label>
            <div class="input-group">
              <div class="input-group-prepend">
                <span class="input-group-text">KITB2-</span>
              </div>
              <input v-model="skuSuffix" type="text" class="form-control" required />
            </div>
          </div>
          <div class="col-md-6 form-group">
            <label>Título</label>
            <input v-model="form.title" type="text" class="form-control" required />
          </div>
        </div>

        <!-- Components -->
        <h5>Componentes do Kit</h5>
        <div class="mb-2">
          <div class="input-group mb-2" style="max-width:400px">
            <input v-model="searchSku" type="text" class="form-control form-control-sm" placeholder="Buscar SKU do catálogo..." />
            <div class="input-group-append">
              <button type="button" class="btn btn-sm btn-outline-primary" @click="searchProduct">
                <i class="fas fa-search"></i>
              </button>
            </div>
          </div>
          <div v-if="foundProduct" class="alert alert-success py-2 d-flex justify-content-between align-items-center">
            <span>{{ foundProduct.sku }} – {{ foundProduct.title }} (estoque: {{ foundProduct.stock_quantity }})</span>
            <button type="button" class="btn btn-sm btn-success" @click="addComponent">Adicionar</button>
          </div>
        </div>

        <table v-if="form.components.length" class="table table-sm mb-3">
          <thead><tr><th>SKU</th><th>Produto</th><th>Qtd</th><th>Contrib. Estoque</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(comp, idx) in form.components" :key="idx">
              <td><code>{{ comp.sku }}</code></td>
              <td>{{ comp.title }}</td>
              <td>
                <input v-model.number="comp.quantity" type="number" min="1" class="form-control form-control-sm" style="width:70px" @change="calcStock" />
              </td>
              <td>{{ comp.contribution }}</td>
              <td>
                <button type="button" class="btn btn-xs btn-danger" @click="form.components.splice(idx, 1); calcStock()">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="font-weight-bold">
              <td colspan="3" class="text-right">Estoque do kit:</td>
              <td><span :class="`badge badge-${kitStock > 0 ? 'success' : 'danger'} h6`">{{ kitStock }}</span></td>
              <td></td>
            </tr>
          </tfoot>
        </table>

        <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
        <button type="submit" class="btn btn-primary" :disabled="loading || !form.components.length">
          <i v-if="loading" class="fas fa-spinner fa-spin mr-1"></i> Criar Kit
        </button>
        <RouterLink to="/kits" class="btn btn-secondary ml-2">Cancelar</RouterLink>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/composables/useApi'

const router = useRouter()
const skuSuffix = ref('')
const searchSku = ref('')
const foundProduct = ref(null)
const loading = ref(false)
const error = ref('')
const kitStock = ref(0)

const form = reactive({
  title: '',
  components: [],
})

async function searchProduct() {
  const { data } = await api.get('/catalog', { params: { search: searchSku.value, page_size: 5 } })
  foundProduct.value = data.items[0] || null
}

function addComponent() {
  if (!foundProduct.value) return
  if (form.components.find(c => c.product_id === foundProduct.value.id)) return
  form.components.push({
    product_id: foundProduct.value.id,
    sku: foundProduct.value.sku,
    title: foundProduct.value.title,
    stock: foundProduct.value.stock_quantity,
    quantity: 1,
    contribution: foundProduct.value.stock_quantity,
  })
  foundProduct.value = null
  searchSku.value = ''
  calcStock()
}

function calcStock() {
  if (!form.components.length) { kitStock.value = 0; return }
  form.components.forEach(c => {
    c.contribution = Math.floor(c.stock / c.quantity)
  })
  kitStock.value = Math.min(...form.components.map(c => c.contribution))
}

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await api.post('/kits', {
      sku: `KITB2-${skuSuffix.value}`,
      title: form.title,
      components: form.components.map(c => ({ product_id: c.product_id, quantity: c.quantity })),
    })
    router.push('/kits')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao criar kit'
  } finally {
    loading.value = false
  }
}
</script>
