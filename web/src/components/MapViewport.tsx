import type { DayInfo, Frame } from '../api/types'
import type { DisplaySettings } from '../ui/display'
import { MapCanvas } from './MapCanvas'

/** Provider-independent data/overlay boundary. The Yandex loader is intentionally not invoked here. */
export function MapViewport(props: { day: DayInfo | null; frame: Frame | null; selected: number | null; focusToken: number; focusReady: boolean; onSelect: (id: number | null) => void; display: DisplaySettings }) {
  return <div className="transport-map" aria-label="Схема маршрутной сети Москвы">
    <div className="map-provider-slot" aria-hidden="true" />
    {props.day && <MapCanvas {...props} day={props.day} />}
    <div className="map-area-label"><span className="map-area-cross" aria-hidden="true">⌖</span><div><strong>Москва</strong><span>Схема маршрутной сети</span></div></div>
    <span className="map-caption">СХЕМА · БЕЗ ГЕОГРАФИЧЕСКОЙ ПОДЛОЖКИ</span>
  </div>
}
