<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0">
              <i class="fas mr-2" :class="directionIcon"></i>
              {{ isNew ? 'Nova ' : 'Editar ' }}{{ directionLabel }}
            </h1>
            <small class="text-muted">{{ form.id ? `NFe #${form.id} (${statusLabel(form.status)})` : 'Rascunho' }}</small>
          </div>
          <div class="col-sm-4 text-right">
            <RouterLink :to="backUrl" class="btn btn-secondary">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <!-- Cabeçalho -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-info-circle mr-2"></i>Dados gerais</h3>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="col-md-3" v-if="isNew">
                <label class="small mb-1">CMIG <span class="text-danger">*</span></label>
                <select v-model="form.cmig_id" class="form-control" :disabled="!isNew" @change="reloadPeople">
                  <option :value="null">Selecione...</option>
                  <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }}</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Finalidade</label>
                <select v-model="form.purpose" class="form-control" :disabled="!editable">
                  <option v-for="opt in purposeOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
              <div class="col-md-6">
                <label class="small mb-1">Natureza da operação</label>
                <input v-model="form.natureza_operacao" class="form-control" :disabled="!editable">
              </div>
            </div>

            <div class="row mt-3">
              <div class="col-md-6">
                <label class="small mb-1">{{ form.direction === 'in' ? 'Fornecedor' : 'Destinatário' }}</label>
                <div class="input-group">
                  <input :value="selectedPersonLabel" class="form-control" readonly placeholder="Nenhuma pessoa selecionada">
                  <div class="input-group-append" v-if="editable">
                    <button class="btn btn-outline-info" type="button" @click="showPersonPicker = true">
                      <i class="fas fa-search mr-1"></i> Selecionar
                    </button>
                  </div>
                </div>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Data emissão</label>
                <input v-model="issueDateLocal" type="date" class="form-control" :disabled="!editable">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Data saída</label>
                <input v-model="exitDateLocal" type="date" class="form-control" :disabled="!editable">
              </div>
            </div>

            <div class="row mt-3">
              <div class="col-md-3">
                <label class="small mb-1">Modalidade do frete</label>
                <select v-model.number="form.freight_modality" class="form-control" :disabled="!editable">
                  <option :value="null">—</option>
                  <option :value="0">0 — Por conta do emitente</option>
                  <option :value="1">1 — Por conta do destinatário</option>
                  <option :value="2">2 — Por conta de terceiros</option>
                  <option :value="9">9 — Sem ocorrência de transporte</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Forma de pagamento</label>
                <select v-model="form.payment_method" class="form-control" :disabled="!editable">
                  <option value="">—</option>
                  <option value="01">01 — Dinheiro</option>
                  <option value="03">03 — Cartão de crédito</option>
                  <option value="04">04 — Cartão de débito</option>
                  <option value="15">15 — Boleto</option>
                  <option value="17">17 — PIX</option>
                  <option value="90">90 — Sem pagamento</option>
                  <option value="99">99 — Outros</option>
                </select>
              </div>
              <div class="col-md-6">
                <label class="small mb-1">Informações adicionais</label>
                <input v-model="form.additional_info" class="form-control" :disabled="!editable">
              </div>
            </div>

            <div class="text-right mt-3" v-if="editable">
              <button class="btn btn-primary" :disabled="saving" @click="saveHeader">
                <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
                {{ saving ? 'Salvando...' : (isNew ? 'Criar Rascunho' : 'Salvar Cabeçalho') }}
              </button>
            </div>
          </div>
        </div>

        <!-- Itens (apenas após criar a invoice) -->
        <div v-if="!isNew" class="card">
          <div class="card-header d-flex align-items-center">
            <h3 class="card-title flex-grow-1"><i class="fas fa-boxes mr-2"></i>Itens</h3>
            <button v-if="editable" class="btn btn-sm btn-primary" @click="openItemModal()">
              <i class="fas fa-plus mr-1"></i> Adicionar Item
            </button>
          </div>
          <div class="card-body p-0">
            <table class="table table-sm mb-0">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Descrição</th>
                  <th>NCM</th>
                  <th>CFOP</th>
                  <th class="text-right">Qtd</th>
                  <th class="text-right">Valor un.</th>
                  <th class="text-right">Total</th>
                  <th v-if="editable"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="(form.items || []).length === 0">
                  <td :colspan="editable ? 8 : 7" class="text-center text-muted py-3">Nenhum item.</td>
                </tr>
                <tr v-for="it in form.items" :key="it.id">
                  <td>{{ it.item_number }}</td>
                  <td>
                    <strong>{{ it.description }}</strong>
                    <small v-if="it.ean" class="d-block text-muted">EAN: {{ it.ean }}</small>
                  </td>
                  <td>{{ it.ncm || '—' }}</td>
                  <td>{{ it.cfop || '—' }}</td>
                  <td class="text-right">{{ formatNumber(it.quantity, 4) }}</td>
                  <td class="text-right">{{ formatCurrency(it.unit_value) }}</td>
                  <td class="text-right"><strong>{{ formatCurrency(it.total_value) }}</strong></td>
                  <td v-if="editable" class="text-right">
                    <button class="btn btn-sm btn-outline-primary mr-1" @click="openItemModal(it)" title="Editar">
                      <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="deleteItem(it)" title="Excluir">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="(form.items || []).length > 0">
                <tr>
                  <td colspan="6" class="text-right"><strong>Total da NFe:</strong></td>
                  <td class="text-right"><strong>{{ formatCurrency(form.total_invoice) }}</strong></td>
                  <td v-if="editable"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>

        <!-- Botões finais -->
        <div v-if="!isNew && editable" class="text-right mb-4">
          <button class="btn btn-outline-primary mr-2" :disabled="calculating || !form.items?.length" @click="calculateTaxes">
            <i class="fas" :class="calculating ? 'fa-spinner fa-spin' : 'fa-calculator'"></i>
            {{ calculating ? 'Calculando...' : 'Calcular Impostos' }}
          </button>
          <button class="btn btn-success" :disabled="transmitting || !form.items?.length" @click="transmit">
            <i class="fas" :class="transmitting ? 'fa-spinner fa-spin' : 'fa-paper-plane'"></i>
            {{ transmitting ? 'Transmitindo...' : 'Transmitir SEFAZ' }}
          </button>
        </div>
      </div>
    </section>

    <!-- Modal: selecionar Pessoa -->
    <div v-if="showPersonPicker" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Selecionar Pessoa</h5>
            <button type="button" class="close" @click="showPersonPicker = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <input v-model="personSearch" class="form-control mb-3" placeholder="Buscar por nome ou documento..."
                   @input="searchPeople">
            <div v-if="loadingPeople" class="text-center py-3">
              <i class="fas fa-spinner fa-spin"></i>
            </div>
            <table v-else class="table table-sm table-hover">
              <tbody>
                <tr v-if="peopleList.length === 0">
                  <td colspan="3" class="text-center text-muted py-3">Nenhuma pessoa encontrada.</td>
                </tr>
                <tr v-for="p in peopleList" :key="p.id" style="cursor:pointer" @click="selectPerson(p)">
                  <td><code>{{ p.document }}</code></td>
                  <td>
                    <strong>{{ p.name }}</strong>
                    <small v-if="p.trade_name" class="d-block text-muted">{{ p.trade_name }}</small>
                  </td>
                  <td>
                    <span v-if="p.is_customer" class="badge badge-info mr-1">Cliente</span>
                    <span v-if="p.is_supplier" class="badge badge-warning">Fornecedor</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- Modal: Item -->
    <div v-if="showItemModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ itemForm.id ? 'Editar Item' : 'Novo Item' }}</h5>
            <button type="button" class="close" @click="showItemModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="row">
              <div class="col-md-12">
                <label class="small mb-1">Descrição <span class="text-danger">*</span></label>
                <input v-model="itemForm.description" class="form-control">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-3">
                <label class="small mb-1">NCM</label>
                <input v-model="itemForm.ncm" class="form-control" maxlength="8">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">CEST</label>
                <input v-model="itemForm.cest" class="form-control" maxlength="7">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">CFOP</label>
                <input v-model="itemForm.cfop" class="form-control" maxlength="4" placeholder="5102">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">EAN</label>
                <input v-model="itemForm.ean" class="form-control" maxlength="14">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-2">
                <label class="small mb-1">Unidade</label>
                <input v-model="itemForm.unit" class="form-control" maxlength="6">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Quantidade</label>
                <input v-model.number="itemForm.quantity" type="number" step="0.0001" min="0" class="form-control">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Valor unitário</label>
                <input v-model.number="itemForm.unit_value" type="number" step="0.0001" min="0" class="form-control">
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Origem</label>
                <select v-model.number="itemForm.origin" class="form-control">
                  <option :value="0">0 — Nacional</option>
                  <option :value="1">1 — Estrangeira (importação direta)</option>
                  <option :value="2">2 — Estrangeira (mercado interno)</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Total calculado</label>
                <input :value="formatCurrency(calcTotal)" class="form-control" disabled>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showItemModal = false">Cancelar</button>
            <button class="btn btn-primary" :disabled="savingItem" @click="saveItem">
              <i class="fas" :class="savingItem ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ savingItem ? 'Salvando...' : 'Salvar Item' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { usePeopleStore } from '@/stores/people'
import { useToast } from '@/composables/useToast'
import { fmt } from '@/views/fiscal/_helpers'

const route = useRoute()
const router = useRouter()
const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const peopleStore = usePeopleStore()
const toast = useToast()
const { cmigs } = storeToRefs(cmigStore)

const initialDirection = (route.query.direction === 'in' ? 'in' : 'out')
const isNew = computed(() => !route.params.id)
const invoiceId = computed(() => route.params.id ? Number(route.params.id) : null)

const saving = ref(false)
const savingItem = ref(false)
const calculating = ref(false)
const transmitting = ref(false)
const showPersonPicker = ref(false)
const showItemModal = ref(false)
const personSearch = ref('')
const loadingPeople = ref(false)
const peopleList = ref([])
const selectedPerson = ref(null)

const form = reactive({
  id: null,
  cmig_id: null,
  direction: initialDirection,
  purpose: 'venda',
  natureza_operacao: initialDirection === 'in' ? 'Compra para revenda' : 'Venda de mercadoria',
  status: 'draft',
  person_id: null,
  issue_date: null,
  exit_date: null,
  freight_modality: null,
  payment_method: '',
  additional_info: '',
  total_invoice: 0,
  items: [],
})

const itemForm = reactive({
  id: null,
  description: '',
  ncm: '',
  cest: '',
  cfop: initialDirection === 'in' ? '1102' : '5102',
  ean: '',
  unit: 'UN',
  quantity: 1,
  unit_value: 0,
  origin: 0,
})

const issueDateLocal = computed({
  get: () => form.issue_date ? form.issue_date.slice(0, 10) : '',
  set: (v) => { form.issue_date = v ? `${v}T00:00:00` : null },
})
const exitDateLocal = computed({
  get: () => form.exit_date ? form.exit_date.slice(0, 10) : '',
  set: (v) => { form.exit_date = v ? `${v}T00:00:00` : null },
})

const editable = computed(() => form.status === 'draft')
const directionIcon = computed(() => form.direction === 'in' ? 'fa-arrow-down text-warning' : 'fa-arrow-up text-success')
const directionLabel = computed(() => form.direction === 'in' ? 'Entrada' : 'Saída')
const backUrl = computed(() => form.direction === 'in' ? '/fiscal/entradas' : '/fiscal/saidas')

const purposeOptions = computed(() => {
  if (form.direction === 'in') {
    return [
      { value: 'venda',         label: 'Compra' },
      { value: 'devolucao',     label: 'Devolução de venda (cliente devolveu)' },
      { value: 'remessa',       label: 'Remessa recebida' },
      { value: 'retorno',       label: 'Retorno de mercadoria' },
      { value: 'transferencia', label: 'Transferência recebida' },
      { value: 'complementar',  label: 'Complementar de entrada' },
      { value: 'ajuste',        label: 'Ajuste' },
      { value: 'outros',        label: 'Outros' },
    ]
  }
  return [
    { value: 'venda',         label: 'Venda' },
    { value: 'devolucao',     label: 'Devolução de compra' },
    { value: 'remessa',       label: 'Simples Remessa' },
    { value: 'retorno',       label: 'Retorno' },
    { value: 'transferencia', label: 'Transferência' },
    { value: 'complementar',  label: 'Complementar' },
    { value: 'ajuste',        label: 'Ajuste' },
    { value: 'outros',        label: 'Outros' },
  ]
})

const selectedPersonLabel = computed(() => {
  if (!selectedPerson.value) return ''
  const p = selectedPerson.value
  return `${p.name} — ${p.document}`
})

const calcTotal = computed(() => Number((itemForm.quantity || 0) * (itemForm.unit_value || 0)).toFixed(2))
const formatNumber = (v, dec = 2) => v == null ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: dec, maximumFractionDigits: dec })
const formatCurrency = fmt.currency
const statusLabel = fmt.statusLabel

watch(() => form.purpose, (p) => {
  // Sugerir CFOP padrão (intra-estadual). Usuário ajusta depois se for interestadual.
  if (form.direction === 'out') {
    if (p === 'venda') itemForm.cfop = '5102'
    if (p === 'devolucao') itemForm.cfop = '5202'  // devolução de compra (saída)
    if (p === 'remessa') itemForm.cfop = '5949'
    if (p === 'transferencia') itemForm.cfop = '5152'
    if (p === 'retorno') itemForm.cfop = '5949'
  } else {
    if (p === 'venda') itemForm.cfop = '1102'         // compra para revenda
    if (p === 'devolucao') itemForm.cfop = '1202'     // devolução de venda (entrada)
    if (p === 'remessa') itemForm.cfop = '1949'
    if (p === 'transferencia') itemForm.cfop = '1152'
    if (p === 'retorno') itemForm.cfop = '1949'
  }
})

async function reloadPeople(query = '') {
  if (!form.cmig_id) return
  loadingPeople.value = true
  try {
    const params = { cmig_id: form.cmig_id, page_size: 50 }
    if (form.direction === 'in') params.is_supplier = true
    else params.is_customer = true
    if (query) params.search = query
    const data = await peopleStore.fetchPeople(params)
    peopleList.value = data.items || []
  } finally {
    loadingPeople.value = false
  }
}

let searchTimer = null
function searchPeople() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => reloadPeople(personSearch.value), 300)
}

function selectPerson(p) {
  selectedPerson.value = p
  form.person_id = p.id
  showPersonPicker.value = false
}

async function loadInvoice() {
  if (!invoiceId.value) return
  try {
    const data = await fiscalStore.fetchInvoice(invoiceId.value)
    Object.assign(form, {
      id: data.id,
      cmig_id: data.cmig_id,
      direction: data.direction,
      purpose: data.purpose,
      natureza_operacao: data.natureza_operacao,
      status: data.status,
      person_id: data.person_id,
      issue_date: data.issue_date,
      exit_date: data.exit_date,
      freight_modality: data.freight_modality,
      payment_method: data.payment_method || '',
      additional_info: data.additional_info || '',
      total_invoice: data.total_invoice || 0,
      items: data.items || [],
    })
    selectedPerson.value = data.person ? { ...data.person } : null
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NFe')
    router.push(backUrl.value)
  }
}

async function saveHeader() {
  saving.value = true
  try {
    const payload = {
      cmig_id: form.cmig_id,
      direction: form.direction,
      purpose: form.purpose,
      natureza_operacao: form.natureza_operacao,
      person_id: form.person_id,
      issue_date: form.issue_date,
      exit_date: form.exit_date,
      freight_modality: form.freight_modality,
      payment_method: form.payment_method || null,
      additional_info: form.additional_info,
    }
    if (isNew.value) {
      const created = await fiscalStore.createInvoice(payload)
      toast.success('Rascunho criado')
      router.replace(`/fiscal/invoices/${created.id}/edit`)
    } else {
      await fiscalStore.updateInvoice(invoiceId.value, payload)
      toast.success('Cabeçalho salvo')
      await loadInvoice()
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

function openItemModal(it) {
  if (it) {
    Object.assign(itemForm, {
      id: it.id,
      description: it.description,
      ncm: it.ncm || '',
      cest: it.cest || '',
      cfop: it.cfop || '',
      ean: it.ean || '',
      unit: it.unit || 'UN',
      quantity: Number(it.quantity || 1),
      unit_value: Number(it.unit_value || 0),
      origin: it.origin ?? 0,
    })
  } else {
    Object.assign(itemForm, {
      id: null,
      description: '',
      ncm: '',
      cest: '',
      cfop: form.direction === 'in' ? '1102' : '5102',
      ean: '',
      unit: 'UN',
      quantity: 1,
      unit_value: 0,
      origin: 0,
    })
  }
  showItemModal.value = true
}

async function saveItem() {
  if (!itemForm.description?.trim()) {
    toast.warning('Descrição é obrigatória')
    return
  }
  savingItem.value = true
  try {
    const payload = {
      description: itemForm.description,
      ncm: itemForm.ncm || null,
      cest: itemForm.cest || null,
      cfop: itemForm.cfop || null,
      ean: itemForm.ean || null,
      unit: itemForm.unit || 'UN',
      quantity: Number(itemForm.quantity || 0),
      unit_value: Number(itemForm.unit_value || 0),
      origin: itemForm.origin ?? 0,
    }
    if (itemForm.id) {
      await fiscalStore.updateItem(invoiceId.value, itemForm.id, payload)
      toast.success('Item atualizado')
    } else {
      await fiscalStore.addItem(invoiceId.value, payload)
      toast.success('Item adicionado')
    }
    showItemModal.value = false
    await loadInvoice()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar item')
  } finally {
    savingItem.value = false
  }
}

async function deleteItem(it) {
  if (!confirm(`Excluir item "${it.description}"?`)) return
  try {
    await fiscalStore.deleteItem(invoiceId.value, it.id)
    toast.success('Item excluído')
    await loadInvoice()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir')
  }
}

async function calculateTaxes() {
  calculating.value = true
  try {
    await fiscalStore.calculateTaxes(invoiceId.value)
    toast.success('Impostos recalculados')
    await loadInvoice()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao calcular impostos')
  } finally {
    calculating.value = false
  }
}

async function transmit() {
  if (!confirm('Transmitir esta NFe para a SEFAZ via Focus NFe? Após a autorização, ela não poderá ser editada.')) return
  transmitting.value = true
  try {
    const result = await fiscalStore.transmit(invoiceId.value)
    if (result.status === 'authorized') {
      toast.success('NFe autorizada!')
    } else if (result.status === 'processing') {
      toast.info('NFe em processamento — aguarde o webhook do Focus.')
    } else {
      toast.warning(`Status: ${result.status} — ${result.focus_message || ''}`)
    }
    router.push(`/fiscal/invoices/${invoiceId.value}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao transmitir')
    await loadInvoice()
  } finally {
    transmitting.value = false
  }
}

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  if (isNew.value) {
    if (cmigs.value.length > 0 && !form.cmig_id) {
      form.cmig_id = cmigs.value[0].id
    }
    form.issue_date = new Date().toISOString()
    await reloadPeople()
  } else {
    await loadInvoice()
    await reloadPeople()
  }
})
</script>
