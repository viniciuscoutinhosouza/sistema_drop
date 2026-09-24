import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const darkMode = ref(false)
  const sidebarCollapsed = ref(false)
  // Tema de cor + logo do Galpão do usuário logado (branding). null = padrão MIG.
  // { logo_url, name, theme_sidebar, theme_accent, theme_topbar, theme_sidebar_text, theme_link }
  const warehouseTheme = ref(null)

  function toggleDarkMode() {
    darkMode.value = !darkMode.value
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setWarehouseTheme(theme) {
    warehouseTheme.value = theme || null
  }

  function clearWarehouseTheme() {
    warehouseTheme.value = null
  }

  return {
    darkMode,
    sidebarCollapsed,
    warehouseTheme,
    toggleDarkMode,
    toggleSidebar,
    setWarehouseTheme,
    clearWarehouseTheme,
  }
})
