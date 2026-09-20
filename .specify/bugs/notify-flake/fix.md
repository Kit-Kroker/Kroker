# Bug Fix: Replay-harness notify race — register the activities the golden histories schedule

- **Slug**: notify-flake
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

The harness activity bundles now register every activity type the committed
golden histories schedule — a no-op `fake_notify` (returns the `Results`
contract, zero deliveries) in all 9 notify-scheduling bundles and an
empty-plan `fake_plan_research` in research_greenfield — eliminating the
unregistered-activity WFT-collision race behind the full-file flake, plus a
consolidated deterministic contract file pinning registration completeness.
Harness-only: no `src/` change, no golden or history file touched.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `tests/replay/scenarios.py` | modified | +`fake_notify`, +`fake_plan_research`; registered in `_base_activities`, `_budget_activities`, and the 7 inline bundles (brownfield_happy, arch_timeout_reject, waves, seeded, research_greenfield — also `fake_plan_research`, cancel_during_code, partial_awaiting_architecture). 40 insertions, 0 deletions. |
| `tests/replay/test_notify_registration_chaos.py` | added (45a7275, adopted) then consolidated (376dc93) | qa-chaos's RED file adopted verbatim per ruling; qa-happy's unique pins folded in (production-transport purity, no-drop guard, golden file-set + notify-count freeze) plus qa-chaos's proposed duplicate-name guard; `test_activity_registration.py` retired as the duplicate. |
| `tests/replay/test_activity_registration.py` | removed (376dc93) | qa-happy's RED file (b89e11e), subsumed — it pinned the same contract over a smaller scenario set (15 golden scenarios vs 16 files) and predated the plan_research discovery. |
| `.specify/bugs/notify-flake/*.md` | added | assessment + both qa red reports + this report + test report; branch carries the whole record. |

Commits on `fix/notify-flake`: b89e11e (qa-happy RED, pre-existing) →
45a7275 (adopt qa-chaos RED + reports) → 376dc93 (consolidate) → a8f9ac6
(the fix).

## Diff Highlights

```python
@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:
    return Results()  # out.results iterated OUTSIDE _notify's try/except


@activity.defn(name="plan_research")
async def fake_plan_research(inp: PlanInput) -> ResearchPlan:
    return ResearchPlan()  # EMPTY plan → same all-findings-failed degrade branch
```

## Tests Added or Updated

- `tests/replay/test_notify_registration_chaos.py` — 77 items: registration
  completeness per scenario (all 16 golden files, notify-inclusive sweep),
  plan_research sweep row, helper rows, Results-contract rows with
  deadline=None/project=None boundaries, purity row (never the production
  transport), no-drop guard, duplicate-name guard, golden file-set +
  per-file notify-count freeze (34 schedulings).
- RED→GREEN evidence: the pre-fix state of the CURRENT 77-item file is
  29 RED / 48 green (verified in this worktree at base; the pre-fix run
  log `.workspace/tmp/nf-wt-red-pre-fix.txt` is a COMBINED run — its 53
  FAILED lines are 29 from this file + 24 from qa-happy's then-separate
  `test_activity_registration.py`, the pre-consolidation 44-item state of
  which was 29 RED / 15 green) → 77/77 green after a8f9ac6
  (`.workspace/tmp/nf-wt-green-contract.txt`).

## Local Verification

- `uv run --frozen pytest tests/replay/test_notify_registration_chaos.py -q`
  → exit 0, 77/77 (post-fix).
- Per-scenario SG-1 gate: 15/15 scenarios exit 0, one pytest invocation each
  (`.workspace/tmp/nf-ps-*.txt`). The 16th golden, partial_awaiting_
  architecture, has no graph-golden replay (`golden=False`); its coverage is
  test_fixtures_present + the contract sweep.
- Statics: `ruff check .`, `ruff format --check .`, `mypy`,
  `scripts/check_file_size.py` — all exit 0.
- Fast pytest tier (`uv run --frozen pytest -q`) → exit 0.
- Golden byte-identity: `git status` + `git diff main --stat` over
  `tests/replay/golden/` and `tests/replay/histories/` — empty; the
  contract's count-freeze row pins the projections in-test as well.
- Race elimination: `not registered` appears in ZERO of this branch's
  full-file run logs; the same grep on the baseline run at main 2c732e0
  finds the explicit NotFoundError (see Deviations).

## Deviations from Assessment

None in the fix itself — the remediation landed exactly as assessed.
**However, the full-file leg of the verification gate is BLOCKED by a
second, PRE-EXISTING race this fix does not address** (detailed in
./test.md): the driver-signal vs gate-schedule-tick race, proven to flake
identically at main 2c732e0 without this branch's changes
(`.workspace/tmp/nf-baseline-ff-run2.txt` — same budget_arch_reject-
sandboxed command divergence at index 11 AND the old "not registered"
error in the same log). The brief's out-of-scope list explicitly excludes
"any other flake", so this seat stopped at the gate instead of expanding
scope. Ruling requested.

## Follow-ups

- Orchestrator ruling on the driver-vs-tick race (new bug file suggested:
  separate slug, e.g. `golden-tick-race`).
- If ruled in scope elsewhere: the determinism lever is the drivers'
  `wait_for` 50ms real-time poll racing skipped-time gate schedule ticks;
  pinning the decision to a tick boundary (or a schedule-consumed signal)
  is the shape — harness-only, same constraint set.
