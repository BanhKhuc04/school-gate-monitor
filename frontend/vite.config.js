import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Proxy only API and specific guard endpoints — NOT root /guard
      // (React Router handles /guard as a SPA route)
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      '/guard/video_feed': {
        target: 'http://localhost:8001',
        changeOrigin: true,
      },
      // WebSocket proxy
      '/guard/ws': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
