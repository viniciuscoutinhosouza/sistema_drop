<template>
  <div class="form-group">
    <label class="d-flex align-items-center mb-1">
      <span>{{ label }}</span>
      <button
        type="button"
        class="btn btn-sm btn-outline-success ml-auto"
        title="Abrir o assistente de IA para escrever a descrição"
        @click="showAi = true"
      >
        <i class="fas fa-robot mr-1"></i>Gerar por IA
      </button>
    </label>

    <textarea
      :value="modelValue"
      class="form-control w-100"
      rows="10"
      :placeholder="placeholder"
      @input="$emit('update:modelValue', $event.target.value)"
    ></textarea>

    <AiDescriptionModal
      :visible="showAi"
      :product-type="productType"
      :product-id="productId"
      :components="components"
      @close="showAi = false"
      @apply="aplicar"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AiDescriptionModal from '@/components/products/AiDescriptionModal.vue'

defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, default: 'Descrição' },
  placeholder: { type: String, default: 'Descrição do produto…' },
  productType: { type: String, default: null },   // 'cmig' | 'pg'
  productId: { type: [Number, String], default: null },
  components: { type: Array, default: () => [] }, // só nos KITs (p/ copiar a descrição de cada um)
})
const emit = defineEmits(['update:modelValue'])

const showAi = ref(false)

// "Pronto" no modal → substitui a descrição do produto.
function aplicar(texto) {
  emit('update:modelValue', texto)
}
</script>
