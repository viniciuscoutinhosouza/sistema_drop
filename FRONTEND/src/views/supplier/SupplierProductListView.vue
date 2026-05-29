<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Produtos Gerais (PG)</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/pg/novo-composto" class="btn btn-outline-primary mr-2">
              <i class="fas fa-layer-group mr-1"></i> Novo KIT
            </RouterLink>
            <RouterLink to="/pg/new" class="btn btn-primary">
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
            <h3 class="card-title"><i class="fas fa-boxes mr-2"></i>Produtos cadastrados</h3>
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
                <span class="text-muted small">{{ filteredProducts.length }} resultado{{ filteredProducts.length === 1 ? '' : 's' }}</span>
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
                  <th>SKU</th>
                  <th>Título</th>
                  <th>Custo</th>
                  <th>Preço Sugerido</th>
                  <th>Estoque</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="filteredProducts.length === 0">
                  <td colspan="8" class="text-center text-muted py-4">Nenhum produto cadastrado.</td>
                </tr>
                <tr v-for="p in filteredProducts" :key="p.id">
                  <td class="p-1 text-center">
                    <img v-if="p.thumbnail" :src="p.thumbnail"
                         style="width:56px;height:56px;object-fit:cover;border-radius:4px;" />
                    <div v-else style="width:56px;height:56px;background:#f4f4f4;border-radius:4px;display:flex;align-items:center;justify-content:center;">
                      <i class="fas fa-image text-muted"></i>
                    </div>
                  </td>
                  <td><code>{{ p.sku }}</code></td>
                  <td>
                    <span v-if="p.is_composite" class="badge badge-warning mr-1" style="font-size:0.7em">COMPOSTO</span>
                    <span v-else-if="p.product_type === 'variant'" class="badge badge-info mr-1" style="font-size:0.7em">VARIANTE</span>
                    {{ p.title }}
                  </td>
                  <td>{{ p.cost_price ? `R$ ${Number(p.cost_price).toFixed(2)}` : '—' }}</td>
                  <td>{{ p.suggested_price ? `R$ ${Number(p.suggested_price).toFixed(2)}` : '—' }}</td>
                  <td>
                    <input
                      type="number" min="0"
                      :value="p.stock_quantity"
                      class="form-control form-control-sm"
                      style="width:80px"
                      @change="updateStock(p.id, $event.target.value)"
                    />
                  </td>
                  <td>
                    <span :class="`badge badge-${p.is_active ? 'success' : 'secondary'}`">
                      {{ p.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink
                      :to="p.is_composite ? `/pg/${p.id}/editar-composto` : `/pg/${p.id}/edit`"
                      class="btn btn-sm btn-outline-primary mr-1" title="Editar"
                    >
                      <i class="fas fa-edit"></i>
                    </RouterLink>
                    <button class="btn btn-sm btn-outline-secondary mr-1" title="Duplicar produto" @click="duplicate(p)">
                      <i class="fas fa-copy"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-dark mr-1" title="Histórico de movimentação de estoque" @click="openMovements(p)">
                      <i class="fas fa-history"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" title="Desativar" @click="deactivate(p)">
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
  </div>

  <!-- M10: Modal Histórico de Movimentações (componente reutilizável) -->
  <StockMovementsModal
    v-model:show="movementsModal.show"
    product-type="pg"
    :product-id="movementsModal.product?.id"
    :product-sku="movementsModal.product?.sku || ''"
    :product-title="movementsModal.product?.title || ''"
    @recalculated="onStockRecalculated"
  />

  <!-- Modal Duplicar PG -->
  <div v-if="duplicateModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
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
              autofocus
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
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import StockMovementsModal from '@/components/stock/StockMovementsModal.vue'

const products = ref([])
const loading  = ref(true)
const categories = ref([])

const searchQuery = ref('')
const categoryFilter = ref('')
const sortBy = ref('title_asc')

const categoryMap = computed(() => {
  const m = {}
  for (const c of categories.value) m[c.id] = c.name
  return m
})

function _norm(s) { return (s || '').toString().toLowerCase().trim() }

const filteredProducts = computed(() => {
  let list = products.value
  if (categoryFilter.value) list = list.filter(p => p.category_id == categoryFilter.value)
  const q = _norm(searchQuery.value)
  if (q) {
    list = list.filter(p => _norm(p.title).includes(q) || _norm(p.sku).includes(q))
  }
  const arr = [...list]
  switch (sortBy.value) {
    case 'title_desc': arr.sort((a, b) => _norm(b.title).localeCompare(_norm(a.title))); break
    case 'sku_asc':    arr.sort((a, b) => _norm(a.sku).localeCompare(_norm(b.sku))); break
    case 'sku_desc':   arr.sort((a, b) => _norm(b.sku).localeCompare(_norm(a.sku))); break
    case 'category_asc':
      arr.sort((a, b) => _norm(categoryMap.value[a.category_id]).localeCompare(_norm(categoryMap.value[b.category_id])))
      break
    case 'title_asc':
    default:
      arr.sort((a, b) => _norm(a.title).localeCompare(_norm(b.title)))
  }
  return arr
})

async function loadCategories() {
  try {
    const { data } = await api.get('/catalog/categories')
    categories.value = Array.isArray(data) ? data : []
  } catch {
    categories.value = []
  }
}
const toast    = useToast()
const router   = useRouter()

const duplicateModal = ref({ show: false, srcId: null, srcSku: '', newSku: '', loading: false })

// M10: estado mínimo — a lógica completa está no componente StockMovementsModal
const movementsModal = reactive({ show: false, product: null })

function openMovements(product) {
  movementsModal.product = product
  movementsModal.show = true
}

function onStockRecalculated({ new_stock }) {
  // Atualiza o cache local para a coluna estoque na lista refletir sem recarregar
  if (movementsModal.product) movementsModal.product.stock_quantity = new_stock
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/pg')
    products.value = data
  } finally {
    loading.value = false
  }
}

async function updateStock(id, qty) {
  try {
    await api.put(`/pg/${id}/stock`, { stock_quantity: parseInt(qty) })
  } catch (e) {
    toast.error('Erro ao atualizar estoque.')
  }
}

function duplicate(p) {
  duplicateModal.value = { show: true, srcId: p.id, srcSku: p.sku, newSku: '', loading: false }
}

async function confirmDuplicate() {
  const m = duplicateModal.value
  if (!m.newSku.trim()) return
  m.loading = true
  try {
    const { data } = await api.post(`/pg/${m.srcId}/duplicate`, { sku: m.newSku.trim() })
    toast.success(`Produto duplicado! SKU: ${data.sku}`)
    duplicateModal.value.show = false
    router.push(`/pg/${data.id}/edit`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao duplicar produto.')
    m.loading = false
  }
}

async function deactivate(p) {
  if (!confirm(`Excluir "${p.title}"?\n\nSe o produto não possuir vendas será excluído permanentemente, caso contrário será desativado.`)) return
  try {
    const { data } = await api.delete(`/pg/${p.id}`)
    if (data?.action === 'deactivated') {
      toast.warning(data.message || 'Produto desativado (possui vendas).')
    } else {
      toast.success('Produto excluído com sucesso!')
    }
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir produto.')
  }
}

onMounted(() => {
  load()
  loadCategories()
})
</script>
