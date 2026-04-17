<template>
  <div>
    <div class="alert alert-info">
      <i class="fas fa-info-circle mr-2"></i>
      Compre diretamente do fornecedor sem venda no marketplace.
      Útil para pedidos de clientes do WhatsApp, Instagram, etc.
    </div>

    <!-- Search catalog -->
    <div class="card mb-3">
      <div class="card-header"><h3 class="card-title">Selecionar Produto</h3></div>
      <div class="card-body">
        <div class="input-group mb-3" style="max-width:500px">
          <input v-model="search" type="text" class="form-control" placeholder="Buscar produto no catálogo..." @keyup.enter="searchProducts" />
          <div class="input-group-append">
            <button class="btn btn-primary" @click="searchProducts"><i class="fas fa-search"></i></button>
          </div>
        </div>
        <div class="row">
          <div v-for="p in products" :key="p.id" class="col-md-4 mb-3">
            <div class="card h-100">
              <img :src="p.image_url || 'https://via.placeholder.com/200x140'" class="card-img-top" style="height:140px;object-fit:cover" />
              <div class="card-body p-2">
                <p class="small text-muted mb-0">{{ p.sku }}</p>
                <p class="font-weight-bold mb-1 small">{{ p.title.slice(0, 50) }}</p>
                <p class="text-success">{{ formatCurrency(p.cost_price) }}</p>
              </div>
              <div class="card-footer p-1">
                <button class="btn btn-primary btn-sm btn-block" @click="selectProduct(p)">
                  Comprar Produto
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Order modal -->
    <div v-if="selectedProduct" class="modal d-block" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5>Confirmar Pedido Manual</h5>
            <button type="button" class="close" @click="selectedProduct = null"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p><strong>Produto:</strong> {{ selectedProduct.title }}</p>
            <p><strong>Custo:</strong> {{ formatCurrency(selectedProduct.cost_price) }}</p>
            <div class="form-group">
              <label>Quantidade</label>
              <input v-model.number="orderForm.quantity" type="number" min="1" class="form-control" />
            </div>
            <div class="form-group">
              <label>Nome do Cliente</label>
              <input v-model="orderForm.buyer_name" type="text" class="form-control" />
            </div>
            <div class="form-group">
              <label>Endereço de Entrega</label>
              <textarea v-model="orderForm.shipping_address" class="form-control" rows="3" placeholder="Rua, número, bairro, cidade, estado, CEP"></textarea>
            </div>
            <div v-if="orderError" class="alert alert-danger py-2">{{ orderError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="selectedProduct = null">Cancelar</button>
            <button class="btn btn-success" :disabled="orderLoading" @click="submitOrder">
              {{ orderLoading ? 'Processando...' : 'Confirmar Pedido' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'

const router = useRouter()
const products = ref([])
const search = ref('')
const selectedProduct = ref(null)
const orderLoading = ref(false)
const orderError = ref('')

const orderForm = reactive({ quantity: 1, buyer_name: '', shipping_address: '' })

async function searchProducts() {
  const { data } = await api.get('/catalog', { params: { search: search.value, page_size: 9 } })
  products.value = data.items
}

function selectProduct(p) {
  selectedProduct.value = p
  orderForm.quantity = 1
  orderForm.buyer_name = ''
  orderForm.shipping_address = ''
  orderError.value = ''
}

async function submitOrder() {
  orderError.value = ''
  orderLoading.value = true
  try {
    const { data } = await api.post('/manual-orders', {
      catalog_product_id: selectedProduct.value.id,
      quantity: orderForm.quantity,
      buyer_name: orderForm.buyer_name,
      shipping_address: { raw: orderForm.shipping_address },
    })
    router.push(`/orders/${data.id}`)
  } catch (err) {
    orderError.value = err.response?.data?.detail || 'Erro ao criar pedido'
  } finally {
    orderLoading.value = false
  }
}
</script>
