<template>
  <div class="card">
    <div class="card-header">
      <h3 class="card-title"><i class="fas fa-warehouse mr-2"></i>Integração eShip (WMS)</h3>
    </div>
    <div class="card-body">
      <div v-if="loading" class="text-center py-4">
        <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
      </div>
      <div v-else>
        <div class="alert py-2" :class="config.eship_active && config.eship_api_key_set ? 'alert-success' : 'alert-secondary'">
          <i class="fas mr-1" :class="config.eship_active && config.eship_api_key_set ? 'fa-check-circle' : 'fa-info-circle'"></i>
          <strong>{{ statusLabel }}</strong>
          <span class="d-block small text-muted">
            Envia produtos, pedidos, NF-e e etiqueta ao WMS eShip e sincroniza estoque/status.
          </span>
        </div>

        <form @submit.prevent="save">
          <div class="row">
            <div class="col-md-6 form-group">
              <label class="small mb-1">URL base do eShip <span class="text-danger">*</span></label>
              <input v-model="form.eship_base_url" class="form-control" :disabled="!canEdit"
                     placeholder="https://armazenaki.eship.com.br/v3">
              <small class="form-text text-muted">Subdomínio da sua conta eShip + /v3</small>
            </div>
            <div class="col-md-3 form-group">
              <label class="small mb-1">Código do armazém <span class="text-danger">*</span></label>
              <input v-model="form.eship_warehouse_code" class="form-control" :disabled="!canEdit"
                     placeholder="2">
              <small class="form-text text-muted">codigoArmazemOrigem (também usado nos anexos)</small>
            </div>
            <div class="col-md-3 form-group">
              <label class="small mb-1">Integração ativa</label>
              <div class="custom-control custom-switch mt-2">
                <input type="checkbox" class="custom-control-input" id="eshipActive"
                       v-model="form.eship_active" :disabled="!canEdit">
                <label class="custom-control-label" for="eshipActive">
                  {{ form.eship_active ? 'Ativa' : 'Inativa' }}
                </label>
              </div>
            </div>
          </div>

          <!-- Cadastro da empresa DENTRO do eShip — vão no webServicePostOrdem -->
          <div class="row">
            <div class="col-md-3 form-group">
              <label class="small mb-1">idTipo</label>
              <input v-model="form.eship_id_tipo" type="number" class="form-control" :disabled="!canEdit"
                     placeholder="104">
              <small class="form-text text-muted">idTipo da ordem no eShip</small>
            </div>
            <div class="col-md-6 form-group">
              <label class="small mb-1">Tipo da ordem</label>
              <input v-model="form.eship_tipo_ordem" class="form-control" :disabled="!canEdit"
                     placeholder="MIG IMPORTACOES">
              <small class="form-text text-muted">tipoOrdem — nome do tipo cadastrado no eShip</small>
            </div>
          </div>

          <div class="form-group">
            <label class="small mb-1">
              Token da API (apikey) {{ config.eship_api_key_set ? '(já configurado)' : '' }}
              <span v-if="!config.eship_api_key_set" class="text-danger">*</span>
            </label>
            <input v-model="form.eship_api_key" type="password" class="form-control" autocomplete="new-password"
                   :disabled="!canEdit"
                   :placeholder="config.eship_api_key_set ? '•••••••• (deixe em branco para manter)' : 'cole a apikey do painel eShip'">
            <small class="form-text text-muted">Enviado no header <code>api</code> de cada requisição. Único por empresa.</small>
          </div>

          <div class="text-right" v-if="canEdit">
            <button type="submit" class="btn btn-primary" :disabled="saving">
              <i class="fas" :class="saving ? 'fa-spinner fa-spin' : 'fa-save'"></i>
              {{ saving ? 'Salvando...' : 'Salvar integração eShip' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({ cmigId: { type: Number, required: true } })

const toast = useToast()
const authStore = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const config = ref({})
const form = reactive({
  eship_base_url: '',
  eship_warehouse_code: '',
  eship_id_tipo: '',
  eship_tipo_ordem: '',
  eship_api_key: '',
  eship_active: false,
})

const canEdit = computed(() => ['ac', 'admin'].includes(authStore.user?.role))
const statusLabel = computed(() => {
  if (!config.value.eship_api_key_set) return 'Não configurado'
  return config.value.eship_active ? 'Integração ativa' : 'Configurado, mas inativo'
})

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/cmigs/${props.cmigId}/eship-config`)
    config.value = data
    form.eship_base_url = data.eship_base_url || ''
    form.eship_warehouse_code = data.eship_warehouse_code || ''
    form.eship_id_tipo = data.eship_id_tipo ?? ''
    form.eship_tipo_ordem = data.eship_tipo_ordem || ''
    form.eship_active = !!data.eship_active
    form.eship_api_key = ''
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar config eShip')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    const payload = {
      eship_base_url: form.eship_base_url,
      eship_warehouse_code: form.eship_warehouse_code,
      eship_id_tipo: form.eship_id_tipo === '' ? null : form.eship_id_tipo,
      eship_tipo_ordem: form.eship_tipo_ordem,
      eship_active: form.eship_active,
    }
    if (form.eship_api_key) payload.eship_api_key = form.eship_api_key
    const { data } = await api.patch(`/cmigs/${props.cmigId}/eship-config`, payload)
    config.value = data
    form.eship_api_key = ''
    toast.success('Integração eShip salva')
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
