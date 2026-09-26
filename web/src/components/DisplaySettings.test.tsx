import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_DISPLAY, PALETTES } from '../ui/display'
import { DisplaySettings } from './DisplaySettings'

describe('DisplaySettings', () => {
  it('opens the popover, switches palette and toggles a layer', async () => {
    const onChange = vi.fn()
    render(<DisplaySettings settings={DEFAULT_DISPLAY} onChange={onChange} />)

    await userEvent.click(screen.getByRole('button', { name: /Отображение/ }))
    expect(screen.getByRole('dialog', { name: 'Настройки отображения' })).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Контрастная' }))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_DISPLAY, palette: 'contrast', colors: PALETTES.contrast })

    await userEvent.click(screen.getByLabelText('Подписи ТС'))
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_DISPLAY, vehicleLabels: false })
  })

  it('closes on Escape and returns focus to the trigger', async () => {
    render(<DisplaySettings settings={DEFAULT_DISPLAY} onChange={vi.fn()} />)
    const trigger = screen.getByRole('button', { name: /Отображение/ })

    await userEvent.click(trigger)
    expect(screen.getByRole('dialog')).toBeVisible()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(trigger).toHaveFocus()
  })
})
