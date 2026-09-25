import type { Alert, DayInfo, Frame, Kpi, LiveSnapshot, ModelQuality, RiskLevel, Timeline, TripCard } from './types'

// Entirely invented routes, stops, vehicles and predictions. No dataset or backend is used.
// Familiar Moscow labels are illustrative: they do not describe real routes or stop coordinates.
const demoLabels = [
  ['Тверская', 'Пушкинская площадь', 'Маяковская', 'Белорусский вокзал', 'Новослободская', 'Садовая-Триумфальная', 'Страстной бульвар', 'Чеховская'],
  ['Арбатские ворота', 'Новый Арбат', 'Смоленская', 'Плющиха', 'Зубовская площадь', 'Парк культуры', 'Пречистенка', 'Гоголевский бульвар'],
  ['Павелецкая', 'Новокузнецкая', 'Большая Ордынка', 'Полянка', 'Добрынинская', 'Серпуховская', 'Дубининская', 'Зацепская площадь'],
  ['Таганская', 'Марксистская', 'Рогожский Вал', 'Площадь Ильича', 'Николоямская', 'Яузские Ворота', 'Солянка', 'Китай-город'],
  ['Проспект Мира', 'Сухаревская', 'Сретенский бульвар', 'Тургеневская', 'Чистые пруды', 'Красные Ворота', 'Комсомольская', 'Каланчёвская'],
  ['Покровские Ворота', 'Чистопрудный бульвар', 'Сретенка', 'Трубная площадь', 'Цветной бульвар', 'Самотёчная площадь', 'Достоевская', 'Олимпийский проспект'],
]
const routes = Array.from({ length: 6 }, (_, r) => ({
  route: ['17', '24', '38', '64', '7', '12'][r],
  mode: r < 4 ? 'bus' : 'tram',
  name: `${demoLabels[r][0]} — ${demoLabels[r][3]}`,
  stops: Array.from({ length: 8 }, (_, s): [number, number] => {
    const angle = (s / 8) * Math.PI * 2
    return [37.617 + (r % 3 - 1) * 0.05 + Math.cos(angle) * 0.035,
      55.753 + (Math.floor(r / 3) - 0.5) * 0.055 + Math.sin(angle) * 0.022]
  }),
}))

const day: DayInfo = {
  date: '2026-09-25', dow: 5, rain: { level: 0, start: 0, end: 0 }, threshold: 5,
  tMin: 360, tMax: 1380, horizonLabel: '12 минут', riskLevels: { mid: 40, high: 70 },
  modes: [{ id: 0, key: 'bus' }, { id: 1, key: 'tram' }], trips: 24,
  network: {
    stops: routes.flatMap((r) => r.stops),
    segments: routes.flatMap((_, r) => Array.from({ length: 8 }, (_, s): [number, number] =>
      [r * 8 + s, r * 8 + (s + 1) % 8])),
  },
}

const clock = (t: number) => `${String(Math.floor(t / 60) % 24).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}`
const stopName = (r: number, s: number) => demoLabels[r][s]

function vehicle(i: number, t: number) {
  const r = Math.floor(i / 4)
  const route = routes[r]
  const progress = ((t - day.tMin) / (32 + r * 3) + (i % 4) / 4) * 8
  const s = Math.floor(progress) % 8
  const f = progress - Math.floor(progress)
  const a = route.stops[s]
  const b = route.stops[(s + 1) % 8]
  const risk = Math.round(8 + (Math.sin(t / 13 + i * 1.71) + 1) * 43)
  const level: RiskLevel = i === 23 ? 3 : risk >= 70 ? 2 : risk >= 40 ? 1 : 0
  const delay = Math.round((Math.sin(t / 21 + i * 0.7) * 3.8 + (i % 5 === 0 ? 4 : 0.4)) * 10) / 10
  return { id: 1001 + i, r, route, s, level, risk, delay,
    lon: a[0] + (b[0] - a[0]) * f, lat: a[1] + (b[1] - a[1]) * f }
}

function forecastDelay(v: ReturnType<typeof vehicle>) {
  return Math.round(Math.max(v.level === 2 ? 5.5 : -5, v.delay + v.risk / 12) * 10) / 10
}

const problemSegments = [2, 12, 18, 27, 36, 43]
function context(v: ReturnType<typeof vehicle>, t: number) {
  if (v.level === 3) return {}
  const index = problemSegments[v.r]
  return {
    forecastReason: v.r % 2 ? 'Увеличение времени на остановках' : 'Снижение скорости на участке',
    problemSegment: { index, from: stopName(v.r, index % 8), to: stopName(v.r, (index + 1) % 8) },
    forecastTime: clock(t + 12),
    averageSpeed: Math.round((28 - v.risk / 5) * 10) / 10,
    dwellMinutes: Math.round(v.risk / 5) / 10,
  }
}

export const demoDirectory = Array.from({ length: 24 }, (_, i) => ({
  tripId: 1001 + i, route: routes[Math.floor(i / 4)].route, mode: routes[Math.floor(i / 4)].mode,
}))

function trip(v: ReturnType<typeof vehicle>, t: number): TripCard {
  return {
    ...context(v, t),
    tripId: v.id, found: true, onLine: true, route: v.route.route, routeName: v.route.name,
    mode: v.route.mode, stop: stopName(v.r, v.s), delay: v.delay,
    risk: v.level === 3 ? null : v.risk, level: v.level,
    ...(v.level !== 3 ? { forecastMinutes: 12, forecastDelay: forecastDelay(v) } : {}),
    next: [1, 2, 3].map((n) => ({ stop: stopName(v.r, (v.s + n) % 8), plan: clock(t + n * 4) })),
  }
}

function frame(p: { t: number; mode?: string; minLevel?: number; trip?: number | null }): Frame {
  const all = Array.from({ length: 24 }, (_, i) => vehicle(i, p.t))
  const filtered = all.filter((v) => !p.mode || p.mode === 'all' || v.route.mode === p.mode)
  const visible = filtered.filter((v) => !p.minLevel || (v.level !== 3 && v.level >= p.minLevel))
  const alerts: Alert[] = filtered.filter((v) => v.level === 2 && v.delay < day.threshold)
    .sort((a, b) => b.risk - a.risk).map((v) => ({
      ...context(v, p.t),
      tripId: v.id, route: v.route.route, mode: v.route.mode,
      dest: stopName(v.r, (v.s + 3) % 8), stop: stopName(v.r, v.s), delay: v.delay, risk: v.risk,
      forecastMinutes: 12, forecastDelay: forecastDelay(v),
    }))
  const kpi: Kpi[] = [
    { key: 'onLine', label: 'на линии', value: String(filtered.length) },
    { key: 'high', label: 'высокий риск', value: String(filtered.filter((v) => v.level === 2).length), tone: 'high' },
    { key: 'late', label: 'уже опаздывают', value: String(filtered.filter((v) => v.delay >= day.threshold).length) },
    { key: 'hit', label: 'ранних тревог сбылось', value: '78%', hint: 'Синтетический показатель для демонстрации' },
  ]
  const selected = all.find((v) => v.id === p.trip)
  return { t: p.t, clock: clock(p.t), raining: false, kpi, alerts,
    vehicles: {
      id: visible.map((v) => v.id), lon: visible.map((v) => v.lon), lat: visible.map((v) => v.lat),
      risk: visible.map((v) => v.risk), level: visible.map((v) => v.level), late: visible.map((v) => Number(v.delay >= day.threshold)),
      route: visible.map((v) => v.route.route), mode: visible.map((v) => v.route.mode),
    },
    slowSegments: [[2, 1, 4.8], [12, 0, 2.1], [18, 1, 3.6], [27, 1, 5.2], [36, 0, 2.7], [43, 1, 4.1]],
    trip: selected ? trip(selected, p.t) : null,
  }
}

function timeline(mode?: string): Timeline {
  return { tMin: day.tMin, tMax: day.tMax, rain: null,
    ticks: Array.from({ length: 18 }, (_, i) => ({ t: day.tMin + i * 60, label: clock(day.tMin + i * 60) })),
    bins: Array.from({ length: 103 }, (_, i) => {
      const t = day.tMin + i * 10
      return { t, high: Number(frame({ t, mode }).kpi[1].value) }
    }),
  }
}

const model: ModelQuality = {
  horizon: '12 минут', threshold: 5, recall: 84, precision: 78, baselinePrecision: 46,
  prAuc: 0.86, baselinePrAuc: 0.52, testSize: null,
  features: [
    { key: 'segment', label: 'Замедление на участке', importance: 42, share: 0.42 },
    { key: 'delay', label: 'Текущее отклонение', importance: 34, share: 0.34 },
    { key: 'hour', label: 'Время суток', importance: 24, share: 0.24 },
  ],
}

const started = Date.now()
function live(): LiveSnapshot {
  const t = 450 + (((Date.now() - started) / 1000) * (10 / 60)) % 930
  const current = frame({ t })
  return { clock: current.clock, tracked: 24, kpi: current.kpi, alerts: current.alerts,
    trips: Object.fromEntries(Array.from({ length: 24 }, (_, i) => {
      const v = vehicle(i, t)
      return [v.id, trip(v, t)]
    })),
  }
}

async function respond<T>(get: () => T, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted()
  return get()
}

export const demoApi = {
  day: (signal?: AbortSignal) => respond(() => day, signal),
  frame: (p: Parameters<typeof frame>[0], signal?: AbortSignal) => respond(() => frame(p), signal),
  timeline: (mode?: string, signal?: AbortSignal) => respond(() => timeline(mode), signal),
  model: (signal?: AbortSignal) => respond(() => model, signal),
  live: (signal?: AbortSignal) => respond(live, signal),
}
