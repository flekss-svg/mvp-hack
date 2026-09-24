import type { TripCard } from '../api/types'

const LEVEL_CLASS = ['low', 'mid', 'high', 'muted']

export function TripPanel({ trip, onClose }: { trip: TripCard; onClose: () => void }) {
  return (
    <section className="panel trip">
      <div className="trip-head">
        <h2>
          Маршрут {trip.route} <span className="trip-name">{trip.routeName}</span>
        </h2>
        <button className="link" onClick={onClose}>
          закрыть
        </button>
      </div>

      {!trip.onLine ? (
        <p className="empty">Рейс сейчас не на линии.</p>
      ) : (
        <>
          <dl>
            <dt>Остановка</dt>
            <dd>{trip.stop}</dd>
            <dt>Отклонение</dt>
            <dd>
              {(trip.delay ?? 0) >= 0 ? '+' : ''}
              {(trip.delay ?? 0).toFixed(1)} мин
            </dd>
            <dt>Риск</dt>
            <dd className={`risk-${LEVEL_CLASS[trip.level ?? 3]}`}>
              {trip.risk === null || trip.risk === undefined
                ? 'рейс скоро завершится'
                : `${trip.risk}%`}
            </dd>
            {trip.outcome && (
              <>
                <dt>Проверка</dt>
                <dd>
                  {trip.outcome.late ? 'опоздал' : 'успел'} ({trip.outcome.delay.toFixed(1)} мин)
                </dd>
              </>
            )}
          </dl>
          <div className="trip-next">
            Дальше по плану:
            {trip.next?.length ? (
              <ul>
                {trip.next.map((n) => (
                  <li key={`${n.stop}-${n.plan}`}>
                    <span>{n.stop}</span>
                    <span>{n.plan}</span>
                  </li>
                ))}
              </ul>
            ) : (
              ' конечная'
            )}
          </div>
        </>
      )}
    </section>
  )
}
