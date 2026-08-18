/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      // One origin (D2): the backend serves board + dashboard on 8500.
      '/api': { target: 'http://127.0.0.1:8500', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
  },
})
