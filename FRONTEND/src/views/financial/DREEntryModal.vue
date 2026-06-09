<template>
  <div class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title"><i class="fas fa-plus-circle mr-2"></i>Lançamentos manuais — {{ year }}</h5>
          <button type="button" class="close" @click="$emit('close')"><span>&times;</span></button>
        </div>
        <div class="modal-body">
          <!-- Formulário -->
          <form @submit.prevent="save">
            <div class="row">
              <div class="col-md-4">
                <label class="small mb-1">Tipo <span class="text-danger">*</span></label>
                <select v-model="form.category_kind" class="form-control form-control-sm">
                  <option value="entrada">Entrada</option>
                  <option value="custo_operacional">Custo Operacional</option>
                  <option value="custo_fixo">Custo Fixo</option>
                </select>
              </div>
              <div class="col-md-4">
                <label class="small mb-1">Categoria</label>
                <input v-model="form.category" class="form-control form-control-sm" placeholder="Ex: Aluguel, Pró-labore…">
              </div>
              <div class="col-md-4">
                <label class="small mb-1">Valor (R$) <span class="text-danger">*</span></label>
                <input v-model.number="form.amount" type="number" step="0.01" min="0" class="form-control form-control-sm">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-6">
                <label class="small mb-1">Descrição</label>
                <input v-model="form.description" class="form-control form-control-sm">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Mês de referência <span class="text-danger">*</span></label>
                <select v-model.number="form.ref_month" class="form-control form-control-sm">
                  <option v-for="(m, i) in monthsPt" :key="i" :value="i + 1">{{ m }}</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Ano</label>
                <input v-model.number="form.ref_year" type="number" class="form-control form-control-sm">
              </div>
            </div>
            <div class="row mt-2 align-items-end">
              <div class="col-md-4">
                <div class="custom-control custom-switch">
                  <input id="recSwitch" v-model="recurrent" type="checkbox" class="custom-control-input">
                  <label class="custom-control-label small" for="recSwitch">Lançamento recorrente</label>
                </div>
              </div>
              <div class="col-md-4" v-if="recurrent">
                <label class="small mb-1">Nº de parcelas (meses)</label>
                <input v-model.number="form.installments" type="number" min="2" max="120" class="form-control form-control-sm">
              </div>
              <div class="col-md-4 text-right">
                <button type="submit" class="btn btn-sm btn-success" :disabled="saving || !valid">
                  <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
                  {{ editingId ? 'Salvar alterações' : 'Adicionar' }}
                </button>
                <button v-if="editingId" type="button" class="btn btn-sm btn-secondary ml-1" @click="resetForm">
                  Cancelar edição
                </button>
              </div>
            </div>
          </form>

          <hr>

          <!-- Lista -->
          <div class="table-responsive" style="max-height:320px;overflow:auto">
            <table class="table table-sm table-striped mb-0" style="font-size:.82rem">
              <thead>
                <tr>
                  <th>Tipo</th>
                  <th>Descrição / Categoria</th>
                  <th class="text-right">Valor</th>
                  <th class="text-center">Mês</th>
                  <th class="text-center">Parcela</th>
                  <th class="text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!entries.length">
                  <td colspan="6" class="text-center text-muted py-2">Nenhum lançamento neste ano.</td>
                </tr>
                <tr v-for="e in entries" :key="e.id">
                  <td><span class="badge" :class="kindBadge(e.category_kind)">{{ kindLabel(e.category_kind) }}</span></td>
                  <td>{{ e.description || e.category || '—' }}<span v-if="e.category && e.description" class="text-muted"> · {{ e.category }}</span></td>
                  <td class="text-right">{{ formatCurrency(e.amount) }}</td>
                  <td class="text-center">{{ monthsPt[e.ref_month - 1] }}</td>
                  <td class="text-center">
                    <span v-if="e.total_installments">{{ e.installment_no }}/{{ e.total_installments }}</span>
                    <span v-else>—</span>
                  </td>
                  <td class="text-right">
                    <button class="btn btn-xs btn-outline-primary" title="Editar" @click="edit(e)"><i class="fas fa-edit"></i></button>
                    <button class="btn btn-xs btn-outline-danger ml-1" title="Excluir" @click="remove(e)"><i class="fas fa-trash"></i></button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="$emit('close')">Fechar</button>
          <button class="btn btn-primary" @click="$emit('saved')">Aplicar e atualizar DRE</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatCurrency } from '@/utils/formatters'

const props = defineProps({
  cmigId: { type: Number, required: true },
  year: { type: Number, required: true },
})
defineEmits(['close', 'saved'])

const toast = useToast()
const monthsPt = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

const entries = ref([])
const saving = ref(false)
const recurrent = ref(false)
const editingId = ref(null)

const form = reactive({
  category_kind: 'custo_fixo',
  category: '',
  description: '',
  amount: null,
  ref_month: new Date().getMonth() + 1,
  ref_year: props.year,
  installments: 2,
})

const valid = computed(() => form.amount > 0 && form.category_kind && form.ref_month)

function kindLabel(k) {
  return { entrada: 'Entrada', custo_operacional: 'Custo Op.', custo_fixo: 'Custo Fixo' }[k] || k
}
function kindBadge(k) {
  return { entrada: 'badge-success', custo_operacional: 'badge-warning', custo_fixo: 'badge-danger' }[k] || 'badge-secondary'
}

async function loadEntries() {
  try {
    const { data } = await api.get('/financial/dre/entries', {
      params: { cmig_id: props.cmigId, year: props.year },
    })
    entries.value = data
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar lançamentos')
  }
}

function resetForm() {
  editingId.value = null
  recurrent.value = false
  Object.assign(form, {
    category_kind: 'custo_fixo',
    category: '',
    description: '',
    amount: null,
    ref_month: new Date().getMonth() + 1,
    ref_year: props.year,
    installments: 2,
  })
}

async function save() {
  if (!valid.value) return
  saving.value = true
  try {
    if (editingId.value) {
      let scope = 'one'
      const e = entries.value.find((x) => x.id === editingId.value)
      if (e?.total_installments) {
        scope = window.confirm('Aplicar a alteração a ESTA e às parcelas FUTURAS?\n\nOK = esta e futuras · Cancelar = só esta') ? 'future' : 'one'
      }
      await api.put(`/financial/dre/entries/${editingId.value}?scope=${scope}`, {
        category_kind: form.category_kind,
        category: form.category,
        description: form.description,
        amount: form.amount,
      })
      toast.success('Lançamento atualizado')
    } else {
      await api.post('/financial/dre/entries', {
        cmig_id: props.cmigId,
        category_kind: form.category_kind,
        category: form.category,
        description: form.description,
        amount: form.amount,
        ref_year: form.ref_year,
        ref_month: form.ref_month,
        installments: recurrent.value ? form.installments : 1,
      })
      toast.success('Lançamento adicionado')
    }
    resetForm()
    await loadEntries()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar lançamento')
  } finally {
    saving.value = false
  }
}

function edit(e) {
  editingId.value = e.id
  recurrent.value = false
  Object.assign(form, {
    category_kind: e.category_kind,
    category: e.category || '',
    description: e.description || '',
    amount: e.amount,
    ref_month: e.ref_month,
    ref_year: e.ref_year,
    installments: 2,
  })
}

async function remove(e) {
  let scope = 'one'
  if (e.total_installments) {
    scope = window.confirm('Excluir ESTA e as parcelas FUTURAS?\n\nOK = esta e futuras · Cancelar = só esta') ? 'future' : 'one'
  } else if (!window.confirm('Excluir este lançamento?')) {
    return
  }
  try {
    await api.delete(`/financial/dre/entries/${e.id}?scope=${scope}`)
    toast.success('Lançamento excluído')
    await loadEntries()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao excluir')
  }
}

onMounted(loadEntries)
</script>
