<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Gestores Operacionais</h1>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/goes/new" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Novo GO
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div class="card">
          <div class="card-header">
            <h3 class="card-title"><i class="fas fa-building mr-2"></i>GOs cadastrados</h3>
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
                <tr v-if="goes.length === 0">
                  <td colspan="6" class="text-center text-muted py-4">Nenhum GO cadastrado.</td>
                </tr>
                <tr v-for="go in goes" :key="go.id">
                  <td>{{ go.id }}</td>
                  <td>
                    <strong>{{ go.company_name }}</strong>
                    <small class="d-block text-muted">{{ go.trade_name }}</small>
                  </td>
                  <td>{{ go.cnpj }}</td>
                  <td>{{ go.email }}</td>
                  <td>
                    <span class="badge" :class="go.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ go.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td>
                    <RouterLink :to="`/goes/${go.id}/edit`" class="btn btn-sm btn-outline-primary mr-1">
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
import { onMounted } from 'vue'
import { useGoStore } from '@/stores/go'
import { storeToRefs } from 'pinia'

const goStore = useGoStore()
const { goes, loading } = storeToRefs(goStore)

onMounted(() => goStore.fetchGoes())
</script>
