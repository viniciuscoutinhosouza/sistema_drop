<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><i class="fas fa-list-ol text-primary mr-2"></i>Cadastro de CFOPs</h1>
            <small class="text-muted">Códigos Fiscais de Operações e Prestações</small>
          </div>
          <div class="col-sm-6 text-right" v-if="isAdmin">
            <button class="btn btn-primary" @click="openNew">
              <i class="fas fa-plus mr-1"></i> Novo CFOP
            </button>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Filtros -->
        <div class="card">
          <div class="card-body py-2">
            <div class="row align-items-end">
              <div class="col-md-4">
                <label class="small mb-1">Buscar</label>
                <input v-model="filters.q" class="form-control form-control-sm"
                       placeholder="código ou descrição..." @input="onSearch">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Direção</label>
                <select v-model="filters.direction" class="form-control form-control-sm" @change="reload">
                  <option value="">Todas</option>
                  <option value="in">Entradas (1xxx / 2xxx / 3xxx)</option>
                  <option value="out">Saídas (5xxx / 6xxx / 7xxx)</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Status</label>
                <select v-model="filters.activeOnly" class="form-control form-control-sm" @change="reload">
                  <option :value="true">Apenas ativos</option>
                  <option :value="false">Todos (incl. inativos)</option>
                </select>
              </div>
              <div class="col-md-2 text-right">
                <small class="text-muted">{{ filtered.length }} registro(s)</small>
              </div>
            </div>
          </div>
        </div>

        <!-- Tabela -->
        <div class="card">
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-sm table-hover mb-0">
              <thead class="thead-light">
                <tr>
                  <th style="width:80px">Código</th>
                  <th>Descrição</th>
                  <th style="width:100px">Direção</th>
                  <th style="width:80px">Status</th>
                  <th v-if="isAdmin" style="width:100px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="filtered.length === 0">
                  <td :colspan="isAdmin ? 5 : 4" class="text-center text-muted py-4">
                    Nenhum CFOP encontrado.
                  </td>
                </tr>
                <tr v-for="c in filtered" :key="c.id">
                  <td><code class="text-primary font-weight-bold">{{ c.code }}</code></td>
                  <td>
                    {{ c.description }}
                    <small v-if="c.notes" class="d-block text-muted">{{ c.notes }}</small>
                  </td>
                  <td>
                    <span class="badge" :class="c.direction === 'in' ? 'badge-warning' : 'badge-success'">
                      {{ c.direction === 'in' ? 'Entrada' : 'Saída' }}
                    </span>
                  </td>
                  <td>
                    <span class="badge" :class="c.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ c.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td v-if="isAdmin" class="text-right">
                    <button class="btn btn-xs btn-outline-secondary mr-1" @click="openEdit(c)">
                      <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-xs btn-outline-danger" @click="confirmDelete(c)">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </section>

    <!-- Modal criar/editar -->
    <div v-if="showModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-list-ol mr-2"></i>{{ editingId ? 'Editar CFOP' : 'Novo CFOP' }}
            </h5>
            <button type="button" class="close" @click="closeModal"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label class="small">Código <span class="text-danger">*</span></label>
              <input v-model="form.code" class="form-control" maxlength="4" placeholder="ex: 5102"
                     :disabled="!!editingId">
              <small class="form-text text-muted">4 dígitos numéricos</small>
            </div>
            <div class="form-group">
              <label class="small">Direção <span class="text-danger">*</span></label>
              <select v-model="form.direction" class="form-control">
                <option value="in">Entrada (1xxx / 2xxx / 3xxx)</option>
                <option value="out">Saída (5xxx / 6xxx / 7xxx)</option>
              </select>
            </div>
            <div class="form-group">
              <label class="small">Descrição <span class="text-danger">*</span></label>
              <input v-model="form.description" class="form-control"
                     placeholder="ex: Venda de mercadoria adquirida de terceiros (intra-estado)">
            </div>
            <div class="form-group mb-0">
              <label class="small">Observações</label>
              <textarea v-model="form.notes" class="form-control" rows="2"
                        placeholder="informações adicionais (opcional)"></textarea>
            </div>
            <div v-if="editingId" class="form-group mt-2 mb-0">
              <div class="custom-control custom-switch">
                <input type="checkbox" class="custom-control-input" id="activeSwitch"
                       v-model="form.is_active">
                <label class="custom-control-label" for="activeSwitch">Ativo</label>
              </div>
            </div>
            <div v-if="modalError" class="alert alert-danger small mt-2">{{ modalError }}</div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeModal">Cancelar</button>
            <button class="btn btn-primary" :disabled="saving" @click="save">
              <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ saving ? 'Salvando...' : 'Salvar' }}
            </button>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useCfopStore } from '@/stores/cfop'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const cfopStore = useCfopStore()
const authStore = useAuthStore()
const toast = useToast()

const loading = ref(false)
const showModal = ref(false)
const saving = ref(false)
const editingId = ref(null)
const modalError = ref('')

const filters = reactive({ q: '', direction: '', activeOnly: true })
let searchTimer = null

const isAdmin = computed(() => authStore.user?.role === 'admin')

const form = reactive({ code: '', direction: 'out', description: '', notes: '', is_active: true })

const filtered = computed(() => {
  const q = filters.q.toLowerCase()
  return cfopStore.cfops.filter(c => {
    if (!q) return true
    return c.code.includes(q) || c.description.toLowerCase().includes(q)
  })
})

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(reload, 300)
}

async function reload() {
  loading.value = true
  try {
    await cfopStore.fetchAll({
      direction: filters.direction || null,
      activeOnly: filters.activeOnly,
    })
  } catch {
    toast.error('Erro ao carregar CFOPs')
  } finally {
    loading.value = false
  }
}

function openNew() {
  editingId.value = null
  Object.assign(form, { code: '', direction: 'out', description: '', notes: '', is_active: true })
  modalError.value = ''
  showModal.value = true
}

function openEdit(c) {
  editingId.value = c.id
  Object.assign(form, {
    code: c.code,
    direction: c.direction,
    description: c.description,
    notes: c.notes || '',
    is_active: c.is_active,
  })
  modalError.value = ''
  showModal.value = true
}

function closeModal() {
  showModal.value = false
}

async function save() {
  modalError.value = ''
  if (!form.code || !form.description || !form.direction) {
    modalError.value = 'Código, direção e descrição são obrigatórios'
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await cfopStore.update(editingId.value, {
        description: form.description,
        notes: form.notes || null,
        is_active: form.is_active,
        direction: form.direction,
      })
      toast.success('CFOP atualizado')
    } else {
      await cfopStore.create({
        code: form.code,
        direction: form.direction,
        description: form.description,
        notes: form.notes || null,
      })
      toast.success('CFOP criado')
    }
    closeModal()
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Erro ao salvar'
  } finally {
    saving.value = false
  }
}

async function confirmDelete(c) {
  if (!confirm(`Remover CFOP ${c.code}?\n\nPreira desativar CFOPs em uso em vez de deletar.`)) return
  try {
    await cfopStore.remove(c.id)
    toast.success(`CFOP ${c.code} removido`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao remover')
  }
}

onMounted(reload)
</script>
