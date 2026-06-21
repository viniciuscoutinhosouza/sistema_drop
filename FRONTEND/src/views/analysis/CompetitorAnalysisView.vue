<template>
  <div>
    <div class="content-header"><div class="container-fluid">
      <h1 class="m-0"><i class="fas fa-search-dollar mr-2 text-primary"></i>Análise de Concorrência</h1>
      <small class="text-muted">Estudo de mercado (Mercado Livre + IA) para um produto PG ou CMIG.</small>
    </div></div>

    <section class="content"><div class="container-fluid">
      <!-- Parâmetros -->
      <div class="card">
        <div class="card-body">
          <div class="row">
            <div class="col-md-4 form-group">
              <label class="small font-weight-bold">Conta de marketplace (ML)</label>
              <select v-model="accountId" class="form-control form-control-sm">
                <option :value="''">Selecione...</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">
                  {{ a.description || a.platform_username || ('Conta #'+a.id) }}
                </option>
              </select>
            </div>
            <div class="col-md-2 form-group">
              <label class="small font-weight-bold">Catálogo</label>
              <div class="btn-group btn-group-sm d-flex">
                <button class="btn" :class="source==='pg'?'btn-primary':'btn-outline-primary'" @click="setSource('pg')">PG</button>
                <button class="btn" :class="source==='cmig'?'btn-primary':'btn-outline-primary'" @click="setSource('cmig')" :disabled="!cmigId">CMIG</button>
              </div>
            </div>
            <div class="col-md-4 form-group">
              <label class="small font-weight-bold">Produto</label>
              <VariationProductPicker
                :source="source" :account-cmig-id="cmigId" v-model="product"
                placeholder="Buscar por título ou SKU..."
              />
              <div v-if="product" class="small text-success mt-1">
                <i class="fas fa-check mr-1"></i>{{ product.title }} ({{ product._sku }})
              </div>
            </div>
            <div class="col-md-2 form-group">
              <label class="small font-weight-bold">Margem desejada (%)</label>
              <input v-model.number="margin" type="number" step="0.1" min="0" class="form-control form-control-sm" />
            </div>
          </div>
          <div class="form-group mb-2">
            <label class="small font-weight-bold">Comentário / instrução para a IA (opcional)</label>
            <textarea v-model="userPrompt" rows="2" class="form-control form-control-sm"
              placeholder="Ex.: foco em margem alta; comparar só anúncios Premium; priorizar Full..."></textarea>
          </div>
          <button class="btn btn-primary" :disabled="!canRun || running" @click="startAnalysis">
            <i :class="running ? 'fas fa-spinner fa-spin' : 'fas fa-rocket'" class="mr-1"></i>
            {{ running ? 'Analisando…' : 'Analisar concorrência' }}
          </button>
          <span v-if="running" class="ml-3 text-muted small"><i class="fas fa-circle-notch fa-spin mr-1"></i>{{ progress }}</span>
          <span v-if="errorMsg" class="ml-3 text-danger small"><i class="fas fa-exclamation-triangle mr-1"></i>{{ errorMsg }}</span>
        </div>
      </div>

      <!-- Diagnóstico: erros na coleta do ML -->
      <div v-if="mlErrors.length" class="alert alert-warning">
        <h6 class="mb-1"><i class="fas fa-exclamation-triangle mr-1"></i>Diagnóstico da coleta no Mercado Livre</h6>
        <ul class="mb-1 pl-3 small">
          <li v-for="(e,i) in mlErrors" :key="i"><code>{{ e }}</code></li>
        </ul>
        <small v-if="searchStudy && searchStudy.total_found === 0" class="text-muted">
          A busca não retornou anúncios — as recomendações da IA abaixo (se houver) não são confiáveis,
          pois foram geradas sem dados reais de mercado.
        </small>
      </div>

      <!-- ══ ESTUDO DE MERCADO (dados reais da busca no ML) ══ -->
      <template v-if="searchStudy && searchStudy.total_found > 0">
        <div class="row">
          <!-- Top categorias -->
          <div class="col-md-4">
            <div class="card card-outline card-primary h-100">
              <div class="card-header py-2">
                <h3 class="card-title">Top categorias
                  <small class="text-muted">({{ searchStudy.total_found }} concorrentes · {{ searchStudy.catalog_count }} catálogo · {{ searchStudy.scraped_count }} relevância · {{ searchStudy.highlights_count }} categoria)</small>
                </h3>
              </div>
              <div class="card-body p-2">
                <table class="table table-sm mb-0">
                  <tbody>
                    <tr v-for="(cat, i) in (searchStudy.top_categories || [])" :key="cat.name || i">
                      <td>
                        <a v-if="cat.url" :href="cat.url" target="_blank" rel="noopener">{{ cat.name }}</a>
                        <span v-else>{{ cat.name }}</span>
                        <small v-if="cat.id" class="text-muted">({{ cat.id }})</small>
                      </td>
                      <td class="text-right" style="white-space:nowrap">
                        <span v-if="cat.count" class="badge badge-primary">{{ cat.count }}×</span>
                        <small v-if="cat.pct != null" class="text-muted ml-1">{{ cat.pct }}%</small>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- Frete / Full + Preços -->
          <div class="col-md-8">
            <div class="card card-outline card-info h-100">
              <div class="card-header py-2"><h3 class="card-title">Frete, Full e faixas de preço</h3></div>
              <div class="card-body p-2">
                <div class="row text-center mb-2">
                  <div class="col">
                    <div class="h5 mb-0 text-success">{{ searchStudy.shipping_stats?.free_shipping_count }}</div>
                    <small class="text-muted">c/ frete grátis ({{ searchStudy.shipping_stats?.free_shipping_pct }}%)</small>
                  </div>
                  <div class="col">
                    <div class="h5 mb-0 text-primary">{{ searchStudy.shipping_stats?.full_count }}</div>
                    <small class="text-muted">no Full ({{ searchStudy.shipping_stats?.full_pct }}%)</small>
                  </div>
                  <div class="col">
                    <div class="h5 mb-0 text-warning">{{ searchStudy.shipping_stats?.kit_count }}</div>
                    <small class="text-muted">são KIT ({{ searchStudy.shipping_stats?.kit_pct }}%)</small>
                  </div>
                  <div class="col" v-if="searchStudy.rating_avg">
                    <div class="h5 mb-0 text-info">★ {{ searchStudy.rating_avg }}</div>
                    <small class="text-muted">avaliação média</small>
                  </div>
                </div>
                <table class="table table-sm mb-0">
                  <thead class="thead-light"><tr>
                    <th>Grupo</th><th class="text-center">Mín</th><th class="text-center">Médio</th><th class="text-center">Máx</th><th class="text-center">Qtd</th>
                  </tr></thead>
                  <tbody>
                    <tr v-for="row in priceRows" :key="row.label">
                      <td><span class="badge" :class="row.badge">{{ row.label }}</span></td>
                      <td class="text-center">{{ money(row.block?.min) }}</td>
                      <td class="text-center"><strong>{{ money(row.block?.avg) }}</strong></td>
                      <td class="text-center">{{ money(row.block?.max) }}</td>
                      <td class="text-center">{{ row.block?.count }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- Distribuição de preço + Concentração de vendedores -->
        <div class="row">
          <div class="col-md-6" v-if="searchStudy.price_stats?.distribution?.median">
            <div class="card card-outline card-info h-100">
              <div class="card-header py-2"><h3 class="card-title">Distribuição de preço</h3></div>
              <div class="card-body p-2">
                <table class="table table-sm mb-2">
                  <tbody>
                    <tr><td>25% mais baratos até</td><td class="text-right"><strong>{{ money(searchStudy.price_stats?.distribution?.p25) }}</strong></td></tr>
                    <tr><td>Mediana</td><td class="text-right"><strong>{{ money(searchStudy.price_stats?.distribution?.median) }}</strong></td></tr>
                    <tr><td>25% mais caros a partir de</td><td class="text-right"><strong>{{ money(searchStudy.price_stats?.distribution?.p75) }}</strong></td></tr>
                  </tbody>
                </table>
                <div v-if="searchStudy.sweet_spot?.count" class="alert alert-success py-2 mb-0" style="font-size:13px">
                  <strong>Sweet spot</strong> (faixa dos mais vendidos):
                  {{ money(searchStudy.sweet_spot.min) }} – {{ money(searchStudy.sweet_spot.max) }}
                  <span class="text-muted">(médio {{ money(searchStudy.sweet_spot.avg) }})</span>
                </div>
              </div>
            </div>
          </div>
          <div class="col-md-6" v-if="searchStudy.seller_concentration">
            <div class="card card-outline card-warning h-100">
              <div class="card-header py-2"><h3 class="card-title">Concentração de vendedores</h3>
                <small v-if="searchStudy.seller_concentration" class="text-muted d-block">
                  {{ searchStudy.seller_concentration.distinct_sellers }} vendedores distintos · maior tem {{ searchStudy.seller_concentration.share_top_seller_pct }}%
                </small>
              </div>
              <div class="card-body p-2">
                <table class="table table-sm mb-0">
                  <tbody>
                    <tr v-for="sc in (searchStudy.seller_concentration?.top_sellers || [])" :key="sc.seller">
                      <td>{{ sc.seller }}</td>
                      <td class="text-right"><span class="badge badge-primary">{{ sc.count }}×</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <!-- Top 30 palavras-chave -->
        <div class="card card-outline card-secondary">
          <div class="card-header py-2"><h3 class="card-title">Top 30 palavras-chave (título · marca · modelo)</h3></div>
          <div class="card-body p-2">
            <span v-for="kw in (searchStudy.top_keywords || [])" :key="kw.word"
              class="badge badge-light border mr-1 mb-1" style="font-size:12px;font-weight:normal">
              {{ kw.word }} <span class="badge badge-secondary ml-1">{{ kw.count }}</span>
            </span>
          </div>
        </div>

        <!-- Top concorrentes (com link p/ o anúncio) -->
        <div class="card" v-if="topCompetitors.length">
          <div class="card-header py-2">
            <h3 class="card-title">Top {{ topCompetitors.length }} concorrentes por vendas (aprox.)</h3>
            <small class="text-muted d-block">Os {{ deepVisitedCount }} mais relevantes tiveram a página visitada (categoria, ficha técnica, reputação, data). Visitas são indisponíveis na página pública do ML.</small>
          </div>
          <div class="card-body p-0">
            <table class="table table-sm table-hover mb-0">
              <thead class="thead-light"><tr>
                <th style="width:54px">Foto</th><th>Anúncio / Título</th><th>Vendedor</th><th>Categoria</th><th class="text-center">Preço</th>
                <th class="text-center">Vendas</th><th class="text-center" v-if="!enrichmentOff">Visitas 30d</th><th>Frete</th>
                <th v-if="hasReputation">Reputação</th><th class="text-center">Avaliação</th>
              </tr></thead>
              <tbody>
                <tr v-for="c in topCompetitors" :key="c.item_id">
                  <td>
                    <a v-if="c.permalink" :href="c.permalink" target="_blank" rel="noopener">
                      <img :src="c.thumbnail || 'https://via.placeholder.com/44?text=%E2%80%94'" style="width:44px;height:44px;object-fit:contain;border-radius:4px" />
                    </a>
                    <img v-else :src="c.thumbnail || 'https://via.placeholder.com/44?text=%E2%80%94'" style="width:44px;height:44px;object-fit:contain;border-radius:4px" />
                  </td>
                  <td>
                    <a v-if="c.permalink" :href="c.permalink" target="_blank" rel="noopener" title="Abrir anúncio no ML">
                      <small>{{ c.item_id }} <i class="fas fa-external-link-alt" style="font-size:9px"></i></small>
                    </a>
                    <small v-else>{{ c.item_id }}</small>
                    <div style="font-size:12px;line-height:1.25">{{ c.title }}</div>
                    <small v-if="c.brand || c.model" class="text-muted">{{ [c.brand, c.model].filter(Boolean).join(' · ') }}</small>
                  </td>
                  <td style="font-size:12px">
                    <a v-if="c.seller_url" :href="c.seller_url" target="_blank" rel="noopener" title="Abrir página do vendedor">
                      {{ c.seller || 'vendedor' }} <i class="fas fa-external-link-alt" style="font-size:9px"></i>
                    </a>
                    <span v-else>{{ c.seller || '—' }}</span>
                  </td>
                  <td style="font-size:11px">{{ c.category_leaf || '—' }}</td>
                  <td class="text-center">
                    {{ money(c.price) }}
                    <div v-if="c.original_price" class="text-muted" style="font-size:10px;text-decoration:line-through">{{ money(c.original_price) }}</div>
                  </td>
                  <td class="text-center">{{ c.sold_quantity ?? '—' }}<div v-if="c.sales_per_day" class="text-muted" style="font-size:10px">{{ c.sales_per_day }}/dia</div></td>
                  <td class="text-center" v-if="!enrichmentOff">{{ c.visits_30d ?? '—' }}<div v-if="c.visits_per_day" class="text-muted" style="font-size:10px">{{ c.visits_per_day }}/dia</div></td>
                  <td><small>{{ c.free_shipping ? 'Frete grátis' : '—' }}<br>{{ c.logistic_type === 'fulfillment' ? 'FULL' : '' }}</small></td>
                  <td v-if="hasReputation"><small>{{ repLabel(c) }}</small></td>
                  <td class="text-center"><small>{{ c.rating ? `★ ${c.rating}` : '—' }}<div v-if="c.reviews_text" class="text-muted" style="font-size:10px">{{ c.reviews_text }}</div></small></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>

      <!-- Resultado (síntese da IA) -->
      <template v-if="study">
        <!-- Análise do especialista (comentário geral) -->
        <div class="card card-outline card-primary" v-if="study.expert_analysis">
          <div class="card-header py-2"><h3 class="card-title"><i class="fas fa-user-tie mr-1"></i> Análise do especialista</h3></div>
          <div class="card-body" style="white-space:pre-line;font-size:14px;line-height:1.5">{{ study.expert_analysis }}</div>
        </div>

        <!-- Clássico × Premium (seu produto) -->
        <div class="card card-outline card-success" v-if="ownerListingTypes?.options?.length">
          <div class="card-header py-2">
            <h3 class="card-title">Clássico × Premium (seu produto)</h3>
            <small class="text-muted d-block">No preço que atinge sua margem desejada ({{ ownerListingTypes.desired_margin_pct }}%) · custo {{ money(ownerListingTypes.cost_price) }}
              <span v-if="!ownerListingTypes.has_dimensions" class="text-danger">· ⚠ sem dimensões → frete não calculado (cadastre peso/medidas)</span>
            </small>
          </div>
          <div class="card-body p-0">
            <table class="table table-sm mb-0">
              <thead class="thead-light"><tr>
                <th>Tipo</th><th class="text-center">Preço</th><th class="text-center">Comissão</th><th class="text-center">Frete</th>
                <th class="text-center">Receita líq.</th><th class="text-center">Lucro</th><th class="text-center">Margem s/ custo</th>
              </tr></thead>
              <tbody>
                <tr v-for="o in ownerListingTypes.options" :key="o.listing_type_id"
                    :class="{ 'table-success': o.listing_type_id === ownerListingTypes.recommended }">
                  <td><strong>{{ o.label }}</strong> <i v-if="o.listing_type_id === ownerListingTypes.recommended" class="fas fa-star text-warning" title="Recomendado"></i><br><small class="text-muted">{{ o.fee_range }}</small></td>
                  <td class="text-center">{{ money(o.price) }}</td>
                  <td class="text-center">{{ money(o.commission_amount) }}<div class="text-muted" style="font-size:10px">{{ o.commission_pct }}%</div></td>
                  <td class="text-center">{{ money(o.shipping_cost) }}</td>
                  <td class="text-center">{{ money(o.net_revenue) }}</td>
                  <td class="text-center"><strong>{{ money(o.gross_profit) }}</strong></td>
                  <td class="text-center">{{ o.margin_on_cost_pct }}%</td>
                </tr>
              </tbody>
            </table>
            <div v-if="study.listing_type_recommendation?.rationale" class="p-2 small text-muted">{{ study.listing_type_recommendation.rationale }}</div>
          </div>
        </div>

        <div class="row">
          <div class="col-md-8">
            <div class="card card-outline card-success">
              <div class="card-header"><h3 class="card-title">Recomendações do estudo</h3></div>
              <div class="card-body">
                <dl class="row mb-0">
                  <dt class="col-sm-3">Melhor título</dt>
                  <dd class="col-sm-9">
                    <strong>{{ study.best_title }}</strong>
                    <button class="btn btn-xs btn-outline-secondary ml-2" @click="copy(study.best_title)"><i class="fas fa-copy"></i></button>
                  </dd>
                  <dt class="col-sm-3">Modelo</dt><dd class="col-sm-9">{{ study.model_field || '—' }}</dd>
                  <dt class="col-sm-3">Melhor categoria</dt>
                  <dd class="col-sm-9">
                    <span v-if="study.best_category">{{ study.best_category.name }} <small class="text-muted">({{ study.best_category.id }})</small></span>
                    <div v-if="study.best_category?.path" class="small text-muted">{{ study.best_category.path }}</div>
                    <div v-if="study.best_category?.rationale" class="small text-muted">{{ study.best_category.rationale }}</div>
                  </dd>
                  <dt class="col-sm-3">Faixa de preço</dt>
                  <dd class="col-sm-9" v-if="study.price_range">
                    <div><span class="badge badge-info">Iniciante</span> {{ money(study.price_range.beginner?.min) }} – {{ money(study.price_range.beginner?.max) }}</div>
                    <div><span class="badge badge-success">Maduro</span> {{ money(study.price_range.mature?.min) }} – {{ money(study.price_range.mature?.max) }}</div>
                    <div class="small text-muted">{{ study.price_range.rationale }} <em v-if="study.price_range.margin_check">— {{ study.price_range.margin_check }}</em></div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="card card-outline card-warning">
              <div class="card-header"><h3 class="card-title">Ações p/ relevância</h3></div>
              <div class="card-body p-2">
                <ul class="mb-0 pl-3" style="font-size:13px">
                  <li v-for="(r,i) in (study.recommendations||[])" :key="i">{{ r }}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <!-- Previsão -->
        <div class="card" v-if="study.forecast">
          <div class="card-header"><h3 class="card-title">Previsão (estimativa)</h3></div>
          <div class="card-body p-0">
            <table class="table table-sm mb-0">
              <thead class="thead-light"><tr>
                <th>Janela</th><th class="text-center">Vendas (faixa)</th><th class="text-center">Visitas (faixa)</th>
                <th class="text-center">Lucro (faixa)</th><th class="text-center">Confiança</th>
              </tr></thead>
              <tbody>
                <tr v-for="w in ['7','14','30','60','90']" :key="w">
                  <td><strong>{{ w }} dias</strong></td>
                  <td class="text-center">{{ range(study.forecast[w]?.sales) }}</td>
                  <td class="text-center">{{ range(study.forecast[w]?.visits) }}</td>
                  <td class="text-center">{{ rangeMoney(study.forecast[w]?.profit) }}</td>
                  <td class="text-center"><span class="badge" :class="confColor(study.forecast[w]?.confidence)">{{ study.forecast[w]?.confidence || '—' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="card-footer small text-muted">{{ study.forecast.method_note }} {{ study.disclaimer }}</div>
        </div>

        <!-- Anotações -->
        <div class="card card-outline card-secondary" v-if="currentId">
          <div class="card-header"><h3 class="card-title">Minhas anotações (usadas em estudos futuros)</h3></div>
          <div class="card-body">
            <textarea v-model="notes" rows="3" class="form-control form-control-sm" placeholder="Anote conclusões/decisões deste estudo..."></textarea>
            <button class="btn btn-sm btn-secondary mt-2" @click="saveNotes"><i class="fas fa-save mr-1"></i>Salvar anotações</button>
          </div>
        </div>
      </template>

      <div v-else-if="rawResult" class="alert alert-warning">
        A IA não retornou um JSON válido. Resposta bruta:
        <pre class="mt-2 small" style="white-space:pre-wrap">{{ rawResult }}</pre>
      </div>

      <!-- Histórico -->
      <div class="card" v-if="history.length">
        <div class="card-header"><h3 class="card-title">Estudos anteriores deste produto</h3></div>
        <div class="card-body p-0">
          <table class="table table-sm mb-0">
            <thead class="thead-light"><tr><th>Data</th><th>Status</th><th>Anotações</th><th style="width:120px"></th></tr></thead>
            <tbody>
              <tr v-for="h in history" :key="h.id">
                <td><small>{{ fmtDate(h.created_at) }}</small></td>
                <td><span class="badge" :class="h.status==='done'?'badge-success':(h.status==='error'?'badge-danger':'badge-info')">{{ h.status }}</span></td>
                <td><small class="text-muted">{{ (h.notes||'').slice(0,80) }}</small></td>
                <td class="text-right">
                  <button class="btn btn-xs btn-outline-info mr-1" @click="openHistory(h.id)" title="Reabrir"><i class="fas fa-eye"></i></button>
                  <button class="btn btn-xs btn-outline-danger" @click="removeAnalysis(h.id)" title="Excluir"><i class="fas fa-trash"></i></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div></section>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency, formatDateTime } from '@/utils/formatters'
import VariationProductPicker from '@/components/catalog/VariationProductPicker.vue'

const toast = useToast()
const accounts = ref([])
const accountId = ref('')
const source = ref('pg')
const product = ref(null)
const margin = ref(30)
const userPrompt = ref('')

const running = ref(false)
const progress = ref('')
const errorMsg = ref('')
const currentId = ref(null)
const study = ref(null)
const rawResult = ref(null)
const competitors = ref([])   // top 20 por vendas (ml_data), com link/foto/métricas
const searchStudy = ref(null) // estudo de mercado (categorias, keywords, frete, preço)
const mlErrors = ref([])      // erros da coleta no ML (diagnóstico)
const enrichmentOff = ref(false) // API do ML de itens bloqueada → dados só da busca raspada
const ownerListingTypes = ref(null) // simulador Clássico × Premium do produto do dono
const topCompetitors = computed(() => competitors.value)
const hasReputation = computed(() => competitors.value.some(c => c.seller_reputation && (c.seller_reputation.text || c.seller_reputation.sales)))
const deepVisitedCount = computed(() => searchStudy.value?.deep_visited_count ?? 0)
const priceRows = computed(() => {
  const ps = searchStudy.value?.price_stats || {}
  return [
    { label: 'Com frete grátis', badge: 'badge-success', block: ps.with_free_shipping },
    { label: 'Sem frete grátis', badge: 'badge-secondary', block: ps.without_free_shipping },
    { label: 'FULL', badge: 'badge-primary', block: ps.full },
    { label: 'KIT', badge: 'badge-warning', block: ps.kit },
    { label: 'Sem KIT', badge: 'badge-light border', block: ps.non_kit },
  ].filter(r => r.block && r.block.count)
})
const notes = ref('')
const history = ref([])
let pollTimer = null

const selectedAccount = computed(() => accounts.value.find(a => a.id === accountId.value) || null)
const cmigId = computed(() => selectedAccount.value?.cmig_id ?? null)
const canRun = computed(() => !!accountId.value && !!product.value && margin.value >= 0)

function money(v) { return v != null ? formatCurrency(v) : '—' }
function range(arr) { return Array.isArray(arr) && arr.length === 2 ? `${arr[0]} – ${arr[1]}` : '—' }
function rangeMoney(arr) { return Array.isArray(arr) && arr.length === 2 ? `${money(arr[0])} – ${money(arr[1])}` : '—' }
function fmtDate(d) { return d ? formatDateTime(d) : '—' }
function confColor(c) { return c === 'alta' ? 'badge-success' : (c === 'media' ? 'badge-warning' : 'badge-secondary') }
function copy(t) { navigator.clipboard?.writeText(t || ''); toast.success('Copiado') }
function buildCompetitors(result) {
  // O backend já entrega competitors = top20_by_sales ordenado; mantém a ordem.
  competitors.value = [...(result?.ml_data?.competitors || [])].slice(0, 20)
  searchStudy.value = result?.ml_data?.search_study || null
  mlErrors.value = result?.ml_data?.errors || []
  enrichmentOff.value = !!result?.ml_data?.enrichment_off
  ownerListingTypes.value = result?.ml_data?.owner_listing_types || null
}
function repLabel(c) {
  const rep = c?.seller_reputation
  if (rep && (rep.text || rep.sales)) return [rep.text, rep.sales].filter(Boolean).join(' · ')
  const lvl = rep?.level_id
  return lvl ? `Nível ${lvl}` : (c?.seller_id ? `Vend. ${c.seller_id}` : '—')
}

function setSource(s) {
  if (s === 'cmig' && !cmigId.value) return
  source.value = s
  product.value = null
}

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    accounts.value = Array.isArray(data) ? data : []
    if (accounts.value.length === 1) accountId.value = accounts.value[0].id
  } catch { accounts.value = [] }
}

async function loadHistory() {
  if (!product.value) { history.value = []; return }
  try {
    const { data } = await api.get('/competitor-analysis', {
      params: { product_type: source.value, product_id: product.value.id },
    })
    history.value = Array.isArray(data) ? data : []
  } catch { history.value = [] }
}

async function startAnalysis() {
  if (!canRun.value) return
  running.value = true; errorMsg.value = ''; study.value = null; rawResult.value = null
  searchStudy.value = null; competitors.value = []; mlErrors.value = []
  progress.value = 'Iniciando…'
  try {
    const { data } = await api.post('/competitor-analysis', {
      product_type: source.value,
      product_id: product.value.id,
      account_id: accountId.value,
      desired_margin_pct: margin.value,
      user_prompt: userPrompt.value || null,
    })
    currentId.value = data.id
    poll()
  } catch (e) {
    running.value = false
    errorMsg.value = e.response?.data?.detail || 'Erro ao iniciar a análise.'
  }
}

function poll() {
  clearInterval(pollTimer)
  pollTimer = setInterval(fetchStatus, 3000)
  fetchStatus()
}

async function fetchStatus() {
  if (!currentId.value) return
  try {
    const { data } = await api.get(`/competitor-analysis/${currentId.value}`)
    progress.value = data.progress_step || ''
    if (data.status === 'done') {
      clearInterval(pollTimer); running.value = false
      study.value = data.result?.study || null
      rawResult.value = data.result?.study_raw || null
      buildCompetitors(data.result)
      notes.value = data.notes || ''
      loadHistory()
    } else if (data.status === 'error') {
      clearInterval(pollTimer); running.value = false
      errorMsg.value = data.error || 'Falha na análise.'
    }
  } catch {
    clearInterval(pollTimer); running.value = false
    errorMsg.value = 'Erro ao consultar o status.'
  }
}

async function openHistory(id) {
  try {
    const { data } = await api.get(`/competitor-analysis/${id}`)
    currentId.value = id
    study.value = data.result?.study || null
    rawResult.value = data.result?.study_raw || null
    buildCompetitors(data.result)
    notes.value = data.notes || ''
    errorMsg.value = data.status === 'error' ? (data.error || '') : ''
  } catch { toast.error('Erro ao abrir o estudo.') }
}

async function saveNotes() {
  if (!currentId.value) return
  try {
    await api.patch(`/competitor-analysis/${currentId.value}`, { notes: notes.value })
    toast.success('Anotações salvas.')
    loadHistory()
  } catch { toast.error('Erro ao salvar anotações.') }
}

async function removeAnalysis(id) {
  if (!confirm('Excluir este estudo?')) return
  try {
    await api.delete(`/competitor-analysis/${id}`)
    if (currentId.value === id) { study.value = null; rawResult.value = null; currentId.value = null }
    toast.success('Estudo excluído.')
    loadHistory()
  } catch { toast.error('Erro ao excluir.') }
}

watch(product, () => { study.value = null; rawResult.value = null; currentId.value = null; searchStudy.value = null; competitors.value = []; mlErrors.value = []; loadHistory() })
onMounted(loadAccounts)
onBeforeUnmount(() => clearInterval(pollTimer))
</script>
