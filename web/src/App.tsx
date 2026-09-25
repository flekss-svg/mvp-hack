import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, LIVE_TELEMETRY_ENABLED } from './api/client'
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
import { TransportMap } from './components/TransportMap'
import { ModelPanel } from './components/ModelPanel'
import { Segmented } from './components/Segmented'
import { Timeline } from './components/Timeline'
import { TripPanel } from './components/TripPanel'
import { DisplaySettings } from './components/DisplaySettings'
import { VehicleSearch } from './components/VehicleSearch'
import { ConnectionStatus } from './components/ConnectionStatus'
import { Icon } from './components/Icon'
import { FleetDrawer } from './components/FleetDrawer'
import { liveVehicles, replaySlowSegments, replayVehicles } from './maps/vehicles'
import { UI_PREVIEW_ALERTS, UI_PREVIEW_DAY, UI_PREVIEW_SLOW_SEGMENTS, UI_PREVIEW_SNAPSHOT, UI_PREVIEW_TIMELINE, UI_PREVIEW_TRIPS, UI_PREVIEW_VEHICLES } from './ui/preview'

type Source = 'simulation' | 'live'
const EMPTY_KPI: Kpi[] = [
  { key: 'onLine', label: 'на линии', value: '—' },
  { key: 'high', label: 'высокий риск', value: '—', tone: 'high' },
  { key: 'late', label: 'уже опаздывают', value: '—' },
  { key: 'hit', label: 'ранних тревог сбылось', value: '—' },
]

export default function App() {
  const uiPreview = import.meta.env.DEV && new URLSearchParams(window.location.search).get('uiPreview') === '1'
  const previewUpdatedAt = useRef(Date.now() - 3000).current
  const previewMapUpdatedAt = useRef(Date.now() - 2000).current
  const [source, setSource] = useState<Source>('simulation')
  const [mode, setMode] = useState('all')
  const [minLevel, setMinLevel] = useState(0)
  const [incidentFilter, setIncidentFilter] = useState('all')
  const [selected, setSelected] = useState<string | number | null>(null)
  const [fleetOpen, setFleetOpen] = useState(false)
  const [focusToken, setFocusToken] = useState(0)
  const asideRef = useRef<HTMLElement>(null)
  const { settings, setSettings } = useDisplaySettings()
  const now = useNow()
  useEffect(() => { if (selected !== null) asideRef.current?.scrollTo({ top: 0 }) }, [selected, focusToken])
  const replay = source === 'simulation'
  const day = useResource((signal) => api.day(signal), [], { enabled: replay && !uiPreview })
  const playback = usePlayback(day.data ? { tMin: day.data.tMin, tMax: day.data.tMax } : null, replay)
  const frame = useResource(async (signal) => {
    const trip = typeof selected === 'number' ? selected : null
    const result = await api.frame({ t: playback.t!, mode, trip }, signal)
    return { ...result, trip: result.trip ? { ...result.trip, tripId: trip ?? undefined } : null }
  }, [playback.playing ? null : playback.t, mode, selected], {
    enabled: replay && !uiPreview && playback.t !== null && !!day.data, pollMs: playback.playing ? 120 : undefined,
  })
  const timeline = useResource((signal) => api.timeline(mode, signal), [mode], { enabled: replay && !uiPreview })
  const live = useResource((signal) => api.live(signal), [], { pollMs: 4000, enabled: !replay && LIVE_TELEMETRY_ENABLED })
  const offline = !uiPreview && (replay ? !!(day.error || frame.error) : !!live.error)
  // Every layout component receives this single view model; preview only swaps its source in development.
  const realData = replay ? frame.data : live.data
  const dashboardData = uiPreview ? UI_PREVIEW_SNAPSHOT : realData
  const mapDay = uiPreview ? UI_PREVIEW_DAY : replay ? day.data : null
  const rawFrame = uiPreview ? null : replay ? frame.data : null
  const updatedAt = uiPreview ? previewUpdatedAt : replay ? frame.updatedAt : live.updatedAt
  const scope = `${source}:${mode}:${uiPreview ? 'preview' : 'data'}`
  const buffered = useBufferedSnapshot<{ alerts: Alert[]; kpi: Kpi[] }>(dashboardData, updatedAt, scope, replay && !playback.playing)
  const order = useRef<{ scope: string; alerts: StableIncident[] }>({ scope, alerts: [] })
  const alerts = useMemo(() => {
    const incoming = (uiPreview ? UI_PREVIEW_ALERTS : buffered.value?.alerts ?? []).filter((a) => mode === 'all' || a.mode === mode)
    const next = stableIncidents(order.current.scope === scope ? order.current.alerts : [], incoming)
    order.current = { scope, alerts: next }
    return next
  }, [uiPreview, buffered.value, scope, mode])
  const filteredAlerts = alerts.filter((a) => incidentFilter === 'all' || (incidentFilter === 'critical' ? a.critical : !a.critical))
  const liveTrip = useMemo<TripCard | null>(() => {
    if (typeof selected !== 'number') return null
    const detailed = live.data?.trips?.[selected]
    if (detailed) return detailed
    const a = live.data?.alerts.find((v) => v.tripId === selected)
    return a ? { ...a, found: true, onLine: true, routeName: a.dest, level: 2 } : null
  }, [live.data, selected])
  const currentTrip = uiPreview && typeof selected === 'number' ? UI_PREVIEW_TRIPS[selected] ?? null : replay ? (frame.data?.trip?.tripId === selected ? frame.data.trip : null) : liveTrip
  const detail = useBufferedSnapshot(currentTrip, updatedAt, `${source}:${selected}`, replay && !playback.playing)
  const trip = detail.value
  const { playing, toggle } = playback
  useEffect(() => { if (offline && playing) toggle() }, [offline, playing, toggle])
  const selectVehicle = useCallback((id: string | number | null) => {
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
    const known = new Map((dashboardData?.alerts ?? []).map((a) => [a.tripId, { tripId: a.tripId, route: a.route, mode: a.mode }]))
    rawFrame?.vehicles.id.forEach((id, i) => { if (!known.has(id)) known.set(id, { tripId: id, route: rawFrame.vehicles.route?.[i] ?? '', mode: rawFrame.vehicles.mode?.[i] ?? '' }) })
    return [...known.values()]
  }, [dashboardData, rawFrame])
  const mapVehicles = useMemo(() => uiPreview ? UI_PREVIEW_VEHICLES : replay ? replayVehicles(mapFrame) : liveVehicles(live.data?.vehicles), [uiPreview, replay, mapFrame, live.data?.vehicles])
  const mapSelected = uiPreview && selected === null ? 1011 : selected
  const retry = () => { day.refresh(); frame.refresh(); timeline.refresh(); live.refresh() }
  return <div className={`app density-${settings.density}`}>
    <Header clock={dashboardData?.clock ?? '--:--'} kpi={buffered.value?.kpi ?? EMPTY_KPI}
      status={offline ? 'OFFLINE' : !dashboardData && replay && !uiPreview ? 'CONNECTING' : replay ? 'SIMULATION' : 'WAITING'}
      subtitle={replay ? 'Записанный сценарий движения' : 'Положение транспорта появится после подключения live-потока'} />
    <main className="stage" aria-label="Карта и обстановка">
      <div className="map-body">
        <TransportMap day={mapDay} vehicles={mapVehicles} slowSegments={uiPreview ? UI_PREVIEW_SLOW_SEGMENTS : replaySlowSegments(mapFrame)} selected={mapSelected} focusToken={focusToken} display={settings} onSelect={selectVehicle} />
        <div className="workspace-toolbar">
          <div className="toolbar-title"><Icon name="pin" size={14} /><strong>Москва</strong></div>
          <div className="toolbar-filters">
            <Segmented label="Вид транспорта" value={mode} onChange={(v) => { setMode(v); setSelected(null) }} options={[{ value: 'all', label: 'Все' }, { value: 'bus', label: 'Автобусы' }, { value: 'tram', label: 'Трамваи' }]} />
            <Segmented label="Уровень риска" value={minLevel} onChange={setMinLevel} options={[{ value: 0, label: 'Все риски' }, { value: 1, label: 'Средний+' }, { value: 2, label: 'Высокий' }]} />
          </div>
          <VehicleSearch vehicles={searchVehicles} onSelect={searchSelect} />
          <button className="fleet-trigger" onClick={() => setFleetOpen(true)}>Весь транспорт</button>
        </div>
        <div className="workspace-actions"><div className="toolbar-source"><Segmented label="Источник данных" value={source} onChange={(v) => { setSource(v); setSelected(null) }} options={[{ value: 'simulation', label: 'Симуляция' }, { value: 'live', label: 'Live' }]} /></div><DisplaySettings settings={settings} onChange={setSettings} /></div>
        {!offline && <div className="connection-overlay"><ConnectionStatus updatedAt={uiPreview ? previewMapUpdatedAt : updatedAt} now={now} offline={offline} paused={replay && !playing && !uiPreview} /></div>}
        {!uiPreview && offline && !dashboardData && <div className="offline-floating" role="alert"><span className="status-dot" /><div><strong>Нет соединения</strong><span>Данные временно недоступны</span></div><button onClick={retry}>Повторить</button></div>}
        {!uiPreview && !offline && !dashboardData && replay && <div className="service-state loading-state" role="status"><span className="loader" /><h2>Загружаем записанный сценарий</h2><p>Подключение к Replay-сервису…</p></div>}
        {!replay && <div className="telemetry-wait" role="status"><span className="status-dot" /><div><strong>ОЖИДАНИЕ ТЕЛЕМЕТРИИ</strong><span>Положение транспорта появится после подключения live-потока</span></div></div>}
        {mapDay && <Legend threshold={mapDay.threshold} />}
        {selected !== null && <div className="selection-chip"><span className="selection-dot" />Выбрано ТС <b>{selected}</b><button aria-label="Снять выбор ТС" onClick={() => setSelected(null)}>×</button></div>}
        <aside ref={asideRef} className="aside" aria-label="Диспетчерская панель">
          <div className="aside-heading"><div className="aside-title"><Icon name="warning" size={16} /><h2>Раннее предупреждение</h2></div><div className="aside-subtitle">Активные инциденты <span className={`count-badge${alerts.length ? ' has-incidents' : ''}`}>{uiPreview || buffered.value ? alerts.length : '—'}</span></div><p>Прогнозируемые отклонения движения</p>
            {selected === null && <Segmented label="Инциденты" value={incidentFilter} onChange={setIncidentFilter} options={[{ value: 'all', label: 'Все' }, { value: 'critical', label: 'Критические' }, { value: 'attention', label: 'Требуют внимания' }]} />}
          </div>
          <div className="incident-scroll">{selected !== null ? trip?.found && typeof selected === 'number' ? <TripPanel trip={trip} tripId={selected} updatedAt={detail.updatedAt} now={now} onClose={() => setSelected(null)} /> : <div className="selection-loading" role="status"><button className="back-button" onClick={() => setSelected(null)}>← Все инциденты</button><span>ТС {selected} · {frame.loading && replay ? 'получаем сведения…' : 'сведения недоступны'}</span></div> : <AlertList alerts={filteredAlerts} onSelect={selectVehicle} updatedAt={updatedAt} now={now} empty={offline ? 'Ожидаем восстановление связи с сервисом.' : !replay ? 'Ожидание потока телеметрии. Проблемные ТС появятся здесь после подключения live-данных.' : !dashboardData ? 'Загружаем прогнозы…' : 'Сейчас нет прогнозируемых критических отклонений'} />}<div className="aside-bottom"><span className="info-icon">i</span><p>Риск — вероятность будущего опоздания. Панель обновляется раз в 4 секунды, чтобы прогноз было удобно читать.</p></div><ModelPanel demo={false} /></div>
        </aside>
        {fleetOpen && <FleetDrawer vehicles={mapVehicles} onSelect={selectVehicle} onClose={() => setFleetOpen(false)} />}
        <footer className={`footer${replay ? '' : ' footer-live'}`}>{replay ? <><div className="playback-controls"><button disabled={(!day.data && !uiPreview) || offline} onClick={uiPreview ? undefined : toggle} className="play-button" aria-label={uiPreview || playing ? 'Пауза' : 'Воспроизвести'}>{uiPreview || playing ? 'Ⅱ' : '▶'}</button><div><strong>{dashboardData?.clock ?? '--:--'}</strong><span>{uiPreview || playing ? 'Воспроизведение' : 'На паузе'}</span></div><button className="speed-button" onClick={uiPreview ? undefined : playback.cycleSpeed} aria-label="Изменить скорость">×{uiPreview ? 10 : playback.speed}</button></div><div className="timeline-wrap"><div className="timeline-heading"><span>РИСК В ТЕЧЕНИЕ ДНЯ</span><span><i className="tiny-dot" />ТС с высоким риском</span></div>{!uiPreview && timeline.error ? <div className="timeline-error">Шкала времени недоступна <button onClick={timeline.refresh}>Повторить</button></div> : <Timeline data={uiPreview ? UI_PREVIEW_TIMELINE : timeline.data} t={uiPreview ? 492 : playback.t} onSeek={uiPreview ? () => {} : playback.seek} highColor={settings.colors.high} />}</div><div className="timeline-hint">Выберите время<br />на шкале</div></> : <><Icon name="signal" /><strong>Ожидание телеметрии</strong><span className="muted">Live-поток ещё не подключён</span>{LIVE_TELEMETRY_ENABLED && <button onClick={live.refresh}>Обновить</button>}</>}</footer>
      </div>
    </main>
  </div>
}
