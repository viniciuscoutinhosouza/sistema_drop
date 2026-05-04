<template>
  <div class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-boxes mr-2"></i>Atualizar Estoque</h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <div v-if="!result">
            <p class="text-muted small">
              Os itens desta entrada serão somados ao estoque dos produtos CMIG correspondentes.
              O sistema faz match por <strong>EAN</strong>; itens sem EAN ou sem produto cadastrado
              serão ignorados.
            </p>
            <div class="alert alert-info small">
              <i class="fas fa-info-circle mr-1"></i>
              {{ invoice.items?.length || 0 }} {{ invoice.items?.length === 1 ? 'item' : 'itens' }} nesta NFe.
              Esta ação é <strong>idempotente</strong> — não pode ser reaplicada.
            </div>
          </div>
          <div v-else class="alert alert-success small">
            <i class="fas fa-check-circle mr-1"></i><strong>Estoque atualizado!</strong>
            <p class="mb-0 mt-1">
              {{ result.matched }} produto(s) tiveram estoque atualizado.<br>
              {{ result.unmatched }} item(ns) sem match (sem EAN ou produto não cadastrado).
            </p>
          </div>

          <div v-if="error" class="alert alert-danger small">{{ error }}</div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">{{ result ? 'Fechar' : 'Cancelar' }}</button>
          <button v-if="!result" class="btn btn-primary" :disabled="submitting" @click="submit">
            <i class="fas" :class="submitting ? 'fa-spinner fa-spin' : 'fa-check'"></i>
            {{ submitting ? 'Atualizando...' : 'Confirmar Atualização' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useFiscalStore } from '@/stores/fiscal'

const props = defineProps({
  invoice: { type: Object, required: true },
})
const emit = defineEmits(['close', 'updated'])
const fiscalStore = useFiscalStore()

const submitting = ref(false)
const error = ref('')
const result = ref(null)

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    result.value = await fiscalStore.updateStock(props.invoice.id)
    emit('updated', result.value)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao atualizar estoque'
  } finally {
    submitting.value = false
  }
}
</script>
