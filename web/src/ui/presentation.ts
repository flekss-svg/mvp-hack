import type { Alert } from '../api/types'

export const amount = (v: number) => String(Number(Math.abs(v).toFixed(1)))
const known = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
// Display tolerance only (6 seconds); never changes lateness calculations or API values.
const onTime = (v: number) => Math.abs(v) < 0.1
export function currentText(delay?: number) {
  if (!known(delay)) return 'Отклонение не передано'
  if (onTime(delay)) return 'По графику'
  return delay < 0 ? `На ${amount(delay)} мин раньше графика` : `Опаздывает на ${amount(delay)} мин`
}
export function forecastText(current?: number, future?: number) {
  if (!known(future)) return 'Прогноз опоздания не передан'
  if (onTime(future)) return 'Ожидается движение по графику'
  if (future < 0) return `Ожидается прибытие на ${amount(future)} мин раньше графика`
  if (known(current) && current >= 0.1) {
    const difference = Number(future.toFixed(1)) - Number(current.toFixed(1))
    if (difference > 0) return `Опоздание вырастет до ${amount(future)} мин`
    if (difference < 0) return `Опоздание сократится до ${amount(future)} мин`
    return `Сохранится опоздание на ${amount(future)} мин`
  }
  return `Ожидается опоздание на ${amount(future)} мин`
}
export const horizonText = (minutes?: number) => known(minutes) ? `Через ${amount(minutes)} мин` : 'Горизонт не передан'
export const riskText = (risk?: number | null) => known(risk) ? `${Math.round(risk)}%` : 'Нет прогноза'
export const ageSeconds = (updatedAt: number | null, now: number) => updatedAt === null ? null : Math.max(0, Math.floor((now - updatedAt) / 1000))
export const updatedText = (updatedAt: number | null, now: number) => {
  const age = ageSeconds(updatedAt, now)
  return age === null ? 'Ожидание данных' : age === 0 ? 'Обновлено только что' : `Обновлено ${age} сек назад`
}
export interface StableIncident extends Alert { critical: boolean }
/** Hysteresis prevents 1–2% changes near 90% from moving a card between groups. */
export function stableIncidents(previous: StableIncident[], incoming: Alert[]): StableIncident[] {
  const old = new Map(previous.map((item, index) => [item.tripId, { item, index }]))
  const initial = [...incoming].sort((a, b) => b.risk - a.risk)
  return initial.map((a) => {
    const prior = old.get(a.tripId)?.item
    return { ...a, risk: Math.round(a.risk), critical: prior ? prior.critical ? a.risk >= 87 : a.risk >= 93 : a.risk >= 90 }
  }).sort((a, b) => Number(b.critical) - Number(a.critical) ||
    (old.get(a.tripId)?.index ?? previous.length + initial.findIndex((v) => v.tripId === a.tripId)) -
    (old.get(b.tripId)?.index ?? previous.length + initial.findIndex((v) => v.tripId === b.tripId)))
}
