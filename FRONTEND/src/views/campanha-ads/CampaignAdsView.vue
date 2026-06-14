<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency } from '@/utils/formatters'
import { useCampaignAds, derive, num, isoDate } from '@/composables/useCampaignAds'
import AdRaioXModal from '@/components/campanha-ads/AdRaioXModal.vue'
import CampaignDetailModal from '@/components/campanha-ads/CampaignDetailModal.vue'

const toast = useToast()
const { loadAdvertisers, loadCampaigns, loadAds, loadAdGroups } = useCampaignAds()

// ── Filtros ────────────────────────────────────────────────────────────────
const cmigs = ref([])
const cmigId = ref(null)
const advertisers = ref([])
const advertiserKey = ref(null) // `${account_id}:${advertiser_id}`
const loadingAdvertisers = ref(false)

const today = new Date()
const start = new Date()
start.setDate(today.getDate() - 29)
const filters = reactive({
  date_from: isoDate(start),
  date_to: isoDate(today),
  status: '',
  campaign_id: '',
})
// Catálogo/UP
const catFilters = reactive({ q: '', ad_group_id: '', item_id: '' })

const activeTab = ref('product') // product | catalog
const productSubTab = ref('campaigns') // campaigns | ads

const selectedAdvertiser = computed(() =>
  advertisers.value.find((a) => `${a.account_id}:${a.advertiser_id}` === advertiserKey.value),
)

// ── Dados ────────────────────────────────────────────────────────────────────
const loading = ref(false)
const campaigns = ref([])
const campaignsSummary = ref({})
const expandedCampaign = ref(null)

const ads = ref([])
const adsSummary = ref({})
const adsPaging = reactive({ total: 0, offset: 0, limit: 50 })

const adGroups = ref([])
const adGroupsSummary = ref({})

// ── Carregamento inicial ─────────────────────────────────────────────────────
async function fetchCmigs() {
  try {
    const { data } = await api.get('/cmigs')
    cmigs.value = data || []
    if (cmigs.value.length === 1) {
      cmigId.value = cmigs.value[0].id
      await onCmigChange()
    }
  } catch (e) {
    toast.error('Falha ao carregar CMIGs.')
  }
}

async function onCmigChange() {
  advertisers.value = []
  advertiserKey.value = null
  if (!cmigId.value) return
  loadingAdvertisers.value = true
  try {
    advertisers.value = await loadAdvertisers(cmigId.value)
    if (advertisers.value.length) {
      const a = advertisers.value[0]
      advertiserKey.value = `${a.account_id}:${a.advertiser_id}`
    } else {
      toast.warning('Nenhum anunciante de Product Ads encontrado nas contas ML desta CMIG.')
    }
  } catch (e) {
    toast.error('Falha ao carregar anunciantes.')
  } finally {
    loadingAdvertisers.value = false
  }
}

function baseParams() {
  const adv = selectedAdvertiser.value
  if (!adv) return {}
  return {
    account_id: adv.account_id,
    advertiser_id: adv.advertiser_id,
    site_id: adv.site_id || 'MLB',
    date_from: filters.date_from,
    date_to: filters.date_to,
  }
}

async function applyFilters() {
  if (!selectedAdvertiser.value) {
    toast.warning('Selecione uma CMIG e um anunciante.')
    return
  }
  loading.value = true
  try {
    if (activeTab.value === 'product') {
      if (productSubTab.value === 'campaigns') await fetchCampaigns()
      else await fetchAds()
    } else {
      await fetchAdGroups()
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Falha ao consultar a API de ADS do ML.')
  } finally {
    loading.value = false
  }
}

async function fetchCampaigns() {
  const params = { ...baseParams() }
  if (filters.status) params.status = filters.status
  if (filters.campaign_id) params.campaign_id = filters.campaign_id
  const data = await loadCampaigns(params)
  campaigns.value = data.results || []
  campaignsSummary.value = data.metrics_summary || {}
  expandedCampaign.value = null
}

async function fetchAds(offset = 0) {
  const params = { ...baseParams(), limit: adsPaging.limit, offset }
  if (filters.status) params.statuses = filters.status
  if (filters.campaign_id) params.campaign_id = filters.campaign_id
  const data = await loadAds(params)
  ads.value = data.results || []
  adsSummary.value = data.metrics_summary || {}
  Object.assign(adsPaging, { total: data.paging?.total || 0, offset: data.paging?.offset || offset })
}

async function fetchAdGroups() {
  const params = { ...baseParams() }
  if (filters.status) params.statuses = filters.status
  if (catFilters.q) params.q = catFilters.q
  if (catFilters.ad_group_id) params.ad_group_id = catFilters.ad_group_id
  const data = await loadAdGroups(params)
  adGroups.value = data.results || []
  adGroupsSummary.value = data.metrics_summary || {}
}

function switchTab(tab) {
  activeTab.value = tab
  if (selectedAdvertiser.value) applyFilters()
}
function switchSubTab(sub) {
  productSubTab.value = sub
  if (selectedAdvertiser.value) applyFilters()
}

// ── Derivadas / totalizadores ──────────────────────────────────────────────
const globalProduct = computed(() => derive(campaignsSummary.value || {}))
const globalAds = computed(() => derive(adsSummary.value || {}))
const globalGroups = computed(() => derive(adGroupsSummary.value || {}))

const activeGroupsCount = computed(
  () => adGroups.value.filter((g) => (g.status || '').toUpperCase() === 'ACTIVE').length,
)
const totalAdsInGroups = computed(() =>
  adGroups.value.reduce((s, g) => s + num(g.advertising_items_quantity), 0),
)

// Insights automáticos (PRODUCT — campanhas)
const insights = computed(() => {
  const rows = campaigns.value.map((c) => ({ name: c.name, d: derive(c.metrics || {}, c) }))
  if (!rows.length) return null
  const bestRoas = [...rows].sort((a, b) => b.d.roas - a.d.roas)[0]
  const belowRoas = rows.filter((r) => r.d.roasOk === false).length
  const acosOk = rows.filter((r) => r.d.acosOk === true).length
  const bestAcos = [...rows].filter((r) => r.d.acos > 0).sort((a, b) => a.d.acos - b.d.acos)[0]
  const g = globalProduct.value
  const orgUnits = rows.reduce((s, r) => s + r.d.organicUnits, 0)
  const orgAmount = rows.reduce((s, r) => s + r.d.organicAmount, 0)
  const paidUnits = g.units
  const ticket = paidUnits > 0 ? g.revenue / paidUnits : 0
  return {
    bestRoas,
    belowRoas,
    acosOk,
    totalCamps: rows.length,
    bestAcos,
    orgUnits,
    orgAmount,
    paidUnits,
    paidAmount: g.revenue,
    ticket,
    cpa: g.cpa,
  }
})

// ── Formatadores ─────────────────────────────────────────────────────────────
const money = (v) => formatCurrency(num(v))
const intf = (v) => num(v).toLocaleString('pt-BR')
const pct = (v) => `${num(v).toFixed(2)}%`
const roasf = (v) => `${num(v).toFixed(2)}x`

function statusBadge(s) {
  const v = (s || '').toLowerCase()
  if (v === 'active') return { cls: 'badge-success', txt: 'Ativa' }
  if (v === 'paused') return { cls: 'badge-warning', txt: 'Pausada' }
  if (v === 'hold') return { cls: 'badge-danger', txt: 'Suspenso' }
  if (v === 'idle') return { cls: 'badge-secondary', txt: 'Ocioso' }
  return { cls: 'badge-secondary', txt: s || '—' }
}

function toggleCampaign(id) {
  expandedCampaign.value = expandedCampaign.value === id ? null : id
}

const adsPage = computed(() => Math.floor(adsPaging.offset / adsPaging.limit) + 1)
const adsPages = computed(() => Math.max(1, Math.ceil(adsPaging.total / adsPaging.limit)))

// ── Modais: Raio-X do anúncio / Detalhe da campanha ──────────────────────────
const raioXAd = ref(null)
const detailCampaign = ref(null)

function openRaioX(ad) {
  raioXAd.value = ad
}
function openCampaignDetail(c) {
  detailCampaign.value = c
}

onMounted(fetchCmigs)
</script>

<template>
  <div class="campaign-ads">
    <!-- Cabeçalho -->
    <div class="card card-outline card-primary">
      <div class="card-header d-flex align-items-center flex-wrap">
        <h3 class="card-title mb-0">
          <i class="fas fa-bullhorn mr-2"></i>Campanhas ADS
        </h3>
        <span class="ml-3 text-muted small" v-if="activeTab === 'product'">
          <i class="fas fa-box mr-1"></i>Product Ads — anúncios patrocinados
          <span v-if="campaigns.length"> · {{ campaigns.length }} campanhas</span>
        </span>
        <span class="ml-3 text-muted small" v-else>
          <i class="fas fa-book mr-1"></i>Catálogo &amp; Variações — grupos de famílias
          <span v-if="adGroups.length"> · {{ adGroups.length }} grupos</span>
        </span>
        <span class="ml-auto badge badge-info" v-if="selectedAdvertiser">
          {{ selectedAdvertiser.advertiser_name }} · {{ selectedAdvertiser.advertiser_id }}
        </span>
      </div>

      <!-- Abas principais -->
      <div class="card-body pb-0">
        <ul class="nav nav-tabs">
          <li class="nav-item">
            <a class="nav-link" :class="{ active: activeTab === 'product' }" href="#"
              @click.prevent="switchTab('product')"><i class="fas fa-box mr-1"></i>Product</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" :class="{ active: activeTab === 'catalog' }" href="#"
              @click.prevent="switchTab('catalog')"><i class="fas fa-book mr-1"></i>Catálogo/UP</a>
          </li>
        </ul>
      </div>

      <!-- Filtros -->
      <div class="card-body">
        <div class="form-row align-items-end">
          <div class="form-group col-md-3">
            <label class="small mb-1">CMIG</label>
            <select class="form-control form-control-sm" v-model="cmigId" @change="onCmigChange">
              <option :value="null">Selecione…</option>
              <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name || c.trade_name || ('CMIG ' + c.id) }}</option>
            </select>
          </div>
          <div class="form-group col-md-3">
            <label class="small mb-1">Anunciante</label>
            <select class="form-control form-control-sm" v-model="advertiserKey" :disabled="loadingAdvertisers || !advertisers.length">
              <option :value="null">{{ loadingAdvertisers ? 'Carregando…' : 'Selecione…' }}</option>
              <option v-for="a in advertisers" :key="`${a.account_id}:${a.advertiser_id}`" :value="`${a.account_id}:${a.advertiser_id}`">
                {{ a.advertiser_name }} ({{ a.account_description }})
              </option>
            </select>
          </div>
          <div class="form-group col-md-2">
            <label class="small mb-1">De</label>
            <input type="date" class="form-control form-control-sm" v-model="filters.date_from" />
          </div>
          <div class="form-group col-md-2">
            <label class="small mb-1">Até</label>
            <input type="date" class="form-control form-control-sm" v-model="filters.date_to" />
          </div>
          <div class="form-group col-md-2">
            <label class="small mb-1">Status</label>
            <select class="form-control form-control-sm" v-model="filters.status">
              <option value="">Todos</option>
              <option value="active">Ativo</option>
              <option value="paused">Pausado</option>
            </select>
          </div>
        </div>
        <div class="form-row align-items-end" v-if="activeTab === 'catalog'">
          <div class="form-group col-md-3">
            <label class="small mb-1">Buscar (nome)</label>
            <input class="form-control form-control-sm" v-model="catFilters.q" placeholder="nome do produto" />
          </div>
          <div class="form-group col-md-3">
            <label class="small mb-1">ID do Ad Group</label>
            <input class="form-control form-control-sm" v-model="catFilters.ad_group_id" />
          </div>
        </div>
        <div class="text-right">
          <small class="text-muted mr-2">Intervalo máx. 90 dias (limite ML)</small>
          <button class="btn btn-sm btn-primary" :disabled="loading || !selectedAdvertiser" @click="applyFilters">
            <i class="fas fa-filter mr-1"></i>Filtrar
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="text-center text-muted py-5">
      <i class="fas fa-spinner fa-spin fa-2x"></i>
      <p class="mt-2">Consultando Mercado Ads…</p>
    </div>

    <template v-else-if="selectedAdvertiser">
      <!-- ════════════ PRODUCT ════════════ -->
      <template v-if="activeTab === 'product'">
        <ul class="nav nav-pills mb-3">
          <li class="nav-item">
            <a class="nav-link" :class="{ active: productSubTab === 'campaigns' }" href="#"
              @click.prevent="switchSubTab('campaigns')">Filtrar Campanhas</a>
          </li>
          <li class="nav-item">
            <a class="nav-link" :class="{ active: productSubTab === 'ads' }" href="#"
              @click.prevent="switchSubTab('ads')">Filtrar Anúncios</a>
          </li>
        </ul>

        <!-- ── Campanhas ── -->
        <template v-if="productSubTab === 'campaigns'">
          <!-- Cards globais -->
          <div class="row">
            <div class="col-6 col-md-3 col-xl mb-3">
              <div class="info-box"><span class="info-box-icon bg-success"><i class="fas fa-coins"></i></span>
                <div class="info-box-content"><span class="info-box-text">RECEITA</span>
                  <span class="info-box-number">{{ money(globalProduct.revenue) }}</span>
                  <span class="text-muted small">{{ money(globalProduct.revenuePerClick) }}/clique</span></div></div>
            </div>
            <div class="col-6 col-md-3 col-xl mb-3">
              <div class="info-box"><span class="info-box-icon bg-danger"><i class="fas fa-money-bill"></i></span>
                <div class="info-box-content"><span class="info-box-text">CUSTO</span>
                  <span class="info-box-number">{{ money(globalProduct.cost) }}</span>
                  <span class="text-muted small">CPC {{ money(globalProduct.cpc) }} · {{ pct(globalProduct.costPct) }}</span></div></div>
            </div>
            <div class="col-6 col-md-3 col-xl mb-3">
              <div class="info-box"><span class="info-box-icon" :class="globalProduct.profit >= 0 ? 'bg-primary' : 'bg-danger'"><i class="fas fa-chart-line"></i></span>
                <div class="info-box-content"><span class="info-box-text">LUCRO</span>
                  <span class="info-box-number">{{ money(globalProduct.profit) }}</span>
                  <span class="text-muted small">{{ pct(globalProduct.margin) }} margem · {{ intf(globalProduct.units) }} un.</span></div></div>
            </div>
            <div class="col-6 col-md-3 col-xl mb-3">
              <div class="info-box"><span class="info-box-icon bg-info"><i class="fas fa-eye"></i></span>
                <div class="info-box-content"><span class="info-box-text">IMPRESSÕES</span>
                  <span class="info-box-number">{{ intf(globalProduct.prints) }}</span>
                  <span class="text-muted small">CLIQUES {{ intf(globalProduct.clicks) }} · CTR {{ pct(globalProduct.ctr) }}</span></div></div>
            </div>
            <div class="col-6 col-md-3 col-xl mb-3">
              <div class="info-box"><span class="info-box-icon bg-secondary"><i class="fas fa-bullseye"></i></span>
                <div class="info-box-content"><span class="info-box-text">ROAS / ACOS</span>
                  <span class="info-box-number">{{ roasf(globalProduct.roas) }}</span>
                  <span class="text-muted small">ACOS {{ pct(globalProduct.acos) }} · SOV {{ pct(globalProduct.sov) }}</span></div></div>
            </div>
          </div>

          <!-- Insights -->
          <div class="card bg-light" v-if="insights">
            <div class="card-body py-2">
              <h6 class="text-warning mb-2"><i class="fas fa-bolt mr-1"></i>Insights Automáticos</h6>
              <div class="row">
                <div class="col-md-3"><strong>ROAS</strong><br>
                  <span class="small">Melhor: {{ insights.bestRoas.name }} ({{ roasf(insights.bestRoas.d.roas) }}).
                  <span v-if="insights.belowRoas" class="text-danger">{{ insights.belowRoas }} abaixo da meta.</span>
                  <span v-else class="text-success">Todas na meta.</span></span></div>
                <div class="col-md-3"><strong>ACOS</strong><br>
                  <span class="small">{{ insights.acosOk }}/{{ insights.totalCamps }} dentro da meta.
                  <span v-if="insights.bestAcos">Melhor: {{ insights.bestAcos.name }} ({{ pct(insights.bestAcos.d.acos) }}).</span></span></div>
                <div class="col-md-3"><strong>Orgânico vs Pago</strong><br>
                  <span class="small">Org.: {{ intf(insights.orgUnits) }} un. ({{ money(insights.orgAmount) }}).
                  Pago: {{ intf(insights.paidUnits) }} un. ({{ money(insights.paidAmount) }}).</span></div>
                <div class="col-md-3"><strong>Ticket Médio</strong><br>
                  <span class="small">{{ money(insights.ticket) }} por venda · CPA {{ money(insights.cpa) }}.</span></div>
              </div>
            </div>
          </div>

          <!-- Lista de campanhas -->
          <div class="card">
            <div class="card-header"><strong>EXIBINDO {{ campaigns.length }} CAMPANHAS</strong></div>
            <div class="card-body p-0">
              <div v-if="!campaigns.length" class="text-center text-muted py-4">Nenhuma campanha no período.</div>
              <table v-else class="table table-sm table-hover mb-0">
                <thead>
                  <tr><th></th><th>Campanha</th><th class="text-right">ROAS</th><th class="text-right">ACOS</th>
                  <th class="text-right">Receita</th><th class="text-right">Custo</th><th class="text-right">Lucro</th></tr>
                </thead>
                <tbody v-for="c in campaigns" :key="c.id">
                  <tr style="cursor:pointer" @click="toggleCampaign(c.id)">
                    <td><i class="fas" :class="expandedCampaign === c.id ? 'fa-eye-slash' : 'fa-eye'"></i></td>
                    <td>{{ c.name }}
                      <span class="badge ml-1" :class="statusBadge(c.status).cls">{{ statusBadge(c.status).txt }}</span>
                      <span class="text-muted small ml-1">{{ c.strategy }} · ID {{ c.id }}</span></td>
                    <td class="text-right" :class="derive(c.metrics||{}, c).roasOk === false ? 'text-danger' : 'text-success'">{{ roasf(derive(c.metrics||{}).roas) }}</td>
                    <td class="text-right" :class="derive(c.metrics||{}, c).acosOk === false ? 'text-danger' : 'text-success'">{{ pct(derive(c.metrics||{}).acos) }}</td>
                    <td class="text-right">{{ money(derive(c.metrics||{}).revenue) }}</td>
                    <td class="text-right">{{ money(derive(c.metrics||{}).cost) }}</td>
                    <td class="text-right">{{ money(derive(c.metrics||{}).profit) }}</td>
                  </tr>
                  <tr v-if="expandedCampaign === c.id">
                    <td colspan="7" class="bg-light">
                      <div class="text-right mb-2">
                        <button class="btn btn-xs btn-outline-primary" @click.stop="openCampaignDetail(c)">
                          <i class="fas fa-chart-line mr-1"></i>Detalhe completo
                        </button>
                      </div>
                      <div class="row text-center small">
                        <div class="col"><div class="text-muted">UN. VENDIDAS</div><strong>{{ intf(derive(c.metrics||{}).units) }}</strong><br>CPA {{ money(derive(c.metrics||{}).cpa) }}</div>
                        <div class="col"><div class="text-muted">IMPRESSÕES</div><strong>{{ intf(derive(c.metrics||{}).prints) }}</strong></div>
                        <div class="col"><div class="text-muted">CLIQUES</div><strong>{{ intf(derive(c.metrics||{}).clicks) }}</strong><br>CTR {{ pct(derive(c.metrics||{}).ctr) }}</div>
                        <div class="col"><div class="text-muted">CPC</div><strong>{{ money(derive(c.metrics||{}).cpc) }}</strong></div>
                        <div class="col"><div class="text-muted">SOV</div><strong>{{ pct(derive(c.metrics||{}).sov) }}</strong></div>
                        <div class="col"><div class="text-muted">CVR</div><strong>{{ pct(derive(c.metrics||{}).cvr) }}</strong></div>
                      </div>
                      <div class="mt-2" v-if="c.roas_target || c.acos_target">
                        <div class="small text-muted">Metas de Performance</div>
                        <div v-if="c.roas_target" class="d-flex align-items-center">
                          <span class="small mr-2" style="width:50px">ROAS</span>
                          <div class="progress flex-grow-1" style="height:10px">
                            <div class="progress-bar bg-success" :style="{width: Math.min(100, (derive(c.metrics||{}).roas / c.roas_target)*100) + '%'}"></div>
                          </div>
                          <span class="small ml-2">{{ roasf(derive(c.metrics||{}).roas) }} / {{ roasf(c.roas_target) }}</span>
                        </div>
                        <div v-if="c.acos_target" class="d-flex align-items-center mt-1">
                          <span class="small mr-2" style="width:50px">ACOS</span>
                          <div class="progress flex-grow-1" style="height:10px">
                            <div class="progress-bar bg-info" :style="{width: Math.min(100, (derive(c.metrics||{}).acos / c.acos_target)*100) + '%'}"></div>
                          </div>
                          <span class="small ml-2">{{ pct(derive(c.metrics||{}).acos) }} / {{ pct(c.acos_target) }}</span>
                        </div>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

        <!-- ── Anúncios ── -->
        <template v-else>
          <div class="mb-2">
            <span class="badge badge-light border mr-2">CVR {{ pct(globalAds.cvr) }}</span>
            <span class="badge badge-light border mr-2">Receita {{ money(globalAds.revenue) }}</span>
            <span class="badge badge-light border mr-2">Custo {{ money(globalAds.cost) }}</span>
            <span class="badge badge-light border mr-2">Lucro Ads {{ money(globalAds.profit) }}</span>
            <span class="badge badge-light border">Margem {{ pct(globalAds.margin) }}</span>
          </div>
          <div class="card">
            <div class="card-body p-0 table-responsive">
              <table class="table table-sm table-hover mb-0">
                <thead><tr>
                  <th>Anúncio</th><th>Campanha</th><th>Status</th>
                  <th class="text-right">Cliques</th><th class="text-right">Impr.</th><th class="text-right">CTR</th>
                  <th class="text-right">Custo</th><th class="text-right">CPC</th><th class="text-right">CPA</th>
                  <th class="text-right">Vend.</th><th class="text-right">Receita</th><th class="text-right">ACOS</th>
                  <th class="text-center">Raio-X</th>
                </tr></thead>
                <tbody>
                  <tr v-if="!ads.length"><td colspan="13" class="text-center text-muted py-4">Nenhum anúncio no período.</td></tr>
                  <tr v-for="a in ads" :key="a.item_id">
                    <td><a :href="a.permalink" target="_blank" rel="noopener">{{ a.title }}</a><br><span class="text-muted small">{{ a.item_id }}</span></td>
                    <td class="small">{{ a.campaign_id }}</td>
                    <td><span class="badge" :class="statusBadge(a.status).cls">{{ statusBadge(a.status).txt }}</span></td>
                    <td class="text-right">{{ intf(derive(a.metrics||{}).clicks) }}</td>
                    <td class="text-right">{{ intf(derive(a.metrics||{}).prints) }}</td>
                    <td class="text-right">{{ pct(derive(a.metrics||{}).ctr) }}</td>
                    <td class="text-right">{{ money(derive(a.metrics||{}).cost) }}</td>
                    <td class="text-right">{{ money(derive(a.metrics||{}).cpc) }}</td>
                    <td class="text-right">{{ money(derive(a.metrics||{}).cpa) }}</td>
                    <td class="text-right">{{ intf(derive(a.metrics||{}).units) }}</td>
                    <td class="text-right">{{ money(derive(a.metrics||{}).revenue) }}</td>
                    <td class="text-right">{{ pct(derive(a.metrics||{}).acos) }}</td>
                    <td class="text-center">
                      <button class="btn btn-xs btn-outline-info" title="Raio-X do anúncio" @click="openRaioX(a)">
                        <i class="fas fa-x-ray"></i>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="card-footer d-flex justify-content-between align-items-center" v-if="adsPaging.total">
              <small class="text-muted">{{ adsPaging.offset + 1 }}–{{ Math.min(adsPaging.offset + adsPaging.limit, adsPaging.total) }} de {{ adsPaging.total }}</small>
              <div>
                <button class="btn btn-sm btn-outline-secondary" :disabled="adsPage <= 1" @click="fetchAds(adsPaging.offset - adsPaging.limit)">‹</button>
                <span class="mx-2 small">{{ adsPage }} / {{ adsPages }}</span>
                <button class="btn btn-sm btn-outline-secondary" :disabled="adsPage >= adsPages" @click="fetchAds(adsPaging.offset + adsPaging.limit)">›</button>
              </div>
            </div>
          </div>
        </template>
      </template>

      <!-- ════════════ CATÁLOGO/UP ════════════ -->
      <template v-else>
        <div class="row">
          <div class="col-6 col-md-3 col-xl mb-3">
            <div class="info-box"><span class="info-box-icon bg-success"><i class="fas fa-coins"></i></span>
              <div class="info-box-content"><span class="info-box-text">RECEITA</span>
                <span class="info-box-number">{{ money(globalGroups.revenue) }}</span></div></div>
          </div>
          <div class="col-6 col-md-3 col-xl mb-3">
            <div class="info-box"><span class="info-box-icon bg-danger"><i class="fas fa-money-bill"></i></span>
              <div class="info-box-content"><span class="info-box-text">CUSTO</span>
                <span class="info-box-number">{{ money(globalGroups.cost) }}</span>
                <span class="text-muted small">{{ pct(globalGroups.costPct) }} da receita</span></div></div>
          </div>
          <div class="col-6 col-md-3 col-xl mb-3">
            <div class="info-box"><span class="info-box-icon bg-primary"><i class="fas fa-chart-line"></i></span>
              <div class="info-box-content"><span class="info-box-text">LUCRO</span>
                <span class="info-box-number">{{ money(globalGroups.profit) }}</span>
                <span class="text-muted small">{{ intf(globalGroups.units) }} un. vendidas</span></div></div>
          </div>
          <div class="col-6 col-md-3 col-xl mb-3">
            <div class="info-box"><span class="info-box-icon bg-info"><i class="fas fa-layer-group"></i></span>
              <div class="info-box-content"><span class="info-box-text">GRUPOS ATIVOS</span>
                <span class="info-box-number">{{ activeGroupsCount }} de {{ adGroups.length }}</span>
                <span class="text-muted small">{{ intf(totalAdsInGroups) }} anúncios</span></div></div>
          </div>
          <div class="col-6 col-md-3 col-xl mb-3">
            <div class="info-box"><span class="info-box-icon bg-secondary"><i class="fas fa-bullseye"></i></span>
              <div class="info-box-content"><span class="info-box-text">ROAS / ACOS</span>
                <span class="info-box-number">{{ roasf(globalGroups.roas) }}</span>
                <span class="text-muted small">ACOS {{ pct(globalGroups.acos) }}</span></div></div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><strong>EXIBINDO {{ adGroups.length }} GRUPOS</strong></div>
          <div class="card-body p-0 table-responsive">
            <table class="table table-sm table-hover mb-0">
              <thead><tr>
                <th>Produto / Família</th><th>Tipo</th><th>Status</th>
                <th class="text-right">Anúncios</th><th class="text-right">ROAS</th>
                <th class="text-right">Receita</th><th class="text-right">Custo</th><th class="text-right">Lucro</th>
              </tr></thead>
              <tbody>
                <tr v-if="!adGroups.length"><td colspan="8" class="text-center text-muted py-4">Nenhum grupo no período.</td></tr>
                <tr v-for="g in adGroups" :key="g.id">
                  <td>{{ g.title }}<br><span class="text-muted small">{{ g.ad_group_external_id || g.id }}</span></td>
                  <td class="small">{{ g.ad_group_type }}</td>
                  <td><span class="badge" :class="statusBadge(g.status).cls">{{ statusBadge(g.status).txt }}</span></td>
                  <td class="text-right">{{ intf(g.advertising_items_quantity) }}</td>
                  <td class="text-right">{{ roasf(derive(g.metrics||{}).roas) }}</td>
                  <td class="text-right">{{ money(derive(g.metrics||{}).revenue) }}</td>
                  <td class="text-right">{{ money(derive(g.metrics||{}).cost) }}</td>
                  <td class="text-right">{{ money(derive(g.metrics||{}).profit) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </template>

    <div v-else class="text-center text-muted py-5">
      <i class="fas fa-bullhorn fa-2x mb-2"></i>
      <p>Selecione uma CMIG e um anunciante para acompanhar as campanhas.</p>
    </div>

    <!-- Modais -->
    <AdRaioXModal v-if="raioXAd" :params="baseParams()" :ad="raioXAd" @close="raioXAd = null" />
    <CampaignDetailModal v-if="detailCampaign" :params="baseParams()" :campaign="detailCampaign" @close="detailCampaign = null" />
  </div>
</template>
