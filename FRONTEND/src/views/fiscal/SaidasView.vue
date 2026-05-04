<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><i class="fas fa-arrow-up text-success mr-2"></i>Saídas (NF-e)</h1>
            <small class="text-muted">NFes emitidas pelo sistema</small>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/fiscal/invoices/new?direction=out" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Nova Saída
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <!-- Filtros -->
        <div class="card">
          <div class="card-body">
            <div class="row">
              <div class="col-md-3" v-if="cmigs.length > 1">
                <label class="small mb-1">CMIG</label>
                <select v-model="filters.cmig_id" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }}</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Status</label>
                <select v-model="filters.status" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todos</option>
                  <option value="draft">Rascunho</option>
                  <option value="queued">Em fila</option>
                  <option value="processing">Processando</option>
                  <option value="authorized">Autorizada</option>
                  <option value="rejected">Rejeitada</option>
                  <option value="cancelled">Cancelada</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Finalidade</label>
                <select v-model="filters.purpose" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option value="venda">Venda</option>
                  <option value="devolucao">Devolução</option>
                  <option value="remessa">Simples Remessa</option>
                  <option value="retorno">Retorno</option>
                  <option value="transferencia">Transferência</option>
                  <option value="complementar">Complementar</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Origem</label>
                <select v-model="originFilter" class="form-control form-control-sm" @change="reload">
                  <option value="">Todas</option>
                  <option value="manual">Manual</option>
                  <option value="order">Pedido</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Buscar (chave/número)</label>
                <input v-model="filters.search" class="form-control form-control-sm" @keyup.enter="reload">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-3">
                <label class="small mb-1">Data emissão de</label>
                <input v-model="filters.date_from" type="date" class="form-control form-control-sm" @change="reload">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Data emissão até</label>
                <input v-model="filters.date_to" type="date" class="form-control form-control-sm" @change="reload">
              </div>
            </div>
          </div>
        </div>

        <!-- Tabela -->
        <div class="card">
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Nº / Série</th>
                  <th>Emissão</th>
                  <th>Destinatário</th>
                  <th>Finalidade</th>
                  <th>Origem</th>
                  <th class="text-right">Total</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="invoices.length === 0">
                  <td colspan="8" class="text-center text-muted py-4">Nenhuma NFe encontrada.</td>
                </tr>
                <tr v-for="inv in invoices" :key="inv.id" style="cursor:pointer"
                    @click="$router.push(`/fiscal/invoices/${inv.id}`)">
                  <td>
                    <span v-if="inv.nfe_number">{{ inv.nfe_number }} / {{ inv.serie }}</span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>{{ formatDate(inv.issue_date) }}</td>
                  <td>
                    <span v-if="inv.person">
                      <strong>{{ inv.person.name }}</strong>
                      <small class="d-block text-muted">{{ inv.person.document }}</small>
                    </span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <span class="badge badge-light">{{ purposeLabel(inv.purpose) }}</span>
                  </td>
                  <td @click.stop>
                    <RouterLink v-if="inv.order_id" :to="`/orders/${inv.order_id}`"
                                class="badge badge-info" :title="`Ver pedido #${inv.order_id}`">
                      <i class="fas fa-shopping-cart mr-1"></i> Pedido #{{ inv.order_id }}
                    </RouterLink>
                    <span v-else class="badge badge-secondary">Manual</span>
                  </td>
                  <td class="text-right">
                    <strong>{{ formatCurrency(inv.total_invoice) }}</strong>
                  </td>
                  <td>
                    <span class="badge" :class="statusClass(inv.status)">{{ statusLabel(inv.status) }}</span>
                  </td>
                  <td @click.stop class="text-right">
                    <RouterLink :to="`/fiscal/invoices/${inv.id}`" class="btn btn-sm btn-outline-info" title="Detalhes">
                      <i class="fas fa-eye"></i>
                    </RouterLink>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="total > pageSize" class="card-footer">
            <button class="btn btn-sm btn-outline-secondary mr-2" :disabled="filters.page === 1"
                    @click="filters.page--; reload()">
              <i class="fas fa-chevron-left"></i> Anterior
            </button>
            <span class="text-muted">Página {{ filters.page }} de {{ totalPages }}</span>
            <button class="btn btn-sm btn-outline-secondary ml-2" :disabled="filters.page >= totalPages"
                    @click="filters.page++; reload()">
              Próxima <i class="fas fa-chevron-right"></i>
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { useToast } from '@/composables/useToast'
import { fmt } from '@/views/fiscal/_helpers'

const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const toast = useToast()
const { invoices, total, loading } = storeToRefs(fiscalStore)
const { cmigs } = storeToRefs(cmigStore)

const pageSize = 20
const originFilter = ref('')
const filters = reactive({
  cmig_id: null,
  direction: 'out',
  status: null,
  purpose: null,
  search: '',
  date_from: '',
  date_to: '',
  page: 1,
  page_size: pageSize,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function reload() {
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== '') params[k] = v
  }
  try {
    const data = await fiscalStore.fetchInvoices(params)
    if (originFilter.value) {
      const want = originFilter.value
      const filtered = (data.items || []).filter(i =>
        want === 'order' ? !!i.order_id : !i.order_id
      )
      invoices.value = filtered
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NFes')
  }
}

const formatDate = fmt.date
const formatCurrency = fmt.currency
const purposeLabel = fmt.purpose
const statusLabel = fmt.statusLabel
const statusClass = fmt.statusClass

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  reload()
})
</script>
