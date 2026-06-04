<template>
  <div class="content-header">
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-8">
          <h1 class="m-0">
            <i class="fas fa-terminal mr-2 text-primary"></i>
            Console de API do Marketplace
          </h1>
          <small class="text-muted">
            Executa requests diretas à API do ML usando o token da conta selecionada.
            <span class="badge badge-danger ml-1">Admin only</span>
          </small>
        </div>
      </div>
    </div>
  </div>

  <section class="content">
    <div class="container-fluid">

      <!-- Aviso: conta sem autorização -->
      <div v-if="selectedAccount && selectedAccount.requires_reauth"
           class="alert alert-warning py-2 mb-3">
        <i class="fas fa-exclamation-triangle mr-1"></i>
        A conta <strong>{{ selectedAccountLabel }}</strong> precisa ser reconectada em
        <RouterLink to="/integrations">Integrações</RouterLink>. As requests vão falhar com 401.
      </div>

      <div class="row">

        <!-- ── Coluna esquerda: Request ── -->
        <div class="col-lg-6">
          <div class="card card-outline card-primary mb-3">
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

              <!-- Templates rápidos -->
              <div class="form-group">
                <label class="font-weight-bold small text-muted">Templates rápidos:</label>
                <div class="d-flex flex-wrap" style="gap:4px">
                  <button v-for="t in TEMPLATES" :key="t.label" type="button"
                          class="btn btn-sm btn-outline-secondary" @click="applyTemplate(t)">
                    {{ t.label }}
                  </button>
                </div>
              </div>

              <!-- Query params -->
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

              <!-- Headers extras -->
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

              <!-- Body (JSON) -->
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
        </div>

        <!-- ── Coluna direita: Response ── -->
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
  query: [],          // [{ key, value }]
  headers: [],        // [{ key, value }]
  body_text: '',
})

const sending = ref(false)
const response = ref(null)
const execError = ref('')

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

const formattedResponseBody = computed(() => {
  const body = response.value?.response_body
  if (body == null) return ''
  if (typeof body === 'string') return body
  try { return JSON.stringify(body, null, 2) } catch { return String(body) }
})

function statusBadgeClass(status) {
  if (!status) return 'badge-secondary'
  if (status >= 200 && status < 300) return 'badge-success'
  if (status >= 300 && status < 400) return 'badge-info'
  if (status >= 400 && status < 500) return 'badge-warning'
  return 'badge-danger'
}

const accountsLoadError = ref('')
async function loadAccounts() {
  accountsLoadError.value = ''
  try {
    // Endpoint admin-only que retorna TODAS as contas (diferente do /accounts
    // que filtra pelas contas co-administradas pelo usuário).
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

async function copyResponseBody() {
  try {
    await navigator.clipboard.writeText(formattedResponseBody.value)
  } catch { /* navegador antigo — ignora */ }
}

onMounted(loadAccounts)
</script>
