<template>
  <div v-if="show" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-xl" style="max-width:95vw">
      <div class="modal-content">
        <!-- Header -->
        <div class="modal-header">
          <h5 class="modal-title">
            <i class="fas fa-history mr-2"></i>Movimentação de Estoque
            <small class="text-muted ml-2">· {{ productSku }} — {{ productTitle }}</small>
          </h5>
          <button type="button" class="close" @click="closeModal"><span>&times;</span></button>
        </div>

        <div class="modal-body">
          <!-- Filtros de período -->
          <div class="row mb-3">
            <div class="col-md-3">
              <label class="font-weight-bold" style="font-size:13px">Data inicial</label>
              <input type="date" v-model="startDate" class="form-control form-control-sm" @change="load" />
            </div>
            <div class="col-md-3">
              <label class="font-weight-bold" style="font-size:13px">Data final</label>
              <input type="date" v-model="endDate" class="form-control form-control-sm" @change="load" />
            </div>
            <div class="col-md-6 d-flex align-items-end" style="gap:.25rem">
              <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(7)">7 dias</button>
              <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(30)">30 dias</button>
              <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(90)">90 dias</button>
              <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(365)">1 ano</button>
              <button class="btn btn-sm btn-outline-secondary" @click="setPeriodPreset(null)" title="Todo o histórico">Tudo</button>
            </div>
          </div>

          <!-- M1: Banner de reconciliação -->
          <div v-if="!loading && data" class="mb-3">
            <div v-if="cacheInSync" class="alert alert-success py-2 mb-2 small">
              <i class="fas fa-check-circle mr-1"></i>
              Saldo em cache (<strong>{{ cacheBalance }}</strong>) está em sync com o saldo calculado a partir dos eventos.
            </div>
            <div v-else class="alert alert-warning py-2 mb-2 small d-flex justify-content-between align-items-center">
              <div>
                <i class="fas fa-exclamation-triangle mr-1"></i>
                Cache divergente do calculado:
                cache = <strong>{{ cacheBalance }}</strong>,
                calculado = <strong>{{ data.calculated_balance }}</strong>
                (Δ {{ (data.calculated_balance - cacheBalance) >= 0 ? '+' : '' }}{{ data.calculated_balance - cacheBalance }})
              </div>
              <button class="btn btn-sm btn-warning" @click="recalc" :disabled="recalcLoading">
                <i class="fas fa-calculator mr-1"></i>Recalcular agora
              </button>
            </div>
          </div>

          <!-- M2: Cards Estado atual -->
          <div v-if="!loading && data">
            <div class="row mb-2">
              <div class="col-md-4">
                <div class="card bg-dark text-white mb-0" title="Saldo atual no cache (stock_quantity). Reflete NFes + pedidos definitivos.">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Saldo em estoque</small>
                    <strong style="font-size:1.4rem">{{ cacheBalance }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md-4">
                <div class="card bg-warning text-dark mb-0" title="Pedidos com status handling ou ready_to_ship — compromissos ainda na rua.">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Reservado <small class="text-muted">(pedidos a expedir)</small></small>
                    <strong style="font-size:1.4rem">−{{ reserved }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md-4">
                <div class="card bg-primary text-white mb-0" title="Saldo em estoque − Reservado. Quantidade livre para novas vendas.">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Disponível para vender</small>
                    <strong style="font-size:1.4rem">{{ data.current_balance_available }}</strong>
                  </div>
                </div>
              </div>
            </div>

            <!-- Cards Movimentação no período -->
            <div class="row mb-2">
              <div class="col-md-3">
                <div class="card bg-success text-white mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Entradas NFe</small>
                    <strong style="font-size:1.2rem">+{{ data.period_in_nfe }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md-3">
                <div class="card bg-danger text-white mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Saídas NFe</small>
                    <strong style="font-size:1.2rem">−{{ data.period_out_nfe }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md-3">
                <div class="card mb-0" style="background:#fd7e14;color:#fff" title="Saídas via pedidos no período.">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Saídas (Pedidos)</small>
                    <strong style="font-size:1.2rem">−{{ data.period_out_orders }}</strong>
                  </div>
                </div>
              </div>
              <div class="col-md-3">
                <div class="card bg-info text-white mb-0">
                  <div class="card-body py-2 text-center">
                    <small class="d-block">Variação líquida</small>
                    <strong style="font-size:1.2rem">{{ periodNetSign }}{{ periodNet }}</strong>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="movedNoNfe > 0" class="alert alert-light border py-2 mb-3 small">
              <i class="fas fa-info-circle mr-1 text-warning"></i>
              <strong>{{ movedNoNfe }}</strong> pedido(s) entregue(s) sem NFe regularizada — saída fiscal pendente (não impacta o disponível).
            </div>

            <!-- M7: filtros + M9: export CSV -->
            <div class="d-flex justify-content-between align-items-center flex-wrap mb-2" style="gap:.5rem">
              <div class="d-flex flex-wrap align-items-center" style="gap:.75rem">
                <small class="text-muted font-weight-bold">Filtrar:</small>
                <div class="custom-control custom-checkbox custom-control-inline">
                  <input type="checkbox" class="custom-control-input" :id="fId('nfe-in')" v-model="filters.nfeIn" />
                  <label class="custom-control-label small" :for="fId('nfe-in')">NFe Entrada</label>
                </div>
                <div class="custom-control custom-checkbox custom-control-inline">
                  <input type="checkbox" class="custom-control-input" :id="fId('nfe-out')" v-model="filters.nfeOut" />
                  <label class="custom-control-label small" :for="fId('nfe-out')">NFe Saída</label>
                </div>
                <div class="custom-control custom-checkbox custom-control-inline">
                  <input type="checkbox" class="custom-control-input" :id="fId('orders')" v-model="filters.ordersDefinitive" />
                  <label class="custom-control-label small" :for="fId('orders')">Pedidos</label>
                </div>
                <div class="custom-control custom-checkbox custom-control-inline">
                  <input type="checkbox" class="custom-control-input" :id="fId('reserved')" v-model="filters.reserved" />
                  <label class="custom-control-label small" :for="fId('reserved')">Reservados</label>
                </div>
                <div class="custom-control custom-checkbox custom-control-inline">
                  <input type="checkbox" class="custom-control-input" :id="fId('adj')" v-model="filters.adjustments" />
                  <label class="custom-control-label small" :for="fId('adj')">Ajustes</label>
                </div>
              </div>
              <div>
                <button class="btn btn-sm btn-outline-secondary" @click="exportCsv" :disabled="!filteredMovements.length">
                  <i class="fas fa-file-csv mr-1"></i>Exportar CSV
                </button>
              </div>
            </div>
          </div>

          <!-- Tabela -->
          <div v-if="loading" class="text-center py-5">
            <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
          </div>
          <div v-else-if="!data || data.movements.length === 0" class="text-center text-muted py-4">
            <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
            <span v-if="productType === 'pg' && data && data.linked_cmig_count === 0">
              Este PG não tem nenhum CMIGProduct vinculado — sem movimentações para exibir.
            </span>
            <span v-else>Nenhuma movimentação no período.</span>
          </div>
          <div v-else class="table-responsive" style="max-height:45vh">
            <table class="table table-sm table-hover mb-0" style="white-space:nowrap;font-size:13px">
              <thead class="thead-light sticky-top">
                <tr>
                  <th>Data</th>
                  <th>Origem</th>
                  <th>Referência</th>
                  <th v-if="productType === 'pg'">CMIG / Produto</th>
                  <th>Pessoa / Anúncio</th>
                  <th v-if="productType === 'cmig'">Item</th>
                  <th class="text-right">Qtd</th>
                  <th class="text-right">Saldo Disponível</th>
                </tr>
              </thead>
              <tbody>
                <!-- M8: saldo final (topo, DESC) -->
                <tr v-if="filteredMovements.length" class="bg-light">
                  <td :colspan="dataColspan" class="text-right small text-muted">
                    <i class="fas fa-flag-checkered mr-1"></i>
                    <strong>Saldo no fim do período</strong>
                    <span v-if="endDate">({{ formatBR(endDate) }})</span>
                  </td>
                  <td class="text-right"><strong>{{ data.period_final_available ?? cacheBalance }}</strong></td>
                </tr>
                <tr v-for="(m, idx) in filteredMovements" :key="idx">
                  <td style="font-size:12px">{{ formatDateTimeOneLine(m.date) }}</td>
                  <td style="white-space:normal">
                    <span v-if="m.source === 'nfe_in'" class="badge badge-success">
                      <i class="fas fa-file-invoice mr-1"></i>NFe Entrada
                    </span>
                    <span v-else-if="m.source === 'nfe_out'" class="badge badge-danger">
                      <i class="fas fa-file-invoice mr-1"></i>NFe Saída
                    </span>
                    <span v-else-if="m.source === 'adjustment'"
                          class="badge badge-dark"
                          :title="adjustmentTooltip(m)">
                      <i class="fas fa-tools mr-1"></i>{{ adjustmentLabel(m) }}
                    </span>
                    <span v-else-if="m.source === 'inventory'"
                          class="badge" style="background:#20c997;color:#fff"
                          title="Contagem de inventário finalizada">
                      <i class="fas fa-clipboard-check mr-1"></i>Inventário {{ m.inventory_mode === 'baseline' ? '(baseline)' : '(ajuste)' }}
                    </span>
                    <template v-else>
                      <span v-if="m.order_platform === 'mercadolivre'"
                            class="d-inline-flex align-items-center">
                        <img v-if="!mlLogoError" :src="mlLogoUrl" alt="ML"
                             style="height:22px;width:auto" @error="mlLogoError = true" />
                        <span v-else class="badge" style="background:#FFE600;color:#3F3F3F;font-weight:bold">
                          <i class="fas fa-shopping-bag mr-1"></i>ML
                        </span>
                      </span>
                      <span v-else-if="m.order_platform === 'shopee'"
                            class="badge" style="background:#EE4D2D;color:#fff;font-weight:bold">
                        <i class="fas fa-shopping-bag mr-1"></i>Shopee
                      </span>
                      <span v-else class="badge badge-secondary">
                        <i class="fas fa-shopping-bag mr-1"></i>{{ m.order_platform || 'Pedido' }}
                      </span>
                      <span v-if="m.origin_kind === 'direct_pg'"
                            class="badge badge-info ml-1" style="font-size:10px"
                            title="Pedido aponta direto ao PG (sem CMIG intermediário)">Direto PG</span>
                      <span v-else-if="m.origin_kind === 'overflow_cmig'"
                            class="badge badge-warning text-dark ml-1" style="font-size:10px"
                            title="Pedido consumiu estoque PG por overflow de CMIG vinculado">Overflow CMIG</span>
                      <span v-else-if="m.origin_kind === 'kit_component'"
                            class="badge badge-secondary ml-1" style="font-size:10px"
                            title="Componente consumido por venda de kit">Kit</span>
                    </template>
                  </td>
                  <td style="font-size:12px">
                    <RouterLink v-if="m.source !== 'order' && m.source !== 'adjustment' && m.invoice_id" :to="`/fiscal/invoices/${m.invoice_id}`" class="text-primary">
                      <span v-if="m.invoice_number">NF #{{ m.invoice_number }}<span v-if="m.invoice_serie">/{{ m.invoice_serie }}</span></span>
                      <span v-else>Rascunho #{{ m.invoice_id }}</span>
                    </RouterLink>
                    <span v-else-if="m.source === 'order' && m.order_id">
                      <RouterLink :to="`/orders/${m.order_id}`" class="text-primary">#{{ m.order_platform_id || m.order_id }}</RouterLink>
                      <a v-if="mktUrl(m.order_platform, m.order_platform_id)"
                         :href="mktUrl(m.order_platform, m.order_platform_id)"
                         target="_blank" rel="noopener" class="ml-1"
                         :title="`Abrir venda no ${marketplaceName(m.order_platform)}`">
                        <i class="fas fa-external-link-alt" style="font-size:10px"></i>
                      </a>
                      <span class="text-muted ml-1">· {{ shipmentLabel(m.order_shipment_status) }}</span>
                      <span v-if="m.is_reserved" class="badge badge-warning text-dark ml-1" title="Status handling ou ready_to_ship">reservado</span>
                    </span>
                    <span v-else-if="m.source === 'adjustment'" class="text-muted">
                      {{ m.adjustment_old }} → <strong>{{ m.adjustment_new }}</strong>
                    </span>
                    <span v-if="m.source !== 'order' && m.source !== 'adjustment' && m.invoice_status" class="text-muted ml-1">· {{ statusLabel(m.invoice_status) }}</span>
                  </td>
                  <!-- Coluna CMIG/Produto (só PG) -->
                  <td v-if="productType === 'pg'" style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis"
                      :title="m.source === 'order' && m.origin_kind === 'kit_component' ? m.item_description : ((m.cmig_name || '') + ' · ' + (m.cmig_product_title || ''))">
                    <span v-if="m.source === 'order' && m.origin_kind === 'kit_component'">
                      <i class="fas fa-cube text-muted mr-1"></i>{{ m.item_description }}
                    </span>
                    <template v-else>
                      <span v-if="m.cmig_product_sku"><code>{{ m.cmig_product_sku }}</code></span>
                      <span v-if="m.cmig_name" class="text-muted ml-1">· {{ m.cmig_name }}</span>
                      <span v-if="!m.cmig_product_sku && !m.cmig_name" class="text-muted">—</span>
                    </template>
                  </td>
                  <td style="font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis">
                    <span v-if="m.source === 'order'" :title="m.item_ml_item_id || ''">
                      <code v-if="m.item_ml_item_id">{{ m.item_ml_item_id }}</code>
                      <span v-else class="text-muted">—</span>
                    </span>
                    <span v-else-if="m.source === 'adjustment'" class="text-muted" :title="m.adjustment_reason || ''">
                      <i class="fas fa-user mr-1"></i>{{ m.adjustment_user_name || 'sistema' }}
                    </span>
                    <span v-else :title="m.person_name || ''">{{ m.person_name || '—' }}</span>
                  </td>
                  <!-- Coluna Item (só CMIG) -->
                  <td v-if="productType === 'cmig'" style="max-width:340px;overflow:hidden;text-overflow:ellipsis" :title="m.item_description || ''">
                    <code v-if="m.item_sku">{{ m.item_sku }}</code>
                    <span v-if="m.item_sku && m.item_description"> - </span>
                    <span>{{ m.item_description || '' }}</span>
                  </td>
                  <td class="text-right" :class="m.source === 'inventory' ? 'text-muted' : (m.direction === 'in' ? 'text-success' : (m.source === 'adjustment' ? 'text-muted' : 'text-danger'))">
                    <span v-if="m.source === 'adjustment'" :title="'Ajuste informativo — cache foi sobrescrito de ' + m.adjustment_old + ' para ' + m.adjustment_new">
                      Δ{{ (m.adjustment_new - m.adjustment_old) >= 0 ? '+' : '' }}{{ m.adjustment_new - m.adjustment_old }}
                    </span>
                    <span v-else-if="m.source === 'inventory'" :title="'Inventário ' + (m.inventory_mode === 'baseline' ? 'baseline (reset p/ a contagem)' : 'ajuste (delta congelado)')">
                      {{ m.inventory_mode === 'baseline' ? '=' + m.inventory_counted : ((m.inventory_delta >= 0 ? '+' : '') + m.inventory_delta) }}
                    </span>
                    <template v-else>
                      {{ m.direction === 'in' ? '+' : '−' }}{{ m.qty }}<span v-if="qtySplitAnnotation(m)" class="ml-1" :class="qtySplitClass" :title="qtySplitAnnotation(m, true)">({{ qtySplitAnnotation(m) }})</span>
                    </template>
                  </td>
                  <td class="text-right"><strong>{{ m.running_available }}</strong></td>
                </tr>
                <!-- M8: saldo inicial (fim, DESC) -->
                <tr v-if="filteredMovements.length" class="bg-light">
                  <td :colspan="dataColspan" class="text-right small text-muted">
                    <i class="fas fa-flag mr-1"></i>
                    <strong>Saldo no início do período</strong>
                    <span v-if="startDate">({{ formatBR(startDate) }})</span>
                  </td>
                  <td class="text-right"><strong>{{ data.period_initial_available ?? 0 }}</strong></td>
                </tr>
                <tr v-if="!filteredMovements.length && data.movements.length > 0">
                  <td :colspan="totalColspan" class="text-center text-muted py-3">
                    <i class="fas fa-filter mr-1"></i>Nenhuma movimentação corresponde aos filtros ativos.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- Movimentações FULL (fulfillment ML) — trilha informativa, ciclo próprio -->
          <div v-if="!loading && data && (data.full_movements || []).length" class="mt-4">
            <h6 class="text-muted mb-2" style="font-size:13px">
              <i class="fas fa-warehouse mr-1" style="color:#6f42c1"></i>
              Movimentações no FULL (Fulfillment)
              <small class="text-muted">· estoque do ML, não entra no saldo local</small>
            </h6>
            <div class="table-responsive" style="max-height:30vh">
              <table class="table table-sm table-hover mb-0" style="font-size:12px;white-space:nowrap">
                <thead class="thead-light">
                  <tr>
                    <th>Data</th>
                    <th>Evento</th>
                    <th>Venda / Marketplace</th>
                    <th>NF-e</th>
                    <th class="text-right">Qtd</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(f, i) in data.full_movements" :key="'full-'+i">
                    <td>{{ formatDateTimeOneLine(f.date) }}</td>
                    <td>
                      <span class="badge" :class="fullBadgeClass(f.movement_type)">{{ f.label }}</span>
                    </td>
                    <td>
                      <template v-if="f.order_id">
                        <span v-if="f.order_platform === 'mercadolivre'" class="badge mr-1" style="background:#FFE600;color:#3F3F3F;font-weight:bold">ML</span>
                        <span v-else-if="f.order_platform === 'shopee'" class="badge mr-1" style="background:#EE4D2D;color:#fff;font-weight:bold">Shopee</span>
                        <RouterLink :to="`/orders/${f.order_id}`" class="text-primary">#{{ f.order_platform_id || f.order_id }}</RouterLink>
                        <a v-if="f.marketplace_url" :href="f.marketplace_url" target="_blank" rel="noopener" class="ml-1" :title="`Abrir venda no ${marketplaceName(f.order_platform)}`">
                          <i class="fas fa-external-link-alt" style="font-size:10px"></i>
                        </a>
                      </template>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td>
                      <RouterLink v-if="f.invoice_id" :to="`/fiscal/invoices/${f.invoice_id}`" class="text-primary">
                        <span v-if="f.invoice_number">NF #{{ f.invoice_number }}</span>
                        <span v-else>Rascunho #{{ f.invoice_id }}</span>
                      </RouterLink>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td class="text-right" :class="f.delta >= 0 ? 'text-success' : 'text-danger'">
                      <strong>{{ f.delta >= 0 ? '+' : '−' }}{{ Math.abs(f.delta) }}</strong>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <small class="text-muted d-block mt-2">
            <i class="fas fa-info-circle mr-1"></i>
            <strong>Saldo em estoque</strong> reflete NFes (entrada − saída não-fiscalizada) − pedidos shipped/delivered.
            <strong>Pedidos sem NFe regularizada</strong> ainda contam no saldo (não duplica com NFe quando esta for emitida).
            <span v-if="productType === 'pg' && data && data.linked_cmig_count > 0">
              Este PG agrega NFes de {{ data.linked_cmig_count }} CMIG(s) vinculado(s).
            </span>
            <span v-else-if="productType === 'cmig' && data && data.has_pg_link">
              Pedidos que excedem o estoque CMIG (overflow) são debitados do PG vinculado (#{{ data.pg_product_id }}).
            </span>
            <span v-else-if="productType === 'cmig'">Este produto não tem vínculo com PG — overflow não aplicável.</span>
          </small>
        </div>

        <div class="modal-footer">
          <button class="btn btn-warning" @click="recalc" :disabled="recalcLoading">
            <i class="fas mr-1" :class="recalcLoading ? 'fa-spinner fa-spin' : 'fa-calculator'"></i>
            Recalcular Estoque
          </button>
          <button class="btn btn-secondary" @click="closeModal">Fechar</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'
import { formatDateTime, brToday, brDaysAgo } from '@/utils/formatters'

const props = defineProps({
  show: { type: Boolean, required: true },
  productType: { type: String, required: true, validator: (v) => ['pg', 'cmig'].includes(v) },
  productId: { type: Number, default: null },
  productSku: { type: String, default: '' },
  productTitle: { type: String, default: '' },
  cmigId: { type: [Number, String], default: null },
})

const emit = defineEmits(['update:show', 'recalculated'])

const toast = useToast()

const loading = ref(false)
const recalcLoading = ref(false)
const data = ref(null)
const startDate = ref('')
const endDate = ref('')

const mlLogoError = ref(false)
const mlLogoUrl = '/marketplaces/mercadolivre-icon.png'

// Filtros M7
const filters = reactive({
  nfeIn: true,
  nfeOut: true,
  ordersDefinitive: true,
  reserved: true,
  adjustments: true,
})

// IDs únicos para checkbox (evita colisão entre instâncias)
const instanceId = Math.random().toString(36).slice(2, 8)
function fId(name) { return `sm-${instanceId}-${name}` }

// Quando abre o modal, reseta para últimos 30 dias e carrega
watch(() => props.show, (val) => {
  if (val) {
    startDate.value = isoDaysAgo(30)
    endDate.value = todayIso()
    data.value = null
    load()
  }
})

const cacheBalance = computed(() => {
  if (!data.value) return 0
  return props.productType === 'pg' ? data.value.current_balance_pg : data.value.current_balance_nfe
})

const reserved = computed(() => {
  if (!data.value) return 0
  return props.productType === 'pg' ? data.value.reserved_in_pending_orders_pg : data.value.reserved_in_pending_orders
})

const movedNoNfe = computed(() => {
  if (!data.value) return 0
  return props.productType === 'pg' ? data.value.moved_in_orders_no_nfe_pg : data.value.moved_in_orders_no_nfe
})

const cacheInSync = computed(() => {
  if (!data.value) return true
  return data.value.calculated_balance === cacheBalance.value
})

const periodNet = computed(() => {
  if (!data.value) return 0
  return (data.value.period_in_nfe || 0) - (data.value.period_out_nfe || 0) - (data.value.period_out_orders || 0)
})

const periodNetSign = computed(() => (periodNet.value >= 0 ? '+' : ''))

const filteredMovements = computed(() => {
  if (!data.value) return []
  return (data.value.movements || []).filter((m) => {
    if (m.source === 'nfe_in') return filters.nfeIn
    if (m.source === 'nfe_out') return filters.nfeOut
    if (m.source === 'adjustment') return filters.adjustments
    if (m.source === 'order') {
      if (m.is_reserved) return filters.reserved
      return filters.ordersDefinitive
    }
    return true
  })
})

// Colspan dinâmico: PG tem 6 cols antes do Saldo, CMIG tem 6 também (Item substitui CMIG/Produto)
const dataColspan = 6
const totalColspan = 7

const qtySplitClass = computed(() => props.productType === 'cmig' ? 'text-secondary' : 'text-info')

function qtySplitAnnotation(m, full = false) {
  if (m.source !== 'order') return null
  if (props.productType === 'cmig' && m.qty_to_pg > 0) {
    return full ? `${m.qty_to_pg} em overflow PG` : `+${m.qty_to_pg} PG`
  }
  if (props.productType === 'pg' && m.qty_to_cmig > 0) {
    return full ? `${m.qty_to_cmig} em CMIG` : `${m.qty_to_cmig} CMIG`
  }
  return null
}

function closeModal() { emit('update:show', false) }

function mktUrl(platform, platformOrderId) {
  if (platform === 'mercadolivre' && platformOrderId) {
    return `https://www.mercadolivre.com.br/vendas/${platformOrderId}/detalhe`
  }
  return null
}
function marketplaceName(p) {
  return { mercadolivre: 'Mercado Livre', shopee: 'Shopee' }[p] || 'marketplace'
}
function fullBadgeClass(type) {
  const map = {
    full_in: 'badge-success',
    full_out: 'badge-danger',
    full_reserve: 'badge-warning text-dark',
    full_unreserve: 'badge-info',
    full_return_out: 'badge-secondary',
  }
  return map[type] || 'badge-light'
}

// "Hoje"/N dias atrás no fuso do Brasil (não usa toISOString=UTC, que desloca perto da meia-noite).
function todayIso() { return brToday() }
function isoDaysAgo(days) { return brDaysAgo(days) }

function setPeriodPreset(days) {
  if (days === null) {
    startDate.value = ''
    endDate.value = ''
  } else {
    startDate.value = isoDaysAgo(days)
    endDate.value = todayIso()
  }
  load()
}

function endpointUrl(action) {
  if (props.productType === 'pg') {
    return action === 'recalc'
      ? `/pg/${props.productId}/recalculate-stock`
      : `/pg/${props.productId}/stock-movements`
  }
  return action === 'recalc'
    ? `/cmigs/${props.cmigId}/products/${props.productId}/recalculate-stock`
    : `/cmigs/${props.cmigId}/products/${props.productId}/stock-movements`
}

async function load() {
  if (!props.productId) return
  loading.value = true
  try {
    const params = {}
    if (startDate.value) params.start_date = startDate.value
    if (endDate.value) params.end_date = endDate.value
    const res = await api.get(endpointUrl('movements'), { params })
    data.value = res.data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar movimentações.')
  } finally {
    loading.value = false
  }
}

async function recalc() {
  if (!props.productId) return
  recalcLoading.value = true
  try {
    const res = await api.post(endpointUrl('recalc'))
    const { old_stock, new_stock, delta } = res.data
    const sign = delta > 0 ? '+' : ''
    toast.success(`Estoque recalculado: ${old_stock} → ${new_stock} (${sign}${delta})`)
    emit('recalculated', { old_stock, new_stock, delta })
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao recalcular estoque.')
  } finally {
    recalcLoading.value = false
  }
}

function adjustmentLabel(m) {
  const kind = m.adjustment_kind || m.origin_kind
  if (kind === 'manual_override') return 'Ajuste Manual'
  if (kind === 'recompute') return 'Recálculo'
  if (kind === 'batch_recompute') return 'Recálculo em Lote'
  return 'Ajuste'
}

function adjustmentTooltip(m) {
  const parts = []
  parts.push(`${m.adjustment_old || 0} → ${m.adjustment_new || 0}`)
  if (m.adjustment_user_name) parts.push(`Por: ${m.adjustment_user_name}`)
  if (m.adjustment_reason) parts.push(`Motivo: ${m.adjustment_reason}`)
  return parts.join(' | ')
}

function formatDateTimeOneLine(iso) { return formatDateTime(iso) }  // fonte única (horário do Brasil)

function formatBR(iso) {
  if (!iso) return '—'
  const [y, mo, d] = String(iso).split('-')
  return `${d}/${mo}/${y}`
}

function shipmentLabel(s) {
  const labels = {
    handling: 'em separação',
    ready_to_ship: 'pronto para envio',
    shipped: 'enviado',
    delivered: 'entregue',
    cancelled: 'cancelado',
  }
  return labels[s] || s || ''
}

function statusLabel(s) {
  const labels = {
    authorized: 'autorizada',
    finalized: 'finalizada',
    queued: 'na fila',
    processing: 'processando',
    cancelled: 'cancelada',
    denied: 'denegada',
    rejected: 'rejeitada',
  }
  return labels[s] || s || ''
}

function csvCell(v) {
  if (v === null || v === undefined) return ''
  const s = String(v).replace(/"/g, '""')
  return /[",;\n]/.test(s) ? `"${s}"` : s
}

function exportCsv() {
  const rows = filteredMovements.value
  if (!rows.length) return
  const isCmig = props.productType === 'cmig'
  const header = isCmig
    ? ['Data', 'Origem', 'Sub-classificacao', 'Referencia', 'Pessoa/Anuncio', 'Item', 'Quantidade', 'Saldo Disponivel']
    : ['Data', 'Origem', 'Sub-classificacao', 'Referencia', 'Pessoa/Anuncio', 'Quantidade', 'Saldo Disponivel']
  const lines = [header.join(';')]
  for (const m of rows) {
    let origem = ''
    let sub = ''
    let ref = ''
    let pessoa = ''
    let qty = ''
    if (m.source === 'nfe_in') origem = 'NFe Entrada'
    else if (m.source === 'nfe_out') origem = 'NFe Saida'
    else if (m.source === 'adjustment') origem = adjustmentLabel(m)
    else if (m.source === 'order') origem = m.order_platform === 'mercadolivre' ? 'Pedido ML' : (m.order_platform === 'shopee' ? 'Pedido Shopee' : 'Pedido')
    if (m.source === 'order' && m.origin_kind === 'direct_pg') sub = 'Direto PG'
    else if (m.source === 'order' && m.origin_kind === 'overflow_cmig') sub = 'Overflow CMIG'
    else if (m.source === 'order' && m.origin_kind === 'kit_component') sub = 'Kit Componente'
    if (m.source === 'order') {
      ref = '#' + (m.order_platform_id || m.order_id || '')
      pessoa = m.item_ml_item_id || ''
    } else if (m.source === 'adjustment') {
      ref = `${m.adjustment_old} -> ${m.adjustment_new}`
      pessoa = m.adjustment_user_name || ''
    } else {
      ref = m.invoice_number ? `NF ${m.invoice_number}/${m.invoice_serie || ''}` : (m.invoice_id ? `Rascunho ${m.invoice_id}` : '')
      pessoa = m.person_name || ''
    }
    if (m.source === 'adjustment') {
      const delta = (m.adjustment_new || 0) - (m.adjustment_old || 0)
      qty = (delta >= 0 ? '+' : '') + delta
    } else {
      qty = (m.direction === 'in' ? '+' : '-') + m.qty
    }
    if (isCmig) {
      const itemDesc = [m.item_sku, m.item_description].filter(Boolean).join(' - ')
      lines.push([m.date, origem, sub, ref, pessoa, itemDesc, qty, m.running_available ?? ''].map(csvCell).join(';'))
    } else {
      lines.push([m.date, origem, sub, ref, pessoa, qty, m.running_available ?? ''].map(csvCell).join(';'))
    }
  }
  const csv = '﻿' + lines.join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const period = `${startDate.value || 'inicio'}_${endDate.value || 'fim'}`
  link.href = url
  link.download = `movimentacao_${props.productSku || props.productType}_${period}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
</script>
