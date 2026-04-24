<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ isEdit ? 'Editar Produto CMIG' : 'Novo Produto CMIG' }}</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink :to="`/cmig-products?cmig_id=${cmigId}`" class="btn btn-secondary">
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

            <!-- Dados do Produto -->
            <div class="card">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-box mr-2"></i>Dados do Produto</h3>
              </div>
              <form @submit.prevent="submit">
                <div class="card-body">
                  <div v-if="error" class="alert alert-danger">{{ error }}</div>

                  <div class="row">
                    <div class="col-md-3 form-group">
                      <label>SKU CMIG <span class="text-danger">*</span></label>
                      <input v-model="form.sku_cmig" class="form-control" required :disabled="isEdit" />
                    </div>
                    <div class="col-md-6 form-group">
                      <label>Título <span class="text-danger">*</span></label>
                      <input v-model="form.title" class="form-control" required />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>EAN / GTIN</label>
                      <input v-model="form.ean" class="form-control" maxlength="14" placeholder="7891234567890" />
                    </div>
                  </div>

                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>Marca</label>
                      <input v-model="form.brand" class="form-control" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Modelo</label>
                      <input v-model="form.model" class="form-control" placeholder="Ex: Air Max 97" />
                    </div>
                    <div class="col-md-2 form-group">
                      <label>Preço de Custo</label>
                      <div class="input-group">
                        <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                        <input v-model="form.cost_price" type="number" step="0.01" class="form-control" />
                      </div>
                    </div>
                    <div class="col-md-2 form-group">
                      <label>Estoque</label>
                      <input v-model="form.stock_quantity" type="number" class="form-control" min="0" />
                    </div>
                  </div>

                  <div class="form-group">
                    <label>Descrição</label>
                    <textarea v-model="form.description" class="form-control" rows="4"></textarea>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Dimensões e Peso</small></h6>
                  <div class="row">
                    <div class="col-md-3 form-group">
                      <label>Peso (kg)</label>
                      <input v-model="form.weight_kg" type="number" step="0.001" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Altura (cm)</label>
                      <input v-model="form.height_cm" type="number" step="0.01" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Largura (cm)</label>
                      <input v-model="form.width_cm" type="number" step="0.01" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Comprimento (cm)</label>
                      <input v-model="form.length_cm" type="number" step="0.01" class="form-control" />
                    </div>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Informações Fiscais</small></h6>
                  <div class="row">
                    <div class="col-md-3 form-group">
                      <label>NCM</label>
                      <input v-model="form.ncm" class="form-control" maxlength="8" placeholder="00000000" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>CEST</label>
                      <input v-model="form.cest" class="form-control" maxlength="7" placeholder="0000000" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Origem</label>
                      <select v-model="form.origin" class="form-control">
                        <option :value="0">0 - Nacional</option>
                        <option :value="1">1 - Estrangeira (Importação Direta)</option>
                        <option :value="2">2 - Estrangeira (Mercado Interno)</option>
                      </select>
                    </div>
                    <div class="col-md-3 form-group d-flex align-items-end pb-3" v-if="isEdit">
                      <div class="custom-control custom-switch">
                        <input v-model="form.is_active" type="checkbox" class="custom-control-input" id="is_active" />
                        <label class="custom-control-label" for="is_active">Produto Ativo</label>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="card-footer">
                  <button type="submit" class="btn btn-primary" :disabled="saving">
                    <span v-if="saving"><i class="fas fa-spinner fa-spin mr-1"></i>Salvando...</span>
                    <span v-else><i class="fas fa-save mr-1"></i>{{ isEdit ? 'Salvar Alterações' : 'Cadastrar Produto' }}</span>
                  </button>
                </div>
              </form>
            </div>

            <!-- Variações (somente no modo edição) -->
            <div class="card" v-if="isEdit">
              <div class="card-header d-flex align-items-center justify-content-between">
                <h3 class="card-title mb-0"><i class="fas fa-th-large mr-2"></i>Variações</h3>
                <button class="btn btn-sm btn-success" @click="openVariantModal(null)">
                  <i class="fas fa-plus mr-1"></i>Adicionar Variação
                </button>
              </div>
              <div class="card-body p-0">
                <div v-if="loadingVariants" class="text-center py-3">
                  <i class="fas fa-spinner fa-spin"></i> Carregando...
                </div>
                <div v-else-if="variants.length === 0" class="text-center text-muted py-4">
                  Nenhuma variação cadastrada. Clique em "Adicionar Variação" para começar.
                </div>
                <table v-else class="table table-sm table-hover mb-0">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Nome</th>
                      <th>Cor</th>
                      <th>Tamanho</th>
                      <th>Voltagem</th>
                      <th>Estoque</th>
                      <th>Mod. Preço</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="v in variants" :key="v.id">
                      <td><code>{{ v.sku }}</code></td>
                      <td>{{ v.variant_name || '—' }}</td>
                      <td>{{ v.color || '—' }}</td>
                      <td>{{ v.size_label || '—' }}</td>
                      <td>{{ v.voltage || '—' }}</td>
                      <td>{{ v.stock_quantity }}</td>
                      <td>{{ v.price_modifier > 0 ? '+' : '' }}{{ formatCurrency(v.price_modifier) }}</td>
                      <td class="text-right pr-2">
                        <div class="btn-group btn-group-sm">
                          <button class="btn btn-outline-primary" @click="openVariantModal(v)" title="Editar">
                            <i class="fas fa-edit"></i>
                          </button>
                          <button class="btn btn-outline-danger" @click="deleteVariant(v)" title="Excluir">
                            <i class="fas fa-trash"></i>
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        </div>
      </div>
    </section>

    <!-- Modal Variação -->
    <div v-if="variantModal" class="modal fade show d-block" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ variantForm.id ? 'Editar' : 'Nova' }} Variação</h5>
            <button class="close" @click="variantModal=false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="variantError" class="alert alert-danger py-1">{{ variantError }}</div>
            <div class="row">
              <div class="col-md-6 form-group">
                <label>SKU <span class="text-danger">*</span></label>
                <input v-model="variantForm.sku" class="form-control" :disabled="!!variantForm.id" placeholder="SKU-001-AZUL-P" />
              </div>
              <div class="col-md-6 form-group">
                <label>Nome da Variação</label>
                <input v-model="variantForm.variant_name" class="form-control" placeholder="Ex: Azul P" />
              </div>
            </div>
            <div class="row">
              <div class="col-md-4 form-group">
                <label>Cor</label>
                <input v-model="variantForm.color" class="form-control" placeholder="Azul" />
              </div>
              <div class="col-md-4 form-group">
                <label>Tamanho</label>
                <input v-model="variantForm.size_label" class="form-control" placeholder="P / M / G / 42" />
              </div>
              <div class="col-md-4 form-group">
                <label>Voltagem</label>
                <input v-model="variantForm.voltage" class="form-control" placeholder="110V / 220V / Bivolt" />
              </div>
            </div>
            <div class="row">
              <div class="col-md-6 form-group">
                <label>Estoque</label>
                <input v-model.number="variantForm.stock_quantity" type="number" min="0" class="form-control" />
              </div>
              <div class="col-md-6 form-group">
                <label>Modificador de Preço (R$)</label>
                <input v-model.number="variantForm.price_modifier" type="number" step="0.01" class="form-control" placeholder="0.00" />
              </div>
            </div>
            <div class="form-group">
              <label>Atributos Extras <small class="text-muted">(JSON: {"material":"algodão"})</small></label>
              <input v-model="variantForm.attributes_json" class="form-control" placeholder='{"material":"algodão"}' />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="variantModal=false">Cancelar</button>
            <button class="btn btn-primary" @click="saveVariant" :disabled="savingVariant">
              <i v-if="savingVariant" class="fas fa-spinner fa-spin mr-1"></i>Salvar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const isEdit = computed(() => !!route.params.id)
const cmigId = computed(() => route.query.cmig_id)
const saving = ref(false)
const error = ref('')

const form = ref({
  sku_cmig: '',
  title: '',
  brand: '',
  model: '',
  ean: '',
  description: '',
  cost_price: null,
  stock_quantity: 0,
  weight_kg: null,
  height_cm: null,
  width_cm: null,
  length_cm: null,
  ncm: '',
  cest: '',
  origin: 0,
  is_active: true,
})

// Variações
const variants = ref([])
const loadingVariants = ref(false)
const variantModal = ref(false)
const variantError = ref('')
const savingVariant = ref(false)
const variantForm = ref({})

function formatCurrency(v) {
  return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadVariants() {
  if (!isEdit.value) return
  loadingVariants.value = true
  try {
    const { data } = await api.get(`/cmigs/${cmigId.value}/products/${route.params.id}/variants`)
    variants.value = data
  } catch {
    // silencioso — variantes são opcionais
  } finally {
    loadingVariants.value = false
  }
}

function openVariantModal(variant) {
  variantError.value = ''
  variantForm.value = variant
    ? { ...variant }
    : { sku: '', variant_name: '', color: '', size: '', voltage: '', stock_quantity: 0, price_modifier: 0, attributes_json: '' }
  variantModal.value = true
}

async function saveVariant() {
  variantError.value = ''
  if (!variantForm.value.sku?.trim()) { variantError.value = 'SKU é obrigatório'; return }
  savingVariant.value = true
  try {
    const base = `/cmigs/${cmigId.value}/products/${route.params.id}/variants`
    if (variantForm.value.id) {
      await api.put(`${base}/${variantForm.value.id}`, variantForm.value)
      toast.success('Variação atualizada!')
    } else {
      await api.post(base, variantForm.value)
      toast.success('Variação adicionada!')
    }
    variantModal.value = false
    await loadVariants()
  } catch (e) {
    variantError.value = e.response?.data?.detail || 'Erro ao salvar variação.'
  } finally {
    savingVariant.value = false
  }
}

async function deleteVariant(v) {
  if (!confirm(`Excluir variação ${v.sku}?`)) return
  try {
    await api.delete(`/cmigs/${cmigId.value}/products/${route.params.id}/variants/${v.id}`)
    toast.success('Variação excluída!')
    await loadVariants()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir variação.')
  }
}

onMounted(async () => {
  if (isEdit.value) {
    const { data } = await api.get(`/cmigs/${cmigId.value}/products/${route.params.id}`)
    Object.assign(form.value, data)
    await loadVariants()
  }
})

async function submit() {
  error.value = ''
  saving.value = true
  try {
    if (isEdit.value) {
      await api.put(`/cmigs/${cmigId.value}/products/${route.params.id}`, form.value)
      toast.success('Produto atualizado com sucesso!')
    } else {
      await api.post(`/cmigs/${cmigId.value}/products`, form.value)
      toast.success('Produto cadastrado com sucesso!')
    }
    router.push(`/cmig-products?cmig_id=${cmigId.value}`)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar produto.'
  } finally {
    saving.value = false
  }
}
</script>
