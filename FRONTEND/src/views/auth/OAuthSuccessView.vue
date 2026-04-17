<template>
  <div class="d-flex align-items-center justify-content-center" style="height:100vh">
    <div class="text-center">
      <i class="fas fa-check-circle fa-4x text-success mb-3"></i>
      <h4>Integração realizada com sucesso!</h4>
      <p>Esta janela será fechada automaticamente...</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

onMounted(() => {
  const platform = route.query.platform || 'unknown'
  const status = route.query.status || 'connected'

  if (window.opener) {
    window.opener.postMessage({ platform, status }, window.location.origin)
    setTimeout(() => window.close(), 1500)
  }
})
</script>
