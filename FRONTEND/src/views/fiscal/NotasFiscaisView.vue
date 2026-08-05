<template>
  <div class="container-fluid py-3">
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap">
      <h4 class="mb-0"><i class="fas fa-file-invoice mr-2"></i>Notas Fiscais</h4>
      <div class="d-flex flex-wrap" style="gap:.4rem">
        <button class="btn btn-outline-secondary btn-sm" :disabled="!!exporting" title="Baixar XMLs (zip) das notas filtradas, agrupadas por CMIG" @click="doExport('xml')">
          <i class="fas mr-1" :class="exporting === 'xml' ? 'fa-spinner fa-spin' : 'fa-file-code'"></i>XMLs
        </button>
        <button class="btn btn-outline-secondary btn-sm" :disabled="!!exporting" title="Baixar DANFEs (zip) das notas filtradas, agrupadas por CMIG" @click="doExport('danfe')">
          <i class="fas mr-1" :class="exporting === 'danfe' ? 'fa-spinner fa-spin' : 'fa-file-pdf'"></i>PDFs
        </button>
        <button class="btn btn-outline-info btn-sm" :disabled="syncing" title="Sincroniza as NF-e do mês em todos os marketplaces (Faturador)" @click="doSync">
          <i class="fas mr-1" :class="syncing ? 'fa-spinner fa-spin' : 'fa-cloud-download-alt'"></i>Sincronizar mês
        </button>
        <RouterLink to="/fiscal/invoices/new?direction=out" class="btn btn-primary btn-sm"><i class="fas fa-plus mr-1"></i>Nova saída</RouterLink>
        <RouterLink to="/fiscal/invoices/new?direction=in" class="btn btn-outline-primary btn-sm"><i class="fas fa-plus mr-1"></i>Nova entrada</RouterLink>
      </div>
    </div>

    <div class="btn-group btn-group-toggle mb-3" role="group">
      <button v-for="opt in dirOptions" :key="opt.v" type="button"
              class="btn" :class="direction === opt.v ? 'btn-primary' : 'btn-outline-primary'" @click="setDirection(opt.v)">
        <i class="fas mr-1" :class="opt.icon"></i>{{ opt.label }}
      </button>
    </div>

    <div class="card">
      <div class="card-body">
        <div class="row mb-3">
          <div class="col-md-2"><label class="small mb-1">CMIG</label>
            <select v-model="filters.cmig_id" class="form-control form-control-sm" @change="reload">
              <option :value="null">Todas</option>
              <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name || c.name || ('CMIG ' + c.id) }}</option>
            </select>
          </div>
          <div class="col-md-2"><label class="small mb-1">Status</label>
            <select v-model="filters.status" class="form-control form-control-sm" @change="reload">
              <option :value="null">Todos</option>
              <option value="authorized">Autorizada</option>
              <option value="finalized">Finalizada</option>
              <option value="draft">Rascunho</option>
              <option value="rejected">Rejeitada</option>
              <option value="cancelled">Cancelada</option>
            </select>
          </div>
          <div class="col-md-2"><label class="small mb-1">De</label>
            <input v-model="filters.date_from" type="date" class="form-control form-control-sm" @change="reload">
          </div>
          <div class="col-md-2"><label class="small mb-1">Até</label>
            <input v-model="filters.date_to" type="date" class="form-control form-control-sm" @change="reload">
          </div>
          <div class="col-md-4"><label class="small mb-1">Buscar</label>
            <input v-model="filters.search" class="form-control form-control-sm" placeholder="Número, chave, natureza…" @keyup.enter="reload">
          </div>
        </div>

        <div class="table-responsive">
          <table class="table table-sm table-hover" style="font-size:13px;white-space:nowrap">
            <thead class="thead-light">
              <tr>
                <th role="button" @click="setSort('emissao')">Emissão <i class="fas" :class="sortIcon('emissao')"></i></th>
                <th role="button" @click="setSort('numero')">NF <i class="fas" :class="sortIcon('numero')"></i></th>
                <th role="button" @click="setSort('direcao')">Direção <i class="fas" :class="sortIcon('direcao')"></i></th>
                <th role="button" @click="setSort('cmig')">CMIG <i class="fas" :class="sortIcon('cmig')"></i></th>
                <th>Contraparte</th>
                <th>Natureza</th>
                <th>CFOP</th>
                <th>Pedido</th>
                <th class="text-right" role="button" @click="setSort('valor')">Valor <i class="fas" :class="sortIcon('valor')"></i></th>
                <th role="button" @click="setSort('status')">Status <i class="fas" :class="sortIcon('status')"></i></th>
                <th class="text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="11" class="text-center text-muted py-4"><i class="fas fa-spinner fa-spin mr-1"></i>Carregando…</td></tr>
              <tr v-else-if="!rows.length"><td colspan="11" class="text-center text-muted py-4"><i class="fas fa-inbox mr-1"></i>Nenhuma nota no filtro.</td></tr>
              <tr v-for="inv in rows" :key="inv.id" @click="openDetail(inv)" style="cursor:pointer">
                <td>{{ fmtDate(inv.issue_date) }}</td>
                <td><span v-if="inv.nfe_number">{{ inv.nfe_number }}<span v-if="inv.serie" class="text-muted">/{{ inv.serie }}</span></span><span v-else class="text-muted">—</span></td>
                <td>
                  <span v-if="inv.direction === 'out'" class="badge badge-danger">Saída</span>
                  <span v-else class="badge badge-success">Entrada</span>
                </td>
                <td class="text-muted">{{ inv.cmig_name || '—' }}</td>
                <td>{{ inv.counterparty || '—' }}</td>
                <td class="text-muted" style="max-width:230px;white-space:normal">{{ inv.natureza_operacao || '—' }}</td>
                <td class="text-muted">{{ inv.cfop || '—' }}</td>
                <td @click.stop>
                  <span v-if="inv.order_id">
                    <RouterLink :to="`/orders/${inv.order_id}`" class="text-primary">#{{ inv.platform_order_id || inv.order_id }}</RouterLink>
                    <a v-if="inv.marketplace_url" :href="inv.marketplace_url" target="_blank" rel="noopener" class="ml-1" title="Abrir no marketplace"><i class="fas fa-external-link-alt" style="font-size:10px"></i></a>
                    <span v-if="inv.platform" class="badge badge-light ml-1" style="font-size:10px">{{ inv.platform === 'mercadolivre' ? 'ML' : (inv.platform === 'shopee' ? 'Shopee' : inv.platform) }}</span>
                  </span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="text-right">{{ fmtMoney(inv.total) }}</td>
                <td><span class="badge" :class="statusClass(inv.status)">{{ statusLabel(inv.status) }}</span></td>
                <td class="text-right" @click.stop>
                  <button class="btn btn-sm btn-outline-secondary mr-1" :disabled="!inv.xml_available || docLoading[inv.id]" title="Baixar XML" @click="downloadDoc(inv, 'xml')">
                    <i class="fas" :class="docLoading[inv.id] === 'xml' ? 'fa-spinner fa-spin' : 'fa-file-code'"></i>
                  </button>
                  <button class="btn btn-sm btn-outline-secondary mr-1" :disabled="(!inv.danfe_available && !inv.danfe_preview) || docLoading[inv.id]" title="Baixar DANFE" @click="downloadDoc(inv, 'danfe')">
                    <i class="fas" :class="docLoading[inv.id] === 'danfe' ? 'fa-spinner fa-spin' : 'fa-file-pdf'"></i>
                  </button>
                  <button v-if="!inv.ml_invoice_id" class="btn btn-sm btn-outline-info" title="Detalhes" @click="openDetail(inv)"><i class="fas fa-eye"></i></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center">
          <small class="text-muted">{{ total }} nota(s)</small>
          <div>
            <button class="btn btn-sm btn-outline-secondary mr-2" :disabled="page === 1" @click="page--; reload()"><i class="fas fa-chevron-left"></i></button>
            <span class="small">Página {{ page }}</span>
            <button class="btn btn-sm btn-outline-secondary ml-2" :disabled="rows.length < pageSize" @click="page++; reload()"><i class="fas fa-chevron-right"></i></button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const router = useRouter()
const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const toast = useToast()

const dirOptions = [
  { v: 'all', label: 'Todas', icon: 'fa-layer-group' },
  { v: 'in', label: 'Entradas', icon: 'fa-arrow-down' },
  { v: 'out', label: 'Saídas', icon: 'fa-arrow-up' },
]
const direction = ref('all')
const filters = reactive({ cmig_id: null, status: null, date_from: null, date_to: null, search: null })
const rows = ref([])
const total = ref(0)
const loading = ref(false)
const page = ref(1)
const pageSize = 30
const sortBy = ref('emissao')
const sortDir = ref('desc')
const exporting = ref(null)
const syncing = ref(false)
const docLoading = reactive({})
const cmigs = ref([])

function buildParams() {
  const p = { direction: direction.value, page: page.value, page_size: pageSize, sort_by: sortBy.value, sort_dir: sortDir.value }
  for (const k of ['cmig_id', 'status', 'date_from', 'date_to', 'search']) {
    if (filters[k] !== null && filters[k] !== '') p[k] = filters[k]
  }
  return p
}

async function reload() {
  loading.value = true
  try {
    const { data } = await api.get('/invoices/notas', { params: buildParams() })
    rows.value = data.items || []
    total.value = data.total || 0
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar notas')
  } finally {
    loading.value = false
  }
}

function setDirection(v) { direction.value = v; page.value = 1; reload() }
function setSort(col) {
  if (sortBy.value === col) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortBy.value = col; sortDir.value = 'desc' }
  page.value = 1; reload()
}
function sortIcon(col) {
  if (sortBy.value !== col) return 'fa-sort text-muted'
  return sortDir.value === 'asc' ? 'fa-sort-up' : 'fa-sort-down'
}

async function downloadDoc(inv, kind) {
  if (kind === 'xml' && !inv.xml_available) { toast.warning('XML não disponível'); return }
  if (kind === 'danfe' && !inv.danfe_available && !inv.danfe_preview) { toast.warning('DANFE não disponível'); return }
  docLoading[inv.id] = kind
  try {
    // NF-e servida pelo backend (SEFAZ própria/upload): sem ml_invoice_id.
    // Faturador ML (ml_invoice_id preenchido): baixa via pedido.
    const own = !inv.ml_invoice_id
    const path = own
      ? `/invoices/${inv.id}/${kind}`
      : `/orders/${inv.order_id}/invoices/${inv.ml_invoice_id}/${kind}`
    const resp = await api.get(path, { responseType: 'blob' })
    const ext = kind === 'xml' ? 'xml' : 'pdf'
    const url = URL.createObjectURL(new Blob([resp.data], { type: kind === 'xml' ? 'application/xml' : 'application/pdf' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${kind === 'xml' ? 'NFe' : 'DANFE'}_${inv.access_key || inv.nfe_number || inv.id}.${ext}`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    let msg = 'Erro ao baixar documento'
    if (e.response?.data instanceof Blob) { try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* keep */ } }
    toast.error(msg)
  } finally {
    docLoading[inv.id] = null
  }
}

async function doExport(kind) {
  exporting.value = kind
  try {
    const { page: _p, page_size: _ps, sort_by, sort_dir, ...f } = buildParams()
    const resp = await api.get('/invoices/notas/export', { params: { ...f, kind }, responseType: 'blob' })
    const cd = resp.headers['content-disposition'] || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const url = URL.createObjectURL(new Blob([resp.data], { type: 'application/zip' }))
    const a = document.createElement('a')
    a.href = url
    a.download = m ? m[1] : `notas_${kind}.zip`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    let msg = 'Erro ao exportar'
    if (e.response?.data instanceof Blob) { try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* keep */ } }
    toast.error(msg)
  } finally {
    exporting.value = null
  }
}

async function doSync() {
  syncing.value = true
  try {
    const params = {}
    if (filters.cmig_id) params.cmig_id = filters.cmig_id
    const data = await fiscalStore.syncMlFiscal(params)
    toast.success(`Sincronização concluída${data?.created != null ? ` (${data.created} nota(s))` : ''}`)
    reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar')
  } finally {
    syncing.value = false
  }
}

function openDetail(inv) {
  if (inv.ml_invoice_id) return  // Faturador ML: sem página de detalhe própria
  router.push({ path: `/fiscal/invoices/${inv.id}`, query: { from: 'notas' } })
}

function statusLabel(s) {
  return ({ authorized: 'Autorizada', finalized: 'Finalizada', draft: 'Rascunho', rejected: 'Rejeitada', cancelled: 'Cancelada', processing: 'Processando' })[s] || s || '—'
}
function statusClass(s) {
  return ({ authorized: 'badge-success', finalized: 'badge-info', draft: 'badge-secondary', rejected: 'badge-danger', cancelled: 'badge-dark', processing: 'badge-warning text-dark' })[s] || 'badge-light'
}
function fmtDate(d) { if (!d) return '—'; try { return new Date(d).toLocaleDateString('pt-BR') } catch { return d } }
function fmtMoney(v) { if (v == null) return '—'; return 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }

onMounted(async () => {
  try {
    if (!cmigStore.cmigs?.length) await cmigStore.fetchCmigs()
    cmigs.value = cmigStore.cmigs || []
  } catch { /* segue sem lista */ }
  reload()
})
</script>
