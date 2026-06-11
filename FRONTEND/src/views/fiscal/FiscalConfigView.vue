<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-6">
            <h1 class="m-0"><i class="fas fa-cogs text-secondary mr-2"></i>Configuração Fiscal</h1>
            <small class="text-muted">Certificado Digital, Focus NFe e parâmetros de emissão por CMIG</small>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Seletor de CMIG -->
        <div class="card" v-if="cmigs.length > 1">
          <div class="card-body py-2">
            <div class="row align-items-center">
              <div class="col-auto">
                <label class="small mb-0 font-weight-bold">CMIG</label>
              </div>
              <div class="col-md-4">
                <select v-model="selectedCmigId" class="form-control form-control-sm" @change="onCmigChange">
                  <option :value="null" disabled>Selecione a conta...</option>
                  <option v-for="c in cmigs" :key="c.id" :value="c.id">
                    {{ c.company_name }} ({{ c.cnpj_formatted || c.cnpj }})
                  </option>
                </select>
              </div>
              <div class="col-auto" v-if="selectedCmig">
                <span class="badge badge-secondary">{{ selectedCmig.company_name }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Placeholder enquanto nenhuma CMIG selecionada -->
        <div v-if="!selectedCmigId" class="card">
          <div class="card-body text-center py-5 text-muted">
            <i class="fas fa-arrow-up fa-2x mb-3 d-block"></i>
            Selecione uma CMIG acima para configurar o certificado digital e o Focus NFe.
          </div>
        </div>

        <!-- Config Fiscal (reutiliza CmigFiscalConfigCard) -->
        <CmigFiscalConfigCard
          v-else
          :key="selectedCmigId"
          :cmig-id="selectedCmigId"
        />

        <!-- Guia rápido -->
        <div class="card mt-3" v-if="selectedCmigId">
          <div class="card-header py-2">
            <h6 class="card-title mb-0"><i class="fas fa-info-circle text-info mr-1"></i>Ordem de configuração</h6>
          </div>
          <div class="card-body py-2">
            <ol class="mb-0 small text-muted pl-3">
              <li>Preencha os dados fiscais (CRT, IE, CNAE) e salve.</li>
              <li>Clique em <strong>Registrar no Focus NFe</strong> informando o token mestre.</li>
              <li>Após registrar, clique em <strong>Enviar Certificado</strong> e faça upload do arquivo <code>.pfx</code>.</li>
              <li>Configure o ambiente como <strong>Produção</strong> apenas quando os testes em Homologação estiverem concluídos.</li>
            </ol>
          </div>
        </div>

      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useCmigStore } from '@/stores/cmig'
import { useAuthStore } from '@/stores/auth'
import CmigFiscalConfigCard from '@/components/cmigs/CmigFiscalConfigCard.vue'

const cmigStore = useCmigStore()
const authStore = useAuthStore()
const { cmigs } = storeToRefs(cmigStore)

const selectedCmigId = ref(null)

const selectedCmig = computed(() =>
  cmigs.value.find(c => c.id === selectedCmigId.value) || null
)

function onCmigChange() {}

onMounted(async () => {
  if (!cmigs.value.length) await cmigStore.fetchCmigs?.()
  if (cmigs.value.length === 1) {
    selectedCmigId.value = cmigs.value[0].id
  }
})
</script>
