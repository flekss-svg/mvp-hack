import type { TripCard } from '../api/types'
import { amount, currentText, expectedArrival, expectedDelayText, horizonText, riskText, updatedText } from '../ui/presentation'
import { ChangedValue } from './ChangedValue'

const TONES = ['low', 'mid', 'high', 'muted']
const LABELS = ['Низкий риск', 'Средний риск', 'Высокий риск', 'Нет прогноза']
export function TripPanel({ trip, tripId, updatedAt, now, onClose }: { trip: TripCard; tripId: number; updatedAt: number | null; now: number; onClose: () => void }) {
  const hasRisk = trip.risk !== null && trip.risk !== undefined
  const tone = TONES[trip.level ?? 3]
  return <section className="trip" aria-label={`Подробности ТС ${tripId}`}>
    <button className="back-button" onClick={onClose}>← Все инциденты</button>
    <div className="trip-head"><div><h2>Маршрут <span className={`route-badge badge-${trip.mode}`}>{trip.route}</span></h2><p className="trip-vehicle">{trip.mode === 'tram' ? 'Трамвай' : trip.mode === 'bus' ? 'Автобус' : 'Транспорт'} · <b>ТС {tripId}</b></p></div><span className="selected-label">Выбрано</span></div>
    <p className="trip-name">{trip.routeName}</p>
    <div className={`trip-risk-row risk-${tone}`}><span>{!hasRisk || trip.level === undefined ? 'Риск опоздания' : LABELS[trip.level]}</span><ChangedValue value={riskText(trip.risk)} /></div>
    <div className="trip-section"><h3>{trip.currentTime ? `СЕЙЧАС · ${trip.currentTime}` : 'СЕЙЧАС'}</h3><ChangedValue className="trip-statement" value={currentText(trip.delay)} /><dl><dt>Текущая остановка</dt><dd>{trip.stop || 'Не передана'}</dd>{trip.next?.[0] && <><dt>Следующая остановка</dt><dd>{trip.next[0].stop}</dd></>}<dt>Статус</dt><dd>{trip.onLine ? 'На линии' : 'Не на линии'}</dd></dl></div>
    <div className={`trip-section trip-forecast forecast-${tone}`}><div className="forecast-heading"><h3>ПРОГНОЗ</h3><span>{trip.forecastMinutes === undefined ? '' : horizonText(trip.forecastMinutes)}</span></div>
      {trip.forecastStop || trip.scheduledArrival || trip.expectedArrival || trip.forecastDelay !== undefined ? <dl><dt>Остановка</dt><dd>{trip.forecastStop ?? 'Не передана'}</dd>{trip.scheduledArrival && <><dt>По расписанию</dt><dd>{trip.scheduledArrival}</dd></>}{expectedArrival(trip.scheduledArrival, trip.expectedArrival, trip.expectedDelay ?? trip.forecastDelay) && <><dt>Ожидаемое прибытие</dt><dd>{expectedArrival(trip.scheduledArrival, trip.expectedArrival, trip.expectedDelay ?? trip.forecastDelay)}</dd></>}{expectedDelayText(trip.expectedDelay ?? trip.forecastDelay) && <><dt>Ожидаемое опоздание</dt><dd>{expectedDelayText(trip.expectedDelay ?? trip.forecastDelay)}</dd></>}</dl> : <p className="forecast-unavailable">Прогноз времени прибытия пока недоступен</p>}
      <dl><dt>Предполагаемая причина</dt><dd>{trip.forecastReason ?? 'Не передана'}</dd><dt>Проблемный участок</dt><dd>{trip.problemSegment ? `${trip.problemSegment.from} → ${trip.problemSegment.to}` : 'Не передан'}</dd></dl>
      {trip.level === 3 && <p className="muted">Рейс скоро завершится — прогноз не выдаётся.</p>}
    </div>
    {(trip.averageSpeed !== undefined || trip.dwellMinutes !== undefined) && <div className="trip-section"><h3>ДВИЖЕНИЕ</h3><dl>{trip.averageSpeed !== undefined && <><dt>Средняя скорость</dt><dd>{amount(trip.averageSpeed)} км/ч</dd></>}{trip.dwellMinutes !== undefined && <><dt>Время простоя</dt><dd>{amount(trip.dwellMinutes)} мин</dd></>}</dl></div>}
    {trip.outcome && <div className="trip-outcome">Фактический исход: {currentText(trip.outcome.delay)}</div>}
    {!!trip.next?.length && <details className="trip-next"><summary>Следующая: {trip.next[0].stop} · {trip.next[0].plan}</summary><ul>{trip.next.map((n) => <li key={`${n.stop}-${n.plan}`}><span>{n.stop}</span><time>{n.plan}</time></li>)}</ul></details>}
    <p className="trip-updated">{updatedText(updatedAt, now)}</p>
  </section>
}
