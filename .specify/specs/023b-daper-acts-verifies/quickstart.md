# Quickstart — validating round 023b

Prerequisites:
- The same as 023a (`.specify/specs/023-daper-maintenance-loop/quickstart.md`): `uv sync --frozen --extra dev`, and `.venv/bin` on PATH.
- The temporal tier uses the fixture-spawned dev server.
- The repair child is a **stubbed `GraphWorkflow`-compatible child** registered in the test worker. It exposes the same `pending_decisions` / `run_state` queries and the `submit_gate_decision` signal, and it is scripted to commit a fix (or a non-fix) on its integration branch, park at `merge`, then honour approve or reject. No model or harness spend happens anywhere below §5.

## 1. Pure-domain tier (fast, no Temporal)

```bash
pytest -q tests/maintenance/ -m "not temporal"
```

Expected outcomes:
- **`may_execute`** (research R6). Policy is accepted only for mechanical, all-`code_fix`, `consecutive_seen >= 2`, `reopens == 0`, `effective > threshold`. The matrix covers a threshold of 0.55 with a reproduced judgement plan, a mixed plan, a reopened plan, and a stale non-consecutive reproduction, and each is refused (SC-B02).
- **`apply_verdict`** (R11). It gives exactly 3 attempts at `max_reopens=2`, then `escalated`. A non-retryable configuration failure escalates on attempt 1. A per-cycle `PERSISTED` never moves `reopens`.
- **`step()` additions** (R7–R9). `approved`/`queued` + RESOLVED → `resolved_externally`. `executing`/`verifying` are untouched by Detect. `verified` + absent goes to the closure check, never to `resolved_externally` directly. PERSISTED refreshes `finding` and `commit_sha`. `consecutive_seen` resets on a not-collected cycle.
- **`choose_starts`** (R10). Over 3 approved incidents with a per-cycle cap of 1, one starts and two are `queued`. A full 7-day window starts nothing. Path overlap queues the second incident. Window pruning uses the injected `now`.
- **Merge-decision builder.** Only `REJECT` is ever constructed (SC-B10).
- **Refusal rounds are human-only.** At threshold 0.55, a reproduced judgement plan is refused once. The next `repair:<n>` round has no auto-decision, the operator is notified, and there is no re-approve loop (plan review, gap 2).
- **Ops are never executed** (SC-B03, GATE 1 Q6).
  - A human-approved mixed plan (ops + `code_fix`) gives `repair_work_for` with only the `code_fix` action, and the ops action is recorded `not executed — ops proposal only`.
  - An ops-only plan, even human-approved, starts nothing and is recorded the same way.
  - No code path builds an ops execution.
- **Execute off.** With `execute=False`, `step()` leaves `finding`/`commit_sha`/`consecutive_seen` exactly as 023a does.
- **`confidence_floor`** with `reopens=1` on a mechanical plan floors at 0.75, which is human-gated at 0.8.
- **`repair_work_for`** names the signal, rule and version, lists every `code_fix` action, and does not contain "Change nothing else".
- **Memory and state.** `render_retention` is bounded. `MemoryKind` has both new kinds. For the captured 023a `MaintenanceState` fixture: the 023a payload validates under the new models; every 023a field round-trips unchanged (`json.loads` of the fixture equals the new `model_dump(mode="json")` with the 023b-added keys removed); and every 023b-added field takes its default (R7).
- **`MaintenanceConfig`.** `execute=True` without the acknowledgement, or with `build_probe=False`, is refused.

## 2. Workflow tier

```bash
pytest -q -m temporal tests/maintenance/
```

Expected outcomes, using the stub child and the fixture repo:
- **Abandon survives roll-over** (R1; the first test written, SC-B11). A child started with ABANDON keeps running across a forced `continue_as_new` (`max_cycles_per_history=2`), and the next history re-attaches through `probe_repair_child`.
- **Execute does not block** (SC-B05). With an approved mechanical incident, exactly one child starts with the R1 id. The cycle returns while the child is still parked, and further nudged cycles complete.
- **Clean fix** (SC-B01). The child parks at merge, the verification branch is built from `base_sha`, the re-detect is collected, and the verdict is `resolved`. The incident goes to `verified`, and the child's merge gate is still pending for a human.
- **Non-fix** (SC-B01, SC-B10). The verdict is `persisted`. The child receives exactly one `REJECT` (`decided_by="policy"`), no PR step runs, and the incident goes to `reopened`. A second and third non-fix lead to `escalated`. The verify worktree and ref are gone after each attempt.
- **Closure** (SC-B04). A human approves the child's merge in the test, and the stub merges its integration head into the default branch. The next collected default-branch Detect closes the incident and writes one `INCIDENT_LESSON` record to the fake memory. A squash-style merge (head not an ancestor) gives `resolved_externally` with an `INCIDENT_EXPERIENCE` record.
- **Caps** (SC-B06). Three approved incidents with a cap of 1 give one start per cycle, and the others go to `queued` and keep their approval (no second gate).
- **Restart** (SC-B08). A worker killed between the start decision and its acknowledgement, with `max_cached_workflows=0`, leads to exactly one child, one execution record and one gate.
- **Child timeout.** A child that never parks is cancelled at `child_timeout_hours` (time-skipped), and the attempt counts as failed.
- **Memory outage** (SC-B07). A failing fake memory still lets the cycle complete, the incident still closes, and `retained` is set only after an attempt.
- **Execute off** (B-FR-018). The 023a e2e tests run unchanged and pass. An approval lands `approved_not_executed`.
- **Advisory kind.** The workflow tier still runs `advisory_source=none` (no OSV egress in tests), so advisory execution is unit-tier only. This is recorded as a residual in `verification.md` (spec Part D.2).
- **Replay.** Each new test's history replays clean through `Replayer`.

## 3. Regression battery (SC-B09)

```bash
ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py
pytest -q                                      # fast tier
pytest -q tests/replay/                        # existing goldens unchanged
pytest -q -m temporal tests/maintenance/ tests/test_tidyup*.py tests/test_triage_workflow_e2e.py
```

- The fast tier must fail only on the ids in this round's `baseline-failures.txt` (captured at A1 on HEAD; 2 known ids expected per `f576d2f7`: the prompt-SHA tripwire and SC-003-awaiting-records). The sorted FAILED lists must be identical.
- `git status --short tests/replay/` must be empty.

## 4. CLI smoke (local Temporal, no spend)

```bash
sdlc maintain enable demo --repo /tmp/m-demo --execute                  # refused: needs --ack-unattended-build-probe
sdlc maintain enable demo --repo /tmp/m-demo --no-build-probe --execute # refused: --execute needs the build probe
sdlc maintain enable demo --repo /tmp/m-demo --ack-unattended-build-probe --execute  # refused if no origin / gh
sdlc maintain enable demo --repo /tmp/m-demo --ack-unattended-build-probe --max-reopens 1  # refused: cap flags need --execute
```

## 5. Live execution run — owner's word only (residual, B-FR-022)

This needs a scratch GitHub repo with `gh` authenticated and an `origin` remote, the z.ai subscription, and a running worker.

1. Enable with `--ack-unattended-build-probe --execute`.
2. Seed a mechanical fault, such as a committed `.env`, then nudge twice so it reproduces. Policy approval follows.
3. Check that one child starts, parks at merge, and that the incident reads `verified`. Approve the child's merge in `sdlc inbox`, merge the PR, and nudge. The incident reads `closed`.

This run is **not** part of 023b's acceptance. It is recorded as a residual in `verification.md`.
