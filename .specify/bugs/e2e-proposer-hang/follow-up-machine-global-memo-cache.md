# Follow-up card: machine-global memo cache root (deferred Mechanism 2)

Deferral ruling: 2026-09-20 cause gate for e2e-proposer-hang cleared with
Mechanism 1 (unbounded retries on `AGENT_ACTIVITY_CONFIG`) as the fix target;
this card carries Mechanism 2 so it is not lost. Full evidence lives in
`chaos-qa-findings.md` (same directory), §"machine-global memo cache masks
the hang".

## Defect

`src/sdlc/memoization/cache.py::_cache_root()` defaults to
`%TEMP%/sdlc/memo_cache` — machine-global, shared across checkouts, branches,
and runs — and the risk/discover memo keys are pure content
(`project|tree_hash|map_digest|rules_sha|prompt_sha|model`). Any earlier run
of the same scenario anywhere on the machine (including the primary
checkout) leaves a judged entry under the exact key a later run computes, so
`_assess`/`_discover` can hit the memo and never await the proposer at all.

## Why it mattered to this bug

It made the reported hang **cold-cache-only** and cache-temperature
dependent: the same test passes on warm machines and wedges on cold ones
(tier position #102 runs before the memo-warming test). It is also why the
1.30-vs-1.31 temporalio theory was a dead end.

## Scope decision (this bug's ruling)

Production behavior of `_cache_root()` is deliberately NOT changed here.
The e2e proposer tests isolate `SDLC_MEMOIZATION_CACHE_ROOT` to a per-test
`tmp_path` directory (test-side only, the same isolation the chaos file's
`assessed_repo` fixture already applies), which makes the RED/GREEN of this
bug's tests deterministic on any machine.

## Candidate directions for the fixer (unruled)

- Scope the default root per checkout (e.g. under the repo's cache dir) so
  content keys cannot cross checkouts; or
- Add the checkout/worktree identity to the memo key; or
- Keep the machine-global root but namespace it per resolved repo path.
- Whichever direction, `test_a_second_assessment_of_the_same_tree_hits_the_memo`
  (DD10, self-contained two-run memo hit) must stay green, and any cross-run
  memo reuse that production intentionally provides must be re-stated as a
  contract with tests that do not depend on machine history.
