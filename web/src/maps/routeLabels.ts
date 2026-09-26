import type { RouteStop } from '../api/types'

type Box = { left: number; right: number; top: number; bottom: number }
export type StopLabel = { side: 'left' | 'right'; visible: boolean }

/** Screen-space collision checks keep long names apart as the map zoom changes. */
export function routeLabels(stops: RouteStop[], zoom: number): StopLabel[] {
  const scale = 256 * 2 ** zoom
  const points = stops.map(({ lat, lon }) => {
    const sin = Math.sin(Math.max(-85, Math.min(85, lat)) * Math.PI / 180)
    return { x: (lon + 180) / 360 * scale, y: (.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale }
  })
  const result: StopLabel[] = stops.map(() => ({ side: 'right', visible: false }))
  const boxes: Box[] = []
  // The terminuses get first choice of space; every stop keeps its numbered dot.
  const order = [...new Set([0, stops.length - 1, ...stops.map((_, i) => i)])].filter((i) => i >= 0 && i < stops.length)
  for (const i of order) {
    const { x, y } = points[i]
    const width = Math.min(174, Math.max(60, stops[i].name.length * 6.5 + 20))
    const preferred = i % 2 ? 'left' : 'right'
    for (const side of [preferred, preferred === 'left' ? 'right' : 'left'] as const) {
      const box = { left: side === 'right' ? x + 14 : x - 14 - width, right: side === 'right' ? x + 14 + width : x - 14, top: y - 14, bottom: y + 14 }
      if (boxes.some((b) => box.left < b.right && box.right > b.left && box.top < b.bottom && box.bottom > b.top)) continue
      if (points.some((p, j) => i !== j && p.x + 11 > box.left && p.x - 11 < box.right && p.y + 11 > box.top && p.y - 11 < box.bottom)) continue
      boxes.push(box)
      result[i] = { side, visible: true }
      break
    }
  }
  return result
}

export const escapeMapText = (text: string) => text.replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]!)
