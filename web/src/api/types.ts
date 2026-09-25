/**
 * Контракт API (app/api.py). Фронтенд не выводит эти данные сам и не хранит их копии —
 * он показывает то, что посчитал сервис.
 */

/** 0 низкий · 1 средний · 2 высокий · 3 прогноз не выдается (рейс скоро завершится) */
export type RiskLevel = 0 | 1 | 2 | 3

export interface Kpi {
  key: string
  label: string
  value: string
  tone?: 'high'
  hint?: string
}

/** Optional presentation context; currently supplied by the synthetic source only. */
export interface ForecastContext {
  currentTime?: string
  forecastReason?: string
  problemSegment?: { from: string; to: string; index: number }
  forecastTime?: string
  forecastStop?: string
  scheduledArrival?: string
  expectedArrival?: string
  expectedDelay?: number
  averageSpeed?: number
  dwellMinutes?: number
}

export interface Alert extends ForecastContext {
  tripId: number
  route: string
  mode: string
  dest: string
  stop: string
  /** Signed minutes: negative = ahead of schedule, positive = late. */
  delay: number
  risk: number
  forecastMinutes?: number
  forecastDelay?: number
}

export interface TripCard extends ForecastContext {
  found: boolean
  onLine: boolean
  route: string
  routeName: string
  mode: string
  stop?: string
  delay?: number
  risk?: number | null
  level?: RiskLevel
  outcome?: { late: boolean; delay: number } | null
  next?: { stop: string; plan: string }[]
  tripId?: number
  forecastMinutes?: number
  forecastDelay?: number
}

export interface DayInfo {
  date: string
  dow: number
  rain: { level: number; start: number; end: number }
  threshold: number
  tMin: number
  tMax: number
  horizonLabel: string
  riskLevels: { mid: number; high: number }
  modes: { id: number; key: string }[]
  trips: number
  network: {
    /** [долгота, широта] по индексу остановки */
    stops: [number, number][]
    /** [индекс остановки A, индекс остановки B] */
    segments: [number, number][]
  }
}

/** Машины приходят колонками, а не объектами: так кадр в разы компактнее. */
export interface Vehicles {
  id: number[]
  lon: number[]
  lat: number[]
  level: RiskLevel[]
  risk: number[]
  late: number[]
  route?: string[]
  mode?: string[]
}

/** [индекс перегона, ступень (0 медленно · 1 сильно), среднее превышение в минутах] */
export type SlowSegment = [number, 0 | 1, number]

export interface Frame {
  t: number
  clock: string
  raining: boolean
  kpi: Kpi[]
  vehicles: Vehicles
  slowSegments: SlowSegment[]
  alerts: Alert[]
  trip: TripCard | null
}

export interface Timeline {
  tMin: number
  tMax: number
  bins: { t: number; high: number }[]
  ticks: { t: number; label: string }[]
  rain: { level: number; start: number; end: number } | null
}

export interface LiveSnapshot {
  clock: string
  tracked: number
  kpi: Kpi[]
  alerts: Alert[]
  /** Live stream adapter input; this must never be populated from replay responses. */
  vehicles?: LiveVehicle[]
  trips?: Record<number, TripCard>
}

export interface LiveVehicle {
  vehicleId: string | number
  tripId?: string | number
  route?: string
  mode?: string
  lat: number
  lon: number
  speed?: number
  risk?: number | null
  level?: RiskLevel | null
  delay?: number | null
  updatedAt?: string | number
}

export interface ModelQuality {
  horizon: string
  threshold: number
  recall: number
  precision: number
  baselinePrecision: number
  prAuc: number
  baselinePrAuc: number
  testSize: number | null
  features: { key: string; label: string; importance: number; share: number }[]
}

/** 503 от API: чего не хватает и что запустить. */
export interface ApiProblem {
  what: string
  error: string | null
  hint: string
}
