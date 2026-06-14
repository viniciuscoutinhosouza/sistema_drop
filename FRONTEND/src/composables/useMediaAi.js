/**
 * Composable de IA de mídia — geração de foto e de clip (vídeo), reutilizado
 * pelo wizard de anúncios e pelos forms de produto (PG/CMIG). Centraliza o
 * polling de clips (custo real) num único lugar, com limpeza de timers no unmount.
 */
import { ref, onBeforeUnmount } from 'vue'
import api from '@/composables/useApi'
import { useToast } from '@/composables/useToast'

const MAX_POLLS = 120  // ~10 min a 5s

export function useMediaAi() {
  const toast = useToast()
  const clips = ref([])
  let timers = []

  function clearTimers() {
    timers.forEach(clearTimeout)
    timers = []
  }
  onBeforeUnmount(clearTimers)

  /** Gera uma imagem. Retorna { url, width, height }. */
  async function generatePhoto({
    prompt, marketplace = null, productType = null, productId = null,
    includeBrief = true, sourceUrls = [],
  }) {
    const { data } = await api.post('/media/generate-image', {
      prompt,
      marketplace,
      include_brief: includeBrief,
      product_type: productType,
      product_id: productId,
      source_urls: (sourceUrls || []).slice(0, 4),
    })
    return data
  }

  function _setClip(jobId, data) {
    const c = clips.value.find(x => x.job_id === jobId)
    if (c) { c.status = data.status; c.url = data.url || null; c.error = data.error || null }
  }

  async function pollClip(jobId, attempt = 0) {
    if (attempt > MAX_POLLS) { _setClip(jobId, { status: 'failed', error: 'tempo esgotado' }); return }
    try {
      const { data } = await api.get(`/media/clip-status/${jobId}`)
      if (data.status === 'running') {
        timers.push(setTimeout(() => pollClip(jobId, attempt + 1), 5000))
      } else {
        _setClip(jobId, data)
        if (data.status === 'done') toast.success('Clip gerado.')
      }
    } catch {
      timers.push(setTimeout(() => pollClip(jobId, attempt + 1), 8000))  // erro transitório → re-tenta
    }
  }

  /** Inicia a geração de um clip; adiciona à lista `clips` e começa o polling. */
  async function startClip({
    prompt, marketplace = null, productType = null, productId = null,
    includeBrief = true, sourceUrl = null,
  }) {
    const { data } = await api.post('/media/generate-clip', {
      prompt,
      marketplace,
      include_brief: includeBrief,
      product_type: productType,
      product_id: productId,
      source_url: sourceUrl,
    })
    if (data?.job_id) {
      clips.value.unshift({ job_id: data.job_id, status: 'running', url: null, error: null })
      pollClip(data.job_id)
    }
    return data
  }

  /** Carrega os clips recentes (opcionalmente de um produto) e retoma o polling dos pendentes. */
  async function loadClips({ productType = null, productId = null } = {}) {
    try {
      const params = {}
      if (productType && productId) { params.product_type = productType; params.product_id = productId }
      const { data } = await api.get('/media/clips', { params })
      clips.value = data.clips || []
      clips.value.filter(c => c.status === 'running').forEach(c => pollClip(c.job_id))
    } catch { /* silencioso */ }
  }

  /** Exclui um clip (registro + arquivo) e remove da lista. */
  async function deleteClip(jobId) {
    await api.delete(`/media/clips/${jobId}`)
    clips.value = clips.value.filter(c => c.job_id !== jobId)
  }

  return { clips, clearTimers, loadClips, pollClip, startClip, generatePhoto, deleteClip }
}
