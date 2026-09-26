import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_DISPLAY } from '../ui/display'
import { TransportMap } from './TransportMap'

// В тестовом окружении VITE_YANDEX_MAPS_API_KEY не задан — TransportMap должен явно
// сообщить об этом, а не пытаться грузить внешний SDK Яндекса.
describe('TransportMap without an API key', () => {
  it('shows the missing-key notice instead of loading the SDK', () => {
    render(
      <TransportMap day={null} vehicles={[]} slowSegments={[]} selected={null} focusToken={0}
        display={DEFAULT_DISPLAY} onSelect={vi.fn()} />,
    )
    expect(screen.getByText(/VITE_YANDEX_MAPS_API_KEY/)).toBeVisible()
    expect(screen.getByLabelText('Yandex Map Москвы')).toBeInTheDocument()
  })
})
