import type { Alert } from '../api/types'

interface Props {
  alerts: Alert[]
  selected: number | null
  onSelect: (tripId: number) => void
  empty: string
}

const delayText = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}`

export function AlertList({ alerts, selected, onSelect, empty }: Props) {
  // Presentation order only; never mutate the response or change server-side sorting.
  const ordered = [...alerts].sort((a, b) => b.risk - a.risk)
  return (
    <div className="alerts">
      {ordered.length === 0 ? <div className="empty-alerts"><span aria-hidden="true">—</span><p>{empty}</p></div> : (
        <ul>{ordered.map((a) => (
          <li key={a.tripId}>
            <button className={`alert${a.risk >= 90 ? ' alert-priority' : ''}${a.tripId === selected ? ' on' : ''}`}
              onClick={() => onSelect(a.tripId)} aria-pressed={a.tripId === selected}>
              <span className="alert-top">
                <span className={`route-badge badge-${a.mode}`}>{a.route}</span>
                <span className="vehicle-id">{a.mode === 'tram' ? 'Трамвай' : a.mode === 'bus' ? 'Автобус' : 'Транспорт'} · ТС {a.tripId}</span>
                <span className="alert-risk" aria-label={`Риск опоздания ${a.risk}%`}>{a.risk}<small>%</small></span>
              </span>
              <span className="alert-dest" title={`${a.stop} → ${a.dest || 'Направление не передано'}`}>
                {a.stop || 'Остановка не передана'} <span aria-hidden="true">→</span> {a.dest || 'Направление не передано'}
              </span>
              <span className="delay-comparison">
                <span className="delay-current"><span className="comparison-label">Сейчас</span><strong>{delayText(a.delay)} <small>мин</small></strong></span>
                <span className="comparison-arrow" aria-hidden="true">→</span>
                <span className="delay-forecast"><span className="comparison-label">{a.forecastMinutes !== undefined ? `Через ${a.forecastMinutes} мин` : 'Прогноз'}</span>
                  {a.forecastDelay !== undefined ? <strong>{delayText(a.forecastDelay)} <small>мин</small></strong> : <span className="forecast-unavailable">Нет данных об отклонении</span>}
                </span>
              </span>
              <span className="alert-bottom"><span className="risk-text"><i className="risk-symbol" aria-hidden="true">!</i>Высокий риск</span>
                <span className={a.risk >= 90 ? 'priority-label' : 'alert-action'}>{a.risk >= 90 ? 'В первую очередь' : 'Подробнее →'}</span>
              </span>
            </button>
          </li>
        ))}</ul>
      )}
    </div>
  )
}
