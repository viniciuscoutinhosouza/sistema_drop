<template>
  <div>
    <div class="d-flex align-items-center mb-3">
      <h1 class="h4 mb-0"><i class="fas fa-warehouse mr-2 text-primary"></i>Armazenaki</h1>
      <span class="badge badge-light ml-2">Conciliação eShip</span>
    </div>

    <div class="card">
      <div class="card-header d-flex align-items-center flex-wrap" style="gap:.5rem">
        <!-- Filtro por CMIG (inclui "Todas as CMIGs") -->
        <div class="form-group mb-0" style="min-width:280px">
          <select class="form-control form-control-sm" v-model="cmigId" @change="load" :disabled="loading">
            <option :value="null" disabled>Selecione…</option>
            <option value="all">★ Todas as CMIGs</option>
            <option v-for="c in cmigsAtivas" :key="c.cmig_id" :value="c.cmig_id">
              {{ c.company_name }}{{ c.cnpj ? ` — ${c.cnpj}` : (c.cpf ? ` — ${c.cpf}` : '') }}
            </option>
          </select>
        </div>
        <!-- Filtro por status (client-side) -->
        <div class="form-group mb-0" style="min-width:180px">
          <select class="form-control form-control-sm" v-model="statusFilter" :disabled="loading || !data">
            <option value="">Todos os status</option>
            <option value="conciliado">Conciliados</option>
            <option value="so_sistema">Só no sistema</option>
            <option value="indeterminado">Indeterminados</option>
            <option value="falhou">Falhou envio</option>
            <option value="cancelado">Cancelados</option>
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
          Selecione <strong>uma CMIG</strong> ou <strong>Todas as CMIGs</strong> para conciliar os pedidos
          enviados ao eShip com as ordens que estão de fato no WMS.
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
            <span class="badge badge-info p-2">No WMS: {{ data.wms_count }}</span>
          </div>

          <!-- Avisos de qualidade da consulta ao WMS -->
          <div v-for="(err, i) in wmsErrors" :key="i" class="alert alert-danger py-2 small">
            <i class="fas fa-exclamation-triangle mr-1"></i>
            Falha ao consultar o eShip: {{ err }}. A lista mostra o lado do sistema; divergências ficam indeterminadas.
          </div>
          <div v-if="wmsMeta.escopo_indefinido" class="alert alert-warning py-2 small">
            <i class="fas fa-exclamation-circle mr-1"></i>
            A CMIG não tem CNPJ/CPF cadastrado — sem ele não dá para isolar a empresa no WMS multi-tenant.
            Cadastre o documento na CMIG para conciliar.
          </div>
          <div v-else-if="wmsMeta.parcial || wmsMeta.truncado" class="alert alert-warning py-2 small">
            <i class="fas fa-exclamation-circle mr-1"></i>
            Varredura do WMS <strong>incompleta</strong>{{ wmsMeta.truncado ? ' (muitas páginas)' : '' }}{{ wmsMeta.parcial ? ' (falha em páginas)' : '' }} —
            os "Só no sistema" viram "Indeterminado". Atualize novamente.
          </div>

          <!-- Enviados pelo sistema (com estado de conciliação) -->
          <h2 class="h6 text-muted mt-2">
            Pedidos enviados ao eShip pelo sistema
            <span v-if="statusFilter" class="badge badge-light">filtro: {{ statusLabel(statusFilter) }} ({{ filteredLocal.length }})</span>
          </h2>
          <div class="table-responsive">
            <table class="table table-sm table-hover">
              <thead>
                <tr>
                  <th v-if="isAll">CMIG</th>
                  <th style="width:70px">Pedido</th>
                  <th style="width:120px">Data</th>
                  <th>numeroOrigem</th>
                  <th>Comprador</th>
                  <th style="width:130px">Conciliação</th>
                  <th>Status no WMS</th>
                  <th style="width:260px">Ordem eShip</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in filteredLocal" :key="row.order_id"
                    :class="{ 'table-danger': isDivergencia(row) }">
                  <td v-if="isAll" class="small">{{ row.cmig_name || '—' }}</td>
                  <td class="text-monospace">#{{ row.order_id }}</td>
                  <td class="small">{{ fmtDate(row.data) }}</td>
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
                    <span v-else-if="!row.wms_confiavel" class="badge badge-secondary"
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
                <tr v-if="!filteredLocal.length">
                  <td :colspan="isAll ? 8 : 7" class="text-center text-muted py-3">
                    {{ statusFilter ? 'Nenhum pedido neste status.' : 'Nenhum pedido enviado ao eShip.' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- TODAS as ordens que estão no eShip (WMS), marcando conciliadas × só no eShip -->
          <template v-if="wmsOrdens.length">
            <h2 class="h6 text-muted mt-3">
              <i class="fas fa-dolly-flatbed text-info mr-1"></i>
              Ordens no eShip (WMS) — {{ wmsOrdens.length }}
              <span class="badge badge-success">{{ wmsConciliadas }} conciliadas</span>
              <span class="badge badge-warning">{{ data.so_eship_count }} só no eShip</span>
            </h2>
            <div class="table-responsive">
              <table class="table table-sm">
                <thead>
                  <tr>
                    <th v-if="isAll">CMIG</th>
                    <th style="width:130px">Conciliação</th>
                    <th>numeroOrigem</th>
                    <th>Ordem eShip</th>
                    <th>Destinatário</th>
                    <th>Status</th>
                    <th>Data/Hora</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="w in wmsOrdens" :key="`${w.eship_order_id || ''}-${w.numero_origem}`"
                      :class="{ 'table-success': w.conciliado }">
                    <td v-if="isAll" class="small">
                      <span v-if="w.cmig_ambiguo" class="text-muted" title="idTipo compartilhado — não dá para atribuir a uma CMIG">(compartilhado)</span>
                      <span v-else>{{ w.cmig_name || '—' }}</span>
                    </td>
                    <td>
                      <span v-if="w.conciliado" class="badge badge-success">
                        <i class="fas fa-check mr-1"></i>Conciliada
                      </span>
                      <span v-else class="badge badge-warning">
                        <i class="fas fa-exclamation-triangle mr-1"></i>Só no eShip
                      </span>
                    </td>
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
const statusFilter = ref('')

const cmigsAtivas = computed(() => cmigs.value.filter((c) => c.eship_active))
const isAll = computed(() => cmigId.value === 'all')
// Lista completa das ordens do WMS (com fallback p/ payloads antigos que só traziam so_eship).
const wmsOrdens = computed(() => data.value?.wms_ordens || data.value?.so_eship || [])
const wmsConciliadas = computed(() => wmsOrdens.value.filter((w) => w.conciliado).length)
const wmsMeta = computed(() => data.value?.wms_meta || {})
const wmsErrors = computed(() => {
  if (!data.value) return []
  if (data.value.wms_errors) return data.value.wms_errors          // consolidado
  return data.value.wms_error ? [data.value.wms_error] : []        // per-CMIG
})

const STATUS_LABELS = {
  conciliado: 'Conciliados', so_sistema: 'Só no sistema',
  indeterminado: 'Indeterminados', falhou: 'Falhou envio', cancelado: 'Cancelados',
}
function statusLabel(s) { return STATUS_LABELS[s] || s }

// Estado derivado de cada linha (mesma lógica dos badges) — usado pelo filtro por status.
function estadoOf(row) {
  if (row.cancelado) return 'cancelado'
  if (row.falhou) return 'falhou'
  if (row.conciliado) return 'conciliado'
  if (!row.wms_confiavel) return 'indeterminado'
  return 'so_sistema'
}
const filteredLocal = computed(() => {
  const rows = data.value?.local || []
  return statusFilter.value ? rows.filter((r) => estadoOf(r) === statusFilter.value) : rows
})

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

// Divergência real (linha em vermelho) = enviado, só no sistema, com o WMS confiável (por linha).
function isDivergencia(row) {
  return estadoOf(row) === 'so_sistema'
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

// Normaliza os dois payloads (consolidado e per-CMIG) para um shape único de renderização:
// cada linha local ganha `wms_confiavel` (no per-CMIG é global; no consolidado já vem por linha).
function normalize(res) {
  if (!res.consolidado) {
    const conf = !!res.wms_confiavel
    for (const r of res.local || []) if (r.wms_confiavel === undefined) r.wms_confiavel = conf
  }
  return res
}

async function load() {
  if (!cmigId.value) return
  loading.value = true
  data.value = null
  try {
    const url = isAll.value
      ? '/integrations/eship/reconciliacao'
      : `/integrations/eship/cmigs/${cmigId.value}/reconciliacao`
    const { data: res } = await api.get(url)
    data.value = normalize(res)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao conciliar com o eShip')
  } finally {
    loading.value = false
  }
}

onMounted(loadCmigs)
</script>
