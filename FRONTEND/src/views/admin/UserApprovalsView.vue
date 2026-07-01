<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0"><i class="fas fa-user-check text-primary mr-2"></i>Aprovações de Cadastro</h1>
            <small class="text-muted">Colaboradores convidados que se cadastraram e aguardam liberação de acesso.</small>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <div v-else-if="items.length === 0" class="text-center py-5 text-muted">
              <i class="fas fa-inbox fa-2x mb-2 d-block"></i>
              Nenhum cadastro aguardando liberação.
            </div>
            <table v-else class="table table-hover mb-0">
              <thead class="thead-light">
                <tr>
                  <th>Nome</th><th>E-mail</th><th>WhatsApp</th><th>Convidado por (empresa)</th>
                  <th>Data</th><th class="text-right" style="width:180px">Ação</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="it in items" :key="it.invite_id">
                  <td><strong>{{ it.full_name }}</strong></td>
                  <td class="text-muted small">{{ it.email }}</td>
                  <td class="text-muted small">{{ it.whatsapp || '—' }}</td>
                  <td>{{ it.company_name || '—' }}</td>
                  <td class="text-muted small">{{ fmtDate(it.created_at) }}</td>
                  <td class="text-right">
                    <button class="btn btn-sm btn-success mr-1" :disabled="busy[it.invite_id]" @click="approve(it)">
                      <i class="fas fa-check mr-1"></i>Liberar
                    </button>
                    <button class="btn btn-sm btn-outline-danger" :disabled="busy[it.invite_id]" @click="reject(it)">
                      <i class="fas fa-times"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { formatDateTime } from '@/utils/formatters'

const toast = useToast()
const loading = ref(true)
const items = ref([])
const busy = reactive({})

function fmtDate(d) { return d ? formatDateTime(d) : '—' }

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/users/approvals')
    items.value = Array.isArray(data) ? data : []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar aprovações')
  } finally {
    loading.value = false
  }
}

async function approve(it) {
  busy[it.invite_id] = true
  try {
    await api.post(`/users/approvals/${it.invite_id}/approve`)
    toast.success('Acesso liberado. O dono da conta já pode vincular o colaborador.')
    items.value = items.value.filter(x => x.invite_id !== it.invite_id)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao liberar')
  } finally {
    busy[it.invite_id] = false
  }
}

async function reject(it) {
  if (!confirm(`Recusar o cadastro de ${it.full_name}?`)) return
  busy[it.invite_id] = true
  try {
    await api.post(`/users/approvals/${it.invite_id}/reject`)
    toast.success('Cadastro recusado.')
    items.value = items.value.filter(x => x.invite_id !== it.invite_id)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao recusar')
  } finally {
    busy[it.invite_id] = false
  }
}

onMounted(load)
</script>
