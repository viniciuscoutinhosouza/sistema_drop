<template>
  <teleport to="body">
    <!-- Backdrop -->
    <div
      v-if="modelValue"
      class="modal-backdrop fade show"
      style="z-index: 1050"
      @click="close"
    ></div>

    <!-- Modal -->
    <div
      v-if="modelValue"
      class="modal fade show"
      style="display: block; z-index: 1055"
      tabindex="-1"
      @click.self="close"
    >
      <div class="modal-dialog modal-lg modal-dialog-scrollable">
        <div class="modal-content">

          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-search mr-2 text-warning"></i>
              Buscar Categoria — Mercado Livre
            </h5>
            <button type="button" class="close" @click="close">
              <span>&times;</span>
            </button>
          </div>

          <div class="modal-body pb-2">

            <!-- Campo de busca -->
            <div class="input-group input-group-lg mb-3">
              <input
                ref="inputRef"
                v-model="query"
                type="text"
                class="form-control"
                placeholder="Ex: celular samsung, tênis esportivo, notebook gamer..."
                @input="onInput"
                @keydown.escape="close"
              />
              <div class="input-group-append">
                <span class="input-group-text" style="min-width: 48px; justify-content: center">
                  <i v-if="loading" class="fas fa-spinner fa-spin text-primary"></i>
                  <i v-else class="fas fa-search text-muted"></i>
                </span>
              </div>
            </div>

            <!-- Hint inicial -->
            <div v-if="!query" class="text-center text-muted py-5">
              <i class="fas fa-layer-group fa-3x mb-3 d-block text-secondary"></i>
              <p class="mb-1 font-weight-bold">Digite o nome do produto ou segmento</p>
              <small>A busca usa o motor do próprio Mercado Livre para sugerir categorias.<br/>Mín. 3 caracteres.</small>
            </div>

            <!-- Query muito curta -->
            <div v-else-if="query.length < 3" class="text-center text-muted py-4">
              <i class="fas fa-keyboard fa-2x mb-2 d-block text-secondary"></i>
              <small>
                Continue digitando...
                ({{ 3 - query.length }} caractere{{ 3 - query.length !== 1 ? 's' : '' }} restante{{ 3 - query.length !== 1 ? 's' : '' }})
              </small>
            </div>

            <!-- Loading -->
            <div v-else-if="loading && !results.length" class="text-center text-muted py-5">
              <i class="fas fa-spinner fa-spin fa-2x mb-2 d-block text-primary"></i>
              <small>Buscando categorias no Mercado Livre...</small>
            </div>

            <!-- Sem resultados -->
            <div v-else-if="!loading && searched && !results.length" class="text-center text-muted py-4">
              <i class="fas fa-search-minus fa-2x mb-2 d-block text-secondary"></i>
              <p class="mb-1">Nenhuma categoria encontrada para <strong>"{{ query }}"</strong>.</p>
              <small>Tente termos mais genéricos — ex: "sapato" em vez de "tênis corrida masculino".</small>
            </div>

            <!-- Lista de resultados -->
            <div v-if="results.length" class="list-group list-group-flush border rounded">
              <button
                v-for="cat in results"
                :key="cat.id"
                type="button"
                class="list-group-item list-group-item-action py-3 px-3"
                @click="select(cat)"
              >
                <div class="d-flex justify-content-between align-items-start">
                  <div style="min-width: 0; flex: 1">

                    <!-- Cadeia de pais (breadcrumb) -->
                    <div
                      v-if="cat.path_from_root && cat.path_from_root.length > 1"
                      class="text-muted mb-1"
                      style="font-size: 0.75rem; line-height: 1.3"
                    >
                      <span
                        v-for="(p, idx) in cat.path_from_root.slice(0, -1)"
                        :key="p.id"
                      >
                        <span class="text-secondary">{{ p.name }}</span>
                        <i class="fas fa-angle-right mx-1 text-muted" style="font-size:0.65rem"></i>
                      </span>
                    </div>

                    <!-- Nome do domínio (mais específico — destaque principal) -->
                    <div class="font-weight-bold text-dark" style="font-size: 0.95rem">
                      {{ cat.domain_name || cat.name }}
                    </div>

                    <!-- Categoria registrada (se diferente do domain_name) -->
                    <div
                      v-if="cat.name && cat.name !== cat.domain_name"
                      class="text-muted mt-1"
                      style="font-size: 0.8rem"
                    >
                      <i class="fas fa-folder-open mr-1"></i>
                      {{ cat.name }}
                    </div>

                  </div>

                  <!-- Badge com ID -->
                  <span
                    class="badge badge-warning ml-3 flex-shrink-0"
                    style="font-size: 0.8rem; padding: 5px 8px; align-self: center"
                  >
                    {{ cat.id }}
                  </span>
                </div>
              </button>
            </div>

          </div>

          <div class="modal-footer py-2">
            <small class="text-muted mr-auto">
              <i class="fas fa-info-circle mr-1"></i>
              Clique na linha desejada para preencher o campo automaticamente.
            </small>
            <button type="button" class="btn btn-sm btn-secondary" @click="close">Fechar</button>
          </div>

        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import api from '@/composables/useApi'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'select'])

const query    = ref('')
const results  = ref([])
const loading  = ref(false)
const searched = ref(false)
const inputRef = ref(null)

let debounceTimer = null

function close() {
  emit('update:modelValue', false)
}

function buildPathString(pathFromRoot) {
  if (!pathFromRoot || pathFromRoot.length === 0) return ''
  return pathFromRoot.map(p => p.name).join(' › ')
}

function select(cat) {
  const path = buildPathString(cat.path_from_root)
  emit('select', {
    id:           cat.id,
    name:         cat.domain_name || cat.name,
    category_name: cat.name,
    path:         path,
    path_from_root: cat.path_from_root || [],
  })
  close()
}

function onInput() {
  searched.value = false
  results.value  = []
  clearTimeout(debounceTimer)
  if (query.value.length < 3) return
  debounceTimer = setTimeout(doSearch, 400)
}

async function doSearch() {
  if (query.value.length < 3) return
  loading.value = true
  try {
    const { data } = await api.get('/anuncios/categories/search', {
      params: { q: query.value },
    })
    results.value  = Array.isArray(data) ? data : []
    searched.value = true
  } catch {
    results.value  = []
    searched.value = true
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, async (open) => {
  if (open) {
    query.value    = ''
    results.value  = []
    searched.value = false
    await nextTick()
    inputRef.value?.focus()
  } else {
    clearTimeout(debounceTimer)
  }
})
</script>
