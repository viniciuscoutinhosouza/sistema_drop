<template>
  <div :class="`small-box bg-${color}`">
    <div class="inner">
      <h3>{{ formattedValue }}</h3>
      <p>{{ title }}</p>
      <div v-if="change !== null" class="mt-1">
        <i :class="change >= 0 ? 'fas fa-arrow-up' : 'fas fa-arrow-down'"></i>
        <span class="ml-1">{{ Math.abs(change).toFixed(1) }}% vs mês anterior</span>
      </div>
    </div>
    <div class="icon">
      <i :class="icon"></i>
    </div>
    <component :is="linkTo ? 'RouterLink' : 'div'" :to="linkTo" class="small-box-footer">
      {{ subtitle }}
      <i v-if="linkTo" class="fas fa-arrow-circle-right"></i>
    </component>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatCurrency } from '@/utils/formatters'

const props = defineProps({
  title: { type: String, required: true },
  value: { type: [Number, String], required: true },
  icon: { type: String, default: 'fas fa-chart-bar' },
  color: { type: String, default: 'info' },
  subtitle: { type: String, default: '' },
  linkTo: { type: String, default: null },
  isCurrency: { type: Boolean, default: false },
  change: { type: Number, default: null },
})

const formattedValue = computed(() => {
  if (props.isCurrency) return formatCurrency(props.value)
  return props.value
})
</script>
