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
            <RouterLink v-if="isAC" :to="`/cmig-products/new?cmig_id=${cmigId}`" class="btn btn-outline-primary mr-2">
              <i class="fas fa-plus mr-1"></i> Novo Produto
            </RouterLink>
            <RouterLink v-if="isAC" :to="`/cmig-products/novo-composto?cmig_id=${cmigId}`" class="btn btn-primary">
              <i class="fas fa-layer-group mr-1"></i> Novo KIT
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-header d-flex align-items-center">
            <h3 class="card-title flex-grow-1"><i class="fas fa-box mr-2"></i>Produtos cadastrados</h3>
            <div class="btn-group btn-group-sm">
              <button class="btn btn-outline-secondary" :class="{ active: filter === 'all' }" @click="setFilter('all')">Todos</button>
              <button class="btn btn-outline-secondary" :class="{ active: filter === 'simple' }" @click="setFilter('simple')">Simples</button>
              <button class="btn btn-outline-secondary" :class="{ active: filter === 'composite' }" @click="setFilter('composite')">KITs</button>
            </div>
          </div>
          <div class="card-body p-2 border-bottom" style="background:#f8f9fa">
            <div class="row no-gutters" style="gap:.5rem">
              <div class="col-md flex-grow-1" style="min-width:200px">
                <input v-model="searchQuery" class="form-control form-control-sm" placeholder="Buscar por nome ou SKU..." />
              </div>
              <div class="col-md" style="min-width:160px;max-width:240px">
                <select v-model="categoryFilter" class="form-control form-control-sm">
                  <option value="">Todas categorias</option>
                  <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </div>
              <div class="col-md" style="min-width:140px;max-width:220px">
                <select v-model="sortBy" class="form-control form-control-sm">
                  <option value="title_asc">Nome (A-Z)</option>
                  <option value="title_desc">Nome (Z-A)</option>
                  <option value="sku_asc">SKU (A-Z)</option>
                  <option value="sku_desc">SKU (Z-A)</option>
                  <option value="category_asc">Categoria (A-Z)</option>
                </select>
              </div>
              <div class="col-auto d-flex align-items-center">
                <span class="text-muted small">{{ products.length }} resultado{{ products.length === 1 ? '' : 's' }}</span>
              </div>
            </div>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover table-striped mb-0">
              <thead>
                <tr>
                  <th style="width:72px"></th>
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
                  <td colspan="8" class="text-center text-muted py-4">Nenhum produto cadastrado.</td>
                </tr>
                <tr v-for="p in products" :key="p.id">
                  <td class="p-1 text-center">
                    <img v-if="getThumb(p)" :src="getThumb(p)"
                         style="width:56px;height:56px;object-fit:cover;border-radius:4px;" />
                    <div v-else style="width:56px;height:56px;background:#f4f4f4;border-radius:4px;display:flex;align-items:center;justify-content:center;">
                      <i class="fas fa-image text-muted"></i>
                    </div>
                  </td>
                  <td><code>{{ p.sku_cmig }}</code></td>
                  <td>
                    <span v-if="p.is_composite" class="badge badge-warning mr-1" style="font-size:0.7em">KIT</span>
                    {{ p.title }}
                    <div v-if="p.brand || p.model" class="small text-muted mt-1">
                      <span v-if="p.brand">{{ p.brand }}</span>
                      <span v-if="p.brand && p.model"> · </span>
                      <span v-if="p.model">{{ p.model }}</span>
                    </div>
                  </td>
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
                    <RouterLink
                      v-if="isAC || isUGO"
                      :to="p.is_composite ? `/cmig-products/${p.id}/editar-composto?cmig_id=${cmigId}` : `/cmig-products/${p.id}/edit?cmig_id=${cmigId}`"
                      class="btn btn-sm btn-outline-primary mr-1" title="Editar"
                    >
                      <i class="fas fa-edit"></i>
                    </RouterLink>
                    <button v-if="isAC || isUGO" class="btn btn-sm btn-outline-secondary mr-1" title="Duplicar produto" @click="duplicate(p)">
                      <i class="fas fa-copy"></i>
                    </button>
                    <button v-if="isAC && !p.pg_product_id" class="btn btn-sm btn-outline-secondary mr-1" @click="openLinkPg(p)" title="Vincular ao PG">
                      <i class="fas fa-link"></i>
                    </button>
                    <button v-if="isUGO && !p.pg_product_id" class="btn btn-sm btn-outline-warning mr-1" @click="importToPg(p)" title="Importar para PG">
                      <i class="fas fa-file-import"></i>
                    </button>
                    <button v-if="isUGO && p.pg_product_id" class="btn btn-sm btn-outline-info mr-1" @click="syncPg(p)" title="Sincronizar dados com PG">
                      <i class="fas fa-sync-alt"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-dark mr-1" @click="openMovements(p)" title="Histórico de movimentação de estoque">
                      <i class="fas fa-history"></i>
                    </button>
                    <button v-if="isAC" class="btn btn-sm btn-outline-danger" @click="deleteProduct(p)" title="Excluir produto">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Modal Duplicar CMIG -->
    <div v-if="duplicateModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header py-2">
            <h6 class="modal-title"><i class="fas fa-copy mr-2"></i>Duplicar Produto</h6>
            <button type="button" class="close" @click="duplicateModal.show = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted mb-2" style="font-size:12px">SKU de origem: <strong>{{ duplicateModal.srcSku }}</strong></p>
            <div class="form-group mb-0">
              <label class="font-weight-bold" style="font-size:13px">Novo SKU <span class="text-danger">*</span></label>
              <input
                v-model="duplicateModal.newSku"
                type="text"
                class="form-control form-control-sm"
                placeholder="Digite o SKU do novo produto"
                @keyup.enter="confirmDuplicate"
              />
            </div>
          </div>
          <div class="modal-footer py-2">
            <button class="btn btn-sm btn-secondary" @click="duplicateModal.show = false">Cancelar</button>
            <button class="btn btn-sm btn-primary" :disabled="!duplicateModal.newSku.trim() || duplicateModal.loading" @click="confirmDuplicate">
              <i v-if="duplicateModal.loading" class="fas fa-spinner fa-spin mr-1"></i>
              Duplicar
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- M10: Modal Histórico de Movimentações (componente reutilizável) -->
    <StockMovementsModal
      v-model:show="movementsModal.show"
      product-type="cmig"
      :product-id="movementsModal.product?.id"
      :product-sku="movementsModal.product?.sku_cmig || ''"
      :product-title="movementsModal.product?.title || ''"
      :cmig-id="cmigId"
      @recalculated="onStockRecalculated"
    />

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
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import StockMovementsModal from '@/components/stock/StockMovementsModal.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

const duplicateModal = ref({ show: false, srcId: null, srcSku: '', newSku: '', loading: false })

// M10: estado mínimo — lógica completa no componente StockMovementsModal
const movementsModal = reactive({ show: false, product: null })

function openMovements(product) {
  movementsModal.product = product
  movementsModal.show = true
}

function onStockRecalculated({ new_stock }) {
  if (movementsModal.product) movementsModal.product.stock_quantity = new_stock
}

const cmigId = computed(() => route.query.cmig_id || route.params.cmig_id)
const cmig = ref(null)
const allProducts = ref([])
const categories = ref([])
const filter = ref('all')
const searchQuery = ref('')
const categoryFilter = ref('')
const sortBy = ref('title_asc')

const categoryMap = computed(() => {
  const m = {}
  for (const c of categories.value) m[c.id] = c.name
  return m
})

function _norm(s) { return (s || '').toString().toLowerCase().trim() }

const products = computed(() => {
  let list = allProducts.value
  if (filter.value === 'composite') list = list.filter(p => p.is_composite)
  else if (filter.value === 'simple') list = list.filter(p => !p.is_composite)
  if (categoryFilter.value) list = list.filter(p => p.category_id == categoryFilter.value)
  const q = _norm(searchQuery.value)
  if (q) {
    list = list.filter(p =>
      _norm(p.title).includes(q) ||
      _norm(p.sku_cmig).includes(q)
    )
  }
  const arr = [...list]
  switch (sortBy.value) {
    case 'title_desc': arr.sort((a, b) => _norm(b.title).localeCompare(_norm(a.title))); break
    case 'sku_asc':    arr.sort((a, b) => _norm(a.sku_cmig).localeCompare(_norm(b.sku_cmig))); break
    case 'sku_desc':   arr.sort((a, b) => _norm(b.sku_cmig).localeCompare(_norm(a.sku_cmig))); break
    case 'category_asc':
      arr.sort((a, b) => _norm(categoryMap.value[a.category_id]).localeCompare(_norm(categoryMap.value[b.category_id])))
      break
    case 'title_asc':
    default:
      arr.sort((a, b) => _norm(a.title).localeCompare(_norm(b.title)))
  }
  return arr
})
const loading = ref(false)
const showLinkModal = ref(false)
const selectedProduct = ref(null)
const pgProductId = ref('')
const savingLink = ref(false)

const isAC = computed(() => authStore.user?.role === 'ac')
const isUGO = computed(() => ['ugo', 'admin'].includes(authStore.user?.role))

function setFilter(val) { filter.value = val }

async function loadCategories() {
  try {
    const { data } = await api.get('/catalog/categories')
    categories.value = Array.isArray(data) ? data : []
  } catch {
    categories.value = []
  }
}

onMounted(async () => {
  if (!cmigId.value) return
  const { data: c } = await api.get(`/cmigs/${cmigId.value}`)
  cmig.value = c
  await Promise.all([loadProducts(), loadCategories()])
})

function getThumb(p) {
  if (p.images && p.images.length) return p.images[0].url
  if (p.pictures_json) {
    try {
      const pics = JSON.parse(p.pictures_json)
      if (pics.length) return pics[0].url
    } catch {}
  }
  return null
}

async function loadProducts() {
  loading.value = true
  try {
    const { data } = await api.get(`/cmigs/${cmigId.value}/products`)
    allProducts.value = data
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

function duplicate(p) {
  duplicateModal.value = { show: true, srcId: p.id, srcSku: p.sku_cmig, newSku: '', loading: false }
}

async function confirmDuplicate() {
  const m = duplicateModal.value
  if (!m.newSku.trim()) return
  m.loading = true
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${m.srcId}/duplicate`, { sku_cmig: m.newSku.trim() })
    toast.success(`Produto duplicado! SKU: ${data.sku_cmig}`)
    duplicateModal.value.show = false
    router.push(`/cmig-products/${data.id}/edit?cmig_id=${cmigId.value}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao duplicar produto.')
    m.loading = false
  }
}

async function deleteProduct(p) {
  if (!confirm(`Excluir "${p.title}"?\n\nSe o produto não possuir vendas será excluído permanentemente, caso contrário será desativado.`)) return
  try {
    const { data } = await api.delete(`/cmigs/${cmigId.value}/products/${p.id}`)
    if (data?.action === 'deactivated') {
      toast.warning(data.message || 'Produto desativado (possui vendas).')
    } else {
      toast.success('Produto excluído com sucesso!')
    }
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir produto.')
  }
}

async function importToPg(product) {
  if (!confirm(`Importar "${product.title}" para o Produto Geral (PG)?`)) return
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${product.id}/import-to-pg`)
    const extras = [
      data.photos_imported ? `${data.photos_imported} foto(s)` : null,
      data.variants_imported ? `${data.variants_imported} variante(s)` : null,
      data.brand ? `Marca: ${data.brand}` : null,
      data.model ? `Modelo: ${data.model}` : null,
    ].filter(Boolean).join(' · ')
    toast.success(`Produto importado para o PG! SKU: ${data.sku}${extras ? ' · ' + extras : ''}`)
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao importar produto.')
  }
}

async function syncPg(product) {
  if (!confirm(`Sincronizar dados de "${product.title}" com o PG vinculado (PG #${product.pg_product_id})?\n\nIsso irá atualizar: Marca, Modelo, EAN, NCM, CEST, dimensões e origem no PG.`)) return
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${product.id}/sync-pg`)
    const synced = [
      data.brand ? `Marca: ${data.brand}` : null,
      data.model ? `Modelo: ${data.model}` : null,
      data.ean ? `EAN: ${data.ean}` : null,
    ].filter(Boolean).join(' · ')
    toast.success(`PG sincronizado!${synced ? ' ' + synced : ' (sem Marca/Modelo no CMIG — edite o produto CMIG primeiro)'}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar com PG.')
  }
}
</script>
