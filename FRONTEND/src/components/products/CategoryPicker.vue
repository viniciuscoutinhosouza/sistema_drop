<template>
  <div>
    <select
      :value="modelValue"
      class="form-control"
      :class="{ 'is-invalid': !modelValue && required }"
      @change="$emit('update:modelValue', Number($event.target.value) || null)"
    >
      <option :value="null">-- Selecione uma categoria --</option>
      <optgroup v-for="group in grouped" :key="group.label" :label="group.label">
        <option v-for="cat in group.items" :key="cat.id" :value="cat.id">
          {{ cat.name }}
        </option>
      </optgroup>
    </select>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'

const props = defineProps({
  modelValue: { type: Number, default: null },
  required:   { type: Boolean, default: false },
})

defineEmits(['update:modelValue'])

const categories = ref([])

onMounted(async () => {
  try {
    const { data } = await api.get('/catalog/categories')
    categories.value = data
  } catch {
    // silently fail — field remains empty
  }
})

const grouped = computed(() => {
  const parents = categories.value.filter(c => !c.parent_id)
  return parents.map(p => ({
    label: p.name,
    items: categories.value.filter(c => c.parent_id === p.id),
  })).filter(g => g.items.length)
    .concat(
      categories.value.filter(c => !c.parent_id).map(p => ({
        label: '',
        items: [p],
      })).filter(g => !categories.value.some(c => c.parent_id === g.items[0].id))
    )
})
</script>
