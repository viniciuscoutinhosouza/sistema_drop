<template>
  <div class="card">
    <div class="card-header d-flex justify-content-between align-items-center">
      <h3 class="card-title mb-0"><i class="fas fa-university mr-2"></i>Bancos / Recebimento</h3>
      <button type="button" class="btn btn-sm btn-primary" @click="openNew">
        <i class="fas fa-plus mr-1"></i> Novo banco
      </button>
    </div>
    <div class="card-body p-0">
      <p class="small text-muted px-3 pt-2 mb-1">
        <i class="fas fa-info-circle"></i>
        A chave Pix do galpão (seção "Recebimentos") é legada; o recebimento pelas contas cadastradas
        aqui é o que será usado no checkout (próximas fases).
      </p>
      <div v-if="loading" class="text-center text-muted py-3">
        <i class="fas fa-spinner fa-spin"></i>
      </div>
      <table v-else class="table table-sm mb-0">
        <thead>
          <tr>
            <th>Banco</th>
            <th>Rótulo</th>
            <th>API Key</th>
            <th>Status</th>
            <th style="width:90px"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!banks.length">
            <td colspan="5" class="text-center text-muted py-3">Nenhuma conta de recebimento cadastrada.</td>
          </tr>
          <tr v-for="b in banks" :key="b.id">
            <td>
              {{ providerLabel(b.provider) }}
              <small v-if="b.bank_code" class="text-muted">({{ b.bank_code }})</small>
              <span v-if="b.is_primary" class="badge badge-primary ml-1">Principal</span>
            </td>
            <td>{{ b.name }}</td>
            <td>
              <span class="badge" :class="b.api_key_set ? 'badge-success' : 'badge-secondary'">
                {{ b.api_key_set ? 'configurada' : 'não cadastrada' }}
              </span>
            </td>
            <td>
              <span class="badge" :class="b.is_active ? 'badge-success' : 'badge-secondary'">
                {{ b.is_active ? 'Ativo' : 'Inativo' }}
              </span>
              <span v-if="b.is_sandbox" class="badge badge-warning ml-1">Homolog.</span>
            </td>
            <td class="text-right text-nowrap">
              <button type="button" class="btn btn-sm btn-outline-info" :disabled="busy[b.id]"
                      title="Testar conexão com o ASAAS" @click="testConnection(b)">
                <i class="fas" :class="busy[b.id] === 'test' ? 'fa-spinner fa-spin' : 'fa-plug'"></i>
              </button>
              <button type="button" class="btn btn-sm ml-1" :disabled="busy[b.id]"
                      :class="b.webhook_configured ? 'btn-outline-success' : 'btn-outline-warning'"
                      :title="b.webhook_configured ? 'Webhook configurado — reconfigurar' : 'Configurar webhook no ASAAS'"
                      @click="configureWebhook(b)">
                <i class="fas" :class="busy[b.id] === 'webhook' ? 'fa-spinner fa-spin' : 'fa-bolt'"></i>
              </button>
              <button type="button" class="btn btn-sm btn-outline-primary ml-1" title="Editar" @click="openEdit(b)">
                <i class="fas fa-edit"></i>
              </button>
              <button type="button" class="btn btn-sm btn-outline-danger ml-1" title="Excluir" @click="removeBank(b)">
                <i class="fas fa-trash"></i>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal add/editar banco -->
    <div v-if="modal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5);z-index:1065">
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header py-2">
            <h6 class="modal-title"><i class="fas fa-university mr-2"></i>{{ form.id ? 'Editar banco' : 'Novo banco' }}</h6>
            <button type="button" class="close" :disabled="saving" @click="modal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body" style="font-size:.9rem;max-height:72vh;overflow-y:auto">
            <div class="form-group">
              <label class="small font-weight-bold">Banco <span class="text-danger">*</span></label>
              <select v-model="form.provider" class="form-control form-control-sm">
                <option value="asaas">ASAAS (banco 461)</option>
              </select>
            </div>
            <div class="form-group">
              <label class="small font-weight-bold">API Key do {{ providerLabel(form.provider) }}</label>
              <input v-model="form.api_key" class="form-control form-control-sm" type="password" autocomplete="new-password"
                     :placeholder="form.id && form.api_key_set ? '•••••• (já cadastrada — deixe em branco para manter)' : 'Cole a API Key'" />
              <small class="text-muted">Guardada <strong>criptografada</strong> no servidor; nunca é exibida de volta.</small>
            </div>
            <div class="form-group">
              <label class="small font-weight-bold">Wallet ID (opcional)</label>
              <input v-model="form.wallet_id" class="form-control form-control-sm" />
            </div>
            <div class="form-group">
              <label class="small font-weight-bold">Nome (rótulo) <span class="text-danger">*</span></label>
              <input v-model="form.name" class="form-control form-control-sm" placeholder="Ex: ASAAS - Principal" />
            </div>
            <div class="form-group">
              <label class="small font-weight-bold">Conta do plano de contas</label>
              <input v-model="form.chart_account_label" class="form-control form-control-sm" placeholder="Ex: 1.1.1.01 — Caixa" />
              <small class="text-muted">Texto livre por enquanto — o Plano de Contas entra numa fase futura.</small>
            </div>
            <div class="form-row">
              <div class="col custom-control custom-checkbox mb-2">
                <input id="bank-sandbox" v-model="form.is_sandbox" type="checkbox" class="custom-control-input" />
                <label class="custom-control-label small" for="bank-sandbox">Homologação (sandbox)</label>
              </div>
              <div class="col custom-control custom-checkbox mb-2">
                <input id="bank-active" v-model="form.is_active" type="checkbox" class="custom-control-input" />
                <label class="custom-control-label small" for="bank-active">Ativo</label>
              </div>
              <div class="col custom-control custom-checkbox mb-2">
                <input id="bank-primary" v-model="form.is_primary" type="checkbox" class="custom-control-input" />
                <label class="custom-control-label small" for="bank-primary">Conta principal</label>
              </div>
            </div>

            <hr class="my-2" />
            <div class="small text-muted mb-2">Dados bancários</div>
            <div class="form-row">
              <div class="form-group col-4">
                <label class="small">Código do banco</label>
                <input v-model="form.bank_code" class="form-control form-control-sm" placeholder="461" />
              </div>
              <div class="form-group col-4">
                <label class="small">Agência</label>
                <input v-model="form.agency" class="form-control form-control-sm" />
              </div>
              <div class="form-group col-4">
                <label class="small">Conta</label>
                <input v-model="form.account_number" class="form-control form-control-sm" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group col-6">
                <label class="small">Tipo da chave Pix</label>
                <select v-model="form.pix_key_type" class="form-control form-control-sm">
                  <option :value="null">— sem chave —</option>
                  <option value="cpf">CPF</option>
                  <option value="cnpj">CNPJ</option>
                  <option value="email">E-mail</option>
                  <option value="phone">Telefone</option>
                  <option value="random">Aleatória</option>
                </select>
              </div>
              <div class="form-group col-6">
                <label class="small">Chave Pix</label>
                <input v-model="form.pix_key" class="form-control form-control-sm" :disabled="!form.pix_key_type" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group col-6">
                <label class="small">Titular</label>
                <input v-model="form.holder_name" class="form-control form-control-sm" />
              </div>
              <div class="form-group col-6">
                <label class="small">CPF/CNPJ do titular</label>
                <input v-model="form.holder_document" class="form-control form-control-sm" />
              </div>
            </div>

            <hr class="my-2" />
            <div class="small text-muted mb-2">Saldo inicial (abertura)</div>
            <div class="form-row">
              <div class="form-group col-6">
                <label class="small">Saldo inicial (R$)</label>
                <input v-model.number="form.opening_balance" type="number" step="0.01" class="form-control form-control-sm" />
              </div>
              <div class="form-group col-6">
                <label class="small">Data do saldo inicial</label>
                <input v-model="form.opening_balance_date" type="date" class="form-control form-control-sm" />
              </div>
            </div>
            <small class="text-muted d-block mb-2">
              Capturado para o Livro-Caixa de uma fase futura — ainda não afeta relatórios.
            </small>

            <div class="form-group mb-0">
              <label class="small">Observação</label>
              <textarea v-model="form.notes" class="form-control form-control-sm" rows="2"></textarea>
            </div>
          </div>
          <div class="modal-footer py-2">
            <button type="button" class="btn btn-sm btn-secondary" :disabled="saving" @click="modal = false">Cancelar</button>
            <button type="button" class="btn btn-sm btn-primary" :disabled="saving" @click="save">
              <i v-if="saving" class="fas fa-spinner fa-spin mr-1"></i>{{ saving ? 'Salvando…' : 'Salvar banco' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  warehouseId: { type: Number, required: true },
})

const toast = useToast()
const banks = ref([])
const loading = ref(false)
const saving = ref(false)
const modal = ref(false)
const busy = ref({})   // { [bankId]: 'test' | 'webhook' | false }

async function testConnection(b) {
  busy.value = { ...busy.value, [b.id]: 'test' }
  try {
    const { data } = await api.post(`/warehouse/${props.warehouseId}/bank-accounts/${b.id}/test-connection`)
    toast.success(`Conexão OK${data.name ? ' — ' + data.name : ''}${data.sandbox ? ' (sandbox)' : ''}`)
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Falha ao conectar no ASAAS')
  } finally {
    busy.value = { ...busy.value, [b.id]: false }
  }
}

async function configureWebhook(b) {
  if (b.webhook_configured && !confirm('Já há webhook configurado. Reconfigurar (gera novo token)?')) return
  busy.value = { ...busy.value, [b.id]: 'webhook' }
  try {
    await api.post(`/warehouse/${props.warehouseId}/bank-accounts/${b.id}/configure-webhook`)
    toast.success('Webhook configurado no ASAAS.')
    await load()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Falha ao configurar o webhook')
  } finally {
    busy.value = { ...busy.value, [b.id]: false }
  }
}

function providerLabel(p) {
  return { asaas: 'ASAAS' }[p] || (p || '').toUpperCase()
}

function emptyForm() {
  return {
    id: null, provider: 'asaas', name: '', api_key: '', api_key_set: false,
    wallet_id: '', chart_account_label: '',
    is_sandbox: false, is_active: true, is_primary: false,
    bank_code: '', agency: '', account_number: '',
    pix_key_type: null, pix_key: '',
    holder_name: '', holder_document: '',
    opening_balance: 0, opening_balance_date: '', notes: '',
  }
}
const form = ref(emptyForm())

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/warehouse/${props.warehouseId}/bank-accounts`)
    banks.value = Array.isArray(data) ? data : []
  } catch {
    toast.error('Falha ao carregar contas de recebimento')
  } finally {
    loading.value = false
  }
}

function openNew() {
  form.value = emptyForm()
  modal.value = true
}

function openEdit(b) {
  form.value = {
    ...emptyForm(),
    ...b,
    api_key: '',  // nunca vem do backend — em branco mantém
    opening_balance_date: b.opening_balance_date ? b.opening_balance_date.slice(0, 10) : '',
  }
  modal.value = true
}

async function save() {
  if (!(form.value.name || '').trim()) {
    toast.error('Informe o nome/rótulo da conta')
    return
  }
  saving.value = true
  const payload = { ...form.value }
  delete payload.api_key_set
  if (!payload.api_key) delete payload.api_key  // não enviar vazio = mantém
  if (!payload.opening_balance_date) payload.opening_balance_date = null
  try {
    if (form.value.id) {
      await api.put(`/warehouse/${props.warehouseId}/bank-accounts/${form.value.id}`, payload)
    } else {
      await api.post(`/warehouse/${props.warehouseId}/bank-accounts`, payload)
    }
    toast.success('Conta de recebimento salva')
    modal.value = false
    await load()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao salvar a conta')
  } finally {
    saving.value = false
  }
}

async function removeBank(b) {
  if (!confirm(`Excluir a conta "${b.name}"?`)) return
  try {
    await api.delete(`/warehouse/${props.warehouseId}/bank-accounts/${b.id}`)
    toast.success('Conta removida')
    await load()
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Erro ao excluir')
  }
}

onMounted(load)
</script>
