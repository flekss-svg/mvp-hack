import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface Resource<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  updatedAt: number | null
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
): Resource<T> & { refresh: () => void } {
  const { pollMs, enabled = true } = options
  const [state, setState] = useState<Resource<T>>({ data: null, error: null, loading: enabled, updatedAt: null })
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision((v) => v + 1), [])
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false, updatedAt: null })
      return
    }
    const ctrl = new AbortController()
    let timer: number | undefined
    let stopped = false

    const run = async () => {
      try {
        const data = await loadRef.current(ctrl.signal)
        if (!stopped) setState({ data, error: null, loading: false, updatedAt: Date.now() })
      } catch (e) {
        if (ctrl.signal.aborted || stopped) return
        const error = e instanceof ApiError ? e : new ApiError((e as Error).message)
        setState((prev) => ({ ...prev, error, loading: false }))
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
  }, [...deps, pollMs, enabled, revision])

  return { ...state, refresh }
}
