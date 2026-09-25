import { useMemo, useState } from 'react'
import type { MapVehicle } from '../maps/vehicles'
import { currentText, riskText } from '../ui/presentation'
import { Segmented } from './Segmented'

const ROW_HEIGHT = 48
const VIEWPORT_ROWS = 10

export function FleetDrawer({ vehicles, onSelect, onClose }: { vehicles: MapVehicle[]; onSelect: (id: string | number) => void; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('all')
  const [risk, setRisk] = useState('all')
  const [status, setStatus] = useState('all')
  const [sort, setSort] = useState<'risk' | 'route' | 'delay'>('risk')
  const [scrollTop, setScrollTop] = useState(0)
  const rows = useMemo(() => {
    const term = query.trim().toLowerCase()
    return [...vehicles].filter((vehicle) => (!term || vehicle.route?.toLowerCase().includes(term) || String(vehicle.vehicleId).includes(term)) &&
      (mode === 'all' || vehicle.mode === mode) &&
      (risk === 'all' || risk === 'low' && (vehicle.level ?? 3) === 0 || risk === 'mid' && (vehicle.level ?? 3) === 1 || risk === 'high' && (vehicle.level ?? 3) === 2) &&
      (status === 'all' || status === 'late' && (vehicle.delay ?? 0) > .1 || status === 'early' && (vehicle.delay ?? 0) < -.1 || status === 'on-time' && Math.abs(vehicle.delay ?? 0) <= .1)
    ).sort((a, b) => sort === 'route' ? String(a.route ?? '').localeCompare(String(b.route ?? ''), 'ru') : sort === 'delay' ? (b.delay ?? -Infinity) - (a.delay ?? -Infinity) : (b.risk ?? -Infinity) - (a.risk ?? -Infinity))
  }, [vehicles, query, mode, risk, status, sort])
  const start = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 3)
  const end = Math.min(rows.length, start + VIEWPORT_ROWS + 6)
  return <section className="fleet-drawer" aria-label="Весь транспорт">
    <header className="fleet-heading"><div><span className="fleet-eyebrow">ОПЕРАЦИОННЫЙ СПИСОК</span><h2>Весь транспорт <em>{vehicles.length}</em></h2></div><button className="fleet-close" onClick={onClose} aria-label="Закрыть весь транспорт">×</button></header>
    <div className="fleet-controls"><label className="fleet-search"><span>⌕</span><input value={query} onChange={(event) => { setQuery(event.target.value); setScrollTop(0) }} placeholder="Маршрут или ТС" aria-label="Поиск транспорта" /></label><Segmented label="Тип транспорта" value={mode} onChange={(value) => { setMode(value); setScrollTop(0) }} options={[{ value: 'all', label: 'Все' }, { value: 'bus', label: 'Автобусы' }, { value: 'tram', label: 'Трамваи' }]} /><Segmented label="Риск" value={risk} onChange={(value) => { setRisk(value); setScrollTop(0) }} options={[{ value: 'all', label: 'Все риски' }, { value: 'low', label: 'Низкий' }, { value: 'mid', label: 'Средний' }, { value: 'high', label: 'Высокий' }]} /></div>
    <div className="fleet-subcontrols"><Segmented label="Статус" value={status} onChange={(value) => { setStatus(value); setScrollTop(0) }} options={[{ value: 'all', label: 'Все статусы' }, { value: 'late', label: 'Опаздывают' }, { value: 'on-time', label: 'По графику' }, { value: 'early', label: 'Раньше' }]} /><label className="fleet-sort">Сортировка<select value={sort} onChange={(event) => setSort(event.target.value as typeof sort)}><option value="risk">По риску</option><option value="delay">По задержке</option><option value="route">По маршруту</option></select></label></div>
    <div className="fleet-table-head"><span>Маршрут</span><span>ТС / тип</span><span>Текущий статус</span><span>Риск</span><span>Обновлено</span></div>
    <div className="fleet-scroll" onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}><div style={{ height: rows.length * ROW_HEIGHT, position: 'relative' }}>{rows.slice(start, end).map((vehicle, index) => <button key={String(vehicle.vehicleId)} className="fleet-row" style={{ top: (start + index) * ROW_HEIGHT }} onClick={() => { onSelect(vehicle.vehicleId); onClose() }}>
      <span className={`fleet-route level-${vehicle.level ?? 3}`}>{vehicle.route || '—'}</span><span><b>ТС {vehicle.vehicleId}</b><small>{vehicle.mode === 'tram' ? 'Трамвай' : vehicle.mode === 'bus' ? 'Автобус' : 'Транспорт'}</small></span><span className={vehicle.delay && vehicle.delay > .1 ? 'fleet-late' : ''}>{currentText(vehicle.delay ?? undefined)}</span><strong>{riskText(vehicle.risk)}</strong><time>{vehicle.updatedAt ? 'только что' : '—'}</time>
    </button>)}</div>{!rows.length && <p className="fleet-empty">Нет ТС по выбранным условиям</p>}</div>
  </section>
}
