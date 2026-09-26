import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { FleetDrawer } from './FleetDrawer'

const vehicles = [
  { vehicleId: 1, route: '38', mode: 'bus', risk: 92, level: 2, delay: 3.2, lat: 55.75, lon: 37.6 },
  { vehicleId: 2, route: '3', mode: 'tram', risk: 20, level: 0, delay: -1, lat: 55.76, lon: 37.61 },
]

describe('FleetDrawer', () => {
  it('lists vehicles, filters by mode and selects a row', async () => {
    const onSelect = vi.fn()
    const onClose = vi.fn()
    render(<FleetDrawer vehicles={vehicles} onSelect={onSelect} onClose={onClose} />)

    expect(screen.getByText('2')).toBeVisible() // счетчик "Весь транспорт 2"
    expect(screen.getByText('ТС 1')).toBeVisible()
    expect(screen.getByText('ТС 2')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Трамваи' }))
    expect(screen.queryByText('ТС 1')).toBeNull()
    expect(screen.getByText('ТС 2')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: /ТС 2/ }))
    expect(onSelect).toHaveBeenCalledWith(2)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('filters by search text and shows an empty state', async () => {
    render(<FleetDrawer vehicles={vehicles} onSelect={vi.fn()} onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Поиск транспорта'), 'нет такого')
    expect(screen.getByText('Нет ТС по выбранным условиям')).toBeVisible()
  })

  it('closes via the close button', async () => {
    const onClose = vi.fn()
    render(<FleetDrawer vehicles={vehicles} onSelect={vi.fn()} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Закрыть весь транспорт' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
