<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0">Relatórios CMIG</h1>
          </div>
          <div class="col-sm-6 text-right">
            <small class="text-muted">Gere relatórios em PDF prontos para impressão</small>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Seleção de conta e filtros -->
        <div class="card card-outline card-primary mb-3">
          <div class="card-body py-3">
            <div class="row align-items-center">
              <div class="col-md-6">
                <label class="mb-1 text-muted"><small>Conta MIG (CMIG):</small></label>
                <select v-model="selectedCmigId" class="form-control form-control-sm" :disabled="loading">
                  <option value="">Selecione uma conta CMIG...</option>
                  <option v-for="c in cmigStore.cmigs" :key="c.id" :value="c.id">
                    {{ c.trade_name || c.company_name || `CMIG #${c.id}` }}
                    <template v-if="c.cnpj"> — {{ c.cnpj }}</template>
                    <template v-else-if="c.cpf"> — {{ c.cpf }}</template>
                  </option>
                </select>
              </div>
              <div class="col-md-6">
                <div class="custom-control custom-switch mt-4">
                  <input
                    id="includeZeroStock"
                    v-model="includeZeroStock"
                    type="checkbox"
                    class="custom-control-input"
                  />
                  <label class="custom-control-label" for="includeZeroStock">
                    Incluir produtos sem estoque
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Cards de relatórios -->
        <div class="row">
          <div
            v-for="report in reports"
            :key="report.key"
            class="col-md-6 col-xl-4 mb-4"
          >
            <div class="card shadow-sm h-100">
              <div class="card-body text-center py-4">
                <div :class="['report-icon mb-3', `text-${report.color}`]">
                  <i :class="['fas', report.icon]"></i>
                </div>
                <p class="text-muted mb-4">{{ report.description }}</p>
                <button
                  class="btn btn-block"
                  :class="`btn-${report.color}`"
                  :disabled="!selectedCmigId || downloading === report.key"
                  @click="downloadReport(report)"
                >
                  <i
                    :class="[
                      'fas mr-2',
                      downloading === report.key ? 'fa-spinner fa-spin' : 'fa-file-pdf',
                    ]"
                  ></i>
                  {{ downloading === report.key ? `Gerando ${report.title}...` : `Gerar ${report.title}` }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div v-if="cmigStore.cmigs.length === 0 && !loading" class="alert alert-warning">
          <i class="fas fa-exclamation-triangle mr-2"></i>
          Nenhuma conta CMIG cadastrada. Cadastre uma CMIG antes de gerar relatórios.
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useCmigStore } from '@/stores/cmig'

const cmigStore = useCmigStore()
const toast = useToast()

const selectedCmigId = ref('')
const includeZeroStock = ref(true)
const downloading = ref(null)
const loading = ref(false)

const reports = [
  {
    key: 'price-table',
    title: 'Tabela de Preços',
    description: 'Foto, SKU, EAN, título e preço de venda dos produtos cadastrados.',
    icon: 'fa-tags',
    color: 'primary',
    filename: 'tabela-precos',
  },
  {
    key: 'stock',
    title: 'Relatório de Estoque',
    description: 'Foto, SKU, EAN, título, estoque, custo unitário e custo total acumulado.',
    icon: 'fa-boxes',
    color: 'success',
    filename: 'estoque',
  },
]

async function downloadReport(report) {
  if (!selectedCmigId.value) {
    toast.warning('Selecione uma conta CMIG primeiro')
    return
  }
  downloading.value = report.key
  try {
    const { data } = await api.get(
      `/cmigs/${selectedCmigId.value}/reports/${report.key}`,
      {
        params: { include_zero_stock: includeZeroStock.value },
        responseType: 'blob',
      }
    )
    const blob = new Blob([data], { type: 'application/pdf' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${report.filename}-cmig-${selectedCmigId.value}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success('Relatório gerado com sucesso')
  } catch (err) {
    const detail = err?.response?.data?.detail || err?.message || 'Erro ao gerar relatório'
    toast.error(detail)
  } finally {
    downloading.value = null
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await cmigStore.fetchCmigs()
    if (cmigStore.cmigs.length === 1) {
      selectedCmigId.value = cmigStore.cmigs[0].id
    } else if (cmigStore.activeCmig?.id) {
      selectedCmigId.value = cmigStore.activeCmig.id
    }
  } catch (err) {
    toast.error('Erro ao carregar contas CMIG')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.report-icon {
  font-size: 4rem;
  line-height: 1;
}
.card {
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
}
</style>
