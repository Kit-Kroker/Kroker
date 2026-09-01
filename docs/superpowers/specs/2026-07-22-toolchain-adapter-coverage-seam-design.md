# E-30 — `ToolchainAdapter` + coverage seam (Python reference)

| | |
|---|---|
| Date | 2026-07-22 |
| Roadmap item | E-30 (§9.8); §1 stage 12; ADR-15 |
| Anchors | **FR-108** (new, added by this increment), FR-106, FR-104, FR-203 (pattern), NFR-6, SC-5; unblocks E-31 |
| Status | Approved design — pre-plan |

## 1. Why

Generated projects can be Python / TS / Go / Rust, but the deterministic quality
gate's stack-specific verification is hardcoded Python: `DEFAULT_TEST_CMD =
"pytest -q"` / `DEFAULT_LINT_CMD = "ruff check ."` (`feature.py:145`). So the
grade cannot be language-agnostic, and — worse — there is **no objective,
test-based grade at all**, because of a wiring gap:

- `run_test_suite` runs **per-task** in each *task* worktree (`feature.py:576`).
- `measure_coverage` reads `coverage.xml` from the *integration* worktree
  (`feature.py:1116`).
- Nothing carries the artifact across the merge, and the contract's default test
  command (`pytest -q`) is not even coverage-instrumented — so `coverage.xml`
  never exists where the gate looks. `measure_coverage` returns `measured=False`
  every run, and the `coverage` advisory check is a permanent no-op (ROADMAP §1
  stage 12, FR-106).

A second latent gap surfaced while tracing this: **`build_integration_green`
never runs tests in integration.** At `feature.py:1162` it is
`_merge_evidence_all_green(list(done.values()))` — an *aggregate of per-task* QA
results, not a test run against the merged integration head. A per-task-green /
integration-red combination is invisible to it, contra ADR-14 (integration by
running branch).

E-30 is the highest-leverage item in BENCHMARK.md §6: *"without this there is no
objective grade and every other metric sits on rubric-only judging."* It is a
**pipeline capability, not a benchmark fix** — the stage-11/12 activities are
production code the benchmark merely exercises.

**Scope decisions locked in brainstorming:**
- PRD amended first: **FR-108 — Language-agnostic toolchain** landed in
  `PRD.md` before this spec (source-of-truth discipline; E-30's `(new scope)`
  marker).
- **Python reference adapter, end-to-end.** Go / TS / Rust are **E-30a/b/c**,
  deferred and additive (each is the N-th adapter, same shape). E-31 (held-out
  oracle) is out.
- **Security floor = SARIF *seam*, regex *default*.** Define the canonical
  SARIF-normalized `SecurityReport`; keep today's offline deterministic regex
  ruleset as the default `security_scan` body; semgrep is an opt-in path feeding
  the same normalizer. Preserves the "pure filesystem read, reproducible across
  Temporal retries, CI-safe without external tools/keys" invariant.
- **Coverage crosses into integration by re-running test + coverage there**
  (not by carrying a git-tracked `coverage.xml` across per-task merges). Matches
  ADR-14; deterministic; no merge-conflict/staleness on a generated artifact.
- **`build_integration_green` becomes a real integration test run** (the folded
  fix above), with the per-task aggregate retained as the no-adapter fallback.

## 2. ADR-15 — Toolchain adapter (recorded here)

> **ADR-15 — Language-agnostic toolchain by marker file.** The gate's
> stack-specific verification (build / test / lint / coverage / security) is
> performed by a `ToolchainAdapter` resolved from the produced repository's
> **marker file** (`pyproject.toml` / `package.json` / `go.mod` /
> `Cargo.toml`), structurally identical to the harness adapter (ADR-2/3): a
> `TOOLCHAINS` registry beside `HARNESSES`, normalizing into the gate's
> canonical evidence formats — **Cobertura XML** for coverage and a
> **SARIF-shaped `SecurityReport`** for the absolute security floor. The gate
> readers (`measure_coverage`, `security_no_critical`) are unchanged and
> language-neutral; adding a language changes neither workflow nor gate code
> (cf. ADR-2/FR-203). Detection resolves by **what was built** (marker file),
> not by the contract's claimed stack — a marker/claim mismatch is itself a
> signal (the toolchain analogue of the criterion→test traceability gap, and
> the anti-cheat stance E-31 extends).

The ADR text is added to `ARCHITECTURE.md §12` and marked `[x] ADR-15` in
`ROADMAP.md §6` during implementation.

## 3. Component design — `src/sdlc/toolchain/`

Mirrors `src/sdlc/harness/adapters.py` exactly (ABC + concrete + module-level
registry dict).

```
src/sdlc/toolchain/
  __init__.py
  adapters.py     # ToolchainKind, ToolchainAdapter (ABC), PythonToolchain,
                  #   TOOLCHAINS registry, detect(worktree)
  sarif.py        # SARIF run.results -> list[SecurityFinding] normalizer
```

```python
class ToolchainKind(str, Enum):
    PYTHON = "python"
    # GO/TS/RUST added by E-30a/b/c


class ToolchainAdapter(ABC):
    kind: ToolchainKind
    marker: str  # relative marker filename to detect by

    @abstractmethod
    def test_cmd(self) -> str: ...  # coverage-INSTRUMENTED, emits Cobertura
    @abstractmethod
    def lint_cmd(self) -> str: ...
    def build_cmd(self) -> str | None:  # None where no separate build (Python)
        return None


class PythonToolchain(ToolchainAdapter):
    kind = ToolchainKind.PYTHON
    marker = "pyproject.toml"

    def test_cmd(self) -> str:
        # coverage.py emits Cobertura; --cov-report=xml:coverage.xml lands it
        # exactly where measure_coverage reads. -q --maxfail keeps output bounded.
        return "pytest -q --maxfail=25 --cov=. --cov-report=xml:coverage.xml"

    def lint_cmd(self) -> str:
        return "ruff check ."


TOOLCHAINS: dict[ToolchainKind, ToolchainAdapter] = {
    ToolchainKind.PYTHON: PythonToolchain(),
}


def detect(worktree: str) -> ToolchainAdapter | None:
    """First adapter whose marker file exists at the worktree root. Returns
    None for an unrecognized/absent marker -> caller degrades gracefully."""
    for adapter in TOOLCHAINS.values():
        if os.path.isfile(os.path.join(worktree, adapter.marker)):
            return adapter
    return None
```

**Design invariants**
- The adapter object is **pure** — it produces command strings and identity,
  no subprocess/I-O. Execution stays in Temporal *activities* (identical
  discipline to `CodingHarness`, which never runs in workflow code).
- `detect()` reads a **marker file in the produced repo**, never the contract's
  `stack` field. "Grade what was built."
- `coverage()` is deliberately **not** an adapter method: the canonical Cobertura
  reader is the existing `measure_coverage`, fed by whatever `test_cmd()`
  emitted. One reader, all languages.

## 4. Canonical formats

### 4.1 Coverage → Cobertura `coverage.xml` (reader unchanged)
`PythonToolchain.test_cmd()` runs coverage.py, which writes Cobertura
`coverage.xml`. `measure_coverage` (`activities.py:568`) already parses exactly
that with `defusedxml`, diff-scoped to `changed_files`, `measured=False` on
absent/unsafe/no-changed-file. **No change to the reader** — the only fix E-30
makes is ensuring the artifact exists in the integration worktree (§5).

### 4.2 Security → SARIF-shaped `SecurityReport` (seam; regex default)
`SecurityReport` / `SecurityFinding` (`models.py:205`) are the canonical
normalized shape. Add `toolchain/sarif.py`:

```python
def findings_from_sarif(doc: dict) -> list[SecurityFinding]:
    """Normalize a SARIF log's runs[].results[] into SecurityFinding.
    Fail-safe: a malformed/partial SARIF yields [] (never raises), mirroring
    measure_coverage's measured=False discipline — an unbuilt/broken scan must
    never fabricate a blocking finding OR crash the gate."""
```

- `security_scan` keeps its **regex ruleset as the default body** — offline,
  deterministic, reproducible, CI-safe without semgrep.
- An **opt-in** semgrep path (config-gated, default off) runs semgrep `--sarif`
  and feeds `findings_from_sarif` → the *same* `SecurityReport`. `security_scan`'s
  return type and the `security_no_critical` reader (`feature.py:1170`, SC-5)
  are unchanged either way.
- Severity mapping: SARIF `level` (`error`/`warning`/`note`) → the existing
  `critical`/`high`/`medium`/`low` scale via a small explicit table (semgrep
  emits `error` for its blocking rules → `critical`).

## 5. Workflow wiring — stage 12, integration worktree

New activity in `activities.py`:

```python
@dataclass
class IntegrationChecksInput:
    worktree: str
    changed_files: list[str]


@activity.defn
async def run_integration_checks(inp) -> IntegrationChecks:
    """Resolve the toolchain by marker file and run test(+coverage) and lint
    against the merged integration head. Emits coverage.xml into `worktree`
    (where measure_coverage reads). adapter=None -> tests/lint not re-run here;
    caller falls back to per-task aggregate + no coverage."""
```

Returns a small normalized bundle: `QAReport` (integration test run),
`(lint_clean, lint_detail)`, and the resolved `toolchain` kind (or `None`).

Stage-12 changes in `feature.py` (§ around `1148–1195`):
1. `checks = await run_integration_checks(IntegrationChecksInput(integration_wt, integration_diff["files"]))`.
2. `measure_coverage` runs **after** step 1, so `coverage.xml` is now present →
   real diff-scoped `coverage` advisory check.
3. `build_integration_green` = `checks.qa.tests_passed` **when an adapter was
   detected**; otherwise `_merge_evidence_all_green(...)` (unchanged fallback).
4. `lint_clean` = `checks.lint_clean` when an adapter was detected; otherwise
   the existing standalone `run_lint` call (kept as fallback).
5. `security_scan` is unchanged in placement (already integration-scoped).

**No-adapter degradation is total and safe:** an unrecognized language behaves
exactly as today — per-task aggregate for green, `run_lint` for lint,
`measured=False` for coverage. E-30 never *blocks* on a language it doesn't know;
it only *adds* a real grade for the ones it does.

**Coverage instrumentation must not corrupt the absolute green signal.**
`build_integration_green` is an **absolute** check (blocks merge, no override) and
`coverage` is **advisory**. The instrumented `test_cmd()` therefore must never let a
*coverage-tooling* problem (e.g. `pytest-cov`/`coverage.py` absent → `unrecognized
arguments: --cov`) read as a *test failure* and falsely block the merge. Invariant
the plan must satisfy: **the green signal derives from actual test pass/fail; a
coverage-tooling failure degrades coverage to `measured=False`, never `green=False`.**
The reference adapter treats coverage.py as a documented Python-toolchain
prerequisite; the *activity* keeps the two signals independent so a missing plugin
is an advisory no-op, matching `measure_coverage`'s own "unbuilt measurement never
forces an override" discipline. Exact mechanism (dep assumption vs. green-signal
fallback run) is a plan decision.

## 6. Testing

- **Adapter units** (`tests/test_toolchain_adapters.py`): `detect()` picks
  Python by `pyproject.toml` and returns `None` on a bare dir; `test_cmd()` /
  `lint_cmd()` strings; `TOOLCHAINS` registry shape.
- **SARIF normalizer** (`tests/test_sarif.py`): well-formed multi-result SARIF →
  `SecurityFinding` list with correct severity mapping; malformed / empty /
  missing-keys SARIF → `[]` (fail-safe, no raise).
- **End-to-end coverage seam** (`tests/test_integration_checks.py`): a tiny
  fixture Python project (one covered fn + one uncovered fn + a test) →
  `run_integration_checks` produces a real `coverage.xml` in the worktree →
  `measure_coverage` reports a diff-scoped % strictly between 0 and 100 →
  `measured=True`. **This is the proof E-30 exists to deliver:** the artifact
  now crosses into integration and the gate consumes it.
- **Degradation regression**: a worktree with no known marker → `detect()` None →
  `run_integration_checks` returns `toolchain=None`, and stage 12 falls back
  without crashing. Existing gate/e2e tests continue to pass unchanged.

## 7. Out of scope / follow-ons

- **E-30a/b/c** — Go / TS / Rust adapters (each: `test_cmd` → Cobertura via the
  language's tool, `lint_cmd`, semgrep shared). Added as the case corpus needs
  the language.
- **E-31** — Tier-A held-out oracle, run *through* this adapter. Depends on E-30.
- **Real semgrep adoption** — the seam is built here; turning it on by default
  (and version-pinning it, cf. E-24) is a separate decision (OQ-B in
  BENCHMARK.md is silent on this; note it).
- **Per-task stage-11 QA refit** — stays contract-driven (`contract.test_commands`);
  E-30 touches only the stage-12 integration grade.
