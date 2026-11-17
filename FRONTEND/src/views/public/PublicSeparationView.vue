<template>
  <div class="pub-sep">
    <div v-if="loading" class="text-center p-5"><i class="fas fa-spinner fa-spin fa-2x text-muted"></i></div>

    <div v-else-if="notFound" class="text-center p-5">
      <i class="fas fa-unlink fa-3x text-muted mb-3"></i>
      <h4>Link inválido ou revogado</h4>
      <p class="text-muted">Peça um novo link ao responsável pela gaiola.</p>
    </div>

    <div v-else class="container-fluid py-3">
      <!-- Header -->
      <div class="d-flex align-items-center flex-wrap mb-3 pb-2 border-bottom">
        <h4 class="mb-0 mr-2"><i class="fas fa-shopping-basket text-primary mr-2"></i>Gaiola {{ cart.cart_number }}</h4>
        <span class="badge badge-secondary mr-2">{{ modeLabel }}</span>
        <span class="badge" :class="cart.status === 'separated' ? 'badge-success' : 'badge-warning text-dark'">
          {{ cart.status === 'separated' ? 'Concluída' : 'Em separação' }}
        </span>
        <div class="ml-auto d-flex align-items-center">
          <button class="btn btn-sm btn-outline-primary mr-2" @click="printPicking" :disabled="busy">
            <i class="fas fa-list mr-1"></i> Lista de picking
          </button>
          <button class="btn btn-sm btn-success" @click="conclude" :disabled="busy || cart.status !== 'open'">
            <i class="fas fa-check mr-1"></i> Concluir gaiola
          </button>
        </div>
      </div>

      <div v-if="msg" class="alert py-2" :class="msgErr ? 'alert-danger' : 'alert-success'">{{ msg }}</div>

      <!-- Bipagem automática -->
      <div v-if="cart.mode === 'scan_auto'" class="mb-3 p-3 border rounded" style="background:#fffbea">
        <label class="small font-weight-bold mb-1"><i class="fas fa-bolt mr-1"></i> Bipagem automática — bipe o código, o sistema acha o pedido:</label>
        <input ref="scanAutoInput" v-model="scanAutoCode" @keyup.enter="doScanLocate" :disabled="busy"
               class="form-control form-control-lg" placeholder="Código de barras / EAN" autofocus />
      </div>

      <!-- Pedidos -->
      <div class="table-responsive">
        <table class="table table-sm table-hover align-middle">
          <thead class="thead-light">
            <tr><th>Pedido</th><th>Cliente</th><th>Itens</th><th>Bipagem</th><th class="text-right">Ações</th></tr>
          </thead>
          <tbody>
            <tr v-for="o in cart.orders" :key="o.id" :class="{ 'table-success': o.item_status === 'separated' }">
              <td class="text-nowrap"><strong>#{{ o.id }}</strong><br><small class="text-muted">{{ o.platform }}</small></td>
              <td>{{ o.buyer_name || '—' }}</td>
              <td>
                <div v-for="it in (o.items || [])" :key="it.id" class="small">
                  {{ it.sku || it.title }} <span class="text-muted">×{{ it.quantity }}</span>
                </div>
              </td>
              <td style="min-width:140px">
                <template v-if="o.scan">
                  <span class="badge" :class="o.scan.scanned >= o.scan.expected ? 'badge-success' : 'badge-secondary'">
                    {{ o.scan.scanned }}/{{ o.scan.expected }}
                  </span>
                  <input v-if="cart.mode === 'scan' && o.scan.scanned < o.scan.expected" class="form-control form-control-sm mt-1"
                         placeholder="bipe o item" @keyup.enter="e => doScan(o, e)" :disabled="busy" />
                </template>
                <span v-else class="text-muted small">—</span>
              </td>
              <td class="text-right text-nowrap">
                <button class="btn btn-xs btn-outline-dark mr-1" @click="printLabel(o)" :disabled="busy" title="Etiqueta">
                  <i class="fas fa-tag"></i>
                </button>
                <button class="btn btn-xs btn-outline-dark mr-1" @click="printDanfe(o)" :disabled="busy" title="NF-e (DANFE)">
                  <i class="fas fa-file-invoice"></i>
                </button>
                <label class="btn btn-xs btn-outline-secondary mb-0 mr-1" title="Fotos (opcional)">
                  <i class="fas fa-camera"></i>
                  <input type="file" accept="image/*" capture="environment" multiple class="d-none" @change="e => uploadPhotos(o, e)" />
                </label>
                <span v-if="o.item_status === 'separated'" class="badge badge-success"><i class="fas fa-check"></i></span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="text-muted small"><i class="fas fa-info-circle mr-1"></i> A foto é opcional. Imprima a etiqueta de cada pedido e conclua a gaiola ao terminar.</p>
    </div>
  </div>
</template>

<script setup>
// Página PÚBLICA da gaiola (sem login) — acesso só pelo token. Usa fetch() de propósito (o composable
// useApi injeta JWT e redireciona p/ /login). Reusa os endpoints /api/v1/public/separation/{token}.
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const token = route.params.token
const loading = ref(true)
const notFound = ref(false)
const busy = ref(false)
const cart = ref({})
const msg = ref('')
const msgErr = ref(false)
const scanAutoCode = ref('')
const scanAutoInput = ref(null)

const modeLabel = computed(() =>
  cart.value.mode === 'scan' ? 'Bipagem' : cart.value.mode === 'scan_auto' ? 'Bipagem automática' : 'Manual')

function flash(text, err = false) { msg.value = text; msgErr.value = err; if (!err) setTimeout(() => { if (msg.value === text) msg.value = '' }, 4000) }
const base = `/api/v1/public/separation/${token}`

async function call(method, path, body) {
  const res = await fetch(`${base}${path}`, {
    method, headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 404) { const j = await res.json().catch(() => ({})); if ((j.detail || '').includes('Link')) { notFound.value = true; throw new Error('not_found') } throw new Error(j.detail || 'Não encontrado') }
  const j = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(j.detail || 'Erro ao processar')
  return j
}

async function openBlob(path, method = 'GET', body) {
  const res = await fetch(`${base}${path}`, {
    method, headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 202) { flash('Etiqueta sendo gerada na Shopee — clique de novo em instantes.'); return }
  if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.detail || 'Erro ao gerar o documento') }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

async function load() {
  loading.value = true
  try { cart.value = await call('GET', '') }
  catch (e) { if (e.message !== 'not_found') flash(e.message, true) }
  finally { loading.value = false; if (cart.value.mode === 'scan_auto') await nextTick(() => scanAutoInput.value?.focus()) }
}

async function printPicking() { busy.value = true; try { await openBlob('/picking-list', 'POST') } catch (e) { flash(e.message, true) } finally { busy.value = false } }

async function printLabel(o) {
  busy.value = true
  try {
    if (o.platform === 'shopee') await openBlob(`/orders/${o.id}/shopee-label`)
    else await openBlob(`/labels.pdf?order_id=${o.id}`)
    await load()
  } catch (e) { flash(e.message, true) } finally { busy.value = false }
}
async function printDanfe(o) { busy.value = true; try { await openBlob(`/orders/${o.id}/danfe`) } catch (e) { flash(e.message, true) } finally { busy.value = false } }

async function doScan(o, e) {
  const code = (e.target.value || '').trim(); if (!code) return
  busy.value = true
  try { await call('POST', `/orders/${o.id}/scan`, { code }); e.target.value = ''; await load() }
  catch (err) { flash(err.message, true) } finally { busy.value = false }
}
async function doScanLocate() {
  const code = scanAutoCode.value.trim(); if (!code) return
  busy.value = true
  try { const r = await call('POST', '/scan-locate', { code }); scanAutoCode.value = ''; flash(r.detail || `Bipado no pedido #${r.order_id || ''}`); await load() }
  catch (e) { flash(e.message, true) } finally { busy.value = false; await nextTick(() => scanAutoInput.value?.focus()) }
}

async function uploadPhotos(o, e) {
  const files = [...(e.target.files || [])]; if (!files.length) return
  busy.value = true
  try {
    const fd = new FormData(); files.forEach(f => fd.append('files', f))
    const res = await fetch(`${base}/orders/${o.id}/separate`, { method: 'POST', body: fd })
    const j = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(j.detail || 'Erro ao enviar fotos')
    flash(`${j.fotos || 0} foto(s) — pedido separado`); await load()
  } catch (err) { flash(err.message, true) } finally { busy.value = false; e.target.value = '' }
}

async function conclude() {
  if (!confirm('Concluir a gaiola? Ela ficará pronta para a transportadora.')) return
  busy.value = true
  try { cart.value = await call('POST', '/conclude'); flash('Gaiola concluída!'); await load() }
  catch (e) { flash(e.message, true) } finally { busy.value = false }
}

onMounted(load)
</script>

<style scoped>
.pub-sep { max-width: 1100px; margin: 0 auto; }
.btn-xs { padding: .15rem .4rem; font-size: .75rem; }
</style>
