import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'

vi.mock('./api/client', () => {
  class ApiError extends Error {}
  return {
    ApiError,
    api: {
      model: vi.fn(),
      day: vi.fn(),
      frame: vi.fn(),
      timeline: vi.fn(),
      live: vi.fn(),
    },
  }
})

vi.mock('./components/MapCanvas', () => ({
  MapCanvas: () => <canvas aria-label="Карта маршрутов" />,
}))
vi.mock('./components/Timeline', () => ({ Timeline: () => <div /> }))
vi.mock('./components/ModelPanel', () => ({ ModelPanel: () => <section /> }))

describe('App selected trip', () => {
  it('renders and closes the selected trip card', async () => {
    vi.mocked(api.day).mockResolvedValue({
      date: '2026-09-03',
      dow: 3,
      rain: { level: 0, start: 0, end: 0 },
      threshold: 3,
      tMin: 400,
      tMax: 600,
      horizonLabel: '10–15 мин',
      riskLevels: { mid: 0.3, high: 0.6 },
      modes: [{ id: 0, key: 'bus' }],
      trips: 1,
      network: { stops: [[37.6, 55.7]], segments: [] },
    })
    vi.mocked(api.timeline).mockResolvedValue({
      tMin: 400,
      tMax: 600,
      bins: [],
      ticks: [],
      rain: null,
    })
    vi.mocked(api.frame).mockImplementation(async ({ trip }) => ({
      t: 450,
      clock: '07:30',
      raining: false,
      kpi: [],
      vehicles: { id: [], lon: [], lat: [], level: [], risk: [], late: [] },
      slowSegments: [],
      alerts: trip === null ? [{
        tripId: 1,
        route: '42',
        mode: 'bus',
        dest: 'Конечная',
        stop: 'Начальная',
        delay: 1,
        risk: 80,
      }] : [],
      trip: trip === 1 ? {
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
      } : null,
    }))

    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /Конечная/ }))
    expect(await screen.findByRole('heading', { name: /Маршрут 42/ })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'закрыть' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: /Маршрут 42/ })).toBeNull())
  })
})
