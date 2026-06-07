<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0"><i class="fas fa-dolly mr-2 text-primary"></i>Separação — Pedidos não-FULL</h5>
      <RouterLink to="/separacao/gaiolas" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-shipping-fast mr-1"></i> Gaiolas / Transportadora
      </RouterLink>
    </div>

    <!-- ══ Pedidos pendentes ══════════════════════════════════════════════ -->
    <div class="card">
      <div class="card-header d-flex flex-wrap align-items-center">
        <strong class="mr-3">Pedidos a separar</strong>
        <div class="input-group input-group-sm mr-2" style="max-width:220px">
          <input v-model="search" class="form-control" placeholder="Buscar cliente..." />
          <div class="input-group-append">
            <span class="input-group-text"><i class="fas fa-search"></i></span>
          </div>
        </div>
        <!-- Filtro: Marketplace -->
        <select v-model="filterPlatform" class="form-control form-control-sm mr-2" style="max-width:150px">
          <option value="">Todos marketplaces</option>
          <option v-for="p in platformOptions" :key="p" :value="p">{{ platformLabel(p) }}</option>
        </select>
        <!-- Filtro: CMIG -->
        <select v-model="filterCmig" class="form-control form-control-sm mr-2" style="max-width:170px">
          <option value="">Todas as CMIGs</option>
          <option v-for="c in cmigOptions" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <!-- Filtro: Modo Envio -->
        <select v-model="filterMode" class="form-control form-control-sm mr-2" style="max-width:150px">
          <option value="">Todos os envios</option>
          <option v-for="m in modeOptions" :key="m" :value="m">{{ shippingModeStyle(m).label }}</option>
        </select>
        <button v-if="hasFilters" class="btn btn-sm btn-link text-muted px-1 mr-2" @click="clearFilters" title="Limpar filtros">
          <i class="fas fa-times"></i>
        </button>
        <div class="ml-auto d-flex">
          <button class="btn btn-sm btn-outline-info mr-2" :disabled="!selected.size" @click="printList">
            <i class="fas fa-print mr-1"></i> Imprimir Lista ({{ selected.size }})
          </button>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-success dropdown-toggle" data-bs-toggle="dropdown" :disabled="!selected.size">
              <i class="fas fa-plus mr-1"></i> Nova Gaiola
            </button>
            <div class="dropdown-menu dropdown-menu-right">
              <a class="dropdown-item" href="#" @click.prevent="newCart('manual')">
                <i class="fas fa-hand-paper mr-1"></i> Modo Manual
              </a>
              <a class="dropdown-item" href="#" @click.prevent="newCart('scan')">
                <i class="fas fa-barcode mr-1"></i> Modo Bipagem
              </a>
            </div>
          </div>
        </div>
      </div>
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>
        <table v-else class="table table-hover table-sm mb-0">
          <thead class="thead-light">
            <tr>
              <th style="width:36px"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
              <th class="sortable" @click="setSort('id')">Pedido <i :class="sortIcon('id')"></i></th>
              <th class="sortable" @click="setSort('platform')">Marketplace <i :class="sortIcon('platform')"></i></th>
              <th class="sortable" @click="setSort('cmig')">Conta CMIG <i :class="sortIcon('cmig')"></i></th>
              <th class="sortable" @click="setSort('shipping_mode')">Modo Envio <i :class="sortIcon('shipping_mode')"></i></th>
              <th class="sortable" @click="setSort('buyer')">Cliente <i :class="sortIcon('buyer')"></i></th>
              <th>Itens</th>
              <th class="sortable" @click="setSort('created_at')">Criado <i :class="sortIcon('created_at')"></i></th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!displayedOrders.length">
              <td colspan="8" class="text-center text-muted py-4">
                {{ pending.length ? 'Nenhum pedido com os filtros atuais.' : 'Nenhum pedido pendente de separação.' }}
              </td>
            </tr>
            <tr v-for="o in displayedOrders" :key="o.id" @click="toggle(o.id)" style="cursor:pointer">
              <td @click.stop><input type="checkbox" :checked="selected.has(o.id)" @change="toggle(o.id)" /></td>
              <td class="font-weight-bold align-middle">#{{ o.id }}</td>
              <td class="align-middle">
                <img v-if="platformLogo(o.platform)" :src="platformLogo(o.platform).src"
                     :alt="platformLogo(o.platform).label" :title="platformLogo(o.platform).label"
                     style="height:20px;max-width:80px;object-fit:contain" />
                <span v-else class="badge badge-light text-capitalize">{{ o.platform || '—' }}</span>
              </td>
              <td class="align-middle text-truncate" style="max-width:170px" :title="o.cmig_name">
                <i class="fas fa-id-card text-muted mr-1"></i>{{ o.cmig_name || '—' }}
              </td>
              <td class="align-middle">
                <span class="badge" :title="shippingModeStyle(o.shipping_mode).title"
                      :style="{ background: shippingModeStyle(o.shipping_mode).bg, color: shippingModeStyle(o.shipping_mode).fg, fontSize: '.68rem', fontWeight: 500 }">
                  <i :class="shippingModeStyle(o.shipping_mode).icon" class="mr-1"></i>{{ shippingModeStyle(o.shipping_mode).label }}
                </span>
              </td>
              <td class="align-middle text-truncate" style="max-width:180px">{{ o.buyer_name || '—' }}</td>
              <td class="align-middle">
                <span v-for="it in o.items" :key="it.id" class="badge badge-light border mr-1" :title="it.title">
                  {{ it.sku || '?' }} ×{{ it.quantity }}
                </span>
              </td>
              <td class="text-nowrap small text-muted align-middle">{{ fmt(o.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!loading && pending.length" class="card-footer py-2 text-muted small">
        {{ displayedOrders.length }} de {{ pending.length }} pedido(s)
      </div>
    </div>

    <!-- ══ Gaiolas abertas ════════════════════════════════════════════════ -->
    <div class="card mt-3">
      <div class="card-header"><strong>Gaiolas abertas</strong></div>
      <div class="card-body p-2">
        <span v-if="!openCarts.length" class="text-muted small">Nenhuma gaiola aberta.</span>
        <button v-for="c in openCarts" :key="c.id"
                class="btn btn-sm mr-2 mb-1"
                :class="activeCart && activeCart.id === c.id ? 'btn-primary' : 'btn-outline-primary'"
                @click="openCart(c.id)">
          <i :class="c.mode === 'scan' ? 'fas fa-barcode' : 'fas fa-hand-paper'" class="mr-1"></i>
          {{ c.cart_number }} <span class="badge badge-light ml-1">{{ c.order_count }}</span>
        </button>
      </div>
    </div>

    <!-- ══ Workspace da gaiola ════════════════════════════════════════════ -->
    <div v-if="activeCart" class="card mt-3 border-primary">
      <div class="card-header bg-primary text-white d-flex align-items-center">
        <strong>{{ activeCart.cart_number }}</strong>
        <span class="badge badge-light ml-2 text-capitalize">{{ activeCart.mode }}</span>
        <div class="ml-auto">
          <select v-model="layout" class="form-control form-control-sm d-inline-block" style="width:auto">
            <option v-for="l in layouts" :key="l.key" :value="l.key">{{ l.label }}</option>
          </select>
          <button class="btn btn-sm btn-light ml-2" @click="printLabels()"><i class="fas fa-tags mr-1"></i> Etiquetas (todas)</button>
          <button class="btn btn-sm btn-light ml-1" @click="openNfe()"><i class="fas fa-file-invoice mr-1"></i> NF-e</button>
          <button class="btn btn-sm btn-success ml-1" @click="concludeCart" :disabled="!allSeparated">
            <i class="fas fa-check mr-1"></i> Concluir Gaiola
          </button>
          <button class="btn btn-sm btn-outline-light ml-1" @click="cancelCart" title="Cancelar gaiola e devolver pedidos">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead class="thead-light">
            <tr><th>Pedido</th><th>Cliente</th><th>Conferência</th><th class="text-right">Ações</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in activeCart.orders" :key="o.id">
              <td class="font-weight-bold align-middle">#{{ o.id }}</td>
              <td class="align-middle text-truncate" style="max-width:180px">{{ o.buyer_name || '—' }}</td>
              <td class="align-middle">
                <span v-if="o.item_status === 'separated'" class="badge badge-success"><i class="fas fa-check"></i> Separado</span>
                <template v-else-if="activeCart.mode === 'scan' && o.scan">
                  <div class="progress" style="height:18px;min-width:160px">
                    <div class="progress-bar" :class="o.scan.scanned >= o.scan.expected ? 'bg-success' : 'bg-info'"
                         :style="{ width: pct(o.scan) + '%' }">
                      {{ o.scan.scanned }}/{{ o.scan.expected }}
                    </div>
                  </div>
                  <div class="input-group input-group-sm mt-1" style="max-width:240px">
                    <input :ref="el => bipRefs[o.id] = el" v-model="bipCode[o.id]" class="form-control"
                           placeholder="Bipar SKU/EAN..." @keyup.enter="scan(o)" />
                    <div class="input-group-append">
                      <button class="btn btn-outline-primary" @click="scan(o)"><i class="fas fa-barcode"></i></button>
                    </div>
                  </div>
                </template>
                <span v-else class="text-muted small">Modo manual</span>
              </td>
              <td class="text-right align-middle text-nowrap">
                <button class="btn btn-xs btn-outline-secondary" @click="printLabels(o.id)" title="Etiqueta"><i class="fas fa-tag"></i></button>
                <button v-if="o.item_status !== 'separated'" class="btn btn-xs btn-outline-danger ml-1" @click="removeOrder(o.id)" title="Remover"><i class="fas fa-times"></i></button>
                <button v-if="o.item_status !== 'separated'" class="btn btn-xs btn-success ml-1" @click="separate(o)"
                        :disabled="activeCart.mode === 'scan' && o.scan && o.scan.scanned < o.scan.expected">
                  <i class="fas fa-check mr-1"></i> Separado
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { platformLogo, shippingModeStyle, PLATFORMS } from '@/utils/constants'

const toast = useToast()

const pending = ref([])
const loading = ref(false)
const search = ref('')
const selected = ref(new Set())

// Filtros + ordenação (client-side; a lista de pendentes vem inteira)
const filterPlatform = ref('')
const filterCmig = ref('')
const filterMode = ref('')
const sortKey = ref('created_at')
const sortDir = ref('asc')

const openCarts = ref([])
const activeCart = ref(null)
const layouts = ref([{ key: '10x15', label: 'Térmica 10x15' }, { key: 'a4_4up', label: 'A4 (4 por página)' }])
const layout = ref('10x15')
const bipCode = ref({})
const bipRefs = ref({})

onMounted(async () => {
  await Promise.all([loadPending(), loadCarts(), loadLayouts()])
})

async function loadLayouts() {
  try { const { data } = await api.get('/separation/label-layouts'); if (Array.isArray(data) && data.length) layouts.value = data } catch { /* keep defaults */ }
}

async function loadPending() {
  loading.value = true
  try {
    const { data } = await api.get('/separation/orders')
    pending.value = data.orders || []
  } catch { pending.value = [] } finally { loading.value = false }
}

async function loadCarts() {
  try { const { data } = await api.get('/separation/carts', { params: { status: 'open' } }); openCarts.value = data.carts || [] }
  catch { openCarts.value = [] }
}

// ── Opções de filtro derivadas dos pedidos carregados ──
const platformOptions = computed(() => [...new Set(pending.value.map(o => o.platform).filter(Boolean))])
const modeOptions = computed(() => [...new Set(pending.value.map(o => o.shipping_mode).filter(Boolean))])
const cmigOptions = computed(() => {
  const map = new Map()
  for (const o of pending.value) {
    if (o.cmig_id && !map.has(o.cmig_id)) map.set(o.cmig_id, { id: o.cmig_id, name: o.cmig_name || `CMIG ${o.cmig_id}` })
  }
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
})
const hasFilters = computed(() => !!(filterPlatform.value || filterCmig.value || filterMode.value || search.value))

function platformLabel(key) {
  return PLATFORMS.find(p => p.key === key)?.label || key
}

function clearFilters() {
  filterPlatform.value = ''; filterCmig.value = ''; filterMode.value = ''; search.value = ''
}

// ── Lista exibida (filtro + ordenação) ──
const displayedOrders = computed(() => {
  let rows = pending.value.filter(o => {
    if (filterPlatform.value && o.platform !== filterPlatform.value) return false
    if (filterCmig.value && o.cmig_id !== filterCmig.value) return false
    if (filterMode.value && o.shipping_mode !== filterMode.value) return false
    if (search.value && !(o.buyer_name || '').toLowerCase().includes(search.value.toLowerCase())) return false
    return true
  })
  const dir = sortDir.value === 'asc' ? 1 : -1
  const keyFn = {
    id: o => o.id,
    platform: o => o.platform || '',
    cmig: o => (o.cmig_name || '').toLowerCase(),
    shipping_mode: o => o.shipping_mode || '',
    buyer: o => (o.buyer_name || '').toLowerCase(),
    created_at: o => o.created_at || '',
  }[sortKey.value] || (o => o.id)
  return [...rows].sort((a, b) => {
    const va = keyFn(a), vb = keyFn(b)
    return va < vb ? -dir : va > vb ? dir : 0
  })
})

function setSort(key) {
  if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortKey.value = key; sortDir.value = 'asc' }
}
function sortIcon(key) {
  if (sortKey.value !== key) return 'fas fa-sort text-muted'
  return sortDir.value === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'
}

const allChecked = computed(() => displayedOrders.value.length > 0 && displayedOrders.value.every(o => selected.value.has(o.id)))
const allSeparated = computed(() => activeCart.value?.orders?.length > 0 && activeCart.value.orders.every(o => o.item_status === 'separated'))

function toggle(id) {
  const s = new Set(selected.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selected.value = s
}
function toggleAll() {
  const s = new Set(selected.value)
  if (allChecked.value) displayedOrders.value.forEach(o => s.delete(o.id))
  else displayedOrders.value.forEach(o => s.add(o.id))
  selected.value = s
}

async function printList() {
  await openPdf('/separation/picking-list', 'post', { order_ids: [...selected.value] })
}

async function newCart(mode) {
  try {
    const { data } = await api.post('/separation/carts', { mode })
    const { data: addRes } = await api.post(`/separation/carts/${data.id}/orders`, { order_ids: [...selected.value] })
    selected.value = new Set()
    await Promise.all([loadPending(), loadCarts()])
    await openCart(data.id)
    toast.success(`Gaiola ${data.cart_number} criada (${mode === 'scan' ? 'bipagem' : 'manual'})`)
    if (addRes?.skipped?.length) toast.warning(`${addRes.skipped.length} pedido(s) não adicionado(s): ${addRes.skipped.join(', ')}`)
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao criar gaiola') }
}

async function openCart(id) {
  try { const { data } = await api.get(`/separation/carts/${id}`); activeCart.value = data; focusFirstBip() }
  catch { toast.error('Erro ao abrir gaiola') }
}

async function refreshCart() {
  if (activeCart.value) await openCart(activeCart.value.id)
}

async function scan(o) {
  const code = (bipCode.value[o.id] || '').trim()
  if (!code) return
  try {
    const { data } = await api.post(`/separation/carts/${activeCart.value.id}/orders/${o.id}/scan`, { code })
    bipCode.value[o.id] = ''
    if (o.scan) { o.scan.scanned = data.scanned; o.scan.expected = data.expected }
    if (data.complete) toast.success(`Pedido #${o.id} conferido 100%`)
    await nextTick(); bipRefs.value[o.id]?.focus()
  } catch (e) {
    bipCode.value[o.id] = ''
    toast.error(e.response?.data?.detail || 'Código inválido')
    await nextTick(); bipRefs.value[o.id]?.focus()
  }
}

async function separate(o) {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/orders/${o.id}/separate`)
    toast.success(`Pedido #${o.id} separado`)
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao separar') }
}

async function removeOrder(id) {
  try {
    await api.delete(`/separation/carts/${activeCart.value.id}/orders/${id}`)
    await Promise.all([refreshCart(), loadPending(), loadCarts()])
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao remover') }
}

async function concludeCart() {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/conclude`)
    toast.success('Gaiola concluída — pedidos marcados como separados')
    activeCart.value = null
    await Promise.all([loadCarts(), loadPending()])
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao concluir') }
}

async function cancelCart() {
  if (!confirm('Cancelar esta gaiola? Os pedidos voltam para a lista de separação.')) return
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/cancel`)
    toast.success('Gaiola cancelada — pedidos devolvidos')
    activeCart.value = null
    await Promise.all([loadCarts(), loadPending()])
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao cancelar') }
}

async function printLabels(orderId) {
  const params = { layout: layout.value }
  if (orderId) params.order_id = orderId
  await openPdf(`/separation/carts/${activeCart.value.id}/labels.pdf`, 'get', null, params)
}

async function openNfe() {
  try {
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/nfe`)
    const urls = (data.nfe || []).filter(n => n.nfe_url)
    if (!urls.length) return toast.warning('Nenhuma NF-e disponível nesta gaiola')
    urls.forEach(n => window.open(n.nfe_url, '_blank'))
  } catch { toast.error('Erro ao buscar NF-e') }
}

async function openPdf(url, method, body, params) {
  try {
    const cfg = { responseType: 'blob', params }
    const resp = method === 'post' ? await api.post(url, body, cfg) : await api.get(url, cfg)
    const blobUrl = URL.createObjectURL(new Blob([resp.data], { type: 'application/pdf' }))
    window.open(blobUrl, '_blank')
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000)
  } catch (e) { toast.error('Erro ao gerar PDF') }
}

function focusFirstBip() {
  if (activeCart.value?.mode !== 'scan') return
  nextTick(() => {
    const first = activeCart.value.orders.find(o => o.item_status !== 'separated')
    if (first) bipRefs.value[first.id]?.focus()
  })
}

function pct(scan) { return scan.expected ? Math.round((scan.scanned / scan.expected) * 100) : 0 }
function fmt(dt) { return dt ? new Date(dt).toLocaleString('pt-BR') : '—' }
</script>

<style scoped>
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { background: rgba(0,0,0,.03); }
</style>
