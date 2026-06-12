<template>
  <div>
    <div class="card card-primary card-outline">
      <div class="card-header">
        <h3 class="card-title"><i class="fas fa-dolly-flatbed mr-2"></i>Integração eShip (WMS) por Galpão</h3>
      </div>
      <div class="card-body">
        <p class="text-muted small">
          Configure o servidor eShip de cada galpão. Quando <strong>ativo</strong>, os pedidos do galpão
          podem ser enviados ao eShip e o status/rastreio é sincronizado automaticamente. Deixe inativo
          até validar as credenciais em homologação.
        </p>

        <div v-if="loading" class="text-center py-4">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>

        <div v-else class="table-responsive">
          <table class="table table-sm align-middle">
            <thead>
              <tr>
                <th>Galpão</th>
                <th style="min-width:240px">URL base</th>
                <th style="min-width:200px">API Key</th>
                <th class="text-center">Ativo</th>
                <th class="text-right">Ação</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!rows.length"><td colspan="5" class="text-center text-muted py-3">Nenhum galpão.</td></tr>
              <tr v-for="r in rows" :key="r.warehouse_id">
                <td>{{ r.warehouse_name }}</td>
                <td><input v-model="r.base_url" class="form-control form-control-sm" placeholder="https://..." autocomplete="off"></td>
                <td>
                  <input v-model="r.api_key" type="password" class="form-control form-control-sm"
                         autocomplete="new-password"
                         :placeholder="r.api_key_set ? '•••••• (manter)' : 'apikey eShip'">
                </td>
                <td class="text-center">
                  <div class="custom-control custom-switch">
                    <input :id="`act${r.warehouse_id}`" v-model="r.is_active" type="checkbox" class="custom-control-input">
                    <label class="custom-control-label" :for="`act${r.warehouse_id}`"></label>
                  </div>
                </td>
                <td class="text-right">
                  <button class="btn btn-sm btn-primary" :disabled="r.saving" @click="save(r)">
                    <i class="fas" :class="r.saving ? 'fa-spinner fa-spin' : 'fa-save'"></i> Salvar
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="small text-muted mt-1">
          A API Key não é exibida depois de salva; deixe em branco para manter a atual.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const loading = ref(true)
const rows = ref([])

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/integrations/eship/configs')
    rows.value = data.map(d => ({ ...d, api_key: '', saving: false }))
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar configurações eShip')
  } finally {
    loading.value = false
  }
}

async function save(r) {
  r.saving = true
  try {
    const payload = { base_url: r.base_url, is_active: r.is_active }
    if (r.api_key) payload.api_key = r.api_key
    const { data } = await api.put(`/integrations/eship/configs/${r.warehouse_id}`, payload)
    r.api_key = ''
    r.api_key_set = data.api_key_set
    toast.success(`Galpão "${r.warehouse_name}" salvo`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao salvar')
  } finally {
    r.saving = false
  }
}

onMounted(load)
</script>
