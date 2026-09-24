import { useCallback, useEffect, useRef, useState } from 'react'

export const SPEEDS = [15, 60, 300]
/** Как часто отпускаем новое время наружу: каждое значение — это запрос кадра к API. */
const COMMIT_MS = 120

export interface Playback {
  t: number | null
  playing: boolean
  speed: number
  toggle: () => void
  cycleSpeed: () => void
  seek: (t: number) => void
}

/**
 * Часы воспроизведения записанного дня. Здесь живет только позиция ползунка — все, что
 * показывается на этот момент, приходит с сервера (GET /api/replay/frame).
 */
export function usePlayback(bounds: { tMin: number; tMax: number } | null): Playback {
  const [t, setT] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(60)
  const clock = useRef(0)

  useEffect(() => {
    if (bounds && t === null) {
      // начинаем с утреннего пика — там видно, ради чего нужен прогноз
      const start = Math.min(Math.max(7.5 * 60, bounds.tMin), bounds.tMax)
      clock.current = start
      setT(start)
    }
  }, [bounds, t])

  useEffect(() => {
    if (!playing || !bounds) return
    let raf = 0
    let last = performance.now()
    let sinceCommit = 0

    const step = (now: number) => {
      const dt = now - last
      last = now
      clock.current += (dt / 1000) * (speed / 60)
      if (clock.current > bounds.tMax) clock.current = bounds.tMin
      sinceCommit += dt
      if (sinceCommit >= COMMIT_MS) {
        sinceCommit = 0
        setT(clock.current)
      }
      raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, bounds])

  const seek = useCallback((next: number) => {
    clock.current = next
    setT(next)
  }, [])

  const cycleSpeed = useCallback(
    () => setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length]),
    [],
  )

  return { t, playing, speed, toggle: () => setPlaying((p) => !p), cycleSpeed, seek }
}
