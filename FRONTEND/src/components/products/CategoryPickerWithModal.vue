<template>
  <div>
    <div class="input-group">
      <select :value="modelValue ?? ''"
              class="form-control"
              @change="$emit('update:modelValue', $event.target.value ? Number($event.target.value) : null)">
        <option value="">— Selecione uma categoria —</option>
        <option v-for="cat in flat" :key="cat.id" :value="cat.id">
          {{ cat.parent_id ? '    └ ' + cat.name : cat.name }}
        </option>
      </select>
      <div class="input-group-append">
        <button type="button" class="btn btn-outline-secondary" @click="modal=true" title="Gerenciar categorias">
          <i class="fas fa-pen"></i>
        </button>
      </div>
    </div>

    <CategoryCrudModal
      :visible="modal"
      @close="modal=false"
      @select="onSelect"
      @changed="loadCategories"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import CategoryCrudModal from './CategoryCrudModal.vue'

defineProps({
  modelValue: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue'])

const categories = ref([])
const modal      = ref(false)

async function loadCategories() {
  try {
    const { data } = await api.get('/catalog/categories')
    categories.value = data
  } catch {
    categories.value = []
  }
}

const flat = computed(() => {
  const byName = (a, b) => a.name.localeCompare(b.name, 'pt-BR')
  const parents  = categories.value.filter(c => !c.parent_id).slice().sort(byName)
  const orphans  = categories.value.filter(c => c.parent_id && !parents.some(p => p.id === c.parent_id))
  const result   = []
  for (const p of parents) {
    result.push(p)
    const children = categories.value.filter(c => c.parent_id === p.id).slice().sort(byName)
    result.push(...children)
  }
  result.push(...orphans.slice().sort(byName))
  return result
})

function onSelect(cat) {
  emit('update:modelValue', cat.id)
  modal.value = false
}

onMounted(loadCategories)
</script>
