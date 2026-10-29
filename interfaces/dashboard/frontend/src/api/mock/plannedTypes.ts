// 018 T066 (V9, A8): the planned node types — a presentation-only mock
// fixture. Planned types render dashed and unplaceable in Design's palette
// (FR-046); there is no read route yet, and the http provider serves none
// until one exists.
export const PLANNED_TYPES: string[] = ['outcome.watch']

export function mockPlannedTypes(): string[] {
  return [...PLANNED_TYPES]
}
