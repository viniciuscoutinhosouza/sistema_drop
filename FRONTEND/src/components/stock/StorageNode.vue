<template>
  <div class="storage-node">
    <div class="node-row d-flex align-items-center" :class="{ selected: selectedId === node.id }"
         :style="{ paddingLeft: (depth * 16 + 4) + 'px' }">
      <span class="toggle mr-1" @click="expanded = !expanded" v-if="node.children && node.children.length">
        <i class="fas" :class="expanded ? 'fa-caret-down' : 'fa-caret-right'"></i>
      </span>
      <span class="toggle mr-1" v-else>&nbsp;</span>
      <span class="flex-grow-1 node-label" @click="$emit('select', node)">
        <span class="text-muted small">{{ node.level_type }}</span>
        <strong class="ml-1">{{ node.code }}</strong>
        <i v-if="node.is_storable" class="fas fa-box text-success ml-1" title="Armazenável"></i>
        <span v-if="node.area_kind" class="badge badge-light ml-1">{{ areaLabel }}</span>
      </span>
      <span class="actions text-nowrap">
        <button v-if="canConfig" class="btn btn-xs btn-link p-0 mr-1" title="Novo sub-endereço" @click="$emit('add', node)"><i class="fas fa-plus"></i></button>
        <button v-if="canConfig" class="btn btn-xs btn-link p-0 mr-1" title="Gerar em massa" @click="$emit('bulk', node)"><i class="fas fa-layer-group"></i></button>
        <button v-if="canConfig" class="btn btn-xs btn-link p-0 mr-1" title="Editar" @click="$emit('edit', node)"><i class="fas fa-edit"></i></button>
        <button class="btn btn-xs btn-link p-0 mr-1" title="Etiqueta de endereço" @click="$emit('label', node)"><i class="fas fa-tag"></i></button>
        <button v-if="canConfig" class="btn btn-xs btn-link text-danger p-0" title="Excluir" @click="$emit('remove', node)"><i class="fas fa-trash"></i></button>
      </span>
    </div>
    <template v-if="expanded && node.children">
      <StorageNode v-for="c in node.children" :key="c.id" :node="c" :depth="depth + 1"
        :can-config="canConfig" :selected-id="selectedId"
        @select="$emit('select', $event)" @add="$emit('add', $event)" @bulk="$emit('bulk', $event)"
        @edit="$emit('edit', $event)" @remove="$emit('remove', $event)" @label="$emit('label', $event)" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  canConfig: { type: Boolean, default: false },
  selectedId: { type: [Number, null], default: null },
})
defineEmits(['select', 'add', 'bulk', 'edit', 'remove', 'label'])

const expanded = ref(true)
const areaLabel = computed(() => ({ pallet: 'Porta-pallet', cabinet: 'Armários', other: 'Área' }[props.node.area_kind] || ''))
</script>

<style scoped>
.node-row { padding: 2px 4px; border-radius: 3px; }
.node-row:hover { background: #f4f6f9; }
.node-row.selected { background: #e8f0fe; }
.node-label { cursor: pointer; }
.toggle { cursor: pointer; width: 12px; display: inline-block; }
.btn-xs { font-size: .75rem; }
</style>
