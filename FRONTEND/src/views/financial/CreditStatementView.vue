<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h1 class="h4 mb-0"><i class="fas fa-hand-holding-usd mr-2"></i>Extrato de Crédito</h1>
    </div>

    <div class="card">
      <div class="card-header d-flex flex-wrap align-items-end" style="gap:.75rem">
        <div v-if="!cmigStore.hasSingleCmig">
          <label class="small mb-1 d-block">CMIG</label>
          <select v-model="cmigId" class="form-control form-control-sm" style="min-width:240px" @change="load">
            <option :value="null" disabled>Selecione…</option>
            <option v-for="c in cmigStore.cmigs" :key="c.id" :value="c.id">{{ cmigLabel(c) }}</option>
          </select>
        </div>
        <div class="ml-auto text-right">
          <div class="small text-muted">Saldo de crédito</div>
          <div class="h4 mb-0" :class="balance < 0 ? 'text-danger' : 'text-success'">
            {{ formatCurrency(balance) }}
          </div>
        </div>
      </div>

      <div class="card-body">
        <p class="text-muted small">
          Crédito que esta CMIG mantém com o Galpão para cobrir vendas de Produto Geral (PG) antes da
          entrega. <strong>Crédito</strong> = depósito da CMIG; <strong>Débito</strong> = consumo por venda PG.
        </p>

        <!-- Lançamento manual (o backend permite só ao Galpão/admin) -->
        <form v-if="canPost && cmigId" class="form-row align-items-end mb-3" @submit.prevent="addEntry">
          <div class="col-auto">
            <label class="small mb-1 d-block">Tipo</label>
            <select v-model="form.entry_type" class="form-control form-control-sm">
              <option value="credit">Crédito (depósito)</option>
              <option value="debit">Débito (ajuste)</option>
            </select>
          </div>
          <div class="col-auto">
            <label class="small mb-1 d-block">Valor</label>
            <input v-model="form.amount" type="number" step="0.01" min="0.01" class="form-control form-control-sm" style="width:130px" />
          </div>
          <div class="col">
            <label class="small mb-1 d-block">Descrição</label>
            <input v-model="form.description" type="text" class="form-control form-control-sm" placeholder="Ex.: Depósito Pix recebido" />
          </div>
          <div class="col-auto">
            <button class="btn btn-sm btn-primary" :disabled="posting">
              <i class="fas" :class="posting ? 'fa-spinner fa-spin' : 'fa-plus'"></i> Lançar
            </button>
          </div>
        </form>

        <div class="table-responsive">
          <table class="table table-sm table-striped mb-0">
            <thead>
              <tr><th>Data</th><th>Tipo</th><th class="text-right">Valor</th><th>Pedido</th><th>Descrição</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in entries" :key="e.id">
                <td class="text-nowrap">{{ formatDateTime(e.created_at) }}</td>
                <td>
                  <span class="badge" :class="e.entry_type === 'credit' ? 'badge-success' : 'badge-secondary'">
                    {{ e.entry_type === 'credit' ? 'Crédito' : 'Débito' }}
                  </span>
                </td>
                <td class="text-right" :class="e.entry_type === 'credit' ? 'text-success' : 'text-danger'">
                  {{ e.entry_type === 'credit' ? '+' : '−' }}{{ formatCurrency(e.amount) }}
                </td>
                <td>{{ e.order_id ? ('#' + e.order_id) : '—' }}</td>
                <td>{{ e.description || '—' }}</td>
              </tr>
              <tr v-if="!entries.length">
                <td colspan="5" class="text-center text-muted py-3">
                  {{ cmigId ? 'Sem lançamentos.' : 'Selecione uma CMIG.' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useCmigStore } from '@/stores/cmig'
import { useAuthStore } from '@/stores/auth'
import { formatCurrency, formatDateTime } from '@/utils/formatters'

const toast = useToast()
const cmigStore = useCmigStore()
const auth = useAuthStore()

const cmigId = ref(null)
const balance = ref(0)
const entries = ref([])
const posting = ref(false)
const form = reactive({ entry_type: 'credit', amount: '', description: '' })

// O lançamento é permitido ao lado do Galpão (operador/dono) ou admin; o backend reforça.
const canPost = computed(() => ['admin', 'go'].includes(auth.user?.role))

function cmigLabel(c) {
  return c.name || c.legal_name || c.company_name || c.trade_name || `CMIG #${c.id}`
}

async function load() {
  if (!cmigId.value) {
    entries.value = []
    balance.value = 0
    return
  }
  try {
    const { data } = await api.get('/credits', { params: { cmig_id: cmigId.value } })
    balance.value = data.balance || 0
    entries.value = Array.isArray(data.entries) ? data.entries : []
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao carregar o extrato')
    entries.value = []
    balance.value = 0
  }
}

async function addEntry() {
  const amount = Number(form.amount)
  if (!Number.isFinite(amount) || amount <= 0) {
    toast.error('Informe um valor maior que zero')
    return
  }
  posting.value = true
  try {
    await api.post('/credits', {
      cmig_id: cmigId.value,
      entry_type: form.entry_type,
      amount,
      description: form.description || null,
    })
    toast.success('Lançamento registrado.')
    form.amount = ''
    form.description = ''
    await load()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao lançar')
  } finally {
    posting.value = false
  }
}

onMounted(async () => {
  if (!cmigStore.cmigs.length) await cmigStore.fetchCmigs()
  if (cmigStore.singleCmigId) {
    cmigId.value = cmigStore.singleCmigId
  } else if (cmigStore.cmigs.length) {
    cmigId.value = cmigStore.cmigs[0].id
  }
  await load()
})
</script>
