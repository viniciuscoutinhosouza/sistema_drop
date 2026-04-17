import { ref } from 'vue'

const toasts = ref([])
let idCounter = 0

export function useToast() {
  function show(message, type = 'info', duration = 4000) {
    const id = ++idCounter
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, duration)
  }

  function success(msg) { show(msg, 'success') }
  function error(msg) { show(msg, 'danger') }
  function warning(msg) { show(msg, 'warning') }
  function info(msg) { show(msg, 'info') }
  function remove(id) { toasts.value = toasts.value.filter(t => t.id !== id) }

  return { toasts, show, success, error, warning, info, remove }
}
