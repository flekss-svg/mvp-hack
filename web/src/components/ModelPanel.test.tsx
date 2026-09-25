import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ModelPanel } from './ModelPanel'

afterEach(() => vi.restoreAllMocks())

describe('ModelPanel', () => {
  it('loads and renders model quality', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          horizon: '10–15 мин',
          threshold: 3,
          recall: 70,
          precision: 83,
          baselinePrecision: 56,
          prAuc: 0.87,
          baselinePrAuc: 0.66,
          testSize: 100,
          features: [{
            key: 'delay_now',
            label: 'Текущее опоздание',
            importance: 33.7,
            share: 1,
          }],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    render(<ModelPanel />)

    expect(screen.getByText('Загрузка метрик…')).toBeVisible()
    expect(await screen.findByRole('heading', { name: 'Качество модели' })).toBeVisible()
    expect(screen.getByText('Текущее опоздание')).toBeVisible()
    expect(screen.getByText('33.7')).toBeVisible()
  })

  it('shows an API error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Метрики недоступны' }), {
        status: 503,
        headers: { 'Content-Type': 'application/json' },
      }),
    )

    render(<ModelPanel />)

    expect(await screen.findByText('Метрики недоступны')).toBeVisible()
  })
})
