import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { api } from './api/client'
import { alert, day, frame, timeline, trip } from './test/fixtures'

vi.mock('./api/client', () => ({
  ApiError: class ApiError extends Error {},
  LIVE_TELEMETRY_ENABLED: true,
  api: { model: vi.fn(), day: vi.fn(), frame: vi.fn(), timeline: vi.fn(), live: vi.fn() },
}))
// Настоящая карта грузит внешний SDK Яндекса — в тестах она заменяется заглушкой.
vi.mock('./components/TransportMap', () => ({
  TransportMap: () => <div aria-label="Карта" />,
}))
vi.mock('./components/Timeline', () => ({ Timeline: () => <div /> }))
vi.mock('./components/ModelPanel', () => ({ ModelPanel: () => <section /> }))

describe('App', () => {
  beforeEach(() => {
    vi.mocked(api.day).mockResolvedValue(day)
    vi.mocked(api.frame).mockResolvedValue(frame)
    vi.mocked(api.timeline).mockResolvedValue(timeline)
    vi.mocked(api.live).mockResolvedValue({
      clock: '12:00', tracked: 1, kpi: [], alerts: [],
      vehicles: [{ vehicleId: 1166336, lat: 55.7, lon: 37.5, speed: 40, level: null, risk: null }],
    })
  })

  it('loads the recorded scenario and switches to live mode', async () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Контроль движения' })).toBeVisible()
    expect(await screen.findByLabelText('Карта')).toBeVisible()
    await waitFor(() => expect(api.frame).toHaveBeenCalled())

    await userEvent.click(screen.getByRole('button', { name: 'Live' }))

    await waitFor(() => expect(api.live).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Live' })).toHaveAttribute('aria-pressed', 'true')
    // машина из потока NDTP включает статус LIVE и убирает плашку «ожидание телеметрии»
    expect(await screen.findByText('LIVE · NDTP')).toBeVisible()
    expect(screen.getByText(/ТС на связи: 1/, { selector: '.header-time p' })).toBeVisible()
  })

  it('opens the trip card from an alert and closes it', async () => {
    vi.mocked(api.frame).mockImplementation(async (params) => ({
      ...frame,
      alerts: params.trip == null ? [alert] : [],
      trip: params.trip === alert.tripId ? { ...trip, tripId: alert.tripId } : null,
    }))

    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: /Конечная/ }))
    expect(await screen.findByLabelText(`Подробности ТС ${alert.tripId}`)).toBeVisible()

    await userEvent.click(screen.getByRole('button', { name: /Все инциденты/ }))
    await waitFor(() => expect(screen.queryByLabelText(`Подробности ТС ${alert.tripId}`)).toBeNull())
  })
})
