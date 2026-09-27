import { useState } from 'react'
import { api } from './api/client'
import type { Frame, Kpi } from './api/types'
import { useResource } from './hooks/useResource'
import { usePlayback } from './hooks/usePlayback'
import { AlertList } from './components/AlertList'
import { Header } from './components/Header'
import { Legend } from './components/Legend'
import { MapCanvas } from './components/MapCanvas'
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

const formatDay = (iso: string) =>
  new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' })

export default function App() {
  const [source, setSource] = useState<Source>('replay')
  const [mode, setMode] = useState('all')
  const [minLevel, setMinLevel] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)

  const day = useResource((signal) => api.day(signal), [])
  const bounds = day.data ? { tMin: day.data.tMin, tMax: day.data.tMax } : null
  const playback = usePlayback(bounds)
  const replayOn = source === 'replay'

  const frame = useResource(
    (signal) => api.frame({ t: playback.t!, mode, minLevel, trip: selected }, signal),
    [playback.t, mode, minLevel, selected],
    { enabled: replayOn && playback.t !== null },
  )
  const timeline = useResource((signal) => api.timeline(mode, signal), [mode], {
    enabled: replayOn,
  })
  const live = useResource((signal) => api.live(signal), [], {
    pollMs: 4000,
    enabled: source === 'live',
  })
  const liveFrame: Frame | null = live.data
    ? {
        t: 0,
        clock: live.data.clock,
        raining: false,
        kpi: live.data.kpi,
        vehicles: live.data.vehicles ?? { id: [], lon: [], lat: [], level: [], risk: [], late: [] },
        slowSegments: [],
        alerts: live.data.alerts,
        trip: null,
      }
    : null

  const blocker = replayOn ? day.error : live.error
  const kpi = (replayOn ? frame.data?.kpi : live.data?.kpi) ?? EMPTY_KPI
  const clock = (replayOn ? frame.data?.clock : live.data?.clock) ?? '--:--'
  const subtitle = replayOn
    ? day.data
      ? `${formatDay(day.data.date)} · записанный день${frame.data?.raining ? ' · дождь' : ''}`
      : 'Загрузка дня…'
    : `Live · прогноз по событиям, которые прислал сервис${live.data ? ` · ${live.data.tracked} рейсов` : ''}`

  return (
    <div className={`app${replayOn ? '' : ' app-live'}`}>
      <Header clock={clock} subtitle={subtitle} kpi={kpi} />

      <div className="stage">
        {day.data ? (
          <MapCanvas
            day={day.data}
            frame={replayOn ? frame.data : liveFrame}
            selected={replayOn ? selected : null}
            onSelect={replayOn ? setSelected : () => setSelected(null)}
          />
        ) : (
          <div className="stage-note">{blocker ? blocker.message : 'Загрузка карты…'}</div>
        )}
        {day.data && (
          <>
            <p className="banner">
              {replayOn
                ? 'Расписание и остановки — реальные (data.mos.ru). Движение в записанном дне смоделировано.'
                : 'Live: координаты приходят по NDTP, прогноз задержки — из выделенного ML-сервиса.'}
            </p>
            <Legend threshold={day.data.threshold} />
          </>
        )}
      </div>

      <aside className="aside">
        <section className="panel">
          <h2>Источник данных</h2>
          <Segmented
            label="Источник данных"
            value={source}
            onChange={(v) => {
              setSource(v)
              setSelected(null)
            }}
            options={[
              { value: 'replay', label: 'Записанный день' },
              { value: 'live', label: 'Live (события)' },
            ]}
          />
          {!replayOn && live.error && <p className="empty">{live.error.message}</p>}
        </section>

        {replayOn && (
          <section className="panel">
            <h2>Показывать</h2>
            <Segmented
              label="Вид транспорта"
              value={mode}
              onChange={setMode}
              options={[
                { value: 'all', label: 'Все' },
                { value: 'bus', label: 'Автобусы' },
                { value: 'tram', label: 'Трамваи' },
              ]}
            />
            <Segmented
              label="Уровень риска"
              value={minLevel}
              onChange={setMinLevel}
              options={[
                { value: 0, label: 'Все машины' },
                { value: 2, label: 'Только высокий риск' },
              ]}
            />
          </section>
        )}

        {replayOn && frame.data?.trip?.found && (
          <TripPanel trip={frame.data.trip} onClose={() => setSelected(null)} />
        )}

        <AlertList
          title={replayOn ? 'Пока по графику, но опоздают' : 'Высокий риск сейчас'}
          alerts={(replayOn ? frame.data?.alerts : live.data?.alerts) ?? []}
          selected={selected}
          onSelect={replayOn ? setSelected : undefined}
          empty={
            replayOn
              ? 'Сейчас таких машин нет — перемотайте на часы пик или запустите воспроизведение.'
              : 'Сервис пока не получил событий, по которым стоит поднимать тревогу.'
          }
        />

        <ModelPanel />
      </aside>

      {replayOn && (
        <footer className="footer">
          <div className="controls">
            <button onClick={playback.toggle} className="primary">
              {playback.playing ? '❚❚ Пауза' : '▶ Пуск'}
            </button>
            <button onClick={playback.cycleSpeed}>×{playback.speed}</button>
          </div>
          <Timeline data={timeline.data} t={playback.t} onSeek={playback.seek} />
        </footer>
      )}
    </div>
  )
}
