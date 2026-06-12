import { ref } from 'vue'
import api from '@/composables/useApi'

// Estado compartilhado/cacheado: carrega uma vez por sessão.
const enabled = ref(false)
let loaded = false

/**
 * Composable do módulo eShip. `eshipEnabled` indica se há algum galpão com
 * integração eShip ativa — usado para decidir se mostra as ações de eShip.
 */
export function useEship() {
  async function ensureLoaded() {
    if (loaded) return
    loaded = true
    try {
      const { data } = await api.get('/integrations/eship/enabled')
      enabled.value = !!data.enabled
    } catch {
      enabled.value = false
    }
  }
  return { eshipEnabled: enabled, ensureLoaded }
}
