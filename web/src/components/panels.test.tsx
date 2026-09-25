import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AlertList } from './AlertList'
import { Header } from './Header'
import { Legend } from './Legend'
import { TripPanel } from './TripPanel'

describe('dashboard panels', () => {
  it('renders header KPI and legend', () => {
    render(
      <>
        <Header
          clock="08:05"
          subtitle="Тестовый день"
          kpi={[{ key: 'high', label: 'риск', value: '2', tone: 'high' }]}
        />
        <Legend threshold={3} />
      </>,
    )
    expect(screen.getByText('08:05')).toBeVisible()
    expect(screen.getByText('2')).toBeVisible()
    expect(screen.getByText(/3 мин/)).toBeVisible()
  })

  it('selects an alert and closes a trip card', async () => {
    const onSelect = vi.fn()
    const onClose = vi.fn()
    render(
      <>
        <AlertList
          title="Тревоги"
          alerts={[{
            tripId: 1,
            route: '42',
            mode: 'bus',
            dest: 'Конечная',
            stop: 'Начальная',
            delay: 1,
            risk: 80,
          }]}
          selected={null}
          onSelect={onSelect}
          empty="Пусто"
        />
        <TripPanel
          trip={{
            found: true,
            onLine: true,
            route: '42',
            routeName: 'Тестовый маршрут',
            mode: 'bus',
            stop: 'Начальная',
            delay: 1,
            risk: 80,
            level: 2,
            outcome: null,
            next: [],
          }}
          onClose={onClose}
        />
      </>,
    )

    await userEvent.click(screen.getByRole('button', { name: /Конечная/ }))
    expect(onSelect).toHaveBeenCalledWith(1)
    await userEvent.click(screen.getByRole('button', { name: /закрыть/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
