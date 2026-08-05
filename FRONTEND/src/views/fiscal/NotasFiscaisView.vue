<template>
  <div class="container-fluid py-3">
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap">
      <h4 class="mb-0"><i class="fas fa-file-invoice mr-2"></i>Notas Fiscais</h4>
      <div>
        <button class="btn btn-outline-secondary btn-sm mr-2" :disabled="exporting || direction === 'in'"
                :title="direction === 'in' ? 'Export em lote disponível p/ saídas' : 'Baixar XMLs (zip) das saídas filtradas'"
                @click="doExportXml">
          <i class="fas mr-1" :class="exporting ? 'fa-spinner fa-spin' : 'fa-file-code'"></i>Exportar XMLs (saídas)
        </button>
        <RouterLink to="/fiscal/invoices/new?direction=out" class="btn btn-primary btn-sm mr-2"><i class="fas fa-plus mr-1"></i>Nova saída</RouterLink>
        <RouterLink to="/fiscal/invoices/new?direction=in" class="btn btn-outline-primary btn-sm"><i class="fas fa-plus mr-1"></i>Nova entrada</RouterLink>
      </div>
    </div>

    <!-- Filtro de DIREÇÃO bem visível -->
    <div class="btn-group btn-group-toggle mb-3" role="group">
      <button v-for="opt in dirOptions" :key="opt.v" type="button"
              class="btn" :class="direction === opt.v ? 'btn-primary' : 'btn-outline-primary'"
              @click="setDirection(opt.v)">
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
            <input v-model="filters.search" class="form-control form-control-sm" placeholder="Número, chave, destinatário…"
                   @keyup.enter="reload">
          </div>
        </div>

        <div class="table-responsive">
          <table class="table table-sm table-hover" style="font-size:13px">
            <thead class="thead-light">
              <tr>
                <th>Emissão</th><th>NF</th><th>Direção</th><th>CMIG</th>
                <th>Contraparte</th><th>Natureza</th><th>Status</th><th class="text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading"><td colspan="8" class="text-center text-muted py-4"><i class="fas fa-spinner fa-spin mr-1"></i>Carregando…</td></tr>
              <tr v-else-if="!rows.length"><td colspan="8" class="text-center text-muted py-4"><i class="fas fa-inbox mr-1"></i>Nenhuma nota no filtro.</td></tr>
              <tr v-for="inv in rows" :key="(inv.direction || '') + '-' + inv.id" @click="openDetail(inv)" style="cursor:pointer">
                <td>{{ fmtDate(inv.issue_date || inv.emission_date || inv.created_at) }}</td>
                <td>
                  <span v-if="inv.nfe_number">{{ inv.nfe_number }}<span v-if="inv.serie" class="text-muted">/{{ inv.serie }}</span></span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td>
                  <span v-if="inv.direction === 'out'" class="badge badge-danger">Saída</span>
                  <span v-else class="badge badge-success">Entrada</span>
                </td>
                <td class="text-muted">{{ inv.cmig_name || inv.cmig || '' }}</td>
                <td>{{ inv.person_name || inv.recipient_name || inv.emitter_name || '—' }}</td>
                <td class="text-muted" style="max-width:220px;white-space:normal">{{ inv.natureza_operacao || '' }}</td>
                <td><span class="badge" :class="statusClass(inv.status)">{{ statusLabel(inv.status) }}</span></td>
                <td class="text-right" @click.stop>
                  <button class="btn btn-sm btn-outline-secondary mr-1" :disabled="!inv.xml_available && !inv.access_key"
                          title="Baixar XML" @click="downloadDoc(inv, 'xml')"><i class="fas fa-file-code"></i></button>
                  <button class="btn btn-sm btn-outline-secondary mr-1" :disabled="!inv.danfe_available && inv.status !== 'authorized'"
                          title="Baixar DANFE" @click="downloadDoc(inv, 'danfe')"><i class="fas fa-file-pdf"></i></button>
                  <button v-if="inv.source !== 'ml'" class="btn btn-sm btn-outline-info" title="Detalhes" @click="openDetail(inv)"><i class="fas fa-eye"></i></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="d-flex justify-content-between align-items-center">
          <small class="text-muted">{{ total }} nota(s){{ direction === 'all' ? ' (entradas + saídas)' : '' }}</small>
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
const exporting = ref(false)
const cmigs = ref([])

function buildParams(dir) {
  const p = { page: page.value, page_size: pageSize }
  for (const k of ['cmig_id', 'status', 'date_from', 'date_to', 'search']) {
    if (filters[k] !== null && filters[k] !== '') p[k] = filters[k]
  }
  if (dir === 'in') p.direction = 'in'
  return p
}

// Ordena por (série, número) desc para manter a sequência fiscal ao juntar direções.
function sortSeq(list) {
  return [...list].sort((a, b) => (b.serie || 0) - (a.serie || 0) || (b.nfe_number || 0) - (a.nfe_number || 0))
}

async function reload() {
  loading.value = true
  try {
    if (direction.value === 'out') {
      const d = await fiscalStore.fetchOutbound(buildParams())
      rows.value = (d.items || []).map(r => ({ ...r, direction: 'out' }))
      total.value = d.total || 0
    } else if (direction.value === 'in') {
      const d = await fiscalStore.fetchInvoices(buildParams('in'))
      rows.value = (d.items || []).map(r => ({ ...r, direction: 'in' }))
      total.value = d.total || 0
    } else {
      // Todas: junta as duas fontes (a NFe-out inclui o merge do Faturador ML)
      const [out, inb] = await Promise.all([
        fiscalStore.fetchOutbound(buildParams()),
        fiscalStore.fetchInvoices(buildParams('in')),
      ])
      const merged = [
        ...(out.items || []).map(r => ({ ...r, direction: 'out' })),
        ...(inb.items || []).map(r => ({ ...r, direction: 'in' })),
      ]
      rows.value = sortSeq(merged)
      total.value = (out.total || 0) + (inb.total || 0)
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar notas')
  } finally {
    loading.value = false
  }
}

function setDirection(v) { direction.value = v; page.value = 1; reload() }

async function doExportXml() {
  exporting.value = true
  try {
    const { page: _p, page_size: _ps, ...f } = buildParams()
    await fiscalStore.exportOutbound('xml', f)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao exportar')
  } finally {
    exporting.value = false
  }
}

async function downloadDoc(inv, kind) {
  try {
    const path = kind === 'xml' ? `/invoices/${inv.id}/xml` : `/invoices/${inv.id}/danfe`
    const resp = await api.get(path, { responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([resp.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `${kind === 'xml' ? 'nfe' : 'danfe'}_${inv.nfe_number || inv.id}.${kind === 'xml' ? 'xml' : 'pdf'}`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Documento indisponível')
  }
}

function openDetail(inv) {
  if (inv.source === 'ml') return  // nota só do cache ML ainda não materializada
  router.push(`/fiscal/invoices/${inv.id}`)
}

function statusLabel(s) {
  return ({ authorized: 'Autorizada', finalized: 'Finalizada', draft: 'Rascunho', rejected: 'Rejeitada', cancelled: 'Cancelada', processing: 'Processando' })[s] || s || '—'
}
function statusClass(s) {
  return ({ authorized: 'badge-success', finalized: 'badge-info', draft: 'badge-secondary', rejected: 'badge-danger', cancelled: 'badge-dark', processing: 'badge-warning text-dark' })[s] || 'badge-light'
}
function fmtDate(d) {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString('pt-BR') } catch { return d }
}

onMounted(async () => {
  try {
    if (!cmigStore.cmigs?.length) await cmigStore.fetchCmigs()
    cmigs.value = cmigStore.cmigs || []
  } catch { /* segue sem a lista de CMIGs */ }
  reload()
})
</script>
