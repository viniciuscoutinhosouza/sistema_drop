<template>
  <div class="card h-100">
    <div class="card-body d-flex flex-column">
      <div class="d-flex align-items-center mb-3">
        <img :src="logoSrc" :alt="platform" style="height:36px;object-fit:contain" class="mr-3" />
        <div>
          <h6 class="mb-0">{{ title }}</h6>
          <small class="text-muted">{{ subtitle }}</small>
        </div>
      </div>

      <!-- Connected state -->
      <div v-if="integration && integration.is_active" class="mb-3">
        <span class="badge badge-success mr-2"><i class="fas fa-check-circle mr-1"></i>Conectado</span>
        <small class="text-muted d-block mt-1">
          {{ integration.platform_username || integration.platform_user_id }}
        </small>
        <small v-if="integration.last_sync_at" class="text-muted d-block">
          Última sync: {{ formatDate(integration.last_sync_at) }}
        </small>
      </div>

      <!-- Disconnected state -->
      <div v-else class="mb-3">
        <span class="badge badge-secondary">Não conectado</span>
      </div>

      <!-- Bling API key field -->
      <div v-if="platform === 'bling' && !integration?.is_active" class="form-group mb-3">
        <label class="small">API Key Bling</label>
        <input v-model="blingKey" type="text" class="form-control form-control-sm" placeholder="Cole sua API Key" />
      </div>

      <div class="mt-auto d-flex gap-2">
        <button
          v-if="!integration?.is_active"
          class="btn btn-sm btn-primary"
          :disabled="loading"
          @click="connect"
        >
          <i v-if="loading" class="fas fa-spinner fa-spin mr-1"></i>
          <i v-else class="fas fa-plug mr-1"></i>
          Conectar
        </button>
        <button
          v-else
          class="btn btn-sm btn-outline-danger"
          :disabled="loading"
          @click="disconnect"
        >
          Desconectar
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/composables/useApi'
import { formatDate } from '@/utils/formatters'

const props = defineProps({
  platform:    { type: String, required: true },  // 'mercadolivre' | 'shopee' | 'bling'
  title:       { type: String, required: true },
  subtitle:    { type: String, default: '' },
  logoSrc:     { type: String, required: true },
  integration: { type: Object, default: null },   // from GET /integrations
})

const emit = defineEmits(['connected', 'disconnected'])

const loading  = ref(false)
const blingKey = ref('')

async function connect() {
  loading.value = true
  try {
    if (props.platform === 'bling') {
      await api.post('/integrations/bling', { api_key: blingKey.value })
      emit('connected')
    } else {
      // OAuth popup flow
      const { data } = await api.get(`/integrations/${props.platform}/auth-url`)
      const popup = window.open(data.url, 'oauth', 'width=600,height=700')
      const handler = (e) => {
        if (e.data?.type === 'oauth_success' && e.data.platform === props.platform) {
          window.removeEventListener('message', handler)
          popup?.close()
          emit('connected')
        }
      }
      window.addEventListener('message', handler)
    }
  } catch (err) {
    console.error('Connect error', err)
  } finally {
    loading.value = false
  }
}

async function disconnect() {
  if (!confirm(`Desconectar ${props.title}?`)) return
  loading.value = true
  try {
    await api.delete(`/integrations/${props.platform}`)
    emit('disconnected')
  } finally {
    loading.value = false
  }
}
</script>
