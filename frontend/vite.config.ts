import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Dev: forward API calls to uvicorn so the app and API share an origin (no CORS).
    proxy: { '/api': 'http://localhost:8000' },
  },
})
