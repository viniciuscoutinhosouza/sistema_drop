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
                <button class="btn btn-sm btn-info mr-2" @click="openWizard(null)" :disabled="!selectedAccountId">
                  <i class="fas fa-plus mr-1"></i>Novo Anúncio
                </button>
                <button class="btn btn-sm btn-success mr-2" @click="syncStock" :disabled="!selectedAccountId || syncingStock"
                        title="Envia o estoque atual de cada produto vinculado para o marketplace">
                  <i :class="['fas', syncingStock ? 'fa-spinner fa-spin' : 'fa-sync-alt', 'mr-1']"></i>Sincronizar Estoque
                </button>
                <button class="btn btn-sm btn-secondary" @click="importAnuncios" :disabled="!selectedAccountId || importing">
                  <i :class="['fas', importing ? 'fa-spinner fa-spin' : 'fa-download', 'mr-1']"></i>Importar
                </button>
              </div>
            </div>
            <div v-if="selectedAccountId" class="row mt-2">
              <div class="col-12">
                <ul class="nav nav-pills" style="gap:2px">
                  <li v-for="tab in statusTabs" :key="tab.key" class="nav-item">
                    <a :class="['nav-link py-1 px-2 small', filterStatus === tab.key ? 'active' : '']"
                       href="#" @click.prevent="filterStatus = tab.key">
                      {{ tab.label }}
                      <span v-if="tab.key !== 'all' && statsBar?.counts?.[tab.key]"
                            class="badge badge-light ml-1">{{ statsBar.counts[tab.key] }}</span>
                    </a>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        <!-- Stats bar -->
        <div v-if="statsBar && selectedAccountId" class="card card-body py-2 px-3 mb-3">
          <div class="d-flex align-items-center flex-wrap" style="gap:20px">
            <span class="text-muted small">
              <i class="fas fa-eye mr-1 text-info"></i>
              Visitas (7d): <strong>{{ (statsBar.visits?.total_visits || 0).toLocaleString('pt-BR') }}</strong>
            </span>
            <span class="text-muted small">
              <i class="fas fa-shopping-cart mr-1 text-success"></i>
              Total vendidos: <strong>{{ statsBar.total_sold || 0 }}</strong>
            </span>
            <span v-for="tab in statusTabs.filter(t => t.key !== 'all')" :key="'stat-'+tab.key" class="text-muted small">
              <span :class="statusBadgeClass(tab.key)">{{ tab.label }}</span>
              <strong class="ml-1">{{ statsBar.counts?.[tab.key] || 0 }}</strong>
            </span>
            <button class="btn btn-sm btn-outline-secondary ml-auto" @click="loadStats" :disabled="loadingStats">
              <i :class="['fas', loadingStats ? 'fa-spinner fa-spin' : 'fa-sync-alt']"></i>
            </button>
          </div>
        </div>

        <!-- Listagem -->
        <div class="card">
          <div class="card-body p-0">
            <div v-if="!selectedAccountId" class="text-center text-muted py-5">
              <i class="fas fa-plug fa-2x mb-2 d-block"></i>Selecione uma conta de marketplace acima.
            </div>
            <div v-else-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else-if="filteredAnuncios.length === 0" class="text-center text-muted py-5">
              <i class="fas fa-tag fa-2x mb-2 d-block"></i>Nenhum anúncio encontrado.
              <div class="mt-2">
                <button class="btn btn-sm btn-secondary mr-2" @click="importAnuncios" :disabled="importing">
                  <i class="fas fa-download mr-1"></i>Importar do Marketplace
                </button>
                <button class="btn btn-sm btn-success" @click="openWizard(null)">
                  <i class="fas fa-plus mr-1"></i>Criar Manualmente
                </button>
              </div>
            </div>
            <div v-else>
              <div v-for="a in filteredAnuncios" :key="a.id"
                   class="border-bottom"
                   :style="!a.is_linked ? 'background:#fffbea' : ''">

                <!-- ── Linha única: thumb | info | financeiro | ações ── -->
                <div class="d-flex align-items-start p-2" style="gap:10px">

                  <!-- Thumbnail (fallback pra imagem do produto vinculado se listing.thumbnail vazio) -->
                  <img v-if="listingThumb(a)" :src="listingThumb(a)"
                       style="width:64px;height:64px;object-fit:cover;border-radius:4px;flex-shrink:0" />
                  <div v-else class="d-flex align-items-center justify-content-center bg-light"
                       style="width:64px;height:64px;border-radius:4px;flex-shrink:0">
                    <i class="fas fa-image text-muted"></i>
                  </div>

                  <!-- Info central -->
                  <div class="flex-grow-1" style="min-width:0;font-size:12px">

                    <!-- Título + status inline -->
                    <div class="d-flex align-items-baseline" style="gap:6px">
                      <span class="font-weight-bold text-truncate" style="font-size:13px" :title="a.title_override">{{ a.title_override }}</span>
                      <span :class="statusBadgeClass(a.status)" style="flex-shrink:0;font-size:10px">{{ statusLabel(a.status) }}</span>
                    </div>

                    <!-- ID · SKU · tipo · logística · vínculo -->
                    <div class="d-flex flex-wrap align-items-center mt-1" style="gap:4px">
                      <span class="text-monospace text-muted" style="font-size:11px">{{ a.platform_item_id }}</span>
                      <span v-if="a.sku" class="text-muted" style="font-size:11px">· SKU: {{ a.sku }}</span>
                      <span v-if="a.listing_type" :class="listingTypeBadge(a.listing_type)" style="font-size:10px">{{ listingTypeLabel(a.listing_type) }}</span>
                      <span v-if="a.is_full" class="badge" style="background:#00a650;color:#fff;font-size:10px"><i class="fas fa-warehouse mr-1"></i>Full</span>
                      <span v-if="a.catalog_listing && a.ml_catalog_id" class="badge badge-primary" style="font-size:10px" :title="'Produto: ' + a.ml_catalog_id"><i class="fas fa-bookmark mr-1"></i>Anúncio de Catálogo</span>
                      <span v-else-if="!a.catalog_listing && a.ml_catalog_id" class="badge badge-secondary" style="font-size:10px" :title="'Vinculado: ' + a.ml_catalog_id"><i class="fas fa-link mr-1"></i>Vinculado ao Catálogo</span>
                      <span :class="'badge ' + listingQuality(a).cls" style="font-size:10px;cursor:help"
                            :title="listingQuality(a).issues.length ? listingQuality(a).issues.join('\n') : 'Anúncio completo'">
                        <i class="fas fa-star mr-1"></i>{{ listingQuality(a).label }}
                      </span>
                      <span class="text-muted" style="font-size:11px"><i class="fas fa-truck mr-1"></i>{{ logisticLabel(a) }}</span>
                      <span v-if="a.free_shipping" class="text-success font-weight-bold" style="font-size:11px">· Frete Grátis</span>
                      <span v-if="listingBrand(a)" class="text-muted" style="font-size:11px">· <i class="fas fa-tag mr-1"></i>{{ listingBrand(a) }}</span>
                      <!-- Badge de ajuste automático de preço (PRICE_DISCOUNT / PRICE_MATCHING) -->
                      <span v-if="a.has_auto_price_adj || ['PRICE_DISCOUNT','PRICE_MATCHING'].includes(promoData(a).promoType)"
                            class="badge"
                            style="background:#0284c7;color:#fff;font-size:10px;cursor:default"
                            title="O Mercado Livre está ajustando o preço automaticamente para ganhar competitividade">
                        <span class="fa-stack" style="font-size:6px;line-height:2em;vertical-align:middle;margin-right:3px">
                          <i class="fas fa-sync-alt fa-stack-2x"></i>
                          <i class="fas fa-dollar-sign fa-stack-1x" style="color:#0284c7;font-size:0.7em"></i>
                        </span>Preço Auto ML
                        <template v-if="promoData(a).discountPct"> −{{ promoData(a).discountPct }}%</template>
                      </span>
                      <!-- Badge de promoção regular (campanhas ML) -->
                      <template v-else-if="promoData(a).hasPromo">
                        <span class="badge" style="background:#e11d48;color:#fff;font-size:10px">
                          <i class="fas fa-tag mr-1"></i>
                          {{ PROMO_TYPE_LABEL[promoData(a).promoType] || 'Em promoção' }}
                          <template v-if="promoData(a).discountPct"> −{{ promoData(a).discountPct }}%</template>
                        </span>
                      </template>
                      <span v-if="a.cmig_product" class="badge badge-success" style="font-size:10px">CMIG: {{ a.cmig_product.sku }}</span>
                      <span v-else-if="a.catalog_product" class="badge badge-info" style="font-size:10px">PG: {{ a.catalog_product.sku }}</span>
                      <span v-else class="badge badge-warning" style="font-size:10px"><i class="fas fa-exclamation-triangle mr-1"></i>Sem vínculo</span>
                    </div>

                    <!-- Categoria -->
                    <div v-if="a.category_id" class="mt-1 text-muted" style="font-size:11px;line-height:1.3">
                      <i class="fas fa-layer-group mr-1"></i>
                      <template v-if="categoryPaths[a.category_id]?.length">
                        {{ categoryPaths[a.category_id].slice(0,-1).map(p => p.name).join(' › ') }}
                        <span v-if="categoryPaths[a.category_id].length > 1"> › </span>
                        <strong class="text-dark">{{ categoryPaths[a.category_id].slice(-1)[0]?.name || a.category_name }}</strong>
                      </template>
                      <span v-else>{{ a.category_name || a.category_id }}</span>
                      <span class="text-monospace ml-1" style="font-size:10px">({{ a.category_id }})</span>
                    </div>

                    <!-- Dimensões -->
                    <div class="mt-1" style="font-size:11px">
                      <i class="fas fa-box-open mr-1 text-secondary"></i>
                      <template v-if="a.height_cm || a.width_cm || a.length_cm">
                        <template v-if="a.height_cm && a.width_cm && a.length_cm">{{ a.height_cm }}×{{ a.width_cm }}×{{ a.length_cm }} cm</template>
                        <span v-if="a.weight_kg" class="ml-1 text-muted">· {{ a.weight_kg }} kg físico</span>
                        <span v-if="billableWeight(a)" class="ml-1 font-weight-bold"
                              :style="isCubicBillable(a) ? 'color:#d97706' : 'color:#374151'">
                          · {{ billableWeight(a) }} kg faturável<template v-if="isCubicBillable(a)"> (cúbico)</template>
                        </span>
                      </template>
                      <span v-else class="text-muted">Dimensões não cadastradas</span>
                    </div>

                    <!-- Métricas -->
                    <div class="d-flex flex-wrap align-items-center mt-1" style="gap:8px;font-size:11px">
                      <span class="text-info"><i class="fas fa-eye mr-1"></i>{{ a.visits_7d || 0 }} vis./7d</span>
                      <span class="text-success"><i class="fas fa-shopping-cart mr-1"></i>{{ a.sold_quantity || 0 }} vendidos</span>
                      <span class="text-primary"><i class="fas fa-box mr-1"></i>{{ a.available_quantity || 0 }} disp.</span>
                      <span v-if="a.is_full" style="color:#00a650;font-weight:600"><i class="fas fa-warehouse mr-1"></i>Full: {{ a.qty_full }} un.</span>
                      <span v-else-if="a.qty_local !== undefined" class="text-secondary"><i class="fas fa-store mr-1"></i>Local: {{ a.qty_local }} un.</span>
                      <a v-if="pictureCount(a)" href="#" class="text-secondary" @click.prevent="openPhotosModal(a)">
                        <i class="fas fa-camera mr-1"></i>{{ pictureCount(a) }}
                      </a>
                      <a v-if="hasVariations(a)" href="#" class="text-info" @click.prevent="showVariationsModal(a)">
                        <i class="fas fa-sitemap mr-1"></i>Variações
                      </a>
                    </div>
                  </div>

                  <!-- Grid financeiro -->
                  <div style="flex:0 0 220px;font-size:11px;border-left:1px solid #e2e8f0;padding-left:10px;align-self:stretch;display:flex;flex-direction:column;justify-content:center">
                    <div v-if="loadingCosts[a.id]" class="text-muted">
                      <i class="fas fa-spinner fa-spin mr-1"></i>Consultando...
                    </div>
                    <template v-else>
                      <!-- Preço: normal + promocional (quando há promoção) -->
                      <div class="mb-1">
                        <div class="d-flex align-items-center flex-wrap" style="gap:5px">
                          <span v-if="pricingCalc(a).isReal && !pricingCalc(a).isStale"
                                style="font-size:10px;background:#dcfce7;color:#16a34a;border-radius:3px;padding:0 4px;font-weight:600">ML real</span>
                          <span v-else-if="pricingCalc(a).isReal && pricingCalc(a).isStale"
                                style="font-size:10px;background:#ffedd5;color:#c2410c;border-radius:3px;padding:0 4px;font-weight:600"
                                title="Cache > 4h — clique em Recalcular para atualizar">desatualizado</span>
                          <span v-else
                                style="font-size:10px;background:#fef9c3;color:#92400e;border-radius:3px;padding:0 4px">estimado</span>
                          <template v-if="promoData(a).hasPromo">
                            <span class="text-muted" style="font-size:11px;text-decoration:line-through">
                              {{ formatCurrency(promoData(a).regularPrice) }}
                            </span>
                            <!-- Preço com ajuste automático ML: azul + ícone -->
                            <template v-if="a.has_auto_price_adj || ['PRICE_DISCOUNT','PRICE_MATCHING'].includes(promoData(a).promoType)">
                              <span style="font-size:13px;font-weight:700;color:#0284c7">
                                {{ formatCurrency(promoData(a).salePrice) }}
                              </span>
                              <span class="fa-stack" style="font-size:7px;line-height:2em;vertical-align:middle;margin-left:2px" title="Preço ajustado automaticamente pelo Mercado Livre">
                                <i class="fas fa-sync-alt fa-stack-2x" style="color:#0284c7"></i>
                                <i class="fas fa-dollar-sign fa-stack-1x" style="color:#fff"></i>
                              </span>
                            </template>
                            <!-- Promoção regular: vermelho -->
                            <template v-else>
                              <span style="font-size:13px;font-weight:700;color:#e11d48">
                                {{ formatCurrency(promoData(a).salePrice) }}
                              </span>
                              <span v-if="promoData(a).discountPct"
                                    style="font-size:10px;background:#fce7f3;color:#be185d;border-radius:3px;padding:0 4px;font-weight:600">
                                −{{ promoData(a).discountPct }}%
                              </span>
                            </template>
                          </template>
                          <!-- Preço sem promoção mas com ajuste automático ML silencioso -->
                          <template v-else-if="a.has_auto_price_adj">
                            <span style="font-size:13px;font-weight:700;color:#0284c7">
                              {{ formatCurrency(a.sale_price) }}
                            </span>
                            <span class="fa-stack" style="font-size:7px;line-height:2em;vertical-align:middle;margin-left:2px" title="Preço ajustado automaticamente pelo Mercado Livre">
                              <i class="fas fa-sync-alt fa-stack-2x" style="color:#0284c7"></i>
                              <i class="fas fa-dollar-sign fa-stack-1x" style="color:#fff"></i>
                            </span>
                          </template>
                          <span v-else class="font-weight-bold" style="font-size:13px">
                            {{ formatCurrency(a.sale_price) }}
                          </span>
                        </div>
                      </div>
                      <div class="d-flex justify-content-between text-danger">
                        <span>Comissão ({{ pricingCalc(a).rate }}%):</span>
                        <span>−{{ formatCurrency(pricingCalc(a).fee) }}</span>
                      </div>
                      <div v-if="pricingCalc(a).financing_fee > 0" class="d-flex justify-content-between text-danger">
                        <span>Parcelamento:</span>
                        <span>−{{ formatCurrency(pricingCalc(a).financing_fee) }}</span>
                      </div>
                      <div v-if="pricingCalc(a).fixed_fee > 0" class="d-flex justify-content-between text-danger">
                        <span>Taxa fixa:</span>
                        <span>−{{ formatCurrency(pricingCalc(a).fixed_fee) }}</span>
                      </div>
                      <!-- Frete pago pelo vendedor (free_shipping / Full) -->
                      <div v-if="a.free_shipping || a.is_full"
                           class="d-flex justify-content-between" style="color:#d97706">
                        <span>Frete (vendedor):</span>
                        <span v-if="pricingCalc(a).shipping_cost > 0">−{{ formatCurrency(pricingCalc(a).shipping_cost) }}</span>
                        <span v-else-if="!hasDimensions(a)" class="text-muted small">sem dims.</span>
                        <span v-else class="text-warning small" style="cursor:pointer"
                              :title="'Dimensões presentes mas ML não retornou custo de frete. Clique para forçar refresh.'"
                              @click="forceRefreshCosts(a)">
                          recalcular <i class="fas fa-sync-alt"></i>
                        </span>
                      </div>
                      <!-- Frete pago pelo comprador (ME2 sem frete grátis) — informativo -->
                      <div v-else-if="a.shipping_mode === 'me2' || (!a.free_shipping && !a.is_full)"
                           class="d-flex justify-content-between text-muted">
                        <span>Frete:</span>
                        <span class="small">pago pelo comprador</span>
                      </div>
                      <div style="border-top:1px solid #e2e8f0;margin:4px 0"></div>
                      <div class="d-flex justify-content-between font-weight-bold" style="color:#16a34a">
                        <span>Receita Líq.:</span>
                        <span>{{ formatCurrency(pricingCalc(a).margin) }} <span class="text-muted font-weight-normal">({{ pricingCalc(a).marginPct }}%)</span></span>
                      </div>
                      <div v-if="a.costs_cached_at" class="text-right mt-1" style="font-size:10px;color:#94a3b8">
                        <i class="fas fa-clock mr-1"></i>{{ timeSince(a.costs_cached_at) }}
                      </div>
                    </template>
                  </div>

                  <!-- Ações -->
                  <div class="flex-shrink-0 d-flex flex-column align-items-end" style="gap:3px;padding-left:16px;border-left:1px solid #e2e8f0">
                    <!-- Linha 1: edição e vínculo -->
                    <div class="btn-group btn-group-sm">
                      <button class="btn btn-outline-secondary" title="Editar" @click="openWizard(a)"><i class="fas fa-edit"></i></button>
                      <button class="btn btn-outline-primary" title="Vincular produto" @click="openLinkModal(a)"><i class="fas fa-link"></i></button>
                      <button v-if="!a.is_linked" class="btn btn-outline-dark" title="Criar produto CMIG" @click="openCreateCmigModal(a)"><i class="fas fa-plus"></i></button>
                      <button v-if="a.is_linked" class="btn btn-outline-warning" title="Desvincular produto" @click="unlinkAnuncio(a)"><i class="fas fa-unlink"></i></button>
                    </div>
                    <!-- Linha 2: status e marketplace -->
                    <div class="btn-group btn-group-sm">
                      <button v-if="a.status === 'published'" class="btn btn-outline-warning" title="Pausar anúncio" @click="pauseAnuncio(a)"><i class="fas fa-pause"></i></button>
                      <button v-if="a.status === 'paused'" class="btn btn-outline-success" title="Reativar anúncio" @click="reactivateAnuncio(a)"><i class="fas fa-play"></i></button>
                      <button v-if="a.platform_item_id && a.is_linked" class="btn btn-outline-info" title="Sincronizar com ML" @click="syncToMl(a)"><i class="fas fa-sync-alt"></i></button>
                      <a v-if="a.permalink" :href="a.permalink" target="_blank" class="btn btn-outline-info" title="Ver no Marketplace"><i class="fas fa-external-link-alt"></i></a>
                    </div>
                    <!-- Linha 3: exclusão -->
                    <div class="btn-group btn-group-sm">
                      <button class="btn btn-outline-danger" title="Excluir do sistema" @click="deleteAnuncioSistema(a)"><i class="fas fa-trash"></i></button>
                      <button v-if="a.platform_item_id" class="btn btn-danger" title="Excluir do sistema e do Marketplace" @click="deleteAnuncioMarketplace(a)"><i class="fas fa-trash-alt"></i></button>
                    </div>
                  </div>

                </div>

              </div>
              <!-- /item v-for -->

            </div>
          </div>
        </div>

      </div>
    </section>

    <!-- ═══════════ WIZARD MODAL ═══════════ -->
    <div v-if="wizard.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-bullhorn mr-2"></i>
              {{ wizard.isEdit ? 'Editar Anúncio' : 'Novo Anúncio' }}
            </h5>
            <button type="button" class="close" @click="wizard.show = false"><span>&times;</span></button>
          </div>

          <!-- Abas -->
          <div class="modal-body p-0">
            <ul class="nav nav-tabs px-3 pt-2 bg-light">
              <li class="nav-item" v-for="(tab, i) in wizardTabs" :key="i">
                <a :class="['nav-link', wizardStep === i+1 ? 'active' : '']" href="#" @click.prevent="wizardStep = i+1">
                  <span :class="['badge mr-1', wizardStep > i+1 ? 'badge-success' : (wizardStep === i+1 ? 'badge-primary' : 'badge-secondary')]">{{ i+1 }}</span>
                  {{ tab }}
                </a>
              </li>
            </ul>

            <div class="p-3" style="max-height:calc(75vh - 160px);overflow-y:auto">
              <div v-if="wizard.error" class="alert alert-danger py-2">{{ wizard.error }}</div>

              <!-- ABA 1 — Produto -->
              <div v-if="wizardStep === 1">
                <p class="text-muted small mb-2">Selecione o produto base do anúncio:</p>
                <ul class="nav nav-pills mb-3">
                  <li class="nav-item">
                    <a :class="['nav-link', wf.product_type==='cmig'?'active':'']" href="#" @click.prevent="wf.product_type='cmig'; wf.product_id=null; wf.selectedProduct=null">Produto CMIG</a>
                  </li>
                  <li class="nav-item">
                    <a :class="['nav-link', wf.product_type==='pg'?'active':'']" href="#" @click.prevent="wf.product_type='pg'; wf.product_id=null; wf.selectedProduct=null">Produto PG (Catálogo)</a>
                  </li>
                </ul>
                <div class="input-group mb-3">
                  <input v-model="productSearch" class="form-control" :placeholder="`Buscar ${wf.product_type==='cmig' ? 'produto CMIG' : 'produto PG'} por nome ou SKU...`" @input="filterProducts" />
                  <div class="input-group-append"><span class="input-group-text"><i class="fas fa-search"></i></span></div>
                </div>
                <div style="max-height:280px;overflow-y:auto">
                  <div v-if="filteredProductList.length === 0" class="text-muted text-center py-3">Nenhum produto encontrado.</div>
                  <div v-for="p in filteredProductList" :key="p.id"
                    :class="['d-flex align-items-center p-2 border-bottom cursor-pointer', wf.product_id === p.id ? 'bg-primary text-white' : 'hover-bg']"
                    style="cursor:pointer" @click="selectProduct(p)">
                    <img v-if="p.thumbnail || (p.images && p.images[0])" :src="p.thumbnail || p.images[0]?.url" style="width:40px;height:40px;object-fit:cover;border-radius:3px;margin-right:10px" />
                    <i v-else class="fas fa-box mr-3 text-muted" style="font-size:1.5rem;width:40px;text-align:center"></i>
                    <div class="flex-grow-1">
                      <div class="font-weight-bold">{{ p.sku_cmig || p.sku }}</div>
                      <div class="small">{{ p.title }}</div>
                      <div v-if="p.brand" class="small text-muted">{{ p.brand }}<span v-if="p.model"> · {{ p.model }}</span></div>
                    </div>
                    <div v-if="wf.product_id === p.id" class="ml-2"><i class="fas fa-check-circle fa-lg"></i></div>
                  </div>
                </div>
                <div v-if="wf.selectedProduct" class="alert alert-success py-1 mt-2 small mb-0">
                  <i class="fas fa-check mr-1"></i>Selecionado: <strong>{{ wf.selectedProduct.sku_cmig || wf.selectedProduct.sku }}</strong> — {{ wf.selectedProduct.title }}
                </div>
              </div>

              <!-- ABA 2 — Detalhes do Anúncio -->
              <div v-if="wizardStep === 2">
                <div class="row">
                  <div class="col-md-8 form-group">
                    <label>Título do Anúncio <span class="text-danger">*</span></label>
                    <input v-model="wf.title_override" class="form-control" maxlength="60"
                           :required="!!selectedAccount?.is_official_store"
                           :disabled="!selectedAccount?.is_official_store && !!wf.platform_item_id" />
                    <small v-if="!selectedAccount?.is_official_store && !!wf.platform_item_id" class="text-warning">
                      <i class="fas fa-lock mr-1"></i>Esta conta não é Loja Oficial — o título não pode ser alterado via API.
                    </small>
                    <small v-else :class="wf.title_override.length > 55 ? 'text-danger' : 'text-muted'">
                      {{ wf.title_override.length }}/60 caracteres
                    </small>
                  </div>
                  <div class="col-md-4 form-group">
                    <label>Preço de Venda (R$) <span class="text-danger">*</span></label>
                    <div class="input-group">
                      <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                      <input v-model.number="wf.sale_price" type="number" step="0.01" min="0" class="form-control" required />
                    </div>
                  </div>
                </div>
                <div class="row">
                  <div class="col-md-3 form-group">
                    <label>Tipo de Anúncio</label>
                    <template v-if="wizard.isEdit">
                      <div class="form-control bg-light" style="cursor:default">
                        {{ wf.listing_type === 'gold_pro' ? 'Premium' : 'Clássico' }}
                      </div>
                      <small class="text-muted">Não editável após publicação.</small>
                    </template>
                    <template v-else>
                      <select v-model="wf.listing_type" class="form-control">
                        <option value="gold_special">Clássico</option>
                        <option value="gold_pro">Premium</option>
                      </select>
                    </template>
                  </div>
                  <div class="col-12 form-group">
                    <label class="font-weight-bold">Estoque Local</label>
                    <div class="d-flex mb-2" style="gap:10px">
                      <div class="card flex-fill text-center p-2"
                           style="cursor:pointer;border-width:2px;transition:border-color .15s"
                           :style="wf.stock_mode === 'product' ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                           @click="wf.stock_mode = 'product'">
                        <div style="font-size:16px" class="mb-1">📦</div>
                        <div style="font-size:12px;font-weight:600">Estoque do Produto</div>
                        <div class="text-muted" style="font-size:11px">Sincroniza automaticamente com o PG/CMIG</div>
                      </div>
                      <div class="card flex-fill text-center p-2"
                           style="cursor:pointer;border-width:2px;transition:border-color .15s"
                           :style="wf.stock_mode === 'fixed' ? 'border-color:#6366f1;background:#f5f3ff' : 'border-color:#dee2e6'"
                           @click="wf.stock_mode = 'fixed'">
                        <div style="font-size:16px" class="mb-1">🔢</div>
                        <div style="font-size:12px;font-weight:600">Valor Fixo</div>
                        <div class="text-muted" style="font-size:11px">Quantidade definida manualmente</div>
                      </div>
                    </div>
                    <div v-if="wf.stock_mode === 'fixed'" class="p-2 rounded" style="background:#f5f3ff;border:1px solid #c4b5fd">
                      <div class="d-flex align-items-center mb-2" style="gap:10px">
                        <label class="small font-weight-bold mb-0">Quantidade:</label>
                        <input v-model.number="wf.fixed_quantity" type="number" min="0" step="1"
                               class="form-control form-control-sm" style="width:90px" />
                        <span class="text-muted small">unidades no ML</span>
                      </div>
                      <div class="custom-control custom-checkbox">
                        <input v-model="wf.keep_stock_fixed" type="checkbox"
                               class="custom-control-input" id="ksf_edit" />
                        <label class="custom-control-label small" for="ksf_edit">
                          Manter fixo — restaurar para {{ wf.fixed_quantity }} após cada venda
                        </label>
                      </div>
                    </div>
                    <div v-else class="text-muted small mt-1">
                      <i class="fas fa-sync-alt mr-1"></i>O sync a cada 30 min atualiza o ML com o estoque real do produto.
                    </div>
                  </div>
                  <div class="col-md-3 form-group">
                    <label>Condição</label>
                    <template v-if="wizard.isEdit">
                      <div class="form-control bg-light" style="cursor:default">
                        {{ wf.item_condition === 'new' ? 'Novo' : wf.item_condition === 'used' ? 'Usado' : 'Não especificado' }}
                      </div>
                      <small class="text-muted">Não editável após publicação.</small>
                    </template>
                    <template v-else>
                      <select v-model="wf.item_condition" class="form-control">
                        <option value="new">Novo</option>
                        <option value="used">Usado</option>
                        <option value="not_specified">Não especificado</option>
                      </select>
                    </template>
                  </div>
                  <div class="col-md-3 form-group">
                    <label>ID no Marketplace</label>
                    <template v-if="wizard.isEdit">
                      <div class="form-control bg-light text-monospace" style="font-size:13px;cursor:default">
                        {{ wf.platform_item_id || '—' }}
                      </div>
                    </template>
                    <input v-else v-model="wf.platform_item_id" class="form-control" placeholder="MLB12345678 (para vincular)" />
                  </div>
                </div>
                <div class="row">
                  <div class="col-md-3 form-group">
                    <label>SKU do Vendedor</label>
                    <input v-model="wf.sku" class="form-control" placeholder="Ex: PROD-001" />
                  </div>
                </div>
                <div v-if="!wizard.isEdit" class="form-group">
                  <label>Modo de Publicação</label>
                  <div class="d-flex">
                    <div class="custom-control custom-radio mr-4">
                      <input type="radio" v-model="wf.mode" value="create" class="custom-control-input" id="mode_create" />
                      <label class="custom-control-label" for="mode_create">Criar novo anúncio no marketplace</label>
                    </div>
                    <div class="custom-control custom-radio">
                      <input type="radio" v-model="wf.mode" value="link" class="custom-control-input" id="mode_link" />
                      <label class="custom-control-label" for="mode_link">Vincular a ID existente</label>
                    </div>
                  </div>
                </div>
              </div>

              <!-- ABA 3 — Categoria & Atributos -->
              <div v-if="wizardStep === 3">
                <!-- Categoria atual como breadcrumb -->
                <div class="d-flex align-items-center mb-3">
                  <div class="flex-grow-1">
                    <label class="mb-1 d-block small font-weight-bold">Categoria</label>
                    <div v-if="wf.category_id" class="d-flex align-items-center flex-wrap" style="gap:4px;font-size:12px">
                      <template v-if="categoryPaths[wf.category_id]?.length">
                        <span v-for="(p, i) in categoryPaths[wf.category_id]" :key="p.id">
                          <span :class="i === categoryPaths[wf.category_id].length-1 ? 'font-weight-bold text-dark' : 'text-muted'">{{ p.name }}</span>
                          <i v-if="i < categoryPaths[wf.category_id].length-1" class="fas fa-angle-right mx-1 text-muted"></i>
                        </span>
                      </template>
                      <span v-else class="font-weight-bold">{{ wf.category_name || wf.category_id }}</span>
                      <code class="text-muted ml-1" style="font-size:11px">{{ wf.category_id }}</code>
                    </div>
                    <span v-else class="text-muted small">Nenhuma categoria selecionada</span>
                  </div>
                  <button type="button" class="btn btn-sm btn-outline-secondary ml-3" @click="categoryEditMode = !categoryEditMode"
                          :title="categoryEditMode ? 'Fechar busca' : 'Alterar categoria'">
                    <i :class="['fas', categoryEditMode ? 'fa-times' : 'fa-pencil-alt']"></i>
                  </button>
                </div>

                <!-- Campo de busca — visível apenas quando categoryEditMode = true -->
                <div v-if="categoryEditMode" class="mb-3">
                  <div class="input-group">
                    <input v-model="categorySearch" class="form-control" placeholder="Ex: Tênis Masculino, Celular, Notebook..." @input="debouncedCategorySearch" />
                    <div class="input-group-append">
                      <button class="btn btn-outline-secondary" @click="searchCategories" :disabled="catLoading">
                        <i :class="['fas', catLoading ? 'fa-spinner fa-spin' : 'fa-search']"></i>
                      </button>
                    </div>
                  </div>
                  <div v-if="categoryResults.length > 0" class="list-group mt-2" style="max-height:200px;overflow-y:auto">
                    <a v-for="c in categoryResults" :key="c.id"
                      :class="['list-group-item list-group-item-action py-1', wf.category_id === c.id ? 'active' : '']"
                      href="#" @click.prevent="selectCategory(c); categoryEditMode = false">
                      <strong>{{ c.name }}</strong>
                      <span class="text-muted small ml-2">{{ c.id }}</span>
                      <span v-if="c.total_items_in_this_category" class="badge badge-light ml-1">{{ c.total_items_in_this_category.toLocaleString() }}</span>
                    </a>
                  </div>
                </div>

                <!-- Atributos ML da categoria (obrigatórios/recomendados) -->
                <div v-if="wf.category_id">
                  <div v-if="attrLoading" class="text-center py-2"><i class="fas fa-spinner fa-spin text-muted"></i> Carregando atributos...</div>
                  <template v-else>
                    <div v-if="categoryAttributes.length > 0">
                      <h6 class="text-muted small text-uppercase mb-2">Atributos da Categoria</h6>
                      <div class="row">
                        <div v-for="attr in categoryAttributes" :key="attr.id" class="col-md-4 form-group">
                          <label class="small">
                            {{ attr.name }}
                            <span v-if="attr.is_required" class="text-danger">*</span>
                            <span v-else class="text-muted">(recom.)</span>
                          </label>
                          <select v-if="attr.values && attr.values.length > 0" v-model="attrValues[attr.id]" class="form-control form-control-sm">
                            <option value="">— Selecione —</option>
                            <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                          </select>
                          <input v-else v-model="attrValues[attr.id]" class="form-control form-control-sm" :placeholder="attr.name" />
                        </div>
                      </div>
                    </div>

                    <!-- Atributos extras do anúncio (existentes mas fora da lista ML da categoria) -->
                    <div v-if="extraCategoryAttrs.length > 0" class="mt-2">
                      <h6 class="text-muted small text-uppercase mb-2">Características Secundárias</h6>
                      <div class="row">
                        <div v-for="attr in extraCategoryAttrs" :key="attr.id" class="col-md-4 form-group">
                          <label class="small">{{ attr.name }}</label>
                          <input v-model="attrValues[attr.id]" class="form-control form-control-sm" />
                        </div>
                      </div>
                    </div>
                  </template>
                </div>
              </div>

              <!-- ABA 4 — Fotos -->
              <div v-if="wizardStep === 4">
                <p class="text-muted small mb-2">Selecione até 12 fotos. A primeira será a foto principal.</p>

                <div v-if="wf.selectedProduct">
                  <div class="d-flex align-items-center mb-2">
                    <h6 class="text-muted small text-uppercase mb-0 flex-grow-1">
                      Fotos do produto vinculado
                      <span v-if="wf.product_type === 'cmig'" class="badge badge-secondary ml-1">CMIG</span>
                      <span v-else-if="wf.product_type === 'pg'" class="badge badge-info ml-1">PG</span>
                    </h6>
                    <button class="btn btn-sm btn-outline-primary"
                            type="button"
                            :disabled="refreshingProductImages"
                            :title="`Buscar fotos atualizadas do cadastro de ${wf.product_type === 'cmig' ? 'Produto CMIG' : 'Produto PG'}`"
                            @click="refreshProductImages">
                      <i :class="['fas', refreshingProductImages ? 'fa-spinner fa-spin' : 'fa-sync-alt']"></i>
                      Atualizar fotos
                    </button>
                  </div>
                  <div v-if="productImages.length > 0" class="d-flex flex-wrap mb-3">
                    <div v-for="(img, i) in productImages" :key="i" class="mr-2 mb-2 position-relative" style="cursor:pointer" @click="toggleImage(img)">
                      <img :src="img" :style="`width:80px;height:80px;object-fit:cover;border-radius:4px;border:3px solid ${isImageSelected(img) ? '#007bff' : '#dee2e6'}`" />
                      <span v-if="isImageSelected(img)" class="badge badge-primary position-absolute" style="top:-6px;right:-6px;font-size:10px">{{ wf.pictures.indexOf(img)+1 }}</span>
                    </div>
                  </div>
                  <div v-else class="text-muted small mb-3">Produto sem fotos cadastradas.</div>
                </div>

                <div class="form-group">
                  <label class="small">Adicionar URL de foto</label>
                  <div class="input-group input-group-sm">
                    <input v-model="extraImageUrl" class="form-control" placeholder="https://..." />
                    <div class="input-group-append">
                      <button class="btn btn-outline-secondary" @click="addExtraImage" :disabled="!extraImageUrl">
                        <i class="fas fa-plus"></i>
                      </button>
                    </div>
                  </div>
                </div>

                <div v-if="wf.pictures.length > 0">
                  <h6 class="text-muted small text-uppercase mb-1">Fotos selecionadas ({{ wf.pictures.length }}/12)</h6>
                  <div class="d-flex flex-wrap">
                    <div v-for="(img, i) in wf.pictures" :key="i" class="mr-2 mb-2 position-relative" style="width:70px"
                      @mouseenter="startWizardPreview($event, img)"
                      @mouseleave="stopWizardPreview"
                    >
                      <img :src="img" style="width:70px;height:70px;object-fit:cover;border-radius:4px;border:2px solid #007bff;display:block" />
                      <!-- Badge posição / capa -->
                      <span
                        class="position-absolute d-flex align-items-center justify-content-center text-white rounded"
                        style="top:2px;left:2px;min-width:18px;height:18px;font-size:9px;padding:0 3px;line-height:1"
                        :style="i === 0 ? 'background:#007bff' : 'background:rgba(0,0,0,0.55)'"
                        :title="i === 0 ? 'Foto de capa' : `Posição ${i+1}`"
                      >{{ i === 0 ? '★' : i + 1 }}</span>
                      <!-- Botão remover -->
                      <button class="btn btn-danger position-absolute" style="top:-6px;right:-6px;width:20px;height:20px;padding:0;line-height:1;border-radius:50%;font-size:10px" @click="removeImage(i)"><i class="fas fa-times"></i></button>
                      <!-- Botões mover -->
                      <button
                        v-if="i > 0"
                        class="position-absolute"
                        style="bottom:2px;left:2px;width:20px;height:20px;padding:0;border:none;border-radius:3px;font-size:9px;background:rgba(0,0,0,0.55);color:#fff;cursor:pointer"
                        title="Mover para esquerda"
                        @click="moveImage(i, -1)"
                      ><i class="fas fa-chevron-left"></i></button>
                      <button
                        v-if="i < wf.pictures.length - 1"
                        class="position-absolute"
                        style="bottom:2px;right:2px;width:20px;height:20px;padding:0;border:none;border-radius:3px;font-size:9px;background:rgba(0,0,0,0.55);color:#fff;cursor:pointer"
                        title="Mover para direita"
                        @click="moveImage(i, 1)"
                      ><i class="fas fa-chevron-right"></i></button>
                    </div>
                  </div>
                </div>
                <div v-if="wf.pictures.length === 0" class="text-muted small">Nenhuma foto selecionada.</div>
              </div>

              <!-- ABA 5 — Descrição, Envio & Garantia -->
              <div v-if="wizardStep === 5">
                <div class="row">
                  <div class="col-md-8">
                    <div class="form-group">
                      <label>Descrição do Produto</label>
                      <textarea v-model="wf.description_override" class="form-control" rows="6" placeholder="Descreva o produto em detalhes (texto simples)..."></textarea>
                    </div>
                    <div class="form-group">
                      <label>YouTube Video ID <small class="text-muted">(opcional)</small></label>
                      <input v-model="wf.video_id" class="form-control" placeholder="dQw4w9WgXcQ" />
                      <div v-if="wf.video_id" class="mt-2">
                        <iframe :src="`https://www.youtube.com/embed/${wf.video_id}`" width="280" height="160" frameborder="0" allowfullscreen></iframe>
                      </div>
                    </div>
                  </div>
                  <div class="col-md-4">
                    <h6 class="text-muted small text-uppercase mb-2">Frete</h6>
                    <div class="form-group">
                      <label class="small">Modalidade de Envio</label>
                      <select v-model="wf.shipping_mode" class="form-control form-control-sm">
                        <option value="me2">Mercado Envios (me2)</option>
                        <option value="custom">Frete Customizado</option>
                        <option value="not_specified">Não especificado</option>
                      </select>
                    </div>
                    <div class="form-group">
                      <label class="small">Quem paga o frete?</label>
                      <div class="d-flex" style="gap:8px">
                        <div class="card flex-fill text-center p-2"
                             style="cursor:pointer;border-width:2px;transition:border-color .15s"
                             :style="!wf.free_shipping ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                             @click="wf.free_shipping = false">
                          <div style="font-size:16px" class="mb-1">🛒</div>
                          <div style="font-size:11px;font-weight:600">Comprador</div>
                        </div>
                        <div class="card flex-fill text-center p-2"
                             style="cursor:pointer;border-width:2px;transition:border-color .15s"
                             :style="wf.free_shipping ? 'border-color:#28a745;background:#f0fff4' : 'border-color:#dee2e6'"
                             @click="wf.free_shipping = true">
                          <div style="font-size:16px" class="mb-1">🚚</div>
                          <div style="font-size:11px;font-weight:600;color:#16a34a">Vendedor</div>
                        </div>
                      </div>
                      <div class="text-muted mt-1" style="font-size:10px">
                        {{ wf.free_shipping ? 'Frete Grátis — vendedor arca com o custo' : 'Frete cobrado do comprador' }}
                      </div>
                    </div>

                    <hr />
                    <h6 class="text-muted small text-uppercase mb-2">Dimensões do Pacote</h6>
                    <div class="row">
                      <div class="col-6 form-group">
                        <label class="small">Peso (kg)</label>
                        <input v-model.number="wf.weight_kg" type="number" step="0.001" min="0" class="form-control form-control-sm" placeholder="Ex: 0.500" />
                      </div>
                      <div class="col-6 form-group">
                        <label class="small">Altura (cm)</label>
                        <input v-model.number="wf.height_cm" type="number" step="0.1" min="0" class="form-control form-control-sm" placeholder="Ex: 10" />
                      </div>
                      <div class="col-6 form-group">
                        <label class="small">Largura (cm)</label>
                        <input v-model.number="wf.width_cm" type="number" step="0.1" min="0" class="form-control form-control-sm" placeholder="Ex: 15" />
                      </div>
                      <div class="col-6 form-group">
                        <label class="small">Comprimento (cm)</label>
                        <input v-model.number="wf.length_cm" type="number" step="0.1" min="0" class="form-control form-control-sm" placeholder="Ex: 20" />
                      </div>
                    </div>

                    <hr />
                    <h6 class="text-muted small text-uppercase mb-2">Garantia</h6>
                    <div class="form-group">
                      <label class="small">Tipo de Garantia</label>
                      <select v-model="wf.warranty_type" class="form-control form-control-sm">
                        <option value="">Sem garantia</option>
                        <option value="Garantia do vendedor">Garantia do Vendedor</option>
                        <option value="Garantia do fabricante">Garantia do Fabricante</option>
                      </select>
                    </div>
                    <div class="form-group" v-if="wf.warranty_type">
                      <label class="small">Prazo de Garantia</label>
                      <select v-model="wf.warranty_time" class="form-control form-control-sm">
                        <option value="">— Selecione —</option>
                        <option value="3 meses">3 meses</option>
                        <option value="6 meses">6 meses</option>
                        <option value="12 meses">12 meses</option>
                        <option value="18 meses">18 meses</option>
                        <option value="24 meses">24 meses</option>
                        <option value="36 meses">36 meses</option>
                      </select>
                    </div>
                  </div>
                </div>

                <!-- Dados Fiscais -->
                <hr class="mt-3" />
                <h6 class="text-muted small text-uppercase mb-2">Dados Fiscais</h6>
                <div class="row">
                  <div class="col-md-3 form-group">
                    <label class="small">NCM</label>
                    <input v-model="wizardFiscal.ncm" class="form-control form-control-sm" placeholder="Ex: 84713012" maxlength="10" />
                  </div>
                  <div class="col-md-3 form-group">
                    <label class="small">EAN / GTIN</label>
                    <input v-model="wizardFiscal.ean" class="form-control form-control-sm" placeholder="Ex: 7891234567890" maxlength="14" />
                  </div>
                  <div class="col-md-3 form-group">
                    <label class="small">CEST</label>
                    <input v-model="wizardFiscal.cest" class="form-control form-control-sm" placeholder="Ex: 2800100" maxlength="7" />
                  </div>
                </div>
              </div>

            </div><!-- /p-3 -->
          </div><!-- /modal-body -->

          <div class="modal-footer justify-content-between">
            <div>
              <button class="btn btn-outline-secondary mr-2" @click="wizardStep = Math.max(1, wizardStep-1)" :disabled="wizardStep === 1">
                <i class="fas fa-arrow-left mr-1"></i>Anterior
              </button>
              <button v-if="wizardStep < wizardTabs.length" class="btn btn-outline-primary" @click="wizardStep = wizardStep+1">
                Próximo<i class="fas fa-arrow-right ml-1"></i>
              </button>
            </div>
            <div class="d-flex align-items-center">
              <small v-if="wizard.isEdit && wf.platform_item_id" class="text-muted mr-3">
                <i class="fas fa-cloud-upload-alt mr-1 text-warning"></i>Salvar envia as alterações ao Mercado Livre
              </small>
              <button class="btn btn-secondary mr-2" @click="wizard.show = false">Cancelar</button>
              <button class="btn btn-primary" @click="saveWizard" :disabled="wizard.saving">
                <i v-if="wizard.saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ wizard.saving ? 'Salvando...' : (wizard.isEdit ? 'Salvar e Enviar ao ML' : (wf.mode === 'create' ? 'Publicar no Marketplace' : 'Vincular Anúncio')) }}
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>

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
                <span>Novos anúncios importados</span><span class="badge badge-success badge-pill">{{ importResult.imported }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Atualizados</span><span class="badge badge-info badge-pill">{{ importResult.updated }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Auto-vinculados</span><span class="badge badge-primary badge-pill">{{ importResult.auto_matched }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Sem vínculo</span><span class="badge badge-warning badge-pill">{{ importResult.unlinked }}</span>
              </li>
            </ul>
          </div>
          <div class="modal-footer">
            <button v-if="importResult.unlinked > 0" class="btn btn-warning btn-sm" @click="setFilter('unlinked'); importResult = null">Ver sem vínculo</button>
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
                <div><strong>{{ p.sku }}</strong> — {{ p.title }}<span class="badge badge-light ml-1">{{ Math.round(p.similarity * 100) }}%</span></div>
                <button class="btn btn-sm btn-success" @click="doLink({ cmig_product_id: p.id })">Vincular</button>
              </div>
              <h6 class="text-uppercase text-muted small mb-2 mt-3">Produtos PG (Catálogo)</h6>
              <div v-if="linkModal.pg_suggestions.length === 0" class="text-muted small">Nenhum produto PG encontrado.</div>
              <div v-for="p in linkModal.pg_suggestions" :key="'p'+p.id" class="d-flex justify-content-between align-items-center border-bottom py-2">
                <div><strong>{{ p.sku }}</strong> — {{ p.title }}<span class="badge badge-light ml-1">{{ Math.round(p.similarity * 100) }}%</span></div>
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
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-plus mr-2"></i>Criar Produto CMIG</h5>
            <button type="button" class="close" @click="createCmigModal.show = false"><span>&times;</span></button>
          </div>
          <form @submit.prevent="doCreateCmigProduct">
            <div class="modal-body" style="max-height:75vh;overflow-y:auto">
              <div v-if="createCmigModal.error" class="alert alert-danger py-2">{{ createCmigModal.error }}</div>
              <p class="text-muted small mb-3">A partir do anúncio: <strong>{{ createCmigModal.listing?.title_override }}</strong></p>

              <!-- Fotos importadas -->
              <div v-if="createCmigModal.pictures.length" class="mb-3">
                <p class="font-weight-bold small text-uppercase text-muted mb-1">
                  <i class="fas fa-images mr-1"></i>Fotos importadas ({{ createCmigModal.pictures.length }})
                </p>
                <div class="d-flex flex-wrap">
                  <img v-for="(pic, i) in createCmigModal.pictures.slice(0, 8)" :key="i"
                       :src="pic.url" class="rounded border mr-1 mb-1"
                       style="width:60px;height:60px;object-fit:cover;" />
                  <span v-if="createCmigModal.pictures.length > 8"
                        class="d-flex align-items-center text-muted small px-2">
                    +{{ createCmigModal.pictures.length - 8 }} fotos
                  </span>
                </div>
              </div>

              <hr class="my-2" />

              <!-- Identificação -->
              <p class="font-weight-bold small text-uppercase text-muted mb-2">Identificação</p>
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
                <div class="col-md-6 form-group">
                  <label>Título <span class="text-danger">*</span></label>
                  <input v-model="createCmigForm.title" class="form-control" required />
                </div>
                <div class="col-md-3 form-group">
                  <label>Marca</label>
                  <input v-model="createCmigForm.brand" class="form-control" />
                </div>
                <div class="col-md-3 form-group">
                  <label>Modelo</label>
                  <input v-model="createCmigForm.model" class="form-control" />
                </div>
              </div>
              <div class="row">
                <div class="col-md-8 form-group">
                  <label>Categoria</label>
                  <input v-model="createCmigForm.category_name" class="form-control" placeholder="Nome da categoria" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Video ID</label>
                  <input v-model="createCmigForm.video_id" class="form-control" placeholder="ID do vídeo" />
                </div>
              </div>

              <hr class="my-2" />

              <!-- Preço e Estoque -->
              <p class="font-weight-bold small text-uppercase text-muted mb-2">Preço e Estoque</p>
              <div class="row">
                <div class="col-md-4 form-group">
                  <label>Preço de Venda (R$)</label>
                  <input v-model="createCmigForm.sale_price" type="number" step="0.01" min="0" class="form-control" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Custo (R$)</label>
                  <input v-model="createCmigForm.cost_price" type="number" step="0.01" min="0" class="form-control" />
                </div>
                <div class="col-md-4 form-group">
                  <label>Qtd. Estoque</label>
                  <input v-model="createCmigForm.stock_quantity" type="number" min="0" class="form-control" />
                </div>
              </div>

              <hr class="my-2" />

              <!-- Descrição -->
              <p class="font-weight-bold small text-uppercase text-muted mb-2">Descrição</p>
              <div class="form-group">
                <textarea v-model="createCmigForm.description" class="form-control" rows="4" placeholder="Descrição do produto..."></textarea>
              </div>

              <hr class="my-2" />

              <!-- Dimensões -->
              <p class="font-weight-bold small text-uppercase text-muted mb-2">Dimensões e Peso</p>
              <div class="row">
                <div class="col-md-3 form-group">
                  <label>Peso (kg)</label>
                  <input v-model="createCmigForm.weight_kg" type="number" step="0.001" min="0" class="form-control" />
                </div>
                <div class="col-md-3 form-group">
                  <label>Altura (cm)</label>
                  <input v-model="createCmigForm.height_cm" type="number" step="0.01" min="0" class="form-control" />
                </div>
                <div class="col-md-3 form-group">
                  <label>Largura (cm)</label>
                  <input v-model="createCmigForm.width_cm" type="number" step="0.01" min="0" class="form-control" />
                </div>
                <div class="col-md-3 form-group">
                  <label>Comprimento (cm)</label>
                  <input v-model="createCmigForm.length_cm" type="number" step="0.01" min="0" class="form-control" />
                </div>
              </div>

              <hr class="my-2" />

              <!-- Fiscal -->
              <p class="font-weight-bold small text-uppercase text-muted mb-2">Fiscal</p>
              <div class="row">
                <div class="col-md-4 form-group">
                  <label>NCM</label>
                  <input v-model="createCmigForm.ncm" class="form-control" maxlength="8" placeholder="00000000" />
                </div>
                <div class="col-md-4 form-group">
                  <label>CEST</label>
                  <input v-model="createCmigForm.cest" class="form-control" maxlength="7" placeholder="0000000" />
                </div>
                <div class="col-md-4 form-group">
                  <label>EAN / GTIN</label>
                  <input v-model="createCmigForm.ean" class="form-control" maxlength="14" placeholder="0000000000000" />
                </div>
              </div>

              <!-- Variantes -->
              <template v-if="createCmigModal.variants.length">
                <hr class="my-2" />
                <p class="font-weight-bold small text-uppercase text-muted mb-2">
                  <i class="fas fa-layer-group mr-1"></i>
                  Variantes — {{ createCmigModal.variants.length }} serão criadas automaticamente
                </p>
                <div class="table-responsive">
                  <table class="table table-sm table-bordered mb-0">
                    <thead class="thead-light">
                      <tr>
                        <th>SKU</th>
                        <th>Estoque</th>
                        <th>Preço</th>
                        <th>Atributos</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(v, i) in createCmigModal.variants" :key="i">
                        <td class="text-monospace small">{{ v.sku }}</td>
                        <td>{{ v.available_quantity }}</td>
                        <td>{{ v.price != null ? 'R$ ' + Number(v.price).toFixed(2) : '—' }}</td>
                        <td>
                          <span v-for="(a, ai) in v.attrs" :key="ai" class="badge badge-secondary mr-1">
                            {{ a.name }}: {{ a.value }}
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </template>
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

    <!-- Modal: Fotos do Anúncio -->
    <div v-if="photosModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.7)" @click.self="photosModal.show = false">
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-images mr-2"></i>
              Fotos — {{ photosModal.listing?.title_override }}
            </h5>
            <button type="button" class="close" @click="photosModal.show = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="photosModal.photos.length === 0" class="text-center text-muted py-4">
              Nenhuma foto disponível.
            </div>
            <div v-else class="d-flex flex-wrap" style="gap:10px">
              <div v-for="(photo, i) in photosModal.photos" :key="photo.id || i"
                   class="position-relative" style="cursor:pointer"
                   @click="photosModal.zoomed = photo.url">
                <img :src="photo.url" style="width:160px;height:160px;object-fit:cover;border-radius:6px;border:2px solid #dee2e6" />
                <span class="badge badge-dark position-absolute" style="bottom:6px;left:6px;font-size:10px">{{ i + 1 }}</span>
              </div>
            </div>
            <!-- Zoom -->
            <div v-if="photosModal.zoomed" class="text-center mt-3">
              <img :src="photosModal.zoomed" style="max-width:100%;max-height:60vh;border-radius:6px;border:2px solid #007bff" />
              <div class="mt-1">
                <a :href="photosModal.zoomed" target="_blank" class="small text-muted">Abrir em nova aba</a>
                <button class="btn btn-xs btn-outline-secondary ml-3" @click="photosModal.zoomed = null">Fechar zoom</button>
              </div>
            </div>
          </div>
          <div class="modal-footer justify-content-between">
            <small class="text-muted">{{ photosModal.photos.length }} foto(s)</small>
            <button class="btn btn-secondary" @click="photosModal.show = false">Fechar</button>
          </div>
        </div>
      </div>
    </div>

  </div>

  <!-- Preview hover wizard photos -->
  <Teleport to="body">
    <div
      v-if="wizardImgPreview.show"
      style="position:fixed;z-index:9999;pointer-events:none;border-radius:8px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5);background:#111"
      :style="{ left: wizardImgPreview.left + 'px', top: wizardImgPreview.top + 'px' }"
    >
      <img :src="wizardImgPreview.src" style="width:300px;height:300px;object-fit:contain;display:block" />
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const toast = useToast()

const accounts = ref([])
const selectedAccountId = ref('')
const anuncios = ref([])
const loading = ref(false)
const importing = ref(false)
const syncingStock = ref(false)
const filterVinculo = ref('all')
const filterStatus = ref('published')
const statsBar = ref(null)
const loadingStats = ref(false)
const importResult = ref(null)
const cmigs = ref([])

const statusTabs = [
  { key: 'all',       label: 'Todos' },
  { key: 'published', label: 'Ativos' },
  { key: 'paused',    label: 'Pausados' },
  { key: 'draft',     label: 'Em revisão' },
  { key: 'closed',    label: 'Finalizados' },
]

const selectedAccount = computed(() => accounts.value.find(a => a.id === selectedAccountId.value))
const selectedAccountPlatform = computed(() => selectedAccount.value?.platform || '')

const filteredAnuncios = computed(() => {
  let list = anuncios.value
  if (filterVinculo.value === 'linked')   list = list.filter(a => a.is_linked)
  if (filterVinculo.value === 'unlinked') list = list.filter(a => !a.is_linked)
  if (filterStatus.value !== 'all')       list = list.filter(a => a.status === filterStatus.value)
  return list
})

// ══════════════════════════════════════════════════
// WIZARD
// ══════════════════════════════════════════════════

const wizardTabs = ['Produto', 'Anúncio', 'Categoria', 'Fotos', 'Descrição & Envio']
const wizardStep = ref(1)
const wizard = ref({ show: false, isEdit: false, listingId: null, saving: false, error: '', originalSku: '' })

const wf = ref(defaultWizardForm())

function defaultWizardForm() {
  return {
    product_type: 'cmig',
    product_id: null,
    selectedProduct: null,
    title_override: '',
    sale_price: null,
    listing_type: 'gold_special',
    available_quantity: 1,
    item_condition: 'new',
    platform_item_id: '',
    sku: '',
    mode: 'create',
    category_id: '',
    category_name: '',
    attributes: [],
    pictures: [],
    description_override: '',
    video_id: '',
    shipping_mode:    'me2',
    free_shipping:    false,
    stock_mode:       'product',
    fixed_quantity:   1,
    keep_stock_fixed: false,
    warranty_type:    '',
    warranty_time:    '',
    weight_kg:        '',
    height_cm:        '',
    width_cm:         '',
    length_cm:        '',
  }
}

// Produto search
const productSearch = ref('')
const cmigProductList = ref([])
const pgProductList = ref([])

const filteredProductList = computed(() => {
  const list = wf.value.product_type === 'cmig' ? cmigProductList.value : pgProductList.value
  const q = productSearch.value.toLowerCase()
  if (!q) return list
  return list.filter(p => (p.title || '').toLowerCase().includes(q) || (p.sku_cmig || p.sku || '').toLowerCase().includes(q))
})

const productImages = computed(() => {
  const p = wf.value.selectedProduct
  if (!p) return []
  const imgs = p.images || []
  return imgs.map(i => i.url || i).filter(Boolean)
})

function filterProducts() { /* computed filters reactively */ }

function selectProduct(p) {
  wf.value.product_id = p.id
  wf.value.selectedProduct = p
  if (!wf.value.title_override) {
    wf.value.title_override = (p.title || '').substring(0, 60)
  }
  // Auto-populate pictures from product images
  if (wf.value.pictures.length === 0 && p.images?.length) {
    wf.value.pictures = p.images.slice(0, 12).map(i => i.url || i).filter(Boolean)
  }
}

const refreshingProductImages = ref(false)

async function refreshProductImages() {
  const p = wf.value.selectedProduct
  if (!p || !p.id) return
  refreshingProductImages.value = true
  try {
    let fresh = null
    if (wf.value.product_type === 'cmig') {
      const cmigId = p.cmig_id
      if (!cmigId) throw new Error('Produto CMIG sem cmig_id — não foi possível atualizar.')
      const { data } = await api.get(`/cmigs/${cmigId}/products/${p.id}`)
      fresh = data
      // atualiza também a lista do wizard
      const idx = cmigProductList.value.findIndex(x => x.id === p.id)
      if (idx >= 0) cmigProductList.value[idx] = data
    } else if (wf.value.product_type === 'pg') {
      const { data } = await api.get(`/pg/${p.id}`)
      fresh = data
      const idx = pgProductList.value.findIndex(x => x.id === p.id)
      if (idx >= 0) pgProductList.value[idx] = data
    }
    if (fresh) {
      const prevUrls = (p.images || []).map(i => i.url || i).filter(Boolean)
      wf.value.selectedProduct = fresh
      const newUrls = (fresh.images || []).map(i => i.url || i).filter(Boolean)
      const added = newUrls.filter(u => !prevUrls.includes(u))
      if (added.length === 0) {
        toast.info('Nenhuma foto nova no produto vinculado.')
      } else {
        toast.success(`${added.length} foto${added.length === 1 ? '' : 's'} nova${added.length === 1 ? '' : 's'} disponível${added.length === 1 ? '' : 'is'} pra seleção.`)
      }
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao atualizar fotos do produto.')
  } finally {
    refreshingProductImages.value = false
  }
}

// Category search
const categorySearch = ref('')
const categoryResults = ref([])
const catLoading = ref(false)
const categoryAttributes = ref([])
const attrValues = ref({})
const savedAttrNames = ref({})   // { attr_id: display_name } para atributos já existentes
const attrLoading = ref(false)
const categoryEditMode = ref(false)  // exibe campo de busca de categoria somente qdo true

// Atributos que existem no anúncio mas não estão na lista de atributos ML da categoria
const extraCategoryAttrs = computed(() => {
  const catIds = new Set(categoryAttributes.value.map(a => a.id))
  return Object.keys(attrValues.value)
    .filter(id => !catIds.has(id) && attrValues.value[id])
    .map(id => ({ id, name: savedAttrNames.value[id] || id }))
})

// Dados fiscais do anúncio
const wizardFiscal = ref({ ncm: '', ean: '', cest: '', gtin: '' })

let catDebounceTimer = null
function debouncedCategorySearch() {
  clearTimeout(catDebounceTimer)
  catDebounceTimer = setTimeout(searchCategories, 400)
}

async function searchCategories() {
  if (!categorySearch.value.trim()) return
  catLoading.value = true
  try {
    const { data } = await api.get(`/anuncios/categories/search?q=${encodeURIComponent(categorySearch.value)}`)
    categoryResults.value = Array.isArray(data) ? data.slice(0, 20) : []
  } catch {
    categoryResults.value = []
  } finally {
    catLoading.value = false
  }
}

async function selectCategory(c) {
  wf.value.category_id = c.id
  wf.value.category_name = c.name
  categoryResults.value = []
  attrValues.value = {}
  attrLoading.value = true
  try {
    const { data } = await api.get(`/anuncios/categories/${c.id}/attributes`)
    categoryAttributes.value = Array.isArray(data) ? data : []
  } catch {
    categoryAttributes.value = []
  } finally {
    attrLoading.value = false
  }
}

// Photos
const extraImageUrl = ref('')

function toggleImage(url) {
  if (wf.value.pictures.includes(url)) {
    wf.value.pictures = wf.value.pictures.filter(u => u !== url)
  } else if (wf.value.pictures.length < 12) {
    wf.value.pictures.push(url)
  }
}

function isImageSelected(url) {
  return wf.value.pictures.includes(url)
}

function addExtraImage() {
  if (extraImageUrl.value && !wf.value.pictures.includes(extraImageUrl.value) && wf.value.pictures.length < 12) {
    wf.value.pictures.push(extraImageUrl.value)
    extraImageUrl.value = ''
  }
}

function removeImage(i) {
  wf.value.pictures.splice(i, 1)
}

const wizardImgPreview = ref({ show: false, src: '', x: 0, y: 0 })
let wizardImgTimer = null
function startWizardPreview(event, src) {
  clearTimeout(wizardImgTimer)
  const rect = event.currentTarget.getBoundingClientRect()
  wizardImgTimer = setTimeout(() => {
    const PW = 300, PH = 300, M = 10
    const vw = window.innerWidth, vh = window.innerHeight
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    let left, top
    if (rect.bottom + PH + M <= vh) {
      top  = rect.bottom + M
      left = Math.min(Math.max(cx - PW / 2, M), vw - PW - M)
    } else if (rect.top - PH - M >= 0) {
      top  = rect.top - PH - M
      left = Math.min(Math.max(cx - PW / 2, M), vw - PW - M)
    } else if (rect.right + PW + M <= vw) {
      left = rect.right + M
      top  = Math.min(Math.max(cy - PH / 2, M), vh - PH - M)
    } else {
      left = Math.max(rect.left - PW - M, M)
      top  = Math.min(Math.max(cy - PH / 2, M), vh - PH - M)
    }
    wizardImgPreview.value = { show: true, src, left, top }
  }, 1000)
}
function stopWizardPreview() {
  clearTimeout(wizardImgTimer)
  wizardImgPreview.value.show = false
}

function moveImage(i, dir) {
  const pics = wf.value.pictures
  const target = i + dir
  if (target < 0 || target >= pics.length) return
  ;[pics[i], pics[target]] = [pics[target], pics[i]]
}

async function openWizard(listing) {
  wizardStep.value = 1
  wizard.value = { show: true, isEdit: !!listing, listingId: listing?.id || null, saving: false, error: '', originalSku: listing?.sku || '' }
  wf.value = defaultWizardForm()
  categorySearch.value = ''
  categoryResults.value = []
  categoryAttributes.value = []
  attrValues.value = {}
  savedAttrNames.value = {}
  wizardFiscal.value = { ncm: '', ean: '', cest: '', gtin: '' }
  categoryEditMode.value = !listing  // edit mode: categoria só muda ao clicar; novo: já abre campo
  productSearch.value = ''
  extraImageUrl.value = ''

  await Promise.all([loadCmigProductsForWizard(), loadPgProductsForWizard()])

  if (listing) {
    // Pre-fill from existing listing
    wf.value.title_override = listing.title_override || ''
    wf.value.sale_price = listing.sale_price
    wf.value.listing_type = listing.listing_type || 'gold_special'
    wf.value.available_quantity = listing.available_quantity || 1
    wf.value.stock_mode         = listing.stock_mode       || 'product'
    wf.value.fixed_quantity     = listing.fixed_quantity   || 1
    wf.value.keep_stock_fixed   = !!listing.keep_stock_fixed
    wf.value.item_condition = listing.item_condition || 'new'
    wf.value.platform_item_id = listing.platform_item_id || ''
    wf.value.category_id = listing.category_id || ''
    wf.value.description_override = listing.description_override || ''
    wf.value.video_id = listing.video_id || ''
    wf.value.shipping_mode = listing.shipping_mode || 'me2'
    wf.value.free_shipping = !!listing.free_shipping
    wf.value.warranty_type = listing.warranty_type || ''
    wf.value.warranty_time = listing.warranty_time || ''
    wf.value.sku       = listing.sku || ''
    wf.value.weight_kg = listing.weight_kg != null ? listing.weight_kg : ''
    wf.value.height_cm = listing.height_cm != null ? listing.height_cm : ''
    wf.value.width_cm  = listing.width_cm  != null ? listing.width_cm  : ''
    wf.value.length_cm = listing.length_cm != null ? listing.length_cm : ''
    // Pre-popular dados fiscais
    wizardFiscal.value = { ncm: '', ean: '', cest: '', gtin: '' }
    if (listing.fiscal_json) {
      try {
        const f = JSON.parse(listing.fiscal_json)
        wizardFiscal.value.ncm  = f.ncm  || f.NCM  || ''
        // EAN e GTIN são a mesma coisa — ML frequentemente retorna como "gtin" no import
        wizardFiscal.value.ean  = f.ean  || f.EAN  || f.gtin || f.GTIN || ''
        wizardFiscal.value.cest = f.cest || f.CEST || ''
        wizardFiscal.value.gtin = f.gtin || f.GTIN || f.ean  || f.EAN  || ''
      } catch { /* ignore */ }
    }
    // Fallback: busca NCM/EAN/CEST em attributes_json caso não estejam em fiscal_json
    if (listing.attributes_json && (!wizardFiscal.value.ncm || !wizardFiscal.value.ean || !wizardFiscal.value.cest)) {
      try {
        const attrs = JSON.parse(listing.attributes_json)
        for (const a of attrs) {
          const id  = (a.id || '').toUpperCase()
          const val = a.value || a.value_name || ''
          if (!val) continue
          if (id === 'NCM'  && !wizardFiscal.value.ncm)  wizardFiscal.value.ncm  = val
          if ((id === 'EAN' || id === 'GTIN') && !wizardFiscal.value.ean) wizardFiscal.value.ean = val
          if (id === 'CEST' && !wizardFiscal.value.cest) wizardFiscal.value.cest = val
        }
      } catch { /* ignore */ }
    }
    if (listing.cmig_product) {
      wf.value.product_type = 'cmig'
      wf.value.product_id = listing.cmig_product.id
      wf.value.selectedProduct = cmigProductList.value.find(p => p.id === listing.cmig_product.id) || listing.cmig_product
    } else if (listing.catalog_product) {
      wf.value.product_type = 'pg'
      wf.value.product_id = listing.catalog_product.id
      wf.value.selectedProduct = pgProductList.value.find(p => p.id === listing.catalog_product.id) || listing.catalog_product
    }
    // Pre-popular fotos do anúncio
    if (listing.pictures_json) {
      try {
        const pics = JSON.parse(listing.pictures_json)
        wf.value.pictures = pics.map(p => p.url || p).filter(Boolean).slice(0, 12)
      } catch { /* ignore */ }
    }
    if (listing.category_id) {
      wf.value.category_name = listing.category_name || listing.category_id
      fetchCategoryPath(listing.category_id)  // carrega breadcrumb no mapa compartilhado
      try {
        const { data } = await api.get(`/anuncios/categories/${listing.category_id}/attributes`)
        categoryAttributes.value = Array.isArray(data) ? data : []
        if (listing.attributes_json) {
          try {
            const saved = JSON.parse(listing.attributes_json)
            for (const a of saved) {
              if (a.id) {
                attrValues.value[a.id] = a.value ?? a.value_name ?? ''
                if (a.name) savedAttrNames.value[a.id] = a.name
              }
            }
          } catch { /* ignore */ }
        }
      } catch { /* ignore */ }
    }
  }
}

async function loadCmigProductsForWizard() {
  try {
    const { data } = await api.get('/cmig-products')
    cmigProductList.value = Array.isArray(data) ? data : []
  } catch { cmigProductList.value = [] }
}

async function loadPgProductsForWizard() {
  try {
    const { data } = await api.get('/catalog')
    pgProductList.value = Array.isArray(data?.items || data) ? (data?.items || data) : []
  } catch { pgProductList.value = [] }
}

async function saveWizard() {
  wizard.value.saving = true
  wizard.value.error = ''
  try {
    if (!wf.value.sale_price) throw new Error('Preço de venda é obrigatório (Aba 2)')
    if (!wf.value.title_override) throw new Error('Título é obrigatório (Aba 2)')

    // Build attributes array from attrValues
    const attributes = categoryAttributes.value
      .filter(a => attrValues.value[a.id])
      .map(a => ({ id: a.id, value_name: attrValues.value[a.id] }))

    const payload = {
      account_id: selectedAccountId.value,
      title_override: wf.value.title_override,
      sale_price: parseFloat(wf.value.sale_price),
      listing_type: wf.value.listing_type,
      stock_mode:       wf.value.stock_mode,
      fixed_quantity:   wf.value.stock_mode === 'fixed' ? Number(wf.value.fixed_quantity) : undefined,
      keep_stock_fixed: wf.value.stock_mode === 'fixed' ? wf.value.keep_stock_fixed : undefined,
      item_condition: wf.value.item_condition,
      platform_item_id: wf.value.platform_item_id || null,
      sku: wf.value.sku || null,
      category_id: wf.value.category_id || null,
      description_override: wf.value.description_override || null,
      attributes_json: attributes.length ? JSON.stringify(attributes) : null,
      attributes,
      pictures: wf.value.pictures,
      warranty_type: wf.value.warranty_type || null,
      warranty_time: wf.value.warranty_time || null,
      shipping_mode: wf.value.shipping_mode,
      free_shipping: wf.value.free_shipping,
      video_id: wf.value.video_id || null,
      weight_kg: wf.value.weight_kg !== '' ? parseFloat(wf.value.weight_kg) || null : null,
      height_cm: wf.value.height_cm !== '' ? parseFloat(wf.value.height_cm) || null : null,
      width_cm:  wf.value.width_cm  !== '' ? parseFloat(wf.value.width_cm)  || null : null,
      length_cm: wf.value.length_cm !== '' ? parseFloat(wf.value.length_cm) || null : null,
      fiscal_json: (wizardFiscal.value.ncm || wizardFiscal.value.ean || wizardFiscal.value.cest)
        ? JSON.stringify({ ncm: wizardFiscal.value.ncm || null, ean: wizardFiscal.value.ean || null, cest: wizardFiscal.value.cest || null, gtin: wizardFiscal.value.gtin || null })
        : undefined,
      mode: wf.value.mode,
    }
    if (wf.value.product_type === 'cmig') {
      payload.cmig_product_id = wf.value.product_id
    } else {
      payload.catalog_product_id = wf.value.product_id
    }

    if (wizard.value.isEdit) {
      // Se o SKU mudou em edição, perguntar sobre cascata pro CMIG/PG vinculado
      const skuChanged = wizard.value.originalSku && payload.sku && payload.sku !== wizard.value.originalSku
      if (skuChanged) {
        const linkLabel = wf.value.product_type === 'cmig' ? 'produto CMIG' : 'produto PG'
        payload.cascade_sku_to_linked = confirm(
          `Você alterou o SKU de "${wizard.value.originalSku}" para "${payload.sku}".\n\n` +
          `Deseja propagar também o novo SKU para o ${linkLabel} vinculado?`
        )
      }
      const { data } = await api.put(`/anuncios/${wizard.value.listingId}`, payload)
      if (data?._cascade && (data._cascade.cmig_updated || data._cascade.pg_updated)) {
        const where = data._cascade.cmig_updated ? 'CMIG vinculado' : 'PG vinculado'
        toast.success(`Anúncio atualizado. SKU propagado para o ${where}.`)
      } else if (data?.ml_sync_warning) {
        toast.success('Anúncio salvo no sistema.')
        toast.error(`Aviso ML: ${data.ml_sync_warning}`)
      } else if (data?.ml_skipped_fields?.length) {
        toast.success('Anúncio atualizado no Mercado Livre.')
        const labels = {
          pictures: 'fotos', title: 'título', condition: 'condição',
          listing_type_id: 'tipo de anúncio', description: 'descrição',
        }
        const skipped = data.ml_skipped_fields.map(f => labels[f] || f).join(', ')
        toast.warning(`Esses campos não foram alterados no ML (anúncio com vendas ou de catálogo): ${skipped}. Os demais foram salvos.`)
      } else {
        toast.success('Anúncio atualizado e enviado ao Mercado Livre!')
      }
    } else {
      await api.post('/anuncios/publish', payload)
      toast.success('Anúncio publicado!')
    }

    wizard.value.show = false
    await loadAnuncios()
  } catch (e) {
    wizard.value.error = e.message || e.response?.data?.detail || 'Erro ao salvar anúncio'
  } finally {
    wizard.value.saving = false
  }
}

// ══════════════════════════════════════════════════
// Misc modals & actions
// ══════════════════════════════════════════════════

const linkModal = ref({ show: false, listing: null, loading: false, cmig_suggestions: [], pg_suggestions: [] })
const linkSearch = ref('')
const createCmigModal = ref({ show: false, listing: null, saving: false, error: '', pictures: [], variants: [] })
const photosModal = ref({ show: false, listing: null, photos: [], zoomed: null })
const createCmigForm = ref({
  cmig_id: '', sku_cmig: '', title: '', brand: '', model: '',
  category_name: '', description: '', video_id: '',
  sale_price: '', cost_price: '', stock_quantity: 0,
  weight_kg: '', height_cm: '', width_cm: '', length_cm: '',
  ncm: '', cest: '', ean: '',
})

onMounted(async () => {
  await Promise.all([loadAccounts(), loadCmigs()])
})

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    const platformLabel = p => ({ mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[p] || p)
    accounts.value = (Array.isArray(data) ? data : []).map(a => ({ ...a, platform_label: platformLabel(a.platform) }))
  } catch { }
}

async function loadCmigs() {
  try {
    const { data } = await api.get('/cmigs')
    cmigs.value = Array.isArray(data) ? data : []
  } catch { }
}

async function loadAnuncios() {
  if (!selectedAccountId.value) { anuncios.value = []; statsBar.value = null; listingCosts.value = {}; categoryPaths.value = {}; listingPromos.value = {}; return }
  loading.value = true
  listingCosts.value = {}
  categoryPaths.value = {}
  listingPromos.value = {}
  loadingPromos.value = {}
  try {
    const [res] = await Promise.all([
      api.get(`/anuncios?account_id=${selectedAccountId.value}`),
      loadStats(),
    ])
    anuncios.value = Array.isArray(res.data) ? res.data : []
    // Pré-carrega breadcrumbs do BD — elimina Onda 1 para itens já importados
    for (const a of anuncios.value) {
      if (a.category_id && a.category_path_json) {
        try {
          const path = JSON.parse(a.category_path_json)
          if (Array.isArray(path) && path.length) categoryPaths.value[a.category_id] = path
        } catch { /* ignore */ }
      }
    }
    fetchAllCategoryPaths()
  } catch {
    toast.error('Erro ao carregar anúncios')
  } finally {
    loading.value = false
  }
}

async function fetchAllCategoryPaths() {
  const CONCURRENCY = 5
  // Onda 1: apenas categorias ainda sem path carregado do BD
  const withCat = anuncios.value.filter(a => a.category_id && !categoryPaths.value[a.category_id])
  for (let i = 0; i < withCat.length; i += CONCURRENCY) {
    await Promise.all(withCat.slice(i, i + CONCURRENCY).map(a => fetchCategoryPath(a.category_id)))
  }
  // Fetch live costs for all eligible listings (fresh data sempre sobrepõe cache do BD)
  const withCosts = anuncios.value.filter(a => a.category_id && a.sale_price)
  for (let i = 0; i < withCosts.length; i += CONCURRENCY) {
    await Promise.all(withCosts.slice(i, i + CONCURRENCY).map(a => fetchCost(a)))
  }
}

async function loadStats() {
  if (!selectedAccountId.value) return
  loadingStats.value = true
  try {
    const { data } = await api.get(`/anuncios/stats?account_id=${selectedAccountId.value}`)
    statsBar.value = data
  } catch { statsBar.value = null }
  finally { loadingStats.value = false }
}

async function importAnuncios() {
  if (!selectedAccountId.value) return
  importing.value = true
  try {
    const { data } = await api.post(`/anuncios/import/${selectedAccountId.value}`)
    importResult.value = data
    await loadAnuncios()
  } catch (e) {
    const detail = e.response?.data?.detail || 'Erro ao importar anúncios'
    if (e.response?.status === 409) {
      alert(`Conta incorreta!\n\n${detail}`)
    } else {
      toast.error(detail)
    }
  } finally {
    importing.value = false
  }
}

async function syncStock() {
  if (!selectedAccountId.value) return
  syncingStock.value = true
  try {
    const { data } = await api.post('/anuncios/sync-stock', { account_id: selectedAccountId.value })
    const { updated, skipped, errors } = data
    if (errors > 0) {
      toast.warning(`Estoque sincronizado: ${updated} atualizados, ${skipped} ignorados, ${errors} com erro.`)
    } else {
      toast.success(`Estoque sincronizado: ${updated} anúncio(s) atualizado(s), ${skipped} ignorado(s).`)
    }
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar estoque.')
  } finally {
    syncingStock.value = false
  }
}

async function deleteAnuncioSistema(listing) {
  if (!confirm(`Excluir "${listing.title_override}" apenas do sistema?\n\nO anúncio continuará publicado no Marketplace.`)) return
  try {
    await api.delete(`/anuncios/${listing.id}`)
    anuncios.value = anuncios.value.filter(a => a.id !== listing.id)
    toast.success('Anúncio removido do sistema')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir anúncio')
  }
}

async function deleteAnuncioMarketplace(listing) {
  if (!confirm(`Excluir "${listing.title_override}" do sistema E do Marketplace?\n\nEsta ação fechará o anúncio no Mercado Livre e não pode ser desfeita.`)) return
  try {
    await api.delete(`/anuncios/${listing.id}/marketplace`)
    anuncios.value = anuncios.value.filter(a => a.id !== listing.id)
    toast.success('Anúncio removido do sistema e fechado no Marketplace')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir anúncio no Marketplace')
  }
}

function setFilter(f) { filterVinculo.value = f }

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
      const matches = p => (p.title || '').toLowerCase().includes(q) || (p.sku || '').toLowerCase().includes(q)
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
  } catch { toast.error('Erro ao remover vínculo') }
}

function openCreateCmigModal(listing) {
  // Dados fiscais: tenta fiscal_json primeiro, depois attributes_json como fallback
  const _FISCAL_MAP = { NCM: 'ncm', CEST: 'cest', GTIN: 'gtin', EAN: 'ean' }
  let fiscal = {}
  let brand = ''
  let model = ''
  try { fiscal = JSON.parse(listing.fiscal_json || '{}') } catch {}
  try {
    const attrs = JSON.parse(listing.attributes_json || '[]')
    for (const a of attrs) {
      const id = (a.id || '').toUpperCase()
      const key = _FISCAL_MAP[id]
      if (key && !fiscal[key] && a.value) fiscal[key] = String(a.value)
      if (id === 'BRAND' && a.value) brand = String(a.value)
      if (id === 'MODEL' && a.value) model = String(a.value)
    }
  } catch {}

  // Normaliza NCM e CEST removendo pontos/hífens
  const normNcm  = (v) => v ? v.replace(/[.\-]/g, '').slice(0, 8) : ''
  const normCest = (v) => v ? v.replace(/[.\-]/g, '').slice(0, 7) : ''

  let pictures = []
  try { pictures = JSON.parse(listing.pictures_json || '[]') } catch {}

  let variants = []
  try {
    const rawVars = JSON.parse(listing.variations_json || '[]')
    variants = rawVars.map((v, idx) => {
      const attrs = v.attributes || []
      const sellerSku = attrs.find(a => a.id === 'SELLER_SKU')
      const sku = (sellerSku?.value) || `${listing.sku || 'VAR'}_${idx + 1}`
      const displayAttrs = attrs.filter(a => a.id !== 'SELLER_SKU').map(a => ({ name: a.name, value: a.value }))
      return { sku, price: v.price, available_quantity: v.available_quantity, attrs: displayAttrs }
    })
  } catch {}

  createCmigModal.value = { show: true, listing, saving: false, error: '', pictures, variants }
  createCmigForm.value = {
    cmig_id:        selectedAccount.value?.cmig_id || '',
    sku_cmig:       listing.sku || '',
    title:          listing.title_override || '',
    brand:          brand,
    model:          model,
    category_name:  listing.category_name || '',
    description:    listing.description_override || '',
    video_id:       listing.video_id || '',
    sale_price:     listing.sale_price || '',
    cost_price:     '',
    stock_quantity: listing.available_quantity ?? 0,
    weight_kg:      listing.weight_kg || '',
    height_cm:      listing.height_cm || '',
    width_cm:       listing.width_cm || '',
    length_cm:      listing.length_cm || '',
    ncm:            normNcm(fiscal.ncm),
    cest:           normCest(fiscal.cest),
    ean:            fiscal.ean || fiscal.gtin || '',
  }
}

async function doCreateCmigProduct() {
  createCmigModal.value.saving = true
  createCmigModal.value.error = ''
  const f = createCmigForm.value
  try {
    const res = await api.post(`/anuncios/${createCmigModal.value.listing.id}/create-cmig-product`, {
      ...f,
      sale_price:     f.sale_price     ? parseFloat(f.sale_price)     : null,
      cost_price:     f.cost_price     ? parseFloat(f.cost_price)     : null,
      stock_quantity: f.stock_quantity !== '' ? parseInt(f.stock_quantity) : null,
      weight_kg:      f.weight_kg      ? parseFloat(f.weight_kg)      : null,
      height_cm:      f.height_cm      ? parseFloat(f.height_cm)      : null,
      width_cm:       f.width_cm       ? parseFloat(f.width_cm)       : null,
      length_cm:      f.length_cm      ? parseFloat(f.length_cm)      : null,
    })
    const vCount = res.data?.product?.variants_created
    const msg = vCount ? `Produto CMIG criado com ${vCount} variante(s)!` : 'Produto CMIG criado e vinculado!'
    toast.success(msg)
    createCmigModal.value.show = false
    await loadAnuncios()
  } catch (e) {
    createCmigModal.value.error = e.response?.data?.detail || 'Erro ao criar produto'
  } finally {
    createCmigModal.value.saving = false
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

async function reactivateAnuncio(listing) {
  if (!confirm(`Reativar o anúncio "${listing.title_override}"?`)) return
  try {
    await api.post(`/anuncios/${listing.id}/reactivate`)
    toast.success('Anúncio reativado!')
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao reativar anúncio')
  }
}

async function syncToMl(listing) {
  try {
    await api.post(`/anuncios/${listing.id}/sync-to-ml`)
    await api.post(`/anuncios/${listing.id}/refresh-costs`).catch(() => {})
    toast.success('Anúncio sincronizado com o ML!')
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar com ML')
  }
}

function listingBrand(listing) {
  const linked = listing.cmig_product || listing.catalog_product
  if (linked?.brand) return linked.brand
  if (!listing.attributes_json) return null
  try {
    const attrs = JSON.parse(listing.attributes_json)
    const b = attrs.find(a => (a.id || '').toUpperCase() === 'BRAND')
    return b?.value || b?.value_name || null
  } catch { return null }
}

function timeSince(isoDate) {
  if (!isoDate) return ''
  const diffH = Math.floor((Date.now() - new Date(isoDate).getTime()) / 3600000)
  if (diffH === 0) return 'agora'
  if (diffH === 1) return '1h atrás'
  if (diffH < 24)  return `${diffH}h atrás`
  return `${Math.floor(diffH / 24)}d atrás`
}

function formatCurrency(v) {
  if (!v) return '—'
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

function statusBadgeClass(s) {
  return {
    published: 'badge badge-success',
    paused:    'badge badge-warning',
    draft:     'badge badge-secondary',
    closed:    'badge badge-danger',
    error:     'badge badge-danger',
  }[s] || 'badge badge-secondary'
}

function statusLabel(s) {
  return { published: 'Ativo', paused: 'Pausado', draft: 'Em revisão', closed: 'Finalizado', error: 'Erro' }[s] || s
}

function listingTypeLabel(t) {
  return { gold_special: 'Clássico', gold_pro: 'Premium', gold_premium: 'Premium', silver: 'Prata', bronze: 'Bronze', free: 'Grátis' }[t] || t || ''
}

function listingTypeBadge(t) {
  return {
    gold_special:  'badge badge-info',
    gold_pro:      'badge badge-primary',
    gold_premium:  'badge badge-primary',
    silver:        'badge badge-secondary',
    bronze:        'badge badge-secondary',
    free:          'badge badge-light text-dark border',
  }[t] || 'badge badge-secondary'
}

const _ML_FEES = { gold_special: 11, gold_pro: 15, gold_premium: 15, silver: 8, bronze: 6, free: 0 }

function listingFees(listing) {
  const price = Number(listing.sale_price) || 0
  const rate = _ML_FEES[listing.listing_type] ?? 11
  return { rate, feeAmt: (price * rate / 100).toFixed(2) }
}

const listingCosts  = ref({})
const loadingCosts  = ref({})
const categoryPaths = ref({})
const listingPromos = ref({})
const loadingPromos = ref({})

function listingThumb(a) {
  if (a.thumbnail) return a.thumbnail
  const imgs = a.cmig_product?.images || a.catalog_product?.images || []
  const first = imgs[0]
  if (!first) return null
  return first.url || first
}

function hasDimensions(a) {
  return !!(a.weight_kg && a.height_cm && a.width_cm && a.length_cm)
}

async function forceRefreshCosts(listing) {
  const id = listing.id
  loadingCosts.value = { ...loadingCosts.value, [id]: true }
  try {
    // Limpa o cache local primeiro pra forçar nova chamada à API
    const novo = { ...listingCosts.value }
    delete novo[id]
    listingCosts.value = novo
    // Reseta cache do backend
    await api.post(`/anuncios/${id}/refresh-costs`).catch(() => {})
    // Refetcha
    const { data } = await api.get(`/anuncios/${id}/costs`)
    listingCosts.value = { ...listingCosts.value, [id]: data }
    if (data.shipping_cost > 0) {
      toast.success(`Frete recalculado: R$ ${data.shipping_cost.toFixed(2)}`)
    } else {
      toast.warning('ML ainda retornou frete = 0. Pode ser política do ML para este modo de envio ou peso.')
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao recalcular custos.')
  } finally {
    loadingCosts.value = { ...loadingCosts.value, [id]: false }
  }
}

async function fetchCost(listing) {
  const id = listing.id
  if (loadingCosts.value[id] || listingCosts.value[id]) return
  loadingCosts.value = { ...loadingCosts.value, [id]: true }
  try {
    const { data } = await api.get(`/anuncios/${id}/costs`)
    listingCosts.value = { ...listingCosts.value, [id]: data }
    // Promo já vem junto — sem fetch separado
    listingPromos.value = { ...listingPromos.value, [id]: {
      has_promotion:  data.has_promotion  ?? false,
      sale_price:     data.sale_price     ?? null,
      regular_price:  data.regular_price  ?? null,
      promotion_type: data.promotion_type ?? null,
      discount_pct:   data.discount_pct   ?? null,
    }}
    // Propaga ajuste automático e preço atualizado para o objeto do listing
    listing.has_auto_price_adj = data.has_auto_price_adj ?? false
    if (data.price && data.price > 0) listing.sale_price = data.price
    if (data.regular_price)  listing.regular_price = data.regular_price
    if (data.promo_type !== undefined) listing.promo_type = data.promo_type ?? null
  } catch { /* silencia — mantém estimativa */ }
  finally { loadingCosts.value = { ...loadingCosts.value, [id]: false } }
}

async function fetchCategoryPath(categoryId) {
  if (!categoryId || categoryPaths.value[categoryId]) return
  try {
    const { data } = await api.get(`/anuncios/categories/${categoryId}`)
    categoryPaths.value = { ...categoryPaths.value, [categoryId]: data.path_from_root || [] }
  } catch { /* silencia */ }
}

async function fetchSalePrice(listing) {
  const id = listing.id
  if (listingPromos.value[id]) return
  try {
    const { data } = await api.get(`/anuncios/${id}/sale-price`)
    listingPromos.value = { ...listingPromos.value, [id]: {
      has_promotion:  data.has_promotion  ?? false,
      sale_price:     data.sale_price     ?? null,
      regular_price:  data.regular_price  ?? null,
      promotion_type: data.promotion_type ?? null,
      discount_pct:   data.discount_pct   ?? null,
    }}
  } catch { /* silencia */ }
}

async function fetchAllCosts() {
  const items = anuncios.value.filter(a => a.category_id && a.sale_price)
  const CONCURRENCY = 5
  for (let i = 0; i < items.length; i += CONCURRENCY) {
    const batch = items.slice(i, i + CONCURRENCY)
    await Promise.all([
      ...batch.map(a => fetchCost(a)),
      ...batch.map(a => fetchCategoryPath(a.category_id)),
    ])
  }
}

const PROMO_TYPE_LABEL = {
  DEAL:                    'Campanha',
  MARKETPLACE_CAMPAIGN:    'Campanha ML',
  PRICE_DISCOUNT:          'Desconto',
  LIGHTNING:               'Oferta Relâmpago',
  DOD:                     'Oferta do Dia',
  VOLUME:                  'Vol. Desconto',
  PRE_NEGOTIATED:          'Pré-negociado',
  SELLER_CAMPAIGN:         'Camp. Vendedor',
  SMART:                   'Smart',
  PRICE_MATCHING:          'Preço Competitivo',
  UNHEALTHY_STOCK:         'Liquidação Full',
  SELLER_COUPON_CAMPAIGN:  'Cupom',
}

// Retorna { hasPromo, salePrice, regularPrice, discountPct, promoType }
// Priority 1: BD-cached promo fields (regular_price / promo_type set after import/refresh-costs)
// Priority 2: live listingCosts + listingPromos (fetched by fetchCost)
function promoData(listing) {
  const stored = Number(listing.sale_price) || 0

  // BD-cached
  if (listing.regular_price || listing.promo_type) {
    const regularPrice = Number(listing.regular_price || stored)
    const hasPromo     = !!(listing.promo_type || regularPrice > stored * 1.01)
    return {
      hasPromo,
      salePrice:    stored,
      regularPrice: hasPromo ? regularPrice : stored,
      discountPct:  listing.promo_discount_pct ?? (hasPromo && regularPrice > 0
        ? Math.round((regularPrice - stored) / regularPrice * 1000) / 10
        : null),
      promoType: listing.promo_type ?? null,
    }
  }

  // Live fetch fallback
  const costs = listingCosts.value[listing.id]
  const promo = listingPromos.value[listing.id]
  const realPrice = (costs?.price > 0) ? Number(costs.price)
    : (promo?.sale_price > 0)          ? Number(promo.sale_price)
    : stored

  const promoRegular = promo?.regular_price > 0 ? Number(promo.regular_price) : 0
  const hasPromo = promo?.has_promotion
    || (promoRegular > 0 && promoRegular > stored * 1.01)
    || (realPrice > 0 && stored > 0 && realPrice < stored * 0.99)

  const regularPrice = hasPromo
    ? (promoRegular > stored * 1.01 ? promoRegular : stored)
    : stored

  const discountPct = (hasPromo && regularPrice > 0)
    ? Math.round((regularPrice - realPrice) / regularPrice * 1000) / 10
    : (promo?.discount_pct ?? null)

  return {
    hasPromo,
    salePrice:    realPrice,
    regularPrice,
    discountPct,
    promoType:    promo?.promotion_type ?? null,
  }
}

function effectivePrice(listing) {
  return promoData(listing).salePrice
}

function pricingCalc(listing) {
  const price = effectivePrice(listing)

  // Priority 1: live fetch (sempre mais fresco que o cache do BD)
  const real = listingCosts.value[listing.id]
  if (real) {
    return {
      rate:            real.commission_pct,
      fee:             real.commission_amount.toFixed(2),
      financing_fee:   real.financing_fee,
      fixed_fee:       real.fixed_fee,
      shipping_cost:   real.shipping_cost,
      shipping_detail: real.shipping_detail ?? null,
      margin:          real.net_revenue.toFixed(2),
      marginPct:       real.margin_pct.toFixed(2),
      isReal:          true,
    }
  }

  // Priority 2: BD-cached costs (set after import or refresh-costs)
  if (listing.costs_cached_at) {
    const cachedAtMs = new Date(listing.costs_cached_at).getTime()
    const ageHours   = (Date.now() - cachedAtMs) / (1000 * 60 * 60)
    const isStale    = ageHours > 4   // TTL: 4h
    return {
      rate:            listing.commission_pct ?? 0,
      fee:             Number(listing.commission_amount ?? 0).toFixed(2),
      financing_fee:   0,
      fixed_fee:       0,
      shipping_cost:   listing.shipping_cost ?? 0,
      shipping_detail: null,
      margin:          Number(listing.net_revenue ?? 0).toFixed(2),
      marginPct:       Number(listing.margin_pct ?? 0).toFixed(2),
      isReal:          true,
      isStale,
      cachedAt:        listing.costs_cached_at,
    }
  }

  // Estimativa estática enquanto dados não chegaram
  const rate = _ML_FEES[listing.listing_type] ?? 11
  const fee = price * rate / 100
  const margin = price - fee
  return {
    rate,
    fee:             fee.toFixed(2),
    financing_fee:   0,
    fixed_fee:       0,
    shipping_cost:   0,
    shipping_detail: null,
    margin:          margin.toFixed(2),
    marginPct:       price > 0 ? ((margin / price) * 100).toFixed(2) : '0.00',
    isReal:          false,
  }
}

function billableWeight(listing) {
  const { weight_kg: w, height_cm: h, width_cm: ww, length_cm: l } = listing
  if (!w || !h || !ww || !l) return null
  const cubic = (h * ww * l) / 6000
  return Math.max(Number(w), cubic).toFixed(3)
}

function isCubicBillable(listing) {
  const { weight_kg: w, height_cm: h, width_cm: ww, length_cm: l } = listing
  if (!w || !h || !ww || !l) return false
  const cubic = (h * ww * l) / 6000
  return cubic > Number(w)
}

function logisticLabel(listing) {
  if (listing.is_full) return 'Full ML'
  if (listing.shipping_mode === 'me1') return 'ME1'
  return 'ME2 Drop Off'
}

function listingQuality(listing) {
  const issues = []
  let score = 0

  const pics = pictureCount(listing)
  if (pics === 0)      { issues.push('Nenhuma foto cadastrada') }
  else if (pics < 3)   { score += 15; issues.push('Adicione mais fotos (min. 3, ideal 8+)') }
  else if (pics < 6)   { score += 25; issues.push('Adicione mais fotos para aumentar conversão') }
  else                 { score += 35 }

  const desc = (listing.description_override || '').trim()
  if (!desc)                    { issues.push('Sem descricao — detalhe o produto') }
  else if (desc.length < 150)   { score += 10; issues.push('Descricao muito curta') }
  else if (desc.length < 500)   { score += 20; issues.push('Descricao pode ser mais detalhada') }
  else                          { score += 30 }

  const attrs = listing.attributes_json
  if (!attrs || attrs.length < 10) { issues.push('Ficha tecnica incompleta (marca, modelo...)') }
  else                             { score += 20 }

  if (!listing.thumbnail) { issues.push('Sem imagem principal') }
  else                    { score += 10 }

  if (!listing.sku) { issues.push('SKU do vendedor nao preenchido') }
  else              { score += 5 }

  let label, cls
  if      (score >= 80) { label = 'Excelente'; cls = 'badge-success' }
  else if (score >= 55) { label = 'Bom';       cls = 'badge-info' }
  else if (score >= 30) { label = 'Regular';   cls = 'badge-warning text-dark' }
  else                  { label = 'Fraco';     cls = 'badge-danger' }

  return { score, label, cls, issues }
}

function openPhotosModal(listing) {
  let photos = []
  if (listing.pictures_json) {
    try { photos = JSON.parse(listing.pictures_json) } catch { /* ignore */ }
  }
  photosModal.value = { show: true, listing, photos, zoomed: null }
}

function pictureCount(listing) {
  if (!listing.pictures_json) return 0
  try { return JSON.parse(listing.pictures_json).length } catch { return 0 }
}

function hasVariations(listing) {
  if (!listing.variations_json) return false
  try { return JSON.parse(listing.variations_json).length > 0 } catch { return false }
}

function showVariationsModal(listing) {
  if (!listing.variations_json) return
  try {
    const vars = JSON.parse(listing.variations_json)
    alert(`Variações de "${listing.title_override}":\n\n` +
      vars.map(v => {
        const attrs = (v.attributes || []).map(a => `${a.name}: ${a.value}`).join(', ')
        return `• ${attrs} — Estoque: ${v.available_quantity ?? '?'} | Vendidos: ${v.sold_quantity ?? 0}`
      }).join('\n'))
  } catch { /* ignore */ }
}
</script>
