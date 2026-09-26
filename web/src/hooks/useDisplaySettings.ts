import { useEffect, useState } from 'react'
import { DEFAULT_DISPLAY, DISPLAY_KEY, parseDisplay } from '../ui/display'
import type { DisplaySettings } from '../ui/display'

export function useDisplaySettings() {
  const [settings, setSettings] = useState<DisplaySettings>(() => {
    try { return parseDisplay(localStorage.getItem(DISPLAY_KEY)) } catch { return DEFAULT_DISPLAY }
  })
  useEffect(() => {
    try { localStorage.setItem(DISPLAY_KEY, JSON.stringify(settings)) } catch { /* Storage may be blocked; session settings still work. */ }
    const cssNames = { low: '--low', mid: '--mid', high: '--high', selected: '--sel', network: '--net', warning: '--slow', critical: '--slow-strong' }
    for (const [name, value] of Object.entries(settings.colors)) document.documentElement.style.setProperty(cssNames[name as keyof typeof cssNames], value)
  }, [settings])
  return { settings, setSettings }
}
