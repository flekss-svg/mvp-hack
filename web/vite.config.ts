import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В разработке фронтенд живет на 5173 и ходит в API на 8000 через прокси, поэтому в коде
// адреса всегда относительные (/api/...). В проде собранный dist отдает сам FastAPI.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
