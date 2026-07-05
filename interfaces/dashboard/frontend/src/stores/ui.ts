import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProjectMode } from '../api/types'

export interface Toast {
  id: number
  msg: string
  color: string
}

export const useUiStore = defineStore('ui', () => {
  const toasts = ref<Toast[]>([])
  const startOpen = ref(false)
  const startTitle = ref('')
  const startRepo = ref('')
  const startMode = ref<ProjectMode>('brownfield')
  let next = 1

  function toast(msg: string, color = '#4fae7f') {
    const id = next++
    toasts.value.push({ id, msg, color })
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
  }

  return { toasts, startOpen, startTitle, startRepo, startMode, toast, openStart, closeStart, resetStartForm }
})
