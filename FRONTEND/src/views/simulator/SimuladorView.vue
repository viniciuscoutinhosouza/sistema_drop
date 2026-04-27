<template>
  <div class="content-header">
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-6">
          <h1 class="m-0">Simulador de Custos — ML</h1>
        </div>
        <div class="col-sm-6">
          <ol class="breadcrumb float-sm-right">
            <li class="breadcrumb-item"><a href="/dashboard">Home</a></li>
            <li class="breadcrumb-item active">Simulador ML</li>
          </ol>
        </div>
      </div>
    </div>
  </div>

  <section class="content">
    <div class="container-fluid">
      <div class="row">

        <!-- ── Formulário ─────────────────────────────────────────────── -->
        <div class="col-lg-4">
          <div class="card card-primary card-outline">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-sliders-h mr-2"></i>Parâmetros</h3>
            </div>
            <div class="card-body">

              <!-- Conta ML -->
              <div class="form-group">
                <label>Conta Mercado Livre <span class="text-danger">*</span></label>
                <select v-model="form.account_id" class="form-control">
                  <option value="">— Selecione uma conta —</option>
                  <option v-for="a in mlAccounts" :key="a.id" :value="a.id">
                    {{ a.description || a.email || `Conta #${a.id}` }}
                    <template v-if="a.platform_username"> · @{{ a.platform_username }}</template>
                  </option>
                </select>
                <small v-if="!loadingAccounts && mlAccounts.length === 0" class="text-warning">
                  <i class="fas fa-exclamation-triangle mr-1"></i>Nenhuma conta ML encontrada.
                </small>
              </div>

              <!-- Preço de venda -->
              <div class="form-group">
                <label>Preço de Venda (R$) <span class="text-danger">*</span></label>
                <div class="input-group">
                  <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                  <input v-model.number="form.price" type="number" min="0.01" step="0.01"
                         class="form-control" placeholder="0,00" />
                </div>
              </div>

              <!-- Categoria ML -->
              <div class="form-group">
                <label>Categoria ML <span class="text-danger">*</span></label>
                <div class="input-group">
                  <input
                    v-model="form.category_id"
                    type="text" class="form-control" placeholder="Ex: MLB1055"
                    @input="form.category_id = form.category_id.toUpperCase(); selectedCategoryName = ''; selectedCategoryPath = ''"
                  />
                  <div class="input-group-append">
                    <button type="button" class="btn btn-outline-warning"
                            @click="showCategoryModal = true" title="Buscar categoria">
                      <i class="fas fa-search"></i>
                    </button>
                  </div>
                </div>
                <div v-if="selectedCategoryName" class="mt-1">
                  <small class="text-success d-block">
                    <i class="fas fa-check-circle mr-1"></i><strong>{{ selectedCategoryName }}</strong>
                  </small>
                  <small v-if="selectedCategoryPath" class="text-muted d-block" style="font-size:0.78rem">
                    <i class="fas fa-sitemap mr-1"></i>{{ selectedCategoryPath }}
                  </small>
                </div>
                <small v-else class="text-muted">Digite o ID ou clique em <i class="fas fa-search"></i> para buscar.</small>
              </div>

              <!-- Custo do produto -->
              <div class="form-group">
                <label>
                  Custo do Produto (R$)
                  <small class="text-muted ml-1">opcional</small>
                </label>
                <div class="input-group">
                  <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                  <input v-model.number="form.cost_price" type="number" min="0" step="0.01"
                         class="form-control" placeholder="0,00" />
                </div>
                <small class="text-muted">Para calcular lucro e % sobre custo.</small>
              </div>

              <!-- Frete -->
              <hr class="mt-1 mb-2" />
              <div class="form-check mb-3">
                <input v-model="form.free_shipping" type="checkbox" class="form-check-input" id="chkFrete" />
                <label class="form-check-label" for="chkFrete">
                  <i class="fas fa-truck mr-1 text-muted"></i>
                  Calcular frete grátis por tipo logístico
                </label>
              </div>

              <div v-if="form.free_shipping">
                <p class="text-muted mb-2" style="font-size:0.85rem">
                  <i class="fas fa-info-circle mr-1"></i>
                  Dimensões da embalagem para comparar o custo por modalidade de envio.
                </p>
                <div class="row">
                  <div class="col-6">
                    <div class="form-group">
                      <label>Peso (kg)</label>
                      <input v-model.number="form.weight_kg" type="number" min="0.001" step="0.001"
                             class="form-control" placeholder="0,500" />
                    </div>
                  </div>
                  <div class="col-6">
                    <div class="form-group">
                      <label>Comprimento (cm)</label>
                      <input v-model.number="form.length_cm" type="number" min="1"
                             class="form-control" placeholder="30" />
                    </div>
                  </div>
                  <div class="col-6">
                    <div class="form-group">
                      <label>Altura (cm)</label>
                      <input v-model.number="form.height_cm" type="number" min="1"
                             class="form-control" placeholder="20" />
                    </div>
                  </div>
                  <div class="col-6">
                    <div class="form-group mb-0">
                      <label>Largura (cm)</label>
                      <input v-model.number="form.width_cm" type="number" min="1"
                             class="form-control" placeholder="15" />
                    </div>
                  </div>
                </div>
              </div>

            </div>
            <div class="card-footer">
              <button @click="calcular" :disabled="loading || !isFormValid"
                      class="btn btn-primary btn-block btn-lg">
                <i v-if="loading" class="fas fa-spinner fa-spin mr-2"></i>
                <i v-else class="fas fa-calculator mr-2"></i>
                {{ loading ? 'Calculando...' : 'Calcular' }}
              </button>
              <div v-if="errorMsg" class="alert alert-danger mt-3 mb-0 py-2">
                <i class="fas fa-exclamation-circle mr-1"></i>{{ errorMsg }}
              </div>
            </div>
          </div>
        </div>

        <!-- ── Resultados ──────────────────────────────────────────────── -->
        <div class="col-lg-8">

          <!-- Placeholder -->
          <div v-if="!hasResults && !loading" class="card card-outline card-secondary">
            <div class="card-body d-flex flex-column align-items-center justify-content-center text-muted py-5">
              <i class="fas fa-chart-bar fa-4x mb-4 text-secondary"></i>
              <h5>Pronto para simular</h5>
              <p class="text-center mb-0">
                Preencha os parâmetros e clique em <strong>Calcular</strong>.<br />
                O sistema compara Clássico e Premium para cada modalidade logística em paralelo.
              </p>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="card card-outline card-secondary">
            <div class="card-body text-center py-5">
              <i class="fas fa-spinner fa-spin fa-3x mb-3 text-primary"></i>
              <p class="text-muted mb-1">Consultando APIs do Mercado Livre...</p>
              <small class="text-muted">
                Comparando Clássico e Premium para todas as modalidades
                <template v-if="hasDimensions"> com custo de frete</template>.
              </small>
            </div>
          </div>

          <!-- ── Tabela Unificada ── -->
          <div v-if="hasResults" class="card card-outline card-primary">
            <div class="card-header">
              <h3 class="card-title">
                <i class="fas fa-table mr-2"></i>Comparativo de Custos por Modalidade
              </h3>
            </div>
            <div class="card-body p-0">
              <div class="table-responsive">
                <table class="table table-sm table-bordered table-hover mb-0" style="font-size:0.82rem">
                  <thead>
                    <tr>
                      <th rowspan="2" class="align-middle pl-2 thead-light" style="min-width:130px">Modalidade</th>
                      <template v-if="hasShippingData">
                        <th rowspan="2" class="align-middle text-right thead-light" style="min-width:85px">Custo Bruto</th>
                        <th rowspan="2" class="align-middle text-right thead-light" style="min-width:100px">Desc. Rep.</th>
                      </template>
                      <th colspan="4" class="text-center text-white" style="background:#17a2b8">
                        Clássico &nbsp;<small style="opacity:.85">(10–14%)</small>
                      </th>
                      <th colspan="4" class="text-center text-white" style="background:#007bff">
                        Premium &nbsp;<small style="opacity:.85">(15–19%)</small>
                      </th>
                    </tr>
                    <tr class="thead-light">
                      <th class="text-right" style="min-width:60px">Taxa %</th>
                      <th class="text-right" style="min-width:80px">Comissão</th>
                      <th class="text-right" style="min-width:80px">{{ hasCost ? 'Lucro R$' : 'Rec. Líq.' }}</th>
                      <th class="text-right pr-2" style="min-width:65px">{{ hasCost ? '% Custo' : '% Venda' }}</th>
                      <th class="text-right" style="min-width:60px">Taxa %</th>
                      <th class="text-right" style="min-width:80px">Comissão</th>
                      <th class="text-right" style="min-width:80px">{{ hasCost ? 'Lucro R$' : 'Rec. Líq.' }}</th>
                      <th class="text-right pr-2" style="min-width:65px">{{ hasCost ? '% Custo' : '% Venda' }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in unifiedComparisons" :key="row.logistic_type_id">

                      <!-- Modalidade -->
                      <td class="pl-2 align-middle">
                        <i :class="['fas', row.icon, 'mr-1 text-muted']"></i>{{ row.label }}
                      </td>

                      <!-- Frete (somente se calculado) -->
                      <template v-if="hasShippingData">
                        <td class="text-right align-middle">
                          <span v-if="row.shipping_detail">{{ fmt(row.shipping_detail.list_cost) }}</span>
                          <span v-else class="text-muted">—</span>
                        </td>
                        <td class="text-right align-middle">
                          <template v-if="row.shipping_detail?.discount_amount > 0">
                            <span class="text-success">−{{ fmt(row.shipping_detail.discount_amount) }}</span>
                            <br /><small class="text-muted">({{ row.shipping_detail.discount_rate_pct }}%)</small>
                          </template>
                          <span v-else class="text-muted">—</span>
                        </td>
                      </template>

                      <!-- Clássico -->
                      <td class="text-right align-middle text-danger">
                        <span v-if="row.classico">{{ effectivePct(row.classico) }}%</span>
                        <span v-else class="text-muted">—</span>
                      </td>
                      <td class="text-right align-middle font-weight-bold text-danger">
                        {{ row.classico ? fmt(row.classico.commission_amount) : '—' }}
                      </td>
                      <td class="text-right align-middle font-weight-bold" :class="lucroClass(row.classico)">
                        {{ row.classico ? fmt(lucro(row.classico)) : '—' }}
                      </td>
                      <td class="text-right align-middle pr-2">
                        <span v-if="row.classico" class="badge" :class="marginBadge(row.classico)">
                          {{ marginValue(row.classico) }}%
                        </span>
                        <span v-else class="text-muted">—</span>
                      </td>

                      <!-- Premium -->
                      <td class="text-right align-middle text-danger">
                        <span v-if="row.premium">{{ effectivePct(row.premium) }}%</span>
                        <span v-else class="text-muted">—</span>
                      </td>
                      <td class="text-right align-middle font-weight-bold text-danger">
                        {{ row.premium ? fmt(row.premium.commission_amount) : '—' }}
                      </td>
                      <td class="text-right align-middle font-weight-bold" :class="lucroClass(row.premium)">
                        {{ row.premium ? fmt(lucro(row.premium)) : '—' }}
                      </td>
                      <td class="text-right align-middle pr-2">
                        <span v-if="row.premium" class="badge" :class="marginBadge(row.premium)">
                          {{ marginValue(row.premium) }}%
                        </span>
                        <span v-else class="text-muted">—</span>
                      </td>

                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div class="card-footer text-muted py-2" style="font-size:0.78rem">
              <i class="fas fa-info-circle mr-1"></i>
              <template v-if="hasCost">
                Lucro = Receita líquida − Custo do produto. % Custo = Lucro ÷ Custo × 100.
              </template>
              <template v-else>
                Informe o custo do produto para calcular Lucro e % sobre Custo.
              </template>
              <span v-if="hasShippingData"> Frete calculado com peso faturável max(físico, cúbico).</span>
            </div>
          </div>

          <!-- ── Detalhes do Frete ── -->
          <div v-if="selectedShipping" class="card card-outline card-secondary">
            <div class="card-header">
              <h3 class="card-title">
                <i class="fas fa-boxes mr-2"></i>Detalhes do Frete
                <small class="text-muted ml-2">({{ selectedShippingLabel }})</small>
              </h3>
              <div class="card-tools d-flex align-items-center">
                <small class="text-muted mr-2">Modalidade:</small>
                <select v-model="selectedShippingIdx" class="form-control form-control-sm" style="width:auto">
                  <option v-for="(r, i) in unifiedComparisons" :key="i" :value="i"
                          :disabled="!r.shipping_detail">{{ r.label }}</option>
                </select>
              </div>
            </div>
            <div class="card-body p-0">
              <table class="table table-sm mb-0">
                <tbody>
                  <tr>
                    <td class="pl-3 text-muted" style="width:55%">
                      <i class="fas fa-weight-hanging mr-2"></i>Peso físico
                    </td>
                    <td class="text-right pr-3">{{ selectedShipping.physical_weight_kg }} kg</td>
                  </tr>
                  <tr>
                    <td class="pl-3 text-muted">
                      <i class="fas fa-cube mr-2"></i>Peso cúbico
                      <small class="text-muted">(A×L×C ÷ 6.000)</small>
                    </td>
                    <td class="text-right pr-3">{{ selectedShipping.cubic_weight_kg }} kg</td>
                  </tr>
                  <tr :class="selectedShipping.billable_weight_used === 'cúbico' ? 'table-warning' : 'table-light'">
                    <td class="pl-3 font-weight-bold">
                      <i class="fas fa-balance-scale mr-2"></i>Peso faturável
                      <span class="badge badge-warning ml-1">cobrado</span>
                    </td>
                    <td class="text-right pr-3 font-weight-bold">
                      {{ selectedShipping.billable_weight_kg }} kg
                      <small class="text-muted ml-1">({{ selectedShipping.billable_weight_used }})</small>
                    </td>
                  </tr>
                  <tr><td colspan="2" class="p-0"><hr class="m-0" /></td></tr>
                  <tr>
                    <td class="pl-3 text-muted">
                      <i class="fas fa-list-ol mr-2"></i>Custo bruto (tabela ML)
                    </td>
                    <td class="text-right pr-3">{{ fmt(selectedShipping.list_cost) }}</td>
                  </tr>
                  <tr>
                    <td class="pl-3 text-success">
                      <i class="fas fa-tag mr-2"></i>Desconto reputação
                      <span v-if="selectedShipping.discount_rate_pct > 0"
                            class="badge badge-success ml-1">{{ selectedShipping.discount_rate_pct }}%</span>
                      <small v-if="selectedShipping.discount_type" class="text-muted ml-1">({{ selectedShipping.discount_type }})</small>
                    </td>
                    <td class="text-right pr-3 text-success">
                      {{ selectedShipping.discount_amount > 0 ? '− ' + fmt(selectedShipping.discount_amount) : '—' }}
                    </td>
                  </tr>
                  <tr><td colspan="2" class="p-0"><hr class="m-0" /></td></tr>
                  <tr class="table-light">
                    <td class="pl-3 font-weight-bold">
                      <i class="fas fa-equals mr-2 text-muted"></i>Custo líquido ao vendedor
                    </td>
                    <td class="text-right pr-3 font-weight-bold text-danger">
                      {{ fmt(selectedShipping.net_cost) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="selectedShipping.billable_weight_used === 'cúbico'"
                 class="card-footer py-2 bg-warning" style="font-size:0.8rem">
              <i class="fas fa-exclamation-triangle mr-1"></i>
              <strong>Atenção:</strong> peso cúbico supera o físico — frete cobrado pelo volume da embalagem.
              Use embalagem mais compacta para reduzir o custo.
            </div>
          </div>

        </div>
      </div>
    </div>
  </section>

  <CategorySearchModal v-model="showCategoryModal" @select="onCategorySelect" />
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import CategorySearchModal from '@/components/CategorySearchModal.vue'

// ── constantes ────────────────────────────────────────────────────────────────
const LISTING_TYPES = [
  { listing_type_id: 'gold_special', label: 'Clássico', color: 'info'    },
  { listing_type_id: 'gold_pro',     label: 'Premium',  color: 'primary' },
]

const LOGISTIC_TYPES = [
  { logistic_type_id: 'drop_off',      label: 'ME2 — Correios', icon: 'fa-building'       },
  { logistic_type_id: 'xd_drop_off',   label: 'ME2 Places',     icon: 'fa-map-marker-alt' },
  { logistic_type_id: 'fulfillment',   label: 'Full ML',         icon: 'fa-warehouse'      },
  { logistic_type_id: 'cross_docking', label: 'Coleta',          icon: 'fa-truck'          },
]

// ── state ─────────────────────────────────────────────────────────────────────
const accounts             = ref([])
const loadingAccounts      = ref(false)
const loading              = ref(false)
const errorMsg             = ref('')
const unifiedComparisons   = ref([])
const showCategoryModal    = ref(false)
const selectedCategoryName = ref('')
const selectedCategoryPath = ref('')
const selectedShippingIdx  = ref(0)

const form = reactive({
  account_id:    '',
  price:         null,
  category_id:   '',
  cost_price:    null,
  free_shipping: true,
  weight_kg:     null,
  height_cm:     null,
  width_cm:      null,
  length_cm:     null,
  shipping_mode: 'me2',
})

// ── computed ──────────────────────────────────────────────────────────────────
const mlAccounts = computed(() =>
  accounts.value.filter(a => a.platform === 'mercadolivre' && a.is_active)
)

const isFormValid = computed(() =>
  form.account_id && form.price > 0 && form.category_id.trim().length > 0
)

const hasDimensions = computed(() =>
  form.free_shipping && form.weight_kg && form.height_cm && form.width_cm && form.length_cm
)

const hasCost = computed(() => form.cost_price > 0)

const hasResults = computed(() => unifiedComparisons.value.length > 0)

// Colunas de frete aparecem somente se os dados foram calculados com dimensões
const hasShippingData = computed(() =>
  unifiedComparisons.value.some(r => r.shipping_detail != null)
)

const selectedShipping = computed(() =>
  unifiedComparisons.value[selectedShippingIdx.value]?.shipping_detail ?? null
)

const selectedShippingLabel = computed(() =>
  unifiedComparisons.value[selectedShippingIdx.value]?.label ?? ''
)

// ── helpers ───────────────────────────────────────────────────────────────────
function fmt(v) {
  const n = Number(v ?? 0)
  return 'R$ ' + n.toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

function effectivePct(data) {
  if (!data?.price) return '—'
  return ((data.commission_amount / data.price) * 100).toFixed(1)
}

function lucro(data) {
  if (!data) return 0
  return data.gross_profit ?? data.net_revenue
}

function lucroClass(data) {
  if (!data) return ''
  return lucro(data) >= 0 ? 'text-success' : 'text-danger'
}

function marginValue(data) {
  if (!data) return '—'
  const v = data.margin_on_cost_pct ?? data.margin_pct
  return v != null ? Number(v).toFixed(1) : '—'
}

function marginBadge(data) {
  if (!data) return 'badge-secondary'
  const v = parseFloat(data.margin_on_cost_pct ?? data.margin_pct ?? 0)
  if (v >= 20) return 'badge-success'
  if (v >= 10) return 'badge-warning'
  return 'badge-danger'
}

function basePayload(overrides = {}) {
  return {
    account_id:    form.account_id,
    price:         form.price,
    category_id:   form.category_id.trim(),
    cost_price:    form.cost_price || null,
    shipping_mode: form.shipping_mode,
    ...overrides,
  }
}

function dimPayload() {
  return hasDimensions.value
    ? { weight_kg: form.weight_kg, height_cm: form.height_cm,
        width_cm: form.width_cm, length_cm: form.length_cm }
    : {}
}

// ── actions ───────────────────────────────────────────────────────────────────
function onCategorySelect({ id, name, path }) {
  form.category_id           = id
  selectedCategoryName.value = name
  selectedCategoryPath.value = path || ''
}

async function loadAccounts() {
  loadingAccounts.value = true
  try {
    const res = await api.get('/accounts')
    accounts.value = Array.isArray(res.data)
      ? res.data
      : (res.data.accounts ?? res.data.items ?? [])
  } catch {
    accounts.value = []
  } finally {
    loadingAccounts.value = false
  }
}

async function calcular() {
  errorMsg.value            = ''
  unifiedComparisons.value  = []
  selectedShippingIdx.value = 0
  loading.value             = true

  try {
    // 8 chamadas em paralelo: 4 modalidades × 2 tipos de anúncio
    const calls = []
    for (const lt of LOGISTIC_TYPES) {
      for (const listing of LISTING_TYPES) {
        calls.push(
          api.post('/simulator/full', basePayload({
            listing_type_id: listing.listing_type_id,
            logistic_type:   lt.logistic_type_id,
            free_shipping:   !!hasDimensions.value,
            ...dimPayload(),
          }))
            .then(r => ({
              ...r.data,
              _lt_id:      lt.logistic_type_id,
              _listing_id: listing.listing_type_id,
            }))
            .catch(e => {
              const detail = e?.response?.data?.detail || e?.message || 'Falha'
              console.error(`[Simulator] ${lt.logistic_type_id}/${listing.listing_type_id}:`, detail, e)
              return { _error: true, _detail: detail, _lt_id: lt.logistic_type_id, _listing_id: listing.listing_type_id }
            })
        )
      }
    }

    const results = await Promise.all(calls)

    const errors = results.filter(r => r?._error)
    if (errors.length === calls.length) {
      // Todas falharam — mostra o detalhe da primeira
      errorMsg.value = errors[0]?._detail ?? 'Erro ao consultar o Mercado Livre. Verifique se a conta está conectada.'
      return
    }

    // Agrupa por modalidade logística (ignora chamadas com erro)
    const ok = results.filter(r => !r?._error)
    unifiedComparisons.value = LOGISTIC_TYPES.map(lt => {
      const classicoData = ok.find(
        r => r._lt_id === lt.logistic_type_id && r._listing_id === 'gold_special'
      ) ?? null
      const premiumData = ok.find(
        r => r._lt_id === lt.logistic_type_id && r._listing_id === 'gold_pro'
      ) ?? null
      return {
        ...lt,
        shipping_detail: classicoData?.shipping_detail ?? premiumData?.shipping_detail ?? null,
        classico: classicoData,
        premium:  premiumData,
      }
    })
  } catch (err) {
    errorMsg.value = err?.response?.data?.detail ?? err?.message ?? 'Erro ao calcular. Verifique os parâmetros.'
  } finally {
    loading.value = false
  }
}

onMounted(loadAccounts)
</script>
