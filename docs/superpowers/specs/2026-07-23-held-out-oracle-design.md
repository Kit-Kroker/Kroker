# E-31 — Tier-A held-out oracle (benchmark grade)

| | |
|---|---|
| Date | 2026-07-23 |
| Roadmap item | E-31 (§9.8); extends E-27; depends on E-30 |
| Anchors | **SC-1** (unattended-reach grade), **FR-106** (criterion→test discipline), FR-108/ADR-15 (adapter), FR-704/NFR-4 (records); **(new scope)** — held-out oracle is new measurement scope |
| Status | Approved design — pre-plan |

## 1. Why

The benchmark grades **rubric-only** today. `judge_artifact` (`benchmarks/judge.py`)
LLM-scores proposer artifacts (`clarifier` / `architect` / …) against the case's
`rubric-*.md`. Nothing runs the **produced code** and grades it objectively, so —
in BENCHMARK.md's framing — "every benchmark number rests on rubric-only judging."

E-30 landed the missing half: a language-agnostic `ToolchainAdapter` (`detect()` by
marker file, `test_cmd()` → Cobertura, run against the merged integration head by
`run_integration_checks`). E-31 uses that adapter to run a **held-out oracle** — a
hidden suite + fixtures that never enter the workflow's context (no worktree, no
prompt, no recall) — against the produced code, graded as **fraction passing**. That
fraction is the first **objective (Tier-A)** grade: the number SC-1's
unattended-reach rate and the E-36 heatmap are built on.

The oracle also carries E-31's anti-cheat stance (Cursor): grade **what was built,
not what was intended**, and make integrity breaches loud. Two cheap, load-bearing
checks ship here — a **held-out assertion** (the oracle never appears in the produced
diff) and a **language mismatch signal** (manifest-declared vs marker-detected). The
harder "built evenly, not to the test" overfit check is deferred to **E-31a** with
its own metric design (§7).

**Scope decisions locked in brainstorming:**
- **Seam:** a benchmark-only `grade_oracle` activity invoked by `BenchmarkWorkflow`
  **strictly after** each `FeatureWorkflow` child — the oracle is held out *by
  construction*, applied only in benchmark mode, never a pipeline stage.
- **In scope:** the fraction-passing grade + manifest `language:` adapter dispatch +
  manifest-vs-marker mismatch signal + oracle-is-held-out assertion. **Out:** the
  "built evenly" overfit metric (E-31a).
- **Grade extraction = JUnit XML** via a new `ToolchainAdapter.oracle_test_cmd`,
  mirroring E-30's Cobertura choice — one structured cross-language format, parsed
  with `defusedxml` (untrusted produced code).
- **Reference oracle = `todo-api-greenfield`** (Python): a CRUD API is black-box,
  deterministic, crisply testable.

## 2. Architecture — the seam

The oracle grade runs **after** the child that produced the code, so it can never
enter that run's context:

```
BenchmarkWorkflow.run:
  for cell in matrix:
    child = execute_child_workflow(FeatureWorkflow.run, id=<bench>/<cell>, ...)
    if case.language and <case>/oracle/ exists:
      grade = execute_activity(grade_oracle, OracleInput(
                  case_id, repo_url, run_id=child_id, language))
      # the WORKFLOW assembles the record from the cell it is iterating
      # (harness, model, bench_run_id) + the returned grade; grade_oracle
      # itself needs only what it uses to compute the grade.
      record = BenchmarkRecord(scope=ORACLE, stage="oracle", role="oracle",
                               harness=cell.harness, model=cell.model,
                               quality=<from grade>, ...)
      execute_activity(record_benchmark, record)
```

Key properties:
- **Runs on pass *and* rejection.** A rejected run still left produced code on
  `sdlc/<run_id>/integration`; its objective grade is meaningful. The child is
  wrapped in `try/except` today (`workflow.py:96`) — grading follows the same path
  regardless of the child's terminal string.
- **Produced head located deterministically.** `run_id` is the child workflow id
  `BenchmarkWorkflow` already constructs (`f"{bench_run_id}/{cell.cell_id}"`), and
  the integration branch is `sdlc/<run_id>/integration` in the case's `repo_url`
  (`activities.py:307`). No new plumbing to find produced code.
- **Determinism.** All git / subprocess / filesystem I/O lives in `grade_oracle`
  (an activity); the workflow passes only serializable args and assembles the record
  with `workflow.now()` timestamps, exactly as `FeatureWorkflow` does for stage
  records.

## 3. Components

### 3.1 `ToolchainAdapter.oracle_test_cmd(oracle_path, report_out)` — E-30 extension

Runs **only** the oracle suite and emits canonical **JUnit XML**. Parallels
`test_cmd`'s Cobertura decision: one structured format, all languages.

```python
class ToolchainAdapter(ABC):
    ...
    @abstractmethod
    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        """Run ONLY the tests under oracle_path, emitting a JUnit XML report at
        report_out. Held-out oracle grade reads tests/failures/errors from it."""

class PythonToolchain(ToolchainAdapter):
    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        # -p no:cacheprovider: never write .pytest_cache into the produced repo
        # (keeps the throwaway worktree clean; no cross-test state).
        return f"pytest {oracle_path} -q --junitxml={report_out} -p no:cacheprovider"
```

The adapter object stays **pure** (command strings only); execution is in
`grade_oracle`, identical to the `test_cmd`/`_bounded_shell` discipline.

### 3.2 `src/sdlc/benchmarks/oracle.py` — the `grade_oracle` activity

```python
@dataclass
class OracleInput:
    case_id: str
    repo_url: str
    run_id: str                 # child workflow id -> sdlc/<run_id>/integration
    language: str               # manifest-declared (CaseSpec.language)
    base_branch: str = "main"   # for the produced-diff (held-out) computation

@dataclass
class OracleGrade:
    score: float | None         # fraction passing, or None (excluded)
    passed: int
    total: int
    language_manifest: str
    language_detected: str | None
    language_match: bool
    held_out_ok: bool
    detail: str
```

Steps (each degrading to `score=None` + detail, never raising past the boundary):

1. **Check out produced head (throwaway).**
   `git worktree add <tmp> sdlc/<run_id>/integration` off `repo_url`. Branch absent
   (early rejection, never reached integration) → return `score=None`,
   `detail="no produced code (integration branch absent)"`.
2. **Mismatch signal.** `detect(<tmp>)` (marker language) → `language_detected`;
   `language_match = (language_detected == language)`.
3. **Held-out assertion.** Produced changed files =
   `git diff --name-only <base_branch>...<head>`; `held_out_ok = ` none of them live
   under any oracle relative path. (The oracle is copied *uncommitted* in step 5, so
   this asserts the *model* never authored files under the oracle path.)
4. **Copy the oracle in, uncommitted.** `benchmarks/cases/<case_id>/oracle/` →
   `<tmp>/oracle/`.
5. **Resolve adapter by manifest language.** `TOOLCHAINS[ToolchainKind(language)]`.
   No adapter → `score=None`, `detail="no toolchain adapter for <language>"`.
6. **Run + parse.** `adapter.oracle_test_cmd("oracle", "<tmp>/oracle-report.xml")`
   via `_bounded_shell`. Parse JUnit with `defusedxml`:
   `total = sum(testsuite@tests)`, `failures + errors` summed likewise,
   `passed = total - failures - errors`, `score = passed / total` (total 0 →
   `score=None`, `detail="oracle produced no tests"`). Malformed/absent report →
   `score=None`.
7. **Clean up.** `git worktree remove --force <tmp>` (best-effort in a `finally`).

`grade_oracle` mirrors `judge_artifact`: it catches at the boundary and returns
`score=None` on any unexpected exception, so a broken grader can never fail a cell.

### 3.3 Model additions

- `BenchmarkScope.ORACLE = "oracle"`.
- `QualityScore.judge` literal gains `"oracle"`.
- `CaseSpec.language: str | None = None` — declares the oracle language; also the
  value the mismatch signal compares against. Oracle grading is gated on
  `language` being set **and** a `benchmarks/cases/<case>/oracle/` dir existing, so
  the two oracle-less cases are wholly untouched.

`BenchmarkWorkflow` builds one `BenchmarkRecord` per graded cell:
`scope=ORACLE, stage="oracle", role="oracle", judge="oracle",
quality=QualityScore(score, components={passed, total, held_out_ok, language_match},
judge="oracle")`. When `held_out_ok` is False **or** `language_match` is False, the
record's `error` is set (e.g. `"held-out breach: oracle path in produced diff"` /
`"language mismatch: manifest=python detected=typescript"`) so the integrity breach
surfaces in the report's failure section — loud, never silent.

## 4. Data flow — the grade's meaning

The grade flows through existing aggregation **untouched**. `compute_summaries`
(`scoring.py`) groups by `(case_id, stage, harness, model)`, so `stage="oracle"`
becomes a distinct report row beside the rubric-only stage rows:

```
| case         | stage     | harness  | model   | n | quality | ... |
| todo-api-... | oracle    | opencode | glm-5.2 | 1 | 0.857   | ... |   <- objective
| todo-api-... | architect | opencode | glm-5.2 | 1 | 0.780   | ... |   <- rubric-only
```

`quality.score` = fraction passing; `quality.components` carries `passed` / `total`
/ `held_out_ok` / `language_match` for drill-down. The grade feeds `composite` with
the same weights as any quality axis — deliberately **not** special-cased in scoring.
It earns authority by being objective, not by a weighting trick. Formalizing Tier-A
vs Tier-B trust is **E-36** (calibration); E-31 only *produces* the Tier-A number.

## 5. Error handling — fail-safe, mirroring `measure_coverage`

Every failure degrades to an excluded-or-honest grade with a detail string; the
unattended benchmark never crashes.

| Condition | Result |
|---|---|
| Integration branch absent (early rejection) | `score=None`, "no produced code" — excluded from composite |
| No adapter for manifest `language` | `score=None`, "no toolchain adapter for <lang>" |
| Oracle run errors / times out / malformed JUnit / 0 tests | `score=None`, detail carries the tail — never a fabricated pass/fail |
| `language_match` False (manifest ≠ marker) | grade still computed if adapter exists; `error` set — mismatch is loud |
| `held_out_ok` False (oracle path in produced diff) | grade reported but `error` set — breach surfaced, cell not silently trusted |
| Oracle import fails (interface contract unmet) | tests error → counted in `total` → grade drops honestly |
| Unexpected exception anywhere | boundary catch → `score=None`, like `judge_artifact` |

## 6. The reference oracle — `benchmarks/cases/todo-api-greenfield/oracle/`

An in-process oracle must exercise produced code through a **stable interface
contract** — the criterion→test discipline (FR-106) E-31 leans on. Amend the
`todo-api-greenfield` case description to add, as a frozen acceptance criterion:

> Implement in **Python**. Expose a WSGI/ASGI application object importable as
> **`app:app`** (module `app.py`, attribute `app`) serving the CRUD routes.

The oracle is then black-box against that HTTP contract, not internal layout:

```
benchmarks/cases/todo-api-greenfield/
  case.yaml          # + language: python
  oracle/
    conftest.py      # import app:app; wrap in a test client (WSGI/ASGI);
                     #   fresh store per test; if import fails, tests error honestly
    test_crud.py     # create -> 201 + id; list contains it; get by id;
                     #   update -> reflected; delete -> subsequent get 404
```

Depending only on the declared entrypoint + HTTP contract keeps architect's stack
choice (Flask / FastAPI / …) and storage free — so `rubric-architect` stays
meaningful — while the oracle stays deterministic. Produced code that misses
`app:app` fails import → the grade honestly reflects an unmet interface.

## 7. Testing

- **Adapter unit** (`tests/test_toolchain_adapters.py`): `oracle_test_cmd` string
  shape; JUnit report path is where the grader reads.
- **Grade parsing** (`tests/test_oracle.py`, pure): well-formed JUnit (mixed
  pass/fail/error) → correct fraction; `passed = tests − failures − errors` incl.
  all-pass (1.0) and all-fail (0.0) edges; malformed / empty / zero-tests → `None`.
- **Held-out + mismatch logic** (pure): a produced-diff path under `oracle/` →
  `held_out_ok=False`; manifest ≠ detected → `language_match=False`.
- **End-to-end seam** (`tests/test_grade_oracle.py`): a tiny fixture git repo whose
  integration branch has an `app.py` exposing `app:app` and a two-test oracle where
  one test passes and one fails → `grade_oracle` returns a fraction strictly between
  0 and 1, `held_out_ok=True`, `language_match=True`, and cleans up the worktree.
  **This is the proof E-31 exists to deliver:** a hidden suite, never in the run,
  grading produced code through the adapter.
- **Degradation regressions**: missing integration branch → `score=None`; unknown
  `language` → `score=None`; the two oracle-less cases (`add-login`, `cat-cafe`) run
  through `BenchmarkWorkflow` unchanged (grading gated off).

## 8. Out of scope / follow-ons

- **E-31a** — anti-cheat B, "built evenly, not to the test": a diff-coverage-
  distribution overfit metric. Needs its own defensible definition; shipping it
  half-specified would undercut the objective grade E-31 establishes.
- **E-30a/b/c** — `oracle_test_cmd` for Go / TS / Rust, added with those adapters as
  the case corpus needs the language (go-junit-report / vitest / cargo-nextest → the
  same JUnit reader).
- **Oracles for `cat-cafe` / `add-login`** — authored once the mechanism is proven
  on the Python reference.
- **E-36** — Tier-A vs Tier-B trust calibration reads the grade E-31 produces; not
  built here.
