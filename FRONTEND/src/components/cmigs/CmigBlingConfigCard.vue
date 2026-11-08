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

        <!-- Config ausente no servidor -->
        <div v-if="!status.configurado" class="alert alert-warning py-2 small mb-2">
          <i class="fas fa-exclamation-triangle mr-1"></i>
          {{ status.aviso || 'Bling não configurado no servidor (BLING_CLIENT_ID/SECRET).' }}
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
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({ cmigId: { type: Number, required: true } })

const toast = useToast()
const authStore = useAuthStore()

const loading = ref(true)
const connecting = ref(false)
const testing = ref(false)
const disconnecting = ref(false)
const status = ref({})
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
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar status do Bling')
  } finally {
    loading.value = false
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
