<template>
  <div>
    <!-- Balance Card -->
    <div class="row mb-3">
      <div class="col-md-4">
        <div class="card card-success">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-wallet mr-2"></i>Saldo Disponível</h3>
          </div>
          <div class="card-body text-center">
            <h2 class="text-success">{{ formatCurrency(financialStore.balance) }}</h2>
            <p class="text-muted mb-0">
              Reservado: {{ formatCurrency(financialStore.balanceReserved) }}
            </p>
          </div>
          <div class="card-footer">
            <button class="btn btn-success btn-block" @click="showDepositModal = true">
              <i class="fas fa-plus mr-1"></i> Adicionar Saldo via PIX
            </button>
          </div>
        </div>
      </div>
      <!-- PIX info card -->
      <div class="col-md-8">
        <div class="card card-outline card-info">
          <div class="card-header">
            <h3 class="card-title">Como adicionar saldo</h3>
          </div>
          <div class="card-body">
            <ol>
              <li>Faça um PIX para a chave do fornecedor</li>
              <li>Copie o ID/código da transação</li>
              <li>Clique em "Adicionar Saldo via PIX" e informe o código</li>
              <li>Seu saldo será creditado após confirmação</li>
            </ol>
          </div>
        </div>
      </div>
    </div>

    <!-- Filters + Transaction Table -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Extrato da Conta Corrente</h3>
        <div class="card-tools d-flex gap-2">
          <select v-model="filters.type" class="form-control form-control-sm" style="width:130px">
            <option value="">Todos</option>
            <option value="credit">Entradas</option>
            <option value="debit">Saídas</option>
          </select>
          <input v-model="filters.date_from" type="date" class="form-control form-control-sm" style="width:150px" />
          <input v-model="filters.date_to" type="date" class="form-control form-control-sm" style="width:150px" />
          <button class="btn btn-sm btn-primary" @click="loadTransactions">
            <i class="fas fa-search"></i>
          </button>
        </div>
      </div>
      <div class="card-body p-0">
        <table class="table table-striped table-sm">
          <thead>
            <tr>
              <th>#</th>
              <th>Descrição</th>
              <th>Valor</th>
              <th>Saldo após</th>
              <th>Status</th>
              <th>Data/Hora</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="6" class="text-center py-3">
                <i class="fas fa-spinner fa-spin"></i> Carregando...
              </td>
            </tr>
            <tr v-else-if="!transactions.length">
              <td colspan="6" class="text-center py-3 text-muted">Nenhuma transação encontrada</td>
            </tr>
            <tr v-for="tx in transactions" :key="tx.id">
              <td>{{ tx.id }}</td>
              <td>{{ tx.description }}</td>
              <td :class="tx.type === 'credit' ? 'text-success font-weight-bold' : 'text-danger font-weight-bold'">
                {{ tx.type === 'credit' ? '+' : '-' }} {{ formatCurrency(tx.amount) }}
              </td>
              <td>{{ formatCurrency(tx.balance_after) }}</td>
              <td>
                <span :class="`badge badge-${tx.status === 'completed' ? 'success' : 'warning'}`">
                  {{ tx.status }}
                </span>
              </td>
              <td>{{ formatDateTime(tx.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card-footer">
        <!-- Pagination -->
        <div class="d-flex justify-content-between align-items-center">
          <span class="text-muted small">Total: {{ pagination.total }} registros</span>
          <div>
            <select v-model="pagination.pageSize" @change="loadTransactions" class="form-control form-control-sm d-inline" style="width:70px">
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
            <button class="btn btn-sm btn-outline-secondary ml-2" :disabled="pagination.currentPage <= 1" @click="prevPage">
              <i class="fas fa-chevron-left"></i>
            </button>
            <span class="mx-2">{{ pagination.currentPage }} / {{ pagination.totalPages }}</span>
            <button class="btn btn-sm btn-outline-secondary" :disabled="pagination.currentPage >= pagination.totalPages" @click="nextPage">
              <i class="fas fa-chevron-right"></i>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- PIX Deposit Modal -->
    <div v-if="showDepositModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Adicionar Saldo via PIX</h5>
            <button type="button" class="close" @click="showDepositModal = false">
              <span>&times;</span>
            </button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>Valor (R$)</label>
              <input v-model="depositForm.amount" type="number" step="0.01" class="form-control" placeholder="0,00" />
            </div>
            <div class="form-group">
              <label>ID/Código da transação PIX</label>
              <input v-model="depositForm.pix_txid" type="text" class="form-control" placeholder="Cole o código aqui" />
            </div>
            <div v-if="depositError" class="alert alert-danger py-2">{{ depositError }}</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showDepositModal = false">Cancelar</button>
            <button type="button" class="btn btn-success" :disabled="depositLoading" @click="submitDeposit">
              <span v-if="depositLoading"><i class="fas fa-spinner fa-spin"></i></span>
              <span v-else>Confirmar Depósito</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useFinancialStore } from '@/stores/financial'
import { formatCurrency, formatDateTime } from '@/utils/formatters'

const financialStore = useFinancialStore()

const transactions = ref([])
const loading = ref(false)
const showDepositModal = ref(false)
const depositLoading = ref(false)
const depositError = ref('')

const filters = reactive({ type: '', date_from: '', date_to: '' })
const pagination = reactive({ currentPage: 1, pageSize: 20, total: 0, totalPages: 1 })

const depositForm = reactive({ amount: '', pix_txid: '' })

async function loadTransactions() {
  loading.value = true
  try {
    const params = {
      page: pagination.currentPage,
      page_size: pagination.pageSize,
    }
    if (filters.type) params.type = filters.type
    if (filters.date_from) params.date_from = filters.date_from
    if (filters.date_to) params.date_to = filters.date_to

    const { data } = await api.get('/financial/transactions', { params })
    transactions.value = data.items
    pagination.total = data.total
    pagination.totalPages = Math.max(1, Math.ceil(data.total / pagination.pageSize))
  } finally {
    loading.value = false
  }
}

async function submitDeposit() {
  depositError.value = ''
  if (!depositForm.amount || !depositForm.pix_txid) {
    depositError.value = 'Preencha todos os campos'
    return
  }
  depositLoading.value = true
  try {
    await api.post('/financial/pix-deposit', {
      amount: parseFloat(depositForm.amount),
      pix_txid: depositForm.pix_txid,
    })
    showDepositModal.value = false
    await financialStore.fetchBalance()
    await loadTransactions()
  } catch (err) {
    depositError.value = err.response?.data?.detail || 'Erro ao registrar depósito'
  } finally {
    depositLoading.value = false
  }
}

function prevPage() {
  if (pagination.currentPage > 1) {
    pagination.currentPage--
    loadTransactions()
  }
}

function nextPage() {
  if (pagination.currentPage < pagination.totalPages) {
    pagination.currentPage++
    loadTransactions()
  }
}

onMounted(() => {
  financialStore.fetchBalance()
  loadTransactions()
})
</script>
