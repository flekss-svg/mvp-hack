import { expect, test } from '@playwright/test'

test('production dashboard opens and its main API requests pass', async ({ page, request }) => {
  for (const path of [
    '/api/health',
    '/api/model',
    '/api/replay/day',
    '/api/replay/frame?t=485',
    '/api/replay/timeline',
  ]) {
    const response = await request.get(path)
    expect(response.ok(), `${path} returned ${response.status()}`).toBe(true)
  }

  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Контроль движения' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Симуляция' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Воспроизвести' })).toBeVisible()
  await expect(page.getByLabel('Yandex Map Москвы')).toBeVisible()
  expect(errors).toEqual([])
})
