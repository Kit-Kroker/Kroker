# FR-502 ops risk-classing — design (2026-11-19)

Owner ruling (this session): complete FR-502's open clause ("ops actions
SHALL be risk-classed", `PRD.md:293`) as a **classification + gate
mechanism with zero execution**. The 023a GATE 2 ruling stands unchanged:
ops actions are proposals, never executed.

## Intent

Close the gap found at the FR-502 close-out: the repair gate's
`human_only` is decided **only by round** (`gate_round > 1`,
`workflows/maintenance.py:374`), so an ops-bearing plan at round 1 above
threshold is built SOFT and stamped `approved / decided_by="policy"`
before `may_execute`'s policy path refuses the ops part
(`execution.py:322-323`) and bounces the incident to a human gate. The
never-execute invariant holds at the execution layer, but the gate layer
lets **policy "approve" a plan containing ops actions** — the approval
record misstates who is accountable, and "ops ⇒ human decision" is not
structural.

After this change: any human-required action hardens the repair gate at
construction; policy can never approve an ops-bearing plan; only a human
decision resolves it (and still executes only the code_fix subset —
GATE 1 Q6 semantics unchanged).

## Goals

- Pure classification: ops verbs (`rollback|restart|scale`) →
  `RiskClass.HUMAN_REQUIRED`; `code_fix` → no class (confidence governs).
- The gate conjunct: `human_only = gate_round > 1 or
  bears_human_required(plan)`, so an ops-bearing plan's gate is HARD from
  birth and the auto-decision is structurally impossible.
- Risk classes surface twice: the gate context names the human-required
  actions ("bears human-required ops: rollback"), and `maintain
  incidents` gains a class column.
- FR-502 flips `[x]` after fresh verification (both clauses then
  delivered), with log prepend, §7 banner, and the `maintenance/AGENTS.md`
  invariant row.

## Non-goals / anti-goals

- **No execution of ops actions** — `OPS_REFUSAL_OUTCOME` stays as the
  execution-layer backstop (defense in depth, not the primary guard).
- No rollback/restart/scale adapters, no deploy-plan persistence, no
  deploy liveness (past-P4 scope, deferral stands).
- No maintainer-agent self-classification — classification is
  deterministic and code-side (the code-computed confidence floor
  precedent; a stored field would trust agent judgment for a safety
  property and put wire data where policy belongs).
- PRD untouched — the clause is met by building the mechanism, not by
  rewording.
- GATE 1 Q6 unchanged: a human approval of a mixed plan executes the
  `code_fix` subset only.

## Constraints

- `gate.py` purity (no I/O, no Temporal, no config surface); **no new
  `MaintenanceConfig` gate fields** — R9's "no configuration can open the
  repair gate" stays literal.
- Replay safety: pure-code_fix plans byte-identical. The conjunct rides
  `workflow.patched("maint-risk-class")`, the marker taken **only** for
  ops-bearing plans (the `maint-023b-execute` precedent), so old
  histories and code_fix-only paths schedule exactly the commands they
  always did.
- `tests/replay/` untouched; benchmark registry untouched.
- No stored `risk_class` field on `RepairAction`/`RepairPlan` — computed
  at gate-build and render time (changing the proposer `output_type` wire
  would ripple histories for nothing).

## Approaches

1. **Honest 2-form taxonomy (picked)**: `RiskClass.HUMAN_REQUIRED` for
   all three ops verbs today, absent for `code_fix`; the structure
   discriminates when adapters exist.
2. Rich vocabulary now (rejected): `REVERSIBLE/DESTRUCTIVE/…` mapped
   from three verbs that all land human-required at the gate — the
   constant-table dressing the skeptic pre-critiqued (023 consults,
   skeptic (b)1).
- Conjunct placement: **gate construction** (picked) vs auto-approve
  branch only (rejected — SOFT settings would claim auto-approvable
  while silently waiting for a human; the record lies).
- Render: **gate text + incidents column** (picked) vs gate-text-only
  (rejected — the operator scanning `maintain incidents` wouldn't see
  classes).

## The how (decided)

- `RiskClass` enum in `maintenance/models.py` (one member:
  `HUMAN_REQUIRED`; grows with adapters).
- `risk_class(action: RepairAction) -> RiskClass | None` and
  `bears_human_required(plan: RepairPlan) -> bool` — pure functions in
  `gate.py` (they feed gate construction).
- `workflows/maintenance.py::_repair_gate`:
  `human_only = inc.gate_round > 1 or (workflow.patched("maint-risk-class")
  and bears_human_required(inc.plan))`; the existing `auto` condition
  already follows `human_only`.
- Gate context (`gate_context_text`) gains the human-required action
  names when present.
- `render.py`: incidents table gains a bounded class column (`-` for
  pure code_fix plans).
- Tests (RED first):
  - fast pure: classification cells (each verb → `HUMAN_REQUIRED`,
    `code_fix` → `None`, mixed/ops-only plans → `bears_human_required`
    True, code_fix-only → False);
  - fast workflow-tier: mixed plan, round 1, above threshold → gate HARD,
    no policy auto-decision, human APPROVE executes the code_fix subset;
    pure code_fix, round 1, above threshold → SOFT auto-approve unchanged
    (the regression pin);
  - temporal e2e: one mixed-plan → human-gate → code-fix-child cell in
    the 023b US-suite style.

## Left to the builder

- Exact column header/format in `render.py` (keep the table bounded; the
  023b render bounds are the precedent).
- New `tests/maintenance/test_risk_class.py` vs extending an existing
  suite file (prefer the new small file).
- Whether the temporal cell needs a new fixture or reuses the US5
  overlap fixtures (reuse where possible).
