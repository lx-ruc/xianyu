<template>
  <div>
    <!-- KPI Cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-primary-lighter); color: var(--color-primary)">
            <el-icon :size="22"><Monitor /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">系统状态</div>
            <div class="kpi-value-row">
              <span class="status-dot" :class="stats.bot_online ? 'online' : 'offline'"></span>
              <span :style="{ color: stats.bot_online ? 'var(--color-success)' : 'var(--color-danger)', fontWeight: 600 }">
                {{ stats.bot_online ? '运行中' : '已离线' }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-info-light); color: var(--color-info)">
            <el-icon :size="22"><ChatDotRound /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">今日对话</div>
            <div class="kpi-value">{{ stats.today_conversations ?? '-' }}</div>
          </div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-success-light); color: var(--color-success)">
            <el-icon :size="22"><Goods /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">在售商品</div>
            <div class="kpi-value">{{ stats.item_count ?? '-' }}</div>
          </div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-warning-light); color: var(--color-warning)">
            <el-icon :size="22"><User /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">手动接管</div>
            <div class="kpi-value">{{ stats.manual_mode_count ?? '-' }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 多账号概览 -->
    <el-card v-if="accountId === '__all__' && accounts.length > 1" class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">多账号概览</span>
          <el-tag size="small" type="info">{{ accounts.filter(a => a.online).length }}/{{ accounts.length }} 在线</el-tag>
        </div>
      </template>
      <el-table :data="accounts" stripe size="small">
        <el-table-column prop="display_name" label="账号" min-width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.online ? 'success' : 'danger'" size="small" effect="light">
              {{ row.online ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="manual_mode_count" label="手动接管" width="90" />
      </el-table>
    </el-card>

    <!-- Health Table -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">商品健康度</span>
          <el-tag size="small" type="info">{{ healthItems.length }} 件</el-tag>
        </div>
      </template>
      <el-table :data="healthItems" stripe size="small" v-loading="loading">
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="browse_cnt" label="浏览" width="90" sortable />
        <el-table-column prop="want_cnt" label="想要" width="90" sortable />
        <el-table-column prop="days" label="天数" width="80" sortable />
        <el-table-column prop="daily_browse" label="日均" width="80" sortable />
        <el-table-column label="健康度" width="100">
          <template #default="{ row }">
            <el-tag :type="healthType(row.health)" size="small" effect="light">
              {{ healthLabel(row.health) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Recent Activity -->
    <el-card class="section-card">
      <template #header>
        <span class="card-title">最近活动</span>
      </template>
      <el-timeline v-if="activities.length">
        <el-timeline-item
          v-for="(a, i) in activities"
          :key="i"
          :timestamp="a.timestamp"
          placement="top"
          color="var(--color-primary)"
        >
          {{ a.content }}
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无活动记录" :image-size="80" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import api from '../api'

const props = defineProps<{ accountId?: string }>()

const stats = ref<Record<string, unknown>>({})
const healthItems = ref<any[]>([])
const activities = ref<any[]>([])
const accounts = ref<any[]>([])
const loading = ref(false)

function healthType(h: string) {
  return { excellent: 'success', good: '', warning: 'warning', critical: 'danger' }[h] || 'info'
}
function healthLabel(h: string) {
  return { excellent: '优秀', good: '良好', warning: '偏低', critical: '极差' }[h] || h
}

async function loadData() {
  loading.value = true
  try {
    const params = props.accountId ? { account_id: props.accountId } : {}
    const [summaryRes, healthRes, accountsRes] = await Promise.all([
      api.get('/stats/summary', { params }),
      api.get('/analytics/item-health'),
      api.get('/accounts'),
    ])
    stats.value = summaryRes.data
    healthItems.value = healthRes.data.items || []
    accounts.value = accountsRes.data || []
  } catch { /* ignore */ } finally {
    loading.value = false
  }
}

onMounted(loadData)
watch(() => props.accountId, loadData)
</script>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.kpi-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  padding: var(--space-5);
  transition: all var(--transition-base);
  box-shadow: var(--shadow-sm);
}

.kpi-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--color-border);
}

.kpi-inner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
}

.kpi-icon-wrap {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kpi-content {
  flex: 1;
  min-width: 0;
}

.kpi-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-1);
}

.kpi-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text);
  line-height: 1.2;
}

.kpi-value-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-lg);
}

.section-card {
  margin-bottom: var(--space-5);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  font-size: var(--text-base);
}

@media (max-width: 1200px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
