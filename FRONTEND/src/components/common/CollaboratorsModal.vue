<template>
  <div v-if="visible" class="modal fade show d-block" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-user-friends mr-2"></i>Colaboradores
            <small class="text-muted ml-2" v-if="entityLabel">— {{ entityLabel }}</small>
          </h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>

          <!-- Adicionar colaborador -->
          <form class="form-inline mb-3" @submit.prevent="add">
            <label class="mr-2 mb-0"><i class="fas fa-user-plus mr-1"></i>Adicionar AC:</label>
            <select v-model.number="selectedUserId" class="form-control form-control-sm mr-2" style="min-width:260px">
              <option :value="null">— selecione um AC —</option>
              <option v-for="u in availableAcs" :key="u.id" :value="u.id">
                {{ u.full_name }} <span v-if="u.email">({{ u.email }})</span>
              </option>
            </select>
            <button type="submit" class="btn btn-sm btn-primary"
                    :disabled="!selectedUserId || saving">
              <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
              <i v-else class="fas fa-plus mr-1"></i>Adicionar
            </button>
          </form>

          <div v-if="loading" class="text-center py-3">
            <i class="fas fa-spinner fa-spin"></i> Carregando...
          </div>
          <div v-else-if="admins.length === 0" class="text-center text-muted py-3">
            Nenhum colaborador cadastrado.
          </div>
          <table v-else class="table table-sm table-hover mb-0">
            <thead>
              <tr>
                <th>Nome</th>
                <th>E-mail</th>
                <th>Função</th>
                <th class="text-right" style="width:90px">Ações</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in admins" :key="a.user_id">
                <td>{{ a.full_name }}</td>
                <td class="small text-muted">{{ a.email }}</td>
                <td>
                  <span v-if="a.is_owner" class="badge badge-success">
                    <i class="fas fa-crown mr-1"></i>Proprietário
                  </span>
                  <span v-else class="badge badge-secondary">Colaborador</span>
                </td>
                <td class="text-right">
                  <button v-if="!a.is_owner" class="btn btn-xs btn-outline-danger"
                          :disabled="removingId === a.user_id"
                          @click="remove(a)" title="Remover colaborador">
                    <i v-if="removingId === a.user_id" class="fas fa-spinner fa-spin"></i>
                    <i v-else class="fas fa-trash"></i>
                  </button>
                  <span v-else class="text-muted small">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="$emit('close')">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  visible:     { type: Boolean, default: false },
  entityType:  { type: String,  required: true, validator: v => ['cmig', 'account'].includes(v) },
  entityId:    { type: [Number, String], default: null },
  entityLabel: { type: String,  default: '' },
})
defineEmits(['close'])

const toast = useToast()

const admins         = ref([])
const allAcs         = ref([])
const loading        = ref(false)
const saving         = ref(false)
const removingId     = ref(null)
const error          = ref('')
const selectedUserId = ref(null)

const baseUrl = computed(() => {
  if (!props.entityId) return ''
  return props.entityType === 'cmig'
    ? `/cmigs/${props.entityId}/admins`
    : `/accounts/${props.entityId}/admins`
})

const adminIds = computed(() => new Set(admins.value.map(a => a.user_id)))
const availableAcs = computed(() =>
  allAcs.value.filter(u => u.role === 'ac' && !adminIds.value.has(u.id))
)

async function loadAdmins() {
  if (!baseUrl.value) return
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(baseUrl.value)
    admins.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao carregar colaboradores.'
  } finally {
    loading.value = false
  }
}

async function loadAcs() {
  try {
    const { data } = await api.get('/users?role=ac')
    allAcs.value = data
  } catch {
    allAcs.value = []
  }
}

async function add() {
  if (!selectedUserId.value) return
  error.value = ''
  saving.value = true
  try {
    await api.post(baseUrl.value, { user_id: selectedUserId.value })
    toast.success('Colaborador adicionado!')
    selectedUserId.value = null
    await loadAdmins()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao adicionar colaborador.'
  } finally {
    saving.value = false
  }
}

async function remove(admin) {
  if (!confirm(`Remover ${admin.full_name} dos colaboradores?`)) return
  removingId.value = admin.user_id
  try {
    await api.delete(`${baseUrl.value}/${admin.user_id}`)
    toast.success('Colaborador removido!')
    await loadAdmins()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao remover colaborador.')
  } finally {
    removingId.value = null
  }
}

watch(() => props.visible, (v) => {
  if (v) {
    selectedUserId.value = null
    error.value = ''
    loadAdmins()
    loadAcs()
  }
})
</script>
