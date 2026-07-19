<template>
  <div>
    <div class="d-flex align-items-center mb-3">
      <h1 class="h4 mb-0"><i class="fas fa-warehouse mr-2 text-primary"></i>Armazenaki</h1>
      <span class="badge badge-light ml-2">Conciliação eShip</span>
    </div>

    <div class="card">
      <div class="card-header d-flex align-items-center flex-wrap" style="gap:.5rem">
        <div class="form-group mb-0" style="min-width:280px">
          <select class="form-control form-control-sm" v-model="cmigId" @change="load" :disabled="loading">
            <option :value="null" disabled>Selecione uma CMIG com eShip…</option>
            <option v-for="c in cmigsAtivas" :key="c.cmig_id" :value="c.cmig_id">
              {{ c.company_name }}{{ c.cnpj ? ` — ${c.cnpj}` : (c.cpf ? ` — ${c.cpf}` : '') }}
            </option>
          </select>
        </div>
        <button class="btn btn-sm btn-outline-primary" :disabled="!cmigId || loading" @click="load">
          <i class="fas mr-1" :class="loading ? 'fa-spinner fa-spin' : 'fa-sync'"></i>Atualizar (ao vivo)
        </button>
        <div v-if="cmigsAtivas.length === 0 && !loadingCmigs" class="text-muted small ml-2">
          Nenhuma CMIG com eShip ativo à sua vista.
        </div>
      </div>

      <div class="card-body">
        <div v-if="!cmigId" class="text-center text-muted py-5">
          <i class="fas fa-warehouse fa-2x mb-2 d-block"></i>
          Selecione uma CMIG configurada com o eShip para conciliar os pedidos enviados
          com as ordens que estão de fato no WMS.
        </div>

        <div v-else-if="loading" class="text-center text-muted py-5">
          <i class="fas fa-spinner fa-spin fa-2x mb-2 d-block"></i>Consultando o eShip ao vivo…
        </div>

        <template v-else-if="data">
          <!-- Resumo -->
          <div class="d-flex flex-wrap mb-3" style="gap:.5rem">
            <span class="badge badge-secondary p-2">Enviados: {{ data.enviados_count }}</span>
            <span class="badge badge-success p-2">Conciliados: {{ data.conciliados_count }}</span>
            <span class="badge p-2" :class="data.so_sistema_count ? 'badge-danger' : 'badge-light'">
              Só no sistema: {{ data.so_sistema_count }}
            </span>
            <span class="badge p-2" :class="data.so_eship_count ? 'badge-warning' : 'badge-light'">
              Só no eShip: {{ data.so_eship_count }}
            </span>
            <span v-if="data.cancelados_count" class="badge badge-dark p-2">
              Cancelados: {{ data.cancelados_count }}
            </span>
            <span class="badge badge-info p-2">No WMS (empresa): {{ data.wms_count }}</span>
          </div>

          <!-- Avisos de qualidade da consulta ao WMS -->
          <div v-if="data.wms_error" class="alert alert-danger py-2 small">
            <i class="fas fa-exclamation-triangle mr-1"></i>
            Não foi possível consultar o eShip: {{ data.wms_error }}. A lista mostra apenas o lado do sistema.
          </div>
          <div v-else-if="wmsMeta.escopo_indefinido" class="alert alert-warning py-2 small">
            <i class="fas fa-exclamation-circle mr-1"></i>
            A CMIG não tem CNPJ/CPF cadastrado — sem ele não dá para isolar a empresa no WMS multi-tenant.
            Cadastre o documento na CMIG para conciliar.
          </div>
          <div v-else-if="wmsMeta.parcial || wmsMeta.truncado" class="alert alert-warning py-2 small">
            <i class="fas fa-exclamation-circle mr-1"></i>
            Varredura do WMS <strong>incompleta</strong>{{ wmsMeta.truncado ? ' (muitas páginas)' : '' }}{{ wmsMeta.parcial ? ' (falha em páginas)' : '' }} —
            a coluna "Só no sistema" pode conter falsos positivos. Atualize novamente.
          </div>

          <!-- Enviados pelo sistema (com estado de conciliação) -->
          <h2 class="h6 text-muted mt-2">Pedidos enviados ao eShip pelo sistema</h2>
          <div class="table-responsive">
            <table class="table table-sm table-hover">
              <thead>
                <tr>
                  <th style="width:70px">Pedido</th>
                  <th>numeroOrigem</th>
                  <th>Comprador</th>
                  <th style="width:130px">Conciliação</th>
                  <th>Status no WMS</th>
                  <th style="width:260px">Ordem eShip</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in data.local" :key="row.order_id"
                    :class="{ 'table-danger': isDivergencia(row) }">
                  <td class="text-monospace">#{{ row.order_id }}</td>
                  <td class="text-monospace small">{{ row.numero_origem }}</td>
                  <td class="small">{{ row.buyer_name || '—' }}</td>
                  <td>
                    <span v-if="row.cancelado" class="badge badge-dark">
                      <i class="fas fa-ban mr-1"></i>Cancelado
                    </span>
                    <span v-else-if="row.falhou" class="badge badge-warning"
                          :title="row.dispatch_error || 'Falha no último envio ao eShip'">
                      <i class="fas fa-exclamation-triangle mr-1"></i>Falhou envio
                    </span>
                    <span v-else-if="row.conciliado" class="badge badge-success">
                      <i class="fas fa-check mr-1"></i>Conciliado
                    </span>
                    <span v-else-if="!data.wms_confiavel" class="badge badge-secondary"
                          title="Não deu para varrer o WMS por completo — situação indeterminada">
                      <i class="fas fa-question mr-1"></i>Indeterminado
                    </span>
                    <span v-else class="badge badge-danger">
                      <i class="fas fa-times mr-1"></i>Só no sistema
                    </span>
                  </td>
                  <td class="small">{{ row.wms_status || '—' }}</td>
                  <td><OrderEShipActions :order="asOrder(row)" @updated="load" /></td>
                </tr>
                <tr v-if="!data.local.length">
                  <td colspan="6" class="text-center text-muted py-3">Nenhum pedido enviado ao eShip para esta CMIG.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Ordens que estão no eShip mas sem registro de envio local -->
          <template v-if="data.so_eship.length">
            <h2 class="h6 text-muted mt-3">
              <i class="fas fa-exclamation-triangle text-warning mr-1"></i>
              Ordens no eShip sem registro de envio local ({{ data.so_eship.length }})
            </h2>
            <div class="table-responsive">
              <table class="table table-sm">
                <thead>
                  <tr>
                    <th>numeroOrigem</th>
                    <th>Ordem eShip</th>
                    <th>Destinatário</th>
                    <th>Status</th>
                    <th>Data/Hora</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="w in data.so_eship" :key="w.numero_origem">
                    <td class="text-monospace small">{{ w.numero_origem }}</td>
                    <td class="text-monospace small">{{ w.eship_order_id || '—' }}</td>
                    <td class="small">{{ w.destinatario || '—' }}</td>
                    <td class="small">{{ w.status_desc || '—' }}</td>
                    <td class="small">{{ fmtDate(w.data_hora) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/formatters'
import OrderEShipActions from '@/views/integrations/eship/OrderEShipActions.vue'

const toast = useToast()
const cmigs = ref([])
const loadingCmigs = ref(false)
const cmigId = ref(null)
const data = ref(null)
const loading = ref(false)

const cmigsAtivas = computed(() => cmigs.value.filter((c) => c.eship_active))
const wmsMeta = computed(() => data.value?.wms_meta || {})

// Mapeia a linha da conciliação para o shape que OrderEShipActions consome (order.eship_*).
function asOrder(row) {
  return {
    id: row.order_id,
    platform_order_id: row.numero_origem,
    eship_order_id: row.eship_order_id,
    eship_dispatch_status: row.dispatch_status,
    eship_dispatch_error: row.dispatch_error,
    eship_nfe_attached: row.nfe_attached ? 1 : 0,
    eship_label_attached: row.label_attached ? 1 : 0,
    eship_enviada: !row.cancelado
      && (!!row.eship_order_id || ['sent', 'partial'].includes(row.dispatch_status)),
  }
}

function fmtDate(v) {
  return v ? formatDateTime(v) : '—'
}

// Divergência real (linha em vermelho) = enviado, presente só no sistema, com o WMS confiável.
// Cancelado, falhou-sem-id e WMS incompleto NÃO são divergência (rótulo próprio / indeterminado).
function isDivergencia(row) {
  return !row.conciliado && !row.cancelado && !row.falhou && !!data.value?.wms_confiavel
}

async function loadCmigs() {
  loadingCmigs.value = true
  try {
    const { data: rows } = await api.get('/integrations/eship/cmigs')
    cmigs.value = rows || []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar as CMIGs')
  } finally {
    loadingCmigs.value = false
  }
}

async function load() {
  if (!cmigId.value) return
  loading.value = true
  data.value = null
  try {
    const { data: res } = await api.get(`/integrations/eship/cmigs/${cmigId.value}/reconciliacao`)
    data.value = res
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao conciliar com o eShip')
  } finally {
    loading.value = false
  }
}

onMounted(loadCmigs)
</script>
