import type { Alert, DayInfo, Kpi, Timeline, TripCard } from '../api/types'
import type { MapVehicle } from '../maps/vehicles'

/** Development-only panel fixtures. They are intentionally never passed to the map. */
export const UI_PREVIEW_ALERTS: Alert[] = [
  { tripId: 1011, route: '38', mode: 'bus', dest: 'Полянка', stop: 'Павелецкая', delay: 2, risk: 92, currentTime: '08:00', forecastMinutes: 12, forecastDelay: 10, forecastStop: 'Полянка', scheduledArrival: '08:12', expectedArrival: '08:22', expectedDelay: 10, forecastReason: 'Снижение скорости на участке', problemSegment: { from: 'Большая Ордынка', to: 'Полянка', index: 0 }, averageSpeed: 24 },
  { tripId: 2048, route: '91', mode: 'bus', dest: 'Метро «Сокол»', stop: 'Белорусская', delay: 1.4, risk: 81, currentTime: '08:03', forecastMinutes: 9, forecastDelay: 7, forecastStop: 'Тверская Застава', scheduledArrival: '08:17', expectedArrival: '08:24', expectedDelay: 7, forecastReason: 'Увеличение времени посадки', problemSegment: { from: '1-я Тверская-Ямская', to: 'Тверская Застава', index: 1 }, averageSpeed: 18 },
  { tripId: 306, route: '3', mode: 'tram', dest: 'Метро «Чистые пруды»', stop: 'Павелецкий вокзал', delay: 0.8, risk: 68, currentTime: '08:05', forecastMinutes: 14, forecastDelay: 5, forecastStop: 'Зацепская площадь', scheduledArrival: '08:20', expectedArrival: '08:25', expectedDelay: 5, forecastReason: 'Замедление в смешанном потоке', problemSegment: { from: 'Новокузнецкая', to: 'Зацепская площадь', index: 2 }, averageSpeed: 15 },
]

export const UI_PREVIEW_KPI: Kpi[] = [
  { key: 'onLine', label: 'на линии', value: '24' },
  { key: 'high', label: 'высокий риск', value: '5', tone: 'high' },
  { key: 'late', label: 'уже опаздывают', value: '2' },
  { key: 'hit', label: 'ранних предупреждений подтвердилось', value: '78%' },
]

export const UI_PREVIEW_SNAPSHOT = { clock: '08:12', kpi: UI_PREVIEW_KPI, alerts: UI_PREVIEW_ALERTS }

export const UI_PREVIEW_VEHICLES: MapVehicle[] = [
  { vehicleId: 1011, tripId: 1011, route: '38', mode: 'bus', lat: 55.7448, lon: 37.6351, level: 2, risk: 92, delay: 2 },
  { vehicleId: 2048, tripId: 2048, route: '91', mode: 'bus', lat: 55.7586, lon: 37.6078, level: 1, risk: 81, delay: 1.4 },
  { vehicleId: 306, tripId: 306, route: '3', mode: 'tram', lat: 55.7678, lon: 37.6364, level: 1, risk: 68, delay: .8 },
  { vehicleId: 409, tripId: 409, route: '24', mode: 'bus', lat: 55.7332, lon: 37.6035, level: 2, risk: 91, delay: 3.1 },
  { vehicleId: 512, tripId: 512, route: '70', mode: 'bus', lat: 55.7529, lon: 37.5754, level: 0, risk: 18, delay: 0 },
  { vehicleId: 618, tripId: 618, route: 'А', mode: 'tram', lat: 55.7807, lon: 37.6191, level: 0, risk: 26, delay: -.4 },
  { vehicleId: 724, tripId: 724, route: 'М3', mode: 'bus', lat: 55.7702, lon: 37.5858, level: 0, risk: 34, delay: .2 },
]

export const UI_PREVIEW_DAY: DayInfo = {
  date: '2026-09-25', dow: 5, rain: { level: 0, start: 0, end: 0 }, threshold: 65, tMin: 360, tMax: 1320, horizonLabel: '12 минут', riskLevels: { mid: 65, high: 90 }, modes: [], trips: 24,
  network: { stops: [[37.631, 55.7435], [37.638, 55.7472]], segments: [[0, 1]] },
}
export const UI_PREVIEW_SLOW_SEGMENTS: [number, 0 | 1, number][] = [[0, 1, 6]]
export const UI_PREVIEW_TIMELINE: Timeline = {
  tMin: 360, tMax: 1320,
  bins: [{ t: 360, high: 1 }, { t: 420, high: 2 }, { t: 480, high: 5 }, { t: 540, high: 4 }, { t: 600, high: 2 }, { t: 660, high: 1 }, { t: 720, high: 1 }, { t: 780, high: 2 }, { t: 840, high: 3 }, { t: 900, high: 2 }, { t: 960, high: 1 }, { t: 1020, high: 2 }, { t: 1080, high: 3 }, { t: 1140, high: 2 }, { t: 1200, high: 1 }, { t: 1260, high: 1 }],
  ticks: [{ t: 360, label: '06:00' }, { t: 480, label: '08:00' }, { t: 600, label: '10:00' }, { t: 720, label: '12:00' }, { t: 840, label: '14:00' }, { t: 960, label: '16:00' }, { t: 1080, label: '18:00' }, { t: 1200, label: '20:00' }, { t: 1320, label: '22:00' }], rain: null,
}

export const UI_PREVIEW_TRIPS: Record<number, TripCard> = Object.fromEntries(UI_PREVIEW_ALERTS.map((alert) => [alert.tripId, {
  ...alert,
  found: true,
  onLine: true,
  routeName: `${alert.stop} → ${alert.dest}`,
  level: alert.risk >= 90 ? 2 : alert.risk >= 65 ? 1 : 0,
  next: [{ stop: alert.tripId === 1011 ? 'Добрынинская' : alert.forecastStop ?? alert.dest, plan: alert.tripId === 1011 ? '08:06' : alert.scheduledArrival ?? '—' }],
}]))
