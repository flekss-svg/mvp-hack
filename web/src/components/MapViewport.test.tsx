import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_DISPLAY } from '../ui/display'
import { day, frame } from '../test/fixtures'
import { MapViewport } from './MapViewport'

// Canvas-схема без географической подложки — альтернатива TransportMap, которая сейчас
// не подключена к App, но сохранена в кодовой базе (см. web/README.md).
describe('MapViewport', () => {
  it('renders the caption without a day and the canvas map once a day is loaded', () => {
    // jsdom не реализует 2D-контекст канваса; MapCanvas сам это учитывает (ctx === null),
    // но без мока в консоль летит шумное "Not implemented".
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    const { rerender } = render(
      <MapViewport day={null} frame={null} selected={null} focusToken={0} focusReady display={DEFAULT_DISPLAY} onSelect={vi.fn()} />,
    )
    expect(screen.getByText('СХЕМА · БЕЗ ГЕОГРАФИЧЕСКОЙ ПОДЛОЖКИ')).toBeVisible()
    expect(screen.queryByLabelText('Карта маршрутов и машин')).toBeNull()

    rerender(
      <MapViewport day={day} frame={frame} selected={null} focusToken={0} focusReady display={DEFAULT_DISPLAY} onSelect={vi.fn()} />,
    )
    expect(screen.getByLabelText('Карта маршрутов и машин')).toBeVisible()
  })
})
