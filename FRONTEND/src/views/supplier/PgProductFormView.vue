<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ isEdit ? 'Editar Produto PG' : 'Novo Produto PG' }}</h1>
          </div>
          <div class="col-sm-6 text-right">
            <button v-if="isEdit" class="btn btn-outline-info mr-2"
                    :disabled="recalculating"
                    title="Recalcula estoque a partir dos eventos (NFes + Pedidos)."
                    @click="recalculateStock">
              <i :class="['fas', recalculating ? 'fa-spinner fa-spin' : 'fa-calculator']"></i>
              Recalcular estoque
            </button>
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

            <!-- Dados do Produto -->
            <div class="card">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-box mr-2"></i>Dados do Produto</h3>
              </div>
              <form @submit.prevent="submit">
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
                      <small v-if="isEdit && form.sku !== originalSku" class="text-warning">
                        <i class="fas fa-exclamation-triangle mr-1"></i>SKU alterado — será perguntado sobre propagação aos itens vinculados ao salvar.
                      </small>
                    </div>
                    <div class="col-md-6 form-group">
                      <label>Título <span class="text-danger">*</span></label>
                      <input v-model="form.title" class="form-control" required />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>EAN / GTIN</label>
                      <div class="input-group">
                        <input v-model="form.ean" class="form-control" maxlength="14" placeholder="7891234567890" />
                        <div class="input-group-append">
                          <button type="button" class="btn btn-outline-secondary"
                                  title="Gerar código EAN-13 interno (prefixo 200)"
                                  @click="generateEan">
                            <i class="fas fa-magic"></i>
                          </button>
                        </div>
                      </div>
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
                        <input v-model="form.cost_price" type="number" step="0.01" min="0" class="form-control" required />
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Preço de Venda</label>
                      <div class="input-group">
                        <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                        <input v-model="form.suggested_price" type="number" step="0.01" min="0" class="form-control" />
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Video ID</label>
                      <input v-model="form.video_id" class="form-control" placeholder="ID do vídeo" />
                    </div>
                  </div>

                  <div class="form-group">
                    <label>Descrição</label>
                    <textarea v-model="form.description" class="form-control" rows="4"></textarea>
                  </div>

                  <ProductDimensionsFields :form="form" />

                  <ProductFiscalFields :form="form" />

                  <div class="row" v-if="isEdit">
                    <div class="col-md-12 form-group pt-2">
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
import { generateEan13 } from '@/utils/ean'

const route  = useRoute()
const router = useRouter()
const toast  = useToast()

const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const error  = ref('')

const form = ref({
  sku: '', title: '', brand: '', model: '', ean: '',
  description: '', cost_price: null, suggested_price: null,
  weight_kg: null, height_cm: null,
  width_cm: null, length_cm: null, ncm: '', cest: '',
  origin: 0, category_id: null, video_id: '', attributes_json: null,
  is_active: true,
})

const pictures = ref([])
const originalSku = ref('')
const recalculating = ref(false)

onMounted(async () => {
  if (isEdit.value) {
    const { data } = await api.get(`/pg/${route.params.id}`)
    Object.assign(form.value, data)
    pictures.value = data.images || []
    originalSku.value = data.sku || ''
  }
})

function generateEan() {
  form.value.ean = generateEan13()
  toast.success('EAN gerado (prefixo 200 — uso interno).')
}

async function recalculateStock() {
  recalculating.value = true
  try {
    const { data } = await api.post(`/pg/${route.params.id}/recalculate-stock`)
    const delta = data.delta
    const sign = delta > 0 ? '+' : ''
    toast.success(
      `Estoque recalculado: ${data.old_stock} → ${data.new_stock} (${sign}${delta}).`
    )
    form.value.stock_quantity = data.new_stock
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao recalcular estoque.')
  } finally {
    recalculating.value = false
  }
}

async function submit() {
  error.value = ''
  let cascade = false
  const skuChanged = isEdit.value && form.value.sku !== originalSku.value && originalSku.value
  if (skuChanged) {
    cascade = confirm(
      `Você alterou o SKU de "${originalSku.value}" para "${form.value.sku}".\n\n` +
      `Deseja propagar o novo SKU para todos os CMIGProducts vinculados e anúncios?`
    )
  }
  saving.value = true
  try {
    const payload = {
      ...form.value,
      product_type: 'simple',
      images: pictures.value.map(p => ({ url: p.url })),
      cascade_sku_to_linked: cascade,
    }
    if (isEdit.value) {
      const { data } = await api.put(`/pg/${route.params.id}`, payload)
      const c = data?._cascade
      if (c && (c.cmigs_updated || c.listings_updated)) {
        const parts = []
        if (c.cmigs_updated) parts.push(`${c.cmigs_updated} CMIG(s)`)
        if (c.listings_updated) parts.push(`${c.listings_updated} anúncio(s)`)
        toast.success(`Produto atualizado. SKU propagado para: ${parts.join(', ')}.`)
      } else {
        toast.success('Produto atualizado com sucesso!')
      }
    } else {
      await api.post('/pg', payload)
      toast.success('Produto cadastrado com sucesso!')
    }
    router.push('/pg')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar produto.'
  } finally {
    saving.value = false
  }
}
</script>
