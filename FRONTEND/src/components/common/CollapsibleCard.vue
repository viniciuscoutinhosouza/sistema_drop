<template>
  <div class="card card-outline" :class="borderClass">
    <div class="card-header py-2" role="button" @click="open = !open">
      <h3 class="card-title mb-0">
        <i v-if="icon" class="fas mr-2" :class="icon"></i>{{ title }}
      </h3>
      <div class="card-tools">
        <span v-if="badge" class="badge mr-2" :class="badgeClass">{{ badge }}</span>
        <button type="button" class="btn btn-tool">
          <i class="fas" :class="open ? 'fa-minus' : 'fa-plus'"></i>
        </button>
      </div>
    </div>
    <div v-show="open" class="card-body">
      <slot />
    </div>
  </div>
</template>

<script setup>
// Card recolhível reutilizável (AdminLTE-styled) sem depender do JS do AdminLTE.
// Usado para apresentar os grupos do XML da NF-e sem poluir a tela — recolhidos por padrão.
import { ref } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  icon: { type: String, default: '' },
  color: { type: String, default: 'primary' },   // borda/badge: primary|info|secondary|success…
  badge: { type: [String, Number], default: '' },
  badgeClass: { type: String, default: 'badge-light' },
  defaultOpen: { type: Boolean, default: false },
})

const open = ref(props.defaultOpen)
const borderClass = `card-${props.color}`
</script>
