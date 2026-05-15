<template>
  <div>
    <h4 class="mb-2 font-weight-bold">Pedidos</h4>
    <!-- Paginação topo -->
    <div class="d-flex align-items-center justify-content-between mb-2 flex-wrap" style="gap:.5rem">
      <div class="d-flex align-items-center" style="gap:.25rem">
        <select v-model="pageSize" class="form-control form-control-sm" style="width:70px" @change="onPageSizeChange">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
        </select>
        <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage <= 1" @click="goPage(1)" title="Primeira">
          <i class="fas fa-angle-double-left"></i>
        </button>
        <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage <= 1" @click="prevPage">
          <i class="fas fa-angle-left"></i>
        </button>
        <template v-for="p in visiblePages" :key="p">
          <button class="btn btn-sm" :class="p === currentPage ? 'btn-primary' : 'btn-outline-secondary'" @click="goPage(p)">{{ p }}</button>
        </template>
        <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage >= totalPages" @click="nextPage">
          <i class="fas fa-angle-right"></i>
        </button>
        <button class="btn btn-sm btn-outline-secondary" :disabled="currentPage >= totalPages" @click="goPage(totalPages)" title="Última">
          <i class="fas fa-angle-double-right"></i>
        </button>
        <select v-model.number="currentPage" class="form-control form-control-sm" style="width:70px" @change="loadOrders">
          <option v-for="p in totalPages" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
      <span class="text-muted small">{{ total }} pedidos</span>
    </div>

    <!-- Filtros -->
    <div class="card mb-2">
      <div class="card-body py-2">
        <div class="row align-items-center g-2">
          <div class="col-md-3">
            <input v-model="filters.search" type="text" class="form-control form-control-sm" placeholder="Buscar por cliente..." @keyup.enter="resetAndLoad" />
          </div>
          <div class="col-md-2">
            <select v-model="filters.status" class="form-control form-control-sm" @change="resetAndLoad">
              <option value="">Todos os status</option>
              <option v-for="s in ORDER_STATUSES" :key="s.key" :value="s.key">{{ s.label }}</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.platform" class="form-control form-control-sm" @change="resetAndLoad">
              <option value="">Todos os canais</option>
              <option v-for="p in PLATFORMS" :key="p.key" :value="p.key">{{ p.label }}</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.payment_status" class="form-control form-control-sm" @change="resetAndLoad">
              <option value="">Pagamento</option>
              <option value="pending">Não pago</option>
              <option value="paid">Pago</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.shipment_status" class="form-control form-control-sm" @change="resetAndLoad">
              <option value="">Envio</option>
              <option value="pending">Aguardando</option>
              <option value="handling">Em Preparação</option>
              <option value="ready_to_ship">Pronto p/ Envio</option>
              <option value="shipped">A caminho</option>
              <option value="delivered">Entregue</option>
              <option value="not_delivered">Não Entregue</option>
              <option value="cancelled">Cancelado</option>
            </select>
          </div>
          <div class="col-md-2">
            <select v-model="filters.tag" class="form-control form-control-sm" @change="resetAndLoad">
              <option value="">Tags</option>
              <option value="fraud_risk_detected">⚠️ Risco de Fraude</option>
              <option value="not_paid">Não pago</option>
              <option value="cart">Carrinho</option>
              <option value="test_order">Teste</option>
              <option value="not_delivered">Não entregue</option>
            </select>
          </div>
          <div v-if="availableCmigs.length > 1" class="col-md-3">
            <select v-model="filters.cmig_id" class="form-control form-control-sm" @change="resetAndLoad">
              <option value="">Todas as CMIGs</option>
              <option v-for="c in availableCmigs" :key="c.id" :value="c.id">
                {{ c.trade_name || c.company_name }}
              </option>
            </select>
          </div>
          <div class="col-auto">
            <button class="btn btn-sm btn-primary" @click="resetAndLoad"><i class="fas fa-search"></i></button>
          </div>
        </div>
      </div>
    </div>

    <!-- Toolbar bulk -->
    <div class="card mb-2">
      <div class="card-body py-2 d-flex align-items-center flex-wrap" style="gap:.5rem">
        <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" style="width:16px;height:16px" />
        <div class="dropdown">
          <button class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
            <i class="fas fa-print mr-1"></i>Imprimir Selecionadas
            <span v-if="selectedOrders.length" class="badge badge-primary ml-1">{{ selectedOrders.length }}</span>
          </button>
          <div class="dropdown-menu">
            <a class="dropdown-item" href="#" @click.prevent="printSelected"><i class="fas fa-print mr-2"></i>Imprimir Etiquetas</a>
            <a class="dropdown-item" href="#" @click.prevent="viewSelectedLabels"><i class="fas fa-eye mr-2"></i>Visualizar Etiquetas</a>
          </div>
        </div>
        <div class="dropdown">
          <button class="btn btn-sm btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
            <i class="fas fa-tasks mr-1"></i>Ações Múltiplas
            <span v-if="selectedOrders.length" class="badge badge-secondary ml-1">{{ selectedOrders.length }}</span>
          </button>
          <div class="dropdown-menu">
            <a class="dropdown-item" href="#" @click.prevent="bulkStatus('separated')"><i class="fas fa-box-open mr-2"></i>Marcar como Separado</a>
            <a class="dropdown-item" href="#" @click.prevent="bulkStatus('shipped')"><i class="fas fa-truck mr-2"></i>Marcar como Coletado</a>
            <div class="dropdown-divider"></div>
            <a class="dropdown-item text-danger" href="#" @click.prevent="bulkHide"><i class="fas fa-eye-slash mr-2"></i>Ocultar Selecionados</a>
            <a v-if="canDelete" class="dropdown-item text-danger" href="#" @click.prevent="bulkDelete">
              <i class="fas fa-trash mr-2"></i>Excluir Selecionados
            </a>
            <div class="dropdown-divider"></div>
            <a class="dropdown-item" href="#" @click.prevent="bulkDownloadXml"><i class="fas fa-file-code mr-2"></i>Baixar XMLs (NF-e)</a>
            <a class="dropdown-item" href="#" @click.prevent="bulkPrintDanfe"><i class="fas fa-print mr-2"></i>Imprimir DANFEs</a>
          </div>
        </div>
        <div class="ml-auto d-flex" style="gap:.4rem">
          <button class="btn btn-sm btn-outline-primary" @click="syncOrders" :disabled="syncing" title="Sincronizar últimos 7 dias com ML/Shopee">
            <i class="fas fa-cloud-download-alt mr-1" :class="{ 'fa-spin': syncing }"></i>
            {{ syncing ? 'Sincronizando...' : 'Sincronizar' }}
          </button>
          <button class="btn btn-sm btn-outline-secondary" @click="showSyncRangeModal = true" title="Sincronizar período">
            <i class="fas fa-calendar-alt"></i>
          </button>
          <button class="btn btn-sm btn-outline-secondary" @click="loadOrders" title="Recarregar lista">
            <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-5 text-muted">
      <i class="fas fa-spinner fa-spin fa-2x"></i>
    </div>

    <!-- Vazio -->
    <div v-else-if="!orders.length" class="text-center py-5 text-muted">
      <i class="fas fa-box-open fa-2x mb-2 d-block"></i>Nenhum pedido encontrado.
    </div>

    <!-- Cards -->
    <div v-else>
      <div
        v-for="order in orders"
        :key="order.id"
        class="card mb-2 order-card"
        :class="isCancelled(order) ? 'border-left-danger' : (isDeliveryUrgent(order) ? 'border-left-warning' : 'border-left-light')"
        style="border-left-width:4px"
      >
        <div class="card-body p-2">
          <div class="d-flex align-items-start" style="gap:.75rem">

            <!-- Checkbox -->
            <div class="pt-1 flex-shrink-0">
              <input type="checkbox" :value="order.id" v-model="selectedOrders" style="width:16px;height:16px" />
            </div>

            <!-- ── Col COMPRADOR ── -->
            <div style="min-width:210px;max-width:220px;flex-shrink:0">
              <div class="d-flex align-items-center mb-1">
                <i class="fas fa-user-circle text-muted mr-1 fa-sm"></i>
                <strong style="font-size:.85rem" class="text-truncate" :title="order.buyer_name">{{ order.buyer_name || '—' }}</strong>
              </div>

              <!-- Link para ML -->
              <div class="mb-1" style="font-size:.75rem">
                <span class="text-muted">Venda: </span>
                <a
                  v-if="order.platform === 'mercadolivre' && order.platform_order_id"
                  :href="`https://www.mercadolivre.com.br/vendas/${order.platform_order_id}/detalhe`"
                  target="_blank"
                  rel="noopener"
                  class="badge badge-light border text-primary"
                  title="Ver venda no Mercado Livre"
                >
                  #{{ order.platform_order_id }}
                  <i class="fas fa-external-link-alt ml-1" style="font-size:.65rem"></i>
                </a>
                <span v-else class="badge badge-light border">#{{ order.platform_order_id }}</span>
                <i class="fas fa-copy ml-1 text-muted" style="cursor:pointer;font-size:.7rem" @click="copyText(order.platform_order_id)" title="Copiar"></i>
              </div>

              <div v-if="order.platform_order_ref && order.platform_order_ref !== order.platform_order_id" class="mb-1" style="font-size:.75rem">
                <span class="text-muted">Carrinho: </span>
                <span class="badge badge-light border">#{{ order.platform_order_ref }}</span>
                <i class="fas fa-copy ml-1 text-muted" style="cursor:pointer;font-size:.7rem" @click="copyText(order.platform_order_ref)" title="Copiar"></i>
              </div>

              <div v-if="addressZip(order)" class="mb-1" style="font-size:.75rem">
                <span class="text-muted">CEP: </span>{{ addressZip(order) }}
              </div>
              <div v-if="order.cmig" class="mb-1" style="font-size:.72rem">
                <span class="badge badge-light border text-secondary" :title="`CMIG: ${order.cmig.company_name || ''} — CNPJ: ${order.cmig.cnpj || ''}`">
                  <i class="fas fa-building mr-1"></i>{{ order.cmig.trade_name || order.cmig.company_name }}
                </span>
              </div>
              <div style="font-size:.75rem" class="text-muted">
                <i class="fas fa-calendar-alt mr-1"></i><span class="text-muted">Data venda: </span>{{ formatDateTime(order.created_at) }}
              </div>
            </div>

            <!-- ── Col PRODUTO ── -->
            <div class="flex-grow-1" style="min-width:0">
              <div
                v-for="(item, idx) in visibleItems(order)"
                :key="item.id"
                class="d-flex align-items-start mb-2"
                :class="{ 'border-top pt-2': idx > 0 }"
              >
                <!-- Thumbnail -->
                <div class="mr-2 flex-shrink-0" style="width:64px;height:64px">
                  <img
                    v-if="item.image_url"
                    :src="item.image_url"
                    width="64" height="64"
                    style="object-fit:cover;border-radius:4px;border:1px solid #dee2e6"
                    :alt="item.title"
                    @error="item.image_url = null"
                  />
                  <div
                    v-else
                    style="width:64px;height:64px;background:#f8f9fa;border:1px solid #dee2e6;border-radius:4px;display:flex;align-items:center;justify-content:center"
                  ><i class="fas fa-image text-muted"></i></div>
                </div>

                <!-- Info do item -->
                <div style="min-width:0;flex:1">
                  <!-- Título com badge qtd -->
                  <div class="d-flex align-items-start mb-1" style="gap:.25rem">
                    <span class="badge badge-warning text-dark font-weight-bold flex-shrink-0">{{ item.quantity }}x</span>
                    <span style="font-size:.82rem;line-height:1.3" :title="item.title">{{ item.title }}</span>
                    <button class="btn btn-link p-0 flex-shrink-0" @click="copyText(item.title)" style="font-size:.65rem;line-height:1"><i class="fas fa-copy text-muted"></i></button>
                  </div>

                  <!-- SKU + Badges de ícones -->
                  <div class="d-flex align-items-center flex-wrap mb-1" style="gap:.3rem">
                    <!-- SKU -->
                    <small class="text-muted" style="font-size:.72rem">SKU: {{ item.sku || '—' }}</small>
                    <button class="btn btn-link p-0" @click="copyText(item.sku)" style="font-size:.65rem" title="Copiar SKU">
                      <i class="fas fa-copy text-muted"></i>
                    </button>

                    <!-- Modalidade: Premium ou Clássico -->
                    <span v-if="isPremium(item.listing_type)" class="badge badge-warning text-dark" title="Anúncio Premium">
                      <i class="fas fa-trophy"></i> Premium
                    </span>
                    <span v-else-if="item.listing_type" class="badge badge-secondary" title="Anúncio Clássico">
                      <i class="fas fa-medal"></i> Clássico
                    </span>

                    <!-- FULL ou Galpão -->
                    <span v-if="item.is_full" class="badge badge-info" title="Estoque Full ML">
                      <i class="fas fa-bolt"></i> FULL
                    </span>
                    <span v-else class="badge badge-secondary" title="Estoque no Galpão">
                      <i class="fas fa-warehouse"></i> Galpão
                    </span>

                    <!-- Catálogo ou Normal -->
                    <span v-if="item.catalog_listing" class="badge badge-primary" title="Anúncio de Catálogo">
                      <i class="fas fa-book"></i> Catálogo
                    </span>

                    <!-- Frete -->
                    <span v-if="item.free_shipping" class="badge badge-success" title="Frete Grátis para o comprador">
                      <i class="fas fa-shipping-fast"></i> Grátis
                    </span>
                    <span v-else class="badge badge-light border text-muted" title="Frete pago pelo comprador">
                      <i class="fas fa-dollar-sign"></i> Frete pago
                    </span>

                    <!-- ID do anúncio ML com link -->
                    <template v-if="item.platform_item_id || item.ml_item_id">
                      <a
                        v-if="item.platform_item_id"
                        :href="`https://www.mercadolivre.com.br/metricas/${item.platform_item_id}/rendimiento-item?channel=ml_tabs#source=listing`"
                        target="_blank"
                        rel="noopener"
                        class="badge badge-light border text-muted"
                        style="font-size:.68rem"
                        title="Ver métricas do anúncio no ML"
                      >{{ item.platform_item_id }} <i class="fas fa-external-link-alt" style="font-size:.6rem"></i></a>
                      <span v-else class="badge badge-light border text-muted" style="font-size:.68rem">{{ item.ml_item_id }}</span>
                      <button class="btn btn-link p-0" @click="copyText(item.platform_item_id || item.ml_item_id)" style="font-size:.65rem" title="Copiar ID">
                        <i class="fas fa-copy text-muted"></i>
                      </button>
                    </template>
                  </div>

                  <!-- Preço + disponível + frete -->
                  <div class="d-flex align-items-center" style="gap:.5rem;font-size:.78rem">
                    <strong>{{ formatCurrency(item.unit_price) }}</strong>
                    <span v-if="item.available_quantity != null" class="text-muted">
                      | {{ item.available_quantity }} disponíveis após esta venda
                    </span>
                    <span class="text-muted">| {{ order.shipping_method || 'Mercado Envios' }}</span>
                  </div>
                </div>
              </div>

              <!-- Expandir múltiplos itens -->
              <div v-if="order.items.length > 1 && !expandedOrders.has(order.id)" style="font-size:.78rem">
                <button class="btn btn-link btn-sm p-0 text-muted" @click="expandOrder(order.id)">
                  <i class="fas fa-chevron-down mr-1"></i>+{{ order.items.length - 1 }} item(s)
                </button>
              </div>
            </div>

            <!-- ── Col FINANCEIRO ── -->
            <div style="flex-shrink:0">
              <OrderFinancialCard :order="order" />
            </div>

            <!-- ── Col STATUS / NF-e ── -->
            <div style="min-width:180px;flex-shrink:0;text-align:right">

              <!-- Cancelado -->
              <div v-if="isCancelled(order)" class="mb-1">
                <span class="badge badge-danger w-100 d-block" style="font-size:.82rem;padding:.35rem .5rem">
                  <i class="fas fa-ban mr-1"></i>CANCELADO
                </span>
              </div>

              <!-- Botão de Entrega — ícone/cor/label refletem o shipment_status do ML -->
              <button
                class="btn btn-sm btn-block mb-1"
                :class="deliveryBtnClass(order)"
                style="font-size:.78rem;white-space:nowrap"
                @click="openShipmentModal(order)"
                :title="`Ver detalhes da entrega — ${deliveryBtnLabel(order)}`"
              >
                <i :class="deliveryBtnIcon(order)" class="mr-1"></i>{{ deliveryBtnLabel(order) }}
              </button>

              <!-- NF-e -->
              <div class="d-flex" style="gap:.25rem">
                <!-- Autorizada com URL: abre DANFE direto em nova aba -->
                <a
                  v-if="order.nfe_status === 'authorized' && order.nfe_url"
                  :href="order.nfe_url"
                  target="_blank"
                  rel="noopener"
                  class="btn btn-sm btn-success flex-grow-1"
                  style="font-size:.78rem"
                  title="Abrir DANFE no Mercado Livre"
                >
                  <i class="fas fa-print mr-1"></i>Imprimir DANFE
                </a>
                <!-- Autorizada sem URL: abre modal de invoices para consultar -->
                <button
                  v-else-if="order.nfe_status === 'authorized'"
                  class="btn btn-sm btn-success flex-grow-1"
                  style="font-size:.78rem"
                  @click="openInvoicesModal(order)"
                  title="Consultar NF-e"
                >
                  <i class="fas fa-print mr-1"></i>Imprimir DANFE
                </button>
                <!-- Em processamento: aguardando Faturador ML -->
                <button
                  v-else-if="['pending','in_process'].includes(order.nfe_status)"
                  class="btn btn-sm btn-outline-info flex-grow-1"
                  style="font-size:.78rem"
                  disabled
                  title="NF-e em processamento pelo Faturador ML"
                >
                  <i class="fas fa-spinner fa-spin mr-1"></i>Processando NF-e…
                </button>
                <!-- ML sem NF-e: emitir -->
                <button
                  v-else-if="order.platform === 'mercadolivre'"
                  class="btn btn-sm btn-outline-warning flex-grow-1"
                  style="font-size:.78rem"
                  :disabled="nfeEmitting[order.id]"
                  @click="emitNfe(order)"
                  title="Emitir NF-e via Faturador ML"
                >
                  <i class="fas fa-file-invoice mr-1"></i>
                  {{ nfeEmitting[order.id] ? 'Emitindo…' : 'Emitir NF-e' }}
                </button>
                <!-- Outros canais -->
                <button v-else class="btn btn-sm btn-outline-secondary flex-grow-1" style="font-size:.78rem" disabled>
                  <i class="fas fa-file-invoice mr-1"></i>NF-e Pendente
                </button>
              </div>
            </div>
          </div>

          <!-- Stepper + Ações -->
          <div class="mt-2 border-top pt-2 d-flex align-items-center" style="gap:.4rem">
            <OrderStatusStepper
              :status="order.status"
              :order="order"
              :payment-status="order.payment_status"
              :label-url="order.label_url || ''"
              :can-pay="canPay && !isCancelled(order)"
              @click:delivery="openShipmentModal(order)"
              @click:pay="payOrder(order)"
              @click:label="openLabel(order)"
            />

            <!-- Ícone redondo: Imprimir Etiqueta — não disponível para Full (ML gerencia logística) -->
            <div
              v-if="order.platform === 'mercadolivre' && order.shipment_id && !isFullOrder(order)"
              class="step-circle invoice-circle"
              :class="labelCircleClass(order)"
              :title="labelCircleTooltip(order)"
              style="cursor:pointer"
              @click="printShippingLabel(order)"
            >
              <i class="fas fa-tag" :class="{ 'fa-spin': labelLoading[order.id] }"></i>
            </div>

            <!-- Ícone redondo: Consultar NF-e -->
            <div
              v-if="order.platform === 'mercadolivre'"
              class="step-circle invoice-circle"
              :class="invoiceCircleClass(order)"
              :title="invoiceCircleTooltip(order)"
              style="cursor:pointer"
              @click="openInvoicesModal(order)"
            >
              <i class="fas fa-file-invoice-dollar"></i>
            </div>

            <!-- Atualizar status (UGO/Admin) — botões inline -->
            <template v-if="canUpdateStatus">
              <button v-if="['paid','label_generated'].includes(order.status)" class="btn btn-xs btn-outline-warning" @click="updateStatus(order,'label_printed')" title="Etiqueta Impressa"><i class="fas fa-print"></i></button>
              <button v-if="order.status==='label_printed'" class="btn btn-xs btn-outline-info" @click="updateStatus(order,'separated')" title="Pedido Separado"><i class="fas fa-box-open"></i></button>
              <button v-if="order.status==='separated'" class="btn btn-xs btn-outline-success" @click="updateStatus(order,'shipped')" title="Coletado p/ Entrega"><i class="fas fa-truck"></i></button>
            </template>

            <!-- Nota interna (lado direito, antes do menu) -->
            <div class="position-relative ml-auto">
              <button
                class="btn btn-xs btn-outline-secondary"
                :class="order.notes ? 'text-warning' : ''"
                title="Nota interna"
                @click="toggleNote(order)"
              ><i class="fas fa-sticky-note"></i></button>
              <div
                v-if="noteOpen === order.id"
                class="position-absolute bg-white border rounded shadow p-2"
                style="z-index:200;min-width:220px;bottom:28px;right:0"
              >
                <textarea v-model="noteText" class="form-control form-control-sm mb-1" rows="3" placeholder="Nota interna..."></textarea>
                <div class="d-flex" style="gap:.25rem">
                  <button class="btn btn-xs btn-primary" @click="saveNote(order)"><i class="fas fa-check"></i></button>
                  <button class="btn btn-xs btn-default" @click="noteOpen=null"><i class="fas fa-times"></i></button>
                </div>
              </div>
            </div>

            <!-- Menu de ações -->
            <div class="dropdown">
              <button class="btn btn-xs btn-outline-secondary dropdown-toggle" data-bs-toggle="dropdown">
                <i class="fas fa-ellipsis-v"></i>
              </button>
              <div class="dropdown-menu dropdown-menu-right">
                <RouterLink :to="`/orders/${order.id}`" class="dropdown-item"><i class="fas fa-eye mr-2"></i>Ver detalhes</RouterLink>
                <div class="dropdown-divider"></div>
                <a class="dropdown-item text-danger" href="#" @click.prevent="hideOrder(order)"><i class="fas fa-eye-slash mr-2"></i>Ocultar pedido</a>
                <a v-if="canDelete" class="dropdown-item text-danger" href="#" @click.prevent="deleteOrder(order)">
                  <i class="fas fa-trash mr-2"></i>Excluir pedido
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Modais -->
    <DeliveryModal :show="showDeliveryModal" :order="selectedOrder" @close="showDeliveryModal = false" />
    <InvoicesModal :show="showInvoicesModal" :order="invoicesOrder" @close="showInvoicesModal = false" />
    <ShipmentModal :show="showShipmentModal" :order="shipmentOrder" @close="showShipmentModal = false" />

    <!-- Modal Sincronizar Período -->
    <div v-if="showSyncRangeModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5);z-index:1060">
      <div class="modal-dialog modal-sm">
        <div class="modal-content">
          <div class="modal-header py-2">
            <h6 class="modal-title"><i class="fas fa-calendar-alt mr-2"></i>Sincronizar Período</h6>
            <button type="button" class="close" @click="closeSyncRangeModal"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="form-group mb-2">
              <label class="small font-weight-bold">Data início</label>
              <input type="date" v-model="syncRange.date_from" class="form-control form-control-sm" />
            </div>
            <div class="form-group mb-2">
              <label class="small font-weight-bold">Data fim</label>
              <input type="date" v-model="syncRange.date_to" class="form-control form-control-sm" />
            </div>
            <div class="form-group mb-0">
              <label class="small font-weight-bold">Plataforma</label>
              <select v-model="syncRange.platform" class="form-control form-control-sm">
                <option value="all">Todos (ML + Shopee)</option>
                <option value="mercadolivre">Mercado Livre</option>
                <option value="shopee">Shopee</option>
              </select>
            </div>
            <div v-if="syncRangeResult" class="mt-2 alert alert-sm" :class="syncRangeResult.error ? 'alert-danger' : 'alert-success'" style="font-size:.82rem;padding:.4rem .7rem">
              <i :class="syncRangeResult.error ? 'fas fa-exclamation-circle' : 'fas fa-check-circle'" class="mr-1"></i>
              {{ syncRangeResult.message }}
            </div>
          </div>
          <div class="modal-footer py-2">
            <button class="btn btn-sm btn-secondary" @click="closeSyncRangeModal">Fechar</button>
            <button class="btn btn-sm btn-primary" @click="runSyncRange" :disabled="syncingRange || !syncRange.date_from">
              <i class="fas fa-cloud-download-alt mr-1" :class="{ 'fa-spin': syncingRange }"></i>
              {{ syncingRange ? 'Sincronizando...' : 'Sincronizar' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <ConfirmModal
    :show="confirmModal.show"
    :title="confirmModal.title"
    :message="confirmModal.message"
    :confirm-label="confirmModal.confirmLabel"
    :confirm-class="confirmModal.confirmClass"
    @confirm="onConfirmOk"
    @cancel="onConfirmCancel"
  />
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import api from '@/composables/useApi'
import { formatCurrency, formatDateTime, formatDate } from '@/utils/formatters'
import { ORDER_STATUSES, PLATFORMS } from '@/utils/constants'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import OrderStatusStepper from '@/components/orders/OrderStatusStepper.vue'
import OrderFinancialCard from '@/components/orders/OrderFinancialCard.vue'
import DeliveryModal from '@/components/orders/DeliveryModal.vue'
import InvoicesModal from '@/components/orders/InvoicesModal.vue'
import ShipmentModal from '@/components/orders/ShipmentModal.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'

const route = useRoute()
const toast = useToast()
const authStore = useAuthStore()

// Modal de confirmação reutilizável
const confirmModal = reactive({
  show: false,
  title: '',
  message: '',
  confirmLabel: 'Confirmar',
  confirmClass: 'btn-danger',
  _resolve: null,
})
function showConfirm(title, message, options = {}) {
  return new Promise((resolve) => {
    confirmModal.title = title
    confirmModal.message = message
    confirmModal.confirmLabel = options.confirmLabel || 'Confirmar'
    confirmModal.confirmClass = options.confirmClass || 'btn-danger'
    confirmModal.show = true
    confirmModal._resolve = resolve
  })
}
function onConfirmOk() { confirmModal.show = false; confirmModal._resolve?.(true) }
function onConfirmCancel() { confirmModal.show = false; confirmModal._resolve?.(false) }

const orders = ref([])
const total = ref(0)
const loading = ref(false)
const syncing = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const selectedOrders = ref([])
const expandedOrders = ref(new Set())
const noteOpen = ref(null)
const noteText = ref('')
const selectedOrder = ref(null)
const showDeliveryModal = ref(false)
const showSyncRangeModal = ref(false)
const syncingRange = ref(false)
const syncRangeResult = ref(null)
const syncRange = ref({ date_from: '', date_to: '', platform: 'all' })
const nfeEmitting = ref({})
const showInvoicesModal = ref(false)
const invoicesOrder = ref(null)
const showShipmentModal = ref(false)
const shipmentOrder = ref(null)

const filters = reactive({
  search: route.query.search || '',
  status: route.query.status || '',
  platform: route.query.platform || '',
  payment_status: route.query.payment_status || '',
  shipment_status: '',
  tag: '',
  cmig_id: route.query.cmig_id || '',
})

const availableCmigs = ref([])

async function loadAvailableCmigs() {
  try {
    const { data } = await api.get('/orders/cmigs/available')
    availableCmigs.value = data.items || []
  } catch {
    availableCmigs.value = []
  }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const allSelected = computed(() =>
  orders.value.length > 0 && orders.value.every(o => selectedOrders.value.includes(o.id))
)
const userRole = computed(() => authStore.user?.role || '')
const canPay = computed(() => ['ac', 'admin'].includes(userRole.value))
const canUpdateStatus = computed(() => ['ugo', 'admin'].includes(userRole.value))
const canDelete = computed(() => ['ac', 'ugo', 'admin'].includes(userRole.value))
const visiblePages = computed(() => {
  const start = Math.max(1, currentPage.value - 2)
  const end = Math.min(totalPages.value, start + 4)
  const pages = []
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isCancelled(order) {
  return order.status === 'cancelled' || order.platform_status === 'cancelled'
}

function statusLabel(key) { return ORDER_STATUSES.find(s => s.key === key)?.label || key }

function statusBtnClass(key) {
  const map = {
    downloaded: 'btn-secondary', paid: 'btn-info',
    label_generated: 'btn-primary', label_printed: 'btn-warning',
    separated: 'btn-dark', shipped: 'btn-warning text-dark',
    delivered: 'btn-success', cancelled: 'btn-danger', returned: 'btn-danger',
  }
  return map[key] || 'btn-secondary'
}

function statusIcon(key) {
  const map = {
    downloaded: 'fas fa-download', paid: 'fas fa-dollar-sign',
    label_generated: 'fas fa-tag', label_printed: 'fas fa-print',
    separated: 'fas fa-box-open', shipped: 'fas fa-truck',
    delivered: 'fas fa-check-circle', cancelled: 'fas fa-times-circle',
    returned: 'fas fa-undo',
  }
  return map[key] || 'fas fa-circle'
}

function isPremium(listingType) {
  return ['gold_special', 'gold_pro'].includes(listingType)
}

const SHIPMENT_STATUS_MAP = {
  pending:        { label: 'Aguardando',         icon: 'fas fa-clock',         badge: 'badge-secondary' },
  handling:       { label: 'Em Preparação',       icon: 'fas fa-box-open',      badge: 'badge-warning text-dark' },
  ready_to_ship:  { label: 'Pronto p/ Envio',     icon: 'fas fa-dolly',         badge: 'badge-info' },
  shipped:        { label: 'A caminho',           icon: 'fas fa-shipping-fast', badge: 'badge-primary' },
  delivered:      { label: 'Entregue',            icon: 'fas fa-check-circle',  badge: 'badge-success' },
  not_delivered:  { label: 'Não Entregue',        icon: 'fas fa-exclamation-triangle', badge: 'badge-danger' },
  cancelled:      { label: 'Cancelado',           icon: 'fas fa-times-circle',  badge: 'badge-dark' },
}
function shipmentStatusLabel(s)  { return SHIPMENT_STATUS_MAP[s]?.label || s }
function shipmentStatusIcon(s)   { return SHIPMENT_STATUS_MAP[s]?.icon  || 'fas fa-circle' }
function shipmentStatusBadge(s)  { return SHIPMENT_STATUS_MAP[s]?.badge || 'badge-secondary' }

// ─── Botão de Entrega: prioriza shipment_status do ML, fallback para order.status ─
const SHIPMENT_BTN_CLASS = {
  pending:        'btn-secondary',
  handling:       'btn-warning text-dark',
  ready_to_ship:  'btn-info',
  shipped:        'btn-primary',
  delivered:      'btn-success',
  not_delivered:  'btn-danger',
  cancelled:      'btn-dark',
}
function deliveryBtnIcon(order) {
  if (isCancelled(order)) return 'fas fa-times-circle'
  if (order.shipment_status) return shipmentStatusIcon(order.shipment_status)
  return statusIcon(order.status)
}
function deliveryBtnLabel(order) {
  if (isCancelled(order)) return 'Cancelado'
  if (order.shipment_status) return shipmentStatusLabel(order.shipment_status)
  return statusLabel(order.status)
}
function deliveryBtnClass(order) {
  if (isCancelled(order)) return 'btn-danger'
  if (order.shipment_status && SHIPMENT_BTN_CLASS[order.shipment_status]) {
    return SHIPMENT_BTN_CLASS[order.shipment_status]
  }
  return statusBtnClass(order.status)
}

// ─── Ícone redondo de Etiqueta de Envio ─────────────────────────────────────
const labelLoading = ref({})
const LABEL_READY_STATES = ['handling', 'ready_to_ship', 'shipped', 'delivered', 'not_delivered']

function isFullOrder(order) {
  // Full (Fulfillment) shipments are managed by ML — seller doesn't print labels
  return (order.shipping_method || '').includes('fulfillment')
}
function labelAvailable(order) {
  return !isFullOrder(order) && LABEL_READY_STATES.includes(order.shipment_status)
}
function labelCircleClass(order) {
  const s = order.shipment_status
  // Pedido Full — etiqueta gerenciada pelo ML, sem ação para o vendedor
  if (isFullOrder(order)) return 'bg-light text-muted border'
  // Já tem cache local: indicador verde-escuro com check
  if (order.label_cached_at) return 'bg-success text-white'
  if (s === 'shipped' || s === 'delivered') return 'bg-success text-white'
  if (s === 'ready_to_ship') return 'bg-info text-white'
  if (s === 'handling') return 'bg-warning text-dark'
  if (s === 'pending') return 'bg-light text-muted border'
  if (s === 'cancelled' || s === 'not_delivered') return 'bg-secondary text-muted'
  return 'bg-secondary text-white'
}
function labelCircleTooltip(order) {
  const s = order.shipment_status
  if (isFullOrder(order)) return 'Pedido Full — etiqueta gerenciada pelo Mercado Livre'
  if (s === 'cancelled') return 'Envio cancelado — etiqueta indisponível'
  if (s === 'pending' || !s) return 'Aguardando aprovação do pagamento — etiqueta ainda não disponível'
  if (!order.shipment_id) return 'Sem envio'
  if (order.label_cached_at) return 'Etiqueta salva — clique para imprimir'
  return 'Imprimir Etiqueta de Envio'
}
async function printShippingLabel(order) {
  if (!order.shipment_id) {
    toast.warning('Pedido sem envio')
    return
  }
  if (!labelAvailable(order)) {
    toast.warning(labelCircleTooltip(order))
    return
  }
  labelLoading.value[order.id] = true
  try {
    const { data } = await api.get(`/orders/${order.id}/label`, { responseType: 'blob' })
    const blobUrl = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
    window.open(blobUrl, '_blank')
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000)
    // Marca cache na lista local para o ícone ficar verde sem reload
    if (!order.label_cached_at) order.label_cached_at = new Date().toISOString()
  } catch (err) {
    let msg = 'Erro ao gerar etiqueta'
    // axios with responseType:blob returns the error as a Blob — need to parse
    if (err.response?.data instanceof Blob) {
      try {
        const txt = await err.response.data.text()
        const json = JSON.parse(txt)
        msg = json.detail || msg
      } catch { /* keep default */ }
    } else if (err.response?.data?.detail) {
      msg = err.response.data.detail
    }
    if (typeof msg === 'string' && msg.includes('NF-e')) {
      // Aviso acionável (NF-e sendo emitida), não é um erro
      toast.warning(msg)
    } else {
      toast.error(typeof msg === 'string' ? msg : 'Erro ao gerar etiqueta')
    }
  } finally {
    labelLoading.value[order.id] = false
  }
}

// ─── Ícone redondo de Notas Fiscais ─────────────────────────────────────────
function invoiceCircleClass(order) {
  const s = order.nfe_status
  if (s === 'authorized') return 'bg-success text-white'
  if (s === 'pending' || s === 'in_process') return 'bg-warning text-dark'
  if (s === 'rejected' || s === 'error') return 'bg-danger text-white'
  return 'bg-secondary text-white'
}
function invoiceCircleTooltip(order) {
  const s = order.nfe_status
  if (s === 'authorized') return 'NF-e autorizada — clique para consultar'
  if (s === 'pending' || s === 'in_process') return 'NF-e em processamento — clique para consultar'
  if (s === 'rejected' || s === 'error') return 'Erro na NF-e — clique para consultar'
  return 'Consultar Notas Fiscais'
}

const LOGISTIC_MAP = {
  fulfillment:   { label: 'Full',         icon: 'fas fa-warehouse',     badge: 'badge-info' },
  cross_docking: { label: 'ME2',          icon: 'fas fa-shipping-fast', badge: 'badge-primary' },
  xd_drop_off:   { label: 'ME2 Agência',  icon: 'fas fa-shipping-fast', badge: 'badge-primary' },
  self_service:  { label: 'Flex',         icon: 'fas fa-bolt',          badge: 'badge-warning text-dark' },
  me1:           { label: 'ME1',          icon: 'fas fa-truck',         badge: 'badge-secondary' },
}
function _logistic(method) {
  if (!method) return null
  const key = Object.keys(LOGISTIC_MAP).find(k => method.includes(k))
  return LOGISTIC_MAP[key] || null
}
function logisticLabel(method) { return _logistic(method)?.label || null }
function logisticIcon(method)  { return _logistic(method)?.icon  || 'fas fa-question-circle' }
function logisticBadge(method) { return _logistic(method)?.badge || 'badge-secondary' }

function hasTag(order, tag) { return (order.order_tags || '').includes(tag) }
function hasFraudRisk(order) { return hasTag(order, 'fraud_risk_detected') }
function isHandlingUrgent(order) {
  if (!order.estimated_handling_limit) return false
  return (new Date(order.estimated_handling_limit) - new Date()) / 86400000 < 1
}

function addressZip(order) {
  const a = order.shipping_address || {}
  const z = a.zip_code || a.zipcode || a.cep || ''
  const d = String(z).replace(/\D/g, '')
  return d.length === 8 ? `${d.slice(0, 5)}-${d.slice(5)}` : z
}

function isDeliveryUrgent(order) {
  if (!order.estimated_delivery_date) return false
  return (new Date(order.estimated_delivery_date) - new Date()) / 86400000 <= 2
}

function visibleItems(order) {
  return expandedOrders.value.has(order.id) ? order.items : order.items.slice(0, 1)
}
function expandOrder(id) {
  expandedOrders.value = new Set([...expandedOrders.value, id])
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(String(text)); toast.success('Copiado!') }
  catch { toast.error('Não foi possível copiar') }
}

// ─── API ─────────────────────────────────────────────────────────────────────

async function loadOrders() {
  loading.value = true
  try {
    const params = { page: currentPage.value, page_size: pageSize.value }
    if (filters.search) params.search = filters.search
    if (filters.status) params.status = filters.status
    if (filters.platform) params.platform = filters.platform
    if (filters.payment_status) params.payment_status = filters.payment_status
    if (filters.shipment_status) params.shipment_status = filters.shipment_status
    if (filters.tag) params.tag = filters.tag
    if (filters.cmig_id) params.cmig_id = filters.cmig_id
    const { data } = await api.get('/orders', { params })
    orders.value = data.items
    total.value = data.total
    selectedOrders.value = []
  } catch { toast.error('Erro ao carregar pedidos') }
  finally { loading.value = false }
}

function resetAndLoad() { currentPage.value = 1; loadOrders() }
function onPageSizeChange() { currentPage.value = 1; loadOrders() }
function prevPage() { if (currentPage.value > 1) { currentPage.value--; loadOrders() } }
function nextPage() { if (currentPage.value < totalPages.value) { currentPage.value++; loadOrders() } }
function goPage(p) { currentPage.value = p; loadOrders() }
function toggleSelectAll() {
  selectedOrders.value = allSelected.value ? [] : orders.value.map(o => o.id)
}

async function payOrder(order) {
  if (!confirm(`Pagar pedido #${order.id}? O valor será debitado do seu saldo.`)) return
  try {
    const { data } = await api.post(`/orders/${order.id}/pay`)
    toast.success(`Pedido pago! Débito: ${formatCurrency(data.total_debit)}`)
    await loadOrders()
  } catch (err) { toast.error(err.response?.data?.detail || 'Erro ao pagar pedido') }
}

async function updateStatus(order, status) {
  try {
    await api.put(`/orders/${order.id}/status`, { status })
    order.status = status
    toast.success('Status atualizado')
  } catch (err) { toast.error(err.response?.data?.detail || 'Erro ao atualizar status') }
}

async function hideOrder(order) {
  const ok = await showConfirm('Ocultar pedido', 'Ocultar este pedido?', { confirmLabel: 'Ocultar', confirmClass: 'btn-warning' })
  if (!ok) return
  try {
    await api.post(`/orders/${order.id}/hide`)
    orders.value = orders.value.filter(o => o.id !== order.id)
    toast.success('Pedido ocultado')
  } catch { toast.error('Erro ao ocultar pedido') }
}

async function deleteOrder(order) {
  const ok = await showConfirm(
    'Excluir pedido',
    `Excluir pedido #${order.platform_order_id || order.id}?\n\nO pedido será removido do sistema e poderá ser re-baixado na próxima sincronização.\nEsta ação não pode ser desfeita.`
  )
  if (!ok) return
  try {
    await api.delete(`/orders/${order.id}`)
    orders.value = orders.value.filter(o => o.id !== order.id)
    selectedOrders.value = selectedOrders.value.filter(id => id !== order.id)
    toast.success('Pedido excluído. Será re-baixado na próxima sincronização.')
  } catch (err) { toast.error(err.response?.data?.detail || 'Erro ao excluir pedido') }
}

async function bulkDelete() {
  if (!selectedOrders.value.length) return
  const ok = await showConfirm(
    'Excluir pedidos',
    `Excluir ${selectedOrders.value.length} pedido(s) selecionado(s)?\n\nEles serão removidos do sistema e poderão ser re-baixados na próxima sincronização.`
  )
  if (!ok) return
  try {
    const { data } = await api.post('/orders/bulk-delete', { ids: selectedOrders.value })
    orders.value = orders.value.filter(o => !data.deleted.includes(o.id))
    selectedOrders.value = []
    toast.success(`${data.count} pedido(s) excluído(s)`)
  } catch (err) { toast.error(err.response?.data?.detail || 'Erro ao excluir pedidos') }
}

function toggleNote(order) {
  noteOpen.value = noteOpen.value === order.id ? null : order.id
  if (noteOpen.value === order.id) noteText.value = order.notes || ''
}

async function saveNote(order) {
  try {
    await api.put(`/orders/${order.id}/notes`, { notes: noteText.value })
    order.notes = noteText.value
    noteOpen.value = null
    toast.success('Nota salva')
  } catch { toast.error('Erro ao salvar nota') }
}

function openLabel(order) {
  if (order.label_url) window.open(order.label_url, '_blank')
}

function printLabel(order) {
  if (order.label_url) window.open(order.label_url, '_blank')
}

function printSelected() {
  const withLabel = orders.value.filter(o => selectedOrders.value.includes(o.id) && o.label_url)
  if (!withLabel.length) { toast.warning('Nenhum selecionado tem etiqueta'); return }
  withLabel.forEach(o => window.open(o.label_url, '_blank'))
}

function viewSelectedLabels() { printSelected() }

async function bulkStatus(status) {
  if (!selectedOrders.value.length) { toast.warning('Selecione ao menos um pedido'); return }
  const ids = selectedOrders.value.slice()
  try {
    await Promise.all(ids.map(id => api.put(`/orders/${id}/status`, { status })))
    await loadOrders()
    toast.success(`${ids.length} pedido(s) atualizados`)
  } catch { toast.error('Erro ao atualizar pedidos') }
}

async function bulkHide() {
  if (!selectedOrders.value.length) { toast.warning('Selecione ao menos um pedido'); return }
  if (!confirm(`Ocultar ${selectedOrders.value.length} pedido(s)?`)) return
  const ids = selectedOrders.value.slice()
  try {
    await Promise.all(ids.map(id => api.post(`/orders/${id}/hide`)))
    await loadOrders()
    toast.success(`${ids.length} pedido(s) ocultados`)
  } catch { toast.error('Erro ao ocultar pedidos') }
}

async function syncOrders() {
  syncing.value = true
  try {
    const { data } = await api.post('/orders/sync')
    const parts = [`${data.imported} novo(s) pedido(s) importado(s)`]
    if (data.nfe_updated > 0) parts.push(`${data.nfe_updated} NF-e(s) atualizada(s)`)
    if (data.ship_updated > 0) parts.push(`${data.ship_updated} envio(s) atualizado(s)`)
    if (data.dates_fixed > 0) parts.push(`${data.dates_fixed} data(s) corrigida(s)`)
    toast.success(`Sincronização concluída — ${parts.join(' · ')}`)
    await loadOrders()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao sincronizar pedidos')
  } finally {
    syncing.value = false
  }
}

function closeSyncRangeModal() {
  showSyncRangeModal.value = false
  syncRangeResult.value = null
}

async function runSyncRange() {
  if (!syncRange.value.date_from) { toast.warning('Informe a data de início'); return }
  syncingRange.value = true
  syncRangeResult.value = null
  try {
    const { data } = await api.post('/orders/sync-range', {
      date_from: syncRange.value.date_from,
      date_to: syncRange.value.date_to || null,
      platform: syncRange.value.platform,
    })
    const parts = [`${data.imported} novo(s) pedido(s) importado(s)`]
    if (data.nfe_updated > 0) parts.push(`${data.nfe_updated} NF-e(s) atualizada(s)`)
    if (data.dates_fixed > 0) parts.push(`${data.dates_fixed} data(s) corrigida(s)`)
    if (data.ship_updated > 0) parts.push(`${data.ship_updated} envio(s) atualizado(s)`)
    syncRangeResult.value = {
      error: false,
      message: parts.join(' · '),
    }
    await loadOrders()
  } catch (err) {
    syncRangeResult.value = {
      error: true,
      message: err.response?.data?.detail || 'Erro ao sincronizar período',
    }
  } finally {
    syncingRange.value = false
  }
}

async function emitNfe(order) {
  nfeEmitting.value[order.id] = true
  try {
    const { data } = await api.post(`/orders/${order.id}/emit-nfe`)
    order.nfe_status = data.nfe_status
    order.nfe_key = data.nfe_key
    order.nfe_url = data.nfe_url
    toast.success('NF-e emitida com sucesso!')
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao emitir NF-e')
  } finally {
    nfeEmitting.value[order.id] = false
  }
}


function openDeliveryModal(order) { selectedOrder.value = order; showDeliveryModal.value = true }
function openInvoicesModal(order) { invoicesOrder.value = order; showInvoicesModal.value = true }
function openShipmentModal(order) { shipmentOrder.value = order; showShipmentModal.value = true }

async function _getOrderInvoices(orderId) {
  try {
    const { data } = await api.get(`/orders/${orderId}/invoices`)
    return data.invoices || []
  } catch { return [] }
}

async function _downloadBlob(url, filename, type) {
  const { data } = await api.get(url, { responseType: 'blob' })
  const blobUrl = URL.createObjectURL(new Blob([data], { type }))
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  a.click()
  URL.revokeObjectURL(blobUrl)
}

async function _openBlobPdf(url) {
  const { data } = await api.get(url, { responseType: 'blob' })
  const blobUrl = URL.createObjectURL(new Blob([data], { type: 'application/pdf' }))
  window.open(blobUrl, '_blank')
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60000)
}

async function bulkDownloadXml() {
  if (!selectedOrders.value.length) { toast.warning('Selecione ao menos um pedido'); return }
  const mlOrders = orders.value.filter(
    o => selectedOrders.value.includes(o.id) && o.platform === 'mercadolivre'
  )
  if (!mlOrders.length) { toast.warning('Nenhum pedido do Mercado Livre selecionado'); return }

  toast.info(`Baixando XMLs de ${mlOrders.length} pedido(s)…`)
  let downloaded = 0
  for (const order of mlOrders) {
    const invoices = await _getOrderInvoices(order.id)
    const saleInvoices = invoices.filter(inv => inv.xml_location)
    for (const inv of saleInvoices) {
      try {
        await _downloadBlob(
          `/orders/${order.id}/invoices/${inv.id}/xml`,
          `NFe_${inv.invoice_number || inv.id}.xml`,
          'application/xml',
        )
        downloaded++
      } catch { /* continua */ }
      await new Promise(r => setTimeout(r, 300))
    }
  }
  if (downloaded) toast.success(`${downloaded} XML(s) baixado(s)`)
  else toast.warning('Nenhum XML disponível para os pedidos selecionados')
}

async function bulkPrintDanfe() {
  if (!selectedOrders.value.length) { toast.warning('Selecione ao menos um pedido'); return }
  const mlOrders = orders.value.filter(
    o => selectedOrders.value.includes(o.id) && o.platform === 'mercadolivre'
  )
  if (!mlOrders.length) { toast.warning('Nenhum pedido do Mercado Livre selecionado'); return }

  toast.info(`Abrindo DANFEs de ${mlOrders.length} pedido(s)…`)
  let opened = 0
  for (const order of mlOrders) {
    const invoices = await _getOrderInvoices(order.id)
    // Apenas NF-e de venda com DANFE disponível
    const saleInvoice = invoices.find(inv => inv.danfe_location && inv.transaction_type === 'sale')
    if (saleInvoice) {
      try {
        await _openBlobPdf(`/orders/${order.id}/invoices/${saleInvoice.id}/danfe`)
        opened++
      } catch { /* continua */ }
      await new Promise(r => setTimeout(r, 400))
    }
  }
  if (opened) toast.success(`${opened} DANFE(s) aberta(s) — use Ctrl+P para imprimir`)
  else toast.warning('Nenhuma DANFE disponível para os pedidos selecionados')
}

onMounted(() => {
  loadAvailableCmigs()
  loadOrders()
})
</script>

<style scoped>
.order-card { transition: box-shadow .15s; }
.order-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.12); }
.btn-xs { padding: .15rem .4rem; font-size: .72rem; line-height: 1.4; border-radius: .2rem; }
.border-left-warning { border-left: 4px solid #ffc107 !important; }
.border-left-light { border-left: 4px solid #dee2e6 !important; }
.step-circle {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}
.invoice-circle:hover {
  filter: brightness(1.15);
  transform: scale(1.1);
  transition: transform .15s;
}
</style>
