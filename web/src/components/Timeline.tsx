import { useCallback, useEffect, useRef } from 'react'
import type { Timeline as TimelineData } from '../api/types'

interface Props {
  data: TimelineData | null
  t: number | null
  onSeek: (t: number) => void
}

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** Сколько машин с высоким риском в каждый момент дня. Счет ведет сервер, здесь — отрисовка. */
export function Timeline({ data, t, onSeek }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const dragging = useRef(false)

  const draw = useCallback(() => {
    const cv = ref.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx || !data) return
    const dpr = window.devicePixelRatio || 1
    const w = cv.clientWidth
    const h = cv.clientHeight
    cv.width = w * dpr
    cv.height = h * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    const span = data.tMax - data.tMin || 1
    const x = (v: number) => ((v - data.tMin) / span) * w
    const peak = Math.max(1, ...data.bins.map((b) => b.high))
    const barWidth = Math.max(1, w / Math.max(data.bins.length, 1) - 0.5)

    ctx.fillStyle = cssVar('--high')
    ctx.globalAlpha = 0.32
    for (const b of data.bins) {
      const bh = (b.high / peak) * (h - 14)
      ctx.fillRect(x(b.t), h - 12 - bh, barWidth, bh)
    }

    ctx.globalAlpha = 1
    if (data.rain) {
      ctx.fillStyle = cssVar('--sel')
      ctx.globalAlpha = 0.3
      ctx.fillRect(x(data.rain.start), 0, x(data.rain.end) - x(data.rain.start), 3)
      ctx.globalAlpha = 1
    }

    ctx.fillStyle = cssVar('--muted')
    ctx.font = '11px Onest, system-ui'
    const every = w < 600 ? 4 : 2
    data.ticks.forEach((tick, i) => {
      if (i % every) return
      const label = ctx.measureText(tick.label).width
      ctx.fillText(tick.label, Math.min(Math.max(x(tick.t) - label / 2, 0), w - label), h - 1)
    })

    if (t !== null) {
      ctx.fillStyle = cssVar('--ink')
      ctx.fillRect(x(t) - 1, 0, 2, h - 12)
    }
  }, [data, t])

  useEffect(() => {
    draw()
    window.addEventListener('resize', draw)
    return () => window.removeEventListener('resize', draw)
  }, [draw])

  const seekFrom = (clientX: number, target: HTMLCanvasElement) => {
    if (!data) return
    const r = target.getBoundingClientRect()
    const ratio = Math.min(1, Math.max(0, (clientX - r.left) / r.width))
    onSeek(data.tMin + ratio * (data.tMax - data.tMin))
  }

  return (
    <div className="timeline">
      <canvas
        ref={ref}
        aria-label="Шкала времени: число машин с высоким риском"
        onPointerDown={(e) => {
          dragging.current = true
          e.currentTarget.setPointerCapture(e.pointerId)
          seekFrom(e.clientX, e.currentTarget)
        }}
        onPointerMove={(e) => dragging.current && seekFrom(e.clientX, e.currentTarget)}
        onPointerUp={() => (dragging.current = false)}
      />
    </div>
  )
}
