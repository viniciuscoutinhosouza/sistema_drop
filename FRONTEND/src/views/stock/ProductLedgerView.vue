<template>
  <div>
    <!-- Seletor de produto -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title mb-0"><i class="fas fa-stream mr-2"></i>Extrato de Movimentação de Produto</h3>
      </div>
      <div class="card-body">
        <div class="row">
          <div class="col-md-7 position-relative">
            <label class="font-weight-bold small mb-1">Produto (por SKU ou nome)</label>
            <input
              v-model="search"
              @input="onSearch"
              @focus="onSearch"
              type="text"
              class="form-control"
              placeholder="Digite o SKU, EAN ou nome do produto..."
              autocomplete="off"
            />
            <div v-if="showResults && (searching || results.length)" class="list-group position-absolute w-100 shadow-sm" style="z-index:1050;max-height:320px;overflow:auto">
              <div v-if="searching" class="list-group-item text-muted small"><i class="fas fa-spinner fa-spin mr-1"></i>Buscando...</div>
              <button
                v-for="r in results" :key="r.product_type + '-' + r.product_id"
                type="button"
                class="list-group-item list-group-item-action py-2"
                @click="selectProduct(r)"
              >
                <div class="d-flex justify-content-between align-items-center">
                  <div>
                    <span class="badge mr-2" :class="r.product_type === 'pg' ? 'badge-primary' : 'badge-info'">
                      {{ r.product_type === 'pg' ? 'PG' : ('CMIG' + (r.cmig_name ? ' · ' + r.cmig_name : '')) }}
                    </span>
                    <code>{{ r.sku }}</code>
                    <span class="ml-1">{{ r.name }}</span>
                    <span v-if="r.is_full_mirror" class="badge badge-light border ml-1" style="font-size:10px" title="Espelho criado só p/ segurar o FULL">espelho FULL</span>
                  </div>
                  <small class="text-muted">disp. {{ r.available }}<span v-if="r.full_stock_total"> · FULL {{ r.full_stock_total }}</span></small>
                </div>
              </button>
              <div v-if="!searching && !results.length" class="list-group-item text-muted small">Nenhum produto encontrado.</div>
            </div>
          </div>

          <div class="col-md-5 d-flex align-items-end">
            <div class="btn-group btn-group-sm mr-3" role="group" title="A partir de quando exibir os movimentos">
              <button type="button" class="btn" :class="anchor === 'inicio' ? 'btn-primary' : 'btn-outline-primary'" @click="setAnchor('inicio')">Desde o início</button>
              <button type="button" class="btn" :class="anchor === 'baseline' ? 'btn-primary' : 'btn-outline-primary'" @click="setAnchor('baseline')" title="A partir do último inventário Baseline de cada estoque">Desde inventário baseline</button>
            </div>
            <button v-if="selected" class="btn btn-sm btn-outline-secondary" @click="loadLedger" title="Recarregar"><i class="fas fa-sync-alt"></i></button>
          </div>
        </div>
      </div>
    </div>

    <!-- Estado -->
    <div v-if="loading" class="text-center py-5"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>

    <div v-else-if="!selected" class="card"><div class="card-body text-center text-muted py-5">
      <i class="fas fa-hand-pointer fa-2x mb-2 d-block"></i>
      Selecione um produto acima para ver o extrato completo de movimentação — galpão, FULL e cada CMIG.
    </div></div>

    <template v-else-if="ledger">
      <!-- Cabeçalho da família -->
      <div class="alert alert-light border d-flex flex-wrap align-items-center justify-content-between">
        <div>
          <i class="fas fa-boxes mr-1 text-muted"></i>
          <strong>{{ selectedLabel }}</strong>
          <span class="text-muted ml-2 small">
            Família: {{ ledger.family.pg ? '1 PG' : 'sem PG' }} · {{ ledger.family.cmig_count }} CMIG(s)
          </span>
        </div>
        <small class="text-muted">
          Âncora: {{ anchor === 'baseline' ? 'desde inventário baseline' : 'desde o início' }}
        </small>
      </div>

      <!-- GALPÃO PG -->
      <div v-if="ledger.groups.galpao_pg" class="card">
        <div class="card-header bg-primary">
          <h3 class="card-title mb-0 text-white"><i class="fas fa-warehouse mr-2"></i>Galpão (PG) · <code class="text-white">{{ ledger.groups.galpao_pg.sku }}</code> {{ ledger.groups.galpao_pg.title }}</h3>
        </div>
        <div class="card-body">
          <StockCards :card="ledger.groups.galpao_pg.card" />
          <BaselineNote :block="ledger.groups.galpao_pg" :anchor="anchor" />
          <h6 class="text-muted mt-3 mb-2 small text-uppercase">Razão (NF-e · pedidos · inventário)</h6>
          <MovementsTable :movements="ledger.groups.galpao_pg.razao.movements" />
          <OperacionalTable :movements="ledger.groups.galpao_pg.operacional" />
        </div>
      </div>

      <!-- GALPÃO CMIG (por CMIG) -->
      <div v-for="g in ledger.groups.galpao_cmig" :key="'cmigg-' + g.product_id" class="card">
        <div class="card-header" style="background:#17a2b8">
          <h3 class="card-title mb-0 text-white">
            <i class="fas fa-warehouse mr-2"></i>Galpão CMIG · {{ g.cmig_name }}
            <span class="ml-1">· <code class="text-white">{{ g.sku }}</code> {{ g.title }}</span>
            <span v-if="g.is_full_mirror" class="badge badge-light ml-2" style="font-size:10px">espelho FULL</span>
          </h3>
        </div>
        <div class="card-body">
          <StockCards :card="g.card" />
          <BaselineNote :block="g" :anchor="anchor" />
          <h6 class="text-muted mt-3 mb-2 small text-uppercase">Razão (NF-e · pedidos · inventário)</h6>
          <MovementsTable :movements="g.razao.movements" />
          <OperacionalTable :movements="g.operacional" />
        </div>
      </div>

      <!-- FULL (por CMIG × conta / marketplace) -->
      <div v-for="f in ledger.groups.full" :key="'full-' + f.product_id" class="card">
        <div class="card-header" style="background:#6f42c1">
          <h3 class="card-title mb-0 text-white"><i class="fas fa-truck-loading mr-2"></i>FULL (Fulfillment) · {{ f.cmig_name }} · <code class="text-white">{{ f.sku }}</code></h3>
        </div>
        <div class="card-body">
          <!-- Saldo por conta / plataforma (canônico) -->
          <div v-if="f.contas.length" class="row mb-2">
            <div v-for="c in f.contas" :key="c.account_id" class="col-md-3 mb-2">
              <div class="card mb-0 border">
                <div class="card-body py-2">
                  <div class="d-flex align-items-center mb-1">
                    <span v-if="c.platform === 'mercadolivre'" class="badge mr-1" style="background:#FFE600;color:#3F3F3F;font-weight:bold">ML</span>
                    <span v-else-if="c.platform === 'shopee'" class="badge mr-1" style="background:#EE4D2D;color:#fff;font-weight:bold">Shopee</span>
                    <span v-else class="badge badge-secondary mr-1">{{ c.platform || 'conta' }}</span>
                    <small class="text-muted text-truncate">{{ c.platform_username || ('conta #' + c.account_id) }}</small>
                  </div>
                  <div class="d-flex justify-content-between small">
                    <span title="Físico no FULL">Físico <strong>{{ c.qty }}</strong></span>
                    <span title="Reservado" class="text-warning">Res. {{ c.reserved_qty }}</span>
                    <span title="Disponível" class="text-primary">Disp. {{ c.available_qty }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="text-muted small mb-2">Sem saldo FULL nas contas desta CMIG.</p>

          <!-- Trilha temporal FULL (informativa — ADR-0019) -->
          <h6 class="text-muted mt-2 mb-2 small text-uppercase">Movimentos FULL <span class="text-muted" style="text-transform:none">· trilha informativa (o saldo canônico é o de cada conta acima)</span></h6>
          <div class="table-responsive">
            <table class="table table-sm table-hover mb-0" style="font-size:12px;white-space:nowrap">
              <thead class="thead-light">
                <tr><th>Data</th><th>Evento</th><th>Marketplace / Venda</th><th>NF-e</th><th class="text-right">Qtd</th></tr>
              </thead>
              <tbody>
                <tr v-if="!f.trilha.length"><td colspan="5" class="text-center text-muted py-2">Sem movimentos FULL no período.</td></tr>
                <tr v-for="(t, i) in f.trilha" :key="i">
                  <td>{{ fmt(t.date) }}</td>
                  <td><span class="badge" :class="fullBadge(t.movement_type)">{{ t.label }}</span></td>
                  <td>
                    <template v-if="t.order_id">
                      <span v-if="t.order_platform === 'mercadolivre'" class="badge mr-1" style="background:#FFE600;color:#3F3F3F;font-weight:bold">ML</span>
                      <span v-else-if="t.order_platform === 'shopee'" class="badge mr-1" style="background:#EE4D2D;color:#fff;font-weight:bold">Shopee</span>
                      <RouterLink :to="`/orders/${t.order_id}`" class="text-primary">#{{ t.order_platform_id || t.order_id }}</RouterLink>
                    </template>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <RouterLink v-if="t.invoice_id" :to="`/fiscal/invoices/${t.invoice_id}`" class="text-primary">
                      <span v-if="t.invoice_number">NF #{{ t.invoice_number }}</span><span v-else>Rascunho #{{ t.invoice_id }}</span>
                    </RouterLink>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="text-right">
                    <span v-if="t.movement_type === 'full_migrate'" class="text-muted" title="Migração PG→CMIG — sem efeito no saldo">{{ t.qty }} un</span>
                    <strong v-else :class="t.delta >= 0 ? 'text-success' : 'text-danger'">{{ t.delta >= 0 ? '+' : '−' }}{{ Math.abs(t.delta) }}</strong>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div v-if="!ledger.groups.galpao_pg && !ledger.groups.galpao_cmig.length && !ledger.groups.full.length" class="card">
        <div class="card-body text-center text-muted py-4"><i class="fas fa-inbox fa-2x mb-2 d-block"></i>Sem movimentação para este produto.</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, h, ref } from 'vue'
import { RouterLink } from 'vue-router'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/formatters'
import MovementsTable from '@/components/stock/MovementsTable.vue'

const toast = useToast()

const search = ref('')
const results = ref([])
const searching = ref(false)
const showResults = ref(false)
let searchTimer = null

const selected = ref(null)      // { product_type, product_id, sku, name, cmig_name }
const anchor = ref('inicio')
const loading = ref(false)
const ledger = ref(null)

const selectedLabel = computed(() => {
  if (!selected.value) return ''
  const s = selected.value
  const tag = s.product_type === 'pg' ? 'PG' : ('CMIG' + (s.cmig_name ? ' · ' + s.cmig_name : ''))
  return `[${tag}] ${s.sku} — ${s.name}`
})

function onSearch() {
  showResults.value = true
  const q = search.value.trim()
  if (searchTimer) clearTimeout(searchTimer)
  if (q.length < 2) { results.value = []; searching.value = false; return }
  searching.value = true
  searchTimer = setTimeout(async () => {
    try {
      const { data } = await api.get('/stock/summary', {
        params: { search: q, show_zeroed: true, active_cmig_only: true, page_size: 15 },
      })
      results.value = data.items || []
    } catch (e) {
      results.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function selectProduct(r) {
  selected.value = {
    product_type: r.product_type,
    product_id: r.product_id,
    sku: r.sku,
    name: r.name,
    cmig_name: r.cmig_name,
  }
  search.value = `${r.sku} — ${r.name}`
  showResults.value = false
  results.value = []
  loadLedger()
}

function setAnchor(a) {
  anchor.value = a
  if (selected.value) loadLedger()
}

async function loadLedger() {
  if (!selected.value) return
  loading.value = true
  ledger.value = null
  try {
    const { data } = await api.get(
      `/stock/ledger/${selected.value.product_type}/${selected.value.product_id}`,
      { params: { anchor: anchor.value } },
    )
    ledger.value = data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar o extrato.')
  } finally {
    loading.value = false
  }
}

function fmt(iso) { return formatDateTime(iso) }

function fullBadge(type) {
  return ({
    full_in: 'badge-success',
    full_out: 'badge-danger',
    full_reserve: 'badge-warning text-dark',
    full_unreserve: 'badge-info',
    full_return_out: 'badge-secondary',
    full_migrate: 'badge-light border',
  })[type] || 'badge-light'
}

// ---- Subcomponentes inline (cards de saldo, nota de baseline, tabela operacional) ----
const StockCards = {
  props: { card: { type: Object, default: null } },
  setup(props) {
    const n = (v) => (v == null ? '—' : v)
    return () => {
      const c = props.card || {}
      const tile = (label, val, bg, tip) => h('div', { class: 'col' }, [
        h('div', { class: `card mb-0 ${bg}`, title: tip || '' }, [
          h('div', { class: 'card-body py-2 text-center' }, [
            h('small', { class: 'd-block' }, label),
            h('strong', { style: 'font-size:1.2rem' }, String(n(val))),
          ]),
        ]),
      ])
      const extras = []
      if (c.local_awaiting_return) extras.push(tile('Ag. retorno', c.local_awaiting_return, 'bg-light border'))
      if (c.local_pending_validation) extras.push(tile('Ag. inspeção', c.local_pending_validation, 'bg-light border'))
      if (c.local_unfit) extras.push(tile('Inservível', c.local_unfit, 'bg-light border'))
      return h('div', { class: 'row row-cols-2 row-cols-md-4' }, [
        tile('Físico', c.local_physical, 'bg-dark text-white', 'Estoque físico no galpão'),
        tile('Reservado', c.local_reserved, 'bg-warning text-dark', 'Reservado por pedidos a expedir'),
        tile('Disponível', c.local_available, 'bg-primary text-white', 'Físico − reservado'),
        ...extras,
      ])
    }
  },
}

const BaselineNote = {
  props: { block: { type: Object, required: true }, anchor: { type: String, required: true } },
  setup(props) {
    return () => {
      if (props.anchor !== 'baseline') return null
      if (props.block.baseline_date) {
        return h('div', { class: 'small text-muted mt-2' }, [
          h('i', { class: 'fas fa-flag mr-1' }),
          `Exibindo a partir do inventário baseline de ${brDate(props.block.baseline_date)}.`,
        ])
      }
      return h('div', { class: 'small text-warning mt-2' }, [
        h('i', { class: 'fas fa-exclamation-triangle mr-1' }),
        'Sem inventário baseline para este estoque — exibindo desde o início.',
      ])
    }
  },
}

const OperacionalTable = {
  props: { movements: { type: Array, default: () => [] } },
  setup(props) {
    return () => {
      if (!props.movements.length) return null
      const rows = props.movements.map((m) => h('tr', {}, [
        h('td', { style: 'font-size:12px' }, formatDateTime(m.date)),
        h('td', {}, [
          h('span', { class: 'badge badge-light border' }, m.label),
          m.is_variant ? h('span', { class: 'badge badge-secondary ml-1', style: 'font-size:10px', title: 'Variante' }, m.variant_label) : null,
        ]),
        h('td', { style: 'font-size:12px' }, m.order_platform_id ? `#${m.order_platform_id}` : (m.return_id ? `Devolução #${m.return_id}` : '—')),
        h('td', { class: 'text-right ' + (m.delta >= 0 ? 'text-success' : 'text-danger') }, `${m.delta >= 0 ? '+' : '−'}${Math.abs(m.delta)}`),
      ]))
      return h('div', {}, [
        h('h6', { class: 'text-muted mt-3 mb-2 small text-uppercase' }, [
          'Reservas & Devoluções ',
          h('span', { class: 'text-muted', style: 'text-transform:none' }, '· ciclo operacional (a mesma reserva/pedido também aparece na Razão acima, sob outra ótica)'),
        ]),
        h('div', { class: 'table-responsive' }, [
          h('table', { class: 'table table-sm table-hover mb-0', style: 'font-size:12px;white-space:nowrap' }, [
            h('thead', { class: 'thead-light' }, [h('tr', {}, [
              h('th', {}, 'Data'), h('th', {}, 'Evento'), h('th', {}, 'Referência'), h('th', { class: 'text-right' }, 'Qtd'),
            ])]),
            h('tbody', {}, rows),
          ]),
        ]),
      ])
    }
  },
}

function brDate(iso) {
  if (!iso) return '—'
  const [y, mo, d] = String(iso).split('T')[0].split('-')
  return `${d}/${mo}/${y}`
}
</script>
