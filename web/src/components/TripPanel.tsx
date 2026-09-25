import type { TripCard } from '../api/types'
import { amount, currentText, forecastText, horizonText, riskText, updatedText } from '../ui/presentation'
import { ChangedValue } from './ChangedValue'

const TONES = ['low', 'mid', 'high', 'muted']
const LABELS = ['Низкий риск', 'Средний риск', 'Высокий риск', 'Нет прогноза']
export function TripPanel({ trip, tripId, demo, updatedAt, now, onClose }: { trip: TripCard; tripId: number; demo: boolean; updatedAt: number | null; now: number; onClose: () => void }) {
  const hasRisk = trip.risk !== null && trip.risk !== undefined
  const tone = TONES[trip.level ?? 3]
  return <section className="trip" aria-label={`Подробности ТС ${tripId}`}>
    <button className="back-button" onClick={onClose}>← Все инциденты</button>
    <div className="trip-head"><div><h2>Маршрут <span className={`route-badge badge-${trip.mode}`}>{trip.route}</span></h2><p className="trip-vehicle">{trip.mode === 'tram' ? 'Трамвай' : trip.mode === 'bus' ? 'Автобус' : 'Транспорт'} · <b>ТС {tripId}</b></p></div><span className="selected-label">Выбрано</span></div>
    <p className="trip-name">{trip.routeName}</p>
    <div className={`trip-risk-row risk-${tone}`}><span>{!hasRisk ? 'Нет прогноза' : trip.level === undefined ? 'Риск опоздания' : LABELS[trip.level]}</span><ChangedValue value={riskText(trip.risk)} /></div>
    <div className="trip-section"><h3>СЕЙЧАС</h3><ChangedValue className="trip-statement" value={currentText(trip.delay)} /><dl><dt>Текущая остановка</dt><dd>{trip.stop || 'Не передана'}</dd><dt>Статус</dt><dd>{trip.onLine ? 'На линии' : 'Не на линии'}</dd></dl></div>
    <div className={`trip-section trip-forecast forecast-${tone}`}><div className="forecast-heading"><h3>ПРОГНОЗ</h3><span>{horizonText(trip.forecastMinutes)}</span></div><ChangedValue className="trip-statement" value={forecastText(trip.delay, trip.forecastDelay)} />
      <dl><dt>Время события</dt><dd>{trip.forecastTime ?? 'Не передано'}</dd><dt>Предполагаемая причина</dt><dd>{trip.forecastReason ?? 'Не передана'}</dd><dt>Проблемный участок</dt><dd>{trip.problemSegment ? `${trip.problemSegment.from} → ${trip.problemSegment.to}` : 'Не передан'}</dd></dl>
      {trip.level === 3 && <p className="muted">Рейс скоро завершится — прогноз не выдаётся.</p>}
    </div>
    {(trip.averageSpeed !== undefined || trip.dwellMinutes !== undefined) && <div className="trip-section"><h3>ДВИЖЕНИЕ</h3><dl>{trip.averageSpeed !== undefined && <><dt>Средняя скорость</dt><dd>{amount(trip.averageSpeed)} км/ч</dd></>}{trip.dwellMinutes !== undefined && <><dt>Время простоя</dt><dd>{amount(trip.dwellMinutes)} мин</dd></>}</dl></div>}
    {trip.outcome && <div className="trip-outcome">Фактический исход: {currentText(trip.outcome.delay)}</div>}
    {!!trip.next?.length && <details className="trip-next"><summary>Следующая: {trip.next[0].stop} · {trip.next[0].plan}</summary><ul>{trip.next.map((n) => <li key={`${n.stop}-${n.plan}`}><span>{n.stop}</span><time>{n.plan}</time></li>)}</ul></details>}
    {demo && <div className="demo-actions"><h3>Возможные действия</h3><p>Демонстрационные рекомендации диспетчеру. Решение остаётся за вами.</p><ul><li>Проверить интервал движения</li><li>Контролировать следующий участок</li><li>Подготовить резервное ТС</li></ul></div>}
    <p className="trip-updated">{updatedText(updatedAt, now)}</p>
  </section>
}
