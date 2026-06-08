<template>
  <div v-if="show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)" @click.self="$emit('close')">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-box-open mr-2"></i> Separação e Coleta
          </h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <div v-if="!info" class="text-center text-muted py-3"><i class="fas fa-spinner fa-spin"></i></div>
          <template v-else>
            <!-- Separação -->
            <h6 class="text-primary"><i class="fas fa-box-open mr-1"></i> Pedido Separado</h6>
            <div v-if="info.separated && info.separated.at" class="row">
              <div class="col-6 mb-2"><small class="text-muted d-block">Data/Hora</small><strong>{{ fmt(info.separated.at) }}</strong></div>
              <div class="col-6 mb-2"><small class="text-muted d-block">Usuário</small><strong>{{ info.separated.by_name || '—' }}</strong></div>
              <template v-if="info.has_gaiola">
                <div class="col-6 mb-2"><small class="text-muted d-block">Modo de Separação</small><strong>{{ modeLabel(info.separated.mode) }}</strong></div>
                <div class="col-6 mb-2"><small class="text-muted d-block">Gaiola</small><strong>{{ info.separated.cart_number || '—' }}</strong></div>
                <div class="col-6 mb-2"><small class="text-muted d-block">Status da Gaiola</small>
                  <span class="badge" :class="cartBadge(info.separated.cart_status)">{{ cartStatusLabel(info.separated.cart_status) }}</span>
                </div>
              </template>
              <div v-else class="col-12"><small class="text-warning"><i class="fas fa-info-circle mr-1"></i>Separado fora de gaiola (sem detalhes de gaiola)</small></div>
            </div>
            <p v-else class="text-muted small mb-0">Pedido ainda não separado.</p>

            <hr />

            <!-- Coleta -->
            <h6 class="text-primary"><i class="fas fa-truck mr-1"></i> Pedido Coletado</h6>
            <div v-if="info.dispatched && info.dispatched.at" class="row">
              <div class="col-6 mb-2"><small class="text-muted d-block">Data/Hora</small><strong>{{ fmt(info.dispatched.at) }}</strong></div>
              <div class="col-6 mb-2"><small class="text-muted d-block">Entregue por</small><strong>{{ info.dispatched.by_name || '—' }}</strong></div>
              <div class="col-6 mb-2"><small class="text-muted d-block">Gaiola</small><strong>{{ info.dispatched.cart_number || '—' }}</strong></div>
            </div>
            <p v-else class="text-muted small mb-0">Pedido ainda não coletado pela transportadora.</p>
          </template>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  show: { type: Boolean, default: false },
  info: { type: Object, default: null },
})
defineEmits(['close'])

function fmt(dt) { return dt ? new Date(dt).toLocaleString('pt-BR') : '—' }
function modeLabel(m) { return { manual: 'Manual', scan: 'Bipagem' }[m] || (m || '—') }
function cartStatusLabel(s) {
  return { open: 'Em separação', separated: 'Concluída (pronta p/ transportadora)', delivered: 'Entregue', cancelled: 'Cancelada' }[s] || (s || '—')
}
function cartBadge(s) {
  return { open: 'badge-secondary', separated: 'badge-warning text-dark', delivered: 'badge-success', cancelled: 'badge-danger' }[s] || 'badge-light'
}
</script>
