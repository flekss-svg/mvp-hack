import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'

afterEach(() => vi.restoreAllMocks())

describe('api client fallback errors', () => {
  it('reports HTTP status when the error body is not JSON', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('upstream failure', { status: 502 }),
    )

    await expect(api.day()).rejects.toThrow('Ошибка API: HTTP 502')
  })
})
