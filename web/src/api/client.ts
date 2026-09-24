/** Единственное место во фронтенде, которое знает про HTTP и адреса эндпоинтов. */
import type { ApiProblem, DayInfo, Frame, LiveSnapshot, ModelQuality, Timeline } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  constructor(
    message: string,
    readonly problem?: ApiProblem,
  ) {
    super(message)
  }
}

async function get<T>(path: string, params?: Record<string, string | number | undefined>, signal?: AbortSignal): Promise<T> {
  const query = new URLSearchParams()
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== '') query.set(k, String(v))
  }
  const qs = query.toString()
  const res = await fetch(`${BASE}/api${path}${qs ? `?${qs}` : ''}`, { signal })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    if (detail && typeof detail === 'object') throw new ApiError(detail.hint, detail as ApiProblem)
    throw new ApiError(typeof detail === 'string' ? detail : `Ошибка API: HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  model: (signal?: AbortSignal) => get<ModelQuality>('/model', undefined, signal),
  day: (signal?: AbortSignal) => get<DayInfo>('/replay/day', undefined, signal),
  frame: (
    p: { t: number; mode?: string; minLevel?: number; trip?: number | null },
    signal?: AbortSignal,
  ) =>
    get<Frame>(
      '/replay/frame',
      {
        t: p.t.toFixed(2),
        mode: p.mode === 'all' ? undefined : p.mode,
        min_level: p.minLevel || undefined,
        trip: p.trip ?? undefined,
      },
      signal,
    ),
  timeline: (mode: string | undefined, signal?: AbortSignal) =>
    get<Timeline>('/replay/timeline', { mode: mode === 'all' ? undefined : mode }, signal),
  live: (signal?: AbortSignal) => get<LiveSnapshot>('/live/snapshot', undefined, signal),
}
