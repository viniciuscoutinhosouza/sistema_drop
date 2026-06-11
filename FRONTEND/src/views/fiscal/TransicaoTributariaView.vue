<template>
  <div>
    <div class="content-header">
      <div class="container-fluid">
        <div class="row mb-2">
          <div class="col-sm-7">
            <h1 class="m-0"><i class="fas fa-balance-scale text-info mr-2"></i>Transição Tributária</h1>
            <small class="text-muted">Reforma Tributária EC 132/2023 — cronograma e impacto por CMIG</small>
          </div>
          <div class="col-sm-5 text-right">
            <span class="badge badge-info px-3 py-2">
              <i class="fas fa-calendar mr-1"></i>Ano {{ currentYear }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <section class="content">
      <div class="container-fluid">

        <!-- Cards de régime por CMIG -->
        <div class="row" v-if="cmigs.length">
          <div class="col-md-4" v-for="cmig in cmigs" :key="cmig.id">
            <div class="card" :class="regimeCardClass(cmig)">
              <div class="card-header py-2">
                <h6 class="card-title mb-0">
                  <i class="fas fa-building mr-1"></i>{{ cmig.company_name }}
                </h6>
              </div>
              <div class="card-body py-2">
                <div class="d-flex justify-content-between align-items-center mb-2">
                  <small class="text-muted">Regime fiscal</small>
                  <span class="badge" :class="regimeBadgeClass(cmig.tax_regime_mode)">
                    {{ regimeLabel(cmig.tax_regime_mode) }}
                  </span>
                </div>
                <div class="d-flex justify-content-between align-items-center mb-2">
                  <small class="text-muted">CRT</small>
                  <span class="text-sm">{{ crtLabel(cmig.crt) }}</span>
                </div>
                <div class="d-flex justify-content-between align-items-center">
                  <small class="text-muted">Certificado</small>
                  <span class="badge" :class="cmig.certificate_loaded ? 'badge-success' : 'badge-danger'">
                    {{ cmig.certificate_loaded ? 'Válido' : 'Ausente' }}
                  </span>
                </div>
                <div class="mt-2" v-if="canEdit">
                  <select class="form-control form-control-sm"
                          :value="cmig.tax_regime_mode"
                          @change="changeRegime(cmig, $event.target.value)">
                    <option value="legacy">Legado (ICMS/PIS/COFINS)</option>
                    <option value="transition">Transição (2026-2032)</option>
                    <option value="reform">Reforma Plena (2033+)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Timeline da reforma -->
        <div class="card mt-2">
          <div class="card-header">
            <h5 class="card-title"><i class="fas fa-road mr-2"></i>Cronograma EC 132/2023</h5>
          </div>
          <div class="card-body p-0">
            <div class="table-responsive">
              <table class="table table-sm table-hover mb-0">
                <thead class="thead-light">
                  <tr>
                    <th style="width:80px">Ano</th>
                    <th>Marco / Obrigação</th>
                    <th style="width:100px" class="text-center">CBS</th>
                    <th style="width:120px" class="text-center">IBS (UF+Mun)</th>
                    <th style="width:100px" class="text-center">PIS/COFINS</th>
                    <th style="width:100px" class="text-center">ICMS</th>
                    <th style="width:80px" class="text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in timeline" :key="row.year"
                      :class="row.year === currentYear ? 'table-warning' : ''">
                    <td><strong>{{ row.year }}</strong></td>
                    <td>
                      {{ row.milestone }}
                      <small v-if="row.note" class="d-block text-muted">{{ row.note }}</small>
                    </td>
                    <td class="text-center"><code>{{ row.cbs }}</code></td>
                    <td class="text-center"><code>{{ row.ibs }}</code></td>
                    <td class="text-center"><code>{{ row.pis_cofins }}</code></td>
                    <td class="text-center"><code>{{ row.icms }}</code></td>
                    <td class="text-center">
                      <span class="badge" :class="row.status === 'current' ? 'badge-warning' :
                        row.status === 'past' ? 'badge-secondary' : 'badge-light'">
                        {{ row.status === 'current' ? 'Vigente' : row.status === 'past' ? 'Passou' : 'Futuro' }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Alíquotas CBS/IBS do ano corrente -->
        <div class="row mt-3">
          <div class="col-md-4">
            <div class="card card-outline card-info">
              <div class="card-body text-center">
                <div class="text-muted small mb-1">CBS {{ currentYear }}</div>
                <div class="display-4 text-info font-weight-bold">{{ currentRates.cbs }}%</div>
                <small class="text-muted">Substitui PIS + COFINS</small>
              </div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="card card-outline card-primary">
              <div class="card-body text-center">
                <div class="text-muted small mb-1">IBS Estadual {{ currentYear }}</div>
                <div class="display-4 text-primary font-weight-bold">{{ currentRates.ibs_uf }}%</div>
                <small class="text-muted">Substitui ICMS (parcial)</small>
              </div>
            </div>
          </div>
          <div class="col-md-4">
            <div class="card card-outline card-success">
              <div class="card-body text-center">
                <div class="text-muted small mb-1">IBS Municipal {{ currentYear }}</div>
                <div class="display-4 text-success font-weight-bold">{{ currentRates.ibs_mun }}%</div>
                <small class="text-muted">Substitui ISS (parcial)</small>
              </div>
            </div>
          </div>
        </div>

        <!-- Notas legais -->
        <div class="card card-outline card-secondary mt-1">
          <div class="card-body py-2">
            <h6 class="mb-2"><i class="fas fa-gavel mr-1"></i>Base Legal e Referências</h6>
            <ul class="mb-0 small text-muted pl-3">
              <li><strong>EC 132/2023</strong> — Emenda Constitucional que institui IBS, CBS e IS</li>
              <li><strong>PLP 68/2024</strong> — Lei Complementar que regulamenta o IBS e CBS</li>
              <li><strong>Comitê Gestor do IBS</strong> — Órgão responsável pelas alíquotas por UF/município</li>
              <li>Alíquotas de transição são estimativas do PLP 68/2024 e podem ser revisadas pelo Senado.</li>
              <li>Manter <em>Regime = Transição</em> para CMIGs que já iniciaram apuração dual.</li>
              <li>As alíquotas desta tela são atualizadas via <code>tax_calculator.py</code> — revisar anualmente.</li>
            </ul>
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
import { useToast } from '@/composables/useToast'
import api from '@/composables/useApi'

const cmigStore = useCmigStore()
const authStore = useAuthStore()
const toast = useToast()

const canEdit = computed(() => ['ac', 'admin'].includes(authStore.user?.role))
const currentYear = new Date().getFullYear()

// Dados fiscais das CMIGs (fiscal_config enriquecido)
const cmigs = ref([])

// Alíquotas de transição por ano (espelho do tax_calculator.py)
const TRANSITION = {
  2026: { cbs: '0.90', ibs_uf: '0.05', ibs_mun: '0.05' },
  2027: { cbs: '1.80', ibs_uf: '0.10', ibs_mun: '0.05' },
  2028: { cbs: '2.70', ibs_uf: '0.20', ibs_mun: '0.10' },
  2029: { cbs: '3.60', ibs_uf: '0.30', ibs_mun: '0.15' },
  2030: { cbs: '4.50', ibs_uf: '0.40', ibs_mun: '0.20' },
  2031: { cbs: '5.40', ibs_uf: '0.60', ibs_mun: '0.25' },
  2032: { cbs: '7.60', ibs_uf: '0.80', ibs_mun: '0.30' },
  2033: { cbs: '9.25', ibs_uf: '5.00', ibs_mun: '2.00' },
}

const currentRates = computed(() => {
  const y = currentYear
  return TRANSITION[y] || TRANSITION[2033]
})

const timeline = computed(() => [
  { year: 2026, milestone: 'CBS 0,9% + IBS teste — coexistência inicia', note: 'PIS/COFINS mantidos integrais', cbs: '0,90%', ibs: '0,10%', pis_cofins: '9,25%', icms: 'Integral', status: currentYear > 2026 ? 'past' : currentYear === 2026 ? 'current' : 'future' },
  { year: 2027, milestone: 'CBS 1,8% + IBS 0,15% — escalonamento', note: 'PIS/COFINS reduzidos em 1,8%', cbs: '1,80%', ibs: '0,15%', pis_cofins: '7,45%', icms: 'Integral', status: currentYear > 2027 ? 'past' : currentYear === 2027 ? 'current' : 'future' },
  { year: 2028, milestone: 'CBS 2,7% — fase 3', note: '', cbs: '2,70%', ibs: '0,30%', pis_cofins: '6,55%', icms: 'Integral', status: currentYear > 2028 ? 'past' : currentYear === 2028 ? 'current' : 'future' },
  { year: 2029, milestone: 'IBS 0,45% — aumento expressivo', note: 'Primeiras alíquotas IBS divulgadas pelo CG', cbs: '3,60%', ibs: '0,45%', pis_cofins: '5,65%', icms: 'Integral', status: currentYear > 2029 ? 'past' : currentYear === 2029 ? 'current' : 'future' },
  { year: 2030, milestone: 'CBS 4,5%', note: '', cbs: '4,50%', ibs: '0,60%', pis_cofins: '4,75%', icms: 'Integral', status: currentYear > 2030 ? 'past' : currentYear === 2030 ? 'current' : 'future' },
  { year: 2031, milestone: 'CBS 5,4%', note: '', cbs: '5,40%', ibs: '0,85%', pis_cofins: '3,85%', icms: 'Integral', status: currentYear > 2031 ? 'past' : currentYear === 2031 ? 'current' : 'future' },
  { year: 2032, milestone: 'CBS 7,6% — penúltimo estágio', note: 'ICMS começa a ser reduzido', cbs: '7,60%', ibs: '1,10%', pis_cofins: '1,65%', icms: '≈ 90%', status: currentYear > 2032 ? 'past' : currentYear === 2032 ? 'current' : 'future' },
  { year: 2033, milestone: 'REFORMA PLENA — PIS/COFINS e ICMS extintos', note: 'IBS e CBS em alíquota cheia', cbs: '9,25%', ibs: '7,00%', pis_cofins: '0%', icms: '0%', status: currentYear >= 2033 ? 'current' : 'future' },
])

function regimeLabel(mode) {
  return { legacy: 'Legado', transition: 'Transição', reform: 'Reforma' }[mode] || 'Legado'
}
function regimeBadgeClass(mode) {
  return { legacy: 'badge-secondary', transition: 'badge-warning', reform: 'badge-success' }[mode] || 'badge-secondary'
}
function regimeCardClass(cmig) {
  return { legacy: '', transition: 'card-warning', reform: 'card-success' }[cmig.tax_regime_mode] || ''
}
function crtLabel(crt) {
  return { 1: 'Simples Nacional', 2: 'Simples (excesso)', 3: 'Lucro Presumido/Real', 4: 'MEI' }[crt] || '—'
}

async function changeRegime(cmig, mode) {
  try {
    await api.patch(`/cmigs/${cmig.id}/fiscal-config`, { tax_regime_mode: mode })
    cmig.tax_regime_mode = mode
    toast.success(`Regime de ${cmig.company_name} alterado para ${regimeLabel(mode)}`)
  } catch (e) {
    toast.error(e.response?.data?.detail || 'Erro ao alterar regime')
  }
}

async function loadCmigFiscalData() {
  const { cmigs: rawCmigs } = storeToRefs(cmigStore)
  if (!rawCmigs.value.length) await cmigStore.fetchCmigs?.()

  const results = await Promise.allSettled(
    rawCmigs.value.map(c =>
      api.get(`/cmigs/${c.id}/fiscal-config`).then(r => ({ ...c, ...r.data }))
    )
  )
  cmigs.value = results
    .filter(r => r.status === 'fulfilled')
    .map(r => r.value)
}

onMounted(loadCmigFiscalData)
</script>
