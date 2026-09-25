import { useCallback, useEffect, useRef, useState } from 'react'
import { api, DEMO_MODE } from './api/client'
import type { Kpi, TripCard } from './api/types'
import { useResource } from './hooks/useResource'
import { usePlayback } from './hooks/usePlayback'
import { AlertList } from './components/AlertList'
import { Header } from './components/Header'
import { Legend } from './components/Legend'
import { TransportMap } from './components/TransportMap'
import { ModelPanel } from './components/ModelPanel'
import { Segmented } from './components/Segmented'
import { Timeline } from './components/Timeline'
import { TripPanel } from './components/TripPanel'

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
  const [selected, setSelected] = useState<number | null>(null)
  const [focusToken, setFocusToken] = useState(0)
  const asideRef = useRef<HTMLElement>(null)
  useEffect(() => { if (selected !== null) asideRef.current?.scrollTo({ top: 0 }) }, [selected, focusToken])
  const replay = source === 'replay'
  const day = useResource((signal) => api.day(signal), [], { enabled: replay })
  const playback = usePlayback(day.data ? { tMin: day.data.tMin, tMax: day.data.tMax } : null, replay, DEMO_MODE)
  const frame = useResource(
    async (signal) => {
      const result = await api.frame({ t: playback.t!, mode, minLevel, trip: selected }, signal)
      return { ...result, trip: result.trip ? { ...result.trip, tripId: selected ?? undefined } : null }
    },
    // Poll sequentially while playing: slow responses must not be aborted by each clock tick.
    [playback.playing ? null : playback.t, mode, minLevel, selected],
    { enabled: replay && playback.t !== null && !!day.data, pollMs: playback.playing ? 120 : undefined },
  )
  const timeline = useResource((signal) => api.timeline(mode, signal), [mode], { enabled: replay })
  const live = useResource((signal) => api.live(signal), [], { pollMs: 4000, enabled: !replay })
  const offline = replay ? !!(day.error || frame.error) : !!live.error
  const data = replay ? frame.data : live.data
  const alerts = data?.alerts ?? []
  const mapDay = replay ? day.data : live.data?.map?.day ?? null
  const mapFrame = replay ? frame.data : live.data?.map?.frame ?? null
  const updatedAt = replay ? frame.updatedAt : live.updatedAt
  const selectedAlert = alerts.find((a) => a.tripId === selected)
  const liveTrip: TripCard | null = selected === null ? null : live.data?.trips?.[selected] ?? (selectedAlert ? {
    found: true, onLine: true, tripId: selectedAlert.tripId, route: selectedAlert.route,
    routeName: selectedAlert.dest, mode: selectedAlert.mode, stop: selectedAlert.stop,
    delay: selectedAlert.delay, risk: selectedAlert.risk,
  } : null)
  // A previous HTTP frame may still contain the previously selected trip.
  const trip = replay ? (frame.data?.trip?.tripId === selected ? frame.data.trip : null) : liveTrip
  const { playing, toggle } = playback
  const selectVehicle = useCallback((id: number | null) => {
    setSelected(id)
    setFocusToken((n) => n + 1)
    if (id !== null && replay && playing) toggle()
  }, [replay, playing, toggle])
  const retry = () => { day.refresh(); frame.refresh(); timeline.refresh(); live.refresh() }
  const dateLabel = day.data ? new Date(`${day.data.date}T12:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) : 'Записанный день'

  return (
    <div className="app">
      <Header clock={data?.clock ?? '--:--'} kpi={data?.kpi ?? EMPTY_KPI}
        status={DEMO_MODE ? 'DEMO' : offline ? 'OFFLINE' : !data ? 'CONNECTING' : replay ? 'REPLAY' : 'LIVE'}
        subtitle={replay ? `${dateLabel} · воспроизведение` : 'Мониторинг входящих событий'} />

      <div className="workspace-toolbar">
        <div className="toolbar-title"><strong>Москва</strong></div>
        <div className="toolbar-filters">
          {replay ? <>
            <Segmented label="Вид транспорта" value={mode} onChange={(v) => { setMode(v); setSelected(null) }}
              options={[{ value: 'all', label: 'Весь транспорт' }, { value: 'bus', label: 'Автобусы' }, { value: 'tram', label: 'Трамваи' }]} />
            <button className={`risk-filter${minLevel === 2 ? ' active' : ''}`} aria-pressed={minLevel === 2}
              onClick={() => { setMinLevel((n) => n === 2 ? 0 : 2); setSelected(null) }}><span className="risk-symbol" aria-hidden="true">!</span>Только высокий риск</button>
          </> : <span className="live-caption"><span className="status-dot" />События сервиса · обновление каждые 4 с</span>}
        </div>
        {DEMO_MODE && <span className="demo-badge" title="Все маршруты, ТС и прогнозы синтетические">DEMO DATA</span>}
        <div className="toolbar-source">
          <Segmented label="Источник данных" value={source} onChange={(v) => { setSource(v); setSelected(null) }}
            options={[{ value: 'replay', label: 'Записанный день' }, { value: 'live', label: 'Live' }]} />
        </div>
      </div>

      <main className="stage" aria-label="Карта и обстановка">
        <div className="map-body">
          <TransportMap day={mapDay} frame={mapFrame} selected={selected} focusToken={focusToken}
            focusReady={!replay || frame.data?.trip?.tripId === selected} onSelect={selectVehicle} />
          {offline && <div className="service-state" role="alert">
            <span className="state-symbol">↻</span><h2>Сервис данных недоступен</h2>
            <p>{data ? 'Показаны последние полученные данные. Обновление приостановлено.' : 'Не удалось получить оперативную обстановку. Попробуйте подключиться ещё раз.'}</p>
            <button className="primary" onClick={retry}>Повторить</button>
          </div>}
          {!offline && !data && <div className="service-state loading-state" role="status"><span className="loader" /><h2>Загружаем обстановку</h2><p>Подключение к сервису данных…</p></div>}
          {!replay && live.data && !mapDay && !offline && <div className="service-state map-empty">
            <span className="state-symbol">⌖</span><h2>В событиях нет координат</h2>
            <p>Live API передаёт показатели и тревоги. Доступные сведения о ТС — в панели справа.</p>
          </div>}
          {mapDay && <Legend threshold={mapDay.threshold} />}
          {selected !== null && <div className="selection-chip"><span className="selection-dot" />Выбрано ТС <b>{selected}</b>
            <button aria-label="Снять выбор ТС" onClick={() => setSelected(null)}>×</button></div>}
        </div>
        <div className="map-statusbar"><span className="map-count">{mapFrame ? `${mapFrame.vehicles.id.length} ТС на карте` : 'Ожидание координат'}</span><span>{DEMO_MODE ? 'Демонстрационные маршруты и прогнозы' : replay ? 'Записанный день · движение смоделировано' : 'Данные входящих событий'}</span>
          <span>{offline ? 'Нет соединения' : updatedAt ? `Получено ${new Date(updatedAt).toLocaleTimeString('ru-RU')}` : 'Ожидание данных'}</span></div>
      </main>

      <aside ref={asideRef} className="aside" aria-label="Диспетчерская панель">
        <div className="aside-heading"><h2>Раннее предупреждение</h2><div className="aside-subtitle">Прогнозируемые инциденты <span className={`count-badge${alerts.length ? ' has-incidents' : ''}`}>{data ? alerts.length : '—'}</span></div>
          <p>{offline ? 'Данные не обновляются' : replay ? 'Пока по графику, но есть риск опоздания' : 'Высокий риск по поступившим событиям'}</p></div>
        {selected !== null && (trip?.found ? <TripPanel trip={trip} tripId={selected} onClose={() => setSelected(null)} /> :
          <div className="panel selection-loading" role="status"><button className="back-button" onClick={() => setSelected(null)}>← Ко всем инцидентам</button><span>ТС {selected} · {frame.loading && replay ? 'получаем сведения…' : 'сведения недоступны'}</span></div>)}
        {selected === null && <AlertList alerts={alerts} selected={selected} onSelect={selectVehicle}
          empty={offline ? 'Ожидаем восстановление связи с сервисом.' : !data ? 'Загружаем прогнозы…' : 'Инцидентов по текущим условиям нет.'} />
        }
        <div className="aside-bottom"><span className="info-icon">i</span><p>Риск — вероятность будущего опоздания. Текущее отклонение показано отдельно.</p></div>
        <ModelPanel demo={DEMO_MODE} />
      </aside>

      <footer className={`footer${replay ? '' : ' footer-live'}`}>
        {replay ? <>
          <div className="playback-controls"><button disabled={!day.data || offline} onClick={playback.toggle} className="play-button" aria-label={playback.playing ? 'Пауза' : 'Воспроизвести'}>{playback.playing ? 'Ⅱ' : '▶'}</button>
            <div><strong>{data?.clock ?? '--:--'}</strong><span>{playback.playing ? 'Воспроизведение' : 'На паузе'}</span></div>
            <button className="speed-button" onClick={playback.cycleSpeed} aria-label="Изменить скорость">×{playback.speed}</button></div>
          <div className="timeline-wrap"><div className="timeline-heading"><span>РИСК В ТЕЧЕНИЕ ДНЯ</span><span><i className="tiny-dot" />ТС с высоким риском</span></div>
            {timeline.error ? <div className="timeline-error">Шкала времени недоступна <button onClick={timeline.refresh}>Повторить</button></div> : <Timeline data={timeline.data} t={playback.t} onSeek={playback.seek} />}</div>
          <div className="timeline-hint">Выберите время<br />на шкале</div>
        </> : <><span className="status-dot" /><strong>Мониторинг событий</strong><span className="muted">{DEMO_MODE ? 'Демонстрационный поток · синтетические данные' : 'Автоматическое обновление каждые 4 секунды'}</span><button onClick={live.refresh}>Обновить</button></>}
      </footer>
    </div>
  )
}
