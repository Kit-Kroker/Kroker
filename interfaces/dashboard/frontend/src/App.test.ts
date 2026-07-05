import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import App from './App.vue'
import { router } from './router'

vi.mock('./api/client', () => ({
  api: {
    listRuns: vi.fn(async () => []),
    listInbox: vi.fn(async () => []),
  },
}))

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('App shell', () => {
  it('mounts and renders the header brand', async () => {
    const w = mount(App, { global: { plugins: [router] } })
    await new Promise((r) => setTimeout(r, 0))
    expect(w.text()).toContain('SDLC·FACTORY')
  })
})
