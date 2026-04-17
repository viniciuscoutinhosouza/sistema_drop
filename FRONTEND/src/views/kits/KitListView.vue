<template>
  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      <h3 class="card-title">Meus Kits</h3>
      <RouterLink to="/kits/new" class="btn btn-sm btn-primary">
        <i class="fas fa-plus mr-1"></i> Criar Kit
      </RouterLink>
    </div>
    <div class="card-body p-0">
      <table class="table table-sm">
        <thead><tr><th>#</th><th>SKU</th><th>Título</th><th>Estoque Calculado</th><th>Ações</th></tr></thead>
        <tbody>
          <tr v-if="loading"><td colspan="5" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></td></tr>
          <tr v-else-if="!kits.length"><td colspan="5" class="text-center py-4 text-muted">Nenhum kit criado</td></tr>
          <tr v-for="kit in kits" :key="kit.id">
            <td>{{ kit.id }}</td>
            <td><code>{{ kit.sku }}</code></td>
            <td>{{ kit.title }}</td>
            <td>
              <span :class="`badge badge-${kit.stock_quantity > 0 ? 'success' : 'danger'}`">
                {{ kit.stock_quantity }}
              </span>
            </td>
            <td>
              <RouterLink :to="`/kits/${kit.id}/edit`" class="btn btn-xs btn-outline-secondary">
                <i class="fas fa-edit"></i>
              </RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'

const kits = ref([])
const loading = ref(true)

onMounted(async () => {
  const { data } = await api.get('/kits')
  kits.value = data.items
  loading.value = false
})
</script>
