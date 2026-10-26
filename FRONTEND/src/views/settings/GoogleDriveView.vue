<template>
  <div>
    <h4 class="mb-3 font-weight-bold"><i class="fab fa-google-drive mr-2"></i>Google Drive</h4>

    <div class="card">
      <div class="card-header"><h3 class="card-title">Armazenamento de imagens no Google Drive</h3></div>
      <div class="card-body">
        <div v-if="loading" class="text-center py-4 text-muted">
          <i class="fas fa-spinner fa-spin fa-2x"></i>
        </div>

        <template v-else>
          <!-- Não configurado (faltam credenciais no .env) -->
          <div v-if="!status.configurado" class="alert alert-warning">
            <i class="fas fa-exclamation-triangle mr-1"></i>
            {{ status.aviso || 'Google Drive não configurado no servidor (GOOGLE_CLIENT_ID/SECRET).' }}
          </div>

          <template v-else>
            <!-- Estado da conexão -->
            <div class="d-flex align-items-center flex-wrap mb-3" style="gap:.75rem">
              <span v-if="status.conectado" class="badge badge-success" style="font-size:.85rem">
                <i class="fas fa-check-circle mr-1"></i>Conectado
              </span>
              <span v-else class="badge badge-secondary" style="font-size:.85rem">
                <i class="fas fa-plug mr-1"></i>Não conectado
              </span>
              <span v-if="status.conectado && status.email" class="text-muted">
                {{ status.email }}
              </span>
            </div>

            <table v-if="status.conectado" class="table table-sm table-borderless mb-3" style="max-width:640px">
              <tr><th style="width:200px">Pasta raiz</th><td>{{ status.pasta_raiz_nome }} <span v-if="status.pasta_raiz_id" class="text-muted small">({{ status.pasta_raiz_id }})</span></td></tr>
              <tr v-if="status.cota">
                <th>Espaço usado</th>
                <td>
                  {{ status.cota.usado_gb }} GB<span v-if="status.cota.limite_gb"> de {{ status.cota.limite_gb }} GB</span>
                  <span v-if="status.cota.percentual != null" :class="status.cota.alerta ? 'text-danger font-weight-bold' : 'text-muted'"> ({{ status.cota.percentual }}%)</span>
                  <div v-if="status.cota.alerta" class="text-danger small"><i class="fas fa-exclamation-triangle mr-1"></i>Espaço acima de 80% — considere o Google One.</div>
                </td>
              </tr>
              <tr v-if="status.conectado_em"><th>Conectado em</th><td>{{ formatDateTime(status.conectado_em) }}</td></tr>
              <tr v-if="status.ultimo_erro"><th>Último erro</th><td class="text-danger">{{ status.ultimo_erro }}</td></tr>
            </table>

            <div v-if="status.aviso" class="alert alert-info py-2">{{ status.aviso }}</div>

            <!-- Ações -->
            <div class="d-flex flex-wrap" style="gap:.5rem">
              <button v-if="!status.conectado" class="btn btn-primary" :disabled="busy" @click="connect">
                <i class="fab fa-google-drive mr-1"></i> Conectar ao Google Drive
              </button>
              <template v-else>
                <button class="btn btn-outline-secondary" :disabled="busy" @click="test">
                  <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-vial'"></i> Testar conexão
                </button>
                <button class="btn btn-outline-primary" :disabled="busy" @click="connect">
                  <i class="fas fa-sync mr-1"></i> Reconectar
                </button>
                <button class="btn btn-outline-danger" :disabled="busy" @click="disconnect">
                  <i class="fas fa-unlink mr-1"></i> Desconectar
                </button>
              </template>
              <button class="btn btn-link text-muted" :disabled="busy" @click="load">
                <i class="fas fa-redo mr-1"></i> Atualizar
              </button>
            </div>

            <small class="text-muted d-block mt-3">
              As imagens são guardadas na sua conta Google (pasta <strong>{{ status.pasta_raiz_nome }}</strong>),
              organizadas em subpastas por área. O acesso às fotos é servido pelo próprio sistema (login exigido) —
              o link do Drive não fica público.
            </small>
            <small class="text-muted d-block">
              Redirect URI configurado: <code>{{ status.redirect_uri }}</code>
            </small>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/formatters'

const toast = useToast()
const loading = ref(true)
const busy = ref(false)
const status = reactive({})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/integrations/google-drive/status')
    Object.assign(status, data)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao carregar o status do Google Drive')
  } finally {
    loading.value = false
  }
}

async function connect() {
  busy.value = true
  try {
    const { data } = await api.get('/integrations/google-drive/authorize')
    // Abre a autorização numa aba nova; o callback fecha a aba sozinho ao concluir.
    const win = window.open(data.url, '_blank', 'width=560,height=720')
    toast.info('Autorize o acesso na aba do Google e depois clique em Atualizar.')
    // Revalida o status quando a aba de autorização fechar (ou após um tempo).
    const timer = setInterval(() => {
      if (!win || win.closed) { clearInterval(timer); load() }
    }, 1500)
    setTimeout(() => clearInterval(timer), 180000)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao iniciar a conexão')
  } finally {
    busy.value = false
  }
}

async function test() {
  busy.value = true
  try {
    const { data } = await api.post('/integrations/google-drive/test')
    toast.success(`Conexão OK. Pasta "${data.pasta_raiz_nome}" pronta${data.espaco ? ' — ' + data.espaco : ''}.`)
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Teste falhou')
  } finally {
    busy.value = false
  }
}

async function disconnect() {
  if (!confirm('Desconectar o Google Drive? Os arquivos já enviados permanecem no seu Drive.')) return
  busy.value = true
  try {
    await api.delete('/integrations/google-drive/connection')
    toast.success('Google Drive desconectado.')
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao desconectar')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
