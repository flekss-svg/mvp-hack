/** Общие ответы API для тестов — одна копия вместо трех разных. */
import type { Alert, DayInfo, Frame, ModelQuality, Timeline, TripCard } from '../api/types'

export const day: DayInfo = {
  date: '2026-09-03',
  dow: 3,
  rain: { level: 0, start: 0, end: 0 },
  threshold: 3,
  tMin: 400,
  tMax: 600,
  horizonLabel: '10–15 мин',
  riskLevels: { mid: 0.3, high: 0.6 },
  modes: [{ id: 0, key: 'bus' }],
  trips: 1,
  network: { stops: [[37.6, 55.75], [37.62, 55.75]], segments: [[0, 1]] },
}

export const alert: Alert = {
  tripId: 1,
  route: '42',
  mode: 'bus',
  dest: 'Конечная',
  stop: 'Начальная',
  delay: 1,
  risk: 80,
}

export const trip: TripCard = {
  found: true,
  onLine: true,
  route: '42',
  routeName: 'Тестовый маршрут',
  mode: 'bus',
  stop: 'Начальная',
  delay: 1,
  risk: 80,
  level: 2,
  outcome: null,
  next: [],
}

export const frame: Frame = {
  t: 450,
  clock: '07:30',
  raining: false,
  kpi: [{ key: 'onLine', label: 'на линии', value: '1' }],
  vehicles: { id: [7], lon: [37.61], lat: [55.75], level: [2], risk: [80], late: [1] },
  slowSegments: [[0, 1, 3]],
  alerts: [],
  trip: null,
}

export const timeline: Timeline = {
  tMin: 400,
  tMax: 600,
  bins: [{ t: 400, high: 2 }, { t: 500, high: 4 }],
  ticks: [{ t: 400, label: '06:40' }, { t: 500, label: '08:20' }],
  rain: { level: 1, start: 450, end: 480 },
}

export const model: ModelQuality = {
  horizon: '10–15 мин',
  threshold: 3,
  recall: 70,
  precision: 83,
  baselinePrecision: 56,
  prAuc: 0.87,
  baselinePrAuc: 0.66,
  testSize: 100,
  features: [{ key: 'delay_now', label: 'Текущее опоздание', importance: 33.7, share: 1 }],
}

export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
