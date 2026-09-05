import type { InboxItem } from '../api/types'

export interface AdaptedInboxItem {
  id: string
  kind: string
  title: string
  age: string
}

export function toInboxItem(item: InboxItem): AdaptedInboxItem {
  return {
    id: item.id,
    kind: item.type,
    title: item.title,
    age: item.age,
  }
}
