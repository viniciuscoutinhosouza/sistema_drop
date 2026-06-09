<template>
  <div>
    <div class="alert alert-info py-2 small">
      <strong>DRE (Demonstração do Resultado do Exercício):</strong>
      composta pelos lançamentos cadastrados nesta tela e pelos valores das transações dos
      marketplaces. Clique no ícone de atualizar <i class="fas fa-sync"></i> no mês desejado para
      sincronizar os valores com o Mercado Livre.
    </div>

    <!-- Filtros -->
    <div class="card">
      <div class="card-header d-flex align-items-center flex-wrap">
        <div class="d-flex align-items-center mr-2">
          <select v-model="cmigId" class="form-control form-control-sm" style="width:220px">
            <option :value="null" disabled>Selecione a CMIG…</option>
            <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.trade_name }}</option>
          </select>
          <select v-model.number="year" class="form-control form-control-sm ml-2" style="width:110px">
            <option v-for="y in yearOptions" :key="y" :value="y">{{ y }}</option>
          </select>
          <button class="btn btn-sm btn-primary ml-2" :disabled="!cmigId || loading" @click="loadDre">
            <i class="fas fa-search mr-1"></i> Buscar
          </button>
        </div>
        <div class="ml-auto d-flex">
          <button class="btn btn-sm btn-outline-success mr-2" :disabled="!grid" @click="exportCsv">
            <i class="fas fa-file-excel mr-1"></i> Excel
          </button>
          <button class="btn btn-sm btn-outline-danger mr-2" :disabled="!grid" @click="exportPdf">
            <i class="fas fa-file-pdf mr-1"></i> PDF
          </button>
          <button class="btn btn-sm btn-success" :disabled="!cmigId" @click="openNewEntry">
            <i class="fas fa-plus mr-1"></i> Lançamento
          </button>
        </div>
      </div>

      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>
        <div v-else-if="!grid" class="text-center py-4 text-muted">
          Selecione uma CMIG e o ano e clique em Buscar.
        </div>
        <div v-else class="table-responsive" id="dre-print-area">
          <table class="table table-sm table-bordered mb-0" style="font-size:.82rem">
            <thead>
              <tr>
                <th style="min-width:230px"></th>
                <th v-for="(m, i) in grid.months" :key="i" class="text-right" style="white-space:nowrap">
                  {{ m }}
                  <i class="fas fa-sync ml-1"
                     :class="syncingMonth === (i + 1) ? 'fa-spin' : ''"
                     style="cursor:pointer"
                     :title="grid.synced[i + 1] ? 'Sincronizado em ' + formatDateTime(grid.synced[i + 1]) : 'Nunca sincronizado — clique para sincronizar'"
                     @click="syncMonth(i + 1)"></i>
                  <i class="fas fa-search ml-1 text-info"
                     style="cursor:pointer"
                     title="Ver auditoria (banco / ao vivo / billing) deste mês"
                     @click="openDebug(i + 1)"></i>
                </th>
                <th class="text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(row, ri) in grid.rows" :key="ri">
                <tr :style="rowStyle(row)">
                  <td :style="row.kind === 'line' ? 'padding-left:1.5rem' : 'font-weight:bold'">
                    {{ row.label }}
                  </td>
                  <td v-for="(v, i) in row.values" :key="i" class="text-right">
                    {{ v ? formatCurrency(v) : '-' }}
                  </td>
                  <td class="text-right" style="font-weight:bold">
                    {{ row.total ? formatCurrency(row.total) : '-' }}
                  </td>
                </tr>
                <!-- linha de % para margem/lucro -->
                <tr v-if="row.kind === 'result'" :style="rowStyle(row)">
                  <td></td>
                  <td v-for="(p, i) in row.pct" :key="i" class="text-right">
                    {{ p ? p.toFixed(2) + '%' : '%' }}
                  </td>
                  <td class="text-right" style="font-weight:bold">
                    {{ row.pct_total ? row.pct_total.toFixed(2) + '%' : '%' }}
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Modal de auditoria -->
    <div v-if="showDebug" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-search mr-2"></i>Auditoria — {{ debugMonthLabel }}/{{ year }}
            </h5>
            <button type="button" class="close" @click="showDebug = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="debugLoading" class="text-center py-3">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else-if="debugError" class="alert alert-warning">{{ debugError }}</div>
            <div v-else>
              <p class="small text-muted mb-2">
                Fonte usada: <strong>{{ debugData.source }}</strong> ·
                sincronizado em {{ debugData.last_synced_at ? formatDateTime(debugData.last_synced_at) : '—' }}.
                Compare <code>reconciliacao.live.faturamento</code> com o "Vendas brutas" do ML.
              </p>
              <pre style="max-height:55vh;overflow:auto;background:#f4f4f4;padding:.75rem;font-size:.78rem">{{ JSON.stringify(debugData, null, 2) }}</pre>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showDebug = false">Fechar</button>
          </div>
        </div>
      </div>
    </div>

    <DREEntryModal
      v-if="showEntryModal"
      :cmig-id="cmigId"
      :year="year"
      @close="showEntryModal = false"
      @saved="onEntriesSaved"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import DREEntryModal from './DREEntryModal.vue'

const toast = useToast()

const cmigs = ref([])
const cmigId = ref(null)
const year = ref(new Date().getFullYear())
const grid = ref(null)
const loading = ref(false)
const syncingMonth = ref(null)
const showEntryModal = ref(false)

const showDebug = ref(false)
const debugLoading = ref(false)
const debugError = ref('')
const debugData = ref({})
const debugMonth = ref(null)
const debugMonthLabel = computed(() => (debugMonth.value && grid.value ? grid.value.months[debugMonth.value - 1] : ''))

const yearOptions = computed(() => {
  const y = new Date().getFullYear()
  return [y + 1, y, y - 1, y - 2, y - 3]
})

async function openDebug(month) {
  debugMonth.value = month
  showDebug.value = true
  debugLoading.value = true
  debugError.value = ''
  debugData.value = {}
  try {
    const { data } = await api.get('/financial/dre/debug', {
      params: { cmig_id: cmigId.value, year: year.value, month },
    })
    debugData.value = data
  } catch (e) {
    debugError.value = e.response?.data?.detail || 'Erro ao carregar auditoria (sincronize o mês primeiro).'
  } finally {
    debugLoading.value = false
  }
}

function rowStyle(row) {
  if (row.kind === 'total' || row.kind === 'result') {
    const green = ['entrada', 'margem', 'lucro'].includes(row.variant)
    return {
      backgroundColor: green ? '#1e7e34' : '#c82333',
      color: '#fff',
    }
  }
  return {}
}

async function loadCmigs() {
  try {
    const { data } = await api.get('/financial/dre/cmigs')
    cmigs.value = data
    if (data.length && !cmigId.value) cmigId.value = data[0].id
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar CMIGs')
  }
}

async function loadDre() {
  if (!cmigId.value) return
  loading.value = true
  try {
    const { data } = await api.get('/financial/dre', {
      params: { cmig_id: cmigId.value, year: year.value },
    })
    grid.value = data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar DRE')
  } finally {
    loading.value = false
  }
}

async function syncMonth(month) {
  if (!cmigId.value || syncingMonth.value) return
  syncingMonth.value = month
  try {
    await api.post('/financial/dre/sync', {
      cmig_id: cmigId.value,
      year: year.value,
      month,
    })
    toast.success(`Mês ${month} sincronizado`)
    await loadDre()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar o mês')
  } finally {
    syncingMonth.value = null
  }
}

function openNewEntry() {
  showEntryModal.value = true
}

function onEntriesSaved() {
  showEntryModal.value = false
  loadDre()
}

function exportCsv() {
  if (!grid.value) return
  const sep = ';'
  const header = ['Linha', ...grid.value.months, 'Total'].join(sep)
  const lines = grid.value.rows.map((r) =>
    [r.label, ...r.values.map((v) => (v || 0).toFixed(2)), (r.total || 0).toFixed(2)].join(sep)
  )
  const csv = '﻿' + [header, ...lines].join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `DRE_${cmigId.value}_${year.value}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function exportPdf() {
  window.print()
}

onMounted(loadCmigs)
</script>
