<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0"><i class="fas fa-clipboard-list mr-2 text-success"></i>Inventários</h5>
      <RouterLink v-if="canCreate" to="/inventario/novo" class="btn btn-primary">
        <i class="fas fa-plus mr-1"></i> Novo Inventário
      </RouterLink>
    </div>

    <div class="card">
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-5">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>
        <table v-else class="table table-hover table-sm mb-0">
          <thead class="thead-light">
            <tr>
              <th>#</th>
              <th>Catálogo</th>
              <th>Modo</th>
              <th>Itens</th>
              <th>Status</th>
              <th>Criado por</th>
              <th>Criado em</th>
              <th>Finalizado</th>
              <th class="text-center">Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="rows.length === 0">
              <td colspan="9" class="text-center text-muted py-4">Nenhum inventário cadastrado.</td>
            </tr>
            <tr v-for="r in rows" :key="r.id" style="cursor:pointer" @click="open(r)">
              <td class="font-weight-bold">{{ r.number }}</td>
              <td>
                <span v-if="r.catalog_type === 'pg'" class="badge badge-secondary">PG</span>
                <span v-else class="badge badge-info">CMIG: {{ r.cmig_name || r.cmig_id }}</span>
              </td>
              <td>
                <span :class="r.mode === 'baseline' ? 'badge badge-primary' : 'badge badge-warning'">
                  {{ r.mode === 'baseline' ? 'Baseline' : 'Ajuste' }}
                </span>
              </td>
              <td>{{ r.item_count }}</td>
              <td><span :class="statusBadge(r.status)">{{ statusLabel(r.status) }}</span></td>
              <td class="text-muted small">{{ r.created_by_name || '—' }}</td>
              <td class="text-nowrap small">{{ fmt(r.created_at) }}</td>
              <td class="text-nowrap small">{{ r.finalized_at ? fmt(r.finalized_at) : '—' }}</td>
              <td class="text-center">
                <button class="btn btn-xs btn-outline-primary" title="Abrir" @click.stop="open(r)">
                  <i class="fas fa-folder-open"></i>
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/composables/useApi'

const router = useRouter()
const authStore = useAuthStore()

const rows = ref([])
const loading = ref(false)

const canCreate = computed(() => {
  const u = authStore.user
  if (u?.role === 'admin') return true
  return Array.isArray(u?.menu_permissions) && u.menu_permissions.includes('inventario_criar')
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/inventories')
    rows.value = Array.isArray(data) ? data : []
  } catch { rows.value = [] } finally {
    loading.value = false
  }
}

function open(r) {
  router.push(`/inventario/${r.id}`)
}

function statusLabel(s) {
  return { draft: 'Rascunho', finalized: 'Finalizado', cancelled: 'Cancelado' }[s] || s
}
function statusBadge(s) {
  return { draft: 'badge badge-secondary', finalized: 'badge badge-success', cancelled: 'badge badge-danger' }[s] || 'badge badge-light'
}
function fmt(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleString('pt-BR')
}
</script>
