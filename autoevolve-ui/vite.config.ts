import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/company': 'http://127.0.0.1:8787', '/openapi.json': 'http://127.0.0.1:8787' },
  },
  test: { environment: 'jsdom', exclude: ['tests/e2e/**', 'node_modules/**'] },
})
