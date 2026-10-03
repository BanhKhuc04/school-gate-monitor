// Vite config dedicated to the browser integration runner — proxy to the
// QA backend port set via env. Used by scripts/run_browser_integration.sh
// alongside scripts/qa_launcher.py. The default frontend/vite.config.js
// keeps the dev port 8001.
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const QA_BACKEND_PORT = process.env.QA_BACKEND_PORT || '8002';
const QA_BACKEND_HOST = process.env.QA_BACKEND_HOST || '127.0.0.1';
const QA_FRONTEND_PORT = process.env.QA_FRONTEND_PORT || '5187';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(QA_FRONTEND_PORT),
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api':         { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/media':       { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/guard/video_feed':    { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/guard/ws':            { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true, ws: true },
      '/guard/audio':         { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/guard/recognition_log':{ target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/guard/recognition_cards': { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/guard/recognition_image':{ target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
      '/guard/plate_best':    { target: `http://${QA_BACKEND_HOST}:${QA_BACKEND_PORT}`, changeOrigin: true },
    },
  },
  preview: {
    port: Number(QA_FRONTEND_PORT),
    strictPort: true,
    host: '127.0.0.1',
  },
});