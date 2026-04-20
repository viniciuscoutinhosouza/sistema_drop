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

const { add: toast } = useToast()

const loading = ref(true)
const saving  = ref(false)
const error   = ref('')
const success = ref('')

const form = ref({
  id: null,
  name: '', cnpj: '', company_name: '', trade_name: '',
  phone: '', whatsapp: '', email: '',
  zip_code: '', street: '', number: '', complement: '',
  neighborhood: '', city: '', state: '',
  pix_key_type: '', pix_key: '',
  notes: '',
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
    toast(success.value, 'success')
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao salvar galpão'
  } finally {
    saving.value = false
  }
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
