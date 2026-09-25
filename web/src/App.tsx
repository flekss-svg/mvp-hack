import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, DEMO_MODE } from './api/client'
import { demoDirectory } from './api/demo'
import type { Alert, Frame, Kpi, TripCard } from './api/types'
import { useResource } from './hooks/useResource'
import { usePlayback } from './hooks/usePlayback'
import { useBufferedSnapshot, useNow } from './hooks/useBufferedSnapshot'
import { useDisplaySettings } from './hooks/useDisplaySettings'
import { stableIncidents } from './ui/presentation'
import type { StableIncident } from './ui/presentation'
import { AlertList } from './components/AlertList'
import { Header } from './components/Header'
import { Legend } from './components/Legend'
import { MapViewport } from './components/MapViewport'
import { ModelPanel } from './components/ModelPanel'
import { Segmented } from './components/Segmented'
import { Timeline } from './components/Timeline'
import { TripPanel } from './components/TripPanel'
import { DisplaySettings } from './components/DisplaySettings'
import { VehicleSearch } from './components/VehicleSearch'
import { ConnectionStatus } from './components/ConnectionStatus'
import { Icon } from './components/Icon'

type Source = 'replay' | 'live'
const EMPTY_KPI: Kpi[] = [
  { key: 'onLine', label: 'на линии', value: '—' },
  { key: 'high', label: 'высокий риск', value: '—', tone: 'high' },
  { key: 'late', label: 'уже опаздывают', value: '—' },
  { key: 'hit', label: 'ранних тревог сбылось', value: '—' },
]

export default function App() {
  const [source, setSource] = useState<Source>('replay')
  const [mode, setMode] = useState('all')
  const [minLevel, setMinLevel] = useState(0)
  const [incidentFilter, setIncidentFilter] = useState('all')
  const [selected, setSelected] = useState<number | null>(null)
  const [focusToken, setFocusToken] = useState(0)
  const asideRef = useRef<HTMLElement>(null)
  const { settings, setSettings } = useDisplaySettings()
  const now = useNow()
  useEffect(() => { if (selected !== null) asideRef.current?.scrollTo({ top: 0 }) }, [selected, focusToken])
  const replay = source === 'replay'
  const day = useResource((signal) => api.day(signal), [], { enabled: replay })
  const playback = usePlayback(day.data ? { tMin: day.data.tMin, tMax: day.data.tMax } : null, replay, DEMO_MODE)
  const frame = useResource(async (signal) => {
    const result = await api.frame({ t: playback.t!, mode, trip: selected }, signal)
    return { ...result, trip: result.trip ? { ...result.trip, tripId: selected ?? undefined } : null }
  }, [playback.playing ? null : playback.t, mode, selected], {
    enabled: replay && playback.t !== null && !!day.data, pollMs: playback.playing ? 120 : undefined,
  })
  const timeline = useResource((signal) => api.timeline(mode, signal), [mode], { enabled: replay })
  const live = useResource((signal) => api.live(signal), [], { pollMs: 4000, enabled: !replay })
  const offline = replay ? !!(day.error || frame.error) : !!live.error
  const data = replay ? frame.data : live.data
  const mapDay = replay ? day.data : live.data?.map?.day ?? null
  const rawFrame = replay ? frame.data : live.data?.map?.frame ?? null
  const updatedAt = replay ? frame.updatedAt : live.updatedAt
  const scope = `${source}:${mode}`
  const buffered = useBufferedSnapshot<{ alerts: Alert[]; kpi: Kpi[] }>(data, updatedAt, scope, replay && !playback.playing)
  const order = useRef<{ scope: string; alerts: StableIncident[] }>({ scope, alerts: [] })
  const alerts = useMemo(() => {
    const incoming = (buffered.value?.alerts ?? []).filter((a) => mode === 'all' || a.mode === mode)
    const next = stableIncidents(order.current.scope === scope ? order.current.alerts : [], incoming)
    order.current = { scope, alerts: next }
    return next
  }, [buffered.value, scope, mode])
  const filteredAlerts = alerts.filter((a) => incidentFilter === 'all' || (incidentFilter === 'critical' ? a.critical : !a.critical))
  const liveTrip = useMemo<TripCard | null>(() => {
    if (selected === null) return null
    const detailed = live.data?.trips?.[selected]
    if (detailed) return detailed
    const a = live.data?.alerts.find((v) => v.tripId === selected)
    return a ? { ...a, found: true, onLine: true, routeName: a.dest, level: 2 } : null
  }, [live.data, selected])
  const currentTrip = replay ? (frame.data?.trip?.tripId === selected ? frame.data.trip : null) : liveTrip
  const detail = useBufferedSnapshot(currentTrip, updatedAt, `${source}:${selected}`, replay && !playback.playing)
  const trip = detail.value
  const { playing, toggle } = playback
  useEffect(() => { if (offline && playing) toggle() }, [offline, playing, toggle])
  const selectVehicle = useCallback((id: number | null) => {
    setSelected(id)
    setFocusToken((n) => n + 1)
    if (id !== null && replay && playing) toggle()
  }, [replay, playing, toggle])
  const searchSelect = (id: number) => { setMode('all'); setMinLevel(0); selectVehicle(id) }
  const mapFrame = useMemo<Frame | null>(() => {
    if (!rawFrame) return null
    const v = rawFrame.vehicles
    const indexes = v.id.map((_, i) => i).filter((i) => v.id[i] === selected ||
      ((mode === 'all' || !v.mode || v.mode[i] === mode) && (settings.lowRisk || v.level[i] !== 0) && (!minLevel || (v.level[i] !== 3 && v.level[i] >= minLevel))))
    return { ...rawFrame, vehicles: {
      id: indexes.map((i) => v.id[i]), lon: indexes.map((i) => v.lon[i]), lat: indexes.map((i) => v.lat[i]),
      level: indexes.map((i) => v.level[i]), risk: indexes.map((i) => v.risk[i]), late: indexes.map((i) => v.late[i]),
      route: v.route && indexes.map((i) => v.route![i]), mode: v.mode && indexes.map((i) => v.mode![i]),
    } }
  }, [rawFrame, mode, minLevel, settings.lowRisk, selected])
  const searchVehicles = useMemo(() => {
    if (DEMO_MODE) return demoDirectory
    const known = new Map((data?.alerts ?? []).map((a) => [a.tripId, { tripId: a.tripId, route: a.route, mode: a.mode }]))
    rawFrame?.vehicles.id.forEach((id, i) => { if (!known.has(id)) known.set(id, { tripId: id, route: rawFrame.vehicles.route?.[i] ?? '', mode: rawFrame.vehicles.mode?.[i] ?? '' }) })
    return [...known.values()]
  }, [data, rawFrame])
  const retry = () => { day.refresh(); frame.refresh(); timeline.refresh(); live.refresh() }
  const dateLabel = day.data ? new Date(`${day.data.date}T12:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) : 'Записанный день'

  return <div className={`app density-${settings.density}`}>
    <Header clock={data?.clock ?? '--:--'} kpi={buffered.value?.kpi ?? EMPTY_KPI}
      status={offline ? 'OFFLINE' : DEMO_MODE ? 'DEMO' : !data ? 'CONNECTING' : replay ? 'REPLAY' : 'LIVE'}
      subtitle={replay ? `${dateLabel} · записанный день` : 'Мониторинг входящих событий'} />
    <div className="workspace-toolbar">
      <div className="toolbar-title"><Icon name="pin" size={14} /><strong>Москва</strong></div>
      <div className="toolbar-filters">
        <Segmented label="Вид транспорта" value={mode} onChange={(v) => { setMode(v); setSelected(null) }} options={[{ value: 'all', label: 'Все' }, { value: 'bus', label: 'Автобусы' }, { value: 'tram', label: 'Трамваи' }]} />
        <Segmented label="Уровень риска" value={minLevel} onChange={setMinLevel} options={[{ value: 0, label: 'Все' }, { value: 1, label: 'Средний+' }, { value: 2, label: 'Высокий' }]} />
      </div>
      <VehicleSearch vehicles={searchVehicles} onSelect={searchSelect} />
      {DEMO_MODE && <span className="demo-badge" title="Синтетические маршруты, движение, прогнозы и рекомендации">DEMO DATA</span>}
      <div className="toolbar-source"><Segmented label="Источник данных" value={source} onChange={(v) => { setSource(v); setSelected(null) }} options={[{ value: 'replay', label: 'Записанный день' }, { value: 'live', label: 'Live' }]} /></div>
      <DisplaySettings settings={settings} onChange={setSettings} />
    </div>
    <main className="stage" aria-label="Карта и обстановка">
      <div className="map-body">
        <MapViewport day={mapDay} frame={mapFrame} selected={selected} focusToken={focusToken} display={settings}
          focusReady={!replay || frame.data?.trip?.tripId === selected} onSelect={selectVehicle} />
        <div className="connection-overlay"><ConnectionStatus updatedAt={updatedAt} now={now} offline={offline} paused={replay && !playing} />{offline && data && <button onClick={retry}>Повторить</button>}</div>
        {offline && !data && <div className="service-state" role="alert"><Icon name="signal" size={28} /><h2>Сервис данных недоступен</h2><p>Не удалось получить оперативную обстановку. Попробуйте подключиться ещё раз.</p><button className="primary" onClick={retry}>Повторить</button></div>}
        {!offline && !data && <div className="service-state loading-state" role="status"><span className="loader" /><h2>Загружаем обстановку</h2><p>Подключение к сервису данных…</p></div>}
        {!replay && live.data && !mapDay && !offline && <div className="service-state map-empty"><Icon name="pin" size={28} /><h2>Позиции ТС не переданы</h2><p>Доступные показатели и прогнозы — в панели справа.</p></div>}
        {mapDay && <Legend threshold={mapDay.threshold} />}
        {selected !== null && <div className="selection-chip"><span className="selection-dot" />Выбрано ТС <b>{selected}</b><button aria-label="Снять выбор ТС" onClick={() => setSelected(null)}>×</button></div>}
      </div>
      <div className="map-statusbar"><span className="map-count">{mapFrame ? `${mapFrame.vehicles.id.length} ТС на схеме` : 'Ожидание координат'}</span><span>{DEMO_MODE ? 'Все маршруты, позиции и прогнозы синтетические' : replay ? 'Записанный день · движение смоделировано' : 'Данные входящих событий'}</span><span>Круг · треугольник · ромб — уровни риска</span></div>
    </main>
    <aside ref={asideRef} className="aside" aria-label="Диспетчерская панель">
      <div className="aside-heading"><div className="aside-title"><Icon name="warning" size={16} /><h2>Раннее предупреждение</h2></div><div className="aside-subtitle">Прогнозируемые инциденты <span className={`count-badge${alerts.length ? ' has-incidents' : ''}`}>{buffered.value ? alerts.length : '—'}</span></div><p>Прогноз до возникновения опоздания</p>
        {selected === null && <Segmented label="Инциденты" value={incidentFilter} onChange={setIncidentFilter} options={[{ value: 'all', label: 'Все' }, { value: 'critical', label: 'Критические' }, { value: 'attention', label: 'Требуют внимания' }]} />}
      </div>
      {selected !== null ? trip?.found ? <TripPanel trip={trip} tripId={selected} demo={DEMO_MODE} updatedAt={detail.updatedAt} now={now} onClose={() => setSelected(null)} /> : <div className="selection-loading" role="status"><button className="back-button" onClick={() => setSelected(null)}>← Все инциденты</button><span>ТС {selected} · {frame.loading && replay ? 'получаем сведения…' : 'сведения недоступны'}</span></div> :
        <AlertList alerts={filteredAlerts} onSelect={selectVehicle} updatedAt={buffered.updatedAt} now={now} empty={offline ? 'Ожидаем восстановление связи с сервисом.' : !data ? 'Загружаем прогнозы…' : 'Инцидентов по выбранным условиям нет.'} />}
      <div className="aside-bottom"><span className="info-icon">i</span><p>Риск — вероятность будущего опоздания. Панель обновляется раз в 4 секунды, чтобы прогноз было удобно читать.</p></div>
      <ModelPanel demo={DEMO_MODE} />
    </aside>
    <footer className={`footer${replay ? '' : ' footer-live'}`}>
      {replay ? <><div className="playback-controls"><button disabled={!day.data || offline} onClick={toggle} className="play-button" aria-label={playing ? 'Пауза' : 'Воспроизвести'}>{playing ? 'Ⅱ' : '▶'}</button><div><strong>{data?.clock ?? '--:--'}</strong><span>{playing ? 'Воспроизведение' : 'На паузе'}</span></div><button className="speed-button" onClick={playback.cycleSpeed} aria-label="Изменить скорость">×{playback.speed}</button></div>
        <div className="timeline-wrap"><div className="timeline-heading"><span>РИСК В ТЕЧЕНИЕ ДНЯ</span><span><i className="tiny-dot" />ТС с высоким риском</span></div>{timeline.error ? <div className="timeline-error">Шкала времени недоступна <button onClick={timeline.refresh}>Повторить</button></div> : <Timeline data={timeline.data} t={playback.t} onSeek={playback.seek} highColor={settings.colors.high} />}</div><div className="timeline-hint">Выберите время<br />на шкале</div></> : <><Icon name="signal" /><strong>Мониторинг событий</strong><span className="muted">{DEMO_MODE ? 'Демонстрационный поток · синтетические данные' : 'Обновление каждые 4 секунды'}</span><button onClick={live.refresh}>Обновить</button></>}
    </footer>
  </div>
}
