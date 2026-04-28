import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useConversationsStore = defineStore('conversations', () => {
  const conversations = ref<any[]>([])
  const currentMessages = ref<any[]>([])
  const currentChatId = ref('')
  const currentMode = ref('auto')
  const loading = ref(false)

  async function fetchConversations(itemId?: string) {
    loading.value = true
    try {
      const params: any = {}
      if (itemId) params.item_id = itemId
      const { data } = await api.get('/conversations', { params })
      conversations.value = data.conversations
    } finally {
      loading.value = false
    }
  }

  async function fetchMessages(chatId: string) {
    currentChatId.value = chatId
    const { data } = await api.get(`/conversations/${chatId}`)
    currentMessages.value = data.messages
    currentMode.value = data.mode
    return data
  }

  async function sendReply(chatId: string, content: string) {
    await api.post(`/conversations/${chatId}/reply`, { content })
  }

  async function toggleMode(chatId: string, mode: 'manual' | 'auto') {
    await api.post(`/conversations/${chatId}/toggle-mode`, { mode })
    currentMode.value = mode
  }

  return { conversations, currentMessages, currentChatId, currentMode, loading, fetchConversations, fetchMessages, sendReply, toggleMode }
})
