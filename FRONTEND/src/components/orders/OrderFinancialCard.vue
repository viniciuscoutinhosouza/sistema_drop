<template>
  <div class="financial-card">
    <!-- Venda -->
    <i class="fas fa-shopping-cart text-success" title="Valor da venda"></i>
    <span></span>
    <strong class="text-success amount">{{ formatCurrency(saleAmount) }}</strong>
    <span></span>

    <!-- Frete pago pelo vendedor -->
    <i class="fas fa-truck text-danger" title="Frete pago pelo vendedor (deduzido pelo ML)"></i>
    <span class="text-danger sign">{{ sellerShipping > 0 ? '−' : '' }}</span>
    <span class="amount" :class="sellerShipping > 0 ? 'text-danger' : 'text-muted'">{{ formatCurrency(sellerShipping) }}</span>
    <span></span>

    <!-- Tarifa ML -->
    <i class="fas fa-percentage text-danger" title="Tarifa do Mercado Livre (comissão)"></i>
    <span class="text-danger sign">{{ mlFee > 0 ? '−' : '' }}</span>
    <span class="text-danger amount">{{ formatCurrency(mlFee) }}</span>
    <small v-if="order.ml_fee_pct != null" class="pct">({{ formatPct(order.ml_fee_pct) }})</small>
    <span v-else></span>

    <!-- Custo do produto -->
    <template v-if="productCost > 0">
      <i class="fas fa-box text-danger" title="Custo do produto"></i>
      <span class="text-danger sign">−</span>
      <span class="text-danger amount">{{ formatCurrency(productCost) }}</span>
      <span></span>
    </template>

    <!-- Divisor -->
    <div class="divider"></div>

    <!-- Lucro Bruto -->
    <i class="fas fa-wallet" :class="profitColor" title="Lucro bruto (venda − frete − tarifa − custo)"></i>
    <span></span>
    <strong class="amount" :class="profitColor">{{ formatCurrency(grossProfit) }}</strong>
    <small v-if="grossProfitPct != null" class="pct">({{ formatPct(grossProfitPct) }})</small>
    <span v-else></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatCurrency } from '@/utils/formatters'

const props = defineProps({
  order: { type: Object, required: true },
})

const saleAmount     = computed(() => Number(props.order.sale_amount ?? 0))
const sellerShipping = computed(() => Number(props.order.seller_shipping_cost ?? 0))
const mlFee          = computed(() => Number(props.order.ml_fee ?? props.order.platform_fee ?? 0))
const productCost    = computed(() => Number(props.order.product_cost ?? 0))
const grossProfit    = computed(() => {
  if (props.order.gross_profit != null) return Number(props.order.gross_profit)
  return saleAmount.value - sellerShipping.value - mlFee.value - productCost.value
})
const grossProfitPct = computed(() => {
  if (props.order.gross_profit_pct != null) return Number(props.order.gross_profit_pct)
  return saleAmount.value > 0 ? (grossProfit.value / saleAmount.value * 100) : null
})

function formatPct(v) {
  if (v == null) return ''
  return `${Number(v).toFixed(2).replace('.', ',')} %`
}

const profitColor = computed(() => {
  const v = grossProfit.value
  if (v < 0) return 'text-danger'
  if (saleAmount.value > 0 && v < saleAmount.value * 0.1) return 'text-warning'
  return 'text-primary'
})
</script>

<style scoped>
.financial-card {
  display: grid;
  grid-template-columns: 18px 10px max-content auto;
  align-items: baseline;
  column-gap: .35rem;
  row-gap: .2rem;
  font-size: .88rem;
  line-height: 1.3;
  margin-right: .75rem;
}
.financial-card > i {
  text-align: center;
  font-size: .9rem;
}
.amount {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.sign {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.pct {
  font-size: .72rem;
  color: #6c757d;
  white-space: nowrap;
  margin-left: .4rem;
}
.divider {
  grid-column: 1 / -1;
  border-top: 1px solid #e9ecef;
  margin: .1rem 0 0 0;
}
</style>
