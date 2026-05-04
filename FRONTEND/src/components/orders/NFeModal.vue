<template>
  <div
    v-if="show"
    class="modal fade show d-block"
    tabindex="-1"
    style="background:rgba(0,0,0,.5)"
    @click.self="$emit('close')"
  >
    <div class="modal-dialog modal-md">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-file-invoice mr-2 text-success"></i>
            Nota Fiscal — Venda #{{ order?.platform_order_id || order?.id }}
          </h5>
          <button type="button" class="close" @click="$emit('close')">
            <span>&times;</span>
          </button>
        </div>
        <div class="modal-body text-center py-4">
          <i class="fas fa-check-circle fa-3x text-success mb-3"></i>
          <h5 class="mb-1">NF-e Autorizada</h5>
          <p class="text-muted mb-3">A DANFE será aberta no site do Mercado Livre.</p>
          <a
            v-if="order?.nfe_url"
            :href="order.nfe_url"
            target="_blank"
            rel="noopener"
            class="btn btn-success btn-lg"
            @click="$emit('close')"
          >
            <i class="fas fa-print mr-2"></i>Abrir / Imprimir DANFE
          </a>
          <div v-if="order?.nfe_key" class="mt-4">
            <small class="text-muted d-block">Chave de acesso</small>
            <code class="small">{{ order.nfe_key }}</code>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-default" @click="$emit('close')">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  show: { type: Boolean, default: false },
  order: { type: Object, default: null },
})

defineEmits(['close'])
</script>
