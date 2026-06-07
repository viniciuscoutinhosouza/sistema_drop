<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0"><i class="fas fa-shipping-fast mr-2 text-primary"></i>Gaiolas — Entrega à Transportadora</h5>
      <RouterLink to="/separacao" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-arrow-left mr-1"></i> Voltar à Separação
      </RouterLink>
    </div>

    <ul class="nav nav-tabs mb-2">
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'separated' }" href="#" @click.prevent="setTab('separated')">Aguardando coleta</a></li>
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'open' }" href="#" @click.prevent="setTab('open')">Em separação</a></li>
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'delivered' }" href="#" @click.prevent="setTab('delivered')">Entregues</a></li>
    </ul>

    <div class="card">
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>
        <table v-else class="table table-hover table-sm mb-0">
          <thead class="thead-light">
            <tr>
              <th>Gaiola</th><th>Modo</th><th>Pedidos</th><th>Status</th>
              <th>Criada</th><th>Concluída</th><th>Entregue</th><th class="text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!carts.length"><td colspan="8" class="text-center text-muted py-4">Nenhuma gaiola.</td></tr>
            <tr v-for="c in carts" :key="c.id">
              <td class="font-weight-bold">{{ c.cart_number }}</td>
              <td><span class="badge badge-light text-capitalize">{{ c.mode }}</span></td>
              <td>{{ c.order_count }}</td>
              <td><span :class="badge(c.status)">{{ statusLabel(c.status) }}</span></td>
              <td class="small text-nowrap text-muted">{{ fmt(c.created_at) }}</td>
              <td class="small text-nowrap text-muted">{{ fmt(c.separated_at) }}</td>
              <td class="small text-nowrap text-muted">{{ fmt(c.delivered_at) }}</td>
              <td class="text-right text-nowrap">
                <RouterLink v-if="c.status === 'open'" to="/separacao" class="btn btn-xs btn-outline-primary">Abrir</RouterLink>
                <button v-if="c.status === 'separated'" class="btn btn-xs btn-success" @click="askDeliver(c)">
                  <i class="fas fa-truck mr-1"></i> Entregar à transportadora
                </button>
                <span v-if="c.carrier_name" class="text-muted small ml-1">{{ c.carrier_name }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal entrega -->
    <div v-if="deliverModal.show" class="modal-backdrop-custom" @click.self="deliverModal.show = false">
      <div class="card shadow" style="width:420px">
        <div class="card-header"><strong>Entregar {{ deliverModal.cart?.cart_number }}</strong></div>
        <div class="card-body">
          <p class="small text-muted">Confirma a coleta pela transportadora? Os {{ deliverModal.cart?.order_count }} pedidos serão marcados como <strong>enviados</strong> e o estoque será baixado.</p>
          <div class="form-group">
            <label class="small">Transportadora (opcional)</label>
            <input v-model="deliverModal.carrier" class="form-control form-control-sm" placeholder="Ex: Correios, Jadlog..." />
          </div>
        </div>
        <div class="card-footer text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="deliverModal.show = false">Cancelar</button>
          <button class="btn btn-sm btn-success" @click="confirmDeliver"><i class="fas fa-truck mr-1"></i> Confirmar entrega</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const carts = ref([])
const loading = ref(false)
const tab = ref('separated')
const deliverModal = reactive({ show: false, cart: null, carrier: '' })

onMounted(load)

function setTab(t) { tab.value = t; load() }

async function load() {
  loading.value = true
  try { const { data } = await api.get('/separation/carts', { params: { status: tab.value } }); carts.value = data.carts || [] }
  catch { carts.value = [] } finally { loading.value = false }
}

function askDeliver(c) { deliverModal.cart = c; deliverModal.carrier = ''; deliverModal.show = true }

async function confirmDeliver() {
  try {
    await api.post(`/separation/carts/${deliverModal.cart.id}/deliver`, { carrier_name: deliverModal.carrier })
    toast.success('Gaiola entregue à transportadora')
    deliverModal.show = false
    await load()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao entregar') }
}

function statusLabel(s) { return { open: 'Em separação', separated: 'Aguardando coleta', delivered: 'Entregue', cancelled: 'Cancelada' }[s] || s }
function badge(s) { return { open: 'badge badge-secondary', separated: 'badge badge-warning', delivered: 'badge badge-success', cancelled: 'badge badge-danger' }[s] || 'badge badge-light' }
function fmt(dt) { return dt ? new Date(dt).toLocaleString('pt-BR') : '—' }
</script>

<style scoped>
.modal-backdrop-custom {
  position: fixed; inset: 0; background: rgba(0,0,0,.5);
  display: flex; align-items: center; justify-content: center; z-index: 1050;
}
</style>
