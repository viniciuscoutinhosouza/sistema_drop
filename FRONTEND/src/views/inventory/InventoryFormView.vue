<template>
  <div>
    <!-- Cabeçalho -->
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0">
        <i class="fas fa-clipboard-list mr-2 text-success"></i>
        <span v-if="isNew">Novo Inventário</span>
        <span v-else>Inventário #{{ header.number }}</span>
      </h5>
      <RouterLink to="/inventario" class="btn btn-outline-secondary btn-sm">
        <i class="fas fa-arrow-left mr-1"></i> Voltar
      </RouterLink>
    </div>

    <!-- ETAPA 1: criação -->
    <div v-if="isNew" class="card">
      <div class="card-body">
        <div v-if="error" class="alert alert-danger">{{ error }}</div>
        <div class="row">
          <div class="col-md-4 form-group">
            <label>Modo do inventário <span class="text-danger">*</span></label>
            <select v-model="newForm.mode" class="form-control">
              <option value="baseline">Baseline (a contagem vira a verdade)</option>
              <option value="adjustment">Ajuste (gera delta sobre o saldo)</option>
            </select>
            <small class="text-muted">
              <strong>Baseline</strong>: o saldo é redefinido para o contado na data.
              <strong>Ajuste</strong>: soma a diferença (contado − sistema) ao saldo.
            </small>
          </div>
          <div class="col-md-4 form-group">
            <label>Catálogo <span class="text-danger">*</span></label>
            <select v-model="newForm.catalog_type" class="form-control">
              <option value="pg">Produto Geral (PG)</option>
              <option value="cmig">Conta CMIG</option>
            </select>
          </div>
          <div v-if="newForm.catalog_type === 'cmig'" class="col-md-4 form-group">
            <label>Conta CMIG <span class="text-danger">*</span></label>
            <select v-model="newForm.cmig_id" class="form-control">
              <option :value="null">Selecione…</option>
              <option v-for="c in cmigs" :key="c.id" :value="c.id">
                {{ c.name || c.company_name || c.trade_name || `CMIG ${c.id}` }}
              </option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label>Observações</label>
          <textarea v-model="newForm.notes" rows="2" class="form-control" placeholder="Opcional"></textarea>
        </div>
        <button class="btn btn-primary" :disabled="saving || !canCreate" @click="create">
          <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>
          Criar e carregar produtos
        </button>
      </div>
    </div>

    <!-- ETAPA 2: contagem -->
    <template v-else>
      <div v-if="loading" class="text-center py-5">
        <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
      </div>
      <template v-else>
        <!-- Resumo -->
        <div class="card mb-3">
          <div class="card-body py-2">
            <div class="row small">
              <div class="col-md-3">
                <span class="text-muted">Catálogo:</span>
                <span v-if="header.catalog_type === 'pg'" class="badge badge-secondary ml-1">PG</span>
                <span v-else class="badge badge-info ml-1">CMIG: {{ header.cmig_name || header.cmig_id }}</span>
              </div>
              <div class="col-md-2">
                <span class="text-muted">Modo:</span>
                <span :class="header.mode === 'baseline' ? 'badge badge-primary ml-1' : 'badge badge-warning ml-1'">
                  {{ header.mode === 'baseline' ? 'Baseline' : 'Ajuste' }}
                </span>
              </div>
              <div class="col-md-3">
                <span class="text-muted">Status:</span>
                <span :class="statusBadge(header.status)" class="ml-1">{{ statusLabel(header.status) }}</span>
              </div>
              <div class="col-md-4 text-muted">
                Criado por {{ header.created_by_name || '—' }} em {{ fmt(header.created_at) }}
              </div>
            </div>
            <div v-if="header.finalized_at" class="row small mt-1">
              <div class="col-12 text-muted">
                Finalizado por {{ header.finalized_by_name || '—' }} em {{ fmt(header.finalized_at) }}
              </div>
            </div>
          </div>
        </div>

        <!-- Barra de ações -->
        <div class="d-flex justify-content-between align-items-center mb-2">
          <input v-model="search" class="form-control form-control-sm" style="width:280px"
                 placeholder="Buscar por SKU ou título…" />
          <div v-if="editable">
            <button class="btn btn-outline-primary btn-sm mr-2" :disabled="saving" @click="saveDraft">
              <i class="fas fa-save mr-1"></i> Salvar rascunho
            </button>
            <button class="btn btn-success btn-sm mr-2" :disabled="saving" @click="finalize">
              <i class="fas fa-check mr-1"></i> Finalizar
            </button>
            <button class="btn btn-outline-danger btn-sm" :disabled="saving" @click="cancel">
              <i class="fas fa-ban mr-1"></i> Cancelar inventário
            </button>
          </div>
        </div>

        <div class="card">
          <div class="card-body p-0">
            <table class="table table-sm table-hover mb-0">
              <thead class="thead-light">
                <tr>
                  <th>SKU</th>
                  <th>Produto</th>
                  <th class="text-center">Sistema</th>
                  <th class="text-center" style="width:120px">Contagem física</th>
                  <th class="text-center">Diferença</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="filtered.length === 0">
                  <td colspan="5" class="text-center text-muted py-4">Nenhum produto.</td>
                </tr>
                <tr v-for="it in filtered" :key="it.id">
                  <td><code>{{ it.sku }}</code></td>
                  <td>{{ it.title }}</td>
                  <td class="text-center text-muted">{{ it.system_qty }}</td>
                  <td class="text-center">
                    <input v-if="editable" type="number" min="0"
                           v-model="it.counted_qty"
                           class="form-control form-control-sm text-center" style="width:90px;margin:0 auto" />
                    <span v-else>{{ it.counted_qty ?? '—' }}</span>
                  </td>
                  <td class="text-center">
                    <span v-if="diff(it) !== null" :class="diffClass(diff(it))">
                      {{ diff(it) > 0 ? '+' : '' }}{{ diff(it) }}
                    </span>
                    <span v-else class="text-muted">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { formatDateTime as fmtBrDateTime } from '@/utils/formatters'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()

const isNew = computed(() => !route.params.id)
const canCreate = computed(() => {
  const u = authStore.user
  if (u?.role === 'admin') return true
  return Array.isArray(u?.menu_permissions) && u.menu_permissions.includes('inventario_criar')
})

const cmigs = ref([])
const newForm = ref({ mode: 'baseline', catalog_type: 'pg', cmig_id: null, notes: '' })
const error = ref('')
const saving = ref(false)

const header = ref({})
const items = ref([])
const loading = ref(false)
const search = ref('')

const editable = computed(() => header.value.status === 'draft' && canCreate.value)

const filtered = computed(() => {
  if (!search.value) return items.value
  const q = search.value.toLowerCase()
  return items.value.filter(i =>
    (i.sku || '').toLowerCase().includes(q) || (i.title || '').toLowerCase().includes(q)
  )
})

onMounted(async () => {
  if (isNew.value) {
    try {
      const { data } = await api.get('/cmigs')
      cmigs.value = Array.isArray(data) ? data : (data?.items || [])
    } catch { cmigs.value = [] }
  } else {
    await loadInventory()
  }
})

async function loadInventory() {
  loading.value = true
  try {
    const { data } = await api.get(`/inventories/${route.params.id}`)
    const { items: its, ...hdr } = data
    header.value = hdr
    items.value = its || []
  } catch {
    toast.error('Erro ao carregar inventário.')
  } finally {
    loading.value = false
  }
}

async function create() {
  error.value = ''
  if (newForm.value.catalog_type === 'cmig' && !newForm.value.cmig_id) {
    error.value = 'Selecione a conta CMIG.'
    return
  }
  saving.value = true
  try {
    const { data } = await api.post('/inventories', {
      mode: newForm.value.mode,
      catalog_type: newForm.value.catalog_type,
      cmig_id: newForm.value.catalog_type === 'cmig' ? newForm.value.cmig_id : null,
      notes: newForm.value.notes || null,
    })
    toast.success('Inventário criado.')
    router.replace(`/inventario/${data.id}`)
  } catch (err) {
    error.value = err.response?.data?.detail || 'Erro ao criar inventário.'
  } finally {
    saving.value = false
  }
}

async function saveDraft() {
  saving.value = true
  try {
    const payload = {
      items: items.value.map(i => ({
        id: i.id,
        counted_qty: i.counted_qty === '' || i.counted_qty === null || i.counted_qty === undefined
          ? null : parseInt(i.counted_qty),
      })),
    }
    await api.put(`/inventories/${route.params.id}/items`, payload)
    toast.success('Contagens salvas.')
  } catch {
    toast.error('Erro ao salvar contagens.')
  } finally {
    saving.value = false
  }
}

async function finalize() {
  const counted = items.value.filter(i => i.counted_qty !== null && i.counted_qty !== '' && i.counted_qty !== undefined)
  if (counted.length === 0) {
    toast.warning('Informe ao menos uma contagem antes de finalizar.')
    return
  }
  if (!confirm(`Finalizar o inventário com ${counted.length} produto(s) contado(s)? Isso ajusta o estoque físico e não pode ser editado depois.`)) return
  saving.value = true
  try {
    await saveDraftSilent()
    await api.post(`/inventories/${route.params.id}/finalize`)
    toast.success('Inventário finalizado e estoque atualizado.')
    await loadInventory()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao finalizar.')
  } finally {
    saving.value = false
  }
}

async function saveDraftSilent() {
  const payload = {
    items: items.value.map(i => ({
      id: i.id,
      counted_qty: i.counted_qty === '' || i.counted_qty === null || i.counted_qty === undefined
        ? null : parseInt(i.counted_qty),
    })),
  }
  await api.put(`/inventories/${route.params.id}/items`, payload)
}

async function cancel() {
  if (!confirm('Cancelar este inventário?')) return
  saving.value = true
  try {
    await api.post(`/inventories/${route.params.id}/cancel`)
    toast.success('Inventário cancelado.')
    await loadInventory()
  } catch {
    toast.error('Erro ao cancelar.')
  } finally {
    saving.value = false
  }
}

function diff(it) {
  if (it.counted_qty === null || it.counted_qty === '' || it.counted_qty === undefined) return null
  return parseInt(it.counted_qty) - (it.system_qty || 0)
}
function diffClass(d) {
  if (d > 0) return 'text-success font-weight-bold'
  if (d < 0) return 'text-danger font-weight-bold'
  return 'text-muted'
}
function statusLabel(s) {
  return { draft: 'Rascunho', finalized: 'Finalizado', cancelled: 'Cancelado' }[s] || s
}
function statusBadge(s) {
  return { draft: 'badge badge-secondary', finalized: 'badge badge-success', cancelled: 'badge badge-danger' }[s] || 'badge badge-light'
}
function fmt(dt) { return fmtBrDateTime(dt) }   // fonte única (horário do Brasil)
</script>
