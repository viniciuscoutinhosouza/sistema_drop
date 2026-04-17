<template>
  <div>
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h3 class="card-title">Meus Produtos</h3>
        <RouterLink to="/products/new" class="btn btn-sm btn-primary">
          <i class="fas fa-plus mr-1"></i> Novo Produto
        </RouterLink>
      </div>
      <div class="card-body">
        <div class="input-group mb-3" style="max-width:400px">
          <input v-model="search" type="text" class="form-control" placeholder="Buscar produto..." @keyup.enter="load" />
          <div class="input-group-append">
            <button class="btn btn-primary" @click="load"><i class="fas fa-search"></i></button>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-sm table-hover">
            <thead>
              <tr><th>#</th><th>Título</th><th>Preço ML</th><th>Preço Shopee</th><th>Status</th><th>ML ID</th><th>Ações</th></tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="7" class="text-center"><i class="fas fa-spinner fa-spin"></i></td></tr>
              <tr v-else-if="!products.length"><td colspan="7" class="text-center text-muted">Nenhum produto cadastrado</td></tr>
              <tr v-for="p in products" :key="p.id">
                <td>{{ p.id }}</td>
                <td>{{ p.title }}</td>
                <td>{{ formatCurrency(p.sale_price_ml) }}</td>
                <td>{{ formatCurrency(p.sale_price_shopee) }}</td>
                <td><span :class="`badge badge-${p.status === 'active' ? 'success' : 'secondary'}`">{{ p.status }}</span></td>
                <td><small>{{ p.ml_item_id || '—' }}</small></td>
                <td>
                  <RouterLink :to="`/products/${p.id}/edit`" class="btn btn-xs btn-outline-secondary">
                    <i class="fas fa-edit"></i>
                  </RouterLink>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'

const products = ref([])
const loading = ref(true)
const search = ref('')

async function load() {
  loading.value = true
  const { data } = await api.get('/products', { params: search.value ? { search: search.value } : {} })
  products.value = data.items
  loading.value = false
}

onMounted(load)
</script>
