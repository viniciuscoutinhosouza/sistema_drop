<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ isEdit ? 'Editar Gestor Operacional' : 'Novo Gestor Operacional' }}</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/goes" class="btn btn-secondary">
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
                <h3 class="card-title"><i class="fas fa-building mr-2"></i>Empresa / Galpão</h3>
              </div>
              <form @submit.prevent="submit">
                <div class="card-body">
                  <div v-if="error" class="alert alert-danger">{{ error }}</div>

                  <div class="row">
                    <div class="col-md-6 form-group">
                      <label>Razão Social <span class="text-danger">*</span></label>
                      <input v-model="form.company_name" class="form-control" required />
                    </div>
                    <div class="col-md-6 form-group">
                      <label>Nome Fantasia</label>
                      <input v-model="form.trade_name" class="form-control" />
                    </div>
                  </div>
                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>CNPJ <span class="text-danger">*</span></label>
                      <input v-model="form.cnpj" class="form-control" required :disabled="isEdit" placeholder="00.000.000/0000-00" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Telefone</label>
                      <input v-model="form.phone" class="form-control" placeholder="(11) 0000-0000" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>WhatsApp</label>
                      <input v-model="form.whatsapp" class="form-control" placeholder="(11) 90000-0000" />
                    </div>
                  </div>
                  <div class="row">
                    <div class="col-md-6 form-group">
                      <label>E-mail da Empresa</label>
                      <input v-model="form.email" type="email" class="form-control" />
                    </div>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Endereço</small></h6>
                  <div class="row">
                    <div class="col-md-3 form-group">
                      <label>CEP</label>
                      <div class="input-group">
                        <input v-model="form.zip_code" class="form-control" placeholder="00000-000" @blur="lookupCep" />
                        <div class="input-group-append">
                          <span class="input-group-text" style="cursor:pointer" @click="lookupCep">
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
                      <input v-model="form.number" class="form-control" />
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

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Chave PIX</small></h6>
                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>Tipo de Chave</label>
                      <select v-model="form.pix_key_type" class="form-control">
                        <option value="">Nenhuma</option>
                        <option value="cpf">CPF</option>
                        <option value="cnpj">CNPJ</option>
                        <option value="email">E-mail</option>
                        <option value="phone">Telefone</option>
                        <option value="random">Chave Aleatória</option>
                      </select>
                    </div>
                    <div class="col-md-8 form-group">
                      <label>Chave PIX</label>
                      <input v-model="form.pix_key" class="form-control" :disabled="!form.pix_key_type" />
                    </div>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Observações</small></h6>
                  <div class="form-group">
                    <textarea v-model="form.notes" class="form-control" rows="3"></textarea>
                  </div>

                  <!-- Seção do responsável — somente no cadastro -->
                  <template v-if="!isEdit">
                    <hr />
                    <h6 class="text-muted text-uppercase mb-3"><small>Responsável (Pessoa Física)</small></h6>
                    <div class="row">
                      <div class="col-md-6 form-group">
                        <label>Nome Completo <span class="text-danger">*</span></label>
                        <input v-model="form.full_name" class="form-control" required />
                      </div>
                      <div class="col-md-6 form-group">
                        <label>E-mail de Login <span class="text-danger">*</span></label>
                        <input v-model="form.user_email" type="email" class="form-control" required />
                      </div>
                    </div>
                    <div class="row">
                      <div class="col-md-4 form-group">
                        <label>WhatsApp do Responsável</label>
                        <input v-model="form.user_whatsapp" class="form-control" placeholder="(11) 90000-0000" />
                      </div>
                      <div class="col-md-4 form-group">
                        <label>Senha <span class="text-danger">*</span></label>
                        <input v-model="form.password" type="password" class="form-control" required />
                      </div>
                      <div class="col-md-4 form-group">
                        <label>Confirmar Senha <span class="text-danger">*</span></label>
                        <input v-model="form.password_confirm" type="password" class="form-control" required />
                      </div>
                    </div>
                  </template>

                  <template v-if="isEdit">
                    <hr />
                    <div class="form-group">
                      <div class="custom-control custom-switch">
                        <input v-model="form.is_active" type="checkbox" class="custom-control-input" id="is_active" />
                        <label class="custom-control-label" for="is_active">GO Ativo</label>
                      </div>
                    </div>
                  </template>
                </div>
                <div class="card-footer">
                  <button type="submit" class="btn btn-primary" :disabled="saving">
                    <span v-if="saving"><i class="fas fa-spinner fa-spin mr-1"></i>Salvando...</span>
                    <span v-else><i class="fas fa-save mr-1"></i>{{ isEdit ? 'Salvar Alterações' : 'Cadastrar GO' }}</span>
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
import { useGoStore } from '@/stores/go'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const goStore = useGoStore()
const toast = useToast()

const isEdit = computed(() => !!route.params.id)
const saving = ref(false)
const error = ref('')

const form = ref({
  // Empresa / Galpão
  company_name: '',
  trade_name: '',
  cnpj: '',
  phone: '',
  whatsapp: '',
  email: '',
  zip_code: '',
  street: '',
  number: '',
  complement: '',
  neighborhood: '',
  city: '',
  state: '',
  pix_key_type: '',
  pix_key: '',
  notes: '',
  is_active: true,
  // Responsável (só no cadastro)
  full_name: '',
  user_email: '',
  user_whatsapp: '',
  password: '',
  password_confirm: '',
})

onMounted(async () => {
  if (isEdit.value) {
    const { data } = await api.get(`/goes/${route.params.id}`)
    Object.assign(form.value, data)
  }
})

async function lookupCep() {
  const cep = (form.value.zip_code || '').replace(/\D/g, '')
  if (cep.length !== 8) return
  try {
    const { data } = await api.get(`/users/address/lookup/${cep}`)
    if (!data.erro) {
      form.value.street = data.logradouro
      form.value.neighborhood = data.bairro
      form.value.city = data.localidade
      form.value.state = data.uf
    }
  } catch { }
}

async function submit() {
  error.value = ''
  if (!isEdit.value && form.value.password !== form.value.password_confirm) {
    error.value = 'As senhas não coincidem.'
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      const payload = {
        company_name: form.value.company_name,
        trade_name: form.value.trade_name,
        phone: form.value.phone,
        whatsapp: form.value.whatsapp,
        email: form.value.email,
        zip_code: form.value.zip_code,
        street: form.value.street,
        number: form.value.number,
        complement: form.value.complement,
        neighborhood: form.value.neighborhood,
        city: form.value.city,
        state: form.value.state,
        pix_key_type: form.value.pix_key_type,
        pix_key: form.value.pix_key,
        notes: form.value.notes,
        is_active: form.value.is_active,
      }
      await goStore.updateGo(route.params.id, payload)
      toast.success('GO atualizado com sucesso!')
    } else {
      await goStore.createGo(form.value)
      toast.success('GO cadastrado com sucesso!')
    }
    router.push('/goes')
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar GO.'
  } finally {
    saving.value = false
  }
}
</script>
