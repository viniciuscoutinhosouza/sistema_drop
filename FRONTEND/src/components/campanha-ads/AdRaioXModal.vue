<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useToast } from '@/composables/useToast'
import { formatCurrency } from '@/utils/formatters'
import { useCampaignAds, derive, num } from '@/composables/useCampaignAds'

const props = defineProps({
  params: { type: Object, required: true }, // account_id, advertiser_id, site_id, date_from, date_to
  ad: { type: Object, required: true }, // linha já carregada (fallback imediato)
})
defineEmits(['close'])

const toast = useToast()
const { loadAdDetail } = useCampaignAds()

const loading = ref(true)
const detail = reactive({ ad: {}, daily: [] })

const merged = computed(() => ({ ...props.ad, ...detail.ad }))
const m = computed(() => merged.value.metrics || props.ad.metrics || {})
const d = computed(() => derive(m.value))

const money = (v) => formatCurrency(num(v))
const intf = (v) => num(v).toLocaleString('pt-BR')
const pct = (v) => `${num(v).toFixed(2)}%`
const roasf = (v) => `${num(v).toFixed(2)}x`

function statusBadge(s) {
  const v = (s || '').toLowerCase()
  if (v === 'active') return { cls: 'badge-success', txt: 'Ativo' }
  if (v === 'paused') return { cls: 'badge-warning', txt: 'Pausado' }
  if (v === 'hold') return { cls: 'badge-danger', txt: 'Suspenso' }
  if (v === 'idle') return { cls: 'badge-secondary', txt: 'Ocioso' }
  return { cls: 'badge-secondary', txt: s || '—' }
}

// Funil (largura relativa às impressões)
const funnel = computed(() => {
  const prints = d.value.prints || 0
  const clicks = d.value.clicks || 0
  const units = d.value.units || 0
  const base = prints || 1
  return [
    { label: 'Impressões', value: prints, w: 100, cls: 'bg-info' },
    { label: 'Cliques', value: clicks, w: Math.min(100, (clicks / base) * 100), cls: 'bg-primary' },
    { label: 'Conversões', value: units, w: Math.min(100, (units / base) * 100), cls: 'bg-success' },
  ]
})

// Série diária — normalização defensiva (o ML não documenta o nome do campo de data)
const dailyRows = computed(() =>
  (detail.daily || [])
    .map((r) => {
      const date = r.date || r.day || r.aggregation_date || r.metric_date || null
      const dm = r.metrics || r
      return date ? { date, cost: num(dm.cost), revenue: num(dm.total_amount) } : null
    })
    .filter(Boolean)
    .sort((a, b) => String(a.date).localeCompare(String(b.date))),
)
const hasChart = computed(() => dailyRows.value.length > 0)

const chartSeries = computed(() => [
  { name: 'Custo', data: dailyRows.value.map((r) => Number(r.cost.toFixed(2))) },
  { name: 'Receita', data: dailyRows.value.map((r) => Number(r.revenue.toFixed(2))) },
])
const chartOptions = computed(() => ({
  chart: { type: 'line', toolbar: { show: false }, animations: { enabled: false } },
  stroke: { curve: 'smooth', width: 2 },
  colors: ['#dc3545', '#28a745'],
  xaxis: { categories: dailyRows.value.map((r) => String(r.date).slice(5)), labels: { rotate: -45, style: { fontSize: '10px' } } },
  yaxis: { labels: { formatter: (v) => formatCurrency(v) } },
  legend: { position: 'top' },
  tooltip: { y: { formatter: (v) => formatCurrency(v) } },
}))

onMounted(async () => {
  try {
    const data = await loadAdDetail({ ...props.params, item_id: props.ad.item_id })
    detail.ad = data.ad || {}
    detail.daily = data.daily || []
  } catch (e) {
    toast.error('Falha ao carregar o Raio-X do anúncio.')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="cad-overlay" @click.self="$emit('close')">
    <div class="cad-modal card">
      <div class="card-header py-2 d-flex align-items-center">
        <strong><i class="fas fa-x-ray mr-2"></i>Raio-X do anúncio</strong>
        <button class="btn btn-sm btn-light ml-auto" @click="$emit('close')"><i class="fas fa-times"></i></button>
      </div>
      <div class="card-body">
        <!-- Cabeçalho do anúncio -->
        <div class="d-flex mb-3">
          <img v-if="merged.thumbnail" :src="merged.thumbnail" alt="" style="width:64px;height:64px;object-fit:contain;border:1px solid #eee;border-radius:4px" class="mr-2" />
          <div>
            <a v-if="merged.permalink" :href="merged.permalink" target="_blank" rel="noopener"><strong>{{ merged.title }}</strong></a>
            <strong v-else>{{ merged.title }}</strong>
            <div class="text-muted small">
              {{ merged.item_id }} ·
              <span class="badge" :class="statusBadge(merged.status).cls">{{ statusBadge(merged.status).txt }}</span>
              <span v-if="merged.campaign_id"> · Campanha {{ merged.campaign_id }}</span>
            </div>
          </div>
          <i v-if="loading" class="fas fa-spinner fa-spin ml-auto text-muted"></i>
        </div>

        <!-- Cards -->
        <div class="row text-center">
          <div class="col-3 mb-2"><div class="text-muted small">IMPRESSÕES</div><strong>{{ intf(d.prints) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">CLIQUES</div><strong>{{ intf(d.clicks) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">CTR</div><strong>{{ pct(d.ctr) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">CVR</div><strong>{{ pct(d.cvr) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">CUSTO</div><strong>{{ money(d.cost) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">CPC</div><strong>{{ money(d.cpc) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">CPA</div><strong>{{ money(d.cpa) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">VENDIDOS</div><strong>{{ intf(d.units) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">RECEITA</div><strong>{{ money(d.revenue) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">ROAS</div><strong>{{ roasf(d.roas) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">ACOS</div><strong>{{ pct(d.acos) }}</strong></div>
          <div class="col-3 mb-2"><div class="text-muted small">LUCRO</div><strong>{{ money(d.profit) }}</strong></div>
        </div>

        <hr class="my-2" />
        <!-- Funil -->
        <strong class="small">Funil de Conversão</strong>
        <div v-for="f in funnel" :key="f.label" class="d-flex align-items-center mb-1 mt-1">
          <span class="small mr-2" style="width:90px">{{ f.label }}</span>
          <div class="progress flex-grow-1" style="height:14px">
            <div class="progress-bar" :class="f.cls" :style="{ width: f.w + '%' }"></div>
          </div>
          <span class="small ml-2" style="width:80px;text-align:right">{{ intf(f.value) }}</span>
        </div>

        <!-- Gráfico diário -->
        <div v-if="hasChart" class="mt-3">
          <strong class="small">Custo × Receita por dia</strong>
          <apexchart type="line" height="240" :options="chartOptions" :series="chartSeries" />
        </div>
        <p v-else-if="!loading" class="text-muted small mt-3 mb-0">
          Sem série diária disponível para este anúncio no período.
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
.cad-modal { width: 720px; max-width: 95vw; margin: 0; max-height: 92vh; overflow-y: auto; }
</style>
