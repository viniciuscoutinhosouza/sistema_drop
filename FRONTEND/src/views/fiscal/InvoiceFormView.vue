<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0">
              <i class="fas mr-2" :class="directionIcon"></i>
              {{ isNew ? 'Nova ' : 'Editar ' }}{{ directionLabel }}
            </h1>
            <small class="text-muted">{{ form.id ? `NFe #${form.id} (${statusLabel(form.status)})` : 'Rascunho' }}</small>
          </div>
          <div class="col-sm-4 text-right">
            <RouterLink :to="backUrl" class="btn btn-secondary">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <!-- Cabeçalho -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-info-circle mr-2"></i>Dados gerais</h3>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="col-md-3" v-if="isNew">
                <label class="small mb-1">CMIG <span class="text-danger">*</span></label>
                <select v-model="form.cmig_id" class="form-control" :disabled="!isNew" @change="reloadPeople">
                  <option :value="null">Selecione...</option>
                  <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }}</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Finalidade</label>
                <select v-model="form.purpose" class="form-control" :disabled="!editable">
                  <option v-for="opt in purposeOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
              <div class="col-md-6">
                <label class="small mb-1">Natureza da operação</label>
                <input v-model="form.natureza_operacao" class="form-control" :disabled="!editable">
              </div>
            </div>

            <!-- Emitente (CMIG selecionada) -->
            <div v-if="selectedCmig" class="callout callout-info mt-3 py-2">
              <i class="fas fa-building mr-1"></i>
              <strong>Emitente:</strong>
              {{ selectedCmig.company_name }}
              <span v-if="selectedCmig.trade_name" class="text-muted"> — {{ selectedCmig.trade_name }}</span>
              <code class="ml-2">{{ selectedCmig.cnpj || selectedCmig.cpf }}</code>
            </div>

            <div class="row mt-3">
              <div class="col-md-6">
                <label class="small mb-1">{{ form.direction === 'in' ? 'Fornecedor' : 'Destinatário' }}</label>
                <div class="input-group">
                  <input :value="selectedPersonLabel" class="form-control" readonly placeholder="Nenhuma pessoa selecionada">
                  <div class="input-group-append" v-if="editable">
                    <button class="btn btn-outline-info" type="button" @click="openPersonPicker">
                      <i class="fas fa-search mr-1"></i> Selecionar
                    </button>
                  </div>
                </div>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Data emissão</label>
                <input v-model="issueDateLocal" type="date" class="form-control" :disabled="!editable">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Data saída</label>
                <input v-model="exitDateLocal" type="date" class="form-control" :disabled="!editable">
              </div>
            </div>

            <div class="row mt-3">
              <div class="col-md-3">
                <label class="small mb-1">Modalidade do frete</label>
                <select v-model.number="form.freight_modality" class="form-control" :disabled="!editable">
                  <option :value="null">—</option>
                  <option :value="0">0 — Por conta do emitente</option>
                  <option :value="1">1 — Por conta do destinatário</option>
                  <option :value="2">2 — Por conta de terceiros</option>
                  <option :value="9">9 — Sem ocorrência de transporte</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Forma de pagamento</label>
                <select v-model="form.payment_method" class="form-control" :disabled="!editable">
                  <option value="">—</option>
                  <option value="01">01 — Dinheiro</option>
                  <option value="03">03 — Cartão de crédito</option>
                  <option value="04">04 — Cartão de débito</option>
                  <option value="15">15 — Boleto</option>
                  <option value="17">17 — PIX</option>
                  <option value="90">90 — Sem pagamento</option>
                  <option value="99">99 — Outros</option>
                </select>
              </div>
              <div class="col-md-6">
                <label class="small mb-1">Informações adicionais</label>
                <input v-model="form.additional_info" class="form-control" :disabled="!editable">
              </div>
            </div>

            <div class="text-right mt-3" v-if="editable">
              <button class="btn btn-primary" :disabled="saving" @click="saveHeader">
                <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
                {{ saving ? 'Salvando...' : (isNew ? 'Criar Rascunho' : 'Salvar Cabeçalho') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Itens (apenas após criar a invoice) -->
        <div v-if="!isNew" class="card">
          <div class="card-header d-flex align-items-center">
            <h3 class="card-title flex-grow-1"><i class="fas fa-boxes mr-2"></i>Itens</h3>
            <button v-if="editable" class="btn btn-sm btn-primary" @click="openProductPicker()">
              <i class="fas fa-plus mr-1"></i> Adicionar Item
            </button>
          </div>
          <div class="card-body p-0">
            <table class="table table-sm mb-0">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Descrição</th>
                  <th>Origem</th>
                  <th>NCM</th>
                  <th>CFOP</th>
                  <th class="text-right">Qtd</th>
                  <th class="text-right">Valor un.</th>
                  <th class="text-right">Total</th>
                  <th v-if="editable"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="(form.items || []).length === 0">
                  <td :colspan="editable ? 9 : 8" class="text-center text-muted py-3">Nenhum item.</td>
                </tr>
                <tr v-for="it in form.items" :key="it.id">
                  <td>{{ it.item_number }}</td>
                  <td>
                    <strong>{{ it.description }}</strong>
                    <small v-if="it.sku" class="d-block text-muted">SKU: <code>{{ it.sku }}</code></small>
                    <small v-if="it.ean" class="d-block text-muted">EAN: {{ it.ean }}</small>
                  </td>
                  <td>
                    <span v-if="it.source_type === 'cmig'" class="badge badge-secondary" title="Produto do estoque CMIG">CMIG</span>
                    <span v-else-if="it.source_type === 'pg'" class="badge badge-info" title="Produto do estoque PG (Produto Geral)">PG</span>
                    <span v-else-if="it.cmig_product_id" class="badge badge-secondary" title="Produto do estoque CMIG">CMIG</span>
                    <span v-else class="badge badge-light text-muted" title="Item manual sem vínculo com estoque">Manual</span>
                  </td>
                  <td>{{ it.ncm || '—' }}</td>
                  <td>{{ it.cfop || '—' }}</td>
                  <td class="text-right">{{ formatNumber(it.quantity, 4) }}</td>
                  <td class="text-right">{{ formatCurrency(it.unit_value) }}</td>
                  <td class="text-right"><strong>{{ formatCurrency(it.total_value) }}</strong></td>
                  <td v-if="editable" class="text-right">
                    <button class="btn btn-sm btn-outline-primary mr-1" @click="openItemModal(it)" title="Editar">
                      <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="deleteItem(it)" title="Excluir">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="(form.items || []).length > 0">
                <tr>
                  <td colspan="7" class="text-right"><strong>Total da NFe:</strong></td>
                  <td class="text-right"><strong>{{ formatCurrency(form.total_invoice) }}</strong></td>
                  <td v-if="editable"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <!-- Botões finais -->
        <div v-if="!isNew && editable" class="text-right mb-4">
          <button class="btn btn-outline-primary mr-2" :disabled="calculating || !form.items?.length" @click="calculateTaxes">
            <i class="fas" :class="calculating ? 'fa-spinner fa-spin' : 'fa-calculator'"></i>
            {{ calculating ? 'Calculando...' : 'Calcular Impostos' }}
          </button>
          <button class="btn btn-primary mr-2" :disabled="finalizing || !form.items?.length"
                  :title="'Marca a NFe como finalizada sem transmitir à SEFAZ. O estoque é movimentado e ela entra nos totalizadores por Natureza da Operação.'"
                  @click="finalizeNoSefaz">
            <i class="fas" :class="finalizing ? 'fa-spinner fa-spin' : 'fa-check-double'"></i>
            {{ finalizing ? 'Salvando...' : 'Salvar sem SEFAZ' }}
          </button>
          <button class="btn btn-success" :disabled="transmitting || !form.items?.length" @click="transmit">
            <i class="fas" :class="transmitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
            {{ transmitting ? 'Transmitindo...' : 'Transmitir SEFAZ' }}
          </button>
        </div>
      </div>
    </section>

    <!-- Modal: selecionar Pessoa -->
    <div v-if="showPersonPicker" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Selecionar {{ form.direction === 'in' ? 'Fornecedor' : 'Destinatário' }}</h5>
            <button type="button" class="close" @click="showPersonPicker = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="d-flex mb-3" style="gap:.5rem">
              <input v-model="personSearch" class="form-control" placeholder="Buscar por nome ou documento..."
                     @input="searchPeople">
              <button class="btn btn-primary text-nowrap" type="button" @click="openCreatePerson">
                <i class="fas fa-user-plus mr-1"></i> Novo {{ form.direction === 'in' ? 'Fornecedor' : 'Cliente' }}
              </button>
            </div>
            <div v-if="loadingPeople" class="text-center py-3">
              <i class="fas fa-spinner fa-spin"></i>
            </div>
            <table v-else class="table table-sm table-hover">
              <tbody>
                <tr v-if="peopleList.length === 0">
                  <td colspan="3" class="text-center text-muted py-3">
                    <i class="fas fa-search mr-1"></i>
                    Nenhuma pessoa encontrada.
                    <div class="small mt-1">
                      Verifique se a pessoa está cadastrada <strong>na mesma CMIG desta NF-e</strong>,
                      ou clique em <strong>"Novo {{ form.direction === 'in' ? 'Fornecedor' : 'Cliente' }}"</strong> para cadastrar.
                    </div>
                  </td>
                </tr>
                <tr v-for="p in peopleList" :key="p.id" style="cursor:pointer" @click="selectPerson(p)">
                  <td><code>{{ p.document }}</code></td>
                  <td>
                    <strong>{{ p.name }}</strong>
                    <small v-if="p.trade_name" class="d-block text-muted">{{ p.trade_name }}</small>
                  </td>
                  <td>
                    <span v-if="p.is_customer" class="badge badge-info mr-1">Cliente</span>
                    <span v-if="p.is_supplier" class="badge badge-warning">Fornecedor</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: criar nova Pessoa (Cliente/Fornecedor) -->
    <div v-if="showCreatePerson" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5); z-index: 1060">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">
              Novo {{ form.direction === 'in' ? 'Fornecedor' : 'Cliente' }}
            </h5>
            <button type="button" class="close" @click="showCreatePerson = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="row">
              <div class="col-md-4">
                <label class="small mb-1">Tipo</label>
                <select v-model="newPerson.person_type" class="form-control">
                  <option value="PJ">PJ — Pessoa Jurídica</option>
                  <option value="PF">PF — Pessoa Física</option>
                </select>
              </div>
              <div class="col-md-5">
                <label class="small mb-1">{{ newPerson.person_type === 'PJ' ? 'CNPJ' : 'CPF' }} <span class="text-danger">*</span></label>
                <div class="input-group">
                  <input v-model="newPerson.document" class="form-control"
                         :placeholder="newPerson.person_type === 'PJ' ? '00.000.000/0000-00' : '000.000.000-00'">
                  <div v-if="newPerson.person_type === 'PJ'" class="input-group-append">
                    <button class="btn btn-outline-info" type="button"
                            :disabled="lookingUpCnpj || !newPerson.document"
                            @click="lookupCnpj">
                      <i class="fas" :class="lookingUpCnpj ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                    </button>
                  </div>
                </div>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">IE</label>
                <input v-model="newPerson.ie" class="form-control" :disabled="newPerson.ie_isento">
                <div class="form-check mt-1">
                  <input v-model="newPerson.ie_isento" type="checkbox" class="form-check-input" id="ieIsentoChk">
                  <label class="form-check-label small" for="ieIsentoChk">Isento de IE</label>
                </div>
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-7">
                <label class="small mb-1">Nome / Razão Social <span class="text-danger">*</span></label>
                <input v-model="newPerson.name" class="form-control">
              </div>
              <div class="col-md-5">
                <label class="small mb-1">Nome Fantasia</label>
                <input v-model="newPerson.trade_name" class="form-control">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-6">
                <label class="small mb-1">E-mail</label>
                <input v-model="newPerson.email" class="form-control" type="email">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Telefone</label>
                <input v-model="newPerson.phone" class="form-control">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">CEP</label>
                <input v-model="newPerson.zip_code" class="form-control" maxlength="9">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-6">
                <label class="small mb-1">Logradouro</label>
                <input v-model="newPerson.street" class="form-control">
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Número</label>
                <input v-model="newPerson.address_number" class="form-control">
              </div>
              <div class="col-md-4">
                <label class="small mb-1">Complemento</label>
                <input v-model="newPerson.complement" class="form-control">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-5">
                <label class="small mb-1">Bairro</label>
                <input v-model="newPerson.neighborhood" class="form-control">
              </div>
              <div class="col-md-5">
                <label class="small mb-1">Cidade</label>
                <input v-model="newPerson.city" class="form-control">
              </div>
              <div class="col-md-2">
                <label class="small mb-1">UF</label>
                <input v-model="newPerson.state" class="form-control" maxlength="2" style="text-transform:uppercase">
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showCreatePerson = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="savingPerson" @click="saveNewPerson">
              <i class="fas" :class="savingPerson ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ savingPerson ? 'Salvando...' : 'Salvar e Selecionar' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Selecionar Produto (CMIG ou PG) -->
    <div v-if="showProductPicker" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-xl">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title"><i class="fas fa-box-open mr-2"></i>Selecionar Produto</h5>
            <button type="button" class="close" @click="showProductPicker = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <input v-model="productSearch" class="form-control mb-3"
                   placeholder="Buscar por nome ou SKU...">
            <!-- Tabs -->
            <ul class="nav nav-tabs mb-3">
              <li class="nav-item">
                <a class="nav-link" :class="{ active: productPickerTab === 'cmig' }"
                   href="#" @click.prevent="productPickerTab = 'cmig'">
                  <i class="fas fa-tag mr-1"></i>Produtos CMIG
                  <span class="badge badge-secondary ml-1">{{ cmigProductsFiltered.length }}</span>
                </a>
              </li>
              <li class="nav-item">
                <a class="nav-link" :class="{ active: productPickerTab === 'pg' }"
                   href="#" @click.prevent="switchToPgTab()">
                  <i class="fas fa-warehouse mr-1"></i>Catálogo PG
                  <span class="badge badge-secondary ml-1">{{ pgProductsFiltered.length }}</span>
                </a>
              </li>
            </ul>

            <!-- Tab CMIG -->
            <div v-if="productPickerTab === 'cmig'">
              <div v-if="loadingCmigProducts" class="text-center py-4">
                <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
              </div>
              <div v-else-if="cmigProductsFiltered.length === 0" class="text-center text-muted py-4">
                <i class="fas fa-box-open fa-2x mb-2 d-block"></i>
                Nenhum produto CMIG encontrado.
              </div>
              <div v-else class="table-responsive" style="max-height:400px;overflow-y:auto">
                <table class="table table-sm table-hover mb-0">
                  <thead class="thead-light sticky-top">
                    <tr>
                      <th style="width:56px"></th>
                      <th>SKU</th>
                      <th>Nome</th>
                      <th>NCM</th>
                      <th class="text-right">Estoque</th>
                      <th class="text-right">Preço sugerido</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="p in cmigProductsFiltered" :key="p.id"
                        style="cursor:pointer" @click="selectProduct(p, 'cmig')">
                      <td class="text-center">
                        <img v-if="p.thumbnail" :src="p.thumbnail" style="width:40px;height:40px;object-fit:cover;border-radius:4px">
                        <i v-else class="fas fa-image text-muted" style="font-size:1.5rem"></i>
                      </td>
                      <td><code>{{ p.sku_cmig || '—' }}</code></td>
                      <td>
                        <strong>{{ p.title }}</strong>
                        <small v-if="p.brand" class="d-block text-muted">{{ p.brand }}</small>
                      </td>
                      <td>{{ p.ncm || '—' }}</td>
                      <td class="text-right">
                        <span :class="p.stock_quantity > 0 ? 'text-success' : 'text-danger'">
                          {{ p.stock_quantity ?? 0 }}
                        </span>
                      </td>
                      <td class="text-right">{{ p.suggested_price != null ? formatCurrency(p.suggested_price) : '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Tab PG -->
            <div v-if="productPickerTab === 'pg'">
              <div v-if="loadingPgProducts" class="text-center py-4">
                <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
              </div>
              <div v-else-if="pgProductsFiltered.length === 0" class="text-center text-muted py-4">
                <i class="fas fa-warehouse fa-2x mb-2 d-block"></i>
                Nenhum produto PG encontrado.
              </div>
              <div v-else class="table-responsive" style="max-height:400px;overflow-y:auto">
                <table class="table table-sm table-hover mb-0">
                  <thead class="thead-light sticky-top">
                    <tr>
                      <th style="width:56px"></th>
                      <th>SKU</th>
                      <th>Nome</th>
                      <th>NCM</th>
                      <th class="text-right">Estoque</th>
                      <th class="text-right">Preço sugerido</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="p in pgProductsFiltered" :key="p.id"
                        style="cursor:pointer" @click="selectProduct(p, 'pg')">
                      <td class="text-center">
                        <img v-if="p.thumbnail" :src="p.thumbnail" style="width:40px;height:40px;object-fit:cover;border-radius:4px">
                        <i v-else class="fas fa-image text-muted" style="font-size:1.5rem"></i>
                      </td>
                      <td><code>{{ p.sku || '—' }}</code></td>
                      <td>
                        <strong>{{ p.title }}</strong>
                        <small v-if="p.brand" class="d-block text-muted">{{ p.brand }}</small>
                      </td>
                      <td>{{ p.ncm || '—' }}</td>
                      <td class="text-right">
                        <span :class="p.stock_quantity > 0 ? 'text-success' : 'text-danger'">
                          {{ p.stock_quantity ?? 0 }}
                        </span>
                      </td>
                      <td class="text-right">{{ p.suggested_price != null ? formatCurrency(p.suggested_price) : '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <small class="text-muted mr-auto">Clique em um produto para adicioná-lo à NF-e.</small>
            <button class="btn btn-secondary" @click="showProductPicker = false">Cancelar</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Item -->
    <div v-if="showItemModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <div>
              <h5 class="modal-title mb-0">{{ itemForm.id ? 'Editar Item' : 'Confirmar Item' }}</h5>
              <small v-if="!itemForm.id && itemForm.description" class="text-muted">
                Produto: {{ itemForm.description }}
              </small>
            </div>
            <button type="button" class="close" @click="showItemModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="row">
              <div class="col-md-9">
                <label class="small mb-1">Descrição <span class="text-danger">*</span></label>
                <input v-model="itemForm.description" class="form-control">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">SKU</label>
                <input :value="itemForm.sku || '—'" class="form-control bg-light" readonly>
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-3">
                <label class="small mb-1">NCM</label>
                <input v-model="itemForm.ncm" class="form-control" maxlength="10" placeholder="0000.00.00">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">CEST</label>
                <input v-model="itemForm.cest" class="form-control" maxlength="7">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">CFOP</label>
                <input v-model="itemForm.cfop" class="form-control" maxlength="4" placeholder="5102">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">EAN</label>
                <input v-model="itemForm.ean" class="form-control" maxlength="14">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-2">
                <label class="small mb-1">Unidade</label>
                <input v-model="itemForm.unit" class="form-control" maxlength="6">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Quantidade</label>
                <input v-model.number="itemForm.quantity" type="number" step="0.0001" min="0" class="form-control">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Valor unitário</label>
                <input v-model.number="itemForm.unit_value" type="number" step="0.0001" min="0" class="form-control">
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Origem</label>
                <select v-model.number="itemForm.origin" class="form-control">
                  <option :value="0">0 — Nacional</option>
                  <option :value="1">1 — Estrangeira (importação direta)</option>
                  <option :value="2">2 — Estrangeira (mercado interno)</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Total calculado</label>
                <input :value="formatCurrency(calcTotal)" class="form-control" disabled>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showItemModal = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="savingItem" @click="saveItem">
              <i class="fas" :class="savingItem ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ savingItem ? 'Salvando...' : 'Salvar Item' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { usePeopleStore } from '@/stores/people'
import { useToast } from '@/composables/useToast'
import { fmt } from '@/views/fiscal/_helpers'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const peopleStore = usePeopleStore()
const toast = useToast()
const { cmigs } = storeToRefs(cmigStore)

const initialDirection = (route.query.direction === 'in' ? 'in' : 'out')
const isNew = computed(() => !route.params.id)
const invoiceId = computed(() => route.params.id ? Number(route.params.id) : null)

const saving = ref(false)
const savingItem = ref(false)
const calculating = ref(false)
const transmitting = ref(false)
const finalizing = ref(false)
const showPersonPicker = ref(false)
const showCreatePerson = ref(false)
const showItemModal = ref(false)
const personSearch = ref('')
const loadingPeople = ref(false)
const peopleList = ref([])
const selectedPerson = ref(null)
const savingPerson = ref(false)
const lookingUpCnpj = ref(false)

// Product Picker
const showProductPicker = ref(false)
const productPickerTab = ref('cmig')
const productSearch = ref('')
const cmigProductsAll = ref([])
const pgProductsAll = ref([])
const loadingCmigProducts = ref(false)
const loadingPgProducts = ref(false)

function _emptyNewPerson() {
  return {
    person_type: 'PJ',
    document: '',
    ie: '',
    ie_isento: false,
    name: '',
    trade_name: '',
    email: '',
    phone: '',
    zip_code: '',
    street: '',
    address_number: '',
    complement: '',
    neighborhood: '',
    city: '',
    state: '',
  }
}
const newPerson = reactive(_emptyNewPerson())

const form = reactive({
  id: null,
  cmig_id: null,
  direction: initialDirection,
  purpose: 'venda',
  natureza_operacao: initialDirection === 'in' ? 'Compra para revenda' : 'Venda de mercadoria',
  status: 'draft',
  person_id: null,
  issue_date: null,
  exit_date: null,
  freight_modality: null,
  payment_method: '',
  additional_info: '',
  total_invoice: 0,
  items: [],
})

const itemForm = reactive({
  id: null,
  cmig_product_id: null,
  catalog_product_id: null,
  sku: '',
  source_type: null,
  description: '',
  ncm: '',
  cest: '',
  cfop: initialDirection === 'in' ? '1102' : '5102',
  ean: '',
  unit: 'UN',
  quantity: 1,
  unit_value: 0,
  origin: 0,
})

const issueDateLocal = computed({
  get: () => form.issue_date ? form.issue_date.slice(0, 10) : '',
  set: (v) => { form.issue_date = v ? `${v}T00:00:00` : null },
})
const exitDateLocal = computed({
  get: () => form.exit_date ? form.exit_date.slice(0, 10) : '',
  set: (v) => { form.exit_date = v ? `${v}T00:00:00` : null },
})

const editable = computed(() => form.status === 'draft')
const directionIcon = computed(() => form.direction === 'in' ? 'fa-arrow-down text-warning' : 'fa-arrow-up text-success')
const directionLabel = computed(() => form.direction === 'in' ? 'Entrada' : 'Saída')
const backUrl = computed(() => form.direction === 'in' ? '/fiscal/entradas' : '/fiscal/saidas')

const purposeOptions = computed(() => {
  if (form.direction === 'in') {
    return [
      { value: 'venda',         label: 'Compra' },
      { value: 'devolucao',     label: 'Devolução de venda (cliente devolveu)' },
      { value: 'remessa',       label: 'Remessa recebida' },
      { value: 'retorno',       label: 'Retorno de mercadoria' },
      { value: 'transferencia', label: 'Transferência recebida' },
      { value: 'complementar',  label: 'Complementar de entrada' },
      { value: 'ajuste',        label: 'Ajuste' },
      { value: 'outros',        label: 'Outros' },
    ]
  }
  return [
    { value: 'venda',         label: 'Venda' },
    { value: 'devolucao',     label: 'Devolução de compra' },
    { value: 'remessa',       label: 'Simples Remessa' },
    { value: 'retorno',       label: 'Retorno' },
    { value: 'transferencia', label: 'Transferência' },
    { value: 'complementar',  label: 'Complementar' },
    { value: 'ajuste',        label: 'Ajuste' },
    { value: 'outros',        label: 'Outros' },
  ]
})

const selectedPersonLabel = computed(() => {
  if (!selectedPerson.value) return ''
  const p = selectedPerson.value
  return `${p.name} — ${p.document}`
})

const selectedCmig = computed(() => cmigs.value.find(c => c.id === form.cmig_id) || null)

const cmigProductsFiltered = computed(() => {
  const q = productSearch.value.toLowerCase()
  if (!q) return cmigProductsAll.value
  return cmigProductsAll.value.filter(p =>
    (p.title || '').toLowerCase().includes(q) ||
    (p.sku_cmig || '').toLowerCase().includes(q)
  )
})

const pgProductsFiltered = computed(() => {
  const q = productSearch.value.toLowerCase()
  if (!q) return pgProductsAll.value
  return pgProductsAll.value.filter(p =>
    (p.title || '').toLowerCase().includes(q) ||
    (p.sku || '').toLowerCase().includes(q)
  )
})

const calcTotal = computed(() => Number((itemForm.quantity || 0) * (itemForm.unit_value || 0)).toFixed(2))
const formatNumber = (v, dec = 2) => v == null ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec })
const formatCurrency = fmt.currency
const statusLabel = fmt.statusLabel

// Limpa cache de produtos CMIG ao trocar de CMIG
watch(() => form.cmig_id, () => {
  cmigProductsAll.value = []
})

watch(() => form.purpose, (p) => {
  // Sugerir CFOP padrão (intra-estadual). Usuário ajusta depois se for interestadual.
  if (form.direction === 'out') {
    if (p === 'venda') itemForm.cfop = '5102'
    if (p === 'devolucao') itemForm.cfop = '5202'  // devolução de compra (saída)
    if (p === 'remessa') itemForm.cfop = '5949'
    if (p === 'transferencia') itemForm.cfop = '5152'
    if (p === 'retorno') itemForm.cfop = '5949'
  } else {
    if (p === 'venda') itemForm.cfop = '1102'         // compra para revenda
    if (p === 'devolucao') itemForm.cfop = '1202'     // devolução de venda (entrada)
    if (p === 'remessa') itemForm.cfop = '1949'
    if (p === 'transferencia') itemForm.cfop = '1152'
    if (p === 'retorno') itemForm.cfop = '1949'
  }
})

// ── Product Picker ─────────────────────────────────────────────────────────────

async function openProductPicker() {
  if (!form.cmig_id) {
    toast.warning('Selecione a CMIG antes de adicionar itens.')
    return
  }
  productSearch.value = ''
  productPickerTab.value = 'cmig'
  showProductPicker.value = true
  if (cmigProductsAll.value.length === 0) {
    loadingCmigProducts.value = true
    try {
      const { data } = await api.get(`/cmigs/${form.cmig_id}/products`)
      cmigProductsAll.value = data
    } catch (e) {
      toast.error('Erro ao carregar produtos CMIG')
    } finally {
      loadingCmigProducts.value = false
    }
  }
}

async function switchToPgTab() {
  productPickerTab.value = 'pg'
  if (pgProductsAll.value.length === 0) {
    loadingPgProducts.value = true
    try {
      const { data } = await api.get('/pg')
      pgProductsAll.value = data
    } catch (e) {
      toast.error('Erro ao carregar catálogo PG')
    } finally {
      loadingPgProducts.value = false
    }
  }
}

function selectProduct(p, source) {
  const cfop = form.direction === 'in' ? '1102' : '5102'
  const sku = source === 'cmig' ? (p.sku_cmig || '') : (p.sku || '')
  Object.assign(itemForm, {
    id: null,
    cmig_product_id: source === 'cmig' ? p.id : null,
    catalog_product_id: source === 'pg' ? p.id : null,
    sku,
    source_type: source,
    description: p.title || '',
    ncm: p.ncm || '',
    cest: p.cest || '',
    cfop,
    ean: p.ean || '',
    unit: 'UN',
    quantity: 1,
    unit_value: form.direction === 'in'
      ? (p.cost_price ?? p.suggested_price ?? 0)
      : (p.suggested_price ?? p.cost_price ?? 0),
    origin: p.origin ?? 0,
  })
  showProductPicker.value = false
  showItemModal.value = true
}

// ── People ─────────────────────────────────────────────────────────────────────

async function reloadPeople(query = '') {
  if (!form.cmig_id) return
  loadingPeople.value = true
  try {
    const params = { cmig_id: form.cmig_id, page_size: 100, is_active: true }
    // Sem filtro is_customer/is_supplier: mostra todas as pessoas ativas da CMIG
    // O tipo (Cliente/Fornecedor) é exibido como badge na lista para o usuário escolher
    if (query) params.search = query
    const data = await peopleStore.fetchPeople(params)
    peopleList.value = data.items || []
  } finally {
    loadingPeople.value = false
  }
}

function openPersonPicker() {
  showPersonPicker.value = true
  personSearch.value = ''
  reloadPeople()
}

let searchTimer = null
function searchPeople() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => reloadPeople(personSearch.value), 300)
}

function selectPerson(p) {
  selectedPerson.value = p
  form.person_id = p.id
  showPersonPicker.value = false
}

function openCreatePerson() {
  if (!form.cmig_id) {
    toast.warning('Selecione a CMIG antes de cadastrar uma pessoa.')
    return
  }
  Object.assign(newPerson, _emptyNewPerson())
  // Pré-preenche o documento se o usuário digitou algo na busca
  const digits = (personSearch.value || '').replace(/\D/g, '')
  if (digits.length === 11 || digits.length === 14) {
    newPerson.document = digits
    newPerson.person_type = digits.length === 14 ? 'PJ' : 'PF'
  }
  showCreatePerson.value = true
}

async function lookupCnpj() {
  const cnpj = (newPerson.document || '').replace(/\D/g, '')
  if (cnpj.length !== 14) {
    toast.warning('Informe um CNPJ válido (14 dígitos).')
    return
  }
  lookingUpCnpj.value = true
  try {
    const data = await peopleStore.lookupCnpj(cnpj)
    Object.assign(newPerson, {
      document: cnpj,
      name: data.razao_social || data.nome || newPerson.name,
      trade_name: data.nome_fantasia || newPerson.trade_name,
      email: data.email || newPerson.email,
      phone: data.ddd_telefone_1 || data.telefone || newPerson.phone,
      zip_code: data.cep || newPerson.zip_code,
      street: data.logradouro || newPerson.street,
      address_number: data.numero || newPerson.address_number,
      complement: data.complemento || newPerson.complement,
      neighborhood: data.bairro || newPerson.neighborhood,
      city: data.municipio || newPerson.city,
      state: data.uf || newPerson.state,
    })
  } catch (e) {
    toast.error(e.response?.data?.detail || 'CNPJ não encontrado')
  } finally {
    lookingUpCnpj.value = false
  }
}

async function saveNewPerson() {
  if (!form.cmig_id) {
    toast.warning('Selecione a CMIG antes de cadastrar uma pessoa.')
    return
  }
  const doc = (newPerson.document || '').replace(/\D/g, '')
  if (doc.length !== 11 && doc.length !== 14) {
    toast.warning('Documento deve ter 11 (CPF) ou 14 (CNPJ) dígitos.')
    return
  }
  if (!newPerson.name?.trim()) {
    toast.warning('Nome / Razão Social é obrigatório.')
    return
  }
  savingPerson.value = true
  try {
    const payload = {
      cmig_id: form.cmig_id,
      person_type: newPerson.person_type,
      document: doc,
      ie: newPerson.ie || null,
      ie_isento: !!newPerson.ie_isento,
      name: newPerson.name.trim(),
      trade_name: newPerson.trade_name || null,
      email: newPerson.email || null,
      phone: newPerson.phone || null,
      zip_code: newPerson.zip_code || null,
      street: newPerson.street || null,
      address_number: newPerson.address_number || null,
      complement: newPerson.complement || null,
      neighborhood: newPerson.neighborhood || null,
      city: newPerson.city || null,
      state: (newPerson.state || '').toUpperCase() || null,
      is_customer: form.direction !== 'in',
      is_supplier: form.direction === 'in',
    }
    const created = await peopleStore.createPerson(payload)
    toast.success(`${form.direction === 'in' ? 'Fornecedor' : 'Cliente'} cadastrado`)
    showCreatePerson.value = false
    selectPerson(created)
    // Atualiza a lista do picker em segundo plano para refletir o novo registro
    reloadPeople(personSearch.value)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao cadastrar pessoa')
  } finally {
    savingPerson.value = false
  }
}

async function loadInvoice() {
  if (!invoiceId.value) return
  try {
    const data = await fiscalStore.fetchInvoice(invoiceId.value)
    Object.assign(form, {
      id: data.id,
      cmig_id: data.cmig_id,
      direction: data.direction,
      purpose: data.purpose,
      natureza_operacao: data.natureza_operacao,
      status: data.status,
      person_id: data.person_id,
      issue_date: data.issue_date,
      exit_date: data.exit_date,
      freight_modality: data.freight_modality,
      payment_method: data.payment_method || '',
      additional_info: data.additional_info || '',
      total_invoice: data.total_invoice || 0,
      items: data.items || [],
    })
    selectedPerson.value = data.person ? { ...data.person } : null
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NFe')
    router.push(backUrl.value)
  }
}

async function saveHeader({ silent = false } = {}) {
  saving.value = true
  try {
    const payload = {
      cmig_id: form.cmig_id,
      direction: form.direction,
      purpose: form.purpose,
      natureza_operacao: form.natureza_operacao,
      person_id: form.person_id,
      issue_date: form.issue_date,
      exit_date: form.exit_date,
      freight_modality: form.freight_modality,
      payment_method: form.payment_method || null,
      additional_info: form.additional_info,
    }
    if (isNew.value) {
      const created = await fiscalStore.createInvoice(payload)
      if (!silent) toast.success('Rascunho criado')
      router.replace(`/fiscal/invoices/${created.id}/edit`)
    } else {
      await fiscalStore.updateInvoice(invoiceId.value, payload)
      if (!silent) {
        toast.success('Cabeçalho salvo')
        await loadInvoice()
      }
    }
  } catch (e) {
    if (silent) throw e
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

function openItemModal(it) {
  if (it) {
    Object.assign(itemForm, {
      id: it.id,
      cmig_product_id: it.cmig_product_id || null,
      catalog_product_id: it.catalog_product_id || null,
      sku: it.sku || '',
      source_type: it.source_type || null,
      description: it.description,
      ncm: it.ncm || '',
      cest: it.cest || '',
      cfop: it.cfop || '',
      ean: it.ean || '',
      unit: it.unit || 'UN',
      quantity: Number(it.quantity || 1),
      unit_value: Number(it.unit_value || 0),
      origin: it.origin ?? 0,
    })
    showItemModal.value = true
  }
  // Novos itens sempre passam pelo openProductPicker() antes de chegar aqui
}

async function saveItem() {
  if (!itemForm.description?.trim()) {
    toast.warning('Descrição é obrigatória')
    return
  }
  savingItem.value = true
  try {
    const payload = {
      cmig_product_id: itemForm.cmig_product_id || null,
      catalog_product_id: itemForm.catalog_product_id || null,
      sku: itemForm.sku || null,
      source_type: itemForm.source_type || null,
      description: itemForm.description,
      ncm: itemForm.ncm || null,
      cest: itemForm.cest || null,
      cfop: itemForm.cfop || null,
      ean: itemForm.ean || null,
      unit: itemForm.unit || 'UN',
      quantity: Number(itemForm.quantity || 0),
      unit_value: Number(itemForm.unit_value || 0),
      origin: itemForm.origin ?? 0,
    }
    if (itemForm.id) {
      await fiscalStore.updateItem(invoiceId.value, itemForm.id, payload)
      toast.success('Item atualizado')
    } else {
      await fiscalStore.addItem(invoiceId.value, payload)
      toast.success('Item adicionado')
    }
    showItemModal.value = false
    await loadInvoice()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar item')
  } finally {
    savingItem.value = false
  }
}

async function deleteItem(it) {
  if (!confirm(`Excluir item "${it.description}"?`)) return
  try {
    await fiscalStore.deleteItem(invoiceId.value, it.id)
    toast.success('Item excluído')
    await loadInvoice()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir')
  }
}

async function calculateTaxes() {
  calculating.value = true
  try {
    await saveHeader({ silent: true })
    await fiscalStore.calculateTaxes(invoiceId.value)
    toast.success('Impostos recalculados')
    await loadInvoice()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao calcular impostos')
  } finally {
    calculating.value = false
  }
}

async function transmit() {
  if (!confirm('Transmitir esta NFe para a SEFAZ via Focus NFe? Após a autorização, ela não poderá ser editada.')) return
  transmitting.value = true
  try {
    await saveHeader({ silent: true })
    const result = await fiscalStore.transmit(invoiceId.value)
    if (result.status === 'authorized') {
      toast.success('NFe autorizada!')
    } else if (result.status === 'processing') {
      toast.info('NFe em processamento — aguarde o webhook do Focus.')
    } else {
      toast.warning(`Status: ${result.status} — ${result.focus_message || ''}`)
    }
    router.push(`/fiscal/invoices/${invoiceId.value}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao transmitir')
    await loadInvoice()
  } finally {
    transmitting.value = false
  }
}

async function finalizeNoSefaz() {
  if (!confirm(
    'Finalizar esta NFe SEM transmitir à SEFAZ?\n\n' +
    '• O estoque dos CMIGProducts vinculados será movimentado.\n' +
    '• A NFe entrará nos totalizadores por Natureza da Operação.\n' +
    '• Não será possível editá-la depois.'
  )) return
  finalizing.value = true
  try {
    await saveHeader({ silent: true })
    const result = await fiscalStore.finalizeNoSefaz(invoiceId.value)
    const sm = result.stock_movement || {}
    toast.success(
      `NFe finalizada — estoque: ${sm.matched || 0} item(ns) OK` +
      (sm.unmatched ? `, ${sm.unmatched} sem vínculo` : '')
    )
    router.push(`/fiscal/invoices/${invoiceId.value}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao finalizar')
    await loadInvoice()
  } finally {
    finalizing.value = false
  }
}

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  if (isNew.value) {
    if (cmigs.value.length > 0 && !form.cmig_id) {
      form.cmig_id = cmigs.value[0].id
    }
    form.issue_date = new Date().toISOString()
    await reloadPeople()
  } else {
    await loadInvoice()
    await reloadPeople()
  }
})
</script>
