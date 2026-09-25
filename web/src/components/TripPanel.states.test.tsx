import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TripPanel } from './TripPanel'

describe('TripPanel states', () => {
  it('renders offline and completed prediction states', () => {
    const { rerender } = render(
      <TripPanel
        trip={{
          found: true,
          onLine: false,
          route: '42',
          routeName: 'Тестовый маршрут',
          mode: 'bus',
        }}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText('Рейс сейчас не на линии.')).toBeVisible()

    rerender(
      <TripPanel
        trip={{
          found: true,
          onLine: true,
          route: '42',
          routeName: 'Тестовый маршрут',
          mode: 'bus',
          stop: 'Начальная',
          delay: -1,
          risk: null,
          level: 3,
          outcome: { late: false, delay: 1.5 },
          next: [{ stop: 'Конечная', plan: '08:30' }],
        }}
        onClose={vi.fn()}
      />,
    )
    expect(screen.getByText('рейс скоро завершится')).toBeVisible()
    expect(screen.getByText(/успел.*1\.5 мин/)).toBeVisible()
    expect(screen.getByText('Конечная')).toBeVisible()
    expect(screen.getByText('08:30')).toBeVisible()
  })
})
