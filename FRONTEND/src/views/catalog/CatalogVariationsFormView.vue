<template>
  <div class="content-header">
    <div class="container-fluid">
      <div class="row mb-2">
        <div class="col-sm-8">
          <h1 class="m-0">
            <i class="fas fa-layer-group mr-2 text-success"></i>
            {{ isEdit ? 'Editar Anúncio com Variações' : 'Novo Anúncio com Variações' }}
          </h1>
        </div>
        <div class="col-sm-4 text-right">
          <RouterLink to="/catalog" class="btn btn-sm btn-outline-secondary">
            <i class="fas fa-arrow-left mr-1"></i>Voltar ao Catálogo
          </RouterLink>
        </div>
      </div>
    </div>
  </div>

  <section class="content">
    <div class="container-fluid">

      <div v-if="loading" class="text-center py-5">
        <i class="fas fa-spinner fa-spin fa-3x text-muted"></i>
      </div>

      <template v-else>
        <!-- Modo: Criar com variações (categoria tradicional) ou Agrupar (User Products) -->
        <div v-if="!isEdit" class="card card-outline card-secondary mb-3">
          <div class="card-body py-2">
            <label class="font-weight-bold d-block mb-2">Como quer publicar?</label>
            <div class="d-flex flex-wrap" style="gap:12px">
              <div
                class="card flex-fill p-3"
                style="cursor:pointer;border-width:2px;min-width:280px"
                :style="mode === 'create' ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                @click="setMode('create')"
              >
                <div class="font-weight-bold"><i class="fas fa-plus-circle mr-1"></i> Criar com variações</div>
                <div class="text-muted small mt-1">
                  Cria <strong>1 anúncio novo</strong> agrupando produtos PG/CMIG como variações
                  (array <code>variations</code>). Para <strong>categorias tradicionais</strong>.
                </div>
              </div>
              <div
                class="card flex-fill p-3"
                style="cursor:pointer;border-width:2px;min-width:280px"
                :style="mode === 'group' ? 'border-color:#28a745;background:#f0fff4' : 'border-color:#dee2e6'"
                @click="setMode('group')"
              >
                <div class="font-weight-bold"><i class="fas fa-object-group mr-1"></i> Agrupar anúncios existentes</div>
                <div class="text-muted small mt-1">
                  Agrupa <strong>N anúncios já publicados</strong> via <code>family_name</code> compartilhada.
                  Para <strong>categorias User Products</strong> (o ML renderiza como pickers na VIP).
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ════════════════════════════════════════════════════════════════ -->
        <!-- MODO AGRUPAR (User Products): tela completamente diferente       -->
        <!-- ════════════════════════════════════════════════════════════════ -->
        <template v-if="mode === 'group'">

          <div class="card card-outline card-success mb-3">
            <div class="card-header py-2"><strong>1. Conta do Mercado Livre</strong></div>
            <div class="card-body">
              <div class="form-group mb-0">
                <select v-model="group.account_id" class="form-control" @change="onGroupAccountChange">
                  <option value="">Selecione uma conta...</option>
                  <option v-for="a in mlAccounts" :key="a.id" :value="a.id">
                    {{ a.platform_label }} — {{ a.description || a.platform_username || a.email }}
                  </option>
                </select>
              </div>
            </div>
          </div>

          <div v-if="group.account_id" class="card card-outline card-success mb-3">
            <div class="card-header py-2 d-flex justify-content-between align-items-center">
              <strong>2. Anúncios para agrupar ({{ group.selected.length }})</strong>
              <button class="btn btn-sm btn-success" @click="openAdsPicker">
                <i class="fas fa-plus mr-1"></i> Adicionar anúncio
              </button>
            </div>
            <div class="card-body p-2">
              <div v-if="!group.selected.length" class="text-center text-muted py-3">
                Selecione ao menos 2 anúncios já publicados que serão variações entre si.
              </div>
              <table v-else class="table table-sm table-bordered mb-0" style="font-size:12px">
                <thead class="thead-light">
                  <tr>
                    <th style="width:60px">Foto</th>
                    <th>Título</th>
                    <th style="width:120px">MLB</th>
                    <th style="width:80px">Estoque</th>
                    <th style="width:100px">Preço</th>
                    <th style="width:140px">Categoria</th>
                    <th style="width:40px"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(l, i) in group.selected" :key="l.id"
                      :class="{ 'table-warning': i > 0 && incompatibilityWarnings[l.id] }">
                    <td>
                      <img v-if="l.thumbnail" :src="l.thumbnail" style="width:40px;height:40px;object-fit:cover;border-radius:3px" />
                    </td>
                    <td>{{ l.title_override }}</td>
                    <td><code>{{ l.platform_item_id }}</code></td>
                    <td class="text-right">{{ l.available_quantity }}</td>
                    <td class="text-right">{{ formatCurrency(l.sale_price) }}</td>
                    <td class="text-truncate" :title="l.category_name">{{ l.category_name || l.category_id }}</td>
                    <td>
                      <button class="btn btn-sm btn-link text-danger p-0" @click="removeFromGroup(i)" title="Remover">
                        <i class="fas fa-times"></i>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="group.selected.length >= 2" class="card card-outline card-success mb-3">
            <div class="card-header py-2"><strong>3. Nome da família (visual na VIP)</strong></div>
            <div class="card-body">
              <div class="form-group mb-1">
                <input v-model="group.family_name" type="text" class="form-control" maxlength="120"
                       :placeholder="suggestedFamilyName" />
                <small class="text-muted">
                  Deixe em branco para usar a sugestão automática:
                  <strong>{{ suggestedFamilyName }}</strong>
                </small>
              </div>
              <div v-if="groupValidationError" class="alert alert-danger py-2 mb-0 mt-2 small">
                <i class="fas fa-exclamation-triangle mr-1"></i>{{ groupValidationError }}
              </div>
              <div v-else class="alert alert-info py-2 mb-0 mt-2 small">
                <i class="fas fa-info-circle mr-1"></i>
                Validação: mesma conta, mesma categoria. O ML agrupa pelas atributos
                <strong>BRAND</strong> e <strong>MODEL</strong> idênticos e diferencia pelos
                atributos divergentes (cor/tamanho/voltagem).
              </div>

              <div v-if="groupError" class="alert alert-danger py-2 mt-2 small">{{ groupError }}</div>
              <div v-if="groupSuccess" class="alert alert-success py-2 mt-2 small">
                <i class="fas fa-check-circle mr-1"></i>{{ groupSuccess }}
              </div>

              <div class="text-right mt-3">
                <button class="btn btn-secondary mr-2" @click="$router.push('/catalog')" :disabled="groupSaving">
                  Cancelar
                </button>
                <button class="btn btn-success" @click="submitGroup"
                        :disabled="groupSaving || !!groupValidationError">
                  <i :class="['fas', groupSaving ? 'fa-spinner fa-spin' : 'fa-object-group', 'mr-1']"></i>
                  {{ groupSaving ? 'Agrupando...' : 'Criar grupo de variações' }}
                </button>
              </div>
            </div>
          </div>

          <!-- Modal: picker de anúncios -->
          <div v-if="adsPickerOpen" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.55);z-index:1080">
            <div class="modal-dialog modal-lg modal-dialog-scrollable">
              <div class="modal-content">
                <div class="modal-header">
                  <h5 class="modal-title"><i class="fas fa-search mr-2"></i>Selecione um anúncio</h5>
                  <button type="button" class="close" @click="adsPickerOpen = false"><span>&times;</span></button>
                </div>
                <div class="modal-body">
                  <input v-model="adsSearch" type="text" class="form-control mb-2"
                         placeholder="Filtrar por título ou MLB..." />
                  <div v-if="loadingAds" class="text-center py-3">
                    <i class="fas fa-spinner fa-spin"></i>
                  </div>
                  <div v-else class="list-group">
                    <button v-for="ad in filteredAds" :key="ad.id" type="button"
                            class="list-group-item list-group-item-action py-2"
                            @click="addToGroup(ad)">
                      <div class="d-flex align-items-center" style="gap:10px">
                        <img v-if="ad.thumbnail" :src="ad.thumbnail"
                             style="width:48px;height:48px;object-fit:cover;border-radius:3px;flex-shrink:0" />
                        <div class="flex-grow-1" style="min-width:0">
                          <div class="text-truncate" style="font-size:13px">{{ ad.title_override }}</div>
                          <div class="text-muted small">
                            <code>{{ ad.platform_item_id }}</code> ·
                            {{ ad.category_name || ad.category_id }} ·
                            Estoque {{ ad.available_quantity }} ·
                            {{ formatCurrency(ad.sale_price) }}
                            <span v-if="ad.is_variation_grouped" class="badge badge-warning ml-1">já em outro grupo</span>
                          </div>
                        </div>
                      </div>
                    </button>
                    <div v-if="!filteredAds.length" class="text-center text-muted py-3">
                      Nenhum anúncio elegível encontrado.
                    </div>
                  </div>
                </div>
                <div class="modal-footer">
                  <button class="btn btn-secondary" @click="adsPickerOpen = false">Fechar</button>
                </div>
              </div>
            </div>
          </div>

        </template>

        <!-- ════════════════════════════════════════════════════════════════ -->
        <!-- MODO CRIAR (categoria tradicional) — fluxo original              -->
        <!-- ════════════════════════════════════════════════════════════════ -->
        <template v-else>

        <!-- Seção 1: Conta + Origem + Tipo -->
        <div class="card card-outline card-primary mb-3">
          <div class="card-header py-2"><strong>1. Conta, Origem e Tipo</strong></div>
          <div class="card-body">

            <div class="form-group">
              <label class="font-weight-bold">Conta de Marketplace <span class="text-danger">*</span></label>
              <select v-model="form.account_id" class="form-control" :disabled="isEdit" @change="onAccountChange">
                <option value="">Selecione...</option>
                <option v-for="a in accounts" :key="a.id" :value="a.id">
                  {{ a.platform_label }} — {{ a.description || a.platform_username || a.email }}
                </option>
              </select>
              <small v-if="!isMercadoLivre && form.account_id" class="text-danger">
                Apenas contas do Mercado Livre suportam variações.
              </small>
            </div>

            <div class="form-group">
              <label class="font-weight-bold d-block mb-1">Origem dos Produtos <span class="text-danger">*</span></label>
              <div class="d-flex" style="gap:8px">
                <button
                  type="button"
                  class="btn d-flex flex-column align-items-center justify-content-center"
                  style="width:80px;height:80px;border-width:2px"
                  :style="form.source === 'pg' ? 'border-color:#007bff;background:#f0f7ff;color:#0056b3' : 'border-color:#dee2e6;background:#fff;color:#495057'"
                  :title="'Produtos PG — catálogo do galpão'"
                  @click="changeSource('pg')"
                >
                  <span style="font-size:22px;line-height:1">📦</span>
                  <small class="font-weight-bold mt-1" style="font-size:11px">PG</small>
                </button>
                <button
                  type="button"
                  class="btn d-flex flex-column align-items-center justify-content-center"
                  style="width:80px;height:80px;border-width:2px"
                  :style="!canUseCmig ? 'opacity:.45;border-color:#dee2e6;background:#fff;color:#6c757d;cursor:not-allowed' :
                          (form.source === 'cmig' ? 'border-color:#ffc107;background:#fffbf0;color:#856404' : 'border-color:#dee2e6;background:#fff;color:#495057')"
                  :title="canUseCmig ? 'Produtos CMIG — catálogo da CMIG vinculada à conta' : 'Conta sem CMIG vinculada'"
                  :disabled="!canUseCmig"
                  @click="canUseCmig && changeSource('cmig')"
                >
                  <span style="font-size:22px;line-height:1">🏷️</span>
                  <small class="font-weight-bold mt-1" style="font-size:11px">CMIG</small>
                </button>
              </div>
              <small v-if="isEdit" class="text-muted">Origem não pode ser alterada no modo edição.</small>
              <small v-else-if="!canUseCmig && form.account_id" class="text-muted d-block">
                A conta selecionada não tem CMIG vinculada — apenas PG disponível.
              </small>
            </div>

            <div class="form-group">
              <label class="font-weight-bold d-block mb-1">Tipo do Anúncio <span class="text-danger">*</span></label>
              <div class="d-flex" style="gap:8px">
                <button
                  type="button"
                  class="btn d-flex flex-column align-items-center justify-content-center"
                  style="width:80px;height:80px;border-width:2px"
                  :style="form.listing_type === 'gold_special' ? 'border-color:#007bff;background:#f0f7ff;color:#0056b3' : 'border-color:#dee2e6;background:#fff;color:#495057'"
                  title="Clássico — comissão menor, exposição padrão"
                  @click="form.listing_type = 'gold_special'"
                >
                  <span style="font-size:22px;line-height:1">⭐</span>
                  <small class="font-weight-bold mt-1" style="font-size:11px">Clássico</small>
                </button>
                <button
                  type="button"
                  class="btn d-flex flex-column align-items-center justify-content-center"
                  style="width:80px;height:80px;border-width:2px"
                  :style="form.listing_type === 'gold_pro' ? 'border-color:#007bff;background:#f0f7ff;color:#0056b3' : 'border-color:#dee2e6;background:#fff;color:#495057'"
                  title="Premium — maior comissão, máxima exposição"
                  @click="form.listing_type = 'gold_pro'"
                >
                  <span style="font-size:22px;line-height:1">🏆</span>
                  <small class="font-weight-bold mt-1" style="font-size:11px">Premium</small>
                </button>
              </div>
            </div>

          </div>
        </div>

        <!-- Seção 2: Título / Modelo / Categoria -->
        <div class="card card-outline card-primary mb-3">
          <div class="card-header py-2"><strong>2. Título, Modelo e Categoria</strong></div>
          <div class="card-body">
            <div class="form-group">
              <label class="font-weight-bold">Título do Anúncio <span class="text-danger">*</span></label>
              <input v-model="form.title" type="text" class="form-control" maxlength="60" />
              <small class="text-muted">{{ form.title.length }}/60 caracteres</small>
            </div>

            <div class="form-group">
              <label class="font-weight-bold">Modelo</label>
              <input v-model="form.model" type="text" class="form-control" placeholder="Ex: Turbo 40" />
            </div>

            <div class="form-group">
              <label class="font-weight-bold">Categoria <span class="text-danger">*</span></label>

              <div v-if="isEdit && form.category_id" class="p-2 rounded border bg-light">
                <div v-if="form.category_path && form.category_path.length"
                     class="d-flex align-items-center flex-wrap" style="gap:4px;font-size:12px">
                  <template v-for="(p, i) in form.category_path" :key="p.id || i">
                    <span :class="i === form.category_path.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">
                      {{ p.name }}
                    </span>
                    <i v-if="i < form.category_path.length - 1" class="fas fa-angle-right text-muted"></i>
                  </template>
                </div>
                <div v-else class="font-weight-bold" style="font-size:13px">
                  {{ form.category_name || form.category_id }}
                </div>
                <code class="text-muted d-block mt-1" style="font-size:11px">ID: {{ form.category_id }}</code>
                <small class="text-muted">Categoria não pode ser alterada no modo edição.</small>
              </div>

              <template v-else>
                <div class="input-group input-group-sm">
                  <input v-model="catSearch" type="text" class="form-control"
                         placeholder="Pesquisar categoria ML..." @input="onCatSearch" />
                  <div class="input-group-append">
                    <span class="input-group-text"><i class="fas fa-search"></i></span>
                  </div>
                </div>
                <div v-if="catSearching" class="text-muted small mt-1">
                  <i class="fas fa-spinner fa-spin mr-1"></i>Buscando...
                </div>
                <div v-if="catResults.length" class="list-group mt-1"
                     style="max-height:280px;overflow-y:auto;position:relative;z-index:10">
                  <button v-for="cat in catResults" :key="cat.id" type="button"
                          class="list-group-item list-group-item-action py-2 px-2"
                          @click="selectCategory(cat)">
                    <div v-if="cat.path_from_root && cat.path_from_root.length"
                         class="d-flex align-items-center flex-wrap" style="gap:3px;font-size:12px">
                      <template v-for="(p, i) in cat.path_from_root" :key="p.id || i">
                        <span :class="i === cat.path_from_root.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">
                          {{ p.name }}
                        </span>
                        <i v-if="i < cat.path_from_root.length - 1" class="fas fa-angle-right text-muted" style="font-size:10px"></i>
                      </template>
                    </div>
                    <div v-else class="font-weight-bold" style="font-size:12px">{{ cat.name }}</div>
                    <code class="text-muted d-block" style="font-size:10px">{{ cat.id }}</code>
                  </button>
                </div>

                <div v-if="form.category_id" class="p-2 rounded border bg-light mt-2">
                  <div class="d-flex align-items-center justify-content-between">
                    <div class="flex-grow-1">
                      <div v-if="form.category_path && form.category_path.length"
                           class="d-flex align-items-center flex-wrap" style="gap:4px;font-size:12px">
                        <template v-for="(p, i) in form.category_path" :key="p.id || i">
                          <span :class="i === form.category_path.length - 1 ? 'font-weight-bold text-dark' : 'text-muted'">
                            {{ p.name }}
                          </span>
                          <i v-if="i < form.category_path.length - 1" class="fas fa-angle-right text-muted"></i>
                        </template>
                      </div>
                      <div v-else class="font-weight-bold" style="font-size:13px">{{ form.category_name }}</div>
                      <code class="text-muted d-block mt-1" style="font-size:11px">ID: {{ form.category_id }}</code>
                    </div>
                    <button type="button" class="btn btn-sm btn-link text-danger" @click="clearCategory" title="Limpar categoria">
                      <i class="fas fa-times"></i>
                    </button>
                  </div>
                </div>
              </template>
            </div>

            <div v-if="catSupportLoading" class="text-muted small">
              <i class="fas fa-spinner fa-spin mr-1"></i>Verificando suporte a variações...
            </div>
            <div v-else-if="form.category_id && catSupport && catSupport.requires_family_name"
                 class="alert alert-danger py-2">
              <i class="fas fa-exclamation-triangle mr-1"></i>
              Esta categoria está sob o <strong>modelo User Products</strong> do Mercado Livre
              (<code>{{ catSupport.catalog_domain }}</code>). Nesse modelo o ML exige o campo
              <code>family_name</code> no item-pai e <strong>não permite variações via API de itens</strong>.
              Use a publicação padrão do Catálogo (1 produto = 1 anúncio) ou publique como
              anúncio de catálogo associado a um <code>catalog_product_id</code>.
            </div>
            <div v-else-if="form.category_id && catSupport && !catSupport.supports_variations"
                 class="alert alert-danger py-2">
              <i class="fas fa-exclamation-triangle mr-1"></i>
              Esta categoria <strong>não aceita variações</strong>. Escolha outra categoria ou
              use o fluxo padrão de publicação do Catálogo.
            </div>
            <div v-else-if="form.category_id && catSupport && catSupport.allows_custom_variations && !catSupport.variation_combination_attrs.length"
                 class="alert alert-warning py-2">
              <i class="fas fa-info-circle mr-1"></i>
              Esta categoria só aceita <strong>variações personalizadas</strong> (sem atributos
              padrão). Você precisará informar o nome do atributo (ex.: "Design", "Estampa")
              ao adicionar cada variação.
            </div>
            <div v-else-if="form.category_id && catSupport" class="alert alert-success py-2">
              <i class="fas fa-check-circle mr-1"></i>
              Categoria aceita variações por:
              <strong>{{ catSupport.variation_combination_attrs.map(a => a.name).join(', ') }}</strong>.
              Máx. variações: {{ catSupport.max_variations_allowed || '100' }} ·
              Máx. fotos/variação: {{ catSupport.max_pictures_per_item_var || 10 }}
            </div>
          </div>
        </div>

        <!-- Seção 3: Variações -->
        <div v-if="canEditVariations" class="card card-outline card-success mb-3">
          <div class="card-header py-2 d-flex justify-content-between align-items-center">
            <strong>3. Variações ({{ form.variations.length }})</strong>
            <button class="btn btn-sm btn-success" @click="addVariation"
                    :disabled="form.variations.length >= maxVariations">
              <i class="fas fa-plus mr-1"></i>Adicionar variação
            </button>
          </div>
          <div class="card-body p-2">
            <div v-if="!form.variations.length" class="text-center text-muted py-4">
              Adicione ao menos uma variação para publicar.
            </div>
            <div class="table-responsive" v-else>
              <table class="table table-sm table-bordered" style="font-size:12px">
                <thead class="thead-light">
                  <tr>
                    <th style="width:30%">Combinação</th>
                    <th>Produto</th>
                    <th style="width:120px">SKU</th>
                    <th style="width:120px">EAN</th>
                    <th style="width:80px">Estoque</th>
                    <th style="width:110px">Preço (R$)</th>
                    <th style="width:90px">Fotos</th>
                    <th style="width:40px"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(v, idx) in form.variations" :key="idx">
                    <td>
                      <div v-for="attr in catSupport.variation_combination_attrs" :key="attr.id" class="mb-1">
                        <div class="small text-muted mb-0">{{ attr.name }}</div>
                        <select
                          v-if="attr.values && attr.values.length"
                          class="form-control form-control-sm"
                          :value="getCombValue(v, attr.id)"
                          @change="setCombValue(v, attr, $event.target.value)"
                        >
                          <option value="">Selecione...</option>
                          <option v-for="val in attr.values" :key="val.id" :value="val.id">{{ val.name }}</option>
                        </select>
                        <input
                          v-else
                          type="text"
                          class="form-control form-control-sm"
                          :value="getCombValueName(v, attr.id)"
                          @input="setCombValueName(v, attr, $event.target.value)"
                          placeholder="(texto livre)"
                        />
                      </div>
                    </td>
                    <td>
                      <div v-if="v._product">
                        <div class="text-truncate" style="font-size:12px;max-width:240px">
                          <i class="fas fa-link text-success mr-1"></i>{{ v._product.title }}
                        </div>
                        <button class="btn btn-link btn-sm p-0" style="font-size:11px" @click="clearProduct(v)">
                          <i class="fas fa-times mr-1"></i>trocar
                        </button>
                      </div>
                      <VariationProductPicker
                        v-else
                        :source="form.source"
                        :account-cmig-id="selectedAccount?.cmig_id"
                        @select="onProductSelected(v, $event)"
                      />
                    </td>
                    <td><input type="text" class="form-control form-control-sm" :value="v._sku" disabled /></td>
                    <td><input type="text" class="form-control form-control-sm" :value="v._ean || ''" disabled /></td>
                    <td><input type="text" class="form-control form-control-sm text-right" :value="v._stock ?? ''" disabled /></td>
                    <td>
                      <input v-model.number="v.price_override" type="number" min="0" step="0.01"
                             class="form-control form-control-sm text-right" />
                    </td>
                    <td>
                      <VariationPicturesEditor
                        v-model="v.picture_urls_override"
                        :product-images="v._product_images || []"
                        :max-pictures="catSupport.max_pictures_per_item_var || 10"
                        :title="`Var #${idx + 1}`"
                      />
                    </td>
                    <td class="text-center">
                      <button class="btn btn-sm btn-link text-danger p-0" @click="removeVariation(idx)" title="Remover">
                        <i class="fas fa-trash"></i>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="priceMismatchWarning" class="alert alert-warning py-2 mb-0 small">
              <i class="fas fa-info-circle mr-1"></i>
              Há preços diferentes entre as variações. Na página do produto (VIP) o ML
              exibirá apenas o <strong>maior preço</strong>; para preços realmente
              distintos por variação seria necessário o modelo "User Products".
            </div>
          </div>
        </div>

        <!-- Seção 4: Frete e Publicação -->
        <div v-if="canEditVariations" class="card card-outline card-primary mb-3">
          <div class="card-header py-2"><strong>4. Frete e Publicação</strong></div>
          <div class="card-body">
            <div class="form-group">
              <label class="font-weight-bold">Pagamento do Frete</label>
              <div class="d-flex" style="gap:12px;max-width:600px">
                <div class="card flex-fill text-center p-3"
                     style="cursor:pointer;border-width:2px"
                     :style="!form.free_shipping ? 'border-color:#007bff;background:#f0f7ff' : 'border-color:#dee2e6'"
                     @click="form.free_shipping = false">
                  <div style="font-size:18px" class="mb-1">🛒</div>
                  <div class="font-weight-bold">Comprador paga</div>
                </div>
                <div class="card flex-fill text-center p-3"
                     style="cursor:pointer;border-width:2px"
                     :style="form.free_shipping ? 'border-color:#28a745;background:#f0fff4' : 'border-color:#dee2e6'"
                     @click="form.free_shipping = true">
                  <div style="font-size:18px" class="mb-1">🚚</div>
                  <div class="font-weight-bold text-success">Vendedor paga</div>
                </div>
              </div>
            </div>

            <div class="form-group">
              <label class="font-weight-bold">Estoque</label>
              <div class="alert alert-info py-2 mb-0">
                <i class="fas fa-cubes mr-1"></i>
                Estoque total = soma dos estoques dos produtos selecionados.
                Atual: <strong>{{ totalStock }} unidades</strong>.
                Variações com estoque ≤ 0 ficarão "Sem estoque" na VIP e voltam sozinhas quando o estoque crescer.
              </div>
            </div>

            <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
            <div v-if="success" class="alert alert-success py-2">
              <i class="fas fa-check-circle mr-1"></i>{{ success }}
            </div>

            <div class="text-right">
              <button class="btn btn-secondary mr-2" @click="$router.push('/catalog')" :disabled="saving">
                Cancelar
              </button>
              <button class="btn btn-success" @click="submit" :disabled="!canSubmit || saving">
                <i :class="['fas', saving ? 'fa-spinner fa-spin' : (isEdit ? 'fa-save' : 'fa-bullhorn'), 'mr-1']"></i>
                {{ saving ? 'Salvando...' : (isEdit ? 'Salvar Alterações' : 'Publicar Anúncio') }}
              </button>
            </div>
          </div>
        </div>

        </template><!-- /MODO CRIAR -->

      </template>
    </div>
  </section>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency } from '@/utils/formatters'
import VariationProductPicker from '@/components/catalog/VariationProductPicker.vue'
import VariationPicturesEditor from '@/components/catalog/VariationPicturesEditor.vue'

const route   = useRoute()
const router  = useRouter()

const listingId = computed(() => route.params.listing_id)
const isEdit    = computed(() => !!listingId.value)

const loading = ref(true)
const saving  = ref(false)
const error   = ref('')
const success = ref('')

const accounts = ref([])
const mlAccounts = computed(() => accounts.value.filter(a => a.platform === 'mercadolivre'))

// Modo: 'create' (criar 1 anúncio com variations array) | 'group' (agrupar N anúncios via family_name)
const mode = ref('create')
function setMode(m) { mode.value = m }

// ── Estado do modo 'group' ──────────────────────────────────────────────────
const group = reactive({
  account_id: '',
  selected: [],         // [ProductListing, ...]
  family_name: '',
})
const accountAds = ref([])           // todos os anúncios da conta selecionada
const loadingAds = ref(false)
const adsPickerOpen = ref(false)
const adsSearch = ref('')
const groupSaving = ref(false)
const groupError = ref('')
const groupSuccess = ref('')

const suggestedFamilyName = computed(() => {
  const titles = group.selected.map(l => (l.title_override || '').trim()).filter(Boolean)
  if (!titles.length) return 'Família'
  let prefix = titles[0]
  for (const t of titles.slice(1)) {
    let i = 0
    while (i < prefix.length && i < t.length && prefix[i].toLowerCase() === t[i].toLowerCase()) i++
    prefix = prefix.slice(0, i)
  }
  prefix = prefix.replace(/[\s\-–—·,\/]+$/g, '')
  return prefix.slice(0, 60) || titles[0].slice(0, 60)
})

const incompatibilityWarnings = computed(() => {
  // Marca listings que divergem do primeiro em categoria (visualização)
  const map = {}
  const first = group.selected[0]
  if (!first) return map
  for (const l of group.selected.slice(1)) {
    if ((l.category_id || '') !== (first.category_id || '')) map[l.id] = true
  }
  return map
})

const groupValidationError = computed(() => {
  if (group.selected.length < 2) return 'Selecione ao menos 2 anúncios para agrupar.'
  const first = group.selected[0]
  for (const l of group.selected.slice(1)) {
    if (l.account_id !== first.account_id)
      return `Anúncio #${l.id} é de outra conta — não pode ser agrupado.`
    if (!l.platform_item_id)
      return `Anúncio #${l.id} não está publicado no Mercado Livre.`
    if ((l.category_id || '') !== (first.category_id || ''))
      return `Anúncio #${l.id} está em categoria diferente do primeiro (${first.category_name || first.category_id}).`
  }
  return ''
})

const filteredAds = computed(() => {
  const selectedIds = new Set(group.selected.map(l => l.id))
  const q = adsSearch.value.trim().toLowerCase()
  return accountAds.value
    .filter(a => !selectedIds.has(a.id))
    .filter(a => !q || (a.title_override || '').toLowerCase().includes(q) || (a.platform_item_id || '').toLowerCase().includes(q))
    .slice(0, 50)
})

async function onGroupAccountChange() {
  group.selected = []
  group.family_name = ''
  accountAds.value = []
  if (!group.account_id) return
  loadingAds.value = true
  try {
    const { data } = await api.get('/anuncios', {
      params: { account_id: group.account_id, status: 'published' },
    })
    accountAds.value = Array.isArray(data) ? data : []
  } finally {
    loadingAds.value = false
  }
}

function openAdsPicker() {
  adsSearch.value = ''
  adsPickerOpen.value = true
}

function addToGroup(ad) {
  if (group.selected.find(l => l.id === ad.id)) return
  group.selected.push(ad)
  adsPickerOpen.value = false
}

function removeFromGroup(idx) {
  group.selected.splice(idx, 1)
}

async function submitGroup() {
  groupError.value = ''
  groupSuccess.value = ''
  if (groupValidationError.value) {
    groupError.value = groupValidationError.value
    return
  }
  groupSaving.value = true
  try {
    const payload = {
      listing_ids: group.selected.map(l => l.id),
      family_name: group.family_name.trim() || suggestedFamilyName.value,
    }
    const { data } = await api.post('/anuncios/groups', payload)
    groupSuccess.value = `Grupo criado: ${data.listings.length} anúncios agrupados como "${data.family_name}".`
    setTimeout(() => router.push('/catalog'), 1800)
  } catch (e) {
    const det = e.response?.data?.detail
    groupError.value = typeof det === 'string' ? det : (det?.message || 'Erro ao criar grupo.')
  } finally {
    groupSaving.value = false
  }
}


const form = reactive({
  account_id: '',
  source: '',                 // 'pg' | 'cmig'
  listing_type: 'gold_special',
  title: '',
  model: '',
  category_id: '',
  category_name: '',
  category_path: [],          // [{id, name}, ...] caminho completo da categoria
  free_shipping: false,
  variations: [],
})

const selectedAccount = computed(() => accounts.value.find(a => a.id === form.account_id) || null)
const isMercadoLivre  = computed(() => selectedAccount.value?.platform === 'mercadolivre')
const canUseCmig      = computed(() => !!selectedAccount.value?.cmig_id)

// Categoria search
const catSearch = ref('')
const catSearching = ref(false)
const catResults = ref([])
let catTimer = null

// Suporte a variações da categoria
const catSupport = ref(null)
const catSupportLoading = ref(false)

const maxVariations = computed(() => catSupport.value?.max_variations_allowed || 100)
const canEditVariations = computed(() =>
  !!form.category_id && catSupport.value?.supports_variations && form.source
)

const totalStock = computed(() =>
  form.variations.reduce((s, v) => s + (Number(v._stock) > 0 ? Number(v._stock) : 0), 0)
)

const priceMismatchWarning = computed(() => {
  const prices = form.variations.map(v => Number(v.price_override)).filter(p => p > 0)
  return new Set(prices).size > 1
})

const canSubmit = computed(() => {
  if (!form.account_id || !form.source || !form.title.trim() || !form.category_id) return false
  if (!form.variations.length) return false
  for (const v of form.variations) {
    if (!v._product) return false
    if (!Number(v.price_override) || Number(v.price_override) <= 0) return false
    if (!hasAllCombValues(v)) return false
  }
  if (hasDuplicateCombinations()) return false
  return true
})

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadAccounts()
  if (isEdit.value) {
    await loadListing()
  } else {
    const qsAccount = Number(route.query.account_id)
    if (qsAccount && accounts.value.some(a => a.id === qsAccount)) {
      form.account_id = qsAccount
    } else if (accounts.value.length === 1) {
      form.account_id = accounts.value[0].id
    }
  }
  loading.value = false
})

async function loadAccounts() {
  const { data } = await api.get('/accounts')
  const label = p => ({ mercadolivre: 'Mercado Livre', shopee: 'Shopee', bling: 'Bling' }[p] || p)
  accounts.value = (Array.isArray(data) ? data : []).map(a => ({ ...a, platform_label: label(a.platform) }))
}

async function loadListing() {
  try {
    const { data } = await api.get(`/anuncios/${listingId.value}`)
    form.account_id    = data.account_id
    form.title         = data.title_override || ''
    form.category_id   = data.category_id || ''
    form.category_name = data.category_name || ''
    form.listing_type  = data.listing_type || 'gold_special'
    form.free_shipping = !!data.free_shipping
    // Variações vêm em variations_json (string)
    let vars = []
    try { vars = JSON.parse(data.variations_json || '[]') } catch { vars = [] }
    if (!vars.length) {
      error.value = 'Este anúncio não tem variações persistidas — não pode ser editado nesta tela.'
      return
    }
    // Determina source pela primeira variação
    form.source = vars[0]?._source || ''
    // Carrega cada variação enriquecida
    for (const v of vars) {
      const variation = makeEmptyVariation()
      variation._ml_variation_id = v.id
      variation.attribute_combinations = (v.attribute_combinations || []).map(c => ({
        id: c.id, name: c.name,
        value_id: c.value_id || null,
        value_name: c.value_name || null,
      }))
      variation.price_override = Number(v.price) || null
      variation.picture_urls_override = Array.isArray(v._pictures_urls) ? [...v._pictures_urls] : []
      const pid = v._catalog_product_id || v._cmig_product_id
      if (pid) {
        await hydrateProductIntoVariation(variation, v._source, pid)
      }
      form.variations.push(variation)
    }
    // Carrega path da categoria pra exibir hierarquia + suporte a variações
    if (form.category_id) {
      await Promise.all([
        fetchCategoryPath(form.category_id),
        loadCategorySupport(form.category_id),
      ])
    }
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao carregar anúncio.'
  }
}

// ── Conta / Source ───────────────────────────────────────────────────────────
function onAccountChange() {
  if (!isMercadoLivre.value) form.source = ''
  // Se ainda não tem source e a conta tem CMIG, deixa o usuário escolher
}

function changeSource(s) {
  if (isEdit.value) return
  if (form.source === s) return
  if (form.variations.length && !confirm('Trocar a origem irá remover as variações já adicionadas. Continuar?')) {
    return
  }
  form.source = s
  form.variations = []
}

// ── Categoria ────────────────────────────────────────────────────────────────
function onCatSearch() {
  clearTimeout(catTimer)
  catTimer = setTimeout(doCatSearch, 300)
}

async function doCatSearch() {
  const q = catSearch.value.trim()
  if (q.length < 2) { catResults.value = []; return }
  catSearching.value = true
  try {
    const { data } = await api.get('/anuncios/categories/search', { params: { q } })
    catResults.value = (data || []).slice(0, 12)
  } catch { catResults.value = [] }
  finally { catSearching.value = false }
}

async function selectCategory(cat) {
  form.category_id   = cat.id
  form.category_name = cat.name
  form.category_path = Array.isArray(cat.path_from_root) && cat.path_from_root.length
    ? cat.path_from_root.map(p => ({ id: p.id, name: p.name }))
    : [{ id: cat.id, name: cat.name }]
  catSearch.value = ''
  catResults.value = []
  await loadCategorySupport(cat.id)
}

function clearCategory() {
  form.category_id = ''
  form.category_name = ''
  form.category_path = []
  catSupport.value = null
}

async function fetchCategoryPath(categoryId) {
  try {
    const { data } = await api.get(`/anuncios/categories/${categoryId}`)
    const path = Array.isArray(data.path_from_root) ? data.path_from_root : []
    form.category_path = path.length
      ? path.map(p => ({ id: p.id, name: p.name }))
      : [{ id: data.id, name: data.name }]
    if (!form.category_name) form.category_name = data.name
  } catch { /* mantém o que tinha */ }
}

async function loadCategorySupport(categoryId) {
  catSupportLoading.value = true
  catSupport.value = null
  try {
    const { data } = await api.get(`/anuncios/categories/${categoryId}/variation-support`)
    catSupport.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao verificar categoria.'
  } finally {
    catSupportLoading.value = false
  }
}

watch(() => form.category_id, (newId, oldId) => {
  // Ao trocar categoria mid-flow (não no modo edição), invalidar combinações
  if (oldId && newId !== oldId && !isEdit.value) {
    form.variations.forEach(v => { v.attribute_combinations = [] })
  }
})

// ── Variações ────────────────────────────────────────────────────────────────
function makeEmptyVariation() {
  return {
    _ml_variation_id: null,
    _product: null,
    _product_images: [],
    _sku: '',
    _ean: '',
    _stock: null,
    catalog_product_id: null,
    cmig_product_id: null,
    attribute_combinations: [],
    price_override: null,
    picture_urls_override: [],
  }
}

function addVariation() {
  form.variations.push(makeEmptyVariation())
}

function removeVariation(idx) {
  form.variations.splice(idx, 1)
}

function clearProduct(v) {
  v._product = null
  v._product_images = []
  v._sku = ''
  v._ean = ''
  v._stock = null
  v.catalog_product_id = null
  v.cmig_product_id = null
  v.price_override = null
  v.picture_urls_override = []
}

function onProductSelected(v, product) {
  v._product = product
  v._product_images = (product.images || (product.image_url ? [{ url: product.image_url }] : []))
                       .map(i => ({ url: i.url || i }))
  v._sku   = product._sku || product.sku || product.sku_cmig || ''
  v._ean   = product.ean || ''
  v._stock = product.stock_quantity ?? 0
  if (form.source === 'pg') {
    v.catalog_product_id = product.id
    v.cmig_product_id    = null
  } else {
    v.cmig_product_id    = product.id
    v.catalog_product_id = null
  }
  // Preço sempre vem do suggested_price (ou cost_price fallback) — usuário pode editar
  const sug = product.suggested_price ?? product._price ?? product.cost_price
  v.price_override = sug ? Number(sug) : null
  // Fotos vêm do produto por padrão; usuário pode editar/adicionar
  v.picture_urls_override = (v._product_images || []).map(i => i.url).filter(Boolean)
}

async function hydrateProductIntoVariation(v, source, pid) {
  try {
    if (source === 'pg') {
      const { data } = await api.get(`/catalog/${pid}`)
      const product = {
        id: data.id, title: data.title, sku: data.sku, ean: data.ean,
        stock_quantity: data.stock_quantity, suggested_price: data.suggested_price,
        cost_price: data.cost_price, images: data.images || [],
        _sku: data.sku, _price: data.suggested_price || data.cost_price,
      }
      v._product = product
      v._product_images = (data.images || []).map(i => ({ url: i.url }))
      v._sku = data.sku
      v._ean = data.ean
      v._stock = data.stock_quantity ?? 0
      v.catalog_product_id = data.id
    } else {
      const cmigId = selectedAccount.value?.cmig_id
      if (!cmigId) return
      const { data } = await api.get(`/cmigs/${cmigId}/products/${pid}`)
      const product = {
        id: data.id, title: data.title, sku_cmig: data.sku_cmig, ean: data.ean,
        stock_quantity: data.stock_quantity, suggested_price: data.suggested_price,
        cost_price: data.cost_price, images: data.images || [],
        _sku: data.sku_cmig, _price: data.suggested_price || data.cost_price,
      }
      v._product = product
      v._product_images = (data.images || []).map(i => ({ url: i.url }))
      v._sku = data.sku_cmig
      v._ean = data.ean
      v._stock = data.stock_quantity ?? 0
      v.cmig_product_id = data.id
    }
  } catch { /* manteve o que tinha */ }
}

// Combinação
function getCombValue(v, attrId) {
  const c = (v.attribute_combinations || []).find(x => x.id === attrId)
  return c?.value_id || ''
}
function getCombValueName(v, attrId) {
  const c = (v.attribute_combinations || []).find(x => x.id === attrId)
  return c?.value_name || ''
}
function setCombValue(v, attr, valueId) {
  const idx = v.attribute_combinations.findIndex(x => x.id === attr.id)
  const valObj = (attr.values || []).find(x => x.id === valueId) || null
  const entry = { id: attr.id, name: attr.name, value_id: valueId || null, value_name: valObj?.name || null }
  if (idx === -1) v.attribute_combinations.push(entry)
  else            v.attribute_combinations[idx] = entry
}
function setCombValueName(v, attr, name) {
  const idx = v.attribute_combinations.findIndex(x => x.id === attr.id)
  const entry = { id: attr.id, name: attr.name, value_id: null, value_name: name || null }
  if (idx === -1) v.attribute_combinations.push(entry)
  else            v.attribute_combinations[idx] = entry
}
function hasAllCombValues(v) {
  if (!catSupport.value?.variation_combination_attrs?.length) return true
  for (const a of catSupport.value.variation_combination_attrs) {
    const c = (v.attribute_combinations || []).find(x => x.id === a.id)
    if (!c || (!c.value_id && !c.value_name)) return false
  }
  return true
}
function hasDuplicateCombinations() {
  const seen = new Set()
  for (const v of form.variations) {
    const key = (v.attribute_combinations || [])
      .slice().sort((a, b) => a.id.localeCompare(b.id))
      .map(c => `${c.id}=${c.value_id || c.value_name || ''}`).join('|')
    if (seen.has(key)) return true
    seen.add(key)
  }
  return false
}

// ── Submit ───────────────────────────────────────────────────────────────────
async function submit() {
  error.value = ''
  success.value = ''
  if (!canSubmit.value) {
    error.value = 'Preencha todas as variações (combinação, produto, preço) antes de publicar.'
    return
  }
  if (hasDuplicateCombinations()) {
    error.value = 'Há combinações de variações repetidas.'
    return
  }

  const payload = {
    account_id: form.account_id,
    source: form.source,
    title: form.title.trim(),
    category_id: form.category_id,
    listing_type: form.listing_type,
    model: form.model.trim() || null,
    free_shipping: form.free_shipping,
    pictures: [],
    attributes: [],
    variations: form.variations.map(v => ({
      catalog_product_id: form.source === 'pg' ? v.catalog_product_id : null,
      cmig_product_id:    form.source === 'cmig' ? v.cmig_product_id  : null,
      attribute_combinations: v.attribute_combinations.map(c => {
        const obj = { id: c.id }
        if (c.value_id)   obj.value_id = c.value_id
        if (c.value_name) obj.value_name = c.value_name
        return obj
      }),
      price_override: Number(v.price_override),
      picture_urls_override: v.picture_urls_override,
      ...(isEdit.value && v._ml_variation_id ? { _ml_variation_id: v._ml_variation_id } : {}),
    })),
  }

  saving.value = true
  try {
    if (isEdit.value) {
      await api.put(`/anuncios/${listingId.value}/variations`, payload)
      success.value = 'Anúncio atualizado com sucesso!'
    } else {
      await api.post('/anuncios/publish-with-variations', payload)
      success.value = 'Anúncio publicado com sucesso!'
    }
    setTimeout(() => router.push('/catalog'), 1500)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar anúncio.'
  } finally {
    saving.value = false
  }
}
</script>
