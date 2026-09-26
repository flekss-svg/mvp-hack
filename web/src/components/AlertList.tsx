import type { StableIncident } from '../ui/presentation'
import { currentText, expectedArrival, expectedDelayText, horizonText, riskText, updatedText } from '../ui/presentation'
import { ChangedValue } from './ChangedValue'
import { Icon } from './Icon'

interface Props { alerts: StableIncident[]; onSelect: (id: number) => void; empty: string; updatedAt: number | null; now: number }
export function AlertList({ alerts, onSelect, empty, updatedAt, now }: Props) {
  return <div className="alerts">{!alerts.length ? <div className="empty-alerts"><Icon name="signal" size={26} /><p>{empty}</p></div> : <ul>{alerts.map((a, index) => <li key={a.tripId}>
    <button className={`alert${index === 0 ? ' alert-hero' : ' alert-compact'}${a.critical ? ' alert-priority' : ''}`} data-trip-id={a.tripId} onClick={() => onSelect(a.tripId)}>
      <span className="alert-top"><span className={`route-badge badge-${a.mode}`} aria-label={`Маршрут ${a.route}`}>{a.route}</span><span className="vehicle-id">{a.mode === 'tram' ? 'Трамвай' : 'Автобус'} · ТС {a.tripId}</span><ChangedValue className="alert-risk" value={riskText(a.risk)} /></span>
      <span className="alert-dest" title={`${a.stop} → ${a.dest}`}><b>{a.stop || 'Остановка не передана'}</b> <span aria-hidden="true">→</span> <b>{a.dest || 'Направление не передано'}</b></span>
      <span className="incident-current"><span className="comparison-label">{a.currentTime ? `Сейчас · ${a.currentTime}` : 'Сейчас'}</span><ChangedValue value={currentText(a.delay)} /></span>
      <span className="incident-forecast"><span className="forecast-heading"><span className="comparison-label">Прогноз</span><span>{a.forecastMinutes === undefined ? '' : horizonText(a.forecastMinutes)}</span></span>
        {a.forecastStop || a.scheduledArrival || a.expectedArrival || a.forecastDelay !== undefined ? <span className="arrival-forecast"><b>{a.forecastStop || 'Остановка прогноза не передана'}</b>{a.scheduledArrival && <span><i>По расписанию</i><time>{a.scheduledArrival}</time></span>}{expectedArrival(a.scheduledArrival, a.expectedArrival, a.expectedDelay ?? a.forecastDelay) && <span><i>Ожидаемое прибытие</i><time>{expectedArrival(a.scheduledArrival, a.expectedArrival, a.expectedDelay ?? a.forecastDelay)}</time></span>}{expectedDelayText(a.expectedDelay ?? a.forecastDelay) && <span><i>Ожидаемое опоздание</i><strong>{expectedDelayText(a.expectedDelay ?? a.forecastDelay)}</strong></span>}</span> : <span className="forecast-unavailable">Прогноз времени прибытия пока недоступен</span>}</span>
      <span className="incident-context"><span><span>Причина</span><span>{a.forecastReason || 'Не передана сервисом'}</span></span><span><span>Участок</span><span>{a.problemSegment ? `${a.problemSegment.from} → ${a.problemSegment.to}` : 'Не передан сервисом'}</span></span></span>
      <span className="alert-bottom"><span className="risk-text"><Icon name="warning" size={12} />{a.critical ? 'Критический риск' : 'Высокий риск'}</span><span className="incident-age">{updatedText(updatedAt, now)}</span></span>
    </button>
  </li>)}</ul>}</div>
}
