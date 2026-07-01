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

          <!-- Abas: selecionar AC existente vs convidar por email (convite só p/ CMIG) -->
          <ul class="nav nav-pills nav-sm mb-3">
            <li class="nav-item">
              <a class="nav-link py-1 px-3" :class="{ active: tab === 'select' }" href="#" @click.prevent="tab = 'select'">
                <i class="fas fa-user-check mr-1"></i>Selecionar AC
              </a>
            </li>
            <li class="nav-item" v-if="isCmig">
              <a class="nav-link py-1 px-3" :class="{ active: tab === 'invite' }" href="#" @click.prevent="tab = 'invite'">
                <i class="fas fa-envelope mr-1"></i>Convidar por e-mail
              </a>
            </li>
          </ul>

          <!-- Selecionar AC existente -->
          <form v-if="tab === 'select'" class="form-inline mb-3" @submit.prevent="add">
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
            <small v-if="!availableAcs.length && !acsError" class="text-muted ml-2 mt-1 d-block w-100">
              Nenhum Gestor de Conta disponível para adicionar. Use "Convidar por e-mail" para trazer alguém novo.
            </small>
            <small v-if="acsError" class="text-danger ml-2 mt-1 d-block w-100">{{ acsError }}</small>
          </form>

          <!-- Convidar por e-mail -->
          <div v-if="tab === 'invite'" class="mb-3">
            <p class="small text-muted mb-2">
              A pessoa recebe um link para se cadastrar. Após o cadastro, o administrador libera o acesso
              e então você poderá adicioná-la pela aba "Selecionar AC".
            </p>
            <form class="form-inline" @submit.prevent="invite">
              <input v-model="inviteEmail" type="email" class="form-control form-control-sm mr-2"
                     style="min-width:280px" placeholder="email@colaborador.com" required>
              <button type="submit" class="btn btn-sm btn-primary" :disabled="inviting || !inviteEmail">
                <i v-if="inviting" class="fas fa-spinner fa-spin mr-1"></i>
                <i v-else class="fas fa-paper-plane mr-1"></i>Enviar convite
              </button>
            </form>
            <div v-if="inviteResult" class="alert py-2 mt-2"
                 :class="inviteResult.already_user ? 'alert-info' : (inviteResult.email_sent ? 'alert-success' : 'alert-warning')">
              <div v-if="inviteResult.already_user">{{ inviteResult.message }}</div>
              <div v-else-if="inviteResult.email_sent">Convite enviado para <strong>{{ inviteEmailSent }}</strong>.</div>
              <div v-else>
                E-mail não pôde ser enviado (SMTP inativo). Copie o link e envie manualmente:
                <div class="input-group input-group-sm mt-1">
                  <input :value="inviteResult.invite_link" class="form-control" readonly>
                  <div class="input-group-append">
                    <button class="btn btn-outline-secondary" @click="copyLink(inviteResult.invite_link)"><i class="fas fa-copy"></i></button>
                  </div>
                </div>
              </div>
            </div>
          </div>

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
const acsError       = ref('')
const selectedUserId = ref(null)
const tab            = ref('select')
const inviteEmail    = ref('')
const inviteEmailSent = ref('')
const inviting       = ref(false)
const inviteResult   = ref(null)

const isCmig = computed(() => props.entityType === 'cmig')

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
  acsError.value = ''
  try {
    // CMIG: endpoint dedicado acessível ao dono (não depende de config_usuarios).
    // Account: mantém o endpoint de usuários existente.
    const url = isCmig.value
      ? `/cmigs/${props.entityId}/collaborators/candidates`
      : '/users?role=ac'
    const { data } = await api.get(url)
    allAcs.value = data
  } catch (e) {
    allAcs.value = []
    acsError.value = e.response?.data?.detail || 'Não foi possível carregar a lista de Gestores de Conta.'
  }
}

async function invite() {
  if (!inviteEmail.value) return
  inviting.value = true
  inviteResult.value = null
  try {
    const { data } = await api.post(`/cmigs/${props.entityId}/invites`, { email: inviteEmail.value })
    inviteResult.value = data
    inviteEmailSent.value = inviteEmail.value
    if (data.already_user) {
      // já é AC ativo — recarrega candidatos p/ aparecer na aba Selecionar
      await loadAcs()
    } else {
      inviteEmail.value = ''
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar convite.')
  } finally {
    inviting.value = false
  }
}

async function copyLink(link) {
  try {
    await navigator.clipboard.writeText(link)
    toast.success('Link copiado')
  } catch {
    toast.info(link)
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
    tab.value = 'select'
    inviteEmail.value = ''
    inviteResult.value = null
    loadAdmins()
    loadAcs()
  }
})
</script>
