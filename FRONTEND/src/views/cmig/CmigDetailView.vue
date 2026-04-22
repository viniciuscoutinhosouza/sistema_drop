<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">{{ cmig?.company_name || 'CMIG' }}</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/cmigs" class="btn btn-secondary mr-2">
              <i class="fas fa-arrow-left mr-1"></i> Voltar
            </RouterLink>
            <RouterLink v-if="isAC" :to="`/cmigs/${cmig?.id}/edit`" class="btn btn-primary mr-2">
              <i class="fas fa-edit mr-1"></i> Editar
            </RouterLink>
            <RouterLink :to="`/cmig-products?cmig_id=${cmig?.id}`" class="btn btn-info">
              <i class="fas fa-box mr-1"></i> Produtos CMIG
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content" v-if="cmig">
      <div class="container-fluid">
        <div class="row">
          <!-- Info Card -->
          <div class="col-md-4">
            <div class="card">
              <div class="card-header"><h3 class="card-title">Informações</h3></div>
              <div class="card-body">
                <dl class="row mb-0">
                  <dt class="col-sm-5">CNPJ</dt>
                  <dd class="col-sm-7">{{ cmig.cnpj }}</dd>
                  <dt class="col-sm-5">Razão Social</dt>
                  <dd class="col-sm-7">{{ cmig.company_name }}</dd>
                  <dt class="col-sm-5">Nome Fantasia</dt>
                  <dd class="col-sm-7">{{ cmig.trade_name || '—' }}</dd>
                  <dt class="col-sm-5">E-mail</dt>
                  <dd class="col-sm-7">{{ cmig.email || '—' }}</dd>
                  <dt class="col-sm-5">Telefone</dt>
                  <dd class="col-sm-7">{{ cmig.phone || '—' }}</dd>
                  <dt class="col-sm-5">Status</dt>
                  <dd class="col-sm-7">
                    <span class="badge" :class="cmig.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ cmig.is_active ? 'Ativa' : 'Inativa' }}
                    </span>
                  </dd>
                </dl>
              </div>
            </div>
          </div>

          <!-- NF-e Configs -->
          <div class="col-md-8">
            <div class="card">
              <div class="card-header d-flex align-items-center">
                <h3 class="card-title flex-grow-1"><i class="fas fa-file-invoice mr-2"></i>Configurações de NF-e por CM</h3>
                <button v-if="isAC" class="btn btn-sm btn-primary" @click="showNFeModal = true">
                  <i class="fas fa-plus mr-1"></i> Nova Regra
                </button>
              </div>
              <div class="card-body p-0">
                <div v-if="loadingNfe" class="text-center py-3">
                  <i class="fas fa-spinner fa-spin text-muted"></i>
                </div>
                <table v-else class="table table-sm mb-0">
                  <thead>
                    <tr>
                      <th>CM</th>
                      <th>Método de Envio</th>
                      <th>Emissor</th>
                      <th v-if="isAC">Ações</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-if="nfeConfigs.length === 0">
                      <td :colspan="isAC ? 4 : 3" class="text-center text-muted py-3">Nenhuma regra NF-e configurada.</td>
                    </tr>
                    <tr v-for="cfg in nfeConfigs" :key="cfg.id">
                      <td>CM #{{ cfg.cm_id }}</td>
                      <td>{{ cfg.shipping_method }}</td>
                      <td>
                        <span class="badge" :class="cfg.issuer === 'system' ? 'badge-primary' : 'badge-warning'">
                          {{ cfg.issuer === 'system' ? 'Sistema' : 'Marketplace' }}
                        </span>
                      </td>
                      <td v-if="isAC">
                        <button class="btn btn-sm btn-outline-danger" @click="deleteNfe(cfg)" title="Remover">
                          <i class="fas fa-trash"></i>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Co-administradores -->
            <div class="card" v-if="isAC">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-users mr-2"></i>Co-administradores</h3>
              </div>
              <div class="card-body">
                <p class="text-muted">Adicione outros ACs cadastrados para co-administrar esta CMIG.</p>
                <div class="input-group">
                  <input v-model="coAdminId" type="number" class="form-control" placeholder="ID do AC" />
                  <div class="input-group-append">
                    <button class="btn btn-outline-primary" @click="addCoAdmin">Adicionar</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Modal Nova Regra NF-e -->
    <div v-if="showNFeModal" class="modal d-block" tabindex="-1" style="background:rgba(0,0,0,.5)">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Nova Regra NF-e</h5>
            <button type="button" class="close" @click="showNFeModal = false"><span>&times;</span></button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label>CM (Conta Marketplace)</label>
              <select v-model="nfeForm.cm_id" class="form-control">
                <option value="">Selecione uma CM...</option>
                <option v-for="cm in cms" :key="cm.id" :value="cm.id">{{ cm.description || cm.platform }} ({{ cm.email }})</option>
              </select>
            </div>
            <div class="form-group">
              <label>Método de Envio</label>
              <select v-model="nfeForm.shipping_method" class="form-control">
                <option value="FULL_ML">FULL Mercado Livre</option>
                <option value="ENVIOS_ML">Envios Mercado Livre</option>
                <option value="NORMAL_SHOPEE">Normal Shopee</option>
                <option value="SHOPEE_EXPRESS">Shopee Express</option>
                <option value="OUTRO">Outro</option>
              </select>
            </div>
            <div class="form-group">
              <label>Responsável pela NF-e</label>
              <select v-model="nfeForm.issuer" class="form-control">
                <option value="marketplace">Marketplace (não emitir)</option>
                <option value="system">Sistema (emitir NF-e)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Observações</label>
              <input v-model="nfeForm.notes" class="form-control" />
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" @click="showNFeModal = false">Cancelar</button>
            <button class="btn btn-primary" @click="saveNfe" :disabled="savingNfe">
              <span v-if="savingNfe"><i class="fas fa-spinner fa-spin mr-1"></i></span>
              Salvar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const cmig = ref(null)
const nfeConfigs = ref([])
const cms = ref([])
const loadingNfe = ref(false)
const showNFeModal = ref(false)
const savingNfe = ref(false)
const coAdminId = ref('')

const nfeForm = ref({ cm_id: '', shipping_method: 'FULL_ML', issuer: 'marketplace', notes: '' })

const isAC = computed(() => authStore.user?.role === 'ac')
const cmigId = computed(() => route.params.id)

onMounted(async () => {
  const { data } = await api.get(`/cmigs/${cmigId.value}`)
  cmig.value = data
  loadNfeConfigs()
  // Carregar CMs da CMIG
  const { data: accData } = await api.get('/accounts', { params: { cmig_id: cmigId.value } }).catch(() => ({ data: [] }))
  cms.value = Array.isArray(accData) ? accData : (accData?.items || [])
})

async function loadNfeConfigs() {
  if (!cms.value.length) return
  loadingNfe.value = true
  try {
    const configs = []
    for (const cm of cms.value) {
      const { data } = await api.get(`/cmigs/${cmigId.value}/nfe-configs/${cm.id}`).catch(() => ({ data: [] }))
      configs.push(...(data || []))
    }
    nfeConfigs.value = configs
  } finally {
    loadingNfe.value = false
  }
}

async function saveNfe() {
  if (!nfeForm.value.cm_id) { toast.error('Selecione uma CM.'); return }
  savingNfe.value = true
  try {
    await api.post(`/cmigs/${cmigId.value}/nfe-configs/${nfeForm.value.cm_id}`, nfeForm.value)
    toast.success('Regra NF-e salva!')
    showNFeModal.value = false
    nfeForm.value = { cm_id: '', shipping_method: 'FULL_ML', issuer: 'marketplace', notes: '' }
    loadNfeConfigs()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar regra NF-e.')
  } finally {
    savingNfe.value = false
  }
}

async function deleteNfe(cfg) {
  if (!confirm('Remover esta regra NF-e?')) return
  await api.delete(`/cmigs/${cmigId.value}/nfe-configs/${cfg.cm_id}/${cfg.id}`)
  toast.success('Regra removida.')
  loadNfeConfigs()
}

async function addCoAdmin() {
  if (!coAdminId.value) return
  try {
    await api.post(`/cmigs/${cmigId.value}/admins`, { user_id: Number(coAdminId.value) })
    toast.success('Co-administrador adicionado!')
    coAdminId.value = ''
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao adicionar co-admin.')
  }
}
</script>
