import { useCallback, useEffect, useRef, useState } from 'react'
import type { Timeline as TimelineData } from '../api/types'

interface Props {
  data: TimelineData | null
  t: number | null
  onSeek: (t: number) => void
  highColor?: string
}

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/** Сколько машин с высоким риском в каждый момент дня. Счет ведет сервер, здесь — отрисовка. */
export function Timeline({ data, t, onSeek, highColor }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const [hover, setHover] = useState<number | null>(null)
  const bin = data && hover !== null ? data.bins.reduce<(typeof data.bins)[number] | null>((best, b) => !best || Math.abs(b.t - hover) < Math.abs(best.t - hover) ? b : best, null) : null

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

    ctx.fillStyle = highColor ?? cssVar('--high')
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
    ctx.font = '11px system-ui, sans-serif'
    const every = w < 600 ? 4 : 2
    let lastRight = -8
    data.ticks.forEach((tick, i) => {
      if (i % every) return
      const label = ctx.measureText(tick.label).width
      const left = Math.min(Math.max(x(tick.t) - label / 2, 0), w - label)
      if (left < lastRight + 8) return
      ctx.fillText(tick.label, left, h - 1)
      lastRight = left + label
    })

    if (t !== null) {
      ctx.fillStyle = cssVar('--ink')
      ctx.fillRect(x(t) - 1, 0, 2, h - 12)
    }
  }, [data, t, highColor])

  useEffect(() => {
    draw()
    const observer = new ResizeObserver(draw)
    if (ref.current) observer.observe(ref.current)
    return () => observer.disconnect()
  }, [draw])

  return (
    <div className="timeline">
      <canvas ref={ref} aria-hidden="true" />
      <input type="range" aria-label="Время записанного дня" min={data?.tMin ?? 0} max={data?.tMax ?? 1}
        step={0.25} value={t ?? data?.tMin ?? 0} disabled={!data}
        aria-valuetext={t === null ? 'Нет данных' : `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`}
        onPointerMove={(e) => { if (data) { const r = e.currentTarget.getBoundingClientRect(); setHover(data.tMin + Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (data.tMax - data.tMin)) } }}
        onPointerLeave={() => setHover(null)} onBlur={() => setHover(null)} onFocus={() => setHover(t)}
        onChange={(e) => { const next = Number(e.target.value); setHover(next); onSeek(next) }} />
      {bin && data && <div className="timeline-tooltip" role="tooltip" style={{ left: `${Math.min(90, Math.max(10, (bin.t - data.tMin) / (data.tMax - data.tMin || 1) * 100))}%` }}><b>{String(Math.floor(bin.t / 60)).padStart(2, '0')}:{String(Math.floor(bin.t % 60)).padStart(2, '0')}</b><span>{bin.high} ТС высокого риска</span></div>}
    </div>
  )
}
