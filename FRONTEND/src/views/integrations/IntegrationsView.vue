<template>
  <div>
    <div class="row">
      <!-- Mercado Livre -->
      <div class="col-md-4">
        <div class="card card-outline card-warning">
          <div class="card-header text-center">
            <h3 class="card-title w-100 text-center">
              <i class="fas fa-store mr-2"></i> Mercado Livre
            </h3>
          </div>
          <div class="card-body text-center">
            <template v-if="mlIntegration">
              <span class="badge badge-success mb-2">Conectado</span>
              <p>{{ mlIntegration.platform_username }}</p>
              <small class="text-muted d-block">
                Última sync: {{ mlIntegration.last_sync_at ? formatDateTime(mlIntegration.last_sync_at) : 'Nunca' }}
              </small>
            </template>
            <template v-else>
              <span class="badge badge-secondary mb-2">Desconectado</span>
              <p class="text-muted">Conecte sua conta do Mercado Livre para importar pedidos automaticamente.</p>
            </template>
          </div>
          <div class="card-footer">
            <button v-if="!mlIntegration" class="btn btn-warning btn-block" @click="connectML">
              <i class="fas fa-plug mr-1"></i> Conectar Mercado Livre
            </button>
            <button v-else class="btn btn-outline-danger btn-block" @click="disconnect(mlIntegration.id, 'ml')">
              <i class="fas fa-unlink mr-1"></i> Desconectar
            </button>
          </div>
        </div>
      </div>

      <!-- Shopee -->
      <div class="col-md-4">
        <div class="card card-outline card-danger">
          <div class="card-header text-center">
            <h3 class="card-title w-100 text-center">
              <i class="fas fa-shopping-bag mr-2"></i> Shopee
            </h3>
          </div>
          <div class="card-body text-center">
            <template v-if="shopeeIntegration">
              <span class="badge badge-success mb-2">Conectado</span>
              <p>Shop ID: {{ shopeeIntegration.platform_user_id }}</p>
            </template>
            <template v-else>
              <span class="badge badge-secondary mb-2">Desconectado</span>
              <p class="text-muted">Conecte sua loja Shopee.</p>
            </template>
          </div>
          <div class="card-footer">
            <button v-if="!shopeeIntegration" class="btn btn-danger btn-block" @click="connectShopee">
              <i class="fas fa-plug mr-1"></i> Conectar Shopee
            </button>
            <button v-else class="btn btn-outline-danger btn-block" @click="disconnect(shopeeIntegration.id, 'shopee')">
              <i class="fas fa-unlink mr-1"></i> Desconectar
            </button>
          </div>
        </div>
      </div>

      <!-- Bling -->
      <div class="col-md-4">
        <div class="card card-outline card-info">
          <div class="card-header text-center">
            <h3 class="card-title w-100 text-center">
              <i class="fas fa-file-invoice mr-2"></i> Bling V3
            </h3>
          </div>
          <div class="card-body text-center">
            <template v-if="blingIntegration">
              <span class="badge badge-success mb-2">Conectado</span>
            </template>
            <template v-else>
              <span class="badge badge-secondary mb-2">Desconectado</span>
              <div class="form-group mt-2">
                <input v-model="blingKey" type="text" class="form-control form-control-sm" placeholder="API Key do Bling V3" />
              </div>
            </template>
          </div>
          <div class="card-footer">
            <button v-if="!blingIntegration" class="btn btn-info btn-block" :disabled="!blingKey" @click="connectBling">
              <i class="fas fa-plug mr-1"></i> Conectar Bling
            </button>
            <button v-else class="btn btn-outline-danger btn-block" @click="disconnect(blingIntegration.id, 'bling')">
              <i class="fas fa-unlink mr-1"></i> Desconectar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatDateTime } from '@/utils/formatters'

const integrations = ref([])
const blingKey = ref('')

const mlIntegration = computed(() => integrations.value.find(i => i.platform === 'mercadolivre' && i.is_active))
const shopeeIntegration = computed(() => integrations.value.find(i => i.platform === 'shopee' && i.is_active))
const blingIntegration = computed(() => integrations.value.find(i => i.platform === 'bling' && i.is_active))

async function loadIntegrations() {
  const { data } = await api.get('/integrations')
  integrations.value = data
}

async function connectML() {
  const { data } = await api.get('/integrations/ml/authorize')
  const popup = window.open(data.auth_url, 'ml_oauth', 'width=600,height=700')
  window.addEventListener('message', async (event) => {
    if (event.origin !== window.location.origin) return
    if (event.data?.platform === 'mercadolivre') {
      await loadIntegrations()
    }
  }, { once: true })
}

async function connectShopee() {
  const { data } = await api.get('/integrations/shopee/authorize')
  window.open(data.auth_url, 'shopee_oauth', 'width=600,height=700')
}

async function connectBling() {
  await api.post('/integrations/bling', { api_key: blingKey.value })
  blingKey.value = ''
  await loadIntegrations()
}

async function disconnect(integrationId, platform) {
  if (!confirm('Desconectar esta integração?')) return
  await api.delete(`/integrations/${platform}/${integrationId}`)
  await loadIntegrations()
}

onMounted(loadIntegrations)
</script>
