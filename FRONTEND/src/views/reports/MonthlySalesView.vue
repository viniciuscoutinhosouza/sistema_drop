<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <h1 class="m-0"><i class="fas fa-coins text-primary mr-2"></i>Vendas do Mês</h1>
        <small class="text-muted">Vendas por produto de uma conta no mês — custo, lucro, % do lucro e rateio de taxa/frete.</small>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <!-- Filtros -->
        <div class="card card-body py-2 mb-3">
          <div class="d-flex align-items-end flex-wrap" style="gap:12px">
            <div>
              <label class="mb-1 text-muted"><small>Conta:</small></label>
              <select v-model="accountId" class="form-control form-control-sm" style="min-width:280px">
                <option value="">Selecione uma conta...</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">
                  {{ a.platform_label }} — {{ a.description || a.platform_username || a.email || ('#' + a.id) }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-1 text-muted"><small>Mês:</small></label>
              <input v-model="monthStr" type="month" class="form-control form-control-sm" style="width:160px">
            </div>
            <button class="btn btn-sm btn-primary" :disabled="!accountId || loading" @click="gerar">
              <i class="fas mr-1" :class="loading ? 'fa-spinner fa-spin' : 'fa-search'"></i>Gerar
            </button>
            <button class="btn btn-sm btn-outline-secondary" :disabled="!accountId || refreshing || loading" @click="atualizar"
                    title="Re-sincroniza os pedidos do período no Mercado Livre">
              <i class="fas mr-1" :class="refreshing ? 'fa-spinner fa-spin' : 'fa-sync-alt'"></i>Atualizar
            </button>
            <div class="ml-auto d-flex" style="gap:6px" v-if="report">
              <button class="btn btn-sm btn-outline-danger" :disabled="exporting" @click="exportar('pdf')">
                <i class="fas fa-file-pdf mr-1"></i>PDF
              </button>
              <button class="btn btn-sm btn-outline-success" :disabled="exporting" @click="exportar('xlsx')">
                <i class="fas fa-file-excel mr-1"></i>Excel
              </button>
            </div>
          </div>
        </div>

        <div v-if="loading" class="text-center py-5"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>

        <div v-else-if="report" class="card">
          <div class="card-header py-2">
            <h6 class="card-title mb-0">{{ report.account?.label }} · {{ report.period }} — {{ report.rows.length }} produto(s)</h6>
          </div>
          <div class="card-body p-0" style="overflow:auto">
            <table class="table table-sm table-hover small mb-0">
              <thead class="thead-light">
                <tr>
                  <th style="cursor:pointer" @click="sortBy('titulo')">Produto <i :class="sortIcon('titulo')"></i></th>
                  <th class="text-center" style="cursor:pointer" @click="sortBy('qtd_vendida')">Vendida <i :class="sortIcon('qtd_vendida')"></i></th>
                  <th class="text-center" style="cursor:pointer" @click="sortBy('qtd_cancelada')">Canc. <i :class="sortIcon('qtd_cancelada')"></i></th>
                  <th class="text-center" style="cursor:pointer" @click="sortBy('qtd_entregue')">Entregue <i :class="sortIcon('qtd_entregue')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('custo')">Custo <i :class="sortIcon('custo')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('venda')">Venda <i :class="sortIcon('venda')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('lucro_bruto')">Lucro Bruto <i :class="sortIcon('lucro_bruto')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('pct_lucro')">% Lucro <i :class="sortIcon('pct_lucro')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('taxa_rateada')">Taxa <i :class="sortIcon('taxa_rateada')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('frete_rateado')">Frete <i :class="sortIcon('frete_rateado')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('ll_parcial')" title="Lucro Líquido Parcial = Lucro Bruto − Taxa − Frete">LL Parcial <i :class="sortIcon('ll_parcial')"></i></th>
                  <th class="text-right" style="cursor:pointer" @click="sortBy('pct_ll_parcial')">% LL <i :class="sortIcon('pct_ll_parcial')"></i></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in sortedRows" :key="r.sku || i">
                  <td>
                    {{ r.titulo || '—' }}
                    <span v-if="r.sku" class="text-muted">({{ r.sku }})</span>
                    <i v-if="r.custo_incompleto" class="fas fa-exclamation-triangle text-warning ml-1"
                       title="Custo ausente em algum item — lucro pode estar incorreto"></i>
                  </td>
                  <td class="text-center">{{ r.qtd_vendida }}</td>
                  <td class="text-center">{{ r.qtd_cancelada }}</td>
                  <td class="text-center">{{ r.qtd_entregue }}</td>
                  <td class="text-right">{{ money(r.custo) }}</td>
                  <td class="text-right">{{ money(r.venda) }}</td>
                  <td class="text-right" :class="r.lucro_bruto < 0 ? 'text-danger' : 'text-success'">{{ money(r.lucro_bruto) }}</td>
                  <td class="text-right">{{ r.pct_lucro.toFixed(1) }}%</td>
                  <td class="text-right">{{ money(r.taxa_rateada) }}</td>
                  <td class="text-right">{{ money(r.frete_rateado) }}</td>
                  <td class="text-right" :class="r.ll_parcial < 0 ? 'text-danger' : 'text-success'">{{ money(r.ll_parcial) }}</td>
                  <td class="text-right">{{ r.pct_ll_parcial.toFixed(1) }}%</td>
                </tr>
                <tr v-if="!report.rows.length">
                  <td colspan="12" class="text-center text-muted py-3">Nenhuma venda no período.</td>
                </tr>
              </tbody>
              <tfoot v-if="report.rows.length">
                <tr class="font-weight-bold" style="background:#e8eef4">
                  <td>TOTAL</td>
                  <td class="text-center">{{ report.totals.qtd_vendida }}</td>
                  <td class="text-center">{{ report.totals.qtd_cancelada }}</td>
                  <td class="text-center">{{ report.totals.qtd_entregue }}</td>
                  <td class="text-right">{{ money(report.totals.custo) }}</td>
                  <td class="text-right">{{ money(report.totals.venda) }}</td>
                  <td class="text-right">{{ money(report.totals.lucro_bruto) }}</td>
                  <td class="text-right">100%</td>
                  <td class="text-right">{{ money(report.totals.taxa_rateada) }}</td>
                  <td class="text-right">{{ money(report.totals.frete_rateado) }}</td>
                  <td class="text-right">{{ money(report.totals.ll_parcial) }}</td>
                  <td class="text-right">100%</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <div v-else class="card">
          <div class="card-body text-center py-5 text-muted">
            <i class="fas fa-coins fa-2x mb-3 d-block"></i>
            Selecione uma conta e um mês e clique em <strong>Gerar</strong>.
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency, brToday } from '@/utils/formatters'

const toast = useToast()
const accounts = ref([])
const accountId = ref('')
const monthStr = ref(brToday().slice(0, 7))  // YYYY-MM do mês corrente (fuso BR)
const report = ref(null)
const loading = ref(false)
const refreshing = ref(false)
const exporting = ref(false)
const sortKey = ref('venda')
const sortDir = ref('desc')

function money(v) { return formatCurrency(v) }

function _ym() {
  const [y, m] = (monthStr.value || '').split('-')
  return { year: Number(y), month: Number(m) }
}

const sortedRows = computed(() => {
  if (!report.value) return []
  const k = sortKey.value
  const dir = sortDir.value === 'desc' ? -1 : 1
  return [...report.value.rows].sort((a, b) => {
    const va = a[k], vb = b[k]
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
    return String(va ?? '').localeCompare(String(vb ?? ''), 'pt-BR') * dir
  })
})

function sortBy(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortKey.value = key; sortDir.value = 'desc' }
}
function sortIcon(key) {
  if (sortKey.value !== key) return 'fas fa-sort text-muted'
  return sortDir.value === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'
}

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    const label = p => ({ mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[p] || p)
    accounts.value = (Array.isArray(data) ? data : []).map(a => ({ ...a, platform_label: label(a.platform) }))
  } catch { accounts.value = [] }
}

async function gerar() {
  const { year, month } = _ym()
  if (!accountId.value || !year || !month) return
  loading.value = true
  try {
    const { data } = await api.get('/reports/monthly-sales', { params: { account_id: accountId.value, year, month } })
    report.value = data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao gerar relatório')
  } finally {
    loading.value = false
  }
}

async function atualizar() {
  const { year, month } = _ym()
  if (!accountId.value || !year || !month) return
  refreshing.value = true
  try {
    const { data } = await api.post('/reports/monthly-sales/refresh', null, { params: { account_id: accountId.value, year, month } })
    report.value = data
    if (data.refresh_warning) toast.warning(data.refresh_warning)
    else toast.success('Dados atualizados do Mercado Livre.')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao atualizar')
  } finally {
    refreshing.value = false
  }
}

async function exportar(format) {
  const { year, month } = _ym()
  if (!accountId.value || !year || !month) return
  exporting.value = true
  try {
    const { data } = await api.get('/reports/monthly-sales/export', {
      params: { account_id: accountId.value, year, month, format },
      responseType: 'blob',
    })
    const ext = format === 'xlsx' ? 'xlsx' : 'pdf'
    const url = URL.createObjectURL(new Blob([data]))
    const link = document.createElement('a')
    link.href = url
    link.download = `vendas-${monthStr.value}-conta-${accountId.value}.${ext}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao exportar')
  } finally {
    exporting.value = false
  }
}

onMounted(loadAccounts)
</script>
