<template>
  <div class="d-flex align-items-center justify-content-center" style="height:100vh">
    <div class="text-center" style="max-width:520px">
      <template v-if="isError">
        <i class="fas fa-exclamation-triangle fa-4x text-danger mb-3"></i>
        <h4>Não foi possível conectar a conta</h4>
        <p class="text-muted">{{ detail || 'A conta autorizada não corresponde à conta selecionada.' }}</p>
        <p class="small text-muted">Feche esta janela e tente novamente.</p>
      </template>
      <template v-else>
        <i class="fas fa-check-circle fa-4x text-success mb-3"></i>
        <h4>Integração realizada com sucesso!</h4>
        <p v-if="seller" class="text-muted">Conta conectada: <strong>{{ seller }}</strong></p>
        <p>Esta janela será fechada automaticamente...</p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const status = computed(() => route.query.status || 'connected')
const isError = computed(() => status.value !== 'connected')
const detail = computed(() => route.query.detail || '')
const seller = computed(() => route.query.seller || '')

onMounted(() => {
  const platform = route.query.platform || 'unknown'

  if (window.opener) {
    window.opener.postMessage(
      { platform, status: status.value, detail: detail.value, seller: seller.value },
      window.location.origin
    )
    // Mantém a janela aberta mais tempo em caso de erro para o usuário ler a mensagem.
    setTimeout(() => window.close(), isError.value ? 8000 : 1500)
  }
})
</script>
