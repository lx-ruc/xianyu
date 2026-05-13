<template>
  <div>
    <!-- KPI Cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-primary-lighter); color: var(--color-primary)">
            <el-icon :size="22"><List /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">今日订单</div>
            <div class="kpi-value">{{ stats.today_count }}</div>
          </div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-success-light); color: var(--color-success)">
            <el-icon :size="22"><CircleCheck /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">今日已发货</div>
            <div class="kpi-value">{{ stats.today_delivered }}</div>
          </div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-info-light); color: var(--color-info)">
            <el-icon :size="22"><Star /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">已评价</div>
            <div class="kpi-value">{{ stats.rated }}</div>
          </div>
        </div>
      </div>

      <div class="kpi-card">
        <div class="kpi-inner">
          <div class="kpi-icon-wrap" style="background: var(--color-warning-light); color: var(--color-warning)">
            <el-icon :size="22"><Clock /></el-icon>
          </div>
          <div class="kpi-content">
            <div class="kpi-label">待处理</div>
            <div class="kpi-value">{{ stats.pending + stats.rate_failed }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Config Panel -->
    <el-card class="config-card">
      <div class="config-grid">
        <!-- Auto Delivery Toggle -->
        <div class="config-item">
          <div class="config-info">
            <div class="kpi-icon-wrap config-icon" style="background: var(--color-primary-lighter); color: var(--color-primary)">
              <el-icon :size="16"><Promotion /></el-icon>
            </div>
            <div>
              <div class="config-label">自动发货</div>
              <div class="config-desc">买家付款后自动标记为已发货</div>
            </div>
          </div>
          <el-switch
            v-model="config.auto_delivery"
            @change="(val: boolean) => updateConfig('auto_delivery', val)"
            :loading="configLoading"
            active-text="开启"
            inactive-text="关闭"
          />
        </div>

        <el-divider />

        <!-- Auto Rate Toggle -->
        <div class="config-item">
          <div class="config-info">
            <div class="kpi-icon-wrap config-icon" style="background: var(--color-success-light); color: var(--color-success)">
              <el-icon :size="16"><Star /></el-icon>
            </div>
            <div>
              <div class="config-label">自动好评</div>
              <div class="config-desc">交易完成后自动给买家好评</div>
            </div>
          </div>
          <el-switch
            v-model="config.auto_rate"
            @change="(val: boolean) => updateConfig('auto_rate', val)"
            :loading="configLoading"
            active-text="开启"
            inactive-text="关闭"
          />
        </div>

        <!-- Rate Content -->
        <div class="rate-content-row" v-if="config.auto_rate">
          <span class="rate-content-label">好评文案</span>
          <el-input
            v-model="config.rate_content"
            placeholder="输入好评文案"
            size="small"
            class="rate-content-input"
            @blur="updateConfig('rate_content', config.rate_content)"
          />
        </div>
      </div>
    </el-card>

    <!-- Orders Table -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <div class="card-title-group">
            <span class="card-title">订单列表</span>
            <el-tag size="small" type="info">{{ total }} 条</el-tag>
          </div>
          <div class="card-actions">
            <el-button @click="fetchData" :loading="loading">
              <el-icon><Refresh /></el-icon>
              <span>刷新</span>
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="orders" stripe size="small" v-loading="loading">
        <el-table-column type="index" width="50" label="#" />
        <el-table-column prop="biz_order_id" label="订单ID" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono-text">{{ row.biz_order_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="user_id" label="买家ID" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono-text">{{ row.user_id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="item_id" label="商品ID" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="mono-text">{{ row.item_id || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" effect="light">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发货时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ row.delivered_at ? formatTime(row.delivered_at) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <div class="action-group">
              <el-button
                v-if="row.status === 'pending' || row.status === 'failed'"
                size="small"
                type="primary"
                plain
                @click="handleManualDeliver(row.biz_order_id)"
                :loading="deliveringIds.has(row.biz_order_id)"
              >
                发货
              </el-button>
              <el-button
                v-if="row.status === 'delivered' || row.status === 'rate_failed'"
                size="small"
                type="success"
                plain
                @click="handleManualRate(row.biz_order_id)"
                :loading="ratingIds.has(row.biz_order_id)"
              >
                评价
              </el-button>
              <el-icon
                v-if="row.status === 'rated'"
                :size="16"
                color="var(--color-success)"
              >
                <CircleCheck />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无订单" :image-size="80" />
        </template>
      </el-table>

      <div class="pagination-row" v-if="total > pageSize">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

interface Order {
  biz_order_id: string
  user_id: string
  item_id: string | null
  status: string
  delivery_result: string | null
  created_at: string | null
  delivered_at: string | null
}

interface OrderStats {
  total: number
  pending: number
  delivered: number
  failed: number
  rated: number
  rate_failed: number
  today_count: number
  today_delivered: number
}

interface OrderConfig {
  auto_delivery: boolean
  auto_rate: boolean
  rate_content: string
}

const orders = ref<Order[]>([])
const stats = ref<OrderStats>({
  total: 0, pending: 0, delivered: 0, failed: 0,
  rated: 0, rate_failed: 0, today_count: 0, today_delivered: 0,
})
const config = reactive<OrderConfig>({
  auto_delivery: false,
  auto_rate: false,
  rate_content: '好买家，交易愉快',
})
const loading = ref(false)
const configLoading = ref(false)
const deliveringIds = ref<Set<string>>(new Set())
const ratingIds = ref<Set<string>>(new Set())
const currentPage = ref(1)
const pageSize = 20
const total = ref(0)

function statusType(s: string) {
  return {
    pending: 'warning',
    delivered: '',
    failed: 'danger',
    rated: 'success',
    rate_failed: 'danger',
  }[s] || 'info'
}

function statusLabel(s: string) {
  return {
    pending: '待发货',
    delivered: '已发货',
    failed: '发货失败',
    rated: '已评价',
    rate_failed: '评价失败',
  }[s] || s
}

function formatTime(t: string | null): string {
  if (!t) return '-'
  try {
    const d = new Date(t)
    if (isNaN(d.getTime())) return t
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch {
    return t
  }
}

async function fetchData() {
  loading.value = true
  try {
    const [ordersRes, statsRes] = await Promise.all([
      api.get('/orders', { params: { page: currentPage.value, page_size: pageSize } }),
      api.get('/orders/stats'),
    ])
    orders.value = ordersRes.data.orders || []
    total.value = ordersRes.data.total || 0
    stats.value = statsRes.data
  } catch {
    ElMessage.error('加载订单失败')
  } finally {
    loading.value = false
  }
}

async function fetchConfig() {
  try {
    const { data } = await api.get('/orders/config')
    config.auto_delivery = data.auto_delivery ?? false
    config.auto_rate = data.auto_rate ?? false
    config.rate_content = data.rate_content ?? '好买家，交易愉快'
  } catch {
    // silent
  }
}

async function updateConfig(key: string, value: boolean | string) {
  configLoading.value = true
  try {
    const payload: Record<string, unknown> = {}
    payload[key] = value
    const { data } = await api.post('/orders/config', payload)
    if (data.error) {
      ElMessage.error(data.error)
      await fetchConfig()
      return
    }
    ElMessage.success(data.message)
  } catch {
    ElMessage.error('配置失败')
    await fetchConfig()
  } finally {
    configLoading.value = false
  }
}

async function handleManualDeliver(orderId: string) {
  deliveringIds.value = new Set([...deliveringIds.value, orderId])
  try {
    const { data } = await api.post(`/orders/${orderId}/deliver`)
    if (data.error) {
      ElMessage.error(data.error)
      return
    }
    ElMessage[data.success ? 'success' : 'warning'](data.message)
    await fetchData()
  } catch {
    ElMessage.error('发货失败')
  } finally {
    const next = new Set(deliveringIds.value)
    next.delete(orderId)
    deliveringIds.value = next
  }
}

async function handleManualRate(orderId: string) {
  ratingIds.value = new Set([...ratingIds.value, orderId])
  try {
    const { data } = await api.post(`/orders/${orderId}/rate`)
    if (data.error) {
      ElMessage.error(data.error)
      return
    }
    ElMessage[data.success ? 'success' : 'warning'](data.message)
    await fetchData()
  } catch {
    ElMessage.error('评价失败')
  } finally {
    const next = new Set(ratingIds.value)
    next.delete(orderId)
    ratingIds.value = next
  }
}

onMounted(() => {
  fetchData()
  fetchConfig()
})
</script>

<style scoped>
/* KPI Grid */
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

/* Config Panel */
.config-card {
  margin-bottom: var(--space-5);
}

.config-card :deep(.el-card__body) {
  padding: var(--space-4) var(--space-5);
}

.config-card :deep(.el-divider) {
  margin: var(--space-3) 0;
}

.config-grid {
  display: flex;
  flex-direction: column;
}

.config-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-info {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.config-icon {
  width: 36px;
  height: 36px;
}

.config-label {
  font-weight: 600;
  font-size: var(--text-base);
  color: var(--color-text);
}

.config-desc {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
}

.rate-content-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-3);
  padding-left: 48px;
}

.rate-content-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  white-space: nowrap;
}

.rate-content-input {
  max-width: 280px;
}

/* Table Section */
.section-card {
  margin-bottom: var(--space-5);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title-group {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.card-title {
  font-weight: 600;
  font-size: var(--text-base);
}

.card-actions {
  display: flex;
  gap: var(--space-2);
}

.mono-text {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.time-text {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.action-group {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: var(--space-4);
}

/* Responsive */
@media (max-width: 1200px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .config-item {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }
}
</style>
