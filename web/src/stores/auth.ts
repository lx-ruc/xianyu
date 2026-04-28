import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('access_token') || '')
  const refreshTokenVal = ref(localStorage.getItem('refresh_token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isAuthenticated = computed(() => !!token.value)

  async function login(user: string, password: string) {
    const { data } = await api.post('/auth/login', { username: user, password })
    token.value = data.access_token
    refreshTokenVal.value = data.refresh_token
    username.value = user
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    localStorage.setItem('username', user)
  }

  function logout() {
    token.value = ''
    refreshTokenVal.value = ''
    username.value = ''
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('username')
  }

  return { token, username, isAuthenticated, login, logout }
})
