<template>
  <div class="storage-addressing">
    <div class="d-flex justify-content-between align-items-center mb-2 flex-wrap">
      <h1 class="h4 mb-0"><i class="fas fa-map-marked-alt mr-2"></i>Endereçamento de Estoque</h1>
      <div v-if="isAdmin" class="form-inline">
        <label class="mr-2 small text-muted">Galpão</label>
        <select v-model="warehouseId" class="form-control form-control-sm" @change="reloadAll">
          <option :value="null" disabled>Selecione…</option>
          <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
        </select>
      </div>
    </div>

    <ul class="nav nav-tabs mb-3">
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'estrutura' }" href="#" @click.prevent="tab = 'estrutura'">Estrutura</a></li>
      <li class="nav-item"><a class="nav-link" :class="{ active: tab === 'mapa' }" href="#" @click.prevent="tab = 'mapa'; loadReconciliation()">Mapa & Reconciliação</a></li>
    </ul>

    <div v-if="isAdmin && !warehouseId" class="alert alert-info">Selecione um galpão para começar.</div>

    <!-- ════ ESTRUTURA ════ -->
    <div v-else-if="tab === 'estrutura'" class="row">
      <div class="col-md-7">
        <div class="card">
          <div class="card-header d-flex justify-content-between align-items-center">
            <span><i class="fas fa-sitemap mr-1"></i>Árvore de endereços</span>
            <div v-if="canConfig">
              <button class="btn btn-sm btn-outline-primary mr-1" @click="openNodeModal(null)"><i class="fas fa-plus"></i> Área/Raiz</button>
              <button class="btn btn-sm btn-outline-secondary" @click="openBulkModal(null)"><i class="fas fa-layer-group"></i> Gerar em massa</button>
            </div>
          </div>
          <div class="card-body p-2" style="max-height: 70vh; overflow:auto">
            <p v-if="!tree.length" class="text-muted small mb-0">Nenhum endereço ainda. Crie uma área ou gere em massa.</p>
            <StorageNode
              v-for="n in tree" :key="n.id" :node="n" :depth="0" :can-config="canConfig"
              :selected-id="selectedNode && selectedNode.id"
              @select="selectNode" @add="openNodeModal" @bulk="openBulkModal"
              @edit="n => openNodeModal(n, true)" @remove="removeNode" @label="printLocationLabel" />
          </div>
        </div>
      </div>

      <div class="col-md-5">
        <div class="card">
          <div class="card-header">
            <i class="fas fa-box-open mr-1"></i>
            <span v-if="selectedNode">{{ selectedNode.full_code }}</span>
            <span v-else class="text-muted">Selecione um endereço</span>
          </div>
          <div class="card-body p-2">
            <template v-if="selectedNode">
              <div v-if="!selectedNode.is_storable" class="alert alert-warning py-2 small mb-2">
                Este nó é organizacional (não armazenável). Produtos ficam nos nós-folha marcados como armazenáveis.
              </div>
              <div v-else>
                <button v-if="canMove" class="btn btn-sm btn-primary mb-2" @click="openAllocModal(null)"><i class="fas fa-plus"></i> Endereçar produto aqui</button>
                <p v-if="!nodeContents.length" class="text-muted small">Nada endereçado aqui.</p>
                <table v-else class="table table-sm table-hover">
                  <thead><tr><th>Produto</th><th class="text-right">Qtd</th><th>Caixas</th><th></th></tr></thead>
                  <tbody>
                    <tr v-for="a in nodeContents" :key="a.id">
                      <td>
                        <div class="small"><strong>{{ a.product && a.product.sku }}</strong></div>
                        <div class="small text-muted">{{ a.product && a.product.title }}</div>
                        <span v-if="a.lot" class="badge badge-info">Lote {{ a.lot.lot_code }}<span v-if="a.lot.expiry_date"> · val {{ a.lot.expiry_date }}</span></span>
                      </td>
                      <td class="text-right">{{ a.qty_units }}<div class="small text-muted" v-if="a.loose_units">({{ a.loose_units }} soltas)</div></td>
                      <td class="small">
                        <span v-for="p in a.packs" :key="p.id" class="d-block">{{ p.box_count }}×{{ p.units_per_box }}<span v-if="p.label"> ({{ p.label }})</span></span>
                        <span v-if="a.packs_over" class="text-danger">⚠ caixas &gt; qtd</span>
                      </td>
                      <td class="text-nowrap">
                        <button v-if="canMove" class="btn btn-xs btn-link p-0 mr-2" title="Editar" @click="openAllocModal(a)"><i class="fas fa-edit"></i></button>
                        <button v-if="canMove && a.packs.length" class="btn btn-xs btn-link p-0 mr-2" title="Etiquetas de caixa" @click="printBoxLabels(a)"><i class="fas fa-qrcode"></i></button>
                        <button v-if="canMove" class="btn btn-xs btn-link text-danger p-0" title="Remover" @click="removeAlloc(a)"><i class="fas fa-trash"></i></button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ════ MAPA & RECONCILIAÇÃO ════ -->
    <div v-else class="row">
      <div class="col-md-5">
        <div class="card">
          <div class="card-header"><i class="fas fa-barcode mr-1"></i>Bipar / buscar código</div>
          <div class="card-body">
            <div class="input-group">
              <input v-model="scanCode" class="form-control" placeholder="EAN, código interno, LOC-… ou BOX-…" @keyup.enter="doScan">
              <div class="input-group-append"><button class="btn btn-primary" @click="doScan"><i class="fas fa-search"></i></button></div>
            </div>
            <div v-if="scanResult" class="mt-3 small">
              <div class="font-weight-bold">{{ scanLabel }}</div>
              <pre class="bg-light p-2 mt-1" style="max-height:40vh;overflow:auto">{{ scanResult }}</pre>
            </div>
          </div>
        </div>
      </div>
      <div class="col-md-7">
        <div class="card">
          <div class="card-header d-flex justify-content-between">
            <span><i class="fas fa-balance-scale mr-1"></i>Reconciliação (endereçado × saldo)</span>
            <button class="btn btn-sm btn-outline-secondary" @click="loadReconciliation"><i class="fas fa-sync"></i></button>
          </div>
          <div class="card-body p-2" style="max-height:70vh;overflow:auto">
            <p class="small text-muted">Diferença = <strong>sem endereço</strong> (estoque ainda não alocado). Negativo = endereçado além do saldo.</p>
            <table class="table table-sm">
              <thead><tr><th>Produto</th><th class="text-right">Endereçado</th><th class="text-right">Saldo</th><th class="text-right">Sem endereço</th></tr></thead>
              <tbody>
                <tr v-for="i in recon" :key="i.product_type + i.product_id" :class="{ 'table-warning': i.sem_endereco !== 0 }">
                  <td class="small"><strong>{{ i.sku }}</strong><div class="text-muted">{{ i.title }}</div></td>
                  <td class="text-right">{{ i.addressed }}</td>
                  <td class="text-right">{{ i.stock }}</td>
                  <td class="text-right" :class="{ 'text-danger': i.over, 'text-success': i.sem_endereco === 0 }">{{ i.sem_endereco }}</td>
                </tr>
                <tr v-if="!recon.length"><td colspan="4" class="text-center text-muted small">Nada endereçado ainda.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: criar/editar nó -->
    <div v-if="nodeModal.open" class="modal-backdrop-custom" @click.self="nodeModal.open = false">
      <div class="modal-card">
        <h5>{{ nodeModal.id ? 'Editar endereço' : (nodeModal.parent ? 'Novo sub-endereço' : 'Nova área/raiz') }}</h5>
        <p v-if="nodeModal.parent" class="small text-muted">Dentro de: {{ nodeModal.parent.full_code }}</p>
        <div class="form-group"><label class="small">Tipo de nível (Sala, Armário, Estante, Coluna, Altura, Pallet…)</label>
          <input v-model="nodeModal.level_type" class="form-control form-control-sm"></div>
        <div class="form-group"><label class="small">Identificação (nome, número ou letra)</label>
          <input v-model="nodeModal.code" class="form-control form-control-sm"></div>
        <div class="form-group" v-if="!nodeModal.parent"><label class="small">Tipo de área</label>
          <select v-model="nodeModal.area_kind" class="form-control form-control-sm">
            <option :value="null">—</option><option value="pallet">Porta-pallet</option><option value="cabinet">Armários</option><option value="other">Outra</option>
          </select></div>
        <div class="form-check mb-2"><input type="checkbox" class="form-check-input" id="stor" v-model="nodeModal.is_storable">
          <label class="form-check-label small" for="stor">Armazenável (recebe produto)</label></div>
        <div class="form-group"><label class="small">Sequência de picking (rota)</label>
          <input type="number" v-model.number="nodeModal.pick_sequence" class="form-control form-control-sm"></div>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="nodeModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" @click="saveNode">Salvar</button>
        </div>
      </div>
    </div>

    <!-- Modal: gerar em massa -->
    <div v-if="bulkModal.open" class="modal-backdrop-custom" @click.self="bulkModal.open = false">
      <div class="modal-card">
        <h5>Gerar em massa</h5>
        <p v-if="bulkModal.parent" class="small text-muted">Dentro de: {{ bulkModal.parent.full_code }}</p>
        <div class="form-group"><label class="small">Tipo de nível (ex.: Estante)</label>
          <input v-model="bulkModal.level_type" class="form-control form-control-sm"></div>
        <div class="form-group"><label class="small">Esquema de identificação</label>
          <select v-model="bulkModal.scheme.type" class="form-control form-control-sm">
            <option value="numeric">Faixa numérica (1 a 8)</option>
            <option value="letter">Faixa de letras (A a F)</option>
            <option value="named">Lista de nomes (Mickey, Pateta…)</option>
          </select></div>
        <div v-if="bulkModal.scheme.type === 'numeric'" class="form-row">
          <div class="col"><label class="small">De</label><input type="number" v-model.number="bulkModal.scheme.start" class="form-control form-control-sm"></div>
          <div class="col"><label class="small">Até</label><input type="number" v-model.number="bulkModal.scheme.end" class="form-control form-control-sm"></div>
          <div class="col"><label class="small">Zeros à esq.</label><input type="number" v-model.number="bulkModal.scheme.pad" class="form-control form-control-sm"></div>
        </div>
        <div v-else-if="bulkModal.scheme.type === 'letter'" class="form-row">
          <div class="col"><label class="small">De</label><input v-model="bulkModal.scheme.start" maxlength="1" class="form-control form-control-sm"></div>
          <div class="col"><label class="small">Até</label><input v-model="bulkModal.scheme.end" maxlength="1" class="form-control form-control-sm"></div>
        </div>
        <div v-else class="form-group"><label class="small">Nomes separados por vírgula</label>
          <input v-model="bulkModal.namesCsv" class="form-control form-control-sm" placeholder="Mickey, Pateta, Donald"></div>
        <div class="form-check mb-2"><input type="checkbox" class="form-check-input" id="bstor" v-model="bulkModal.is_storable">
          <label class="form-check-label small" for="bstor">Marcar os gerados como armazenáveis</label></div>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="bulkModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" @click="saveBulk">Gerar</button>
        </div>
      </div>
    </div>

    <!-- Modal: alocar produto -->
    <div v-if="allocModal.open" class="modal-backdrop-custom" @click.self="allocModal.open = false">
      <div class="modal-card">
        <h5>{{ allocModal.id ? 'Editar alocação' : 'Endereçar produto' }}</h5>
        <p class="small text-muted">Em: {{ selectedNode && selectedNode.full_code }}</p>
        <div v-if="!allocModal.id" class="form-group">
          <label class="small">Localizar produto (bipe EAN / código interno)</label>
          <div class="input-group">
            <input v-model="allocModal.scan" class="form-control form-control-sm" placeholder="EAN ou código interno" @keyup.enter="resolveAllocProduct">
            <div class="input-group-append"><button class="btn btn-sm btn-outline-primary" @click="resolveAllocProduct">Buscar</button></div>
          </div>
        </div>
        <div v-if="allocModal.product" class="alert alert-light py-2 small">
          <strong>{{ allocModal.product.sku }}</strong> — {{ allocModal.product.title }}
          <span v-if="allocModal.product.is_traceable" class="badge badge-warning ml-1">rastreável</span>
          <button v-if="!allocModal.product.main_ean && allocModal.canInternal" class="btn btn-xs btn-outline-secondary float-right" @click="genInternal">Gerar código interno</button>
        </div>
        <div class="form-row">
          <div class="form-group col"><label class="small">Quantidade (unidades)</label>
            <input type="number" v-model.number="allocModal.qty_units" class="form-control form-control-sm"></div>
          <div class="form-group col"><label class="small">Ordem de picking</label>
            <input type="number" v-model.number="allocModal.pick_order" class="form-control form-control-sm"></div>
        </div>
        <div v-if="allocModal.product && allocModal.product.is_traceable" class="form-group">
          <label class="small">Lote (id) <span class="text-muted">— informe o lote rastreável</span></label>
          <input type="number" v-model.number="allocModal.lot_id" class="form-control form-control-sm">
        </div>
        <label class="small d-block">Composição de caixas <span v-if="allocModal.defaults.length" class="text-muted">(padrões: <a v-for="d in allocModal.defaults" :key="d.id" href="#" class="mr-2" @click.prevent="addPack(d.units_per_box, d.label)">{{ d.units_per_box }}un</a>)</span></label>
        <div v-for="(p, idx) in allocModal.packs" :key="idx" class="form-row align-items-end mb-1">
          <div class="col"><input type="number" v-model.number="p.box_count" class="form-control form-control-sm" placeholder="caixas"></div>
          <div class="col-1 text-center">×</div>
          <div class="col"><input type="number" v-model.number="p.units_per_box" class="form-control form-control-sm" placeholder="un/caixa"></div>
          <div class="col"><input v-model="p.label" class="form-control form-control-sm" placeholder="rótulo"></div>
          <div class="col-auto"><button class="btn btn-xs btn-link text-danger" @click="allocModal.packs.splice(idx,1)"><i class="fas fa-times"></i></button></div>
        </div>
        <button class="btn btn-xs btn-outline-secondary mb-2" @click="addPack()"><i class="fas fa-plus"></i> caixa</button>
        <div class="text-right">
          <button class="btn btn-sm btn-secondary mr-2" @click="allocModal.open = false">Cancelar</button>
          <button class="btn btn-sm btn-primary" :disabled="!allocModal.product" @click="saveAlloc">Salvar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import StorageNode from '@/components/stock/StorageNode.vue'

const toast = useToast()
const auth = useAuthStore()

const isAdmin = computed(() => auth.user?.role === 'admin')
const canConfig = computed(() => auth.hasAction('endereco_configurar'))
const canMove = computed(() => auth.hasAction('endereco_movimentar'))

const tab = ref('estrutura')
const warehouseId = ref(null)
const warehouses = ref([])
const tree = ref([])
const selectedNode = ref(null)
const nodeContents = ref([])
const recon = ref([])
const scanCode = ref('')
const scanResult = ref(null)
const scanLabel = ref('')

const nodeModal = ref({ open: false })
const bulkModal = ref({ open: false, scheme: {} })
const allocModal = ref({ open: false, packs: [], defaults: [] })

function whParam() { return warehouseId.value ? { warehouse_id: warehouseId.value } : {} }

async function loadWarehouses() {
  try { const { data } = await api.get('/warehouse'); warehouses.value = data.items || data || [] } catch { /* ignore */ }
}
async function loadTree() {
  try {
    const { data } = await api.get('/storage/locations', { params: whParam() })
    tree.value = data.tree || []
    if (!warehouseId.value && data.warehouse_id) warehouseId.value = data.warehouse_id
  } catch (e) {
    if (e?.response?.status === 400) { await loadWarehouses() } // admin precisa escolher galpão
    else toast.error(e?.response?.data?.detail || 'Falha ao carregar a árvore.')
  }
}
async function reloadAll() { selectedNode.value = null; nodeContents.value = []; await loadTree() }

async function selectNode(node) {
  selectedNode.value = node
  nodeContents.value = []
  if (node.is_storable) {
    try { const { data } = await api.get(`/storage/locations/${node.id}/contents`); nodeContents.value = data.allocations || [] }
    catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao ler o conteúdo.') }
  }
}

// ── Nó ──
function openNodeModal(nodeOrParent, isEdit) {
  // chamado como add(parent), edit(node) — distinguimos pelo 2º arg
  if (isEdit) {
    const n = nodeOrParent
    nodeModal.value = { open: true, id: n.id, parent: null, level_type: n.level_type, code: n.code,
      area_kind: n.area_kind, is_storable: n.is_storable, pick_sequence: n.pick_sequence }
  } else {
    nodeModal.value = { open: true, id: null, parent: nodeOrParent || null, level_type: '', code: '',
      area_kind: null, is_storable: false, pick_sequence: 0 }
  }
}
async function saveNode() {
  const m = nodeModal.value
  if (!m.level_type || !m.code) { toast.warning('Preencha tipo de nível e identificação.'); return }
  try {
    if (m.id) {
      await api.patch(`/storage/locations/${m.id}`, { level_type: m.level_type, code: m.code, area_kind: m.area_kind, is_storable: m.is_storable, pick_sequence: m.pick_sequence })
    } else {
      const body = { level_type: m.level_type, code: m.code, area_kind: m.area_kind, is_storable: m.is_storable, pick_sequence: m.pick_sequence }
      if (m.parent) body.parent_id = m.parent.id; else Object.assign(body, whParam())
      await api.post('/storage/locations', body)
    }
    nodeModal.value.open = false
    await loadTree()
    toast.success('Endereço salvo.')
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao salvar.') }
}
async function removeNode(node) {
  if (!confirm(`Excluir o endereço ${node.full_code}?`)) return
  try { await api.delete(`/storage/locations/${node.id}`); await loadTree(); toast.success('Excluído.') }
  catch (e) { toast.error(e?.response?.data?.detail || 'Não foi possível excluir.') }
}

// ── Bulk ──
function openBulkModal(parent) {
  bulkModal.value = { open: true, parent: parent || null, level_type: '', is_storable: !parent ? false : true,
    scheme: { type: 'numeric', start: 1, end: 5, pad: 0 }, namesCsv: '' }
}
async function saveBulk() {
  const m = bulkModal.value
  if (!m.level_type) { toast.warning('Informe o tipo de nível.'); return }
  const scheme = { ...m.scheme }
  if (scheme.type === 'named') scheme.names = (m.namesCsv || '').split(',').map(s => s.trim()).filter(Boolean)
  try {
    const body = { level_type: m.level_type, scheme, is_storable: m.is_storable }
    if (m.parent) body.parent_id = m.parent.id; else Object.assign(body, whParam())
    const { data } = await api.post('/storage/locations/bulk', body)
    bulkModal.value.open = false
    await loadTree()
    toast.success(`Criados ${data.created.length}, pulados ${data.skipped.length}.`)
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha na geração.') }
}

// ── Alocação ──
async function openAllocModal(a) {
  if (a) {
    allocModal.value = { open: true, id: a.id, product: a.product ? { ...a.product } : null,
      qty_units: a.qty_units, pick_order: a.pick_order, lot_id: a.lot_id,
      packs: a.packs.map(p => ({ box_count: p.box_count, units_per_box: p.units_per_box, label: p.label })),
      defaults: [], product_type: a.product_type, product_id: a.product_id, scan: '', canInternal: a.product_type === 'pg' || a.product_type === 'cmig' }
  } else {
    allocModal.value = { open: true, id: null, product: null, qty_units: 0, pick_order: 0, lot_id: null, packs: [], defaults: [], scan: '', canInternal: false }
  }
}
async function resolveAllocProduct() {
  const code = (allocModal.value.scan || '').trim()
  if (!code) return
  try {
    const { data } = await api.get(`/storage/scan/${encodeURIComponent(code)}`)
    if (data.kind !== 'product') { toast.warning('Código não é de produto.'); return }
    const p = data.product
    allocModal.value.product = { sku: p.sku, title: p.title, main_ean: p.main_ean, is_traceable: p.is_traceable }
    allocModal.value.product_type = p.product_type
    allocModal.value.product_id = p.product_id
    allocModal.value.canInternal = p.product_type === 'pg' || p.product_type === 'cmig'
    allocModal.value.defaults = data.pack_defaults || []
  } catch (e) { toast.error(e?.response?.data?.detail || 'Produto não encontrado.') }
}
function addPack(upb, label) { allocModal.value.packs.push({ box_count: 0, units_per_box: upb || 0, label: label || '' }) }
async function genInternal() {
  const m = allocModal.value
  try {
    const { data } = await api.post(`/storage/products/${m.product_type}/${m.product_id}/internal-code`)
    m.product.main_ean = data.ean
    toast.success(`Código interno: ${data.ean}`)
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao gerar código.') }
}
async function saveAlloc() {
  const m = allocModal.value
  const packs = m.packs.filter(p => p.box_count > 0 && p.units_per_box > 0)
  try {
    if (m.id) {
      await api.patch(`/storage/allocations/${m.id}`, { qty_units: m.qty_units, pick_order: m.pick_order, packs })
    } else {
      await api.post('/storage/allocations', {
        location_id: selectedNode.value.id, product_type: m.product_type, product_id: m.product_id,
        lot_id: m.lot_id || null, qty_units: m.qty_units, pick_order: m.pick_order, packs,
      })
    }
    allocModal.value.open = false
    await selectNode(selectedNode.value)
    toast.success('Alocação salva.')
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao salvar alocação.') }
}
async function removeAlloc(a) {
  if (!confirm('Remover esta alocação?')) return
  try { await api.delete(`/storage/allocations/${a.id}`); await selectNode(selectedNode.value); toast.success('Removida.') }
  catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao remover.') }
}

// ── Reconciliação / Scan ──
async function loadReconciliation() {
  try { const { data } = await api.get('/storage/reconciliation', { params: whParam() }); recon.value = data.items || [] }
  catch (e) { if (e?.response?.status !== 400) toast.error(e?.response?.data?.detail || 'Falha na reconciliação.') }
}
async function doScan() {
  const code = (scanCode.value || '').trim()
  if (!code) return
  try {
    const { data } = await api.get(`/storage/scan/${encodeURIComponent(code)}`)
    scanLabel.value = { product: 'Produto', box: 'Caixa', location: 'Endereço' }[data.kind] || 'Resultado'
    scanResult.value = JSON.stringify(data, null, 2)
  } catch (e) { scanResult.value = null; toast.error(e?.response?.data?.detail || 'Nada encontrado.') }
}

// ── Etiquetas (impressão com QR/barcode via CDN, sem dep no bundle) ──
// SEGURANÇA: os campos (full_code/level_type/sku/título/token) são dados livres do usuário e vão
// para uma nova janela mesma-origem. Escapamos TUDO (texto e atributo) e anulamos `opener` — senão
// um `code` malicioso (ex.: <img onerror>) rodaria script com acesso ao localStorage (JWT). XSS→token.
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}
function printLabels(title, items) {
  const w = window.open('', '_blank')
  if (!w) { toast.warning('Permita pop-ups para imprimir etiquetas.'); return }
  try { w.opener = null } catch { /* ignore */ }
  const cards = items.map(it => `
    <div class="lbl">
      <div class="code">${esc(it.human)}</div>
      ${it.barcode ? `<svg class="bc" data-code="${esc(it.barcode)}"></svg>` : ''}
      ${it.qr ? `<div class="qr" data-code="${esc(it.qr)}"></div>` : ''}
      <div class="sub">${esc(it.sub)}</div>
    </div>`).join('')
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jsbarcode/3.11.6/JsBarcode.all.min.js"><\/script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"><\/script>
    <style>body{font-family:sans-serif}.lbl{display:inline-block;border:1px solid #000;padding:8px;margin:6px;text-align:center;width:220px}
    .code{font-weight:bold;font-size:14px;margin-bottom:4px}.sub{font-size:11px;margin-top:4px}.qr{display:flex;justify-content:center}</style>
    </head><body>${cards}
    <script>
      document.querySelectorAll('svg.bc').forEach(function(el){ try{ JSBarcode(el,el.dataset.code,{format:'EAN13',height:40,fontSize:12}); }catch(e){ JSBarcode(el,el.dataset.code,{height:40,fontSize:12}); } });
      document.querySelectorAll('.qr').forEach(function(el){ new QRCode(el,{text:el.dataset.code,width:90,height:90}); });
      setTimeout(function(){ window.print(); }, 500);
    <\/script></body></html>`)
  w.document.close()
}
async function printLocationLabel(node) {
  try {
    const { data } = await api.get(`/storage/locations/${node.id}/label`)
    printLabels('Etiqueta de endereço', [{ human: data.full_code, qr: data.qr, sub: data.level_type }])
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao gerar etiqueta.') }
}
async function printBoxLabels(a) {
  if (!confirm('Gerar etiquetas das caixas desta alocação?')) return
  try {
    const { data } = await api.post(`/storage/allocations/${a.id}/box-labels`)
    const sku = data.product?.sku || ''
    printLabels('Etiquetas de caixa', data.labels.map(l => ({
      human: sku, qr: l.token, sub: `${l.units_per_box} un/caixa`,
    })))
  } catch (e) { toast.error(e?.response?.data?.detail || 'Falha ao gerar etiquetas.') }
}

onMounted(async () => {
  if (isAdmin.value) await loadWarehouses()
  await loadTree()
})
</script>

<style scoped>
.btn-xs { padding: 0 .25rem; font-size: .75rem; }
.modal-backdrop-custom { position: fixed; inset: 0; background: rgba(0,0,0,.5); display:flex; align-items:center; justify-content:center; z-index: 1050; }
.modal-card { background:#fff; border-radius:6px; padding:18px; width: 480px; max-width: 94vw; max-height: 92vh; overflow:auto; }
</style>
