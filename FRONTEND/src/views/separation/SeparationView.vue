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
        <div class="input-group input-group-sm mr-2" style="max-width:200px">
          <input v-model="search" class="form-control" placeholder="Buscar cliente..." />
          <div class="input-group-append"><span class="input-group-text"><i class="fas fa-search"></i></span></div>
        </div>
        <select v-model="filterShipment" class="form-control form-control-sm mr-2" style="max-width:150px">
          <option value="">Todos os status</option>
          <option v-for="s in shipmentOptions" :key="s" :value="s">{{ shipmentLabel(s) }}</option>
        </select>
        <select v-model="filterPlatform" class="form-control form-control-sm mr-2" style="max-width:140px">
          <option value="">Marketplaces</option>
          <option v-for="p in platformOptions" :key="p" :value="p">{{ platformLabel(p) }}</option>
        </select>
        <select v-model="filterCmig" class="form-control form-control-sm mr-2" style="max-width:160px">
          <option value="">Todas as CMIGs</option>
          <option v-for="c in cmigOptions" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <select v-model="filterNfe" class="form-control form-control-sm mr-2" style="max-width:130px">
          <option value="">NF-e (todas)</option>
          <option value="emitida">Com NF-e</option>
          <option value="pendente">Sem NF-e</option>
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
              <a class="dropdown-item" href="#" @click.prevent="newCart('manual')"><i class="fas fa-hand-paper mr-1"></i> Modo Manual</a>
              <a class="dropdown-item" href="#" @click.prevent="newCart('scan')"><i class="fas fa-barcode mr-1"></i> Modo Bipagem</a>
            </div>
          </div>
        </div>
      </div>
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>
        <table v-else class="table table-hover table-sm mb-0 align-middle">
          <thead class="thead-light">
            <tr>
              <th style="width:34px"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
              <th class="sortable" @click="setSort('id')">Pedido <i :class="sortIcon('id')"></i></th>
              <th class="sortable" @click="setSort('platform')">MKT <i :class="sortIcon('platform')"></i></th>
              <th class="sortable" @click="setSort('cmig')">Conta CMIG <i :class="sortIcon('cmig')"></i></th>
              <th class="sortable" @click="setSort('shipment')">Envio <i :class="sortIcon('shipment')"></i></th>
              <th>Modo</th>
              <th class="sortable" @click="setSort('nfe')">NF-e <i :class="sortIcon('nfe')"></i></th>
              <th class="sortable" @click="setSort('sale')">Venda (Mkt) <i :class="sortIcon('sale')"></i></th>
              <th class="sortable" @click="setSort('delivery')">Prev. Entrega <i :class="sortIcon('delivery')"></i></th>
              <th class="sortable" @click="setSort('buyer')">Cliente <i :class="sortIcon('buyer')"></i></th>
              <th>Itens</th>
              <th class="text-right">Ação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!displayedOrders.length">
              <td colspan="12" class="text-center text-muted py-4">
                {{ pending.length ? 'Nenhum pedido com os filtros atuais.' : 'Nenhum pedido pendente de separação.' }}
              </td>
            </tr>
            <tr v-for="o in displayedOrders" :key="o.id"
                :class="{ 'text-muted': !selectable(o) }"
                :style="selectable(o) ? 'cursor:pointer' : ''"
                @click="selectable(o) && toggle(o.id)">
              <td @click.stop>
                <input type="checkbox" :checked="selected.has(o.id)" :disabled="!selectable(o)"
                       :title="selectable(o) ? '' : 'Só pedidos Prontos p/ Envio podem ir para a gaiola'"
                       @change="toggle(o.id)" />
              </td>
              <td class="font-weight-bold">
                #{{ o.id }}
                <span v-if="o.payment_status && o.payment_status !== 'paid'" class="badge badge-warning ml-1" title="Pagamento não confirmado">
                  <i class="fas fa-exclamation-triangle"></i>
                </span>
              </td>
              <td>
                <img v-if="platformLogo(o.platform)" :src="platformLogo(o.platform).src"
                     :alt="platformLogo(o.platform).label" :title="platformLogo(o.platform).label"
                     style="height:18px;max-width:70px;object-fit:contain" />
                <span v-else class="badge badge-light text-capitalize">{{ o.platform || '—' }}</span>
              </td>
              <td class="text-truncate" style="max-width:150px" :title="o.cmig_name"><i class="fas fa-id-card text-muted mr-1"></i>{{ o.cmig_name || '—' }}</td>
              <td>
                <span class="badge" :class="shipmentBadge(o.shipment_status)">
                  <i :class="shipmentIcon(o.shipment_status)" class="mr-1"></i>{{ shipmentLabel(o.shipment_status) }}
                </span>
              </td>
              <td>
                <span class="badge" :title="shippingModeStyle(o.shipping_mode).title"
                      :style="{ background: shippingModeStyle(o.shipping_mode).bg, color: shippingModeStyle(o.shipping_mode).fg, fontSize: '.66rem' }">
                  {{ shippingModeStyle(o.shipping_mode).label }}
                </span>
              </td>
              <td @click.stop>
                <button v-if="o.nfe_url || o.nfe_key" class="btn btn-xs btn-success" title="Imprimir DANFE" @click="openDanfe(o.id)">
                  <i class="fas fa-file-invoice mr-1"></i>Emitida
                </button>
                <span v-else-if="['pending','in_process'].includes(o.nfe_status)" class="badge badge-info">
                  <i class="fas fa-spinner fa-spin mr-1"></i>Processando
                </span>
                <button v-else-if="o.platform === 'mercadolivre' && o.shipment_status === 'ready_to_ship'"
                        class="btn btn-xs btn-outline-warning" :disabled="nfeEmitting[o.id]" @click="emitNfeList(o)" title="Emitir NF-e via ML">
                  <i class="fas fa-file-invoice mr-1"></i>{{ nfeEmitting[o.id] ? 'Emitindo…' : 'Emitir' }}
                </button>
                <span v-else class="text-muted small">—</span>
              </td>
              <td @click.stop>
                <a v-if="o.platform === 'mercadolivre' && o.platform_order_id"
                   :href="`https://www.mercadolivre.com.br/vendas/${o.platform_order_id}/detalhe`"
                   target="_blank" rel="noopener" class="badge badge-light border text-primary"
                   title="Ver venda no Mercado Livre">
                  #{{ o.platform_order_id }} <i class="fas fa-external-link-alt ml-1"></i>
                </a>
                <span v-else class="small">{{ o.platform_order_id || '—' }}</span>
                <div class="small text-muted text-nowrap"><i class="far fa-calendar mr-1"></i>{{ fmt(o.created_at) }}</div>
              </td>
              <td class="small text-nowrap">
                <i class="far fa-clock mr-1 text-muted"></i>{{ fmtDate(o.estimated_delivery_date || o.estimated_delivery_final) }}
              </td>
              <td class="text-truncate" style="max-width:160px">{{ o.buyer_name || '—' }}</td>
              <td>
                <span v-for="it in o.items" :key="it.id" class="badge badge-light border mr-1" :title="it.title">{{ it.sku || '?' }} ×{{ it.quantity }}</span>
              </td>
              <td class="text-right" @click.stop>
                <button v-if="selectable(o)" class="btn btn-xs btn-outline-primary" title="Adicionar a uma gaiola aberta" @click="openAddModal(o)">
                  <i class="fas fa-cart-plus"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!loading && pending.length" class="card-footer py-2 text-muted small">
        {{ displayedOrders.length }} de {{ pending.length }} pedido(s) — selecionáveis: Prontos p/ Envio
      </div>
    </div>

    <!-- ══ Gaiolas abertas ════════════════════════════════════════════════ -->
    <div class="card mt-3">
      <div class="card-header"><strong>Gaiolas abertas</strong></div>
      <div class="card-body p-2">
        <span v-if="!openCarts.length" class="text-muted small">Nenhuma gaiola aberta.</span>
        <button v-for="c in openCarts" :key="c.id" class="btn btn-sm mr-2 mb-1"
                :class="activeCart && activeCart.id === c.id ? 'btn-primary' : 'btn-outline-primary'" @click="openCart(c.id)">
          <i :class="c.mode === 'scan' ? 'fas fa-barcode' : 'fas fa-hand-paper'" class="mr-1"></i>
          {{ c.cart_number }} <span class="badge badge-light ml-1">{{ c.order_count }}</span>
        </button>
      </div>
    </div>

    <!-- ══ Workspace da gaiola ════════════════════════════════════════════ -->
    <div v-if="activeCart" class="card mt-3 border-primary">
      <div class="card-header bg-primary text-white d-flex align-items-center flex-wrap">
        <strong>{{ activeCart.cart_number }}</strong>
        <span class="badge badge-light ml-2 text-capitalize">{{ activeCart.mode === 'scan' ? 'Bipagem' : 'Manual' }}</span>
        <span class="badge ml-2" :class="activeCart.status === 'separated' ? 'badge-success' : 'badge-warning text-dark'">
          {{ activeCart.status === 'separated' ? 'Concluída — pronta p/ transportadora' : 'Em separação' }}
        </span>
        <div class="ml-auto d-flex align-items-center">
          <select v-model="layout" class="form-control form-control-sm d-inline-block mr-2" style="width:auto" title="Layout p/ etiqueta interna (manual)">
            <option v-for="l in layouts" :key="l.key" :value="l.key">{{ l.label }}</option>
          </select>
          <button class="btn btn-sm btn-light mr-1" @click="printAllLabels"><i class="fas fa-tags mr-1"></i> Etiquetas</button>
          <button class="btn btn-sm btn-light mr-1" @click="cartNfe"><i class="fas fa-file-invoice mr-1"></i> NF-e</button>
          <button class="btn btn-sm btn-warning text-dark mr-1" @click="downloadBundle" :disabled="downloadingBundle"
                  title="Baixa NF-e (PDF+XML) e etiquetas de todos os pedidos num único ZIP">
            <i class="fas mr-1" :class="downloadingBundle ? 'fa-spinner fa-spin' : 'fa-file-archive'"></i> Baixar tudo (ZIP)
          </button>
          <button class="btn btn-sm btn-success mr-1" @click="concludeCart" :disabled="!allLabelPrinted"
                  :title="allLabelPrinted ? '' : 'Imprima a etiqueta de todos os pedidos para concluir'">
            <i class="fas fa-check mr-1"></i> Concluir
          </button>
          <button class="btn btn-sm btn-outline-light" @click="cancelCart" title="Cancelar gaiola e devolver pedidos"><i class="fas fa-trash"></i></button>
        </div>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0 align-middle">
          <thead class="thead-light">
            <tr><th>Pedido</th><th>Cliente</th><th>Conferência</th><th class="text-center">Etiq.</th><th class="text-center">NF-e</th><th class="text-right">Ações</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in activeCart.orders" :key="o.id">
              <td class="font-weight-bold">#{{ o.id }}
                <span v-if="o.item_status === 'separated'" class="badge badge-success ml-1"><i class="fas fa-box-open"></i></span>
              </td>
              <td class="text-truncate" style="max-width:160px">{{ o.buyer_name || '—' }}</td>
              <td>
                <template v-if="activeCart.mode === 'scan' && o.scan">
                  <div class="progress" style="height:18px;min-width:150px">
                    <div class="progress-bar" :class="o.scan.scanned >= o.scan.expected ? 'bg-success' : 'bg-info'" :style="{ width: pct(o.scan) + '%' }">
                      {{ o.scan.scanned }}/{{ o.scan.expected }}
                    </div>
                  </div>
                  <div v-if="o.scan.scanned < o.scan.expected" class="input-group input-group-sm mt-1" style="max-width:230px">
                    <input :ref="el => bipRefs[o.id] = el" v-model="bipCode[o.id]" class="form-control" placeholder="Bipar SKU/EAN..." @keyup.enter="scan(o)" />
                    <div class="input-group-append"><button class="btn btn-outline-primary" @click="scan(o)"><i class="fas fa-barcode"></i></button></div>
                  </div>
                  <span v-else class="badge badge-success"><i class="fas fa-check"></i> Conferido</span>
                </template>
                <span v-else class="text-muted small">Manual</span>
              </td>
              <td class="text-center">
                <i class="fas fa-tag" :class="o.label_printed ? 'text-success' : 'text-muted'"
                   :title="o.label_printed ? 'Etiqueta impressa' : 'Etiqueta não impressa'"></i>
              </td>
              <td class="text-center">
                <i class="fas fa-file-invoice" :class="nfeIconClass(o)" :title="nfeIconTitle(o)"></i>
              </td>
              <td class="text-right text-nowrap">
                <button class="btn btn-xs btn-outline-secondary" :disabled="!canPrintLabel(o)"
                        :title="canPrintLabel(o) ? 'Imprimir etiqueta' : 'Bipe todos os itens primeiro'" @click="printOrderLabel(o)">
                  <i class="fas fa-tag"></i>
                </button>
                <button class="btn btn-xs btn-outline-info ml-1" :disabled="!o.label_printed"
                        :title="o.label_printed ? 'Emitir + imprimir NF-e' : 'Imprima a etiqueta primeiro'" @click="emitPrintOrderNfe(o)">
                  <i class="fas fa-file-invoice"></i>
                </button>
                <button v-if="o.item_status !== 'separated'" class="btn btn-xs btn-outline-danger ml-1" title="Remover" @click="removeOrder(o.id)">
                  <i class="fas fa-times"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal: adicionar pedido a gaiola aberta -->
    <div v-if="addModal.show" class="modal-backdrop-custom" @click.self="addModal.show = false">
      <div class="card shadow" style="width:420px">
        <div class="card-header"><strong>Adicionar pedido #{{ addModal.order?.id }} a uma gaiola</strong></div>
        <div class="card-body">
          <p v-if="!openCarts.length" class="text-muted small mb-0">Nenhuma gaiola aberta. Crie uma nova gaiola primeiro.</p>
          <div v-else class="list-group">
            <button v-for="c in openCarts" :key="c.id" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" @click="addToCart(c)">
              <span><i :class="c.mode === 'scan' ? 'fas fa-barcode' : 'fas fa-hand-paper'" class="mr-2"></i>{{ c.cart_number }}</span>
              <span class="badge badge-primary badge-pill">{{ c.order_count }} pedido(s)</span>
            </button>
          </div>
        </div>
        <div class="card-footer text-right"><button class="btn btn-sm btn-secondary" @click="addModal.show = false">Fechar</button></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, reactive } from 'vue'
import { formatDate as fmtBrDate, formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import { openAndSaveBlobResponse } from '@/utils/download'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { platformLogo, shippingModeStyle, PLATFORMS } from '@/utils/constants'

const toast = useToast()

// ── Mapa de shipment_status (igual à Gestão de Pedidos) ──
const SHIPMENT_MAP = {
  pending:       { label: 'Aguardando',      icon: 'fas fa-clock',         badge: 'badge-secondary' },
  handling:      { label: 'Em Preparação',   icon: 'fas fa-box-open',      badge: 'badge-warning text-dark' },
  ready_to_ship: { label: 'Pronto p/ Envio', icon: 'fas fa-dolly',         badge: 'badge-info' },
  shipped:       { label: 'A caminho',       icon: 'fas fa-shipping-fast', badge: 'badge-primary' },
  delivered:     { label: 'Entregue',        icon: 'fas fa-check-circle',  badge: 'badge-success' },
  not_delivered: { label: 'Não Entregue',    icon: 'fas fa-exclamation-triangle', badge: 'badge-danger' },
  cancelled:     { label: 'Cancelado',       icon: 'fas fa-times-circle',  badge: 'badge-dark' },
}
function shipmentLabel(s) { return SHIPMENT_MAP[s]?.label || (s || '—') }
function shipmentIcon(s)  { return SHIPMENT_MAP[s]?.icon || 'fas fa-circle' }
function shipmentBadge(s) { return SHIPMENT_MAP[s]?.badge || 'badge-light' }

const pending = ref([])
const loading = ref(false)
const search = ref('')
const selected = ref(new Set())
const nfeEmitting = reactive({})

const filterPlatform = ref('')
const filterCmig = ref('')
const filterShipment = ref('')
const filterNfe = ref('')
const sortKey = ref('shipment')
const sortDir = ref('asc')

const openCarts = ref([])
const activeCart = ref(null)
const layouts = ref([{ key: '10x15', label: 'Térmica 10x15' }, { key: 'a4_4up', label: 'A4 (4 por página)' }])
const layout = ref('10x15')
const downloadingBundle = ref(false)
const bipCode = ref({})
const bipRefs = ref({})
const addModal = reactive({ show: false, order: null })

onMounted(async () => { await Promise.all([loadPending(), loadCarts(), loadLayouts()]) })

async function loadLayouts() {
  try { const { data } = await api.get('/separation/label-layouts'); if (Array.isArray(data) && data.length) layouts.value = data } catch { /* defaults */ }
}
async function loadPending() {
  loading.value = true
  try { const { data } = await api.get('/separation/orders'); pending.value = data.orders || [] }
  catch { pending.value = [] } finally { loading.value = false }
}
async function loadCarts() {
  try { const { data } = await api.get('/separation/carts', { params: { status: 'open' } }); openCarts.value = data.carts || [] }
  catch { openCarts.value = [] }
}

function selectable(o) { return o.shipment_status === 'ready_to_ship' }

// ── Opções de filtro ──
const platformOptions = computed(() => [...new Set(pending.value.map(o => o.platform).filter(Boolean))])
const shipmentOptions = computed(() => [...new Set(pending.value.map(o => o.shipment_status).filter(Boolean))])
const cmigOptions = computed(() => {
  const map = new Map()
  for (const o of pending.value) if (o.cmig_id && !map.has(o.cmig_id)) map.set(o.cmig_id, { id: o.cmig_id, name: o.cmig_name || `CMIG ${o.cmig_id}` })
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
})
const hasFilters = computed(() => !!(filterPlatform.value || filterCmig.value || filterShipment.value || filterNfe.value || search.value))
function platformLabel(key) { return PLATFORMS.find(p => p.key === key)?.label || key }
function clearFilters() { filterPlatform.value = ''; filterCmig.value = ''; filterShipment.value = ''; filterNfe.value = ''; search.value = '' }

function hasNfe(o) { return !!(o.nfe_url || o.nfe_key || ['authorized', 'pending', 'in_process'].includes(o.nfe_status)) }

const displayedOrders = computed(() => {
  let rows = pending.value.filter(o => {
    if (filterPlatform.value && o.platform !== filterPlatform.value) return false
    if (filterCmig.value && String(o.cmig_id) !== String(filterCmig.value)) return false
    if (filterShipment.value && o.shipment_status !== filterShipment.value) return false
    if (filterNfe.value === 'emitida' && !hasNfe(o)) return false
    if (filterNfe.value === 'pendente' && hasNfe(o)) return false
    if (search.value && !(o.buyer_name || '').toLowerCase().includes(search.value.toLowerCase())) return false
    return true
  })
  const dir = sortDir.value === 'asc' ? 1 : -1
  const keyFn = {
    id: o => o.id,
    platform: o => o.platform || '',
    cmig: o => (o.cmig_name || '').toLowerCase(),
    shipment: o => o.shipment_status || '',
    nfe: o => (hasNfe(o) ? '1' : '0'),
    sale: o => o.created_at || '',
    delivery: o => o.estimated_delivery_date || o.estimated_delivery_final || '',
    buyer: o => (o.buyer_name || '').toLowerCase(),
  }[sortKey.value] || (o => o.id)
  return [...rows].sort((a, b) => { const va = keyFn(a), vb = keyFn(b); return va < vb ? -dir : va > vb ? dir : 0 })
})
function setSort(key) { if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; else { sortKey.value = key; sortDir.value = 'asc' } }
function sortIcon(key) { if (sortKey.value !== key) return 'fas fa-sort text-muted'; return sortDir.value === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down' }

const selectableDisplayed = computed(() => displayedOrders.value.filter(selectable))
const allChecked = computed(() => selectableDisplayed.value.length > 0 && selectableDisplayed.value.every(o => selected.value.has(o.id)))
const allLabelPrinted = computed(() => activeCart.value?.orders?.length > 0 && activeCart.value.orders.every(o => o.label_printed))

function toggle(id) { const s = new Set(selected.value); s.has(id) ? s.delete(id) : s.add(id); selected.value = s }
function toggleAll() {
  const s = new Set(selected.value)
  if (allChecked.value) selectableDisplayed.value.forEach(o => s.delete(o.id))
  else selectableDisplayed.value.forEach(o => s.add(o.id))
  selected.value = s
}

async function printList() { await openPdf('/separation/picking-list', 'post', { order_ids: [...selected.value] }) }

// ── Emitir NF-e direto na lista (pedido fora de gaiola) ──
async function emitNfeList(o) {
  nfeEmitting[o.id] = true
  try {
    await api.post(`/orders/${o.id}/emit-nfe`)
    toast.success(`NF-e do pedido #${o.id} solicitada`)
    await loadPending()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao emitir NF-e') }
  finally { nfeEmitting[o.id] = false }
}

// ── Gaiolas ──
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

function openAddModal(o) {
  if (!openCarts.value.length) return toast.info('Nenhuma gaiola aberta. Crie uma nova gaiola primeiro.')
  addModal.order = o; addModal.show = true
}
async function addToCart(cart) {
  try {
    const { data } = await api.post(`/separation/carts/${cart.id}/orders`, { order_ids: [addModal.order.id] })
    if (data.added?.length) toast.success(`Pedido #${addModal.order.id} adicionado à ${cart.cart_number}`)
    else toast.warning('Pedido não pôde ser adicionado (não está Pronto p/ Envio?)')
    addModal.show = false
    await Promise.all([loadPending(), loadCarts()])
    if (activeCart.value?.id === cart.id) await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao adicionar') }
}

async function openCart(id) {
  try { const { data } = await api.get(`/separation/carts/${id}`); activeCart.value = data; focusFirstBip() }
  catch { toast.error('Erro ao abrir gaiola') }
}
async function refreshCart() { if (activeCart.value) await openCart(activeCart.value.id) }

async function scan(o) {
  const code = (bipCode.value[o.id] || '').trim()
  if (!code) return
  try {
    const { data } = await api.post(`/separation/carts/${activeCart.value.id}/orders/${o.id}/scan`, { code })
    bipCode.value[o.id] = ''
    if (o.scan) { o.scan.scanned = data.scanned; o.scan.expected = data.expected }
    if (data.complete) toast.success(`Pedido #${o.id} conferido 100% — etiqueta liberada`)
    await nextTick(); bipRefs.value[o.id]?.focus()
  } catch (e) {
    bipCode.value[o.id] = ''
    toast.error(e.response?.data?.detail || 'Código inválido')
    await nextTick(); bipRefs.value[o.id]?.focus()
  }
}

function canPrintLabel(o) {
  if (activeCart.value?.mode === 'scan' && o.scan) return o.scan.scanned >= o.scan.expected
  return true
}

async function removeOrder(id) {
  try { await api.delete(`/separation/carts/${activeCart.value.id}/orders/${id}`); await Promise.all([refreshCart(), loadPending(), loadCarts()]) }
  catch (e) { toast.error(e.response?.data?.detail || 'Erro ao remover') }
}

async function concludeCart() {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/conclude`)
    toast.success('Gaiola concluída — pronta para a transportadora')
    await Promise.all([refreshCart(), loadCarts(), loadPending()])
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

// ── Etiquetas ──
async function printOrderLabel(o) {
  await openPdf(`/separation/carts/${activeCart.value.id}/labels.pdf`, 'get', null, { order_id: o.id, layout: layout.value })
  await refreshCart()
}
async function printAllLabels() {
  try {
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/label-jobs`)
    const jobs = data.jobs || []
    if (!jobs.length) return toast.warning('Nenhuma etiqueta pronta para imprimir (bipe os pedidos no modo bipagem).')
    for (const job of jobs) {
      const params = job.kind === 'manual' ? { manual: true, layout: layout.value } : { account_id: job.account_id }
      await openPdf(`/separation/carts/${activeCart.value.id}/labels.pdf`, 'get', null, params)
    }
    if (data.blocked_scan) toast.info(`${data.blocked_scan} pedido(s) aguardando bipagem (etiqueta não liberada).`)
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao imprimir etiquetas') }
}

// ── NF-e na gaiola ──
async function openDanfe(orderId) {
  await openPdf(`/separation/orders/${orderId}/danfe`, 'get')
}
async function emitPrintOrderNfe(o) {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/emit-nfe`, { order_ids: [o.id] })
    // sincroniza/marca e descobre quais já têm nota
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/nfe`, { params: { order_id: o.id, mark: 1 } })
    const ready = (data.nfe || []).filter(n => n.nfe_key || n.nfe_url)
    if (ready.length) for (const n of ready) await openDanfe(n.order_id)
    else toast.info(`NF-e do #${o.id} solicitada — DANFE ainda processando no ML`)
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro na NF-e') }
}
async function cartNfe() {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/emit-nfe`, {})
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/nfe`, { params: { mark: 1 } })
    const ready = (data.nfe || []).filter(n => n.nfe_key || n.nfe_url)
    if (!ready.length) return toast.info('NF-e solicitadas — DANFE ainda processando no ML')
    for (const n of ready) await openDanfe(n.order_id)
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro na NF-e') }
}

// ── Baixar tudo (ZIP): etiquetas + DANFE + XML ──
async function downloadBundle() {
  if (!activeCart.value || downloadingBundle.value) return
  downloadingBundle.value = true
  try {
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/bundle.zip`,
      { responseType: 'blob', params: { layout: layout.value } })
    const url = URL.createObjectURL(new Blob([data], { type: 'application/zip' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${activeCart.value.cart_number}-documentos.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 60000)
    toast.success('ZIP gerado. Confira o _avisos.txt caso algum pedido tenha ficado de fora.')
    await refreshCart()
  } catch (e) {
    let msg = 'Erro ao gerar o ZIP'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* ignore */ }
    toast.error(msg)
  } finally {
    downloadingBundle.value = false
  }
}

function nfeIconClass(o) {
  if (o.nfe_printed) return 'text-success'
  if (o.nfe_url || o.nfe_status === 'authorized') return 'text-info'
  if (['pending', 'in_process'].includes(o.nfe_status)) return 'text-warning'
  return 'text-muted'
}
function nfeIconTitle(o) {
  if (o.nfe_printed) return 'DANFE impressa'
  if (o.nfe_url || o.nfe_status === 'authorized') return 'NF-e emitida (não impressa)'
  if (['pending', 'in_process'].includes(o.nfe_status)) return 'NF-e processando no ML'
  return 'Sem NF-e (opcional)'
}

async function openPdf(url, method, body, params) {
  try {
    const cfg = { responseType: 'blob', params }
    const resp = method === 'post' ? await api.post(url, body, cfg) : await api.get(url, cfg)
    // abre para imprimir E baixa cópia nomeada (nome vem do Content-Disposition do backend)
    openAndSaveBlobResponse(resp, 'documento.pdf', 'application/pdf')
  } catch (e) {
    // erro pode vir como blob JSON
    let msg = 'Erro ao gerar PDF'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* ignore */ }
    toast.error(msg)
  }
}

function focusFirstBip() {
  if (activeCart.value?.mode !== 'scan') return
  nextTick(() => {
    const first = activeCart.value.orders.find(o => o.scan && o.scan.scanned < o.scan.expected)
    if (first) bipRefs.value[first.id]?.focus()
  })
}

function pct(scan) { return scan.expected ? Math.round((scan.scanned / scan.expected) * 100) : 0 }
function fmt(dt) { return fmtBrDateTime(dt) }   // fonte única (horário do Brasil)
function fmtDate(d) { return fmtBrDate(d) }
</script>

<style scoped>
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { background: rgba(0,0,0,.03); }
.modal-backdrop-custom { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1050; }
</style>
