<template>
  <RouterView />
</template>

<script setup>
import { watch } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import api from '@/composables/useApi'

const ui = useUiStore()
const auth = useAuthStore()

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

// ── Tema de cor por Galpão ───────────────────────────────────────────────────
const THEME_VARS = {
  theme_sidebar: '--wh-sidebar',
  theme_accent: '--wh-accent',
  theme_topbar: '--wh-topbar',
  theme_sidebar_text: '--wh-sidebar-text',
  theme_link: '--wh-link',
}

function applyWarehouseTheme(theme) {
  const body = document.body
  Object.values(THEME_VARS).forEach((v) => body.style.removeProperty(v))
  let any = false
  if (theme) {
    for (const [field, cssVar] of Object.entries(THEME_VARS)) {
      if (theme[field]) {
        body.style.setProperty(cssVar, theme[field])
        any = true
      }
    }
  }
  body.classList.toggle('wh-themed', any)
}

// Reaplica sempre que o tema muda no store → reflete a troca de cor sem F5.
watch(() => ui.warehouseTheme, applyWarehouseTheme, { immediate: true, deep: true })

// Busca o tema do galpão do usuário logado. Sem warehouse_id (admin/AC) ou 403/404 → padrão MIG.
async function loadWarehouseTheme(warehouseId) {
  if (!warehouseId) {
    ui.clearWarehouseTheme()
    return
  }
  try {
    const { data } = await api.get(`/warehouse/${warehouseId}`)
    ui.setWarehouseTheme({
      logo_url: data.logo_url || null,
      name: data.trade_name || data.name || null,
      theme_sidebar: data.theme_sidebar || null,
      theme_accent: data.theme_accent || null,
      theme_topbar: data.theme_topbar || null,
      theme_sidebar_text: data.theme_sidebar_text || null,
      theme_link: data.theme_link || null,
    })
  } catch {
    ui.clearWarehouseTheme()
  }
}

watch(() => auth.user?.warehouse_id, (id) => loadWarehouseTheme(id), { immediate: true })
</script>
