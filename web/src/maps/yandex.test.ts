import { afterEach, describe, expect, it, vi } from 'vitest'

// loadYandex() caches a module-level promise, so each test needs a fresh module instance.
const importYandex = () => import('./yandex')

afterEach(() => {
  document.head.querySelectorAll('script[data-yandex-maps]').forEach((el) => el.remove())
  vi.unstubAllGlobals()
  vi.resetModules()
  delete window.ymaps
})

describe('loadYandex', () => {
  it('injects one script tag, resolves once ymaps is ready, and reuses the tag on the next call', async () => {
    const { loadYandex } = await importYandex()
    const ready = vi.fn((cb: () => void) => cb())
    const sdk = { ready } as unknown as Window['ymaps']

    const first = loadYandex()
    const script = document.head.querySelector<HTMLScriptElement>('script[data-yandex-maps="2.1"]')
    expect(script).toBeTruthy()
    expect(script!.src).toContain('api-maps.yandex.ru/2.1')

    window.ymaps = sdk
    script!.onload?.(new Event('load'))
    await expect(first).resolves.toBe(sdk)

    const scriptsBefore = document.head.querySelectorAll('script[data-yandex-maps]').length
    await expect(loadYandex()).resolves.toBe(sdk)
    expect(document.head.querySelectorAll('script[data-yandex-maps]').length).toBe(scriptsBefore)
  })

  it('rejects on script error and lets the next call retry', async () => {
    const { loadYandex } = await importYandex()
    const first = loadYandex()
    const script = document.head.querySelector<HTMLScriptElement>('script[data-yandex-maps]')
    script!.onerror?.(new Event('error'))
    await expect(first).rejects.toThrow()

    const ready = vi.fn((cb: () => void) => cb())
    const retry = loadYandex()
    // Ошибка не убирает старый <script> из DOM — повтор навешивает слушатели на него же,
    // а не создает новый тег (см. loadYandex: ветка `existing`).
    const scripts = document.head.querySelectorAll<HTMLScriptElement>('script[data-yandex-maps]')
    expect(scripts.length).toBe(1)
    window.ymaps = { ready } as unknown as Window['ymaps']
    scripts[0].dispatchEvent(new Event('load'))
    await expect(retry).resolves.toBeDefined()
  })
})
