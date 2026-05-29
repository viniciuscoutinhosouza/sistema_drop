<template>
  <div class="container-fluid">
    <!-- Filtros -->
    <div class="card mb-3">
      <div class="card-header">
        <h3 class="card-title"><i class="fas fa-clock mr-2"></i>Monitoramento de Rotinas Automatizadas</h3>
        <div class="card-tools d-flex gap-2 flex-wrap">
          <div class="btn-group btn-group-sm" role="group">
            <button class="btn btn-outline-secondary" :class="{ active: preset === '3h' }" @click="applyPreset('3h')">Últimas 3h</button>
            <button class="btn btn-outline-secondary" :class="{ active: preset === '24h' }" @click="applyPreset('24h')">24h</button>
            <button class="btn btn-outline-secondary" :class="{ active: preset === '7d' }" @click="applyPreset('7d')">7 dias</button>
          </div>
          <input v-model="dateFromInput" type="datetime-local" class="form-control form-control-sm" style="width:200px" />
          <input v-model="dateToInput"   type="datetime-local" class="form-control form-control-sm" style="width:200px" />
          <select v-model="filters.job_id" class="form-control form-control-sm" style="width:220px">
            <option value="">Todas as rotinas</option>
            <option v-for="j in jobs" :key="j.job_id" :value="j.job_id">{{ j.name }}</option>
          </select>
          <select v-model="filters.status" class="form-control form-control-sm" style="width:140px">
            <option value="">Todos os status</option>
            <option value="success">Sucesso</option>
            <option value="failed">Falha</option>
            <option value="running">Em execução</option>
          </select>
          <button class="btn btn-sm btn-primary" @click="refreshAll" :disabled="loading">
            <i class="fas" :class="loading ? 'fa-spinner fa-spin' : 'fa-sync-alt'"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Cards por rotina -->
    <div class="row">
      <div v-for="j in jobs" :key="j.job_id" class="col-lg-6 col-xl-4 mb-3">
        <div class="card h-100">
          <div class="card-header py-2">
            <div class="d-flex justify-content-between align-items-start">
              <div>
                <strong>{{ j.name }}</strong>
                <div class="text-muted small">{{ j.schedule }}</div>
              </div>
              <span class="badge" :class="successBadgeClass(j.success_rate)">
                {{ j.success_rate !== null ? j.success_rate + '%' : '—' }}
              </span>
            </div>
          </div>
          <div class="card-body py-2">
            <div class="row text-center small">
              <div class="col-4">
                <div class="text-muted">Execuções</div>
                <strong>{{ j.executions_in_period }}</strong>
              </div>
              <div class="col-4">
                <div class="text-muted">Falhas</div>
                <strong :class="{ 'text-danger': j.failures > 0 }">{{ j.failures }}</strong>
              </div>
              <div class="col-4">
                <div class="text-muted">Duração méd.</div>
                <strong>{{ formatDuration(j.avg_duration_ms) }}</strong>
              </div>
            </div>
            <hr class="my-2">
            <div class="small">
              <div>
                <span class="text-muted">Última execução:</span>
                <span v-if="j.last_run">
                  <span class="badge mr-1" :class="statusBadgeClass(j.last_run.status)">{{ j.last_run.status }}</span>
                  {{ formatRelative(j.last_run.started_at) }}
                </span>
                <span v-else class="text-muted">sem execução no período</span>
              </div>
              <div>
                <span class="text-muted">Próxima execução:</span>
                <span v-if="j.next_run_at">{{ formatAbsolute(j.next_run_at) }} <span class="text-muted">({{ formatRelative(j.next_run_at, true) }})</span></span>
                <span v-else class="text-muted">—</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Tabela de execuções -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Histórico de Execuções</h3>
        <div class="card-tools">
          <span class="badge badge-info">{{ executionsTotal }} resultado(s)</span>
        </div>
      </div>
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-sm table-hover mb-0">
            <thead class="thead-light">
              <tr>
                <th>Rotina</th>
                <th>Início</th>
                <th>Duração</th>
                <th>Status</th>
                <th>Resultado</th>
                <th>Origem</th>
                <th class="text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!executions.length">
                <td colspan="7" class="text-center text-muted py-3">Sem execuções no período.</td>
              </tr>
              <tr v-for="ex in executions" :key="ex.id">
                <td>{{ jobNameById(ex.job_id) }}</td>
                <td>{{ formatAbsolute(ex.started_at) }}</td>
                <td>{{ formatDuration(ex.duration_ms) }}</td>
                <td><span class="badge" :class="statusBadgeClass(ex.status)">{{ ex.status }}</span></td>
                <td class="small">{{ shortResult(ex.result) }}</td>
                <td><span class="badge badge-light">{{ ex.triggered_by || 'scheduler' }}</span></td>
                <td class="text-right">
                  <button class="btn btn-xs btn-outline-secondary" @click="openDetail(ex)">
                    <i class="fas fa-eye"></i>
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card-footer d-flex justify-content-between align-items-center">
        <small class="text-muted">Página {{ page }} de {{ totalPages }}</small>
        <div class="btn-group btn-group-sm">
          <button class="btn btn-outline-secondary" :disabled="page <= 1" @click="page = page - 1; loadExecutions()">
            <i class="fas fa-angle-left"></i>
          </button>
          <button class="btn btn-outline-secondary" :disabled="page >= totalPages" @click="page = page + 1; loadExecutions()">
            <i class="fas fa-angle-right"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Modal de detalhe -->
    <div v-if="selected" class="modal fade show" style="display:block; background:rgba(0,0,0,0.45);" @click.self="selected = null">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Execução #{{ selected.id }} — {{ jobNameById(selected.job_id) }}</h5>
            <button type="button" class="close" @click="selected = null"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="row mb-3">
              <div class="col-md-4"><strong>Início:</strong> {{ formatAbsolute(selected.started_at) }}</div>
              <div class="col-md-4"><strong>Fim:</strong> {{ selected.finished_at ? formatAbsolute(selected.finished_at) : '—' }}</div>
              <div class="col-md-4"><strong>Duração:</strong> {{ formatDuration(selected.duration_ms) }}</div>
            </div>
            <div class="row mb-3">
              <div class="col-md-4"><strong>Status:</strong> <span class="badge" :class="statusBadgeClass(selected.status)">{{ selected.status }}</span></div>
              <div class="col-md-4"><strong>Origem:</strong> {{ selected.triggered_by || 'scheduler' }}</div>
            </div>
            <div class="mb-3">
              <strong>Indicadores (result_json):</strong>
              <pre class="bg-light p-2 small mt-1" style="max-height:240px; overflow:auto;">{{ JSON.stringify(detail?.result || selected.result, null, 2) }}</pre>
            </div>
            <div v-if="detail?.error_message || selected.error_message">
              <strong class="text-danger">Erro:</strong>
              <pre class="bg-light p-2 small mt-1 text-danger" style="max-height:260px; overflow:auto;">{{ detail?.error_message || selected.error_message }}</pre>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="selected = null">Fechar</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, computed, watch } from 'vue'
import { formatDistanceToNow, format, parseISO } from 'date-fns'
import { ptBR } from 'date-fns/locale'
import api from '@/composables/useApi'

const preset = ref('3h')
const dateFromInput = ref('')
const dateToInput = ref('')
const filters = ref({ job_id: '', status: '' })

const jobs = ref([])
const executions = ref([])
const executionsTotal = ref(0)
const page = ref(1)
const size = ref(50)
const totalPages = computed(() => Math.max(1, Math.ceil(executionsTotal.value / size.value)))

const selected = ref(null)
const detail = ref(null)
const loading = ref(false)

let refreshTimer = null

function applyPreset(p) {
  preset.value = p
  const now = new Date()
  let from
  if (p === '3h') from = new Date(now.getTime() - 3 * 60 * 60 * 1000)
  else if (p === '24h') from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
  else if (p === '7d') from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
  dateFromInput.value = toLocalInputValue(from)
  dateToInput.value = toLocalInputValue(now)
  page.value = 1
  refreshAll()
}

function toLocalInputValue(d) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromLocalInputValue(s) {
  if (!s) return null
  return new Date(s).toISOString()
}

async function loadJobs() {
  try {
    // Calcula hours a partir do range; default 3
    let hours = 3
    if (dateFromInput.value) {
      const from = new Date(dateFromInput.value)
      const to = dateToInput.value ? new Date(dateToInput.value) : new Date()
      hours = Math.max(1, Math.round((to - from) / 36e5))
    }
    const { data } = await api.get('/scheduler/jobs', { params: { hours } })
    jobs.value = data.jobs || []
  } catch (e) {
    console.error('Erro ao carregar jobs', e)
  }
}

async function loadExecutions() {
  try {
    const params = { page: page.value, size: size.value }
    if (dateFromInput.value) params.date_from = fromLocalInputValue(dateFromInput.value)
    if (dateToInput.value)   params.date_to   = fromLocalInputValue(dateToInput.value)
    if (filters.value.job_id) params.job_id = filters.value.job_id
    if (filters.value.status) params.status = filters.value.status
    const { data } = await api.get('/scheduler/executions', { params })
    executions.value = data.items || []
    executionsTotal.value = data.total || 0
  } catch (e) {
    console.error('Erro ao carregar execuções', e)
  }
}

async function refreshAll() {
  loading.value = true
  await Promise.all([loadJobs(), loadExecutions()])
  loading.value = false
}

async function openDetail(ex) {
  selected.value = ex
  detail.value = null
  try {
    const { data } = await api.get(`/scheduler/executions/${ex.id}`)
    detail.value = data
  } catch (e) {
    console.error('Erro ao carregar detalhe', e)
  }
}

function jobNameById(jid) {
  const j = jobs.value.find((x) => x.job_id === jid)
  return j ? j.name : jid
}

function statusBadgeClass(s) {
  if (s === 'success') return 'badge-success'
  if (s === 'failed') return 'badge-danger'
  if (s === 'running') return 'badge-warning'
  return 'badge-secondary'
}

function successBadgeClass(rate) {
  if (rate === null || rate === undefined) return 'badge-secondary'
  if (rate >= 95) return 'badge-success'
  if (rate >= 80) return 'badge-warning'
  return 'badge-danger'
}

function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  return `${(ms / 60000).toFixed(1)} min`
}

function formatRelative(iso, addPrefix = false) {
  if (!iso) return '—'
  try {
    const d = typeof iso === 'string' ? parseISO(iso) : iso
    const out = formatDistanceToNow(d, { locale: ptBR, addSuffix: true })
    return addPrefix ? `em ${out.replace(/^(há|em)\s+/, '')}` : out
  } catch {
    return iso
  }
}

function formatAbsolute(iso) {
  if (!iso) return '—'
  try {
    const d = typeof iso === 'string' ? parseISO(iso) : iso
    return format(d, 'dd/MM HH:mm:ss', { locale: ptBR })
  } catch {
    return iso
  }
}

function shortResult(result) {
  if (!result || typeof result !== 'object') return '—'
  const entries = Object.entries(result).filter(([k]) => k !== 'order_id' && k !== 'platform')
  if (!entries.length) return '—'
  return entries.slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')
}

watch(() => filters.value.job_id, () => { page.value = 1; loadExecutions() })
watch(() => filters.value.status, () => { page.value = 1; loadExecutions() })
watch(dateFromInput, () => { page.value = 1 })
watch(dateToInput,   () => { page.value = 1 })

onMounted(() => {
  applyPreset('3h')
  refreshTimer = setInterval(refreshAll, 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.btn-xs {
  padding: 0.125rem 0.375rem;
  font-size: 0.75rem;
}
.gap-2 > * + * {
  margin-left: 0.5rem;
}
</style>
