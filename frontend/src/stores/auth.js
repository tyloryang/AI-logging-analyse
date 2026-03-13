import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/index.js'

const LEVEL_RANK = { none: 0, view: 1, operate: 2 }

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)   // { id, username, displayName, isAdmin }
  const permissions = ref({}) // { module_id: level }
  const loading = ref(false)

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.isAdmin ?? false)

  function can(module, level = 'view') {
    if (!user.value) return false
    if (user.value.isAdmin) return true
    const userLevel = permissions.value[module] ?? 'none'
    return (LEVEL_RANK[userLevel] ?? 0) >= (LEVEL_RANK[level] ?? 0)
  }

  async function fetchMe() {
    loading.value = true
    try {
      const data = await api.getMe()
      user.value = {
        id: data.id,
        username: data.username,
        email: data.email,
        displayName: data.display_name,
        isAdmin: data.is_superuser,
      }
      permissions.value = data.permissions ?? {}
      return true
    } catch {
      user.value = null
      permissions.value = {}
      return false
    } finally {
      loading.value = false
    }
  }

  async function login(username, password) {
    const data = await api.login({ username, password })
    user.value = {
      id: data.id,
      username: data.username,
      displayName: data.display_name,
      isAdmin: data.is_superuser,
    }
    permissions.value = data.permissions ?? {}
  }

  async function logout() {
    try { await api.logout() } catch {}
    user.value = null
    permissions.value = {}
  }

  return { user, permissions, loading, isLoggedIn, isAdmin, can, fetchMe, login, logout }
})
