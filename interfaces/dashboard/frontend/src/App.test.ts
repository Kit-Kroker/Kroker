import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import App from './App.vue'

describe('App', () => {
  it('boots and renders the sentinel', () => {
    const w = mount(App)
    expect(w.find('[data-testid="boot-sentinel"]').text()).toBe('SDLC Factory Console')
  })
})
