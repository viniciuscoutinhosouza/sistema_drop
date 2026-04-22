<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Produtos CMIG</h1>
            <small class="text-muted" v-if="cmig">{{ cmig.company_name }}</small>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink :to="`/cmigs/${cmigId}`" class="btn btn-secondary mr-2">
              <i class="fas fa-arrow-left mr-1"></i> Voltar à CMIG
            </RouterLink>
            <RouterLink v-if="isAC" :to="`/cmig-products/new?cmig_id=${cmigId}`" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Novo Produto
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-box mr-2"></i>Produtos cadastrados</h3>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover table-striped mb-0">
              <thead>
                <tr>
                  <th>SKU CMIG</th>
                  <th>Título</th>
                  <th>Estoque</th>
                  <th>Custo</th>
                  <th>PG Vinculado</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="products.length === 0">
                  <td colspan="7" class="text-center text-muted py-4">Nenhum produto cadastrado.</td>
                </tr>
                <tr v-for="p in products" :key="p.id">
                  <td><code>{{ p.sku_cmig }}</code></td>
                  <td>{{ p.title }}</td>
                  <td>
                    <span :class="p.stock_quantity === 0 ? 'text-danger font-weight-bold' : ''">
                      {{ p.stock_quantity }}
                    </span>
                  </td>
                  <td>{{ p.cost_price ? `R$ ${Number(p.cost_price).toFixed(2)}` : '—' }}</td>
                  <td>
                    <span v-if="p.pg_product_id" class="badge badge-success">PG #{{ p.pg_product_id }}</span>
                    <span v-else class="badge badge-secondary">Sem vínculo</span>
                  </td>
                  <td>
                    <span class="badge" :class="p.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ p.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink v-if="isAC" :to="`/cmig-products/${p.id}/edit?cmig_id=${cmigId}`" class="btn btn-sm btn-outline-primary mr-1" title="Editar">
                      <i class="fas fa-edit"></i>
                    </RouterLink>
                    <button v-if="isAC && !p.pg_product_id" class="btn btn-sm btn-outline-secondary mr-1" @click="openLinkPg(p)" title="Vincular ao PG">
                      <i class="fas fa-link"></i>
                    </button>
                    <button v-if="isUGO && !p.pg_product_id" class="btn btn-sm btn-outline-warning" @click="importToPg(p)" title="Importar para PG">
                      <i class="fas fa-file-import"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Modal Vincular PG -->
    <div v-if="showLinkModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Vincular ao PG</h5>
            <button class="close" @click="showLinkModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p>Produto: <strong>{{ selectedProduct?.title }}</strong></p>
            <div class="form-group">
              <label>ID do Produto PG</label>
              <input v-model="pgProductId" type="number" class="form-control" placeholder="Ex: 42" />
              <small class="text-muted">Informe o ID do produto no Produto Geral (PG) do Galpão.</small>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showLinkModal = false">Cancelar</button>
            <button class="btn btn-primary" @click="linkToPg" :disabled="savingLink">
              <span v-if="savingLink"><i class="fas fa-spinner fa-spin mr-1"></i></span>Vincular
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const cmigId = computed(() => route.query.cmig_id || route.params.cmig_id)
const cmig = ref(null)
const products = ref([])
const loading = ref(false)
const showLinkModal = ref(false)
const selectedProduct = ref(null)
const pgProductId = ref('')
const savingLink = ref(false)

const isAC = computed(() => authStore.user?.role === 'ac')
const isUGO = computed(() => ['ugo', 'admin'].includes(authStore.user?.role))

onMounted(async () => {
  if (!cmigId.value) return
  const { data: c } = await api.get(`/cmigs/${cmigId.value}`)
  cmig.value = c
  await loadProducts()
})

async function loadProducts() {
  loading.value = true
  try {
    const { data } = await api.get(`/cmigs/${cmigId.value}/products`)
    products.value = data
  } finally {
    loading.value = false
  }
}

function openLinkPg(product) {
  selectedProduct.value = product
  pgProductId.value = ''
  showLinkModal.value = true
}

async function linkToPg() {
  savingLink.value = true
  try {
    await api.post(`/cmigs/${cmigId.value}/products/${selectedProduct.value.id}/link-pg`, {
      pg_product_id: Number(pgProductId.value),
    })
    toast.success('Produto vinculado ao PG!')
    showLinkModal.value = false
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao vincular produto.')
  } finally {
    savingLink.value = false
  }
}

async function importToPg(product) {
  if (!confirm(`Importar "${product.title}" para o Produto Geral (PG)?`)) return
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${product.id}/import-to-pg`)
    toast.success(`Produto importado para o PG! SKU: ${data.sku}`)
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao importar produto.')
  }
}
</script>
