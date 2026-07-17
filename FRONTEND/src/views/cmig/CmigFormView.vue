<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ isEdit ? 'Editar CMIG' : 'Nova Conta MIG' }}</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/cmigs" class="btn btn-secondary">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="row">
          <div class="col-lg-9">
            <div class="card">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-id-card mr-2"></i>Dados da CMIG</h3>
              </div>
              <form @submit.prevent="submit">
                <div class="card-body">
                  <div v-if="error" class="alert alert-danger">{{ error }}</div>

                  <h6 class="text-muted text-uppercase mb-3"><small>Identificação</small></h6>

                  <!-- Toggle PJ / PF — disponível também na edição (permite converter o tipo fiscal) -->
                  <div class="form-group mb-3">
                    <div class="btn-group btn-group-sm" role="group">
                      <button type="button" class="btn" :class="personType === 'pj' ? 'btn-primary' : 'btn-outline-secondary'" @click="setPersonType('pj')">
                        <i class="fas fa-building mr-1"></i> Pessoa Jurídica (CNPJ)
                      </button>
                      <button type="button" class="btn" :class="personType === 'pf' ? 'btn-primary' : 'btn-outline-secondary'" @click="setPersonType('pf')">
                        <i class="fas fa-user mr-1"></i> Pessoa Física (CPF)
                      </button>
                    </div>
                    <small v-if="isEdit" class="d-block text-muted mt-1">
                      Trocar o tipo converte a identidade fiscal da conta (CPF ⇆ CNPJ).
                    </small>
                  </div>

                  <!-- Aviso de impacto ao CONVERTER o tipo fiscal na edição -->
                  <div v-if="isConverting" class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle mr-1"></i>
                    <strong>Você está convertendo o tipo fiscal desta conta ({{ originalType === 'pf' ? 'CPF → CNPJ' : 'CNPJ → CPF' }}).</strong>
                    <ul class="mb-0 mt-1 pl-3">
                      <li>Pedidos <em>ainda pendentes</em> de documento fiscal passarão a exigir
                        {{ personType === 'pj' ? 'NF-e (PJ)' : 'DC-e (PF)' }} — não o documento anterior.</li>
                      <li>Se houver integração <strong>eShip</strong> ativa, recadastre os produtos no WMS com a nova identidade (o cadastro é filtrado por CPF/CNPJ).</li>
                      <li>O tipo de pessoa da conta no <strong>marketplace</strong> não muda por aqui — uma conta ML de CPF continua exigindo DC-e no ML.</li>
                    </ul>
                  </div>

                  <div class="row">
                    <!-- PJ: CNPJ -->
                    <div v-if="personType === 'pj'" class="col-md-4 form-group">
                      <label>CNPJ <span class="text-danger">*</span></label>
                      <input v-model="form.cnpj" class="form-control" :required="personType === 'pj'" :disabled="isEdit && originalType === 'pj' && !!originalCnpj" placeholder="00.000.000/0000-00" />
                    </div>
                    <!-- PF: CPF -->
                    <div v-if="personType === 'pf'" class="col-md-4 form-group">
                      <label>CPF <span class="text-danger">*</span></label>
                      <input v-model="form.cpf" class="form-control" :required="personType === 'pf'" :disabled="isEdit && originalType === 'pf' && !!originalCpf" placeholder="000.000.000-00" />
                    </div>

                    <div class="col-md-4 form-group">
                      <label>{{ personType === 'pf' ? 'Nome Completo' : 'Razão Social' }} <span class="text-danger">*</span></label>
                      <input v-model="form.company_name" class="form-control" required />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>{{ personType === 'pf' ? 'Apelido' : 'Nome Fantasia' }}</label>
                      <input v-model="form.trade_name" class="form-control" />
                    </div>
                  </div>

                  <!-- IE só na conversão CPF→CNPJ (fora dela, a IE mora na Configuração Fiscal).
                       O IBGE aparece SEMPRE para PJ: é obrigatório na NF-e própria (cMunFG) e
                       ficava inacessível fora da conversão — ninguém achava onde preencher. -->
                  <div v-if="personType === 'pj'" class="row">
                    <div v-if="isConverting" class="col-md-4 form-group">
                      <label>Inscrição Estadual (IE) <span class="text-danger">*</span></label>
                      <input v-model="form.ie" class="form-control" :required="isConverting" placeholder="Somente números ou ISENTO" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Código IBGE do município <span v-if="isConverting" class="text-danger">*</span></label>
                      <input v-model="form.ibge_code" class="form-control" :required="isConverting" maxlength="7" placeholder="ex.: 3550308" />
                      <small class="form-text text-muted">
                        Código do município do endereço fiscal (7 dígitos) — obrigatório para emitir NF-e
                        e para a prévia em PDF. Consulte em ibge.gov.br/explica/codigos-dos-municipios.php
                      </small>
                    </div>
                  </div>

                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>E-mail Fiscal</label>
                      <input v-model="form.email" type="email" class="form-control" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Telefone</label>
                      <input v-model="form.phone" class="form-control" />
                    </div>
                    <div class="col-md-4 form-group" v-if="!isEdit">
                      <label>Galpão</label>
                      <input class="form-control" :value="warehouseLabel" disabled />
                    </div>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Endereço</small></h6>
                  <div class="row">
                    <div class="col-md-3 form-group">
                      <label>CEP</label>
                      <div class="input-group">
                        <input v-model="form.zip_code" class="form-control" placeholder="00000-000" maxlength="9" @blur="fetchCep" />
                        <div class="input-group-append">
                          <span class="input-group-text" style="cursor:pointer" @click="fetchCep">
                            <i class="fas fa-search"></i>
                          </span>
                        </div>
                      </div>
                    </div>
                    <div class="col-md-6 form-group">
                      <label>Logradouro</label>
                      <input v-model="form.street" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Número</label>
                      <input v-model="form.address_number" class="form-control" />
                    </div>
                  </div>
                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>Complemento</label>
                      <input v-model="form.complement" class="form-control" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Bairro</label>
                      <input v-model="form.neighborhood" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Cidade</label>
                      <input v-model="form.city" class="form-control" />
                    </div>
                    <div class="col-md-1 form-group">
                      <label>UF</label>
                      <input v-model="form.state" class="form-control" maxlength="2" />
                    </div>
                  </div>

                  <template v-if="isEdit">
                    <hr />
                    <div class="form-group">
                      <div class="custom-control custom-switch">
                        <input v-model="form.is_active" type="checkbox" class="custom-control-input" id="is_active" />
                        <label class="custom-control-label" for="is_active">CMIG Ativa</label>
                      </div>
                    </div>
                  </template>
                </div>
                <div class="card-footer">
                  <button type="submit" class="btn btn-primary" :disabled="saving">
                    <span v-if="saving"><i class="fas fa-spinner fa-spin mr-1"></i>Salvando...</span>
                    <span v-else><i class="fas fa-save mr-1"></i>{{ isEdit ? 'Salvar Alterações' : 'Cadastrar CMIG' }}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCmigStore } from '@/stores/cmig'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const cmigStore = useCmigStore()
const authStore = useAuthStore()
const toast = useToast()

const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const error = ref('')
const warehouseLabel = ref('')
const personType = ref('pj') // 'pj' | 'pf'
// Estado fiscal ORIGINAL (para detectar conversão de tipo na edição).
const originalType = ref(null) // 'pj' | 'pf' | null (criação)
const originalCnpj = ref('')
const originalCpf = ref('')

const form = ref({
  cnpj: '',
  cpf: '',
  company_name: '',
  trade_name: '',
  email: '',
  phone: '',
  warehouse_id: '',
  zip_code: '',
  street: '',
  address_number: '',
  complement: '',
  neighborhood: '',
  city: '',
  state: '',
  ibge_code: '',
  ie: '',
  is_active: true,
})

// Só é "conversão" quando o tipo escolhido difere do tipo original de uma conta existente.
const isConverting = computed(() => isEdit.value && originalType.value && personType.value !== originalType.value)

function setPersonType(type) {
  personType.value = type
  form.value.cnpj = ''
  form.value.cpf = ''
}

onMounted(async () => {
  try {
    const { data: wh } = await api.get('/warehouse')
    const w = Array.isArray(wh) ? wh[0] : wh
    if (w) {
      form.value.warehouse_id = w.id
      warehouseLabel.value = w.name || w.company_name || `Galpão #${w.id}`
    }
  } catch { }
  if (isEdit.value) {
    const { data } = await api.get(`/cmigs/${route.params.id}`)
    Object.assign(form.value, data)
    // Inferir tipo a partir dos dados existentes
    personType.value = data.cpf && !data.cnpj ? 'pf' : 'pj'
    originalType.value = personType.value
    originalCnpj.value = data.cnpj || ''
    originalCpf.value = data.cpf || ''
    // Prefill da IE (mora no fiscal-config) para não exigir redigitar na conversão.
    try {
      const { data: fc } = await api.get(`/cmigs/${route.params.id}/fiscal-config`)
      if (fc?.ie) form.value.ie = fc.ie
    } catch { }
  }
})

async function fetchCep() {
  const cep = form.value.zip_code?.replace(/\D/g, '')
  if (cep?.length !== 8) return
  try {
    const { data } = await api.get(`/users/address/lookup/${cep}`)
    form.value.street = data.street
    form.value.neighborhood = data.neighborhood
    form.value.city = data.city
    form.value.state = data.state
  } catch {}
}

async function submit() {
  error.value = ''
  saving.value = true
  try {
    if (isEdit.value) {
      await cmigStore.updateCmig(route.params.id, form.value)
      toast.success('CMIG atualizada com sucesso!')
    } else {
      await cmigStore.createCmig(form.value)
      toast.success('CMIG cadastrada com sucesso!')
    }
    router.push('/cmigs')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar CMIG.'
  } finally {
    saving.value = false
  }
}
</script>
