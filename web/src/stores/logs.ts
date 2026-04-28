import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface LogEntry {
  type: string
  level: string
  message: string
  source: string
  timestamp: string
}

export const useLogsStore = defineStore('logs', () => {
  const logs = ref<LogEntry[]>([])
  const paused = ref(false)
  const levelFilter = ref('INFO')
  const maxLogs = 1000

  function addLog(entry: LogEntry) {
    if (paused.value) return
    logs.value.push(entry)
    if (logs.value.length > maxLogs) {
      logs.value = logs.value.slice(-maxLogs)
    }
  }

  function clearLogs() { logs.value = [] }
  function togglePause() { paused.value = !paused.value }

  return { logs, paused, levelFilter, addLog, clearLogs, togglePause }
})
