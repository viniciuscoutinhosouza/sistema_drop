<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><i class="fas fa-arrow-down text-warning mr-2"></i>Entradas (NF-e)</h1>
            <small class="text-muted">NFes recebidas de fornecedores</small>
          </div>
          <div class="col-sm-6 text-right">
            <button class="btn btn-outline-info mr-2" @click="showImport = true">
              <i class="fas fa-file-import mr-1"></i> Importar XML
            </button>
            <button class="btn btn-outline-info mr-2" :disabled="syncing || !filters.cmig_id"
                    @click="syncReceived"
                    :title="filters.cmig_id ? '' : 'Selecione uma CMIG no filtro'">
              <i class="fas" :class="syncing ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
              {{ syncing ? 'Sincronizando...' : 'Sincronizar Recebidas' }}
            </button>
            <RouterLink to="/fiscal/invoices/new?direction=in" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Lançar Manual
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
                <label class="small mb-1">Origem</label>
                <select v-model="filters.inbound_source" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option value="xml_upload">Upload XML</option>
                  <option value="manual">Manual</option>
                  <option value="dfe_focus">DFe</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Manifestação</label>
                <select v-model="filters.manifestation" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option value="pending">Pendente</option>
                  <option value="ciencia">Ciência</option>
                  <option value="confirmacao">Confirmação</option>
                  <option value="desconhecimento">Desconhecimento</option>
                  <option value="nao_realizada">Não Realizada</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Buscar (chave)</label>
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
          <div v-if="canMoveStock" class="card-header d-flex align-items-center">
            <button class="btn btn-sm btn-success" :disabled="selectedIds.length === 0 || bulkBusy"
                    @click="contabilizarLote">
              <i class="fas" :class="bulkBusy ? 'fa-spinner fa-spin' : 'fa-boxes'"></i>
              Contabilizar Estoque<span v-if="selectedIds.length"> ({{ selectedIds.length }})</span>
            </button>
            <small class="text-muted ml-2">
              Marque as entradas com <i class="fas fa-box text-warning"></i> (ainda não contabilizadas) e
              lance o estoque de todas de uma vez.
            </small>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover mb-0">
              <thead>
                <tr>
                  <th v-if="canMoveStock" style="width:34px" class="text-center" @click.stop>
                    <input type="checkbox" :checked="allPendingSelected" :disabled="pendingInvoices.length === 0"
                           title="Selecionar todas as entradas pendentes de estoque"
                           @change="toggleSelectAll" style="width:16px;height:16px">
                  </th>
                  <th role="button" @click="setSort('numero')">Chave / Número <i class="fas" :class="sortIcon('numero')"></i></th>
                  <th role="button" @click="setSort('emissao')">Emissão <i class="fas" :class="sortIcon('emissao')"></i></th>
                  <th>Fornecedor</th>
                  <th role="button" @click="setSort('tipo')">Origem <i class="fas" :class="sortIcon('tipo')"></i></th>
                  <th>Manifestação</th>
                  <th class="text-right">Total</th>
                  <th>Status</th>
                  <th class="text-center">Estoque</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="invoices.length === 0">
                  <td :colspan="canMoveStock ? 10 : 9" class="text-center text-muted py-4">Nenhuma NFe de entrada encontrada.</td>
                </tr>
                <tr v-for="inv in invoices" :key="inv.id" style="cursor:pointer"
                    :class="{'table-warning': inv.manifestation === 'pending' && inv.inbound_source === 'dfe_focus'}"
                    @click="$router.push(`/fiscal/invoices/${inv.id}`)">
                  <td v-if="canMoveStock" class="text-center" @click.stop>
                    <input v-if="inv.stock_pending && !inv.has_unmatched_items" type="checkbox"
                           :value="inv.id" v-model="selectedIds" style="width:16px;height:16px">
                  </td>
                  <td>
                    <code v-if="inv.access_key" class="small">…{{ inv.access_key.slice(-12) }}</code>
                    <span v-else-if="inv.nfe_number">{{ inv.nfe_number }} / {{ inv.serie }}</span>
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
                    <span class="badge badge-light">{{ inboundSourceLabel(inv.inbound_source) }}</span>
                  </td>
                  <td>
                    <span class="badge" :class="manifestationClass(inv.manifestation)">
                      {{ manifestationLabel(inv.manifestation) }}
                    </span>
                  </td>
                  <td class="text-right">
                    <strong>{{ formatCurrency(inv.total_invoice) }}</strong>
                  </td>
                  <td>
                    <span class="badge" :class="statusClass(inv.status)">{{ statusLabel(inv.status) }}</span>
                  </td>
                  <td @click.stop class="text-center">
                    <button v-if="inv.has_unmatched_items && canMoveStock" class="btn btn-sm btn-outline-danger"
                            title="Esta nota tem produtos não sincronizados — clique para vincular ou cadastrar"
                            @click="openSync(inv)">
                      <i class="fas fa-link"></i>
                    </button>
                    <span v-else-if="inv.has_unmatched_items" class="text-danger" title="Produtos não sincronizados">
                      <i class="fas fa-link"></i>
                    </span>
                    <button v-else-if="inv.stock_pending && canMoveStock" class="btn btn-sm btn-outline-warning"
                            title="Contabilizar o estoque desta nota" :disabled="rowBusy[inv.id]"
                            @click="contabilizarUma(inv)">
                      <i class="fas" :class="rowBusy[inv.id] ? 'fa-spinner fa-spin' : 'fa-box'"></i>
                    </button>
                    <span v-else-if="inv.stock_pending" class="text-warning" title="Estoque não contabilizado">
                      <i class="fas fa-box"></i>
                    </span>
                    <span v-else-if="inv.stock_updated" class="text-success" title="Estoque já contabilizado">
                      <i class="fas fa-check-circle"></i>
                    </span>
                    <span v-else class="text-muted" title="Não contabiliza estoque">—</span>
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

    <XmlImportModal
      v-if="showImport"
      :default-cmig-id="filters.cmig_id"
      @close="showImport = false"
      @imported="onImported" />

    <ProductSyncModal
      v-if="syncModalInvoiceId"
      :invoice-id="syncModalInvoiceId"
      @close="syncModalInvoiceId = null"
      @done="reload" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { fmt } from '@/views/fiscal/_helpers'
import XmlImportModal from '@/components/fiscal/XmlImportModal.vue'
import ProductSyncModal from '@/components/fiscal/ProductSyncModal.vue'

const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const authStore = useAuthStore()
const toast = useToast()
const { invoices, total, loading } = storeToRefs(fiscalStore)
const { cmigs } = storeToRefs(cmigStore)

const pageSize = 20
const showImport = ref(false)
const syncing = ref(false)
const syncModalInvoiceId = ref(null)
function openSync(inv) { syncModalInvoiceId.value = inv.id }

// Contabilização de estoque (ícone por linha + ação em lote) — gateado por permissão de ação
// `estoque_movimentar` (ADR-0036; admin bypassa). O backend reforça em require_permission.
const canMoveStock = computed(() => authStore.hasAction('estoque_movimentar'))
const selectedIds = ref([])
const bulkBusy = ref(false)
const rowBusy = reactive({})
// Só notas prontas p/ contabilizar entram na seleção em lote (as com produtos não sincronizados
// precisam ser resolvidas no modal primeiro — senão o lote cairia em no_match).
const pendingInvoices = computed(() => invoices.value.filter(i => i.stock_pending && !i.has_unmatched_items))
const allPendingSelected = computed(() =>
  pendingInvoices.value.length > 0 && pendingInvoices.value.every(i => selectedIds.value.includes(i.id))
)
function toggleSelectAll() {
  selectedIds.value = allPendingSelected.value ? [] : pendingInvoices.value.map(i => i.id)
}
async function contabilizarUma(inv) {
  rowBusy[inv.id] = true
  try {
    const r = await fiscalStore.updateStock(inv.id)
    if (r.no_match) {
      toast.warning('Nenhum produto desta nota casou pelo EAN — cadastre/corrija o produto com o EAN da nota e contabilize novamente. Estoque NÃO alterado.')
    } else if (r.already_updated) {
      toast.info('Esta nota já estava contabilizada no estoque.')
    } else {
      toast.success('Estoque contabilizado.')
    }
    reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao contabilizar o estoque')
  } finally {
    rowBusy[inv.id] = false
  }
}
async function contabilizarLote() {
  if (selectedIds.value.length === 0) return
  bulkBusy.value = true
  try {
    const r = await fiscalStore.updateStockBulk(selectedIds.value)
    const parts = [`${r.updated} contabilizada(s)`]
    if (r.no_match) parts.push(`${r.no_match} sem produto casado (EAN)`)
    if (r.skipped) parts.push(`${r.skipped} já/inaplicável`)
    if (r.errors?.length) parts.push(`${r.errors.length} com erro`)
    const msg = parts.join(' · ')
    if (r.errors?.length || r.no_match) toast.warning(msg)
    else toast.success(msg)
    selectedIds.value = []
    reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao contabilizar o estoque em lote')
  } finally {
    bulkBusy.value = false
  }
}
const filters = reactive({
  cmig_id: null,
  direction: 'in',
  status: null,
  inbound_source: null,
  manifestation: null,
  search: '',
  date_from: '',
  date_to: '',
  sort_by: null,
  sort_dir: 'desc',
  page: 1,
  page_size: pageSize,
})

function setSort(col) {
  if (filters.sort_by === col) {
    filters.sort_dir = filters.sort_dir === 'asc' ? 'desc' : 'asc'
  } else {
    filters.sort_by = col
    filters.sort_dir = 'asc'
  }
  filters.page = 1
  reload()
}

function sortIcon(col) {
  if (filters.sort_by !== col) return 'fa-sort text-muted'
  return filters.sort_dir === 'asc' ? 'fa-sort-up' : 'fa-sort-down'
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function reload() {
  selectedIds.value = []  // seleção não sobrevive a troca de página/filtro
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== '') params[k] = v
  }
  try {
    await fiscalStore.fetchInvoices(params)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NFes')
  }
}

function onImported() {
  toast.success('XML importado com sucesso!')
  reload()
}

async function syncReceived() {
  if (!filters.cmig_id) {
    toast.warning('Selecione uma CMIG no filtro acima.')
    return
  }
  syncing.value = true
  try {
    const r = await fiscalStore.syncReceived(filters.cmig_id)
    if (r.new > 0) {
      toast.success(`${r.new} nova(s) NFe(s) recebida(s); ${r.skipped} já existente(s)`)
    } else {
      toast.info(`Nenhuma NFe nova encontrada (${r.skipped} já existente${r.skipped === 1 ? '' : 's'})`)
    }
    if (r.errors?.length) {
      toast.warning(`${r.errors.length} erro(s) — verifique os logs`)
    }
    reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar')
  } finally {
    syncing.value = false
  }
}

const formatDate = fmt.date
const formatCurrency = fmt.currency
const inboundSourceLabel = fmt.inboundSource
const manifestationLabel = fmt.manifestation
const manifestationClass = fmt.manifestationClass
const statusLabel = fmt.statusLabel
const statusClass = fmt.statusClass

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  // 1 só CMIG: dropdown escondido — auto-seleciona para liberar sync/exportações
  if (cmigs.value.length === 1) filters.cmig_id = cmigs.value[0].id
  reload()
})
</script>
