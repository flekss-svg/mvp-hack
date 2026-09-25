import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse } from '../test/fixtures'
import { api } from './client'

afterEach(() => vi.restoreAllMocks())

describe('api client', () => {
  it('serializes frame filters and omits defaults', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ t: 485 }))

    await api.frame({ t: 485.126, mode: 'all', minLevel: 0, trip: 7 })

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/replay/frame?t=485.13&trip=7')
  })

  it('turns a structured 503 into ApiError with the hint', async () => {
    const detail = { what: 'replay', error: 'missing', hint: 'build replay' }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail }, 503))

    await expect(api.day()).rejects.toMatchObject({ message: 'build replay', problem: detail })
  })

  it('reports the HTTP status when the error body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('upstream failure', { status: 502 }))

    await expect(api.day()).rejects.toThrow('Ошибка API: HTTP 502')
  })
})
