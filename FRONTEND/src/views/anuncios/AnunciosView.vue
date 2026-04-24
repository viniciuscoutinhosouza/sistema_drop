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
                <button class="btn btn-sm btn-secondary" @click="importAnuncios" :disabled="!selectedAccountId || importing">
                  <i :class="['fas', importing ? 'fa-spinner fa-spin' : 'fa-download', 'mr-1']"></i>Importar
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Tabela -->
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
            <table v-else class="table table-hover table-sm mb-0">
              <thead class="thead-light">
                <tr>
                  <th style="width:32px"></th>
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
                  <td class="text-center">
                    <img v-if="a.thumbnail" :src="a.thumbnail" style="width:28px;height:28px;object-fit:cover;border-radius:3px" />
                    <i v-else class="fas fa-image text-muted"></i>
                  </td>
                  <td class="text-monospace small">{{ a.platform_item_id || '—' }}</td>
                  <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="a.title_override">
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
                    <div class="btn-group">
                      <button class="btn btn-sm btn-outline-secondary" title="Editar" @click="openWizard(a)">
                        <i class="fas fa-edit"></i>
                      </button>
                      <button class="btn btn-sm btn-outline-primary" title="Vincular produto" @click="openLinkModal(a)">
                        <i class="fas fa-link"></i>
                      </button>
                      <button v-if="!a.is_linked" class="btn btn-sm btn-outline-dark" title="Criar Produto CMIG" @click="openCreateCmigModal(a)">
                        <i class="fas fa-plus"></i>
                      </button>
                      <button v-if="a.is_linked" class="btn btn-sm btn-outline-danger" title="Remover vínculo" @click="unlinkAnuncio(a)">
                        <i class="fas fa-unlink"></i>
                      </button>
                      <button v-if="a.status === 'active' || a.status === 'published'" class="btn btn-sm btn-outline-warning" title="Pausar" @click="pauseAnuncio(a)">
                        <i class="fas fa-pause"></i>
                      </button>
                      <button v-if="a.status === 'paused' || a.status === 'closed'" class="btn btn-sm btn-outline-success" title="Reativar" @click="reactivateAnuncio(a)">
                        <i class="fas fa-play"></i>
                      </button>
                      <button v-if="a.platform_item_id && a.is_linked" class="btn btn-sm btn-outline-info" title="Sincronizar ML" @click="syncToMl(a)">
                        <i class="fas fa-sync-alt"></i>
                      </button>
                      <a v-if="a.permalink || (a.platform_item_id && selectedAccountPlatform === 'mercadolivre')"
                         :href="a.permalink || `https://www.mercadolivre.com.br/p/${a.platform_item_id}`"
                         target="_blank" class="btn btn-sm btn-outline-info" title="Ver no ML">
                        <i class="fas fa-external-link-alt"></i>
                      </a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
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

            <div class="p-3">
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
                    <input v-model="wf.title_override" class="form-control" maxlength="60" required />
                    <small :class="wf.title_override.length > 55 ? 'text-danger' : 'text-muted'">
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
                    <select v-model="wf.listing_type" class="form-control">
                      <option value="gold_special">Gold Special</option>
                      <option value="gold_pro">Gold Pro</option>
                      <option value="gold_premium">Gold Premium</option>
                      <option value="silver">Silver</option>
                      <option value="bronze">Bronze</option>
                      <option value="free">Grátis</option>
                    </select>
                  </div>
                  <div class="col-md-3 form-group">
                    <label>Quantidade Disponível</label>
                    <input v-model.number="wf.available_quantity" type="number" min="1" class="form-control" />
                  </div>
                  <div class="col-md-3 form-group">
                    <label>Condição</label>
                    <select v-model="wf.item_condition" class="form-control">
                      <option value="new">Novo</option>
                      <option value="used">Usado</option>
                      <option value="not_specified">Não especificado</option>
                    </select>
                  </div>
                  <div class="col-md-3 form-group">
                    <label>ID no Marketplace</label>
                    <input v-model="wf.platform_item_id" class="form-control" placeholder="MLB12345678 (para vincular)" />
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
                <div class="row align-items-end mb-2">
                  <div class="col-md-8 form-group mb-0">
                    <label>Buscar Categoria ML</label>
                    <div class="input-group">
                      <input v-model="categorySearch" class="form-control" placeholder="Ex: Tênis Masculino, Celular, Notebook..." @input="debouncedCategorySearch" />
                      <div class="input-group-append">
                        <button class="btn btn-outline-secondary" @click="searchCategories" :disabled="catLoading">
                          <i :class="['fas', catLoading ? 'fa-spinner fa-spin' : 'fa-search']"></i>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div class="col-md-4">
                    <div v-if="wf.category_id" class="alert alert-success py-1 small mb-0">
                      <i class="fas fa-check mr-1"></i>{{ wf.category_name }} <code class="small">{{ wf.category_id }}</code>
                    </div>
                  </div>
                </div>

                <div v-if="categoryResults.length > 0" class="list-group mb-3" style="max-height:160px;overflow-y:auto">
                  <a v-for="c in categoryResults" :key="c.id"
                    :class="['list-group-item list-group-item-action py-1', wf.category_id === c.id ? 'active' : '']"
                    href="#" @click.prevent="selectCategory(c)">
                    <strong>{{ c.name }}</strong>
                    <span class="text-muted small ml-2">{{ c.id }}</span>
                    <span v-if="c.total_items_in_this_category" class="badge badge-light ml-1">{{ c.total_items_in_this_category.toLocaleString() }} anúncios</span>
                  </a>
                </div>

                <div v-if="wf.category_id">
                  <hr class="my-2" />
                  <div v-if="attrLoading" class="text-center py-2"><i class="fas fa-spinner fa-spin text-muted"></i> Carregando atributos...</div>
                  <div v-else-if="categoryAttributes.length === 0" class="text-muted small">Nenhum atributo obrigatório/recomendado para esta categoria.</div>
                  <template v-else>
                    <h6 class="text-muted small text-uppercase mb-2">Atributos da Categoria</h6>
                    <div class="row">
                      <div v-for="attr in categoryAttributes" :key="attr.id" class="col-md-4 form-group">
                        <label class="small">
                          {{ attr.name }}
                          <span v-if="attr.is_required" class="text-danger">*</span>
                          <span v-else class="text-muted">(recomendado)</span>
                        </label>
                        <select v-if="attr.values && attr.values.length > 0" v-model="attrValues[attr.id]" class="form-control form-control-sm">
                          <option value="">— Selecione —</option>
                          <option v-for="v in attr.values" :key="v.id" :value="v.name">{{ v.name }}</option>
                        </select>
                        <input v-else v-model="attrValues[attr.id]" class="form-control form-control-sm" :placeholder="attr.name" />
                      </div>
                    </div>
                  </template>
                </div>
              </div>

              <!-- ABA 4 — Fotos -->
              <div v-if="wizardStep === 4">
                <p class="text-muted small mb-2">Selecione até 12 fotos. A primeira será a foto principal.</p>

                <div v-if="productImages.length > 0">
                  <h6 class="text-muted small text-uppercase mb-2">Fotos do produto vinculado</h6>
                  <div class="d-flex flex-wrap mb-3">
                    <div v-for="(img, i) in productImages" :key="i" class="mr-2 mb-2 position-relative" style="cursor:pointer" @click="toggleImage(img)">
                      <img :src="img" :style="`width:80px;height:80px;object-fit:cover;border-radius:4px;border:3px solid ${isImageSelected(img) ? '#007bff' : '#dee2e6'}`" />
                      <span v-if="isImageSelected(img)" class="badge badge-primary position-absolute" style="top:-6px;right:-6px;font-size:10px">{{ wf.pictures.indexOf(img)+1 }}</span>
                    </div>
                  </div>
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
                    <div v-for="(img, i) in wf.pictures" :key="i" class="mr-2 mb-2 position-relative">
                      <img :src="img" style="width:70px;height:70px;object-fit:cover;border-radius:4px;border:2px solid #007bff" />
                      <span class="badge badge-primary position-absolute" style="top:-6px;left:-6px;font-size:10px">{{ i+1 }}</span>
                      <button class="btn btn-danger btn-xs position-absolute" style="top:-6px;right:-6px;padding:1px 5px;font-size:10px;line-height:1.2" @click="removeImage(i)">×</button>
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
                      <div class="custom-control custom-switch">
                        <input v-model="wf.free_shipping" type="checkbox" class="custom-control-input" id="wf_free_shipping" />
                        <label class="custom-control-label" for="wf_free_shipping">Frete Grátis</label>
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
            <div>
              <button class="btn btn-secondary mr-2" @click="wizard.show = false">Cancelar</button>
              <button class="btn btn-primary" @click="saveWizard" :disabled="wizard.saving">
                <i v-if="wizard.saving" class="fas fa-spinner fa-spin mr-1"></i>
                {{ wizard.saving ? 'Salvando...' : (wizard.isEdit ? 'Salvar Alterações' : (wf.mode === 'create' ? 'Publicar no Marketplace' : 'Vincular Anúncio')) }}
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

  </div>
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

// ══════════════════════════════════════════════════
// WIZARD
// ══════════════════════════════════════════════════

const wizardTabs = ['Produto', 'Anúncio', 'Categoria', 'Fotos', 'Descrição & Envio']
const wizardStep = ref(1)
const wizard = ref({ show: false, isEdit: false, listingId: null, saving: false, error: '' })

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
    mode: 'create',
    category_id: '',
    category_name: '',
    attributes: [],
    pictures: [],
    description_override: '',
    video_id: '',
    shipping_mode: 'me2',
    free_shipping: false,
    warranty_type: '',
    warranty_time: '',
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

// Category search
const categorySearch = ref('')
const categoryResults = ref([])
const catLoading = ref(false)
const categoryAttributes = ref([])
const attrValues = ref({})
const attrLoading = ref(false)

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

async function openWizard(listing) {
  wizardStep.value = 1
  wizard.value = { show: true, isEdit: !!listing, listingId: listing?.id || null, saving: false, error: '' }
  wf.value = defaultWizardForm()
  categorySearch.value = ''
  categoryResults.value = []
  categoryAttributes.value = []
  attrValues.value = {}
  productSearch.value = ''
  extraImageUrl.value = ''

  await Promise.all([loadCmigProductsForWizard(), loadPgProductsForWizard()])

  if (listing) {
    // Pre-fill from existing listing
    wf.value.title_override = listing.title_override || ''
    wf.value.sale_price = listing.sale_price
    wf.value.listing_type = listing.listing_type || 'gold_special'
    wf.value.available_quantity = listing.available_quantity || 1
    wf.value.item_condition = listing.item_condition || 'new'
    wf.value.platform_item_id = listing.platform_item_id || ''
    wf.value.category_id = listing.category_id || ''
    wf.value.description_override = listing.description_override || ''
    wf.value.video_id = listing.video_id || ''
    wf.value.shipping_mode = listing.shipping_mode || 'me2'
    wf.value.free_shipping = !!listing.free_shipping
    wf.value.warranty_type = listing.warranty_type || ''
    wf.value.warranty_time = listing.warranty_time || ''
    if (listing.cmig_product) {
      wf.value.product_type = 'cmig'
      wf.value.product_id = listing.cmig_product.id
      wf.value.selectedProduct = cmigProductList.value.find(p => p.id === listing.cmig_product.id) || listing.cmig_product
    } else if (listing.catalog_product) {
      wf.value.product_type = 'pg'
      wf.value.product_id = listing.catalog_product.id
      wf.value.selectedProduct = pgProductList.value.find(p => p.id === listing.catalog_product.id) || listing.catalog_product
    }
    if (listing.category_id) {
      wf.value.category_name = listing.category_id
      // try to load attributes for saved category
      try {
        const { data } = await api.get(`/anuncios/categories/${listing.category_id}/attributes`)
        categoryAttributes.value = Array.isArray(data) ? data : []
        if (listing.attributes_json) {
          try {
            const saved = JSON.parse(listing.attributes_json)
            for (const a of saved) { attrValues.value[a.id] = a.value_name }
          } catch { /* ignore parse error */ }
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
      available_quantity: wf.value.available_quantity || 1,
      item_condition: wf.value.item_condition,
      platform_item_id: wf.value.platform_item_id || null,
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
      mode: wf.value.mode,
    }
    if (wf.value.product_type === 'cmig') {
      payload.cmig_product_id = wf.value.product_id
    } else {
      payload.catalog_product_id = wf.value.product_id
    }

    if (wizard.value.isEdit) {
      await api.put(`/anuncios/${wizard.value.listingId}`, payload)
      toast.success('Anúncio atualizado!')
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
const createCmigModal = ref({ show: false, listing: null, saving: false, error: '' })
const createCmigForm = ref({ cmig_id: '', sku_cmig: '', title: '', brand: '', cost_price: '', ncm: '', weight_kg: '' })

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
    toast.success('Anúncio sincronizado com o ML!')
    await loadAnuncios()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar com ML')
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
