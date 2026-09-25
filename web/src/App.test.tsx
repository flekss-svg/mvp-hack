import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import { alert, day, frame, timeline, trip } from './test/fixtures'

vi.mock('./api/client', () => ({
  ApiError: class ApiError extends Error {},
  api: { model: vi.fn(), day: vi.fn(), frame: vi.fn(), timeline: vi.fn(), live: vi.fn() },
}))
vi.mock('./components/MapCanvas', () => ({
  MapCanvas: () => <canvas aria-label="Карта маршрутов" />,
}))
vi.mock('./components/Timeline', () => ({ Timeline: () => <div /> }))
vi.mock('./components/ModelPanel', () => ({ ModelPanel: () => <section /> }))

describe('App', () => {
  beforeEach(() => {
    vi.mocked(api.day).mockResolvedValue(day)
    vi.mocked(api.frame).mockResolvedValue(frame)
    vi.mocked(api.timeline).mockResolvedValue(timeline)
    vi.mocked(api.live).mockResolvedValue({ clock: '12:00', tracked: 2, kpi: [], alerts: [] })
  })

  it('loads the recorded day and switches to live mode', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Раннее предупреждение задержек' })).toBeVisible()
    expect(await screen.findByLabelText('Карта маршрутов')).toBeVisible()
    expect(await screen.findByText('07:30')).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'Live (события)' }))

    await waitFor(() => expect(api.live).toHaveBeenCalled())
    expect(await screen.findByText(/Live · прогноз/)).toBeVisible()
    expect(screen.queryByLabelText('Карта маршрутов')).not.toBeInTheDocument()
  })

  it('opens the trip card from an alert and closes it', async () => {
    vi.mocked(api.frame).mockImplementation(async (params) => ({
      ...frame,
      alerts: params.trip == null ? [alert] : [],
      trip: params.trip === alert.tripId ? trip : null,
    }))

    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /Конечная/ }))
    expect(await screen.findByRole('heading', { name: /Маршрут 42/ })).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: 'закрыть' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: /Маршрут 42/ })).toBeNull())
  })
})
