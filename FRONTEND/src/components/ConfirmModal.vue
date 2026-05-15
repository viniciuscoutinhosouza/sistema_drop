<template>
  <teleport to="body">
    <div v-if="show" class="modal fade show d-block" tabindex="-1" role="dialog" style="background:rgba(0,0,0,.5)" @click.self="$emit('cancel')">
      <div class="modal-dialog modal-dialog-centered" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ title }}</h5>
            <button type="button" class="close" aria-label="Fechar" @click="$emit('cancel')">
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body">
            <p class="mb-0" style="white-space:pre-line">{{ message }}</p>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="$emit('cancel')">Cancelar</button>
            <button type="button" :class="['btn', confirmClass]" @click="$emit('confirm')">{{ confirmLabel }}</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: 'Confirmar ação' },
  message: { type: String, default: 'Tem certeza?' },
  confirmLabel: { type: String, default: 'Confirmar' },
  confirmClass: { type: String, default: 'btn-danger' },
})
defineEmits(['confirm', 'cancel'])
</script>
