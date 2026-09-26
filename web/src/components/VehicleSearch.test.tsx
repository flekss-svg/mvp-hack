import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { VehicleSearch } from './VehicleSearch'

const vehicles = [
  { tripId: 1, route: '38', mode: 'bus' },
  { tripId: 2, route: '3', mode: 'tram' },
]

describe('VehicleSearch', () => {
  it('filters by route or id and selects a match with the mouse', async () => {
    const onSelect = vi.fn()
    render(<VehicleSearch vehicles={vehicles} onSelect={onSelect} />)
    const input = screen.getByRole('combobox', { name: 'Найти маршрут или ТС' })

    await userEvent.type(input, '38')
    expect(screen.getByRole('option', { name: /ТС 1/ })).toBeVisible()
    expect(screen.queryByRole('option', { name: /ТС 2/ })).toBeNull()

    await userEvent.click(screen.getByRole('option', { name: /ТС 1/ }))
    expect(onSelect).toHaveBeenCalledWith(1)
    expect(input).toHaveValue('')
  })

  it('supports keyboard navigation and shows an empty state for no matches', async () => {
    const onSelect = vi.fn()
    render(<VehicleSearch vehicles={vehicles} onSelect={onSelect} />)
    const input = screen.getByRole('combobox', { name: 'Найти маршрут или ТС' })

    await userEvent.type(input, '9999')
    expect(screen.getByText('Нет совпадений в доступных данных')).toBeVisible()

    await userEvent.clear(input)
    await userEvent.type(input, '3')
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(onSelect).toHaveBeenCalledWith(2)

    await userEvent.type(input, 'x')
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).toBeNull()
  })
})
