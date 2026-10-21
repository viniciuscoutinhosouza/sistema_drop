<script setup>
// Checkout PÚBLICO da venda manual (Fase 3, ADR-0033). Página sem login, acessível só pelo
// token do pedido. Usa fetch() de propósito: o composable useApi injeta JWT e redireciona
// para /login em 401 — comportamento errado para uma página pública sem sessão.
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const token = route.params.token

const loading = ref(true)
const notFound = ref(false)
const data = ref(null)
const billingType = ref('PIX')
const busy = ref(false)
const errorMsg = ref('')
const copied = ref(false)

const paid = computed(() => data.value?.payment_status === 'paid')
const review = computed(() => data.value?.needs_price_review)
const charge = computed(() => data.value?.charge || null)

function money(v) {
  return (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

async function call(method, path, body) {
  const res = await fetch(`/api/v1/public/checkout/${token}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 404) {
    notFound.value = true
    throw new Error('not_found')
  }
  const json = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(json.detail || 'Erro ao processar')
  return json
}

async function load() {
  loading.value = true
  try {
    data.value = await call('GET', '')
  } catch (e) {
    if (e.message !== 'not_found') errorMsg.value = e.message
  } finally {
    loading.value = false
  }
}

async function changeQty(item, delta) {
  if (paid.value || busy.value) return
  const next = (item.quantity || 0) + delta
  if (next < 0) return
  busy.value = true
  errorMsg.value = ''
  try {
    data.value = await call('PATCH', `/items/${item.id}`, { quantity: next })
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    busy.value = false
  }
}

async function removeItem(item) {
  if (paid.value || busy.value) return
  busy.value = true
  errorMsg.value = ''
  try {
    data.value = await call('PATCH', `/items/${item.id}`, { quantity: 0 })
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    busy.value = false
  }
}

async function pay() {
  if (busy.value) return
  busy.value = true
  errorMsg.value = ''
  try {
    data.value = await call('POST', '/pay', { billing_type: billingType.value })
  } catch (e) {
    errorMsg.value = e.message
  } finally {
    busy.value = false
  }
}

async function copyPix() {
  try {
    await navigator.clipboard.writeText(charge.value.pix_payload)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch (e) {
    errorMsg.value = 'Não foi possível copiar'
  }
}

onMounted(load)
</script>

<template>
  <div class="checkout-wrap">
    <div class="checkout-card">
      <div class="checkout-head">
        <h1>Seu pedido</h1>
      </div>

      <div v-if="loading" class="text-center p-4 text-muted">Carregando…</div>

      <div v-else-if="notFound" class="text-center p-4">
        <i class="fas fa-link-slash fa-2x text-muted mb-2"></i>
        <p class="mb-0">Link inválido ou expirado. Peça um novo ao vendedor.</p>
      </div>

      <template v-else-if="data">
        <p class="text-muted small mb-3">Olá, {{ data.buyer_name }}. Confira os itens abaixo.</p>

        <div v-if="paid" class="alert alert-success">
          <i class="fas fa-circle-check me-1"></i> Pagamento confirmado. Obrigado!
        </div>

        <div v-if="review && !paid" class="alert alert-warning">
          <i class="fas fa-triangle-exclamation me-1"></i>
          Você alterou itens com desconto. O vendedor precisa revisar o preço antes de liberar o
          pagamento. Volte em instantes.
        </div>

        <ul class="item-list">
          <li v-for="it in data.items" :key="it.id" class="item">
            <img v-if="it.image_url" :src="it.image_url" :alt="it.title" class="item-thumb" loading="lazy" />
            <div v-else class="item-thumb item-thumb--empty"><i class="fas fa-image"></i></div>
            <div class="item-info">
              <span class="item-title">{{ it.title }}</span>
              <span v-if="it.has_discount" class="badge bg-success ms-1">desconto</span>
              <div class="item-price small text-muted">{{ money(it.unit_price) }} / un.</div>
            </div>
            <div class="item-qty" v-if="data.editable">
              <button class="btn btn-sm btn-outline-secondary" :disabled="busy" @click="changeQty(it, -1)">−</button>
              <span class="qty">{{ it.quantity }}</span>
              <button class="btn btn-sm btn-outline-secondary" :disabled="busy" @click="changeQty(it, 1)">+</button>
              <button class="btn btn-sm btn-outline-danger ms-2" :disabled="busy" @click="removeItem(it)" title="Remover">
                <i class="fas fa-trash"></i>
              </button>
            </div>
            <div class="item-qty" v-else>
              <span class="qty">{{ it.quantity }}×</span>
            </div>
            <div class="item-total">{{ money(it.line_total) }}</div>
          </li>
        </ul>

        <div class="totals">
          <div class="row-line"><span>Itens</span><span>{{ money(data.items_total) }}</span></div>
          <div class="row-line"><span>Frete</span><span>{{ money(data.shipping_cost) }}</span></div>
          <div class="row-line total"><span>Total</span><span>{{ money(data.total) }}</span></div>
        </div>

        <div v-if="errorMsg" class="alert alert-danger py-2 my-2">{{ errorMsg }}</div>

        <!-- Pagamento -->
        <div v-if="!paid" class="pay-box">
          <template v-if="charge">
            <p class="small text-muted mb-2">Cobrança gerada ({{ money(charge.value) }}):</p>
            <a v-if="charge.invoice_url" :href="charge.invoice_url" target="_blank" rel="noopener"
               class="btn btn-primary w-100 mb-2">
              <i class="fas fa-up-right-from-square me-1"></i> Abrir página de pagamento
            </a>
            <a v-if="charge.bank_slip_url" :href="charge.bank_slip_url" target="_blank" rel="noopener"
               class="btn btn-outline-secondary w-100 mb-2">
              <i class="fas fa-barcode me-1"></i> Ver boleto
            </a>
            <button v-if="charge.pix_payload" class="btn btn-outline-secondary w-100" @click="copyPix">
              <i class="fas fa-copy me-1"></i> {{ copied ? 'Copiado!' : 'Copiar Pix copia-e-cola' }}
            </button>
          </template>
          <template v-else>
            <label class="form-label small">Forma de pagamento</label>
            <select v-model="billingType" class="form-select mb-2" :disabled="review">
              <option value="PIX">Pix</option>
              <option value="BOLETO">Boleto</option>
              <option value="UNDEFINED">Deixar o cliente escolher</option>
            </select>
            <button class="btn btn-success w-100" :disabled="busy || review" @click="pay">
              <i class="fas fa-credit-card me-1"></i> Pagar {{ money(data.total) }}
            </button>
          </template>
        </div>
      </template>
    </div>
    <p class="footer-note">Pagamento processado via ASAAS.</p>
  </div>
</template>

<style scoped>
.checkout-wrap {
  min-height: 100vh;
  background: #f4f6f9;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 16px;
}
.checkout-card {
  width: 100%;
  max-width: 460px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  padding: 20px;
}
.checkout-head h1 {
  font-size: 1.25rem;
  margin: 0 0 12px;
}
.item-list {
  list-style: none;
  padding: 0;
  margin: 0 0 12px;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0;
  border-bottom: 1px solid #eee;
}
.item-thumb {
  width: 52px;
  height: 52px;
  object-fit: cover;
  border-radius: 8px;
  flex-shrink: 0;
  background: #f1f1f1;
  border: 1px solid #eee;
}
.item-thumb--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #bbb;
  font-size: 1.1rem;
}
.item-info {
  flex: 1;
  min-width: 0;
}
.item-title {
  font-weight: 500;
}
.item-qty {
  display: flex;
  align-items: center;
  gap: 6px;
}
.item-qty .qty {
  min-width: 22px;
  text-align: center;
}
.item-total {
  min-width: 84px;
  text-align: right;
  font-weight: 600;
}
.totals {
  margin-top: 8px;
}
.row-line {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
}
.row-line.total {
  font-weight: 700;
  font-size: 1.1rem;
  border-top: 2px solid #eee;
  margin-top: 6px;
  padding-top: 8px;
}
.pay-box {
  margin-top: 16px;
}
.footer-note {
  margin-top: 16px;
  color: #9aa0a6;
  font-size: 0.8rem;
}
</style>
