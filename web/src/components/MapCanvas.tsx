import { useCallback, useEffect, useRef } from 'react'
import type { DayInfo, Frame } from '../api/types'

interface Props {
  day: DayInfo
  frame: Frame | null
  selected: number | null
  onSelect: (tripId: number | null) => void
  focusToken?: number
  focusReady?: boolean
}

const LEVEL_VAR = ['--low', '--mid', '--high', '--muted']
/** Снизу вверх: серые и спокойные под низом, тревожные — поверх всех. */
const DRAW_ORDER = [3, 0, 1, 2]

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/**
 * Карта сети и машин. Рисует то, что пришло в кадре: координаты, уровни риска и медленные
 * перегоны считает сервер, здесь остаются только проекция, панорама и зум.
 */
export function MapCanvas({ day, frame, selected, onSelect, focusToken = 0, focusReady = true }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const view = useRef({ cx: 0, cy: 0, k: 1, ready: false })
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null)
  const latest = useRef(frame)
  latest.current = frame
  const focused = useRef('')
  const autoFit = useRef(true)

  const stops = day.network.stops
  // Меркатор на таком масштабе не нужен — достаточно сжать долготу по широте города.
  const kx = useRef(Math.cos(((stops[0]?.[1] ?? 55.75) * Math.PI) / 180))

  const project = useCallback(
    (lon: number, lat: number, w: number, h: number) => {
      const v = view.current
      return [(lon * kx.current - v.cx) * v.k + w / 2, (-lat - v.cy) * v.k + h / 2] as const
    },
    [],
  )

  const fit = useCallback(() => {
    const cv = ref.current
    if (!cv || !stops.length) return
    const xs = stops.map((s) => s[0] * kx.current)
    const ys = stops.map((s) => -s[1])
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)]
    view.current = {
      cx: (x0 + x1) / 2,
      cy: (y0 + y1) / 2,
      k: 0.9 * Math.min(cv.clientWidth / (x1 - x0 || 1), cv.clientHeight / (y1 - y0 || 1)),
      ready: true,
    }
  }, [stops])

  const draw = useCallback(() => {
    const cv = ref.current
    const ctx = cv?.getContext('2d')
    if (!cv || !ctx) return
    if (!view.current.ready) fit()

    const dpr = window.devicePixelRatio || 1
    const w = cv.clientWidth
    const h = cv.clientHeight
    if (cv.width !== w * dpr || cv.height !== h * dpr) {
      cv.width = w * dpr
      cv.height = h * dpr
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    // сеть маршрутов
    ctx.strokeStyle = cssVar('--net')
    ctx.lineWidth = 3
    ctx.beginPath()
    for (const [a, b] of day.network.segments) {
      const p = project(stops[a][0], stops[a][1], w, h)
      const q = project(stops[b][0], stops[b][1], w, h)
      ctx.moveTo(p[0], p[1])
      ctx.lineTo(q[0], q[1])
    }
    ctx.stroke()

    const f = latest.current
    if (!f) return

    // перегоны, которые машины сейчас проходят медленнее плана
    ctx.lineCap = 'round'
    for (const [seg, severity] of f.slowSegments) {
      const pair = day.network.segments[seg]
      if (!pair) continue
      const p = project(stops[pair[0]][0], stops[pair[0]][1], w, h)
      const q = project(stops[pair[1]][0], stops[pair[1]][1], w, h)
      ctx.strokeStyle = cssVar(severity ? '--slow-strong' : '--slow')
      ctx.lineWidth = severity ? 5 : 3.5
      ctx.beginPath()
      ctx.moveTo(p[0], p[1])
      ctx.lineTo(q[0], q[1])
      ctx.stroke()
    }

    // машины
    const v = f.vehicles
    const r = Math.max(5, Math.min(8, view.current.k / 900))
    const ink = cssVar('--ink')
    for (const level of DRAW_ORDER) {
      ctx.fillStyle = cssVar(LEVEL_VAR[level])
      for (let i = 0; i < v.id.length; i++) {
        if (v.level[i] !== level) continue
        const [x, y] = project(v.lon[i], v.lat[i], w, h)
        if (x < -10 || y < -10 || x > w + 10 || y > h + 10) continue
        ctx.beginPath()
        if (level === 2) {
          ctx.moveTo(x, y - r - 3)
          ctx.lineTo(x + r + 3, y)
          ctx.lineTo(x, y + r + 3)
          ctx.lineTo(x - r - 3, y)
          ctx.closePath()
        } else if (level === 3) ctx.rect(x - r, y - r, r * 2, r * 2)
        else ctx.arc(x, y, r, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = '#fff'
        ctx.lineWidth = 2
        ctx.stroke()
        if (v.late[i]) {
          ctx.strokeStyle = ink
          ctx.lineWidth = 1.5
          ctx.stroke()
        }
        if (level === 2) {
          ctx.fillStyle = '#fff'
          ctx.font = 'bold 10px system-ui'
          ctx.textAlign = 'center'
          ctx.fillText('!', x, y + 3)
          ctx.fillStyle = cssVar(LEVEL_VAR[level])
        }
        if (v.route?.[i] || selected === v.id[i]) {
          const label = `${v.route?.[i] ?? v.id[i]}`
          ctx.font = '600 11px system-ui'
          ctx.textAlign = 'center'
          const width = ctx.measureText(label).width + 10
          ctx.fillStyle = '#fff'
          ctx.fillRect(x - width / 2, y + r + 5, width, 17)
          ctx.fillStyle = ink
          ctx.fillText(label, x, y + r + 17)
          ctx.fillStyle = cssVar(LEVEL_VAR[level])
        }
      }
    }

    const sel = v.id.indexOf(selected ?? -1)
    if (sel >= 0) {
      const [x, y] = project(v.lon[sel], v.lat[sel], w, h)
      ctx.strokeStyle = cssVar('--sel')
      ctx.lineWidth = 2.5
      ctx.beginPath()
      ctx.arc(x, y, r + 6, 0, Math.PI * 2)
      ctx.stroke()
    }
  }, [day, fit, project, selected, stops])

  useEffect(() => {
    const target = `${selected}:${focusToken}`
    const v = frame?.vehicles
    const idx = v?.id.indexOf(selected ?? -1) ?? -1
    if (focusReady && v && idx >= 0 && focused.current !== target) {
      if (!view.current.ready) fit()
      focused.current = target
      autoFit.current = false
      view.current.cx = v.lon[idx] * kx.current
      view.current.cy = -v.lat[idx]
      view.current.k = Math.max(view.current.k, 9000)
    }
    if (selected === null) focused.current = ''
    draw()
  }, [draw, frame, selected, focusToken, focusReady, fit])

  useEffect(() => {
    const onResize = () => { if (autoFit.current) fit(); draw() }
    const observer = new ResizeObserver(onResize)
    if (ref.current) observer.observe(ref.current)
    return () => observer.disconnect()
  }, [draw, fit])

  const zoomAt = (factor: number, x: number, y: number) => {
    const cv = ref.current
    if (!cv) return
    const w = cv.clientWidth
    const h = cv.clientHeight
    const v = view.current
    autoFit.current = false
    const wx = v.cx + (x - w / 2) / v.k
    const wy = v.cy + (y - h / 2) / v.k
    v.k *= factor
    v.cx = wx - (x - w / 2) / v.k
    v.cy = wy - (y - h / 2) / v.k
    draw()
  }

  const pick = (x: number, y: number) => {
    const cv = ref.current
    const f = latest.current
    if (!cv || !f) return
    const w = cv.clientWidth
    const h = cv.clientHeight
    let best: number | null = null
    let bestDist = 144
    for (let i = 0; i < f.vehicles.id.length; i++) {
      const [px, py] = project(f.vehicles.lon[i], f.vehicles.lat[i], w, h)
      const d = (px - x) ** 2 + (py - y) ** 2
      if (d < bestDist) {
        bestDist = d
        best = f.vehicles.id[i]
      }
    }
    onSelect(best)
  }

  return (
    <div className="map">
      <canvas
        ref={ref}
        aria-label="Карта маршрутов и машин"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          drag.current = { x: e.clientX, y: e.clientY, cx: view.current.cx, cy: view.current.cy, moved: false }
        }}
        onPointerMove={(e) => {
          const d = drag.current
          if (!d) return
          const dx = e.clientX - d.x
          const dy = e.clientY - d.y
          if (Math.abs(dx) + Math.abs(dy) > 3) { d.moved = true; autoFit.current = false }
          view.current.cx = d.cx - dx / view.current.k
          view.current.cy = d.cy - dy / view.current.k
          draw()
        }}
        onPointerUp={(e) => {
          const d = drag.current
          drag.current = null
          if (!d || d.moved) return
          const r = e.currentTarget.getBoundingClientRect()
          pick(e.clientX - r.left, e.clientY - r.top)
        }}
        onPointerCancel={() => { drag.current = null }}
        onWheel={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          zoomAt(e.deltaY < 0 ? 1.2 : 1 / 1.2, e.clientX - r.left, e.clientY - r.top)
        }}
      />
      <div className="sr-only vehicle-options" aria-label="Транспорт на схеме">
        {frame?.vehicles.id.map((id, i) => <button key={id} onClick={() => onSelect(id)}>ТС {id}, риск {frame.vehicles.level[i] === 3 ? 'не определён' : `${frame.vehicles.risk[i]}%`}</button>)}
      </div>
      <div className="map-zoom">
        <button onClick={() => zoomAt(1.4, (ref.current?.clientWidth ?? 0) / 2, (ref.current?.clientHeight ?? 0) / 2)} aria-label="Приблизить">+</button>
        <button onClick={() => zoomAt(1 / 1.4, (ref.current?.clientWidth ?? 0) / 2, (ref.current?.clientHeight ?? 0) / 2)} aria-label="Отдалить">−</button>
        <button onClick={() => { autoFit.current = true; fit(); draw() }} aria-label="Показать всё">⤢</button>
      </div>
    </div>
  )
}
