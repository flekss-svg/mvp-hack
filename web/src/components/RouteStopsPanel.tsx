import { useEffect, useId, useRef, useState } from 'react'
import type { RouteStop } from '../api/types'

interface Props {
  stops: RouteStop[]
  currentStopIndex?: number | null
  onFit: () => void
}

export function RouteStopsPanel({ stops, currentStopIndex, onFit }: Props) {
  const [expanded, setExpanded] = useState(false)
  const listId = useId()
  const list = useRef<HTMLOListElement>(null)
  const positionKnown = typeof currentStopIndex === 'number' && Number.isInteger(currentStopIndex)
    && currentStopIndex >= -1 && currentStopIndex <= stops.length

  useEffect(() => {
    if (!expanded || !list.current) return
    const current = list.current.querySelector<HTMLElement>('[aria-current="step"]')
    if (current) {
      const container = list.current
      if (current.offsetTop < container.scrollTop || current.offsetTop + current.offsetHeight > container.scrollTop + container.clientHeight) {
        container.scrollTop = Math.max(0, current.offsetTop - container.clientHeight / 3)
      }
    }
  }, [expanded, currentStopIndex])

  return <section className={`selected-route-summary${expanded ? ' is-expanded' : ''}`} aria-label="Остановки выбранного маршрута">
    <div className="route-summary-header">
      <span className="selected-route-swatch" aria-hidden="true" />
      <span>Маршрут · {stops.length} остановок</span>
      <button aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded((value) => !value)}>{expanded ? 'Свернуть' : 'Показать целиком'}<span aria-hidden="true"> {expanded ? '⌃' : '⌄'}</span></button>
    </div>
    {expanded && <div id={listId} className="route-stops-dropdown">
      <div className="route-stops-heading"><span>Остановки по порядку</span><button onClick={onFit}>Вписать в карту</button></div>
      {!positionKnown && <p className="route-position-unknown">Положение транспорта уточняется</p>}
      <ol ref={list} className="route-stops-list" aria-label="Все остановки маршрута">
        {stops.map((stop, index) => {
          const state = !positionKnown ? 'unknown' : index < currentStopIndex! ? 'passed' : index === currentStopIndex ? 'current' : 'upcoming'
          return <li key={index} className={`route-list-stop is-${state}`} aria-current={state === 'current' ? 'step' : undefined}>
            <span className="route-list-number" aria-hidden="true">{index + 1}</span>
            <div>
              <span className="route-list-name">{stop.name}</span>
              <span className="route-list-state">{state === 'passed' ? 'Пройдена' : state === 'current' ? 'Текущая остановка' : state === 'upcoming' ? 'Впереди' : '—'}</span>
              <dl className="route-stop-times">
                <div><dt>По расписанию</dt><dd>{stop.scheduledTime ?? '—'}</dd></div>
                <div><dt>По факту</dt><dd className={stop.actualTime ? 'has-time' : 'no-time'} title={!stop.actualTime ? state === 'upcoming' ? 'Остановка ещё не пройдена' : 'Нет фактического времени' : undefined}>{stop.actualTime ?? '—'}</dd></div>
              </dl>
            </div>
          </li>
        })}
      </ol>
    </div>}
  </section>
}
