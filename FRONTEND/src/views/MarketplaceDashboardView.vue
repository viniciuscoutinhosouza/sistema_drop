<template>
  <div class="mkt-dashboard">
    <!-- Barra de filtros -->
    <div class="card card-outline card-primary mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center">
          <h5 class="mb-0 mr-auto">
            <i class="fas fa-store text-primary mr-2"></i>
            Dashboard de Marketplaces
          </h5>

          <div class="form-group mb-0 mr-2" style="min-width: 220px">
            <select v-model="filters.account_id" class="form-control form-control-sm" @change="load">
              <option :value="null">Todas as contas do escopo</option>
              <option v-for="a in accounts" :key="a.id" :value="a.id">
                {{ platformIcon(a.platform) }} {{ a.description || a.platform_username || a.email }}
              </option>
            </select>
          </div>

          <div class="btn-group btn-group-sm mr-2" role="group">
            <button
              type="button"
              class="btn"
              :class="filters.platform === null ? 'btn-primary' : 'btn-outline-primary'"
              @click="setPlatform(null)"
            >Todos</button>
            <button
              type="button"
              class="btn"
              :class="filters.platform === 'mercadolivre' ? 'btn-warning' : 'btn-outline-warning'"
              @click="setPlatform('mercadolivre')"
            >Mercado Livre</button>
            <button
              type="button"
              class="btn"
              :class="filters.platform === 'shopee' ? 'btn-danger' : 'btn-outline-danger'"
              @click="setPlatform('shopee')"
            >Shopee</button>
          </div>

          <button class="btn btn-sm btn-outline-secondary" :disabled="loading" @click="load">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Cards hero -->
    <div class="row">
      <div class="col-lg-3 col-6">
        <div class="small-box bg-gradient-info">
          <div class="inner">
            <h3>{{ formatCurrency(rows.faturamento?.mes) }}</h3>
            <p>Faturamento (mês)</p>
            <small :class="deltaTextClass(heroDelta('faturamento'))">
              <i :class="deltaArrow(heroDelta('faturamento'))"></i>
              {{ fmtPct(heroDelta('faturamento')) }} vs mês anterior
            </small>
          </div>
          <div class="icon"><i class="fas fa-dollar-sign"></i></div>
        </div>
      </div>
      <div class="col-lg-3 col-6">
        <div class="small-box bg-gradient-success">
          <div class="inner">
            <h3>{{ rows.qtd_pedidos?.hoje ?? 0 }}</h3>
            <p>Pedidos hoje</p>
            <small class="text-white-50">{{ rows.qtd_pedidos?.mes ?? 0 }} no mês</small>
          </div>
          <div class="icon"><i class="fas fa-shopping-cart"></i></div>
        </div>
      </div>
      <div class="col-lg-3 col-6">
        <div class="small-box bg-gradient-primary">
          <div class="inner">
            <h3>{{ fmtNum(rows.conversao?.mes) }}%</h3>
            <p>Conversão (mês)</p>
            <small class="text-white-50">{{ fmtInt(rows.visitas?.mes) }} visitas</small>
          </div>
          <div class="icon"><i class="fas fa-percent"></i></div>
        </div>
      </div>
      <div class="col-lg-3 col-6">
        <div class="small-box" :class="acosBg">
          <div class="inner">
            <h3>{{ fmtNum(extras.mes?.acos) }}%</h3>
            <p>ACOS (ADS/Faturamento)</p>
            <small class="text-white-50">{{ formatCurrency(rows.ads_cost?.mes) }} em ADS</small>
          </div>
          <div class="icon"><i class="fas fa-bullhorn"></i></div>
        </div>
      </div>
    </div>

    <!-- Matriz principal -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title"><i class="fas fa-table mr-2"></i>Visão por período</h3>
        <div class="card-tools text-muted small" v-if="scope.generated_at">
          Atualizado {{ formatDateTime(scope.generated_at) }}
          <span v-if="scope.is_global" class="badge badge-info ml-1">Visão global</span>
        </div>
      </div>
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-5">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>
        <MetricsMatrix
          v-else
          :windows="windows"
          :window-labels="windowLabels"
          :row-meta="rowMeta"
          :rows="rows"
        />
      </div>
      <div class="card-footer text-muted small">
        <i class="fas fa-info-circle mr-1"></i>
        Visitas, Conversão, Perguntas e Gasto no ADS são exclusivos do Mercado Livre
        (coletados 4x/dia). "Hoje" pode ser parcial até o fechamento do dia.
      </div>
    </div>

    <!-- Gráficos -->
    <div class="row">
      <div class="col-lg-4">
        <div class="card">
          <div class="card-header"><h3 class="card-title">Pedidos por modo de envio (mês)</h3></div>
          <div class="card-body">
            <apexchart v-if="!loading" type="donut" height="280" :options="donutOptions" :series="donutSeries" />
          </div>
        </div>
      </div>
      <div class="col-lg-5">
        <div class="card">
          <div class="card-header"><h3 class="card-title">Pedidos por período</h3></div>
          <div class="card-body">
            <apexchart v-if="!loading" type="bar" height="280" :options="barOptions" :series="barSeries" />
          </div>
        </div>
      </div>
      <div class="col-lg-3">
        <div class="card">
          <div class="card-header"><h3 class="card-title">Conversão (mês)</h3></div>
          <div class="card-body">
            <apexchart v-if="!loading" type="radialBar" height="280" :options="gaugeOptions" :series="gaugeSeries" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import MetricsMatrix from '@/components/dashboard/MetricsMatrix.vue'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const toast = useToast()
const loading = ref(true)
const accounts = ref([])

const filters = reactive({ account_id: null, platform: null })

const windows = ref([])
const windowLabels = ref({})
const rowMeta = ref({})
const rows = reactive({})
const extras = reactive({})
const scope = reactive({})

function platformIcon(p) {
  if (p === 'mercadolivre') return '🟡'
  if (p === 'shopee') return '🟠'
  return '•'
}

function setPlatform(p) {
  filters.platform = p
  load()
}

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    accounts.value = Array.isArray(data) ? data : []
  } catch (e) {
    console.error('[mkt-dashboard] contas:', e?.response?.status ?? e?.message)
  }
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.account_id != null) params.account_id = filters.account_id
    if (filters.platform) params.platform = filters.platform
    const { data } = await api.get('/dashboard/marketplace', { params })
    windows.value = data.windows
    windowLabels.value = data.window_labels
    rowMeta.value = data.row_meta
    Object.assign(rows, data.rows)
    Object.assign(extras, data.extras)
    Object.assign(scope, data.scope)
  } catch (e) {
    toast.error('Erro ao carregar dashboard de marketplaces')
    console.error('[mkt-dashboard]', e?.response?.status ?? e?.message)
  } finally {
    loading.value = false
  }
}

// ---- formatadores ----
function fmtNum(v) {
  return Number(v || 0).toFixed(2).replace('.', ',')
}
function fmtInt(v) {
  return new Intl.NumberFormat('pt-BR').format(Number(v || 0))
}
function fmtPct(v) {
  const n = Number(v || 0)
  return (n >= 0 ? '+' : '') + n.toFixed(1).replace('.', ',') + '%'
}
function heroDelta(key) {
  const cur = Number(rows[key]?.mes || 0)
  const prev = Number(rows[key]?.mes_anterior || 0)
  if (prev === 0) return cur === 0 ? 0 : 100
  return ((cur - prev) / prev) * 100
}
function deltaArrow(d) {
  return d > 0 ? 'fas fa-arrow-up' : d < 0 ? 'fas fa-arrow-down' : 'fas fa-minus'
}
function deltaTextClass(d) {
  return d > 0 ? 'text-white' : d < 0 ? 'text-white-50' : 'text-white-50'
}

const acosBg = computed(() => {
  const a = Number(extras.mes?.acos || 0)
  if (a === 0) return 'bg-gradient-secondary'
  if (a > 15) return 'bg-gradient-danger'
  if (a > 8) return 'bg-gradient-warning'
  return 'bg-gradient-dark'
})

// ---- gráficos ----
const donutSeries = computed(() => [
  Number(rows.full?.mes || 0),
  Number(rows.flex?.mes || 0),
  Number(rows.outros?.mes || 0),
])
const donutOptions = {
  labels: ['Full', 'Flex', 'Outros'],
  colors: ['#3490dc', '#f6993f', '#6c757d'],
  legend: { position: 'bottom' },
  dataLabels: { enabled: true },
  stroke: { width: 1 },
}

const barSeries = computed(() => [
  { name: 'Pedidos', data: windows.value.map((w) => Number(rows.qtd_pedidos?.[w] || 0)) },
])
const barOptions = computed(() => ({
  chart: { toolbar: { show: false } },
  plotOptions: { bar: { borderRadius: 4, columnWidth: '55%' } },
  colors: ['#38c172'],
  dataLabels: { enabled: false },
  xaxis: { categories: windows.value.map((w) => windowLabels.value[w] || w) },
}))

const gaugeSeries = computed(() => [Math.min(Number(rows.conversao?.mes || 0), 100)])
const gaugeOptions = {
  colors: ['#6574cd'],
  plotOptions: {
    radialBar: {
      hollow: { size: '60%' },
      dataLabels: {
        name: { show: true, label: 'Conversão' },
        value: { formatter: (v) => Number(v).toFixed(2).replace('.', ',') + '%' },
      },
    },
  },
  labels: ['Conversão'],
}

onMounted(async () => {
  await Promise.all([loadAccounts(), load()])
})
</script>

<style scoped>
.small-box .inner small {
  display: block;
  margin-top: 4px;
}
</style>
