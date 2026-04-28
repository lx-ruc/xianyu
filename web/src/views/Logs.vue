<template>
  <el-card class="logs-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">运行日志</span>
        <div class="card-actions">
          <el-select v-model="store.levelFilter" style="width: 130px" size="default">
            <el-option label="全部" value="DEBUG" />
            <el-option label="INFO" value="INFO" />
            <el-option label="WARNING" value="WARNING" />
            <el-option label="ERROR" value="ERROR" />
          </el-select>
          <el-button @click="store.togglePause" :type="store.paused ? 'success' : 'default'">
            <el-icon><VideoPlay v-if="store.paused" /><VideoPause v-else /></el-icon>
            <span>{{ store.paused ? '恢复' : '暂停' }}</span>
          </el-button>
          <el-button @click="store.clearLogs">
            <el-icon><Delete /></el-icon>
            <span>清空</span>
          </el-button>
        </div>
      </div>
    </template>

    <div ref="logContainer" class="log-terminal">
      <div v-for="(log, i) in filteredLogs" :key="i" class="log-line">
        <span class="log-time">{{ log.timestamp?.slice(11, 19) }}</span>
        <span class="log-level" :class="`log-level-${(log.level || 'debug').toLowerCase()}`">
          [{{ log.level }}]
        </span>
        <span class="log-msg">{{ log.message }}</span>
      </div>
      <div v-if="!filteredLogs.length" class="log-empty">等待日志...</div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useLogsStore, type LogEntry } from '../stores/logs'
import { useWebSocket } from '../composables/useWebSocket'

const store = useLogsStore()
const logContainer = ref<HTMLElement>()

const levelPriority: Record<string, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3 }

const filteredLogs = computed(() =>
  store.logs.filter((log: LogEntry) =>
    (levelPriority[log.level] || 0) >= (levelPriority[store.levelFilter] || 0)
  )
)

function scrollBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

watch(() => store.logs.length, () => nextTick(scrollBottom))

useWebSocket(`/ws/logs?level=${store.levelFilter}`, (data: LogEntry) => {
  store.addLog(data)
})

onMounted(() => nextTick(scrollBottom))
</script>

<style scoped>
.logs-card {
  height: calc(100vh - var(--header-height) - var(--space-6) * 2 - var(--space-5));
  display: flex;
  flex-direction: column;
}

.logs-card :deep(.el-card__body) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0;
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

.card-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.log-terminal {
  flex: 1;
  margin: 0;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
  padding: var(--space-4);
  overflow-y: auto;
}

.log-line {
  line-height: 1.7;
  margin-bottom: 1px;
}

.log-time {
  color: #475569;
}

.log-level {
  margin: 0 6px;
  font-weight: 600;
}

.log-msg {
  color: #CBD5E1;
}

.log-empty {
  color: #475569;
  text-align: center;
  padding: var(--space-8) 0;
  font-size: var(--text-sm);
}
</style>
