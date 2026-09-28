<template>
  <div class="content-wrapper-inner p-3">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title"><i class="fas fa-barcode mr-2"></i>Rastreabilidade</h3>
      </div>
      <div class="card-body">
        <ul class="nav nav-tabs mb-3">
          <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'expiring' }" href="#" @click.prevent="tab = 'expiring'">A vencer</a></li>
          <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'recall' }" href="#" @click.prevent="tab = 'recall'">Recall por lote</a></li>
          <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'serial' }" href="#" @click.prevent="tab = 'serial'">Nº serial</a></li>
        </ul>

        <!-- A vencer -->
        <div v-if="tab === 'expiring'">
          <div class="form-inline mb-2">
            <label class="mr-2">Vencendo em até</label>
            <input v-model.number="days" type="number" min="0" class="form-control form-control-sm mr-2" style="width:90px" />
            <label class="mr-2">dias</label>
            <button class="btn btn-sm btn-primary" @click="loadExpiring" :disabled="loading">Buscar</button>
          </div>
          <table class="table table-sm table-hover">
            <thead><tr><th>Produto</th><th>Lote</th><th>Validade</th><th>Saldo</th><th>Dias</th></tr></thead>
            <tbody>
              <tr v-for="l in expiring" :key="l.id" :class="{ 'table-danger': l.expired, 'table-warning': !l.expired && l.days_to_expiry <= 15 }">
                <td>{{ l.product_type }} #{{ l.product_id }}</td>
                <td>{{ l.lot_code }}</td>
                <td>{{ l.expiry_date }}</td>
                <td>{{ l.balance }}</td>
                <td>{{ l.days_to_expiry }}<span v-if="l.expired" class="badge badge-danger ml-1">vencido</span></td>
              </tr>
              <tr v-if="!expiring.length"><td colspan="5" class="text-muted text-center">Nenhum lote a vencer.</td></tr>
            </tbody>
          </table>
        </div>

        <!-- Recall -->
        <div v-if="tab === 'recall'">
          <div class="form-inline mb-2">
            <label class="mr-2">Lote</label>
            <input v-model="lotCode" class="form-control form-control-sm mr-2" placeholder="código do lote" maxlength="20" />
            <button class="btn btn-sm btn-primary" @click="loadRecall" :disabled="loading || !lotCode">Rastrear</button>
          </div>
          <div v-if="recall">
            <h6>Lotes</h6>
            <table class="table table-sm">
              <thead><tr><th>Produto</th><th>Validade</th><th>Saldo</th></tr></thead>
              <tbody>
                <tr v-for="l in recall.lots" :key="l.id"><td>{{ l.product_type }} #{{ l.product_id }}</td><td>{{ l.expiry_date }}</td><td>{{ l.balance }}</td></tr>
              </tbody>
            </table>
            <h6>Saídas (pedidos que levaram este lote)</h6>
            <table class="table table-sm">
              <thead><tr><th>Pedido</th><th>Produto</th><th>Qtd</th><th>Status</th></tr></thead>
              <tbody>
                <tr v-for="(s, i) in recall.saidas" :key="i"><td>#{{ s.order_id }}</td><td>{{ s.product_type }} #{{ s.product_id }}</td><td>{{ s.qty }}</td><td>{{ s.status }}</td></tr>
                <tr v-if="!recall.saidas.length"><td colspan="4" class="text-muted text-center">Nenhuma saída registrada.</td></tr>
              </tbody>
            </table>
            <small class="text-muted">Por LGPD, mostramos o pedido — os dados do comprador ficam na tela de Pedidos.</small>
          </div>
        </div>

        <!-- Serial -->
        <div v-if="tab === 'serial'">
          <div class="form-inline mb-2">
            <label class="mr-2">Serial</label>
            <input v-model="serial" class="form-control form-control-sm mr-2" placeholder="número serial" maxlength="80" />
            <button class="btn btn-sm btn-primary" @click="loadSerial" :disabled="loading || !serial">Buscar</button>
          </div>
          <table class="table table-sm" v-if="serialData">
            <thead><tr><th>Produto</th><th>Status</th><th>Pedido</th><th>Lote</th></tr></thead>
            <tbody>
              <tr v-for="u in serialData.units" :key="u.id"><td>{{ u.product_type }} #{{ u.product_id }}</td><td>{{ u.status }}</td><td>{{ u.order_id ? '#' + u.order_id : '—' }}</td><td>{{ u.lot_id || '—' }}</td></tr>
              <tr v-if="!serialData.units.length"><td colspan="4" class="text-muted text-center">Serial não encontrado.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const tab = ref('expiring')
const loading = ref(false)

const days = ref(30)
const expiring = ref([])
const lotCode = ref('')
const recall = ref(null)
const serial = ref('')
const serialData = ref(null)

async function loadExpiring() {
  loading.value = true
  try {
    const { data } = await api.get('/traceability/expiring', { params: { days: days.value } })
    expiring.value = data
  } catch (e) { toast.error('Falha ao buscar lotes a vencer.') } finally { loading.value = false }
}
async function loadRecall() {
  loading.value = true
  try {
    const { data } = await api.get('/traceability/recall', { params: { lot_code: lotCode.value } })
    recall.value = data
  } catch (e) { toast.error('Falha no recall.') } finally { loading.value = false }
}
async function loadSerial() {
  loading.value = true
  try {
    const { data } = await api.get(`/traceability/serials/${encodeURIComponent(serial.value)}`)
    serialData.value = data
  } catch (e) { toast.error('Falha ao buscar serial.') } finally { loading.value = false }
}

loadExpiring()
</script>
