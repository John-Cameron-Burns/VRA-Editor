import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Proxies /api during dev so the Vue dev server and the Flask backend
// are same-origin as far as the browser's concerned -- no CORS setup
// needed, and it matches how production will actually look too (the
// reverse proxy serves the built static files and forwards /api to
// Flask under one hostname). Flask is expected on :8000 in dev --
// see webapp/wsgi.py.
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
