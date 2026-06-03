<template>
  <div class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1055">
    <div class="modal-dialog modal-xl modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-object-group mr-2 text-success"></i>
            Agrupar Anúncios — {{ products.length }} produto(s) como família
          </h5>
          <button type="button" class="close" @click="closeWithoutSave" :disabled="saving"><span>&times;</span></button>
        </div>

        <div class="modal-body">

          <!-- Conta -->
          <div class="form-group">
            <label class="font-weight-bold">Marketplace</label>
            <input class="form-control form-control-sm" :value="accountLabel" disabled />
          </div>

          <!-- Bloco compartilhado -->
          <div class="card card-outline card-primary mb-3">
            <div class="card-header py-2"><strong>1. Campos compartilhados (iguais em todos os anúncios)</strong></div>
            <div class="card-body">

              <div class="form-group">
                <label class="font-weight-bold">Categoria <span class="text-danger">*</span></label>
                <div class="input-group input-group-sm">
                  <input v-model="catSearch" type="text" class="form-control"
                         placeholder="Buscar categoria ML..." @input="onCatSearch" />
                  <div class="input-group-append">
                    <span class="input-group-text"><i class="fas fa-search"></i></span>
                  </div>
                </div>
                <div v-if="catSearching" class="text-muted small mt-1">
                  <i class="fas fa-spinner fa-spin mr-1"></i>Buscando...
                </div>
                <div v-if="catResults.length" class="list-group mt-1" style="max-height:240px;overflow-y:auto">
                  <button v-for="cat in catResults" :key="cat.id" type="button"
                          class="list-group-item list-group-item-action py-2"
                          @click="selectCategory(cat)">
                    <div v-if="cat.path_from_root && cat.path_from_root.length"
                         class="d-flex flex-wrap" style="gap:3px;font-size:12px">
                      <template v-for="(p,i) in cat.path_from_root" :key="p.id || i">
                        <span :class="i === cat.path_from_root.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">{{ p.name }}</span>
                        <i v-if="i < cat.path_from_root.length - 1" class="fas fa-angle-right text-muted" style="font-size:10px"></i>
                      </template>
                    </div>
                    <code class="text-muted d-block" style="font-size:10px">{{ cat.id }}</code>
                  </button>
                </div>

                <div v-if="form.category_id" class="p-2 rounded border bg-light mt-2">
                  <div class="font-weight-bold" style="font-size:13px">{{ form.category_name }}</div>
                  <code class="text-muted d-block" style="font-size:11px">ID: {{ form.category_id }}</code>
                </div>

                <div v-if="supportLoading" class="text-muted small mt-1">
                  <i class="fas fa-spinner fa-spin mr-1"></i>Verificando suporte da categoria...
                </div>
                <div v-else-if="form.category_id && support" class="mt-2">
                  <div v-if="support.requires_family_name" class="alert alert-success py-2 small mb-0">
                    <i class="fas fa-check-circle mr-1"></i>
                    Categoria <strong>User Products</strong> — perfeito para agrupar via <code>family_name</code>.
                  </div>
                  <div v-else class="alert alert-warning py-2 small mb-0">
                    <i class="fas fa-exclamation-triangle mr-1"></i>
                    Esta categoria <strong>não é User Products</strong>. Para variações tradicionais
                    use o botão <strong>"Anúncio com Variações"</strong>. Você ainda pode tentar
                    publicar como família — o ML pode aceitar ou rejeitar dependendo da categoria.
                  </div>
                </div>
              </div>

              <div class="form-group">
                <label class="font-weight-bold">Nome da Família (family_name) <span class="text-danger">*</span></label>
                <input v-model="form.family_name" type="text" class="form-control" maxlength="60"
                       placeholder="Ex: Rolo Massagem Foam Roller 30cm" />
                <small class="text-muted">
                  Será usado IGUAL em todos os {{ products.length }} anúncios — o ML agrupa os itens que
                  compartilham o mesmo <code>family_name</code> e exibe como seletor de variação (cor/tamanho) na VIP.
                </small>
              </div>

              <div class="form-group">
                <label class="font-weight-bold">Modelo</label>
                <input v-model="form.model" type="text" class="form-control"
                       placeholder="Ex: Rolo de Pilates" />
                <small class="text-muted">Vai como atributo MODEL em todos os anúncios.</small>
              </div>

              <div class="form-row">
                <div class="form-group col-md-6">
                  <label class="font-weight-bold">Tipo do Anúncio</label>
                  <select v-model="form.listing_type" class="form-control form-control-sm">
                    <option value="gold_special">Clássico</option>
                    <option value="gold_pro">Premium</option>
                  </select>
                </div>
                <div class="form-group col-md-6">
                  <label class="font-weight-bold">Pagamento do Frete</label>
                  <select v-model="form.free_shipping" class="form-control form-control-sm">
                    <option :value="false">Comprador paga</option>
                    <option :value="true">Vendedor paga (Frete Grátis)</option>
                  </select>
                </div>
              </div>

              <div class="form-row">
                <div class="form-group col-md-6">
                  <label class="font-weight-bold">Estoque</label>
                  <select v-model="form.stock_mode" class="form-control form-control-sm">
                    <option value="product">Estoque do Produto</option>
                    <option value="fixed">Valor Fixo</option>
                  </select>
                </div>
                <div v-if="form.stock_mode === 'fixed'" class="form-group col-md-6">
                  <label class="font-weight-bold">Quantidade fixa</label>
                  <input v-model.number="form.fixed_quantity" type="number" min="0" step="1"
                         class="form-control form-control-sm" />
                </div>
              </div>

            </div>
          </div>

          <!-- Bloco per-produto -->
          <div class="card card-outline card-success">
            <div class="card-header py-2"><strong>2. Preço e fotos (configurável por produto)</strong></div>
            <div class="card-body p-2">
              <table class="table table-sm table-bordered mb-0" style="font-size:12px">
                <thead class="thead-light">
                  <tr>
                    <th style="width:60px">Foto</th>
                    <th>Produto</th>
                    <th style="width:120px">SKU</th>
                    <th style="width:130px">Diferenciador</th>
                    <th style="width:120px">Preço (R$)</th>
                    <th style="width:90px">Fotos</th>
                    <th style="width:90px">Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, i) in form.products" :key="p.product_id"
                      :class="{
                        'table-success': resultByProductId[p.product_id]?.ok,
                        'table-danger': resultByProductId[p.product_id] && !resultByProductId[p.product_id].ok,
                      }">
                    <td>
                      <img v-if="p._thumb" :src="p._thumb"
                           style="width:40px;height:40px;object-fit:cover;border-radius:3px" />
                    </td>
                    <td>
                      <div class="text-truncate" style="max-width:240px" :title="p._title">{{ p._title }}</div>
                    </td>
                    <td><code class="small">{{ p._sku }}</code></td>
                    <td>
                      <input v-model="p.differentiator" type="text" class="form-control form-control-sm"
                             placeholder="Cor, tamanho..." />
                    </td>
                    <td>
                      <input v-model.number="p.sale_price" type="number" min="0" step="0.01"
                             class="form-control form-control-sm text-right" />
                    </td>
                    <td>
                      <VariationPicturesEditor
                        v-model="p.pictures"
                        :product-images="p._product_images || []"
                        :max-pictures="10"
                        :title="`Fotos #${i+1}`"
                      />
                    </td>
                    <td class="small">
                      <span v-if="resultByProductId[p.product_id]?.ok" class="text-success">
                        <i class="fas fa-check"></i> {{ resultByProductId[p.product_id].platform_item_id }}
                      </span>
                      <span v-else-if="resultByProductId[p.product_id]" class="text-danger"
                            :title="resultByProductId[p.product_id].error">
                        <i class="fas fa-times"></i> falhou
                      </span>
                      <span v-else class="text-muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="error" class="alert alert-danger py-2 mt-3">{{ error }}</div>
          <div v-if="summary" class="alert mt-3 py-2"
               :class="summary.failure_count ? 'alert-warning' : 'alert-success'">
            <i :class="['fas', summary.failure_count ? 'fa-exclamation-triangle' : 'fa-check-circle', 'mr-1']"></i>
            {{ summary.success_count }} publicado(s) / {{ summary.failure_count }} falha(s) de {{ summary.total }} total.
          </div>

          <!-- Detalhes das falhas — não esconde no tooltip -->
          <div v-if="failedDetails.length" class="card border-danger mt-3">
            <div class="card-header py-2 bg-danger text-white">
              <i class="fas fa-bug mr-1"></i>
              <strong>Mensagens de erro do Mercado Livre</strong>
            </div>
            <div class="card-body p-2">
              <div v-for="f in failedDetails" :key="f.product_id" class="mb-2 pb-2 border-bottom" style="font-size:12px">
                <div class="font-weight-bold mb-1">
                  <i class="fas fa-times-circle text-danger mr-1"></i>
                  {{ f.title }} <span class="text-muted">(produto #{{ f.product_id }})</span>
                </div>
                <pre class="bg-light p-2 mb-0" style="white-space:pre-wrap;word-break:break-all;font-size:11px;max-height:200px;overflow:auto">{{ f.error }}</pre>
              </div>
            </div>
          </div>

        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeWithoutSave" :disabled="saving">
            {{ summary ? 'Fechar' : 'Cancelar' }}
          </button>
          <button v-if="!summary || summary.failure_count" class="btn btn-success"
                  :disabled="saving || !canSubmit" @click="submit">
            <i :class="['fas', saving ? 'fa-spinner fa-spin' : 'fa-bullhorn', 'mr-1']"></i>
            {{ saving ? 'Publicando...' : (summary ? 'Tentar novamente os que falharam' : `Publicar ${products.length} anúncios`) }}
          </button>
          <button v-else class="btn btn-success" @click="closeWithSuccess">
            <i class="fas fa-check mr-1"></i>Concluir
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import VariationPicturesEditor from '@/components/catalog/VariationPicturesEditor.vue'

const props = defineProps({
  accountId:    { type: [Number, String], required: true },
  accountLabel: { type: String, default: '' },
  source:       { type: String, required: true },   // 'pg' | 'cmig'
  products:     { type: Array, required: true },
})
const emit = defineEmits(['close'])

const form = reactive({
  category_id: '',
  category_name: '',
  family_name: '',
  model: '',
  listing_type: 'gold_special',
  free_shipping: false,
  stock_mode: 'product',
  fixed_quantity: 1,
  products: [],   // [{ product_id, sale_price, pictures, differentiator, _title, _sku, _thumb, _product_images }]
})

const saving = ref(false)
const error = ref('')
const summary = ref(null)        // { total, success_count, failure_count }
const resultByProductId = ref({})

// Categoria search + suporte
const catSearch = ref('')
const catSearching = ref(false)
const catResults = ref([])
let catTimer = null
const support = ref(null)
const supportLoading = ref(false)

const canSubmit = computed(() =>
  !!form.category_id
  && form.family_name.trim().length > 0
  && form.products.every(p => Number(p.sale_price) > 0 && p.pictures.length > 0)
)

const failedDetails = computed(() =>
  form.products
    .map(p => {
      const r = resultByProductId.value[p.product_id]
      return r && !r.ok
        ? { product_id: p.product_id, title: p._title, error: r.error || 'Erro sem mensagem do backend' }
        : null
    })
    .filter(Boolean)
)

function onCatSearch() {
  clearTimeout(catTimer)
  catTimer = setTimeout(doCatSearch, 300)
}
async function doCatSearch() {
  const q = catSearch.value.trim()
  if (q.length < 2) { catResults.value = []; return }
  catSearching.value = true
  try {
    const { data } = await api.get('/anuncios/categories/search', { params: { q } })
    catResults.value = (data || []).slice(0, 12)
  } catch { catResults.value = [] }
  finally { catSearching.value = false }
}
async function selectCategory(cat) {
  form.category_id = cat.id
  form.category_name = cat.name
  catSearch.value = ''
  catResults.value = []
  support.value = null
  supportLoading.value = true
  try {
    const { data } = await api.get(`/anuncios/categories/${cat.id}/variation-support`)
    support.value = data
  } catch { support.value = null }
  finally { supportLoading.value = false }
}

// Pré-carrega cada produto com imagens (e diferenciador inferido)
async function hydrateProducts() {
  const hydrated = []
  for (const p of props.products) {
    const isPg = props.source === 'pg'
    const productId = p.id
    const baseFields = {
      product_id: productId,
      sale_price: '',
      pictures: [],
      differentiator: '',
      _title: p.title,
      _sku: isPg ? p.sku : p.sku_cmig,
      _thumb: isPg ? p.image_url : (p.images?.[0]?.url || p.thumbnail || null),
      _product_images: [],
    }

    // Busca detalhes completos (imagens, atributos)
    try {
      const url = isPg ? `/catalog/${productId}` : `/cmigs/${p.cmig_id}/products/${productId}`
      const { data } = await api.get(url)
      const imgs = (data.images || []).map(i => ({ url: i.url || i }))
      baseFields._product_images = imgs
      if (imgs.length && !baseFields.pictures.length) baseFields.pictures = [imgs[0].url]
      // Pré-preenche o diferenciador se houver hint nos atributos do produto
      const hint = (data.color || data.size || '')
      if (hint) baseFields.differentiator = hint
      // Sugestão de preço inicial
      if (data.suggested_price) baseFields.sale_price = Number(data.suggested_price)
      else if (data.cost_price) baseFields.sale_price = Number(data.cost_price)
    } catch { /* segue com o que tinha */ }

    hydrated.push(baseFields)
  }
  form.products = hydrated
}

async function submit() {
  error.value = ''
  saving.value = true
  // Se for "tentar novamente os que falharam", manda só os que falharam
  const productsToSend = summary.value
    ? form.products.filter(p => !resultByProductId.value[p.product_id]?.ok)
    : form.products

  try {
    const payload = {
      account_id: props.accountId,
      source: props.source,
      category_id: form.category_id,
      family_name: form.family_name.trim(),
      model: form.model.trim() || null,
      listing_type: form.listing_type,
      free_shipping: form.free_shipping,
      stock_mode: form.stock_mode,
      fixed_quantity: form.stock_mode === 'fixed' ? Number(form.fixed_quantity) : undefined,
      products: productsToSend.map(p => ({
        product_id: p.product_id,
        sale_price: Number(p.sale_price),
        pictures: p.pictures,
        attributes: p.differentiator
          ? [{ id: 'COLOR', value_name: p.differentiator }]  // fallback genérico — backend tenta inferir o id real
          : [],
      })),
    }
    const { data } = await api.post('/anuncios/publish-as-family', payload)
    // Mescla resultados por produto
    const merged = { ...resultByProductId.value }
    for (const r of (data.results || [])) merged[r.product_id] = r
    resultByProductId.value = merged
    summary.value = {
      total: form.products.length,
      success_count: form.products.filter(p => merged[p.product_id]?.ok).length,
      failure_count: form.products.filter(p => merged[p.product_id] && !merged[p.product_id].ok).length,
    }
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao publicar anúncios.'
  } finally {
    saving.value = false
  }
}

function closeWithoutSave() {
  if (saving.value) return
  emit('close', { success: !!summary.value && summary.value.success_count > 0 })
}
function closeWithSuccess() {
  emit('close', { success: true })
}

onMounted(() => {
  hydrateProducts()
})
</script>
