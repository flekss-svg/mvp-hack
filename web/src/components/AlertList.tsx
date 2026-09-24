import type { Alert } from '../api/types'

interface Props {
  title: string
  alerts: Alert[]
  selected: number | null
  onSelect?: (tripId: number) => void
  empty: string
}

/** Машины, которые сейчас идут по графику, но опоздают. Порядок задает сервер. */
export function AlertList({ title, alerts, selected, onSelect, empty }: Props) {
  return (
    <div className="alerts">
      <h2>{title}</h2>
      {alerts.length === 0 ? (
        <p className="empty">{empty}</p>
      ) : (
        <ul>
          {alerts.map((a) => (
            <li key={a.tripId}>
              <button
                className={`alert${a.tripId === selected ? ' on' : ''}`}
                onClick={() => onSelect?.(a.tripId)}
                disabled={!onSelect}
              >
                <span className={`badge badge-${a.mode}`}>{a.route}</span>
                <span className="alert-body">
                  <span className="alert-dest">{a.dest ? `→ ${a.dest}` : a.stop}</span>
                  <span className="alert-sub">
                    сейчас {a.delay >= 0 ? '+' : ''}
                    {a.delay.toFixed(1)} мин · {a.stop}
                  </span>
                </span>
                <span className="alert-risk">{a.risk}%</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
