import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SegmentedControl from './SegmentedControl.vue'

const options = [{ value: 'a', label: 'A', count: 0 }, { value: 'b', label: 'B' }]

describe('SegmentedControl', () => {
  it('marks exactly the model value as selected', () => {  // clause: SEGMENTED_CONTROL-1
    const w = mount(SegmentedControl, { props: { options, modelValue: 'b' } })
    expect(w.find('[data-testid="segment-a"]').attributes('aria-checked')).toBe('false')
    expect(w.find('[data-testid="segment-b"]').attributes('aria-checked')).toBe('true')
    expect(w.findAll('.is-selected')).toHaveLength(1)
  })

  it('emits on an unselected option only', async () => {  // clause: SEGMENTED_CONTROL-2
    const w = mount(SegmentedControl, { props: { options, modelValue: 'a' } })
    await w.find('[data-testid="segment-a"]').trigger('click')
    await w.find('[data-testid="segment-b"]').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['b']])
  })

  it('renders a zero count and omits an undefined one', () => {  // clause: SEGMENTED_CONTROL-3
    const w = mount(SegmentedControl, { props: { options, modelValue: 'a' } })
    expect(w.find('[data-testid="segment-a"] .count').text()).toBe('0')
    expect(w.find('[data-testid="segment-b"] .count').exists()).toBe(false)
  })
})
