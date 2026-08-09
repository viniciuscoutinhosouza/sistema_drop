<template>
  <div>
    <hr />
    <div class="d-flex align-items-center mb-3">
      <h6 class="text-muted text-uppercase mb-0 flex-grow-1">
        <small>Categorias do Marketplace</small>
      </h6>
      <button v-if="ownerId" type="button" class="btn btn-sm btn-outline-primary"
              @click="addMode = !addMode" :title="addMode ? 'Cancelar' : 'Adicionar categoria'">
        <i :class="['fas', addMode ? 'fa-times' : 'fa-plus']"></i>
        {{ addMode ? 'Cancelar' : 'Adicionar Categoria' }}
      </button>
    </div>

    <div v-if="!ownerId" class="alert alert-secondary py-2 small mb-0">
      <i class="fas fa-info-circle mr-1"></i>
      Salve o produto primeiro para cadastrar categorias do marketplace.
    </div>

    <div v-else>
      <!-- Lista de categorias cadastradas -->
      <div v-if="!loading && categories.length === 0 && !addMode" class="text-muted small mb-2">
        Nenhuma categoria cadastrada. Clique em "Adicionar Categoria" para começar.
      </div>

      <div v-if="loading" class="text-center text-muted small py-2">
        <i class="fas fa-spinner fa-spin"></i> Carregando...
      </div>

      <div v-for="cat in categories" :key="cat.id" class="card mb-2">
        <div class="card-header py-2 d-flex align-items-center" style="cursor:pointer"
             @click="toggleExpand(cat.id)">
          <span class="badge badge-info mr-2">{{ marketplaceLabel(cat.marketplace) }}</span>
          <div class="flex-grow-1">
            <strong class="small">{{ categoryDisplay(cat) }}</strong>
            <code class="text-muted ml-2" style="font-size:11px">{{ cat.category_id }}</code>
          </div>
          <span class="badge badge-light mr-2" :title="`${filledCount(cat)} atributo(s) preenchido(s)`">
            {{ filledCount(cat) }} attr
          </span>
          <button type="button" class="btn btn-sm btn-link text-danger p-0 mr-2" @click.stop="removeCategory(cat)"
                  title="Remover categoria">
            <i class="fas fa-trash"></i>
          </button>
          <i :class="['fas', expanded[cat.id] ? 'fa-chevron-up' : 'fa-chevron-down', 'text-muted']"></i>
        </div>
        <div v-if="expanded[cat.id]" class="card-body py-2">
          <div v-if="loadingAttrs[cat.id]" class="text-center text-muted small py-2">
            <i class="fas fa-spinner fa-spin"></i> Carregando atributos...
          </div>
          <template v-else>
            <div v-if="(attrSchemas[cat.id] || []).length === 0" class="text-muted small">
              Esta categoria não retornou atributos do marketplace.
            </div>
            <!-- Marca Shopee (conceito separado do atributo; obrigatória quando is_mandatory) -->
            <div v-if="isShopee(cat)" class="form-group mb-2">
              <label class="small mb-1">
                Marca
                <span v-if="(brandInfo[cat.id] || {}).is_mandatory" class="text-danger">*</span>
              </label>
              <select :value="(brandSel[cat.id] || {}).brand_id ?? ''"
                      @change="setBrand(cat.id, $event.target.value)"
                      class="form-control form-control-sm">
                <option value="">— Selecione a marca —</option>
                <option v-for="b in (brandInfo[cat.id] || {}).brands || []" :key="b.brand_id" :value="b.brand_id">
                  {{ b.name }}
                </option>
              </select>
            </div>

            <div class="row">
              <div v-for="attr in attrSchemas[cat.id]" :key="attr.id" class="col-md-4 form-group mb-2">
                <label class="small mb-1">
                  {{ attr.name }}
                  <span v-if="attr.is_required" class="text-danger">*</span>
                  <span v-else-if="attr.is_recommended" class="text-muted" style="font-size:10px">(rec.)</span>
                  <span v-if="attr.input_kind === 'multi'" class="text-muted" style="font-size:10px">
                    (até {{ attr.max_value_count }})
                  </span>
                </label>

                <!-- ── Ramo Mercado Livre (inalterado) ── -->
                <template v-if="!isShopee(cat)">
                  <select v-if="attr.values && attr.values.length > 0"
                          :value="getAttrValue(cat.id, attr.id)"
                          @change="setAttrValue(cat.id, attr.id, attr.name, $event.target.value)"
                          class="form-control form-control-sm">
                    <option value="">— Selecione —</option>
                    <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                  </select>
                  <input v-else
                         :value="getAttrValue(cat.id, attr.id)"
                         @input="setAttrValue(cat.id, attr.id, attr.name, $event.target.value)"
                         class="form-control form-control-sm" :placeholder="attr.name" />
                </template>

                <!-- ── Ramo Shopee (por input_kind; guarda value_id) ── -->
                <template v-else>
                  <select v-if="attr.input_kind === 'multi'" multiple size="4"
                          @change="setMultiValue(cat.id, attr, $event)"
                          class="form-control form-control-sm">
                    <option v-for="v in attr.values" :key="v.id" :value="v.id"
                            :selected="getMultiValue(cat.id, attr.id).includes(v.id)">{{ v.name }}</option>
                  </select>
                  <div v-else-if="attr.input_kind === 'quantitative'" class="input-group input-group-sm">
                    <input type="number" class="form-control form-control-sm" :placeholder="attr.name"
                           :value="getQtyValue(cat.id, attr.id).value"
                           @input="setQtyValue(cat.id, attr, 'value', $event.target.value)" />
                    <select v-if="attr.allowed_units && attr.allowed_units.length"
                            class="form-control form-control-sm" style="max-width:90px"
                            :value="getQtyValue(cat.id, attr.id).unit"
                            @change="setQtyValue(cat.id, attr, 'unit', $event.target.value)">
                      <option value="">un.</option>
                      <option v-for="u in attr.allowed_units" :key="u" :value="u">{{ u }}</option>
                    </select>
                  </div>
                  <select v-else-if="attr.values && attr.values.length > 0"
                          :value="getAttrValue(cat.id, attr.id)"
                          @change="setShopeeSingle(cat.id, attr, $event.target.value)"
                          class="form-control form-control-sm">
                    <option value="">— Selecione —</option>
                    <option v-for="v in attr.values" :key="v.id" :value="v.id">{{ v.name }}</option>
                  </select>
                  <input v-else
                         :value="getAttrValue(cat.id, attr.id)"
                         @input="setShopeeText(cat.id, attr, $event.target.value)"
                         class="form-control form-control-sm" :placeholder="attr.name" />
                </template>
              </div>
            </div>
            <div class="text-right">
              <button type="button" class="btn btn-sm btn-primary" @click="saveCategoryAttrs(cat)"
                      :disabled="saving[cat.id]">
                <i :class="['fas', saving[cat.id] ? 'fa-spinner fa-spin' : 'fa-save']"></i>
                Salvar atributos
              </button>
            </div>
          </template>
        </div>
      </div>

      <!-- Adicionar nova categoria -->
      <div v-if="addMode" class="card border-primary mt-2">
        <div class="card-body py-2">
          <div class="form-group mb-2">
            <label class="small mb-1">Marketplace</label>
            <select v-model="newCat.marketplace" class="form-control form-control-sm" @change="onMarketplaceChange">
              <option value="mercado_livre">Mercado Livre</option>
              <option value="shopee">Shopee</option>
            </select>
          </div>

          <div v-if="newCat.marketplace === 'shopee' && shopeeAccountError"
               class="alert alert-warning py-2 small mb-2">
            <i class="fas fa-exclamation-triangle mr-1"></i>{{ shopeeAccountError }}
          </div>

          <div class="form-group mb-2">
            <label class="small mb-1">Buscar categoria</label>
            <div class="input-group input-group-sm">
              <input v-model="searchQuery" class="form-control form-control-sm"
                     placeholder="Ex: Tênis Masculino, Celular..."
                     @input="debouncedSearch" />
              <div class="input-group-append">
                <button class="btn btn-outline-secondary" @click="runSearch" :disabled="searchLoading">
                  <i :class="['fas', searchLoading ? 'fa-spinner fa-spin' : 'fa-search']"></i>
                </button>
              </div>
            </div>
            <div v-if="searchResults.length > 0" class="list-group mt-2" style="max-height:180px;overflow-y:auto">
              <a v-for="r in searchResults" :key="r.id"
                 class="list-group-item list-group-item-action py-1 small"
                 href="#" @click.prevent="selectSearchResult(r)">
                <code class="text-primary" style="font-size:11px">{{ r.id }}</code>
                <span class="text-muted mx-2">-</span>
                <template v-if="r.path_from_root && r.path_from_root.length">
                  <span v-for="(p, i) in r.path_from_root" :key="p.id">
                    <span :class="i === r.path_from_root.length - 1 ? 'font-weight-bold' : 'text-muted'">{{ p.name }}</span>
                    <i v-if="i < r.path_from_root.length - 1" class="fas fa-angle-right mx-1 text-muted" style="font-size:9px"></i>
                  </span>
                </template>
                <strong v-else>{{ r.name }}</strong>
              </a>
            </div>
          </div>

          <div v-if="newCat.category_id" class="alert alert-info py-2 small mb-2">
            <div>
              Categoria selecionada: <strong>{{ newCat.category_name }}</strong>
              <code class="ml-1">{{ newCat.category_id }}</code>
            </div>
            <div v-if="newCatPath.length" class="text-muted mt-1" style="font-size:11px">
              <span v-for="(p, i) in newCatPath" :key="p.id">
                <span>{{ p.name }}</span>
                <i v-if="i < newCatPath.length - 1" class="fas fa-angle-right mx-1" style="font-size:9px"></i>
              </span>
            </div>
          </div>

          <div class="text-right">
            <button type="button" class="btn btn-sm btn-secondary mr-2" @click="cancelAdd">Cancelar</button>
            <button type="button" class="btn btn-sm btn-primary" @click="confirmAdd"
                    :disabled="!newCat.category_id || addLoading">
              <i :class="['fas', addLoading ? 'fa-spinner fa-spin' : 'fa-check']"></i>
              Adicionar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  // 'catalog' ou 'cmig'
  ownerType: { type: String, required: true },
  // ID do produto. Se null/undefined, mostra mensagem "salve primeiro"
  ownerId: { type: [Number, String], default: null },
})

const toast = useToast()

const categories = ref([])
const loading = ref(false)
const expanded = reactive({})
const attrSchemas = reactive({})   // { pmcId: [ {id, name, value_type, values, ...} ] }
const attrValues = reactive({})    // { pmcId: { attrId: 'value_name' } }
const loadingAttrs = reactive({})
const saving = reactive({})

// ── Shopee (Fase 1): conta shop-scoped + marca (conceito separado do atributo) ──
const shopeeAccountId = ref(null)
const shopeeAccountError = ref('')
const brandInfo = reactive({})  // { pmcId: {is_mandatory, brands:[{brand_id,name}], ...} }
const brandSel = reactive({})   // { pmcId: {brand_id, name} }

function isShopee(cat) { return cat?.marketplace === 'shopee' }

async function resolveShopeeAccount() {
  if (shopeeAccountId.value) return shopeeAccountId.value
  try {
    const { data } = await api.get('/shopee/default-account')
    if (!data.account_id) {
      shopeeAccountError.value = data.detail ||
        'Nenhuma conta Shopee conectada. Conecte uma loja Shopee para cadastrar categorias Shopee.'
      return null
    }
    shopeeAccountId.value = data.account_id
    shopeeAccountError.value = ''
    return data.account_id
  } catch {
    shopeeAccountError.value = 'Erro ao resolver a conta Shopee.'
    return null
  }
}

async function onMarketplaceChange() {
  searchResults.value = []
  searchQuery.value = ''
  newCat.category_id = ''
  newCat.category_name = ''
  newCat.category_path_json = null
  if (newCat.marketplace === 'shopee') await resolveShopeeAccount()
  else shopeeAccountError.value = ''
}

const addMode = ref(false)
const addLoading = ref(false)
const newCat = reactive({
  marketplace: 'mercado_livre',
  category_id: '',
  category_name: '',
  category_path_json: null,
})

const searchQuery = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
let searchTimer = null

const newCatPath = computed(() => {
  try {
    const p = JSON.parse(newCat.category_path_json || '[]')
    return Array.isArray(p) ? p : []
  } catch {
    return []
  }
})

const ownerEndpoint = () =>
  props.ownerType === 'cmig'
    ? `/product-categories/cmig/${props.ownerId}`
    : `/product-categories/catalog/${props.ownerId}`

function marketplaceLabel(mk) {
  return mk === 'mercado_livre' ? 'ML' : (mk === 'shopee' ? 'Shopee' : mk)
}

function categoryDisplay(cat) {
  // Prefere o breadcrumb completo (mais informativo) quando disponível
  try {
    const path = JSON.parse(cat.category_path_json || '[]')
    if (Array.isArray(path) && path.length) return path.map(p => p.name).join(' > ')
  } catch { /* ignore */ }
  return cat.category_name || cat.category_id
}

function filledCount(cat) {
  const v = attrValues[cat.id] || {}
  return Object.values(v).filter(x => x !== '' && x != null).length
}

async function loadCategories() {
  if (!props.ownerId) {
    categories.value = []
    return
  }
  loading.value = true
  try {
    const { data } = await api.get(ownerEndpoint())
    categories.value = Array.isArray(data) ? data : []
    for (const cat of categories.value) {
      hydrateValuesFromSaved(cat)
    }
  } catch (err) {
    toast.error('Erro ao carregar categorias do marketplace')
  } finally {
    loading.value = false
  }
}

function hydrateValuesFromSaved(cat) {
  if (!attrValues[cat.id]) attrValues[cat.id] = {}
  try {
    const saved = JSON.parse(cat.attributes_json || '[]')
    for (const a of saved) {
      if (a.id === '__SHOPEE_BRAND__') {
        brandSel[cat.id] = { brand_id: a.value_id, name: a.name }
        continue
      }
      if (!a.id) continue
      if (isShopee(cat)) {
        if (a.kind === 'multi') attrValues[cat.id][a.id] = a.value_ids || []
        else if (a.kind === 'quantitative') attrValues[cat.id][a.id] = { value: a.value_name ?? '', unit: a.value_unit ?? '' }
        else if (a.kind === 'single') attrValues[cat.id][a.id] = a.value_id
        else attrValues[cat.id][a.id] = a.value_name ?? ''
      } else {
        attrValues[cat.id][a.id] = a.value_name ?? a.value ?? ''
      }
    }
  } catch { /* ignore */ }
}

async function toggleExpand(catId) {
  expanded[catId] = !expanded[catId]
  if (expanded[catId] && !attrSchemas[catId]) {
    await fetchAttrSchema(catId)
  }
}

async function fetchAttrSchema(pmcId) {
  const cat = categories.value.find(c => c.id === pmcId)
  if (!cat) return
  loadingAttrs[pmcId] = true
  try {
    if (isShopee(cat)) {
      const acc = await resolveShopeeAccount()
      if (!acc) { attrSchemas[pmcId] = []; return }
      const { data } = await api.get(`/shopee/categories/${cat.category_id}/attributes`,
                                     { params: { account_id: acc } })
      attrSchemas[pmcId] = Array.isArray(data) ? data : []
      await fetchBrands(pmcId, cat, acc)
    } else {
      const { data } = await api.get(`/anuncios/categories/${cat.category_id}/attributes`)
      attrSchemas[pmcId] = Array.isArray(data) ? data : []
    }
  } catch (err) {
    attrSchemas[pmcId] = []
    toast.error('Erro ao carregar atributos da categoria')
  } finally {
    loadingAttrs[pmcId] = false
  }
}

// ── Shopee: marca da categoria + getters/setters por input_kind ──
async function fetchBrands(pmcId, cat, acc) {
  try {
    const { data } = await api.get(`/shopee/categories/${cat.category_id}/brands`,
                                   { params: { account_id: acc } })
    brandInfo[pmcId] = data
  } catch { brandInfo[pmcId] = { is_mandatory: false, brands: [] } }
}

function setBrand(pmcId, brandId) {
  const info = brandInfo[pmcId] || { brands: [] }
  const b = (info.brands || []).find(x => String(x.brand_id) === String(brandId))
  brandSel[pmcId] = b ? { brand_id: b.brand_id, name: b.name } : null
}

function getMultiValue(pmcId, attrId) {
  const v = (attrValues[pmcId] || {})[attrId]
  return Array.isArray(v) ? v : []
}
function setMultiValue(pmcId, attr, event) {
  const ids = Array.from(event.target.selectedOptions).map(o => Number(o.value))
  if (!attrValues[pmcId]) attrValues[pmcId] = {}
  attrValues[pmcId][attr.id] = ids.slice(0, attr.max_value_count || ids.length)
}
function getQtyValue(pmcId, attrId) {
  const v = (attrValues[pmcId] || {})[attrId]
  return (v && typeof v === 'object' && !Array.isArray(v)) ? v : { value: '', unit: '' }
}
function setQtyValue(pmcId, attr, field, val) {
  if (!attrValues[pmcId]) attrValues[pmcId] = {}
  attrValues[pmcId][attr.id] = { ...getQtyValue(pmcId, attr.id), [field]: val }
}
function setShopeeSingle(pmcId, attr, valueId) {
  if (!attrValues[pmcId]) attrValues[pmcId] = {}
  attrValues[pmcId][attr.id] = valueId
}
function setShopeeText(pmcId, attr, text) {
  if (!attrValues[pmcId]) attrValues[pmcId] = {}
  attrValues[pmcId][attr.id] = text
}

function getAttrValue(pmcId, attrId) {
  return (attrValues[pmcId] || {})[attrId] ?? ''
}

function setAttrValue(pmcId, attrId, attrName, value) {
  if (!attrValues[pmcId]) attrValues[pmcId] = {}
  attrValues[pmcId][attrId] = value
  // Guarda o nome do atributo no schema (caso usuário só edite e salve sem reabrir)
  const schema = attrSchemas[pmcId] || []
  const found = schema.find(a => a.id === attrId)
  if (!found && attrName) {
    attrSchemas[pmcId] = [...schema, { id: attrId, name: attrName, values: [] }]
  }
}

function hasValue(v) {
  if (v == null || v === '') return false
  if (Array.isArray(v)) return v.length > 0
  if (typeof v === 'object') return v.value !== '' && v.value != null  // quantitativo: 0 é válido
  return true
}

function buildShopeePayload(cat, schema, values) {
  const out = []
  for (const a of schema) {
    const v = values[a.id]
    if (!hasValue(v)) continue
    if (a.input_kind === 'multi') {
      const names = v.map(id => (a.values.find(x => x.id === id) || {}).name)
      out.push({ id: a.id, name: a.name, kind: 'multi', value_ids: v, value_names: names })
    } else if (a.input_kind === 'quantitative') {
      out.push({ id: a.id, name: a.name, kind: 'quantitative',
                 value_id: 0, value_name: String(v.value), value_unit: v.unit || '' })
    } else if (a.values && a.values.length) {
      const vid = Number(v)
      out.push({ id: a.id, name: a.name, kind: 'single',
                 value_id: vid, value_name: (a.values.find(x => x.id === vid) || {}).name })
    } else {
      out.push({ id: a.id, name: a.name, kind: 'text', value_id: 0, value_name: String(v) })
    }
  }
  const b = brandSel[cat.id]
  if (b && b.brand_id != null) {
    out.push({ id: '__SHOPEE_BRAND__', name: b.name, kind: 'brand', value_id: b.brand_id, value_name: b.name })
  }
  return out
}

async function saveCategoryAttrs(cat) {
  const schema = attrSchemas[cat.id] || []
  const values = attrValues[cat.id] || {}
  let attrsPayload
  if (isShopee(cat)) {
    // Falhar alto: obrigatórios (mandatory) + marca (quando is_mandatory) antes de salvar.
    const missing = schema.filter(a => a.is_required && !hasValue(values[a.id])).map(a => a.name)
    if ((brandInfo[cat.id] || {}).is_mandatory && !((brandSel[cat.id] || {}).brand_id != null)) {
      missing.push('Marca')
    }
    if (missing.length) {
      toast.warning('Preencha os campos obrigatórios da Shopee: ' + missing.join(', '))
      return
    }
    attrsPayload = buildShopeePayload(cat, schema, values)
  } else {
    attrsPayload = schema
      .filter(a => values[a.id] !== '' && values[a.id] != null)
      .map(a => ({ id: a.id, name: a.name, value_name: values[a.id] }))
  }

  saving[cat.id] = true
  try {
    await api.put(`/product-categories/${cat.id}`, {
      attributes_json: attrsPayload,
    })
    cat.attributes_json = JSON.stringify(attrsPayload)
    toast.success('Atributos salvos')
  } catch (err) {
    toast.error(err?.response?.data?.detail || 'Erro ao salvar atributos')
  } finally {
    saving[cat.id] = false
  }
}

async function removeCategory(cat) {
  if (!confirm(`Remover categoria "${categoryDisplay(cat)}"?`)) return
  try {
    await api.delete(`/product-categories/${cat.id}`)
    categories.value = categories.value.filter(c => c.id !== cat.id)
    delete attrSchemas[cat.id]
    delete attrValues[cat.id]
    delete expanded[cat.id]
    toast.success('Categoria removida')
  } catch (err) {
    toast.error(err?.response?.data?.detail || 'Erro ao remover')
  }
}

function debouncedSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(runSearch, 400)
}

async function runSearch() {
  if (!searchQuery.value || searchQuery.value.length < 2) {
    searchResults.value = []
    return
  }
  searchLoading.value = true
  try {
    let data
    if (newCat.marketplace === 'shopee') {
      const acc = await resolveShopeeAccount()
      if (!acc) { searchResults.value = []; return }
      ;({ data } = await api.get('/shopee/categories/search',
                                 { params: { account_id: acc, q: searchQuery.value } }))
    } else {
      ;({ data } = await api.get(`/anuncios/categories/search?q=${encodeURIComponent(searchQuery.value)}`))
    }
    searchResults.value = Array.isArray(data) ? data : []
  } catch {
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

function selectSearchResult(r) {
  // Shopee: só categoria FOLHA publica.
  if (newCat.marketplace === 'shopee' && r.is_leaf === false) {
    toast.warning('Na Shopee só é possível publicar em categoria FOLHA (sem subcategorias). Escolha uma folha.')
    return
  }
  newCat.category_id = r.id
  newCat.category_name = r.name || (r.path_from_root && r.path_from_root.length
    ? r.path_from_root[r.path_from_root.length - 1].name : '')
  newCat.category_path_json = r.path_from_root ? JSON.stringify(r.path_from_root) : null
  searchResults.value = []
}

function cancelAdd() {
  addMode.value = false
  newCat.category_id = ''
  newCat.category_name = ''
  newCat.category_path_json = null
  searchQuery.value = ''
  searchResults.value = []
}

async function confirmAdd() {
  if (!newCat.category_id) return
  addLoading.value = true
  try {
    const payload = {
      marketplace: newCat.marketplace,
      category_id: newCat.category_id,
      category_name: newCat.category_name,
      category_path_json: newCat.category_path_json,
    }
    if (props.ownerType === 'cmig') payload.cmig_product_id = props.ownerId
    else payload.catalog_product_id = props.ownerId

    const { data } = await api.post('/product-categories', payload)
    categories.value.push(data)
    hydrateValuesFromSaved(data)
    cancelAdd()
    toast.success('Categoria adicionada')
    // Auto-expande para o usuário começar a preencher
    await toggleExpand(data.id)
  } catch (err) {
    toast.error(err?.response?.data?.detail || 'Erro ao adicionar categoria')
  } finally {
    addLoading.value = false
  }
}

watch(() => props.ownerId, () => {
  loadCategories()
})

onMounted(() => {
  loadCategories()
})
</script>
