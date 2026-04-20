<template>
  <div>
    <!-- Cabeçalho + Botões -->
    <div class="d-flex justify-content-between align-items-center mb-3">
      <div class="btn-group">
        <button
          v-if="canCreateUGO"
          class="btn btn-warning"
          @click="openModal('ugo')"
        >
          <i class="fas fa-user-tie mr-1"></i> Novo Operador Logístico
        </button>
        <button class="btn btn-primary ml-2" @click="openModal('ac')">
          <i class="fas fa-user-plus mr-1"></i> Novo Gestor de Conta
        </button>
      </div>
      <div class="d-flex align-items-center gap-2">
        <select v-model="filterRole" class="form-control form-control-sm" style="width:180px">
          <option value="">Todos os perfis</option>
          <option value="ugo">Operador Logístico</option>
          <option value="ac">Gestor de Conta</option>
        </select>
        <input
          v-model="search"
          class="form-control form-control-sm ml-2"
          placeholder="Buscar nome ou e-mail…"
          style="width:220px"
        />
      </div>
    </div>

    <!-- Tabela -->
    <div class="card">
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-5">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>
        <table v-else class="table table-hover table-sm mb-0">
          <thead class="thead-light">
            <tr>
              <th>#</th>
              <th>Nome</th>
              <th>E-mail</th>
              <th>WhatsApp</th>
              <th>Perfil</th>
              <th>Status</th>
              <th>Cadastro</th>
              <th class="text-center">Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredUsers.length === 0">
              <td colspan="8" class="text-center text-muted py-4">Nenhum usuário encontrado.</td>
            </tr>
            <tr v-for="u in filteredUsers" :key="u.id">
              <td class="text-muted">{{ u.id }}</td>
              <td>{{ u.full_name }}</td>
              <td>{{ u.email }}</td>
              <td>{{ u.whatsapp || '—' }}</td>
              <td>
                <span :class="roleBadge(u.role)">{{ roleLabel(u.role) }}</span>
              </td>
              <td>
                <span :class="u.is_active ? 'badge badge-success' : 'badge badge-secondary'">
                  {{ u.is_active ? 'Ativo' : 'Inativo' }}
                </span>
              </td>
              <td class="text-nowrap">{{ formatDate(u.created_at) }}</td>
              <td class="text-center">
                <button
                  v-if="u.is_active"
                  class="btn btn-xs btn-outline-danger"
                  title="Desativar"
                  @click="deactivate(u)"
                >
                  <i class="fas fa-ban"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal Cadastro -->
    <div v-if="modal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-user-plus mr-2"></i>
              {{ modal.type === 'ugo' ? 'Novo Operador Logístico (UGO)' : 'Novo Gestor de Conta (AC)' }}
            </h5>
            <button type="button" class="close" @click="closeModal">
              <span>&times;</span>
            </button>
          </div>

          <form @submit.prevent="submitForm">
            <div class="modal-body">
              <div v-if="modal.error" class="alert alert-danger">{{ modal.error }}</div>

              <!-- Dados básicos -->
              <div class="row">
                <div class="col-md-6 form-group">
                  <label>Nome completo <span class="text-danger">*</span></label>
                  <input v-model="form.full_name" class="form-control" required />
                </div>
                <div class="col-md-6 form-group">
                  <label>E-mail <span class="text-danger">*</span></label>
                  <input v-model="form.email" type="email" class="form-control" required />
                </div>
              </div>

              <div class="row">
                <div class="col-md-4 form-group">
                  <label>WhatsApp</label>
                  <input v-model="form.whatsapp" class="form-control" placeholder="(11) 91234-5678" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Senha <span class="text-danger">*</span></label>
                  <input v-model="form.password" type="password" class="form-control" required minlength="6" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Confirmar senha <span class="text-danger">*</span></label>
                  <input v-model="form.password_confirm" type="password" class="form-control" required />
                </div>
              </div>

              <!-- Campos extras apenas para AC -->
              <template v-if="modal.type === 'ac'">
                <hr />
                <div class="row">
                  <div class="col-md-4 form-group">
                    <label>Tipo de pessoa <span class="text-danger">*</span></label>
                    <select v-model="form.person_type" class="form-control" required>
                      <option value="fisica">Física (CPF)</option>
                      <option value="juridica">Jurídica (CNPJ)</option>
                    </select>
                  </div>
                  <div class="col-md-4 form-group">
                    <label>CPF / CNPJ <span class="text-danger">*</span></label>
                    <input v-model="form.cpf_cnpj" class="form-control" required />
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Plano de acesso</label>
                    <select v-model="form.plan_id" class="form-control">
                      <option :value="null">Sem plano</option>
                      <option v-for="p in plans" :key="p.id" :value="p.id">
                        {{ p.name }} — {{ formatCurrency(p.monthly_price) }}/mês (até {{ p.max_accounts === -1 ? '∞' : p.max_accounts }} contas)
                      </option>
                    </select>
                  </div>
                </div>

                <div class="row">
                  <div class="col-md-3 form-group">
                    <label>CEP</label>
                    <div class="input-group">
                      <input v-model="form.zip_code" class="form-control" placeholder="00000-000" @blur="lookupCep" />
                      <div class="input-group-append">
                        <span class="input-group-text"><i class="fas fa-search"></i></span>
                      </div>
                    </div>
                  </div>
                  <div class="col-md-6 form-group">
                    <label>Rua</label>
                    <input v-model="form.street" class="form-control" />
                  </div>
                  <div class="col-md-3 form-group">
                    <label>Número</label>
                    <input v-model="form.number" class="form-control" />
                  </div>
                </div>

                <div class="row">
                  <div class="col-md-3 form-group">
                    <label>Complemento</label>
                    <input v-model="form.complement" class="form-control" />
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Bairro</label>
                    <input v-model="form.neighborhood" class="form-control" />
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Cidade</label>
                    <input v-model="form.city" class="form-control" />
                  </div>
                  <div class="col-md-1 form-group">
                    <label>UF</label>
                    <input v-model="form.state" class="form-control" maxlength="2" />
                  </div>
                </div>
              </template>
            </div>

            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" @click="closeModal">Cancelar</button>
              <button type="submit" class="btn btn-primary" :disabled="modal.saving">
                <i v-if="modal.saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ modal.saving ? 'Salvando…' : 'Cadastrar' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const authStore = useAuthStore()
const { add: toast } = useToast()

const users   = ref([])
const plans   = ref([])
const loading = ref(false)
const search  = ref('')
const filterRole = ref('')

const canCreateUGO = computed(() => authStore.user?.role === 'admin')

const modal = ref({ show: false, type: 'ac', saving: false, error: '' })
const formDefault = () => ({
  full_name: '', email: '', whatsapp: '', password: '', password_confirm: '',
  person_type: 'fisica', cpf_cnpj: '', plan_id: null,
  zip_code: '', street: '', number: '', complement: '', neighborhood: '', city: '', state: '',
})
const form = ref(formDefault())

const filteredUsers = computed(() => {
  let list = users.value
  if (filterRole.value) list = list.filter(u => u.role === filterRole.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(u => u.full_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q))
  }
  return list
})

onMounted(async () => {
  await Promise.all([loadUsers(), loadPlans()])
})

async function loadUsers() {
  loading.value = true
  try {
    const { data } = await api.get('/users')
    users.value = data
  } catch { /* silent */ } finally {
    loading.value = false
  }
}

async function loadPlans() {
  try {
    const { data } = await api.get('/users/plans/access')
    plans.value = data
  } catch { /* silent */ }
}

function openModal(type) {
  modal.value = { show: true, type, saving: false, error: '' }
  form.value = formDefault()
}

function closeModal() {
  modal.value.show = false
}

async function submitForm() {
  if (form.value.password !== form.value.password_confirm) {
    modal.value.error = 'As senhas não coincidem'
    return
  }
  modal.value.saving = true
  modal.value.error = ''
  try {
    const endpoint = modal.value.type === 'ugo' ? '/auth/register/ugo' : '/auth/register/ac'
    await api.post(endpoint, form.value)
    toast('Usuário cadastrado com sucesso!', 'success')
    closeModal()
    await loadUsers()
  } catch (err) {
    modal.value.error = err.response?.data?.detail || 'Erro ao cadastrar usuário'
  } finally {
    modal.value.saving = false
  }
}

async function deactivate(user) {
  if (!confirm(`Desativar ${user.full_name}?`)) return
  try {
    await api.put(`/users/${user.id}/deactivate`)
    toast('Usuário desativado', 'warning')
    await loadUsers()
  } catch {
    toast('Erro ao desativar usuário', 'danger')
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

function roleLabel(r) {
  return { admin: 'Administrador', ugo: 'Op. Logístico', ac: 'Gestor de Conta' }[r] || r
}

function roleBadge(r) {
  return { admin: 'badge badge-dark', ugo: 'badge badge-warning', ac: 'badge badge-info' }[r] || 'badge badge-secondary'
}

function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleDateString('pt-BR')
}

function formatCurrency(v) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}
</script>
