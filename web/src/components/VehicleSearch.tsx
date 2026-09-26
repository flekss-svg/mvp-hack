import { useEffect, useId, useRef, useState } from 'react'
import { Icon } from './Icon'

export interface SearchVehicle { tripId: number; route: string; mode: string }
export function VehicleSearch({ vehicles, onSelect }: { vehicles: SearchVehicle[]; onSelect: (id: number) => void }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const root = useRef<HTMLDivElement>(null)
  const id = useId()
  const term = query.trim().toLowerCase()
  const matches = term ? vehicles.filter((v) => v.route.toLowerCase().includes(term) || String(v.tripId).includes(term)).slice(0, 12) : []
  const choose = (tripId: number) => { onSelect(tripId); setOpen(false); setQuery('') }
  useEffect(() => {
    const close = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', close)
    return () => document.removeEventListener('pointerdown', close)
  }, [])
  return <div className="vehicle-search" ref={root}>
    <Icon name="search" /><input role="combobox" aria-label="Найти маршрут или ТС" aria-expanded={open && !!term} aria-controls={id} aria-autocomplete="list"
      aria-activedescendant={open && matches[active] ? `${id}-${matches[active].tripId}` : undefined}
      placeholder="Маршрут или ТС…" value={query} onFocus={() => setOpen(true)}
      onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0) }} onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
        if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((i) => Math.min(i + 1, matches.length - 1)) }
        if (e.key === 'ArrowUp') { e.preventDefault(); setActive((i) => Math.max(0, i - 1)) }
        if (e.key === 'Enter' && matches[active]) { e.preventDefault(); choose(matches[active].tripId) }
      }} />
    {open && term && <ul className="search-results" id={id} role="listbox" aria-label="Найденные ТС">
      {matches.length ? matches.map((v, i) => <li key={v.tripId} id={`${id}-${v.tripId}`} role="option" aria-selected={i === active}
        onPointerDown={(e) => e.preventDefault()} onClick={() => choose(v.tripId)}><span className={`route-badge badge-${v.mode}`}>{v.route || '—'}</span><span><b>ТС {v.tripId}</b><small>{v.mode === 'tram' ? 'Трамвай' : v.mode === 'bus' ? 'Автобус' : 'Транспорт'}</small></span><span className="search-arrow">↗</span></li>) : <li className="search-empty" role="option" aria-selected={false}>Нет совпадений в доступных данных</li>}
    </ul>}
  </div>
}
