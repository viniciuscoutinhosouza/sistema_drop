<template>
  <div class="table-responsive metrics-matrix">
    <table class="table table-sm mb-0">
      <thead>
        <tr>
          <th class="metric-name">Métrica</th>
          <th v-for="w in windows" :key="w" class="text-end">
            {{ windowLabels[w] }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(meta, key) in rowMeta" :key="key" :class="{ 'ml-only-row': meta.ml_only }">
          <td class="metric-name">
            <i :class="iconFor(key)" class="mr-2 text-muted"></i>
            {{ meta.label }}
            <span v-if="meta.ml_only" class="badge badge-ml ml-1">ML</span>
          </td>
          <td
            v-for="w in windows"
            :key="w"
            class="text-end value-cell"
            :class="deltaClass(key, w)"
          >
            <span>{{ fmt(rows[key]?.[w], meta.type) }}</span>
            <i v-if="deltaIcon(key, w)" :class="deltaIcon(key, w)" class="delta-arrow ml-1"></i>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { formatCurrency } from '@/utils/formatters'

const props = defineProps({
  windows: { type: Array, default: () => [] },
  windowLabels: { type: Object, default: () => ({}) },
  rowMeta: { type: Object, default: () => ({}) },
  rows: { type: Object, default: () => ({}) },
})

const ICONS = {
  qtd_pedidos: 'fas fa-shopping-cart',
  cancelados: 'fas fa-times-circle',
  full: 'fas fa-warehouse',
  flex: 'fas fa-bolt',
  outros: 'fas fa-truck',
  faturamento: 'fas fa-dollar-sign',
  fat_full: 'fas fa-warehouse',
  fat_flex: 'fas fa-bolt',
  visitas: 'fas fa-eye',
  conversao: 'fas fa-percent',
  perguntas: 'fas fa-question-circle',
  ads_cost: 'fas fa-bullhorn',
}

// Linhas em que "menos é melhor" (queda = verde).
const LOWER_IS_BETTER = new Set(['cancelados', 'ads_cost'])

function iconFor(key) {
  return ICONS[key] || 'fas fa-circle'
}

function fmt(value, type) {
  const v = Number(value || 0)
  if (type === 'money') return formatCurrency(v)
  if (type === 'pct') return v.toFixed(2).replace('.', ',') + '%'
  return new Intl.NumberFormat('pt-BR').format(v)
}

// Comparações: 7d vs 7d antes, e mes vs mes_anterior.
const COMPARE = { '7d': '7d_antes', mes: 'mes_anterior' }

function delta(key, w) {
  const prevKey = COMPARE[w]
  if (!prevKey) return null
  const cur = Number(props.rows[key]?.[w] || 0)
  const prev = Number(props.rows[key]?.[prevKey] || 0)
  if (prev === 0 && cur === 0) return 0
  if (prev === 0) return 100
  return ((cur - prev) / prev) * 100
}

function deltaClass(key, w) {
  const d = delta(key, w)
  if (d === null || d === 0) return ''
  const better = LOWER_IS_BETTER.has(key) ? d < 0 : d > 0
  return better ? 'cell-up' : 'cell-down'
}

function deltaIcon(key, w) {
  const d = delta(key, w)
  if (d === null || d === 0) return ''
  return d > 0 ? 'fas fa-arrow-up' : 'fas fa-arrow-down'
}
</script>

<style scoped>
.metrics-matrix table {
  font-size: 13px;
}
.metrics-matrix thead th {
  background: #f4f6f9;
  border-bottom: 2px solid #dee2e6;
  font-weight: 600;
  white-space: nowrap;
}
.metric-name {
  font-weight: 600;
  white-space: nowrap;
}
.value-cell {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.cell-up {
  color: #28a745;
  background: rgba(40, 167, 69, 0.06);
}
.cell-down {
  color: #dc3545;
  background: rgba(220, 53, 69, 0.06);
}
.delta-arrow {
  font-size: 10px;
}
.ml-only-row {
  background: rgba(255, 193, 7, 0.04);
}
.badge-ml {
  background: #fff159;
  color: #2d3277;
  font-size: 9px;
  vertical-align: middle;
}
</style>
