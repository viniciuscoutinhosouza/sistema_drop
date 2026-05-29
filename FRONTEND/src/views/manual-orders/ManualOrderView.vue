<template>
  <div>
    <div class="alert alert-info">
      <i class="fas fa-info-circle mr-2"></i>
      Monte um pedido manual com itens do catálogo PG ou CMIG e selecione o cliente.
      Útil para vendas fora dos marketplaces (WhatsApp, Instagram, balcão).
    </div>

    <!-- 1) CMIG -->
    <div class="card mb-3">
      <div class="card-header">
        <h3 class="card-title"><i class="fas fa-id-card mr-2"></i> CMIG</h3>
      </div>
      <div class="card-body">
        <div class="row align-items-end">
          <div class="col-md-6">
            <label class="small mb-1">Selecione a CMIG do pedido</label>
            <select v-model.number="cmigId" class="form-control" @change="onCmigChange">
              <option :value="null">Selecione…</option>
              <option v-for="c in availableCmigs" :key="c.id" :value="c.id">
                {{ c.company_name || c.trade_name || ('CMIG #' + c.id) }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <template v-if="cmigId">
      <!-- 2) Seleção de Produtos -->
      <div class="card mb-3">
        <div class="card-header d-flex justify-content-between align-items-center flex-wrap">
          <h3 class="card-title"><i class="fas fa-boxes mr-2"></i> Selecionar Produtos</h3>
          <div class="btn-group">
            <button
              type="button"
              class="btn btn-sm"
              :class="catalogTab === 'pg' ? 'btn-primary' : 'btn-outline-primary'"
              @click="setTab('pg')"
            >
              <i class="fas fa-warehouse mr-1"></i> Catálogo PG
            </button>
            <button
              type="button"
              class="btn btn-sm"
              :class="catalogTab === 'cmig' ? 'btn-primary' : 'btn-outline-primary'"
              @click="setTab('cmig')"
            >
              <i class="fas fa-id-card mr-1"></i> Catálogo CMIG
            </button>
          </div>
        </div>
        <div class="card-body">
          <div class="input-group mb-3" style="max-width:500px">
            <input
              v-model="search"
              type="text"
              class="form-control"
              :placeholder="catalogTab === 'pg' ? 'Buscar no Catálogo PG…' : 'Buscar no Catálogo CMIG…'"
              @keyup.enter="reloadProducts"
            />
            <div class="input-group-append">
              <button class="btn btn-primary" :disabled="loadingProducts" @click="reloadProducts">
                <i class="fas" :class="loadingProducts ? 'fa-spinner fa-spin' : 'fa-search'"></i>
              </button>
            </div>
          </div>

          <div v-if="loadingProducts && !products.length" class="text-center text-muted py-4">
            Carregando…
          </div>
          <div v-else-if="!products.length" class="text-center text-muted py-4">
            Nenhum produto encontrado.
          </div>
          <div v-else class="row">
            <div
              v-for="p in products"
              :key="catalogTab + '-' + p.id"
              class="col-xl-2 col-lg-3 col-md-4 col-sm-6 mb-3"
            >
              <div class="card h-100">
                <div
                  style="height:130px;background:#f8f9fa;display:flex;align-items:center;justify-content:center;overflow:hidden"
                >
                  <img
                    :src="p._thumb || 'https://via.placeholder.com/200x140?text=Sem+Foto'"
                    style="max-height:100%;max-width:100%;object-fit:contain"
                    :alt="p.title"
                  />
                </div>
                <div class="card-body p-2">
                  <p class="text-muted mb-0" style="font-size:10px">{{ p._sku }}</p>
                  <p class="font-weight-bold mb-1" style="font-size:12px">
                    {{ (p.title || '').slice(0, 50) }}{{ (p.title || '').length > 50 ? '…' : '' }}
                  </p>
                  <p class="text-success mb-0" style="font-size:13px;font-weight:bold">
                    {{ formatCurrency(p.cost_price) }}
                  </p>
                </div>
                <div class="card-footer p-1">
                  <button class="btn btn-success btn-sm btn-block" @click="addToCart(p)">
                    <i class="fas fa-cart-plus mr-1"></i> Adicionar
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div v-if="catalogTab === 'pg' && pgTotal > pgPageSize" class="d-flex justify-content-between align-items-center mt-2">
            <small class="text-muted">{{ products.length }} de {{ pgTotal }}</small>
            <div class="btn-group btn-group-sm">
              <button class="btn btn-outline-secondary" :disabled="pgPage === 1" @click="changePgPage(pgPage - 1)">
                <i class="fas fa-chevron-left"></i>
              </button>
              <button class="btn btn-outline-secondary" disabled>Página {{ pgPage }}</button>
              <button class="btn btn-outline-secondary" :disabled="pgPage * pgPageSize >= pgTotal" @click="changePgPage(pgPage + 1)">
                <i class="fas fa-chevron-right"></i>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 3) Cliente -->
      <div class="card mb-3">
        <div class="card-header">
          <h3 class="card-title"><i class="fas fa-user mr-2"></i> Cliente</h3>
        </div>
        <div class="card-body">
          <div v-if="!selectedPerson" class="d-flex flex-wrap" style="gap:.5rem">
            <button class="btn btn-outline-primary" @click="showSearch = true">
              <i class="fas fa-search mr-1"></i> Buscar cliente
            </button>
            <button class="btn btn-success" @click="showForm = true">
              <i class="fas fa-user-plus mr-1"></i> Novo cliente
            </button>
          </div>
          <div v-else class="d-flex justify-content-between align-items-start">
            <div>
              <strong>{{ selectedPerson.name }}</strong>
              <small v-if="selectedPerson.trade_name" class="d-block text-muted">
                {{ selectedPerson.trade_name }}
              </small>
              <small class="d-block text-muted">
                {{ selectedPerson.document }}
                <span v-if="selectedPerson.city">— {{ selectedPerson.city }}/{{ selectedPerson.state }}</span>
              </small>
            </div>
            <button class="btn btn-sm btn-outline-secondary" @click="selectedPerson = null">
              <i class="fas fa-exchange-alt mr-1"></i> Trocar
            </button>
          </div>
        </div>
      </div>

      <!-- 4) Carrinho -->
      <div class="card mb-3">
        <div class="card-header">
          <h3 class="card-title"><i class="fas fa-shopping-cart mr-2"></i> Carrinho</h3>
        </div>
        <div class="card-body">
          <div v-if="!cart.length" class="text-center text-muted py-3">
            Adicione produtos do catálogo acima para montar o pedido.
          </div>
          <div v-else class="table-responsive">
            <table class="table table-sm align-middle">
              <thead>
                <tr>
                  <th style="width:60px"></th>
                  <th>SKU</th>
                  <th>Produto</th>
                  <th style="width:120px">Qtde</th>
                  <th class="text-right">Unitário</th>
                  <th class="text-right">Subtotal</th>
                  <th style="width:40px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(it, idx) in cart" :key="it.kind + '-' + it.id">
                  <td>
                    <img
                      v-if="it.thumb"
                      :src="it.thumb"
                      style="height:40px;width:40px;object-fit:contain;background:#f8f9fa"
                    />
                  </td>
                  <td>
                    <small class="text-muted">{{ it.sku }}</small>
                    <span class="badge ml-1" :class="it.kind === 'pg' ? 'badge-info' : 'badge-warning'">
                      {{ it.kind === 'pg' ? 'PG' : 'CMIG' }}
                    </span>
                  </td>
                  <td>{{ it.title }}</td>
                  <td>
                    <input
                      v-model.number="it.quantity"
                      type="number"
                      min="1"
                      class="form-control form-control-sm"
                      @change="normalizeQty(idx)"
                    />
                  </td>
                  <td class="text-right">{{ formatCurrency(it.unit_cost) }}</td>
                  <td class="text-right">
                    <strong>{{ formatCurrency(it.unit_cost * it.quantity) }}</strong>
                  </td>
                  <td>
                    <button class="btn btn-sm btn-link text-danger" @click="removeItem(idx)">
                      <i class="fas fa-times"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td colspan="5" class="text-right"><strong>Total</strong></td>
                  <td class="text-right">
                    <strong class="text-success">{{ formatCurrency(cartTotal) }}</strong>
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
        <div class="card-footer text-right">
          <button
            class="btn btn-success"
            :disabled="!canSubmit || submitting"
            @click="closeOrder"
          >
            <span v-if="submitting"><i class="fas fa-spinner fa-spin mr-1"></i> Fechando…</span>
            <span v-else><i class="fas fa-check mr-1"></i> Fechar pedido</span>
          </button>
        </div>
      </div>
    </template>

    <PersonSearchModal
      :show="showSearch"
      :cmig-id="cmigId"
      @select="onPersonSelected"
      @close="showSearch = false"
    />
    <PersonFormModal
      :show="showForm"
      :cmig-id="cmigId"
      @created="onPersonCreated"
      @close="showForm = false"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency } from '@/utils/formatters'
import PersonSearchModal from '@/components/people/PersonSearchModal.vue'
import PersonFormModal from '@/components/people/PersonFormModal.vue'

const router = useRouter()
const toast = useToast()

const availableCmigs = ref([])
const cmigId = ref(null)

const catalogTab = ref('pg')
const search = ref('')
const products = ref([])
const loadingProducts = ref(false)

const pgPage = ref(1)
const pgPageSize = 18
const pgTotal = ref(0)

const cart = ref([])

const selectedPerson = ref(null)
const showSearch = ref(false)
const showForm = ref(false)

const submitting = ref(false)

const cartTotal = computed(() =>
  cart.value.reduce((acc, it) => acc + (Number(it.unit_cost) || 0) * (Number(it.quantity) || 0), 0)
)
const canSubmit = computed(() => cart.value.length > 0 && !!selectedPerson.value && !!cmigId.value)

async function loadAvailableCmigs() {
  try {
    const { data } = await api.get('/orders/cmigs/available')
    availableCmigs.value = data.items || []
    if (availableCmigs.value.length === 1) {
      cmigId.value = availableCmigs.value[0].id
      onCmigChange()
    }
  } catch {
    toast.error('Falha ao carregar CMIGs disponíveis')
  }
}

function onCmigChange() {
  selectedPerson.value = null
  cart.value = []
  products.value = []
  pgPage.value = 1
  pgTotal.value = 0
  if (cmigId.value) reloadProducts()
}

function setTab(tab) {
  catalogTab.value = tab
  search.value = ''
  pgPage.value = 1
  reloadProducts()
}

async function reloadProducts() {
  if (!cmigId.value) return
  loadingProducts.value = true
  try {
    if (catalogTab.value === 'pg') {
      const { data } = await api.get('/catalog', {
        params: { search: search.value || undefined, page: pgPage.value, page_size: pgPageSize },
      })
      pgTotal.value = data.total || 0
      products.value = (data.items || []).map((p) => ({
        ...p,
        _sku: p.sku,
        _thumb: p.image_url,
      }))
    } else {
      const { data } = await api.get(`/cmigs/${cmigId.value}/products`)
      const all = Array.isArray(data) ? data : []
      const term = (search.value || '').toLowerCase().trim()
      const filtered = term
        ? all.filter(
            (p) =>
              (p.title || '').toLowerCase().includes(term) ||
              (p.sku_cmig || '').toLowerCase().includes(term)
          )
        : all
      products.value = filtered.map((p) => ({
        ...p,
        _sku: p.sku_cmig,
        _thumb: p.images && p.images.length ? p.images[0].url : null,
      }))
      pgTotal.value = products.value.length
    }
  } catch {
    toast.error('Falha ao carregar produtos')
    products.value = []
  } finally {
    loadingProducts.value = false
  }
}

function changePgPage(p) {
  pgPage.value = p
  reloadProducts()
}

function addToCart(p) {
  const kind = catalogTab.value
  const existing = cart.value.find((c) => c.kind === kind && c.id === p.id)
  if (existing) {
    existing.quantity += 1
    return
  }
  cart.value.push({
    kind,
    id: p.id,
    sku: p._sku,
    title: p.title,
    thumb: p._thumb || null,
    quantity: 1,
    unit_cost: Number(p.cost_price) || 0,
  })
}

function normalizeQty(idx) {
  const it = cart.value[idx]
  if (!it) return
  if (!Number.isFinite(it.quantity) || it.quantity < 1) it.quantity = 1
}

function removeItem(idx) {
  cart.value.splice(idx, 1)
}

function onPersonSelected(person) {
  selectedPerson.value = person
  showSearch.value = false
}

function onPersonCreated(person) {
  selectedPerson.value = person
  showForm.value = false
}

async function closeOrder() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const { data } = await api.post('/manual-orders', {
      cmig_id: cmigId.value,
      buyer_person_id: selectedPerson.value.id,
      items: cart.value.map((it) => ({ kind: it.kind, id: it.id, quantity: it.quantity })),
    })
    toast.success('Pedido criado com sucesso')
    router.push(`/orders/${data.id}`)
  } catch (err) {
    const detail = err?.response?.data?.detail
    toast.error(typeof detail === 'string' ? detail : 'Erro ao fechar pedido')
  } finally {
    submitting.value = false
  }
}

watch(catalogTab, () => {
  // mudou só via setTab — já recarrega
})

loadAvailableCmigs()
</script>
