import type { StableIncident } from '../ui/presentation'
import { currentText, forecastText, horizonText, riskText, updatedText } from '../ui/presentation'
import { ChangedValue } from './ChangedValue'
import { Icon } from './Icon'

interface Props { alerts: StableIncident[]; onSelect: (id: number) => void; empty: string; updatedAt: number | null; now: number }
export function AlertList({ alerts, onSelect, empty, updatedAt, now }: Props) {
  return <div className="alerts">{!alerts.length ? <div className="empty-alerts"><Icon name="signal" size={26} /><p>{empty}</p></div> : <ul>{alerts.map((a) => <li key={a.tripId}>
    <button className={`alert${a.critical ? ' alert-priority' : ''}`} data-trip-id={a.tripId} onClick={() => onSelect(a.tripId)}>
      <span className="alert-top"><span className={`route-badge badge-${a.mode}`} aria-label={`Маршрут ${a.route}`}>{a.route}</span><span className="vehicle-id">{a.mode === 'tram' ? 'Трамвай' : 'Автобус'} · ТС {a.tripId}</span><ChangedValue className="alert-risk" value={riskText(a.risk)} /></span>
      <span className="alert-dest" title={`${a.stop} → ${a.dest}`}>{a.stop || 'Остановка не передана'} <span aria-hidden="true">→</span> {a.dest || 'Направление не передано'}</span>
      <span className="incident-current"><span className="comparison-label">Сейчас</span><ChangedValue value={currentText(a.delay)} /></span>
      <span className="incident-forecast"><span className="forecast-heading"><span className="comparison-label">Прогноз</span><span>{horizonText(a.forecastMinutes)}</span></span><ChangedValue value={forecastText(a.delay, a.forecastDelay)} /></span>
      <span className="incident-context"><span><span>Причина</span><span>{a.forecastReason || 'Не передана сервисом'}</span></span><span><span>Участок</span><span>{a.problemSegment ? `${a.problemSegment.from} → ${a.problemSegment.to}` : 'Не передан сервисом'}</span></span></span>
      <span className="alert-bottom"><span className="risk-text"><Icon name="warning" size={12} />{a.critical ? 'Критический риск' : 'Высокий риск'}</span><span className="incident-age">{updatedText(updatedAt, now)}</span></span>
    </button>
  </li>)}</ul>}</div>
}
