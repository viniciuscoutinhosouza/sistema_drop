<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-8">
            <h1 class="m-0"><i class="fas fa-box text-primary mr-2"></i>Produtos (eShip)</h1>
            <small class="text-muted">Integração com o WMS eShip — listar/enviar produtos e consultar saldo de estoque por empresa.</small>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">
        <div v-if="loading" class="text-center py-5">
          <i class="fas fa-spinner fa-spin fa-2x text-muted"></i>
        </div>

        <div v-else-if="cmigs.length === 0" class="card">
          <div class="card-body text-center py-5 text-muted">
            <i class="fas fa-warehouse fa-2x mb-3 d-block"></i>
            Nenhuma Conta MIG cadastrada.
          </div>
        </div>

        <div v-else class="row">
          <div class="col-md-6 col-lg-4" v-for="c in cmigs" :key="c.cmig_id">
            <div class="card" :class="c.eship_active && c.eship_configured ? 'card-outline card-success' : 'card-outline card-secondary'">
              <div class="card-header py-2">
                <h3 class="card-title text-truncate">{{ c.company_name || ('CMIG #' + c.cmig_id) }}</h3>
                <span class="badge float-right" :class="statusBadge(c)">{{ statusLabel(c) }}</span>
              </div>
              <div class="card-body p-2">
                <p class="mb-1 small"><i class="fas fa-id-card mr-1 text-muted"></i>{{ c.cnpj || c.cpf || '—' }}</p>
                <p class="mb-1 small" v-if="c.eship_configured">
                  <i class="fas fa-link mr-1 text-muted"></i>{{ c.eship_base_url }}
                </p>
                <p class="mb-2 small" v-if="c.eship_warehouse_code">
                  <i class="fas fa-boxes mr-1 text-muted"></i>Armazém: <code>{{ c.eship_warehouse_code }}</code>
                </p>

                <div v-if="c.eship_active && c.eship_configured">
                  <!-- Cadastro em lote do catálogo no WMS -->
                  <button class="btn btn-sm btn-primary btn-block mb-2" :disabled="pushLoading[c.cmig_id]"
                          @click="enviarProdutos(c)">
                    <i class="fas mr-1" :class="pushLoading[c.cmig_id] ? 'fa-spinner fa-spin' : 'fa-cloud-upload-alt'"></i>
                    {{ pushLoading[c.cmig_id] ? 'Enviando produtos…' : 'Enviar produtos ao WMS' }}
                  </button>
                  <div v-if="pushResult[c.cmig_id]" class="small mb-2">
                    <div :class="pushResult[c.cmig_id].failed ? 'text-warning' : 'text-success'">
                      <i class="fas fa-check-circle mr-1"></i>
                      {{ pushResult[c.cmig_id].sent }}/{{ pushResult[c.cmig_id].total }} enviado(s)<span
                        v-if="pushResult[c.cmig_id].failed">, {{ pushResult[c.cmig_id].failed }} com erro</span>.
                    </div>
                    <details v-if="pushResult[c.cmig_id].sent_skus?.length" class="mt-1">
                      <summary class="text-success" style="cursor:pointer">Ver SKUs enviados ({{ pushResult[c.cmig_id].sent }})</summary>
                      <pre class="bg-light p-2 small mb-0 mt-1" style="max-height:140px;overflow:auto">{{ pushResult[c.cmig_id].sent_skus.join('\n') }}</pre>
                    </details>
                    <div v-if="pushResult[c.cmig_id].errors?.length" class="mt-1">
                      <span class="text-danger">SKUs com erro:</span>
                      <pre class="bg-light p-2 small mb-0 mt-1" style="max-height:140px;overflow:auto">{{ pushErrorsText(c.cmig_id) }}</pre>
                    </div>
                  </div>

                  <div class="input-group input-group-sm mb-2">
                    <input v-model="skuQuery[c.cmig_id]" class="form-control" placeholder="SKU (opcional)"
                           @keyup.enter="consultarSaldo(c)">
                    <div class="input-group-append">
                      <button class="btn btn-outline-primary" :disabled="saldoLoading[c.cmig_id]" @click="consultarSaldo(c)">
                        <i class="fas" :class="saldoLoading[c.cmig_id] ? 'fa-spinner fa-spin' : 'fa-search'"></i>
                        Saldo
                      </button>
                    </div>
                  </div>
                  <pre v-if="saldo[c.cmig_id]" class="bg-light p-2 small mb-0" style="max-height:180px;overflow:auto">{{ saldo[c.cmig_id] }}</pre>

                  <!-- Listar produtos cadastrados no eShip (com estoque) -->
                  <button class="btn btn-sm btn-outline-info btn-block mt-2" @click="abrirProdutos(c)">
                    <i class="fas fa-list mr-1"></i>Listar produtos no eShip
                  </button>
                </div>
                <div v-else class="text-center py-2">
                  <RouterLink :to="`/cmigs/${c.cmig_id}`" class="btn btn-sm btn-outline-primary">
                    <i class="fas fa-cog mr-1"></i>Configurar eShip nesta empresa
                  </RouterLink>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card card-outline card-info">
          <div class="card-header py-2"><h6 class="card-title mb-0"><i class="fas fa-info-circle mr-1"></i>Como funciona</h6></div>
          <div class="card-body py-2 small text-muted">
            <ul class="mb-0 pl-3">
              <li>A apikey do eShip é cadastrada em cada <strong>Conta MIG</strong> (Contas MIG → abrir a empresa → card "Integração eShip").</li>
              <li><strong>Listar produtos no eShip</strong> (botão acima) traz os produtos <strong>desta empresa</strong> no WMS com estoque (Full, físico, disponível, reservado). Dá para <strong>ordenar</strong> por coluna e buscar.</li>
              <li><strong>Enviar produtos ao WMS</strong> (botão acima) pré-cadastra todo o catálogo da empresa no eShip (por SKU; idempotente). Útil antes do primeiro pedido.</li>
              <li>O envio do <strong>pedido</strong> ao eShip é feito na tela de <strong>Pedidos</strong> (ação eShip por pedido) ou automaticamente no fluxo de separação — os produtos do pedido também são cadastrados automaticamente.</li>
              <li>O eShip é a <strong>fonte de verdade do estoque físico</strong> — consulte o saldo por SKU acima.</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <!-- Modal: produtos no eShip (info + estoque) -->
    <div v-if="prod.show">
      <div class="modal fade show d-block" tabindex="-1" @click.self="prod.show = false">
        <div class="modal-dialog modal-xl modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header py-2">
              <h5 class="modal-title"><i class="fas fa-box mr-1"></i>Produtos no eShip — {{ prod.nome }}</h5>
              <button class="btn btn-sm btn-outline-secondary ml-auto mr-2" :disabled="prod.loading"
                      title="Recarregar do eShip" @click="carregarProdutos(true)">
                <i class="fas fa-sync-alt" :class="{ 'fa-spin': prod.loading }"></i>
              </button>
              <button type="button" class="close" @click="prod.show = false"><span>&times;</span></button>
            </div>
            <div class="modal-body p-2">
              <div class="d-flex align-items-center flex-wrap mb-2" style="gap:8px">
                <input v-model="prod.filter" @input="resetPage" class="form-control form-control-sm" style="max-width:260px"
                       placeholder="Buscar (código, descrição, EAN)">
                <span class="text-muted small ml-auto">
                  {{ produtosFiltrados.length }} de {{ prod.rows.length }} produto(s) desta empresa<span
                    v-if="prod.totalCatalogo != null"> · catálogo WMS: {{ prod.totalCatalogo }}</span>
                </span>
              </div>
              <div v-if="prod.escopoIndefinido" class="small text-warning mb-2">
                <i class="fas fa-exclamation-triangle mr-1"></i>Cadastre o CNPJ/CPF desta empresa (Contas MIG → abrir a empresa) para listar os produtos dela no WMS.
              </div>
              <div v-if="prod.parcial" class="small text-danger mb-2">
                <i class="fas fa-exclamation-triangle mr-1"></i>Catálogo parcial — {{ prod.paginasFalhas }} página(s) não puderam ser lidas; alguns produtos podem não aparecer. Tente recarregar.
              </div>
              <div v-if="prod.truncado" class="small text-warning mb-2">
                <i class="fas fa-exclamation-triangle mr-1"></i>Catálogo muito grande — exibindo os primeiros itens.
              </div>
              <div v-if="prod.loading" class="text-center py-5">
                <i class="fas fa-spinner fa-spin fa-2x text-muted d-block mb-2"></i>
                <span class="text-muted small">Carregando catálogo do eShip… (pode levar alguns segundos)</span>
              </div>
              <table v-else class="table table-sm table-hover small mb-0">
                <thead class="thead-light">
                  <tr>
                    <th style="cursor:pointer;white-space:nowrap" @click="sortBy('codigo')">Código <i :class="sortIcon('codigo')"></i></th>
                    <th style="cursor:pointer;white-space:nowrap" @click="sortBy('codigo_barras')">Cód. barras <i :class="sortIcon('codigo_barras')"></i></th>
                    <th style="cursor:pointer" @click="sortBy('descricao')">Descrição <i :class="sortIcon('descricao')"></i></th>
                    <th style="cursor:pointer" @click="sortBy('status')">Status <i :class="sortIcon('status')"></i></th>
                    <th class="text-center">Full</th><th class="text-right">Físico</th><th class="text-right">Disp.</th><th class="text-right">Reserv.</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, i) in produtosPagina" :key="p.codigo || i">
                    <td class="text-nowrap font-weight-bold">{{ p.codigo }}</td>
                    <td class="text-nowrap">{{ p.codigo_barras || '—' }}</td>
                    <td>{{ p.descricao }}</td>
                    <td>{{ p.status || '—' }}</td>
                    <td class="text-center"><span v-if="p.is_full" class="badge badge-info">Full</span></td>
                    <td class="text-right">{{ p.total_fisico ?? '—' }}</td>
                    <td class="text-right">{{ p.total_disponivel ?? '—' }}</td>
                    <td class="text-right">{{ p.total_reservado ?? '—' }}</td>
                  </tr>
                  <tr v-if="!produtosPagina.length">
                    <td colspan="8" class="text-center text-muted py-3">Nenhum produto desta empresa no WMS.</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="modal-footer py-2 justify-content-start">
              <button class="btn btn-sm btn-outline-secondary" :disabled="prod.page <= 1 || prod.loading" @click="prod.page--">
                <i class="fas fa-chevron-left"></i> Anterior
              </button>
              <span class="mx-2 small text-muted">Página {{ prod.page }} de {{ totalPaginas }}</span>
              <button class="btn btn-sm btn-outline-secondary" :disabled="prod.page >= totalPaginas || prod.loading" @click="prod.page++">
                Próxima <i class="fas fa-chevron-right"></i>
              </button>
              <div class="btn-group btn-group-sm ml-auto">
                <button class="btn btn-outline-danger" title="Exportar em PDF"
                        :disabled="prod.loading || !!exporting || !prod.rows.length" @click="exportar('pdf')">
                  <i class="fas" :class="exporting === 'pdf' ? 'fa-spinner fa-spin' : 'fa-file-pdf'"></i> PDF
                </button>
                <button class="btn btn-outline-success" title="Exportar em Excel"
                        :disabled="prod.loading || !!exporting || !prod.rows.length" @click="exportar('xlsx')">
                  <i class="fas" :class="exporting === 'xlsx' ? 'fa-spinner fa-spin' : 'fa-file-excel'"></i> Excel
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-backdrop fade show"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const toast = useToast()
const loading = ref(true)
const cmigs = ref([])
const skuQuery = reactive({})
const saldo = reactive({})
const saldoLoading = reactive({})
const pushLoading = reactive({})
const pushResult = reactive({})
const exporting = ref('')  // '', 'pdf' ou 'xlsx' — formato em exportação

// Modal de listagem de produtos do eShip — produtos DA EMPRESA (CMIG) carregados de uma vez;
// busca, ordenação e paginação são feitos na tela. O WMS é multi-tenant e o backend já
// escopa por empresa (a API não filtra por cadastro) — aqui não há mais filtro por empresa.
const prod = reactive({
  show: false, cmigId: null, nome: '', loading: false,
  rows: [], total: null, totalCatalogo: null, paginas: null, truncado: false,
  parcial: false, paginasFalhas: 0, escopoIndefinido: false,
  filter: '',
  sortKey: 'descricao', sortDir: 'asc',
  page: 1, pageSize: 50,
})

const produtosFiltrados = computed(() => {
  const f = (prod.filter || '').trim().toLowerCase()
  const arr = prod.rows.filter(p => {
    if (f && ![p.codigo, p.codigo_barras, p.descricao]
      .some(v => (v ?? '').toString().toLowerCase().includes(f))) return false
    return true
  })
  const k = prod.sortKey
  const dir = prod.sortDir === 'desc' ? -1 : 1
  return arr.sort((a, b) => {
    const va = (a[k] ?? '').toString().toLowerCase()
    const vb = (b[k] ?? '').toString().toLowerCase()
    return va < vb ? -dir : va > vb ? dir : 0
  })
})

const totalPaginas = computed(() => Math.max(1, Math.ceil(produtosFiltrados.value.length / prod.pageSize)))
const produtosPagina = computed(() => {
  const start = (prod.page - 1) * prod.pageSize
  return produtosFiltrados.value.slice(start, start + prod.pageSize)
})

function sortBy(key) {
  if (prod.sortKey === key) prod.sortDir = prod.sortDir === 'asc' ? 'desc' : 'asc'
  else { prod.sortKey = key; prod.sortDir = 'asc' }
  prod.page = 1
}
function sortIcon(key) {
  if (prod.sortKey !== key) return 'fas fa-sort text-muted'
  return prod.sortDir === 'asc' ? 'fas fa-sort-up' : 'fas fa-sort-down'
}
function resetPage() { prod.page = 1 }

function statusLabel(c) {
  if (!c.eship_configured) return 'Não configurado'
  return c.eship_active ? 'Ativo' : 'Inativo'
}
function statusBadge(c) {
  if (!c.eship_configured) return 'badge-secondary'
  return c.eship_active ? 'badge-success' : 'badge-warning'
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/integrations/eship/cmigs')
    cmigs.value = Array.isArray(data) ? data : []
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao carregar integrações')
  } finally {
    loading.value = false
  }
}

function pushErrorsText(cmigId) {
  const errs = pushResult[cmigId]?.errors || []
  return errs.map(e => `${e.sku}: ${e.error}`).join('\n')
}

async function enviarProdutos(c) {
  const nome = c.company_name || ('CMIG #' + c.cmig_id)
  if (!window.confirm(`Enviar/cadastrar TODOS os produtos de "${nome}" no WMS eShip?`)) return
  pushLoading[c.cmig_id] = true
  try {
    const { data } = await api.post(`/integrations/eship/cmigs/${c.cmig_id}/push-products`)
    pushResult[c.cmig_id] = data
    if (data.total === 0) {
      toast.info('Nenhum produto com SKU para enviar.')
    } else if (data.failed) {
      toast.warning(`${data.sent}/${data.total} produtos enviados — ${data.failed} com erro.`)
    } else {
      toast.success(`${data.sent} produto(s) enviado(s) ao WMS.`)
    }
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao enviar produtos ao WMS')
  } finally {
    pushLoading[c.cmig_id] = false
  }
}

async function abrirProdutos(c) {
  prod.cmigId = c.cmig_id
  prod.nome = c.company_name || ('CMIG #' + c.cmig_id)
  prod.filter = ''; prod.sortKey = 'descricao'; prod.sortDir = 'asc'
  prod.rows = []; prod.total = null; prod.totalCatalogo = null; prod.paginas = null
  prod.truncado = false; prod.parcial = false; prod.paginasFalhas = 0
  prod.escopoIndefinido = false; prod.page = 1
  prod.show = true
  await carregarProdutos()
}

async function carregarProdutos(refresh = false) {
  if (!prod.cmigId) return
  prod.loading = true
  try {
    const params = { all: true }
    if (refresh) params.refresh = true
    const { data } = await api.get(`/integrations/eship/cmigs/${prod.cmigId}/produtos`, { params })
    prod.rows = data.produtos || []
    prod.total = data.total ?? null
    prod.totalCatalogo = data.total_catalogo ?? null
    prod.paginas = data.paginas ?? null
    prod.truncado = !!data.truncado
    prod.parcial = !!data.parcial
    prod.paginasFalhas = data.paginas_falhas ?? 0
    prod.escopoIndefinido = !!data.escopo_indefinido
    prod.page = 1
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao listar produtos do eShip')
  } finally {
    prod.loading = false
  }
}

async function exportar(format) {
  if (!prod.cmigId || exporting.value) return
  exporting.value = format
  try {
    const { data } = await api.get(`/integrations/eship/cmigs/${prod.cmigId}/produtos/export`, {
      params: { format },
      responseType: 'blob',
    })
    const ext = format === 'xlsx' ? 'xlsx' : 'pdf'
    const url = URL.createObjectURL(new Blob([data]))
    const link = document.createElement('a')
    link.href = url
    link.download = `produtos-eship-cmig-${prod.cmigId}.${ext}`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (e) {
    // com responseType:blob, o erro do backend vem como Blob → tenta extrair o detail
    let msg = 'Erro ao exportar'
    try {
      const txt = await e.response?.data?.text?.()
      if (txt) msg = JSON.parse(txt).detail || msg
    } catch { /* mantém msg padrão */ }
    toast.error(msg)
  } finally {
    exporting.value = ''
  }
}

async function consultarSaldo(c) {
  saldoLoading[c.cmig_id] = true
  try {
    const params = {}
    if (skuQuery[c.cmig_id]) params.sku = skuQuery[c.cmig_id]
    const { data } = await api.get(`/integrations/eship/cmigs/${c.cmig_id}/saldo`, { params })
    saldo[c.cmig_id] = JSON.stringify(data, null, 2)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao consultar saldo')
  } finally {
    saldoLoading[c.cmig_id] = false
  }
}

onMounted(load)
</script>
