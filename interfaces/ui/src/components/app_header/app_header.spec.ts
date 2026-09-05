import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AppHeader from './AppHeader.vue'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
}

describe('AppHeader', () => {
  it('renders brand, tabs, and supplied stats', () => {  // clause: APP_HEADER-1
    const w = mount(AppHeader, {
      props: {
        activeCount: 7,
        maxCount: 50,
        totalCost: '$19.80',
        inboxCount: 2,
      },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.text()).toContain('SDLC·FACTORY')
    expect(w.text()).toContain('FLEET')
    expect(w.text()).toContain('INBOX')
    expect(w.text()).toContain('runs 7/50')
    expect(w.text()).toContain('spend today $19.80')
  })

  it('omits inbox badge when count is zero, never rendering 0', () => {  // clause: APP_HEADER-1.1
    const w = mount(AppHeader, {
      props: { inboxCount: 0 },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    expect(w.find('[data-testid="inbox-count"]').exists()).toBe(false)
  })

  it('applies tab-active stable class to active tab', () => {  // clause: APP_HEADER-2
    const w = mount(AppHeader, {
      props: { activeTab: 'inbox' },
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    const tabs = w.findAll('.tab')
    expect(tabs[1].classes()).toContain('tab-active')
  })

  it('emits start-run when start button is clicked', async () => {
    const w = mount(AppHeader, {
      global: { stubs: { RouterLink: RouterLinkStub } },
    })
    await w.find('[data-testid="start-btn"]').trigger('click')
    expect(w.emitted('start-run')).toHaveLength(1)
  })
})
