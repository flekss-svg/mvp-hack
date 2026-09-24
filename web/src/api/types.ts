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

export interface Alert {
  tripId: number
  route: string
  mode: string
  dest: string
  stop: string
  delay: number
  risk: number
}

export interface TripCard {
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
