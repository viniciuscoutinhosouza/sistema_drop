<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Produtos Gerais (PG)</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/pg/novo-composto" class="btn btn-outline-primary mr-2">
              <i class="fas fa-layer-group mr-1"></i> Novo KIT
            </RouterLink>
            <RouterLink to="/pg/new" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Novo Produto
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-boxes mr-2"></i>Produtos cadastrados</h3>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover table-striped mb-0">
              <thead>
                <tr>
                  <th style="width:72px"></th>
                  <th>SKU</th>
                  <th>Título</th>
                  <th>Custo</th>
                  <th>Preço Sugerido</th>
                  <th>Estoque</th>
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
                    <img v-if="p.thumbnail" :src="p.thumbnail"
                         style="width:56px;height:56px;object-fit:cover;border-radius:4px;" />
                    <div v-else style="width:56px;height:56px;background:#f4f4f4;border-radius:4px;display:flex;align-items:center;justify-content:center;">
                      <i class="fas fa-image text-muted"></i>
                    </div>
                  </td>
                  <td><code>{{ p.sku }}</code></td>
                  <td>
                    <span v-if="p.is_composite" class="badge badge-warning mr-1" style="font-size:0.7em">COMPOSTO</span>
                    {{ p.title }}
                  </td>
                  <td>{{ p.cost_price ? `R$ ${Number(p.cost_price).toFixed(2)}` : '—' }}</td>
                  <td>{{ p.suggested_price ? `R$ ${Number(p.suggested_price).toFixed(2)}` : '—' }}</td>
                  <td>
                    <input
                      type="number" min="0"
                      :value="p.stock_quantity"
                      class="form-control form-control-sm"
                      style="width:80px"
                      @change="updateStock(p.id, $event.target.value)"
                    />
                  </td>
                  <td>
                    <span :class="`badge badge-${p.is_active ? 'success' : 'secondary'}`">
                      {{ p.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink
                      :to="p.is_composite ? `/pg/${p.id}/editar-composto` : `/pg/${p.id}/edit`"
                      class="btn btn-sm btn-outline-primary mr-1" title="Editar"
                    >
                      <i class="fas fa-edit"></i>
                    </RouterLink>
                    <button class="btn btn-sm btn-outline-secondary mr-1" title="Duplicar produto" @click="duplicate(p)">
                      <i class="fas fa-copy"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-dark mr-1" title="Histórico de movimentação de estoque" @click="openMovements(p)">
                      <i class="fas fa-history"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" title="Desativar" @click="deactivate(p)">
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
  </div>

  <!-- Modal Histórico de Movimentações -->
  <div v-if="movementsModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-xl" style="max-width:95vw">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-history mr-2"></i>Movimentação de Estoque
            <small class="text-muted ml-2" v-if="movementsModal.product">
              · {{ movementsModal.product.sku }} — {{ movementsModal.product.title }}
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

          <!-- Cards de saldo: NFe agregada dos CMIGs vinculados (linha 1) + Pedidos overflow (linha 2) -->
          <div v-if="!movementsModal.loading && movementsModal.data">
            <div class="row mb-2">
              <div class="col-md">
                <div class="card bg-light mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="text-muted d-block">Saldo Inicial (NFe linked)</small>
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
                <div class="card bg-info text-white mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Saldo Final (NFe linked)</small>
                    <strong style="font-size:1.2rem">{{ movementsModal.data.final_balance }}</strong>
                  </div>
                </div>
              </div>
            </div>
            <div class="row mb-3">
              <div class="col-md">
                <div class="card bg-dark text-white mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Saldo PG Atual</small>
                    <strong style="font-size:1.2rem">{{ movementsModal.data.current_balance_pg }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md">
                <div class="card bg-warning text-dark mb-0" title="Overflow de pedidos com status handling ou ready_to_ship">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Reservado PG</small>
                    <strong style="font-size:1.2rem">−{{ movementsModal.data.reserved_in_pending_orders_pg }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md">
                <div class="card mb-0" style="background:#fd7e14;color:#fff" title="Overflow de pedidos shipped/delivered sem NFe outbound emitida">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Pedidos PG</small>
                    <strong style="font-size:1.2rem">−{{ movementsModal.data.moved_in_orders_no_nfe_pg }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md">
                <div class="card bg-primary text-white mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">PG Disponível</small>
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
            <span v-if="movementsModal.data && movementsModal.data.linked_cmig_count === 0">
              Este PG não tem nenhum CMIGProduct vinculado — sem movimentações para exibir.
            </span>
            <span v-else>Nenhuma movimentação no período.</span>
          </div>
          <div v-else class="table-responsive" style="max-height:45vh">
            <table class="table table-sm table-hover mb-0" style="white-space:nowrap;font-size:13px">
              <thead class="thead-light sticky-top">
                <tr>
                  <th>Data</th>
                  <th>Origem</th>
                  <th>Referência</th>
                  <th>CMIG / Produto</th>
                  <th>Pessoa / Anúncio</th>
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
                          title="Mercado Livre — overflow PG">
                      <img v-if="!mlLogoError" :src="mlLogoUrl" alt="ML"
                           style="height:22px;width:auto" @error="mlLogoError = true" />
                      <span v-else class="badge" style="background:#FFE600;color:#3F3F3F;font-weight:bold">
                        <i class="fas fa-shopping-bag mr-1"></i>ML
                      </span>
                    </span>
                    <span v-else-if="m.order_platform === 'shopee'"
                          class="badge" style="background:#EE4D2D;color:#fff;font-weight:bold"
                          title="Shopee — overflow PG">
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
                  <td style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis"
                      :title="(m.cmig_name || '') + ' · ' + (m.cmig_product_title || '')">
                    <span v-if="m.cmig_product_sku"><code>{{ m.cmig_product_sku }}</code></span>
                    <span v-if="m.cmig_name" class="text-muted ml-1">· {{ m.cmig_name }}</span>
                    <span v-if="!m.cmig_product_sku && !m.cmig_name" class="text-muted">—</span>
                  </td>
                  <td style="font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis">
                    <span v-if="m.source === 'order'" :title="m.item_ml_item_id || ''">
                      <code v-if="m.item_ml_item_id">{{ m.item_ml_item_id }}</code>
                      <span v-else class="text-muted">—</span>
                    </span>
                    <span v-else :title="m.person_name || ''">{{ m.person_name || '—' }}</span>
                  </td>
                  <td class="text-right" :class="m.direction === 'in' ? 'text-success' : 'text-danger'">
                    {{ m.direction === 'in' ? '+' : '−' }}{{ m.qty }}<span v-if="m.source === 'order' && m.qty_to_cmig > 0" class="text-info ml-1" :title="`${m.qty_to_cmig} em CMIG`">({{ m.qty_to_cmig }} CMIG)</span>
                  </td>
                  <td class="text-right"><strong>{{ m.running_available }}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
          <small class="text-muted d-block mt-2">
            <i class="fas fa-info-circle mr-1"></i>
            <strong>NFes</strong> são agregadas de todos os CMIGProducts vinculados a este PG (#{{ movementsModal.data?.linked_cmig_count || 0 }} CMIGs).
            <strong>Pedidos</strong> só aparecem quando excederam o estoque CMIG (overflow para PG).
            Estoque PG (`stock_quantity`) é manual e independente da agregação de NFes acima.
          </small>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeMovements">Fechar</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal Duplicar PG -->
  <div v-if="duplicateModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
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
              autofocus
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
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const products = ref([])
const loading  = ref(true)
const toast    = useToast()
const router   = useRouter()

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
    const { data } = await api.get(`/pg/${movementsModal.product.id}/stock-movements`, { params })
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

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/pg')
    products.value = data
  } finally {
    loading.value = false
  }
}

async function updateStock(id, qty) {
  try {
    await api.put(`/pg/${id}/stock`, { stock_quantity: parseInt(qty) })
  } catch (e) {
    toast.error('Erro ao atualizar estoque.')
  }
}

function duplicate(p) {
  duplicateModal.value = { show: true, srcId: p.id, srcSku: p.sku, newSku: '', loading: false }
}

async function confirmDuplicate() {
  const m = duplicateModal.value
  if (!m.newSku.trim()) return
  m.loading = true
  try {
    const { data } = await api.post(`/pg/${m.srcId}/duplicate`, { sku: m.newSku.trim() })
    toast.success(`Produto duplicado! SKU: ${data.sku}`)
    duplicateModal.value.show = false
    router.push(`/pg/${data.id}/edit`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao duplicar produto.')
    m.loading = false
  }
}

async function deactivate(p) {
  if (!confirm(`Excluir "${p.title}"?\n\nSe o produto não possuir vendas será excluído permanentemente, caso contrário será desativado.`)) return
  try {
    const { data } = await api.delete(`/pg/${p.id}`)
    if (data?.action === 'deactivated') {
      toast.warning(data.message || 'Produto desativado (possui vendas).')
    } else {
      toast.success('Produto excluído com sucesso!')
    }
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir produto.')
  }
}

onMounted(load)
</script>
