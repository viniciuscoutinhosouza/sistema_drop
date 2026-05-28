<template>
  <div>
    <label class="font-weight-bold">Categoria <span class="text-danger">*</span></label>

    <!-- Loading inicial -->
    <div v-if="loadingSaved" class="text-muted small">
      <i class="fas fa-spinner fa-spin mr-1"></i>Carregando categorias salvas...
    </div>

    <template v-else>
      <!-- Dropdown de categorias salvas (quando há ao menos uma) -->
      <div v-if="savedCategories.length" class="mb-2">
        <select v-model="selectedKey" class="form-control" @change="onDropdownChange">
          <option v-for="cat in savedCategories" :key="`s:${cat.id}`" :value="`s:${cat.id}`">
            {{ cat._synthetic ? '📝 (atual) ' : '⭐ ' }}{{ formatCategoryFullName(cat) }} ({{ cat.category_id }})
          </option>
          <option value="new">➕ Buscar outra categoria...</option>
        </select>
      </div>

      <!-- Resumo da categoria selecionada (salva ou nova) -->
      <div v-if="current.category_id && selectedKey !== 'new'" class="mb-2">
        <div class="p-2 rounded border" style="background:#f8f9fa">
          <div v-if="pathLoading" class="text-muted small">
            <i class="fas fa-spinner fa-spin mr-1"></i>Carregando categorias pai...
          </div>
          <div v-else-if="currentPathItems.length" class="d-flex align-items-center flex-wrap" style="gap:4px;font-size:12px">
            <span v-for="(p, i) in currentPathItems" :key="p.id || i">
              <span :class="i === currentPathItems.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">{{ p.name }}</span>
              <i v-if="i < currentPathItems.length - 1" class="fas fa-angle-right mx-1 text-muted"></i>
            </span>
          </div>
          <div v-else class="font-weight-bold" style="font-size:13px">
            {{ current.category_name }}
          </div>
          <code class="text-muted d-block mt-1" style="font-size:11px">ID: {{ current.category_id }}</code>
        </div>
        <div class="d-flex align-items-center flex-wrap mt-2" style="gap:8px">
          <span v-if="attrsLoading" class="text-muted small">
            <i class="fas fa-spinner fa-spin mr-1"></i>Carregando características...
          </span>
          <button v-else-if="attrs.length" type="button"
                  class="btn btn-sm btn-outline-primary" @click="attrsModalShow = true">
            <i class="fas fa-list-ul mr-1"></i>Características
            <span v-if="filledAttrsCount" class="badge badge-primary ml-1">{{ filledAttrsCount }}</span>
            <span v-if="requiredUnfilledCount" class="badge badge-danger ml-1">{{ requiredUnfilledCount }} obrigatórios</span>
          </button>
        </div>
      </div>

      <!-- Busca por nova categoria -->
      <div v-if="!savedCategories.length || selectedKey === 'new'">
        <!-- Quando já há uma categoria nova selecionada -->
        <div v-if="selectedKey === 'new' && current.category_id" class="mb-2">
          <div class="p-2 rounded border" style="background:#e8f5e9;border-color:#a5d6a7 !important">
            <div class="small text-success mb-1">
              <i class="fas fa-plus-circle mr-1"></i>Nova categoria
            </div>
            <div v-if="currentPathItems.length" class="d-flex align-items-center flex-wrap" style="gap:4px;font-size:12px">
              <span v-for="(p, i) in currentPathItems" :key="p.id || i">
                <span :class="i === currentPathItems.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">{{ p.name }}</span>
                <i v-if="i < currentPathItems.length - 1" class="fas fa-angle-right mx-1 text-muted"></i>
              </span>
            </div>
            <div v-else class="font-weight-bold" style="font-size:13px">
              {{ current.category_name }}
            </div>
            <code class="text-muted d-block mt-1" style="font-size:11px">ID: {{ current.category_id }}</code>
          </div>
          <div class="d-flex align-items-center flex-wrap mt-2" style="gap:8px">
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="clearNew">
              <i class="fas fa-times"></i> Limpar
            </button>
            <span v-if="attrsLoading" class="text-muted small">
              <i class="fas fa-spinner fa-spin mr-1"></i>Carregando características...
            </span>
            <button v-else-if="attrs.length" type="button"
                    class="btn btn-sm btn-outline-primary" @click="attrsModalShow = true">
              <i class="fas fa-list-ul mr-1"></i>Características
              <span v-if="filledAttrsCount" class="badge badge-primary ml-1">{{ filledAttrsCount }}</span>
              <span v-if="requiredUnfilledCount" class="badge badge-danger ml-1">{{ requiredUnfilledCount }} obrigatórios</span>
            </button>
          </div>
        </div>

        <div v-else>
          <div class="input-group">
            <input v-model="catSearch" type="text" class="form-control"
                   placeholder="Pesquisar categoria no marketplace..." @input="debouncedCatSearch" />
            <div class="input-group-append">
              <span class="input-group-text"><i class="fas fa-search"></i></span>
            </div>
          </div>
          <div v-if="catSearching" class="text-muted small mt-1">
            <i class="fas fa-spinner fa-spin mr-1"></i>Buscando...
          </div>
          <div v-if="catResults.length" class="list-group mt-1"
               style="max-height:200px;overflow-y:auto;position:relative;z-index:10">
            <button v-for="cat in catResults" :key="cat.id" type="button"
                    class="list-group-item list-group-item-action py-1 px-2" style="font-size:13px"
                    @click="pickNewCategory(cat)">
              <strong>{{ cat.name }}</strong>
              <span v-if="cat.path_from_root?.length" class="text-muted ml-2">
                {{ cat.path_from_root.map(p => p.name).join(' › ') }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- ── Modal: Características da Categoria ── -->
    <div v-if="attrsModalShow" class="modal d-block" tabindex="-1"
         style="background:rgba(0,0,0,0.45);z-index:1060">
      <div class="modal-dialog modal-lg modal-dialog-scrollable">
        <div class="modal-content">

          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-list-ul mr-2"></i>Características da Categoria</h5>
            <button type="button" class="close" @click="attrsModalShow = false"><span>&times;</span></button>
          </div>

          <div class="modal-body">
            <div v-if="requiredAttrs.length" class="mb-4">
              <h6 class="font-weight-bold text-danger mb-2">
                <i class="fas fa-asterisk mr-1" style="font-size:10px"></i>Obrigatórios
              </h6>
              <div class="row">
                <div v-for="attr in requiredAttrs" :key="attr.id" class="col-md-6 form-group mb-2">
                  <label class="font-weight-bold small">{{ attr.name }} <span class="text-danger">*</span></label>
                  <select v-if="attr.values && attr.values.length"
                          v-model="attrValues[attr.id]" @change="emitUpdate"
                          class="form-control form-control-sm"
                          :class="{ 'border-danger': !attrValues[attr.id] }">
                    <option value="">Selecione...</option>
                    <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                  </select>
                  <input v-else v-model="attrValues[attr.id]" @input="emitUpdate"
                         type="text" class="form-control form-control-sm"
                         :class="{ 'border-danger': !attrValues[attr.id] }"
                         :placeholder="attr.allowed_units?.length ? `Valor (${attr.allowed_units.join(', ')})` : 'Digite...'" />
                </div>
              </div>
            </div>

            <div v-if="recommendedAttrs.length" class="mb-4">
              <h6 class="font-weight-bold text-primary mb-2">
                <i class="fas fa-star mr-1" style="font-size:10px"></i>Recomendados
              </h6>
              <div class="row">
                <div v-for="attr in recommendedAttrs" :key="attr.id" class="col-md-6 form-group mb-2">
                  <label class="small font-weight-bold">{{ attr.name }}</label>
                  <select v-if="attr.values && attr.values.length"
                          v-model="attrValues[attr.id]" @change="emitUpdate"
                          class="form-control form-control-sm">
                    <option value="">Selecione...</option>
                    <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                  </select>
                  <input v-else v-model="attrValues[attr.id]" @input="emitUpdate"
                         type="text" class="form-control form-control-sm"
                         :placeholder="attr.allowed_units?.length ? `Valor (${attr.allowed_units.join(', ')})` : 'Digite...'" />
                </div>
              </div>
            </div>

            <div v-if="optionalAttrs.length">
              <button type="button" class="btn btn-sm btn-outline-secondary w-100 text-left mb-2"
                      @click="secondaryExpanded = !secondaryExpanded">
                <i :class="['fas', secondaryExpanded ? 'fa-chevron-down' : 'fa-chevron-right', 'mr-1']"></i>
                Características Secundárias ({{ optionalAttrs.length }})
                <span v-if="filledOptionalCount" class="badge badge-secondary ml-2">{{ filledOptionalCount }} preenchidos</span>
              </button>
              <div v-if="secondaryExpanded" class="row">
                <div v-for="attr in optionalAttrs" :key="attr.id" class="col-md-6 form-group mb-2">
                  <label class="small">{{ attr.name }}</label>
                  <select v-if="attr.values && attr.values.length"
                          v-model="attrValues[attr.id]" @change="emitUpdate"
                          class="form-control form-control-sm">
                    <option value="">Selecione...</option>
                    <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                  </select>
                  <input v-else v-model="attrValues[attr.id]" @input="emitUpdate"
                         type="text" class="form-control form-control-sm"
                         :placeholder="attr.allowed_units?.length ? `Valor (${attr.allowed_units.join(', ')})` : 'Digite...'" />
                </div>
              </div>
            </div>

            <div v-if="!attrs.length && !attrsLoading" class="text-muted small">
              Esta categoria não possui características configuráveis.
            </div>
          </div>

          <div class="modal-footer justify-content-between">
            <span class="text-muted small">
              {{ filledAttrsCount }} preenchido(s)
              <span v-if="requiredUnfilledCount" class="text-danger ml-2">
                · {{ requiredUnfilledCount }} obrigatório(s) pendente(s)
              </span>
            </span>
            <button class="btn btn-primary" @click="attrsModalShow = false">
              <i class="fas fa-check mr-1"></i>Confirmar
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

const props = defineProps({
  ownerType:   { type: String,  required: true },   // 'catalog' | 'cmig'
  ownerId:     { type: [Number, String], required: true },
  marketplace: { type: String,  required: true },   // 'mercado_livre' | 'shopee'
  productHints: { type: Object, default: () => ({}) }, // { brand, model } para pré-preencher BRAND/MODEL
  modelValue:  { type: Object, default: () => ({}) },
  // Para edição: seleção inicial { category_id, category_name?, attributes? }
  initialValue: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue'])

// ── Estado ─────────────────────────────────────────────────────────────────────
const loadingSaved   = ref(false)
const savedCategories = ref([])    // [{id, category_id, category_name, attributes_json, ...}]
const selectedKey    = ref('')     // "s:<pmc_id>" | "new" | ''

const current = reactive({
  pmc_id: null,
  category_id: '',
  category_name: '',
  category_path_json: null,
  isNew: false,
})

// Busca de nova categoria
const catSearch    = ref('')
const catResults   = ref([])
const catSearching = ref(false)
let catDebounce    = null

// Atributos da categoria
const attrs            = ref([])
const attrsLoading     = ref(false)
const attrsModalShow   = ref(false)
const attrValues       = reactive({})
const secondaryExpanded = ref(false)

// Path (breadcrumb) da categoria
const pathLoading = ref(false)

const currentPathItems = computed(() => {
  const raw = current.category_path_json
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
})

function formatCategoryFullName(cat) {
  if (!cat) return ''
  const raw = cat.category_path_json
  if (raw) {
    try {
      const path = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(path) && path.length) {
        return path.map(p => p.name).join(' › ')
      }
    } catch { /* ignore */ }
  }
  return cat.category_name || cat.category_id
}

async function fetchPathFromML(categoryId) {
  pathLoading.value = true
  try {
    const { data } = await api.get(`/anuncios/categories/${categoryId}`)
    if (data?.path_from_root?.length) {
      current.category_path_json = JSON.stringify(data.path_from_root)
      emitUpdate()
    }
  } catch {
    /* ignore — sem path */
  } finally {
    pathLoading.value = false
  }
}

// ── Computed ──────────────────────────────────────────────────────────────────
const requiredAttrs    = computed(() => attrs.value.filter(a => a.is_required))
const recommendedAttrs = computed(() => attrs.value.filter(a => a.is_recommended))
const optionalAttrs    = computed(() => attrs.value.filter(a => a.is_optional))

const filledAttrsCount = computed(() =>
  Object.values(attrValues).filter(v => v !== '' && v != null).length
)
const filledOptionalCount = computed(() =>
  optionalAttrs.value.filter(a => attrValues[a.id]).length
)
const requiredUnfilledCount = computed(() =>
  requiredAttrs.value.filter(a => !attrValues[a.id]).length
)

// ── Helpers ───────────────────────────────────────────────────────────────────
function buildAttributesArray() {
  return Object.entries(attrValues)
    .filter(([, v]) => v !== '' && v != null)
    .map(([id, value_name]) => ({ id, value_name: String(value_name) }))
}

function emitUpdate() {
  emit('update:modelValue', {
    pmc_id: current.pmc_id,
    category_id: current.category_id,
    category_name: current.category_name,
    category_path_json: current.category_path_json,
    isNew: current.isNew,
    attributes: buildAttributesArray(),
  })
}

function clearAttrValues() {
  Object.keys(attrValues).forEach(k => delete attrValues[k])
}

function hydrateFromHints() {
  // Pré-preenche BRAND/MODEL do produto se ainda não preenchidos
  attrs.value.forEach(attr => {
    if (attrValues[attr.id]) return
    if (attr.id === 'BRAND' && props.productHints?.brand) {
      attrValues[attr.id] = props.productHints.brand
    } else if (attr.id === 'MODEL' && props.productHints?.model) {
      attrValues[attr.id] = props.productHints.model
    }
  })
}

async function loadCategoryAttrs(categoryId, savedAttrsJson = null) {
  attrsLoading.value = true
  attrs.value = []
  secondaryExpanded.value = false
  clearAttrValues()
  try {
    const { data } = await api.get(`/anuncios/categories/${categoryId}/attributes`)
    attrs.value = Array.isArray(data) ? data : []

    // Hidrata a partir de attributes_json salvo (lista de {id, value_name})
    if (savedAttrsJson) {
      try {
        const parsed = typeof savedAttrsJson === 'string'
          ? JSON.parse(savedAttrsJson)
          : savedAttrsJson
        if (Array.isArray(parsed)) {
          parsed.forEach(a => {
            if (a && a.id != null) attrValues[a.id] = a.value_name ?? ''
          })
        }
      } catch { /* ignore */ }
    }

    hydrateFromHints()
  } catch {
    attrs.value = []
  } finally {
    attrsLoading.value = false
    emitUpdate()
  }
}

// ── Carregamento inicial ──────────────────────────────────────────────────────
async function loadSavedCategories() {
  if (!props.ownerType || !props.ownerId || !props.marketplace) return
  loadingSaved.value = true
  try {
    const { data } = await api.get(
      `/product-categories/${props.ownerType}/${props.ownerId}`,
      { params: { marketplace: props.marketplace } }
    )
    savedCategories.value = Array.isArray(data) ? data : []
  } catch {
    savedCategories.value = []
  } finally {
    loadingSaved.value = false
  }

  // Modo "edição": se há initialValue.category_id, procura match nas salvas;
  // se não achar, adiciona uma entry sintética (pmc_id null) — será criada
  // de fato em product_marketplace_categories ao salvar.
  if (props.initialValue?.category_id) {
    const match = savedCategories.value.find(
      c => String(c.category_id) === String(props.initialValue.category_id),
    )
    if (match) {
      selectedKey.value = `s:${match.id}`
      await selectSavedCategory(match)
    } else {
      const synthetic = {
        id: 0, // chave especial; pmc_id real só após persist
        category_id: String(props.initialValue.category_id),
        category_name: props.initialValue.category_name || String(props.initialValue.category_id),
        category_path_json: null,
        attributes_json: JSON.stringify(props.initialValue.attributes || []),
        _synthetic: true,
      }
      savedCategories.value = [synthetic, ...savedCategories.value]
      selectedKey.value = 's:0'
      current.pmc_id = null
      current.category_id = synthetic.category_id
      current.category_name = synthetic.category_name
      current.category_path_json = null
      current.isNew = false
      await loadCategoryAttrs(current.category_id, synthetic.attributes_json)
    }
    return
  }

  if (savedCategories.value.length) {
    const first = savedCategories.value[0]
    selectedKey.value = `s:${first.id}`
    await selectSavedCategory(first)
  } else {
    selectedKey.value = ''
    resetCurrent()
    emitUpdate()
  }
}

async function selectSavedCategory(cat) {
  // synthetic entries (id=0, vindas de initialValue sem match) ainda não existem
  // no servidor — tratam-se como "criar" ao salvar.
  current.pmc_id = cat._synthetic ? null : cat.id
  current.category_id = cat.category_id
  current.category_name = cat.category_name || cat.category_id
  current.category_path_json = cat.category_path_json || null
  current.isNew = false
  await loadCategoryAttrs(cat.category_id, cat.attributes_json)
  if (!currentPathItems.value.length) {
    fetchPathFromML(cat.category_id)
  }
}

function resetCurrent() {
  current.pmc_id = null
  current.category_id = ''
  current.category_name = ''
  current.category_path_json = null
  current.isNew = false
  attrs.value = []
  clearAttrValues()
}

function onDropdownChange() {
  if (selectedKey.value === 'new') {
    resetCurrent()
    current.isNew = true
    emitUpdate()
    catSearch.value = ''
    catResults.value = []
    return
  }
  const id = Number(selectedKey.value.slice(2))
  const cat = savedCategories.value.find(c => c.id === id)
  if (cat) selectSavedCategory(cat)
}

// ── Busca ML ──────────────────────────────────────────────────────────────────
function debouncedCatSearch() {
  clearTimeout(catDebounce)
  catDebounce = setTimeout(searchCategories, 400)
}

async function searchCategories() {
  const q = catSearch.value.trim()
  if (!q) { catResults.value = []; return }
  catSearching.value = true
  try {
    const { data } = await api.get('/anuncios/categories/search', { params: { q } })
    catResults.value = Array.isArray(data) ? data : []
  } catch {
    catResults.value = []
  } finally {
    catSearching.value = false
  }
}

function pickNewCategory(cat) {
  current.pmc_id = null
  current.category_id = cat.id
  current.category_name = cat.name
  current.category_path_json = cat.path_from_root
    ? JSON.stringify(cat.path_from_root)
    : null
  current.isNew = true
  catResults.value = []
  catSearch.value  = ''
  loadCategoryAttrs(cat.id)
}

function clearNew() {
  catResults.value = []
  catSearch.value  = ''
  current.pmc_id = null
  current.category_id = ''
  current.category_name = ''
  current.category_path_json = null
  current.isNew = true   // mantém modo "nova" para mostrar o input de busca
  attrs.value = []
  clearAttrValues()
  emitUpdate()
}

// ── Reatividade a mudança de produto/marketplace ──────────────────────────────
watch(
  () => [props.ownerType, props.ownerId, props.marketplace],
  () => { loadSavedCategories() },
)

onMounted(() => {
  loadSavedCategories()
})

defineExpose({
  reload: loadSavedCategories,
  hasRequiredUnfilled: () => requiredUnfilledCount.value > 0,
})
</script>
