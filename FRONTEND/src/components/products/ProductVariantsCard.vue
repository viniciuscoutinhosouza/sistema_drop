<template>
  <div>
    <div class="card">
      <div class="card-header d-flex align-items-center justify-content-between">
        <h3 class="card-title mb-0"><i class="fas fa-th-large mr-2"></i>Variações</h3>
        <button class="btn btn-sm btn-success" @click="openModal(null)">
          <i class="fas fa-plus mr-1"></i>Adicionar Variação
        </button>
      </div>
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-3">
          <i class="fas fa-spinner fa-spin"></i> Carregando...
        </div>
        <div v-else-if="variants.length === 0" class="text-center text-muted py-4">
          Nenhuma variação cadastrada. Clique em "Adicionar Variação" para começar.
        </div>
        <table v-else class="table table-sm table-hover mb-0">
          <thead>
            <tr>
              <th>SKU</th>
              <th>Nome</th>
              <th>Cor</th>
              <th>Tamanho</th>
              <th>Voltagem</th>
              <th>Estoque</th>
              <th>Mod. Preço</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="v in variants" :key="v.id">
              <td><code>{{ v.sku }}</code></td>
              <td>{{ v.variant_name || '—' }}</td>
              <td>{{ v.color || '—' }}</td>
              <td>{{ v.size_label || '—' }}</td>
              <td>{{ v.voltage || '—' }}</td>
              <td>
                <span :class="['badge', stockBadgeClass(v.stock_quantity)]">
                  {{ v.stock_quantity }}
                </span>
              </td>
              <td>{{ v.price_modifier > 0 ? '+' : '' }}{{ formatCurrency(v.price_modifier) }}</td>
              <td class="text-right pr-2">
                <div class="btn-group btn-group-sm">
                  <button class="btn btn-outline-primary" @click="openModal(v)" title="Editar">
                    <i class="fas fa-edit"></i>
                  </button>
                  <button class="btn btn-outline-danger" @click="deleteVariant(v)" title="Excluir">
                    <i class="fas fa-trash"></i>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showModal" class="modal fade show d-block" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ form.id ? 'Editar' : 'Nova' }} Variação</h5>
            <button class="close" @click="showModal=false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div v-if="error" class="alert alert-danger py-1">{{ error }}</div>
            <div class="row">
              <div class="col-md-6 form-group">
                <label>SKU <span class="text-danger">*</span></label>
                <input v-model="form.sku" class="form-control" :disabled="!!form.id" placeholder="SKU-001-AZUL-P" />
              </div>
              <div class="col-md-6 form-group">
                <label>Nome da Variação</label>
                <input v-model="form.variant_name" class="form-control" placeholder="Ex: Azul P" />
              </div>
            </div>
            <div class="row">
              <div class="col-md-4 form-group">
                <label>Cor</label>
                <input v-model="form.color" class="form-control" placeholder="Azul" />
              </div>
              <div class="col-md-4 form-group">
                <label>Tamanho</label>
                <input v-model="form.size_label" class="form-control" placeholder="P / M / G / 42" />
              </div>
              <div class="col-md-4 form-group">
                <label>Voltagem</label>
                <input v-model="form.voltage" class="form-control" placeholder="110V / 220V / Bivolt" />
              </div>
            </div>
            <div class="row">
              <div class="col-md-6 form-group">
                <label>Estoque</label>
                <input v-model.number="form.stock_quantity" type="number" min="0" class="form-control" />
              </div>
              <div class="col-md-6 form-group">
                <label>Modificador de Preço (R$)</label>
                <input v-model.number="form.price_modifier" type="number" step="0.01" class="form-control" placeholder="0.00" />
              </div>
            </div>
            <div class="form-group">
              <label>Atributos Extras <small class="text-muted">(JSON: {"material":"algodão"})</small></label>
              <input v-model="form.attributes_json" class="form-control" placeholder='{"material":"algodão"}' />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showModal=false">Cancelar</button>
            <button class="btn btn-primary" @click="save" :disabled="saving">
              <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>Salvar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  baseUrl: { type: String, required: true },
})

const toast = useToast()

const variants  = ref([])
const loading   = ref(false)
const showModal = ref(false)
const error     = ref('')
const saving    = ref(false)
const form      = ref({})

function formatCurrency(v) {
  return Number(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function stockBadgeClass(qty) {
  if (qty <= 0) return 'badge-danger'
  if (qty <= 4) return 'badge-warning'
  return 'badge-success'
}

async function load() {
  if (!props.baseUrl) return
  loading.value = true
  try {
    const { data } = await api.get(props.baseUrl)
    variants.value = data
  } catch {
    // silencioso — variantes são opcionais
  } finally {
    loading.value = false
  }
}

function openModal(variant) {
  error.value = ''
  form.value = variant
    ? { ...variant }
    : { sku: '', variant_name: '', color: '', size_label: '', voltage: '', stock_quantity: 0, price_modifier: 0, attributes_json: '' }
  showModal.value = true
}

async function save() {
  error.value = ''
  if (!form.value.sku?.trim()) { error.value = 'SKU é obrigatório'; return }
  saving.value = true
  try {
    if (form.value.id) {
      await api.put(`${props.baseUrl}/${form.value.id}`, form.value)
      toast.success('Variação atualizada!')
    } else {
      await api.post(props.baseUrl, form.value)
      toast.success('Variação adicionada!')
    }
    showModal.value = false
    await load()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar variação.'
  } finally {
    saving.value = false
  }
}

async function deleteVariant(v) {
  if (!confirm(`Excluir variação ${v.sku}?`)) return
  try {
    await api.delete(`${props.baseUrl}/${v.id}`)
    toast.success('Variação excluída!')
    await load()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir variação.')
  }
}

watch(() => props.baseUrl, load, { immediate: true })
</script>
