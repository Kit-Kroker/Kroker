import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { InboxItem } from '../api/types'

export const useInboxStore = defineStore('inbox', () => {
  const items = ref<InboxItem[]>([])
  const drafts = ref<Record<string, string>>({})
  const editing = ref<Record<string, boolean>>({})
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    try {
      items.value = await api.listInbox()
    } finally {
      loading.value = false
    }
  }

  function setDraft(id: string, v: string) {
    drafts.value[id] = v
  }
  function toggleEdit(id: string) {
    editing.value[id] = !editing.value[id]
  }

  return { items, drafts, editing, loading, refresh, setDraft, toggleEdit }
})
