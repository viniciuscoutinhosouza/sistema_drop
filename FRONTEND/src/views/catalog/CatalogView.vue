<template>
  <div>
    <!-- Search and Filters -->
    <div class="card mb-3">
      <div class="card-body py-2">
        <div class="row align-items-center">
          <div class="col-md-4">
            <div class="input-group input-group-sm">
              <input v-model="filters.search" type="text" class="form-control" placeholder="Buscar produto..." @keyup.enter="loadProducts" />
              <div class="input-group-append">
                <button class="btn btn-primary" @click="loadProducts"><i class="fas fa-search"></i></button>
              </div>
            </div>
          </div>
          <div class="col-md-3">
            <select v-model="filters.category_id" class="form-control form-control-sm" @change="loadProducts">
              <option value="">Todas as categorias</option>
              <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
            </select>
          </div>
          <div class="col-md-3">
            <select v-model="filters.sort" class="form-control form-control-sm" @change="loadProducts">
              <option value="newest">Mais recentes</option>
              <option value="cheapest">Menor preço</option>
              <option value="expensive">Maior preço</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.page_size" class="form-control form-control-sm" @change="loadProducts">
              <option :value="8">8 por página</option>
              <option :value="16">16 por página</option>
              <option :value="32">32 por página</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-5">
      <i class="fas fa-spinner fa-spin fa-3x text-muted"></i>
    </div>

    <!-- Product Grid -->
    <div v-else>
      <div class="row">
        <div
          v-for="product in products"
          :key="product.id"
          class="col-xl-3 col-lg-4 col-md-6 mb-4"
        >
          <div class="card h-100 shadow-sm">
            <RouterLink :to="`/catalog/${product.id}`">
              <img
                :src="product.image_url || 'https://via.placeholder.com/300x200?text=Sem+Foto'"
                class="card-img-top"
                style="height: 180px; object-fit: cover"
                :alt="product.title"
              />
            </RouterLink>
            <div class="card-body p-3">
              <p class="text-muted small mb-1">({{ product.sku }})</p>
              <h6 class="card-title mb-1">
                {{ product.title.slice(0, 60) }}{{ product.title.length > 60 ? '...' : '' }}
              </h6>
              <p class="text-success font-weight-bold mb-1 h5">{{ formatCurrency(product.cost_price) }}</p>
              <p class="text-muted small mb-0">Estoque: {{ product.stock_quantity }}</p>
            </div>
            <div class="card-footer p-2">
              <RouterLink :to="`/products/new?catalog_id=${product.id}`" class="btn btn-primary btn-sm btn-block">
                <i class="fas fa-plus mr-1"></i> Cadastrar Produto
              </RouterLink>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!products.length" class="text-center py-5 text-muted">
        <i class="fas fa-box-open fa-3x mb-3"></i>
        <p>Nenhum produto encontrado</p>
      </div>

      <!-- Pagination -->
      <nav v-if="totalPages > 1" class="mt-3">
        <ul class="pagination justify-content-center">
          <li :class="['page-item', currentPage <= 1 && 'disabled']">
            <button class="page-link" @click="goToPage(currentPage - 1)">Anterior</button>
          </li>
          <li
            v-for="p in paginationRange"
            :key="p"
            :class="['page-item', p === currentPage && 'active']"
          >
            <button class="page-link" @click="goToPage(p)">{{ p }}</button>
          </li>
          <li :class="['page-item', currentPage >= totalPages && 'disabled']">
            <button class="page-link" @click="goToPage(currentPage + 1)">Próxima</button>
          </li>
        </ul>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'

const products = ref([])
const categories = ref([])
const loading = ref(true)
const total = ref(0)
const currentPage = ref(1)

const filters = reactive({
  search: '',
  category_id: '',
  sort: 'newest',
  page_size: 16,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.page_size)))

const paginationRange = computed(() => {
  const range = []
  const start = Math.max(1, currentPage.value - 2)
  const end = Math.min(totalPages.value, currentPage.value + 2)
  for (let i = start; i <= end; i++) range.push(i)
  return range
})

async function loadProducts() {
  loading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: filters.page_size,
      sort: filters.sort,
    }
    if (filters.search) params.search = filters.search
    if (filters.category_id) params.category_id = filters.category_id

    const { data } = await api.get('/catalog', { params })
    products.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  const { data } = await api.get('/catalog/categories')
  categories.value = data
}

function goToPage(page) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    loadProducts()
  }
}

onMounted(() => {
  loadCategories()
  loadProducts()
})
</script>
