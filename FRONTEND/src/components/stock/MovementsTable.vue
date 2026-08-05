<template>
  <div class="table-responsive">
    <table class="table table-sm table-hover mb-0" style="white-space:nowrap;font-size:13px">
      <thead class="thead-light">
        <tr>
          <th>Data</th>
          <th>Origem</th>
          <th>Referência</th>
          <th>CFOP</th>
          <th class="text-right">Qtd</th>
          <th v-if="showRunning" class="text-right">Saldo disp.</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="!movements.length">
          <td :colspan="showRunning ? 6 : 5" class="text-center text-muted py-3">
            <i class="fas fa-inbox mr-1"></i>{{ emptyText }}
          </td>
        </tr>
        <tr v-for="(m, idx) in movements" :key="idx">
          <td style="font-size:12px">{{ fmt(m.date) }}</td>
          <td style="white-space:normal">
            <span v-if="m.source === 'nfe_in'" class="badge badge-success"><i class="fas fa-file-invoice mr-1"></i>NF-e entrada</span>
            <span v-else-if="m.source === 'nfe_out'" class="badge badge-danger"><i class="fas fa-file-invoice mr-1"></i>NF-e saída</span>
            <span v-else-if="m.source === 'inventory'" class="badge" style="background:#20c997;color:#fff"><i class="fas fa-clipboard-check mr-1"></i>Inventário {{ m.inventory_mode === 'baseline' ? '(baseline)' : '(ajuste)' }}</span>
            <span v-else-if="m.source === 'adjustment'" class="badge badge-dark" :title="m.adjustment_reason || ''"><i class="fas fa-tools mr-1"></i>{{ adjLabel(m) }}</span>
            <template v-else>
              <span v-if="m.order_platform === 'mercadolivre'" class="badge" style="background:#FFE600;color:#3F3F3F;font-weight:bold"><i class="fas fa-shopping-bag mr-1"></i>ML</span>
              <span v-else-if="m.order_platform === 'shopee'" class="badge" style="background:#EE4D2D;color:#fff;font-weight:bold"><i class="fas fa-shopping-bag mr-1"></i>Shopee</span>
              <span v-else class="badge badge-secondary"><i class="fas fa-shopping-bag mr-1"></i>{{ m.order_platform || 'Pedido' }}</span>
              <span v-if="m.origin_kind === 'overflow_cmig'" class="badge badge-warning text-dark ml-1" style="font-size:10px" title="Consumiu PG por overflow do CMIG">Overflow</span>
              <span v-else-if="m.origin_kind === 'kit_component'" class="badge badge-secondary ml-1" style="font-size:10px" title="Componente de kit">Kit</span>
              <span v-if="m.order_shipping_mode === 'full'" class="badge ml-1" style="background:#00a650;color:#fff;font-size:10px" title="Venda entregue pelo FULL (fulfillment do ML)">FULL</span>
              <span v-else class="badge badge-info ml-1" style="font-size:10px" :title="'Venda entregue pelo galpão' + (m.order_shipping_mode ? ' (' + shipModeLabel(m.order_shipping_mode) + ')' : '')">GALPÃO<span v-if="m.order_shipping_mode"> · {{ shipModeLabel(m.order_shipping_mode) }}</span></span>
              <span v-if="m.is_reserved" class="badge badge-warning text-dark ml-1" style="font-size:10px" title="Pedido a expedir (handling/ready_to_ship)">reservado</span>
            </template>
          </td>
          <td style="font-size:12px">
            <RouterLink v-if="(m.source === 'nfe_in' || m.source === 'nfe_out') && m.invoice_id" :to="`/fiscal/invoices/${m.invoice_id}`" class="text-primary">
              <span v-if="m.invoice_number">NF #{{ m.invoice_number }}<span v-if="m.invoice_serie">/{{ m.invoice_serie }}</span></span>
              <span v-else>Rascunho #{{ m.invoice_id }}</span>
            </RouterLink>
            <span v-else-if="m.source === 'order' && m.order_id">
              <RouterLink :to="`/orders/${m.order_id}`" class="text-primary">#{{ m.order_platform_id || m.order_id }}</RouterLink>
              <a v-if="mktUrl(m)" :href="mktUrl(m)" target="_blank" rel="noopener" class="ml-1" title="Abrir venda no marketplace"><i class="fas fa-external-link-alt" style="font-size:10px"></i></a>
              <span v-if="m.order_shipment_status" class="text-muted ml-1">· {{ shipLabel(m.order_shipment_status) }}</span>
              <span v-if="m.order_invoice_number" class="text-muted ml-1" title="NF-e de saída desta venda"><i class="fas fa-file-invoice mr-1"></i>NF #{{ m.order_invoice_number }}<span v-if="m.order_invoice_serie">/{{ m.order_invoice_serie }}</span></span>
            </span>
            <span v-else-if="m.source === 'inventory'" class="text-muted">Inventário #{{ m.inventory_number || m.inventory_id }}<span v-if="m.inventory_counted != null"> · contado {{ m.inventory_counted }}</span></span>
            <span v-else-if="m.source === 'adjustment'" class="text-muted">{{ m.adjustment_old }} → <strong>{{ m.adjustment_new }}</strong></span>
            <span v-else class="text-muted">—</span>
            <span v-if="m.person_name" class="text-muted ml-1">· {{ m.person_name }}</span>
            <span v-else-if="m.item_ml_item_id" class="text-muted ml-1">· <code>{{ m.item_ml_item_id }}</code></span>
          </td>
          <td style="font-size:12px" class="text-muted">{{ m.cfop || '—' }}</td>
          <td class="text-right" :class="qtyClass(m)">
            <span v-if="m.source === 'adjustment'">Δ{{ (m.adjustment_new - m.adjustment_old) >= 0 ? '+' : '' }}{{ m.adjustment_new - m.adjustment_old }}</span>
            <span v-else-if="m.source === 'inventory'" :title="'Contagem: ' + m.inventory_counted">{{ m.inventory_mode === 'baseline' ? '=' + m.inventory_counted : ((m.inventory_delta >= 0 ? '+' : '') + m.inventory_delta) }}</span>
            <span v-else>{{ m.direction === 'in' ? '+' : '−' }}{{ m.qty }}</span>
          </td>
          <td v-if="showRunning" class="text-right"><strong>{{ m.running_available != null ? m.running_available : '—' }}</strong></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'
import { formatDateTime } from '@/utils/formatters'

defineProps({
  movements: { type: Array, default: () => [] },
  showRunning: { type: Boolean, default: true },
  emptyText: { type: String, default: 'Nenhuma movimentação no período.' },
})

function fmt(iso) { return formatDateTime(iso) }

function adjLabel(m) {
  const k = m.adjustment_kind
  if (k === 'manual_override') return 'Ajuste manual'
  if (k === 'recompute') return 'Recálculo'
  if (k === 'batch_recompute') return 'Recálculo em lote'
  return 'Ajuste'
}

function shipLabel(s) {
  return ({ handling: 'em separação', ready_to_ship: 'pronto p/ envio', shipped: 'enviado', delivered: 'entregue', cancelled: 'cancelado' })[s] || s || ''
}

function shipModeLabel(mode) {
  return ({ flex: 'Flex', agencia: 'Agência', correios: 'Correios', me1: 'Envios ML', me2: 'Envios ML', drop_off: 'Correios', xd_drop_off: 'Agência', self_service: 'Flex', custom: 'Combinado' })[mode] || mode || 'Envio'
}

function mktUrl(m) {
  if (m.order_platform === 'mercadolivre' && m.order_platform_id) {
    return `https://www.mercadolivre.com.br/vendas/${m.order_platform_id}/detalhe`
  }
  return null
}

function qtyClass(m) {
  if (m.source === 'adjustment' || m.source === 'inventory') return 'text-muted'
  return m.direction === 'in' ? 'text-success' : 'text-danger'
}
</script>
