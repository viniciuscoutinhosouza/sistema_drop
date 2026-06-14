<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import { formatCurrency } from '@/utils/formatters'
import { useCampaignAds, derive, num } from '@/composables/useCampaignAds'

const props = defineProps({
  params: { type: Object, required: true }, // account_id, advertiser_id, site_id, date_from, date_to
  campaign: { type: Object, required: true }, // linha já carregada (fallback imediato)
})
defineEmits(['close'])

const toast = useToast()
const { loadCampaignDetail } = useCampaignAds()

const loading = ref(true)
const detail = reactive({ data: {} })

const STRATEGY_PT = {
  PROFITABILITY: 'Rentabilidade',
  INCREASE: 'Aumentar vendas',
  VISIBILITY: 'Visibilidade',
}

const merged = computed(() => ({ ...props.campaign, ...detail.data }))
const m = computed(() => merged.value.metrics || props.campaign.metrics || {})
const d = computed(() => derive(m.value, merged.value))

const money = (v) => formatCurrency(num(v))
const intf = (v) => num(v).toLocaleString('pt-BR')
const pct = (v) => `${num(v).toFixed(2)}%`
const roasf = (v) => `${num(v).toFixed(2)}x`

/** Share/benchmark: null/undefined ⇒ "—" (0% é diferente de "sem dado"). */
function sharePct(v) {
  return v === null || v === undefined ? '—' : `${num(v).toFixed(2)}%`
}
function shareWidth(v) {
  return v === null || v === undefined ? 0 : Math.min(100, Math.max(0, num(v)))
}

const shares = computed(() => {
  const x = m.value
  return [
    { label: 'Share de Impressões', key: 'impression_share', cls: 'bg-info' },
    { label: 'Share Top', key: 'top_impression_share', cls: 'bg-primary' },
    { label: 'Perdas por Orçamento', key: 'lost_impression_share_by_budget', cls: 'bg-warning' },
    { label: 'Perdas por Ranking', key: 'lost_impression_share_by_ad_rank', cls: 'bg-danger' },
  ].map((s) => ({ ...s, value: x[s.key] }))
})

function statusBadge(s) {
  const v = (s || '').toLowerCase()
  if (v === 'active') return { cls: 'badge-success', txt: 'Ativa' }
  if (v === 'paused') return { cls: 'badge-warning', txt: 'Pausada' }
  return { cls: 'badge-secondary', txt: s || '—' }
}

onMounted(async () => {
  try {
    detail.data = await loadCampaignDetail({ ...props.params, campaign_id: props.campaign.id })
  } catch (e) {
    toast.error('Falha ao carregar detalhe da campanha.')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="cad-overlay" @click.self="$emit('close')">
    <div class="cad-modal card">
      <div class="card-header py-2 d-flex align-items-center">
        <strong><i class="fas fa-chart-line mr-2"></i>Detalhe da campanha</strong>
        <button class="btn btn-sm btn-light ml-auto" @click="$emit('close')"><i class="fas fa-times"></i></button>
      </div>
      <div class="card-body">
        <h5 class="mb-1">{{ merged.name }}
          <span class="badge ml-1" :class="statusBadge(merged.status).cls">{{ statusBadge(merged.status).txt }}</span>
        </h5>
        <div class="text-muted small mb-3">
          ID {{ merged.id }} ·
          Estratégia: <strong>{{ STRATEGY_PT[merged.strategy] || merged.strategy || '—' }}</strong> ·
          Orçamento: {{ merged.budget ? money(merged.budget) : '—' }}
          <span v-if="merged.automatic_budget"> (automático)</span>
        </div>

        <!-- Cards de métrica -->
        <div class="row">
          <div class="col-4 col-md-2 mb-2"><div class="text-muted small">RECEITA</div><strong>{{ money(d.revenue) }}</strong></div>
          <div class="col-4 col-md-2 mb-2"><div class="text-muted small">CUSTO</div><strong>{{ money(d.cost) }}</strong></div>
          <div class="col-4 col-md-2 mb-2"><div class="text-muted small">LUCRO</div><strong>{{ money(d.profit) }}</strong></div>
          <div class="col-4 col-md-2 mb-2"><div class="text-muted small">ROAS</div><strong :class="d.roasOk === false ? 'text-danger' : 'text-success'">{{ roasf(d.roas) }}</strong></div>
          <div class="col-4 col-md-2 mb-2"><div class="text-muted small">ACOS</div><strong :class="d.acosOk === false ? 'text-danger' : 'text-success'">{{ pct(d.acos) }}</strong></div>
          <div class="col-4 col-md-2 mb-2"><div class="text-muted small">UN. VENDIDAS</div><strong>{{ intf(d.units) }}</strong></div>
        </div>

        <hr class="my-2" />
        <div class="d-flex align-items-center mb-2">
          <strong>Share de Impressões &amp; Concorrência</strong>
          <i v-if="loading" class="fas fa-spinner fa-spin ml-2 text-muted"></i>
        </div>
        <div v-for="s in shares" :key="s.key" class="d-flex align-items-center mb-2">
          <span class="small mr-2" style="width:160px">{{ s.label }}</span>
          <div class="progress flex-grow-1" style="height:12px">
            <div class="progress-bar" :class="s.cls" :style="{ width: shareWidth(s.value) + '%' }"></div>
          </div>
          <span class="small ml-2" style="width:70px;text-align:right">{{ sharePct(s.value) }}</span>
        </div>
        <div class="small text-muted mt-2">
          ACOS Benchmark (alta performance): <strong>{{ sharePct(m.acos_benchmark) }}</strong>
          <span v-if="merged.acos_target"> · Meta ACOS: {{ pct(merged.acos_target) }}</span>
          <span v-if="merged.roas_target"> · Meta ROAS: {{ roasf(merged.roas_target) }}</span>
        </div>
        <p v-if="!loading && shares.every(s => s.value === null || s.value === undefined) && (m.acos_benchmark === null || m.acos_benchmark === undefined)"
          class="text-muted small mt-2 mb-0">
          Sem dados de share/benchmark para o período (a campanha pode não ter histórico suficiente).
        </p>
      </div>
      <div class="card-footer text-right">
        <button class="btn btn-sm btn-outline-secondary" @click="$emit('close')">Fechar</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cad-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1085;
}
.cad-modal { width: 680px; max-width: 95vw; margin: 0; }
</style>
