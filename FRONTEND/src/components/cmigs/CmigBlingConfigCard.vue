<template>
  <div class="card">
    <div class="card-header">
      <h3 class="card-title"><i class="fas fa-plug mr-2"></i>Integração Bling (ERP)</h3>
    </div>
    <div class="card-body">
      <div v-if="loading" class="text-center py-4">
        <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
      </div>
      <div v-else>
        <div class="alert py-2" :class="status.conectado ? 'alert-success' : 'alert-secondary'">
          <i class="fas mr-1" :class="status.conectado ? 'fa-check-circle' : 'fa-info-circle'"></i>
          <strong>{{ statusLabel }}</strong>
          <span class="d-block small text-muted">
            Conecta esta CMIG à conta Bling dela (OAuth). Depois serão importados categorias, produtos e
            kits do Bling.
          </span>
        </div>

        <!-- Sem credenciais -->
        <div v-if="!status.configurado" class="alert alert-warning py-2 small mb-2">
          <i class="fas fa-exclamation-triangle mr-1"></i>
          {{ status.aviso || 'Bling sem credenciais — cadastre o Client ID e o Secret abaixo.' }}
        </div>

        <!-- Credenciais do app Bling desta CMIG (opcional: se vazias, usa o app padrão do servidor) -->
        <div v-if="canEdit && !status.conectado" class="mb-3">
          <label class="small font-weight-bold mb-1 d-block">Credenciais do app Bling (Client ID / Secret)</label>
          <div class="row">
            <div class="col-md-6 form-group mb-2">
              <input v-model="creds.client_id" class="form-control form-control-sm" placeholder="Client ID" />
            </div>
            <div class="col-md-6 form-group mb-2">
              <input v-model="creds.client_secret" type="password" autocomplete="new-password"
                     class="form-control form-control-sm"
                     :placeholder="status.secret_configurado ? '•••••••• (deixe em branco para manter)' : 'Client Secret'" />
            </div>
          </div>
          <div class="d-flex align-items-center justify-content-between">
            <small class="text-muted">
              {{ status.credenciais_proprias ? 'Usando credenciais próprias desta CMIG.' : 'Sem credenciais próprias — usa o app padrão do servidor, se houver.' }}
            </small>
            <button class="btn btn-sm btn-outline-primary" :disabled="savingCreds || !creds.client_id" @click="saveCreds">
              <i class="fas" :class="savingCreds ? 'fa-spinner fa-spin' : 'fa-save'"></i> Salvar credenciais
            </button>
          </div>
        </div>

        <!-- Conectado: detalhes -->
        <dl v-if="status.conectado" class="row mb-2 small">
          <dt class="col-sm-4">Empresa (Bling)</dt>
          <dd class="col-sm-8">{{ status.empresa_nome || '—' }}</dd>
          <dt class="col-sm-4">Conectado em</dt>
          <dd class="col-sm-8">{{ fmt(status.conectado_em) }}</dd>
          <template v-if="status.ultimo_erro">
            <dt class="col-sm-4 text-danger">Último erro</dt>
            <dd class="col-sm-8 text-danger">{{ status.ultimo_erro }}</dd>
          </template>
        </dl>

        <div v-if="canEdit" class="text-right">
          <template v-if="!status.conectado">
            <button class="btn btn-primary" :disabled="!status.configurado || connecting" @click="connect">
              <i class="fas" :class="connecting ? 'fa-spinner fa-spin' : 'fa-link'"></i>
              {{ connecting ? 'Aguardando autorização...' : 'Conectar ao Bling' }}
            </button>
          </template>
          <template v-else>
            <button class="btn btn-outline-secondary mr-2" :disabled="testing" @click="test">
              <i class="fas" :class="testing ? 'fa-spinner fa-spin' : 'fa-vial'"></i> Testar
            </button>
            <button class="btn btn-outline-danger" :disabled="disconnecting" @click="disconnect">
              <i class="fas" :class="disconnecting ? 'fa-spinner fa-spin' : 'fa-unlink'"></i> Desconectar
            </button>
          </template>
        </div>
        <p v-else class="small text-muted mb-0">Você não tem permissão para gerenciar esta integração.</p>

        <!-- Importar catálogo do Bling (ADR-0040 Fase 2) — só quando conectado + permissão -->
        <CmigBlingImport
          v-if="status.conectado && authStore.hasAction('bling_importar')"
          :cmig-id="Number(cmigId)" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import CmigBlingImport from '@/components/cmigs/CmigBlingImport.vue'

const props = defineProps({ cmigId: { type: Number, required: true } })

const toast = useToast()
const authStore = useAuthStore()

const loading = ref(true)
const connecting = ref(false)
const testing = ref(false)
const disconnecting = ref(false)
const savingCreds = ref(false)
const status = ref({})
const creds = ref({ client_id: '', client_secret: '' })
let popup = null
let poll = null

const canEdit = computed(() => authStore.hasAction('bling_gerenciar'))
const statusLabel = computed(() => {
  if (!status.value.configurado) return 'Indisponível (servidor sem credenciais)'
  return status.value.conectado ? 'Conectado' : 'Não conectado'
})

function fmt(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('pt-BR') } catch { return iso }
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/cmigs/${props.cmigId}/bling/status`)
    status.value = data
    creds.value.client_id = data.client_id || ''
    creds.value.client_secret = ''
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar status do Bling')
  } finally {
    loading.value = false
  }
}

async function saveCreds() {
  savingCreds.value = true
  try {
    await api.patch(`/cmigs/${props.cmigId}/bling/credentials`, {
      client_id: creds.value.client_id,
      client_secret: creds.value.client_secret,
    })
    toast.success('Credenciais do Bling salvas')
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar credenciais')
  } finally {
    savingCreds.value = false
  }
}

async function connect() {
  connecting.value = true
  try {
    const { data } = await api.get(`/cmigs/${props.cmigId}/bling/authorize`)
    popup = window.open(data.url, 'bling_oauth', 'width=620,height=760')
    // Acompanha o popup: quando fechar (callback se autofecha), recarrega o status.
    poll = setInterval(async () => {
      if (!popup || popup.closed) {
        clearInterval(poll); poll = null
        connecting.value = false
        await load()
        if (status.value.conectado) toast.success('Bling conectado!')
      }
    }, 1000)
  } catch (e) {
    connecting.value = false
    toast.error(e.response?.data?.detail || 'Erro ao iniciar a conexão com o Bling')
  }
}

async function test() {
  testing.value = true
  try {
    const { data } = await api.post(`/cmigs/${props.cmigId}/bling/test`)
    toast.success(`Conexão OK${data.empresa ? ' — ' + data.empresa : ''}`)
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha no teste da conexão')
    await load()
  } finally {
    testing.value = false
  }
}

async function disconnect() {
  if (!confirm('Desconectar esta CMIG do Bling?')) return
  disconnecting.value = true
  try {
    await api.delete(`/cmigs/${props.cmigId}/bling/connection`)
    toast.success('Bling desconectado')
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao desconectar')
  } finally {
    disconnecting.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => { if (poll) clearInterval(poll) })
</script>
