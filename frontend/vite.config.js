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
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/guard/video_feed': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // Guard APIs also use the frontend origin; keep /guard itself for React Router.
      '/guard/audio': { target: 'http://localhost:8000', changeOrigin: true },
      '/guard/recognition_log': { target: 'http://localhost:8000', changeOrigin: true },
      '/guard/recognition_cards': { target: 'http://localhost:8000', changeOrigin: true },
      '/guard/recognition_image': { target: 'http://localhost:8000', changeOrigin: true },
      '/guard/plate_best': { target: 'http://localhost:8000', changeOrigin: true },
      // WebSocket proxy
      '/guard/ws': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
