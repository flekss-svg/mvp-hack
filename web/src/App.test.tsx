import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import type { DayInfo, Frame } from './api/types'

vi.mock('./api/client', () => {
  class ApiError extends Error {
    problem?: unknown
    constructor(message: string, problem?: unknown) {
      super(message)
      this.problem = problem
    }
  }
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

vi.mock('./components/Timeline', () => ({
  Timeline: () => <div aria-label="Шкала времени" />,
}))

vi.mock('./components/ModelPanel', () => ({
  ModelPanel: () => <section aria-label="Качество модели" />,
}))

const day: DayInfo = {
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
}

const frame: Frame = {
  t: 450,
  clock: '07:30',
  raining: false,
  kpi: [{ key: 'onLine', label: 'на линии', value: '1' }],
  vehicles: { id: [0], lon: [37.6], lat: [55.7], level: [0], risk: [10], late: [0] },
  slowSegments: [],
  alerts: [],
  trip: null,
}

describe('App', () => {
  beforeEach(() => {
    vi.mocked(api.day).mockResolvedValue(day)
    vi.mocked(api.frame).mockResolvedValue(frame)
    vi.mocked(api.timeline).mockResolvedValue({
      tMin: 400,
      tMax: 600,
      bins: [],
      ticks: [],
      rain: null,
    })
    vi.mocked(api.live).mockResolvedValue({ clock: '12:00', tracked: 2, kpi: [], alerts: [] })
  })

  it('loads replay and can switch to live mode', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Раннее предупреждение задержек' })).toBeVisible()
    expect(await screen.findByLabelText('Карта маршрутов')).toBeVisible()
    await waitFor(() => expect(api.frame).toHaveBeenCalled())
    expect(await screen.findByText('07:30')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Live (события)' }))

    await waitFor(() => expect(api.live).toHaveBeenCalled())
    expect(await screen.findByText(/Live · прогноз/)).toBeVisible()
    expect(screen.queryByLabelText('Карта маршрутов')).not.toBeInTheDocument()
  })
})
