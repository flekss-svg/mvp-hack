import { useEffect, useRef, useState } from 'react'
import type { YMap, YMapMarker, YMapFeature } from '@yandex/ymaps3-types'
import type { DayInfo, Frame } from '../api/types'
import { loadYandex, logYandex, YandexLoadError, MAP_KEY, MOSCOW } from '../maps/yandex'
import { MapCanvas } from './MapCanvas'

interface Props {
  day: DayInfo | null
  frame: Frame | null
  selected: number | null
  focusToken: number
  focusReady: boolean
  onSelect: (id: number | null) => void
}

const riskLabels = ['Низкий риск', 'Средний риск', 'Высокий риск', 'Нет прогноза']

export function TransportMap({ day, frame, selected, focusToken, focusReady, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'missing'>(MAP_KEY ? 'loading' : 'missing')
  const [attempt, setAttempt] = useState(0)
  const mapRef = useRef<YMap | null>(null)
  const sdkRef = useRef<Awaited<ReturnType<typeof loadYandex>> | null>(null)
  const markers = useRef(new Map<number, { entity: YMapMarker; button: HTMLButtonElement }>())
  const networkRef = useRef<YMapFeature | null>(null)
  const slowRefs = useRef<YMapFeature[]>([])
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect
  const focused = useRef('')

  useEffect(() => {
    logYandex('configuration', 'start')
    if (!MAP_KEY) return
    let cancelled = false
    let stage: Parameters<typeof logYandex>[0] = 'script-load'
    setStatus('loading')
    void loadYandex().then((sdk) => {
      if (cancelled || !host.current) return
      stage = 'map-create'
      logYandex(stage, 'start')
      const map = new sdk.YMap(host.current, { location: { center: MOSCOW, zoom: 12 }, zoomRange: { min: 9, max: 19 } })
      logYandex(stage, 'success')
      mapRef.current = map
      sdkRef.current = sdk
      stage = 'scheme-layer'
      logYandex(stage, 'start')
      map.addChild(new sdk.YMapDefaultSchemeLayer({}))
      logYandex(stage, 'success')
      stage = 'features-layer'
      logYandex(stage, 'start')
      map.addChild(new sdk.YMapDefaultFeaturesLayer({}))
      logYandex(stage, 'success')
      logYandex('map-ready', 'success')
      setStatus('ready')
    }).catch((error: unknown) => {
      if (!cancelled) {
        logYandex(error instanceof YandexLoadError ? error.stage : stage, 'error', error)
        setStatus('error')
      }
    })
    return () => {
      cancelled = true
      mapRef.current?.destroy()
      mapRef.current = null
      networkRef.current = null
      slowRefs.current = []
      markers.current.clear()
      focused.current = ''
    }
  }, [attempt])

  useEffect(() => {
    const map = mapRef.current
    const sdk = sdkRef.current
    if (!map || !sdk || status !== 'ready') return
    if (networkRef.current) map.removeChild(networkRef.current)
    networkRef.current = null
    if (!day) return
    const coordinates = day.network.segments.flatMap(([a, b]) =>
      day.network.stops[a] && day.network.stops[b] ? [[day.network.stops[a], day.network.stops[b]]] : [])
    if (coordinates.length) {
      const network = new sdk.YMapFeature({ geometry: { type: 'MultiLineString', coordinates },
        style: { stroke: [{ color: '#65829e', width: 2, opacity: 0.5 }] } })
      map.addChild(network)
      networkRef.current = network
    }
  }, [day, status])

  useEffect(() => {
    const map = mapRef.current
    const sdk = sdkRef.current
    if (!map || !sdk || status !== 'ready') return
    const v = frame?.vehicles
    const ids = new Set(v?.id ?? [])
    for (const [id, marker] of markers.current) {
      if (!ids.has(id)) { map.removeChild(marker.entity); markers.current.delete(id) }
    }
    v?.id.forEach((id, i) => {
      let marker = markers.current.get(id)
      if (!marker) {
        const button = document.createElement('button')
        button.type = 'button'
        button.onclick = (event) => { event.stopPropagation(); selectRef.current(id) }
        const entity = new sdk.YMapMarker({ coordinates: [v.lon[i], v.lat[i]], blockBehaviors: true, blockEvents: true }, button)
        marker = { entity, button }
        markers.current.set(id, marker)
        map.addChild(entity)
      }
      const route = v.route?.[i] ?? String(id)
      marker.button.className = `vehicle-marker level-${v.level[i]}${selected === id ? ' is-selected' : ''}${v.late[i] ? ' is-late' : ''}`
      marker.button.textContent = `${v.level[i] === 2 ? '! ' : v.level[i] === 3 ? '− ' : ''}${route}`
      const label = `ТС ${id}, ${riskLabels[v.level[i]]}${v.level[i] === 3 ? '' : ` ${v.risk[i]}%`}`
      marker.button.setAttribute('aria-label', label)
      marker.button.setAttribute('aria-pressed', String(selected === id))
      marker.button.title = label
      marker.entity.update({ coordinates: [v.lon[i], v.lat[i]], zIndex: selected === id ? 100 : v.level[i] === 2 ? 50 : 10 })
    })

    for (const severity of [0, 1] as const) {
      const coordinates = (frame?.slowSegments ?? []).filter((s) => s[1] === severity).flatMap(([idx]) => {
        const pair = day?.network.segments[idx]
        const a = pair && day?.network.stops[pair[0]]
        const b = pair && day?.network.stops[pair[1]]
        return a && b ? [[a, b]] : []
      })
      const previous = slowRefs.current[severity]
      if (!coordinates.length) {
        if (previous) { map.removeChild(previous); delete slowRefs.current[severity] }
        continue
      }
      const geometry = { type: 'MultiLineString' as const, coordinates }
      if (previous) previous.update({ geometry })
      else {
        const feature = new sdk.YMapFeature({ geometry,
          style: { stroke: [{ color: severity ? '#c33f3f' : '#b67a17', width: severity ? 6 : 4 }] } })
        map.addChild(feature)
        slowRefs.current[severity] = feature
      }
    }
    // Focus only on explicit selection (including repeated alert clicks), never on each frame.
    const target = `${selected}:${focusToken}`
    const idx = v?.id.indexOf(selected ?? -1) ?? -1
    if (focusReady && v && idx >= 0 && focused.current !== target) {
      focused.current = target
      map.setLocation({ center: [v.lon[idx], v.lat[idx]], zoom: Math.max(map.zoom, 14), duration: 350 })
    }
    if (selected === null) focused.current = ''
  }, [day, frame, selected, focusToken, focusReady, status])

  return (
    <div className="transport-map">
      <div ref={host} className="yandex-host" aria-label="Карта Москвы" />
      {status !== 'ready' && day && <MapCanvas day={day} frame={frame} selected={selected} onSelect={onSelect} focusToken={focusToken} focusReady={focusReady} />}
      {status !== 'ready' && (
        <div className="map-notice" role="status">
          <span className="notice-icon">⌖</span>
          <div><strong>{status === 'missing' ? 'Не настроен ключ Yandex Maps API' : status === 'error' ? 'Не удалось загрузить Yandex Maps' : 'Подключаем Yandex Maps…'}</strong>
            <span>{day ? 'Доступна интерактивная схема маршрутов' : 'Географическая подложка недоступна'}</span></div>
          {status === 'error' && <button onClick={() => setAttempt((v) => v + 1)}>Повторить</button>}
        </div>
      )}
      {status === 'ready' && <div className="map-zoom">
        <button aria-label="Приблизить" onClick={() => { const m = mapRef.current; if (m) m.setLocation({ zoom: Math.min(19, m.zoom + 1), duration: 200 }) }}>+</button>
        <button aria-label="Отдалить" onClick={() => { const m = mapRef.current; if (m) m.setLocation({ zoom: Math.max(9, m.zoom - 1), duration: 200 }) }}>−</button>
        <button aria-label="Показать Москву" onClick={() => mapRef.current?.setLocation({ center: MOSCOW, zoom: 12, duration: 350 })}>⌖</button>
      </div>}
      <span className="map-caption">{status === 'ready' ? 'МОСКВА' : 'СХЕМА МАРШРУТОВ · БЕЗ ПОДЛОЖКИ'}</span>
    </div>
  )
}
