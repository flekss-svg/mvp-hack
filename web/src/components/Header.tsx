import type { Kpi } from '../api/types'

interface Props {
  clock: string
  subtitle: string
  kpi: Kpi[]
  status: 'LIVE' | 'OFFLINE' | 'DEMO' | 'REPLAY' | 'CONNECTING'
}

export function Header({ clock, subtitle, kpi, status }: Props) {
  return (
    <header className="header">
      <div className="header-title"><h1>Контроль движения</h1><p>Раннее предупреждение задержек</p></div>
      <div className="header-divider" />
      <div className="header-time"><div><time className="clock">{clock}</time><span className={`status status-${status.toLowerCase()}`}><i />{status === 'CONNECTING' ? 'ПОДКЛЮЧЕНИЕ' : status}</span></div><p>{subtitle}</p></div>
      <div className="kpis">{kpi.map((k) => <div key={k.key} className={`kpi${k.tone === 'high' ? ' kpi-high' : ''}`} title={k.hint}><b>{k.value}</b><span>{k.label}</span></div>)}</div>
    </header>
  )
}
