<template>
  <span class="d-inline-flex align-items-center" style="gap:.25rem">
    <template v-if="order.eship_order_id">
      <span class="badge badge-info" title="Pedido no eShip">
        <i class="fas fa-dolly-flatbed mr-1"></i>eShip
      </span>
      <button class="btn btn-xs btn-outline-info" :disabled="busy"
              title="Sincronizar status com o eShip" @click="sync">
        <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
      </button>
    </template>
    <button v-else class="btn btn-xs btn-outline-secondary" :disabled="busy"
            title="Enviar pedido ao eShip" @click="push">
      <i class="fas mr-1" :class="busy ? 'fa-spinner fa-spin' : 'fa-dolly-flatbed'"></i>eShip
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

async function push() {
  busy.value = true
  try {
    await api.post(`/integrations/eship/orders/${props.order.id}/push`)
    toast.success('Pedido enviado ao eShip')
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
