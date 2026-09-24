<template>
  <div>
    <div v-if="loading" class="text-center py-5">
      <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
    </div>

    <div v-else class="row">
      <!-- Coluna principal -->
      <div class="col-lg-8">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-warehouse mr-2"></i>Dados do Galpão
            </h3>
          </div>

          <form @submit.prevent="save">
            <div class="card-body">
              <div v-if="error" class="alert alert-danger">{{ error }}</div>
              <div v-if="success" class="alert alert-success">{{ success }}</div>

              <!-- Identificação -->
              <h6 class="text-muted text-uppercase mb-3"><small>Identificação</small></h6>
              <div class="row">
                <div class="col-md-8 form-group">
                  <label>Nome do Galpão <span class="text-danger">*</span></label>
                  <input v-model="form.name" class="form-control" required placeholder="Ex: Galpão Central MIG" />
                </div>
                <div class="col-md-4 form-group">
                  <label>CNPJ <span class="text-danger">*</span></label>
                  <input v-model="form.cnpj" class="form-control" required placeholder="00.000.000/0000-00" />
                </div>
              </div>

              <div class="row">
                <div class="col-md-6 form-group">
                  <label>Razão Social</label>
                  <input v-model="form.company_name" class="form-control" placeholder="Razão social da empresa" />
                </div>
                <div class="col-md-6 form-group">
                  <label>Nome Fantasia</label>
                  <input v-model="form.trade_name" class="form-control" placeholder="Nome fantasia" />
                </div>
              </div>

              <!-- Contato -->
              <hr />
              <h6 class="text-muted text-uppercase mb-3"><small>Contato</small></h6>
              <div class="row">
                <div class="col-md-4 form-group">
                  <label>Telefone</label>
                  <input v-model="form.phone" class="form-control" placeholder="(11) 3000-0000" />
                </div>
                <div class="col-md-4 form-group">
                  <label>WhatsApp</label>
                  <input v-model="form.whatsapp" class="form-control" placeholder="(11) 91234-5678" />
                </div>
                <div class="col-md-4 form-group">
                  <label>E-mail</label>
                  <input v-model="form.email" type="email" class="form-control" placeholder="contato@galpao.com" />
                </div>
              </div>

              <!-- Endereço -->
              <hr />
              <h6 class="text-muted text-uppercase mb-3"><small>Endereço</small></h6>
              <div class="row">
                <div class="col-md-3 form-group">
                  <label>CEP <span class="text-danger">*</span></label>
                  <div class="input-group">
                    <input v-model="form.zip_code" class="form-control" placeholder="00000-000" @blur="lookupCep" required />
                    <div class="input-group-append">
                      <span class="input-group-text" style="cursor:pointer" @click="lookupCep">
                        <i class="fas fa-search"></i>
                      </span>
                    </div>
                  </div>
                </div>
                <div class="col-md-6 form-group">
                  <label>Rua <span class="text-danger">*</span></label>
                  <input v-model="form.street" class="form-control" required />
                </div>
                <div class="col-md-3 form-group">
                  <label>Número <span class="text-danger">*</span></label>
                  <input v-model="form.number" class="form-control" required />
                </div>
              </div>

              <div class="row">
                <div class="col-md-3 form-group">
                  <label>Complemento</label>
                  <input v-model="form.complement" class="form-control" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Bairro <span class="text-danger">*</span></label>
                  <input v-model="form.neighborhood" class="form-control" required />
                </div>
                <div class="col-md-4 form-group">
                  <label>Cidade <span class="text-danger">*</span></label>
                  <input v-model="form.city" class="form-control" required />
                </div>
                <div class="col-md-1 form-group">
                  <label>UF <span class="text-danger">*</span></label>
                  <input v-model="form.state" class="form-control" maxlength="2" required />
                </div>
              </div>

              <!-- Chave PIX para recebimento -->
              <hr />
              <h6 class="text-muted text-uppercase mb-3"><small>Recebimentos</small></h6>
              <div class="row">
                <div class="col-md-4 form-group">
                  <label>Tipo da Chave PIX</label>
                  <select v-model="form.pix_key_type" class="form-control">
                    <option value="">Selecione…</option>
                    <option value="cpf">CPF</option>
                    <option value="cnpj">CNPJ</option>
                    <option value="email">E-mail</option>
                    <option value="phone">Telefone</option>
                    <option value="random">Chave Aleatória</option>
                  </select>
                </div>
                <div class="col-md-8 form-group">
                  <label>Chave PIX</label>
                  <input v-model="form.pix_key" class="form-control" placeholder="Chave PIX para receber dos Gestores de Conta" />
                </div>
              </div>

              <!-- Marca e Tema -->
              <hr />
              <h6 class="text-muted text-uppercase mb-3"><small>Marca e Tema</small></h6>
              <div class="card">
                <div class="card-body">
                  <p class="text-sm text-muted mb-3">
                    As cores e o logo aparecem para os usuários deste Galpão (canto superior esquerdo e menu lateral).
                    Deixe em branco para usar o padrão do sistema.
                  </p>

                  <!-- Logo -->
                  <div class="form-group">
                    <label>Logo do Galpão</label>
                    <div v-if="form.id">
                      <div v-if="form.logo_url" class="d-flex align-items-center mb-2">
                        <img :src="form.logo_url" alt="Logo" style="max-height:48px; max-width:180px; object-fit:contain;" class="mr-2" />
                        <button type="button" class="btn btn-sm btn-outline-danger" @click="removeLogo">
                          <i class="fas fa-trash mr-1"></i>Remover
                        </button>
                      </div>
                      <input
                        ref="logoInput"
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        class="form-control-file"
                        :disabled="uploadingLogo"
                        @change="onLogoPicked"
                      />
                      <small v-if="uploadingLogo" class="text-muted">
                        <i class="fas fa-spinner fa-spin mr-1"></i>Enviando…
                      </small>
                    </div>
                    <small v-else class="text-muted d-block">
                      Salve o galpão primeiro para enviar o logo.
                    </small>
                  </div>

                  <!-- Cores -->
                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>Barra lateral (fundo)</label>
                      <div class="d-flex align-items-center">
                        <input type="color" class="mr-2" :value="colorValue('theme_sidebar')" @input="setColor('theme_sidebar', $event)" style="width:44px; height:38px; padding:2px;" />
                        <code class="mr-2">{{ form.theme_sidebar || '—' }}</code>
                        <button v-if="form.theme_sidebar" type="button" class="btn btn-sm btn-link text-muted p-0" @click="clearColor('theme_sidebar')">Limpar</button>
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Destaque (item ativo)</label>
                      <div class="d-flex align-items-center">
                        <input type="color" class="mr-2" :value="colorValue('theme_accent')" @input="setColor('theme_accent', $event)" style="width:44px; height:38px; padding:2px;" />
                        <code class="mr-2">{{ form.theme_accent || '—' }}</code>
                        <button v-if="form.theme_accent" type="button" class="btn btn-sm btn-link text-muted p-0" @click="clearColor('theme_accent')">Limpar</button>
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Barra superior</label>
                      <div class="d-flex align-items-center">
                        <input type="color" class="mr-2" :value="colorValue('theme_topbar')" @input="setColor('theme_topbar', $event)" style="width:44px; height:38px; padding:2px;" />
                        <code class="mr-2">{{ form.theme_topbar || '—' }}</code>
                        <button v-if="form.theme_topbar" type="button" class="btn btn-sm btn-link text-muted p-0" @click="clearColor('theme_topbar')">Limpar</button>
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Texto da barra lateral</label>
                      <div class="d-flex align-items-center">
                        <input type="color" class="mr-2" :value="colorValue('theme_sidebar_text')" @input="setColor('theme_sidebar_text', $event)" style="width:44px; height:38px; padding:2px;" />
                        <code class="mr-2">{{ form.theme_sidebar_text || '—' }}</code>
                        <button v-if="form.theme_sidebar_text" type="button" class="btn btn-sm btn-link text-muted p-0" @click="clearColor('theme_sidebar_text')">Limpar</button>
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Links / realces</label>
                      <div class="d-flex align-items-center">
                        <input type="color" class="mr-2" :value="colorValue('theme_link')" @input="setColor('theme_link', $event)" style="width:44px; height:38px; padding:2px;" />
                        <code class="mr-2">{{ form.theme_link || '—' }}</code>
                        <button v-if="form.theme_link" type="button" class="btn btn-sm btn-link text-muted p-0" @click="clearColor('theme_link')">Limpar</button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Observações internas -->
              <div class="form-group">
                <label>Observações internas</label>
                <textarea v-model="form.notes" class="form-control" rows="3" placeholder="Instruções de entrega, horário de funcionamento, etc."></textarea>
              </div>
            </div>

            <div class="card-footer">
              <button type="submit" class="btn btn-primary" :disabled="saving">
                <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ saving ? 'Salvando…' : (form.id ? 'Atualizar Galpão' : 'Cadastrar Galpão') }}
              </button>
            </div>
          </form>
        </div>
      </div>

      <!-- Painel lateral de informações -->
      <div class="col-lg-4">
        <div class="card card-info">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-info-circle mr-1"></i> Sobre o Galpão</h3>
          </div>
          <div class="card-body">
            <p class="text-sm">
              O Galpão é a unidade física do <strong>Gestor Operacional (GO)</strong> onde os produtos são armazenados e as operações logísticas são realizadas.
            </p>
            <ul class="text-sm pl-3">
              <li>O <strong>endereço completo</strong> é exibido nos processos de devolução para que os clientes possam enviar produtos.</li>
              <li>A <strong>Chave PIX</strong> é exibida automaticamente nos módulos financeiros dos Gestores de Conta.</li>
            </ul>
          </div>
        </div>

        <div v-if="form.id" class="card">
          <div class="card-header bg-light">
            <h3 class="card-title text-sm">Endereço para Devoluções</h3>
          </div>
          <div class="card-body text-sm">
            <strong>{{ form.name }}</strong><br />
            {{ form.street }}, {{ form.number }}<span v-if="form.complement">, {{ form.complement }}</span><br />
            {{ form.neighborhood }} — {{ form.city }}/{{ form.state }}<br />
            CEP: {{ form.zip_code }}<br />
            <span v-if="form.whatsapp">WhatsApp: {{ form.whatsapp }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import { useUiStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'

const { add: toast } = useToast()
const feedback = useToast()
const ui = useUiStore()
const auth = useAuthStore()

const loading = ref(true)
const saving  = ref(false)
const error   = ref('')
const success = ref('')
const uploadingLogo = ref(false)
const logoInput = ref(null)

const form = ref({
  id: null,
  name: '', cnpj: '', company_name: '', trade_name: '',
  phone: '', whatsapp: '', email: '',
  zip_code: '', street: '', number: '', complement: '',
  neighborhood: '', city: '', state: '',
  pix_key_type: '', pix_key: '',
  notes: '',
  logo_url: '',
  theme_sidebar: '', theme_accent: '', theme_topbar: '',
  theme_sidebar_text: '', theme_link: '',
})

onMounted(async () => {
  try {
    const { data } = await api.get('/warehouse')
    if (data) Object.assign(form.value, data)
  } catch {
    // Sem galpão cadastrado ainda — formulário vazio
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  error.value = ''
  success.value = ''
  try {
    if (form.value.id) {
      const { data } = await api.put(`/warehouse/${form.value.id}`, form.value)
      Object.assign(form.value, data)
      success.value = 'Galpão atualizado com sucesso!'
    } else {
      const { data } = await api.post('/warehouse', form.value)
      Object.assign(form.value, data)
      success.value = 'Galpão cadastrado com sucesso!'
    }
    feedback.success(success.value)
    applyLiveTheme()
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao salvar galpão'
  } finally {
    saving.value = false
  }
}

// Reaplica o tema ao vivo (sem F5) quando o galpão editado é o do usuário logado.
function applyLiveTheme() {
  if (!form.value.id || auth.user?.warehouse_id !== form.value.id) return
  ui.setWarehouseTheme({
    logo_url: form.value.logo_url || null,
    name: form.value.trade_name || form.value.name || null,
    theme_sidebar: form.value.theme_sidebar || null,
    theme_accent: form.value.theme_accent || null,
    theme_topbar: form.value.theme_topbar || null,
    theme_sidebar_text: form.value.theme_sidebar_text || null,
    theme_link: form.value.theme_link || null,
  })
}

async function onLogoPicked(ev) {
  const file = ev.target?.files?.[0]
  if (!file) return
  if (!form.value.id) {
    feedback.warning('Salve o galpão primeiro para enviar o logo.')
    if (logoInput.value) logoInput.value.value = ''
    return
  }
  uploadingLogo.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post(`/warehouse/${form.value.id}/logo`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    form.value.logo_url = data.logo_url || ''
    feedback.success('Logo enviado com sucesso!')
    applyLiveTheme()
  } catch (err) {
    feedback.error(err.response?.data?.detail || 'Erro ao enviar o logo')
  } finally {
    uploadingLogo.value = false
    if (logoInput.value) logoInput.value.value = ''
  }
}

async function removeLogo() {
  if (!form.value.id) { form.value.logo_url = ''; return }
  try {
    await api.delete(`/warehouse/${form.value.id}/logo`)
    form.value.logo_url = ''
    feedback.success('Logo removido.')
    applyLiveTheme()
  } catch (err) {
    feedback.error(err.response?.data?.detail || 'Erro ao remover o logo')
  }
}

// <input type="color"> não aceita vazio; usamos um proxy: se o campo estiver vazio
// mostramos um cinza neutro, mas só gravamos a cor quando o usuário realmente mexe.
function colorValue(field) {
  return form.value[field] || '#cccccc'
}
function setColor(field, ev) {
  form.value[field] = ev.target.value
}
function clearColor(field) {
  form.value[field] = ''
}

async function lookupCep() {
  const cep = form.value.zip_code.replace(/\D/g, '')
  if (cep.length !== 8) return
  try {
    const { data } = await api.get(`/users/address/lookup/${cep}`)
    if (!data.erro) {
      form.value.street       = data.logradouro
      form.value.neighborhood = data.bairro
      form.value.city         = data.localidade
      form.value.state        = data.uf
    }
  } catch { /* silent */ }
}
</script>
