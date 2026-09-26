import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ChangedValue } from './ChangedValue'

describe('ChangedValue', () => {
  it('flags a highlight only when the value actually changes', async () => {
    const { rerender } = render(<ChangedValue value="80%" />)
    const el = screen.getByText('80%')
    expect(el).not.toHaveClass('value-updated')

    rerender(<ChangedValue value="80%" />)
    expect(el).not.toHaveClass('value-updated')

    rerender(<ChangedValue value="81%" />)
    await waitFor(() => expect(screen.getByText('81%')).toHaveClass('value-updated'))
  })
})
