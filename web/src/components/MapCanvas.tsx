import { useCallback, useEffect, useRef } from 'react'
import type { DayInfo, Frame } from '../api/types'
import { DEFAULT_DISPLAY } from '../ui/display'
import type { DisplaySettings } from '../ui/display'

interface Props {
  day: DayInfo
  frame: Frame | null
  selected: number | null
  onSelect: (tripId: number | null) => void
  focusToken?: number
  focusReady?: boolean
  display?: DisplaySettings
}

const RISK_LABEL = ['Низкий риск', 'Средний риск', 'Высокий риск', 'Нет прогноза']
/** Снизу вверх: серые и спокойные под низом, тревожные — поверх всех. */
const DRAW_ORDER = [3, 0, 1, 2]

const cssVar = (name: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim()

/**
 * Карта сети и машин. Рисует то, что пришло в кадре: координаты, уровни риска и медленные
 * перегоны считает сервер, здесь остаются только проекция, панорама и зум.
 */
export function MapCanvas({ day, frame, selected, onSelect, focusToken = 0, focusReady = true, display = DEFAULT_DISPLAY }: Props) {
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
    ctx.strokeStyle = display.colors.network
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
    for (const [seg, severity] of display.problemSegments ? f.slowSegments : []) {
      const pair = day.network.segments[seg]
      if (!pair) continue
      const p = project(stops[pair[0]][0], stops[pair[0]][1], w, h)
      const q = project(stops[pair[1]][0], stops[pair[1]][1], w, h)
      ctx.strokeStyle = severity ? display.colors.critical : display.colors.warning
      ctx.lineWidth = severity ? 5 : 3.5
      ctx.beginPath()
      ctx.moveTo(p[0], p[1])
      ctx.lineTo(q[0], q[1])
      if (f.trip?.tripId === selected && f.trip.problemSegment?.index === seg) {
        ctx.strokeStyle = display.colors.selected
        ctx.lineWidth = 9
        ctx.stroke()
        ctx.strokeStyle = severity ? display.colors.critical : display.colors.warning
        ctx.lineWidth = severity ? 5 : 3.5
      }
      ctx.stroke()
    }

    // машины
    const v = f.vehicles
    const r = Math.max(5, Math.min(8, view.current.k / 900))
    const ink = cssVar('--ink')
    const colors = [display.colors.low, display.colors.mid, display.colors.high, '#7c8a95']
    for (const level of DRAW_ORDER) {
      ctx.fillStyle = colors[level]
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
        } else if (level === 1) {
          ctx.moveTo(x, y - r - 3)
          ctx.lineTo(x + r + 2, y + r)
          ctx.lineTo(x - r - 2, y + r)
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
          ctx.fillStyle = colors[level]
        }
      }
    }

    // Place labels after markers, giving selected/high-risk vehicles first choice.
    // A small occupancy grid avoids overlapping labels without a quadratic scan.
    if (display.routeNumbers || display.vehicleLabels) {
      type Box = { x: number; y: number; width: number; height: number }
      const occupied = new Set<string>()
      const cells = (b: Box) => {
        const keys: string[] = []
        for (let x = Math.floor(b.x / 16); x <= Math.floor((b.x + b.width) / 16); x++)
          for (let y = Math.floor(b.y / 16); y <= Math.floor((b.y + b.height) / 16); y++) keys.push(`${x}:${y}`)
        return keys
      }
      const reserve = (b: Box) => cells(b).forEach((key) => occupied.add(key))
      reserve({ x: 0, y: h - 115, width: 330, height: 115 })
      reserve({ x: 0, y: 0, width: 210, height: 80 })
      reserve({ x: w - 280, y: 0, width: 280, height: 120 })
      const points = v.id.map((id, i) => ({ id, i, point: project(v.lon[i], v.lat[i], w, h) }))
        .filter(({ point: [x, y] }) => x > 0 && y > 0 && x < w && y < h)
      for (const { point: [x, y] } of points) reserve({ x: x - r - 3, y: y - r - 3, width: r * 2 + 6, height: r * 2 + 6 })
      const priority = (i: number) => v.id[i] === selected ? 10 : v.level[i] === 3 ? -1 : v.level[i]
      points.sort((a, b) => priority(b.i) - priority(a.i))
      ctx.font = '600 11px system-ui'
      ctx.textAlign = 'center'
      for (const { i, point: [x, y] } of points) {
        const label = [display.routeNumbers ? v.route?.[i] : null, display.vehicleLabels ? `ТС ${v.id[i]}` : null].filter(Boolean).join(' · ')
        if (!label) continue
        const width = ctx.measureText(label).width + 10
        const candidates = [
          { x: x - width / 2, y: y + r + 13, width, height: 17 },
          { x: x - width / 2, y: y - r - 30, width, height: 17 },
          { x: x + r + 14, y: y - 8, width, height: 17 },
          { x: x - r - width - 14, y: y - 8, width, height: 17 },
        ]
        const box = candidates.find((b) => b.x > 3 && b.y > 3 && b.x + b.width < w - 3 && b.y + b.height < h - 3 && !cells(b).some((key) => occupied.has(key)))
        if (!box) continue
        reserve(box)
        ctx.fillStyle = '#ffffffed'
        ctx.fillRect(box.x, box.y, width, 17)
        ctx.fillStyle = ink
        ctx.fillText(label, box.x + width / 2, box.y + 12)
      }
    }

    const sel = v.id.indexOf(selected ?? -1)
    if (sel >= 0) {
      const [x, y] = project(v.lon[sel], v.lat[sel], w, h)
      ctx.strokeStyle = display.colors.selected
      ctx.lineWidth = 2.5
      ctx.beginPath()
      ctx.arc(x, y, r + 6, 0, Math.PI * 2)
      ctx.stroke()
    }
  }, [day, fit, project, selected, stops, display])

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
        {frame?.vehicles.id.map((id, i) => <button key={id} onClick={() => onSelect(id)} aria-pressed={id === selected}>ТС {id}, маршрут {frame.vehicles.route?.[i] ?? 'не передан'}, {RISK_LABEL[frame.vehicles.level[i]]}{frame.vehicles.level[i] === 3 ? '' : ` ${Math.round(frame.vehicles.risk[i])}%`}</button>)}
      </div>
      <div className="map-zoom">
        <button onClick={() => zoomAt(1.4, (ref.current?.clientWidth ?? 0) / 2, (ref.current?.clientHeight ?? 0) / 2)} aria-label="Приблизить">+</button>
        <button onClick={() => zoomAt(1 / 1.4, (ref.current?.clientWidth ?? 0) / 2, (ref.current?.clientHeight ?? 0) / 2)} aria-label="Отдалить">−</button>
        <button onClick={() => { autoFit.current = true; fit(); draw() }} aria-label="Показать всё">⤢</button>
      </div>
    </div>
  )
}
