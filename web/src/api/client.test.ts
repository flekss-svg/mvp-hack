import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

afterEach(() => vi.restoreAllMocks())

describe('api client', () => {
  it('serializes frame filters and omits default filters', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ t: 485 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    await api.frame({ t: 485.126, mode: 'all', minLevel: 0, trip: 7 })

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/replay/frame?t=485.13&trip=7')
  })

  it('turns structured API failures into ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ detail: { what: 'replay', error: 'missing', hint: 'build replay' } }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    await expect(api.day()).rejects.toMatchObject({
      message: 'build replay',
      problem: { what: 'replay', error: 'missing', hint: 'build replay' },
    })
  })
})
