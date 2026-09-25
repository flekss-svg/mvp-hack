import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { day, frame, timeline } from '../test/fixtures'
import { MapCanvas } from './MapCanvas'
import { Timeline } from './Timeline'

const context = {
  setTransform: vi.fn(),
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  stroke: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn(() => ({ width: 24 })),
  fillStyle: '',
  strokeStyle: '',
  lineWidth: 1,
  lineCap: 'butt',
  globalAlpha: 1,
  font: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    context as unknown as CanvasRenderingContext2D,
  )
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', {
    configurable: true,
    get: () => 800,
  })
  Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', {
    configurable: true,
    get: () => 400,
  })
  Object.defineProperty(HTMLCanvasElement.prototype, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 800,
      bottom: 400,
      width: 800,
      height: 400,
      toJSON: () => ({}),
    }),
  })
  Object.defineProperty(HTMLCanvasElement.prototype, 'setPointerCapture', {
    configurable: true,
    value: vi.fn(),
  })
})

describe('Timeline canvas', () => {
  it('draws data and seeks with pointer interaction', () => {
    const onSeek = vi.fn()
    render(<Timeline data={timeline} t={500} onSeek={onSeek} />)
    const canvas = screen.getByLabelText('Шкала времени: число машин с высоким риском')

    expect(context.fillRect).toHaveBeenCalled()
    expect(context.fillText).toHaveBeenCalled()
    fireEvent(canvas, new MouseEvent('pointerdown', { bubbles: true, clientX: 400 }))
    expect(onSeek).toHaveBeenLastCalledWith(500)
    fireEvent(canvas, new MouseEvent('pointermove', { bubbles: true, clientX: 800 }))
    expect(onSeek).toHaveBeenLastCalledWith(600)
    fireEvent(canvas, new MouseEvent('pointerup', { bubbles: true }))
  })
})

describe('MapCanvas', () => {
  it('draws network and vehicles, selects, pans and zooms', () => {
    const onSelect = vi.fn()
    render(<MapCanvas day={day} frame={frame} selected={7} onSelect={onSelect} />)
    const canvas = screen.getByLabelText('Карта маршрутов и машин')

    expect(context.lineTo).toHaveBeenCalled()
    expect(context.arc).toHaveBeenCalled()
    fireEvent(canvas, new MouseEvent('pointerdown', { bubbles: true, clientX: 400, clientY: 200 }))
    fireEvent(canvas, new MouseEvent('pointerup', { bubbles: true, clientX: 400, clientY: 200 }))
    expect(onSelect).toHaveBeenCalledWith(7)

    fireEvent(canvas, new MouseEvent('pointerdown', { bubbles: true, clientX: 400, clientY: 200 }))
    fireEvent(canvas, new MouseEvent('pointermove', { bubbles: true, clientX: 420, clientY: 220 }))
    fireEvent(canvas, new MouseEvent('pointerup', { bubbles: true, clientX: 420, clientY: 220 }))
    fireEvent.wheel(canvas, { deltaY: -1, clientX: 400, clientY: 200 })
    fireEvent.click(screen.getByRole('button', { name: 'Приблизить' }))
    fireEvent.click(screen.getByRole('button', { name: 'Отдалить' }))
    fireEvent.click(screen.getByRole('button', { name: 'Показать всё' }))
    expect(context.clearRect).toHaveBeenCalled()
  })
})
