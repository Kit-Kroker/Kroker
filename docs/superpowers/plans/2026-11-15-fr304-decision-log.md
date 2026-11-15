# FR-304 Decision Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every gate decision carry its full FR-304 field set (outcome, decider, gate+round, comments, reviewer, timestamp) into the durable per-run record, and make that record queryable via `sdlc decisions`.

**Architecture:** Enrich the existing record spine in place — `GateDecision` (already complete) → `GATE_DECIDED` event → `GateOutcomeSummary` → `summary.json`/`report.html` — and add a read-side module over the retro exports, mirroring `calibration/store.py::gate_decisions_from_exports`. No new activity, no new workflow command, no second store.

**Tech Stack:** Python 3.13, Pydantic v2, temporalio (no new usage), pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-fr304-decision-log-design.md`

## Global Constraints

- **No new workflow commands** anywhere: no new activity, no timer, no signal/query added. A red `tests/replay/test_graph_replay.py` after a src change means the change altered the command sequence — fix the change (SG-2).
- **New model fields are `None`-defaulted** so pre-change payloads deserialize unchanged (E-1 / 021 precedent).
- **Never hand-edit replay fixtures.** Goldens/histories are written only by the capture tests behind `SDLC_CAPTURE_HISTORIES=1` (`tests/replay/AGENTS.md` rule 1). If replay goes red for a payload (not command) reason, re-baseline only via the capture tests and attach the projection diff (`scripts/check_golden_rebaseline.py` gates it).
- **Determinism-lint budget:** `tests/graph_workflow/test_determinism_lint.py` allows exactly 1 `workflow.` call class in `run_host.py`. Do not add `workflow.now()`/`workflow.info()` to `run_host.py` — the timestamp stamp belongs in `GateHost._gate` (`gates.py`), which already calls `workflow.now()`.
- `ruff check .`, `ruff format .`, `mypy` clean; every touched file stays under 1000 physical lines (`scripts/check_file_size.py`).
- Event data values are strings (`ReportHost._emit(kind, stage=None, **data: str)`); new keys follow the established only-when-set emit pattern.

## Review Focus

1. **Old on-disk `summary.json` without the new keys must parse** (a pre-change export read by the new code) — pinned in Task 1 (model compat) and Task 6 (reader over an old-style export).
2. **A malformed/truncated `summary.json` must not hide other runs' decisions** — one bad run is skipped, the sweep continues — pinned in Task 6.
3. **Duplicate `(gate, round)` emits must merge, not clobber** — merge's overrides re-emit after RunHost's full emit must yield one row with both sets of fields; later always-present values win, absent optionals keep the earlier value — pinned in Task 4.
4. **`decided_at` on policy/timeout decisions must be the decision time, not `None`** (human decisions keep their signal-time stamp) — pinned in Task 2's wiring test and Task 4's summary test.
5. **Friendly empty states, exit 0** — missing export root and no matching decisions render one explanatory line, never a traceback or non-zero exit — pinned in Tasks 6 and 7.

---

### Task 1: `GateOutcomeSummary` gains the full FR-304 field set

**Files:**
- Modify: `src/sdlc/core/models.py:521-535` (`GateOutcomeSummary`)
- Test: `tests/test_run_summary_model.py`

**Interfaces:**
- Consumes: `GateOutcome` (StrEnum, `core/models.py:42`: `approve|reject|revise`).
- Produces: `GateOutcomeSummary.outcome: GateOutcome | None = None`, `.comments: str | None = None`, `.reviewer: str | None = None`, `.decided_at: datetime | None = None` — Tasks 4, 5, 6 read these.

- [ ] **Step 1: Write the failing tests** in `tests/test_run_summary_model.py`

```python
def test_gate_outcome_summary_new_fields_default_none():
    g = GateOutcomeSummary(gate="merge", round=1, policy="soft", decided_by="human", approved=True)
    assert g.outcome is None and g.comments is None and g.reviewer is None and g.decided_at is None


def test_gate_outcome_summary_parses_pre_change_json():
    """A summary.json written before this change has no new keys."""
    g = GateOutcomeSummary.model_validate(
        {"gate": "merge", "round": 1, "policy": "soft", "decided_by": "human", "approved": True}
    )
    assert g.outcome is None


def test_gate_outcome_summary_round_trips_full_fields():
    g = GateOutcomeSummary(
        gate="merge", round=2, policy="hard", decided_by="human", approved=False,
        outcome=GateOutcome.REVISE, comments="narrow the scope", reviewer="maksim",
        decided_at=datetime(2026, 11, 15, 10, 0, tzinfo=UTC),
    )
    assert GateOutcomeSummary.model_validate_json(g.model_dump_json()) == g
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_run_summary_model.py -q`
Expected: FAIL — `GateOutcomeSummary() got an unexpected keyword argument 'outcome'` (or `AttributeError`).

- [ ] **Step 3: Add the four fields** to `GateOutcomeSummary` in `src/sdlc/core/models.py`, after `approved` and before `confidence`. Update the class docstring one line: the None fields mean "pre-FR-304 record" (`approved` distinguishes nothing between reject and revise on those).

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_run_summary_model.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/core/models.py tests/test_run_summary_model.py
git commit -m "feat(core): GateOutcomeSummary carries the FR-304 field set (outcome/comments/reviewer/decided_at)"
```

### Task 2: Stamp `decided_at` at the `_gate` choke point

**Files:**
- Modify: `src/sdlc/workflows/gates.py:272` (in `GateHost._gate`, immediately before the `await self._on_gate_decided(...)` call)
- Test: `tests/test_gate_host.py`

**Interfaces:**
- Consumes: `GateDecision.decided_at` (`core/models.py:166`); `workflow.now()` (already imported/used in `gates.py`).
- Produces: every `GateDecision` returned by `GateHost._gate` — and handed to `_on_gate_decided` — has `decided_at` set. Task 3's emit and the live `run_state()` `decisions` list rely on this.

- [ ] **Step 1: Write the failing test** in `tests/test_gate_host.py`, following that file's established source-inspection style (see `test_soft_gate_auto_approval.py::test_revisable_stage_passes_auto_decision` for the pattern):

```python
def test_gate_stamps_decided_at_before_hook():
    """FR-304: policy/timeout/SOFT-auto decisions get decided_at where they
    are created; a human decision's signal-time stamp (submit_gate_decision)
    must not be overwritten. `_gate` is the one choke point all four paths
    pass, so the stamp lives there, guarded to preserve an existing stamp."""
    src = GATES_SRC.read_text(encoding="utf-8")  # pathlib.Path to src/sdlc/workflows/gates.py
    stamp = "decision.decided_at = decision.decided_at or workflow.now()"
    hook = "await self._on_gate_decided("
    assert stamp in src
    assert src.index(stamp) < src.index(hook)
```

(Define `GATES_SRC = pathlib.Path("src/sdlc/workflows/gates.py")` at module top beside existing helpers.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_gate_host.py::test_gate_stamps_decided_at_before_hook -q`
Expected: FAIL — `stamp` not in source.

- [ ] **Step 3: Add the stamp** in `GateHost._gate` immediately before the `_on_gate_decided` call, with a one-line comment citing FR-304 and that the human path was already stamped at signal time. No other change to `gates.py`.

- [ ] **Step 4: Run to verify it passes, plus the file's existing tests**

Run: `pytest tests/test_gate_host.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/gates.py tests/test_gate_host.py
git commit -m "feat(gates): stamp decided_at on every decision path (FR-304)"
```

### Task 3: `RunHost._on_gate_decided` emits the full field set

**Files:**
- Modify: `src/sdlc/workflows/run_host.py:53-84`
- Test: `tests/test_run_host.py`

**Interfaces:**
- Consumes: Task 2's guaranteed `decided_at`; `GateDecision` fields.
- Produces: `GATE_DECIDED` event data keys `outcome` (always), `reviewer`, `comments`, `decided_at` (ISO string, only-when-set) — Task 4 parses exactly these keys.

- [ ] **Step 1: Write the failing test** in `tests/test_run_host.py`. Bare-instance style works: with `self._cfg = None` the method never reaches `_retain`/`workflow.info()`, so no Temporal env is needed.

```python
@pytest.mark.asyncio
async def test_on_gate_decided_emits_full_field_set():
    host = RunHost()
    host._cfg = None
    emitted: list[tuple[object, dict]] = []
    host._emit = lambda kind, stage=None, **data: emitted.append((kind, data))  # type: ignore[method-assign]
    decision = GateDecision(
        gate="merge", round=1, outcome=GateOutcome.REJECT, decided_by="human",
        reviewer="maksim", comments="not ready", decided_at=datetime(2026, 11, 15, 9, 0, tzinfo=UTC),
    )
    await host._on_gate_decided("merge", 1, GatePolicy.HARD, decision)
    (kind, data), = emitted
    assert data["outcome"] == "reject"
    assert data["reviewer"] == "maksim"
    assert data["comments"] == "not ready"
    assert data["decided_at"] == "2026-11-15T09:00:00+00:00"
```

Add a second test asserting the only-when-set half: a hand-built `GateDecision` with `reviewer=None, comments=None` (e.g. a SOFT auto-approve; note the timeout path *does* carry a comments string) — `decided_at` is always set by Task 2, so assert it is present while `"comments" not in data` and `"reviewer" not in data`.

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_run_host.py -q`
Expected: FAIL — `KeyError: 'outcome'`.

- [ ] **Step 3: Extend the emit** in `RunHost._on_gate_decided`: add `outcome=decision.outcome.value` to the always-emitted kwargs, and only-when-set kwargs after the existing `author_model` line, mirroring its `**({...} if x else {})` pattern: `reviewer` (truthy), `comments` (truthy), `decided_at` (`decision.decided_at.isoformat()` when set). One comment line: FR-304 full-field record; these keys are read by `_gate_outcome`.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_run_host.py tests/test_memory_wiring.py -q`
Expected: PASS (`test_memory_wiring.py` source-inspects this method — confirm unbroken).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/run_host.py tests/test_run_host.py
git commit -m "feat(run-host): GATE_DECIDED carries outcome/reviewer/comments/decided_at (FR-304)"
```

### Task 4: `_gate_outcome` reads the fields; `(gate, round)` dedup becomes field-wise enrich

**Files:**
- Modify: `src/sdlc/observability/summary.py:38-51` (`_gate_outcome`), `:93-101` (dedup loop)
- Test: `tests/test_run_summary_build.py`

**Interfaces:**
- Consumes: Task 1's fields; Task 3's event keys.
- Produces: `RunSummary.gates` rows with full fields; merge semantics — on a repeated `(gate, round)` key, always-present fields (`policy`, `decided_by`, `approved`, `round`, `gate`) take the later event's value; optional fields (`outcome`, `comments`, `reviewer`, `decided_at`, `confidence`, `author_model`) keep the earlier value when the later event omits them; `overrides` takes the later value when non-empty, else keeps the earlier. Tasks 5 and 6 consume the rows.

- [ ] **Step 1: Write the failing tests** in `tests/test_run_summary_build.py` using the file's `_ev` helper:

```python
def test_gate_decided_full_fields_reach_summary():
    trace = [
        _ev(0, RunEventKind.GATE_DECIDED, gate="merge", round=1, policy="hard",
            decided_by="human", approved="false", outcome="reject", reviewer="maksim",
            comments="not ready", decided_at="2026-11-15T09:00:00+00:00"),
        _ev(1, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(run_id="r", mode="greenfield", outcome="rejected", trace=trace, memory_enabled=False)
    g = s.gates[0]
    assert g.outcome is GateOutcome.REJECT and g.reviewer == "maksim"
    assert g.comments == "not ready" and g.decided_at == datetime(2026, 11, 15, 9, 0, tzinfo=UTC)


def test_gate_dedup_enriches_instead_of_replacing():
    """The merge-gate shape: RunHost's full emit, then merge's overrides-only
    re-emit. Field-wise merge, not last-wins replace."""
    trace = [
        _ev(0, RunEventKind.GATE_DECIDED, gate="merge", round=1, policy="soft",
            decided_by="human", approved="true", outcome="approve", reviewer="maksim",
            comments="accepted risk", decided_at="2026-11-15T09:00:00+00:00"),
        _ev(1, RunEventKind.GATE_DECIDED, gate="merge", round=1, policy="soft",
            decided_by="maksim", approved="true", overrides="coverage,lint"),
        _ev(2, RunEventKind.RUN_FINISHED),
    ]
    s = build_run_summary(run_id="r", mode="greenfield", outcome="deployed", trace=trace, memory_enabled=False)
    g = s.gates[0]
    assert g.outcome is GateOutcome.APPROVE and g.comments == "accepted risk"  # kept
    assert g.decided_by == "maksim" and g.overrides == ["coverage", "lint"]      # later wins
```

Also: `test_pre_change_events_parse_to_none_fields` — a `GATE_DECIDED` event with none of the new keys (the existing `test_clean_deploy_aggregates_stages_and_gate` shape) yields `g.outcome is None and g.comments is None`.

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_run_summary_build.py -q`
Expected: FAIL — `_gate_outcome` drops the fields / dedup replaces.

- [ ] **Step 3: Implement.** In `_gate_outcome`: parse `outcome` (`GateOutcome(d["outcome"])` when present else `None`), `reviewer`/`comments` (`d.get(...) or None`), `decided_at` (`datetime.fromisoformat` when present). Replace the dict-assign dedup with a pure `_enrich(prev, new) -> GateOutcomeSummary` helper implementing the Interfaces semantics (a `model_copy(update=...)` over the later record with prev's values substituted for absent optionals is the compact shape). Keep the loop's comment, updated to describe enrich and the merge re-emit it exists for.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_run_summary_build.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/summary.py tests/test_run_summary_build.py
git commit -m "feat(observability): summary reads full decision fields; (gate,round) dedup enriches (FR-304)"
```

### Task 5: `report.html` gates table shows the full record

**Files:**
- Modify: `src/sdlc/observability/export.py:40-53` (`gate_rows`), `:86-88` (table header)
- Test: `tests/test_observability_export.py`

**Interfaces:**
- Consumes: Task 1's fields on `s.gates` rows.
- Produces: none (terminal rendering).

- [ ] **Step 1: Write the failing test** in `tests/test_observability_export.py`, extending the existing `render_report_html` test's `_summary()` fixture to give one gate the full fields, asserting the rendered cells: `reject`, the reviewer, `2026-11-15 09:00` (render `decided_at` via `dt.strftime("%Y-%m-%d %H:%M")`, `-` when None), and the escaped comment text appear in the html; `revise` on another row renders distinctly from `reject`.

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_observability_export.py -q`
Expected: FAIL — new cells absent.

- [ ] **Step 3: Implement** — header becomes `gate, round, policy, decided_by, reviewer, outcome, confidence, overrides, decided_at, comments`; per-row: `-` for `None` outcome/reviewer/decided_at/comments (pre-change summaries), `escape()` on reviewer and comments, comments truncated to 80 chars with an ellipsis marker in a helper `_cell(s, width=80)` (comments can be long; the plan fixes the width at 80).

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_observability_export.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/export.py tests/test_observability_export.py
git commit -m "feat(observability): report.html gates table shows the full FR-304 record"
```

### Task 6: `observability/decisions.py` — the read surface

**Files:**
- Create: `src/sdlc/observability/decisions.py`
- Test: `tests/test_decisions_log.py`

**Interfaces:**
- Consumes: `RunSummary` (with Task 1 fields) from `<root>/<run_id>/summary.json`.
- Produces (Task 7 consumes):
  - `class DecisionLogRow(BaseModel)`: `run_id: str`, `title: str = ""`, `project_key: str | None = None`, `gate: str`, `round: int`, `policy: str`, `outcome: GateOutcome | None = None`, `decided_by: str`, `reviewer: str | None = None`, `comments: str | None = None`, `decided_at: datetime | None = None`, `confidence: float | None = None`, `overrides: list[str] = Field(default_factory=list)`.
  - `def decisions_from_exports(root: str | os.PathLike | None = None, *, run: str | None = None, gate: str | None = None, decided_by: str | None = None, limit: int | None = None) -> list[DecisionLogRow]`
  - `def render_decisions(rows: Sequence[DecisionLogRow]) -> str`

- [ ] **Step 1: Write the failing tests** in `tests/test_decisions_log.py` (tmp_path fixtures writing `<run>/summary.json`):

```python
def test_reads_full_rows_across_runs(tmp_path): ...        # two runs, one gate each; rows carry run_id/title + full fields
def test_filters_run_gate_decided_by(tmp_path): ...         # each filter alone narrows; combined narrows conjunctively
def test_limit_keeps_most_recent_tail(tmp_path): ...        # 3 decisions, limit=2 -> the LAST two rows of the ascending order
def test_limit_zero_is_empty(tmp_path): ...                 # limit=0 -> [], not everything
def test_missing_root_is_empty_not_error(tmp_path): ...     # decisions_from_exports(tmp_path / "nope") == []
def test_malformed_summary_is_skipped(tmp_path): ...        # run A truncated json, run B valid -> only B's rows
def test_old_style_summary_yields_rows_with_none_fields(tmp_path):  # pre-change gates dict (no new keys) -> outcome None rows
def test_render_is_deterministic_table_with_empty_state(): ...  # empty rows -> one friendly line naming the export root contract;
                                                              # non-empty -> header + one line per row, stable across calls
```

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_decisions_log.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.observability.decisions'`.

- [ ] **Step 3: Implement `src/sdlc/observability/decisions.py`** — module docstring cites FR-304 and the contract: coverage is runs that closed and exported (verbatim discipline from `calibration/store.py::gate_decisions_from_exports`); root defaults to `SDLC_EXPORT_ROOT` or `./runs/pipeline`; sorted glob `*/summary.json`; `OSError`/`ValidationError` on one summary skips that run only; rows ascending by run directory then summary order; `limit` returns the tail (most recent). `render_decisions` in the `_render_gates_list`/`render_calibration` style: recomputed column widths, `|`-separated, `-` for `None` cells, comments truncated at 40 chars; empty input returns exactly `"no decisions recorded (runs that closed and exported under the export root)"`.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_decisions_log.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/observability/decisions.py tests/test_decisions_log.py
git commit -m "feat(observability): decisions_from_exports read surface over summary.json (FR-304)"
```

### Task 7: `sdlc decisions` CLI verb

**Files:**
- Modify: `src/sdlc/cli.py` (parser beside `calibration` ~line 395, `local_only` set ~line 121-131, handler beside the `calibration` handler ~line 499)
- Test: `tests/test_decisions_cli.py`

**Interfaces:**
- Consumes: Task 6's `decisions_from_exports` / `render_decisions`.
- Produces: the `decisions` verb: flags `--run`, `--gate`, `--decided-by`, `--limit` (int), `--exports` (root path; named `--exports` to match `sdlc calibration --exports`, superseding the spec's `--root` spelling — same parameter). Local-only: never connects to Temporal, exit 0 always (read surface).

- [ ] **Step 1: Write the failing tests** in `tests/test_decisions_cli.py`, mirroring `tests/test_gates_list_cli.py`'s argv/monkeypatch style: (a) `decisions --exports <tmp>` over two fixture runs renders a table containing a known `gate`/`decided_by` pair; (b) `decisions --exports <tmp> --decided-by human` filters; (c) `decisions --exports <missing>` prints the friendly empty line and exits 0; (d) `_needs_temporal(args)` is `False` for `decisions` (the `local_only` wiring).

- [ ] **Step 2: Run to verify they fail**

Run: `pytest tests/test_decisions_cli.py -q`
Expected: FAIL — argparse rejects the subcommand.

- [ ] **Step 3: Implement** — `sub.add_parser("decisions")` with the five flags; add `or args.cmd == "decisions"` to `local_only`; handler prints `render_decisions(decisions_from_exports(args.exports, run=args.run, gate=args.gate, decided_by=args.decided_by, limit=args.limit))`.

- [ ] **Step 4: Run to verify they pass**

Run: `pytest tests/test_decisions_cli.py tests/test_gates_list_cli.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/cli.py tests/test_decisions_cli.py
git commit -m "feat(cli): sdlc decisions -- the FR-304 queryable decision log"
```

### Task 8: Replay verdict, full gates, close-out

**Files:**
- Modify: `ROADMAP.md:331` (FR-304), `ROADMAP.md:464` (NFR-4 note), `docs/roadmap/last-verified-log.md` (prepend entry)
- Test: none new (this task runs the existing suites)

**Interfaces:**
- Consumes: everything above.
- Produces: the roadmap close-out; the replay verdict recorded.

- [ ] **Step 1: Run the replay corpus**

Run: `pytest tests/replay/ -q`
Expected: PASS. The goldens project only `commands`/`close`/fixed-column trace rows, and no command was added, so no golden may change. If `test_graph_replay.py` is red with a payload (not command) non-determinism: re-baseline ONLY via `SDLC_CAPTURE_HISTORIES=1 pytest tests/replay/test_capture_graph.py`, verify `git diff tests/replay/golden/` is empty (provenance fields excepted — `scripts/check_golden_rebaseline.py` gates this), and record the verdict in the close-out entry. Never hand-edit a fixture.

- [ ] **Step 2: Run the full fast tier plus lint/type/size gates**

Run: `pytest -q && ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py`
Expected: all green.

- [ ] **Step 3: Close out the roadmap.** ROADMAP.md:331 becomes `[x]` with a one-sentence evidence entry (fields on `GateOutcomeSummary` from `GateHost._gate`/`RunHost._on_gate_decided`, enrich-dedup in `build_run_summary`, `sdlc decisions` over the retro exports; spec `2026-11-15-fr304-decision-log-design.md`). NFR-4's entry (line 464) drops its "decisions are not a structured, queryable log (FR-304)" clause, keeping the FR-702 clause and its ⚠️. Prepend the full close-out entry to `docs/roadmap/last-verified-log.md` (the ROADMAP cell keeps only the one-sentence latest).

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/roadmap/last-verified-log.md
git commit -m "docs(roadmap): close FR-304 — full-field decision records, queryable per run"
```
