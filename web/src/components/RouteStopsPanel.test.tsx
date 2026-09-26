import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { RouteStopsPanel } from './RouteStopsPanel'

const stops = [
  { name: 'Начальная', lat: 55.75, lon: 37.6, scheduledTime: '08:00', actualTime: '08:01' },
  { name: 'Средняя', lat: 55.76, lon: 37.61, scheduledTime: '08:05', actualTime: null },
  { name: 'Конечная', lat: 55.77, lon: 37.62, scheduledTime: '08:10', actualTime: null },
]

describe('RouteStopsPanel', () => {
  it('expands to show passed/current/upcoming stops and calls onFit', async () => {
    const onFit = vi.fn()
    render(<RouteStopsPanel stops={stops} currentStopIndex={1} onFit={onFit} />)

    expect(screen.getByText('Маршрут · 3 остановок')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Показать целиком' }))

    expect(screen.getByText('Пройдена')).toBeVisible()
    expect(screen.getByText('Текущая остановка')).toBeVisible()
    expect(screen.getByText('Впереди')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Вписать в карту' }))
    expect(onFit).toHaveBeenCalledOnce()
  })

  it('shows an unknown-position notice when the current stop is not known', async () => {
    render(<RouteStopsPanel stops={stops} currentStopIndex={null} onFit={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Показать целиком' }))
    expect(screen.getByText('Положение транспорта уточняется')).toBeVisible()
  })
})
