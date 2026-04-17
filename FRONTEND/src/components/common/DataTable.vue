<template>
  <div>
    <div class="table-responsive">
      <table class="table table-sm table-hover">
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key" :style="col.style || ''">
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td :colspan="columns.length" class="text-center py-4">
              <i class="fas fa-spinner fa-spin"></i>
            </td>
          </tr>
          <tr v-else-if="!rows.length">
            <td :colspan="columns.length" class="text-center text-muted py-4">
              {{ emptyText }}
            </td>
          </tr>
          <tr v-for="(row, i) in rows" :key="row.id ?? i" @click="$emit('row-click', row)" :class="{ 'cursor-pointer': clickable }">
            <td v-for="col in columns" :key="col.key">
              <slot :name="`cell-${col.key}`" :row="row" :value="row[col.key]">
                {{ row[col.key] ?? '—' }}
              </slot>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="total > pageSize" class="d-flex justify-content-between align-items-center px-3 pb-2">
      <small class="text-muted">{{ total }} registros — página {{ page }} de {{ totalPages }}</small>
      <nav>
        <ul class="pagination pagination-sm mb-0">
          <li class="page-item" :class="{ disabled: page <= 1 }">
            <button class="page-link" @click="$emit('page-change', page - 1)">&laquo;</button>
          </li>
          <li
            v-for="p in visiblePages"
            :key="p"
            class="page-item"
            :class="{ active: p === page }"
          >
            <button class="page-link" @click="$emit('page-change', p)">{{ p }}</button>
          </li>
          <li class="page-item" :class="{ disabled: page >= totalPages }">
            <button class="page-link" @click="$emit('page-change', page + 1)">&raquo;</button>
          </li>
        </ul>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  columns: { type: Array, required: true },   // [{ key, label, style? }]
  rows:    { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  total:   { type: Number, default: 0 },
  page:    { type: Number, default: 1 },
  pageSize:{ type: Number, default: 20 },
  emptyText: { type: String, default: 'Nenhum registro encontrado' },
  clickable: { type: Boolean, default: false },
})

defineEmits(['row-click', 'page-change'])

const totalPages = computed(() => Math.ceil(props.total / props.pageSize) || 1)

const visiblePages = computed(() => {
  const range = []
  const start = Math.max(1, props.page - 2)
  const end   = Math.min(totalPages.value, props.page + 2)
  for (let i = start; i <= end; i++) range.push(i)
  return range
})
</script>
