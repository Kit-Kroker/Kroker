import type { Component } from 'vue'

export interface Profile {
  /** kebab-case, unique within the component */
  name: string
  /** one line, rendered in the showcase and used as the ds card subtitle */
  summary: string
  props: Record<string, unknown>
  slots?: Record<string, string>
  provide?: Record<string | symbol, unknown>
  /** satisfied by the showcase router stub; components using RouterLink need it */
  route?: { path: string }
}

export interface ProfileSet {
  /** snake_case, matches the component directory and the clause ID prefix */
  component: string
  /** Design System pane section, e.g. "Fleet" */
  group: string
  target: Component
  profiles: Profile[]
}

export function defineProfiles(set: ProfileSet): ProfileSet {
  const seen = new Set<string>()
  for (const p of set.profiles) {
    if (seen.has(p.name)) {
      throw new Error(`${set.component}: duplicate profile "${p.name}"`)
    }
    seen.add(p.name)
  }
  if (set.profiles.length === 0) {
    throw new Error(`${set.component}: a component must declare at least one profile`)
  }
  return set
}

/** The single source of the DOM id every consumer agrees on. */
export function profileId(component: string, profile: string): string {
  return `showcase-${component}-${profile}`
}
