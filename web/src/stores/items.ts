import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useItemsStore = defineStore('items', () => {
  const items = ref<any[]>([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchItems(page = 1, pageSize = 20) {
    loading.value = true
    try {
      const { data } = await api.get('/items', { params: { page, page_size: pageSize } })
      items.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  async function bumpItem(itemId: string) {
    return (await api.post(`/items/${itemId}/bump`)).data
  }

  async function bumpAll() {
    return (await api.post('/items/bump-all')).data
  }

  async function syncItems() {
    loading.value = true
    try {
      return (await api.post('/items/sync')).data
    } finally {
      loading.value = false
    }
  }

  return { items, total, loading, fetchItems, bumpItem, bumpAll, syncItems }
})
