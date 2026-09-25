export type Palette = 'standard' | 'contrast' | 'colorblind' | 'custom'
export type Colors = { low: string; mid: string; high: string; selected: string; network: string; warning: string; critical: string }
export interface DisplaySettings {
  palette: Palette
  colors: Colors
  routeNumbers: boolean
  problemSegments: boolean
  lowRisk: boolean
  vehicleLabels: boolean
  density: 'compact' | 'comfortable'
}
export const PALETTES: Record<Exclude<Palette, 'custom'>, Colors> = {
  standard: { low: '#27815f', mid: '#ba861f', high: '#bd393e', selected: '#285fa7', network: '#bbcbd3', warning: '#c19436', critical: '#bd393e' },
  contrast: { low: '#006b3c', mid: '#946400', high: '#a50021', selected: '#064db5', network: '#768590', warning: '#946400', critical: '#a50021' },
  colorblind: { low: '#0072b2', mid: '#e69f00', high: '#b54a91', selected: '#1d2638', network: '#aab3bd', warning: '#e69f00', critical: '#882255' },
}
export const DEFAULT_DISPLAY: DisplaySettings = { palette: 'standard', colors: { ...PALETTES.standard }, routeNumbers: true, problemSegments: true, lowRisk: true, vehicleLabels: true, density: 'compact' }
export const DISPLAY_KEY = 'transport-dashboard-display-v1'
export function parseDisplay(raw: string | null): DisplaySettings {
  try {
    const data = JSON.parse(raw ?? 'null')
    if (!data || !['standard', 'contrast', 'colorblind', 'custom'].includes(data.palette)) return DEFAULT_DISPLAY
    const colors = { ...PALETTES.standard }
    for (const key of Object.keys(colors) as (keyof Colors)[]) if (/^#[0-9a-f]{6}$/i.test(data.colors?.[key])) colors[key] = data.colors[key]
    return { palette: data.palette, colors: data.palette === 'custom' ? colors : PALETTES[data.palette as Exclude<Palette, 'custom'>],
      ...Object.fromEntries(['routeNumbers', 'problemSegments', 'lowRisk', 'vehicleLabels'].map((key) => [key, typeof data[key] === 'boolean' ? data[key] : true])),
      density: data.density === 'comfortable' ? 'comfortable' : 'compact',
    } as DisplaySettings
  } catch { return DEFAULT_DISPLAY }
}
