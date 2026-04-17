<template>
  <div>
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h3 class="card-title">Gestão do Catálogo (Fornecedor)</h3>
        <button class="btn btn-sm btn-primary" @click="showForm = true">
          <i class="fas fa-plus mr-1"></i> Novo Produto
        </button>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm">
          <thead><tr><th>#</th><th>SKU</th><th>Título</th><th>Custo</th><th>Estoque</th><th>Ativo</th><th>Ações</th></tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></td></tr>
            <tr v-for="p in products" :key="p.id">
              <td>{{ p.id }}</td>
              <td><code>{{ p.sku }}</code></td>
              <td>{{ p.title }}</td>
              <td>{{ formatCurrency(p.cost_price) }}</td>
              <td>
                <input
                  type="number"
                  :value="p.stock_quantity"
                  class="form-control form-control-sm"
                  style="width:80px"
                  @change="updateStock(p.id, $event.target.value)"
                />
              </td>
              <td>
                <span :class="`badge badge-${p.is_active ? 'success' : 'danger'}`">
                  {{ p.is_active ? 'Sim' : 'Não' }}
                </span>
              </td>
              <td>
                <button class="btn btn-xs btn-outline-danger" @click="deactivate(p.id)">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
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
const showForm = ref(false)

onMounted(async () => {
  const { data } = await api.get('/supplier')
  products.value = data
  loading.value = false
})

async function updateStock(id, qty) {
  await api.put(`/supplier/${id}/stock`, { stock_quantity: parseInt(qty) })
}

async function deactivate(id) {
  if (!confirm('Desativar produto?')) return
  await api.delete(`/supplier/${id}`)
  products.value = products.value.filter(p => p.id !== id)
}
</script>
