import { useToast } from '@/composables/useToast'

/**
 * Copiar para a área de transferência, com feedback.
 * Centraliza o padrão que estava reimplementado inline em várias telas.
 *
 * `navigator.clipboard` só existe em contexto seguro (HTTPS/localhost) — daí o fallback
 * via textarea + execCommand, senão a cópia falha em silêncio em alguns ambientes.
 */
export function useClipboard() {
  const toast = useToast()

  async function copy(text, msg = 'Copiado!') {
    const value = (text ?? '').toString()
    if (!value.trim()) {
      toast.warning('Nada para copiar.')
      return false
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value)
      } else {
        const ta = document.createElement('textarea')
        ta.value = value
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      toast.success(msg)
      return true
    } catch {
      toast.error('Não foi possível copiar.')
      return false
    }
  }

  return { copy }
}
