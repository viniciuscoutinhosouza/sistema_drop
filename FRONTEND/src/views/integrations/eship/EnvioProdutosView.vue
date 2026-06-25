<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0"><i class="fas fa-truck-loading text-primary mr-2"></i>Envio de Produtos (eShip)</h1>
            <small class="text-muted">Integração com o WMS eShip — produtos, pedidos, NF-e/etiqueta e saldo de estoque por empresa.</small>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div v-if="loading" class="text-center py-5">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>

        <div v-else-if="cmigs.length === 0" class="card">
          <div class="card-body text-center py-5 text-muted">
            <i class="fas fa-warehouse fa-2x mb-3 d-block"></i>
            Nenhuma Conta MIG cadastrada.
          </div>
        </div>

        <div v-else class="row">
          <div class="col-md-6 col-lg-4" v-for="c in cmigs" :key="c.cmig_id">
            <div class="card" :class="c.eship_active && c.eship_configured ? 'card-outline card-success' : 'card-outline card-secondary'">
              <div class="card-header py-2">
                <h3 class="card-title text-truncate">{{ c.company_name || ('CMIG #' + c.cmig_id) }}</h3>
                <span class="badge float-right" :class="statusBadge(c)">{{ statusLabel(c) }}</span>
              </div>
              <div class="card-body p-2">
                <p class="mb-1 small"><i class="fas fa-id-card mr-1 text-muted"></i>{{ c.cnpj || c.cpf || '—' }}</p>
                <p class="mb-1 small" v-if="c.eship_configured">
                  <i class="fas fa-link mr-1 text-muted"></i>{{ c.eship_base_url }}
                </p>
                <p class="mb-2 small" v-if="c.eship_warehouse_code">
                  <i class="fas fa-boxes mr-1 text-muted"></i>Armazém: <code>{{ c.eship_warehouse_code }}</code>
                </p>

                <div v-if="c.eship_active && c.eship_configured">
                  <div class="input-group input-group-sm mb-2">
                    <input v-model="skuQuery[c.cmig_id]" class="form-control" placeholder="SKU (opcional)"
                           @keyup.enter="consultarSaldo(c)">
                    <div class="input-group-append">
                      <button class="btn btn-outline-primary" :disabled="saldoLoading[c.cmig_id]" @click="consultarSaldo(c)">
                        <i class="fas" :class="saldoLoading[c.cmig_id] ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                        Saldo
                      </button>
                    </div>
                  </div>
                  <pre v-if="saldo[c.cmig_id]" class="bg-light p-2 small mb-0" style="max-height:180px;overflow:auto">{{ saldo[c.cmig_id] }}</pre>
                </div>
                <div v-else class="text-center py-2">
                  <RouterLink :to="`/cmigs/${c.cmig_id}`" class="btn btn-sm btn-outline-primary">
                    <i class="fas fa-cog mr-1"></i>Configurar eShip nesta empresa
                  </RouterLink>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card card-outline card-info">
          <div class="card-header py-2"><h6 class="card-title mb-0"><i class="fas fa-info-circle mr-1"></i>Como funciona</h6></div>
          <div class="card-body py-2 small text-muted">
            <ul class="mb-0 pl-3">
              <li>A apikey do eShip é cadastrada em cada <strong>Conta MIG</strong> (Contas MIG → abrir a empresa → card "Integração eShip").</li>
              <li>O envio do <strong>pedido</strong> ao eShip é feito na tela de <strong>Pedidos</strong> (ação eShip por pedido) ou automaticamente no fluxo de separação.</li>
              <li>O eShip é a <strong>fonte de verdade do estoque físico</strong> — consulte o saldo por SKU acima.</li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const loading = ref(true)
const cmigs = ref([])
const skuQuery = reactive({})
const saldo = reactive({})
const saldoLoading = reactive({})

function statusLabel(c) {
  if (!c.eship_configured) return 'Não configurado'
  return c.eship_active ? 'Ativo' : 'Inativo'
}
function statusBadge(c) {
  if (!c.eship_configured) return 'badge-secondary'
  return c.eship_active ? 'badge-success' : 'badge-warning'
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/integrations/eship/cmigs')
    cmigs.value = Array.isArray(data) ? data : []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar integrações')
  } finally {
    loading.value = false
  }
}

async function consultarSaldo(c) {
  saldoLoading[c.cmig_id] = true
  try {
    const params = {}
    if (skuQuery[c.cmig_id]) params.sku = skuQuery[c.cmig_id]
    const { data } = await api.get(`/integrations/eship/cmigs/${c.cmig_id}/saldo`, { params })
    saldo[c.cmig_id] = JSON.stringify(data, null, 2)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao consultar saldo')
  } finally {
    saldoLoading[c.cmig_id] = false
  }
}

onMounted(load)
</script>
