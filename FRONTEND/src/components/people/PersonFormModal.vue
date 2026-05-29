<template>
  <teleport to="body">
    <div
      v-if="show"
      class="modal fade show d-block"
      tabindex="-1"
      role="dialog"
      style="background:rgba(0,0,0,.5)"
      @click.self="close"
    >
      <div class="modal-dialog modal-lg modal-dialog-centered" role="document">
        <div class="modal-content">
          <form @submit.prevent="submit">
            <div class="modal-header">
              <h5 class="modal-title">
                <i class="fas fa-user-plus mr-2"></i> Novo cliente
              </h5>
              <button type="button" class="close" aria-label="Fechar" @click="close">
                <span aria-hidden="true">&times;</span>
              </button>
            </div>
            <div class="modal-body">
              <div class="row">
                <div class="col-md-3">
                  <label class="small mb-1">Tipo</label>
                  <select v-model="form.person_type" class="form-control" :disabled="saving">
                    <option value="PJ">Pessoa Jurídica</option>
                    <option value="PF">Pessoa Física</option>
                  </select>
                </div>
                <div class="col-md-5">
                  <label class="small mb-1">
                    {{ form.person_type === 'PJ' ? 'CNPJ' : 'CPF' }}
                    <span class="text-danger">*</span>
                  </label>
                  <div class="input-group">
                    <input
                      v-model="form.document"
                      class="form-control"
                      :placeholder="form.person_type === 'PJ' ? '00.000.000/0000-00' : '000.000.000-00'"
                      required
                      :disabled="saving"
                    />
                    <div v-if="form.person_type === 'PJ'" class="input-group-append">
                      <button
                        type="button"
                        class="btn btn-outline-info"
                        :disabled="saving || lookingUp"
                        title="Consultar CNPJ na BrasilAPI"
                        @click="doCnpjLookup"
                      >
                        <i class="fas" :class="lookingUp ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                      </button>
                    </div>
                  </div>
                </div>
                <div class="col-md-4">
                  <label class="small mb-1">Telefone</label>
                  <input v-model="form.phone" class="form-control" :disabled="saving" />
                </div>
              </div>

              <div class="row mt-3">
                <div class="col-md-7">
                  <label class="small mb-1">
                    {{ form.person_type === 'PJ' ? 'Razão Social' : 'Nome' }}
                    <span class="text-danger">*</span>
                  </label>
                  <input v-model="form.name" class="form-control" required :disabled="saving" />
                </div>
                <div class="col-md-5">
                  <label class="small mb-1">Nome Fantasia</label>
                  <input v-model="form.trade_name" class="form-control" :disabled="saving" />
                </div>
              </div>

              <div class="row mt-3">
                <div class="col-md-12">
                  <label class="small mb-1">E-mail</label>
                  <input v-model="form.email" type="email" class="form-control" :disabled="saving" />
                </div>
              </div>

              <hr class="mt-4 mb-3" />
              <h6 class="text-muted mb-3"><i class="fas fa-map-marker-alt mr-1"></i> Endereço</h6>

              <div class="row">
                <div class="col-md-3">
                  <label class="small mb-1">CEP</label>
                  <input v-model="form.zip_code" class="form-control" :disabled="saving" />
                </div>
                <div class="col-md-7">
                  <label class="small mb-1">Logradouro</label>
                  <input v-model="form.street" class="form-control" :disabled="saving" />
                </div>
                <div class="col-md-2">
                  <label class="small mb-1">Número</label>
                  <input v-model="form.address_number" class="form-control" :disabled="saving" />
                </div>
              </div>

              <div class="row mt-3">
                <div class="col-md-4">
                  <label class="small mb-1">Complemento</label>
                  <input v-model="form.complement" class="form-control" :disabled="saving" />
                </div>
                <div class="col-md-4">
                  <label class="small mb-1">Bairro</label>
                  <input v-model="form.neighborhood" class="form-control" :disabled="saving" />
                </div>
                <div class="col-md-3">
                  <label class="small mb-1">Cidade</label>
                  <input v-model="form.city" class="form-control" :disabled="saving" />
                </div>
                <div class="col-md-1">
                  <label class="small mb-1">UF</label>
                  <input v-model="form.state" maxlength="2" class="form-control text-uppercase" :disabled="saving" />
                </div>
              </div>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn btn-secondary" :disabled="saving" @click="close">
                Cancelar
              </button>
              <button type="submit" class="btn btn-primary" :disabled="saving">
                <span v-if="saving"><i class="fas fa-spinner fa-spin mr-1"></i> Salvando…</span>
                <span v-else>Salvar cliente</span>
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { usePeopleStore } from '@/stores/people'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  show: { type: Boolean, default: false },
  cmigId: { type: Number, default: null },
})
const emit = defineEmits(['created', 'close'])

const peopleStore = usePeopleStore()
const toast = useToast()

const saving = ref(false)
const lookingUp = ref(false)

function emptyForm() {
  return {
    person_type: 'PJ',
    document: '',
    name: '',
    trade_name: '',
    email: '',
    phone: '',
    zip_code: '',
    street: '',
    address_number: '',
    complement: '',
    neighborhood: '',
    city: '',
    state: '',
  }
}

const form = reactive(emptyForm())

watch(() => props.show, (visible) => {
  if (visible) Object.assign(form, emptyForm())
})

async function doCnpjLookup() {
  const digits = (form.document || '').replace(/\D/g, '')
  if (digits.length !== 14) {
    toast.error('Informe um CNPJ com 14 dígitos')
    return
  }
  lookingUp.value = true
  try {
    const data = await peopleStore.lookupCnpj(digits)
    form.name = data.name || form.name
    form.trade_name = data.trade_name || form.trade_name
    form.email = data.email || form.email
    form.phone = data.phone || form.phone
    form.zip_code = data.zip_code || form.zip_code
    form.street = data.street || form.street
    form.address_number = data.address_number || form.address_number
    form.complement = data.complement || form.complement
    form.neighborhood = data.neighborhood || form.neighborhood
    form.city = data.city || form.city
    form.state = data.state || form.state
    toast.success('Dados do CNPJ preenchidos')
  } catch {
    toast.error('Não foi possível consultar o CNPJ')
  } finally {
    lookingUp.value = false
  }
}

async function submit() {
  if (!props.cmigId) {
    toast.error('Selecione a CMIG antes de cadastrar o cliente')
    return
  }
  saving.value = true
  try {
    const payload = {
      ...form,
      cmig_id: props.cmigId,
      is_customer: true,
      is_supplier: false,
      is_carrier: false,
      is_active: true,
      state: (form.state || '').toUpperCase(),
    }
    const created = await peopleStore.createPerson(payload)
    toast.success('Cliente cadastrado')
    emit('created', created)
  } catch (err) {
    const detail = err?.response?.data?.detail
    toast.error(typeof detail === 'string' ? detail : 'Erro ao cadastrar cliente')
  } finally {
    saving.value = false
  }
}

function close() {
  if (saving.value) return
  emit('close')
}
</script>
