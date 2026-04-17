<template>
  <RouterView />
</template>

<script setup>
import { watch } from 'vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

// Apply dark-mode class to body whenever preference changes
watch(
  () => ui.darkMode,
  (isDark) => {
    if (isDark) {
      document.body.classList.add('dark-mode')
    } else {
      document.body.classList.remove('dark-mode')
    }
  },
  { immediate: true }
)
</script>
