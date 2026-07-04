<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <h1 class="m-0"><i class="fas fa-warehouse text-primary mr-2"></i>Galpões</h1>
        <small class="text-muted">Cadastro e gestão dos galpões (unidades físicas dos Gestores Operacionais).</small>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Formulário (criar/editar) -->
        <div v-if="showForm" class="card card-primary">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-warehouse mr-2"></i>{{ form.id ? 'Editar Galpão' : 'Novo Galpão' }}
            </h3>
          </div>
          <form @submit.prevent="save">
            <div class="card-body">
              <div v-if="error" class="alert alert-danger">{{ error }}</div>

              <div class="row">
                <div class="col-md-5 form-group">
                  <label>GO dono <span class="text-danger">*</span></label>
                  <select v-model.number="form.go_id" class="form-control" required>
                    <option :value="null" disabled>Selecione o Gestor Operacional…</option>
                    <option v-for="g in goes" :key="g.id" :value="g.id">{{ goLabel(g) }}</option>
                  </select>
                </div>
                <div class="col-md-4 form-group">
                  <label>Nome do Galpão <span class="text-danger">*</span></label>
                  <input v-model="form.name" class="form-control" required placeholder="Ex: Galpão Central MIG" />
                </div>
                <div class="col-md-3 form-group">
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

              <hr />
              <h6 class="text-muted text-uppercase mb-3"><small>Endereço</small></h6>
              <div class="row">
                <div class="col-md-3 form-group">
                  <label>CEP <span class="text-danger">*</span></label>
                  <div class="input-group">
                    <input v-model="form.zip_code" class="form-control" placeholder="00000-000" @blur="lookupCep" required />
                    <div class="input-group-append">
                      <span class="input-group-text" style="cursor:pointer" @click="lookupCep"><i class="fas fa-search"></i></span>
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
              <div class="form-group">
                <label>Observações internas</label>
                <textarea v-model="form.notes" class="form-control" rows="2"></textarea>
              </div>
            </div>
            <div class="card-footer">
              <button type="submit" class="btn btn-primary" :disabled="saving">
                <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ saving ? 'Salvando…' : (form.id ? 'Atualizar Galpão' : 'Cadastrar Galpão') }}
              </button>
              <button type="button" class="btn btn-secondary ml-2" @click="cancelForm">Cancelar</button>
            </div>
          </form>
        </div>

        <!-- Lista -->
        <div class="card">
          <div class="card-header d-flex align-items-center">
            <h3 class="card-title flex-grow-1">Galpões cadastrados</h3>
            <button v-if="!showForm" class="btn btn-sm btn-primary" @click="newWarehouse">
              <i class="fas fa-plus mr-1"></i> Novo Galpão
            </button>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>
            <table v-else class="table table-hover mb-0">
              <thead class="thead-light">
                <tr><th>Nome</th><th>CNPJ</th><th>GO dono</th><th>Cidade/UF</th><th class="text-right">Ações</th></tr>
              </thead>
              <tbody>
                <tr v-if="warehouses.length === 0"><td colspan="5" class="text-center text-muted py-3">Nenhum galpão cadastrado.</td></tr>
                <tr v-for="w in warehouses" :key="w.id">
                  <td class="font-weight-bold">{{ w.name }}</td>
                  <td>{{ w.cnpj || '—' }}</td>
                  <td>{{ goNameById(w.go_id) }}</td>
                  <td>{{ w.city ? `${w.city}/${w.state || ''}` : '—' }}</td>
                  <td class="text-right">
                    <button class="btn btn-sm btn-outline-primary mr-1" @click="editWarehouse(w)"><i class="fas fa-edit"></i></button>
                    <button class="btn btn-sm btn-outline-danger" :disabled="deletingId === w.id" @click="removeWarehouse(w)">
                      <i class="fas" :class="deletingId === w.id ? 'fa-spinner fa-spin' : 'fa-trash'"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()

const loading = ref(true)
const saving = ref(false)
const deletingId = ref(null)
const error = ref('')
const showForm = ref(false)
const warehouses = ref([])
const goes = ref([])

function emptyForm() {
  return {
    id: null, go_id: null,
    name: '', cnpj: '', company_name: '', trade_name: '',
    phone: '', whatsapp: '', email: '',
    zip_code: '', street: '', number: '', complement: '',
    neighborhood: '', city: '', state: '',
    pix_key_type: '', pix_key: '', notes: '',
  }
}
const form = ref(emptyForm())

function goLabel(g) {
  const nome = g.full_name || g.company_name || g.trade_name || `GO #${g.id}`
  return g.company_name && g.full_name ? `${g.full_name} — ${g.company_name}` : nome
}
function goNameById(goId) {
  const g = goes.value.find(x => x.id === goId)
  return g ? goLabel(g) : (goId ? `GO #${goId}` : '—')
}

async function load() {
  loading.value = true
  try {
    const [whRes, goRes] = await Promise.all([api.get('/warehouse'), api.get('/goes')])
    warehouses.value = Array.isArray(whRes.data) ? whRes.data : []
    goes.value = Array.isArray(goRes.data) ? goRes.data : []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar galpões')
  } finally {
    loading.value = false
  }
}

function newWarehouse() {
  form.value = emptyForm()
  error.value = ''
  showForm.value = true
}
function editWarehouse(w) {
  form.value = { ...emptyForm(), ...w }
  error.value = ''
  showForm.value = true
}
function cancelForm() {
  showForm.value = false
  error.value = ''
}

async function save() {
  error.value = ''
  if (!form.value.go_id) { error.value = 'Selecione o GO dono do galpão.'; return }
  saving.value = true
  try {
    if (form.value.id) {
      await api.put(`/warehouse/${form.value.id}`, form.value)
      toast.success('Galpão atualizado com sucesso!')
    } else {
      await api.post('/warehouse', form.value)
      toast.success('Galpão cadastrado com sucesso!')
    }
    showForm.value = false
    await load()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar galpão'
  } finally {
    saving.value = false
  }
}

async function removeWarehouse(w) {
  if (!confirm(`Excluir o galpão "${w.name}"? Esta ação não pode ser desfeita.`)) return
  deletingId.value = w.id
  try {
    await api.delete(`/warehouse/${w.id}`)
    toast.success('Galpão excluído.')
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir galpão')
  } finally {
    deletingId.value = null
  }
}

async function lookupCep() {
  const cep = (form.value.zip_code || '').replace(/\D/g, '')
  if (cep.length !== 8) return
  try {
    const { data } = await api.get(`/users/address/lookup/${cep}`)
    if (!data.erro) {
      form.value.street = data.logradouro
      form.value.neighborhood = data.bairro
      form.value.city = data.localidade
      form.value.state = data.uf
    }
  } catch { /* silent */ }
}

onMounted(load)
</script>
