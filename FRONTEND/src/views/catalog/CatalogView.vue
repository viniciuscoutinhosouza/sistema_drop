<template>
  <!-- Page Header -->
  <div class="content-header">
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-6">
          <h1 class="m-0">Catálogo</h1>
        </div>
      </div>
    </div>
  </div>

  <section class="content">
    <div class="container-fluid">

      <!-- Seletor de conta -->
      <div class="card card-outline card-primary mb-3">
        <div class="card-body py-2">
          <div class="d-flex align-items-center flex-wrap" style="gap:12px">
            <label class="mb-0 text-muted small font-weight-bold">Conta para publicar:</label>
            <select v-model="selectedAccountId" class="form-control form-control-sm" style="width:auto;min-width:280px">
              <option value="">Selecione uma conta...</option>
              <option v-for="a in accounts" :key="a.id" :value="a.id">
                {{ a.platform_label }} — {{ a.description || a.platform_username || a.email }}
              </option>
            </select>
            <span v-if="!selectedAccountId" class="text-warning small">
              <i class="fas fa-exclamation-triangle mr-1"></i>Selecione uma conta para publicar anúncios
            </span>
            <span v-else class="text-success small">
              <i class="fas fa-check-circle mr-1"></i>Conta selecionada
            </span>
          </div>
        </div>
      </div>

      <!-- Toggle PG / CMIG + Atalho Anúncio com Variações -->
      <div class="mb-3 d-flex flex-wrap align-items-center" style="gap:8px">
        <div class="btn-group">
          <button class="btn" :class="catalogTab === 'pg' ? 'btn-primary' : 'btn-outline-primary'" @click="catalogTab = 'pg'">
            <i class="fas fa-warehouse mr-1"></i> Catálogo PG
          </button>
          <button class="btn" :class="catalogTab === 'cmig' ? 'btn-primary' : 'btn-outline-primary'" @click="catalogTab = 'cmig'">
            <i class="fas fa-id-card mr-1"></i> Catálogo CMIG
          </button>
        </div>
        <button
          class="btn btn-outline-success ml-auto"
          :disabled="!selectedAccountId || !isMercadoLivre"
          :title="variationsTooltip"
          @click="openVariationsCategoryPicker"
        >
          <i class="fas fa-layer-group mr-1"></i> Anúncio com Variações
        </button>
      </div>

      <!-- Barra de seleção múltipla (aparece quando >= 2 produtos selecionados) -->
      <div
        v-if="currentSelectionCount >= 2"
        class="alert alert-success py-2 mb-3 d-flex flex-wrap align-items-center"
        style="gap:12px"
      >
        <i class="fas fa-check-square mr-1"></i>
        <strong>{{ currentSelectionCount }} produto(s) selecionado(s)</strong>
        <span class="text-muted small">
          · publicar como família (categorias User Products do ML)
        </span>
        <button class="btn btn-sm btn-success ml-auto" @click="openAgruparModal">
          <i class="fas fa-object-group mr-1"></i> Agrupar Anúncios
        </button>
        <button class="btn btn-sm btn-outline-secondary" @click="clearCurrentSelection">
          <i class="fas fa-times mr-1"></i> Limpar seleção
        </button>
      </div>

      <template v-if="catalogTab === 'pg'">

      <!-- Filtros -->
      <div class="card mb-3">
        <div class="card-body py-2">
          <div class="row align-items-center">
            <div class="col-md-4">
              <div class="input-group input-group-sm">
                <input v-model="filters.search" type="text" class="form-control" placeholder="Buscar produto..." @keyup.enter="applyFilter" />
                <div class="input-group-append">
                  <button class="btn btn-primary" @click="applyFilter"><i class="fas fa-search"></i></button>
                </div>
              </div>
            </div>
            <div class="col-md-3">
              <select v-model="filters.category_id" class="form-control form-control-sm" @change="applyFilter">
                <option value="">Todas as categorias</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
              </select>
            </div>
            <div class="col-md-3">
              <select v-model="filters.sort" class="form-control form-control-sm" @change="applyFilter">
                <option value="newest">Mais recentes</option>
                <option value="cheapest">Menor preço</option>
                <option value="expensive">Maior preço</option>
              </select>
            </div>
            <div class="col-md-2">
              <select v-model="filters.page_size" class="form-control form-control-sm" @change="applyFilter">
                <option :value="12">12 por página</option>
                <option :value="24">24 por página</option>
                <option :value="48">48 por página</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-5">
        <i class="fas fa-spinner fa-spin fa-3x text-muted"></i>
      </div>

      <!-- Grade de produtos -->
      <div v-else>
        <div class="row">
          <div v-for="product in products" :key="product.id" class="col-xl-2 col-lg-3 col-md-4 col-sm-6 mb-3">
            <div
              class="card h-100 shadow-sm position-relative"
              :class="{ 'border-success': selectedPgIds.has(product.id) }"
              :style="selectedPgIds.has(product.id) ? 'border-width:2px' : ''"
            >
              <!-- Checkbox de seleção múltipla -->
              <div
                class="position-absolute"
                style="top:6px;left:6px;z-index:2;background:rgba(255,255,255,.9);border-radius:4px;padding:2px 6px"
                @click.stop="togglePgSelection(product.id)"
              >
                <input
                  type="checkbox"
                  :checked="selectedPgIds.has(product.id)"
                  @click.stop="togglePgSelection(product.id)"
                  :title="selectedPgIds.has(product.id) ? 'Desselecionar' : 'Selecionar para agrupar'"
                />
              </div>
              <!-- Ícone: produto já publicado nesta conta (vínculo PG) -->
              <div
                v-if="publishedFor(product, 'pg')"
                class="position-absolute"
                style="top:6px;right:6px;z-index:2;cursor:pointer"
                title="Já publicado nesta conta — ver anúncios"
                @click.stop="openPublishedModal(product, 'pg')"
              >
                <span class="badge badge-success" style="font-size:11px;box-shadow:0 1px 3px rgba(0,0,0,.3)">
                  <i class="fas fa-bullhorn"></i> {{ publishedFor(product, 'pg').length }}
                </span>
              </div>
              <RouterLink :to="`/catalog/${product.id}`">
                <div style="height:130px;background:#f8f9fa;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px 4px 0 0">
                  <img
                    :src="product.image_url || 'https://via.placeholder.com/300x200?text=Sem+Foto'"
                    :style="isSoldOut(product)
                      ? 'max-height:100%;max-width:100%;object-fit:contain;filter:grayscale(1);opacity:.45'
                      : 'max-height:100%;max-width:100%;object-fit:contain'"
                    :alt="product.title"
                  />
                </div>
              </RouterLink>
              <div class="card-body p-2">
                <div class="text-muted mb-1" style="font-size:10px">({{ product.sku }})</div>
                <div
                  class="font-weight-bold mb-2"
                  style="font-size:12px;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.6em"
                  :title="product.title"
                >
                  {{ product.title }}
                </div>
                <div class="text-success font-weight-bold mb-1 text-left" style="font-size:14px">
                  {{ formatCurrency(product.cost_price) }}
                </div>
                <div class="text-muted text-left" style="font-size:11px">
                  Estoque: {{ product.stock_quantity }}
                </div>
              </div>
              <div class="card-footer p-1">
                <button
                  v-if="isSoldOut(product)"
                  class="btn btn-secondary btn-sm btn-block"
                  style="font-size:11px;padding:3px 6px"
                  disabled
                  title="Sem estoque — produto esgotado"
                >
                  <i class="fas fa-ban mr-1"></i> Esgotado
                </button>
                <button
                  v-else
                  class="btn btn-success btn-sm btn-block"
                  style="font-size:11px;padding:3px 6px"
                  :disabled="!selectedAccountId"
                  :title="!selectedAccountId ? 'Selecione uma conta acima' : ''"
                  @click="openPublishModal(product)"
                >
                  <i class="fas fa-bullhorn mr-1"></i> Publicar
                </button>
              </div>
            </div>
          </div>
        </div>

        <div v-if="!products.length" class="text-center py-5 text-muted">
          <i class="fas fa-box-open fa-3x mb-3"></i>
          <p>Nenhum produto encontrado</p>
        </div>

        <!-- Paginação -->
        <nav v-if="totalPages > 1" class="mt-3">
          <ul class="pagination justify-content-center">
            <li :class="['page-item', currentPage <= 1 && 'disabled']">
              <button class="page-link" @click="goToPage(currentPage - 1)">Anterior</button>
            </li>
            <li v-for="p in paginationRange" :key="p" :class="['page-item', p === currentPage && 'active']">
              <button class="page-link" @click="goToPage(p)">{{ p }}</button>
            </li>
            <li :class="['page-item', currentPage >= totalPages && 'disabled']">
              <button class="page-link" @click="goToPage(currentPage + 1)">Próxima</button>
            </li>
          </ul>
        </nav>
      </div>

      </template><!-- end catalogTab === 'pg' -->

      <!-- ── Catálogo CMIG ── -->
      <template v-else>

        <!-- Conta não selecionada -->
        <div v-if="!selectedAccountId" class="text-center py-5 text-muted">
          <i class="fas fa-hand-point-up fa-3x mb-3 d-block"></i>
          <p>Selecione uma conta de marketplace acima para ver o Catálogo CMIG vinculado</p>
        </div>

        <!-- Conta sem CMIG vinculada -->
        <div v-else-if="!derivedCmigId" class="alert alert-warning">
          <i class="fas fa-exclamation-triangle mr-1"></i>
          A conta de marketplace selecionada não possui uma CMIG vinculada.
        </div>

        <!-- Catálogo CMIG da conta -->
        <template v-else>

          <div class="card card-outline card-warning mb-3">
            <div class="card-body py-2">
              <div class="d-flex align-items-center flex-wrap" style="gap:12px">
                <span class="text-muted small font-weight-bold">CMIG:</span>
                <span class="font-weight-bold">
                  <i class="fas fa-id-card mr-1 text-warning"></i>
                  {{ activeCmig?.company_name || `#${derivedCmigId}` }}
                </span>
                <div class="btn-group btn-group-sm ml-auto">
                  <button class="btn btn-outline-secondary" :class="{ active: cmigFilter === 'all' }" @click="cmigFilter = 'all'">Todos</button>
                  <button class="btn btn-outline-secondary" :class="{ active: cmigFilter === 'simple' }" @click="cmigFilter = 'simple'">Simples</button>
                  <button class="btn btn-outline-secondary" :class="{ active: cmigFilter === 'kit' }" @click="cmigFilter = 'kit'">KITs</button>
                </div>
              </div>
            </div>
          </div>

          <div v-if="cmigLoading" class="text-center py-5">
            <i class="fas fa-spinner fa-spin fa-3x text-muted"></i>
          </div>

          <div v-else>
            <div class="row">
              <div v-for="product in filteredCmigProducts" :key="product.id" class="col-xl-2 col-lg-3 col-md-4 col-sm-6 mb-3">
                <div
                  class="card h-100 shadow-sm position-relative"
                  :class="{ 'border-success': selectedCmigIds.has(product.id) }"
                  :style="selectedCmigIds.has(product.id) ? 'border-width:2px' : ''"
                >
                  <div
                    class="position-absolute"
                    style="top:6px;left:6px;z-index:2;background:rgba(255,255,255,.9);border-radius:4px;padding:2px 6px"
                    @click.stop="toggleCmigSelection(product.id)"
                  >
                    <input
                      type="checkbox"
                      :checked="selectedCmigIds.has(product.id)"
                      @click.stop="toggleCmigSelection(product.id)"
                      :title="selectedCmigIds.has(product.id) ? 'Desselecionar' : 'Selecionar para agrupar'"
                    />
                  </div>
                  <!-- Ícone: produto já publicado nesta conta (vínculo CMIG) -->
                  <div
                    v-if="publishedFor(product, 'cmig')"
                    class="position-absolute"
                    style="top:6px;right:6px;z-index:2;cursor:pointer"
                    title="Já publicado nesta conta — ver anúncios"
                    @click.stop="openPublishedModal(product, 'cmig')"
                  >
                    <span class="badge badge-success" style="font-size:11px;box-shadow:0 1px 3px rgba(0,0,0,.3)">
                      <i class="fas fa-bullhorn"></i> {{ publishedFor(product, 'cmig').length }}
                    </span>
                  </div>
                  <div style="height:130px;background:#f8f9fa;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px 4px 0 0">
                    <img
                      :src="getCmigThumb(product) || 'https://via.placeholder.com/300x200?text=Sem+Foto'"
                      :style="isSoldOut(product)
                        ? 'max-height:100%;max-width:100%;object-fit:contain;filter:grayscale(1);opacity:.45'
                        : 'max-height:100%;max-width:100%;object-fit:contain'"
                      :alt="product.title"
                    />
                  </div>
                  <div class="card-body p-2">
                    <div class="text-muted mb-1" style="font-size:10px">
                      <span v-if="product.is_composite" class="badge badge-warning mr-1" style="font-size:9px">KIT</span>
                      ({{ product.sku_cmig }})
                    </div>
                    <div
                      class="font-weight-bold mb-2"
                      style="font-size:12px;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.6em"
                      :title="product.title"
                    >
                      {{ product.title }}
                    </div>
                    <div class="text-success font-weight-bold mb-1 text-left" style="font-size:14px">
                      {{ formatCurrency(product.cost_price) }}
                    </div>
                    <div class="text-muted text-left" style="font-size:11px">
                      Estoque: {{ product.stock_quantity }}
                    </div>
                  </div>
                  <div class="card-footer p-1">
                    <button
                      v-if="isSoldOut(product)"
                      class="btn btn-secondary btn-sm btn-block"
                      style="font-size:11px;padding:3px 6px"
                      disabled
                      title="Sem estoque — produto esgotado"
                    >
                      <i class="fas fa-ban mr-1"></i> Esgotado
                    </button>
                    <button
                      v-else
                      class="btn btn-success btn-sm btn-block"
                      style="font-size:11px;padding:3px 6px"
                      :disabled="!selectedAccountId"
                      :title="!selectedAccountId ? 'Selecione uma conta de marketplace acima' : ''"
                      @click="openPublishModalFromCmig(product)"
                    >
                      <i class="fas fa-bullhorn mr-1"></i> Publicar
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="filteredCmigProducts.length === 0" class="text-center py-5 text-muted">
              <i class="fas fa-box-open fa-3x mb-3"></i>
              <p>Nenhum produto encontrado</p>
            </div>
          </div>

        </template><!-- end derivedCmigId -->

      </template><!-- end catalogTab === 'cmig' -->

    </div>
  </section>

  <!-- ── Modal: Agrupar Anúncios (User Products) ── -->
  <AgruparAnunciosModal
    v-if="agruparModal.show"
    :account-id="selectedAccountId"
    :account-label="selectedAccountLabel"
    :source="agruparModal.source"
    :products="agruparModal.products"
    @close="onAgruparClose"
  />

  <!-- ── Modal: Anúncios já publicados (métricas) ── -->
  <div v-if="publishedModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1060">
    <div class="modal-dialog modal-xl">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-bullhorn mr-2 text-success"></i>Anúncios publicados — {{ publishedModal.title }}</h5>
          <button type="button" class="close" @click="publishedModal.show = false"><span>&times;</span></button>
        </div>
        <div class="modal-body p-0">
          <table class="table table-sm table-hover mb-0">
            <thead class="thead-light">
              <tr>
                <th style="width:64px">Foto</th>
                <th style="width:160px">Nº do anúncio</th>
                <th>Título</th>
                <th class="text-center" style="width:100px">Visitas (7d)</th>
                <th class="text-center" style="width:90px">Vendas</th>
                <th class="text-center" style="width:110px">Conversão</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="l in publishedModal.listings" :key="l.listing_id">
                <td>
                  <div style="width:48px;height:48px;background:#f8f9fa;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px">
                    <img :src="l.thumbnail || 'https://via.placeholder.com/48?text=%E2%80%94'" style="max-width:100%;max-height:100%;object-fit:contain" />
                  </div>
                </td>
                <td>
                  <a v-if="l.permalink" :href="l.permalink" target="_blank" rel="noopener">
                    {{ l.platform_item_id }} <i class="fas fa-external-link-alt" style="font-size:9px"></i>
                  </a>
                  <span v-else>{{ l.platform_item_id }}</span>
                  <span v-if="l.status && l.status !== 'published'" class="badge badge-light border ml-1" style="font-size:9px">{{ l.status }}</span>
                </td>
                <td style="font-size:12px">{{ l.title }}</td>
                <td class="text-center">{{ l.visits_7d }}</td>
                <td class="text-center font-weight-bold">{{ l.sold_quantity }}</td>
                <td class="text-center">
                  <span :class="l.conversion != null && l.conversion > 0 ? 'text-success font-weight-bold' : 'text-muted'">
                    {{ l.conversion != null ? l.conversion + '%' : '—' }}
                  </span>
                </td>
              </tr>
              <tr v-if="!publishedModal.listings.length">
                <td colspan="6" class="text-center text-muted py-3">Nenhum anúncio publicado.</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="modal-footer">
          <small class="text-muted mr-auto">Conversão = vendas ÷ visitas (7 dias).</small>
          <button class="btn btn-secondary" @click="publishedModal.show = false">Fechar</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Modal: Pré-validação de categoria para 'Anúncio com Variações' ── -->
  <div v-if="variationsCategoryModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1060">
    <div class="modal-dialog modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-layer-group mr-2 text-success"></i>Anúncio com Variações
          </h5>
          <button type="button" class="close" @click="closeVariationsCategoryPicker"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <p class="text-muted small mb-2">
            Selecione a categoria do Mercado Livre. Vamos validar se ela aceita variações tradicionais
            (1 anúncio com array de variações) antes de abrir o assistente.
          </p>
          <div class="input-group input-group-sm mb-2">
            <input
              v-model="variationsCategoryModal.catSearch"
              type="text" class="form-control"
              placeholder="Buscar categoria ML..."
              @input="onVarCatSearchInput"
            />
            <div class="input-group-append">
              <span class="input-group-text"><i class="fas fa-search"></i></span>
            </div>
          </div>
          <div v-if="variationsCategoryModal.catSearching" class="text-muted small">
            <i class="fas fa-spinner fa-spin mr-1"></i>Buscando...
          </div>
          <div v-if="variationsCategoryModal.catResults.length" class="list-group mb-2" style="max-height:280px;overflow-y:auto">
            <button
              v-for="cat in variationsCategoryModal.catResults" :key="cat.id" type="button"
              class="list-group-item list-group-item-action py-2"
              @click="selectVarCategory(cat)"
            >
              <div v-if="cat.path_from_root && cat.path_from_root.length" class="d-flex flex-wrap" style="gap:3px;font-size:12px">
                <template v-for="(p,i) in cat.path_from_root" :key="p.id || i">
                  <span :class="i === cat.path_from_root.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">{{ p.name }}</span>
                  <i v-if="i < cat.path_from_root.length - 1" class="fas fa-angle-right text-muted" style="font-size:10px"></i>
                </template>
              </div>
              <code class="text-muted d-block" style="font-size:10px">{{ cat.id }}</code>
            </button>
          </div>

          <div v-if="variationsCategoryModal.selected" class="p-2 border rounded bg-light mb-2">
            <div class="font-weight-bold" style="font-size:13px">{{ variationsCategoryModal.selected.name }}</div>
            <code class="text-muted" style="font-size:11px">ID: {{ variationsCategoryModal.selected.id }}</code>
          </div>

          <div v-if="variationsCategoryModal.supportLoading" class="text-muted small">
            <i class="fas fa-spinner fa-spin mr-1"></i>Validando categoria...
          </div>

          <div v-else-if="variationsCategoryModal.support" class="mt-2">
            <div v-if="variationsCategoryModal.support.requires_family_name" class="alert alert-warning py-2 small mb-0">
              <i class="fas fa-info-circle mr-1"></i>
              <strong>Categoria User Products.</strong> Cada variação é um anúncio separado — não dá pra usar
              array de variações. Use a opção <strong>"Agrupar Anúncios"</strong> selecionando vários produtos
              do catálogo (volte e marque os checkboxes).
            </div>
            <div v-else-if="!variationsCategoryModal.support.supports_variations" class="alert alert-danger py-2 small mb-0">
              <i class="fas fa-times-circle mr-1"></i>
              Esta categoria <strong>não aceita variações</strong> no Mercado Livre.
            </div>
            <div v-else class="alert alert-success py-2 small mb-0">
              <i class="fas fa-check-circle mr-1"></i>
              Categoria aceita variações por:
              <strong>{{ (variationsCategoryModal.support.variation_combination_attrs || []).map(a => a.name).join(', ') || 'atributos personalizados' }}</strong>.
            </div>
          </div>

          <div v-if="variationsCategoryModal.error" class="alert alert-danger py-2 mt-2 small">
            {{ variationsCategoryModal.error }}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeVariationsCategoryPicker">Cancelar</button>
          <button
            class="btn btn-success"
            :disabled="!variationsCategoryModal.support || variationsCategoryModal.support.requires_family_name || !variationsCategoryModal.support.supports_variations"
            @click="proceedToVariationsWizard"
          >
            <i class="fas fa-arrow-right mr-1"></i>Continuar
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- ── Modal: Publicar Anúncio ── -->
  <div v-if="modal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.55);z-index:1050">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">

        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-bullhorn mr-2"></i>Publicar Anúncio</h5>
          <button type="button" class="close" @click="closeModal"><span>&times;</span></button>
        </div>

        <div class="modal-body">

          <!-- Produto de origem -->
          <div class="d-flex align-items-center mb-3 p-2 bg-light rounded" style="gap:12px">
            <img v-if="modal.product?.image_url" :src="modal.product.image_url"
                 style="width:56px;height:56px;object-fit:cover;border-radius:4px" />
            <div>
              <div class="font-weight-bold">{{ modal.product?.title }}</div>
              <div class="text-muted small">SKU: {{ modal.product?.sku }} · Custo: {{ formatCurrency(modal.product?.cost_price) }}</div>
            </div>
          </div>

          <!-- Marketplace -->
          <div class="form-group">
            <label class="font-weight-bold">Marketplace</label>
            <input class="form-control" :value="selectedAccountLabel" disabled />
          </div>

          <!-- Tipo do Anúncio — Mercado Livre -->
          <div v-if="isMercadoLivre" class="form-group">
            <label class="font-weight-bold">Tipo do Anúncio <span class="text-danger">*</span></label>
            <div class="d-flex" style="gap:12px">
              <div
                class="card flex-fill text-center p-3"
                style="cursor:pointer;border-width:2px;transition:border-color .15s"
                :style="form.listing_type === 'gold_special' ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                @click="form.listing_type = 'gold_special'"
              >
                <div style="font-size:22px" class="mb-1">⭐</div>
                <div class="font-weight-bold">Clássico</div>
                <div class="text-muted small">Comissão menor · Exposição padrão</div>
              </div>
              <div
                class="card flex-fill text-center p-3"
                style="cursor:pointer;border-width:2px;transition:border-color .15s"
                :style="form.listing_type === 'gold_pro' ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                @click="form.listing_type = 'gold_pro'"
              >
                <div style="font-size:22px" class="mb-1">🏆</div>
                <div class="font-weight-bold">Premium</div>
                <div class="text-muted small">Maior comissão · Máxima exposição</div>
              </div>
            </div>
          </div>

          <!-- Título -->
          <div class="form-group">
            <label class="font-weight-bold">Título do Anúncio <span class="text-danger">*</span></label>
            <input v-model="form.title" type="text" class="form-control" maxlength="60"
                   placeholder="Título que aparece no marketplace" />
            <small class="text-muted">{{ form.title.length }}/60 caracteres</small>
          </div>

          <!-- Nome da Família (User Products) — só aparece quando a categoria exige -->
          <div v-if="catSupport && catSupport.requires_family_name" class="form-group">
            <label class="font-weight-bold">
              Nome da Família <span class="text-danger">*</span>
              <span class="badge badge-info ml-1" style="font-size:10px">User Products</span>
            </label>
            <input v-model="form.family_name" type="text" class="form-control" maxlength="60"
                   :placeholder="form.title || 'Ex: Rolo Massagem Foam Roller 30cm'" />
            <small class="text-muted">
              Todos os anúncios do mesmo grupo devem ter <strong>exatamente o mesmo nome</strong>.
              O ML usa este campo para exibir os anúncios como seletores de variação (cor, tamanho) na VIP.
            </small>
          </div>

          <!-- Modelo -->
          <div class="form-group">
            <label class="font-weight-bold">Modelo</label>
            <input v-model="form.model" type="text" class="form-control"
                   placeholder="Ex: Galaxy S24, RTX 4060, 12V 7Ah..." />
            <small class="text-muted">Obrigatório em algumas categorias do Mercado Livre.</small>
          </div>

          <!-- Categoria + Características (componente reutilizável) -->
          <div class="form-group">
            <PublishCategoryPicker
              v-if="modal.show && pickerOwnerId && pickerMarketplace"
              :key="`${pickerOwnerType}-${pickerOwnerId}-${pickerMarketplace}`"
              :owner-type="pickerOwnerType"
              :owner-id="pickerOwnerId"
              :marketplace="pickerMarketplace"
              :product-hints="{ brand: modal.product?.brand, model: form.model }"
              v-model="categorySel"
            />
          </div>

          <!-- ── Fotos ── -->
          <div class="form-group">
            <label class="font-weight-bold">Fotos do Anúncio</label>
            <div class="small text-muted mb-2">
              A <strong>primeira foto</strong> será usada como capa.
              Clique nas imagens do produto para adicioná-las, ou faça upload/cole uma URL.
            </div>

            <!-- Fotos selecionadas -->
            <div v-if="form.pictures.length" class="mb-2">
              <div class="d-flex flex-wrap" style="gap:8px">
                <div v-for="(url, i) in form.pictures" :key="i" class="position-relative">
                  <img :src="url" style="width:80px;height:80px;object-fit:cover;border-radius:4px;border:2px solid #007bff" />
                  <span v-if="i === 0"
                        class="position-absolute badge badge-primary"
                        style="top:2px;left:2px;font-size:9px;padding:2px 4px">
                    Capa
                  </span>
                  <button type="button" @click="removePicture(i)"
                          class="btn btn-danger position-absolute"
                          style="top:-6px;right:-6px;width:20px;height:20px;padding:0;line-height:1;border-radius:50%;font-size:10px">
                    <i class="fas fa-times"></i>
                  </button>
                </div>
              </div>
              <small class="text-muted d-block mt-1">{{ form.pictures.length }} foto(s) selecionada(s)</small>
            </div>
            <div v-else class="alert alert-warning py-2 mb-2" style="font-size:13px">
              <i class="fas fa-exclamation-circle mr-1"></i>Nenhuma foto selecionada. Selecione pelo menos uma abaixo.
            </div>

            <!-- Galeria do produto (busca ao abrir modal) -->
            <div class="mb-2">
              <div class="text-muted small font-weight-bold mb-1">
                <i class="fas fa-images mr-1"></i>Imagens do produto — clique para adicionar:
              </div>
              <div v-if="modal.loadingImages" class="text-muted small">
                <i class="fas fa-spinner fa-spin mr-1"></i>Carregando imagens...
              </div>
              <div v-else-if="modal.productImages.length" class="d-flex flex-wrap" style="gap:8px">
                <div v-for="(img, i) in modal.productImages" :key="i"
                     class="position-relative" style="cursor:pointer" @click="toggleProductImage(img.url)">
                  <img :src="img.url"
                       style="width:72px;height:72px;object-fit:cover;border-radius:4px;transition:opacity .15s"
                       :style="isSelected(img.url) ? 'outline:3px solid #28a745;opacity:1' : 'outline:3px solid #dee2e6;opacity:.75'" />
                  <span v-if="isSelected(img.url)"
                        class="position-absolute d-flex align-items-center justify-content-center bg-success text-white"
                        style="top:2px;right:2px;width:18px;height:18px;border-radius:50%;font-size:10px">
                    <i class="fas fa-check"></i>
                  </span>
                </div>
              </div>
              <div v-else class="text-muted small">Nenhuma imagem cadastrada neste produto.</div>
            </div>

            <!-- Adicionar por URL -->
            <div class="input-group input-group-sm mb-2" style="max-width:480px">
              <input v-model="newPhotoUrl" class="form-control"
                     placeholder="Cole uma URL de imagem (https://...)" @keyup.enter="addPhotoByUrl" />
              <div class="input-group-append">
                <button type="button" class="btn btn-outline-secondary" @click="addPhotoByUrl"
                        :disabled="!newPhotoUrl.trim()">
                  <i class="fas fa-link mr-1"></i>Adicionar URL
                </button>
              </div>
            </div>

            <!-- Upload de arquivo -->
            <div>
              <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp,image/gif"
                     class="d-none" @change="uploadPhoto" />
              <button type="button" class="btn btn-sm btn-outline-primary"
                      @click="fileInput.click()" :disabled="uploading">
                <i :class="['fas', uploading ? 'fa-spinner fa-spin' : 'fa-upload', 'mr-1']"></i>
                {{ uploading ? 'Enviando...' : 'Upload de foto' }}
              </button>
            </div>
          </div>

          <!-- Preço -->
          <div class="form-group">
            <label class="font-weight-bold">Preço de Venda (R$) <span class="text-danger">*</span></label>
            <input v-model="form.sale_price" type="number" step="0.01" min="0"
                   class="form-control" placeholder="0,00" style="max-width:200px" />
          </div>

          <!-- Quem paga o frete (ML) -->
          <div v-if="isMercadoLivre" class="form-group">
            <label class="font-weight-bold">Pagamento do Frete</label>
            <div class="d-flex" style="gap:12px">
              <div class="card flex-fill text-center p-3"
                   style="cursor:pointer;border-width:2px;transition:border-color .15s"
                   :style="!form.free_shipping ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                   @click="form.free_shipping = false">
                <div style="font-size:20px" class="mb-1">🛒</div>
                <div class="font-weight-bold">Comprador paga</div>
                <div class="text-muted small">Frete cobrado do comprador</div>
              </div>
              <div class="card flex-fill text-center p-3"
                   style="cursor:pointer;border-width:2px;transition:border-color .15s"
                   :style="form.free_shipping ? 'border-color:#28a745;background:#f0fff4' : 'border-color:#dee2e6'"
                   @click="form.free_shipping = true">
                <div style="font-size:20px" class="mb-1">🚚</div>
                <div class="font-weight-bold text-success">Vendedor paga</div>
                <div class="text-muted small">Anúncio com Frete Grátis</div>
              </div>
            </div>
          </div>

          <!-- Estoque -->
          <div v-if="isMercadoLivre" class="form-group">
            <label class="font-weight-bold">Estoque</label>
            <div class="d-flex mb-2" style="gap:12px">
              <div class="card flex-fill text-center p-3"
                   style="cursor:pointer;border-width:2px;transition:border-color .15s"
                   :style="form.stock_mode === 'product' ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                   @click="form.stock_mode = 'product'">
                <div style="font-size:20px" class="mb-1">📦</div>
                <div class="font-weight-bold">Estoque do Produto</div>
                <div class="text-muted small">
                  {{ modal.product?.stock_quantity ?? 0 }} unid. disponíveis
                </div>
              </div>
              <div class="card flex-fill text-center p-3"
                   style="cursor:pointer;border-width:2px;transition:border-color .15s"
                   :style="form.stock_mode === 'fixed' ? 'border-color:#6366f1;background:#f5f3ff' : 'border-color:#dee2e6'"
                   @click="form.stock_mode = 'fixed'">
                <div style="font-size:20px" class="mb-1">🔢</div>
                <div class="font-weight-bold">Valor Fixo</div>
                <div class="text-muted small">Quantidade definida por mim</div>
              </div>
            </div>
            <div v-if="form.stock_mode === 'fixed'" class="p-3 rounded" style="background:#f5f3ff;border:1px solid #c4b5fd">
              <div class="d-flex align-items-center mb-2" style="gap:12px">
                <label class="small font-weight-bold mb-0">Quantidade:</label>
                <input v-model.number="form.fixed_quantity" type="number" min="0" step="1"
                       class="form-control form-control-sm" style="width:100px" />
              </div>
              <div class="custom-control custom-checkbox">
                <input v-model="form.keep_stock_fixed" type="checkbox"
                       class="custom-control-input" id="ksf_catalog" />
                <label class="custom-control-label small" for="ksf_catalog">
                  Manter fixo — restaurar para {{ form.fixed_quantity }} após cada venda
                </label>
              </div>
            </div>
          </div>

          <!-- Dimensões do pacote (somente leitura) -->
          <div v-if="form.height_cm || form.width_cm || form.length_cm || form.weight_kg"
               class="text-muted small mt-3 pt-3 border-top">
            <i class="fas fa-box-open mr-1"></i>
            <strong>Dimensões do pacote:</strong>
            <span v-if="form.height_cm || form.width_cm || form.length_cm">
              {{ form.height_cm || '?' }}×{{ form.width_cm || '?' }}×{{ form.length_cm || '?' }} cm
            </span>
            <span v-if="form.weight_kg" class="ml-2">· {{ form.weight_kg }} kg</span>
          </div>

          <div v-if="modal.error"   class="alert alert-danger py-2 mt-2">{{ modal.error }}</div>
          <div v-if="modal.success" class="alert alert-success py-2 mt-2">
            <i class="fas fa-check-circle mr-1"></i>{{ modal.success }}
          </div>

        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeModal" :disabled="modal.saving">Cancelar</button>
          <button class="btn btn-success" @click="publishAnuncio" :disabled="modal.saving">
            <i :class="['fas', modal.saving ? 'fa-spinner fa-spin' : 'fa-bullhorn', 'mr-1']"></i>
            {{ modal.saving ? 'Publicando...' : 'Publicar Anúncio' }}
          </button>
        </div>

      </div>
    </div>
  </div>

</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'
import PublishCategoryPicker from '@/components/catalog/PublishCategoryPicker.vue'
import AgruparAnunciosModal from '@/components/catalog/AgruparAnunciosModal.vue'
import { persistCategoryToProduct } from '@/composables/usePublishCategory'

const router = useRouter()

// ── Listagem ──────────────────────────────────────────────────────────────────
const products    = ref([])
const categories  = ref([])
const loading     = ref(true)
const total       = ref(0)
const currentPage = ref(1)

const filters = reactive({
  search:      '',
  category_id: '',
  sort:        'newest',
  page_size:   24,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.page_size)))

const paginationRange = computed(() => {
  const range = []
  const start = Math.max(1, currentPage.value - 2)
  const end   = Math.min(totalPages.value, currentPage.value + 2)
  for (let i = start; i <= end; i++) range.push(i)
  return range
})

// Chamado ao aplicar filtro — reseta para página 1 antes de buscar
function applyFilter() {
  currentPage.value = 1
  loadProducts()
}

async function loadProducts() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: filters.page_size, sort: filters.sort }
    if (filters.search)      params.search      = filters.search
    if (filters.category_id) params.category_id = filters.category_id
    const { data } = await api.get('/catalog', { params })
    products.value = data.items
    total.value    = data.total
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  const { data } = await api.get('/catalog/categories')
  categories.value = data
}

function goToPage(page) {
  if (page >= 1 && page <= totalPages.value) {
    currentPage.value = page
    loadProducts()
  }
}

// ── Contas ────────────────────────────────────────────────────────────────────
const accounts          = ref([])
const selectedAccountId = ref('')

const selectedAccount = computed(() => accounts.value.find(x => x.id === selectedAccountId.value) || null)

const selectedAccountLabel = computed(() => {
  const a = selectedAccount.value
  if (!a) return ''
  return `${a.platform_label} — ${a.description || a.platform_username || a.email}`
})

const isMercadoLivre = computed(() => selectedAccount.value?.platform === 'mercadolivre')

const variationsTooltip = computed(() => {
  if (!selectedAccountId.value) return 'Selecione uma conta para criar anúncio com variações'
  if (!isMercadoLivre.value) return 'Variações disponíveis apenas para Mercado Livre'
  return 'Criar anúncio com variações para esta conta'
})

async function loadAccounts() {
  try {
    const { data } = await api.get('/accounts')
    const label = p => ({ mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[p] || p)
    accounts.value = (Array.isArray(data) ? data : []).map(a => ({ ...a, platform_label: label(a.platform) }))
    if (accounts.value.length === 1) selectedAccountId.value = accounts.value[0].id
  } catch { }
}

// ── Modal ─────────────────────────────────────────────────────────────────────
const modal = reactive({
  show: false,
  product: null,
  productImages: [],
  loadingImages: false,
  saving: false,
  error: '',
  success: '',
  cmigProductId: null,   // preenchido quando publicando CMIG sem vínculo PG
})

const form = reactive({
  title:            '',
  family_name:      '',
  pictures:         [],
  sale_price:       '',
  listing_type:     'gold_special',
  free_shipping:    false,
  stock_mode:       'product',
  fixed_quantity:   1,
  keep_stock_fixed: false,
  model:            '',
  height_cm:        '',
  width_cm:         '',
  length_cm:        '',
  weight_kg:        '',
})

// Suporte a variações da categoria selecionada (carregado ao trocar de categoria)
const catSupport = ref(null)

// ── Categoria + atributos (gerenciado por PublishCategoryPicker) ──────────────
const categorySel = ref({
  pmc_id: null, category_id: '', category_name: '',
  category_path_json: null, isNew: false, attributes: [],
})

watch(() => categorySel.value.category_id, async (catId) => {
  catSupport.value = null
  form.family_name = ''
  if (!catId) return
  try {
    const { data } = await api.get(`/anuncios/categories/${catId}/variation-support`)
    catSupport.value = data
  } catch { /* silencioso — campo não aparece sem suporte confirmado */ }
})

// platform vem como 'mercadolivre' / 'shopee'; o backend espera 'mercado_livre' / 'shopee'
const pickerMarketplace = computed(() => {
  const p = selectedAccount.value?.platform
  if (p === 'mercadolivre') return 'mercado_livre'
  if (p === 'shopee')       return 'shopee'
  return ''
})

const pickerOwnerType = computed(() => modal.cmigProductId ? 'cmig' : 'catalog')
const pickerOwnerId   = computed(() => modal.cmigProductId || modal.product?.id || null)

function resetCategorySel() {
  categorySel.value = {
    pmc_id: null, category_id: '', category_name: '',
    category_path_json: null, isNew: false, attributes: [],
  }
}

// Gestão de fotos
const newPhotoUrl = ref('')
const uploading   = ref(false)
const fileInput   = ref(null)

function isSelected(url) {
  return form.pictures.includes(url)
}

function toggleProductImage(url) {
  const idx = form.pictures.indexOf(url)
  if (idx === -1) {
    form.pictures.push(url)
  } else {
    form.pictures.splice(idx, 1)
  }
}

function removePicture(i) {
  form.pictures.splice(i, 1)
}

function addPhotoByUrl() {
  const url = newPhotoUrl.value.trim()
  if (!url || form.pictures.includes(url)) return
  form.pictures.push(url)
  newPhotoUrl.value = ''
}

async function uploadPhoto(event) {
  const file = event.target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post('/anuncios/upload-image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (data.url && !form.pictures.includes(data.url)) {
      form.pictures.push(data.url)
    }
  } catch (e) {
    modal.error = e.response?.data?.detail || 'Erro ao enviar foto.'
  } finally {
    uploading.value = false
    event.target.value = ''
  }
}

async function openPublishModal(product) {
  modal.product       = product
  modal.productImages = []
  modal.loadingImages = false
  modal.show          = true
  modal.saving        = false
  modal.error         = ''
  modal.success       = ''
  modal.cmigProductId = null

  form.title            = product.title?.slice(0, 60) || ''
  form.pictures         = product.image_url ? [product.image_url] : []
  form.sale_price       = ''
  form.listing_type     = 'gold_special'
  form.free_shipping    = false
  form.stock_mode       = 'product'
  form.fixed_quantity   = 1
  form.keep_stock_fixed = false
  form.model            = product.model     ?? ''
  form.height_cm     = product.height_cm ?? ''
  form.width_cm      = product.width_cm  ?? ''
  form.length_cm     = product.length_cm ?? ''
  form.weight_kg     = product.weight_kg ?? ''
  newPhotoUrl.value  = ''
  resetCategorySel()

  // Busca imagens completas do produto em background
  modal.loadingImages = true
  try {
    const { data } = await api.get(`/catalog/${product.id}`)
    modal.productImages = data.images || []
    // Se o produto tem imagens e ainda não selecionamos nenhuma, pré-seleciona a principal
    if (!form.pictures.length && modal.productImages.length) {
      const primary = modal.productImages.find(i => i.is_primary) || modal.productImages[0]
      form.pictures = [primary.url]
    }
    // Preenche dimensões se o produto tiver e o campo ainda estiver vazio
    if (data.model     && !form.model)     form.model     = data.model
    if (data.height_cm && !form.height_cm) form.height_cm = data.height_cm
    if (data.width_cm  && !form.width_cm)  form.width_cm  = data.width_cm
    if (data.length_cm && !form.length_cm) form.length_cm = data.length_cm
    if (data.weight_kg && !form.weight_kg) form.weight_kg = data.weight_kg
  } catch { }
  finally {
    modal.loadingImages = false
  }
}

function closeModal() {
  if (modal.saving) return
  modal.show = false
}

async function publishAnuncio() {
  modal.error   = ''
  modal.success = ''
  if (!form.title.trim())          return (modal.error = 'Informe o título do anúncio.')
  if (!categorySel.value.category_id) return (modal.error = 'Selecione uma categoria.')
  if (!form.sale_price || Number(form.sale_price) <= 0) return (modal.error = 'Informe um preço válido.')

  modal.saving = true
  try {
    await api.post('/anuncios/publish', {
      account_id:         selectedAccountId.value,
      ...(modal.cmigProductId
        ? { cmig_product_id: modal.cmigProductId }
        : { catalog_product_id: modal.product.id }),
      title_override:     form.title.trim(),
      family_name:        form.family_name.trim() || null,
      category_id:        categorySel.value.category_id,
      sale_price:         Number(form.sale_price),
      pictures:           form.pictures,
      listing_type:       form.listing_type,
      free_shipping:      form.free_shipping,
      stock_mode:         form.stock_mode,
      fixed_quantity:     form.stock_mode === 'fixed' ? Number(form.fixed_quantity) : undefined,
      keep_stock_fixed:   form.stock_mode === 'fixed' ? form.keep_stock_fixed : undefined,
      model:              form.model.trim() || null,
      height_cm:          form.height_cm !== '' ? Number(form.height_cm) : null,
      width_cm:           form.width_cm  !== '' ? Number(form.width_cm)  : null,
      length_cm:          form.length_cm !== '' ? Number(form.length_cm) : null,
      weight_kg:          form.weight_kg !== '' ? Number(form.weight_kg) : null,
      attributes:         categorySel.value.attributes || [],
      mode:               'create',
    })

    // Após publish bem-sucedido, persiste categoria no produto (best-effort).
    await persistCategoryToProduct(
      categorySel.value,
      pickerOwnerType.value,
      pickerOwnerId.value,
      pickerMarketplace.value,
    )

    modal.success = 'Anúncio publicado com sucesso!'
    setTimeout(() => { modal.show = false }, 1800)
  } catch (err) {
    modal.error = err.response?.data?.detail || 'Erro ao publicar anúncio.'
  } finally {
    modal.saving = false
  }
}

// ── Catálogo CMIG ──────────────────────────────────────────────────────────────
const catalogTab = ref('pg')
const cmigs      = ref([])
const cmigProducts = ref([])
const cmigLoading  = ref(false)
const cmigFilter   = ref('all')

// CMIG é derivado automaticamente da conta de marketplace selecionada
const derivedCmigId = computed(() => selectedAccount.value?.cmig_id ?? null)
const activeCmig    = computed(() => cmigs.value.find(c => c.id === derivedCmigId.value) ?? null)

const filteredCmigProducts = computed(() => {
  if (cmigFilter.value === 'kit')    return cmigProducts.value.filter(p => p.is_composite)
  if (cmigFilter.value === 'simple') return cmigProducts.value.filter(p => !p.is_composite)
  return cmigProducts.value
})

async function loadCmigs() {
  try {
    const { data } = await api.get('/cmigs')
    cmigs.value = Array.isArray(data) ? data : []
  } catch {}
}

async function loadCmigProducts() {
  const id = derivedCmigId.value
  if (!id) { cmigProducts.value = []; return }
  cmigLoading.value = true
  try {
    const { data } = await api.get(`/cmigs/${id}/products`)
    cmigProducts.value = Array.isArray(data) ? data : []
  } catch {
    cmigProducts.value = []
  } finally {
    cmigLoading.value = false
  }
}

// Recarrega produtos CMIG ao trocar conta de marketplace ou ativar a aba
watch(derivedCmigId, () => {
  if (catalogTab.value === 'cmig') loadCmigProducts()
  else cmigProducts.value = []
})
watch(catalogTab, (tab) => {
  if (tab === 'cmig') loadCmigProducts()
})

// ── Anúncios já publicados na conta selecionada (ícone no card + modal) ───────
const publishedMap = ref({ pg: {}, cmig: {} })
async function loadPublished() {
  if (!selectedAccountId.value) { publishedMap.value = { pg: {}, cmig: {} }; return }
  try {
    const { data } = await api.get('/catalog/published', { params: { account_id: selectedAccountId.value } })
    publishedMap.value = { pg: data.pg || {}, cmig: data.cmig || {} }
  } catch {
    publishedMap.value = { pg: {}, cmig: {} }
  }
}
watch(selectedAccountId, loadPublished)

function publishedFor(product, type) {
  const map = type === 'cmig' ? publishedMap.value.cmig : publishedMap.value.pg
  return (map && map[product.id]) || null
}
function isSoldOut(product) {
  return Number(product?.stock_quantity || 0) <= 0
}

const publishedModal = reactive({ show: false, title: '', listings: [] })
function openPublishedModal(product, type) {
  publishedModal.title = product.title || product.sku_cmig || product.sku || ''
  publishedModal.listings = publishedFor(product, type) || []
  publishedModal.show = true
}

function getCmigThumb(p) {
  if (p.images && p.images.length) return p.images[0].url
  return null
}

async function openPublishModalFromCmig(cmigProduct) {
  // Publicação a partir do Catálogo CMIG SEMPRE vincula o anúncio ao CMIGProduct,
  // mesmo quando o CMIG tem PG vinculado (cálculo de estoque já é dinâmico e
  // considera o PG vinculado via replay event-sourced em stock_calculator).
  // Antes: se tivesse pg_product_id, virava anúncio PG — confundia o usuário
  // que via badge "PG" mesmo tendo publicado pelo Catálogo CMIG.
  const thumb = getCmigThumb(cmigProduct)
  modal.product = {
    id:             cmigProduct.pg_product_id || null, // só pra modal pegar imagens extras do PG quando vazio
    title:          cmigProduct.title,
    sku:            cmigProduct.sku_cmig,
    cost_price:     cmigProduct.cost_price,
    image_url:      thumb,
    stock_quantity: cmigProduct.stock_quantity,
    model:          cmigProduct.model     || '',
    height_cm:      cmigProduct.height_cm || '',
    width_cm:       cmigProduct.width_cm  || '',
    length_cm:      cmigProduct.length_cm || '',
    weight_kg:      cmigProduct.weight_kg || '',
    brand:          cmigProduct.brand     || '',
  }
  modal.cmigProductId = cmigProduct.id  // <- sempre vincula ao CMIG no anúncio salvo
  modal.productImages = cmigProduct.images || []
  modal.loadingImages = false
  modal.show          = true
  modal.saving        = false
  modal.error         = ''
  modal.success       = ''

  form.title            = cmigProduct.title?.slice(0, 60) || ''
  form.pictures         = (cmigProduct.images || []).map(i => i.url).filter(Boolean)
  if (!form.pictures.length && thumb) form.pictures = [thumb]
  form.sale_price       = ''
  form.listing_type     = 'gold_special'
  form.free_shipping    = false
  form.stock_mode       = 'product'
  form.fixed_quantity   = 1
  form.keep_stock_fixed = false
  form.model            = cmigProduct.model     || ''
  form.height_cm        = cmigProduct.height_cm || ''
  form.width_cm         = cmigProduct.width_cm  || ''
  form.length_cm        = cmigProduct.length_cm || ''
  form.weight_kg        = cmigProduct.weight_kg || ''
  newPhotoUrl.value     = ''
  resetCategorySel()
}

// ── Seleção múltipla para agrupamento ─────────────────────────────────────────
const selectedPgIds = ref(new Set())
const selectedCmigIds = ref(new Set())

const currentSelectionCount = computed(() =>
  catalogTab.value === 'pg' ? selectedPgIds.value.size : selectedCmigIds.value.size
)

function togglePgSelection(id) {
  const s = new Set(selectedPgIds.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  selectedPgIds.value = s
}

function toggleCmigSelection(id) {
  const s = new Set(selectedCmigIds.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  selectedCmigIds.value = s
}

function clearCurrentSelection() {
  if (catalogTab.value === 'pg') selectedPgIds.value = new Set()
  else selectedCmigIds.value = new Set()
}

// Modal "Agrupar Anúncios"
const agruparModal = reactive({ show: false, source: 'pg', products: [] })

function openAgruparModal() {
  if (catalogTab.value === 'pg') {
    agruparModal.source = 'pg'
    // Passa apenas os IDs — o modal hidrata cada produto via API, garantindo que
    // produtos selecionados em páginas diferentes também sejam incluídos.
    agruparModal.products = [...selectedPgIds.value].map(id => ({ id }))
  } else {
    agruparModal.source = 'cmig'
    const cmigId = derivedCmigId.value
    agruparModal.products = [...selectedCmigIds.value].map(id => ({ id, cmig_id: cmigId }))
  }
  agruparModal.show = true
}

function onAgruparClose(result) {
  agruparModal.show = false
  if (result?.success) {
    clearCurrentSelection()
    if (catalogTab.value === 'cmig') loadCmigProducts()
    else loadProducts()
  }
}

// ── Modal de pré-validação de categoria para "Anúncio com Variações" ──────────
const variationsCategoryModal = reactive({
  show: false,
  catSearch: '',
  catResults: [],
  catSearching: false,
  selected: null,           // {id, name, path_from_root}
  support: null,            // /variation-support result
  supportLoading: false,
  error: '',
})

let varCatSearchTimer = null
function openVariationsCategoryPicker() {
  variationsCategoryModal.show = true
  variationsCategoryModal.catSearch = ''
  variationsCategoryModal.catResults = []
  variationsCategoryModal.selected = null
  variationsCategoryModal.support = null
  variationsCategoryModal.error = ''
}
function closeVariationsCategoryPicker() {
  variationsCategoryModal.show = false
}
function onVarCatSearchInput() {
  clearTimeout(varCatSearchTimer)
  varCatSearchTimer = setTimeout(doVarCatSearch, 300)
}
async function doVarCatSearch() {
  const q = variationsCategoryModal.catSearch.trim()
  if (q.length < 2) { variationsCategoryModal.catResults = []; return }
  variationsCategoryModal.catSearching = true
  try {
    const { data } = await api.get('/anuncios/categories/search', { params: { q } })
    variationsCategoryModal.catResults = (data || []).slice(0, 12)
  } catch { variationsCategoryModal.catResults = [] }
  finally { variationsCategoryModal.catSearching = false }
}
async function selectVarCategory(cat) {
  variationsCategoryModal.selected = cat
  variationsCategoryModal.support = null
  variationsCategoryModal.error = ''
  variationsCategoryModal.supportLoading = true
  try {
    const { data } = await api.get(`/anuncios/categories/${cat.id}/variation-support`)
    variationsCategoryModal.support = data
  } catch (e) {
    variationsCategoryModal.error = e.response?.data?.detail || 'Erro ao verificar categoria.'
  } finally {
    variationsCategoryModal.supportLoading = false
  }
}
function proceedToVariationsWizard() {
  const cat = variationsCategoryModal.selected
  const sup = variationsCategoryModal.support
  if (!cat || !sup) return
  closeVariationsCategoryPicker()
  router.push({
    path: '/catalog/anuncios-variacoes/new',
    query: {
      account_id: selectedAccountId.value || undefined,
      category_id: cat.id,
      category_name: cat.name,
    },
  })
}

onMounted(() => {
  loadAccounts()
  loadCategories()
  loadProducts()
  loadCmigs()
})
</script>
