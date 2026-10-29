<template>
  <div class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-link mr-2"></i>Sincronizar produtos da nota
            <span v-if="data" class="text-muted">— NF {{ data.items.length }} item(ns)</span>
          </h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <div v-if="loading" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>
          <div v-else-if="data">
            <p class="text-muted small">
              Itens da nota que não casam com nenhum produto cadastrado (pelo EAN) precisam ser
              <strong>vinculados a um produto</strong> (adicionando o EAN da nota) ou um
              <strong>produto novo</strong> deve ser criado. Depois, contabilize o estoque.
            </p>
            <table class="table table-sm">
              <thead><tr><th>Produto da nota</th><th>EAN</th><th class="text-right">Qtd</th><th>Status</th></tr></thead>
              <tbody>
                <template v-for="it in data.items" :key="it.item_id">
                  <tr>
                    <td>{{ it.description }}</td>
                    <td><code class="small">{{ it.ean || '—' }}</code></td>
                    <td class="text-right">{{ it.quantity }}</td>
                    <td>
                      <span v-if="it.matched" class="badge badge-success">
                        <i class="fas fa-check mr-1"></i>{{ it.matched_product.sku }}
                      </span>
                      <button v-else class="btn btn-sm btn-outline-warning" @click="toggle(it.item_id)">
                        <i class="fas fa-exclamation-triangle mr-1"></i>Resolver
                      </button>
                    </td>
                  </tr>
                  <tr v-if="active === it.item_id && !it.matched">
                    <td colspan="4" class="bg-light">
                      <ul class="nav nav-pills nav-sm mb-2">
                        <li class="nav-item"><a class="nav-link" :class="{active: mode==='link'}" href="#" @click.prevent="mode='link'">Vincular a existente</a></li>
                        <li class="nav-item"><a class="nav-link" :class="{active: mode==='create'}" href="#" @click.prevent="mode='create'">Criar produto novo</a></li>
                      </ul>
                      <div class="form-inline mb-2">
                        <label class="small mr-2">Tipo:</label>
                        <select v-model="target" class="form-control form-control-sm">
                          <option value="cmig">Produto CMIG</option>
                          <option value="pg">Produto Geral (PG)</option>
                        </select>
                      </div>

                      <!-- Vincular a existente -->
                      <div v-if="mode==='link'">
                        <div class="input-group input-group-sm mb-2">
                          <input v-model="q" class="form-control" placeholder="Buscar produto por nome ou SKU..."
                                 @keyup.enter="search">
                          <div class="input-group-append"><button class="btn btn-outline-secondary" @click="search"><i class="fas fa-search"></i></button></div>
                        </div>
                        <div v-if="searching" class="text-center py-2"><i class="fas fa-spinner fa-spin"></i></div>
                        <table v-else-if="results.length" class="table table-sm table-hover mb-2">
                          <tbody>
                            <tr v-for="p in results" :key="p._id" :class="{'table-primary': sel && sel._id===p._id}"
                                style="cursor:pointer" @click="sel=p">
                              <td><strong>{{ p._sku }}</strong> — {{ p._title }}</td>
                              <td><code class="small">{{ p._ean || 's/ EAN' }}</code></td>
                              <td class="text-right">est: {{ p._stock }}</td>
                            </tr>
                          </tbody>
                        </table>
                        <div v-else-if="searched" class="text-muted small mb-2">Nenhum produto encontrado.</div>
                        <div v-if="sel" class="border rounded p-2 mb-2">
                          <div class="small mb-1">Selecionado: <strong>{{ sel._sku }}</strong> — {{ sel._title }}
                            (EAN atual: <code>{{ sel._ean || 's/ EAN' }}</code>)</div>
                          <div class="form-check">
                            <input id="ea-add" class="form-check-input" type="radio" value="add" v-model="eanAction">
                            <label for="ea-add" class="form-check-label">Adicionar o EAN da nota (<code>{{ it.ean }}</code>) ao produto <em>(recomendado)</em></label>
                          </div>
                          <div class="form-check">
                            <input id="ea-repl" class="form-check-input" type="radio" value="replace_product" v-model="eanAction">
                            <label for="ea-repl" class="form-check-label">Substituir o EAN do produto pelo da nota</label>
                          </div>
                        </div>
                        <button class="btn btn-sm btn-primary" :disabled="!sel || busy" @click="doLink(it)">
                          <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-link'"></i> Vincular
                        </button>
                      </div>

                      <!-- Criar novo -->
                      <div v-else>
                        <div class="form-group mb-2">
                          <label class="small mb-1">Título</label>
                          <input v-model="newTitle" class="form-control form-control-sm">
                        </div>
                        <div class="form-group mb-2">
                          <label class="small mb-1">SKU (opcional)</label>
                          <input v-model="newSku" class="form-control form-control-sm" placeholder="gerado automaticamente se vazio">
                        </div>
                        <p class="small text-muted">EAN <code>{{ it.ean || '—' }}</code>, NCM, CEST e origem vêm da nota.</p>
                        <button class="btn btn-sm btn-success" :disabled="busy" @click="doCreate(it)">
                          <i class="fas" :class="busy ? 'fa-spinner fa-spin' : 'fa-plus'"></i> Criar e vincular
                        </button>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <span v-if="data" class="mr-auto small" :class="data.unmatched ? 'text-warning' : 'text-success'">
            {{ data.unmatched ? `${data.unmatched} item(ns) a sincronizar` : 'Todos os itens sincronizados' }}
          </span>
          <button class="btn btn-success btn-sm" :disabled="data && data.unmatched > 0 || contabilizando" @click="contabilizar">
            <i class="fas" :class="contabilizando ? 'fa-spinner fa-spin' : 'fa-boxes'"></i> Contabilizar estoque
          </button>
          <button class="btn btn-secondary btn-sm" @click="$emit('close')">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useFiscalStore } from '@/stores/fiscal'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const props = defineProps({ invoiceId: { type: Number, required: true } })
const emit = defineEmits(['close', 'done'])

const fiscalStore = useFiscalStore()
const toast = useToast()

const loading = ref(true)
const data = ref(null)
const active = ref(null)          // item_id com painel aberto
const mode = ref('link')          // link | create
const target = ref('cmig')        // cmig | pg
const q = ref(''); const results = ref([]); const searching = ref(false); const searched = ref(false)
const sel = ref(null)
const eanAction = ref('add')
const busy = ref(false)
const newTitle = ref(''); const newSku = ref('')
const contabilizando = ref(false)

function reportStock(prefix, stock) {
  // "falhar alto": não diz "contabilizado" se a contabilização falhou ou não casou.
  if (stock?.error) toast.warning(`${prefix}, mas a contabilização falhou — contabilize novamente.`)
  else if (stock?.no_match) toast.warning(`${prefix}, mas ainda há item sem produto casado.`)
  else if (stock?.cmig_recomputed || stock?.pg_recomputed) toast.success(`${prefix}. Estoque contabilizado.`)
  else toast.success(`${prefix}.`)
}

async function load() {
  loading.value = true
  try { data.value = await fiscalStore.stockMatch(props.invoiceId) }
  catch (e) { toast.error(e.response?.data?.detail || 'Erro ao carregar') }
  finally { loading.value = false }
}

function toggle(itemId) {
  active.value = active.value === itemId ? null : itemId
  // reset do painel ao abrir outro item
  mode.value = 'link'; sel.value = null; results.value = []; searched.value = false; q.value = ''; eanAction.value = 'add'
  const it = data.value?.items.find(i => i.item_id === itemId)
  newTitle.value = it?.description || ''; newSku.value = ''
}

async function search() {
  searching.value = true; searched.value = true; sel.value = null
  try {
    const cmigId = data.value.cmig_id
    const url = target.value === 'pg' ? `/cmigs/${cmigId}/pg-products` : `/cmigs/${cmigId}/products`
    const { data: rows } = await api.get(url, { params: { search: q.value, limit: 30 } })
    const arr = Array.isArray(rows) ? rows : (rows.items || [])
    results.value = arr.map(p => ({
      _id: p.id,
      _sku: p.sku_cmig || p.sku,
      _title: p.title,
      _ean: p.ean,
      _stock: p.stock_quantity,
    }))
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro na busca') }
  finally { searching.value = false }
}

async function doLink(it) {
  busy.value = true
  try {
    const r = await fiscalStore.linkItemProduct(props.invoiceId, it.item_id, {
      target: target.value, product_id: sel.value._id, ean_action: eanAction.value,
    })
    reportStock('Produto vinculado', r.stock)
    active.value = null
    await load()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao vincular') }
  finally { busy.value = false }
}

async function doCreate(it) {
  busy.value = true
  try {
    const r = await fiscalStore.createProductFromItem(props.invoiceId, it.item_id, {
      target: target.value, title: newTitle.value, sku: newSku.value || undefined,
    })
    reportStock('Produto criado e vinculado', r.stock)
    active.value = null
    await load()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao criar produto') }
  finally { busy.value = false }
}

async function contabilizar() {
  contabilizando.value = true
  try {
    const r = await fiscalStore.updateStock(props.invoiceId)
    if (r.no_match) toast.warning('Ainda há itens sem produto casado.')
    else if (r.already_updated) toast.info('Nota já contabilizada.')
    else toast.success('Estoque contabilizado.')
    emit('done')
    emit('close')
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao contabilizar') }
  finally { contabilizando.value = false }
}

onMounted(load)
</script>
