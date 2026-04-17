import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/composables/useApi'
import { useUiStore } from './ui'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const accessToken = ref(null)
  const refreshToken = ref(null)

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)

  function loadFromStorage() {
    const stored = localStorage.getItem('auth')
    if (stored) {
      try {
        const data = JSON.parse(stored)
        accessToken.value = data.accessToken
        refreshToken.value = data.refreshToken
        user.value = data.user
        // Apply dark mode preference
        if (data.user?.dark_mode) {
          useUiStore().darkMode = true
        }
      } catch {
        clearStorage()
      }
    }
  }

  function saveToStorage() {
    localStorage.setItem('auth', JSON.stringify({
      accessToken: accessToken.value,
      refreshToken: refreshToken.value,
      user: user.value,
    }))
  }

  function clearStorage() {
    localStorage.removeItem('auth')
    accessToken.value = null
    refreshToken.value = null
    user.value = null
  }

  async function login(email, password) {
    const { data } = await api.post('/auth/login', { email, password })
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    user.value = {
      id: data.user_id,
      full_name: data.full_name,
      email: data.email,
      role: data.role,
      dark_mode: data.dark_mode,
    }
    saveToStorage()
    if (data.dark_mode) {
      useUiStore().darkMode = true
    }
    return data
  }

  async function register(payload) {
    const { data } = await api.post('/auth/register', payload)
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    user.value = {
      id: data.user_id,
      full_name: data.full_name,
      email: data.email,
      role: data.role,
      dark_mode: data.dark_mode,
    }
    saveToStorage()
    return data
  }

  async function logout() {
    try {
      if (refreshToken.value) {
        await api.post('/auth/logout', { refresh_token: refreshToken.value })
      }
    } finally {
      clearStorage()
    }
  }

  async function doRefresh() {
    const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken.value })
    accessToken.value = data.access_token
    refreshToken.value = data.refresh_token
    saveToStorage()
    return data.access_token
  }

  return {
    user,
    accessToken,
    refreshToken,
    isAuthenticated,
    loadFromStorage,
    login,
    register,
    logout,
    doRefresh,
  }
})
