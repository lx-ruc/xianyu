import { ref, onUnmounted } from 'vue'

export function useWebSocket(path: string, onMessage: (data: any) => void) {
  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: number | null = null

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}${path}`
    ws = new WebSocket(url)

    ws.onopen = () => { connected.value = true }
    ws.onclose = () => {
      connected.value = false
      reconnectTimer = window.setTimeout(connect, 3000)
    }
    ws.onmessage = (event) => {
      try { onMessage(JSON.parse(event.data)) } catch { /* ignore */ }
    }
    ws.onerror = () => { ws?.close() }
  }

  function disconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
    ws = null
  }

  connect()
  onUnmounted(disconnect)

  return { connected, disconnect }
}
