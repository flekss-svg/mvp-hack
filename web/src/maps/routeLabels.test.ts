import { describe, expect, it } from 'vitest'
import { escapeMapText, routeLabels } from './routeLabels'

describe('routeLabels', () => {
  it('thins out dense stop names at overview zoom and shows them all when zoomed in', () => {
    const stops = Array.from({ length: 12 }, (_, i) => ({ name: `Остановка ${i + 1}`, lat: 55.75 + i * 0.0004, lon: 37.6 }))
    const overview = routeLabels(stops, 11)
    const detail = routeLabels(stops, 18)
    expect(overview.length).toBe(stops.length)
    expect(overview.filter((label) => label.visible).length).toBeLessThan(stops.length)
    expect(detail.filter((label) => label.visible).length).toBe(stops.length)
  })

  it('does not produce overlapping labels for repeated stops on a circular route', () => {
    const stop = { name: 'Кольцевая', lat: 55.75, lon: 37.6 }
    const labels = routeLabels([stop, stop, stop], 15)
    expect(labels.filter((label) => label.visible).length).toBeLessThanOrEqual(2)
    expect(routeLabels([], 12)).toEqual([])
  })

  it('escapes stop names before they enter the map HTML templates', () => {
    expect(escapeMapText('<img src="x"> & \'улица\'')).toBe('&lt;img src=&quot;x&quot;&gt; &amp; &#39;улица&#39;')
  })
})
