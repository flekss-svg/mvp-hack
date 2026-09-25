import { useEffect, useRef, useState } from 'react'
import { DEFAULT_DISPLAY, PALETTES } from '../ui/display'
import type { Colors, DisplaySettings as Settings, Palette } from '../ui/display'
import { Segmented } from './Segmented'
import { Icon } from './Icon'

const colorLabels: Record<keyof Colors, string> = { low: 'Низкий риск', mid: 'Средний риск', high: 'Высокий риск', selected: 'Выбранное ТС', network: 'Маршрутная сеть', warning: 'Проблемный участок', critical: 'Критический участок' }
const toggleLabels = { routeNumbers: 'Номера маршрутов', problemSegments: 'Проблемные участки', lowRisk: 'ТС низкого риска', vehicleLabels: 'Подписи ТС' }
export function DisplaySettings({ settings, onChange }: { settings: Settings; onChange: (next: Settings) => void }) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const click = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(false); button.current?.focus() } }
    document.addEventListener('pointerdown', click)
    document.addEventListener('keydown', key)
    root.current?.querySelector<HTMLButtonElement>('.display-popover button')?.focus()
    return () => { document.removeEventListener('pointerdown', click); document.removeEventListener('keydown', key) }
  }, [open])
  const palette = (value: Palette) => onChange({ ...settings, palette: value, colors: value === 'custom' ? settings.colors : PALETTES[value] })
  return <div className="display-settings" ref={root}>
    <button ref={button} className="display-trigger" aria-expanded={open} aria-controls="display-popover" onClick={() => setOpen(!open)}><Icon name="settings" />Отображение</button>
    {open && <div className="display-popover" id="display-popover" role="dialog" aria-label="Настройки отображения">
      <div className="popover-heading"><h2>Отображение</h2><button aria-label="Закрыть настройки" onClick={() => { setOpen(false); button.current?.focus() }}>×</button></div>
      <fieldset><legend>Палитра риска</legend><div className="palette-options">{([['standard', 'Стандартная'], ['contrast', 'Контрастная'], ['colorblind', 'Для дальтонизма'], ['custom', 'Своя']] as const).map(([key, label]) => <button key={key} aria-pressed={settings.palette === key} onClick={() => palette(key)}>
        <span className="palette-swatches" aria-hidden="true">{Object.values(key === 'custom' ? settings.colors : PALETTES[key]).slice(0, 3).map((color, i) => <i key={i} style={{ background: color }} />)}</span>{label}</button>)}</div></fieldset>
      {settings.palette === 'custom' && <div className="custom-colors">{Object.entries(colorLabels).map(([key, label]) => <label key={key}>{label}<input type="color" aria-label={label} value={settings.colors[key as keyof Colors]} onChange={(e) => onChange({ ...settings, colors: { ...settings.colors, [key]: e.target.value } })} /></label>)}</div>}
      <button className="reset-colors" onClick={() => onChange({ ...settings, palette: 'standard', colors: { ...DEFAULT_DISPLAY.colors } })}>Сбросить цвета</button>
      <fieldset className="display-toggles"><legend>Слои схемы</legend>{Object.entries(toggleLabels).map(([key, label]) => <label key={key}><input type="checkbox" checked={settings[key as keyof typeof toggleLabels]} onChange={(e) => onChange({ ...settings, [key]: e.target.checked })} />{label}</label>)}</fieldset>
      <fieldset><legend>Плотность</legend><Segmented label="Плотность интерфейса" value={settings.density} onChange={(density) => onChange({ ...settings, density })} options={[{ value: 'compact', label: 'Компактная' }, { value: 'comfortable', label: 'Комфортная' }]} /></fieldset>
      <p className="settings-note">Настройки сохраняются в этом браузере. Форма маркера всегда обозначает уровень риска.</p>
    </div>}
  </div>
}
