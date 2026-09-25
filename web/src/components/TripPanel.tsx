import type { TripCard } from '../api/types'

const LEVEL_CLASS = ['low', 'mid', 'high', 'muted']
const LEVEL_LABEL = ['Низкий риск', 'Средний риск', 'Высокий риск', 'Нет прогноза']
const delayText = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}`

export function TripPanel({ trip, tripId, onClose }: { trip: TripCard; tripId: number; onClose: () => void }) {
  const hasRisk = trip.risk !== null && trip.risk !== undefined
  const tone = LEVEL_CLASS[trip.level ?? 3]
  return (
    <section className="trip" aria-label={`Подробности ТС ${tripId}`}>
      <button className="back-button" onClick={onClose}>← Ко всем инцидентам</button>
      <div className="trip-head"><div><h2>Маршрут <span className={`route-badge badge-${trip.mode}`}>{trip.route}</span></h2>
        <p className="trip-vehicle">{trip.mode === 'tram' ? 'Трамвай' : trip.mode === 'bus' ? 'Автобус' : 'Транспорт'} · <b>ТС {tripId}</b></p></div><span className="selected-label">Выбрано</span></div>
      <p className="trip-name">{trip.routeName}</p>
      <div className={`trip-risk-row risk-${tone}`}><span>{!hasRisk ? 'Нет прогноза' : trip.level !== undefined ? LEVEL_LABEL[trip.level] : 'Риск опоздания'}</span><strong>{hasRisk ? `${trip.risk}%` : '—'}</strong></div>
      <div className="trip-section"><h3>СЕЙЧАС</h3>
        <dl><dt>Остановка</dt><dd>{trip.stop || 'Нет данных'}</dd><dt>Статус</dt><dd>{trip.onLine ? 'На линии' : 'Не на линии'}</dd></dl>
        <div className="trip-deviation"><span>Текущее отклонение</span>{trip.delay !== undefined ? <strong>{delayText(trip.delay)} <small>мин</small></strong> : <span>Нет данных</span>}</div>
      </div>
      <div className={`trip-section trip-forecast forecast-${tone}`}><h3>ПРОГНОЗ</h3>
        <dl><dt>Через</dt><dd>{trip.forecastMinutes !== undefined ? `${trip.forecastMinutes} мин` : 'Не передано сервисом'}</dd></dl>
        <div className="trip-deviation"><span>Ожидаемое отклонение</span>{trip.forecastDelay !== undefined ? <strong>{delayText(trip.forecastDelay)} <small>мин</small></strong> : <span className="forecast-unavailable">Не передано сервисом</span>}</div>
        {trip.level === 3 && <p className="muted">Рейс скоро завершится — прогноз не выдаётся.</p>}
      </div>
      {trip.outcome && <div className="trip-outcome">Фактический исход: <b>{trip.outcome.late ? 'опоздал' : 'успел'}</b> · {delayText(trip.outcome.delay)} мин</div>}
      {!!trip.next?.length && <details className="trip-next"><summary>Следующие остановки <span>{trip.next.length}</span></summary><ul>{trip.next.map((n) => <li key={`${n.stop}-${n.plan}`}><span>{n.stop}</span><time>{n.plan}</time></li>)}</ul></details>}
    </section>
  )
}
