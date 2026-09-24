/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@kroker/ui': fileURLToPath(new URL('../../ui/src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      // One origin (D2): the backend serves board + dashboard on 8500. The
      // board routes mount at /projects/* (002 FR-020b), the dashboard at /api.
      '/api': { target: 'http://127.0.0.1:8500', changeOrigin: true },
      '/projects': { target: 'http://127.0.0.1:8500', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
  },
})
