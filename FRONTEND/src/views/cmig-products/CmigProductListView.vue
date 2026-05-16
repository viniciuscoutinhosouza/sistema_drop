<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Produtos CMIG</h1>
            <small class="text-muted" v-if="cmig">{{ cmig.company_name }}</small>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink :to="`/cmigs/${cmigId}`" class="btn btn-secondary mr-2">
              <i class="fas fa-arrow-left mr-1"></i> Voltar à CMIG
            </RouterLink>
            <RouterLink v-if="isAC" :to="`/cmig-products/new?cmig_id=${cmigId}`" class="btn btn-outline-primary mr-2">
              <i class="fas fa-plus mr-1"></i> Novo Produto
            </RouterLink>
            <RouterLink v-if="isAC" :to="`/cmig-products/novo-composto?cmig_id=${cmigId}`" class="btn btn-primary">
              <i class="fas fa-layer-group mr-1"></i> Novo KIT
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-header d-flex align-items-center">
            <h3 class="card-title flex-grow-1"><i class="fas fa-box mr-2"></i>Produtos cadastrados</h3>
            <div class="btn-group btn-group-sm">
              <button class="btn btn-outline-secondary" :class="{ active: filter === 'all' }" @click="setFilter('all')">Todos</button>
              <button class="btn btn-outline-secondary" :class="{ active: filter === 'simple' }" @click="setFilter('simple')">Simples</button>
              <button class="btn btn-outline-secondary" :class="{ active: filter === 'composite' }" @click="setFilter('composite')">KITs</button>
            </div>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover table-striped mb-0">
              <thead>
                <tr>
                  <th style="width:72px"></th>
                  <th>SKU CMIG</th>
                  <th>Título</th>
                  <th>Estoque</th>
                  <th>Custo</th>
                  <th>PG Vinculado</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="products.length === 0">
                  <td colspan="8" class="text-center text-muted py-4">Nenhum produto cadastrado.</td>
                </tr>
                <tr v-for="p in products" :key="p.id">
                  <td class="p-1 text-center">
                    <img v-if="getThumb(p)" :src="getThumb(p)"
                         style="width:56px;height:56px;object-fit:cover;border-radius:4px;" />
                    <div v-else style="width:56px;height:56px;background:#f4f4f4;border-radius:4px;display:flex;align-items:center;justify-content:center;">
                      <i class="fas fa-image text-muted"></i>
                    </div>
                  </td>
                  <td><code>{{ p.sku_cmig }}</code></td>
                  <td>
                    <span v-if="p.is_composite" class="badge badge-warning mr-1" style="font-size:0.7em">KIT</span>
                    {{ p.title }}
                    <div v-if="p.brand || p.model" class="small text-muted mt-1">
                      <span v-if="p.brand">{{ p.brand }}</span>
                      <span v-if="p.brand && p.model"> · </span>
                      <span v-if="p.model">{{ p.model }}</span>
                    </div>
                  </td>
                  <td>
                    <span :class="p.stock_quantity === 0 ? 'text-danger font-weight-bold' : ''">
                      {{ p.stock_quantity }}
                    </span>
                  </td>
                  <td>{{ p.cost_price ? `R$ ${Number(p.cost_price).toFixed(2)}` : '—' }}</td>
                  <td>
                    <span v-if="p.pg_product_id" class="badge badge-success">PG #{{ p.pg_product_id }}</span>
                    <span v-else class="badge badge-secondary">Sem vínculo</span>
                  </td>
                  <td>
                    <span class="badge" :class="p.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ p.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink
                      v-if="isAC || isUGO"
                      :to="p.is_composite ? `/cmig-products/${p.id}/editar-composto?cmig_id=${cmigId}` : `/cmig-products/${p.id}/edit?cmig_id=${cmigId}`"
                      class="btn btn-sm btn-outline-primary mr-1" title="Editar"
                    >
                      <i class="fas fa-edit"></i>
                    </RouterLink>
                    <button v-if="isAC || isUGO" class="btn btn-sm btn-outline-secondary mr-1" title="Duplicar produto" @click="duplicate(p)">
                      <i class="fas fa-copy"></i>
                    </button>
                    <button v-if="isAC && !p.pg_product_id" class="btn btn-sm btn-outline-secondary mr-1" @click="openLinkPg(p)" title="Vincular ao PG">
                      <i class="fas fa-link"></i>
                    </button>
                    <button v-if="isUGO && !p.pg_product_id" class="btn btn-sm btn-outline-warning mr-1" @click="importToPg(p)" title="Importar para PG">
                      <i class="fas fa-file-import"></i>
                    </button>
                    <button v-if="isUGO && p.pg_product_id" class="btn btn-sm btn-outline-info mr-1" @click="syncPg(p)" title="Sincronizar dados com PG">
                      <i class="fas fa-sync-alt"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-dark mr-1" @click="openMovements(p)" title="Histórico de movimentação de estoque">
                      <i class="fas fa-history"></i>
                    </button>
                    <button v-if="isAC" class="btn btn-sm btn-outline-danger" @click="deleteProduct(p)" title="Excluir produto">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Modal Duplicar CMIG -->
    <div v-if="duplicateModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header py-2">
            <h6 class="modal-title"><i class="fas fa-copy mr-2"></i>Duplicar Produto</h6>
            <button type="button" class="close" @click="duplicateModal.show = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted mb-2" style="font-size:12px">SKU de origem: <strong>{{ duplicateModal.srcSku }}</strong></p>
            <div class="form-group mb-0">
              <label class="font-weight-bold" style="font-size:13px">Novo SKU <span class="text-danger">*</span></label>
              <input
                v-model="duplicateModal.newSku"
                type="text"
                class="form-control form-control-sm"
                placeholder="Digite o SKU do novo produto"
                @keyup.enter="confirmDuplicate"
              />
            </div>
          </div>
          <div class="modal-footer py-2">
            <button class="btn btn-sm btn-secondary" @click="duplicateModal.show = false">Cancelar</button>
            <button class="btn btn-sm btn-primary" :disabled="!duplicateModal.newSku.trim() || duplicateModal.loading" @click="confirmDuplicate">
              <i v-if="duplicateModal.loading" class="fas fa-spinner fa-spin mr-1"></i>
              Duplicar
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal Histórico de Movimentações -->
    <div v-if="movementsModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-xl" style="max-width:95vw">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-history mr-2"></i>Movimentação de Estoque
              <small class="text-muted ml-2" v-if="movementsModal.product">
                · {{ movementsModal.product.sku_cmig }} — {{ movementsModal.product.title }}
              </small>
            </h5>
            <button type="button" class="close" @click="closeMovements"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <!-- Filtros de período -->
            <div class="row mb-3">
              <div class="col-md-3">
                <label class="font-weight-bold" style="font-size:13px">Data inicial</label>
                <input type="date" v-model="movementsModal.startDate" class="form-control form-control-sm" @change="loadMovements" />
              </div>
              <div class="col-md-3">
                <label class="font-weight-bold" style="font-size:13px">Data final</label>
                <input type="date" v-model="movementsModal.endDate" class="form-control form-control-sm" @change="loadMovements" />
              </div>
              <div class="col-md-6 d-flex align-items-end" style="gap:.25rem">
                <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(7)">7 dias</button>
                <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(30)">30 dias</button>
                <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(90)">90 dias</button>
                <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(365)">1 ano</button>
                <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(null)" title="Todo o histórico">Tudo</button>
              </div>
            </div>

            <!-- Cards de saldo -->
            <div v-if="!movementsModal.loading && movementsModal.data">
              <div class="row mb-2">
                <div class="col-md">
                  <div class="card bg-light mb-0">
                    <div class="card-body py-2 text-center">
                      <small class="text-muted d-block">Saldo Inicial</small>
                      <strong style="font-size:1.2rem">{{ movementsModal.data.initial_balance }}</strong>
                    </div>
                  </div>
                </div>
                <div class="col-md">
                  <div class="card bg-success text-white mb-0">
                    <div class="card-body py-2 text-center">
                      <small class="d-block">Entradas NFe</small>
                      <strong style="font-size:1.2rem">+{{ movementsModal.data.period_in_nfe }}</strong>
                    </div>
                  </div>
                </div>
                <div class="col-md">
                  <div class="card bg-danger text-white mb-0">
                    <div class="card-body py-2 text-center">
                      <small class="d-block">Saídas NFe</small>
                      <strong style="font-size:1.2rem">−{{ movementsModal.data.period_out_nfe }}</strong>
                    </div>
                  </div>
                </div>
                <div class="col-md">
                  <div class="card bg-info text-white mb-0"
                       title="Saldo Físico = Saldo Inicial + Entradas NFe − Saídas NFe − Pedidos">
                    <div class="card-body py-2 text-center">
                      <small class="d-block">Saldo Físico</small>
                      <strong style="font-size:1.2rem">{{ saldoFisico }}</strong>
                    </div>
                  </div>
                </div>
              </div>
              <div class="row mb-3">
                <div class="col-md">
                  <div class="card bg-warning text-dark mb-0" title="Pedidos com status handling ou ready_to_ship">
                    <div class="card-body py-2 text-center">
                      <small class="d-block">Reservado</small>
                      <strong style="font-size:1.2rem">−{{ movementsModal.data.reserved_in_pending_orders }}</strong>
                    </div>
                  </div>
                </div>
                <div class="col-md">
                  <div class="card mb-0" style="background:#fd7e14;color:#fff" title="Pedidos shipped/delivered ainda sem NFe outbound emitida.">
                    <div class="card-body py-2 text-center">
                      <small class="d-block">Pedidos</small>
                      <strong style="font-size:1.2rem">−{{ movementsModal.data.moved_in_orders_no_nfe }}</strong>
                    </div>
                  </div>
                </div>
                <div class="col-md">
                  <div class="card bg-primary text-white mb-0">
                    <div class="card-body py-2 text-center">
                      <small class="d-block">Disponível</small>
                      <strong style="font-size:1.2rem">{{ movementsModal.data.current_balance_available }}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Tabela -->
            <div v-if="movementsModal.loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else-if="!movementsModal.data || movementsModal.data.movements.length === 0" class="text-center text-muted py-4">
              <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
              Nenhuma movimentação no período.
            </div>
            <div v-else class="table-responsive" style="max-height:45vh">
              <table class="table table-sm table-hover mb-0" style="white-space:nowrap;font-size:13px">
                <thead class="thead-light sticky-top">
                  <tr>
                    <th>Data</th>
                    <th>Origem</th>
                    <th>Referência</th>
                    <th>Pessoa / Anúncio</th>
                    <th>Item</th>
                    <th class="text-right">Qtd</th>
                    <th class="text-right">Saldo Disponível</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(m, idx) in movementsModal.data.movements" :key="idx">
                    <td style="font-size:12px">{{ formatDateTimeOneLine(m.date) }}</td>
                    <td>
                      <span v-if="m.source === 'nfe_in'" class="badge badge-success">
                        <i class="fas fa-file-invoice mr-1"></i>NFe Entrada
                      </span>
                      <span v-else-if="m.source === 'nfe_out'" class="badge badge-danger">
                        <i class="fas fa-file-invoice mr-1"></i>NFe Saída
                      </span>
                      <span v-else-if="m.order_platform === 'mercadolivre'"
                            class="d-inline-flex align-items-center"
                            title="Mercado Livre">
                        <img v-if="!mlLogoError" :src="mlLogoUrl" alt="ML"
                             style="height:22px;width:auto" @error="mlLogoError = true" />
                        <span v-else class="badge" style="background:#FFE600;color:#3F3F3F;font-weight:bold">
                          <i class="fas fa-shopping-bag mr-1"></i>ML
                        </span>
                      </span>
                      <span v-else-if="m.order_platform === 'shopee'"
                            class="badge" style="background:#EE4D2D;color:#fff;font-weight:bold"
                            title="Shopee">
                        <i class="fas fa-shopping-bag mr-1"></i>Shopee
                      </span>
                      <span v-else class="badge badge-secondary">
                        <i class="fas fa-shopping-bag mr-1"></i>{{ m.order_platform || 'Pedido' }}
                      </span>
                    </td>
                    <td style="font-size:12px">
                      <RouterLink v-if="m.source !== 'order' && m.invoice_id" :to="`/fiscal/invoices/${m.invoice_id}`" class="text-primary">
                        <span v-if="m.invoice_number">NF #{{ m.invoice_number }}<span v-if="m.invoice_serie">/{{ m.invoice_serie }}</span></span>
                        <span v-else>Rascunho #{{ m.invoice_id }}</span>
                      </RouterLink>
                      <span v-else-if="m.source === 'order' && m.order_id">
                        <RouterLink :to="`/orders/${m.order_id}`" class="text-primary">#{{ m.order_platform_id || m.order_id }}</RouterLink>
                        <span class="text-muted ml-1">· {{ shipmentLabel(m.order_shipment_status) }}</span>
                        <span v-if="m.is_reserved" class="badge badge-warning text-dark ml-1" title="Status handling ou ready_to_ship">reservado</span>
                      </span>
                      <span v-if="m.source !== 'order' && m.invoice_status" class="text-muted ml-1">· {{ statusLabel(m.invoice_status) }}</span>
                    </td>
                    <td style="font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis">
                      <span v-if="m.source === 'order'" :title="m.item_ml_item_id || ''">
                        <code v-if="m.item_ml_item_id">{{ m.item_ml_item_id }}</code>
                        <span v-else class="text-muted">—</span>
                      </span>
                      <span v-else :title="m.person_name || ''">{{ m.person_name || '—' }}</span>
                    </td>
                    <td style="max-width:340px;overflow:hidden;text-overflow:ellipsis" :title="m.item_description || ''">
                      <code v-if="m.item_sku">{{ m.item_sku }}</code>
                      <span v-if="m.item_sku && m.item_description"> - </span>
                      <span>{{ m.item_description || '' }}</span>
                    </td>
                    <td class="text-right" :class="m.direction === 'in' ? 'text-success' : 'text-danger'">
                      {{ m.direction === 'in' ? '+' : '−' }}{{ m.qty }}<span v-if="m.source === 'order' && m.qty_to_pg > 0" class="text-secondary ml-1" :title="`${m.qty_to_pg} em overflow PG`">(+{{ m.qty_to_pg }} PG)</span>
                    </td>
                    <td class="text-right"><strong>{{ m.running_available }}</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <small class="text-muted d-block mt-2">
              <i class="fas fa-info-circle mr-1"></i>
              <strong>NFes</strong> ajustam o saldo do banco (`stock_quantity`).
              <strong>Pedidos</strong> com status <code>shipped</code>/<code>delivered</code> sem NFe ainda contam como <em>reservados</em> — `Disponível = NFe Atual − Reservado`.
              <span v-if="movementsModal.data && movementsModal.data.has_pg_link">
                Pedidos que excedem o estoque CMIG (overflow) são debitados do PG vinculado (#{{ movementsModal.data.pg_product_id }}).
              </span>
              <span v-else>Este produto não tem vínculo com PG — overflow não aplicável.</span>
            </small>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="closeMovements">Fechar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal Vincular PG -->
    <div v-if="showLinkModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Vincular ao PG</h5>
            <button class="close" @click="showLinkModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p>Produto: <strong>{{ selectedProduct?.title }}</strong></p>
            <div class="form-group">
              <label>ID do Produto PG</label>
              <input v-model="pgProductId" type="number" class="form-control" placeholder="Ex: 42" />
              <small class="text-muted">Informe o ID do produto no Produto Geral (PG) do Galpão.</small>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showLinkModal = false">Cancelar</button>
            <button class="btn btn-primary" @click="linkToPg" :disabled="savingLink">
              <span v-if="savingLink"><i class="fas fa-spinner fa-spin mr-1"></i></span>Vincular
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

const duplicateModal = ref({ show: false, srcId: null, srcSku: '', newSku: '', loading: false })

const movementsModal = reactive({
  show: false,
  loading: false,
  product: null,
  startDate: '',
  endDate: '',
  data: null,
})

const mlLogoError = ref(false)
const mlLogoUrl = '/marketplaces/mercadolivre-icon.png'

const saldoFisico = computed(() => {
  const d = movementsModal.data
  if (!d) return 0
  return (d.initial_balance || 0)
       + (d.period_in_nfe || 0)
       - (d.period_out_nfe || 0)
       - (d.moved_in_orders_no_nfe || 0)
})

function todayIso() { return new Date().toISOString().slice(0, 10) }
function isoDaysAgo(days) {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

function setPeriodPreset(days) {
  if (days === null) {
    movementsModal.startDate = ''
    movementsModal.endDate = ''
  } else {
    movementsModal.startDate = isoDaysAgo(days)
    movementsModal.endDate = todayIso()
  }
  loadMovements()
}

function openMovements(product) {
  movementsModal.product = product
  movementsModal.startDate = isoDaysAgo(30)
  movementsModal.endDate = todayIso()
  movementsModal.data = null
  movementsModal.show = true
  loadMovements()
}

function closeMovements() {
  movementsModal.show = false
  movementsModal.product = null
  movementsModal.data = null
}

async function loadMovements() {
  if (!movementsModal.product) return
  movementsModal.loading = true
  try {
    const params = {}
    if (movementsModal.startDate) params.start_date = movementsModal.startDate
    if (movementsModal.endDate) params.end_date = movementsModal.endDate
    const { data } = await api.get(
      `/cmigs/${cmigId.value}/products/${movementsModal.product.id}/stock-movements`,
      { params },
    )
    movementsModal.data = data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar movimentações.')
  } finally {
    movementsModal.loading = false
  }
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function formatDateTimeOneLine(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  // Formato curto: dd/MM HH:mm
  const dt = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
  const tm = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  return `${dt} ${tm}`
}

const _statusLabels = {
  draft: 'Rascunho',
  processing: 'Processando',
  authorized: 'Autorizada',
  finalized: 'Finalizada',
  cancelled: 'Cancelada',
  denied: 'Denegada',
  rejected: 'Rejeitada',
}
function statusLabel(s) { return _statusLabels[s] || s }

const _shipmentLabels = {
  pending: 'Pendente',
  handling: 'Em preparação',
  ready_to_ship: 'Pronto p/ envio',
  shipped: 'A caminho',
  delivered: 'Entregue',
  not_delivered: 'Não entregue',
  cancelled: 'Cancelado',
}
function shipmentLabel(s) { return _shipmentLabels[s] || s || '—' }

const cmigId = computed(() => route.query.cmig_id || route.params.cmig_id)
const cmig = ref(null)
const allProducts = ref([])
const filter = ref('all')
const products = computed(() => {
  if (filter.value === 'composite') return allProducts.value.filter(p => p.is_composite)
  if (filter.value === 'simple') return allProducts.value.filter(p => !p.is_composite)
  return allProducts.value
})
const loading = ref(false)
const showLinkModal = ref(false)
const selectedProduct = ref(null)
const pgProductId = ref('')
const savingLink = ref(false)

const isAC = computed(() => authStore.user?.role === 'ac')
const isUGO = computed(() => ['ugo', 'admin'].includes(authStore.user?.role))

function setFilter(val) { filter.value = val }

onMounted(async () => {
  if (!cmigId.value) return
  const { data: c } = await api.get(`/cmigs/${cmigId.value}`)
  cmig.value = c
  await loadProducts()
})

function getThumb(p) {
  if (p.images && p.images.length) return p.images[0].url
  if (p.pictures_json) {
    try {
      const pics = JSON.parse(p.pictures_json)
      if (pics.length) return pics[0].url
    } catch {}
  }
  return null
}

async function loadProducts() {
  loading.value = true
  try {
    const { data } = await api.get(`/cmigs/${cmigId.value}/products`)
    allProducts.value = data
  } finally {
    loading.value = false
  }
}

function openLinkPg(product) {
  selectedProduct.value = product
  pgProductId.value = ''
  showLinkModal.value = true
}

async function linkToPg() {
  savingLink.value = true
  try {
    await api.post(`/cmigs/${cmigId.value}/products/${selectedProduct.value.id}/link-pg`, {
      pg_product_id: Number(pgProductId.value),
    })
    toast.success('Produto vinculado ao PG!')
    showLinkModal.value = false
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao vincular produto.')
  } finally {
    savingLink.value = false
  }
}

function duplicate(p) {
  duplicateModal.value = { show: true, srcId: p.id, srcSku: p.sku_cmig, newSku: '', loading: false }
}

async function confirmDuplicate() {
  const m = duplicateModal.value
  if (!m.newSku.trim()) return
  m.loading = true
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${m.srcId}/duplicate`, { sku_cmig: m.newSku.trim() })
    toast.success(`Produto duplicado! SKU: ${data.sku_cmig}`)
    duplicateModal.value.show = false
    router.push(`/cmig-products/${data.id}/edit?cmig_id=${cmigId.value}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao duplicar produto.')
    m.loading = false
  }
}

async function deleteProduct(p) {
  if (!confirm(`Excluir "${p.title}"?\n\nSe o produto não possuir vendas será excluído permanentemente, caso contrário será desativado.`)) return
  try {
    const { data } = await api.delete(`/cmigs/${cmigId.value}/products/${p.id}`)
    if (data?.action === 'deactivated') {
      toast.warning(data.message || 'Produto desativado (possui vendas).')
    } else {
      toast.success('Produto excluído com sucesso!')
    }
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir produto.')
  }
}

async function importToPg(product) {
  if (!confirm(`Importar "${product.title}" para o Produto Geral (PG)?`)) return
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${product.id}/import-to-pg`)
    const extras = [
      data.photos_imported ? `${data.photos_imported} foto(s)` : null,
      data.variants_imported ? `${data.variants_imported} variante(s)` : null,
      data.brand ? `Marca: ${data.brand}` : null,
      data.model ? `Modelo: ${data.model}` : null,
    ].filter(Boolean).join(' · ')
    toast.success(`Produto importado para o PG! SKU: ${data.sku}${extras ? ' · ' + extras : ''}`)
    await loadProducts()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao importar produto.')
  }
}

async function syncPg(product) {
  if (!confirm(`Sincronizar dados de "${product.title}" com o PG vinculado (PG #${product.pg_product_id})?\n\nIsso irá atualizar: Marca, Modelo, EAN, NCM, CEST, dimensões e origem no PG.`)) return
  try {
    const { data } = await api.post(`/cmigs/${cmigId.value}/products/${product.id}/sync-pg`)
    const synced = [
      data.brand ? `Marca: ${data.brand}` : null,
      data.model ? `Modelo: ${data.model}` : null,
      data.ean ? `EAN: ${data.ean}` : null,
    ].filter(Boolean).join(' · ')
    toast.success(`PG sincronizado!${synced ? ' ' + synced : ' (sem Marca/Modelo no CMIG — edite o produto CMIG primeiro)'}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar com PG.')
  }
}
</script>
