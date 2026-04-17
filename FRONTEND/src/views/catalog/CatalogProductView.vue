<template>
  <div v-if="product">
    <div class="row">
      <div class="col-md-5">
        <img
          :src="primaryImage || 'https://via.placeholder.com/400x300?text=Sem+Foto'"
          class="img-fluid rounded shadow-sm"
          :alt="product.title"
        />
        <div class="d-flex mt-2 flex-wrap">
          <img
            v-for="(img, i) in product.images.slice(0, 5)"
            :key="i"
            :src="img.url"
            class="img-thumbnail mr-1 mb-1"
            style="width:60px;height:60px;object-fit:cover;cursor:pointer"
            @click="primaryImage = img.url"
          />
        </div>
      </div>
      <div class="col-md-7">
        <p class="text-muted mb-1">SKU: {{ product.sku }}</p>
        <h3>{{ product.title }}</h3>
        <h4 class="text-success">{{ formatCurrency(product.cost_price) }}</h4>
        <p class="text-muted">Estoque disponível: <strong>{{ product.stock_quantity }}</strong></p>
        <table class="table table-sm table-borderless w-auto">
          <tr v-if="product.weight_kg"><th>Peso</th><td>{{ product.weight_kg }} kg</td></tr>
          <tr v-if="product.brand"><th>Marca</th><td>{{ product.brand }}</td></tr>
          <tr v-if="product.ncm"><th>NCM</th><td>{{ product.ncm }}</td></tr>
        </table>

        <RouterLink
          :to="`/products/new?catalog_id=${product.id}`"
          class="btn btn-primary btn-lg mt-3"
        >
          <i class="fas fa-plus mr-2"></i> Cadastrar Produto
        </RouterLink>
        <RouterLink to="/catalog" class="btn btn-outline-secondary btn-lg mt-3 ml-2">
          Voltar ao Catálogo
        </RouterLink>
      </div>
    </div>

    <div v-if="product.description" class="card mt-4">
      <div class="card-header"><h5 class="card-title">Descrição</h5></div>
      <div class="card-body" v-html="product.description"></div>
    </div>
  </div>
  <div v-else class="text-center py-5"><i class="fas fa-spinner fa-spin fa-3x text-muted"></i></div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'

const route = useRoute()
const product = ref(null)
const primaryImage = ref('')

onMounted(async () => {
  const { data } = await api.get(`/catalog/${route.params.id}`)
  product.value = data
  primaryImage.value = data.images.find(i => i.is_primary)?.url || data.images[0]?.url || ''
})
</script>
