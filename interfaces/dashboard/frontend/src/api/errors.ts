// An HTTP failure that keeps its status, so callers branch on the code, not
// on message text. A 404 from /decide is FR-302 working as designed: another
// surface decided first (E-76 spec §7.3).
export class HttpStatusError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
    this.name = 'HttpStatusError'
  }
}

export const isNotFound = (e: unknown): boolean => e instanceof HttpStatusError && e.status === 404
