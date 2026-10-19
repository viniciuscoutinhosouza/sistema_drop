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
                  <template v-if="cmig.cnpj">
                    <dt class="col-sm-5">CNPJ</dt>
                    <dd class="col-sm-7">{{ cmig.cnpj }}</dd>
                    <dt class="col-sm-5">Razão Social</dt>
                    <dd class="col-sm-7">{{ cmig.company_name || '—' }}</dd>
                  </template>
                  <template v-else-if="cmig.cpf">
                    <dt class="col-sm-5">CPF</dt>
                    <dd class="col-sm-7">{{ cmig.cpf }}</dd>
                    <dt class="col-sm-5">Nome</dt>
                    <dd class="col-sm-7">{{ cmig.company_name || '—' }}</dd>
                  </template>
                  <dt class="col-sm-5">{{ (cmig.cpf && !cmig.cnpj) ? 'Apelido' : 'Nome Fantasia' }}</dt>
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
            <!-- Emissor de NF-e agora é por CONTA (ADR-0030): Administração ▸ Integrações ▸ editar
                 conta ▸ "Emissão de NF-e". O quadro antigo "por método de envio" foi aposentado
                 (não tinha efeito no roteamento). -->
            <div class="card">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-file-invoice mr-2"></i>Emissão de NF-e</h3>
              </div>
              <div class="card-body">
                <div class="alert alert-info mb-0 py-2">
                  <i class="fas fa-info-circle mr-1"></i>
                  A escolha entre <strong>emissão própria (SEFAZ)</strong> e <strong>pelo marketplace
                  (Faturador ML)</strong> agora é feita <strong>por conta de marketplace</strong>, em
                  <strong>Administração ▸ Integrações</strong> (editar a conta → "Emissão de NF-e").
                  Requer certificado A1 + série na <em>Configuração Fiscal</em> abaixo. Pedidos FULL
                  seguem sempre pelo Mercado Livre.
                </div>
              </div>
            </div>

            <!-- Configuração Fiscal (NF-e via SEFAZ) -->
            <CmigFiscalConfigCard v-if="cmig" :cmig-id="Number(cmig.id)" />

            <!-- Integração eShip (WMS) -->
            <CmigEShipConfigCard v-if="cmig" :cmig-id="Number(cmig.id)" />

            <!-- Colaboradores -->
            <div class="card" v-if="isAC">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-users mr-2"></i>Colaboradores</h3>
              </div>
              <div class="card-body">
                <p class="text-muted mb-2">
                  Selecione Gestores de Conta cadastrados ou convide por e-mail para co-administrar esta CMIG.
                </p>
                <button class="btn btn-outline-primary" @click="showCollab = true">
                  <i class="fas fa-user-friends mr-1"></i>Gerenciar colaboradores
                </button>
              </div>
            </div>
            <CollaboratorsModal
              v-if="cmig"
              :visible="showCollab"
              entity-type="cmig"
              :entity-id="Number(cmig.id)"
              :entity-label="cmig.company_name || cmig.trade_name"
              @close="showCollab = false"
            />

            <!-- IA de Atendimento -->
            <div class="card" v-if="isAC || isAdmin">
              <div class="card-header">
                <h3 class="card-title"><i class="fas fa-robot mr-2 text-success"></i>IA de Atendimento</h3>
              </div>
              <div class="card-body">
                <div class="form-group mb-2">
                  <div class="custom-control custom-switch">
                    <input type="checkbox" class="custom-control-input" id="switchAutoRespond" v-model="aiConfig.auto_respond" />
                    <label class="custom-control-label" for="switchAutoRespond">
                      Auto-resposta ativada
                    </label>
                  </div>
                  <small class="text-muted d-block mt-1">
                    Quando ativado, a IA responde automaticamente aos compradores sem revisão humana.
                  </small>
                </div>
                <div class="form-group mb-2">
                  <label class="small font-weight-bold">Instruções específicas desta conta</label>
                  <textarea
                    v-model="aiConfig.custom_instructions"
                    class="form-control form-control-sm"
                    rows="4"
                    placeholder="Ex: Esta é a conta da Nike. Produtos originais. Prazo de entrega: 5-7 dias úteis..."
                  ></textarea>
                  <small class="text-muted">Combinadas com as instruções gerais do sistema.</small>
                </div>
                <button class="btn btn-sm btn-success" @click="saveAIConfig" :disabled="savingAI">
                  <i :class="['fas', savingAI ? 'fa-spinner fa-spin' : 'fa-save', 'mr-1']"></i>
                  {{ savingAI ? 'Salvando...' : 'Salvar IA' }}
                </button>
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
import CmigFiscalConfigCard from '@/components/cmigs/CmigFiscalConfigCard.vue'
import CmigEShipConfigCard from '@/components/cmigs/CmigEShipConfigCard.vue'
import CollaboratorsModal from '@/components/common/CollaboratorsModal.vue'

const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const cmig = ref(null)
const nfeConfigs = ref([])
const cms = ref([])
const loadingNfe = ref(false)
const showNFeModal = ref(false)
const savingNfe = ref(false)
const showCollab = ref(false)

const nfeForm = ref({ cm_id: '', shipping_method: 'FULL_ML', issuer: 'marketplace', notes: '' })

const isAC = computed(() => authStore.user?.role === 'ac')
const isAdmin = computed(() => authStore.user?.role === 'admin')
const cmigId = computed(() => route.params.id)

const aiConfig = ref({ auto_respond: false, custom_instructions: '' })
const savingAI = ref(false)

onMounted(async () => {
  const { data } = await api.get(`/cmigs/${cmigId.value}`)
  cmig.value = data
  loadNfeConfigs()
  loadAIConfig()
  // Carregar CMs da CMIG
  const { data: accData } = await api.get('/accounts', { params: { cmig_id: cmigId.value, include_inactive_cmig: true } }).catch(() => ({ data: [] }))
  cms.value = Array.isArray(accData) ? accData : (accData?.items || [])
})

async function loadAIConfig() {
  try {
    const { data } = await api.get(`/ai-config/cmig/${cmigId.value}`)
    aiConfig.value = { auto_respond: data.auto_respond || false, custom_instructions: data.custom_instructions || '' }
  } catch (_) {}
}

async function saveAIConfig() {
  savingAI.value = true
  try {
    await api.put(`/ai-config/cmig/${cmigId.value}`, aiConfig.value)
    toast.success('Configuração de IA salva!')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar configuração de IA.')
  } finally {
    savingAI.value = false
  }
}

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

</script>
