<template>
  <div class="content-header">
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-8">
          <h1 class="m-0">
            <i class="fas fa-terminal mr-2 text-primary"></i>
            Console de API — {{ provider === 'eship' ? 'eShip (WMS)' : 'Marketplace' }}
          </h1>
          <small class="text-muted">
            <template v-if="provider === 'eship'">
              Executa funções RPC do eShip usando as credenciais configuradas da CMIG.
            </template>
            <template v-else>
              Executa requests diretas à API do ML usando o token da conta selecionada.
            </template>
            <span class="badge badge-danger ml-1">Admin only</span>
          </small>
        </div>
      </div>
    </div>
  </div>

  <section class="content">
    <div class="container-fluid">

      <!-- Comutador de provider -->
      <div class="btn-group btn-group-sm mb-3">
        <button type="button" :class="['btn', provider === 'ml' ? 'btn-primary' : 'btn-outline-primary']"
                @click="setProvider('ml')">
          <i class="fas fa-store mr-1"></i>Mercado Livre
        </button>
        <button type="button" :class="['btn', provider === 'eship' ? 'btn-warning' : 'btn-outline-warning']"
                @click="setProvider('eship')">
          <i class="fas fa-dolly-flatbed mr-1"></i>eShip
        </button>
      </div>

      <!-- Aviso: conta ML sem autorização -->
      <div v-if="provider === 'ml' && selectedAccount && selectedAccount.requires_reauth"
           class="alert alert-warning py-2 mb-3">
        <i class="fas fa-exclamation-triangle mr-1"></i>
        A conta <strong>{{ selectedAccountLabel }}</strong> precisa ser reconectada em
        <RouterLink to="/integrations">Integrações</RouterLink>. As requests vão falhar com 401.
      </div>

      <div class="row">

        <!-- ══ Coluna esquerda: Request ══ -->
        <div class="col-lg-6">

          <!-- ── Request Mercado Livre ── -->
          <div v-if="provider === 'ml'" class="card card-outline card-primary mb-3">
            <div class="card-header py-2"><strong><i class="fas fa-paper-plane mr-1"></i>Request</strong></div>
            <div class="card-body">

              <div class="form-group">
                <label class="font-weight-bold">
                  Conta de Marketplace <span class="text-danger">*</span>
                  <span class="text-muted ml-1 small">({{ accounts.length }} disponível(is))</span>
                </label>
                <select v-model="form.account_id" class="form-control form-control-sm">
                  <option value="">Selecione...</option>
                  <option v-for="a in accounts" :key="a.id" :value="a.id">
                    {{ a.platform_label }} — {{ a.description || a.platform_username || a.email || '(sem nome)' }}
                  </option>
                </select>
                <small v-if="accountsLoadError" class="text-danger d-block">
                  <i class="fas fa-exclamation-triangle mr-1"></i>{{ accountsLoadError }}
                </small>
                <small v-else-if="!accounts.length" class="text-muted d-block">
                  Nenhuma conta de marketplace cadastrada no sistema.
                </small>
                <small v-if="selectedAccount && selectedAccount.platform !== 'mercadolivre'" class="text-danger d-block">
                  Plataforma <strong>{{ selectedAccount.platform }}</strong> ainda não suportada (só Mercado Livre na v1 do Console).
                </small>
              </div>

              <div class="form-row">
                <div class="form-group col-md-3">
                  <label class="font-weight-bold">Método <span class="text-danger">*</span></label>
                  <select v-model="form.method" class="form-control form-control-sm">
                    <option v-for="m in METHODS" :key="m" :value="m">{{ m }}</option>
                  </select>
                </div>
                <div class="form-group col-md-9">
                  <label class="font-weight-bold">Path <span class="text-danger">*</span></label>
                  <div class="input-group input-group-sm">
                    <div class="input-group-prepend">
                      <span class="input-group-text text-monospace small">{{ BASE_URL }}</span>
                    </div>
                    <input v-model="form.path" type="text" class="form-control text-monospace"
                           placeholder="/users/me" @keyup.ctrl.enter="execute" />
                  </div>
                </div>
              </div>

              <div class="form-group">
                <label class="font-weight-bold small text-muted">Templates rápidos:</label>
                <div class="d-flex flex-wrap" style="gap:4px">
                  <button v-for="t in TEMPLATES" :key="t.label" type="button"
                          class="btn btn-sm btn-outline-secondary" @click="applyTemplate(t)">
                    {{ t.label }}
                  </button>
                </div>
              </div>

              <div class="form-group">
                <label class="font-weight-bold">Query params</label>
                <div v-for="(qp, i) in form.query" :key="`q-${i}`" class="input-group input-group-sm mb-1">
                  <input v-model="qp.key" type="text" class="form-control" placeholder="parâmetro" />
                  <input v-model="qp.value" type="text" class="form-control" placeholder="valor" />
                  <div class="input-group-append">
                    <button class="btn btn-outline-danger" @click="form.query.splice(i,1)" title="Remover">
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                </div>
                <button type="button" class="btn btn-sm btn-link p-0" @click="form.query.push({key:'',value:''})">
                  <i class="fas fa-plus mr-1"></i>Adicionar parâmetro
                </button>
              </div>

              <div class="form-group">
                <label class="font-weight-bold">
                  Headers extras
                  <small class="text-muted ml-2">(Authorization é injetado automaticamente)</small>
                </label>
                <div v-for="(h, i) in form.headers" :key="`h-${i}`" class="input-group input-group-sm mb-1">
                  <input v-model="h.key" type="text" class="form-control text-monospace" placeholder="Content-Type" />
                  <input v-model="h.value" type="text" class="form-control text-monospace" placeholder="application/json" />
                  <div class="input-group-append">
                    <button class="btn btn-outline-danger" @click="form.headers.splice(i,1)" title="Remover">
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                </div>
                <button type="button" class="btn btn-sm btn-link p-0" @click="form.headers.push({key:'',value:''})">
                  <i class="fas fa-plus mr-1"></i>Adicionar header
                </button>
              </div>

              <div v-if="methodAllowsBody" class="form-group">
                <label class="font-weight-bold">Body (JSON)</label>
                <textarea v-model="form.body_text" class="form-control text-monospace"
                          rows="8" placeholder='{"key": "value"}' style="font-size:12px"></textarea>
                <small v-if="bodyParseError" class="text-danger">
                  <i class="fas fa-exclamation-triangle mr-1"></i>JSON inválido: {{ bodyParseError }}
                </small>
              </div>

              <div class="text-right">
                <button class="btn btn-primary" @click="execute" :disabled="!canSubmit || sending">
                  <i :class="['fas', sending ? 'fa-spinner fa-spin' : 'fa-paper-plane', 'mr-1']"></i>
                  {{ sending ? 'Enviando...' : 'Enviar (Ctrl+Enter)' }}
                </button>
              </div>

              <div v-if="execError" class="alert alert-danger py-2 mt-2 small mb-0">
                <i class="fas fa-times-circle mr-1"></i>{{ execError }}
              </div>
            </div>
          </div>

          <!-- ── Request eShip (WMS) ── -->
          <div v-else class="card card-outline card-warning mb-3">
            <div class="card-header py-2"><strong><i class="fas fa-dolly-flatbed mr-1"></i>Request eShip (WMS)</strong></div>
            <div class="card-body">

              <div class="form-group">
                <label class="font-weight-bold">
                  Empresa (CMIG) <span class="text-danger">*</span>
                  <span class="text-muted ml-1 small">({{ eshipCmigs.length }} disponível(is))</span>
                </label>
                <select v-model="eshipForm.cmig_id" class="form-control form-control-sm">
                  <option value="">Selecione...</option>
                  <option v-for="c in eshipCmigs" :key="c.cmig_id" :value="c.cmig_id" :disabled="!c.eship_configured">
                    {{ c.company_name || '(sem nome)' }}{{ c.eship_configured ? '' : ' — eShip não configurado' }}
                  </option>
                </select>
                <small v-if="eshipCmigsError" class="text-danger d-block">
                  <i class="fas fa-exclamation-triangle mr-1"></i>{{ eshipCmigsError }}
                </small>
                <small v-else-if="selectedCmig" class="text-muted d-block text-monospace">
                  {{ selectedCmig.eship_base_url || '(sem base_url)' }} · armazém: {{ selectedCmig.eship_warehouse_code || '—' }}
                  <span :class="['badge ml-1', selectedCmig.eship_active ? 'badge-success' : 'badge-secondary']">
                    {{ selectedCmig.eship_active ? 'ativo' : 'inativo' }}
                  </span>
                </small>
              </div>

              <div class="form-group">
                <label class="font-weight-bold">
                  Função <span class="text-danger">*</span>
                  <span class="text-muted ml-1 small">({{ eshipFnCount }} funções da API)</span>
                </label>
                <select v-model="eshipForm.funcao" class="form-control form-control-sm text-monospace"
                        @change="onEshipFuncaoChange">
                  <option value="">Selecione a função...</option>
                  <optgroup v-for="mod in eshipModules" :key="mod.name" :label="mod.name">
                    <option v-for="fn in mod.fns" :key="fn.f" :value="fn.f">
                      {{ fn.f }}{{ fn.v !== 'GET' ? '  [' + fn.v + ']' : '' }}
                    </option>
                  </optgroup>
                </select>
              </div>

              <!-- Parâmetros do body da função selecionada -->
              <details v-if="selectedEshipFn && selectedEshipFn.params.length" class="form-group" open>
                <summary class="small font-weight-bold text-muted" style="cursor:pointer">
                  Parâmetros do body ({{ selectedEshipFn.params.length }}) —
                  {{ selectedEshipFn.req.length }} obrigatório(s)
                  <button type="button" class="btn btn-xs btn-link p-0 ml-2" @click.prevent="fillTemplate">
                    <i class="fas fa-magic mr-1"></i>preencher template
                  </button>
                </summary>
                <div style="max-height:200px;overflow:auto" class="border rounded mt-1">
                  <table class="table table-sm table-hover mb-0 small">
                    <thead class="text-muted">
                      <tr><th>Campo</th><th>Tipo</th><th></th><th>Descrição</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="p in selectedEshipFn.params" :key="p.n">
                        <td class="text-monospace">{{ p.n }}</td>
                        <td><span class="badge badge-light">{{ p.t || '?' }}</span></td>
                        <td><span v-if="p.r" class="badge badge-danger">obrig.</span></td>
                        <td class="text-muted">{{ p.d }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </details>

              <div class="form-group">
                <label class="font-weight-bold">Body (JSON) <small class="text-muted ml-1">— objeto de parâmetros da função</small></label>
                <textarea v-model="eshipForm.body_text" class="form-control text-monospace"
                          rows="8" placeholder='{"pagina": 1, "quantidadeRegistros": 25}' style="font-size:12px"></textarea>
                <small v-if="eshipBodyParseError" class="text-danger">
                  <i class="fas fa-exclamation-triangle mr-1"></i>JSON inválido: {{ eshipBodyParseError }}
                </small>
              </div>

              <div class="form-group">
                <label class="font-weight-bold">
                  Headers extras
                  <small class="text-muted ml-2">(o header <code>api</code> com a apikey é injetado automaticamente)</small>
                </label>
                <div v-for="(h, i) in eshipForm.headers" :key="`eh-${i}`" class="input-group input-group-sm mb-1">
                  <input v-model="h.key" type="text" class="form-control text-monospace" placeholder="Header" />
                  <input v-model="h.value" type="text" class="form-control text-monospace" placeholder="valor" />
                  <div class="input-group-append">
                    <button class="btn btn-outline-danger" @click="eshipForm.headers.splice(i,1)" title="Remover">
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                </div>
                <button type="button" class="btn btn-sm btn-link p-0" @click="eshipForm.headers.push({key:'',value:''})">
                  <i class="fas fa-plus mr-1"></i>Adicionar header
                </button>
              </div>

              <!-- Guarda para operações de escrita no WMS de produção -->
              <div v-if="eshipIsWrite" class="alert alert-warning py-2 small">
                <label class="mb-0" style="cursor:pointer">
                  <input type="checkbox" v-model="eshipWriteConfirmed" class="mr-1" />
                  Entendo que <strong>{{ eshipForm.funcao }}</strong> é uma operação de
                  <strong>ESCRITA no WMS de produção</strong> (pode criar/alterar ordens e estoque físico).
                </label>
              </div>

              <div class="text-right">
                <button class="btn btn-warning" @click="executeEship" :disabled="!canSubmitEship || sending">
                  <i :class="['fas', sending ? 'fa-spinner fa-spin' : 'fa-paper-plane', 'mr-1']"></i>
                  {{ sending ? 'Enviando...' : 'Enviar (Ctrl+Enter)' }}
                </button>
              </div>

              <div v-if="execError" class="alert alert-danger py-2 mt-2 small mb-0">
                <i class="fas fa-times-circle mr-1"></i>{{ execError }}
              </div>
            </div>
          </div>
        </div>

        <!-- ══ Coluna direita: Response (compartilhada) ══ -->
        <div class="col-lg-6">
          <div class="card card-outline card-secondary mb-3">
            <div class="card-header py-2 d-flex align-items-center" style="gap:8px">
              <strong><i class="fas fa-reply mr-1"></i>Response</strong>
              <template v-if="response">
                <span :class="['badge', statusBadgeClass(response.status)]">
                  HTTP {{ response.status }}
                </span>
                <span class="text-muted small">{{ response.elapsed_ms }} ms</span>
                <button class="btn btn-sm btn-outline-secondary ml-auto" @click="copyResponseBody"
                        :disabled="!response">
                  <i class="fas fa-copy mr-1"></i>Copiar body
                </button>
              </template>
              <span v-else class="text-muted small">Aguardando primeira request...</span>
            </div>
            <div class="card-body p-0">
              <template v-if="response">
                <div class="px-3 py-2 border-bottom text-muted small text-monospace text-truncate"
                     :title="response.request_url">
                  → {{ response.request_url }}
                </div>

                <!-- Erro de negócio do eShip (HTTP 200 + campo `erros`) -->
                <div v-if="responseErros.length" class="alert alert-danger py-2 m-2 small">
                  <i class="fas fa-times-circle mr-1"></i><strong>Erro eShip:</strong>
                  <span v-for="(e, i) in responseErros" :key="i">
                    {{ e }}<span v-if="i < responseErros.length - 1"> · </span>
                  </span>
                </div>

                <details class="border-bottom">
                  <summary class="px-3 py-2 small font-weight-bold" style="cursor:pointer;background:#f8f9fa">
                    Headers do response ({{ Object.keys(response.response_headers || {}).length }})
                  </summary>
                  <div class="px-3 py-2" style="max-height:160px;overflow:auto">
                    <div v-for="(v, k) in response.response_headers" :key="k" class="small text-monospace">
                      <strong>{{ k }}:</strong> {{ v }}
                    </div>
                  </div>
                </details>

                <div class="px-3 py-2 small font-weight-bold" style="background:#f8f9fa">Body</div>
                <pre class="m-0 px-3 py-2" style="background:#1e1e1e;color:#d4d4d4;font-size:12px;max-height:600px;overflow:auto;white-space:pre-wrap;word-break:break-all">{{ formattedResponseBody }}</pre>
              </template>
              <div v-else class="p-4 text-center text-muted small">
                <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
                Envie uma request pra ver a resposta aqui.
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import eshipCatalog from './eshipCatalog.json'

const provider = ref('ml')

// Catálogo completo das funções do eShip (gerado do swagger oficial) — estático.
const ESHIP_MODULE_ORDER = [
  'Ordem', 'Produto', 'Armazem', 'Cadastro', 'Transporte',
  'Recebimento', 'Inventario', 'Usuario', 'Sistema', 'Precificacao', 'Requisicao',
]
const eshipModules = ESHIP_MODULE_ORDER
  .filter(m => (eshipCatalog[m] || []).length)
  .map(m => ({ name: m, fns: eshipCatalog[m] }))
const eshipFnByName = {}
for (const m of Object.keys(eshipCatalog)) {
  for (const fn of eshipCatalog[m]) eshipFnByName[fn.f] = fn
}
const eshipFnCount = Object.keys(eshipFnByName).length

// ─────────────── Mercado Livre ───────────────
const BASE_URL = 'https://api.mercadolibre.com'
const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']

const TEMPLATES = [
  { label: 'GET /users/me', method: 'GET', path: '/users/me', body: null },
  { label: 'GET /items/{id}', method: 'GET', path: '/items/MLB00000000', body: null },
  { label: 'GET /sites/MLB/categories', method: 'GET', path: '/sites/MLB/categories', body: null },
  { label: 'PUT /items/{id}', method: 'PUT', path: '/items/MLB00000000', body: { status: 'paused' } },
]

const accounts = ref([])
const form = reactive({
  account_id: '',
  method: 'GET',
  path: '/users/me',
  query: [],
  headers: [],
  body_text: '',
})

// ─────────────── eShip ───────────────
const eshipCmigs = ref([])
const eshipCmigsError = ref('')
const eshipForm = reactive({
  cmig_id: '',
  funcao: 'webServiceGetProduto',
  body_text: JSON.stringify({ pagina: 1, quantidadeRegistros: 25 }, null, 2),
  headers: [],
})
const eshipWriteConfirmed = ref(false)
const selectedEshipFn = computed(() => eshipFnByName[eshipForm.funcao] || null)

// ─────────────── Compartilhado ───────────────
const sending = ref(false)
const response = ref(null)
const execError = ref('')

// ── ML computeds ──
const selectedAccount = computed(() => accounts.value.find(a => a.id === form.account_id) || null)
const selectedAccountLabel = computed(() => {
  const a = selectedAccount.value
  return a ? `${a.platform_label} — ${a.description || a.platform_username || a.email}` : ''
})
const methodAllowsBody = computed(() => ['POST', 'PUT', 'PATCH', 'DELETE'].includes(form.method))
const bodyParseError = ref('')
const parsedBody = computed(() => {
  bodyParseError.value = ''
  const txt = (form.body_text || '').trim()
  if (!txt) return null
  try { return JSON.parse(txt) } catch (e) { bodyParseError.value = e.message; return undefined }
})
const canSubmit = computed(() =>
  !!form.account_id
  && !!form.method
  && !!form.path.trim()
  && (selectedAccount.value?.platform === 'mercadolivre')
  && (!methodAllowsBody.value || !form.body_text.trim() || parsedBody.value !== undefined)
)

// ── eShip computeds ──
const selectedCmig = computed(() => eshipCmigs.value.find(c => c.cmig_id === eshipForm.cmig_id) || null)
const eshipBodyParseError = ref('')
const parsedEshipBody = computed(() => {
  eshipBodyParseError.value = ''
  const txt = (eshipForm.body_text || '').trim()
  if (!txt) return {}
  let v
  try { v = JSON.parse(txt) } catch (e) { eshipBodyParseError.value = e.message; return undefined }
  if (v === null || typeof v !== 'object' || Array.isArray(v)) {
    eshipBodyParseError.value = 'O body deve ser um objeto JSON (ex: {"pagina": 1}).'
    return undefined
  }
  return v
})
const eshipFuncaoValid = computed(() => /^webService[A-Za-z]+$/.test((eshipForm.funcao || '').trim()))
const eshipIsWrite = computed(() =>
  /^webService(Post|Put|Delete|Cancela|Estornar|Apagar|Desativar|Gerar|Relacionar|Selecionar)/i
    .test((eshipForm.funcao || '').trim())
)
const canSubmitEship = computed(() =>
  !!eshipForm.cmig_id
  && eshipFuncaoValid.value
  && parsedEshipBody.value !== undefined
  && (!eshipIsWrite.value || eshipWriteConfirmed.value)
)

// ── Response compartilhado ──
const formattedResponseBody = computed(() => {
  const body = response.value?.response_body
  if (body == null) return ''
  if (typeof body === 'string') return body
  try { return JSON.stringify(body, null, 2) } catch { return String(body) }
})
const responseErros = computed(() => {
  const b = response.value?.response_body
  const arr = b && typeof b === 'object' ? b.erros : null
  if (!Array.isArray(arr) || !arr.length) return []
  return arr
    .map(x => {
      const e = (x && x.erro) || x || {}
      return [e.codigo, e.mensagem || e.message].filter(Boolean).join(': ')
    })
    .filter(Boolean)
})

function statusBadgeClass(status) {
  if (!status) return 'badge-secondary'
  if (status >= 200 && status < 300) return 'badge-success'
  if (status >= 300 && status < 400) return 'badge-info'
  if (status >= 400 && status < 500) return 'badge-warning'
  return 'badge-danger'
}

// ── ML load/exec ──
const accountsLoadError = ref('')
async function loadAccounts() {
  accountsLoadError.value = ''
  try {
    const { data } = await api.get('/admin/api-console/accounts')
    const label = p => ({ mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[p] || p)
    accounts.value = (Array.isArray(data) ? data : []).map(a => ({ ...a, platform_label: label(a.platform) }))
    if (accounts.value.length === 1) form.account_id = accounts.value[0].id
  } catch (e) {
    accounts.value = []
    accountsLoadError.value = e.response?.data?.detail || e.message || 'Erro ao carregar contas'
  }
}

function applyTemplate(t) {
  form.method = t.method
  form.path = t.path
  form.body_text = t.body ? JSON.stringify(t.body, null, 2) : ''
}

function queryAsObject() {
  const out = {}
  for (const { key, value } of form.query) {
    if (key && key.trim()) out[key.trim()] = value
  }
  return out
}
function headersAsObject() {
  const out = {}
  for (const { key, value } of form.headers) {
    if (key && key.trim()) out[key.trim()] = value
  }
  return out
}

async function execute() {
  if (!canSubmit.value || sending.value) return
  execError.value = ''
  response.value = null
  sending.value = true
  try {
    const payload = {
      account_id: form.account_id,
      method: form.method,
      path: form.path.trim(),
      query: queryAsObject(),
      headers: headersAsObject(),
    }
    if (methodAllowsBody.value && parsedBody.value !== null && parsedBody.value !== undefined) {
      payload.body_json = parsedBody.value
    }
    const { data } = await api.post('/admin/api-console/execute', payload)
    response.value = data
  } catch (e) {
    execError.value = e.response?.data?.detail || e.message || 'Erro desconhecido'
  } finally {
    sending.value = false
  }
}

// ── eShip load/exec ──
async function loadEshipCmigs() {
  eshipCmigsError.value = ''
  try {
    const { data } = await api.get('/integrations/eship/cmigs')
    eshipCmigs.value = Array.isArray(data) ? data : []
    const usable = eshipCmigs.value.filter(c => c.eship_configured)
    if (usable.length === 1) eshipForm.cmig_id = usable[0].cmig_id
  } catch (e) {
    eshipCmigs.value = []
    eshipCmigsError.value = e.response?.data?.detail || e.message || 'Erro ao carregar CMIGs'
  }
}

function fillTemplate() {
  const fn = selectedEshipFn.value
  if (fn && fn.tpl && typeof fn.tpl === 'object') {
    eshipForm.body_text = JSON.stringify(fn.tpl, null, 2)
  }
}

function onEshipFuncaoChange() {
  eshipWriteConfirmed.value = false
  fillTemplate()  // ao trocar de função, preenche o body com o template completo
}

function eshipHeadersObject() {
  const out = {}
  for (const { key, value } of eshipForm.headers) {
    if (key && key.trim()) out[key.trim()] = value
  }
  return out
}

async function executeEship() {
  if (!canSubmitEship.value || sending.value) return
  execError.value = ''
  response.value = null
  sending.value = true
  try {
    const { data } = await api.post('/admin/api-console/eship/execute', {
      cmig_id: eshipForm.cmig_id,
      funcao: eshipForm.funcao.trim(),
      body_json: parsedEshipBody.value,
      headers: eshipHeadersObject(),
    })
    response.value = data
  } catch (e) {
    execError.value = e.response?.data?.detail || e.message || 'Erro desconhecido'
  } finally {
    sending.value = false
  }
}

function setProvider(p) {
  provider.value = p
  execError.value = ''
  if (p === 'eship' && !eshipCmigs.value.length) loadEshipCmigs()
}

async function copyResponseBody() {
  try {
    await navigator.clipboard.writeText(formattedResponseBody.value)
  } catch { /* navegador antigo — ignora */ }
}

onMounted(loadAccounts)
</script>
