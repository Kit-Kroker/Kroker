# Design — Analyst stage (stage 9) + traceability & coverage advisory checks

| | |
|---|---|
| Status | Approved design |
| Date | 2026-07-16 |
| Related | `PRD.md` FR-106, `ARCHITECTURE.md` §3/§4/§10, `ROADMAP.md` §1 stage 9 / §8 item 2 |
| Scope | One increment: the `analyze` stage (proposer) + its two advisory merge-gate checks |

---

## 1. Goal

Build **stage 9 (`analyze`)** of the 14-stage DAG and wire the two advisory
quality-gate checks it unlocks (FR-106):

- **traceability** — every acceptance criterion in the run traces to ≥ 1 test.
  The Analyst *proposes* the criterion→test mapping; the gate *enforces*
  completeness. Fully built this increment.
- **coverage** — diff-scoped coverage ≥ a configurable threshold. Wired as a
  **minimal-but-real deterministic seam**, mirroring how `security_scan` is a
  minimal ruleset today. Real per-stack instrumentation is future work behind
  the seam.

Non-goals this increment: a third "analysis severity" blocking check; real
cross-stack coverage instrumentation; repo-wide (non-diff-scoped) coverage.

## 2. Where it sits

The Analyst is a **clean-context proposer** — the same construct as the
Reviewer and QA analyst (ADR-6/ADR-12): a Pydantic-AI `Agent` wrapped in
`TemporalAgent`, holding no tools, no repo, no worker session. It never sees an
implementer's narrative.

It runs **once per run**, after the per-task loop completes and immediately
before the merge-gate evidence collection (`src/sdlc/workflows/feature.py`,
the block starting at the `# 5. MERGE` comment, currently ~line 787). The
analyze stage produces an `AnalysisReport`; the two new checks are appended to
the `checks` list built for `evaluate_gate`.

Orchestrator-assembled inputs (clean-context — references and scoped extracts,
never a raw transcript):

- **Authoritative acceptance-criteria list**: `(task_id, criterion)` pairs
  enumerated from `plan.tasks[].acceptance_criteria`. This is the source of
  truth for "what must be traced" — not the Analyst's own recollection.
- **Integration diff**: the materialized diff of the run's work. Reuses the
  existing `get_task_diff` activity against the run's base (`base...HEAD` of the
  integration worktree). The diff includes the test files, so the Analyst can
  name the tests it maps criteria to.
- **Aggregate test output**: the per-task `TaskResult.qa` reports already
  collected in `done` (failing-test names, issues). No new test run is
  introduced for the Analyst.

## 3. The `AnalysisReport` model (`src/sdlc/models.py`)

```python
class CriterionTrace(BaseModel):
    task_id: str
    criterion: str
    tests: list[str] = Field(default_factory=list)   # test ids/names that verify it


class AnalysisReport(BaseModel):
    """Clean-context Analyst output (stage 9). Emitted from
    orchestrator-assembled inputs only — the authoritative acceptance-criteria
    list + materialized integration diff + aggregate test output. The Analyst
    holds no tools, no repo, no worker session.

    The Analyst PROPOSES the criterion->test mapping; the DeterministicQualityGate
    ENFORCES completeness (FR-106). This model never carries a pass/fail verdict.
    """
    traceability: list[CriterionTrace] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)   # integration-level
                                                                  # concerns; carried
                                                                  # for memory/observability,
                                                                  # NOT a blocking check
    summary: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
```

Kept small per the claim-check discipline (2 MB history limit). `findings`
reuses the existing `ReviewFinding` type and rides along for the
retain-to-memory signal only — it is **not** wired as a gate check this
increment.

`CoverageReport` (deterministic evidence, produced by an activity, not the LLM):

```python
class CoverageReport(BaseModel):
    """Diff-scoped coverage evidence for the advisory `coverage` gate check.
    `measured=False` means no coverage artifact was emitted by the run's test
    commands — the seam could not measure, so the check passes rather than
    forcing a spurious human override every run."""
    measured: bool
    diff_pct: float | None = None       # 0..100 over changed files
    detail: str = ""
```

## 4. Enforcement — the "gate enforces" half

The **workflow**, not the LLM, derives the traceability verdict. A pure helper
(unit-tested) computes the untraced set:

```python
def untraced_criteria(
    authoritative: list[tuple[str, str]],      # (task_id, criterion) from plan
    report: AnalysisReport,
) -> list[str]:
    """Criteria that the Analyst's mapping either OMITS or maps to zero tests.
    Enforced against the authoritative plan set, so an Analyst cannot hide a
    gap by forgetting to list a criterion."""
```

Match on `(task_id, criterion)`. A criterion is traced iff the report contains a
`CriterionTrace` for that exact pair with a non-empty `tests` list.

Two advisory checks are appended to the existing `checks` list (the
`build_check(...)` sequence in `feature.py`, currently ~line 811):

```python
untraced = untraced_criteria(authoritative, analysis)
checks.append(build_check(
    "traceability", not untraced, CheckClass.ADVISORY,
    detail=(f"{len(untraced)} criterion(s) without a test: {untraced[:10]}"
            if untraced else "every acceptance criterion traces to >=1 test")))

cov = await workflow.execute_activity(measure_coverage, CoverageInput(...), **ACT)
if not cov.measured:
    cov_pass, cov_detail = True, "coverage not measured (seam)"
else:
    cov_pass = cov.diff_pct >= cfg.coverage_threshold
    cov_detail = f"diff coverage {cov.diff_pct:.1f}% vs threshold {cfg.coverage_threshold:.1f}%"
checks.append(build_check("coverage", cov_pass, CheckClass.ADVISORY, detail=cov_detail))
```

Both are **advisory** → they block only until an audited human override,
reusing the existing advisory-override path (the `# 5c.` block in `feature.py`).
`gate.py`'s pure `evaluate_quality_gate` already handles arbitrary advisory
checks — **no change to `gate.py`**. The absolute floor is untouched.

`cfg.coverage_threshold: float` is a new `PipelineConfig` field, default `0.0`
(effectively off until a project opts in), range 0–100.

## 5. Coverage seam (`src/sdlc/activities.py`)

New deterministic activity, structured like `security_scan` (pure filesystem
read, reproducible across Temporal retries):

```python
@dataclass
class CoverageInput:
    worktree: str
    changed_files: list[str]     # from the integration diff (get_task_diff .files)

@activity.defn
async def measure_coverage(inp: CoverageInput) -> CoverageReport:
    """Look for a Cobertura coverage.xml already emitted into the worktree by
    the run's test commands; scope it to changed_files; compute a diff-scoped
    percentage. No artifact -> measured=False. This is a minimal seam: real
    per-stack instrumentation replaces only this activity body."""
```

- Searches the worktree for `coverage.xml` (Cobertura — the most common
  cross-tool format: pytest-cov, coverage.py, jest `--coverage`, gocover-cobertura).
- Parses line-rate per file, restricts to `changed_files`, returns the
  aggregate diff-scoped percentage.
- Missing/unparseable → `CoverageReport(measured=False, detail=...)`.

The seam is honest: today most runs will report `measured=False` and the
`coverage` check passes as a no-op, exactly as the roadmap notes ("wired-but-minimal").

## 6. Agent + wiring (`src/sdlc/agents/roles.py`, `config/agents.yaml`)

- `ANALYST_PROMPT`: clean-context instructions — "You receive ONLY the
  acceptance-criteria list, the materialized diff, and the test output. For each
  criterion, list the test(s) that verify it; leave `tests` empty if none does.
  Never request the implementer's narrative. Report integration-level concerns
  as `findings`. Set a calibrated confidence."
- `analyst_agent = Agent(MODEL, name="analyst_agent", output_type=AnalysisReport, ...)`.
- `t_analyst = TemporalAgent(analyst_agent, ...)`; add to `ALL_TEMPORAL_AGENTS`.
- `PROMPT_SHAS["analyze"] = sha256(ANALYST_PROMPT)`.
- `config/agents.yaml`: register `analyst` as `kind: proposer` (FR-201).

The Analyst uses the base `MODEL` (a strategic/adversarial reasoning role); it
is **not** subject to the reviewer's model-family-inequality rule (that rule is
specifically the developer↔reviewer anti-collusion constraint, ADR-6).

## 7. Stage record + memory

The analyze stage follows the same bookkeeping as other stages:

- Emit a `_stage_record(stage="analyze", role="analyst", ...)` with a
  quality/outcome derived from whether traceability is complete.
- Retain a `STAGE_SUMMARY` to the project bank. When `untraced` is non-empty,
  additionally retain a `GOTCHA` naming the untraced criteria — the same
  fix-loop-learning shape used elsewhere (FR-401).

## 8. Testing

- **Unit — `untraced_criteria`**: authoritative set with a criterion the report
  omits → that criterion is untraced; a criterion mapped to `tests=[]` →
  untraced; a full mapping → empty. Confirms "propose vs enforce".
- **Unit — `measure_coverage`**: no `coverage.xml` → `measured=False`; a fixture
  Cobertura file with changed-file line-rates → correct diff-scoped pct;
  threshold comparison (below → advisory-block, at/above → pass).
- **Workflow/e2e — extend `tests/test_e2e_greenfield.py`**: the analyze stage
  runs; the gate report contains both `traceability` and `coverage` checks;
  with a complete mapping and `coverage_threshold=0.0` the run still ships
  end-to-end (advisory checks pass, no spurious human gate).
- **Fakes** (`tests/fakes/`): add an `AnalysisReport` `TestModel` stub for
  `analyst_agent` so the deterministic CI e2e produces a full mapping.

## 9. Roadmap updates (`ROADMAP.md`)

On completion, flip:

- §1 stage **9 · analyze** → `[x]` (Analyst + `AnalysisReport` + traceability
  produced/enforced).
- §2 **FR-106** → coverage/traceability checks built; note coverage is a
  deterministic seam (real instrumentation future work).
- §1 stage **11 · quality_gate** → coverage + traceability checks now built
  (remove the "still unbuilt" note; keep the seam caveat on coverage).
- §8 item **2 (Analyst stage)** → done, with a pointer to this spec + its plan.

## 10. Files touched

| File | Change |
|---|---|
| `src/sdlc/models.py` | `CriterionTrace`, `AnalysisReport`, `CoverageReport` |
| `src/sdlc/agents/roles.py` | `ANALYST_PROMPT`, `analyst_agent`, `t_analyst`, `PROMPT_SHAS`, `ALL_TEMPORAL_AGENTS` |
| `src/sdlc/activities.py` | `CoverageInput`, `measure_coverage` |
| `src/sdlc/workflows/feature.py` | `untraced_criteria` helper, analyze stage call, 2 advisory `build_check`s, stage record + retain |
| `src/sdlc/models.py` (`PipelineConfig`) | `coverage_threshold: float = 0.0` |
| `config/agents.yaml` | register `analyst` proposer |
| `src/sdlc/worker.py` | register `measure_coverage` activity + `t_analyst` (if the worker enumerates agents/activities explicitly) |
| `tests/` | unit + e2e + fake stub |
| `ROADMAP.md` | flip stage 9 / FR-106 / gate / §8-item-2 |

## 11. Invariants preserved

- **Clean-context validators** (ADR-12): the Analyst sees only assembled
  artifacts, never a worker session.
- **Propose vs enforce** (FR-106): the LLM proposes the mapping; the workflow
  computes the verdict against the authoritative plan set.
- **Absolute floor untouched** (SC-5): both new checks are advisory; the
  security/lint/build absolute checks and their no-override rule are unchanged.
- **Deterministic gate** (`gate.py`): unchanged — it already accepts arbitrary
  advisory checks.
