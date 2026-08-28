import { ref, onUnmounted, watch } from 'vue'

/**
 * WebSocket-based real-time collaboration composable.
 * Usage: const { isConnected, presence, sendChange } = useRealtime('knowledge_doc', docId)
 */
export function useRealtime(resourceType, resourceId) {
  const ws = ref(null)
  const isConnected = ref(false)
  const presence = ref([])
  const lastChange = ref(null)

  let reconnectTimer = null
  let instanceKey = Math.random().toString(36).slice(2, 8)

  function connect() {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) return

    const token = localStorage.getItem('access_token') || ''
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/ws/${resourceType}/${resourceId}?token=${token}`

    try {
      const socket = new WebSocket(url)
      ws.value = socket

      socket.onopen = () => {
        isConnected.value = true
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
      }

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'presence') {
            presence.value = data.users || []
          } else {
            lastChange.value = data
          }
        } catch {}
      }

      socket.onclose = () => {
        isConnected.value = false
        // Reconnect after 3s
        if (!reconnectTimer) {
          reconnectTimer = setTimeout(() => { connect() }, 3000)
        }
      }

      socket.onerror = () => {
        socket.close()
      }
    } catch {
      // WebSocket not available, use polling fallback
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(() => { connect() }, 5000)
      }
    }
  }

  function send(data) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ ...data, _instance: instanceKey }))
    }
  }

  function sendChange(changeData) {
    send({ type: 'change', ...changeData })
  }

  function disconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isConnected.value = false
    presence.value = []
  }

  onUnmounted(() => disconnect())

  return { isConnected, presence, lastChange, connect, disconnect, sendChange, send }
}
