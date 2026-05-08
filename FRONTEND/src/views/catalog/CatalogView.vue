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

      <!-- Toggle PG / CMIG -->
      <div class="mb-3">
        <div class="btn-group">
          <button class="btn" :class="catalogTab === 'pg' ? 'btn-primary' : 'btn-outline-primary'" @click="catalogTab = 'pg'">
            <i class="fas fa-warehouse mr-1"></i> Catálogo PG
          </button>
          <button class="btn" :class="catalogTab === 'cmig' ? 'btn-primary' : 'btn-outline-primary'" @click="catalogTab = 'cmig'">
            <i class="fas fa-id-card mr-1"></i> Catálogo CMIG
          </button>
        </div>
      </div>

      <template v-if="catalogTab === 'pg'">

      <!-- Filtros -->
      <div class="card mb-3">
        <div class="card-body py-2">
          <div class="row align-items-center">
            <div class="col-md-4">
              <div class="input-group input-group-sm">
                <input v-model="filters.search" type="text" class="form-control" placeholder="Buscar produto..." @keyup.enter="loadProducts" />
                <div class="input-group-append">
                  <button class="btn btn-primary" @click="loadProducts"><i class="fas fa-search"></i></button>
                </div>
              </div>
            </div>
            <div class="col-md-3">
              <select v-model="filters.category_id" class="form-control form-control-sm" @change="loadProducts">
                <option value="">Todas as categorias</option>
                <option v-for="cat in categories" :key="cat.id" :value="cat.id">{{ cat.name }}</option>
              </select>
            </div>
            <div class="col-md-3">
              <select v-model="filters.sort" class="form-control form-control-sm" @change="loadProducts">
                <option value="newest">Mais recentes</option>
                <option value="cheapest">Menor preço</option>
                <option value="expensive">Maior preço</option>
              </select>
            </div>
            <div class="col-md-2">
              <select v-model="filters.page_size" class="form-control form-control-sm" @change="loadProducts">
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
            <div class="card h-100 shadow-sm">
              <RouterLink :to="`/catalog/${product.id}`">
                <div style="height:130px;background:#f8f9fa;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px 4px 0 0">
                  <img
                    :src="product.image_url || 'https://via.placeholder.com/300x200?text=Sem+Foto'"
                    style="max-height:100%;max-width:100%;object-fit:contain"
                    :alt="product.title"
                  />
                </div>
              </RouterLink>
              <div class="card-body p-2">
                <p class="text-muted mb-0" style="font-size:10px">({{ product.sku }})</p>
                <p class="card-title mb-1 font-weight-bold" style="font-size:12px;line-height:1.3">
                  {{ product.title.slice(0, 50) }}{{ product.title.length > 50 ? '...' : '' }}
                </p>
                <p class="text-success font-weight-bold mb-0" style="font-size:13px">{{ formatCurrency(product.cost_price) }}</p>
                <p class="text-muted mb-0" style="font-size:11px">Estoque: {{ product.stock_quantity }}</p>
              </div>
              <div class="card-footer p-1">
                <button
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
                <div class="card h-100 shadow-sm">
                  <div style="height:130px;background:#f8f9fa;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px 4px 0 0">
                    <img
                      :src="getCmigThumb(product) || 'https://via.placeholder.com/300x200?text=Sem+Foto'"
                      style="max-height:100%;max-width:100%;object-fit:contain"
                      :alt="product.title"
                    />
                  </div>
                  <div class="card-body p-2">
                    <p class="text-muted mb-0" style="font-size:10px">
                      <span v-if="product.is_composite" class="badge badge-warning mr-1" style="font-size:9px">KIT</span>
                      {{ product.sku_cmig }}
                    </p>
                    <p class="card-title mb-1 font-weight-bold" style="font-size:12px;line-height:1.3">
                      {{ product.title.slice(0, 50) }}{{ product.title.length > 50 ? '...' : '' }}
                    </p>
                    <p class="text-success font-weight-bold mb-0" style="font-size:13px">{{ formatCurrency(product.cost_price) }}</p>
                    <p class="text-muted mb-0" style="font-size:11px">Estoque: {{ product.stock_quantity }}</p>
                  </div>
                  <div class="card-footer p-1">
                    <button
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

          <!-- Modelo -->
          <div class="form-group">
            <label class="font-weight-bold">Modelo</label>
            <input v-model="form.model" type="text" class="form-control"
                   placeholder="Ex: Galaxy S24, RTX 4060, 12V 7Ah..." />
            <small class="text-muted">Obrigatório em algumas categorias do Mercado Livre.</small>
          </div>

          <!-- Categoria -->
          <div class="form-group">
            <label class="font-weight-bold">Categoria <span class="text-danger">*</span></label>
            <div v-if="form.category_id">
              <div class="d-flex align-items-center flex-wrap" style="gap:8px">
                <span class="badge badge-info p-2" style="font-size:13px">
                  <i class="fas fa-layer-group mr-1"></i>{{ form.category_name }}
                </span>
                <button class="btn btn-sm btn-outline-secondary" @click="clearCategory">
                  <i class="fas fa-times"></i> Trocar
                </button>
                <span v-if="attrsModal.loading" class="text-muted small">
                  <i class="fas fa-spinner fa-spin mr-1"></i>Carregando características...
                </span>
                <button v-else-if="attrsModal.attrs.length" type="button"
                        class="btn btn-sm btn-outline-primary" @click="attrsModal.show = true">
                  <i class="fas fa-list-ul mr-1"></i>Características
                  <span v-if="filledAttrsCount" class="badge badge-primary ml-1">{{ filledAttrsCount }}</span>
                  <span v-if="requiredUnfilledCount" class="badge badge-danger ml-1">{{ requiredUnfilledCount }} obrigatórios</span>
                </button>
              </div>
            </div>
            <div v-else>
              <div class="input-group">
                <input v-model="catSearch" type="text" class="form-control"
                       placeholder="Pesquisar categoria no Mercado Livre..." @input="debouncedCatSearch" />
                <div class="input-group-append">
                  <span class="input-group-text"><i class="fas fa-search"></i></span>
                </div>
              </div>
              <div v-if="catSearching" class="text-muted small mt-1">
                <i class="fas fa-spinner fa-spin mr-1"></i>Buscando...
              </div>
              <div v-if="catResults.length" class="list-group mt-1"
                   style="max-height:200px;overflow-y:auto;position:relative;z-index:10">
                <button v-for="cat in catResults" :key="cat.id" type="button"
                        class="list-group-item list-group-item-action py-1 px-2" style="font-size:13px"
                        @click="selectCategory(cat)">
                  <strong>{{ cat.name }}</strong>
                  <span v-if="cat.path_from_root?.length" class="text-muted ml-2">
                    {{ cat.path_from_root.map(p => p.name).join(' › ') }}
                  </span>
                </button>
              </div>
            </div>
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

  <!-- ── Modal: Características da Categoria ── -->
  <div v-if="attrsModal.show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,0.45);z-index:1060">
    <div class="modal-dialog modal-lg modal-dialog-scrollable">
      <div class="modal-content">

        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-list-ul mr-2"></i>Características da Categoria</h5>
          <button type="button" class="close" @click="attrsModal.show = false"><span>&times;</span></button>
        </div>

        <div class="modal-body">

          <!-- Obrigatórios -->
          <div v-if="requiredAttrs.length" class="mb-4">
            <h6 class="font-weight-bold text-danger mb-2">
              <i class="fas fa-asterisk mr-1" style="font-size:10px"></i>Obrigatórios
            </h6>
            <div class="row">
              <div v-for="attr in requiredAttrs" :key="attr.id" class="col-md-6 form-group mb-2">
                <label class="font-weight-bold small">{{ attr.name }} <span class="text-danger">*</span></label>
                <select v-if="attr.values && attr.values.length"
                        v-model="attrValues[attr.id]"
                        class="form-control form-control-sm"
                        :class="{ 'border-danger': !attrValues[attr.id] }">
                  <option value="">Selecione...</option>
                  <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                </select>
                <input v-else v-model="attrValues[attr.id]" type="text" class="form-control form-control-sm"
                       :class="{ 'border-danger': !attrValues[attr.id] }"
                       :placeholder="attr.allowed_units?.length ? `Valor (${attr.allowed_units.join(', ')})` : 'Digite...'" />
              </div>
            </div>
          </div>

          <!-- Recomendados -->
          <div v-if="recommendedAttrs.length" class="mb-4">
            <h6 class="font-weight-bold text-primary mb-2">
              <i class="fas fa-star mr-1" style="font-size:10px"></i>Recomendados
            </h6>
            <div class="row">
              <div v-for="attr in recommendedAttrs" :key="attr.id" class="col-md-6 form-group mb-2">
                <label class="small font-weight-bold">{{ attr.name }}</label>
                <select v-if="attr.values && attr.values.length"
                        v-model="attrValues[attr.id]"
                        class="form-control form-control-sm">
                  <option value="">Selecione...</option>
                  <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                </select>
                <input v-else v-model="attrValues[attr.id]" type="text" class="form-control form-control-sm"
                       :placeholder="attr.allowed_units?.length ? `Valor (${attr.allowed_units.join(', ')})` : 'Digite...'" />
              </div>
            </div>
          </div>

          <!-- Secundários (colapsável) -->
          <div v-if="optionalAttrs.length">
            <button type="button" class="btn btn-sm btn-outline-secondary w-100 text-left mb-2"
                    @click="secondaryExpanded = !secondaryExpanded">
              <i :class="['fas', secondaryExpanded ? 'fa-chevron-down' : 'fa-chevron-right', 'mr-1']"></i>
              Características Secundárias ({{ optionalAttrs.length }})
              <span v-if="filledOptionalCount" class="badge badge-secondary ml-2">{{ filledOptionalCount }} preenchidos</span>
            </button>
            <div v-if="secondaryExpanded" class="row">
              <div v-for="attr in optionalAttrs" :key="attr.id" class="col-md-6 form-group mb-2">
                <label class="small">{{ attr.name }}</label>
                <select v-if="attr.values && attr.values.length"
                        v-model="attrValues[attr.id]"
                        class="form-control form-control-sm">
                  <option value="">Selecione...</option>
                  <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                </select>
                <input v-else v-model="attrValues[attr.id]" type="text" class="form-control form-control-sm"
                       :placeholder="attr.allowed_units?.length ? `Valor (${attr.allowed_units.join(', ')})` : 'Digite...'" />
              </div>
            </div>
          </div>

        </div>

        <div class="modal-footer justify-content-between">
          <span class="text-muted small">
            {{ filledAttrsCount }} preenchido(s)
            <span v-if="requiredUnfilledCount" class="text-danger ml-2">
              · {{ requiredUnfilledCount }} obrigatório(s) pendente(s)
            </span>
          </span>
          <button class="btn btn-primary" @click="attrsModal.show = false">
            <i class="fas fa-check mr-1"></i>Confirmar
          </button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'

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
  category_id:      '',
  category_name:    '',
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

// Busca de categoria
const catSearch    = ref('')
const catResults   = ref([])
const catSearching = ref(false)
let catDebounce    = null

function debouncedCatSearch() {
  clearTimeout(catDebounce)
  catDebounce = setTimeout(searchCategories, 400)
}

async function searchCategories() {
  const q = catSearch.value.trim()
  if (!q) { catResults.value = []; return }
  catSearching.value = true
  try {
    const { data } = await api.get('/anuncios/categories/search', { params: { q } })
    catResults.value = Array.isArray(data) ? data : []
  } catch {
    catResults.value = []
  } finally {
    catSearching.value = false
  }
}

function selectCategory(cat) {
  form.category_id   = cat.id
  form.category_name = cat.name
  catResults.value   = []
  catSearch.value    = ''
  loadCategoryAttrs(cat.id)
}

function clearCategory() {
  form.category_id   = ''
  form.category_name = ''
  attrsModal.attrs   = []
  Object.keys(attrValues).forEach(k => delete attrValues[k])
}

// ── Características da categoria ──────────────────────────────────────────────
const attrsModal        = reactive({ show: false, loading: false, attrs: [] })
const attrValues        = reactive({})
const secondaryExpanded = ref(false)

const requiredAttrs    = computed(() => attrsModal.attrs.filter(a => a.is_required))
const recommendedAttrs = computed(() => attrsModal.attrs.filter(a => a.is_recommended))
const optionalAttrs    = computed(() => attrsModal.attrs.filter(a => a.is_optional))

const filledAttrsCount = computed(() =>
  Object.values(attrValues).filter(v => v !== '' && v != null).length
)

const filledOptionalCount = computed(() =>
  optionalAttrs.value.filter(a => attrValues[a.id]).length
)

const requiredUnfilledCount = computed(() =>
  requiredAttrs.value.filter(a => !attrValues[a.id]).length
)

async function loadCategoryAttrs(categoryId) {
  attrsModal.loading  = true
  attrsModal.attrs    = []
  secondaryExpanded.value = false
  Object.keys(attrValues).forEach(k => delete attrValues[k])
  try {
    const { data } = await api.get(`/anuncios/categories/${categoryId}/attributes`)
    attrsModal.attrs = Array.isArray(data) ? data : []
    // Pré-preenche BRAND e MODEL com dados do produto
    attrsModal.attrs.forEach(attr => {
      if (attr.id === 'BRAND' && modal.product?.brand) {
        attrValues[attr.id] = modal.product.brand
      } else if (attr.id === 'MODEL' && form.model) {
        attrValues[attr.id] = form.model
      }
    })
  } catch {
    attrsModal.attrs = []
  } finally {
    attrsModal.loading = false
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
  form.category_id      = ''
  form.category_name    = ''
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
  catSearch.value    = ''
  catResults.value   = []
  newPhotoUrl.value  = ''
  attrsModal.attrs        = []
  attrsModal.show         = false
  secondaryExpanded.value = false
  Object.keys(attrValues).forEach(k => delete attrValues[k])

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
  if (!form.title.trim())      return (modal.error = 'Informe o título do anúncio.')
  if (!form.category_id)       return (modal.error = 'Selecione uma categoria.')
  if (!form.sale_price || Number(form.sale_price) <= 0) return (modal.error = 'Informe um preço válido.')

  modal.saving = true
  try {
    // Monta array de atributos extras preenchidos pelo usuário
    const extraAttributes = Object.entries(attrValues)
      .filter(([, v]) => v !== '' && v != null)
      .map(([id, value_name]) => ({ id, value_name: String(value_name) }))

    await api.post('/anuncios/publish', {
      account_id:         selectedAccountId.value,
      ...(modal.cmigProductId
        ? { cmig_product_id: modal.cmigProductId }
        : { catalog_product_id: modal.product.id }),
      title_override:     form.title.trim(),
      category_id:        form.category_id,
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
      attributes:         extraAttributes,
      mode:               'create',
    })
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

function getCmigThumb(p) {
  if (p.images && p.images.length) return p.images[0].url
  return null
}

async function openPublishModalFromCmig(cmigProduct) {
  if (cmigProduct.pg_product_id) {
    // Tem vínculo PG → publica via produto PG (estoque real no PG)
    await openPublishModal({
      id:             cmigProduct.pg_product_id,
      title:          cmigProduct.title,
      sku:            cmigProduct.sku_cmig,
      cost_price:     cmigProduct.cost_price,
      image_url:      getCmigThumb(cmigProduct),
      stock_quantity: cmigProduct.stock_quantity,
      model:          cmigProduct.model     || '',
      height_cm:      cmigProduct.height_cm || '',
      width_cm:       cmigProduct.width_cm  || '',
      length_cm:      cmigProduct.length_cm || '',
      weight_kg:      cmigProduct.weight_kg || '',
      brand:          cmigProduct.brand     || '',
    })
    // openPublishModal já seta cmigProductId = null e busca imagens do PG
  } else {
    // Sem vínculo PG → publica diretamente pelo produto CMIG (estoque real na CMIG)
    const thumb = getCmigThumb(cmigProduct)
    modal.product = {
      id:             null,
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
    }
    modal.cmigProductId = cmigProduct.id
    modal.productImages = cmigProduct.images || []
    modal.loadingImages = false
    modal.show          = true
    modal.saving        = false
    modal.error         = ''
    modal.success       = ''

    form.title            = cmigProduct.title?.slice(0, 60) || ''
    form.category_id      = ''
    form.category_name    = ''
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
    catSearch.value       = ''
    catResults.value      = []
    newPhotoUrl.value     = ''
    attrsModal.attrs      = []
    attrsModal.show       = false
    secondaryExpanded.value = false
    Object.keys(attrValues).forEach(k => delete attrValues[k])
  }
}

onMounted(() => {
  loadAccounts()
  loadCategories()
  loadProducts()
  loadCmigs()
})
</script>
