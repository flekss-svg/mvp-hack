import { defineConfig, devices } from '@playwright/test'

// scripts/test-all.sh передает сюда тот же Python, что гоняет pytest (venv или python3).
const python = process.env.PYTHON ?? (process.platform === 'win32' ? 'python' : 'python3')

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `${python} -m uvicorn tests.e2e.server:app --host 127.0.0.1 --port 8765`,
    cwd: '..',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
