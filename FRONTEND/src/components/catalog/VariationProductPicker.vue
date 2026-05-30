<template>
  <div class="position-relative">
    <input
      ref="inputEl"
      v-model="query"
      type="text"
      class="form-control form-control-sm"
      :placeholder="placeholder"
      autocomplete="off"
      @focus="onFocus"
      @input="onInput"
      @blur="onBlur"
    />

    <Teleport to="body">
      <div
        v-if="open && (loading || results.length || (query && !loading))"
        class="card shadow"
        :style="floatStyle"
      >
        <div v-if="loading" class="p-2 small text-muted">
          <i class="fas fa-spinner fa-spin mr-1"></i>Buscando...
        </div>
        <button
          v-for="p in results"
          :key="p.id"
          type="button"
          class="dropdown-item py-2"
          style="white-space:normal"
          @mousedown.prevent="select(p)"
        >
          <div class="d-flex align-items-center" style="gap:8px">
            <img
              v-if="p._thumb"
              :src="p._thumb"
              style="width:36px;height:36px;object-fit:cover;border-radius:3px;flex-shrink:0"
            />
            <div class="flex-grow-1" style="min-width:0">
              <div style="font-size:12px;line-height:1.3">{{ p.title }}</div>
              <div class="text-muted" style="font-size:10px">
                SKU: {{ p._sku }} · Estoque: {{ p.stock_quantity ?? 0 }}
                <span v-if="p._price"> · {{ formatCurrency(p._price) }}</span>
              </div>
            </div>
          </div>
        </button>
        <div v-if="!loading && !results.length && query" class="p-2 small text-muted">
          Nenhum resultado para "{{ query }}"
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'

const props = defineProps({
  source: { type: String, required: true },
  accountCmigId: { type: [Number, String], default: null },
  modelValue: { type: Object, default: null },
  placeholder: { type: String, default: 'Buscar por título ou SKU...' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const inputEl = ref(null)
const query   = ref('')
const open    = ref(false)
const loading = ref(false)
const results = ref([])
const floatStyle = ref({})
let searchTimer = null

function recalcPosition() {
  if (!inputEl.value) return
  const r = inputEl.value.getBoundingClientRect()
  floatStyle.value = {
    position: 'fixed',
    top: `${r.bottom + 2}px`,
    left: `${r.left}px`,
    width: `${Math.max(r.width, 320)}px`,
    maxHeight: '320px',
    overflowY: 'auto',
    zIndex: 2000,
  }
}

function onFocus() {
  open.value = true
  nextTick(recalcPosition)
}

function onInput() {
  open.value = true
  recalcPosition()
  clearTimeout(searchTimer)
  searchTimer = setTimeout(search, 250)
}

function onBlur() {
  // Pequeno delay pra dar tempo do mousedown registrar a seleção
  setTimeout(() => { open.value = false }, 150)
}

function onScrollOrResize() {
  if (open.value) recalcPosition()
}

onMounted(() => {
  window.addEventListener('scroll', onScrollOrResize, true)
  window.addEventListener('resize', onScrollOrResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
})

async function search() {
  const q = query.value.trim()
  if (q.length < 2) { results.value = []; loading.value = false; return }
  loading.value = true
  try {
    if (props.source === 'pg') {
      const { data } = await api.get('/catalog', {
        params: { search: q, page: 1, page_size: 15 },
      })
      results.value = (data.items || []).map(p => ({
        ...p,
        _sku: p.sku,
        _thumb: p.image_url,
        _price: p.suggested_price || p.cost_price,
      }))
    } else {
      if (!props.accountCmigId) { results.value = []; return }
      const { data } = await api.get(`/cmigs/${props.accountCmigId}/products`, {
        params: { search: q, simple_only: true },
      })
      results.value = (Array.isArray(data) ? data : []).slice(0, 15).map(p => ({
        ...p,
        _sku: p.sku_cmig,
        _thumb: p.thumbnail,
        _price: p.suggested_price || p.cost_price,
      }))
    }
    nextTick(recalcPosition)
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

function select(p) {
  emit('update:modelValue', p)
  emit('select', p)
  query.value = ''
  results.value = []
  open.value = false
}

watch(() => props.source, () => {
  query.value = ''
  results.value = []
  open.value = false
})
</script>
