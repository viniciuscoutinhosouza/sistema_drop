<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><i class="fas fa-address-book mr-2"></i>Pessoas</h1>
            <small class="text-muted">Cadastro unificado de Clientes e Fornecedores</small>
          </div>
          <div class="col-sm-6 text-right">
            <RouterLink to="/people/new" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Nova Pessoa
            </RouterLink>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <!-- Filtros -->
        <div class="card">
          <div class="card-body">
            <div class="row">
              <div class="col-md-3" v-if="cmigs.length > 1">
                <label class="small mb-1">CMIG</label>
                <select v-model="filters.cmig_id" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option v-for="c in cmigs" :key="c.id" :value="c.id">{{ c.company_name }}</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Tipo</label>
                <select v-model="typeFilter" class="form-control form-control-sm" @change="reload">
                  <option value="">Todos</option>
                  <option value="customer">Clientes</option>
                  <option value="supplier">Fornecedores</option>
                  <option value="carrier">Transportadores</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Status</label>
                <select v-model="filters.is_active" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todos</option>
                  <option :value="true">Ativos</option>
                  <option :value="false">Inativos</option>
                </select>
              </div>
              <div class="col-md-4">
                <label class="small mb-1">Busca (nome ou documento)</label>
                <div class="input-group input-group-sm">
                  <input v-model="filters.search" class="form-control" placeholder="Digite para buscar..."
                         @keyup.enter="reload">
                  <div class="input-group-append">
                    <button class="btn btn-outline-secondary" @click="reload">
                      <i class="fas fa-search"></i>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Listagem -->
        <div class="card">
          <div class="card-header">
            <h3 class="card-title">
              <i class="fas fa-users mr-2"></i>
              {{ total }} pessoa{{ total === 1 ? '' : 's' }}
            </h3>
          </div>
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Documento</th>
                  <th>Nome / Razão Social</th>
                  <th>Cidade/UF</th>
                  <th>Tipo</th>
                  <th>Status</th>
                  <th class="text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="people.length === 0">
                  <td colspan="6" class="text-center text-muted py-4">Nenhuma pessoa encontrada.</td>
                </tr>
                <tr v-for="p in people" :key="p.id" style="cursor:pointer" @click="$router.push(`/people/${p.id}`)">
                  <td>
                    <code>{{ formatDoc(p.document, p.person_type) }}</code>
                    <small class="d-block text-muted">{{ p.person_type }}</small>
                  </td>
                  <td>
                    <strong>{{ p.name }}</strong>
                    <small v-if="p.trade_name" class="d-block text-muted">{{ p.trade_name }}</small>
                  </td>
                  <td>
                    <span v-if="p.city">{{ p.city }}/{{ p.state }}</span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <span v-if="p.is_customer" class="badge badge-info mr-1">Cliente</span>
                    <span v-if="p.is_supplier" class="badge badge-warning mr-1">Fornecedor</span>
                    <span v-if="p.is_carrier" class="badge badge-secondary">Transp.</span>
                  </td>
                  <td>
                    <span class="badge" :class="p.is_active ? 'badge-success' : 'badge-secondary'">
                      {{ p.is_active ? 'Ativo' : 'Inativo' }}
                    </span>
                  </td>
                  <td class="text-right" @click.stop>
                    <RouterLink :to="`/people/${p.id}`" class="btn btn-sm btn-outline-primary mr-1" title="Editar">
                      <i class="fas fa-edit"></i>
                    </RouterLink>
                    <button class="btn btn-sm btn-outline-danger" @click="askDelete(p)" title="Excluir">
                      <i class="fas fa-trash"></i>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="total > pageSize" class="card-footer">
            <button class="btn btn-sm btn-outline-secondary mr-2" :disabled="filters.page === 1"
                    @click="filters.page--; reload()">
              <i class="fas fa-chevron-left"></i> Anterior
            </button>
            <span class="text-muted">Página {{ filters.page }} de {{ totalPages }}</span>
            <button class="btn btn-sm btn-outline-secondary ml-2" :disabled="filters.page >= totalPages"
                    @click="filters.page++; reload()">
              Próxima <i class="fas fa-chevron-right"></i>
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePeopleStore } from '@/stores/people'
import { useCmigStore } from '@/stores/cmig'
import { useToast } from '@/composables/useToast'

const peopleStore = usePeopleStore()
const cmigStore = useCmigStore()
const toast = useToast()

const { people, total, loading } = storeToRefs(peopleStore)
const { cmigs } = storeToRefs(cmigStore)

const pageSize = 20
const typeFilter = ref('')
const filters = reactive({
  cmig_id: null,
  search: '',
  is_active: null,
  is_customer: null,
  is_supplier: null,
  is_carrier: null,
  page: 1,
  page_size: pageSize,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

watch(typeFilter, (v) => {
  filters.is_customer = v === 'customer' ? true : null
  filters.is_supplier = v === 'supplier' ? true : null
  filters.is_carrier = v === 'carrier' ? true : null
})

async function reload() {
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== '') params[k] = v
  }
  try {
    await peopleStore.fetchPeople(params)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar pessoas')
  }
}

async function askDelete(p) {
  if (!confirm(`Excluir ${p.name}?`)) return
  try {
    await peopleStore.deletePerson(p.id)
    toast.success('Pessoa excluída')
    reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao excluir')
  }
}

function formatDoc(doc, type) {
  if (!doc) return ''
  const d = String(doc).replace(/\D/g, '')
  if (type === 'PJ' && d.length === 14) {
    return `${d.slice(0,2)}.${d.slice(2,5)}.${d.slice(5,8)}/${d.slice(8,12)}-${d.slice(12)}`
  }
  if (type === 'PF' && d.length === 11) {
    return `${d.slice(0,3)}.${d.slice(3,6)}.${d.slice(6,9)}-${d.slice(9)}`
  }
  return d
}

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  reload()
})
</script>
