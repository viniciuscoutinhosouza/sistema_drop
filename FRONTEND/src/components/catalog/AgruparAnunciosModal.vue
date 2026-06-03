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
                    <th style="width:170px">Atributos da categoria</th>
                    <th style="width:120px">Diferenciador</th>
                    <th style="width:110px">Preço (R$)</th>
                    <th style="width:90px">Fotos</th>
                    <th style="width:90px">Resultado</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, i) in form.products" :key="p.product_id"
                      :class="{
                        'table-success': resultByProductId[p.product_id]?.ok,
                        'table-danger': resultByProductId[p.product_id] && !resultByProductId[p.product_id].ok,
                        'table-warning': !resultByProductId[p.product_id] && pmcStatusByProductId[p.product_id] === 'missing',
                      }">
                    <td>
                      <img v-if="p._thumb" :src="p._thumb"
                           style="width:40px;height:40px;object-fit:cover;border-radius:3px" />
                    </td>
                    <td>
                      <div class="text-truncate" style="max-width:260px" :title="p._title">{{ p._title }}</div>
                      <div class="text-muted" style="font-size:11px;line-height:1.4">
                        <span><strong>SKU:</strong> <code>{{ p._sku || '—' }}</code></span>
                        <span class="mx-1">·</span>
                        <span><strong>Estoque:</strong> {{ p._stock ?? 0 }}</span>
                      </div>
                    </td>
                    <td>
                      <template v-if="!form.category_id">
                        <span class="text-muted small">Selecione a categoria acima</span>
                      </template>
                      <template v-else-if="pmcLoading">
                        <i class="fas fa-spinner fa-spin text-muted small"></i>
                      </template>
                      <template v-else-if="pmcStatusByProductId[p.product_id] === 'present'">
                        <span class="text-success small">
                          <i class="fas fa-check-circle mr-1"></i>Cadastrada
                        </span>
                        <div v-if="pmcSummaryByProductId[p.product_id]" class="text-muted" style="font-size:10px;line-height:1.2">
                          {{ pmcSummaryByProductId[p.product_id] }}
                        </div>
                      </template>
                      <template v-else>
                        <span class="text-danger small d-block">
                          <i class="fas fa-exclamation-triangle mr-1"></i>Não cadastrada
                        </span>
                        <a :href="catalogPageUrl(p)" target="_blank" rel="noopener" class="small">
                          <i class="fas fa-external-link-alt mr-1"></i>Cadastrar →
                        </a>
                      </template>
                    </td>
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

              <div v-if="missingPmcCount" class="alert alert-warning py-2 mt-2 mb-0 small">
                <i class="fas fa-exclamation-triangle mr-1"></i>
                <strong>{{ missingPmcCount }} produto(s)</strong> sem a categoria cadastrada nas características.
                Clique em "Cadastrar →" em cada linha para abrir a página do produto, escolher a categoria
                <strong>{{ form.category_name || form.category_id }}</strong> e preencher os atributos obrigatórios.
                Depois volte aqui e tente publicar novamente.
              </div>

              <!-- Alerta de divergência em atributos catalog_required (BRAND/MODEL/MATERIAL...) -->
              <div v-if="attrDivergences.length" class="alert alert-danger py-2 mt-2 mb-0 small">
                <i class="fas fa-exclamation-triangle mr-1"></i>
                <strong>Atributos divergentes entre os produtos.</strong>
                O Mercado Livre exige valor <strong>idêntico</strong> (mesma grafia/caixa) nos
                atributos obrigatórios do catálogo, senão coloca os anúncios em famílias separadas.
                <ul class="mb-0 mt-1 pl-3">
                  <li v-for="d in attrDivergences" :key="d.attr_id">
                    <strong>{{ d.attr_name }}</strong> — valores encontrados:
                    <span v-for="(v, i) in d.values" :key="i">
                      <code>{{ v.value }}</code> em {{ v.product_titles.join(', ') }}<span v-if="i < d.values.length - 1">; </span>
                    </span>
                  </li>
                </ul>
                <div class="mt-1">
                  Corrija na página de cada produto (link "Cadastrar →" na linha) — depois volte e
                  troque a categoria de novo aqui pra revalidar.
                </div>
              </div>
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

// PMC por produto: { [product_id]: 'present' | 'missing' }
const pmcStatusByProductId = ref({})
// Resumo human-readable dos attrs do PMC (ex: "Marca: MIG · Material: EVA · Cor: Violeta")
const pmcSummaryByProductId = ref({})
const pmcLoading = ref(false)
// PMC attrs (parseados) por produto para validação de divergência
const pmcAttrsByProductId = ref({})
// Atributo diferenciador (allow_variations) — qual ID buscar no PMC pra pré-preencher
const differentiatorAttrId = ref(null)
// Quais atributos são "catalog_required" da categoria escolhida (BRAND, MODEL, MATERIAL...)
const catalogRequiredAttrs = ref([])   // [{ id, name }]

const missingPmcCount = computed(() =>
  form.products.filter(p => pmcStatusByProductId.value[p.product_id] === 'missing').length
)
const allPmcPresent = computed(() =>
  form.products.length > 0
  && form.products.every(p => pmcStatusByProductId.value[p.product_id] === 'present')
)

function catalogPageUrl(p) {
  return props.source === 'pg'
    ? `/catalog/${p.product_id}`
    : `/cmig-products/${p.product_id}/edit`
}

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
  && allPmcPresent.value
  && attrDivergences.value.length === 0
  && form.products.every(p => Number(p.sale_price) > 0 && p.pictures.length > 0)
)

// Detecta divergências em atributos catalog_required entre os produtos.
// O ML é case-sensitive ao comparar — então 'PVC anti-estouro' != 'PVC Anti-Estouro'
// e os anúncios caem em famílias separadas mesmo com o mesmo family_name.
// Excluímos da comparação o atributo diferenciador (COLOR), que DEVE divergir.
const attrDivergences = computed(() => {
  if (!catalogRequiredAttrs.value.length || !form.products.length) return []
  const diffId = (differentiatorAttrId.value || '').toUpperCase()
  const divergences = []
  for (const attr of catalogRequiredAttrs.value) {
    if (attr.id.toUpperCase() === diffId) continue   // skip diferenciador
    // Agrupa produtos pelo valor desse atributo
    const buckets = {}
    let anyMissing = false
    for (const p of form.products) {
      const pmcAttrs = pmcAttrsByProductId.value[p.product_id] || []
      const found = pmcAttrs.find(a => (a.id || '').toUpperCase() === attr.id.toUpperCase())
      const value = found?.value_name || found?.value_id || ''
      if (!value) anyMissing = true
      const key = String(value)
      if (!buckets[key]) buckets[key] = []
      buckets[key].push(p._title || `#${p.product_id}`)
    }
    if (anyMissing) continue   // falta de atributo já é tratado pelo PMC missing
    const distinct = Object.keys(buckets)
    if (distinct.length > 1) {
      divergences.push({
        attr_id: attr.id,
        attr_name: attr.name,
        values: distinct.map(value => ({ value, product_titles: buckets[value] })),
      })
    }
  }
  return divergences
})

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
  catalogRequiredAttrs.value = []
  supportLoading.value = true
  try {
    const [{ data: sup }, { data: attrs }] = await Promise.all([
      api.get(`/anuncios/categories/${cat.id}/variation-support`),
      api.get(`/anuncios/categories/${cat.id}/attributes`),
    ])
    support.value = sup
    const combAttrs = sup?.variation_combination_attrs || []
    differentiatorAttrId.value = combAttrs[0]?.id || 'COLOR'
    // Filtra atributos catalog_required (BRAND/MODEL/MATERIAL etc.)
    catalogRequiredAttrs.value = (Array.isArray(attrs) ? attrs : [])
      .filter(a => {
        const tags = a.tags || {}
        const tagKeys = Array.isArray(tags) ? tags : Object.keys(tags || {})
        return tagKeys.includes('catalog_required')
      })
      .map(a => ({ id: a.id, name: a.name }))
  } catch {
    support.value = null
    catalogRequiredAttrs.value = []
  } finally { supportLoading.value = false }
  // Verifica em paralelo se cada produto tem PMC para essa categoria
  await refreshPmcStatuses()
}

async function refreshPmcStatuses() {
  if (!form.category_id || !form.products.length) {
    pmcStatusByProductId.value = {}
    pmcSummaryByProductId.value = {}
    pmcAttrsByProductId.value = {}
    return
  }
  pmcLoading.value = true
  const statusMap = {}
  const summaryMap = {}
  const attrsMap = {}
  const owner = props.source === 'pg' ? 'catalog' : 'cmig'
  try {
    await Promise.all(form.products.map(async (p) => {
      try {
        const { data } = await api.get(`/product-categories/${owner}/${p.product_id}`, {
          params: { marketplace: 'mercado_livre' },
        })
        const list = Array.isArray(data) ? data : []
        const match = list.find(pmc => String(pmc.category_id) === String(form.category_id))
        if (match) {
          statusMap[p.product_id] = 'present'
          // Parseia attributes_json para mostrar resumo + validar divergências
          let parsed = []
          try {
            parsed = typeof match.attributes_json === 'string'
              ? JSON.parse(match.attributes_json || '[]')
              : (match.attributes_json || [])
          } catch { parsed = [] }
          attrsMap[p.product_id] = Array.isArray(parsed) ? parsed : []
          const summary = parsed
            .filter(a => a && a.value_name)
            .slice(0, 4)
            .map(a => `${a.name || a.id}: ${a.value_name}`)
            .join(' · ')
          summaryMap[p.product_id] = summary
          // Pré-preenche diferenciador do produto se for vazio e o PMC tiver o atributo
          if (!p.differentiator && differentiatorAttrId.value) {
            const found = parsed.find(a => (a.id || '').toUpperCase() === differentiatorAttrId.value.toUpperCase())
            if (found?.value_name) p.differentiator = found.value_name
          }
        } else {
          statusMap[p.product_id] = 'missing'
          attrsMap[p.product_id] = []
        }
      } catch {
        statusMap[p.product_id] = 'missing'
        attrsMap[p.product_id] = []
      }
    }))
  } finally {
    pmcStatusByProductId.value = statusMap
    pmcSummaryByProductId.value = summaryMap
    pmcAttrsByProductId.value = attrsMap
    pmcLoading.value = false
  }
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
      _stock: p.stock_quantity ?? 0,
      _product_images: [],
    }

    // Busca detalhes completos (imagens, atributos)
    try {
      const url = isPg ? `/catalog/${productId}` : `/cmigs/${p.cmig_id}/products/${productId}`
      const { data } = await api.get(url)
      const imgs = (data.images || []).map(i => ({ url: i.url || i }))
      baseFields._product_images = imgs
      if (imgs.length && !baseFields.pictures.length) baseFields.pictures = [imgs[0].url]
      // Preenche campos que podem estar ausentes em stubs { id } vindos de seleção multi-página
      if (!baseFields._title) baseFields._title = data.title || data.name || `Produto #${productId}`
      if (!baseFields._sku)   baseFields._sku   = isPg ? (data.sku || '') : (data.sku_cmig || '')
      if (!baseFields._thumb) baseFields._thumb  = imgs[0]?.url || null
      // Pré-preenche o diferenciador se houver hint nos atributos do produto
      const hint = (data.color || data.size || '')
      if (hint) baseFields.differentiator = hint
      // Sugestão de preço inicial
      if (data.suggested_price) baseFields.sale_price = Number(data.suggested_price)
      else if (data.cost_price) baseFields.sale_price = Number(data.cost_price)
      // Atualiza estoque com o valor mais fresco do endpoint detalhado
      if (data.stock_quantity != null) baseFields._stock = data.stock_quantity
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
