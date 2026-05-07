<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <h1 class="m-0"><i class="fas fa-robot mr-2 text-success"></i>Configuração de IA — Atendimento</h1>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="row">
          <div class="col-lg-7">
            <div class="card card-outline card-success">
              <div class="card-header">
                <h3 class="card-title">Provedor e Credenciais</h3>
              </div>
              <div class="card-body">
                <div v-if="loading" class="text-center py-4">
                  <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
                </div>
                <template v-else>
                  <!-- Provedor -->
                  <div class="form-group">
                    <label class="font-weight-bold">Provedor de IA</label>
                    <div class="d-flex" style="gap:16px">
                      <div class="custom-control custom-radio">
                        <input type="radio" id="rOpenAI" class="custom-control-input" value="openai" v-model="form.provider" @change="onProviderChange" />
                        <label class="custom-control-label" for="rOpenAI">
                          <i class="fas fa-brain mr-1"></i> OpenAI (ChatGPT)
                        </label>
                      </div>
                      <div class="custom-control custom-radio">
                        <input type="radio" id="rAnthropic" class="custom-control-input" value="anthropic" v-model="form.provider" @change="onProviderChange" />
                        <label class="custom-control-label" for="rAnthropic">
                          <i class="fas fa-robot mr-1"></i> Anthropic (Claude)
                        </label>
                      </div>
                    </div>
                  </div>

                  <!-- API Key -->
                  <div class="form-group">
                    <label class="font-weight-bold">API Key</label>
                    <div class="input-group">
                      <input
                        :type="showKey ? 'text' : 'password'"
                        class="form-control"
                        v-model="form.api_key"
                        :placeholder="existingKeyMasked || 'Cole sua API Key aqui (deixe vazio para manter a atual)'"
                      />
                      <div class="input-group-append">
                        <button class="btn btn-outline-secondary" type="button" @click="showKey = !showKey">
                          <i :class="showKey ? 'fas fa-eye-slash' : 'fas fa-eye'"></i>
                        </button>
                      </div>
                    </div>
                    <small class="text-muted">
                      {{ form.provider === 'openai' ? 'Obtida em platform.openai.com/api-keys' : 'Obtida em console.anthropic.com/settings/keys' }}
                    </small>
                  </div>

                  <!-- Modelo -->
                  <div class="form-group">
                    <label class="font-weight-bold">Modelo</label>
                    <select v-model="form.model_name" class="form-control">
                      <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
                    </select>
                  </div>

                  <!-- Status -->
                  <div class="form-group">
                    <div class="custom-control custom-switch">
                      <input type="checkbox" class="custom-control-input" id="switchActive" v-model="form.is_active" />
                      <label class="custom-control-label" for="switchActive">
                        IA ativada (permite auto-resposta e sugestões)
                      </label>
                    </div>
                  </div>

                  <!-- Instruções Gerais -->
                  <div class="form-group">
                    <label class="font-weight-bold">Instruções Gerais</label>
                    <textarea
                      v-model="form.global_instructions"
                      class="form-control"
                      rows="6"
                      placeholder="Você é um assistente de atendimento de e-commerce. Responda em português, com tom cordial e profissional. Nunca prometa prazos sem verificar. Assine como 'Equipe [Loja]'."
                    ></textarea>
                    <small class="text-muted">Base para todas as contas. Cada CMIG pode complementar com instruções próprias.</small>
                  </div>

                  <!-- Botões -->
                  <div class="d-flex" style="gap:8px">
                    <button class="btn btn-success" @click="save" :disabled="saving">
                      <i :class="['fas', saving ? 'fa-spinner fa-spin' : 'fa-save', 'mr-1']"></i>
                      {{ saving ? 'Salvando...' : 'Salvar Configuração' }}
                    </button>
                    <button class="btn btn-outline-secondary" @click="testConnection" :disabled="testing || !configExists">
                      <i :class="['fas', testing ? 'fa-spinner fa-spin' : 'fa-plug', 'mr-1']"></i>
                      {{ testing ? 'Testando...' : 'Testar Conexão' }}
                    </button>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- Painel de ajuda -->
          <div class="col-lg-5">
            <div class="card">
              <div class="card-header"><h3 class="card-title">Como funciona</h3></div>
              <div class="card-body small text-muted">
                <p><strong>1. Configure o provedor e a API Key</strong><br>
                  Insira a chave da OpenAI ou Anthropic. A chave é armazenada de forma segura e nunca exibida completa.</p>
                <p><strong>2. Defina as Instruções Gerais</strong><br>
                  Estas instruções valem para todas as contas CMIG. Use para definir tom, idioma e regras gerais do atendimento.</p>
                <p><strong>3. Configure instruções por CMIG</strong><br>
                  Na tela de detalhe de cada CMIG, você pode adicionar instruções específicas (prazo, produto, marca, etc.) e ativar a auto-resposta.</p>
                <p><strong>4. Auto-resposta vs. Sugestão</strong><br>
                  <strong>Auto-resposta OFF</strong>: a IA gera um rascunho que o operador revisa e envia.<br>
                  <strong>Auto-resposta ON</strong>: a IA responde automaticamente quando o comprador manda mensagem.</p>
                <hr />
                <p class="mb-0 text-warning">
                  <i class="fas fa-exclamation-triangle mr-1"></i>
                  <strong>Atenção:</strong> Nunca ative auto-resposta sem antes testar e revisar as instruções. Mensagens inadequadas podem afetar sua reputação no Mercado Livre.
                </p>
              </div>
            </div>

            <!-- Status atual -->
            <div v-if="configExists" class="card">
              <div class="card-header"><h3 class="card-title">Status Atual</h3></div>
              <div class="card-body">
                <dl class="row mb-0 small">
                  <dt class="col-sm-5">Provedor</dt>
                  <dd class="col-sm-7">{{ currentConfig.provider === 'openai' ? 'OpenAI' : 'Anthropic (Claude)' }}</dd>
                  <dt class="col-sm-5">Modelo</dt>
                  <dd class="col-sm-7">{{ currentConfig.model_name }}</dd>
                  <dt class="col-sm-5">API Key</dt>
                  <dd class="col-sm-7"><code>{{ currentConfig.api_key_masked }}</code></dd>
                  <dt class="col-sm-5">Status</dt>
                  <dd class="col-sm-7">
                    <span :class="['badge', currentConfig.is_active ? 'badge-success' : 'badge-secondary']">
                      {{ currentConfig.is_active ? 'Ativa' : 'Inativa' }}
                    </span>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const testing = ref(false)
const showKey = ref(false)
const currentConfig = ref({})
const configExists = computed(() => currentConfig.value?.configured)
const existingKeyMasked = computed(() => currentConfig.value?.api_key_masked || '')

const MODELS = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
}

const form = ref({
  provider: 'anthropic',
  api_key: '',
  model_name: 'claude-sonnet-4-6',
  global_instructions: '',
  is_active: false,
})

const availableModels = computed(() => MODELS[form.value.provider] || [])

function onProviderChange() {
  form.value.model_name = MODELS[form.value.provider]?.[1] || ''
}

onMounted(async () => {
  try {
    const { data } = await api.get('/ai-config/')
    currentConfig.value = data
    if (data.configured) {
      form.value.provider = data.provider
      form.value.model_name = data.model_name
      form.value.global_instructions = data.global_instructions
      form.value.is_active = data.is_active
    }
  } catch (e) {
    toast.error('Erro ao carregar configuração de IA.')
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    const payload = { ...form.value }
    if (!payload.api_key) delete payload.api_key  // não sobrescrever se vazio
    await api.put('/ai-config/', payload)
    toast.success('Configuração de IA salva com sucesso!')
    // Recarrega para atualizar a chave mascarada
    const { data } = await api.get('/ai-config/')
    currentConfig.value = data
    form.value.api_key = ''
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar configuração.')
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  try {
    const { data } = await api.post('/ai-config/test')
    toast.success(`Conexão OK! Provedor: ${data.provider} | Modelo: ${data.model}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha na conexão com a IA.')
  } finally {
    testing.value = false
  }
}
</script>
