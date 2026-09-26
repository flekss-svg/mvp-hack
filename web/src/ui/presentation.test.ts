import { describe, expect, it } from 'vitest'
import type { Alert } from '../api/types'
import { DEFAULT_DISPLAY, PALETTES, parseDisplay } from './display'
import { ageSeconds, currentText, forecastText, riskText, stableIncidents } from './presentation'

const alert = (tripId: number, risk: number): Alert =>
  ({ tripId, risk, delay: 2, route: '17', mode: 'bus', dest: 'Маяковская', stop: 'Тверская' })

describe('presentation text', () => {
  it('explains signed deviations without changing their meaning', () => {
    expect(currentText(-3.5)).toBe('На 3.5 мин раньше графика')
    expect(currentText(2.1)).toBe('Опаздывает на 2.1 мин')
    expect(currentText(-0.04)).toBe('По графику')
    expect(currentText(NaN)).toBe('Отклонение не передано')

    expect(forecastText(-3.5, 5.6)).toBe('Ожидается опоздание на 5.6 мин')
    expect(forecastText(2.1, 7.8)).toBe('Опоздание вырастет до 7.8 мин')
    expect(forecastText(5.4, 2.2)).toBe('Опоздание сократится до 2.2 мин')
    expect(forecastText(5.4, 0)).toBe('Ожидается движение по графику')
    expect(forecastText(2.2, -1.2)).toBe('Ожидается прибытие на 1.2 мин раньше графика')
    expect(forecastText(2.2, undefined)).toBe('Прогноз опоздания не передан')

    expect(riskText(89.9)).toBe('90%')
    expect(ageSeconds(1000, 19000)).toBe(18)
  })
})

describe('stableIncidents', () => {
  it('keeps order stable through small changes and reorders only across severity bands', () => {
    const first = stableIncidents([], [alert(1, 91), alert(2, 89), alert(3, 85)])
    const small = stableIncidents(first, [alert(3, 86), alert(2, 91), alert(1, 89)])
    expect(small.map((v) => v.tripId)).toEqual([1, 2, 3])
    expect(small[0].critical).toBe(true)
    expect(small[1].critical).toBe(false)

    const major = stableIncidents(small, [alert(1, 86), alert(2, 94), alert(3, 87)])
    expect(major.map((v) => v.tripId)).toEqual([2, 1, 3])
    expect(major[0].critical).toBe(true)
    expect(major[1].critical).toBe(false)

    const removed = stableIncidents(major, [alert(1, 86), alert(3, 88)])
    expect(removed.map((v) => v.tripId)).toEqual([1, 3])
  })
})

describe('display preferences', () => {
  it('roundtrip through storage and fall back safely when invalid', () => {
    const custom = { ...DEFAULT_DISPLAY, palette: 'custom' as const,
      colors: { ...DEFAULT_DISPLAY.colors, high: '#123456' }, lowRisk: false, density: 'comfortable' as const }
    expect(parseDisplay(JSON.stringify(custom))).toEqual(custom)
    expect(parseDisplay('broken')).toEqual(DEFAULT_DISPLAY)
    expect(parseDisplay(null)).toEqual(DEFAULT_DISPLAY)
    expect(parseDisplay(JSON.stringify({ ...custom, colors: { high: 'url(bad)' } })).colors.high).toBe(DEFAULT_DISPLAY.colors.high)
    expect(parseDisplay(JSON.stringify({ ...DEFAULT_DISPLAY, palette: 'colorblind' })).colors).toEqual(PALETTES.colorblind)
  })
})
