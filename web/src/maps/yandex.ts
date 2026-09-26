export const MAP_KEY = (import.meta.env.VITE_YANDEX_MAPS_API_KEY ?? '').trim()
export const MOSCOW: [number, number] = [55.7558, 37.6176]

export interface YMaps21 {
  ready: (callback: () => void) => void
  Map: new (element: HTMLElement, state: { center: [number, number]; zoom: number }, options?: Record<string, unknown>) => YMap21
  Placemark: new (coordinates: [number, number], properties?: Record<string, unknown>, options?: Record<string, unknown>) => YPlacemark21
  Polyline: new (coordinates: [number, number][], properties?: Record<string, unknown>, options?: Record<string, unknown>) => YGeoObject21
  templateLayoutFactory: { createClass: (template: string) => unknown }
}

export interface YMap21 {
  geoObjects: { add: (object: YGeoObject21) => void; remove: (object: YGeoObject21) => void }
  setCenter: (center: [number, number], zoom?: number, options?: { duration?: number }) => void
  getZoom: () => number
  setZoom: (zoom: number, options?: { duration?: number }) => void
  destroy: () => void
}

export interface YGeoObject21 {
  geometry: { setCoordinates: (coordinates: [number, number] | [number, number][]) => void }
  properties: { set: (values: Record<string, unknown>) => void }
  options: { set: (values: Record<string, unknown>) => void }
  events: { add: (event: string, callback: (event: { preventDefault: () => void; stopPropagation: () => void }) => void) => void }
}

export interface YPlacemark21 extends YGeoObject21 {}

declare global { interface Window { ymaps?: YMaps21 } }

let pending: Promise<YMaps21> | null = null
const scriptSelector = 'script[data-yandex-maps="2.1"]'

/** API 2.1 is loaded once, independently of React mounts. The key never reaches the UI or logs. */
export function loadYandex(): Promise<YMaps21> {
  if (pending) return pending
  pending = new Promise<YMaps21>((resolve, reject) => {
    const finishReady = () => {
      const sdk = window.ymaps
      if (!sdk) { reject(new Error('Yandex Maps namespace is unavailable')); return }
      sdk.ready(() => resolve(sdk))
    }
    const existing = document.querySelector<HTMLScriptElement>(scriptSelector)
    if (existing) {
      if (window.ymaps) finishReady()
      else {
        existing.addEventListener('load', finishReady, { once: true })
        existing.addEventListener('error', () => reject(new Error('Yandex Maps script failed to load')), { once: true })
      }
      return
    }
    const script = document.createElement('script')
    script.dataset.yandexMaps = '2.1'
    script.async = true
    script.src = `https://api-maps.yandex.ru/2.1/?apikey=${encodeURIComponent(MAP_KEY)}&lang=ru_RU`
    script.onload = finishReady
    script.onerror = () => reject(new Error('Yandex Maps script failed to load'))
    document.head.appendChild(script)
  }).catch((error: unknown) => {
    pending = null
    throw error
  })
  return pending
}
