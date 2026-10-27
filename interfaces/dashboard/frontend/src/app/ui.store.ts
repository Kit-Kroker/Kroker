import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProjectMode } from '../api/types'
import type { ToastItem, ToastKind } from '@kroker/ui/components/toasts/Toasts.vue'

export interface Toast extends ToastItem {
  id: number
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const startOpen = ref(false)
  const startTitle = ref('')
  const startRepo = ref('')
  const startMode = ref<ProjectMode>('brownfield')
  // 011 US2: the start form's budget text ('' = none); the shell converts
  // on submit, the library modal validates.
  const startBudget = ref('')
  let next = 1

  // 018 R-10: a status kind, not a colour — Toasts.vue maps it to the
  // theme token.
  function toast(msg: string, kind: ToastKind = 'done') {
    const id = next++
    toasts.value.push({ id, msg, kind })
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id)
    }, 3800)
  }

  function openStart() {
    startOpen.value = true
  }
  function closeStart() {
    startOpen.value = false
  }
  function resetStartForm() {
    startTitle.value = ''
    startRepo.value = ''
    startMode.value = 'brownfield'
    startBudget.value = ''
  }

  return { toasts, startOpen, startTitle, startRepo, startMode, startBudget, toast, openStart, closeStart, resetStartForm }
})
