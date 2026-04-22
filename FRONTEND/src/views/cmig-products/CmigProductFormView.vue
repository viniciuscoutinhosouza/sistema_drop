<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ isEdit ? 'Editar Produto CMIG' : 'Novo Produto CMIG' }}</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink :to="`/cmig-products?cmig_id=${cmigId}`" class="btn btn-secondary">
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
                <h3 class="card-title"><i class="fas fa-box mr-2"></i>Dados do Produto</h3>
              </div>
              <form @submit.prevent="submit">
                <div class="card-body">
                  <div v-if="error" class="alert alert-danger">{{ error }}</div>

                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>SKU CMIG <span class="text-danger">*</span></label>
                      <input v-model="form.sku_cmig" class="form-control" required :disabled="isEdit" />
                    </div>
                    <div class="col-md-8 form-group">
                      <label>Título <span class="text-danger">*</span></label>
                      <input v-model="form.title" class="form-control" required />
                    </div>
                  </div>

                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>Marca</label>
                      <input v-model="form.brand" class="form-control" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Preço de Custo</label>
                      <div class="input-group">
                        <div class="input-group-prepend"><span class="input-group-text">R$</span></div>
                        <input v-model="form.cost_price" type="number" step="0.01" class="form-control" />
                      </div>
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Estoque</label>
                      <input v-model="form.stock_quantity" type="number" class="form-control" min="0" />
                    </div>
                  </div>

                  <div class="form-group">
                    <label>Descrição</label>
                    <textarea v-model="form.description" class="form-control" rows="4"></textarea>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Dimensões</small></h6>
                  <div class="row">
                    <div class="col-md-3 form-group">
                      <label>Peso (kg)</label>
                      <input v-model="form.weight_kg" type="number" step="0.001" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Altura (cm)</label>
                      <input v-model="form.height_cm" type="number" step="0.01" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Largura (cm)</label>
                      <input v-model="form.width_cm" type="number" step="0.01" class="form-control" />
                    </div>
                    <div class="col-md-3 form-group">
                      <label>Comprimento (cm)</label>
                      <input v-model="form.length_cm" type="number" step="0.01" class="form-control" />
                    </div>
                  </div>

                  <hr />
                  <h6 class="text-muted text-uppercase mb-3"><small>Informações Fiscais</small></h6>
                  <div class="row">
                    <div class="col-md-4 form-group">
                      <label>NCM</label>
                      <input v-model="form.ncm" class="form-control" maxlength="8" placeholder="00000000" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>CEST</label>
                      <input v-model="form.cest" class="form-control" maxlength="7" placeholder="0000000" />
                    </div>
                    <div class="col-md-4 form-group">
                      <label>Origem</label>
                      <select v-model="form.origin" class="form-control">
                        <option :value="0">0 - Nacional</option>
                        <option :value="1">1 - Estrangeira (Importação Direta)</option>
                        <option :value="2">2 - Estrangeira (Mercado Interno)</option>
                      </select>
                    </div>
                  </div>

                  <div class="form-group" v-if="isEdit">
                    <div class="custom-control custom-switch">
                      <input v-model="form.is_active" type="checkbox" class="custom-control-input" id="is_active" />
                      <label class="custom-control-label" for="is_active">Produto Ativo</label>
                    </div>
                  </div>
                </div>
                <div class="card-footer">
                  <button type="submit" class="btn btn-primary" :disabled="saving">
                    <span v-if="saving"><i class="fas fa-spinner fa-spin mr-1"></i>Salvando...</span>
                    <span v-else><i class="fas fa-save mr-1"></i>{{ isEdit ? 'Salvar Alterações' : 'Cadastrar Produto' }}</span>
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
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const isEdit = computed(() => !!route.params.id)
const cmigId = computed(() => route.query.cmig_id)
const saving = ref(false)
const error = ref('')

const form = ref({
  sku_cmig: '',
  title: '',
  brand: '',
  description: '',
  cost_price: null,
  stock_quantity: 0,
  weight_kg: null,
  height_cm: null,
  width_cm: null,
  length_cm: null,
  ncm: '',
  cest: '',
  origin: 0,
  is_active: true,
})

onMounted(async () => {
  if (isEdit.value) {
    const { data } = await api.get(`/cmigs/${cmigId.value}/products/${route.params.id}`)
    Object.assign(form.value, data)
  }
})

async function submit() {
  error.value = ''
  saving.value = true
  try {
    if (isEdit.value) {
      await api.put(`/cmigs/${cmigId.value}/products/${route.params.id}`, form.value)
      toast.success('Produto atualizado com sucesso!')
    } else {
      await api.post(`/cmigs/${cmigId.value}/products`, form.value)
      toast.success('Produto cadastrado com sucesso!')
    }
    router.push(`/cmig-products?cmig_id=${cmigId.value}`)
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao salvar produto.'
  } finally {
    saving.value = false
  }
}
</script>
