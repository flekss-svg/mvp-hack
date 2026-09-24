import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface Resource<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
}

/**
 * Загрузка с сервера: перезапрашивает при смене deps, отменяет предыдущий запрос и, если
 * задан pollMs, обновляет данные по таймеру. Прошлые данные остаются на экране, пока едут
 * новые, — дашборд не должен моргать пустотой на каждом такте.
 */
export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: { pollMs?: number; enabled?: boolean } = {},
): Resource<T> {
  const { pollMs, enabled = true } = options
  const [state, setState] = useState<Resource<T>>({ data: null, error: null, loading: enabled })
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false })
      return
    }
    const ctrl = new AbortController()
    let timer: number | undefined
    let stopped = false

    const run = async () => {
      try {
        const data = await loadRef.current(ctrl.signal)
        if (!stopped) setState({ data, error: null, loading: false })
      } catch (e) {
        if (ctrl.signal.aborted || stopped) return
        const error = e instanceof ApiError ? e : new ApiError((e as Error).message)
        setState((prev) => ({ data: prev.data, error, loading: false }))
      }
      if (!stopped && pollMs) timer = window.setTimeout(run, pollMs)
    }

    setState((prev) => ({ ...prev, loading: true }))
    void run()
    return () => {
      stopped = true
      ctrl.abort()
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, pollMs, enabled])

  return state
}
