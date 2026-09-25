import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { Segmented } from './Segmented'

describe('Segmented', () => {
  it('marks the selected option and reports clicks', async () => {
    const onChange = vi.fn()
    render(
      <Segmented
        label="Transport"
        value="all"
        onChange={onChange}
        options={[
          { value: 'all', label: 'Все' },
          { value: 'bus', label: 'Автобусы' },
        ]}
      />,
    )

    expect(screen.getByRole('button', { name: 'Все' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Автобусы' }))
    expect(onChange).toHaveBeenCalledWith('bus')
  })
})
