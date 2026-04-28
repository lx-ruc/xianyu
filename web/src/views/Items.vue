<template>
  <div>
    <el-card>
      <template #header>
        <div class="card-header">
          <span class="card-title">商品管理</span>
          <div class="card-actions">
            <el-button @click="handleSync" :loading="syncing">
              <el-icon><Refresh /></el-icon>
              <span>同步数据</span>
            </el-button>
            <el-popconfirm title="确认擦亮所有商品？" @confirm="handleBumpAll">
              <template #reference>
                <el-button type="primary" :loading="bumping">
                  <el-icon><Promotion /></el-icon>
                  <span>一键擦亮</span>
                </el-button>
              </template>
            </el-popconfirm>
          </div>
        </div>
      </template>

      <el-table :data="healthItems" stripe v-loading="loading">
        <el-table-column type="index" width="50" label="#" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="browse_cnt" label="浏览" width="90" sortable />
        <el-table-column prop="want_cnt" label="想要" width="90" sortable />
        <el-table-column prop="days" label="天数" width="80" sortable />
        <el-table-column prop="daily_browse" label="日均浏览" width="100" sortable />
        <el-table-column label="健康度" width="100">
          <template #default="{ row }">
            <el-tag :type="healthType(row.health)" size="small" effect="light">
              {{ healthLabel(row.health) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              plain
              @click="handleBump(row.item_id)"
              :loading="bumpingIds.has(row.item_id)"
            >
              擦亮
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const healthItems = ref<any[]>([])
const loading = ref(false)
const syncing = ref(false)
const bumping = ref(false)
const bumpingIds = ref<Set<string>>(new Set())

function healthType(h: string) {
  return { excellent: 'success', good: '', warning: 'warning', critical: 'danger' }[h] || 'info'
}
function healthLabel(h: string) {
  return { excellent: '优秀', good: '良好', warning: '偏低', critical: '极差' }[h] || h
}

async function fetchData() {
  loading.value = true
  try {
    const { data } = await api.get('/analytics/item-health')
    healthItems.value = data.items || []
  } finally {
    loading.value = false
  }
}

async function handleBump(itemId: string) {
  bumpingIds.value = new Set([...bumpingIds.value, itemId])
  try {
    const { data } = await api.post(`/items/${itemId}/bump`)
    if (data.error) {
      ElMessage.error(data.error)
      return
    }
    ElMessage[data.success ? 'success' : 'warning'](data.message)
  } catch {
    ElMessage.error('擦亮失败')
  } finally {
    const next = new Set(bumpingIds.value)
    next.delete(itemId)
    bumpingIds.value = next
  }
}

async function handleBumpAll() {
  bumping.value = true
  try {
    const { data } = await api.post('/items/bump-all')
    if (data.error) {
      ElMessage.error(data.error)
      return
    }
    ElMessage.success(`擦亮完成: 成功${data.success ?? 0}件, 已擦亮${data.already ?? 0}件, 失败${data.fail ?? 0}件`)
    await fetchData()
  } catch {
    ElMessage.error('擦亮失败')
  } finally {
    bumping.value = false
  }
}

async function handleSync() {
  syncing.value = true
  try {
    const { data } = await api.post('/items/sync')
    ElMessage.success(`同步完成: ${data.synced} 件商品`)
    await fetchData()
  } catch {
    ElMessage.error('同步失败')
  } finally {
    syncing.value = false
  }
}

onMounted(fetchData)
</script>

<style scoped>
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  font-size: var(--text-base);
}

.card-actions {
  display: flex;
  gap: var(--space-2);
}
</style>
