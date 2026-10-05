# Baseline: Decision Inbox (010)

Recorded by T001 on branch `010-decision-inbox`.

## Base sha

`18de7f1` ("feat(runs): one runs/ tree with pipeline/benchmarks/ops series"),
one commit past the spec base `39a07a4`.
`git diff --stat 39a07a4 HEAD -- interfaces README.md ROADMAP.md` printed
nothing (verified at branch time), so the commit this branch is cut from
touches nothing this plan relies on.

## check_ui.py (host, Node v25.9.0, run 2026-10-05 ~23:38–23:45)

| Step | Result |
|---|---|
| install | pass (216 packages added; 5 npm audit findings pre-exist) |
| typecheck | pass (vue-tsc, dashboard) |
| typecheck-ui | pass (vue-tsc, @kroker/ui) |
| build-dashboard | pass (191 modules) |
| build-ui | pass (143 modules) |
| vitest-dashboard | pass |
| playwright-browser | pass (chromium present) |
| ds-bundle | pass |
| vitest-ui | pass |
| playwright | pass |

No skipped step. No pre-existing failure. No timeout flake.

Note: the first run of `check_ui.py` failed at `install` with EACCES because
`node_modules/sdlc-dashboard` and `node_modules/@kroker/ui` were junctions
with **relative** targets (`../interfaces/...`), which Windows cannot
resolve. Both junction points were removed (`rmdir`, targets untouched) and
`npm ci` recreated correct ones. Recorded here because it is an environment
repair, not a source change.

## Test counts

| Suite | Files | Tests | Result |
|---|---|---|---|
| vitest-dashboard (sdlc-dashboard) | 35 | 374 | all pass |
| vitest-ui (@kroker/ui) | 32 | 147 | all pass |
| playwright (@kroker/ui) | — | 86 | all pass |

## check_clauses.py

`188 clauses declared, 10 untested, 0 dangling`. The ten untested clauses
are pre-existing stage-tier ones (ARCH-1.4, CODE-1.6, CODE-1.7, MERGE-1.6,
MERGE-1.7, MERGE-1.8, MERGE-1.9, PLAN-1.4, RETRO-1.6, REVIEW-1.6); every
CONSOLE clause has a test.

## Name check (data-model §5 against `F/api/types.ts`)

Part 1 (interfaces/types, lines 1–100): every name of §1.1 appears exactly
as written — `ClarifyItem` (`type: 'clarify'`, `suggestion`), `GateItem`
(`type: 'gate'`, `gate: string`), `OverrideItem` (`type: 'override'`,
`gate: 'merge'`, `verdict`, `checks: CheckRow[]`), `EscalationItem`
(`type: 'escalation'`, `analysis`), common fields `id`, `runId`, `round`,
`age`, `type`, `title`, `body`; `CheckRow` (`name`, `kind:
'ABSOLUTE' | 'ADVISORY'`, `ok: boolean`, `detail`); `GateOutcome =
'approve' | 'revise' | 'reject'`; `InboxItem` union.

Part 2 (client methods, types.ts:118–122): `listInbox(): Promise<InboxItem[]>`,
`answerClarify(runId: string, key: string, answer: string): Promise<void>`,
`decideGate(runId: string, key: string, outcome: GateOutcome, comment: string): Promise<void>`,
`overrideMerge(runId: string, key: string, approve: boolean, justification: string): Promise<void>`,
`resolveEscalation(runId: string, key: string, retry: boolean, guidance: string): Promise<void>`.

**Outcome: no difference from data-model §1.** (SG-1 not triggered.)

## Line counts (for the 1000-line ceiling watch)

| File | Lines |
|---|---|
| `F/app/inbox.store.ts` | 25 |
| `F/api/http.ts` | 210 |
| `F/api/mock/index.ts` | 440 |
| `U/app.md` | 79 |
| `U/app.pw.ts` | 254 |
