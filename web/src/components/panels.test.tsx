import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { incident, jsonResponse, model, trip } from '../test/fixtures'
import { AlertList } from './AlertList'
import { Header } from './Header'
import { Legend } from './Legend'
import { ModelPanel } from './ModelPanel'
import { Segmented } from './Segmented'
import { TripPanel } from './TripPanel'

afterEach(() => vi.restoreAllMocks())

describe('Header and Legend', () => {
  it('render KPI and the connection status', () => {
    render(
      <>
        <Header clock="08:05" subtitle="Тестовый день" status="SIMULATION"
          kpi={[{ key: 'high', label: 'риск', value: '2', tone: 'high' }]} />
        <Legend threshold={3} />
      </>,
    )
    expect(screen.getByText('08:05')).toBeVisible()
    expect(screen.getByText('2')).toBeVisible()
    expect(screen.getByText('СИМУЛЯЦИЯ')).toBeVisible()
    expect(screen.getByText(/3 мин/)).toBeVisible()
  })
})

describe('Segmented', () => {
  it('marks the selected option and reports clicks', async () => {
    const onChange = vi.fn()
    const options = [{ value: 'all', label: 'Все' }, { value: 'bus', label: 'Автобусы' }]
    render(<Segmented label="Transport" value="all" onChange={onChange} options={options} />)

    expect(screen.getByRole('button', { name: 'Все' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Автобусы' }))
    expect(onChange).toHaveBeenCalledWith('bus')
  })
})

describe('AlertList', () => {
  it('selects an incident', async () => {
    const onSelect = vi.fn()
    render(<AlertList alerts={[incident]} onSelect={onSelect} empty="Пусто" updatedAt={Date.now()} now={Date.now()} />)
    await userEvent.click(screen.getByRole('button', { name: /Конечная/ }))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it('shows the empty message', () => {
    render(<AlertList alerts={[]} onSelect={vi.fn()} empty="Пусто" updatedAt={null} now={Date.now()} />)
    expect(screen.getByText('Пусто')).toBeVisible()
  })
})

describe('TripPanel', () => {
  it('closes', async () => {
    const onClose = vi.fn()
    render(<TripPanel trip={trip} tripId={1} updatedAt={Date.now()} now={Date.now()} onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: /закрыть|Все инциденты/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('shows the offline status inline', () => {
    render(<TripPanel trip={{ ...trip, onLine: false }} tripId={1} updatedAt={null} now={Date.now()} onClose={vi.fn()} />)
    expect(screen.getByText('Не на линии')).toBeVisible()
  })

  it('renders a finished forecast with its outcome and next stops', () => {
    const finished = {
      ...trip,
      delay: -1,
      risk: null,
      level: 3 as const,
      outcome: { late: true, delay: 1.5 },
      next: [{ stop: 'Конечная', plan: '08:30' }],
    }
    render(<TripPanel trip={finished} tripId={1} updatedAt={Date.now()} now={Date.now()} onClose={vi.fn()} />)
    expect(screen.getByText(/Рейс скоро завершится/)).toBeVisible()
    expect(screen.getByText(/Фактический исход: Опаздывает на 1\.5 мин/)).toBeVisible()
    expect(screen.getByText(/Следующая: Конечная · 08:30/)).toBeVisible()
  })
})

describe('ModelPanel', () => {
  it('loads and renders model quality', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(model))
    render(<ModelPanel demo={false} />)
    await userEvent.click(screen.getByText('Качество прогноза'))

    expect(await screen.findByText('Текущее опоздание')).toBeVisible()
    expect(screen.getByText('33.7')).toBeVisible()
  })

  it('shows an API error with a retry button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'Метрики недоступны' }, 503))
    render(<ModelPanel demo={false} />)
    await userEvent.click(screen.getByText('Качество прогноза'))
    expect(await screen.findByText(/Сервис данных недоступен/)).toBeVisible()
  })
})
