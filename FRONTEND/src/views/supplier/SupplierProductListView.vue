<template>
  <div>
    <div class="card">
      <div class="card-header d-flex justify-content-between align-items-center">
        <h3 class="card-title">Produto Geral (PG)</h3>
        <button class="btn btn-sm btn-primary" @click="openModal()">
          <i class="fas fa-plus mr-1"></i> Novo Produto
        </button>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm table-hover">
          <thead>
            <tr><th>#</th><th>SKU</th><th>Título</th><th>Custo</th><th>Estoque</th><th>Ativo</th><th class="text-center">Ações</th></tr>
          </thead>
          <tbody>
            <tr v-if="loading"><td colspan="7" class="text-center py-4"><i class="fas fa-spinner fa-spin"></i></td></tr>
            <tr v-else-if="!products.length"><td colspan="7" class="text-center py-4 text-muted">Nenhum produto cadastrado.</td></tr>
            <tr v-for="p in products" :key="p.id">
              <td class="text-muted">{{ p.id }}</td>
              <td><code>{{ p.sku }}</code></td>
              <td>{{ p.title }}</td>
              <td>{{ formatCurrency(p.cost_price) }}</td>
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
              <td class="text-center text-nowrap">
                <button class="btn btn-xs btn-outline-secondary mr-1" title="Editar" @click="openModal(p)">
                  <i class="fas fa-edit"></i>
                </button>
                <button class="btn btn-xs btn-outline-danger" title="Desativar" @click="deactivate(p)">
                  <i class="fas fa-trash"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal Criar / Editar -->
    <div v-if="showModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ editing ? 'Editar Produto' : 'Novo Produto' }}</h5>
            <button class="close" @click="closeModal"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="formError" class="alert alert-danger">{{ formError }}</div>

            <div class="row">
              <div class="col-md-4 form-group">
                <label>SKU <span class="text-danger">*</span></label>
                <input v-model="form.sku" class="form-control" :disabled="!!editing" required />
              </div>
              <div class="col-md-8 form-group">
                <label>Título <span class="text-danger">*</span></label>
                <input v-model="form.title" class="form-control" required />
              </div>
            </div>

            <div class="form-group">
              <label>Descrição</label>
              <textarea v-model="form.description" class="form-control" rows="2"></textarea>
            </div>

            <div class="row">
              <div class="col-md-4 form-group">
                <label>Preço de custo (R$) <span class="text-danger">*</span></label>
                <input v-model.number="form.cost_price" type="number" step="0.01" min="0" class="form-control" required />
              </div>
              <div class="col-md-4 form-group">
                <label>Preço sugerido (R$)</label>
                <input v-model.number="form.suggested_price" type="number" step="0.01" min="0" class="form-control" />
              </div>
              <div class="col-md-4 form-group">
                <label>Estoque inicial</label>
                <input v-model.number="form.stock_quantity" type="number" min="0" class="form-control" />
              </div>
            </div>

            <div class="row">
              <div class="col-md-3 form-group">
                <label>Peso (kg)</label>
                <input v-model.number="form.weight_kg" type="number" step="0.01" min="0" class="form-control" />
              </div>
              <div class="col-md-3 form-group">
                <label>Altura (cm)</label>
                <input v-model.number="form.height_cm" type="number" step="0.1" min="0" class="form-control" />
              </div>
              <div class="col-md-3 form-group">
                <label>Largura (cm)</label>
                <input v-model.number="form.width_cm" type="number" step="0.1" min="0" class="form-control" />
              </div>
              <div class="col-md-3 form-group">
                <label>Comprimento (cm)</label>
                <input v-model.number="form.length_cm" type="number" step="0.1" min="0" class="form-control" />
              </div>
            </div>

            <div class="row">
              <div class="col-md-4 form-group">
                <label>Marca</label>
                <input v-model="form.brand" class="form-control" />
              </div>
              <div class="col-md-4 form-group">
                <label>NCM</label>
                <input v-model="form.ncm" class="form-control" placeholder="0000.00.00" />
              </div>
              <div class="col-md-4 form-group">
                <label>CEST</label>
                <input v-model="form.cest" class="form-control" />
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeModal">Cancelar</button>
            <button class="btn btn-primary" :disabled="saving" @click="save">
              <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
              {{ saving ? 'Salvando...' : (editing ? 'Salvar alterações' : 'Cadastrar produto') }}
            </button>
          </div>
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
const loading  = ref(true)
const showModal = ref(false)
const saving    = ref(false)
const editing   = ref(null)
const formError = ref('')

const defaultForm = () => ({
  sku: '', title: '', description: '',
  cost_price: '', suggested_price: '', stock_quantity: 0,
  weight_kg: '', height_cm: '', width_cm: '', length_cm: '',
  brand: '', ncm: '', cest: '',
})
const form = ref(defaultForm())

async function load() {
  loading.value = true
  const { data } = await api.get('/pg')
  products.value = data
  loading.value = false
}

function openModal(product = null) {
  editing.value = product
  formError.value = ''
  if (product) {
    form.value = {
      sku: product.sku,
      title: product.title,
      description: product.description || '',
      cost_price: product.cost_price,
      suggested_price: product.suggested_price || '',
      stock_quantity: product.stock_quantity,
      weight_kg: product.weight_kg || '',
      height_cm: product.height_cm || '',
      width_cm: product.width_cm || '',
      length_cm: product.length_cm || '',
      brand: product.brand || '',
      ncm: product.ncm || '',
      cest: product.cest || '',
    }
  } else {
    form.value = defaultForm()
  }
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editing.value = null
}

async function save() {
  if (!form.value.sku || !form.value.title || !form.value.cost_price) {
    formError.value = 'SKU, título e preço de custo são obrigatórios.'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (editing.value) {
      await api.put(`/pg/${editing.value.id}`, form.value)
    } else {
      await api.post('/pg', form.value)
    }
    closeModal()
    await load()
  } catch (err) {
    formError.value = err.response?.data?.detail || 'Erro ao salvar produto.'
  } finally {
    saving.value = false
  }
}

async function updateStock(id, qty) {
  await api.put(`/pg/${id}/stock`, { stock_quantity: parseInt(qty) })
}

async function deactivate(p) {
  if (!confirm(`Desativar "${p.title}"?`)) return
  await api.delete(`/pg/${p.id}`)
  await load()
}

onMounted(load)
</script>
