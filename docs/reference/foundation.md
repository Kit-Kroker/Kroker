# Foundation: contracts, activities, and the deterministic gate

Developer companion to the merged **Foundation** change set. It aligned
`src/sdlc/` with the resolved architecture decisions in
[`architecture-review-2026-07.md`](./architecture-review-2026-07.md) at the
**contract and activity** level. The plan that produced it is
[`superpowers/plans/2026-07-04-foundation-contract-alignment.md`](../superpowers/plans/2026-07-04-foundation-contract-alignment.md).

**Scope:** mechanisms only. The workflow control-flow that *uses* these
mechanisms (revision loop, integration setup/merge orchestration,
token-threshold trigger, running the deterministic gate before the merge
gate) is deliberately **not** wired yet — see
[Deferred to Plan 2](#deferred-to-plan-2). `FeatureWorkflow` still branches
every task from `base_branch` and still gates fresh sessions on
`max_session_resumes`.

---

## What changed, by module

### `sdlc/models.py` — contracts

- **`GateOutcome`** enum: `approve | reject | revise`. Replaces the old
  `GateDecision.approved: bool`, which could not express "send back for
  revision."
- **`GateDecision`** now `{gate, round, outcome, decided_by, reviewer?,
  comments?, guidance?, decided_at?}`. Identity is round-scoped — use
  `gate_key(gate, round)` → `"architecture#1"`. A read-only `approved`
  property (`outcome is APPROVE`) keeps go/no-go call sites working; callers
  that must distinguish reject vs. revise read `outcome`.
- **`MergeVerdict`** `{approve, confidence(0..1), rationale, concerns}` — the
  *advisory* LLM release opinion, split out of `GateDecision`. It only ever
  feeds a soft-gate `auto_decision`; it cannot approve a build the
  deterministic gate would fail, and cannot bypass a hard gate.
- **`HarnessRunResult`** gains `input_tokens, output_tokens, context_window,
  compacted`, and `near_context_ceiling(fraction=0.75)` — `True` when the run
  compacted or `input_tokens > fraction × context_window`; unknown token data
  falls back to `False` (the resume counter still governs).

### `sdlc/harness/adapters.py` — harness abstraction

- **`build_env(req_env, allowlist=ENV_ALLOWLIST)`** replaces the old
  `{**os.environ, **req.env}` passthrough. The harness receives *only*
  allowlisted toolchain vars plus the request's deliberately-injected
  (repo-scoped, short-TTL) credentials — never the worker's full environment.
- **`context_window_for(model)`** / `CONTEXT_WINDOWS`: best-effort model →
  window lookup, filled into `HarnessRunResult.context_window` in the base
  `run()`. Both adapters parse `usage.{input,output}_tokens` from the harness
  JSON. (opencode's usage keys are assumed to mirror Claude's — confirm
  against a live run when the harness is wired.)

### `sdlc/activities.py` — git activities (Finding #1)

The running-integration-branch model, so dependent tasks build on each
other's code:

- **`create_worktree(WorktreeInput{repo_path, run_id, task_id, from_ref})`**
  → `WorktreeHandle{path, branch, branch_point}`. Cuts the worktree from
  `from_ref` (the integration head), under a run-scoped path.
- **`setup_integration_branch(...)`** → integration head SHA. Creates
  `sdlc/<run>/integration` from base in its own worktree.
- **`merge_into_integration(...)`** → `MergeResult{merged, conflict,
  integration_head}`. Distinguishes a *real* conflict (unmerged index
  entries, via `git ls-files --unmerged` read **before** `git merge --abort`)
  from an infrastructure/config failure (raises `RuntimeError`).
- **`get_task_diff`** now anchors to `branch_point` (`<branch_point>...HEAD`,
  three-dot) so a dependent task's diff shows only its own change.
- **`evaluate_gate(QualityGateInput)`** → `GateReport` — thin activity wrapper
  over the pure gate below.
- Worktree root is `SDLC_WORKTREES_ROOT` (default `<tempdir>/sdlc/worktrees`,
  cross-platform), read at call time.

### `sdlc/gate.py` — DeterministicQualityGate (Finding #5, new, pure)

No LLM, no I/O. Consumes typed check evidence and decides pass/fail:

- **`CheckClass`** `absolute | advisory`. **`CheckResult{name, passed,
  classification, detail}`**, **`GateOverride{check, approved_by, reason}`**,
  **`GateReport{passed, blocking, overridden, checks}`**.
- **`build_check(name, passed, requested, detail="")`** forces
  `ABSOLUTE_FLOOR` names (`security_no_critical`) to `ABSOLUTE` even if a
  project marks them advisory.
- **`evaluate_quality_gate(checks, overrides=None)`**: a failed **absolute**
  check always blocks (override ignored); a failed **advisory** check blocks
  unless a matching audited `GateOverride` is recorded; `passed = not
  blocking`.

### `sdlc/agents/roles.py` & `sdlc/workflows/feature.py`

- `quality_gate_agent`/`t_gate` renamed to **`merge_verdict_agent`** /
  **`t_merge_verdict`** (output `MergeVerdict`, advisory).
- `feature.py` rewired to the new `create_worktree`/`WorktreeHandle`,
  `DiffInput.branch_point`, and `GateOutcome` constructors. No control-flow
  changes.
- Pre-existing broken relative imports (`agents/roles.py` and
  `workflows/feature.py` used `.` where they needed `..`) were fixed — the
  skeleton had never actually imported as a package.

---

## Developer setup

```bash
pip install -e .[dev]        # Python >=3.11; 3.14 works
python -m pytest             # 26 tests, all green — needs `git` on PATH
```

Gotchas worth knowing:

- **New modules need a reinstall.** setuptools' strict editable wheel does not
  auto-discover files added after `pip install -e .` (e.g. `sdlc.gate`). Re-run
  `pip install -e .` after adding a module, or you'll get `ModuleNotFoundError`.
- **Importing the workflow needs an API key.** `agents/roles.py` constructs all
  six `pydantic_ai.Agent`s at *import* time, so importing
  `sdlc.agents.roles` / `sdlc.workflows.feature` / `sdlc.worker` requires
  `ANTHROPIC_API_KEY` set (a dummy value is fine for import-only — no network
  call happens at construction). Fixing this (lazy construction) is the first
  Plan 2 cleanup.
- **`SDLC_WORKTREES_ROOT`** overrides where worktrees are created; the test
  suite points it at a temp dir.
- Use `python -m pytest` (not bare `pytest`) if the Scripts dir isn't on PATH.

---

## Deferred to Plan 2

The mechanisms above are ready but not orchestrated. See the
[Implementation status table](./architecture-review-2026-07.md#implementation-status-2026-07-04)
for the full map. In short, Plan 2 (the P1 end-to-end greenfield slice) wires:

- `setup_integration_branch` / `merge_into_integration` into `FeatureWorkflow`.
- The gate-revision loop (`revise` outcome) with round-scoped signal keys.
- The `near_context_ceiling` token trigger into the dev-task loop.
- `DeterministicQualityGate` **before** the `MergeVerdict` consult (SC-5) — so
  keep `gates["merge"] = hard` until then.
- The harness `pre_tool` hook, credential injection, and tiered isolation.
- Lazy agent construction (the API-key-at-import smell above).
