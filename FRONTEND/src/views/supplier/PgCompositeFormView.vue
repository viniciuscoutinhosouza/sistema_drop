<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ isEdit ? 'Editar KIT PG' : 'Novo KIT PG' }}</h1>
            <small class="text-muted">Produto Geral — KIT (apenas Catálogo PG)</small>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/pg" class="btn btn-secondary">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="row">
          <div class="col-lg-10">

            <!-- Dados Básicos -->
            <div class="card">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-layer-group mr-2"></i>Dados do KIT PG</h3>
              </div>
              <div class="card-body">
                <div v-if="error" class="alert alert-danger">{{ error }}</div>

                <ProductPhotosCard
                  v-model="pictures"
                  :upload-url="isEdit ? `/pg/${route.params.id}/photos` : ''"
                />

                <div class="row">
                  <div class="col-md-3 form-group">
                    <label>SKU <span class="text-danger">*</span></label>
                    <input v-model="form.sku" class="form-control" required />
                  </div>
                  <div class="col-md-6 form-group">
                    <label>Título <span class="text-danger">*</span></label>
                    <input v-model="form.title" class="form-control" required />
                  </div>
                  <div class="col-md-3 form-group">
                    <label>EAN / GTIN</label>
                    <input v-model="form.ean" class="form-control" maxlength="14" />
                  </div>
                </div>

                <div class="row">
                  <div class="col-md-4 form-group">
                    <label>Marca</label>
                    <input v-model="form.brand" class="form-control" />
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Modelo</label>
                    <input v-model="form.model" class="form-control" />
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Categoria</label>
                    <CategoryPickerWithModal v-model="form.category_id" />
                  </div>
                </div>

                <div class="row">
                  <div class="col-md-4 form-group">
                    <label>Preço de Custo <span class="text-danger">*</span></label>
                    <div class="input-group">
                      <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                      <input v-model="form.cost_price" type="number" step="0.01" class="form-control" required />
                    </div>
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Preço Sugerido</label>
                    <div class="input-group">
                      <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                      <input v-model="form.suggested_price" type="number" step="0.01" class="form-control" />
                    </div>
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Video ID</label>
                    <input v-model="form.video_id" class="form-control" />
                  </div>
                </div>

                <div class="form-group">
                  <label>Descrição</label>
                  <textarea v-model="form.description" class="form-control" rows="3"></textarea>
                </div>

                <ProductDimensionsFields :form="form" />
                <ProductFiscalFields :form="form" />
              </div>
            </div>

            <!-- Componentes do KIT PG -->
            <div class="card">
              <div class="card-header d-flex align-items-center">
                <h3 class="card-title flex-grow-1"><i class="fas fa-cubes mr-2"></i>Componentes (Catálogo PG)</h3>
                <span class="badge badge-lg mr-2" :class="compositeStock > 0 ? 'badge-success' : 'badge-danger'" style="font-size:1rem;padding:.4em .7em">
                  Estoque: {{ compositeStock }}
                </span>
              </div>
              <div class="card-body">

                <!-- Busca PG -->
                <div class="row mb-3">
                  <div class="col-md-6">
                    <label class="small">Buscar produto PG para adicionar:</label>
                    <div class="input-group">
                      <input
                        v-model="searchQuery"
                        type="text"
                        class="form-control form-control-sm"
                        placeholder="Título ou SKU..."
                        @input="debouncedSearch"
                      />
                      <div class="input-group-append">
                        <span class="input-group-text">
                          <i :class="searchLoading ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Resultados -->
                <div v-if="searchResults.length" class="mb-3">
                  <table class="table table-sm table-bordered mb-0">
                    <thead class="thead-light">
                      <tr>
                        <th>SKU</th>
                        <th>Título</th>
                        <th class="text-center">Estoque</th>
                        <th class="text-center" style="width:80px">Adicionar</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="r in searchResults" :key="r.id" :class="{ 'table-secondary': isAlreadyAdded(r.id) }">
                        <td><code>{{ r.sku }}</code></td>
                        <td>{{ r.title }}</td>
                        <td class="text-center">
                          <span :class="r.stock_quantity === 0 ? 'text-danger' : ''">{{ r.stock_quantity }}</span>
                        </td>
                        <td class="text-center">
                          <button v-if="!isAlreadyAdded(r.id)" class="btn btn-sm btn-outline-primary" @click="addComponent(r)">
                            <i class="fas fa-plus"></i>
                          </button>
                          <span v-else class="text-muted small">Adicionado</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- Componentes selecionados -->
                <div v-if="components.length">
                  <h6>Componentes selecionados</h6>
                  <table class="table table-sm table-bordered mb-0">
                    <thead class="thead-light">
                      <tr>
                        <th>SKU</th>
                        <th>Título</th>
                        <th class="text-center">Estoque</th>
                        <th class="text-center" style="width:100px">Qtd no Kit</th>
                        <th class="text-center">Contribuição</th>
                        <th style="width:50px"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(comp, idx) in components" :key="idx">
                        <td><code>{{ comp.sku }}</code></td>
                        <td>{{ comp.title }}</td>
                        <td class="text-center">{{ comp.stock_quantity }}</td>
                        <td class="text-center">
                          <input
                            type="number" min="1"
                            v-model.number="comp.quantity"
                            class="form-control form-control-sm text-center"
                            style="width:70px"
                            @input="updateContribution(comp)"
                          />
                        </td>
                        <td class="text-center">
                          <span :class="comp.contribution === 0 ? 'text-danger' : 'text-success'">{{ comp.contribution }}</span>
                        </td>
                        <td class="text-center">
                          <button class="btn btn-sm btn-outline-danger" @click="removeComponent(idx)">
                            <i class="fas fa-times"></i>
                          </button>
                        </td>
                      </tr>
                    </tbody>
                    <tfoot>
                      <tr>
                        <td colspan="4" class="text-right font-weight-bold">Estoque do KIT:</td>
                        <td class="text-center font-weight-bold">
                          <span :class="compositeStock === 0 ? 'text-danger' : 'text-success'">{{ compositeStock }}</span>
                        </td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
                <div v-else class="alert alert-warning mb-0">
                  <i class="fas fa-exclamation-triangle mr-1"></i>
                  Adicione ao menos um produto PG para compor o kit.
                </div>
              </div>
            </div>

            <!-- Botão Salvar -->
            <div class="card">
              <div class="card-body">
                <button
                  type="button" class="btn btn-primary"
                  :disabled="saving || !form.title || !form.sku || components.length === 0"
                  @click="submit"
                >
                  <span v-if="saving"><i class="fas fa-spinner fa-spin mr-1"></i>Salvando...</span>
                  <span v-else><i class="fas fa-save mr-1"></i>{{ isEdit ? 'Salvar Alterações' : 'Cadastrar KIT' }}</span>
                </button>
                <RouterLink to="/pg" class="btn btn-secondary ml-2">Cancelar</RouterLink>
              </div>
            </div>

          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import ProductPhotosCard from '@/components/products/ProductPhotosCard.vue'
import ProductDimensionsFields from '@/components/products/ProductDimensionsFields.vue'
import ProductFiscalFields from '@/components/products/ProductFiscalFields.vue'
import CategoryPickerWithModal from '@/components/products/CategoryPickerWithModal.vue'

const route  = useRoute()
const router = useRouter()
const toast  = useToast()

const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const error  = ref('')

const form = ref({
  sku: '', title: '', brand: '', model: '', ean: '',
  description: '', cost_price: null, suggested_price: null,
  weight_kg: null, height_cm: null, width_cm: null, length_cm: null,
  ncm: '', cest: '', origin: 0, category_id: null, video_id: '',
  attributes_json: null,
})

const pictures   = ref([])
const components = ref([])  // { component_id, sku, title, stock_quantity, quantity, contribution }

const searchQuery   = ref('')
const searchResults = ref([])
const searchLoading = ref(false)

let searchTimer = null
function debouncedSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(doSearch, 300)
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) { searchResults.value = []; return }
  searchLoading.value = true
  try {
    const { data } = await api.get('/pg', { params: { search: q } })
    const selfId = isEdit.value ? Number(route.params.id) : null
    searchResults.value = (Array.isArray(data) ? data : []).filter(p => !p.is_composite && p.id !== selfId)
  } finally {
    searchLoading.value = false
  }
}

function isAlreadyAdded(id) {
  return components.value.some(c => c.component_id === id)
}

function addComponent(r) {
  const qty = 1
  components.value.push({
    component_id: r.id,
    sku: r.sku,
    title: r.title,
    stock_quantity: r.stock_quantity,
    quantity: qty,
    contribution: Math.floor(r.stock_quantity / qty),
  })
}

function removeComponent(idx) {
  components.value.splice(idx, 1)
}

function updateContribution(comp) {
  const qty = Math.max(comp.quantity || 1, 1)
  comp.contribution = Math.floor(comp.stock_quantity / qty)
}

const compositeStock = computed(() => {
  if (!components.value.length) return 0
  return Math.min(...components.value.map(c => Math.floor(c.stock_quantity / Math.max(c.quantity, 1))))
})

onMounted(async () => {
  if (isEdit.value) {
    const { data } = await api.get(`/pg/${route.params.id}`)
    Object.assign(form.value, data)

    if (data.images?.length) {
      pictures.value = data.images.map(img => ({ url: img.url }))
    }

    if (data.components?.length) {
      components.value = data.components.map(c => ({
        component_id: c.product_id,
        sku: c.sku,
        title: c.title,
        stock_quantity: c.stock_quantity,
        quantity: c.quantity,
        contribution: c.contribution,
      }))
    }
  }
})

async function submit() {
  if (!components.value.length) {
    toast.error('Adicione ao menos um componente PG ao KIT.')
    return
  }
  error.value = ''
  saving.value = true
  try {
    const payload = {
      ...form.value,
      is_composite: true,
      images: pictures.value.map(p => ({ url: p.url })),
      components: components.value.map(c => ({
        component_id: c.component_id,
        quantity: Math.max(c.quantity, 1),
      })),
    }
    if (isEdit.value) {
      await api.put(`/pg/${route.params.id}`, payload)
      toast.success('KIT PG atualizado!')
    } else {
      await api.post('/pg', payload)
      toast.success('KIT PG cadastrado!')
    }
    router.push('/pg')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar KIT PG.'
  } finally {
    saving.value = false
  }
}
</script>
