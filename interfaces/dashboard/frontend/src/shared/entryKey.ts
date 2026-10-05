// FR-012: the only way a per-entry key is formed. Run ids are Temporal
// workflow ids and item ids are free-form ('#' already occurs), so no
// separator can be proved absent from both; the JSON pair encoding is
// collision-free for any two strings.
export function entryKey(item: { runId: string; id: string }): string {
  return JSON.stringify([item.runId, item.id])
}
