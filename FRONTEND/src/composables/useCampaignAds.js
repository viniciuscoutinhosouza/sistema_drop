import api from '@/composables/useApi'

/**
 * Campanhas ADS — chamadas à API de Mercado Ads (via backend /campaign-ads)
 * e cálculos derivados (lucro, margem, CPA, % meta, conversão).
 * Os insights/derivadas são calculados no front (o backend devolve o cru do ML).
 */

export function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** Métricas derivadas a partir do bloco `metrics`/`metrics_summary` + metas. */
export function derive(m, targets = {}) {
  const cost = num(m.cost)
  const revenue = num(m.total_amount)
  const clicks = num(m.clicks)
  const prints = num(m.prints)
  const units = num(m.units_quantity)
  const profit = revenue - cost
  const roas = m.roas != null ? num(m.roas) : cost > 0 ? revenue / cost : 0
  const acos = m.acos != null ? num(m.acos) : revenue > 0 ? (cost / revenue) * 100 : 0
  const ctr = m.ctr != null ? num(m.ctr) : prints > 0 ? (clicks / prints) * 100 : 0
  const cvr = m.cvr != null ? num(m.cvr) : clicks > 0 ? (units / clicks) * 100 : 0
  const cpc = m.cpc != null ? num(m.cpc) : clicks > 0 ? cost / clicks : 0
  const roasTarget = num(targets.roas_target)
  const acosTarget = num(targets.acos_target)
  return {
    cost,
    revenue,
    clicks,
    prints,
    units,
    sov: num(m.sov),
    profit,
    margin: revenue > 0 ? (profit / revenue) * 100 : 0,
    costPct: revenue > 0 ? (cost / revenue) * 100 : 0,
    roas,
    acos,
    ctr,
    cvr,
    cpc,
    cpa: units > 0 ? cost / units : 0,
    revenuePerClick: clicks > 0 ? revenue / clicks : 0,
    printsPerSale: units > 0 ? prints / units : 0,
    organicUnits: num(m.organic_units_quantity),
    organicAmount: num(m.organic_units_amount),
    directAmount: num(m.direct_amount),
    indirectAmount: num(m.indirect_amount),
    roasTarget,
    acosTarget,
    roasPctOfTarget: roasTarget > 0 ? (roas / roasTarget) * 100 : null,
    acosPctOfTarget: acosTarget > 0 ? (acos / acosTarget) * 100 : null,
    roasOk: roasTarget > 0 ? roas >= roasTarget : null,
    acosOk: acosTarget > 0 ? acos <= acosTarget : null,
  }
}

/** Data YYYY-MM-DD a partir de um Date, no fuso do Brasil (não usa toISOString=UTC). */
export function isoDate(d) {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(d)
}

export function useCampaignAds() {
  async function loadAdvertisers(cmigId) {
    const { data } = await api.get('/campaign-ads/advertisers', { params: { cmig_id: cmigId } })
    return data.advertisers || []
  }

  async function loadCampaigns(params) {
    const { data } = await api.get('/campaign-ads/product/campaigns', { params })
    return data
  }

  async function loadAds(params) {
    const { data } = await api.get('/campaign-ads/product/ads', { params })
    return data
  }

  async function loadAdGroups(params) {
    const { data } = await api.get('/campaign-ads/catalog/ad-groups', { params })
    return data
  }

  async function loadCampaignDetail(params) {
    const { data } = await api.get('/campaign-ads/product/campaign-detail', { params })
    return data
  }

  async function loadAdDetail(params) {
    const { data } = await api.get('/campaign-ads/product/ad-detail', { params })
    return data
  }

  return { loadAdvertisers, loadCampaigns, loadAds, loadAdGroups, loadCampaignDetail, loadAdDetail }
}
