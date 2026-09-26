import { useEffect, useRef, useState } from 'react'
import type { DayInfo, SlowSegment } from '../api/types'
import { MAP_KEY, loadYandex, MOSCOW } from '../maps/yandex'
import type { YGeoObject21, YMap21, YMaps21, YPlacemark21 } from '../maps/yandex'
import type { MapVehicle } from '../maps/vehicles'
import { vehicleMarkerTemplate } from '../maps/vehicleMarker'
import type { DisplaySettings } from '../ui/display'

interface Props {
  day: DayInfo | null
  vehicles: MapVehicle[]
  slowSegments: SlowSegment[]
  selected: string | number | null
  focusToken: number
  display: DisplaySettings
  onSelect: (id: string | number | null) => void
}

const level = (vehicle: MapVehicle) => vehicle.level === 0 || vehicle.level === 1 || vehicle.level === 2 ? vehicle.level : 3
const riskLabels = ['Низкий риск', 'Средний риск', 'Высокий риск', 'Нет прогноза']
const coord = ([lon, lat]: [number, number]): [number, number] => [lat, lon]

/** A single map implementation for replay now and independently-normalized live vehicles later. */
export function TransportMap({ day, vehicles, slowSegments, selected, focusToken, display, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const mapRef = useRef<YMap21 | null>(null)
  const sdkRef = useRef<YMaps21 | null>(null)
  const markers = useRef(new Map<string, YPlacemark21>())
  const segmentLines = useRef<YGeoObject21[]>([])
  const selectedRef = useRef(onSelect)
  const focused = useRef('')
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'missing'>(MAP_KEY ? 'loading' : 'missing')
  const [attempt, setAttempt] = useState(0)
  selectedRef.current = onSelect

  useEffect(() => {
    if (!MAP_KEY) return
    let cancelled = false
    setStatus('loading')
    void loadYandex().then((sdk) => {
      if (cancelled || !host.current) return
      const map = new sdk.Map(host.current, { center: MOSCOW, zoom: 11 }, { suppressMapOpenBlock: true, yandexMapDisablePoiInteractivity: true, controls: [] })
      mapRef.current = map
      sdkRef.current = sdk
      setStatus('ready')
    }).catch(() => { if (!cancelled) setStatus('error') })
    return () => {
      cancelled = true
      mapRef.current?.destroy()
      mapRef.current = null
      sdkRef.current = null
      markers.current.clear()
      segmentLines.current = []
      focused.current = ''
    }
  }, [attempt])

  useEffect(() => {
    const map = mapRef.current
    const sdk = sdkRef.current
    if (!map || !sdk || status !== 'ready') return
    const active = new Set(vehicles.map((vehicle) => String(vehicle.vehicleId)))
    markers.current.forEach((marker, key) => {
      if (!active.has(key)) { map.geoObjects.remove(marker); markers.current.delete(key) }
    })
    vehicles.forEach((vehicle) => {
      const key = String(vehicle.vehicleId)
      const selectedMarker = selected === vehicle.vehicleId
      const currentLevel = level(vehicle)
      const mode = vehicle.mode === 'tram' || vehicle.mode === 'bus' ? vehicle.mode : 'unknown'
      const route = display.routeNumbers ? vehicle.route || '—' : ''
      const label = `${mode === 'tram' ? 'Трамвай' : mode === 'bus' ? 'Автобус' : 'Транспорт'}${vehicle.route ? ` ${vehicle.route}` : ''}, ТС ${vehicle.vehicleId}: ${riskLabels[currentLevel]}${currentLevel === 3 || vehicle.risk == null ? '' : `, ${Math.round(vehicle.risk)}%`}`
      const className = `ym-vehicle-marker vehicle-${mode} level-${currentLevel}${selectedMarker ? ' is-selected' : ''}${display.routeNumbers ? '' : ' without-route'}`
      let marker = markers.current.get(key)
      if (!marker) {
        marker = new sdk.Placemark([vehicle.lat, vehicle.lon], {}, {
          iconLayout: sdk.templateLayoutFactory.createClass(vehicleMarkerTemplate),
          iconShape: { type: 'Rectangle', coordinates: [[-18, -29], [18, 29]] }, hideIconOnBalloonOpen: false,
        })
        marker.events.add('click', (event) => {
          event.preventDefault()
          event.stopPropagation()
          selectedRef.current(vehicle.vehicleId)
        })
        markers.current.set(key, marker)
        map.geoObjects.add(marker)
      }
      marker.geometry.setCoordinates([vehicle.lat, vehicle.lon])
      marker.properties.set({ className, label, route, vehicleKey: key, hintContent: label })
      marker.options.set({ zIndex: selectedMarker ? 1000 : currentLevel === 2 ? 600 : currentLevel === 1 ? 400 : 200 })
    })
    segmentLines.current.forEach((line) => map.geoObjects.remove(line))
    segmentLines.current = []
    if (display.problemSegments && day) slowSegments.forEach(([segmentIndex, severity]) => {
      const segment = day.network.segments[segmentIndex]
      const from = segment && day.network.stops[segment[0]]
      const to = segment && day.network.stops[segment[1]]
      if (!from || !to) return
      const line = new sdk.Polyline([coord(from), coord(to)], {}, { strokeColor: severity ? display.colors.critical : display.colors.warning, strokeWidth: severity ? 6 : 4, strokeOpacity: .85, zIndex: severity ? 500 : 300 })
      map.geoObjects.add(line)
      segmentLines.current.push(line)
    })
    const vehicle = vehicles.find((item) => item.vehicleId === selected)
    const target = `${selected ?? ''}:${focusToken}`
    if (vehicle && target !== focused.current) {
      focused.current = target
      map.setCenter([vehicle.lat, vehicle.lon], Math.max(14, map.getZoom()), { duration: 250 })
    }
    if (selected === null) focused.current = ''
  }, [day, vehicles, slowSegments, selected, focusToken, display, status])

  const zoom = (delta: number) => { const map = mapRef.current; if (map) map.setZoom(Math.max(9, Math.min(19, map.getZoom() + delta)), { duration: 150 }) }
  return <div className="transport-map">
    <div ref={host} className="yandex-host" aria-label="Yandex Map Москвы" onClickCapture={(event) => {
      // Keyboard activation uses the button; pointer clicks use the SDK hotspot above.
      const button = event.target instanceof Element ? event.target.closest<HTMLButtonElement>('.ym-vehicle-marker') : null
      const vehicle = button && vehicles.find((item) => String(item.vehicleId) === button.dataset.vehicleId)
      if (!vehicle) return
      event.preventDefault()
      event.stopPropagation()
      onSelect(vehicle.vehicleId)
    }} />
    {status !== 'ready' && <div className="map-notice" role="status"><span className="notice-icon">⌖</span><div><strong>{status === 'missing' ? 'Для отображения карты добавьте VITE_YANDEX_MAPS_API_KEY в web/.env' : status === 'error' ? 'Не удалось загрузить карту' : 'Подключаем Yandex Maps…'}</strong><span>{status === 'missing' ? 'После добавления ключа перезапустите dev-сервер.' : 'Географическая подложка будет доступна после загрузки.'}</span></div>{status === 'error' && <button onClick={() => setAttempt((value) => value + 1)}>Повторить</button>}</div>}
    {status === 'ready' && <div className="map-zoom"><button aria-label="Приблизить" onClick={() => zoom(1)}>+</button><button aria-label="Отдалить" onClick={() => zoom(-1)}>−</button><button aria-label="Показать Москву" onClick={() => mapRef.current?.setCenter(MOSCOW, 11, { duration: 250 })}>⌖</button></div>}
    {status === 'ready' && <span className="map-caption">МОСКВА · YANDEX MAPS</span>}
  </div>
}
