import { useCallback, useEffect, useRef, useState } from 'react'

import { getFleetPositions } from '../api'
import type { FleetPositionResponse } from '../types'

const REFRESH_INTERVAL_MS = 10_000

export function useFleetPositions() {
  const [data, setData] = useState<FleetPositionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const controller = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    controller.current?.abort()
    controller.current = new AbortController()
    try {
      const result = await getFleetPositions(controller.current.signal)
      setData(result)
      setError(null)
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') return
      setError(cause instanceof Error ? cause.message : 'Falha ao atualizar a frota')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), REFRESH_INTERVAL_MS)
    return () => {
      window.clearInterval(timer)
      controller.current?.abort()
    }
  }, [refresh])

  return { data, error, loading, refresh }
}
