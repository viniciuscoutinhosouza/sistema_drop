<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><i class="fas fa-arrow-down text-warning mr-2"></i>Entradas (NF-e)</h1>
            <small class="text-muted">NFes recebidas de fornecedores</small>
          </div>
          <div class="col-sm-6 text-right">
            <button class="btn btn-outline-info mr-2" @click="showImport = true">
              <i class="fas fa-file-import mr-1"></i> Importar XML
            </button>
            <button class="btn btn-outline-info mr-2" :disabled="syncing || !filters.cmig_id"
                    @click="syncReceived"
                    :title="filters.cmig_id ? '' : 'Selecione uma CMIG no filtro'">
              <i class="fas" :class="syncing ? 'fa-spinner fa-spin' : 'fa-sync'"></i>
              {{ syncing ? 'Sincronizando...' : 'Sincronizar Recebidas' }}
            </button>
            <RouterLink to="/fiscal/invoices/new?direction=in" class="btn btn-primary">
              <i class="fas fa-plus mr-1"></i> Lançar Manual
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
              <div class="col-md-2">
                <label class="small mb-1">Origem</label>
                <select v-model="filters.inbound_source" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option value="xml_upload">Upload XML</option>
                  <option value="manual">Manual</option>
                  <option value="dfe_focus">DFe Focus</option>
                </select>
              </div>
              <div class="col-md-2">
                <label class="small mb-1">Manifestação</label>
                <select v-model="filters.manifestation" class="form-control form-control-sm" @change="reload">
                  <option :value="null">Todas</option>
                  <option value="pending">Pendente</option>
                  <option value="ciencia">Ciência</option>
                  <option value="confirmacao">Confirmação</option>
                  <option value="desconhecimento">Desconhecimento</option>
                  <option value="nao_realizada">Não Realizada</option>
                </select>
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Buscar (chave)</label>
                <input v-model="filters.search" class="form-control form-control-sm" @keyup.enter="reload">
              </div>
            </div>
            <div class="row mt-2">
              <div class="col-md-3">
                <label class="small mb-1">Data emissão de</label>
                <input v-model="filters.date_from" type="date" class="form-control form-control-sm" @change="reload">
              </div>
              <div class="col-md-3">
                <label class="small mb-1">Data emissão até</label>
                <input v-model="filters.date_to" type="date" class="form-control form-control-sm" @change="reload">
              </div>
            </div>
          </div>
        </div>

        <!-- Tabela -->
        <div class="card">
          <div class="card-body p-0">
            <div v-if="loading" class="text-center py-5">
              <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
            </div>
            <table v-else class="table table-hover mb-0">
              <thead>
                <tr>
                  <th>Chave / Número</th>
                  <th>Emissão</th>
                  <th>Fornecedor</th>
                  <th>Origem</th>
                  <th>Manifestação</th>
                  <th class="text-right">Total</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="invoices.length === 0">
                  <td colspan="8" class="text-center text-muted py-4">Nenhuma NFe de entrada encontrada.</td>
                </tr>
                <tr v-for="inv in invoices" :key="inv.id" style="cursor:pointer"
                    :class="{'table-warning': inv.manifestation === 'pending' && inv.inbound_source === 'dfe_focus'}"
                    @click="$router.push(`/fiscal/invoices/${inv.id}`)">
                  <td>
                    <code v-if="inv.access_key" class="small">…{{ inv.access_key.slice(-12) }}</code>
                    <span v-else-if="inv.nfe_number">{{ inv.nfe_number }} / {{ inv.serie }}</span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>{{ formatDate(inv.issue_date) }}</td>
                  <td>
                    <span v-if="inv.person">
                      <strong>{{ inv.person.name }}</strong>
                      <small class="d-block text-muted">{{ inv.person.document }}</small>
                    </span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td>
                    <span class="badge badge-light">{{ inboundSourceLabel(inv.inbound_source) }}</span>
                  </td>
                  <td>
                    <span class="badge" :class="manifestationClass(inv.manifestation)">
                      {{ manifestationLabel(inv.manifestation) }}
                    </span>
                  </td>
                  <td class="text-right">
                    <strong>{{ formatCurrency(inv.total_invoice) }}</strong>
                  </td>
                  <td>
                    <span class="badge" :class="statusClass(inv.status)">{{ statusLabel(inv.status) }}</span>
                  </td>
                  <td @click.stop class="text-right">
                    <RouterLink :to="`/fiscal/invoices/${inv.id}`" class="btn btn-sm btn-outline-info" title="Detalhes">
                      <i class="fas fa-eye"></i>
                    </RouterLink>
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

    <XmlImportModal
      v-if="showImport"
      :default-cmig-id="filters.cmig_id"
      @close="showImport = false"
      @imported="onImported" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useFiscalStore } from '@/stores/fiscal'
import { useCmigStore } from '@/stores/cmig'
import { useToast } from '@/composables/useToast'
import { fmt } from '@/views/fiscal/_helpers'
import XmlImportModal from '@/components/fiscal/XmlImportModal.vue'

const fiscalStore = useFiscalStore()
const cmigStore = useCmigStore()
const toast = useToast()
const { invoices, total, loading } = storeToRefs(fiscalStore)
const { cmigs } = storeToRefs(cmigStore)

const pageSize = 20
const showImport = ref(false)
const syncing = ref(false)
const filters = reactive({
  cmig_id: null,
  direction: 'in',
  status: null,
  inbound_source: null,
  manifestation: null,
  search: '',
  date_from: '',
  date_to: '',
  page: 1,
  page_size: pageSize,
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function reload() {
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v !== null && v !== '') params[k] = v
  }
  try {
    await fiscalStore.fetchInvoices(params)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar NFes')
  }
}

function onImported() {
  toast.success('XML importado com sucesso!')
  reload()
}

async function syncReceived() {
  if (!filters.cmig_id) {
    toast.warning('Selecione uma CMIG no filtro acima.')
    return
  }
  syncing.value = true
  try {
    const r = await fiscalStore.syncReceived(filters.cmig_id)
    if (r.new > 0) {
      toast.success(`${r.new} nova(s) NFe(s) recebida(s); ${r.skipped} já existente(s)`)
    } else {
      toast.info(`Nenhuma NFe nova encontrada (${r.skipped} já existente${r.skipped === 1 ? '' : 's'})`)
    }
    if (r.errors?.length) {
      toast.warning(`${r.errors.length} erro(s) — verifique os logs`)
    }
    reload()
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao sincronizar')
  } finally {
    syncing.value = false
  }
}

const formatDate = fmt.date
const formatCurrency = fmt.currency
const inboundSourceLabel = fmt.inboundSource
const manifestationLabel = fmt.manifestation
const manifestationClass = fmt.manifestationClass
const statusLabel = fmt.statusLabel
const statusClass = fmt.statusClass

onMounted(async () => {
  if (cmigs.value.length === 0) await cmigStore.fetchCmigs()
  reload()
})
</script>
