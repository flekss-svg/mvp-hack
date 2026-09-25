import type * as YMaps from '@yandex/ymaps3-types'

export const MAP_KEY = (import.meta.env.VITE_YANDEX_MAPS_API_KEY ?? '').trim()
export const MOSCOW: [number, number] = [37.6176, 55.7558]
let pending: Promise<typeof YMaps> | null = null

type YandexStage = 'configuration' | 'script-load' | 'namespace' | 'sdk-ready' | 'map-create' | 'scheme-layer' | 'features-layer' | 'map-ready'
const SAFE_SCRIPT_URL = 'https://api-maps.yandex.ru/v3/?lang=ru_RU'

function safeErrorText(error: unknown): string {
  // Never pass Error/Event/DOM objects to the console: they can contain script.src.
  let message = error instanceof Error ? error.message
    : typeof error === 'string' ? error
      : error && typeof error === 'object' && 'message' in error && typeof error.message === 'string'
        ? error.message : 'Unknown error (no message provided)'
  if (MAP_KEY) {
    for (const secret of [MAP_KEY, encodeURIComponent(MAP_KEY), encodeURI(MAP_KEY)]) {
      message = message.split(secret).join('[REDACTED]')
    }
  }
  return message.replace(/(apikey\s*[=:]\s*)[^\s&"'<>#]+/gi, '$1[REDACTED]')
}

export class YandexLoadError extends Error {
  constructor(readonly stage: YandexStage, error: unknown) {
    super(safeErrorText(error))
    this.name = 'YandexLoadError'
  }
}

export function logYandex(stage: YandexStage, result: 'start' | 'success' | 'error', error?: unknown) {
  if (!import.meta.env.DEV) return
  const details = {
    stage,
    result,
    hasApiKey: Boolean(MAP_KEY),
    scriptUrl: SAFE_SCRIPT_URL,
    hasWindowYmaps3: Boolean((window as Window & { ymaps3?: typeof YMaps }).ymaps3),
    ...(error === undefined ? {} : { error: safeErrorText(error) }),
  }
  if (result === 'error') console.error('[Yandex Maps]', details)
  else console.info('[Yandex Maps]', details)
}

/** One SDK load shared across React StrictMode mounts. No key is stored in source. */
export function loadYandex(): Promise<typeof YMaps> {
  if (pending) return pending
  pending = new Promise<typeof YMaps>((resolve, reject) => {
    const script = document.createElement('script')
    let settled = false
    let stage: YandexStage = 'script-load'
    const finish = (sdk?: typeof YMaps, error?: unknown) => {
      if (settled) return
      settled = true
      window.clearTimeout(timeout)
      script.onload = null
      script.onerror = null
      if (sdk) resolve(sdk)
      else {
        const failure = new YandexLoadError(stage, error)
        logYandex(stage, 'error', failure)
        script.remove()
        reject(failure)
      }
    }
    const timeout = window.setTimeout(() => finish(undefined, new Error(`Timeout after 15000 ms at ${stage}`)), 15000)
    script.async = true
    script.src = `https://api-maps.yandex.ru/v3/?apikey=${encodeURIComponent(MAP_KEY)}&lang=ru_RU`
    script.onerror = () => finish(undefined, new Error('script.onerror: script request failed; check Network and Content Security Policy'))
    script.onload = async () => {
      logYandex(stage, 'success')
      try {
        stage = 'namespace'
        const sdk = (window as Window & { ymaps3?: typeof YMaps }).ymaps3
        if (!sdk) throw new Error('Script loaded, but window.ymaps3 is absent')
        logYandex(stage, 'success')
        stage = 'sdk-ready'
        logYandex(stage, 'start')
        await sdk.ready
        if (settled) return
        logYandex(stage, 'success')
        finish(sdk)
      } catch (error) {
        finish(undefined, error)
      }
    }
    logYandex(stage, 'start')
    try {
      document.head.appendChild(script)
    } catch (error) {
      finish(undefined, error)
    }
  }).catch((error: unknown) => {
    pending = null
    throw error
  })
  return pending
}
