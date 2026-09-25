import { test } from 'node:test'
import assert from 'node:assert/strict'
import { demoApi } from '../src/api/demo.ts'

test('demo has 24 synthetic vehicles with a valid network and all risk states', async () => {
  const day = await demoApi.day()
  const frame = await demoApi.frame({ t: 450 })
  assert.equal(frame.vehicles.id.length, 24)
  assert.equal(new Set(frame.vehicles.id).size, 24)
  assert.deepEqual(new Set(frame.vehicles.mode), new Set(['bus', 'tram']))
  assert.deepEqual(new Set(frame.vehicles.level), new Set([0, 1, 2, 3]))
  assert.equal(new Set(frame.vehicles.route).size, 6)
  for (const segment of day.network.segments) for (const stop of segment) assert.ok(day.network.stops[stop])
  for (const [segment] of frame.slowSegments) assert.ok(day.network.segments[segment])
  assert.ok(frame.alerts.length > 0)
  for (const alert of frame.alerts) {
    const i = frame.vehicles.id.indexOf(alert.tripId)
    assert.ok(i >= 0)
    assert.equal(frame.vehicles.level[i], 2)
    assert.equal(alert.risk, frame.vehicles.risk[i])
    assert.ok(alert.delay < day.threshold)
    const selected = await demoApi.frame({ t: 450, trip: alert.tripId })
    assert.equal(selected.trip.tripId, alert.tripId)
    assert.equal(selected.trip.forecastDelay, alert.forecastDelay)
    assert.equal(selected.trip.forecastMinutes, 12)
    assert.ok(alert.forecastReason)
    assert.ok(frame.slowSegments.some(([index]) => index === alert.problemSegment.index))
    assert.deepEqual(selected.trip.problemSegment, alert.problemSegment)
    assert.match(selected.trip.forecastTime, /^\d{2}:\d{2}$/)
  }
})

test('movement, changing risk, transport/risk filters and deterministic replay', async () => {
  const a = await demoApi.frame({ t: 450 })
  const b = await demoApi.frame({ t: 460 })
  assert.notDeepEqual(a.vehicles.lon, b.vehicles.lon)
  assert.notDeepEqual(a.vehicles.risk, b.vehicles.risk)
  assert.deepEqual(a, await demoApi.frame({ t: 450 }))
  const trams = await demoApi.frame({ t: 450, mode: 'tram' })
  assert.equal(trams.vehicles.id.length, 8)
  assert.ok(trams.vehicles.mode.every((mode) => mode === 'tram'))
  const high = await demoApi.frame({ t: 450, minLevel: 2 })
  assert.ok(high.vehicles.id.length > 0)
  assert.ok(high.vehicles.level.every((level) => level === 2))
})

test('timeline agrees with frames and live contains matching selection details', async () => {
  const timeline = await demoApi.timeline('bus')
  for (const bin of timeline.bins) {
    const frame = await demoApi.frame({ t: bin.t, mode: 'bus' })
    assert.equal(bin.high, frame.vehicles.level.filter((level) => level === 2).length)
  }
  const live = await demoApi.live()
  assert.equal(live.tracked, 24)
  for (const alert of live.alerts) {
    assert.ok(live.map.frame.vehicles.id.includes(alert.tripId))
    assert.equal(live.trips[alert.tripId].risk, alert.risk)
  }
  const ctrl = new AbortController()
  ctrl.abort()
  await assert.rejects(demoApi.day(ctrl.signal), { name: 'AbortError' })
})
