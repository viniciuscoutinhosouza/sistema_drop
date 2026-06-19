<template>
  <div>
    <div class="content-header"><div class="container-fluid">
      <h1 class="m-0"><i class="fas fa-search-dollar mr-2 text-primary"></i>Análise de Concorrência</h1>
      <small class="text-muted">Estudo de mercado (Mercado Livre + IA) para um produto PG ou CMIG.</small>
    </div></div>

    <section class="content"><div class="container-fluid">
      <!-- Parâmetros -->
      <div class="card">
        <div class="card-body">
          <div class="row">
            <div class="col-md-4 form-group">
              <label class="small font-weight-bold">Conta de marketplace (ML)</label>
              <select v-model="accountId" class="form-control form-control-sm">
                <option :value="''">Selecione...</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">
                  {{ a.description || a.platform_username || ('Conta #'+a.id) }}
                </option>
              </select>
            </div>
            <div class="col-md-2 form-group">
              <label class="small font-weight-bold">Catálogo</label>
              <div class="btn-group btn-group-sm d-flex">
                <button class="btn" :class="source==='pg'?'btn-primary':'btn-outline-primary'" @click="setSource('pg')">PG</button>
                <button class="btn" :class="source==='cmig'?'btn-primary':'btn-outline-primary'" @click="setSource('cmig')" :disabled="!cmigId">CMIG</button>
              </div>
            </div>
            <div class="col-md-4 form-group">
              <label class="small font-weight-bold">Produto</label>
              <VariationProductPicker
                :source="source" :account-cmig-id="cmigId" v-model="product"
                placeholder="Buscar por título ou SKU..."
              />
              <div v-if="product" class="small text-success mt-1">
                <i class="fas fa-check mr-1"></i>{{ product.title }} ({{ product._sku }})
              </div>
            </div>
            <div class="col-md-2 form-group">
              <label class="small font-weight-bold">Margem desejada (%)</label>
              <input v-model.number="margin" type="number" step="0.1" min="0" class="form-control form-control-sm" />
            </div>
          </div>
          <div class="form-group mb-2">
            <label class="small font-weight-bold">Comentário / instrução para a IA (opcional)</label>
            <textarea v-model="userPrompt" rows="2" class="form-control form-control-sm"
              placeholder="Ex.: foco em margem alta; comparar só anúncios Premium; priorizar Full..."></textarea>
          </div>
          <button class="btn btn-primary" :disabled="!canRun || running" @click="startAnalysis">
            <i :class="running ? 'fas fa-spinner fa-spin' : 'fas fa-rocket'" class="mr-1"></i>
            {{ running ? 'Analisando…' : 'Analisar concorrência' }}
          </button>
          <span v-if="running" class="ml-3 text-muted small"><i class="fas fa-circle-notch fa-spin mr-1"></i>{{ progress }}</span>
          <span v-if="errorMsg" class="ml-3 text-danger small"><i class="fas fa-exclamation-triangle mr-1"></i>{{ errorMsg }}</span>
        </div>
      </div>

      <!-- Resultado -->
      <template v-if="study">
        <div class="row">
          <div class="col-md-8">
            <div class="card card-outline card-success">
              <div class="card-header"><h3 class="card-title">Recomendações do estudo</h3></div>
              <div class="card-body">
                <dl class="row mb-0">
                  <dt class="col-sm-3">Melhor título</dt>
                  <dd class="col-sm-9">
                    <strong>{{ study.best_title }}</strong>
                    <button class="btn btn-xs btn-outline-secondary ml-2" @click="copy(study.best_title)"><i class="fas fa-copy"></i></button>
                  </dd>
                  <dt class="col-sm-3">Modelo</dt><dd class="col-sm-9">{{ study.model_field || '—' }}</dd>
                  <dt class="col-sm-3">Melhor categoria</dt>
                  <dd class="col-sm-9">
                    <span v-if="study.best_category">{{ study.best_category.name }} <small class="text-muted">({{ study.best_category.id }})</small></span>
                    <div v-if="study.best_category?.path" class="small text-muted">{{ study.best_category.path }}</div>
                    <div v-if="study.best_category?.rationale" class="small text-muted">{{ study.best_category.rationale }}</div>
                  </dd>
                  <dt class="col-sm-3">Faixa de preço</dt>
                  <dd class="col-sm-9" v-if="study.price_range">
                    <div><span class="badge badge-info">Iniciante</span> {{ money(study.price_range.beginner?.min) }} – {{ money(study.price_range.beginner?.max) }}</div>
                    <div><span class="badge badge-success">Maduro</span> {{ money(study.price_range.mature?.min) }} – {{ money(study.price_range.mature?.max) }}</div>
                    <div class="small text-muted">{{ study.price_range.rationale }} <em v-if="study.price_range.margin_check">— {{ study.price_range.margin_check }}</em></div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="card card-outline card-warning">
              <div class="card-header"><h3 class="card-title">Ações p/ relevância</h3></div>
              <div class="card-body p-2">
                <ul class="mb-0 pl-3" style="font-size:13px">
                  <li v-for="(r,i) in (study.recommendations||[])" :key="i">{{ r }}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <!-- Previsão -->
        <div class="card" v-if="study.forecast">
          <div class="card-header"><h3 class="card-title">Previsão (estimativa)</h3></div>
          <div class="card-body p-0">
            <table class="table table-sm mb-0">
              <thead class="thead-light"><tr>
                <th>Janela</th><th class="text-center">Vendas (faixa)</th><th class="text-center">Visitas (faixa)</th>
                <th class="text-center">Lucro (faixa)</th><th class="text-center">Confiança</th>
              </tr></thead>
              <tbody>
                <tr v-for="w in ['7','14','30','60','90']" :key="w">
                  <td><strong>{{ w }} dias</strong></td>
                  <td class="text-center">{{ range(study.forecast[w]?.sales) }}</td>
                  <td class="text-center">{{ range(study.forecast[w]?.visits) }}</td>
                  <td class="text-center">{{ rangeMoney(study.forecast[w]?.profit) }}</td>
                  <td class="text-center"><span class="badge" :class="confColor(study.forecast[w]?.confidence)">{{ study.forecast[w]?.confidence || '—' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="card-footer small text-muted">{{ study.forecast.method_note }} {{ study.disclaimer }}</div>
        </div>

        <!-- Concorrentes -->
        <div class="card" v-if="(study.top_competitors||[]).length">
          <div class="card-header"><h3 class="card-title">Top concorrentes</h3></div>
          <div class="card-body p-0">
            <table class="table table-sm table-hover mb-0">
              <thead class="thead-light"><tr>
                <th>Anúncio</th><th>Título</th><th>Vendedor / Reput.</th><th class="text-center">Preço</th>
                <th class="text-center">Vendas</th><th class="text-center">Visitas</th><th>Tipo / Frete</th><th>Forças / Fraquezas</th>
              </tr></thead>
              <tbody>
                <tr v-for="c in study.top_competitors" :key="c.item_id">
                  <td>
                    <a v-if="compLink(c)" :href="compLink(c)" target="_blank" rel="noopener" title="Abrir anúncio no ML">
                      <small>{{ c.item_id }} <i class="fas fa-external-link-alt" style="font-size:9px"></i></small>
                    </a>
                    <small v-else>{{ c.item_id }}</small>
                  </td>
                  <td style="font-size:12px">{{ c.title }}</td>
                  <td><small>{{ c.seller }}<br><span class="text-muted">{{ c.reputation }}</span></small></td>
                  <td class="text-center">{{ money(c.price) }}</td>
                  <td class="text-center">{{ c.sold }}</td>
                  <td class="text-center">{{ c.visits }}</td>
                  <td><small>{{ c.listing_type }}<br>{{ c.shipping }}</small></td>
                  <td><small class="text-success">{{ c.strengths }}</small><br><small class="text-danger">{{ c.weaknesses }}</small></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Anotações -->
        <div class="card card-outline card-secondary" v-if="currentId">
          <div class="card-header"><h3 class="card-title">Minhas anotações (usadas em estudos futuros)</h3></div>
          <div class="card-body">
            <textarea v-model="notes" rows="3" class="form-control form-control-sm" placeholder="Anote conclusões/decisões deste estudo..."></textarea>
            <button class="btn btn-sm btn-secondary mt-2" @click="saveNotes"><i class="fas fa-save mr-1"></i>Salvar anotações</button>
          </div>
        </div>
      </template>

      <div v-else-if="rawResult" class="alert alert-warning">
        A IA não retornou um JSON válido. Resposta bruta:
        <pre class="mt-2 small" style="white-space:pre-wrap">{{ rawResult }}</pre>
      </div>

      <!-- Histórico -->
      <div class="card" v-if="history.length">
        <div class="card-header"><h3 class="card-title">Estudos anteriores deste produto</h3></div>
        <div class="card-body p-0">
          <table class="table table-sm mb-0">
            <thead class="thead-light"><tr><th>Data</th><th>Status</th><th>Anotações</th><th style="width:120px"></th></tr></thead>
            <tbody>
              <tr v-for="h in history" :key="h.id">
                <td><small>{{ fmtDate(h.created_at) }}</small></td>
                <td><span class="badge" :class="h.status==='done'?'badge-success':(h.status==='error'?'badge-danger':'badge-info')">{{ h.status }}</span></td>
                <td><small class="text-muted">{{ (h.notes||'').slice(0,80) }}</small></td>
                <td class="text-right">
                  <button class="btn btn-xs btn-outline-info mr-1" @click="openHistory(h.id)" title="Reabrir"><i class="fas fa-eye"></i></button>
                  <button class="btn btn-xs btn-outline-danger" @click="removeAnalysis(h.id)" title="Excluir"><i class="fas fa-trash"></i></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div></section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import VariationProductPicker from '@/components/catalog/VariationProductPicker.vue'

const toast = useToast()
const accounts = ref([])
const accountId = ref('')
const source = ref('pg')
const product = ref(null)
const margin = ref(30)
const userPrompt = ref('')

const running = ref(false)
const progress = ref('')
const errorMsg = ref('')
const currentId = ref(null)
const study = ref(null)
const rawResult = ref(null)
const compLinks = ref({})  // item_id -> permalink (fonte: ml_data dos concorrentes)
const notes = ref('')
const history = ref([])
let pollTimer = null

const selectedAccount = computed(() => accounts.value.find(a => a.id === accountId.value) || null)
const cmigId = computed(() => selectedAccount.value?.cmig_id ?? null)
const canRun = computed(() => !!accountId.value && !!product.value && margin.value >= 0)

function money(v) { return v != null ? formatCurrency(v) : '—' }
function range(arr) { return Array.isArray(arr) && arr.length === 2 ? `${arr[0]} – ${arr[1]}` : '—' }
function rangeMoney(arr) { return Array.isArray(arr) && arr.length === 2 ? `${money(arr[0])} – ${money(arr[1])}` : '—' }
function fmtDate(d) { return d ? formatDateTime(d) : '—' }
function confColor(c) { return c === 'alta' ? 'badge-success' : (c === 'media' ? 'badge-warning' : 'badge-secondary') }
function copy(t) { navigator.clipboard?.writeText(t || ''); toast.success('Copiado') }
function buildLinks(result) {
  const m = {}
  for (const c of (result?.ml_data?.competitors || [])) {
    if (c.item_id && c.permalink) m[String(c.item_id)] = c.permalink
  }
  compLinks.value = m
}
function compLink(c) { return c?.permalink || compLinks.value[String(c?.item_id)] || null }

function setSource(s) {
  if (s === 'cmig' && !cmigId.value) return
  source.value = s
  product.value = null
}

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    accounts.value = Array.isArray(data) ? data : []
    if (accounts.value.length === 1) accountId.value = accounts.value[0].id
  } catch { accounts.value = [] }
}

async function loadHistory() {
  if (!product.value) { history.value = []; return }
  try {
    const { data } = await api.get('/competitor-analysis', {
      params: { product_type: source.value, product_id: product.value.id },
    })
    history.value = Array.isArray(data) ? data : []
  } catch { history.value = [] }
}

async function startAnalysis() {
  if (!canRun.value) return
  running.value = true; errorMsg.value = ''; study.value = null; rawResult.value = null
  progress.value = 'Iniciando…'
  try {
    const { data } = await api.post('/competitor-analysis', {
      product_type: source.value,
      product_id: product.value.id,
      account_id: accountId.value,
      desired_margin_pct: margin.value,
      user_prompt: userPrompt.value || null,
    })
    currentId.value = data.id
    poll()
  } catch (e) {
    running.value = false
    errorMsg.value = e.response?.data?.detail || 'Erro ao iniciar a análise.'
  }
}

function poll() {
  clearInterval(pollTimer)
  pollTimer = setInterval(fetchStatus, 3000)
  fetchStatus()
}

async function fetchStatus() {
  if (!currentId.value) return
  try {
    const { data } = await api.get(`/competitor-analysis/${currentId.value}`)
    progress.value = data.progress_step || ''
    if (data.status === 'done') {
      clearInterval(pollTimer); running.value = false
      study.value = data.result?.study || null
      rawResult.value = data.result?.study_raw || null
      buildLinks(data.result)
      notes.value = data.notes || ''
      loadHistory()
    } else if (data.status === 'error') {
      clearInterval(pollTimer); running.value = false
      errorMsg.value = data.error || 'Falha na análise.'
    }
  } catch {
    clearInterval(pollTimer); running.value = false
    errorMsg.value = 'Erro ao consultar o status.'
  }
}

async function openHistory(id) {
  try {
    const { data } = await api.get(`/competitor-analysis/${id}`)
    currentId.value = id
    study.value = data.result?.study || null
    rawResult.value = data.result?.study_raw || null
    buildLinks(data.result)
    notes.value = data.notes || ''
    errorMsg.value = data.status === 'error' ? (data.error || '') : ''
  } catch { toast.error('Erro ao abrir o estudo.') }
}

async function saveNotes() {
  if (!currentId.value) return
  try {
    await api.patch(`/competitor-analysis/${currentId.value}`, { notes: notes.value })
    toast.success('Anotações salvas.')
    loadHistory()
  } catch { toast.error('Erro ao salvar anotações.') }
}

async function removeAnalysis(id) {
  if (!confirm('Excluir este estudo?')) return
  try {
    await api.delete(`/competitor-analysis/${id}`)
    if (currentId.value === id) { study.value = null; rawResult.value = null; currentId.value = null }
    toast.success('Estudo excluído.')
    loadHistory()
  } catch { toast.error('Erro ao excluir.') }
}

watch(product, () => { study.value = null; rawResult.value = null; currentId.value = null; loadHistory() })
onMounted(loadAccounts)
onBeforeUnmount(() => clearInterval(pollTimer))
</script>
