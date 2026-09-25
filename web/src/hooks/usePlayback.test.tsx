import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SPEEDS, usePlayback } from './usePlayback'

describe('usePlayback', () => {
  it('initializes inside bounds, seeks, toggles and cycles speed', () => {
    const { result } = renderHook(() => usePlayback({ tMin: 400, tMax: 600 }))
    expect(result.current.t).toBe(450)

    act(() => result.current.seek(500))
    expect(result.current.t).toBe(500)

    act(() => result.current.toggle())
    expect(result.current.playing).toBe(true)

    act(() => result.current.cycleSpeed())
    expect(result.current.speed).toBe(SPEEDS[2])
  })
})
