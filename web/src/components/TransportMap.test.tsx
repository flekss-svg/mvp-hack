import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_DISPLAY } from '../ui/display'
import { TransportMap } from './TransportMap'

// Ключ из локального web/.env не должен влиять на тест: подменяем его пустым.
vi.mock('../maps/yandex', async (original) => ({ ...(await original<typeof import('../maps/yandex')>()), MAP_KEY: '' }))

// Без VITE_YANDEX_MAPS_API_KEY TransportMap должен явно сообщить об этом, а не грузить SDK.
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
