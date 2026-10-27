import { defineStore } from 'pinia'
import { ref } from 'vue'

export type Theme = 'dark' | 'light'

// 018 data-model §5 (S4/A4): session-only display preferences. Nothing
// here is persisted — a reload returns to the dark default, and the
// store never touches localStorage.
export const usePrefsStore = defineStore('prefs', () => {
  const theme = ref<Theme>('dark')
  const payloadsEverywhere = ref(false)
  const terminalsEverywhere = ref(false)
  const grid = ref(false)
  const runInContext = ref<string | null>(null)

  return { theme, payloadsEverywhere, terminalsEverywhere, grid, runInContext }
})
