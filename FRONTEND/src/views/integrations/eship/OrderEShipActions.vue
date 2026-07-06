<template>
  <span class="d-inline-flex align-items-center" style="gap:.25rem">
    <template v-if="order.eship_order_id">
      <span class="badge badge-info" title="Pedido no eShip">
        <i class="fas fa-dolly-flatbed mr-1"></i>eShip
      </span>
      <span class="badge" :class="order.eship_nfe_attached ? 'badge-success' : 'badge-light'"
            :title="order.eship_nfe_attached ? 'NF-e anexada à Ordem' : 'NF-e ainda não anexada'">NF-e</span>
      <span class="badge" :class="order.eship_label_attached ? 'badge-success' : 'badge-light'"
            :title="order.eship_label_attached ? 'Etiqueta anexada à Ordem' : 'Etiqueta ainda não anexada'">Etiq</span>
      <button v-if="!order.eship_nfe_attached || !order.eship_label_attached"
              class="btn btn-xs btn-outline-warning" :disabled="busy"
              title="Reenviar — completar os anexos pendentes" @click="send">
        <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-redo'"></i>
      </button>
      <button class="btn btn-xs btn-outline-info" :disabled="busy"
              title="Sincronizar status com o eShip" @click="sync">
        <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
      </button>
    </template>
    <button v-else class="btn btn-xs btn-outline-secondary" :disabled="busy"
            title="Enviar ao eShip (Ordem + NF-e + Etiqueta)" @click="send">
      <i class="fas mr-1" :class="busy ? 'fa-spinner fa-spin' : 'fa-dolly-flatbed'"></i>Enviar ao eShip
    </button>
  </span>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({ order: { type: Object, required: true } })
const emit = defineEmits(['updated'])
const toast = useToast()
const busy = ref(false)

async function send() {
  busy.value = true
  try {
    const { data } = await api.post(`/integrations/eship/orders/${props.order.id}/send`)
    const erros = data.erros || []
    if (!erros.length) {
      toast.success('Enviado ao eShip: Ordem + NF-e + Etiqueta')
    } else {
      const feito = []
      if (data.eship_order_id) feito.push('Ordem')
      if (data.nfe_attached) feito.push('NF-e')
      if (data.label_attached) feito.push('Etiqueta')
      const pend = erros.map((e) => e.erro).join(' · ')
      toast.warning((feito.length ? `Enviado: ${feito.join(' + ')}. ` : '') + `Pendente: ${pend}`)
    }
    emit('updated')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar ao eShip')
  } finally {
    busy.value = false
  }
}

async function sync() {
  busy.value = true
  try {
    const { data } = await api.post(`/integrations/eship/orders/${props.order.id}/sync`)
    toast.success(data.changed ? 'Status atualizado pelo eShip' : 'Sem mudança de status')
    if (data.changed) emit('updated')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar com eShip')
  } finally {
    busy.value = false
  }
}
</script>
