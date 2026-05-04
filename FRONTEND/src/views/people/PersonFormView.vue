<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0">
              <i class="fas fa-address-card mr-2"></i>{{ isNew ? 'Nova Pessoa' : 'Editar Pessoa' }}
            </h1>
          </div>
          <div class="col-sm-4 text-right">
            <RouterLink to="/people" class="btn btn-secondary">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <form @submit.prevent="submit">
          <div class="card">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-id-card mr-2"></i>Identificação</h3>
            </div>
            <div class="card-body">
              <div class="row">
                <div class="col-md-3" v-if="isNew">
                  <label class="small mb-1">CMIG <span class="text-danger">*</span></label>
                  <select v-model="form.cmig_id" class="form-control" required :disabled="!isNew">
                    <option :value="null">Selecione...</option>
                    <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }}</option>
                  </select>
                </div>
                <div class="col-md-2">
                  <label class="small mb-1">Tipo</label>
                  <select v-model="form.person_type" class="form-control">
                    <option value="PJ">Pessoa Jurídica</option>
                    <option value="PF">Pessoa Física</option>
                  </select>
                </div>
                <div class="col-md-4">
                  <label class="small mb-1">{{ form.person_type === 'PJ' ? 'CNPJ' : 'CPF' }} <span class="text-danger">*</span></label>
                  <div class="input-group">
                    <input v-model="form.document" class="form-control"
                           :placeholder="form.person_type === 'PJ' ? '00.000.000/0000-00' : '000.000.000-00'"
                           @blur="onDocumentBlur">
                    <div class="input-group-append" v-if="form.person_type === 'PJ'">
                      <button type="button" class="btn btn-outline-info" :disabled="lookingUp" @click="doCnpjLookup"
                              title="Consultar CNPJ na BrasilAPI">
                        <i class="fas" :class="lookingUp ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                      </button>
                    </div>
                  </div>
                </div>
                <div class="col-md-3">
                  <label class="small mb-1">IE (Inscrição Estadual)</label>
                  <input v-model="form.ie" class="form-control" :disabled="form.ie_isento">
                  <div class="form-check mt-1">
                    <input type="checkbox" class="form-check-input" id="ie-isento" v-model="form.ie_isento">
                    <label class="form-check-label small" for="ie-isento">Isento</label>
                  </div>
                </div>
              </div>

              <div class="row mt-3">
                <div class="col-md-6">
                  <label class="small mb-1">Razão Social / Nome <span class="text-danger">*</span></label>
                  <input v-model="form.name" class="form-control" required>
                </div>
                <div class="col-md-6">
                  <label class="small mb-1">Nome Fantasia</label>
                  <input v-model="form.trade_name" class="form-control">
                </div>
              </div>

              <div class="row mt-3">
                <div class="col-md-4">
                  <label class="small mb-1">E-mail</label>
                  <input v-model="form.email" type="email" class="form-control">
                </div>
                <div class="col-md-4">
                  <label class="small mb-1">Telefone</label>
                  <input v-model="form.phone" class="form-control">
                </div>
                <div class="col-md-4">
                  <label class="small mb-1">Inscrição Municipal</label>
                  <input v-model="form.im" class="form-control">
                </div>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-map-marker-alt mr-2"></i>Endereço</h3>
            </div>
            <div class="card-body">
              <div class="row">
                <div class="col-md-3">
                  <label class="small mb-1">CEP</label>
                  <input v-model="form.zip_code" class="form-control" placeholder="00000-000">
                </div>
                <div class="col-md-7">
                  <label class="small mb-1">Logradouro</label>
                  <input v-model="form.street" class="form-control">
                </div>
                <div class="col-md-2">
                  <label class="small mb-1">Número</label>
                  <input v-model="form.address_number" class="form-control">
                </div>
              </div>
              <div class="row mt-3">
                <div class="col-md-4">
                  <label class="small mb-1">Complemento</label>
                  <input v-model="form.complement" class="form-control">
                </div>
                <div class="col-md-4">
                  <label class="small mb-1">Bairro</label>
                  <input v-model="form.neighborhood" class="form-control">
                </div>
                <div class="col-md-3">
                  <label class="small mb-1">Cidade</label>
                  <input v-model="form.city" class="form-control">
                </div>
                <div class="col-md-1">
                  <label class="small mb-1">UF</label>
                  <input v-model="form.state" class="form-control" maxlength="2">
                </div>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header">
              <h3 class="card-title"><i class="fas fa-tags mr-2"></i>Classificação</h3>
            </div>
            <div class="card-body">
              <div class="row">
                <div class="col-md-3">
                  <div class="form-check">
                    <input type="checkbox" class="form-check-input" id="chk-customer" v-model="form.is_customer">
                    <label class="form-check-label" for="chk-customer">
                      <i class="fas fa-user mr-1 text-info"></i>Cliente
                    </label>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="form-check">
                    <input type="checkbox" class="form-check-input" id="chk-supplier" v-model="form.is_supplier">
                    <label class="form-check-label" for="chk-supplier">
                      <i class="fas fa-truck-loading mr-1 text-warning"></i>Fornecedor
                    </label>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="form-check">
                    <input type="checkbox" class="form-check-input" id="chk-carrier" v-model="form.is_carrier">
                    <label class="form-check-label" for="chk-carrier">
                      <i class="fas fa-truck mr-1 text-secondary"></i>Transportador
                    </label>
                  </div>
                </div>
                <div class="col-md-3">
                  <div class="form-check">
                    <input type="checkbox" class="form-check-input" id="chk-active" v-model="form.is_active">
                    <label class="form-check-label" for="chk-active">
                      <i class="fas fa-check-circle mr-1 text-success"></i>Ativo
                    </label>
                  </div>
                </div>
              </div>
              <div class="row mt-3">
                <div class="col-12">
                  <label class="small mb-1">Observações</label>
                  <textarea v-model="form.notes" class="form-control" rows="2"></textarea>
                </div>
              </div>
            </div>
          </div>

          <div class="text-right mb-4">
            <RouterLink to="/people" class="btn btn-secondary mr-2">Cancelar</RouterLink>
            <button type="submit" class="btn btn-primary" :disabled="saving">
              <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ saving ? 'Salvando...' : 'Salvar' }}
            </button>
          </div>
        </form>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { usePeopleStore } from '@/stores/people'
import { useCmigStore } from '@/stores/cmig'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const peopleStore = usePeopleStore()
const cmigStore = useCmigStore()
const toast = useToast()
const { cmigs } = storeToRefs(cmigStore)

const isNew = computed(() => !route.params.id)
const personId = computed(() => route.params.id ? Number(route.params.id) : null)

const lookingUp = ref(false)
const saving = ref(false)

const form = reactive({
  cmig_id: null,
  person_type: 'PJ',
  document: '',
  ie: '',
  ie_isento: false,
  im: '',
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
  ibge_code: '',
  is_customer: true,
  is_supplier: false,
  is_carrier: false,
  notes: '',
  is_active: true,
})

watch(() => form.document, (v) => {
  // Detectar tipo automaticamente pelo número de dígitos
  const d = String(v || '').replace(/\D/g, '')
  if (d.length === 14 && form.person_type !== 'PJ') form.person_type = 'PJ'
  if (d.length === 11 && form.person_type !== 'PF') form.person_type = 'PF'
})

function onDocumentBlur() {
  // Auto-lookup quando colar/digitar CNPJ completo
  const d = String(form.document || '').replace(/\D/g, '')
  if (form.person_type === 'PJ' && d.length === 14 && !form.name) {
    doCnpjLookup()
  }
}

async function doCnpjLookup() {
  const d = String(form.document || '').replace(/\D/g, '')
  if (d.length !== 14) {
    toast.warning('Informe um CNPJ válido (14 dígitos)')
    return
  }
  lookingUp.value = true
  try {
    const data = await peopleStore.lookupCnpj(d)
    form.name = data.razao_social || form.name
    form.trade_name = data.nome_fantasia || form.trade_name
    form.email = data.email || form.email
    form.phone = data.phone || form.phone
    form.zip_code = data.zip_code || form.zip_code
    form.street = data.street || form.street
    form.address_number = data.address_number || form.address_number
    form.complement = data.complement || form.complement
    form.neighborhood = data.neighborhood || form.neighborhood
    form.city = data.city || form.city
    form.state = data.state || form.state
    form.ibge_code = data.ibge_code || form.ibge_code
    toast.success('Dados do CNPJ preenchidos')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'CNPJ não encontrado')
  } finally {
    lookingUp.value = false
  }
}

async function submit() {
  saving.value = true
  try {
    if (isNew.value) {
      const created = await peopleStore.createPerson(form)
      toast.success('Pessoa criada')
      router.push(`/people/${created.id}`)
    } else {
      await peopleStore.updatePerson(personId.value, form)
      toast.success('Pessoa atualizada')
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  if (isNew.value && cmigs.value.length > 0 && !form.cmig_id) {
    form.cmig_id = cmigs.value[0].id
  }
  if (!isNew.value) {
    try {
      const data = await peopleStore.fetchPerson(personId.value)
      Object.assign(form, data)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Erro ao carregar pessoa')
      router.push('/people')
    }
  }
})
</script>
