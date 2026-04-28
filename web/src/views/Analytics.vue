<template>
  <div>
    <!-- Trend Chart -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">商品浏览量趋势</span>
          <el-select v-model="hours" style="width: 130px" @change="fetchData">
            <el-option label="最近24小时" :value="24" />
            <el-option label="最近7天" :value="168" />
            <el-option label="最近30天" :value="720" />
          </el-select>
        </div>
      </template>
      <div class="chart-container">
        <v-chart :option="trendOption" autoresize />
      </div>
    </el-card>

    <!-- Bottom Row -->
    <el-row :gutter="16">
      <el-col :span="12">
        <el-card class="section-card">
          <template #header>
            <span class="card-title">竞品对比</span>
          </template>
          <div class="chart-container">
            <v-chart :option="competitorOption" autoresize />
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card class="section-card">
          <template #header>
            <span class="card-title">搜索排名</span>
          </template>
          <div class="ranking-list">
            <div v-for="r in rankings" :key="r.keyword" class="ranking-group">
              <div class="ranking-header">
                <strong>{{ r.keyword }}</strong>
                <span class="ranking-meta">{{ r.competitors_count }} 个竞品</span>
              </div>
              <el-progress
                v-for="item in r.my_items"
                :key="item.item_id"
                :percentage="Math.min(100, (item.views / 24000) * 100)"
                :format="() => `#${item.item_id.slice(-4)} - ${item.views}浏览`"
                :stroke-width="16"
                class="ranking-progress"
              />
            </div>
            <el-empty v-if="!rankings.length" description="暂无排名数据" :image-size="80" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart, BarChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import api from '../api'

use([LineChart, BarChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

const hours = ref(168)
const healthItems = ref<any[]>([])
const competitors = ref<any[]>([])
const rankings = ref<any[]>([])

const trendOption = computed(() => ({
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(15, 23, 42, 0.9)',
    borderColor: 'transparent',
    textStyle: { color: '#F8FAFC', fontSize: 13 },
  },
  legend: {
    textStyle: { color: '#64748B' },
  },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category',
    data: healthItems.value.map((i: any) => i.title.slice(0, 10)),
    axisLine: { lineStyle: { color: '#E2E8F0' } },
    axisLabel: { color: '#64748B' },
  },
  yAxis: {
    type: 'value',
    name: '浏览量',
    nameTextStyle: { color: '#94A3B8' },
    axisLine: { show: false },
    splitLine: { lineStyle: { color: '#F1F5F9' } },
    axisLabel: { color: '#64748B' },
  },
  series: [
    {
      name: '浏览量',
      type: 'bar',
      data: healthItems.value.map((i: any) => i.browse_cnt),
      itemStyle: { color: '#2563EB', borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 32,
    },
    {
      name: '想要数',
      type: 'bar',
      data: healthItems.value.map((i: any) => i.want_cnt),
      itemStyle: { color: '#10B981', borderRadius: [4, 4, 0, 0] },
      barMaxWidth: 32,
    },
  ],
}))

const competitorOption = computed(() => {
  const top10 = competitors.value.slice(0, 10)
  return {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 23, 42, 0.9)',
      borderColor: 'transparent',
      textStyle: { color: '#F8FAFC', fontSize: 13 },
    },
    grid: { left: '30%', right: '8%', top: '3%', bottom: '3%' },
    xAxis: {
      type: 'value',
      name: '浏览量',
      nameTextStyle: { color: '#94A3B8' },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#F1F5F9' } },
      axisLabel: { color: '#64748B' },
    },
    yAxis: {
      type: 'category',
      data: top10.map((c: any) => c.title?.slice(0, 15) || ''),
      axisLine: { lineStyle: { color: '#E2E8F0' } },
      axisLabel: { color: '#64748B', fontSize: 12 },
    },
    series: [{
      type: 'bar',
      data: top10.map((c: any) => c.views),
      itemStyle: { color: '#F59E0B', borderRadius: [0, 4, 4, 0] },
      barMaxWidth: 20,
    }],
  }
})

async function fetchData() {
  try {
    const [healthRes, compRes, rankRes] = await Promise.all([
      api.get('/analytics/item-health'),
      api.get('/analytics/competitors'),
      api.get('/analytics/ranking'),
    ])
    healthItems.value = healthRes.data.items || []
    competitors.value = compRes.data.competitors || []
    rankings.value = rankRes.data.rankings || []
  } catch { /* ignore */ }
}

onMounted(fetchData)
</script>

<style scoped>
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

.chart-container {
  height: 350px;
}

.ranking-list {
  max-height: 350px;
  overflow-y: auto;
}

.ranking-group {
  margin-bottom: var(--space-4);
}

.ranking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
  font-size: var(--text-sm);
}

.ranking-meta {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.ranking-progress {
  margin-bottom: var(--space-2);
}
</style>
