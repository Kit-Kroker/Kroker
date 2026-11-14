# Quickstart — validating round 023a

Prerequisites:
- `uv sync --frozen --extra dev`, and `.venv/bin` on PATH.
- For the `temporal` tier: the Temporal dev-server the test fixtures spawn.
- For step 5 only: a running worker, a local Temporal server and a z.ai key. That step is paid, and runs on the owner's word.

## 1. Pure-domain tier (fast, no Temporal)

```bash
pytest -q tests/maintenance/ -m "not temporal"
```

Expected outcomes, against data-model.md / research.md:
- `step()` on a first triage records the baseline and opens 0 incidents (SC-001).
- New / persisted / resolved / unverifiable each map to the transitions in data-model §IncidentState. Not-collected twice gives a `detect_escalation`. A signal that is off by configuration (`advisory_source=none`, `build_probe=False`) reads *not configured*: its streak never increments and it never escalates. A signal-version change re-baselines that signal.
- `confidence_floor` matches the R8 table for each fix class.
- `repair_gate_settings` always yields SOFT + `on_timeout=REJECT`. `MaintenanceConfig` rejects `gates=…`, `threshold<0.5`, and `build_probe=True` without the acknowledgement (SC-003).
- Schedules: the nightly-reflect asset produces a `to_temporal` result byte-identical to before. A kick asset round-trips through `from_temporal`. A sub-hourly cron is refused.

## 2. Workflow tier

```bash
pytest -q -m temporal tests/maintenance/
```

The fixture git repo comes from `tests/maintenance/conftest.py`, and the `maintainer` is the `TestModel` fake.

Expected outcomes:
- **Cycle sequence.** Cycle 1 records the baseline. A build-breaking commit then gives cycle 2 one incident and one `repair:1` pending item. The repo's refs and worktrees are unchanged (SC-002).
- **Timeout.** A time-skipped timeout gives `timed_out`, never `approved_not_executed` (SC-003).
- **Policy approval.** A mechanical, reproduced finding above threshold gives `approved_not_executed` with `decided_by="policy"`.
- **Coalescing.** Three nudges during a cycle produce exactly one follow-up cycle (SC-004).
- **History roll-over.** `max_cycles_per_history=2` forces `continue_as_new`. Incidents and baseline survive equal (SC-005).
- **Disable.** Open gates become `withdrawn`, and the workflow returns `disabled:<project>`.
- **Replay.** Each test's history replays clean through `Replayer` (R13).

## 3. Regression battery (SC-006)

```bash
ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py
pytest -q                                      # fast tier
pytest -q tests/replay/                        # existing goldens unchanged
pytest -q -m temporal tests/test_tidyup*.py tests/test_triage_workflow_e2e.py
```

- The fast tier must fail **only** on the recorded baseline ids: `.specify/specs/021-recall-snapshot-artifact/baseline-failures.txt`, cross-checked against `.specify/specs/022-mcp-channel-adapter/baseline-failures.txt`. Diff the sorted FAILED lists; they must be identical.
- No file under `tests/replay/histories/` or `tests/replay/golden/` changes (`git status --short tests/replay/` is empty).

## 4. CLI smoke (local Temporal, no model spend)

```bash
sdlc maintain enable demo --repo /tmp/m-demo --no-build-probe
sdlc maintain nudge demo
sdlc maintain incidents demo --state
sdlc schedules apply --dry-run      # shows the kick asset if schedules/maint-demo.yaml exists
sdlc inbox                          # lists repair:<n> items for maint-demo
sdlc maintain disable demo
```

This uses the fake maintainer: run the worker with the test registry, or `--no-build-probe` plus a seeded secret fault so no plan is needed for the inbox line.

## 5. Live cycle (SC-007), owner's word only, z.ai subscription

1. Create a scratch git repo with a passing build. Enable maintenance with `--ack-unattended-build-probe` and nudge it. Check that the baseline is recorded.
2. Commit a build break, then nudge again.
3. Check with `sdlc maintain incidents scratch` that there is one incident, a plan rendered with its floor and effective confidence, and a pending `repair:1`.
4. Reject it, or let it time out. Verify the scratch repo is untouched.
