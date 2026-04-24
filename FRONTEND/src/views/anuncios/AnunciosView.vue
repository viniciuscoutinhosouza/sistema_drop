<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Gestão de Anúncios</h1>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Seletor de conta + ações -->
        <div class="card card-outline card-primary mb-3">
          <div class="card-body py-2">
            <div class="row align-items-center">
              <div class="col-md-5">
                <label class="mb-0 mr-2 text-muted"><small>Conta Marketplace:</small></label>
                <select v-model="selectedAccountId" class="form-control form-control-sm d-inline-block" style="width:auto;min-width:260px" @change="loadAnuncios">
                  <option value="">Selecione uma conta...</option>
                  <option v-for="a in accounts" :key="a.id" :value="a.id">
                    {{ a.platform_label }} — {{ a.description || a.platform_username || a.email }}
                    <template v-if="a.cmig_name"> ({{ a.cmig_name }})</template>
                  </option>
                </select>
              </div>
              <div class="col-md-4">
                <div class="btn-group btn-group-sm">
                  <button :class="['btn', filterVinculo === 'all' ? 'btn-primary' : 'btn-outline-primary']" @click="setFilter('all')">Todos</button>
                  <button :class="['btn', filterVinculo === 'unlinked' ? 'btn-warning' : 'btn-outline-warning']" @click="setFilter('unlinked')">
                    <i class="fas fa-exclamation-triangle mr-1"></i>Sem vínculo
                  </button>
                  <button :class="['btn', filterVinculo === 'linked' ? 'btn-success' : 'btn-outline-success']" @click="setFilter('linked')">
                    <i class="fas fa-check mr-1"></i>Vinculados
                  </button>
                </div>
              </div>
              <div class="col-md-3 text-right">
                <button class="btn btn-sm btn-info mr-2" @click="openPublishModal" :disabled="!selectedAccountId">
                  <i class="fas fa-plus mr-1"></i>Publicar Anúncio
                </button>
                <button class="btn btn-sm btn-secondary" @click="importAnuncios" :disabled="!selectedAccountId || importing">
                  <i :class="['fas', importing ? 'fa-spinner fa-spin' : 'fa-download', 'mr-1']"></i>Importar
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Tabela de anúncios -->
        <div class="card">
          <div class="card-body p-0">
            <div v-if="!selectedAccountId" class="text-center text-muted py-5">
              <i class="fas fa-plug fa-2x mb-2 d-block"></i>Selecione uma conta de marketplace acima.
            </div>
            <div v-else-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else-if="filteredAnuncios.length === 0" class="text-center text-muted py-5">
              <i class="fas fa-tag fa-2x mb-2 d-block"></i>
              Nenhum anúncio encontrado.
              <div class="mt-2">
                <button class="btn btn-sm btn-secondary mr-2" @click="importAnuncios" :disabled="importing">
                  <i class="fas fa-download mr-1"></i>Importar do Marketplace
                </button>
                <button class="btn btn-sm btn-success" @click="openEditModal(null)">
                  <i class="fas fa-plus mr-1"></i>Criar Manualmente
                </button>
              </div>
            </div>
            <table v-else class="table table-hover table-sm mb-0">
              <thead class="thead-light">
                <tr>
                  <th>ID Plataforma</th>
                  <th>Título</th>
                  <th>Preço</th>
                  <th>Produto Vinculado</th>
                  <th>Status</th>
                  <th class="text-center">Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="a in filteredAnuncios" :key="a.id" :class="{ 'table-warning': !a.is_linked }">
                  <td class="text-monospace small">{{ a.platform_item_id || '—' }}</td>
                  <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="a.title_override">
                    {{ a.title_override }}
                  </td>
                  <td class="text-nowrap">{{ formatCurrency(a.sale_price) }}</td>
                  <td>
                    <span v-if="a.cmig_product" class="badge badge-success">
                      <i class="fas fa-check mr-1"></i>{{ a.cmig_product.sku }} — {{ a.cmig_product.title }}
                    </span>
                    <span v-else-if="a.catalog_product" class="badge badge-info">
                      <i class="fas fa-check mr-1"></i>PG: {{ a.catalog_product.sku }} — {{ a.catalog_product.title }}
                    </span>
                    <span v-else class="badge badge-warning">
                      <i class="fas fa-exclamation-triangle mr-1"></i>Sem vínculo
                    </span>
                  </td>
                  <td>
                    <span :class="statusBadge(a.status)">{{ a.status }}</span>
                  </td>
                  <td class="text-center text-nowrap">
                    <button class="btn btn-xs btn-outline-primary mr-1" title="Vincular produto" @click="openLinkModal(a)">
                      <i class="fas fa-link"></i>
                    </button>
                    <button v-if="!a.is_linked" class="btn btn-xs btn-outline-secondary mr-1" title="Criar Produto CMIG" @click="openCreateCmigModal(a)">
                      <i class="fas fa-plus"></i>
                    </button>
                    <button v-if="a.is_linked" class="btn btn-xs btn-outline-danger mr-1" title="Remover vínculo" @click="unlinkAnuncio(a)">
                      <i class="fas fa-unlink"></i>
                    </button>
                    <button v-if="a.status === 'active' || a.status === 'published'" class="btn btn-xs btn-outline-warning mr-1" title="Pausar" @click="pauseAnuncio(a)">
                      <i class="fas fa-pause"></i>
                    </button>
                    <a v-if="a.platform_item_id && selectedAccountPlatform === 'mercadolivre'" :href="`https://www.mercadolivre.com.br/p/${a.platform_item_id}`" target="_blank" class="btn btn-xs btn-outline-info" title="Ver no ML">
                      <i class="fas fa-external-link-alt"></i>
                    </a>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>

    <!-- Modal: Resultado de Importação -->
    <div v-if="importResult" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-download mr-2"></i>Resultado da Importação</h5>
            <button type="button" class="close" @click="importResult = null"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <ul class="list-group list-group-flush">
              <li class="list-group-item d-flex justify-content-between">
                <span>Novos anúncios importados</span>
                <span class="badge badge-success badge-pill">{{ importResult.imported }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Atualizados</span>
                <span class="badge badge-info badge-pill">{{ importResult.updated }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Auto-vinculados</span>
                <span class="badge badge-primary badge-pill">{{ importResult.auto_matched }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Sem vínculo</span>
                <span class="badge badge-warning badge-pill">{{ importResult.unlinked }}</span>
              </li>
            </ul>
          </div>
          <div class="modal-footer">
            <button v-if="importResult.unlinked > 0" class="btn btn-warning btn-sm" @click="setFilter('unlinked'); importResult = null">
              Ver sem vínculo
            </button>
            <button class="btn btn-secondary" @click="importResult = null">Fechar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Vincular Produto -->
    <div v-if="linkModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-link mr-2"></i>Vincular Produto</h5>
            <button type="button" class="close" @click="linkModal.show = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p class="text-muted small mb-3">Anúncio: <strong>{{ linkModal.listing?.title_override }}</strong></p>
            <div class="input-group mb-3">
              <input v-model="linkSearch" class="form-control" placeholder="Buscar produto por nome ou SKU..." @input="loadSuggestions" />
              <div class="input-group-append">
                <button class="btn btn-outline-secondary" @click="loadSuggestions"><i class="fas fa-search"></i></button>
              </div>
            </div>

            <div v-if="linkModal.loading" class="text-center py-3"><i class="fas fa-spinner fa-spin text-muted"></i></div>
            <template v-else>
              <h6 class="text-uppercase text-muted small mb-2">Produtos CMIG</h6>
              <div v-if="linkModal.cmig_suggestions.length === 0" class="text-muted small mb-3">Nenhum produto CMIG encontrado.</div>
              <div v-for="p in linkModal.cmig_suggestions" :key="'c'+p.id" class="d-flex justify-content-between align-items-center border-bottom py-2">
                <div>
                  <strong>{{ p.sku }}</strong> — {{ p.title }}
                  <span class="badge badge-light ml-1">{{ Math.round(p.similarity * 100) }}%</span>
                </div>
                <button class="btn btn-sm btn-success" @click="doLink({ cmig_product_id: p.id })">Vincular</button>
              </div>

              <h6 class="text-uppercase text-muted small mb-2 mt-3">Produtos PG (Catálogo)</h6>
              <div v-if="linkModal.pg_suggestions.length === 0" class="text-muted small">Nenhum produto PG encontrado.</div>
              <div v-for="p in linkModal.pg_suggestions" :key="'p'+p.id" class="d-flex justify-content-between align-items-center border-bottom py-2">
                <div>
                  <strong>{{ p.sku }}</strong> — {{ p.title }}
                  <span class="badge badge-light ml-1">{{ Math.round(p.similarity * 100) }}%</span>
                </div>
                <button class="btn btn-sm btn-info" @click="doLink({ catalog_product_id: p.id })">Vincular</button>
              </div>
            </template>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="linkModal.show = false">Fechar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Criar Produto CMIG -->
    <div v-if="createCmigModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-plus mr-2"></i>Criar Produto CMIG</h5>
            <button type="button" class="close" @click="createCmigModal.show = false"><span>&times;</span></button>
          </div>
          <form @submit.prevent="doCreateCmigProduct">
            <div class="modal-body">
              <div v-if="createCmigModal.error" class="alert alert-danger">{{ createCmigModal.error }}</div>
              <p class="text-muted small mb-3">A partir do anúncio: <strong>{{ createCmigModal.listing?.title_override }}</strong></p>

              <div class="row">
                <div class="col-md-6 form-group">
                  <label>CMIG <span class="text-danger">*</span></label>
                  <select v-model="createCmigForm.cmig_id" class="form-control" required>
                    <option value="">Selecione...</option>
                    <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }} ({{ c.cnpj }})</option>
                  </select>
                </div>
                <div class="col-md-6 form-group">
                  <label>SKU CMIG <span class="text-danger">*</span></label>
                  <input v-model="createCmigForm.sku_cmig" class="form-control" required placeholder="Ex: SKU-001" />
                </div>
              </div>
              <div class="row">
                <div class="col-md-8 form-group">
                  <label>Título <span class="text-danger">*</span></label>
                  <input v-model="createCmigForm.title" class="form-control" required />
                </div>
                <div class="col-md-4 form-group">
                  <label>Marca</label>
                  <input v-model="createCmigForm.brand" class="form-control" />
                </div>
              </div>
              <div class="row">
                <div class="col-md-4 form-group">
                  <label>Custo (R$)</label>
                  <input v-model="createCmigForm.cost_price" type="number" step="0.01" class="form-control" />
                </div>
                <div class="col-md-4 form-group">
                  <label>NCM</label>
                  <input v-model="createCmigForm.ncm" class="form-control" maxlength="8" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Peso (kg)</label>
                  <input v-model="createCmigForm.weight_kg" type="number" step="0.001" class="form-control" />
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" @click="createCmigModal.show = false">Cancelar</button>
              <button type="submit" class="btn btn-primary" :disabled="createCmigModal.saving">
                <i v-if="createCmigModal.saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ createCmigModal.saving ? 'Criando...' : 'Criar e Vincular' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- Modal: Publicar Anúncio -->
    <div v-if="publishModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-bullhorn mr-2"></i>Publicar Anúncio</h5>
            <button type="button" class="close" @click="publishModal.show = false"><span>&times;</span></button>
          </div>
          <form @submit.prevent="doPublish">
            <div class="modal-body">
              <div v-if="publishModal.error" class="alert alert-danger">{{ publishModal.error }}</div>

              <div class="row">
                <div class="col-md-6 form-group">
                  <label>Tipo de produto</label>
                  <select v-model="publishForm.product_type" class="form-control">
                    <option value="cmig">Produto CMIG</option>
                    <option value="pg">Produto PG (Catálogo)</option>
                  </select>
                </div>
                <div class="col-md-6 form-group">
                  <label>Modo de publicação</label>
                  <select v-model="publishForm.mode" class="form-control">
                    <option value="create">Criar novo anúncio no marketplace</option>
                    <option value="link">Vincular a ID existente</option>
                  </select>
                </div>
              </div>

              <div class="form-group">
                <label>{{ publishForm.product_type === 'cmig' ? 'Produto CMIG' : 'Produto PG' }} <span class="text-danger">*</span></label>
                <select v-model="publishForm.product_id" class="form-control" required>
                  <option value="">Selecione...</option>
                  <option v-for="p in publishProductList" :key="p.id" :value="p.id">
                    {{ p.sku_cmig || p.sku }} — {{ p.title }}
                  </option>
                </select>
              </div>

              <div class="row">
                <div class="col-md-6 form-group">
                  <label>Preço de venda (R$) <span class="text-danger">*</span></label>
                  <input v-model="publishForm.sale_price" type="number" step="0.01" class="form-control" required />
                </div>
                <div class="col-md-6 form-group">
                  <label>Título customizado</label>
                  <input v-model="publishForm.title_override" class="form-control" placeholder="Deixe em branco para usar o título do produto" />
                </div>
              </div>

              <div v-if="publishForm.mode === 'create'" class="row">
                <div class="col-md-6 form-group">
                  <label>Categoria ML <span class="text-danger">*</span></label>
                  <input v-model="publishForm.category_id" class="form-control" placeholder="Ex: MLB1051" />
                </div>
                <div class="col-md-6 form-group">
                  <label>Tipo de anúncio</label>
                  <select v-model="publishForm.listing_type" class="form-control">
                    <option value="gold_special">Gold Special</option>
                    <option value="gold_pro">Gold Pro</option>
                    <option value="free">Grátis</option>
                  </select>
                </div>
              </div>

              <div v-if="publishForm.mode === 'link'" class="form-group">
                <label>ID do anúncio existente <span class="text-danger">*</span></label>
                <input v-model="publishForm.platform_item_id" class="form-control" placeholder="Ex: MLB12345678" required />
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" @click="publishModal.show = false">Cancelar</button>
              <button type="submit" class="btn btn-primary" :disabled="publishModal.saving">
                <i v-if="publishModal.saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ publishModal.saving ? 'Publicando...' : (publishForm.mode === 'create' ? 'Publicar no Marketplace' : 'Vincular Anúncio') }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const toast = useToast()

const accounts = ref([])
const selectedAccountId = ref('')
const anuncios = ref([])
const loading = ref(false)
const importing = ref(false)
const filterVinculo = ref('all')
const importResult = ref(null)
const cmigs = ref([])

const selectedAccount = computed(() => accounts.value.find(a => a.id === selectedAccountId.value))
const selectedAccountPlatform = computed(() => selectedAccount.value?.platform || '')

const filteredAnuncios = computed(() => {
  if (filterVinculo.value === 'linked') return anuncios.value.filter(a => a.is_linked)
  if (filterVinculo.value === 'unlinked') return anuncios.value.filter(a => !a.is_linked)
  return anuncios.value
})

// ── link modal ──
const linkModal = ref({ show: false, listing: null, loading: false, cmig_suggestions: [], pg_suggestions: [] })
const linkSearch = ref('')

// ── create cmig modal ──
const createCmigModal = ref({ show: false, listing: null, saving: false, error: '' })
const createCmigForm = ref({ cmig_id: '', sku_cmig: '', title: '', brand: '', cost_price: '', ncm: '', weight_kg: '' })

// ── publish modal ──
const publishModal = ref({ show: false, saving: false, error: '' })
const publishForm = ref({ product_type: 'cmig', mode: 'create', product_id: '', sale_price: '', title_override: '', category_id: '', listing_type: 'gold_special', platform_item_id: '' })
const cmigProducts = ref([])
const pgProducts = ref([])

const publishProductList = computed(() => {
  return publishForm.value.product_type === 'cmig' ? cmigProducts.value : pgProducts.value
})

onMounted(async () => {
  await Promise.all([loadAccounts(), loadCmigs()])
})

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    const platformLabel = p => ({ mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[p] || p)
    accounts.value = (Array.isArray(data) ? data : []).map(a => ({
      ...a,
      platform_label: platformLabel(a.platform),
    }))
  } catch { }
}

async function loadCmigs() {
  try {
    const { data } = await api.get('/cmigs')
    cmigs.value = Array.isArray(data) ? data : []
  } catch { }
}

async function loadAnuncios() {
  if (!selectedAccountId.value) { anuncios.value = []; return }
  loading.value = true
  try {
    const { data } = await api.get(`/anuncios?account_id=${selectedAccountId.value}`)
    anuncios.value = Array.isArray(data) ? data : []
  } catch {
    toast.error('Erro ao carregar anúncios')
  } finally {
    loading.value = false
  }
}

async function importAnuncios() {
  if (!selectedAccountId.value) return
  importing.value = true
  try {
    const { data } = await api.post(`/anuncios/import/${selectedAccountId.value}`)
    importResult.value = data
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao importar anúncios')
  } finally {
    importing.value = false
  }
}

function setFilter(f) {
  filterVinculo.value = f
}

// ── Link Modal ──

async function openLinkModal(listing) {
  linkModal.value = { show: true, listing, loading: true, cmig_suggestions: [], pg_suggestions: [] }
  linkSearch.value = ''
  await loadSuggestions()
}

async function loadSuggestions() {
  if (!linkModal.value.listing) return
  linkModal.value.loading = true
  try {
    const { data } = await api.get(`/anuncios/${linkModal.value.listing.id}/suggest`)
    let cmigSugg = data.cmig_suggestions || []
    let pgSugg = data.pg_suggestions || []
    if (linkSearch.value) {
      const q = linkSearch.value.toLowerCase()
      const matches = p => p.title.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)
      cmigSugg = cmigSugg.filter(matches)
      pgSugg = pgSugg.filter(matches)
    }
    linkModal.value.cmig_suggestions = cmigSugg
    linkModal.value.pg_suggestions = pgSugg
  } catch {
    toast.error('Erro ao buscar sugestões')
  } finally {
    linkModal.value.loading = false
  }
}

async function doLink(payload) {
  try {
    await api.post(`/anuncios/${linkModal.value.listing.id}/link`, payload)
    toast.success('Produto vinculado com sucesso!')
    linkModal.value.show = false
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao vincular produto')
  }
}

async function unlinkAnuncio(listing) {
  if (!confirm('Remover vínculo deste anúncio?')) return
  try {
    await api.post(`/anuncios/${listing.id}/unlink`)
    toast.success('Vínculo removido')
    await loadAnuncios()
  } catch {
    toast.error('Erro ao remover vínculo')
  }
}

// ── Create CMIG Product Modal ──

function openCreateCmigModal(listing) {
  createCmigModal.value = { show: true, listing, saving: false, error: '' }
  createCmigForm.value = {
    cmig_id: selectedAccount.value?.cmig_id || '',
    sku_cmig: '',
    title: listing.title_override || '',
    brand: '',
    cost_price: '',
    ncm: '',
    weight_kg: '',
  }
}

async function doCreateCmigProduct() {
  createCmigModal.value.saving = true
  createCmigModal.value.error = ''
  try {
    await api.post(`/anuncios/${createCmigModal.value.listing.id}/create-cmig-product`, {
      ...createCmigForm.value,
      cost_price: createCmigForm.value.cost_price ? parseFloat(createCmigForm.value.cost_price) : null,
      weight_kg: createCmigForm.value.weight_kg ? parseFloat(createCmigForm.value.weight_kg) : null,
    })
    toast.success('Produto CMIG criado e vinculado!')
    createCmigModal.value.show = false
    await loadAnuncios()
  } catch (e) {
    createCmigModal.value.error = e.response?.data?.detail || 'Erro ao criar produto'
  } finally {
    createCmigModal.value.saving = false
  }
}

// ── Publish Modal ──

async function openPublishModal() {
  publishModal.value = { show: true, saving: false, error: '' }
  publishForm.value = {
    product_type: 'cmig', mode: 'create', product_id: '',
    sale_price: '', title_override: '', category_id: '',
    listing_type: 'gold_special', platform_item_id: '',
  }
  await Promise.all([loadCmigProducts(), loadPgProducts()])
}

async function loadCmigProducts() {
  try {
    const { data } = await api.get('/cmig-products')
    cmigProducts.value = Array.isArray(data) ? data : []
  } catch { }
}

async function loadPgProducts() {
  try {
    const { data } = await api.get('/catalog')
    pgProducts.value = Array.isArray(data?.items || data) ? (data?.items || data) : []
  } catch { }
}

async function doPublish() {
  publishModal.value.saving = true
  publishModal.value.error = ''
  try {
    const payload = {
      account_id: selectedAccountId.value,
      sale_price: parseFloat(publishForm.value.sale_price),
      title_override: publishForm.value.title_override || null,
      mode: publishForm.value.mode,
      listing_type: publishForm.value.listing_type,
      category_id: publishForm.value.category_id || null,
      platform_item_id: publishForm.value.platform_item_id || null,
    }
    if (publishForm.value.product_type === 'cmig') {
      payload.cmig_product_id = publishForm.value.product_id
    } else {
      payload.catalog_product_id = publishForm.value.product_id
    }
    await api.post('/anuncios/publish', payload)
    toast.success('Anúncio publicado com sucesso!')
    publishModal.value.show = false
    await loadAnuncios()
  } catch (e) {
    publishModal.value.error = e.response?.data?.detail || 'Erro ao publicar anúncio'
  } finally {
    publishModal.value.saving = false
  }
}

async function pauseAnuncio(listing) {
  if (!confirm(`Pausar o anúncio "${listing.title_override}"?`)) return
  try {
    await api.post(`/anuncios/${listing.id}/pause`)
    toast.success('Anúncio pausado')
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao pausar anúncio')
  }
}

function formatCurrency(v) {
  if (!v) return '—'
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function statusBadge(s) {
  return {
    active: 'badge badge-success', published: 'badge badge-success',
    paused: 'badge badge-warning', draft: 'badge badge-secondary',
    closed: 'badge badge-danger',
  }[s] || 'badge badge-secondary'
}
</script>
