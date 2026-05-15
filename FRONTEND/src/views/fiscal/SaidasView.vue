<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-5">
            <h1 class="m-0"><i class="fas fa-arrow-up text-success mr-2"></i>Saídas (NF-e)</h1>
            <small class="text-muted">NF-e do módulo fiscal + NF-e do Faturador do Mercado Livre, por pedido e por CMIG</small>
          </div>
          <div class="col-sm-7 text-right">
            <button class="btn btn-outline-primary mr-2" :disabled="syncing || loading"
                    title="Busca no Mercado Livre as NF-e ainda não consultadas (inclui Retorno Simbólico de pedidos Full)"
                    @click="syncMl">
              <i class="fas mr-1" :class="syncing ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
              {{ syncing ? `Sincronizando… (${syncProgress})` : 'Sincronizar NF-e do ML' }}
            </button>
            <button class="btn btn-outline-secondary mr-2" :disabled="exporting" @click="doExport('xml')">
              <i class="fas mr-1" :class="exporting === 'xml' ? 'fa-spinner fa-spin' : 'fa-file-code'"></i>
              Exportar XMLs
            </button>
            <button class="btn btn-outline-secondary mr-2" :disabled="exporting" @click="doExport('danfe')">
              <i class="fas mr-1" :class="exporting === 'danfe' ? 'fa-spinner fa-spin' : 'fa-file-pdf'"></i>
              Exportar DANFEs
            </button>
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
                <label class="small mb-1">Origem</label>
                <select v-model="filters.source" class="form-control form-control-sm" @change="reload">
                  <option value="all">Todas</option>
                  <option value="fiscal">Sistema (Focus NFe)</option>
                  <option value="ml">Faturador ML</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Status</label>
                <select v-model="filters.status" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todos</option>
                  <option value="draft">Rascunho</option>
                  <option value="pending">Pendente</option>
                  <option value="processing">Processando</option>
                  <option value="authorized">Autorizada</option>
                  <option value="rejected">Rejeitada</option>
                  <option value="cancelled">Cancelada</option>
                </select>
              </div>
              <div class="col-md-5">
                <label class="small mb-1">Buscar (chave / nº / pedido)</label>
                <input v-model="filters.search" class="form-control form-control-sm"
                       placeholder="Chave de acesso, número da NF-e ou ID do pedido"
                       @keyup.enter="reload">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-3">
                <label class="small mb-1">Emissão de</label>
                <input v-model="filters.date_from" type="date" class="form-control form-control-sm" @change="reload">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Emissão até</label>
                <input v-model="filters.date_to" type="date" class="form-control form-control-sm" @change="reload">
              </div>
            </div>
          </div>
        </div>

        <!-- Resumo por CMIG -->
        <div v-if="byCmig.length" class="mb-2 d-flex flex-wrap" style="gap:.5rem">
          <div v-for="b in byCmig" :key="b.cmig_id" class="badge badge-light border p-2">
            <i class="fas fa-building text-muted mr-1"></i>
            <strong>{{ b.cmig_name || ('CMIG #' + b.cmig_id) }}</strong>
            — {{ b.count }} NF-e · {{ formatCurrency(b.total) }}
          </div>
        </div>

        <!-- Tabela -->
        <div class="card">
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover table-sm mb-0">
              <thead>
                <tr>
                  <th v-if="!filters.cmig_id">CMIG</th>
                  <th>Nº / Série</th>
                  <th>Tipo</th>
                  <th>Emissão</th>
                  <th>Destinatário</th>
                  <th>Origem</th>
                  <th>Pedido</th>
                  <th class="text-right">Total</th>
                  <th>Status</th>
                  <th class="text-right">Documentos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="invoices.length === 0">
                  <td :colspan="filters.cmig_id ? 9 : 10" class="text-center text-muted py-4">
                    Nenhuma NF-e encontrada.
                  </td>
                </tr>
                <tr v-for="inv in invoices" :key="inv.source + '-' + inv.id">
                  <td v-if="!filters.cmig_id">
                    <small>{{ inv.cmig_name || ('#' + inv.cmig_id) }}</small>
                  </td>
                  <td>
                    <span v-if="inv.nfe_number">{{ inv.nfe_number }}<span v-if="inv.serie"> / {{ inv.serie }}</span></span>
                    <span v-else class="text-muted">—</span>
                    <small v-if="inv.access_key" class="d-inline text-muted ml-2" style="font-size:.7rem">
                      ({{ inv.access_key }})
                    </small>
                  </td>
                  <td>
                    {{ inv.nfe_type_label }}
                  </td>
                  <td>{{ formatDate(inv.issue_date) }}</td>
                  <td>
                    <span v-if="inv.recipient">
                      <strong>{{ inv.recipient }}</strong>
                      <small v-if="inv.recipient_document" class="d-block text-muted">{{ inv.recipient_document }}</small>
                    </span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <span class="badge" :class="inv.source === 'ml' ? 'badge-warning' : 'badge-info'">
                      <i class="fas mr-1" :class="inv.source === 'ml' ? 'fa-store' : 'fa-cogs'"></i>
                      {{ inv.source === 'ml' ? 'Mercado Livre' : 'Sistema' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink v-if="inv.order_id" :to="`/orders/${inv.order_id}`"
                                class="badge badge-secondary" :title="`Ver pedido #${inv.platform_order_id || inv.order_id}`">
                      <i class="fas fa-shopping-cart mr-1"></i>
                      {{ inv.platform_order_id || ('#' + inv.order_id) }}
                    </RouterLink>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="text-right"><strong>{{ formatCurrency(inv.total) }}</strong></td>
                  <td>
                    <span class="badge" :class="statusClass(inv.status)">{{ statusLabel(inv.status) }}</span>
                  </td>
                  <td class="text-right text-nowrap">
                    <button class="btn btn-sm btn-outline-danger mr-1"
                            :disabled="!inv.danfe_available || docLoading[rowKey(inv)] === 'danfe'"
                            :title="inv.danfe_available ? 'Visualizar DANFE' : 'DANFE indisponível'"
                            @click="viewDanfe(inv)">
                      <i class="fas" :class="docLoading[rowKey(inv)] === 'danfe' ? 'fa-spinner fa-spin' : 'fa-file-pdf'"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary mr-1"
                            :disabled="!inv.xml_available || docLoading[rowKey(inv)] === 'xml'"
                            :title="inv.xml_available ? 'Baixar XML' : 'XML indisponível'"
                            @click="downloadXml(inv)">
                      <i class="fas" :class="docLoading[rowKey(inv)] === 'xml' ? 'fa-spinner fa-spin' : 'fa-file-code'"></i>
                    </button>
                    <RouterLink v-if="inv.source === 'fiscal'" :to="`/fiscal/invoices/${inv.id}`"
                                class="btn btn-sm btn-outline-info" title="Detalhes da NF-e">
                      <i class="fas fa-eye"></i>
                    </RouterLink>
                    <RouterLink v-else :to="`/orders/${inv.order_id}`"
                                class="btn btn-sm btn-outline-info" title="Ver pedido / NF-e do ML">
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
            <span class="text-muted">Página {{ filters.page }} de {{ totalPages }} ({{ total }} NF-e)</span>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { useToast } from '@/composables/useToast'
import { fmt } from '@/views/fiscal/_helpers'
import api from '@/composables/useApi'

const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const toast = useToast()
const { invoices, total, loading } = storeToRefs(fiscalStore)
const { cmigs } = storeToRefs(cmigStore)

const pageSize = 30
const byCmig = ref([])
const exporting = ref(null)
const docLoading = ref({})
const syncing = ref(false)
const syncProgress = ref(0)

const rowKey = (row) => `${row.source}-${row.id}`

// axios com responseType:blob devolve o erro como Blob — precisa parsear
async function parseBlobError(err, fallback) {
  if (err.response?.data instanceof Blob) {
    try { return JSON.parse(await err.response.data.text()).detail || fallback } catch { return fallback }
  }
  return err.response?.data?.detail || fallback
}
const filters = reactive({
  cmig_id: null,
  source: 'all',
  status: null,
  search: '',
  date_from: '',
  date_to: '',
  page: 1,
  page_size: pageSize,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

// Monta o objeto de params descartando vazios (compartilhado entre listar e exportar)
function buildParams(extra = {}) {
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== '') params[k] = v
  }
  return { ...params, ...extra }
}

async function reload() {
  try {
    const data = await fiscalStore.fetchOutbound(buildParams())
    byCmig.value = data.by_cmig || []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NF-e de saída')
  }
}

// Sincroniza as NF-e do Faturador ML em lotes até esgotar os pedidos pendentes
async function syncMl() {
  syncing.value = true
  syncProgress.value = 0
  try {
    const params = filters.cmig_id ? { cmig_id: filters.cmig_id } : {}
    let guard = 0
    while (guard++ < 500) {
      const data = await fiscalStore.syncMlOutbound(params)
      syncProgress.value += data.processed || 0
      if (!data.remaining || !data.processed) break
    }
    toast.success(`Sincronização concluída — ${syncProgress.value} pedido(s) atualizados`)
    await reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar NF-e do ML')
  } finally {
    syncing.value = false
  }
}

async function doExport(kind) {
  exporting.value = kind
  try {
    // page/page_size não afetam o export — o backend exporta todo o conjunto filtrado
    const { page, page_size, ...exportFilters } = buildParams()
    await fiscalStore.exportOutbound(kind, exportFilters)
  } catch (e) {
    let msg = 'Erro ao exportar'
    if (e.response?.data instanceof Blob) {
      try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* keep */ }
    } else if (e.response?.data?.detail) {
      msg = e.response.data.detail
    }
    toast.error(msg)
  } finally {
    exporting.value = null
  }
}

// Visualiza a DANFE de uma NF-e individual (abre em nova aba)
async function viewDanfe(inv) {
  if (!inv.danfe_available) { toast.warning('DANFE não disponível para esta NF-e'); return }
  if (inv.source === 'fiscal') {
    window.open(inv.danfe_url, '_blank')
    return
  }
  docLoading.value[rowKey(inv)] = 'danfe'
  try {
    const { data } = await api.get(
      `/orders/${inv.order_id}/invoices/${inv.ml_invoice_id}/danfe`, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    toast.error(await parseBlobError(e, 'Erro ao abrir DANFE'))
  } finally {
    docLoading.value[rowKey(inv)] = null
  }
}

// Baixa o XML de uma NF-e individual
async function downloadXml(inv) {
  if (!inv.xml_available) { toast.warning('XML não disponível para esta NF-e'); return }
  if (inv.source === 'fiscal') {
    window.open(inv.xml_url, '_blank')
    return
  }
  docLoading.value[rowKey(inv)] = 'xml'
  try {
    const { data } = await api.get(
      `/orders/${inv.order_id}/invoices/${inv.ml_invoice_id}/xml`, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'application/xml' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `NFe_${inv.access_key || inv.ml_invoice_id}.xml`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    toast.error(await parseBlobError(e, 'Erro ao baixar XML'))
  } finally {
    docLoading.value[rowKey(inv)] = null
  }
}

const formatDate = fmt.date
const formatCurrency = fmt.currency
const statusLabel = fmt.statusLabel
const statusClass = fmt.statusClass

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  reload()
})
</script>
