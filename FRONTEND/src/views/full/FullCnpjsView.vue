<template>
  <div>
    <div class="card">
      <div class="card-header d-flex align-items-center justify-content-between">
        <h3 class="card-title mb-0">
          <i class="fas fa-warehouse mr-2"></i>
          CNPJs FULL (ML Fulfillment)
        </h3>
        <button class="btn btn-sm btn-primary" @click="openCreate">
          <i class="fas fa-plus mr-1"></i> Adicionar CNPJ FULL
        </button>
      </div>

      <div class="card-body pb-0">
        <div class="row mb-3">
          <div class="col-md-4">
            <select class="form-control form-control-sm" v-model="filterCmigId" @change="load">
              <option :value="null">Todas as CMIGs</option>
              <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ cmigLabel(c) }}</option>
            </select>
          </div>
          <div class="col-md-4">
            <select class="form-control form-control-sm" v-model="filterAccountId" @change="load">
              <option :value="null">Todas as contas</option>
              <option v-for="a in filteredAccounts" :key="a.id" :value="a.id">
                {{ accountLabel(a) }}
              </option>
            </select>
          </div>
        </div>
      </div>

      <div class="card-body p-0">
        <table class="table table-sm table-hover mb-0">
          <thead class="thead-light">
            <tr>
              <th>CNPJ</th>
              <th>Label</th>
              <th>Conta Marketplace</th>
              <th>CMIG</th>
              <th class="text-center">Status</th>
              <th style="width:100px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="6" class="text-center py-4">
                <i class="fas fa-spinner fa-spin"></i>
              </td>
            </tr>
            <tr v-else-if="!rows.length">
              <td colspan="6" class="text-center py-4 text-muted">
                Nenhum CNPJ FULL cadastrado
              </td>
            </tr>
            <tr v-for="row in rows" :key="row.id">
              <td class="align-middle font-weight-bold">
                {{ formatCnpj(row.cnpj) }}
              </td>
              <td class="align-middle">{{ row.label || '—' }}</td>
              <td class="align-middle">
                {{ accountName(row.marketplace_account_id) }}
              </td>
              <td class="align-middle">{{ cmigName(row.cmig_id) }}</td>
              <td class="text-center align-middle">
                <span :class="row.is_active ? 'badge badge-success' : 'badge badge-secondary'">
                  {{ row.is_active ? 'Ativo' : 'Inativo' }}
                </span>
              </td>
              <td class="text-right align-middle">
                <button class="btn btn-xs btn-outline-secondary mr-1" @click="openEdit(row)" title="Editar">
                  <i class="fas fa-edit"></i>
                </button>
                <button
                  class="btn btn-xs"
                  :class="row.is_active ? 'btn-outline-danger' : 'btn-outline-success'"
                  @click="toggleActive(row)"
                  :title="row.is_active ? 'Desativar' : 'Ativar'"
                >
                  <i :class="row.is_active ? 'fas fa-ban' : 'fas fa-check'"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal criar/editar -->
    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="card shadow" style="width:480px;max-width:95vw">
        <div class="card-header">
          <h5 class="card-title mb-0">{{ editId ? 'Editar CNPJ FULL' : 'Adicionar CNPJ FULL' }}</h5>
        </div>
        <div class="card-body">
          <div v-if="formError" class="alert alert-danger py-2 small">{{ formError }}</div>

          <template v-if="!editId">
            <div class="form-group">
              <label class="small font-weight-bold">CMIG *</label>
              <select class="form-control form-control-sm" v-model="form.cmig_id" @change="onCmigChange">
                <option :value="null">Selecionar...</option>
                <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ cmigLabel(c) }}</option>
              </select>
            </div>
            <div class="form-group">
              <label class="small font-weight-bold">Conta de Marketplace *</label>
              <select class="form-control form-control-sm" v-model="form.marketplace_account_id" :disabled="!form.cmig_id">
                <option :value="null">Selecionar...</option>
                <option v-for="a in modalAccounts" :key="a.id" :value="a.id">
                  {{ accountLabel(a) }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label class="small font-weight-bold">CNPJ do Fulfillment Center *</label>
              <input
                v-model="form.cnpj"
                class="form-control form-control-sm"
                placeholder="00.000.000/0000-00"
                maxlength="18"
              />
              <small class="text-muted">CNPJ do centro de fulfillment do ML para esta conta</small>
            </div>
          </template>

          <div class="form-group">
            <label class="small font-weight-bold">Label (opcional)</label>
            <input v-model="form.label" class="form-control form-control-sm" placeholder="Ex: FULL SP, FULL RJ..." />
          </div>
        </div>
        <div class="card-footer d-flex justify-content-end gap-2">
          <button class="btn btn-sm btn-secondary mr-2" @click="closeModal">Cancelar</button>
          <button class="btn btn-sm btn-primary" @click="save" :disabled="saving">
            <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
            {{ editId ? 'Salvar' : 'Adicionar' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()

const rows = ref([])
const cmigs = ref([])
const accounts = ref([])
const loading = ref(true)
const filterCmigId = ref(null)
const filterAccountId = ref(null)

const showModal = ref(false)
const editId = ref(null)
const form = ref({ cmig_id: null, marketplace_account_id: null, cnpj: '', label: '' })
const formError = ref('')
const saving = ref(false)

const filteredAccounts = computed(() => {
  if (!filterCmigId.value) return accounts.value
  return accounts.value.filter(a => a.cmig_id === filterCmigId.value)
})

const modalAccounts = computed(() => {
  if (!form.value.cmig_id) return []
  return accounts.value.filter(a => a.cmig_id === form.value.cmig_id)
})

function cmigLabel(c) {
  return c ? (c.company_name || c.trade_name || `CMIG #${c.id}`) : ''
}

function accountLabel(a) {
  return a ? (a.description || a.platform_username || a.platform_user_id || `#${a.id}`) : ''
}

function accountName(id) {
  return accountLabel(accounts.value.find(x => x.id === id)) || `#${id}`
}

function cmigName(id) {
  const c = cmigs.value.find(x => x.id === id)
  return c ? cmigLabel(c) : `#${id}`
}

function formatCnpj(v) {
  if (!v) return ''
  const d = v.replace(/\D/g, '')
  if (d.length !== 14) return v
  return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filterCmigId.value) params.cmig_id = filterCmigId.value
    if (filterAccountId.value) params.marketplace_account_id = filterAccountId.value
    const { data } = await api.get('/full-cnpjs', { params })
    rows.value = Array.isArray(data) ? data : []
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  const [{ data: c }, { data: a }] = await Promise.all([
    api.get('/cmigs'),
    api.get('/accounts'),
  ])
  cmigs.value = Array.isArray(c) ? c : (c?.items || [])
  accounts.value = Array.isArray(a) ? a : []
}

function openCreate() {
  editId.value = null
  form.value = { cmig_id: null, marketplace_account_id: null, cnpj: '', label: '' }
  formError.value = ''
  showModal.value = true
}

function openEdit(row) {
  editId.value = row.id
  form.value = { cmig_id: row.cmig_id, marketplace_account_id: row.marketplace_account_id, cnpj: row.cnpj, label: row.label || '' }
  formError.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

function onCmigChange() {
  form.value.marketplace_account_id = null
}

async function save() {
  formError.value = ''
  if (!editId.value) {
    if (!form.value.cmig_id || !form.value.marketplace_account_id || !form.value.cnpj.trim()) {
      formError.value = 'Preencha todos os campos obrigatórios'
      return
    }
  }
  saving.value = true
  try {
    if (editId.value) {
      await api.put(`/full-cnpjs/${editId.value}`, { label: form.value.label })
      toast.success('CNPJ atualizado')
    } else {
      await api.post('/full-cnpjs', form.value)
      toast.success('CNPJ adicionado')
    }
    closeModal()
    await load()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Erro ao salvar'
  } finally {
    saving.value = false
  }
}

async function toggleActive(row) {
  try {
    await api.put(`/full-cnpjs/${row.id}`, { is_active: !row.is_active })
    row.is_active = !row.is_active
    toast.success(row.is_active ? 'CNPJ ativado' : 'CNPJ desativado')
  } catch {
    toast.error('Erro ao atualizar status')
  }
}

onMounted(async () => {
  await loadMeta()
  await load()
})
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
</style>
