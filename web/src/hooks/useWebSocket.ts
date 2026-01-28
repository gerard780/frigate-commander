import { useEffect, useRef, useState, useCallback } from 'react'
import type { Job } from '../api/types'

interface UseJobWebSocketOptions {
  onUpdate?: (job: Job) => void
  onComplete?: (job: Job) => void
  onError?: (error: Event) => void
  reconnect?: boolean
  reconnectInterval?: number
}

export function useJobWebSocket(
  jobId: string | null,
  options: UseJobWebSocketOptions = {}
) {
  const {
    onUpdate,
    onComplete,
    onError,
    reconnect = true,
    reconnectInterval = 3000,
  } = options

  const [job, setJob] = useState<Job | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  const connect = useCallback(() => {
    if (!jobId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const ws = new WebSocket(`${protocol}//${host}/api/ws/jobs/${jobId}`)

    ws.onopen = () => {
      setConnected(true)
      setError(null)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'heartbeat') return

        const updatedJob = data as Job
        setJob(updatedJob)
        onUpdate?.(updatedJob)

        if (['completed', 'failed', 'cancelled'].includes(updatedJob.status)) {
          onComplete?.(updatedJob)
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onerror = (event) => {
      setError('WebSocket error')
      onError?.(event)
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null

      // Reconnect if enabled and job is still running
      if (reconnect && job?.status === 'running') {
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect()
        }, reconnectInterval)
      }
    }

    wsRef.current = ws
  }, [jobId, onUpdate, onComplete, onError, reconnect, reconnectInterval, job?.status])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send('ping')
    }
  }, [])

  useEffect(() => {
    connect()
    return () => disconnect()
  }, [connect, disconnect])

  return {
    job,
    connected,
    error,
    sendPing,
    disconnect,
    reconnect: connect,
  }
}
