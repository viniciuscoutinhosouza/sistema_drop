<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Contas MIG (CMIG)</h1>
          </div>
          <div class="col-sm-6 text-right" v-if="isAC">
            <RouterLink to="/cmigs/new" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Nova CMIG
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-id-card mr-2"></i>CMIGs cadastradas</h3>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover table-striped mb-0">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Razão Social</th>
                  <th>CNPJ</th>
                  <th>E-mail</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="cmigs.length === 0">
                  <td colspan="6" class="text-center text-muted py-4">Nenhuma CMIG cadastrada.</td>
                </tr>
                <tr v-for="cmig in cmigs" :key="cmig.id">
                  <td>{{ cmig.id }}</td>
                  <td>
                    <strong>{{ cmig.company_name }}</strong>
                    <small class="d-block text-muted">{{ cmig.trade_name }}</small>
                  </td>
                  <td>{{ cmig.cnpj }}</td>
                  <td>{{ cmig.email }}</td>
                  <td>
                    <span class="badge" :class="cmig.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ cmig.is_active ? 'Ativa' : 'Inativa' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink :to="`/cmigs/${cmig.id}`" class="btn btn-sm btn-outline-info mr-1" title="Detalhes">
                      <i class="fas fa-eye"></i>
                    </RouterLink>
                    <RouterLink v-if="isAC" :to="`/cmigs/${cmig.id}/edit`" class="btn btn-sm btn-outline-primary" title="Editar">
                      <i class="fas fa-edit"></i>
                    </RouterLink>
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
import { computed, onMounted } from 'vue'
import { useCmigStore } from '@/stores/cmig'
import { useAuthStore } from '@/stores/auth'
import { storeToRefs } from 'pinia'

const cmigStore = useCmigStore()
const authStore = useAuthStore()
const { cmigs, loading } = storeToRefs(cmigStore)

const isAC = computed(() => authStore.user?.role === 'ac')

onMounted(() => cmigStore.fetchCmigs())
</script>
