import { describe, expect, it } from 'vitest'
import { demoApi } from './demo'

describe('demoApi', () => {
  it('has 24 synthetic vehicles with a valid network and all risk states', async () => {
    const day = await demoApi.day()
    const frame = await demoApi.frame({ t: 450 })
    expect(frame.vehicles.id.length).toBe(24)
    expect(new Set(frame.vehicles.id).size).toBe(24)
    expect(new Set(frame.vehicles.mode)).toEqual(new Set(['bus', 'tram']))
    expect(new Set(frame.vehicles.level)).toEqual(new Set([0, 1, 2, 3]))
    expect(new Set(frame.vehicles.route).size).toBe(6)
    for (const segment of day.network.segments) for (const stop of segment) expect(day.network.stops[stop]).toBeTruthy()
    for (const [segment] of frame.slowSegments) expect(day.network.segments[segment]).toBeTruthy()
    expect(frame.alerts.length).toBeGreaterThan(0)

    for (const alert of frame.alerts) {
      const i = frame.vehicles.id.indexOf(alert.tripId)
      expect(i).toBeGreaterThanOrEqual(0)
      expect(frame.vehicles.level[i]).toBe(2)
      expect(alert.risk).toBe(frame.vehicles.risk[i])
      expect(alert.delay).toBeLessThan(day.threshold)

      const selected = await demoApi.frame({ t: 450, trip: alert.tripId })
      expect(selected.trip?.tripId).toBe(alert.tripId)
      expect(selected.trip?.forecastDelay).toBe(alert.forecastDelay)
      expect(selected.trip?.forecastMinutes).toBe(12)
      expect(alert.forecastReason).toBeTruthy()
      expect(frame.slowSegments.some(([index]) => index === alert.problemSegment?.index)).toBe(true)
      expect(selected.trip?.problemSegment).toEqual(alert.problemSegment)
      expect(selected.trip?.forecastTime).toMatch(/^\d{2}:\d{2}$/)
    }
  })

  it('moves vehicles over time, filters by transport/risk and replays deterministically', async () => {
    const a = await demoApi.frame({ t: 450 })
    const b = await demoApi.frame({ t: 460 })
    expect(a.vehicles.lon).not.toEqual(b.vehicles.lon)
    expect(a.vehicles.risk).not.toEqual(b.vehicles.risk)
    expect(await demoApi.frame({ t: 450 })).toEqual(a)

    const trams = await demoApi.frame({ t: 450, mode: 'tram' })
    expect(trams.vehicles.id.length).toBe(8)
    expect(trams.vehicles.mode?.every((mode) => mode === 'tram')).toBe(true)

    const high = await demoApi.frame({ t: 450, minLevel: 2 })
    expect(high.vehicles.id.length).toBeGreaterThan(0)
    expect(high.vehicles.level.every((level) => level === 2)).toBe(true)
  })

  it('agrees between timeline and frames, and live trips match their alerts', async () => {
    const timeline = await demoApi.timeline('bus')
    for (const bin of timeline.bins) {
      const frame = await demoApi.frame({ t: bin.t, mode: 'bus' })
      expect(bin.high).toBe(frame.vehicles.level.filter((level) => level === 2).length)
    }

    const live = await demoApi.live()
    expect(live.tracked).toBe(24)
    for (const alert of live.alerts) {
      expect(live.trips?.[alert.tripId]).toBeDefined()
      expect(live.trips?.[alert.tripId].risk).toBe(alert.risk)
    }

    const ctrl = new AbortController()
    ctrl.abort()
    await expect(demoApi.day(ctrl.signal)).rejects.toMatchObject({ name: 'AbortError' })
  })
})
