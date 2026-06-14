<template>
  <div class="clip-overlay" @click.self="$emit('close')">
    <div class="clip-modal card">
      <div class="card-header py-2 d-flex align-items-center">
        <strong><i class="fas fa-film mr-2"></i>Visualizar clip</strong>
        <button class="btn btn-sm btn-light ml-auto" @click="$emit('close')"><i class="fas fa-times"></i></button>
      </div>
      <div class="card-body text-center">
        <video :src="url" controls autoplay muted playsinline
          style="max-width:100%;max-height:65vh;background:#000;border-radius:6px"></video>
        <p v-if="prompt" class="text-muted small mt-2 mb-0 text-left">{{ prompt }}</p>
      </div>
      <div class="card-footer d-flex" style="gap:8px">
        <a :href="url" download class="btn btn-sm btn-outline-primary">
          <i class="fas fa-download mr-1"></i>Baixar
        </a>
        <button class="btn btn-sm btn-outline-secondary ml-auto" @click="$emit('close')">Fechar</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  url: { type: String, required: true },
  prompt: { type: String, default: '' },
})
defineEmits(['close'])
</script>

<style scoped>
.clip-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1085;
}
.clip-modal { width: 560px; max-width: 95vw; margin: 0; }
</style>
