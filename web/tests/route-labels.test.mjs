import test from 'node:test'
import assert from 'node:assert/strict'
import { routeLabels, escapeMapText } from '../src/maps/routeLabels.ts'

test('dense stop names thin out at overview zoom and reappear when zooming in', () => {
  const stops = Array.from({ length: 12 }, (_, i) => ({ name: `Остановка ${i + 1}`, lat: 55.75 + i * .0004, lon: 37.6 }))
  const overview = routeLabels(stops, 11)
  const detail = routeLabels(stops, 18)
  assert.equal(overview.length, stops.length)
  assert.ok(overview.filter((label) => label.visible).length < stops.length)
  assert.equal(detail.filter((label) => label.visible).length, stops.length)
})

test('repeated stops on a circular route do not produce overlapping labels', () => {
  const stop = { name: 'Кольцевая', lat: 55.75, lon: 37.6 }
  const labels = routeLabels([stop, stop, stop], 15)
  assert.ok(labels.filter((label) => label.visible).length <= 2)
  assert.deepEqual(routeLabels([], 12), [])
})

test('stop names are escaped before entering map HTML templates', () => {
  assert.equal(escapeMapText('<img src="x"> & \'улица\''), '&lt;img src=&quot;x&quot;&gt; &amp; &#39;улица&#39;')
})
