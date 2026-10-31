<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0"><i class="fas fa-dolly mr-2 text-primary"></i>Separação — Pedidos não-FULL</h5>
      <RouterLink to="/separacao/gaiolas" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-shipping-fast mr-1"></i> Gaiolas / Transportadora
      </RouterLink>
    </div>

    <!-- ══ Pedidos pendentes ══════════════════════════════════════════════ -->
    <div class="card">
      <div class="card-header d-flex flex-wrap align-items-center">
        <strong class="mr-3">Pedidos a separar</strong>
        <div class="input-group input-group-sm mr-2" style="max-width:200px">
          <input v-model="search" class="form-control" placeholder="Buscar cliente..." />
          <div class="input-group-append"><span class="input-group-text"><i class="fas fa-search"></i></span></div>
        </div>
        <select v-model="filterShipment" class="form-control form-control-sm mr-2" style="max-width:150px">
          <option value="">Todos os status</option>
          <option v-for="s in shipmentOptions" :key="s" :value="s">{{ shipmentLabel(s) }}</option>
        </select>
        <select v-model="filterPlatform" class="form-control form-control-sm mr-2" style="max-width:140px">
          <option value="">Marketplaces</option>
          <option v-for="p in platformOptions" :key="p" :value="p">{{ platformLabel(p) }}</option>
        </select>
        <select v-if="cmigOptions.length > 1" v-model="filterCmig" class="form-control form-control-sm mr-2" style="max-width:160px">
          <option value="">Todas as CMIGs</option>
          <option v-for="c in cmigOptions" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <select v-model="filterNfe" class="form-control form-control-sm mr-2" style="max-width:130px">
          <option value="">NF-e (todas)</option>
          <option value="emitida">Com NF-e</option>
          <option value="pendente">Sem NF-e</option>
        </select>
        <input v-model="filterProduct" class="form-control form-control-sm mr-2" style="max-width:160px" placeholder="Produto (SKU/nome)" />
        <select v-model="filterItems" class="form-control form-control-sm mr-2" style="max-width:120px" title="Quantidade de itens do pedido">
          <option value="">Qtd itens</option>
          <option value="1">1 item</option>
          <option value="2">2 itens</option>
          <option value="3">3+ itens</option>
        </select>
        <button v-if="hasFilters" class="btn btn-sm btn-link text-muted px-1 mr-2" @click="clearFilters" title="Limpar filtros">
          <i class="fas fa-times"></i>
        </button>
        <div class="ml-auto d-flex">
          <button class="btn btn-sm btn-outline-info mr-2" :disabled="!selected.size" @click="printList">
            <i class="fas fa-print mr-1"></i> Imprimir Lista ({{ selected.size }})
          </button>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-success dropdown-toggle" data-bs-toggle="dropdown" :disabled="!selected.size">
              <i class="fas fa-plus mr-1"></i> Nova Gaiola
            </button>
            <div class="dropdown-menu dropdown-menu-right">
              <a class="dropdown-item" href="#" @click.prevent="newCart('manual')"><i class="fas fa-hand-paper mr-1"></i> Modo Manual</a>
              <a class="dropdown-item" href="#" @click.prevent="newCart('scan')"><i class="fas fa-barcode mr-1"></i> Modo Bipagem</a>
              <a class="dropdown-item" href="#" @click.prevent="newCart('scan_auto')"><i class="fas fa-bolt mr-1"></i> Bipagem automática</a>
            </div>
          </div>
        </div>
      </div>
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>
        <table v-else class="table table-hover table-sm mb-0 align-middle">
          <thead class="thead-light">
            <tr>
              <th style="width:34px"><input type="checkbox" :checked="allChecked" @change="toggleAll" /></th>
              <th class="sortable" @click="setSort('id')">Pedido <i :class="sortIcon('id')"></i></th>
              <th class="sortable" @click="setSort('platform')">MKT <i :class="sortIcon('platform')"></i></th>
              <th class="sortable" @click="setSort('cmig')">Conta CMIG <i :class="sortIcon('cmig')"></i></th>
              <th class="sortable" @click="setSort('shipment')">Envio <i :class="sortIcon('shipment')"></i></th>
              <th>Modo</th>
              <th class="sortable" @click="setSort('nfe')">NF-e <i :class="sortIcon('nfe')"></i></th>
              <th class="sortable" @click="setSort('sale')">Venda (Mkt) <i :class="sortIcon('sale')"></i></th>
              <th class="sortable" @click="setSort('delivery')">Prev. Entrega <i :class="sortIcon('delivery')"></i></th>
              <th class="sortable" @click="setSort('buyer')">Cliente <i :class="sortIcon('buyer')"></i></th>
              <th>Itens</th>
              <th class="text-right">Ação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!displayedOrders.length">
              <td colspan="12" class="text-center text-muted py-4">
                {{ pending.length ? 'Nenhum pedido com os filtros atuais.' : 'Nenhum pedido pendente de separação.' }}
              </td>
            </tr>
            <tr v-for="o in displayedOrders" :key="o.id"
                :class="{ 'text-muted': !selectable(o) }"
                :style="selectable(o) ? 'cursor:pointer' : ''"
                @click="selectable(o) && toggle(o.id)">
              <td @click.stop>
                <input type="checkbox" :checked="selected.has(o.id)" :disabled="!selectable(o)"
                       :title="selectable(o) ? '' : 'ML: só pedidos Prontos p/ Envio podem ir para a gaiola'"
                       @change="toggle(o.id)" />
              </td>
              <td class="font-weight-bold">
                #{{ o.id }}
                <span v-if="o.payment_status && o.payment_status !== 'paid'" class="badge badge-warning ml-1" title="Pagamento não confirmado">
                  <i class="fas fa-exclamation-triangle"></i>
                </span>
              </td>
              <td>
                <img v-if="platformLogo(o.platform)" :src="platformLogo(o.platform).src"
                     :alt="platformLogo(o.platform).label" :title="platformLogo(o.platform).label"
                     style="height:18px;max-width:70px;object-fit:contain" />
                <span v-else class="badge badge-light text-capitalize">{{ o.platform || '—' }}</span>
              </td>
              <td class="text-truncate" style="max-width:150px" :title="o.cmig_name"><i class="fas fa-id-card text-muted mr-1"></i>{{ o.cmig_name || '—' }}</td>
              <td>
                <span class="badge" :class="shipmentBadge(o.shipment_status)">
                  <i :class="shipmentIcon(o.shipment_status)" class="mr-1"></i>{{ shipmentLabel(o.shipment_status) }}
                </span>
              </td>
              <td>
                <span class="badge" :title="shippingModeStyle(o.shipping_mode).title"
                      :style="{ background: shippingModeStyle(o.shipping_mode).bg, color: shippingModeStyle(o.shipping_mode).fg, fontSize: '.66rem' }">
                  {{ shippingModeStyle(o.shipping_mode).label }}
                </span>
              </td>
              <td @click.stop>
                <button v-if="o.nfe_url || o.nfe_key" class="btn btn-xs btn-success" title="Imprimir DANFE" @click="openDanfe(o.id)">
                  <i class="fas fa-file-invoice mr-1"></i>Emitida
                </button>
                <span v-else-if="['pending','in_process'].includes(o.nfe_status)" class="badge badge-info">
                  <i class="fas fa-spinner fa-spin mr-1"></i>Processando
                </span>
                <button v-else-if="o.platform === 'mercadolivre' && o.shipment_status === 'ready_to_ship'"
                        class="btn btn-xs btn-outline-warning" :disabled="nfeEmitting[o.id]" @click="emitNfeList(o)" title="Emitir NF-e via ML">
                  <i class="fas fa-file-invoice mr-1"></i>{{ nfeEmitting[o.id] ? 'Emitindo…' : 'Emitir' }}
                </button>
                <span v-else class="text-muted small">—</span>
              </td>
              <td @click.stop>
                <a v-if="o.platform === 'mercadolivre' && o.platform_order_id"
                   :href="`https://www.mercadolivre.com.br/vendas/${o.platform_order_id}/detalhe`"
                   target="_blank" rel="noopener" class="badge badge-light border text-primary"
                   title="Ver venda no Mercado Livre">
                  #{{ o.platform_order_id }} <i class="fas fa-external-link-alt ml-1"></i>
                </a>
                <span v-else class="small">{{ o.platform_order_id || '—' }}</span>
                <div class="small text-muted text-nowrap"><i class="far fa-calendar mr-1"></i>{{ fmt(o.created_at) }}</div>
              </td>
              <td class="small text-nowrap">
                <i class="far fa-clock mr-1 text-muted"></i>{{ fmtDate(o.estimated_delivery_date || o.estimated_delivery_final) }}
              </td>
              <td class="text-truncate" style="max-width:160px">{{ o.buyer_name || '—' }}</td>
              <td>
                <span v-for="it in o.items" :key="it.id" class="badge badge-light border mr-1" :title="it.title">{{ it.sku || '?' }} ×{{ it.quantity }}</span>
              </td>
              <td class="text-right" @click.stop>
                <button v-if="selectable(o)" class="btn btn-xs btn-outline-primary" title="Adicionar a uma gaiola aberta" @click="openAddModal(o)">
                  <i class="fas fa-cart-plus"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="!loading && pending.length" class="card-footer py-2 text-muted small">
        {{ displayedOrders.length }} de {{ pending.length }} pedido(s) pago(s) — selecionáveis: venda direta + ML Pronto p/ Envio
      </div>
    </div>

    <!-- ══ Gaiolas abertas ════════════════════════════════════════════════ -->
    <div class="card mt-3">
      <div class="card-header"><strong>Gaiolas abertas</strong></div>
      <div class="card-body p-2">
        <span v-if="!openCarts.length" class="text-muted small">Nenhuma gaiola aberta.</span>
        <button v-for="c in openCarts" :key="c.id" class="btn btn-sm mr-2 mb-1"
                :class="activeCart && activeCart.id === c.id ? 'btn-primary' : 'btn-outline-primary'" @click="openCart(c.id)">
          <i :class="c.mode === 'scan' ? 'fas fa-barcode' : 'fas fa-hand-paper'" class="mr-1"></i>
          {{ c.cart_number }} <span class="badge badge-light ml-1">{{ c.order_count }}</span>
        </button>
      </div>
    </div>

    <!-- ══ Workspace da gaiola ════════════════════════════════════════════ -->
    <div v-if="activeCart" class="card mt-3 border-primary">
      <div class="card-header bg-primary text-white d-flex align-items-center flex-wrap">
        <strong>{{ activeCart.cart_number }}</strong>
        <span class="badge badge-light ml-2 text-capitalize">{{ activeCart.mode === 'scan' ? 'Bipagem' : 'Manual' }}</span>
        <span class="badge ml-2" :class="activeCart.status === 'separated' ? 'badge-success' : 'badge-warning text-dark'">
          {{ activeCart.status === 'separated' ? 'Concluída — pronta p/ transportadora' : 'Em separação' }}
        </span>
        <div class="ml-auto d-flex align-items-center">
          <select v-model="layout" class="form-control form-control-sm d-inline-block mr-2" style="width:auto" title="Layout p/ etiqueta interna (manual)">
            <option v-for="l in layouts" :key="l.key" :value="l.key">{{ l.label }}</option>
          </select>
          <button class="btn btn-sm btn-light mr-1" @click="togglePickRoute" title="Rota de picking por endereço (FEFO → caixa aberta → rota)">
            <i class="fas mr-1" :class="pickRouteBusy ? 'fa-spinner fa-spin' : 'fa-route'"></i> Rota
          </button>
          <button class="btn btn-sm btn-light mr-1" @click="printAllLabels"><i class="fas fa-tags mr-1"></i> Etiquetas</button>
          <div class="btn-group btn-group-sm mr-1">
            <button class="btn btn-light" :disabled="cartNfeBusy" @click="cartNfe(false)"
                    title="Emitir NF-e de todos os pedidos sem nota — transmite à SEFAZ sem confirmação">
              <i class="fas mr-1" :class="cartNfeBusy ? 'fa-spinner fa-spin' : 'fa-file-invoice'"></i> Emitir todos
            </button>
            <button class="btn btn-light" :disabled="cartNfeBusy" @click="cartNfe(true)"
                    title="Emitir NF-e de todos com uma confirmação antes de transmitir">
              <i class="fas fa-file-invoice-dollar mr-1"></i> Emitir confirmando
            </button>
          </div>
          <button class="btn btn-sm btn-warning text-dark mr-1" @click="downloadBundle" :disabled="downloadingBundle"
                  title="Baixa NF-e (PDF+XML) e etiquetas de todos os pedidos num único ZIP">
            <i class="fas mr-1" :class="downloadingBundle ? 'fa-spinner fa-spin' : 'fa-file-archive'"></i> Baixar tudo (ZIP)
          </button>
          <button class="btn btn-sm btn-success mr-1" @click="concludeCart" :disabled="!allSeparated"
                  :title="allSeparated ? '' : 'Separe (com fotos) todos os pedidos para concluir'">
            <i class="fas fa-check mr-1"></i> Concluir
          </button>
          <button class="btn btn-sm btn-outline-light" @click="cancelCart" title="Cancelar gaiola e devolver pedidos"><i class="fas fa-trash"></i></button>
        </div>
      </div>
      <!-- Painel ROTA DE PICKING (ADR-0039 Fase 2) — sugestão: onde pegar cada item, em que ordem -->
      <div v-if="showPickRoute" class="p-3 border-bottom" style="background:#eef5ff">
        <div class="d-flex justify-content-between align-items-center mb-2">
          <strong><i class="fas fa-route mr-1"></i> Rota de picking</strong>
          <button class="btn btn-xs btn-link text-muted" @click="showPickRoute = false"><i class="fas fa-times"></i></button>
        </div>
        <p v-if="!pickRoute.length" class="text-muted small mb-0">Nenhum item para montar a rota.</p>
        <table v-else class="table table-sm table-borderless mb-0">
          <tbody>
            <tr v-for="(it, i) in pickRoute" :key="i">
              <td class="text-right text-muted small" style="width:3rem">{{ it.qty }}×</td>
              <td>
                <div class="small"><strong>{{ it.sku }}</strong> — {{ it.title }}</div>
                <div v-if="it.pick_plan.length" class="small">
                  <span v-for="(s, j) in it.pick_plan" :key="j" class="badge badge-info mr-1">
                    {{ s.full_code }} ({{ s.take }})<span v-if="s.lot_code"> · lote {{ s.lot_code }}</span>
                  </span>
                  <span v-if="it.pick_shortage" class="badge badge-warning text-dark">{{ it.pick_shortage }} sem endereço</span>
                </div>
                <div v-else class="small text-warning">sem endereço cadastrado</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Painel BIPAGEM AUTOMÁTICA -->
      <div v-if="activeCart.mode === 'scan_auto'" class="p-3 border-bottom" style="background:#fffbea">
        <div class="d-flex align-items-start flex-wrap" style="gap:1rem">
          <div class="flex-grow-1" style="min-width:280px">
            <label class="small font-weight-bold mb-1 d-block">
              <i class="fas fa-bolt text-warning mr-1"></i>
              <span v-if="sa.state === 'photos'">FOTOS do pedido #{{ sa.currentOrder }} — bipe o produto p/ fotografar, ou o código <strong>{{ sa.finishCode }}</strong> p/ encerrar</span>
              <span v-else-if="sa.currentOrder">Bipe o PRÓXIMO item do pedido #{{ sa.currentOrder }}</span>
              <span v-else>Bipe um produto para localizar o pedido</span>
            </label>
            <input ref="scanInputEl" v-model="sa.code" class="form-control form-control-lg"
                   :placeholder="sa.state === 'photos' ? 'Bipe produto (foto) ou código de fim…' : 'Bipe o produto…'"
                   :disabled="sa.busy" @keyup.enter="onScanAuto" />
            <div v-if="sa.camError" class="text-danger small mt-1">{{ sa.camError }}</div>
            <div class="small text-muted mt-1">
              Código de fim das fotos: <strong>{{ sa.finishCode || '—' }}</strong>
              <a href="#" class="ml-2" @click.prevent="printFinishCode"><i class="fas fa-print mr-1"></i>Imprimir código (barras/QR)</a>
              <a v-if="isAdmin" href="#" class="ml-2" @click.prevent="fcModal.show = true"><i class="fas fa-cog mr-1"></i>Configurar</a>
            </div>
          </div>
          <div v-if="sa.currentOrder" class="text-center px-2">
            <div class="small text-muted">Pedido</div>
            <div class="font-weight-bold" style="font-size:1.1rem">#{{ sa.currentOrder }}</div>
            <div class="small text-truncate" style="max-width:140px">{{ sa.buyerName || '' }}</div>
            <div class="badge badge-info mt-1">{{ sa.scanned }}/{{ sa.expected }} itens</div>
          </div>
          <div v-show="sa.state === 'photos'" class="text-center">
            <video ref="saVideoEl" autoplay playsinline muted style="width:190px;max-height:150px;background:#000;border-radius:6px;object-fit:cover"></video>
            <div class="small text-muted">{{ sa.photos.length }} foto(s)</div>
          </div>
          <div v-if="sa.photos.length" class="d-flex flex-wrap align-content-start" style="gap:.25rem;max-width:180px">
            <img v-for="(p,i) in sa.photos" :key="i" :src="p.url" style="width:42px;height:42px;object-fit:cover;border-radius:3px;border:1px solid #ccc" />
          </div>
        </div>
        <canvas ref="saCanvasEl" style="display:none"></canvas>
      </div>

      <div class="card-body p-0">
        <table class="table table-sm mb-0 align-middle">
          <thead class="thead-light">
            <tr><th>Pedido</th><th>Cliente</th><th>Conferência</th><th class="text-center">Etiq.</th><th class="text-center">NF-e</th><th class="text-right">Ações</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in activeCart.orders" :key="o.id">
              <td class="font-weight-bold">#{{ o.id }}
                <span v-if="o.item_status === 'separated'" class="badge badge-success ml-1"><i class="fas fa-box-open"></i></span>
              </td>
              <td class="text-truncate" style="max-width:160px">{{ o.buyer_name || '—' }}</td>
              <td>
                <template v-if="activeCart.mode === 'scan' && o.scan">
                  <div class="progress" style="height:18px;min-width:150px">
                    <div class="progress-bar" :class="o.scan.scanned >= o.scan.expected ? 'bg-success' : 'bg-info'" :style="{ width: pct(o.scan) + '%' }">
                      {{ o.scan.scanned }}/{{ o.scan.expected }}
                    </div>
                  </div>
                  <div v-if="o.scan.scanned < o.scan.expected" class="input-group input-group-sm mt-1" style="max-width:230px">
                    <input :ref="el => bipRefs[o.id] = el" v-model="bipCode[o.id]" class="form-control" placeholder="Bipar SKU/EAN..." @keyup.enter="scan(o)" />
                    <div class="input-group-append"><button class="btn btn-outline-primary" @click="scan(o)"><i class="fas fa-barcode"></i></button></div>
                  </div>
                  <span v-else class="badge badge-success"><i class="fas fa-check"></i> Conferido</span>
                </template>
                <span v-else class="text-muted small">Manual</span>
              </td>
              <td class="text-center">
                <i class="fas fa-tag" :class="o.label_printed ? 'text-success' : 'text-muted'"
                   :title="o.label_printed ? 'Etiqueta impressa' : 'Etiqueta não impressa'"></i>
              </td>
              <td class="text-center">
                <i class="fas fa-file-invoice" :class="nfeIconClass(o)" :title="nfeIconTitle(o)"></i>
              </td>
              <td class="text-right text-nowrap">
                <button class="btn btn-xs btn-outline-secondary" :disabled="!canPrintLabel(o)"
                        :title="canPrintLabel(o) ? 'Imprimir etiqueta' : 'Bipe todos os itens primeiro'" @click="printOrderLabel(o)">
                  <i class="fas fa-tag"></i>
                </button>
                <button class="btn btn-xs btn-outline-info ml-1" :disabled="!o.label_printed"
                        :title="o.label_printed ? 'Emitir + imprimir NF-e' : 'Imprima a etiqueta primeiro'" @click="emitPrintOrderNfe(o)">
                  <i class="fas fa-file-invoice"></i>
                </button>
                <button v-if="o.item_status !== 'separated'" class="btn btn-xs btn-outline-success ml-1"
                        :disabled="!o.label_printed"
                        :title="o.label_printed ? 'Separar (foto obrigatória pela webcam)' : 'Imprima a etiqueta primeiro'"
                        @click="openSeparate(o)">
                  <i class="fas fa-camera"></i>
                </button>
                <span v-else class="badge badge-success ml-1" title="Separado"><i class="fas fa-check"></i></span>
                <button v-if="o.item_status !== 'separated'" class="btn btn-xs btn-outline-danger ml-1" title="Remover" @click="removeOrder(o.id)">
                  <i class="fas fa-times"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Modal: adicionar pedido a gaiola aberta -->
    <div v-if="addModal.show" class="modal-backdrop-custom" @click.self="addModal.show = false">
      <div class="card shadow" style="width:420px">
        <div class="card-header"><strong>Adicionar pedido #{{ addModal.order?.id }} a uma gaiola</strong></div>
        <div class="card-body">
          <p v-if="!openCarts.length" class="text-muted small mb-0">Nenhuma gaiola aberta. Crie uma nova gaiola primeiro.</p>
          <div v-else class="list-group">
            <button v-for="c in openCarts" :key="c.id" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" @click="addToCart(c)">
              <span><i :class="c.mode === 'scan' ? 'fas fa-barcode' : 'fas fa-hand-paper'" class="mr-2"></i>{{ c.cart_number }}</span>
              <span class="badge badge-primary badge-pill">{{ c.order_count }} pedido(s)</span>
            </button>
          </div>
        </div>
        <div class="card-footer text-right"><button class="btn btn-sm btn-secondary" @click="addModal.show = false">Fechar</button></div>
      </div>
    </div>

    <!-- Modal: separar com webcam (fotos obrigatórias → Google Drive) -->
    <div v-if="sep.show" class="modal-backdrop-custom" @click.self="closeSeparate">
      <div class="card shadow" style="width:560px;max-width:95vw">
        <div class="card-header d-flex align-items-center">
          <strong><i class="fas fa-camera mr-2"></i>Separar pedido #{{ sep.order?.id }}</strong>
          <button class="close ml-auto" @click="closeSeparate"><span>&times;</span></button>
        </div>
        <div class="card-body">
          <p class="small text-muted mb-2">Tire ao menos uma foto da separação. As fotos vão para o Google Drive (pasta <strong>Ecommerce_Imagens/Separacao</strong>).</p>
          <div v-if="sep.camError" class="alert alert-danger py-2">{{ sep.camError }}</div>
          <div class="text-center mb-2" style="background:#000;border-radius:6px;overflow:hidden">
            <video ref="videoEl" autoplay playsinline muted style="width:100%;max-height:300px;object-fit:contain"></video>
          </div>
          <div class="d-flex justify-content-center mb-2">
            <button class="btn btn-primary" :disabled="!sep.ready || sep.saving" @click="capturePhoto">
              <i class="fas fa-camera mr-1"></i> Tirar foto
            </button>
          </div>
          <div v-if="sep.photos.length" class="d-flex flex-wrap" style="gap:.4rem">
            <div v-for="(p, i) in sep.photos" :key="i" class="position-relative" style="width:80px;height:80px">
              <img :src="p.url" style="width:80px;height:80px;object-fit:cover;border-radius:4px;border:1px solid #dee2e6" />
              <button class="btn btn-xs btn-danger" style="position:absolute;top:-6px;right:-6px;border-radius:50%;padding:0 .35rem;line-height:1" @click="removePhoto(i)" title="Remover">&times;</button>
            </div>
          </div>
          <canvas ref="canvasEl" style="display:none"></canvas>
        </div>
        <div class="card-footer d-flex justify-content-between align-items-center">
          <small class="text-muted">{{ sep.photos.length }} foto(s)</small>
          <div>
            <button class="btn btn-sm btn-secondary mr-1" :disabled="sep.saving" @click="closeSeparate">Cancelar</button>
            <button class="btn btn-sm btn-success" :disabled="!sep.photos.length || sep.saving" @click="concludeSeparate">
              <i class="fas" :class="sep.saving ? 'fa-spinner fa-spin' : 'fa-check'"></i> Concluir separação
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: configurar código de fim das fotos (admin) -->
    <div v-if="fcModal.show" class="modal-backdrop-custom" @click.self="fcModal.show = false">
      <div class="card shadow" style="width:430px">
        <div class="card-header"><strong><i class="fas fa-cog mr-2"></i>Código de finalização das fotos</strong></div>
        <div class="card-body">
          <p class="small text-muted">O operador bipa este código para encerrar as fotos de um pedido (modo Bipagem automática). Vale para todos os galpões.</p>
          <input v-model="fcModal.code" class="form-control" maxlength="60" placeholder="ex.: FIM-FOTOS" />
        </div>
        <div class="card-footer d-flex justify-content-between">
          <button class="btn btn-sm btn-outline-secondary" @click="printFinishCode"><i class="fas fa-print mr-1"></i>Imprimir</button>
          <div>
            <button class="btn btn-sm btn-secondary mr-1" @click="fcModal.show = false">Cancelar</button>
            <button class="btn btn-sm btn-primary" :disabled="fcModal.saving" @click="saveFinishCode">Salvar</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, reactive } from 'vue'
import { formatDate as fmtBrDate, formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import { openAndSaveBlobResponse, saveLabelBoth } from '@/utils/download'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { platformLogo, shippingModeStyle, PLATFORMS } from '@/utils/constants'
import { useAuthStore } from '@/stores/auth'

const toast = useToast()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.user?.role === 'admin')

// ── Mapa de shipment_status (igual à Gestão de Pedidos) ──
const SHIPMENT_MAP = {
  pending:       { label: 'Aguardando',      icon: 'fas fa-clock',         badge: 'badge-secondary' },
  handling:      { label: 'Em Preparação',   icon: 'fas fa-box-open',      badge: 'badge-warning text-dark' },
  ready_to_ship: { label: 'Pronto p/ Envio', icon: 'fas fa-dolly',         badge: 'badge-info' },
  shipped:       { label: 'A caminho',       icon: 'fas fa-shipping-fast', badge: 'badge-primary' },
  delivered:     { label: 'Entregue',        icon: 'fas fa-check-circle',  badge: 'badge-success' },
  not_delivered: { label: 'Não Entregue',    icon: 'fas fa-exclamation-triangle', badge: 'badge-danger' },
  cancelled:     { label: 'Cancelado',       icon: 'fas fa-times-circle',  badge: 'badge-dark' },
}
function shipmentLabel(s) { return SHIPMENT_MAP[s]?.label || (s || '—') }
function shipmentIcon(s)  { return SHIPMENT_MAP[s]?.icon || 'fas fa-circle' }
function shipmentBadge(s) { return SHIPMENT_MAP[s]?.badge || 'badge-light' }

const pending = ref([])
const loading = ref(false)
const search = ref('')
const selected = ref(new Set())
const nfeEmitting = reactive({})

const filterPlatform = ref('')
const filterCmig = ref('')
const filterShipment = ref('')
const filterNfe = ref('')
const filterProduct = ref('')
const filterItems = ref('')
const sortKey = ref('shipment')
const sortDir = ref('asc')

const openCarts = ref([])
const activeCart = ref(null)
const layouts = ref([{ key: '10x15', label: 'Térmica 10x15' }, { key: 'a4_4up', label: 'A4 (4 por página)' }])
const layout = ref('10x15')
const downloadingBundle = ref(false)
const bipCode = ref({})
const bipRefs = ref({})
const addModal = reactive({ show: false, order: null })
const cartNfeBusy = ref(false)

// ── Separar com webcam (fotos obrigatórias → Google Drive) ──
const videoEl = ref(null)
const canvasEl = ref(null)
const sep = reactive({ show: false, order: null, photos: [], saving: false, ready: false, camError: '' })
let mediaStream = null

// ── Bipagem automática (modo scan_auto) ──
const scanInputEl = ref(null)
const saVideoEl = ref(null)
const saCanvasEl = ref(null)
const sa = reactive({
  code: '', state: 'product', currentOrder: null, buyerName: '', scanned: 0, expected: 0,
  orderComplete: false, photos: [], finishCode: '', busy: false, camError: '',
})
let saStream = null
const fcModal = reactive({ show: false, code: '', saving: false })

onMounted(async () => { await Promise.all([loadPending(), loadCarts(), loadLayouts()]) })

async function loadLayouts() {
  try { const { data } = await api.get('/separation/label-layouts'); if (Array.isArray(data) && data.length) layouts.value = data } catch { /* defaults */ }
}
async function loadPending() {
  loading.value = true
  try { const { data } = await api.get('/separation/orders'); pending.value = data.orders || [] }
  catch { pending.value = [] } finally { loading.value = false }
}
async function loadCarts() {
  try { const { data } = await api.get('/separation/carts', { params: { status: 'open' } }); openCarts.value = data.carts || [] }
  catch { openCarts.value = [] }
}

// ML-com-shipment precisa estar "Pronto p/ Envio"; venda direta (manual) basta estar pago
// (a lista já só traz pagos — regra do dono).
function selectable(o) { return o.shipment_status === 'ready_to_ship' || o.platform !== 'mercadolivre' }

// ── Opções de filtro ──
const platformOptions = computed(() => [...new Set(pending.value.map(o => o.platform).filter(Boolean))])
const shipmentOptions = computed(() => [...new Set(pending.value.map(o => o.shipment_status).filter(Boolean))])
const cmigOptions = computed(() => {
  const map = new Map()
  for (const o of pending.value) if (o.cmig_id && !map.has(o.cmig_id)) map.set(o.cmig_id, { id: o.cmig_id, name: o.cmig_name || `CMIG ${o.cmig_id}` })
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name))
})
const hasFilters = computed(() => !!(filterPlatform.value || filterCmig.value || filterShipment.value || filterNfe.value || filterProduct.value || filterItems.value || search.value))
function platformLabel(key) { return PLATFORMS.find(p => p.key === key)?.label || key }
function clearFilters() { filterPlatform.value = ''; filterCmig.value = ''; filterShipment.value = ''; filterNfe.value = ''; filterProduct.value = ''; filterItems.value = ''; search.value = '' }
function matchesProduct(o, q) {
  const s = q.toLowerCase()
  return (o.items || []).some(it => (it.sku || '').toLowerCase().includes(s) || (it.title || '').toLowerCase().includes(s))
}
function matchesItemCount(o, f) {
  const n = (o.items || []).length
  return f === '3' ? n >= 3 : n === Number(f)
}

function hasNfe(o) { return !!(o.nfe_url || o.nfe_key || ['authorized', 'pending', 'in_process'].includes(o.nfe_status)) }

const displayedOrders = computed(() => {
  let rows = pending.value.filter(o => {
    if (filterPlatform.value && o.platform !== filterPlatform.value) return false
    if (filterCmig.value && String(o.cmig_id) !== String(filterCmig.value)) return false
    if (filterShipment.value && o.shipment_status !== filterShipment.value) return false
    if (filterNfe.value === 'emitida' && !hasNfe(o)) return false
    if (filterNfe.value === 'pendente' && hasNfe(o)) return false
    if (filterProduct.value && !matchesProduct(o, filterProduct.value)) return false
    if (filterItems.value && !matchesItemCount(o, filterItems.value)) return false
    if (search.value && !(o.buyer_name || '').toLowerCase().includes(search.value.toLowerCase())) return false
    return true
  })
  const dir = sortDir.value === 'asc' ? 1 : -1
  const keyFn = {
    id: o => o.id,
    platform: o => o.platform || '',
    cmig: o => (o.cmig_name || '').toLowerCase(),
    shipment: o => o.shipment_status || '',
    nfe: o => (hasNfe(o) ? '1' : '0'),
    sale: o => o.created_at || '',
    delivery: o => o.estimated_delivery_date || o.estimated_delivery_final || '',
    buyer: o => (o.buyer_name || '').toLowerCase(),
  }[sortKey.value] || (o => o.id)
  return [...rows].sort((a, b) => { const va = keyFn(a), vb = keyFn(b); return va < vb ? -dir : va > vb ? dir : 0 })
})
function setSort(key) { if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'; else { sortKey.value = key; sortDir.value = 'asc' } }
function sortIcon(key) { if (sortKey.value !== key) return 'fas fa-sort text-muted'; return sortDir.value === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down' }

const selectableDisplayed = computed(() => displayedOrders.value.filter(selectable))
const allChecked = computed(() => selectableDisplayed.value.length > 0 && selectableDisplayed.value.every(o => selected.value.has(o.id)))
const allLabelPrinted = computed(() => activeCart.value?.orders?.length > 0 && activeCart.value.orders.every(o => o.label_printed))
const allSeparated = computed(() => activeCart.value?.orders?.length > 0 && activeCart.value.orders.every(o => o.item_status === 'separated'))

function toggle(id) { const s = new Set(selected.value); s.has(id) ? s.delete(id) : s.add(id); selected.value = s }
function toggleAll() {
  const s = new Set(selected.value)
  if (allChecked.value) selectableDisplayed.value.forEach(o => s.delete(o.id))
  else selectableDisplayed.value.forEach(o => s.add(o.id))
  selected.value = s
}

async function printList() { await openPdf('/separation/picking-list', 'post', { order_ids: [...selected.value] }) }

// ── Emitir NF-e direto na lista (pedido fora de gaiola) ──
async function emitNfeList(o) {
  nfeEmitting[o.id] = true
  try {
    await api.post(`/orders/${o.id}/emit-nfe`)
    toast.success(`NF-e do pedido #${o.id} solicitada`)
    await loadPending()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao emitir NF-e') }
  finally { nfeEmitting[o.id] = false }
}

// ── Gaiolas ──
async function newCart(mode) {
  try {
    const { data } = await api.post('/separation/carts', { mode })
    const { data: addRes } = await api.post(`/separation/carts/${data.id}/orders`, { order_ids: [...selected.value] })
    selected.value = new Set()
    await Promise.all([loadPending(), loadCarts()])
    await openCart(data.id)
    toast.success(`Gaiola ${data.cart_number} criada (${mode === 'scan' ? 'bipagem' : 'manual'})`)
    if (addRes?.skipped?.length) toast.warning(`${addRes.skipped.length} pedido(s) não adicionado(s): ${addRes.skipped.join(', ')}`)
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao criar gaiola') }
}

function openAddModal(o) {
  if (!openCarts.value.length) return toast.info('Nenhuma gaiola aberta. Crie uma nova gaiola primeiro.')
  addModal.order = o; addModal.show = true
}
async function addToCart(cart) {
  try {
    const { data } = await api.post(`/separation/carts/${cart.id}/orders`, { order_ids: [addModal.order.id] })
    if (data.added?.length) toast.success(`Pedido #${addModal.order.id} adicionado à ${cart.cart_number}`)
    else toast.warning('Pedido não pôde ser adicionado (não está Pronto p/ Envio?)')
    addModal.show = false
    await Promise.all([loadPending(), loadCarts()])
    if (activeCart.value?.id === cart.id) await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao adicionar') }
}

async function openCart(id, { refresh = false } = {}) {
  try {
    const wasId = activeCart.value?.id
    const { data } = await api.get(`/separation/carts/${id}`)
    activeCart.value = data
    focusFirstBip()
    if (data.mode === 'scan_auto') {
      if (!refresh && wasId !== id) await initScanAuto()   // abertura nova → inicia câmera/estado
      else { await nextTick(); scanInputEl.value?.focus() } // refresh → mantém estado
    } else { saStopCamera(); resetSaOrder() }
  } catch { toast.error('Erro ao abrir gaiola') }
}
async function refreshCart() { if (activeCart.value) await openCart(activeCart.value.id, { refresh: true }) }

// Rota de picking (ADR-0039 Fase 2) — sugestão de onde pegar cada item; não debita o endereço.
const pickRoute = ref([])
const showPickRoute = ref(false)
const pickRouteBusy = ref(false)
async function togglePickRoute() {
  if (showPickRoute.value) { showPickRoute.value = false; return }
  if (!activeCart.value) return
  pickRouteBusy.value = true
  try {
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/pick-plan`)
    pickRoute.value = data.items || []
    showPickRoute.value = true
  } catch (e) { toast.error(e.response?.data?.detail || 'Falha ao montar a rota.') }
  finally { pickRouteBusy.value = false }
}

async function scan(o) {
  const code = (bipCode.value[o.id] || '').trim()
  if (!code) return
  try {
    const { data } = await api.post(`/separation/carts/${activeCart.value.id}/orders/${o.id}/scan`, { code })
    bipCode.value[o.id] = ''
    if (o.scan) { o.scan.scanned = data.scanned; o.scan.expected = data.expected }
    if (data.complete) toast.success(`Pedido #${o.id} conferido 100% — etiqueta liberada`)
    await nextTick(); bipRefs.value[o.id]?.focus()
  } catch (e) {
    bipCode.value[o.id] = ''
    toast.error(e.response?.data?.detail || 'Código inválido')
    await nextTick(); bipRefs.value[o.id]?.focus()
  }
}

function canPrintLabel(o) {
  if (activeCart.value?.mode === 'scan' && o.scan) return o.scan.scanned >= o.scan.expected
  return true
}

async function removeOrder(id) {
  try { await api.delete(`/separation/carts/${activeCart.value.id}/orders/${id}`); await Promise.all([refreshCart(), loadPending(), loadCarts()]) }
  catch (e) { toast.error(e.response?.data?.detail || 'Erro ao remover') }
}

async function concludeCart() {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/conclude`)
    toast.success('Gaiola concluída — pronta para a transportadora')
    await Promise.all([refreshCart(), loadCarts(), loadPending()])
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao concluir') }
}

async function cancelCart() {
  if (!confirm('Cancelar esta gaiola? Os pedidos voltam para a lista de separação.')) return
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/cancel`)
    toast.success('Gaiola cancelada — pedidos devolvidos')
    saStopCamera(); resetSaOrder()
    activeCart.value = null
    await Promise.all([loadCarts(), loadPending()])
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao cancelar') }
}

// ── Etiquetas ──
// Baixa PDF + ZPL de uma vez. O ZPL vem PRIMEIRO (é render-only, não marca impresso) e o
// PDF depois (marca) — assim os dois arquivos cobrem exatamente o mesmo conjunto de pedidos.
async function printCartLabelsBoth(params) {
  const url = `/separation/carts/${activeCart.value.id}/labels.pdf`
  const zplResp = await api.get(url, { params: { ...params, fmt: 'zpl2' }, responseType: 'blob' }).catch(() => null)
  const pdfResp = await api.get(url, { params, responseType: 'blob' })
  saveLabelBoth(pdfResp, zplResp)
}
async function printOrderLabel(o) {
  try {
    await printCartLabelsBoth({ order_id: o.id, layout: layout.value })
    await refreshCart()
  } catch (e) {
    let msg = 'Erro ao gerar etiqueta'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* ignore */ }
    toast.error(msg)
  }
}
async function printAllLabels() {
  try {
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/label-jobs`)
    const jobs = data.jobs || []
    if (!jobs.length) return toast.warning('Nenhuma etiqueta pronta para imprimir (bipe os pedidos no modo bipagem).')
    for (const job of jobs) {
      const params = job.kind === 'manual' ? { manual: true, layout: layout.value } : { account_id: job.account_id }
      await printCartLabelsBoth(params)
    }
    if (data.blocked_scan) toast.info(`${data.blocked_scan} pedido(s) aguardando bipagem (etiqueta não liberada).`)
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao imprimir etiquetas') }
}

// ── NF-e na gaiola ──
async function openDanfe(orderId) {
  await openPdf(`/separation/orders/${orderId}/danfe`, 'get')
}
async function emitPrintOrderNfe(o) {
  try {
    await api.post(`/separation/carts/${activeCart.value.id}/emit-nfe`, { order_ids: [o.id] })
    // sincroniza/marca e descobre quais já têm nota
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/nfe`, { params: { order_id: o.id, mark: 1 } })
    const ready = (data.nfe || []).filter(n => n.nfe_key || n.nfe_url)
    if (ready.length) for (const n of ready) await openDanfe(n.order_id)
    else toast.info(`NF-e do #${o.id} solicitada — DANFE ainda processando no ML`)
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro na NF-e') }
}
// "Emitir todos" (confirmFirst=false) | "Emitir confirmando" (confirmFirst=true). Para pedido
// manual a NF-e é emissão PRÓPRIA (SEFAZ, transmite); ML segue pelo Faturador.
async function cartNfe(confirmFirst) {
  if (confirmFirst && !confirm('Transmitir as NF-e dos pedidos sem nota à SEFAZ? É um ato fiscal irreversível.')) return
  cartNfeBusy.value = true
  try {
    const { data } = await api.post(`/separation/carts/${activeCart.value.id}/emit-nfe`, {})
    const results = data.results || []
    const errs = results.filter(r => r.error)
    const ok = results.filter(r => r.nfe_status || r.mode)
    if (ok.length) toast.success(`NF-e processada(s): ${ok.length}`)
    if (errs.length) toast.warning(`${errs.length} com erro: ${errs.map(e => '#' + e.order_id + ' ' + (e.error || '')).join(' | ').slice(0, 300)}`)
    if (!ok.length && !errs.length) toast.info('Nenhum pedido elegível (já com nota ou sem etiqueta).')
    // Abre DANFE dos ML prontos (emissão própria pode não ter DANFE via esta rota).
    try {
      const { data: nf } = await api.get(`/separation/carts/${activeCart.value.id}/nfe`, { params: { mark: 1 } })
      const ready = (nf.nfe || []).filter(n => n.nfe_key || n.nfe_url)
      for (const n of ready) await openDanfe(n.order_id)
    } catch { /* own-emission pode não ter DANFE via ML */ }
    await refreshCart()
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro na NF-e') } finally { cartNfeBusy.value = false }
}

async function openSeparate(o) {
  sep.order = o; sep.photos = []; sep.saving = false; sep.ready = false; sep.camError = ''; sep.show = true
  await nextTick()
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    if (videoEl.value) { videoEl.value.srcObject = mediaStream; sep.ready = true }
  } catch {
    sep.camError = 'Não foi possível acessar a câmera. Permita o acesso no navegador (requer HTTPS).'
  }
}
function capturePhoto() {
  const v = videoEl.value, c = canvasEl.value
  if (!v || !c) return
  const w = v.videoWidth || 640, h = v.videoHeight || 480
  c.width = w; c.height = h
  c.getContext('2d').drawImage(v, 0, 0, w, h)
  c.toBlob(blob => { if (blob) sep.photos.push({ blob, url: URL.createObjectURL(blob) }) }, 'image/jpeg', 0.85)
}
function removePhoto(i) {
  const p = sep.photos[i]; if (p?.url) URL.revokeObjectURL(p.url)
  sep.photos.splice(i, 1)
}
function stopCamera() { if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null } }
function closeSeparate() {
  stopCamera()
  sep.photos.forEach(p => p.url && URL.revokeObjectURL(p.url))
  sep.photos = []; sep.show = false
}
async function concludeSeparate() {
  if (!sep.photos.length) return toast.error('Tire ao menos uma foto da separação.')
  sep.saving = true
  try {
    const fd = new FormData()
    sep.photos.forEach((p, i) => fd.append('files', p.blob, `foto-${i + 1}.jpg`))
    await api.post(`/separation/carts/${activeCart.value.id}/orders/${sep.order.id}/separate`, fd,
      { headers: { 'Content-Type': 'multipart/form-data' } })
    toast.success(`Pedido #${sep.order.id} separado (${sep.photos.length} foto(s) no Drive).`)
    closeSeparate()
    await refreshCart()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao concluir a separação')
  } finally {
    sep.saving = false
  }
}
onBeforeUnmount(() => { stopCamera(); saStopCamera() })

// ── Bipagem automática: máquina de estados ──
async function initScanAuto() {
  resetSaOrder()
  try { const { data } = await api.get('/separation/config'); sa.finishCode = data.finish_photos_code || 'FIM-FOTOS' }
  catch { sa.finishCode = 'FIM-FOTOS' }
  fcModal.code = sa.finishCode
  await nextTick()
  await saStartCamera()
  await nextTick(); scanInputEl.value?.focus()
}
function resetSaOrder() {
  sa.photos.forEach(p => p.url && URL.revokeObjectURL(p.url))
  sa.photos = []; sa.currentOrder = null; sa.buyerName = ''; sa.scanned = 0; sa.expected = 0
  sa.orderComplete = false; sa.state = 'product'
}
async function saStartCamera() {
  try {
    saStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    if (saVideoEl.value) saVideoEl.value.srcObject = saStream
    sa.camError = ''
  } catch { sa.camError = 'Câmera indisponível — permita o acesso (requer HTTPS).' }
}
function saStopCamera() { if (saStream) { saStream.getTracks().forEach(t => t.stop()); saStream = null } }

async function onScanAuto() {
  const code = (sa.code || '').trim()
  sa.code = ''
  if (!code || sa.busy) { await nextTick(); scanInputEl.value?.focus(); return }
  if (sa.state === 'photos') {
    if (code.toUpperCase() === (sa.finishCode || '').toUpperCase()) await saFinishPhotos()
    else saCapture()
    await nextTick(); scanInputEl.value?.focus()
  } else {
    await saLocate(code)
  }
}
async function saLocate(code) {
  sa.busy = true
  try {
    const body = { code }
    if (sa.currentOrder) body.order_id = sa.currentOrder
    const { data } = await api.post(`/separation/carts/${activeCart.value.id}/scan-locate`, body)
    sa.scanned = data.scanned; sa.expected = data.expected; sa.orderComplete = data.order_complete
    if (!sa.currentOrder) {
      sa.currentOrder = data.order_id
      sa.buyerName = data.buyer_name || ''
      if (!data.label_printed) { toast.info(`Pedido #${data.order_id} — imprimindo etiqueta…`); await printOrderLabelById(data.order_id) }
    }
    sa.state = 'photos'
    await refreshCart()
    toast.success(`Item bipado (${sa.scanned}/${sa.expected}). Fotografe; bipe "${sa.finishCode}" p/ encerrar.`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Produto não encontrado na gaiola')
  } finally { sa.busy = false; await nextTick(); scanInputEl.value?.focus() }
}
function saCapture() {
  const v = saVideoEl.value, c = saCanvasEl.value
  if (!v || !c) return
  const w = v.videoWidth || 640, h = v.videoHeight || 480
  c.width = w; c.height = h
  c.getContext('2d').drawImage(v, 0, 0, w, h)
  c.toBlob(b => { if (b) sa.photos.push({ blob: b, url: URL.createObjectURL(b) }) }, 'image/jpeg', 0.85)
}
async function saFinishPhotos() {
  if (sa.orderComplete) await saFinalizeOrder()
  else { sa.state = 'product'; toast.info(`Bipe o próximo item do pedido #${sa.currentOrder} (${sa.scanned}/${sa.expected}).`) }
}
async function saFinalizeOrder() {
  if (!sa.photos.length) { toast.error('Tire ao menos uma foto antes de finalizar.'); return }
  sa.busy = true
  try {
    const fd = new FormData()
    sa.photos.forEach((p, i) => fd.append('files', p.blob, `foto-${i + 1}.jpg`))
    await api.post(`/separation/carts/${activeCart.value.id}/orders/${sa.currentOrder}/separate`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
    try {
      const { data } = await api.post(`/separation/carts/${activeCart.value.id}/emit-nfe`, { order_ids: [sa.currentOrder] })
      const r = (data.results || [])[0]
      if (r?.error) toast.warning(`Pedido #${sa.currentOrder}: NF-e NÃO emitida — ${r.error}`)
      else if (r?.already) toast.info(`Pedido #${sa.currentOrder} separado — NF-e já existia.`)
      else if (r?.skipped) toast.warning(`Pedido #${sa.currentOrder} separado, NF-e pulada: ${r.skipped}`)
      else toast.success(`Pedido #${sa.currentOrder} separado e NF-e emitida.`)
    } catch (e) { toast.warning(`Pedido #${sa.currentOrder} separado, mas a NF-e falhou: ${e.response?.data?.detail || ''}`) }
    resetSaOrder()
    await refreshCart()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao finalizar a separação')
  } finally { sa.busy = false; await nextTick(); scanInputEl.value?.focus() }
}
async function printOrderLabelById(orderId) {
  try { await printCartLabelsBoth({ order_id: orderId, layout: layout.value }) }
  catch { toast.error('Falha ao imprimir a etiqueta') }
}
function printFinishCode() { openPdf('/separation/finish-code-label.pdf', 'get') }
async function saveFinishCode() {
  const code = (fcModal.code || '').trim()
  if (!code) return toast.error('Informe o código')
  fcModal.saving = true
  try {
    const { data } = await api.put('/separation/config', { finish_photos_code: code })
    sa.finishCode = data.finish_photos_code
    toast.success('Código salvo.')
    fcModal.show = false
  } catch (e) { toast.error(e.response?.data?.detail || 'Erro ao salvar') } finally { fcModal.saving = false }
}

// ── Baixar tudo (ZIP): etiquetas + DANFE + XML ──
async function downloadBundle() {
  if (!activeCart.value || downloadingBundle.value) return
  downloadingBundle.value = true
  try {
    const { data } = await api.get(`/separation/carts/${activeCart.value.id}/bundle.zip`,
      { responseType: 'blob', params: { layout: layout.value } })
    const url = URL.createObjectURL(new Blob([data], { type: 'application/zip' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${activeCart.value.cart_number}-documentos.zip`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 60000)
    toast.success('ZIP gerado. Confira o _avisos.txt caso algum pedido tenha ficado de fora.')
    await refreshCart()
  } catch (e) {
    let msg = 'Erro ao gerar o ZIP'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* ignore */ }
    toast.error(msg)
  } finally {
    downloadingBundle.value = false
  }
}

function nfeIconClass(o) {
  if (o.nfe_printed) return 'text-success'
  if (o.nfe_url || o.nfe_status === 'authorized') return 'text-info'
  if (['pending', 'in_process'].includes(o.nfe_status)) return 'text-warning'
  return 'text-muted'
}
function nfeIconTitle(o) {
  if (o.nfe_printed) return 'DANFE impressa'
  if (o.nfe_url || o.nfe_status === 'authorized') return 'NF-e emitida (não impressa)'
  if (['pending', 'in_process'].includes(o.nfe_status)) return 'NF-e processando no ML'
  return 'Sem NF-e (opcional)'
}

async function openPdf(url, method, body, params) {
  try {
    const cfg = { responseType: 'blob', params }
    const resp = method === 'post' ? await api.post(url, body, cfg) : await api.get(url, cfg)
    // abre para imprimir E baixa cópia nomeada (nome vem do Content-Disposition do backend)
    openAndSaveBlobResponse(resp, 'documento.pdf', 'application/pdf')
  } catch (e) {
    // erro pode vir como blob JSON
    let msg = 'Erro ao gerar PDF'
    try { msg = JSON.parse(await e.response.data.text()).detail || msg } catch { /* ignore */ }
    toast.error(msg)
  }
}

function focusFirstBip() {
  if (activeCart.value?.mode !== 'scan') return
  nextTick(() => {
    const first = activeCart.value.orders.find(o => o.scan && o.scan.scanned < o.scan.expected)
    if (first) bipRefs.value[first.id]?.focus()
  })
}

function pct(scan) { return scan.expected ? Math.round((scan.scanned / scan.expected) * 100) : 0 }
function fmt(dt) { return fmtBrDateTime(dt) }   // fonte única (horário do Brasil)
function fmtDate(d) { return fmtBrDate(d) }
</script>

<style scoped>
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable:hover { background: rgba(0,0,0,.03); }
.modal-backdrop-custom { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1050; }
</style>
