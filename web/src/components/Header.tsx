import type { Kpi } from '../api/types'

interface Props {
  clock: string
  subtitle: string
  kpi: Kpi[]
}

export function Header({ clock, subtitle, kpi }: Props) {
  return (
    <header className="header">
      <div className="clock">{clock}</div>
      <div className="header-title">
        <h1>Раннее предупреждение задержек</h1>
        <p>{subtitle}</p>
      </div>
      <div className="kpis">
        {kpi.map((k) => (
          <div key={k.key} className={`kpi${k.tone === 'high' ? ' kpi-high' : ''}`} title={k.hint}>
            <b>{k.value}</b>
            <span>{k.label}</span>
          </div>
        ))}
      </div>
    </header>
  )
}
