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
                <select v-model="selectedAccountId" class="form-control form-control-sm d-inline-block" style="width:auto;min-width:260px" @change="onAccountChange">
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
                <div class="dropdown d-inline-block mr-2">
                  <button class="btn btn-sm btn-primary dropdown-toggle" type="button"
                          data-bs-toggle="dropdown" aria-expanded="false"
                          :disabled="selectedIds.length === 0 || batchAction.running">
                    <i class="fas fa-bolt mr-1"></i>Ações <span v-if="selectedIds.length">({{ selectedIds.length }})</span>
                  </button>
                  <ul class="dropdown-menu dropdown-menu-end">
                    <li>
                      <a class="dropdown-item" href="#" @click.prevent="confirmBatchAction('sync_to_ml')">
                        <i class="fas fa-upload mr-2 text-info"></i>Enviar Anúncio ao Marketplace
                      </a>
                    </li>
                    <li>
                      <a class="dropdown-item" href="#" @click.prevent="confirmBatchAction('sync_stock')">
                        <i class="fas fa-warehouse mr-2 text-success"></i>Sincronizar Estoque
                      </a>
                    </li>
                    <li>
                      <a class="dropdown-item" href="#" @click.prevent="confirmBatchAction('reimport')">
                        <i class="fas fa-download mr-2 text-secondary"></i>Ler Anúncio do Marketplace
                      </a>
                    </li>
                    <li><hr class="dropdown-divider"></li>
                    <li>
                      <a class="dropdown-item" href="#" @click.prevent="confirmBatchAction('reactivate')">
                        <i class="fas fa-play mr-2 text-success"></i>Reativar Anúncio
                      </a>
                    </li>
                    <li>
                      <a class="dropdown-item" href="#" @click.prevent="confirmBatchAction('drop_full')">
                        <i class="fas fa-warehouse mr-2 text-danger"></i>Deixar de Oferecer Full no ML
                      </a>
                    </li>
                  </ul>
                </div>
                <button class="btn btn-sm btn-secondary" @click="importAnuncios()" :disabled="!selectedAccountId || importing">
                  <i :class="['fas', importing ? 'fa-spinner fa-spin' : 'fa-download', 'mr-1']"></i>Importar
                </button>
              </div>
            </div>
            <div v-if="selectedAccountId" class="row mt-2">
              <div class="col-md-8">
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
              <div class="col-md-4">
                <div class="input-group input-group-sm">
                  <div class="input-group-prepend">
                    <span class="input-group-text"><i class="fas fa-search"></i></span>
                  </div>
                  <input
                    v-model="searchTerm"
                    type="text"
                    class="form-control"
                    placeholder="Filtrar por título, SKU, MLB ou categoria..."
                  />
                  <div v-if="searchTerm" class="input-group-append">
                    <button class="btn btn-outline-secondary" type="button" @click="searchTerm = ''" title="Limpar">
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                </div>
                <small v-if="searchTerm" class="text-muted">
                  {{ filteredAnuncios.length }} de {{ filteredBeforeSearch.length }} anúncio(s) visível(is)
                </small>
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
                <button class="btn btn-sm btn-secondary mr-2" @click="importAnuncios()" :disabled="importing">
                  <i class="fas fa-download mr-1"></i>Importar do Marketplace
                </button>
                <button class="btn btn-sm btn-success" @click="openWizard(null)">
                  <i class="fas fa-plus mr-1"></i>Criar Manualmente
                </button>
              </div>
            </div>
            <div v-else>
              <!-- Cabeçalho de seleção em lote -->
              <div class="d-flex align-items-center px-3 py-2 border-bottom bg-light" style="font-size:12px">
                <input type="checkbox" class="form-check-input m-0 mr-2"
                       style="width:18px;height:18px;cursor:pointer"
                       :checked="allFilteredSelected"
                       :indeterminate.prop="someFilteredSelected && !allFilteredSelected"
                       @change="toggleSelectAll"
                       title="Selecionar/desmarcar todos os anúncios visíveis" />
                <span class="text-muted">
                  <strong v-if="selectedIds.length">{{ selectedIds.length }}</strong>
                  <template v-if="selectedIds.length"> selecionado(s)</template>
                  <template v-else>Selecione anúncios para usar o botão Ações</template>
                </span>
                <button v-if="selectedIds.length" class="btn btn-link btn-sm py-0 ml-2" @click="selectedIds = []">
                  limpar seleção
                </button>
              </div>
              <div v-for="a in filteredAnuncios" :key="a.id"
                   class="border-bottom"
                   :style="!a.is_linked ? 'background:#fffbea' : ''">

                <!-- ── Linha única: checkbox | thumb | info | financeiro | ações ── -->
                <div class="d-flex align-items-start p-2" style="gap:10px">

                  <!-- Checkbox de seleção em lote -->
                  <div class="d-flex align-items-center" style="height:64px;flex-shrink:0">
                    <input type="checkbox" v-model="selectedIds" :value="a.id"
                           class="form-check-input m-0" style="width:18px;height:18px;cursor:pointer"
                           :title="'Selecionar anúncio ' + a.platform_item_id" />
                  </div>

                  <!-- Thumbnail (fallback pra imagem do produto vinculado se listing.thumbnail vazio) -->
                  <div style="position:relative;flex-shrink:0">
                    <img v-if="listingThumb(a)" :src="listingThumb(a)"
                         style="width:64px;height:64px;object-fit:cover;border-radius:4px" />
                    <div v-else class="d-flex align-items-center justify-content-center bg-light"
                         style="width:64px;height:64px;border-radius:4px">
                      <i class="fas fa-image text-muted"></i>
                    </div>
                    <button v-if="listingHasProcessingPictures(a)"
                            type="button"
                            class="btn btn-warning btn-sm"
                            style="position:absolute;top:-6px;right:-6px;width:22px;height:22px;padding:0;border-radius:50%;font-size:10px"
                            :disabled="!!refreshingPictures[a.id]"
                            :title="'Fotos ainda em processamento no ML. Clique para atualizar.'"
                            @click="refreshListingPictures(a)">
                      <i :class="['fas', refreshingPictures[a.id] ? 'fa-spinner fa-spin' : 'fa-sync-alt']"></i>
                    </button>
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
                      <span v-if="a.is_full" class="badge" :style="{background: smStyle('full').bg, color: smStyle('full').fg, fontSize:'10px'}" :title="smStyle('full').title"><i :class="smStyle('full').icon" class="mr-1"></i>{{ smStyle('full').label }}</span>
                      <span v-if="a.is_flex && !a.is_full" class="badge" :style="{background: smStyle('flex').bg, color: smStyle('flex').fg, fontSize:'10px'}" :title="smStyle('flex').title"><i :class="smStyle('flex').icon" class="mr-1"></i>{{ smStyle('flex').label }}</span>
                      <span v-if="a.catalog_listing && a.ml_catalog_id" class="badge badge-primary" style="font-size:10px" :title="'Produto: ' + a.ml_catalog_id"><i class="fas fa-bookmark mr-1"></i>Anúncio de Catálogo</span>
                      <span v-else-if="!a.catalog_listing && a.ml_catalog_id" class="badge badge-secondary" style="font-size:10px" :title="'Vinculado: ' + a.ml_catalog_id"><i class="fas fa-link mr-1"></i>Vinculado ao Catálogo</span>
                      <span v-if="a.is_variation_grouped" class="badge badge-success" style="font-size:10px" :title="'Família: ' + (a.family_name_ml || a.variation_group_id)"><i class="fas fa-layer-group mr-1"></i>Variação</span>
                      <span :class="'badge ' + listingQuality(a).cls" style="font-size:10px;cursor:help"
                            :title="listingQuality(a).issues.length ? listingQuality(a).issues.join('\n') : 'Anúncio completo'">
                        <i class="fas fa-star mr-1"></i>{{ listingQuality(a).label }}
                      </span>
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
                      <template v-if="a.is_full">
                        <span style="color:#00a650;font-weight:600" title="Estoque no galpão do Mercado Livre (Full)"><i class="fas fa-warehouse mr-1"></i>Full ML: {{ a.qty_full }} un.</span>
                        <span v-if="a.product_stock !== null && a.product_stock !== undefined" class="text-secondary" title="Estoque disponível no galpão do seller"><i class="fas fa-store mr-1"></i>Galpão: {{ a.product_stock }} un.</span>
                      </template>
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
                      <button
                        v-if="!a.is_linked || (a.variations_total > 0)"
                        class="btn btn-outline-dark"
                        :title="a.all_variations_imported
                          ? 'Todas as variações já foram importadas como produtos CMIG'
                          : (a.variations_total > 0
                              ? `Criar produto CMIG (${a.variations_imported_count}/${a.variations_total} variantes já importadas)`
                              : 'Criar produto CMIG')"
                        :disabled="a.all_variations_imported"
                        @click="openCreateCmigModal(a)">
                        <i class="fas fa-plus"></i>
                        <span v-if="a.variations_total > 0" class="ml-1" style="font-size:10px">
                          ({{ a.variations_imported_count }}/{{ a.variations_total }})
                        </span>
                      </button>
                      <button v-if="a.is_linked" class="btn btn-outline-warning" title="Desvincular produto" @click="unlinkAnuncio(a)"><i class="fas fa-unlink"></i></button>
                    </div>
                    <!-- Linha 2: status e marketplace -->
                    <div class="btn-group btn-group-sm">
                      <button v-if="a.status === 'published'" class="btn btn-outline-warning" title="Pausar anúncio" @click="pauseAnuncio(a)"><i class="fas fa-pause"></i></button>
                      <button v-if="a.status === 'paused'" class="btn btn-outline-success" title="Reativar anúncio" @click="reactivateAnuncio(a)"><i class="fas fa-play"></i></button>
                      <!-- Botão Flex: ação de ativar/desativar (só visivel se elígivel).
                           O badge informativo do logistic_type fica na linha de info do anúncio
                           (próximo ao ME2 Drop Off), não aqui. -->
                      <button v-if="canToggleFlex(a)"
                              :class="['btn', isFlexActive(a) ? 'btn-warning' : 'btn-outline-warning']"
                              :title="isFlexActive(a) ? 'Desativar Mercado Envios Flex' : 'Ativar Mercado Envios Flex'"
                              @click="toggleFlex(a)">
                        <i class="fas fa-bolt"></i>
                      </button>
                      <button v-if="a.is_full && a.qty_full === 0 && a.platform_item_id"
                              class="btn btn-outline-danger"
                              title="Deixar de oferecer Full — converter para cross-docking usando estoque do galpão do seller"
                              @click="switchToCrossDocking(a)">
                        <i class="fas fa-warehouse mr-1"></i><i class="fas fa-times" style="font-size:9px;vertical-align:1px"></i>
                      </button>
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
                <PublishCategoryPicker
                  v-if="wf.product_id && wizardPickerMarketplace"
                  :key="`${wf.product_type}-${wf.product_id}-${wizardPickerMarketplace}`"
                  :owner-type="wf.product_type === 'cmig' ? 'cmig' : 'catalog'"
                  :owner-id="wf.product_id"
                  :marketplace="wizardPickerMarketplace"
                  :product-hints="{ brand: wf.selectedProduct?.brand, model: wf.selectedProduct?.model }"
                  :initial-value="wizardCategoryInitialValue"
                  v-model="wizardCategorySel"
                />
                <div v-else class="alert alert-warning py-2 small">
                  <i class="fas fa-info-circle mr-1"></i>
                  Selecione um produto na Aba 1 para escolher a categoria.
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

                    <!-- Tipo logístico — informativo. ML resolve automaticamente baseado em
                         conta + categoria + atributos do produto. Não é configurável por item. -->
                    <div class="form-group">
                      <label class="small">Tipo Logístico</label>
                      <div v-if="wizard.isEdit && currentListingLogisticBadge"
                           class="d-flex align-items-center mb-1">
                        <span :class="['badge px-2 mr-2', currentListingLogisticBadge.cls]"
                              style="font-size:11px;font-weight:600">
                          <i :class="['fas', currentListingLogisticBadge.icon, 'mr-1']"></i>
                          {{ currentListingLogisticBadge.label }}
                        </span>
                        <small class="text-muted">tipo atual no ML</small>
                      </div>
                      <div class="alert alert-light border py-2 px-2 mb-0" style="font-size:10px">
                        <i class="fas fa-info-circle text-info mr-1"></i>
                        O Mercado Livre define automaticamente entre
                        <strong>cross-docking</strong>, <strong>Flex</strong> e <strong>Full</strong>
                        baseado na sua conta, categoria do anúncio e atributos do produto.
                        <span v-if="accountCapabilities.checked && accountCapabilities.has_flex">
                          Sua conta tem <strong>Flex habilitado</strong> ⚡.
                        </span>
                        <span v-if="accountCapabilities.checked && accountCapabilities.has_full">
                          Tem <strong>Full</strong> 🏬.
                        </span>
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
                    <input v-model="wizardFiscal.ean" class="form-control form-control-sm"
                           :class="{ 'is-invalid': wizardEanInvalid }"
                           placeholder="Ex: 7891234567890" maxlength="14" />
                    <small v-if="wizardEanInvalid" class="text-danger">
                      <i class="fas fa-exclamation-triangle mr-1"></i>Checksum EAN-13 inválido — ML rejeitará.
                    </small>
                  </div>
                  <div class="col-md-3 form-group">
                    <label class="small">CEST</label>
                    <input v-model="wizardFiscal.cest" class="form-control form-control-sm" placeholder="Ex: 2800100" maxlength="7" />
                  </div>
                  <div class="col-md-3 form-group">
                    <label class="small">CSOSN do ICMS</label>
                    <select v-model="wizardFiscal.csosn" class="form-control form-control-sm">
                      <option :value="null">— Default da CMIG —</option>
                      <option value="101">101 - Tributada c/ crédito</option>
                      <option value="102">102 - Tributada s/ crédito</option>
                      <option value="103">103 - Isenção faixa receita</option>
                      <option value="201">201 - Tributada c/ crédito e ST</option>
                      <option value="202">202 - Tributada s/ crédito e ST</option>
                      <option value="203">203 - Isenção faixa e ST</option>
                      <option value="300">300 - Imune</option>
                      <option value="400">400 - Não tributada</option>
                      <option value="500">500 - ICMS por ST</option>
                      <option value="900">900 - Outros</option>
                    </select>
                    <small class="text-muted">Obrigatório no Faturador ML</small>
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

    <!-- Modal: Progresso da Importação -->
    <div v-if="importProgress" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1090">
      <div class="modal-dialog modal-sm modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header py-2">
            <h6 class="modal-title">
              <i v-if="importProgress.phase === 'error'" class="fas fa-exclamation-triangle text-danger mr-2"></i>
              <i v-else class="fas fa-cloud-download-alt text-primary mr-2"></i>
              {{ importProgress.phase === 'error' ? 'Falha na importação' : 'Importando anúncios' }}
            </h6>
            <button v-if="importProgress.phase === 'error'" type="button" class="close" @click="closeImportProgress"><span>&times;</span></button>
          </div>
          <div class="modal-body text-center py-3">
            <template v-if="importProgress.phase !== 'error'">
              <div class="mb-3">
                <i class="fas fa-spinner fa-spin fa-2x text-primary"></i>
              </div>
              <div class="font-weight-bold small">{{ importProgress.message }}</div>
              <div class="text-muted small mt-1">{{ importProgress.sub }}</div>
              <div class="text-muted mt-2" style="font-size:11px">
                <i class="far fa-clock mr-1"></i>{{ importProgress.elapsed }}s decorridos
              </div>
              <div v-if="importProgress.elapsed > 30" class="alert alert-info py-1 mt-2 small mb-0">
                Contas com muitos anúncios podem levar até <strong>2 minutos</strong>.
                Não feche esta janela.
              </div>
            </template>
            <template v-else>
              <div class="text-danger mb-2"><i class="fas fa-times-circle fa-2x"></i></div>
              <div class="font-weight-bold">{{ importProgress.error.title }}</div>
              <div class="text-muted small mt-2">{{ importProgress.error.hint }}</div>
            </template>
          </div>
          <div v-if="importProgress.phase === 'error'" class="modal-footer py-2">
            <button class="btn btn-sm btn-secondary" @click="closeImportProgress">Fechar</button>
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
            <div v-if="importResult._statuses" class="alert alert-info py-2 small mb-3">
              <i class="fas fa-info-circle mr-1"></i>
              Status importados: <strong>{{ importResult._statuses }}</strong>
            </div>
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
              <li v-if="importResult.failed" class="list-group-item d-flex justify-content-between">
                <span><i class="fas fa-exclamation-triangle text-danger mr-1"></i>Falharam</span>
                <span class="badge badge-danger badge-pill">{{ importResult.failed }}</span>
              </li>
              <li v-if="importResult.total_seen_in_ml" class="list-group-item d-flex justify-content-between text-muted small">
                <span>Total no ML (antes do filtro)</span><span>{{ importResult.total_seen_in_ml }}</span>
              </li>
            </ul>

            <!-- Erros por item (amigável) -->
            <div v-if="importResult.item_errors && importResult.item_errors.length" class="mt-3">
              <div class="text-danger small font-weight-bold mb-1">
                <i class="fas fa-exclamation-circle mr-1"></i>Anúncios que não puderam ser importados:
              </div>
              <div class="border rounded p-2" style="max-height:160px;overflow-y:auto;background:#fff5f5">
                <div v-for="(err, i) in importResult.item_errors" :key="i" class="small mb-1">
                  <code v-if="err.platform_item_id" style="font-size:10px">{{ err.platform_item_id }}</code>
                  <span v-else class="text-muted">(sem ID)</span>
                  <span class="text-muted ml-1">— {{ err.error }}</span>
                </div>
              </div>
            </div>

            <div v-if="importResult._statuses !== 'all'"
                 class="alert alert-warning py-2 small mt-3 mb-0">
              <i class="fas fa-archive mr-1"></i>
              Por padrão importamos apenas <strong>active, paused, closed, under_review</strong>.
              Anúncios em status raros (suspended_for_prevention, etc.) ficam de fora.
              Clique no botão abaixo para importar <strong>TUDO</strong>.
            </div>
            <div v-else class="alert alert-success py-2 small mt-3 mb-0">
              <i class="fas fa-check mr-1"></i>
              Modo <strong>"Importar Tudo"</strong>: trouxe todos os anúncios do vendedor sem filtro de status.
            </div>

            <!-- Diagnóstico expansível -->
            <div v-if="importResult.diagnostics" class="mt-3">
              <button class="btn btn-sm btn-link p-0" @click="showDiagnostics = !showDiagnostics">
                <i :class="['fas', showDiagnostics ? 'fa-caret-down' : 'fa-caret-right']"></i>
                {{ showDiagnostics ? 'Ocultar' : 'Mostrar' }} diagnóstico técnico
              </button>
              <div v-if="showDiagnostics" class="small mt-2 p-2 rounded" style="background:#f8f9fa;font-family:monospace;font-size:11px;max-height:240px;overflow-y:auto">
                <div v-for="(entry, i) in importResult.diagnostics" :key="i" class="mb-1">
                  <strong v-if="entry.phase">[{{ entry.phase }}]</strong>
                  <strong v-else-if="entry.iter">iter #{{ entry.iter }}:</strong>
                  <span class="text-muted">{{ JSON.stringify(entry, null, 0) }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button v-if="importResult._statuses !== 'all'"
                    class="btn btn-warning btn-sm"
                    :disabled="importing"
                    @click="importAllAnuncios">
              <i :class="['fas', importing ? 'fa-spinner fa-spin' : 'fa-download', 'mr-1']"></i>
              {{ importing ? 'Importando...' : 'Importar TUDO (todos os status)' }}
            </button>
            <button v-if="importResult.unlinked > 0" class="btn btn-info btn-sm" @click="setFilter('unlinked'); importResult = null">Ver sem vínculo</button>
            <button class="btn btn-secondary" @click="importResult = null" :disabled="importing">Fechar</button>
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

    <!-- Modal: Selecionar Variação para importar (anúncio com variações) -->
    <div v-if="variantSelectModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1080">
      <div class="modal-dialog modal-md modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header py-2">
            <h6 class="modal-title">
              <i class="fas fa-layer-group mr-2 text-info"></i>
              Selecione a variação para importar
            </h6>
            <button type="button" class="close" @click="variantSelectModal.show = false"><span>&times;</span></button>
          </div>
          <div class="modal-body py-2">
            <p class="text-muted small mb-2">
              Anúncio: <strong>{{ variantSelectModal.listing?.title_override }}</strong>
            </p>
            <div v-if="variantSelectModal.loading" class="text-center py-3">
              <i class="fas fa-spinner fa-spin"></i>
            </div>
            <div v-else-if="variantSelectModal.status">
              <div v-if="variantSelectModal.status.all_imported" class="alert alert-success py-2 small">
                <i class="fas fa-check-circle mr-1"></i>
                Todas as variações deste anúncio já foram importadas.
              </div>
              <div class="list-group">
                <div v-for="v in variantSelectModal.status.variations" :key="v.id"
                     class="list-group-item p-2">
                  <div class="d-flex align-items-center" style="gap:8px">
                    <div class="flex-grow-1" style="min-width:0">
                      <div class="font-weight-bold" style="font-size:13px">{{ v.attributes_label }}</div>
                      <div class="text-muted" style="font-size:11px">
                        <span v-if="v.sku">SKU: <code>{{ v.sku }}</code> · </span>
                        Estoque: {{ v.available_quantity ?? 0 }} ·
                        {{ formatCurrency(v.price) }}
                      </div>
                      <div v-if="v.imported && v.cmig_product" class="text-success" style="font-size:11px">
                        <i class="fas fa-check mr-1"></i>
                        Já importado como <strong>{{ v.cmig_product.sku_cmig }}</strong>
                      </div>
                    </div>
                    <button
                      v-if="!v.imported"
                      type="button"
                      class="btn btn-sm btn-success"
                      @click="pickVariantToImport(v)">
                      <i class="fas fa-plus mr-1"></i>Importar
                    </button>
                    <span v-else class="badge badge-secondary" style="font-size:10px">
                      <i class="fas fa-check mr-1"></i>Importada
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer py-2">
            <button class="btn btn-sm btn-secondary" @click="variantSelectModal.show = false">Fechar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Criar Produto CMIG -->
    <div v-if="createCmigModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              <i class="fas fa-plus mr-2"></i>Criar Produto CMIG
              <span v-if="createCmigModal.variation_label" class="badge badge-info ml-2" style="font-size:11px">
                <i class="fas fa-layer-group mr-1"></i>{{ createCmigModal.variation_label }}
              </span>
            </h5>
            <button type="button" class="close" @click="createCmigModal.show = false"><span>&times;</span></button>
          </div>
          <form @submit.prevent="doCreateCmigProduct">
            <div class="modal-body" style="max-height:75vh;overflow-y:auto">
              <div v-if="createCmigModal.error" class="alert alert-danger py-2">{{ createCmigModal.error }}</div>
              <p class="text-muted small mb-3">
                A partir do anúncio: <strong>{{ createCmigModal.listing?.title_override }}</strong>
                <span v-if="createCmigModal.variation_label" class="d-block mt-1">
                  <i class="fas fa-arrow-right text-info mr-1"></i>
                  Variação: <strong>{{ createCmigModal.variation_label }}</strong>
                </span>
              </p>

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

              <!-- Preço -->
              <p class="font-weight-bold small text-uppercase text-muted mb-2">Preço</p>
              <div class="row">
                <div class="col-md-6 form-group">
                  <label>Preço de Venda (R$)</label>
                  <input v-model="createCmigForm.sale_price" type="number" step="0.01" min="0" class="form-control" />
                </div>
                <div class="col-md-6 form-group">
                  <label>Custo (R$)</label>
                  <input v-model="createCmigForm.cost_price" type="number" step="0.01" min="0" class="form-control" />
                </div>
              </div>
              <div class="alert alert-info py-2 small mb-3">
                <i class="fas fa-warehouse mr-1"></i>
                <strong>Estoque:</strong> {{ createCmigModal.listing?.available_quantity ?? 0 }} unidade(s) —
                copiado automaticamente do anúncio. Para ajustar, edite o produto depois ou registre uma entrada/saída.
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
              <div class="row">
                <div class="col-md-4 form-group">
                  <label>Origem da Mercadoria</label>
                  <select v-model.number="createCmigForm.origin" class="form-control">
                    <option :value="0">0 — Nacional</option>
                    <option :value="1">1 — Estrangeira (Importação direta)</option>
                    <option :value="2">2 — Estrangeira (Mercado interno)</option>
                    <option :value="3">3 — Nacional (40-70% conteúdo importado)</option>
                    <option :value="4">4 — Nacional (processo produtivo PPB)</option>
                    <option :value="5">5 — Nacional (≤40% conteúdo importado)</option>
                    <option :value="6">6 — Estrangeira (Importação direta, sem similar)</option>
                    <option :value="7">7 — Estrangeira (Mercado interno, sem similar)</option>
                    <option :value="8">8 — Nacional (>70% conteúdo importado)</option>
                  </select>
                </div>
                <div class="col-md-8 form-group">
                  <label>CSOSN do ICMS</label>
                  <select v-model="createCmigForm.csosn" class="form-control">
                    <option :value="null">— Usar padrão da CMIG —</option>
                    <option value="101">101 — Tributada com permissão de crédito</option>
                    <option value="102">102 — Tributada sem permissão de crédito</option>
                    <option value="103">103 — Isenção do ICMS (faixa receita bruta)</option>
                    <option value="201">201 — Trib. com permissão + cobrança ST</option>
                    <option value="202">202 — Trib. sem permissão + cobrança ST</option>
                    <option value="203">203 — Isenção + cobrança ST</option>
                    <option value="300">300 — Imune</option>
                    <option value="400">400 — Não tributada</option>
                    <option value="500">500 — ICMS cobrado anteriormente por ST</option>
                    <option value="900">900 — Outros</option>
                  </select>
                  <small class="text-muted">Usado pelo Faturador ML ao emitir NFe. Deixe em branco para usar o padrão configurado na CMIG.</small>
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

    <!-- Modal: Confirmação de ação em lote -->
    <div v-if="batchAction.confirming" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header bg-primary text-white">
            <h5 class="modal-title"><i class="fas fa-bolt mr-2"></i>Confirmar Ação em Lote</h5>
            <button type="button" class="close text-white" @click="batchAction.confirming = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <p>Executar <strong>{{ batchActionLabel(batchAction.action) }}</strong> em <strong>{{ batchAction.ids.length }}</strong> anúncio(s) selecionado(s)?</p>
            <p v-if="batchAction.action === 'reimport'" class="text-warning small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              Isso vai sobrescrever título, fotos, atributos e preço com o que está no Marketplace. Vínculo de produto e estoque local serão preservados.
            </p>
            <p v-else-if="batchAction.action === 'sync_to_ml'" class="text-warning small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              Vai enviar todos os campos editáveis (título, preço, atributos, fotos, descrição, estoque) ao Marketplace. Pode disparar resolução de conflito se houver anúncios duplicados.
            </p>
            <p v-else-if="batchAction.action === 'sync_stock'" class="text-info small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              Vai enviar o estoque dos anúncios não-Full e ler o estoque Full dos anúncios Full.
            </p>
            <p v-else-if="batchAction.action === 'reactivate'" class="text-success small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              Vai reativar anúncios pausados ou fechados no Marketplace. Anúncios já publicados serão ignorados pelo ML.
            </p>
            <p v-else-if="batchAction.action === 'drop_full'" class="text-danger small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              Vai converter para cross-docking os anúncios Full com estoque zerado no galpão do ML. Anúncios que não são Full ou que ainda têm estoque no galpão serão ignorados.
            </p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="batchAction.confirming = false">Cancelar</button>
            <button class="btn btn-primary" @click="runBatchAction"><i class="fas fa-check mr-1"></i>Confirmar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Progresso de ação em lote -->
    <div v-if="batchAction.running" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header bg-info text-white">
            <h5 class="modal-title"><i class="fas fa-cog fa-spin mr-2"></i>{{ batchActionLabel(batchAction.action) }}</h5>
          </div>
          <div class="modal-body">
            <p v-if="isChunkedAction(batchAction.action)" class="mb-2">
              Processando <strong>{{ batchAction.done }}</strong> de <strong>{{ batchAction.ids.length }}</strong>...
            </p>
            <p v-else class="mb-2">
              Processando <strong>{{ batchAction.ids.length }}</strong> anúncio(s) em uma única requisição...
            </p>
            <div class="progress" style="height:20px">
              <!-- Ações em chunks: barra com progresso real; demais: indeterminada -->
              <div v-if="isChunkedAction(batchAction.action)"
                   class="progress-bar progress-bar-striped progress-bar-animated"
                   :style="{width: ((batchAction.done / Math.max(1, batchAction.ids.length)) * 100) + '%'}">
                {{ Math.round((batchAction.done / Math.max(1, batchAction.ids.length)) * 100) }}%
              </div>
              <div v-else class="progress-bar progress-bar-striped progress-bar-animated bg-info"
                   style="width:100%">
                Aguarde...
              </div>
            </div>
            <div class="mt-2 small">
              <span class="text-success mr-3"><i class="fas fa-check mr-1"></i>Sucesso: {{ batchAction.success }}</span>
              <span class="text-danger"><i class="fas fa-times mr-1"></i>Erros: {{ batchAction.errors.length }}</span>
            </div>
          </div>
          <div class="modal-footer">
            <!-- Cancelar só funciona em ações que rodam em chunks; chamadas únicas
                 não podem ser interrompidas. -->
            <button v-if="isChunkedAction(batchAction.action)"
                    class="btn btn-warning"
                    @click="batchAction.cancelled = true"
                    :disabled="batchAction.cancelled">
              <i class="fas fa-stop mr-1"></i>{{ batchAction.cancelled ? 'Cancelando...' : 'Cancelar' }}
            </button>
            <span v-else class="text-muted small">
              <i class="fas fa-info-circle mr-1"></i>Esta ação não pode ser cancelada.
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Resultado de ação em lote -->
    <div v-if="batchAction.resultOpen" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header" :class="batchAction.errors.length ? 'bg-warning' : 'bg-success text-white'">
            <h5 class="modal-title">
              <i :class="['fas mr-2', batchAction.errors.length ? 'fa-exclamation-triangle' : 'fa-check']"></i>
              Resultado: {{ batchActionLabel(batchAction.action) }}
            </h5>
            <button type="button" class="close" @click="batchAction.resultOpen = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <ul class="list-group list-group-flush">
              <li class="list-group-item d-flex justify-content-between">
                <span>Sucessos</span><span class="badge badge-success badge-pill">{{ batchAction.success }}</span>
              </li>
              <li class="list-group-item d-flex justify-content-between">
                <span>Erros</span><span class="badge badge-danger badge-pill">{{ batchAction.errors.length }}</span>
              </li>
              <li v-if="batchAction.cancelled" class="list-group-item">
                <i class="fas fa-stop text-warning mr-1"></i>Operação cancelada pelo usuário.
              </li>
            </ul>
            <div v-if="batchAction.errors.length" class="mt-3">
              <h6 class="small text-muted">Detalhes dos erros:</h6>
              <div style="max-height:300px;overflow-y:auto">
                <div v-for="(err, idx) in batchAction.errors" :key="`${idx}-${err.listing_id}`"
                     class="alert alert-danger py-1 px-2 mb-1 small">
                  <strong>#{{ err.listing_id }}:</strong>
                  <template v-if="err.detail?.error === 'user_product_repeated_conflict'">
                    Conflito de User Product duplicado — abra o anúncio individualmente para resolver.
                  </template>
                  <template v-else>{{ typeof err.detail === 'string' ? err.detail : (err.detail?.message || err.error || JSON.stringify(err.detail || err.error)) }}</template>
                </div>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="batchAction.resultOpen = false">Fechar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Conflito de User Product (anúncios duplicados no ML) -->
    <div v-if="conflictModal.show" class="modal fade show d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header bg-warning">
            <h5 class="modal-title"><i class="fas fa-exclamation-triangle mr-2"></i>Anúncios duplicados detectados</h5>
            <button type="button" class="close" :disabled="conflictModal.deleting" @click="conflictModal.show = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="alert alert-warning py-2 small mb-3">
              <p class="mb-1"><strong>O Mercado Livre rejeitou a sincronização</strong> porque o anúncio que você está atualizando ficaria idêntico a outro(s) anúncio(s) desta conta — mesmo título + catálogo + atributos + foto principal.</p>
              <p class="mb-0">Escolha qual anúncio remover do Marketplace para concluir a sincronização. A linha em <span class="badge badge-danger">vermelho</span> é a sugestão (menos relevante).</p>
            </div>
            <p v-if="conflictModal.userProductId" class="small text-muted mb-2">
              User Product em conflito: <code>{{ conflictModal.userProductId }}</code>
            </p>
            <div v-if="conflictModal.attemptedItemIds.length" class="alert alert-info py-1 px-2 small mb-2">
              <i class="fas fa-history mr-1"></i>Já fechados nesta sessão:
              <code v-for="id in conflictModal.attemptedItemIds" :key="id" class="mr-1">{{ id }}</code>
            </div>
            <div class="table-responsive">
              <table class="table table-sm table-bordered align-middle">
                <thead class="thead-light small">
                  <tr>
                    <th></th>
                    <th></th>
                    <th>MLB</th>
                    <th>Anúncio</th>
                    <th>Status</th>
                    <th>Tipo</th>
                    <th>Logística</th>
                    <th>Vendas</th>
                    <th>Visualizar</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="c in conflictModal.candidates" :key="c.item_id"
                      :class="c.item_id === conflictModal.suggestedDeleteItemId ? 'table-danger' : ''">
                    <td class="text-center">
                      <input type="radio" :value="c.item_id"
                             :disabled="c.is_current || conflictModal.deleting"
                             v-model="conflictModal.selectedDeleteItemId" />
                    </td>
                    <td><img v-if="c.thumbnail" :src="c.thumbnail" style="width:48px;height:48px;object-fit:cover" class="rounded border" /></td>
                    <td>
                      <code class="small">{{ c.item_id }}</code>
                      <span v-if="c.is_current" class="badge badge-info ml-1">este</span>
                      <span v-if="c.item_id === conflictModal.suggestedDeleteItemId" class="badge badge-danger ml-1">menos relevante</span>
                    </td>
                    <td class="small" style="max-width:240px">{{ c.title }}</td>
                    <td><span class="badge" :class="mlStatusBadgeClass(c.status)">{{ c.status }}</span></td>
                    <td class="small">
                      <span v-if="c.catalog_listing" class="badge badge-primary">Catálogo</span>
                      <span v-else class="badge badge-secondary">Próprio</span>
                    </td>
                    <td class="small">{{ c.logistic_type || '-' }}</td>
                    <td class="text-center small">{{ c.sold_quantity }}</td>
                    <td>
                      <a v-if="c.permalink" :href="c.permalink" target="_blank" rel="noopener" class="btn btn-sm btn-outline-secondary" title="Abrir no ML">
                        <i class="fas fa-external-link-alt"></i>
                      </a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="conflictModal.candidates.length === 0" class="text-muted small text-center py-3">
              Nenhum anúncio candidato encontrado. Verifique manualmente no painel do ML.
            </div>
          </div>
          <div class="modal-footer justify-content-between">
            <small class="text-muted">O anúncio escolhido será <strong>fechado no ML</strong> e removido do sistema.</small>
            <div>
              <button class="btn btn-secondary mr-2" :disabled="conflictModal.deleting" @click="conflictModal.show = false">Cancelar</button>
              <button class="btn btn-danger"
                      :disabled="!conflictModal.selectedDeleteItemId || conflictModal.deleting"
                      @click="resolveConflict">
                <i :class="['fas', conflictModal.deleting ? 'fa-spinner fa-spin' : 'fa-trash', 'mr-1']"></i>
                Excluir selecionado e sincronizar
              </button>
            </div>
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
import { shippingModeStyle as smStyle } from '@/utils/constants'
import { isValidEan13 } from '@/utils/ean'
import PublishCategoryPicker from '@/components/catalog/PublishCategoryPicker.vue'
import { persistCategoryToProduct } from '@/composables/usePublishCategory'

const toast = useToast()

const accounts = ref([])
const selectedAccountId = ref('')
const anuncios = ref([])
const loading = ref(false)
const importing = ref(false)
const filterVinculo = ref('all')
const filterStatus = ref('published')
const statsBar = ref(null)
const loadingStats = ref(false)
const importResult = ref(null)
const cmigs = ref([])

// Capacidades de envio da conta ML selecionada — usado para mostrar opção Flex
// no wizard e botão Flex inline. Carregadas via GET /accounts/{id}/shipping-capabilities.
const accountCapabilities = ref({ has_flex: false, has_full: false, checked: false })

async function onAccountChange() {
  await loadAnuncios()
  loadAccountCapabilities()  // fire-and-forget — não bloqueia listagem
}

async function loadAccountCapabilities() {
  accountCapabilities.value = { has_flex: false, has_full: false, checked: false }
  if (!selectedAccountId.value) return
  const acc = accounts.value.find(a => a.id === selectedAccountId.value)
  if (!acc || acc.platform !== 'mercadolivre') return
  try {
    const { data } = await api.get(`/accounts/${selectedAccountId.value}/shipping-capabilities`)
    accountCapabilities.value = {
      has_flex: !!data.has_flex,
      has_full: !!data.has_full,
      checked: true,
    }
  } catch {
    accountCapabilities.value = { has_flex: false, has_full: false, checked: true }
  }
}

const statusTabs = [
  { key: 'all',       label: 'Todos' },
  { key: 'published', label: 'Ativos' },
  { key: 'paused',    label: 'Pausados' },
  { key: 'draft',     label: 'Em revisão' },
  { key: 'closed',    label: 'Finalizados' },
]

const selectedAccount = computed(() => accounts.value.find(a => a.id === selectedAccountId.value))
const selectedAccountPlatform = computed(() => selectedAccount.value?.platform || '')

// Filtros aplicados em ordem: vínculo → status → busca textual.
// `filteredBeforeSearch` é exposto pra UI mostrar "X de Y anúncios" no header da busca.
const filteredBeforeSearch = computed(() => {
  let list = anuncios.value
  if (filterVinculo.value === 'linked')   list = list.filter(a => a.is_linked)
  if (filterVinculo.value === 'unlinked') list = list.filter(a => !a.is_linked)
  if (filterStatus.value !== 'all')       list = list.filter(a => a.status === filterStatus.value)
  return list
})

const searchTerm = ref('')

const filteredAnuncios = computed(() => {
  const term = (searchTerm.value || '').trim().toLowerCase()
  if (!term) return filteredBeforeSearch.value
  // Suporta múltiplos termos separados por espaço (AND) — cada termo casa em qualquer campo
  const tokens = term.split(/\s+/).filter(Boolean)
  return filteredBeforeSearch.value.filter(a => {
    const haystack = [
      a.title_override,
      a.sku,
      a.platform_item_id,
      a.category_id,
      a.category_name,
      a.ml_catalog_id,
      a.family_name_ml,
      a.cmig_product?.sku,
      a.cmig_product?.sku_cmig,
      a.catalog_product?.sku,
    ].filter(Boolean).join(' ').toLowerCase()
    return tokens.every(t => haystack.includes(t))
  })
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
    account_platform: 'mercadolivre',
    // Read-only no edit: logistic_type do listing atual (Flex/Full/cross-docking)
    current_logistic_type: '',
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
  // Reset da seleção de categoria — o picker recarrega ao perceber novo produto
  resetWizardCategorySel()
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

// ── Categoria + atributos (gerenciado por PublishCategoryPicker) ──────────────
// 'mercadolivre' / 'shopee' → 'mercado_livre' / 'shopee'
const wizardPickerMarketplace = computed(() => {
  const p = selectedAccount.value?.platform || wf.value.account_platform
  if (p === 'mercadolivre') return 'mercado_livre'
  if (p === 'shopee')       return 'shopee'
  return ''
})

const wizardCategorySel = ref({
  pmc_id: null, category_id: '', category_name: '',
  category_path_json: null, isNew: false, attributes: [],
})

// initialValue para o picker no modo edição (preenchido em openWizard com listing)
const wizardCategoryInitialValue = ref(null)

function resetWizardCategorySel() {
  wizardCategorySel.value = {
    pmc_id: null, category_id: '', category_name: '',
    category_path_json: null, isNew: false, attributes: [],
  }
  wizardCategoryInitialValue.value = null
}

// Badge do logistic_type do listing em edição — reusa a mesma função da listagem
const currentListingLogisticBadge = computed(() => {
  if (!wf.value.current_logistic_type) return null
  return logisticBadge({ logistic_type: wf.value.current_logistic_type })
})

// Dados fiscais do anúncio
const wizardFiscal = ref({ ncm: '', ean: '', cest: '', gtin: '', csosn: null })

const wizardEanInvalid = computed(() => {
  const v = (wizardFiscal.value.ean || '').trim()
  return v.length > 0 && !isValidEan13(v)
})

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
  resetWizardCategorySel()
  wizardFiscal.value = { ncm: '', ean: '', cest: '', gtin: '', csosn: null }
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
    wf.value.description_override = listing.description_override || ''
    wf.value.video_id = listing.video_id || ''
    wf.value.shipping_mode = listing.shipping_mode || 'me2'
    wf.value.free_shipping = !!listing.free_shipping
    wf.value.current_logistic_type = (listing.logistic_type || '').toLowerCase()
    wf.value.warranty_type = listing.warranty_type || ''
    wf.value.warranty_time = listing.warranty_time || ''
    wf.value.sku       = listing.sku || ''
    wf.value.weight_kg = listing.weight_kg != null ? listing.weight_kg : ''
    wf.value.height_cm = listing.height_cm != null ? listing.height_cm : ''
    wf.value.width_cm  = listing.width_cm  != null ? listing.width_cm  : ''
    wf.value.length_cm = listing.length_cm != null ? listing.length_cm : ''
    // Pre-popular dados fiscais
    wizardFiscal.value = { ncm: '', ean: '', cest: '', gtin: '', csosn: null }
    if (listing.fiscal_json) {
      try {
        const f = JSON.parse(listing.fiscal_json)
        wizardFiscal.value.ncm  = f.ncm  || f.NCM  || ''
        // EAN e GTIN são a mesma coisa — ML frequentemente retorna como "gtin" no import
        wizardFiscal.value.ean  = f.ean  || f.EAN  || f.gtin || f.GTIN || ''
        wizardFiscal.value.cest = f.cest || f.CEST || ''
        wizardFiscal.value.gtin = f.gtin || f.GTIN || f.ean  || f.EAN  || ''
        wizardFiscal.value.csosn = f.csosn || f.CSOSN || f.icms_csosn || null
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
      fetchCategoryPath(listing.category_id)  // carrega breadcrumb no mapa compartilhado
      let initialAttrs = []
      if (listing.attributes_json) {
        try {
          const saved = JSON.parse(listing.attributes_json)
          initialAttrs = saved
            .filter(a => a && a.id)
            .map(a => ({ id: a.id, value_name: a.value_name ?? a.value ?? '' }))
        } catch { /* ignore */ }
      }
      wizardCategoryInitialValue.value = {
        category_id: listing.category_id,
        category_name: listing.category_name || listing.category_id,
        attributes: initialAttrs,
      }
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
    if (!wizardCategorySel.value.category_id) throw new Error('Selecione uma categoria (Aba 3)')

    const attributes = wizardCategorySel.value.attributes || []

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
      category_id: wizardCategorySel.value.category_id || null,
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
      fiscal_json: (wizardFiscal.value.ncm || wizardFiscal.value.ean || wizardFiscal.value.cest || wizardFiscal.value.csosn)
        ? JSON.stringify({ ncm: wizardFiscal.value.ncm || null, ean: wizardFiscal.value.ean || null, cest: wizardFiscal.value.cest || null, gtin: wizardFiscal.value.gtin || null, csosn: wizardFiscal.value.csosn || null })
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

    // Persiste categoria/atributos no produto para reuso futuro (best-effort).
    if (wf.value.product_id && wizardPickerMarketplace.value) {
      await persistCategoryToProduct(
        wizardCategorySel.value,
        wf.value.product_type === 'cmig' ? 'cmig' : 'catalog',
        wf.value.product_id,
        wizardPickerMarketplace.value,
      )
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
const conflictModal = ref({
  show: false,
  listing: null,
  userProductId: null,
  currentItemId: null,
  candidates: [],
  suggestedDeleteItemId: null,
  selectedDeleteItemId: null,
  attemptedItemIds: [],
  deleting: false,
})

// Seleção em lote
const selectedIds = ref([])
const allFilteredSelected = computed(() =>
  filteredAnuncios.value.length > 0
  && filteredAnuncios.value.every(a => selectedIds.value.includes(a.id))
)
const someFilteredSelected = computed(() =>
  filteredAnuncios.value.some(a => selectedIds.value.includes(a.id))
)
function toggleSelectAll() {
  if (allFilteredSelected.value) {
    const visibleIds = new Set(filteredAnuncios.value.map(a => a.id))
    selectedIds.value = selectedIds.value.filter(id => !visibleIds.has(id))
  } else {
    const set = new Set(selectedIds.value)
    for (const a of filteredAnuncios.value) set.add(a.id)
    selectedIds.value = Array.from(set)
  }
}

// Ações em lote
const BATCH_CHUNK_SIZE = 5
const batchAction = ref({
  action: null,                  // 'sync_to_ml' | 'sync_stock' | 'reimport'
  ids: [],                       // listing ids
  confirming: false,
  running: false,
  cancelled: false,
  done: 0,
  success: 0,
  errors: [],                    // [{listing_id, code?, detail?, error?}]
  resultOpen: false,
})

function batchActionLabel(action) {
  return {
    sync_to_ml: 'Enviar Anúncio ao Marketplace',
    sync_stock: 'Sincronizar Estoque',
    reimport:   'Ler Anúncio do Marketplace',
    reactivate: 'Reativar Anúncio',
    drop_full:  'Deixar de Oferecer Full no ML',
  }[action] || action
}

// Ações que o frontend particiona em chunks (com progresso real + cancelável)
function isChunkedAction(action) {
  return action === 'sync_to_ml' || action === 'reactivate' || action === 'drop_full'
}

function confirmBatchAction(action) {
  if (selectedIds.value.length === 0) {
    toast.warning('Selecione pelo menos um anúncio.')
    return
  }
  batchAction.value = {
    action,
    ids: [...selectedIds.value],
    confirming: true,
    running: false,
    cancelled: false,
    done: 0,
    success: 0,
    errors: [],
    resultOpen: false,
  }
}

async function runBatchAction() {
  const b = batchAction.value
  b.confirming = false
  b.running = true

  try {
    if (b.action === 'sync_stock') {
      // Endpoint /sync-stock já aceita listing_ids — chamada única.
      try {
        const { data } = await api.post('/anuncios/sync-stock', {
          account_id: selectedAccountId.value,
          listing_ids: b.ids,
        })
        b.done = b.ids.length
        b.success = (data.updated || 0) + (data.full_read || 0)
        // error_details vem do backend — mapeia pro formato esperado
        for (const ed of data.error_details || []) {
          b.errors.push({ listing_id: ed.listing_id, error: ed.error, detail: ed })
        }
      } catch (e) {
        b.errors.push({ listing_id: 0, error: e.response?.data?.detail || 'Falha na requisição' })
      }
    } else if (b.action === 'reimport') {
      // reimport-batch também é chamada única
      try {
        const { data } = await api.post('/anuncios/reimport-batch', {
          account_id: selectedAccountId.value,
          listing_ids: b.ids,
        })
        b.done = b.ids.length
        b.success = data.updated || 0
        for (const err of data.errors || []) {
          b.errors.push({ listing_id: err.listing_id, error: err.error })
        }
      } catch (e) {
        b.errors.push({ listing_id: 0, error: e.response?.data?.detail || 'Falha na requisição' })
      }
    } else if (b.action === 'sync_to_ml' || b.action === 'reactivate' || b.action === 'drop_full') {
      // Endpoints batch que processam por listing — particiona em chunks para barra
      const endpoint = b.action === 'sync_to_ml'
        ? '/anuncios/sync-to-ml-batch'
        : b.action === 'reactivate'
        ? '/anuncios/reactivate-batch'
        : '/anuncios/switch-to-cross-docking-batch'
      for (let i = 0; i < b.ids.length; i += BATCH_CHUNK_SIZE) {
        if (b.cancelled) break
        const chunk = b.ids.slice(i, i + BATCH_CHUNK_SIZE)
        try {
          const { data } = await api.post(endpoint, {
            account_id: selectedAccountId.value,
            listing_ids: chunk,
          })
          b.success += data.processed || 0
          for (const err of data.errors || []) {
            b.errors.push({ listing_id: err.listing_id, code: err.code, detail: err.detail })
          }
        } catch (e) {
          for (const lid of chunk) {
            b.errors.push({ listing_id: lid, error: e.response?.data?.detail || 'Falha no chunk' })
          }
        }
        b.done = Math.min(i + chunk.length, b.ids.length)
      }
    }

    // Resumo final
    b.running = false
    b.resultOpen = true
    if (b.errors.length === 0 && b.success > 0) {
      toast.success(`${batchActionLabel(b.action)}: ${b.success} concluído(s).`)
    } else if (b.success > 0 && b.errors.length > 0) {
      toast.warning(`${batchActionLabel(b.action)}: ${b.success} OK, ${b.errors.length} erro(s).`)
    } else {
      toast.error(`${batchActionLabel(b.action)}: ${b.errors.length} erro(s).`)
    }
    await loadAnuncios()
  } finally {
    b.running = false
  }
}
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
  // Sempre limpa seleção em lote ao recarregar (incluindo troca de conta) pra
  // evitar agir sobre IDs de uma conta diferente.
  selectedIds.value = []
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

const importProgress = ref(null)  // { phase, message, elapsed } enquanto a importação roda
let _progressTimer = null

function friendlyMlError(detail, httpStatus) {
  const txt = typeof detail === 'string' ? detail : JSON.stringify(detail || {})
  const low = txt.toLowerCase()
  if (httpStatus === 504 || low.includes('504') || low.includes('gateway timeout'))
    return {
      title: 'Importação demorou demais (timeout)',
      hint: 'A importação está rodando em segundo plano no servidor — aguarde 1–2 minutos e clique em "Importar" novamente. Anúncios já salvos não são perdidos e aparecem na lista automaticamente.',
    }
  if (httpStatus === 401 || low.includes('invalid_token') || low.includes('invalid access token'))
    return {
      title: 'Token do Mercado Livre expirado',
      hint: 'Vá em Integrações → editar a conta → reconectar com o Mercado Livre. Depois tente importar de novo.',
    }
  if (httpStatus === 403)
    return {
      title: 'Acesso negado pelo Mercado Livre',
      hint: 'O token não tem permissão para listar os anúncios desta conta. Reconecte em Integrações.',
    }
  if (httpStatus === 409 || low.includes('identity mismatch') || low.includes('conta incorreta'))
    return {
      title: 'Conta incorreta',
      hint: 'O token conectado pertence a outro vendedor. Reconecte a conta correta em Integrações.',
    }
  if (low.includes('cancelled') || low.includes('network') || low.includes('timeout') || low.includes('econnaborted'))
    return {
      title: 'Conexão interrompida',
      hint: 'A conexão caiu (você fechou a página, perdeu internet ou o servidor demorou). Tente novamente — anúncios já importados não são perdidos.',
    }
  if (httpStatus === 429 || low.includes('429') || low.includes('rate limit'))
    return {
      title: 'Mercado Livre limitou a taxa de requisições',
      hint: 'Aguarde 1–2 minutos e tente de novo. Contas grandes podem precisar fracionar a importação.',
    }
  if (httpStatus >= 500)
    return {
      title: 'Erro no servidor',
      hint: 'Algo inesperado aconteceu no servidor. Tente de novo em alguns segundos. Se persistir, avise o administrador.',
    }
  return {
    title: 'Erro ao importar anúncios',
    hint: txt.length > 300 ? (txt.slice(0, 300) + '...') : txt,
  }
}

async function importAnuncios(statuses = null) {
  if (!selectedAccountId.value) return
  importing.value = true
  // statuses pode vir como evento DOM se chamado errado (@click="importAnuncios" sem ()) — proteger
  if (statuses && typeof statuses === 'object') statuses = null
  // Estado inicial do progresso
  importProgress.value = {
    phase: 'fetching',
    message: 'Buscando anúncios no Mercado Livre…',
    sub: statuses === 'all'
      ? 'Modo "Importar TUDO" — pode levar 1–2 minutos para contas grandes (>500 anúncios).'
      : 'Status padrão: active, paused, closed, under_review.',
    started_at: Date.now(),
    elapsed: 0,
    error: null,
  }
  clearInterval(_progressTimer)
  _progressTimer = setInterval(() => {
    if (importProgress.value) {
      importProgress.value = { ...importProgress.value, elapsed: Math.floor((Date.now() - importProgress.value.started_at) / 1000) }
    }
  }, 1000)
  try {
    const url = `/anuncios/import/${selectedAccountId.value}` + (statuses ? `?statuses=${encodeURIComponent(statuses)}` : '')
    // Timeout de 10min — alinhado ao nginx proxy_read_timeout 600s para contas grandes (500+ items)
    const { data } = await api.post(url, undefined, { timeout: 600000 })
    importResult.value = { ...data, _statuses: statuses || 'active,paused,closed,under_review' }
    await loadAnuncios()
  } catch (e) {
    const detailRaw = e.response?.data?.detail || e.response?.data || e.message || ''
    const friendly = friendlyMlError(detailRaw, e.response?.status)
    importProgress.value = {
      ...importProgress.value,
      phase: 'error',
      error: friendly,
    }
    // Mantém o modal de progresso aberto pra mostrar erro; usuário fecha manualmente
    return
  } finally {
    importing.value = false
    clearInterval(_progressTimer)
    // Se houve sucesso ou erro foi mostrado no modal de resultado, fecha o progresso
    if (importResult.value) {
      importProgress.value = null
    }
  }
}

async function importAllAnuncios() {
  importResult.value = null
  await importAnuncios('all')
}

function closeImportProgress() {
  importProgress.value = null
}

const showDiagnostics = ref(false)

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

// Modal pequeno de seleção de variante (quando o anúncio tem variations_json)
const variantSelectModal = ref({ show: false, listing: null, status: null, loading: false })

async function openCreateCmigModal(listing) {
  // Anúncios sem variações vão direto pro modal de criação
  const hasVars = !!listing.variations_total
  if (!hasVars) {
    return _openCreateCmigModalImpl(listing, null)
  }
  // Bloqueia se todas as variações já foram importadas
  if (listing.all_variations_imported) {
    toast.info('Todas as variações deste anúncio já foram importadas como produtos CMIG.')
    return
  }
  // Carrega status atualizado do servidor e abre modal de seleção
  variantSelectModal.value = { show: true, listing, status: null, loading: true }
  try {
    const { data } = await api.get(`/anuncios/${listing.id}/variation-import-status`)
    variantSelectModal.value.status = data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar variações')
    variantSelectModal.value.show = false
    return
  } finally {
    variantSelectModal.value.loading = false
  }
}

function pickVariantToImport(variation) {
  const listing = variantSelectModal.value.listing
  variantSelectModal.value.show = false
  _openCreateCmigModalImpl(listing, variation)
}

function _openCreateCmigModalImpl(listing, variation) {
  // variation (opcional): { id, sku, price, available_quantity, attributes_label, picture_ids, ... }
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

  // Quando importando por variação: sobrescreve SKU, EAN, preço e estoque
  // com os da variação; ajusta título adicionando o diferenciador.
  let formSku = listing.sku || ''
  let formEan = fiscal.ean || fiscal.gtin || ''
  let formTitle = listing.title_override || ''
  let formPrice = listing.sale_price || ''
  let stockOverride = listing.available_quantity ?? 0
  let variationId = null
  if (variation) {
    variationId = variation.id
    formSku = variation.sku || formSku
    formPrice = variation.price ?? formPrice
    stockOverride = variation.available_quantity ?? 0
    // Adiciona diferenciador ao título se ainda não estiver presente
    const diff = variation.attributes_label || ''
    if (diff && !formTitle.toLowerCase().includes(diff.toLowerCase())) {
      formTitle = `${formTitle} - ${diff}`.slice(0, 255)
    }
    // EAN específico da variação (vem do GTIN nos attributes)
    // Se já tem EAN, mantém; a backend tb resolve via chosen_variation
  }

  // Para o modal: força available_quantity exibida vir da variação selecionada
  const listingWithVarStock = { ...listing, available_quantity: stockOverride }

  createCmigModal.value = {
    show: true,
    listing: listingWithVarStock,
    saving: false,
    error: '',
    pictures,
    variants,
    variation_id: variationId,
    variation_label: variation?.attributes_label || null,
  }
  createCmigForm.value = {
    cmig_id:        selectedAccount.value?.cmig_id || '',
    sku_cmig:       formSku,
    title:          formTitle,
    brand:          brand,
    model:          model,
    category_name:  listing.category_name || '',
    description:    listing.description_override || '',
    video_id:       listing.video_id || '',
    sale_price:     formPrice,
    cost_price:     '',
    weight_kg:      listing.weight_kg || '',
    height_cm:      listing.height_cm || '',
    width_cm:       listing.width_cm || '',
    length_cm:      listing.length_cm || '',
    ncm:            normNcm(fiscal.ncm),
    cest:           normCest(fiscal.cest),
    ean:            formEan,
    origin:         fiscal.origin != null && fiscal.origin !== '' ? Number(fiscal.origin) : 0,
    csosn:          fiscal.csosn || fiscal.icms_csosn || null,
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
      // stock_quantity NÃO enviado — backend usa direto listing.available_quantity ou da variação
      weight_kg:      f.weight_kg      ? parseFloat(f.weight_kg)      : null,
      height_cm:      f.height_cm      ? parseFloat(f.height_cm)      : null,
      width_cm:       f.width_cm       ? parseFloat(f.width_cm)       : null,
      length_cm:      f.length_cm      ? parseFloat(f.length_cm)      : null,
      variation_id:   createCmigModal.value.variation_id || null,
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

function isFlexActive(listing) {
  return (listing.logistic_type || '').toLowerCase() === 'self_service'
}

function canToggleFlex(listing) {
  return accountCapabilities.value.has_flex
      && !listing.is_full
      && !!listing.platform_item_id
      && listing.status === 'published'
}

async function toggleFlex(listing) {
  const turningOn = !isFlexActive(listing)

  // Alert explicativo APENAS na ativação — esclarece o comportamento opt-out automático
  let msg
  if (turningOn) {
    msg = `Ativar Mercado Envios Flex no anúncio "${listing.title_override}"?

ℹ️ Como funciona o Flex:
• O Flex é AUTOMÁTICO: se sua conta tem Flex e o item é elegível pela categoria/região, ele já é oferecido sem você precisar fazer nada.
• Use esta ação APENAS se você desativou o Flex deste anúncio antes e quer reativar.
• Você se compromete a entregar no mesmo dia/24h pela região elegível.

Deseja continuar?`
  } else {
    msg = `Desativar Mercado Envios Flex no anúncio "${listing.title_override}"?

Após desativar, este anúncio não será mais oferecido com Flex (mesmo que sua conta tenha Flex habilitado).`
  }

  if (!confirm(msg)) return

  try {
    const { data } = await api.post(`/anuncios/${listing.id}/toggle-flex`, { enable: turningOn })
    const idx = anuncios.value.findIndex(a => a.id === listing.id)
    if (idx !== -1) anuncios.value[idx] = data
    if (data._already_in_state) {
      toast.info(turningOn ? 'Flex já estava ativo neste anúncio.' : 'Flex já estava desativado neste anúncio.')
    } else {
      toast.success(turningOn ? 'Flex ativado no anúncio!' : 'Flex desativado.')
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao alterar Flex')
  }
}

// Badge informativo do logistic_type real (passivo — ação é o botão ⚡ ao lado)
function logisticBadge(listing) {
  const lt = (listing.logistic_type || '').toLowerCase()
  if (!lt) return null
  if (lt === 'self_service') {
    return {
      label: 'Flex', icon: 'fa-bolt', cls: 'badge-warning',
      title: 'Mercado Envios Flex — entrega mesmo dia/24h. Definido automaticamente pelo ML.',
    }
  }
  if (lt === 'fulfillment') {
    return {
      label: 'Full', icon: 'fa-warehouse', cls: 'badge-info',
      title: 'Mercado Envios Full — estoque e logística pelo galpão do ML.',
    }
  }
  // ME2 (cross_docking/drop_off/xd_drop_off) é o padrão e não recebe badge — reduz ruído visual.
  return null
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

async function switchToCrossDocking(listing) {
  if (!confirm(`Converter "${listing.title_override}" de Full para cross-docking?\n\nO estoque do galpão do seller será usado como disponível.`)) return
  try {
    const { data } = await api.post(`/anuncios/${listing.id}/switch-to-cross-docking`)
    const idx = anuncios.value.findIndex(a => a.id === listing.id)
    if (idx !== -1) anuncios.value[idx] = data
    toast.success('Anúncio convertido para cross-docking com sucesso.')
  } catch (e) {
    const detail = e.response?.data?.detail || 'Erro ao converter para cross-docking.'
    // Se contém URL do Seller Center, abre em nova aba além do toast
    const urlMatch = detail.match(/https?:\/\/\S+/)
    if (urlMatch) {
      toast.warning(detail.replace(urlMatch[0], '').trim())
      if (confirm(`Este anúncio é do catálogo do ML e não pode ser alterado via API.\n\nDeseja abrir o Seller Center para fazer a conversão manualmente?`)) {
        window.open(urlMatch[0], '_blank')
      }
    } else {
      toast.error(detail)
    }
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

function openConflictModal(listing, detail, attempted = []) {
  conflictModal.value = {
    show: true,
    listing,
    userProductId: detail.user_product_id,
    currentItemId: detail.current_item_id,
    candidates: detail.candidates || [],
    suggestedDeleteItemId: detail.suggested_delete_item_id || null,
    selectedDeleteItemId: detail.suggested_delete_item_id || null,
    attemptedItemIds: attempted,
    deleting: false,
  }
  if (!detail.candidates || detail.candidates.length === 0) {
    toast.warning(detail.message || 'Conflito detectado, mas sem candidatos para excluir.')
  }
}

async function resolveConflict() {
  const m = conflictModal.value
  if (!m.selectedDeleteItemId || !m.listing) return
  m.deleting = true
  try {
    const { data } = await api.post(
      `/anuncios/${m.listing.id}/resolve-user-product-conflict`,
      {
        delete_item_id: m.selectedDeleteItemId,
        retry_sync: true,
        attempted_item_ids: m.attemptedItemIds || [],
      },
    )
    toast.success(`Anúncio ${data.deleted_item_id} fechado no ML. Sincronização concluída.`)
    conflictModal.value.show = false
    await loadAnuncios()
  } catch (e) {
    const detail = e.response?.data?.detail
    if (e.response?.status === 409 && detail && detail.error === 'user_product_repeated_conflict') {
      // Ainda há outro conflito — reabre o modal com os candidatos atualizados
      // e a lista cumulativa de MLBs já fechados para o backend respeitar o cap.
      const attempted = detail.previous_deleted_item_ids || m.attemptedItemIds || []
      openConflictModal(m.listing, detail, attempted)
      toast.warning('Ainda há anúncios duplicados. Escolha o próximo a excluir.')
      return
    }
    toast.error(typeof detail === 'string' ? detail : 'Erro ao resolver conflito')
  } finally {
    if (conflictModal.value) conflictModal.value.deleting = false
  }
}

function mlStatusBadgeClass(status) {
  switch ((status || '').toLowerCase()) {
    case 'active': return 'badge-success'
    case 'paused': return 'badge-warning'
    case 'closed': return 'badge-secondary'
    case 'under_review': return 'badge-info'
    default: return 'badge-light'
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
  if (a.thumbnail && !isProcessingPlaceholder(a.thumbnail)) return a.thumbnail
  const imgs = a.cmig_product?.images || a.catalog_product?.images || []
  const first = imgs[0]
  if (!first) return null
  return first.url || first
}

function isProcessingPlaceholder(url) {
  return typeof url === 'string' && url.toLowerCase().includes('processing-image')
}

function listingHasProcessingPictures(a) {
  if (isProcessingPlaceholder(a.thumbnail)) return true
  if (!a.pictures_json) return false
  try {
    const pics = JSON.parse(a.pictures_json)
    if (!Array.isArray(pics) || !pics.length) return false
    return pics.every(p => isProcessingPlaceholder(p?.url))
  } catch {
    return false
  }
}

const refreshingPictures = ref({})
async function refreshListingPictures(a) {
  refreshingPictures.value = { ...refreshingPictures.value, [a.id]: true }
  try {
    const { data } = await api.post(`/anuncios/${a.id}/refresh-pictures`)
    if (data.still_processing) {
      toast.warning('ML ainda está processando — tente de novo em alguns segundos.')
    } else {
      toast.success(`Fotos atualizadas (${data.pictures_count}).`)
      await loadAnuncios()
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao atualizar fotos.')
  } finally {
    const novo = { ...refreshingPictures.value }
    delete novo[a.id]
    refreshingPictures.value = novo
  }
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
  if (listing.is_flex) return 'ME2 Flex'
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
