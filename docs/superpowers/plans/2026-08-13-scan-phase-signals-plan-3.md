# Scan Phase — Plan 3 of 3: S2, S4, SS4, QS3 and the Five Extension Halves

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the nine remaining scan signal bodies — S2 (schema clusters), S4 (frontend entry points), SS4 (data sensitivity), QS3 (testability) and the computed halves of SS1, SS3, QS1, QS2, QS4 — so every one of E-46's thirteen signals reports a measured result, closing FR-912 and E-46.

**Architecture:** Nine pure modules under `src/sdlc/assessment/scan/signals/`, each a function from blob text (plus, for a wave-2 signal, its declared upstream) to a `SignalOutput`. Five of them need payload shapes the artifact does not yet have, so this plan opens with a contracts task that adds five record types, five `ScanResult` fields, and a typed `ScanUpstream` — the channel a wave-2 signal reads its upstream through. Each signal then lands with its activity body (memo-wrapped, never raising) in one task, and a close-out task removes the last `OWED_BY` entry, extends the operator summary and updates the roadmap.

**Tech Stack:** Python 3.12, Pydantic v2, Temporal (`temporalio`), `defusedxml` (untrusted Cobertura XML), PyYAML (`safe_load`, guarded), pytest.

**Spec:** `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md`. Decision ids **D1–D14** refer to its §2; **P2-D1/P2-D2** to plan 2; **P3-D1…P3-D11** are added by this plan and recorded below.

**Prior plans:**
- `docs/superpowers/plans/2026-08-12-scan-phase-signals-plan-1.md` — contracts, `SCAN_SIGNALS`, the memoized activity seam, `run_or_degrade`, `inherit.py`, all thirteen rows.
- `docs/superpowers/plans/2026-08-13-scan-phase-signals-plan-2.md` — S1, S3, S5 and `naming.py`.

## Global Constraints

- **Purity.** Every module under `assessment/scan/` may import Pydantic, third-party pure libraries (`defusedxml`, `yaml`), `...measurement`, `...triage.models` and `...toolchain.adapters` **only**. Never `sdlc.models`, `sdlc.activities`, `sdlc.triage.signals.*`, `sdlc.triage.gitread` or `temporalio`. A dependency there would appear as a reviewable import. This is why `testpaths.py` re-declares test conventions rather than importing `triage/signals/baseline.py`'s.
- **FR-915.** A value that was never measured must not be representable as a measured value. Never `Measurement.measured(0.0)` for something that did not run. A measured zero means *we looked at the whole tree and there is none*; anything else is `not_collected` with a reason naming what was missing.
- **D5 — an unmatched framework reports `not_collected`, never zero.** A file whose framework matches no fingerprint contributes `not_collected` naming the gap.
- **Determinism (NFR-10).** Iterate `SCAN_ORDER`, never a bare `set` or `dict`. Sort every list before it enters an artifact. Sort *inside* each signal, not only in `_scan`. The same tree must yield byte-identical output.
- **No repository code executes.** Every signal is a blob read at the pinned commit. The `init` phase's build probe stays the only place the assessed repo runs (NFR-9, D12). QS2 must not run the suite; QS4 must not run the pipeline.
- **Derived, never assigned.** `ScanCandidate.confidence` comes from `confidence_from(...)`; a signal's wave comes from `consumes`; `Assessment.terminal_status` comes from its phases.
- **Activities never raise.** A signal that fails returns `failed_signal(...)` for itself. `run_or_degrade` covers timeouts and lost workers; the activity's own `try/except` covers everything inside it.
- **Bounded reads.** `MAX_BLOB_BYTES` (1 MB) is applied by `_source_blobs`; a skipped oversized blob is recorded in the owing category's reason, never silently dropped.
- **Severity is a hint.** Scan never assigns a final severity — E-49 does. The field is `severity_hint` and its docstring says so.
- **Test commands:** `pytest tests/<file> -v` for unit; `pytest -m temporal tests/<file> -v` for workflow e2e. Default `pytest` runs unit only.

### Plan-level decisions

**P3-D1 — five payload types, and SS1/SS3 share one list.** The spec's own note on `SignalOutput` (plan-1 review finding 3) records that five computed halves have no payload type. SS1 and SS3 both emit *a security observation at a path, in a declared category*, so they share `ScanResult.security` and each record carries `signal: ScanSignalId` — which is exactly the discriminator `_unmeasured_carries_no_payload` already uses (`getattr(r, "signal", signal_id)`), and the same shape S1–S4 use to share `sources`. QS1, QS2 and QS4 own their fields.

**P3-D2 — `PAYLOAD_FIELD` becomes signal → *tuple* of fields.** QS4 owns two payloads (CI stages and environments) whose shapes share nothing. Widening the map to a tuple is smaller than inventing a union record, and it keeps `_unmeasured_carries_no_payload` total: a signal that did not run carries no records in *any* of its fields.

**P3-D3 — SS4 declares `consumes=(S2, S3)`.** `SensitivityRecord.accessed_by` cites S3 entry points, but the registry as shipped declares SS4 consuming S2 only, and `_upstream_for` filters payloads by that same declaration. As shipped, `accessed_by` could only ever be populated by reading undeclared data — and `rules_sha`, which walks `consumes`, would then miss S3's pattern table. That is the precise stale-cache setup D10 exists to prevent. Both S2 and S3 are wave 1, so SS4 stays a wave-2 signal and `_assert_registry_is_sound`'s two-wave rule still holds.

**P3-D4 — the upstream channel becomes typed (`ScanUpstream`), and carries the upstream's `collected`.** `ScanSignalInput.upstream: list[SourceCandidate]` cannot carry QS1's test→file mapping, and an empty candidate list cannot distinguish *"S2 measured zero clusters"* from *"S2 did not collect"* — the distinction §5 requires a wave-2 signal to make. `ScanUpstream` carries one field per payload kind plus `collected: dict[ScanSignalId, Measurement]`, all filtered by the declared `consumes`. This is `merge()`'s existing `upstream` argument generalized: S5 already needed exactly this pair to tell a gap from a real zero.

**P3-D5 — a wave-2 signal is never memoized when its upstream did not collect.** `memo.store` refuses a non-`MEASURED` row (D10), but SS1 can legitimately report `MEASURED` — a TLS count — while `input_validation` is `not_collected` because S3 degraded. Caching that serves a permanently-missing category against a healthy S3 forever, on an unchanged tree. So `store` gains a third rule: never store when any consumed signal's `collected` is not `MEASURED`. The memo key is sound for the healthy case (upstream output is itself a pure function of the tree and of modules `rules_sha` already hashes); it is unsound for the degraded case, which is what this rule removes.

**P3-D6 — `accessed_by` is a name match, and says so.** SS4 links an entity to the S3 candidates whose normalized name equals the entity's normalized name. A read/write dataflow analysis is not available to a blob-reading scan, and asserting one would be a fabrication at the level FR-914 exists to prevent. The rule name (`ss4_entity_name_matches_entry_point`) travels on the record so a reader can see what the link is worth.

**P3-D7 — QS4's env drift is CI-vs-config, not CI-vs-declared.** BrownKit compares CI environments against `qa_scope.environments`, which comes from `/enrich` — E-56, unbuilt. Rather than report `env_drift` permanently `not_collected`, drift is computed between the two declarations the repository itself carries: environments named by CI deploy targets, and environments named by committed config files. The declared-scope comparison is E-56's when it lands, and the category's reason says so when no CI file exists.

**P3-D8 — YAML is parsed with `safe_load` behind an expansion guard.** `yaml.safe_load` does not execute code, but YAML anchors/aliases still expand (the "billion laughs" bomb), and CI files come from an untrusted repository (NFR-9). `ci.py` refuses a file over 256 KB or carrying more than 50 alias references, reporting `not_collected` for that file with the reason. Cobertura XML gets the same treatment via `defusedxml`, for the same reason `measure_coverage` already uses it.

**P3-D9 — test conventions are a shared rule module (`scan/testpaths.py`).** S2 (exclude fixture schemas), QS1 (find tests), QS2 (exclude tests from significant files) and QS3 (exclude tests from testability findings) all need the same "is this a test path?" fact. Four copies would agree only by coincidence — the reason `naming.py` and `sources.py` are sited once — so all four declare it as a `rule_module`. Deliberately not `ToolchainAdapter.test_globs`: only `PythonToolchain` exists, so gating on the adapter would make QS1 report nothing for the JS/TS repositories Tier 0 actually receives (D4's reasoning, verbatim).

**P3-D10 — QS3 emits one finding per (path, pattern), with the occurrence count in the detail.** A per-line finding turns a mid-size repository's `datetime.now()` habit into thousands of rows in the FR-921 bundle, and each row's `key` (an evidence hash) would differ, so E-44's delta would report a phantom resolved+new pair whenever a line moved. One finding per (path, pattern) with `key=""` gives `testability_identity` exactly the stability E-44 D3 asks for.

**P3-D13 — S2 clusters by name stem; foreign keys corroborate, they never merge.** Union-find over FK connectivity collapses a normalized schema into one component — `orders` → `customers` → `users` → everything — and would emit a single "capability" covering the whole database. Naming is the discriminating half, so it does the clustering; the FK count raises the cluster's confidence contribution and is recorded as a metric. Deciding that two name-distinct clusters are one capability is E-48's `MERGE`, which is the same reason S5 never silently collapses (D9 rule 2).

**P3-D12 — SS4 owns two categories, not one** (stated in full in Task 4). The spec requires that a missing S3 must not make SS4 read as *"no entry point touches PII"*, and a signal with one category has nowhere to say why every `accessed_by` is empty. `data_sensitivity` (needs S2 and the tree) and `entity_access` (needs S3) fail independently, which is what D3's per-category coverage exists for.

**P3-D11 — a category that needs two inputs reports `not_collected` when it has one.** SS3's `env_divergence` compares environment files against each other and QS4's `env_drift` compares CI against config. With fewer than two inputs there is nothing to compare — which is *unmeasurable*, not *no divergence*. This is the same rule S1 applies in the other direction (a tree with no source files is a measured zero, because the whole tree was read).

---

## File Structure

| File | Responsibility |
|---|---|
| `scan/models.py` **(modify)** | Five new record types, `ScanUpstream`, five new `ScanResult`/`SignalOutput` fields, `PAYLOAD_FIELD` widened to tuples. |
| `scan/testpaths.py` **(create)** | `TEST_PATH_GLOBS` + `is_test_path`. Shared rule module for S2, QS1, QS2, QS3 (P3-D9). |
| `scan/registry.py` **(modify)** | SS4 gains `consumes=(S2, S3)`; the new `rule_modules` declarations for eight signals. |
| `scan/memo.py` **(modify)** | `store` gains the upstream-collected rule (P3-D5). |
| `scan/signals/schema.py` **(rewrite)** | S2: table declarations, FK edges, clusters. Also exports `declarations()` for SS4. |
| `scan/signals/frontend.py` **(rewrite)** | S4: file-convention and config routes, grouped by journey. |
| `scan/signals/sensitivity.py` **(rewrite)** | SS4: entity → sensitivity classification, accessors by name match. |
| `scan/signals/testability.py` **(rewrite)** | QS3: testability patterns, one finding per (path, pattern). |
| `scan/signals/tests_inventory.py` **(rewrite)** | QS1: test level classification and test→file mapping. |
| `scan/signals/coverage.py` **(rewrite)** | QS2: committed Cobertura report, else QS1-derived proxy. |
| `scan/signals/security_static.py` **(rewrite)** | SS1 computed half: TLS enforcement, input validation at S3's entry points. |
| `scan/signals/config_infra.py` **(rewrite)** | SS3 computed half: exposed ports, env divergence, DB security, log masking. |
| `scan/signals/ci.py` **(rewrite)** | QS4 computed half: CI stages, environment drift. |
| `scan/summary.py` **(modify)** | Security/QA counts, coverage source and headline, drift line. |
| `assessment/activities.py` **(modify)** | Nine real activity bodies; `ScanSignalInput.upstream: ScanUpstream`; `OWED_BY` emptied, `BUILT` completed. |
| `workflows/assessment.py` **(modify)** | `upstream_for` returns `ScanUpstream`; `_scan` gathers the five new payload lists. |

---

### Task 1: Contracts — five payload types, `ScanUpstream`, and the shared test-path rules

**Files:**
- Modify: `src/sdlc/assessment/scan/models.py`
- Create: `src/sdlc/assessment/scan/testpaths.py`
- Modify: `src/sdlc/assessment/scan/registry.py`
- Modify: `src/sdlc/assessment/scan/memo.py`
- Modify: `src/sdlc/assessment/activities.py` (`ScanSignalInput.upstream`)
- Modify: `src/sdlc/workflows/assessment.py` (`_upstream_for` → `upstream_for`, `_scan` payload gathering)
- Test: `tests/test_scan_testpaths.py` (create)
- Test: `tests/test_scan_upstream.py` (create)
- Test: `tests/test_scan_payloads.py` (extend)
- Test: `tests/test_scan_stub_activities.py` (make the payload check generic)
- Test: `tests/test_assessment_scan_phase.py` (rename the import)

**Interfaces:**
- Produces, from `scan/models.py`: `SecurityObservation`, `security_identity(o) -> str`, `TestLevel`, `TestFileRecord`, `CoverageRecord`, `CiStageRecord`, `EnvironmentRecord`, `ScanUpstream` (with `.measured(sid) -> bool` and `.gap(sid, category) -> Measurement`), and the widened `PAYLOAD_FIELD: dict[ScanSignalId, tuple[str, ...]]`. `ScanResult` and `SignalOutput` both gain `security`, `tests`, `coverage`, `ci`, `environments`.
- Produces, from `scan/testpaths.py`: `TEST_PATH_GLOBS: tuple[str, ...]`, `is_test_path(path: str) -> bool`.
- Produces, from `scan/memo.py`: `store(signal_id, tree_hash, out, upstream: ScanUpstream | None = None) -> bool`.
- Produces, from `workflows/assessment.py`: `upstream_for(signal_id, outputs) -> ScanUpstream`.
- Consumed by: Tasks 2–10 (every signal), and Task 11's summary.

- [ ] **Step 1: Write the failing tests for the shared test-path rules**

Create `tests/test_scan_testpaths.py`:

```python
"""P3-D9: four signals ask the same 'is this a test path?' question. Four
copies would agree only by coincidence, which is why naming.py and sources.py
are sited once and declared as rule modules."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.testpaths import TEST_PATH_GLOBS, is_test_path


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_api.py",
        "src/app/test_service.py",
        "src/app/service_test.py",
        "conftest.py",
        "src/components/Button.test.tsx",
        "src/components/Button.spec.ts",
        "src/__tests__/render.js",
        "cypress/e2e/login.cy.ts",
        "internal/server/handler_test.go",
        "src/test/java/com/acme/OrderTest.java",
        "spec/models/user_spec.rb",
        "e2e/checkout.spec.ts",
    ],
)
def test_test_paths_are_recognized(path):
    assert is_test_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/app/service.py",
        "src/components/Button.tsx",
        "internal/server/handler.go",
        "contest.py",  # not conftest.py
        "src/latest/index.ts",  # 'test' inside a word is not a test path
        "migrations/0001_init.sql",
    ],
)
def test_production_paths_are_not(path):
    assert is_test_path(path) is False


def test_the_four_consumers_all_declare_it_as_a_rule_module():
    """Without the declaration, adding a glob would change four signals'
    output while their memo keys stood still -- the D10 hazard."""
    module = "sdlc.assessment.scan.testpaths"
    for sid in (ScanSignalId.S2, ScanSignalId.QS1, ScanSignalId.QS2, ScanSignalId.QS3):
        assert module in SCAN_SIGNALS[sid].rule_modules, sid.value


def test_the_glob_table_is_not_empty():
    assert len(TEST_PATH_GLOBS) > 10
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_testpaths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.assessment.scan.testpaths'`

- [ ] **Step 3: Create `scan/testpaths.py`**

```python
"""Which paths are TEST paths -- shared by S2, QS1, QS2 and QS3 (P3-D9).

A scan-level constant belonging to no single signal, sited here for the reason
sources.py is: four signals read it, so editing the tuple changes four
signals' output, and all four therefore declare it as a `rule_module` so
rules_sha hashes it into all four memo keys. Without that, adding "*.cy.ts"
would silently serve a stale QS1 -- the exact E-3 / D10 hazard.

Deliberately NOT ToolchainAdapter.test_globs: only PythonToolchain exists, so
gating on the adapter would make QS1 report nothing for the JS/TS repositories
Tier 0 actually receives (D4's reasoning, verbatim). The adapter's tuple stays
the authority for the TRIAGE tier, which resolves a real toolchain first.
"""

from __future__ import annotations

import fnmatch
import posixpath

# fnmatch's '*' crosses '/', so "tests/**" matches "tests/a/b.py" and
# "*/tests/**" matches any nested tests directory. Both shapes are kept
# because a convention is sometimes a basename ("test_*.py") and sometimes a
# path ("cypress/**"), exactly as baseline.find_test_files handles them.
TEST_PATH_GLOBS: tuple[str, ...] = (
    # python
    "test_*.py",
    "*_test.py",
    "conftest.py",
    "tests/**",
    "*/tests/**",
    # javascript / typescript
    "*.test.js",
    "*.test.jsx",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.js",
    "*.spec.jsx",
    "*.spec.ts",
    "*.spec.tsx",
    "*.cy.js",
    "*.cy.ts",
    "__tests__/**",
    "*/__tests__/**",
    # go / rust / jvm / dotnet
    "*_test.go",
    "tests.rs",
    "*Test.java",
    "*Tests.java",
    "*Test.kt",
    "*Test.cs",
    "*Tests.cs",
    "src/test/**",
    "*/src/test/**",
    # ruby / php
    "*_spec.rb",
    "*Test.php",
    "spec/**",
    "*/spec/**",
    # cross-language directories
    "e2e/**",
    "*/e2e/**",
    "cypress/**",
    "*/cypress/**",
    "playwright/**",
    "*/playwright/**",
)


def is_test_path(path: str) -> bool:
    """True when `path` matches a test convention, by full repo-relative path
    OR by basename -- conventions come in both shapes."""
    base = posixpath.basename(path)
    return any(
        fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(base, glob) for glob in TEST_PATH_GLOBS
    )
```

- [ ] **Step 4: Write the failing tests for the five payload types**

Append to `tests/test_scan_payloads.py`:

```python
# --- plan 3: the five payload types the spec's SignalOutput note owes ------

from sdlc.assessment.scan.models import (  # noqa: E402
    CiStageRecord,
    CoverageRecord,
    EnvironmentRecord,
    PAYLOAD_FIELD,
    ScanSignalId,
    SecurityObservation,
    TestFileRecord,
    TestLevel,
    security_identity,
)
from sdlc.measurement import CollectionState, Measurement  # noqa: E402


def test_a_security_observation_declares_which_signal_owns_it():
    """P3-D1: SS1 and SS3 share ScanResult.security, and
    _unmeasured_carries_no_payload discriminates a row's own records by
    exactly this attribute."""
    o = SecurityObservation(
        signal=ScanSignalId.SS1,
        category="tls_enforcement",
        rule="ss1_tls_verification_disabled",
        detail="verify=False",
        severity_hint="high",
        path="src/client.py",
        line=12,
        evidence="requests.get(url, verify=False)",
        key="abc123",
        confidence=Confidence.HIGH,
    )
    assert o.signal is ScanSignalId.SS1
    assert security_identity(o) == "SS1:ss1_tls_verification_disabled:src/client.py:abc123"


def test_a_security_observation_must_name_a_category_its_signal_owes():
    """The row-level rule one level down: a category nobody declared cannot
    be reported, so CATEGORIES stays the one declaration."""
    with pytest.raises(ValidationError):
        SecurityObservation(
            signal=ScanSignalId.SS1,
            category="db_security",  # SS3's
            rule="r",
            detail="d",
            severity_hint="low",
            path="p",
            confidence=Confidence.LOW,
        )


def test_security_identity_ignores_line_like_its_two_siblings():
    o = SecurityObservation(
        signal=ScanSignalId.SS3,
        category="exposed_ports",
        rule="r",
        detail="d",
        severity_hint="info",
        path="Dockerfile",
        line=3,
        key="K",
        confidence=Confidence.LOW,
    )
    assert security_identity(o) == security_identity(o.model_copy(update={"line": 99}))


def test_an_unclassifiable_test_file_is_unknown_never_unit():
    """P3-D8's contract half: defaulting to unit would silently inflate the
    unit-test count, which is a measurement product's worst kind of bug."""
    r = TestFileRecord(
        path="tests/weird.py",
        level=TestLevel.UNKNOWN,
        rule="qs1_no_level_signature",
        mapping_rule="unmapped",
        confidence=Confidence.LOW,
    )
    assert r.level is TestLevel.UNKNOWN
    assert r.covers == []


def test_an_unmapped_test_covers_nothing_and_a_mapped_one_covers_something():
    with pytest.raises(ValidationError):
        TestFileRecord(
            path="t.py",
            level=TestLevel.UNIT,
            rule="r",
            mapping_rule="unmapped",
            covers=["src/a.py"],
            confidence=Confidence.LOW,
        )
    with pytest.raises(ValidationError):
        TestFileRecord(
            path="t.py",
            level=TestLevel.UNIT,
            rule="r",
            mapping_rule="naming_convention",
            covers=[],
            confidence=Confidence.LOW,
        )


def test_a_proxy_coverage_record_is_low_confidence_by_construction():
    """D12 + BrownKit's own rule: a proxy is not a measurement of coverage,
    and a HIGH-confidence proxy would read as one."""
    with pytest.raises(ValidationError):
        CoverageRecord(
            scope="package",
            path="src/app",
            covered=Measurement.measured(80.0),
            source="proxy",
            confidence=Confidence.HIGH,
        )
    ok = CoverageRecord(
        scope="package",
        path="src/app",
        covered=Measurement.measured(80.0),
        source="proxy",
        confidence=Confidence.LOW,
    )
    assert ok.tool == ""


def test_a_report_coverage_record_must_name_its_tool():
    """Acceptance gate 5 of BrownKit's scan: coverage records carry source
    and confidence, never a bare percentage."""
    with pytest.raises(ValidationError):
        CoverageRecord(
            scope="file",
            path="src/a.py",
            covered=Measurement.measured(50.0),
            source="report",
            confidence=Confidence.HIGH,
        )


def test_a_ci_stage_records_blocking_as_unreadable_at_a_commit():
    """A required check is a branch-protection setting, not a tracked file.
    FR-915 says that is not_collected, not False."""
    s = CiStageRecord(
        workflow=".github/workflows/ci.yml",
        stage="test",
        order=0,
        runs_tests=True,
        test_levels=[TestLevel.UNIT],
        blocking=Measurement.not_collected(
            "required checks are a branch-protection setting, not a tracked file"
        ),
    )
    assert s.blocking.state is CollectionState.NOT_COLLECTED


def test_an_environment_must_be_declared_somewhere():
    with pytest.raises(ValidationError):
        EnvironmentRecord(name="staging", in_ci=False, in_config=False)
    drifted = EnvironmentRecord(name="staging", in_ci=True, in_config=False)
    assert drifted.drifted is True
    assert EnvironmentRecord(name="prod", in_ci=True, in_config=True).drifted is False


def test_payload_field_covers_every_signal_that_can_produce_records():
    """P3-D2: QS4 owns two payload fields, so the map is signal -> tuple.
    SS2 owns none (D12 cut its computed half)."""
    assert PAYLOAD_FIELD[ScanSignalId.QS4] == ("ci", "environments")
    assert ScanSignalId.SS2 not in PAYLOAD_FIELD
    assert PAYLOAD_FIELD[ScanSignalId.SS1] == ("security",)
    assert PAYLOAD_FIELD[ScanSignalId.SS3] == ("security",)
```

- [ ] **Step 5: Run it to make sure it fails**

Run: `pytest tests/test_scan_payloads.py -v`
Expected: FAIL with `ImportError: cannot import name 'SecurityObservation'`

- [ ] **Step 6: Add the five payload types to `scan/models.py`**

Insert after the `CATEGORIES` block (they reference it) and before `class InheritedProducer`:

```python
class SecurityObservation(BaseModel):
    """SS1's and SS3's computed half: one security-relevant fact at one path.

    `signal` is carried because the two signals SHARE ScanResult.security and
    _unmeasured_carries_no_payload discriminates a row's own records by
    exactly that attribute -- the same shape S1-S4 use to share `sources`
    (P3-D1).

    `severity_hint`, never `severity`: BrownKit's own rule is that scan emits
    hints and /assess assigns severity (E-49). A field called `severity` would
    invite a consumer to treat a pattern match as a rating.
    """

    signal: ScanSignalId
    category: str
    rule: str
    detail: str
    severity_hint: Literal["info", "low", "medium", "high", "critical"]
    path: str
    line: int | None = None
    evidence: str = ""  # verbatim quote from path@commit_sha
    key: str = ""  # rule-scoped discriminator (E-44 D3)
    confidence: Confidence

    @model_validator(mode="after")
    def _category_is_owed_by_its_signal(self) -> "SecurityObservation":
        if self.category not in CATEGORIES[self.signal]:
            raise ValueError(
                f"{self.signal.value} observation names category "
                f"{self.category!r}, which it does not owe "
                f"{CATEGORIES[self.signal]} -- CATEGORIES is the one "
                f"declaration"
            )
        return self


def security_identity(o: SecurityObservation) -> str:
    """The identity a delta matches on. Excludes `line`, exactly as
    finding_identity and testability_identity do: a fix landing above an
    observation shifts its line, and a line-keyed identity would report a
    phantom resolved+new pair (E-44 D3)."""
    return f"{o.signal.value}:{o.rule}:{o.path}:{o.key}"


class TestLevel(str, Enum):
    """BrownKit's six levels plus UNKNOWN.

    UNKNOWN is the load-bearing member: a test-shaped file whose level no rule
    decided must not default to `unit`, which would silently inflate the
    unit-test count in a product that sells measurement (FR-915's spirit
    applied to a classification rather than a number).
    """

    UNIT = "unit"
    INTEGRATION = "integration"
    CONTRACT = "contract"
    E2E = "e2e"
    PERFORMANCE = "performance"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class TestFileRecord(BaseModel):
    """QS1's computed half: one test file, its level, and what it covers."""

    path: str
    level: TestLevel
    rule: str  # the rule that decided the level
    framework: str = ""  # "" when no framework signature matched
    covers: list[str] = Field(default_factory=list)
    mapping_rule: str  # naming_convention | co_location | unmapped
    confidence: Confidence

    @model_validator(mode="after")
    def _mapping_rule_agrees_with_covers(self) -> "TestFileRecord":
        if self.mapping_rule == "unmapped" and self.covers:
            raise ValueError(
                f"{self.path}: mapping_rule=unmapped but covers "
                f"{self.covers} -- a mapping that produced a file is not an "
                f"absent mapping"
            )
        if self.mapping_rule != "unmapped" and not self.covers:
            raise ValueError(
                f"{self.path}: mapping_rule={self.mapping_rule!r} produced no "
                f"covers -- say `unmapped`, so QS2's proxy cannot read an "
                f"empty mapping as a mapping to nothing"
            )
        return self

    @model_validator(mode="after")
    def _canonicalize(self) -> "TestFileRecord":
        self.covers = sorted(set(self.covers))
        return self


class CoverageRecord(BaseModel):
    """QS2. Never a bare percentage: BrownKit's acceptance gate 5 requires
    every coverage record to carry its source and confidence, and D12 forbids
    running the suite -- so `proxy` is a real and frequent answer here, not an
    edge case."""

    scope: Literal["file", "package"]
    path: str
    covered: Measurement  # percent in [0, 100]
    source: Literal["report", "proxy"]
    tool: str = ""  # "cobertura" for a report, "" for a proxy
    confidence: Confidence

    @model_validator(mode="after")
    def _source_fields_agree(self) -> "CoverageRecord":
        if self.source == "proxy" and self.confidence is not Confidence.LOW:
            raise ValueError(
                "a proxy coverage record is LOW confidence by construction "
                "(D12) -- tested_files/significant_files is not a measurement "
                "of coverage, and a HIGH-confidence proxy would read as one"
            )
        if self.source == "report" and not self.tool:
            raise ValueError(
                "a report coverage record must name the tool that produced "
                "it -- 'source: <tool>' is BrownKit's own rule"
            )
        return self


class CiStageRecord(BaseModel):
    """QS4's stages. `order` is the position within its workflow file, so a
    reader sees the pipeline's shape without re-parsing it."""

    workflow: str  # path of the CI file
    stage: str  # job / stage id
    order: int
    runs_tests: bool
    test_levels: list[TestLevel] = Field(default_factory=list)
    deploys_to: str = ""  # environment name; "" when it does not
    # A required check is a branch-protection setting, not a tracked file, so
    # it is not readable at a pinned commit. not_collected, never False --
    # "this job does not block merges" and "we cannot see what blocks merges"
    # are different facts (FR-915). E-59's app install is what makes it
    # measurable, with no schema change here.
    blocking: Measurement

    @model_validator(mode="after")
    def _levels_only_when_it_tests(self) -> "CiStageRecord":
        if self.test_levels and not self.runs_tests:
            raise ValueError(f"{self.stage}: declares test levels but runs_tests is False")
        return self


CiStageRecord.__test__ = False


class EnvironmentRecord(BaseModel):
    """QS4's env_drift (P3-D7): one environment name and where the repository
    declares it. `drifted` is DERIVED from the two booleans, never assigned --
    D8's rule applied one level down."""

    name: str
    in_ci: bool  # named by a CI job's deploy target
    in_config: bool  # named by a committed config / env file
    evidence: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _declared_somewhere(self) -> "EnvironmentRecord":
        if not self.in_ci and not self.in_config:
            raise ValueError(
                f"{self.name!r} is declared nowhere -- an environment no side "
                f"names is not an environment, it is an empty record"
            )
        return self

    @property
    def drifted(self) -> bool:
        return self.in_ci != self.in_config


class ScanUpstream(BaseModel):
    """Everything a signal may read from the signals it declares in
    `consumes` (D10, P3-D4).

    One field per payload kind, so a new dependent signal is a registry edit
    rather than a new activity-input field. `collected` travels beside the
    payloads because an empty list cannot distinguish "the upstream measured
    zero" from "the upstream did not collect" -- the distinction section 5
    requires every wave-2 signal to make, and the reason merge() already takes
    both.
    """

    sources: list[SourceCandidate] = Field(default_factory=list)
    tests: list[TestFileRecord] = Field(default_factory=list)
    collected: dict[ScanSignalId, Measurement] = Field(default_factory=dict)

    def measured(self, signal_id: ScanSignalId) -> bool:
        """Whether a consumed signal collected. False when it is absent from
        the map: an upstream that never reported is not one that reported
        nothing."""
        m = self.collected.get(signal_id)
        return m is not None and m.state is CollectionState.MEASURED

    def gap(self, signal_id: ScanSignalId, category: str) -> Measurement:
        """The not_collected a dependent category reports when its input did
        not collect, carrying the upstream's own reason so the assessment says
        WHY and not merely THAT (section 5, D5)."""
        m = self.collected.get(signal_id)
        why = m.reason if m is not None and m.reason else f"{signal_id.value} did not report"
        return Measurement.not_collected(
            f"{category}: depends on {signal_id.value}, which did not collect ({why})"
        )
```

Then widen `PAYLOAD_FIELD` and both artifact models:

```python
# Which ScanResult field(s) each signal's payload lands in. A TUPLE per
# signal because QS4 owns two payloads whose shapes share nothing (P3-D2);
# SS2 owns none, since D12 cut its computed half.
PAYLOAD_FIELD: dict[ScanSignalId, tuple[str, ...]] = {
    ScanSignalId.S1: ("sources",),
    ScanSignalId.S2: ("sources",),
    ScanSignalId.S3: ("sources",),
    ScanSignalId.S4: ("sources",),
    ScanSignalId.S5: ("candidates",),
    ScanSignalId.SS1: ("security",),
    ScanSignalId.SS3: ("security",),
    ScanSignalId.SS4: ("data_sensitivity",),
    ScanSignalId.QS1: ("tests",),
    ScanSignalId.QS2: ("coverage",),
    ScanSignalId.QS3: ("testability",),
    ScanSignalId.QS4: ("ci", "environments"),
}


class SignalOutput(BaseModel):
    """One computed signal's whole output -- the row AND its payload, cached
    as a unit (D10). An activity returns this; the workflow folds in the
    inherited half (D7)."""

    row: ScanSignalResult
    sources: list[SourceCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)
    security: list[SecurityObservation] = Field(default_factory=list)
    tests: list[TestFileRecord] = Field(default_factory=list)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    ci: list[CiStageRecord] = Field(default_factory=list)
    environments: list[EnvironmentRecord] = Field(default_factory=list)


class ScanResult(BaseModel):
    signals: list[ScanSignalResult]
    sources: list[SourceCandidate] = Field(default_factory=list)
    candidates: list[ScanCandidate] = Field(default_factory=list)
    data_sensitivity: list[SensitivityRecord] = Field(default_factory=list)
    testability: list[TestabilityFinding] = Field(default_factory=list)
    security: list[SecurityObservation] = Field(default_factory=list)
    tests: list[TestFileRecord] = Field(default_factory=list)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    ci: list[CiStageRecord] = Field(default_factory=list)
    environments: list[EnvironmentRecord] = Field(default_factory=list)
```

and make the payload validator iterate the tuple:

```python
@model_validator(mode="after")
def _unmeasured_carries_no_payload(self) -> "ScanResult":
    by_id = {s.signal: s for s in self.signals}
    for signal_id, field_names in PAYLOAD_FIELD.items():
        row = by_id[signal_id]
        if row.collected.state is CollectionState.MEASURED:
            continue
        for field_name in field_names:
            # A field can hold other signals' records too (S1-S4 share
            # `sources`, SS1+SS3 share `security`), so only this signal's
            # own records are checked.
            mine = [
                r for r in getattr(self, field_name) if getattr(r, "signal", signal_id) is signal_id
            ]
            if mine:
                raise ValueError(
                    f"{signal_id.value} is {row.collected.state.value} "
                    f"but carries {len(mine)} record(s) in "
                    f"{field_name!r} -- a signal that did not run has no "
                    f"records; partial output is UNKNOWN"
                )
    return self
```

Finally, the pytest-collection guard the existing `TestabilityFinding` already carries. pytest collects `Test*`-named classes out of a **test module's namespace**, including imported ones, so any new class whose name starts with `Test` needs it — two do, and `CiStageRecord` does not (its name does not start with `Test`; the `__test__ = False` shown on it above is harmless belt-and-braces and may be dropped):

```python
TestLevel.__test__ = False
TestFileRecord.__test__ = False
```

- [ ] **Step 7: Run the payload tests**

Run: `pytest tests/test_scan_payloads.py tests/test_scan_testpaths.py -v`
Expected: the payload tests PASS; `test_the_four_consumers_all_declare_it_as_a_rule_module` still FAILS (the registry edit is Step 9).

- [ ] **Step 8: Write the failing tests for `ScanUpstream`, `upstream_for` and the memo rule**

Create `tests/test_scan_upstream.py`:

```python
"""P3-D4/P3-D5: the typed upstream channel, and the rule that keeps a
degraded upstream out of the memo."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan import memo
from sdlc.assessment.scan.models import (
    CATEGORIES,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    TestFileRecord,
    TestLevel,
    family_of,
)
from sdlc.assessment.scan.registry import SCAN_SIGNALS
from sdlc.measurement import CollectionState, Measurement
from sdlc.workflows.assessment import upstream_for

TREE = 40 * "cd"


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path))


def _row(sid: ScanSignalId, m: Measurement) -> ScanSignalResult:
    return ScanSignalResult(
        signal=sid,
        family=family_of(sid),
        version=1,
        source=SignalSource.COMPUTED,
        collected=m,
        categories={k: m for k in CATEGORIES[sid]},
    )


def _candidate(sid: ScanSignalId, local_id: str) -> SourceCandidate:
    return SourceCandidate(
        signal=sid,
        local_id=local_id,
        name=local_id,
        rule="r",
        detail="d",
        confidence_contribution=Confidence.LOW,
        members=[CandidateMember(kind=MemberKind.DB_TABLE, value=local_id)],
    )


def _test_file(path: str) -> TestFileRecord:
    return TestFileRecord(
        path=path,
        level=TestLevel.UNIT,
        rule="r",
        mapping_rule="naming_convention",
        covers=["src/a.py"],
        confidence=Confidence.MEDIUM,
    )


def test_ss4_receives_both_the_signals_it_consumes():
    """P3-D3: accessed_by cites S3, so SS4 must DECLARE S3 -- otherwise
    populating it would read undeclared data and rules_sha would miss S3."""
    assert SCAN_SIGNALS[ScanSignalId.SS4].consumes == (ScanSignalId.S2, ScanSignalId.S3)
    measured = Measurement.measured(1.0)
    outputs = {
        ScanSignalId.S1: SignalOutput(
            row=_row(ScanSignalId.S1, measured), sources=[_candidate(ScanSignalId.S1, "S1-a")]
        ),
        ScanSignalId.S2: SignalOutput(
            row=_row(ScanSignalId.S2, measured), sources=[_candidate(ScanSignalId.S2, "S2-orders")]
        ),
        ScanSignalId.S3: SignalOutput(
            row=_row(ScanSignalId.S3, measured), sources=[_candidate(ScanSignalId.S3, "S3-orders")]
        ),
    }
    up = upstream_for(ScanSignalId.SS4, outputs)
    assert [c.local_id for c in up.sources] == ["S2-orders", "S3-orders"]
    assert set(up.collected) == {ScanSignalId.S2, ScanSignalId.S3}
    assert up.measured(ScanSignalId.S2) is True


def test_qs2_receives_qs1s_test_records_not_candidates():
    """The channel a list[SourceCandidate] could not carry."""
    measured = Measurement.measured(2.0)
    outputs = {
        ScanSignalId.QS1: SignalOutput(
            row=_row(ScanSignalId.QS1, measured), tests=[_test_file("tests/test_a.py")]
        )
    }
    up = upstream_for(ScanSignalId.QS2, outputs)
    assert [t.path for t in up.tests] == ["tests/test_a.py"]
    assert up.sources == []


def test_a_gap_names_the_upstream_and_carries_its_reason():
    nc = Measurement.not_collected("S3 activity failed or timed out")
    up = ScanUpstream(collected={ScanSignalId.S3: nc})
    assert up.measured(ScanSignalId.S3) is False
    gap = up.gap(ScanSignalId.S3, "input_validation")
    assert gap.state is CollectionState.NOT_COLLECTED
    assert "S3" in gap.reason and "timed out" in gap.reason


def test_an_absent_upstream_is_not_a_measured_one():
    """An upstream that never reported is not one that reported nothing."""
    assert ScanUpstream().measured(ScanSignalId.S3) is False


def test_a_measured_row_with_a_degraded_upstream_is_not_cached():
    """P3-D5: SS1 can report MEASURED (a TLS count) while input_validation is
    not_collected because S3 degraded. Caching that serves a permanently
    missing category against a healthy S3, on an unchanged tree, forever."""
    out = SignalOutput(row=_row(ScanSignalId.SS1, Measurement.measured(1.0)))
    degraded = ScanUpstream(collected={ScanSignalId.S3: Measurement.not_collected("S3 failed")})
    assert memo.store(ScanSignalId.SS1, TREE, out, degraded) is False
    assert memo.load(ScanSignalId.SS1, TREE) is None

    healthy = ScanUpstream(collected={ScanSignalId.S3: Measurement.measured(3.0)})
    assert memo.store(ScanSignalId.SS1, TREE, out, healthy) is True
    assert memo.load(ScanSignalId.SS1, TREE) is not None


def test_storing_a_consuming_signal_without_its_upstream_is_a_bug_not_a_silence():
    """Forgetting the argument would quietly reinstate the hazard, so it
    raises -- caught by the activity's own try/except in production, and by
    this test in CI."""
    out = SignalOutput(row=_row(ScanSignalId.QS2, Measurement.measured(1.0)))
    with pytest.raises(ValueError):
        memo.store(ScanSignalId.QS2, TREE, out)


def test_a_wave_one_signal_still_stores_without_an_upstream():
    out = SignalOutput(row=_row(ScanSignalId.S1, Measurement.measured(1.0)))
    assert memo.store(ScanSignalId.S1, TREE, out) is True
```

- [ ] **Step 9: Run it to make sure it fails**

Run: `pytest tests/test_scan_upstream.py -v`
Expected: FAIL with `ImportError: cannot import name 'upstream_for'`

- [ ] **Step 10: Make the registry declare the new rule modules and SS4's second input**

In `src/sdlc/assessment/scan/registry.py`, add the shared-module constant beside `_NAMING` / `_SOURCES`:

```python
# scan.testpaths, shared by S2 (exclude fixture schemas), QS1 (find tests),
# QS2 (exclude tests from significant files) and QS3 (exclude tests from
# testability findings). All four hash it, or editing a glob would move four
# signals' output while their keys stood still (P3-D9, D10).
_TESTPATHS = f"{_SIG.rsplit('.', 1)[0]}.testpaths"
```

then replace the eight affected entries:

```python
    ScanSignalId.S2: _spec(
        ScanSignalId.S2, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.schema", activity="scan_schema",
        rule_modules=(_NAMING, _SOURCES, _TESTPATHS)),
    ScanSignalId.S4: _spec(
        ScanSignalId.S4, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.frontend", activity="scan_frontend",
        rule_modules=(_NAMING,)),
    ScanSignalId.SS1: _spec(
        ScanSignalId.SS1, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.security_static", activity="scan_security_static",
        inherits=("triage:misconfig", "triage:secrets"),
        rule_modules=(_SOURCES,),
        consumes=(ScanSignalId.S3,)),
    ScanSignalId.SS3: _spec(
        ScanSignalId.SS3, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.config_infra", activity="scan_config_infra",
        inherits=("triage:misconfig",)),
    ScanSignalId.SS4: _spec(
        ScanSignalId.SS4, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.sensitivity", activity="scan_sensitivity",
        rule_modules=(_NAMING,),
        # P3-D3: accessed_by cites S3, so S3 is DECLARED. _upstream_for
        # filters on this tuple and rules_sha walks it, so an undeclared read
        # would also be an unhashed input -- the D10 hazard exactly.
        consumes=(ScanSignalId.S2, ScanSignalId.S3)),
    ScanSignalId.QS1: _spec(
        ScanSignalId.QS1, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.tests_inventory", activity="scan_tests_inventory",
        inherits=("triage:baseline",),
        rule_modules=(_SOURCES, _TESTPATHS)),
    ScanSignalId.QS2: _spec(
        ScanSignalId.QS2, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.coverage", activity="scan_coverage",
        rule_modules=(_SOURCES, _TESTPATHS),
        consumes=(ScanSignalId.QS1,)),
    ScanSignalId.QS3: _spec(
        ScanSignalId.QS3, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.testability", activity="scan_testability",
        rule_modules=(_SOURCES, _TESTPATHS)),
```

- [ ] **Step 11: Add the third memo rule**

In `src/sdlc/assessment/scan/memo.py`, import `ScanUpstream` and replace `store`:

```python
def store(
    signal_id: ScanSignalId, tree_hash: str, out: SignalOutput, upstream: ScanUpstream | None = None
) -> bool:
    """Cache `out` and report whether it was stored.

    Three rules, all of them the same rule: never serve a failure forever.

    1. ONLY a MEASURED result is stored. Memoizing a timed-out or
       uninterpretable signal returns that failure as a cache hit forever.
    2. A signal that CONSUMES another must pass that signal's `upstream`, and
       is not stored when any consumed signal did not collect (P3-D5). SS1 can
       report MEASURED -- a TLS count -- while input_validation is
       not_collected because S3 degraded; caching that serves a permanently
       missing category against a healthy S3 on an unchanged tree.
    3. Forgetting the argument raises rather than silently reinstating the
       hazard. In production the activity's own try/except turns that into a
       degraded signal; in CI it is a failing test.
    """
    consumes = SCAN_SIGNALS[signal_id].consumes
    if consumes and upstream is None:
        raise ValueError(
            f"{signal_id.value} consumes {[c.value for c in consumes]} but "
            f"store() was called without its upstream -- a consuming signal's "
            f"output is only cacheable when its inputs collected (P3-D5)"
        )
    if out.row.collected.state is not CollectionState.MEASURED:
        return False
    if upstream is not None and not all(upstream.measured(c) for c in consumes):
        return False
    cache.put(_key(signal_id, tree_hash), out.model_dump_json())
    return True
```

- [ ] **Step 12: Make the activity input carry the typed upstream**

In `src/sdlc/assessment/activities.py`, import `ScanUpstream` from `.scan.models` and replace `ScanSignalInput`:

```python
class ScanSignalInput(BaseModel):
    """One signal's activity input. `upstream` is empty for wave 1 and carries
    the DECLARED consumed signals' payloads plus their row-level `collected`
    for wave 2 (spec section 5, P3-D4)."""

    repo_dir: str
    commit_sha: str
    tree_hash: str
    upstream: ScanUpstream = Field(default_factory=ScanUpstream)
```

(`Field` is already imported from pydantic in this module; add it to the import if not.)

- [ ] **Step 13: Rename and widen `upstream_for`, and gather the new payloads**

In `src/sdlc/workflows/assessment.py`, import `ScanUpstream` alongside the other scan models and replace `_upstream_for`:

```python
def upstream_for(
    signal_id: ScanSignalId, outputs: Mapping[ScanSignalId, SignalOutput]
) -> ScanUpstream:
    """Everything one signal is allowed to read: the payloads AND the row
    states of the signals it declares in `consumes`.

    `consumes` already drives the fan-out wave (wave_of) and the memo key
    (rules_sha). Driving the payload from the SAME declaration makes reading
    undeclared data impossible rather than merely discouraged -- otherwise a
    wave-2 signal could read an S1 candidate while declaring only S3, and
    editing S1's pattern table would not move its memo key. That is the
    precise stale-cache setup D10 exists to prevent.

    `collected` travels with the payloads so a dependent signal can tell "the
    upstream measured zero" from "the upstream did not collect" (P3-D4) --
    the same pair merge() has always taken.
    """
    consumes = SCAN_SIGNALS[signal_id].consumes
    present = [c for c in consumes if c in outputs]
    return ScanUpstream(
        sources=sorted(
            (c for sid in present for c in outputs[sid].sources),
            key=lambda c: (c.signal.value, c.local_id),
        ),
        tests=sorted((t for sid in present for t in outputs[sid].tests), key=lambda t: t.path),
        collected={sid: outputs[sid].row.collected for sid in present},
    )
```

In `_scan`, the fan-out argument becomes the model, and S5's merge reads the same channel:

```python
arg = ScanSignalInput(
    repo_dir=inp.repo_dir,
    commit_sha=triage.commit_sha,
    tree_hash=tree.tree_hash,
    upstream=upstream_for(sid, outputs),
)
```

```python
        merged_upstream = upstream_for(ScanSignalId.S5, outputs)
        merged = merge(merged_upstream.sources, merged_upstream.collected)
        outputs[ScanSignalId.S5] = SignalOutput(row=_merged_row(merged))
```

and the artifact gathers all five new lists:

```python
scan = ScanResult(
    signals=rows,
    sources=sources,
    candidates=merged.candidates,
    data_sensitivity=sorted(
        (r for out in outputs.values() for r in out.data_sensitivity),
        key=lambda r: (r.classification.value, r.entity),
    ),
    testability=sorted(
        (f for out in outputs.values() for f in out.testability),
        key=lambda f: (f.path, f.pattern, f.key),
    ),
    security=sorted(
        (o for out in outputs.values() for o in out.security),
        key=lambda o: (o.signal.value, o.category, o.path, o.rule, o.line or 0),
    ),
    tests=sorted((t for out in outputs.values() for t in out.tests), key=lambda t: t.path),
    coverage=sorted(
        (c for out in outputs.values() for c in out.coverage), key=lambda c: (c.scope, c.path)
    ),
    ci=sorted(
        (c for out in outputs.values() for c in out.ci),
        key=lambda c: (c.workflow, c.order, c.stage),
    ),
    environments=sorted(
        (e for out in outputs.values() for e in out.environments), key=lambda e: e.name
    ),
)
```

- [ ] **Step 14: Update the two tests that named the private helper**

In `tests/test_assessment_scan_phase.py`, change the import to `upstream_for` and adjust the two assertions to read `.sources`:

```python
from sdlc.workflows.assessment import (
    ScanOutcome,
    _collected_from_categories,
    _inherited_row,
    fold_row,
    skipped_scan_signal,
    upstream_for,
)
```

```python
# SS1 consumes only S3.
assert [c.local_id for c in upstream_for(ScanSignalId.SS1, outputs).sources] == ["S3-pay"]
# SS4 consumes S2 and S3 (P3-D3).
assert [c.local_id for c in upstream_for(ScanSignalId.SS4, outputs).sources] == [
    "S2-orders",
    "S3-pay",
]
```

```python
def test_upstream_for_a_wave_one_signal_is_empty():
    outputs = {
        ScanSignalId.S1: SignalOutput(
            row=_measured_row(ScanSignalId.S1), sources=[_candidate(ScanSignalId.S1, "S1-pay")]
        )
    }
    up = upstream_for(ScanSignalId.S3, outputs)
    assert up.sources == [] and up.tests == [] and up.collected == {}
```

In `tests/test_scan_stub_activities.py`, make the payload check generic so it covers the five new fields without a per-field edit:

```python
@pytest.mark.parametrize("sid", _stub_signals(), ids=lambda s: s.value)
def test_stub_carries_no_records(sid):
    """Generic over SignalOutput's payload fields: a new payload type added
    in a later plan is covered without editing this test."""
    out = scan_acts.unbuilt_signal(sid)
    for name in (f for f in type(out).model_fields if f != "row"):
        assert getattr(out, name) == [], name
```

- [ ] **Step 15: Run the whole scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS (the stubs still report `not_collected`; nothing produces a new payload yet).

- [ ] **Step 16: Commit**

```bash
git add src/sdlc/assessment/scan/models.py src/sdlc/assessment/scan/testpaths.py \
        src/sdlc/assessment/scan/registry.py src/sdlc/assessment/scan/memo.py \
        src/sdlc/assessment/activities.py src/sdlc/workflows/assessment.py \
        tests/test_scan_testpaths.py tests/test_scan_upstream.py \
        tests/test_scan_payloads.py tests/test_scan_stub_activities.py \
        tests/test_assessment_scan_phase.py
git commit -m "feat(scan): payload contracts, typed upstream and the shared test-path rules (E-46 plan 3)"
```

---

### Task 2: S2 — database schema clusters

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/schema.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_schema` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_s2_schema.py` (create)
- Test: `tests/test_scan_activities_s1_s3.py` (drop the two-signals-only assertion)

**Interfaces:**
- Consumes: `naming.head_token`, `naming.normalize` (Task 1 of plan 2), `testpaths.is_test_path` (Task 1).
- Produces: `EXTRA_EXTENSIONS: tuple[str, ...]`, `TableDecl` (name/rule/path/line/fields), `declarations(blobs) -> list[TableDecl]`, `evaluate(blobs) -> SignalOutput`. **Task 4 (SS4) imports `TableDecl` and `declarations`** — one extractor, two readers (FR-902), and safe for the memo because SS4 declares `consumes=(S2, …)`, so `rules_sha` already hashes this module's bytes into SS4's key.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_s2_schema.py`:

```python
"""S2: tables, FK edges and the clusters they form. BrownKit clusters "by FK
connectivity + naming"; both halves are here, and the naming half is
naming.normalize so S5 can merge an S2 cluster with the S1 package and the S3
controller that share its name."""

from __future__ import annotations

from sdlc.assessment.scan.models import MemberKind, ScanSignalId
from sdlc.assessment.scan.signals import schema
from sdlc.measurement import CollectionState

SQL = {
    "migrations/0001_orders.sql": (
        "CREATE TABLE orders (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  customer_id INTEGER NOT NULL REFERENCES customers(id),\n"
        "  total NUMERIC(10,2)\n"
        ");\n"
        "CREATE TABLE order_items (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  order_id INTEGER NOT NULL REFERENCES orders(id)\n"
        ");\n"
    ),
    "migrations/0002_customers.sql": (
        "CREATE TABLE customers (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  email VARCHAR(255) NOT NULL,\n"
        "  phone VARCHAR(32)\n"
        ");\n"
    ),
}


def test_tables_are_declared_with_their_fields():
    decls = schema.declarations(SQL)
    by_name = {d.name: d for d in decls}
    assert set(by_name) == {"orders", "order_items", "customers"}
    assert "email" in by_name["customers"].fields
    assert by_name["orders"].rule == "s2_sql_create_table"
    assert by_name["orders"].path == "migrations/0001_orders.sql"


def test_orders_and_order_items_cluster_on_the_head_token():
    """'orders' + 'order_items' + 'order_events' is ONE candidate. The head
    token is what those names actually agree on, which is why S3 groups on it
    too (D9's worked example, one signal over)."""
    out = schema.evaluate(SQL)
    ids = {c.local_id for c in out.sources}
    assert "S2-order" in ids
    order = next(c for c in out.sources if c.local_id == "S2-order")
    tables = {m.value for m in order.members if m.kind is MemberKind.DB_TABLE}
    assert tables == {"orders", "order_items"}


def test_a_foreign_key_raises_the_contribution_and_is_counted():
    out = schema.evaluate(SQL)
    order = next(c for c in out.sources if c.local_id == "S2-order")
    assert order.metrics[schema.M_FK_EDGES].state is CollectionState.MEASURED
    assert order.metrics[schema.M_FK_EDGES].value >= 1.0
    assert order.confidence_contribution.value == "high"


def test_a_singleton_table_is_low_and_still_reported():
    out = schema.evaluate(SQL)
    customers = next(c for c in out.sources if c.local_id == "S2-customer")
    assert customers.confidence_contribution.value in {"low", "medium"}


def test_a_foreign_key_does_not_merge_two_named_clusters():
    """P3-D13: orders REFERENCES customers, and union-find over that would
    collapse a normalized schema into one component -- every table reaches
    every other one eventually. Naming clusters; the FK corroborates."""
    out = schema.evaluate(SQL)
    assert {c.local_id for c in out.sources} == {"S2-order", "S2-customer"}
    order = next(c for c in out.sources if c.local_id == "S2-order")
    assert "customers" not in {m.value for m in order.members}


def test_orm_models_are_declarations_too():
    blobs = {
        "app/models/payment.py": (
            "from sqlalchemy import Column, ForeignKey, Integer, String\n"
            "class Payment(Base):\n"
            "    __tablename__ = 'payments'\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    card_last4 = Column(String(4))\n"
            "    order_id = Column(Integer, ForeignKey('orders.id'))\n"
        )
    }
    decls = schema.declarations(blobs)
    assert [d.name for d in decls] == ["payments"]
    assert "card_last4" in decls[0].fields
    out = schema.evaluate(blobs)
    assert any(c.local_id == "S2-payment" for c in out.sources)


def test_a_prisma_schema_is_parsed():
    blobs = {
        "prisma/schema.prisma": (
            "model User {\n"
            "  id    Int     @id @default(autoincrement())\n"
            "  email String  @unique\n"
            "  posts Post[]\n"
            "}\n"
            "model Post {\n"
            "  id       Int  @id\n"
            "  author   User @relation(fields: [authorId], references: [id])\n"
            "  authorId Int\n"
            "}\n"
        )
    }
    decls = schema.declarations(blobs)
    assert {d.name for d in decls} == {"User", "Post"}
    assert "email" in dict((d.name, d.fields) for d in decls)["User"]


def test_a_repository_with_no_schema_is_a_gap_not_a_zero():
    """D5: an ORM we cannot fingerprint looks exactly like an application with
    no database, and only one of those is safe to assert."""
    out = schema.evaluate({"src/app.py": "print('hello')\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.sources == []
    assert "not a repository with no schema" in out.row.collected.reason


def test_a_fixture_schema_under_tests_is_not_a_capability():
    """P3-D9: a CREATE TABLE inside a test fixture describes the test, not the
    product."""
    out = schema.evaluate({"tests/fixtures/seed.sql": "CREATE TABLE widgets (id INT);\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED


def test_output_is_byte_identical_across_input_orderings():
    reference = schema.evaluate(SQL).model_dump_json()
    reversed_blobs = dict(reversed(list(SQL.items())))
    assert schema.evaluate(reversed_blobs).model_dump_json() == reference
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_s2_schema.py -v`
Expected: FAIL with `AttributeError: module 'sdlc.assessment.scan.signals.schema' has no attribute 'declarations'`

- [ ] **Step 3: Write `scan/signals/schema.py`**

```python
"""S2 -- database schema clusters (FR-912).

Tables, foreign-key references, and the clusters they form. BrownKit clusters
"by FK connectivity + naming"; here NAMING clusters and FK CORROBORATES
(P3-D13), because union-find over foreign keys collapses a normalized schema
into one component and would emit a single "capability" covering the whole
database. The naming half is naming.normalize, so S5 can merge an S2 cluster
with the S1 package and the S3 controller that share its name -- which is what
finally lets a candidate reach HIGH (three distinct sources, D8).

D5 applies exactly as it does to S3: a repository with no parseable schema is
NOT a repository with no schema. An ORM we cannot fingerprint looks precisely
like an application with no database, and only one of those is safe to assert.

Also the home of `declarations()`, which SS4 reads: one extractor, two
consumers (FR-902's one-implementation rule, applied inside the phase). Safe
for the memo because SS4 declares `consumes=(S2, S3)` and rules_sha walks
`consumes` transitively, so this module's bytes are already hashed into SS4's
key.

Pure: blobs in, records out. The activity reads the tree.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_SCHEMA,
    CandidateMember,
    Confidence,
    EvidenceRef,
    MemberKind,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
from ..naming import head_token, normalize
from ..testpaths import is_test_path

SIGNAL_ID = "S2"
VERSION = 1

M_FK_EDGES = "fk_edges"
M_TABLES = "tables"

# Extensions the S1/S3 source list does not carry but a schema lives in.
EXTRA_EXTENSIONS: tuple[str, ...] = (".sql", ".prisma")

# How far past a declaration its field block is read. Bounded so a
# mis-detected declaration costs a few lines, not a whole file.
_FIELD_WINDOW = 120
_BLOCK_END = re.compile(r"^[ \t]*[)}][ \t]*;?[ \t]*$")

# (rule, origin, pattern). Group 1 is the declared name. `origin` is what
# SS4's SensitivityRecord records, which is why it is declared beside the
# pattern rather than guessed from the path.
_DECL_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "s2_sql_create_table",
        "table",
        re.compile(
            r"(?im)^[ \t]*create\s+table\s+(?:if\s+not\s+exists\s+)?"
            r"[`\"\[]?(?:[a-z_][a-z0-9_]*\.)?([a-z_][a-z0-9_]*)[`\"\]]?"
        ),
    ),
    ("s2_prisma_model", "table", re.compile(r"(?m)^[ \t]*model[ \t]+([A-Za-z_]\w*)[ \t]*\{")),
    (
        "s2_sqlalchemy_tablename",
        "model",
        re.compile(r"""(?m)^[ \t]*__tablename__\s*=\s*['"]([A-Za-z_]\w*)['"]"""),
    ),
    (
        "s2_django_model",
        "model",
        re.compile(r"(?m)^[ \t]*class[ \t]+([A-Za-z_]\w*)\s*\([^)]*\bModel\b"),
    ),
    (
        "s2_typeorm_entity",
        "model",
        re.compile(r"(?m)^[ \t]*@Entity\([^)]*\)[\s\S]{0,200}?class[ \t]+([A-Za-z_]\w*)"),
    ),
)

# Group 1 is the REFERENCED table/model.
_FK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)references\s+[`\"\[]?(?:[a-z_][a-z0-9_]*\.)?"
        r"([a-z_][a-z0-9_]*)"
    ),
    re.compile(r"""ForeignKey\(\s*['"]([A-Za-z_]\w*)\."""),
    re.compile(
        r"""(?:ForeignKey|OneToOneField|ManyToManyField)\("""
        r"""\s*['"]?([A-Za-z_]\w*)"""
    ),
    re.compile(
        r"(?m)^[ \t]*\w+[ \t]+([A-Za-z_]\w*)(?:\[\])?\??[ \t]+"
        r"@relation\b"
    ),
)

_FIELD_PATTERNS: tuple[re.Pattern[str], ...] = (
    # SQL column inside a CREATE TABLE body.
    re.compile(
        r"""^[ \t]*[`"\[]?([a-z_][a-z0-9_]*)[`"\]]?[ \t]+"""
        r"(?:varchar|char|text|int|integer|bigint|smallint|serial|"
        r"numeric|decimal|float|double|real|bool|boolean|date|"
        r"timestamptz|timestamp|time|uuid|jsonb|json|bytea|blob)\b",
        re.IGNORECASE,
    ),
    # ORM attribute.
    re.compile(
        r"^[ \t]*([A-Za-z_]\w*)\s*=\s*(?:models\.|db\.|sa\.)?"
        r"(?:Column|mapped_column|CharField|TextField|IntegerField|"
        r"BooleanField|DateTimeField|DateField|DecimalField|"
        r"FloatField|EmailField|UUIDField|JSONField)\b"
    ),
    # Prisma / TypeORM typed field.
    re.compile(
        r"^[ \t]*([A-Za-z_]\w*)\??[ \t:]+(?:String|Int|BigInt|Float|"
        r"Decimal|Boolean|DateTime|Json|Bytes|string|number|boolean|"
        r"Date)\b"
    ),
)


class TableDecl(BaseModel):
    """One declared table or entity, and where it was declared."""

    model_config = {"frozen": True}
    name: str
    rule: str
    origin: str  # "table" | "model" -- SS4 records it
    path: str
    line: int
    fields: tuple[str, ...] = ()


def _block(lines: list[str], start: int, starts: set[int]) -> list[str]:
    """A declaration's body: the lines after `start` up to the first block
    terminator, the next declaration, or _FIELD_WINDOW -- whichever comes
    first."""
    out: list[str] = []
    for index in range(start + 1, min(len(lines), start + 1 + _FIELD_WINDOW)):
        if index in starts or _BLOCK_END.match(lines[index]):
            break
        out.append(lines[index])
    return out


def _fields(block: list[str]) -> tuple[str, ...]:
    """Field names in declaration order, de-duplicated. Order is preserved
    rather than sorted because a column order is a fact about the schema and
    SS4 quotes these back."""
    out: list[str] = []
    for line in block:
        for pattern in _FIELD_PATTERNS:
            match = pattern.match(line)
            if match and match.group(1) not in out:
                out.append(match.group(1))
                break
    return tuple(out)


def declarations(blobs: Mapping[str, str]) -> list[TableDecl]:
    """Every table/entity declared in `blobs`, sorted by (path, line).

    Test paths are skipped: a CREATE TABLE inside a fixture describes the
    test, not the product (P3-D9).
    """
    out: list[TableDecl] = []
    for path in sorted(blobs):
        if is_test_path(path):
            continue
        text = blobs[path]
        lines = text.splitlines()
        found: list[tuple[int, str, str, str]] = []  # (line, name, rule, origin)
        for rule, origin, pattern in _DECL_PATTERNS:
            for match in pattern.finditer(text):
                lineno = text.count("\n", 0, match.start())
                found.append((lineno, match.group(1), rule, origin))
        starts = {lineno for lineno, _, _, _ in found}
        for lineno, name, rule, origin in sorted(found):
            out.append(
                TableDecl(
                    name=name,
                    rule=rule,
                    origin=origin,
                    path=path,
                    line=lineno + 1,
                    fields=_fields(_block(lines, lineno, starts)),
                )
            )
    return sorted(out, key=lambda d: (d.path, d.line, d.name))


def _cluster_key(name: str) -> str:
    """The key two tables must share to cluster by NAME. head_token before
    normalize, so 'order_items' and 'orders' both reach 'order' -- the same
    reduction S3 applies to PaymentSettlementJob (D9)."""
    return normalize(head_token(name)) or name.strip().lower()


def _fk_targets(text: str) -> set[str]:
    return {m.group(1) for pattern in _FK_PATTERNS for m in pattern.finditer(text)}


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S2,
            family=family_of(ScanSignalId.S2),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=nc,
            categories={C_SCHEMA: nc},
        )
    )


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound blob whose
    extension is a source or schema extension."""
    decls = declarations(blobs)
    if not decls:
        return _gap(
            f"schema_clusters: no table or entity declaration matched any of "
            f"{sorted(rule for rule, _, _ in _DECL_PATTERNS)}; a repository "
            f"with no parseable schema is not a repository with no schema "
            f"(D5)"
        )

    clusters: dict[str, list[TableDecl]] = {}
    for decl in decls:
        clusters.setdefault(_cluster_key(decl.name), []).append(decl)

    candidates: list[SourceCandidate] = []
    for root in sorted(clusters):
        group = sorted(clusters[root], key=lambda d: (d.name, d.path))
        names = sorted({d.name for d in group})
        # P3-D13: FK references CORROBORATE a cluster, they do not merge one.
        # Counted over the files this cluster's tables are declared in, which
        # is as precise as a signal that does not parse blocks can be.
        cluster_edges = sum(
            len(_fk_targets(blobs[path])) for path in sorted({d.path for d in group})
        )
        if cluster_edges and len(names) > 1:
            contribution = Confidence.HIGH
            detail = (
                f"{len(names)} table(s) sharing the stem {root!r}, "
                f"declared alongside {cluster_edges} foreign-key "
                f"reference(s)."
            )
        elif len(names) > 1:
            contribution = Confidence.MEDIUM
            detail = (
                f"{len(names)} table(s) sharing the stem {root!r}; no "
                f"foreign key is declared beside them."
            )
        else:
            contribution = Confidence.LOW
            detail = f"one table, {names[0]!r}, and no other table shares its name stem."
        candidates.append(
            SourceCandidate(
                signal=ScanSignalId.S2,
                local_id=f"S2-{root}",
                name=min(names, key=lambda n: (len(n), n)),
                rule="s2_schema_cluster",
                detail=detail,
                confidence_contribution=contribution,
                members=[
                    CandidateMember(
                        kind=MemberKind.DB_TABLE,
                        value=n,
                        path=next(d.path for d in group if d.name == n),
                    )
                    for n in names
                ],
                evidence=[EvidenceRef(path=d.path, lines=str(d.line)) for d in group],
                metrics={
                    M_TABLES: Measurement.measured(float(len(names))),
                    M_FK_EDGES: Measurement.measured(float(cluster_edges)),
                },
            )
        )

    candidates.sort(key=lambda c: c.local_id)
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S2,
            family=family_of(ScanSignalId.S2),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={C_SCHEMA: collected},
        ),
        sources=candidates,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_s2_schema.py -v`
Expected: PASS

- [ ] **Step 5: Give S2 a real activity body**

In `src/sdlc/assessment/activities.py`, import `schema` from `.scan.signals`, move `S2` from `OWED_BY` into `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_schema(inp: ScanSignalInput) -> SignalOutput:
    """S2 -- database schema clusters.

    Reads the source extensions S1/S3 read plus schema.EXTRA_EXTENSIONS: a
    .sql or .prisma file is not source code, but it is where a schema is
    declared.
    """
    if (hit := memo.load(ScanSignalId.S2, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(
            inp.repo_dir, inp.commit_sha, paths, SOURCE_EXTENSIONS + schema.EXTRA_EXTENSIONS
        )
        out = schema.evaluate(blobs)
    except Exception as exc:  # noqa: BLE001
        _log.warning("S2 failed: %s", exc)
        return failed_signal(ScanSignalId.S2, exc)
    memo.store(ScanSignalId.S2, inp.tree_hash, out)
    return out
```

- [ ] **Step 6: Retire the two-signals-only assertion**

In `tests/test_scan_activities_s1_s3.py`, delete `test_the_two_built_signals_are_s1_and_s3` (it pins a plan-2 fact that every task in this plan invalidates) and replace it with the invariant that survives:

```python
def test_a_built_signal_is_never_still_owed():
    """The partition test above says BUILT | OWED_BY covers the declared
    activities; this says the two never overlap as bodies land one per task."""
    assert not (acts.BUILT & set(acts.OWED_BY))
    assert acts.BUILT, "at least S1 and S3 have landed"
```

- [ ] **Step 7: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/assessment/scan/signals/schema.py src/sdlc/assessment/activities.py \
        tests/test_scan_s2_schema.py tests/test_scan_activities_s1_s3.py
git commit -m "feat(scan): S2 schema clusters -- tables, FK edges, name-stem grouping (E-46 plan 3)"
```

---

### Task 3: S4 — frontend entry points

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/frontend.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_frontend` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_s4_frontend.py` (create)

**Interfaces:**
- Consumes: `naming.head_token`, `naming.normalize`.
- Produces: `FRONTEND_EXTENSIONS: tuple[str, ...]`, `evaluate(blobs) -> SignalOutput`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_s4_frontend.py`:

```python
"""S4: routes as the user meets them. BrownKit groups by user journey, not by
component hierarchy -- so /payments, /payments/:id and /payments/new are ONE
candidate."""

from __future__ import annotations

from sdlc.assessment.scan.models import MemberKind
from sdlc.assessment.scan.signals import frontend
from sdlc.measurement import CollectionState

NEXT_APP = {
    "package.json": '{"dependencies": {"next": "14.2.0", "react": "18.2.0"}}',
    "app/payments/page.tsx": "export default function Page() { return null }\n",
    "app/payments/[id]/page.tsx": "export default function Page() { return null }\n",
    "app/(marketing)/about/page.tsx": "export default function Page() {}\n",
    "app/layout.tsx": "export default function Layout() {}\n",
}


def test_next_app_router_pages_become_routes():
    out = frontend.evaluate(NEXT_APP)
    routes = {
        m.value for c in out.sources for m in c.members if m.kind is MemberKind.FRONTEND_ROUTE
    }
    assert "/payments" in routes
    assert "/payments/:id" in routes
    # A route group is a layout device, not a URL segment.
    assert "/about" in routes
    # layout.tsx is not a route.
    assert not any(r.endswith("layout") for r in routes)


def test_a_journey_is_one_candidate_not_one_per_route():
    out = frontend.evaluate(NEXT_APP)
    payments = next(c for c in out.sources if c.local_id == "S4-payment")
    values = {m.value for m in payments.members}
    assert values == {"/payments", "/payments/:id"}


def test_react_router_config_routes_are_extracted():
    blobs = {
        "package.json": '{"dependencies": {"react-router-dom": "6.22.0"}}',
        "src/routes.tsx": (
            "export const router = createBrowserRouter([\n"
            "  { path: '/orders', element: <Orders /> },\n"
            "  { path: '/orders/:id', element: <Order /> },\n"
            "]);\n"
        ),
    }
    out = frontend.evaluate(blobs)
    assert out.row.collected.state is CollectionState.MEASURED
    orders = next(c for c in out.sources if c.local_id == "S4-order")
    assert {m.value for m in orders.members} == {"/orders", "/orders/:id"}


def test_a_repository_with_no_frontend_is_a_gap_not_a_zero():
    """BrownKit's own adaptation: has_frontend=false is recorded as
    not-collected with a reason, never as an empty route list (D5)."""
    out = frontend.evaluate({"src/app.py": "print('hi')\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.sources == []
    assert "no frontend framework" in out.row.collected.reason


def test_an_unfingerprinted_frontend_framework_fails_closed():
    """P2-D1, one signal over: extracting only what we recognise would hand a
    partial route set downstream while looking complete."""
    blobs = {
        "package.json": '{"dependencies": {"@angular/core": "17.0.0"}}',
        "src/app/app.component.ts": "export class AppComponent {}\n",
    }
    out = frontend.evaluate(blobs)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "angular" in out.row.collected.reason
    assert out.sources == []


def test_sveltekit_routes_are_extracted():
    blobs = {
        "package.json": '{"devDependencies": {"@sveltejs/kit": "2.0.0"}}',
        "src/routes/orders/+page.svelte": "<h1>Orders</h1>\n",
        "src/routes/orders/[id]/+page.svelte": "<h1>Order</h1>\n",
    }
    out = frontend.evaluate(blobs)
    orders = next(c for c in out.sources if c.local_id == "S4-order")
    assert {m.value for m in orders.members} == {"/orders", "/orders/:id"}


def test_output_is_byte_identical_across_input_orderings():
    reference = frontend.evaluate(NEXT_APP).model_dump_json()
    reordered = dict(reversed(list(NEXT_APP.items())))
    assert frontend.evaluate(reordered).model_dump_json() == reference
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_s4_frontend.py -v`
Expected: FAIL with `AttributeError: module … has no attribute 'evaluate'`

- [ ] **Step 3: Write `scan/signals/frontend.py`**

```python
"""S4 -- frontend entry points (FR-912).

BrownKit's rule is that routes are grouped "by user journey, not by component
hierarchy": /payments, /payments/:id and /payments/new are ONE candidate. That
is the same reduction S3 applies to PaymentController + PaymentSettlementJob,
so it uses the same normalizer (D9, naming.py).

Two extraction shapes, because frameworks split that way:
  * FILE CONVENTION -- Next.js app/ and pages/, SvelteKit src/routes/, Nuxt
    pages/. The path IS the route.
  * CONFIGURED ROUTES -- React Router / Vue Router objects, where a literal
    `path:` or `path=` carries it.

FAIL-CLOSED on a recognized-but-unfingerprinted framework, exactly as S3 is
(P2-D1): extracting only what we recognise would hand a partial route set
downstream while looking complete.

Pure: blobs in, records out.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_FRONTEND_ENTRY,
    CandidateMember,
    Confidence,
    EvidenceRef,
    MemberKind,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
from ..naming import head_token, normalize

SIGNAL_ID = "S4"
VERSION = 1

FRONTEND_EXTENSIONS: tuple[str, ...] = (
    ".tsx",
    ".jsx",
    ".ts",
    ".js",
    ".vue",
    ".svelte",
    ".json",
)

# A dependency name in a package.json is the honest detector: a framework a
# repository DEPENDS on is one it uses, while an import in one file may be a
# comment or a fixture (S3's review finding 4, one signal over).
_DEP = r'"{m}"\s*:'

SUPPORTED_DEPS: tuple[tuple[str, str], ...] = (
    ("next", _DEP.format(m="next")),
    ("sveltekit", _DEP.format(m=r"@sveltejs/kit")),
    ("nuxt", _DEP.format(m="nuxt")),
    ("react_router", _DEP.format(m=r"react-router(?:-dom)?")),
    ("vue_router", _DEP.format(m=r"vue-router")),
)

UNSUPPORTED_DEPS: tuple[tuple[str, str], ...] = (
    ("angular", _DEP.format(m=r"@angular/core")),
    ("ember", _DEP.format(m=r"ember-source")),
    ("remix", _DEP.format(m=r"@remix-run/react")),
    ("solid_start", _DEP.format(m=r"@solidjs/start")),
)

# (framework, path regex, the group holding the route-bearing path segment)
_FILE_ROUTES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("next", re.compile(r"^(?:src/)?app/(.*/)?page\.(?:tsx|jsx|ts|js)$")),
    (
        "next",
        re.compile(
            r"^(?:src/)?pages/(?!api/)(?!_(?:app|document|error))(.*)"
            r"\.(?:tsx|jsx|ts|js)$"
        ),
    ),
    ("sveltekit", re.compile(r"^(?:src/)?routes/(.*/)?\+page\.svelte$")),
    ("nuxt", re.compile(r"^(?:src/)?pages/(.*)\.vue$")),
)

# A literal route in a router config. Both shapes in one table because a Vue
# route object and a React Router object are the same literal.
_CONFIG_ROUTES: tuple[re.Pattern[str], ...] = (
    re.compile(r"""<Route\b[^>]*\bpath\s*=\s*['"]([^'"]+)['"]"""),
    re.compile(r"""\bpath\s*:\s*['"]([^'"]+)['"]"""),
)

# Segments that prefix a route rather than name a journey.
_PATH_PREFIXES: frozenset[str] = frozenset(
    {
        "app",
        "pages",
        "routes",
        "src",
        "_next",
        "public",
    }
)


class _Route(BaseModel):
    model_config = {"frozen": True}
    value: str
    path: str
    line: int | None = None


def _url_from_path(captured: str) -> str:
    """A file-convention route from the captured path fragment.

    Route groups -- Next's `(marketing)`, SvelteKit's `(app)` -- are layout
    devices and carry no URL segment. Dynamic segments become `:name` so a
    route reads the same whichever framework wrote it, and a catch-all
    becomes `*`.
    """
    segments: list[str] = []
    for raw in captured.strip("/").split("/"):
        if not raw or raw == "index":
            continue
        if raw.startswith("(") and raw.endswith(")"):
            continue
        if raw.startswith("[...") or raw.startswith("[[..."):
            segments.append("*")
            continue
        if raw.startswith("[") and raw.endswith("]"):
            segments.append(f":{raw.strip('[]')}")
            continue
        segments.append(raw)
    return "/" + "/".join(segments)


def detected(blobs: Mapping[str, str]) -> tuple[set[str], set[str]]:
    """(supported, unsupported) frontend frameworks the repository DEPENDS
    on, read from every package.json in the tree."""
    manifests = "\n".join(
        blobs[p] for p in sorted(blobs) if posixpath.basename(p) == "package.json"
    )
    supported = {name for name, pattern in SUPPORTED_DEPS if re.search(pattern, manifests)}
    unsupported = {name for name, pattern in UNSUPPORTED_DEPS if re.search(pattern, manifests)}
    return supported, unsupported


def _file_routes(blobs: Mapping[str, str], active: set[str]) -> list[_Route]:
    out: list[_Route] = []
    for path in sorted(blobs):
        for framework, pattern in _FILE_ROUTES:
            if framework not in active:
                continue
            match = pattern.match(path)
            if match:
                out.append(_Route(value=_url_from_path(match.group(1) or ""), path=path))
                break
    return out


def _config_routes(blobs: Mapping[str, str]) -> list[_Route]:
    out: list[_Route] = []
    for path in sorted(blobs):
        if posixpath.basename(path) == "package.json":
            continue
        text = blobs[path]
        for pattern in _CONFIG_ROUTES:
            for match in pattern.finditer(text):
                raw = match.group(1).strip()
                if not raw.startswith("/"):
                    continue
                out.append(
                    _Route(
                        value=re.sub(r"\*+$", "*", raw),
                        path=path,
                        line=text.count("\n", 0, match.start()) + 1,
                    )
                )
    return out


def _journey(route: _Route) -> str:
    """The journey a route belongs to: its first non-parameter, non-prefix
    segment, falling back to the head token of its file's parent directory."""
    for segment in route.value.strip("/").split("/"):
        if not segment or segment[0] in ":*":
            continue
        if segment.lower() in _PATH_PREFIXES:
            continue
        return segment
    parent = posixpath.basename(posixpath.dirname(route.path))
    return head_token(parent) if parent else "root"


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S4,
            family=family_of(ScanSignalId.S4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=nc,
            categories={C_FRONTEND_ENTRY: nc},
        )
    )


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound frontend blob."""
    supported, unsupported = detected(blobs)
    if unsupported:
        return _gap(
            f"frontend_entry_points: detected framework(s) "
            f"{sorted(unsupported)} have no fingerprint here; extracting only "
            f"{sorted(supported)} would hand a partial route set downstream "
            f"while looking complete (D5, P2-D1)"
        )
    if not supported:
        return _gap(
            "frontend_entry_points: no frontend framework in any package.json "
            "dependency list -- BrownKit's has_frontend=false adaptation, "
            "recorded as a gap rather than as an empty route list (D5)"
        )

    routes = _file_routes(blobs, supported) + _config_routes(blobs)
    if not routes:
        return _gap(
            f"frontend_entry_points: {sorted(supported)} is declared, but no "
            f"route matched a file convention or a literal router path -- a "
            f"framework whose routes we cannot read is not a framework with "
            f"no routes (D5)"
        )

    grouped: dict[str, list[_Route]] = {}
    for route in routes:
        name = _journey(route)
        grouped.setdefault(normalize(name) or name.lower(), []).append(route)

    candidates: list[SourceCandidate] = []
    for key, group in sorted(grouped.items()):
        members = [
            CandidateMember(kind=MemberKind.FRONTEND_ROUTE, value=r.value, path=r.path, line=r.line)
            for r in group
        ]
        candidates.append(
            SourceCandidate(
                signal=ScanSignalId.S4,
                local_id=f"S4-{key}",
                name=key,
                rule="s4_route_journey",
                detail=f"{len(members)} route(s) grouped by user journey, not by "
                f"component hierarchy.",
                confidence_contribution=(
                    Confidence.HIGH
                    if len(members) > 2
                    else Confidence.MEDIUM
                    if len(members) > 1
                    else Confidence.LOW
                ),
                members=members,
                evidence=[
                    EvidenceRef(path=r.path, lines=str(r.line) if r.line else "") for r in group
                ],
            )
        )

    candidates.sort(key=lambda c: c.local_id)
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S4,
            family=family_of(ScanSignalId.S4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={C_FRONTEND_ENTRY: collected},
        ),
        sources=candidates,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_s4_frontend.py -v`
Expected: PASS

- [ ] **Step 5: Give S4 a real activity body**

In `src/sdlc/assessment/activities.py`, import `frontend`, move `S4` from `OWED_BY` to `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_frontend(inp: ScanSignalInput) -> SignalOutput:
    """S4 -- frontend entry points. Reads package.json too: a dependency list
    is the honest framework detector (an import can be a comment)."""
    if (hit := memo.load(ScanSignalId.S4, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(inp.repo_dir, inp.commit_sha, paths, frontend.FRONTEND_EXTENSIONS)
        out = frontend.evaluate(blobs)
    except Exception as exc:  # noqa: BLE001
        _log.warning("S4 failed: %s", exc)
        return failed_signal(ScanSignalId.S4, exc)
    memo.store(ScanSignalId.S4, inp.tree_hash, out)
    return out
```

- [ ] **Step 6: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/signals/frontend.py src/sdlc/assessment/activities.py \
        tests/test_scan_s4_frontend.py
git commit -m "feat(scan): S4 frontend routes grouped by journey, fail-closed on an unfingerprinted framework (E-46 plan 3)"
```

---

### Task 4: SS4 — data sensitivity

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/sensitivity.py`
- Modify: `src/sdlc/assessment/scan/models.py` (SS4 gains a second category — **P3-D12**)
- Modify: `src/sdlc/assessment/activities.py` (`scan_sensitivity` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_ss4_sensitivity.py` (create)

**Interfaces:**
- Consumes: `schema.declarations` / `schema.TableDecl` (Task 2), `ScanUpstream` (Task 1), `naming.normalize`.
- Produces: `evaluate(blobs, upstream) -> SignalOutput`, `C_ENTITY_ACCESS = "entity_access"` (in `models.py`).

**P3-D12 — SS4 owns two categories, not one.** The spec says a missing S3 must not make SS4 read as *"no entry point touches PII"*, but SS4 as declared owns one category, so an empty `accessed_by` on every record would have nowhere to say why. Splitting the signal's coverage into `data_sensitivity` (the classification, which needs only S2 and the tree) and `entity_access` (which entry points touch the entity, which needs S3) is exactly what D3's per-category tracking exists for — the same shape SS1 already has. S2 missing still fails the whole signal, because without the table set the classification itself is partial.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_ss4_sensitivity.py`:

```python
"""SS4: which entities hold regulated data, and which entry points touch
them. The classification is the answer E-49 scores per capability."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_DATA_SENSITIVITY,
    C_ENTITY_ACCESS,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanUpstream,
    Sensitivity,
    SourceCandidate,
)
from sdlc.assessment.scan.signals import sensitivity
from sdlc.measurement import CollectionState, Measurement

BLOBS = {
    "migrations/0001_customers.sql": (
        "CREATE TABLE customers (\n"
        "  id SERIAL PRIMARY KEY,\n"
        "  email VARCHAR(255),\n"
        "  phone VARCHAR(32),\n"
        "  password_hash VARCHAR(128)\n"
        ");\n"
    ),
    "app/models/payment.py": (
        "class Payment(Base):\n"
        "    __tablename__ = 'payments'\n"
        "    card_last4 = Column(String(4))\n"
        "    amount = Column(Numeric)\n"
    ),
}


def _upstream(s2_ok=True, s3_ok=True) -> ScanUpstream:
    sources = []
    collected = {}
    if s2_ok:
        collected[ScanSignalId.S2] = Measurement.measured(2.0)
        sources.append(
            SourceCandidate(
                signal=ScanSignalId.S2,
                local_id="S2-customer",
                name="customers",
                rule="s2_schema_cluster",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[CandidateMember(kind=MemberKind.DB_TABLE, value="customers")],
            )
        )
    else:
        collected[ScanSignalId.S2] = Measurement.not_collected("S2 failed")
    if s3_ok:
        collected[ScanSignalId.S3] = Measurement.measured(1.0)
        sources.append(
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-customer",
                name="customer",
                rule="s3_http_route",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[CandidateMember(kind=MemberKind.HTTP_ROUTE, value="GET /api/customers")],
            )
        )
    else:
        collected[ScanSignalId.S3] = Measurement.not_collected("S3 failed")
    return ScanUpstream(sources=sources, collected=collected)


def test_pii_and_authentication_are_distinct_classifications():
    out = sensitivity.evaluate(BLOBS, _upstream())
    by_class = {(r.classification, r.entity) for r in out.data_sensitivity}
    assert (Sensitivity.PII, "customers") in by_class
    assert (Sensitivity.AUTHENTICATION, "customers") in by_class
    pii = next(r for r in out.data_sensitivity if r.classification is Sensitivity.PII)
    assert set(pii.fields) == {"email", "phone"}
    assert pii.origin == "table"


def test_a_financial_model_is_classified_from_its_fields():
    out = sensitivity.evaluate(BLOBS, _upstream())
    fin = next(r for r in out.data_sensitivity if r.classification is Sensitivity.FINANCIAL)
    assert fin.entity == "payments"
    assert fin.origin == "model"
    assert "card_last4" in fin.fields


def test_accessed_by_cites_the_matching_entry_point_by_local_id():
    """P3-D6: a NAME match, and the rule says so. A read/write dataflow
    analysis is not available to a blob-reading scan, and asserting one would
    be the fabrication FR-914 exists to prevent."""
    out = sensitivity.evaluate(BLOBS, _upstream())
    pii = next(r for r in out.data_sensitivity if r.classification is Sensitivity.PII)
    assert pii.accessed_by == ["S3-customer"]


def test_entity_access_is_a_gap_when_s3_did_not_collect():
    """P3-D12: an empty accessed_by must never read as 'no entry point
    touches PII' -- the owing category says why it is empty."""
    out = sensitivity.evaluate(BLOBS, _upstream(s3_ok=False))
    assert out.row.categories[C_ENTITY_ACCESS].state is CollectionState.NOT_COLLECTED
    assert "S3" in out.row.categories[C_ENTITY_ACCESS].reason
    # the classification half still measured
    assert out.row.categories[C_DATA_SENSITIVITY].state is CollectionState.MEASURED
    assert all(r.accessed_by == [] for r in out.data_sensitivity)


def test_the_whole_signal_is_a_gap_when_s2_did_not_collect():
    """Section 5: without the table set the entity set is partial, and a
    partial sensitivity map that says 'no PII' is the dangerous conflation."""
    out = sensitivity.evaluate(BLOBS, _upstream(s2_ok=False))
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.data_sensitivity == []
    assert "S2" in out.row.collected.reason


def test_a_compliance_marker_makes_the_entity_regulatory():
    blobs = dict(BLOBS)
    blobs["app/models/card.py"] = (
        "# PCI-DSS scope: cardholder data\n"
        "class Card(Base):\n"
        "    __tablename__ = 'cards'\n"
        "    pan = Column(String(19))\n"
    )
    out = sensitivity.evaluate(blobs, _upstream())
    assert any(
        r.classification is Sensitivity.REGULATORY and r.entity == "cards"
        for r in out.data_sensitivity
    )


def test_a_field_named_company_is_not_a_card_number():
    """Substring matching would classify 'company' as financial because it
    contains 'pan'. Tokens, not substrings."""
    blobs = {
        "app/models/org.py": (
            "class Org(Base):\n    __tablename__ = 'orgs'\n    company = Column(String(80))\n"
        )
    }
    out = sensitivity.evaluate(blobs, _upstream())
    assert out.data_sensitivity == []
    assert out.row.categories[C_DATA_SENSITIVITY].state is CollectionState.MEASURED
    assert out.row.categories[C_DATA_SENSITIVITY].value == 0.0


def test_output_is_byte_identical_across_input_orderings():
    reference = sensitivity.evaluate(BLOBS, _upstream()).model_dump_json()
    reordered = dict(reversed(list(BLOBS.items())))
    assert sensitivity.evaluate(reordered, _upstream()).model_dump_json() == reference
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_ss4_sensitivity.py -v`
Expected: FAIL with `ImportError: cannot import name 'C_ENTITY_ACCESS'`

- [ ] **Step 3: Add SS4's second category to `scan/models.py`**

Beside the other SS category constants:

```python
C_DATA_SENSITIVITY = "data_sensitivity"  # SS4, computed
C_ENTITY_ACCESS = "entity_access"  # SS4, computed from S3
```

and in `CATEGORIES`:

```python
    ScanSignalId.SS4: (C_DATA_SENSITIVITY, C_ENTITY_ACCESS),
```

The registry needs no edit: `_spec` reads `categories=CATEGORIES[sid]`, which is the whole point of the single declaration.

- [ ] **Step 4: Write `scan/signals/sensitivity.py`**

```python
"""SS4 -- data sensitivity (FR-912).

Classifies ENTITIES, not files: the question E-49 asks is which capability
handles regulated data. The entity set is S2's declarations (one extractor,
two readers -- FR-902), and the accessor set is a NAME match against S3's
entry points, never a dataflow claim (P3-D6).

Two categories, because the two halves fail independently (P3-D12):
  * data_sensitivity -- the classification. Needs the tree and S2.
  * entity_access    -- which entry points touch the entity. Needs S3, and
                        reports not_collected naming it when S3 degraded, so
                        an empty accessed_by never reads as "no entry point
                        touches PII" (D5, section 5).

Pure: blobs and the declared upstream in, records out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ....measurement import Measurement
from ..models import (
    C_DATA_SENSITIVITY,
    C_ENTITY_ACCESS,
    Confidence,
    EvidenceRef,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    Sensitivity,
    SensitivityRecord,
    SignalOutput,
    SignalSource,
    family_of,
)
from ..naming import normalize
from .schema import TableDecl, declarations

SIGNAL_ID = "SS4"
VERSION = 1

# Ordered: the FIRST classification a field matches wins, so `password_hash`
# is authentication rather than PII. Order is the rule, and it is declared
# rather than discovered.
_FIELD_RULES: tuple[tuple[Sensitivity, str, frozenset[str]], ...] = (
    (
        Sensitivity.AUTHENTICATION,
        "ss4_authentication_field_name",
        frozenset(
            {
                "password",
                "passwd",
                "passwordhash",
                "password_hash",
                "secret",
                "token",
                "access_token",
                "accesstoken",
                "refresh_token",
                "refreshtoken",
                "session",
                "session_id",
                "sessionid",
                "api_key",
                "apikey",
                "mfa",
                "totp",
                "otp",
                "salt",
                "credential",
                "credentials",
            }
        ),
    ),
    (
        Sensitivity.FINANCIAL,
        "ss4_financial_field_name",
        frozenset(
            {
                "card",
                "card_number",
                "cardnumber",
                "pan",
                "cvv",
                "cvc",
                "iban",
                "bic",
                "swift",
                "account_number",
                "accountnumber",
                "routing_number",
                "routingnumber",
                "balance",
                "amount",
                "currency",
                "invoice",
                "transaction",
                "payment_method",
                "paymentmethod",
                "card_last4",
                "cardlast4",
                "sort_code",
                "sortcode",
            }
        ),
    ),
    (
        Sensitivity.HEALTH,
        "ss4_health_field_name",
        frozenset(
            {
                "diagnosis",
                "medication",
                "prescription",
                "patient",
                "icd",
                "allergy",
                "blood_type",
                "bloodtype",
                "medical_record",
                "medicalrecord",
                "nhs_number",
                "nhsnumber",
            }
        ),
    ),
    (
        Sensitivity.PII,
        "ss4_pii_field_name",
        frozenset(
            {
                "email",
                "e_mail",
                "phone",
                "phone_number",
                "phonenumber",
                "mobile",
                "first_name",
                "firstname",
                "last_name",
                "lastname",
                "full_name",
                "fullname",
                "address",
                "street",
                "postcode",
                "zip",
                "zipcode",
                "ssn",
                "national_id",
                "nationalid",
                "passport",
                "date_of_birth",
                "dateofbirth",
                "dob",
                "ip_address",
                "ipaddress",
                "latitude",
                "longitude",
            }
        ),
    ),
)

_REGULATORY = re.compile(r"\b(PCI[- ]?DSS|PCI\b|HIPAA|GDPR|SOC ?2|PSD2|CCPA|FERPA)\b")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _tokens(field: str) -> set[str]:
    """A field's comparable forms: its words, its whole lowercased name, and
    the same with separators removed.

    TOKENS, not substrings: 'company' contains 'pan', and a substring rule
    would classify an organisation table as cardholder data. A false PII
    finding in a report a client pays for is worse than a missed one, because
    it is the finding they will check first.
    """
    words = re.split(r"[_\-\s]+", _CAMEL.sub("_", field))
    lowered = field.lower()
    return {w.lower() for w in words if w} | {lowered, lowered.replace("_", "")}


def _origin(decl: TableDecl) -> str:
    """table | model | dto -- SS4's declared shape. A DTO is recognised by
    where it lives, which is the only thing that distinguishes it from a
    model at this depth."""
    if "dto" in decl.path.lower() or decl.name.lower().endswith("dto"):
        return "dto"
    return "table" if decl.origin == "table" else "model"


def _accessors(entity: str, upstream: ScanUpstream) -> list[str]:
    """S3 candidates whose normalized name equals the entity's (P3-D6)."""
    key = normalize(entity)
    return sorted(
        {
            c.local_id
            for c in upstream.sources
            if c.signal is ScanSignalId.S3 and normalize(c.name) == key
        }
    )


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS4,
            family=family_of(ScanSignalId.SS4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=nc,
            categories={C_DATA_SENSITIVITY: nc, C_ENTITY_ACCESS: nc},
        )
    )


def evaluate(blobs: Mapping[str, str], upstream: ScanUpstream) -> SignalOutput:
    """`blobs` is path -> text for readable source/schema blobs; `upstream`
    carries S2's and S3's candidates and row states (P3-D4)."""
    if not upstream.measured(ScanSignalId.S2):
        return _gap(upstream.gap(ScanSignalId.S2, "data_sensitivity").reason)

    s3_ok = upstream.measured(ScanSignalId.S3)
    records: list[SensitivityRecord] = []

    for decl in declarations(blobs):
        regulated = bool(_REGULATORY.search(blobs.get(decl.path, "")))
        matched: dict[Sensitivity, tuple[str, list[str]]] = {}
        for field in decl.fields:
            tokens = _tokens(field)
            for classification, rule, terms in _FIELD_RULES:
                if tokens & terms:
                    matched.setdefault(classification, (rule, []))[1].append(field)
                    break
        accessed = _accessors(decl.name, upstream) if s3_ok else []
        for classification, (rule, fields) in matched.items():
            records.append(
                SensitivityRecord(
                    classification=classification,
                    entity=decl.name,
                    origin=_origin(decl),
                    fields=sorted(set(fields)),
                    accessed_by=accessed,
                    evidence=[EvidenceRef(path=decl.path, lines=str(decl.line))],
                    rule=rule,
                    confidence=(Confidence.HIGH if len(fields) > 1 else Confidence.MEDIUM),
                )
            )
        if regulated:
            records.append(
                SensitivityRecord(
                    classification=Sensitivity.REGULATORY,
                    entity=decl.name,
                    origin=_origin(decl),
                    fields=sorted(decl.fields),
                    accessed_by=accessed,
                    evidence=[EvidenceRef(path=decl.path, lines=str(decl.line))],
                    rule="ss4_declared_compliance_scope",
                    confidence=Confidence.MEDIUM,
                )
            )

    records.sort(key=lambda r: (r.classification.value, r.entity, r.rule))
    classified = Measurement.measured(float(len(records)))
    access = (
        Measurement.measured(float(sum(1 for r in records if r.accessed_by)))
        if s3_ok
        else upstream.gap(ScanSignalId.S3, "entity_access")
    )
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS4,
            family=family_of(ScanSignalId.SS4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=classified,
            categories={C_DATA_SENSITIVITY: classified, C_ENTITY_ACCESS: access},
        ),
        data_sensitivity=records,
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_scan_ss4_sensitivity.py -v`
Expected: PASS

- [ ] **Step 6: Give SS4 a real activity body**

In `src/sdlc/assessment/activities.py`, import `sensitivity`, move `SS4` from `OWED_BY` to `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_sensitivity(inp: ScanSignalInput) -> SignalOutput:
    """SS4 -- data sensitivity. Wave 2: consumes S2's tables and S3's entry
    points, so its output is only cacheable when both collected (P3-D5)."""
    if (hit := memo.load(ScanSignalId.SS4, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(
            inp.repo_dir, inp.commit_sha, paths, SOURCE_EXTENSIONS + schema.EXTRA_EXTENSIONS
        )
        out = sensitivity.evaluate(blobs, inp.upstream)
    except Exception as exc:  # noqa: BLE001
        _log.warning("SS4 failed: %s", exc)
        return failed_signal(ScanSignalId.SS4, exc)
    memo.store(ScanSignalId.SS4, inp.tree_hash, out, inp.upstream)
    return out
```

- [ ] **Step 7: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/assessment/scan/signals/sensitivity.py \
        src/sdlc/assessment/scan/models.py src/sdlc/assessment/activities.py \
        tests/test_scan_ss4_sensitivity.py
git commit -m "feat(scan): SS4 data sensitivity, with entity_access as its own category (E-46 plan 3)"
```

---

### Task 5: QS3 — testability

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/testability.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_testability` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_qs3_testability.py` (create)

**Interfaces:**
- Consumes: `testpaths.is_test_path`, `sources.SOURCE_EXTENSIONS`, `triage.models.evidence_key`.
- Produces: `PATTERNS: tuple[_Pattern, ...]`, `evaluate(blobs) -> SignalOutput`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_qs3_testability.py`:

```python
"""QS3: what stops a test being written. BrownKit's three-valued severity
(blocks | impedes | smell) answers a different question than
critical/high/medium/low, which is why the record does not reuse
TriageFinding's scale."""

from __future__ import annotations

from sdlc.assessment.scan.models import testability_identity
from sdlc.assessment.scan.signals import testability
from sdlc.measurement import CollectionState

BLOBS = {
    "src/scheduler.py": (
        "import datetime\n"
        "import random\n"
        "\n"
        "CACHE = {}\n"
        "\n"
        "def next_run():\n"
        "    now = datetime.datetime.now()\n"
        "    jitter = random.random()\n"
        "    return now, jitter\n"
    ),
    "src/client.py": ("import requests\n\ndef fetch(url):\n    return requests.get(url).json()\n"),
    "tests/test_scheduler.py": (
        "import datetime\ndef test_next_run():\n    assert datetime.datetime.now()\n"
    ),
}


def test_a_clock_read_in_production_code_is_a_finding():
    out = testability.evaluate(BLOBS)
    patterns = {(f.path, f.pattern) for f in out.testability}
    assert ("src/scheduler.py", "static-clock-access") in patterns


def test_test_files_are_not_scanned():
    """A clock read inside a test is the test's own business."""
    out = testability.evaluate(BLOBS)
    assert all(not f.path.startswith("tests/") for f in out.testability)


def test_one_finding_per_path_and_pattern_with_the_count_in_the_detail():
    """P3-D10: a per-line finding turns a common habit into thousands of rows
    and makes every key move when a line moves."""
    blobs = {"src/a.py": "import datetime\n" + ("x = datetime.datetime.now()\n" * 5)}
    out = testability.evaluate(blobs)
    clock = [f for f in out.testability if f.pattern == "static-clock-access"]
    assert len(clock) == 1
    assert "5" in clock[0].detail
    assert clock[0].line == 2  # the FIRST occurrence


def test_identity_is_stable_when_a_line_moves():
    a = testability.evaluate({"src/a.py": "import datetime\nx = datetime.datetime.now()\n"})
    b = testability.evaluate({"src/a.py": "import datetime\n\n\nx = datetime.datetime.now()\n"})
    assert testability_identity(a.testability[0]) == testability_identity(b.testability[0])


def test_every_finding_carries_a_seam_and_a_verbatim_quote():
    out = testability.evaluate(BLOBS)
    assert out.testability
    for finding in out.testability:
        assert finding.recommended_seam
        assert finding.evidence
        assert finding.severity in {"blocks", "impedes", "smell"}


def test_a_clean_module_is_a_measured_zero_not_a_gap():
    """We read every source blob in the tree; finding nothing is an answer."""
    out = testability.evaluate({"src/pure.py": "def add(a, b):\n    return a + b\n"})
    assert out.row.collected.state is CollectionState.MEASURED
    assert out.row.collected.value == 0.0
    assert out.testability == []


def test_output_is_byte_identical_across_input_orderings():
    reference = testability.evaluate(BLOBS).model_dump_json()
    reordered = dict(reversed(list(BLOBS.items())))
    assert testability.evaluate(reordered).model_dump_json() == reference
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_qs3_testability.py -v`
Expected: FAIL with `AttributeError: module … has no attribute 'evaluate'`

- [ ] **Step 3: Write `scan/signals/testability.py`**

```python
"""QS3 -- testability findings (FR-912).

BrownKit's patterns, ported as a declared table with a recommended seam per
pattern -- because "inject a clock" is the actionable half, and E-53 may seed
a fix run from it.

ONE finding per (path, pattern), with the occurrence count in the detail
(P3-D10). A per-line finding would put thousands of rows in the FR-921 bundle
for one common habit, and each row's key -- an evidence hash -- would differ,
so E-44's delta would report a phantom resolved+new pair whenever a line
moved. `key` is therefore empty and testability_identity keys on
(pattern, path), which is exactly the stability E-44 D3 asks for.

Test files are not scanned: a clock read inside a test is the test's own
business, and flagging it would bury the findings that matter.

Pure: blobs in, records out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_TESTABILITY,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    TestabilityFinding,
    family_of,
)
from ..testpaths import is_test_path

SIGNAL_ID = "QS3"
VERSION = 1

_MAX_EVIDENCE = 400


class _Pattern(BaseModel):
    # arbitrary_types_allowed: a compiled regex is not a Pydantic-native type,
    # and compiling once at import is the point of the table.
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    name: str
    severity: str  # blocks | impedes | smell
    regex: re.Pattern[str]
    seam: str
    detail: str


PATTERNS: tuple[_Pattern, ...] = (
    _Pattern(
        name="static-clock-access",
        severity="impedes",
        regex=re.compile(
            r"\b(?:datetime\.datetime\.now|datetime\.now|datetime\.utcnow"
            r"|time\.time|Date\.now|new Date\(\)|DateTime\.Now"
            r"|System\.currentTimeMillis|time\.Now)\s*\("
        ),
        seam="Inject a clock (a callable returning the current time).",
        detail="Reads the wall clock directly, so a test cannot choose the time it runs at.",
    ),
    _Pattern(
        name="unseeded-randomness",
        severity="impedes",
        regex=re.compile(
            r"\b(?:random\.(?:random|randint|choice|shuffle|uniform)"
            r"|Math\.random|uuid\.uuid4|crypto\.randomUUID"
            r"|rand\.Intn|new Random\(\))\s*\("
        ),
        seam="Inject a random source, or seed it from configuration.",
        detail="Produces a different value on every run, so an assertion "
        "cannot be written against it.",
    ),
    _Pattern(
        name="direct-http-call",
        severity="impedes",
        regex=re.compile(
            r"\b(?:requests\.(?:get|post|put|patch|delete)"
            r"|httpx\.(?:get|post|put|patch|delete)"
            r"|urllib\.request\.urlopen|new HttpClient|axios\.(?:get|post)"
            r"|http\.Get|fetch)\s*\("
        ),
        seam="Inject a client or gateway interface.",
        detail="Calls the network from business logic, so a test must reach "
        "the network or monkey-patch a module.",
    ),
    _Pattern(
        name="direct-file-io",
        severity="smell",
        regex=re.compile(
            r"\b(?:open\s*\(\s*['\"]|Path\([^)]*\)\.(?:read_text|write_text)"
            r"|fs\.(?:readFileSync|writeFileSync)|File\.ReadAllText"
            r"|ioutil\.ReadFile)\s*\(?"
        ),
        seam="Inject a reader/writer, or pass the content in.",
        detail="Touches the filesystem from business logic, so a test needs "
        "a real file to exercise it.",
    ),
    _Pattern(
        name="sleep-in-production",
        severity="impedes",
        regex=re.compile(
            r"\b(?:time\.sleep|asyncio\.sleep|Thread\.sleep|setTimeout"
            r"|time\.Sleep)\s*\("
        ),
        seam="Make the wait injectable, or drive it from an event.",
        detail="Blocks for a fixed duration, which makes every test that "
        "crosses it slow and timing-dependent.",
    ),
    _Pattern(
        name="singleton-access",
        severity="blocks",
        regex=re.compile(r"\b\w+\.getInstance\s*\(\s*\)|\bSingleton\.\w+"),
        seam="Pass the collaborator in rather than reaching for the singleton.",
        detail="Reaches a global instance, so a test cannot substitute it "
        "without mutating global state.",
    ),
    _Pattern(
        name="module-level-mutable-global",
        severity="smell",
        regex=re.compile(
            r"(?m)^[A-Za-z_]\w*\s*(?::[^=\n]+)?=\s*(?:\[\s*\]"
            r"|\{\s*\}|set\(\)|dict\(\)|list\(\))\s*$"
        ),
        seam="Move the state behind a factory or a fixture.",
        detail="Module-level mutable state leaks between tests in the same process.",
    ),
    _Pattern(
        name="env-read-in-business-logic",
        severity="smell",
        regex=re.compile(
            r"\b(?:os\.environ\[|os\.getenv\s*\(|process\.env\."
            r"|Environment\.GetEnvironmentVariable\s*\()"
        ),
        seam="Read configuration once at the edge and pass it in.",
        detail="Reads the environment where it is used, so a test must set "
        "process-wide state to steer it.",
    ),
)


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound source blob.

    A clean tree is a MEASURED zero: every source blob was read and no
    pattern fired. That is the same conclusion S1 reaches for a tree with no
    source files, and the opposite of S3's -- S3 cannot see routes it has no
    fingerprint for, while these patterns are the whole definition of what is
    being looked for.
    """
    findings: list[TestabilityFinding] = []
    for path in sorted(blobs):
        if is_test_path(path):
            continue
        text = blobs[path]
        for pattern in PATTERNS:
            matches = list(pattern.regex.finditer(text))
            if not matches:
                continue
            first = matches[0]
            line = text.count("\n", 0, first.start()) + 1
            quote = text.splitlines()[line - 1].strip()[:_MAX_EVIDENCE]
            occurrences = f" {len(matches)} occurrence(s) in this file." if len(matches) > 1 else ""
            findings.append(
                TestabilityFinding(
                    severity=pattern.severity,
                    pattern=pattern.name,
                    detail=f"{pattern.detail}{occurrences}",
                    recommended_seam=pattern.seam,
                    path=path,
                    line=line,
                    evidence=quote,
                )
            )

    findings.sort(key=lambda f: (f.path, f.pattern))
    collected = Measurement.measured(float(len(findings)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.QS3,
            family=family_of(ScanSignalId.QS3),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={C_TESTABILITY: collected},
        ),
        testability=findings,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_qs3_testability.py -v`
Expected: PASS

- [ ] **Step 5: Give QS3 a real activity body**

In `src/sdlc/assessment/activities.py`, import `testability`, move `QS3` from `OWED_BY` to `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_testability(inp: ScanSignalInput) -> SignalOutput:
    """QS3 -- testability findings over production source blobs."""
    if (hit := memo.load(ScanSignalId.QS3, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(inp.repo_dir, inp.commit_sha, paths, SOURCE_EXTENSIONS)
        out = testability.evaluate(blobs)
    except Exception as exc:  # noqa: BLE001
        _log.warning("QS3 failed: %s", exc)
        return failed_signal(ScanSignalId.QS3, exc)
    memo.store(ScanSignalId.QS3, inp.tree_hash, out)
    return out
```

- [ ] **Step 6: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/signals/testability.py \
        src/sdlc/assessment/activities.py tests/test_scan_qs3_testability.py
git commit -m "feat(scan): QS3 testability -- one finding per (path, pattern) with a seam (E-46 plan 3)"
```

---

### Task 6: QS1 — test inventory (the computed half of an EXTENDED signal)

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/tests_inventory.py`
- Modify: `src/sdlc/assessment/scan/models.py` (add `inherited_pending`)
- Modify: `src/sdlc/assessment/activities.py` (`scan_tests_inventory` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_qs1_tests_inventory.py` (create)

**Interfaces:**
- Consumes: `testpaths.is_test_path`, `sources.SOURCE_EXTENSIONS`.
- Produces: `evaluate(paths, blobs) -> SignalOutput`; `models.inherited_pending(category) -> Measurement`, used by **Tasks 8, 9 and 10** for the same reason.

**Why `inherited_pending` exists.** `ScanSignalResult._declares_every_category_it_owes` requires a row to carry *every* category `CATEGORIES` declares for its signal — but an EXTENDED signal's activity computes only its own half, and the workflow folds the inherited half in afterwards (D7). So the activity must put something on the inherited keys. `inherited_pending` is that something: a `not_collected` naming D7, which `fold_row` overwrites in the normal path and which stays — honestly — when triage produced no half at all.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_qs1_tests_inventory.py`:

```python
"""QS1: every test file, its level, and what it covers. The mapping is what
QS2's proxy is computed from, so an over-eager mapping inflates a coverage
number -- which is why an ambiguous match is `unmapped`, not a guess."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_TEST_LEVELS,
    C_TEST_MAPPING,
    C_TESTS_PRESENT,
    TestLevel,
)
from sdlc.assessment.scan.signals import tests_inventory
from sdlc.measurement import CollectionState

PATHS = [
    "src/payments/service.py",
    "src/payments/gateway.py",
    "tests/test_service.py",
    "tests/integration/test_gateway.py",
    "e2e/checkout.spec.ts",
    "src/web/Button.tsx",
    "src/web/Button.test.tsx",
]
BLOBS = {
    "tests/test_service.py": (
        "import pytest\n"
        "from payments.service import settle\n"
        "def test_settle():\n    assert settle(1)\n"
    ),
    "tests/integration/test_gateway.py": (
        "import pytest, psycopg\ndef test_gateway_writes():\n    ...\n"
    ),
    "e2e/checkout.spec.ts": (
        "import { test, expect } from '@playwright/test';\n"
        "test('checkout', async ({ page }) => {});\n"
    ),
    "src/web/Button.test.tsx": (
        "import { describe, it } from 'vitest';\n"
        "describe('Button', () => { it('renders', () => {}) });\n"
    ),
}


def test_every_test_file_is_inventoried():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    assert {r.path for r in out.tests} == {
        "tests/test_service.py",
        "tests/integration/test_gateway.py",
        "e2e/checkout.spec.ts",
        "src/web/Button.test.tsx",
    }


def test_levels_are_classified_by_the_strongest_signal_first():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    level = {r.path: r.level for r in out.tests}
    assert level["e2e/checkout.spec.ts"] is TestLevel.E2E
    assert level["tests/integration/test_gateway.py"] is TestLevel.INTEGRATION
    assert level["tests/test_service.py"] is TestLevel.UNIT
    assert level["src/web/Button.test.tsx"] is TestLevel.UNIT


def test_frameworks_are_recorded_when_a_signature_matches():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    framework = {r.path: r.framework for r in out.tests}
    assert framework["tests/test_service.py"] == "pytest"
    assert framework["e2e/checkout.spec.ts"] == "playwright"
    assert framework["src/web/Button.test.tsx"] == "vitest"


def test_a_test_with_no_signature_is_unknown_not_unit():
    out = tests_inventory.evaluate(["tests/test_mystery.py"], {"tests/test_mystery.py": "x = 1\n"})
    assert out.tests[0].level is TestLevel.UNKNOWN
    assert out.tests[0].rule == "qs1_no_level_signature"


def test_the_naming_convention_maps_a_test_to_its_subject():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    by_path = {r.path: r for r in out.tests}
    assert by_path["tests/test_service.py"].covers == ["src/payments/service.py"]
    assert by_path["tests/test_service.py"].mapping_rule == "naming_convention"


def test_a_co_located_test_prefers_its_own_directory():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    button = next(r for r in out.tests if r.path == "src/web/Button.test.tsx")
    assert button.covers == ["src/web/Button.tsx"]
    assert button.mapping_rule == "co_location"


def test_an_ambiguous_match_is_unmapped_rather_than_a_guess():
    """Two `service.py` files and one `test_service.py`: guessing would
    inflate QS2's proxy for whichever package won the coin toss."""
    paths = ["src/a/service.py", "src/b/service.py", "tests/test_service.py"]
    out = tests_inventory.evaluate(
        paths, {"tests/test_service.py": "import pytest\ndef test_x(): ...\n"}
    )
    record = out.tests[0]
    assert record.mapping_rule == "unmapped"
    assert record.covers == []


def test_both_computed_categories_report_and_the_inherited_one_is_pending():
    out = tests_inventory.evaluate(PATHS, BLOBS)
    assert out.row.categories[C_TEST_LEVELS].state is CollectionState.MEASURED
    assert out.row.categories[C_TEST_MAPPING].state is CollectionState.MEASURED
    # D7: the workflow folds this one in; the activity must still declare it.
    pending = out.row.categories[C_TESTS_PRESENT]
    assert pending.state is CollectionState.NOT_COLLECTED
    assert "D7" in pending.reason


def test_a_repository_with_no_tests_is_a_measured_zero():
    out = tests_inventory.evaluate(["src/a.py"], {})
    assert out.row.categories[C_TEST_LEVELS].value == 0.0
    assert out.tests == []
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_qs1_tests_inventory.py -v`
Expected: FAIL with `ImportError: cannot import name 'C_TEST_LEVELS'`-adjacent errors from the module having no `evaluate`

- [ ] **Step 3: Add `inherited_pending` to `scan/models.py`**

Beside the `CATEGORIES` block:

```python
def inherited_pending(category: str) -> Measurement:
    """What a COMPUTED activity half puts on a category the INHERITED half
    owns (D7).

    A row must declare every category its signal owes, but an EXTENDED
    signal's activity computes only its own half -- the workflow derives the
    other from RepoTriage and folds it in. This placeholder is what fold_row
    overwrites in the normal path, and what stays, honestly, when triage
    produced no half at all.
    """
    return Measurement.not_collected(
        f"{category}: inherited from triage and folded in by the workflow "
        f"(D7); this row carries the activity's computed half only"
    )
```

- [ ] **Step 4: Write `scan/signals/tests_inventory.py`**

```python
"""QS1 -- test inventory (FR-912). The computed half of an EXTENDED signal:
triage's baseline already counted test FILES (the inherited tests_present
category), and this adds the two facts a count cannot carry -- what LEVEL each
test is, and WHAT it covers.

The mapping is what QS2's proxy coverage is computed from, so an over-eager
mapping inflates a coverage number in a product that sells measurement. An
ambiguous match is therefore `unmapped`, never a guess.

Pure: paths and blobs in, records out.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence

from ....measurement import Measurement
from ..models import (
    C_TEST_LEVELS,
    C_TEST_MAPPING,
    C_TESTS_PRESENT,
    Confidence,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    TestFileRecord,
    TestLevel,
    family_of,
    inherited_pending,
)
from ..sources import SOURCE_EXTENSIONS
from ..testpaths import is_test_path

SIGNAL_ID = "QS1"
VERSION = 1

# (framework, signature). First match wins, so the table's order is the rule.
FRAMEWORKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("playwright", re.compile(r"@playwright/test|playwright\.config")),
    ("cypress", re.compile(r"\bcy\.\w+\(|cypress/support")),
    ("selenium", re.compile(r"\bselenium\b|webdriver")),
    ("k6", re.compile(r"from\s+['\"]k6['\"]")),
    ("locust", re.compile(r"\blocust\b|HttpUser")),
    ("pact", re.compile(r"\bpact\b", re.IGNORECASE)),
    ("vitest", re.compile(r"from\s+['\"]vitest['\"]")),
    ("jest", re.compile(r"@jest/globals|\bjest\.(?:mock|fn)\(")),
    ("mocha", re.compile(r"require\(['\"]mocha['\"]\)")),
    ("pytest", re.compile(r"(?m)^\s*import\s+pytest\b|(?m)^\s*def\s+test_")),
    ("unittest", re.compile(r"(?m)^\s*import\s+unittest\b")),
    ("junit", re.compile(r"import\s+org\.junit")),
    ("nunit", re.compile(r"using\s+NUnit")),
    ("xunit", re.compile(r"using\s+Xunit")),
    ("gotest", re.compile(r"(?m)^func\s+Test\w+\(")),
    ("rspec", re.compile(r"(?m)^\s*(?:RSpec\.)?describe\b")),
    ("phpunit", re.compile(r"PHPUnit\\Framework")),
)

# (level, rule, path regex or None, content regex or None). ORDERED: the
# strongest claim first, so an e2e test that also touches a database is e2e
# rather than integration.
_LEVEL_RULES: tuple[tuple[TestLevel, str, re.Pattern[str] | None, re.Pattern[str] | None], ...] = (
    (
        TestLevel.MANUAL,
        "qs1_manual_test_plan",
        re.compile(r"(?i)(^|/)(docs/)?test[-_]?plans?/|\.md$"),
        re.compile(r"(?i)manual test"),
    ),
    (
        TestLevel.E2E,
        "qs1_e2e_marker",
        re.compile(r"(?i)(^|/)(e2e|cypress|playwright)/|\.cy\.[jt]sx?$"),
        re.compile(r"@playwright/test|\bcy\.\w+\(|\bselenium\b|webdriver"),
    ),
    (
        TestLevel.PERFORMANCE,
        "qs1_performance_marker",
        re.compile(r"(?i)(^|/)(perf|performance|load|bench)/"),
        re.compile(r"from\s+['\"]k6['\"]|\blocust\b|HttpUser|\bgatling\b"),
    ),
    (
        TestLevel.CONTRACT,
        "qs1_contract_marker",
        re.compile(r"(?i)(^|/)contracts?/"),
        re.compile(r"(?i)\bpact\b|spring-cloud-contract|schemathesis"),
    ),
    (
        TestLevel.INTEGRATION,
        "qs1_integration_marker",
        re.compile(r"(?i)(^|/)(integration|it)/"),
        re.compile(
            r"testcontainers|psycopg|sqlalchemy\.create_engine"
            r"|TestClient\(|supertest|requests\.(?:get|post)\("
            r"|docker|@SpringBootTest"
        ),
    ),
)

_STEM_RULES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^test_(?P<stem>.+)$"),
    re.compile(r"^(?P<stem>.+)_test$"),
    re.compile(r"^(?P<stem>.+)\.test$"),
    re.compile(r"^(?P<stem>.+)\.spec$"),
    re.compile(r"^(?P<stem>.+)\.cy$"),
    re.compile(r"^(?P<stem>.+)_spec$"),
    re.compile(r"^(?P<stem>.+)Tests?$"),
)


def _stem(path: str) -> str:
    """The subject's stem, derived from the test file's name."""
    base = posixpath.splitext(posixpath.basename(path))[0]
    for rule in _STEM_RULES:
        match = rule.match(base)
        if match:
            return match.group("stem")
    return base


def _framework(text: str) -> str:
    for name, signature in FRAMEWORKS:
        if signature.search(text):
            return name
    return ""


def _level(path: str, text: str) -> tuple[TestLevel, str]:
    for level, rule, path_rule, content_rule in _LEVEL_RULES:
        if (path_rule and path_rule.search(path)) or (content_rule and content_rule.search(text)):
            return level, rule
    if _framework(text):
        return TestLevel.UNIT, "qs1_unit_by_elimination"
    # P3-D8: never default to unit. A test-shaped file no rule recognised is
    # a file we could not classify, and calling it a unit test inflates the
    # one number a QA report is read for.
    return TestLevel.UNKNOWN, "qs1_no_level_signature"


def _mapping(path: str, subjects: Mapping[str, list[str]]) -> tuple[str, list[str], Confidence]:
    """(mapping_rule, covers, confidence) for one test file."""
    matches = subjects.get(_stem(path), [])
    if not matches:
        return "unmapped", [], Confidence.LOW
    here = [p for p in matches if posixpath.dirname(p) == posixpath.dirname(path)]
    if len(here) == 1:
        return "co_location", here, Confidence.HIGH
    if len(matches) == 1:
        return "naming_convention", list(matches), Confidence.MEDIUM
    # Two subjects with the same stem: guessing would inflate QS2's proxy for
    # whichever package won the coin toss.
    return "unmapped", [], Confidence.LOW


def evaluate(paths: Sequence[str], blobs: Mapping[str, str]) -> SignalOutput:
    """`paths` is every tracked path; `blobs` is path -> text for the test
    files that were read."""
    subjects: dict[str, list[str]] = {}
    for path in sorted(paths):
        if is_test_path(path) or not path.endswith(SOURCE_EXTENSIONS):
            continue
        subjects.setdefault(posixpath.splitext(posixpath.basename(path))[0], []).append(path)

    records: list[TestFileRecord] = []
    for path in sorted(p for p in paths if is_test_path(p)):
        text = blobs.get(path, "")
        level, rule = _level(path, text)
        mapping_rule, covers, confidence = _mapping(path, subjects)
        records.append(
            TestFileRecord(
                path=path,
                level=level,
                rule=rule,
                framework=_framework(text),
                covers=covers,
                mapping_rule=mapping_rule,
                confidence=confidence,
            )
        )

    records.sort(key=lambda r: r.path)
    levels = Measurement.measured(float(len(records)))
    mapped = Measurement.measured(float(sum(1 for r in records if r.mapping_rule != "unmapped")))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.QS1,
            family=family_of(ScanSignalId.QS1),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=levels,
            categories={
                C_TEST_LEVELS: levels,
                C_TEST_MAPPING: mapped,
                C_TESTS_PRESENT: inherited_pending(C_TESTS_PRESENT),
            },
        ),
        tests=records,
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_scan_qs1_tests_inventory.py -v`
Expected: PASS

- [ ] **Step 6: Give QS1 a real activity body**

In `src/sdlc/assessment/activities.py`, import `tests_inventory`, move `QS1` from `OWED_BY` to `BUILT`, and replace the stub:

First add the by-path blob reader beside `_source_blobs` — QS1, QS2, SS3 and QS4 all need blobs selected by NAME rather than by extension, and four copies of the size-guarded loop would drift:

```python
def _blobs_for(repo_dir: str, commit_sha: str, paths: Sequence[str]) -> dict[str, str]:
    """path -> text for an explicit path list, size-guarded.

    The companion to _source_blobs, which selects by extension. A config file,
    a CI workflow and a coverage report have no extension in common, so the
    signals that read them select by name and share this reader.
    """
    out: dict[str, str] = {}
    for path, text in read_tree(repo_dir, commit_sha, sorted(paths)):
        if not is_over_size_limit(text):
            out[path] = text
    return out
```

then the activity itself:

```python
@activity.defn
async def scan_tests_inventory(inp: ScanSignalInput) -> SignalOutput:
    """QS1 -- test levels and the test -> file mapping. Reads only the test
    files' blobs; the mapping targets come from the path list."""
    if (hit := memo.load(ScanSignalId.QS1, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        out = tests_inventory.evaluate(
            paths, _blobs_for(inp.repo_dir, inp.commit_sha, [p for p in paths if is_test_path(p)])
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("QS1 failed: %s", exc)
        return failed_signal(ScanSignalId.QS1, exc)
    memo.store(ScanSignalId.QS1, inp.tree_hash, out)
    return out
```

Add `from .scan.testpaths import is_test_path` and `from collections.abc import Sequence` to the activity module's imports (`read_tree` and `is_over_size_limit` are already imported).

- [ ] **Step 7: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/assessment/scan/signals/tests_inventory.py \
        src/sdlc/assessment/scan/models.py src/sdlc/assessment/activities.py \
        tests/test_scan_qs1_tests_inventory.py
git commit -m "feat(scan): QS1 test levels and test->file mapping; unmapped beats a guess (E-46 plan 3)"
```

---

### Task 7: QS2 — coverage from a committed report, else a proxy

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/coverage.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_coverage` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_qs2_coverage.py` (create)

**Interfaces:**
- Consumes: `ScanUpstream.tests` (QS1's records), `testpaths.is_test_path`, `sources.SOURCE_EXTENSIONS`.
- Produces: `REPORT_PATHS: tuple[str, ...]`, `evaluate(paths, reports, upstream) -> SignalOutput`.

**Note on reuse.** `measure_coverage` (E-30, `sdlc/activities.py`) is *not* reused: it is an activity that reads a worktree and averages a diff-scoped subset, while QS2 reads a blob at a pinned commit and reports per file. D2's narrow definition applies — reusing a parser would be code reuse, not inheritance, and this is not even that. What *is* carried over is the reason it uses `defusedxml`: the XML is attacker-controlled.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_qs2_coverage.py`:

```python
"""QS2: coverage without running the suite (D12). A committed report when
there is one, BrownKit's tested_files/significant_files proxy when there is
not -- and never a bare percentage."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_COVERAGE,
    Confidence,
    ScanSignalId,
    ScanUpstream,
    TestFileRecord,
    TestLevel,
)
from sdlc.assessment.scan.signals import coverage
from sdlc.measurement import CollectionState, Measurement

PATHS = [
    "src/payments/service.py",
    "src/payments/gateway.py",
    "src/payments/__init__.py",
    "tests/test_service.py",
]

REPORT = """<?xml version="1.0" ?>
<coverage line-rate="0.75">
  <packages><package name="payments"><classes>
    <class filename="src/payments/service.py" line-rate="0.9"/>
    <class filename="src/payments/gateway.py" line-rate="0.2"/>
  </classes></package></packages>
</coverage>
"""


def _qs1_ok() -> ScanUpstream:
    return ScanUpstream(
        tests=[
            TestFileRecord(
                path="tests/test_service.py",
                level=TestLevel.UNIT,
                rule="qs1_unit_by_elimination",
                mapping_rule="naming_convention",
                covers=["src/payments/service.py"],
                confidence=Confidence.MEDIUM,
            )
        ],
        collected={ScanSignalId.QS1: Measurement.measured(1.0)},
    )


def test_a_committed_report_is_read_per_file():
    out = coverage.evaluate(PATHS, {"coverage.xml": REPORT}, _qs1_ok())
    by_path = {r.path: r for r in out.coverage}
    assert by_path["src/payments/service.py"].covered.value == 90.0
    assert by_path["src/payments/service.py"].source == "report"
    assert by_path["src/payments/service.py"].tool == "cobertura"
    assert by_path["src/payments/service.py"].confidence is Confidence.HIGH


def test_the_proxy_is_used_when_no_report_is_committed():
    """BrownKit's own adaptation rule, and D12's consequence: running the
    suite would execute the assessed repository's code a second time."""
    out = coverage.evaluate(PATHS, {}, _qs1_ok())
    assert [r.scope for r in out.coverage] == ["package"]
    record = out.coverage[0]
    assert record.path == "src/payments"
    # one significant file of two is covered by a test (__init__.py is not
    # significant)
    assert record.covered.value == 50.0
    assert record.source == "proxy"
    assert record.confidence is Confidence.LOW


def test_the_proxy_is_unavailable_when_qs1_did_not_collect():
    """Section 5: a missing QS1 must not make QS2 read as zero coverage."""
    up = ScanUpstream(collected={ScanSignalId.QS1: Measurement.not_collected("QS1 timed out")})
    out = coverage.evaluate(PATHS, {}, up)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "QS1" in out.row.categories[C_COVERAGE].reason
    assert out.coverage == []


def test_a_report_is_used_even_when_qs1_degraded():
    """The report path does not depend on QS1 at all, so a QS1 failure must
    not suppress a coverage number the repository actually committed."""
    up = ScanUpstream(collected={ScanSignalId.QS1: Measurement.not_collected("QS1 timed out")})
    out = coverage.evaluate(PATHS, {"coverage.xml": REPORT}, up)
    assert out.row.collected.state is CollectionState.MEASURED
    assert all(r.source == "report" for r in out.coverage)


def test_a_non_finite_rate_is_unknown_not_measured():
    """The guard measure_coverage already carries, for the same reason: nan
    >= threshold is False, which fabricates a passing advisory."""
    bad = REPORT.replace('line-rate="0.9"', 'line-rate="nan"').replace(
        'line-rate="0.2"', 'line-rate="inf"'
    )
    out = coverage.evaluate(PATHS, {"coverage.xml": bad}, _qs1_ok())
    assert out.row.categories[C_COVERAGE].state is CollectionState.UNKNOWN
    assert out.coverage == []


def test_an_unparseable_report_falls_back_to_the_proxy():
    out = coverage.evaluate(PATHS, {"coverage.xml": "<not xml"}, _qs1_ok())
    assert all(r.source == "proxy" for r in out.coverage)


def test_output_is_byte_identical_across_input_orderings():
    reference = coverage.evaluate(PATHS, {}, _qs1_ok()).model_dump_json()
    assert coverage.evaluate(list(reversed(PATHS)), {}, _qs1_ok()).model_dump_json() == reference
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_qs2_coverage.py -v`
Expected: FAIL with `AttributeError: module … has no attribute 'evaluate'`

- [ ] **Step 3: Write `scan/signals/coverage.py`**

```python
"""QS2 -- coverage (FR-912), without running the suite.

D12 cut the suite run for two reasons that both still hold: executing the
assessed repository's tests would widen NFR-9's exposure past E-41's build
probe, and a suite run is not a pure function of the tree, so it could not be
memoized under D10 anyway.

So: parse a coverage report the repository COMMITTED, else compute BrownKit's
proxy from QS1's mapping and mark it `proxy` / LOW. Never a bare percentage --
a coverage record carries its source and its confidence (BrownKit's own
acceptance gate 5), which is what stops a proxy reading as a measurement.

The XML comes from an untrusted repository, so it is parsed with defusedxml --
the same guard measure_coverage carries, for the same reason. That activity is
NOT reused: it reads a worktree and averages a diff-scoped subset, while this
reads a blob at a pinned commit and reports per file.

Pure: paths, report text and the declared upstream in, records out.
"""

from __future__ import annotations

import math
import posixpath
import re
from collections.abc import Mapping, Sequence

import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException

from ....measurement import Measurement
from ..models import (
    C_COVERAGE,
    Confidence,
    CoverageRecord,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    SignalOutput,
    SignalSource,
    family_of,
)
from ..sources import SOURCE_EXTENSIONS
from ..testpaths import is_test_path

SIGNAL_ID = "QS2"
VERSION = 1

# Where a committed Cobertura report lives. Checked in this order; the first
# that parses wins, so a repository with several reports gets a deterministic
# answer.
REPORT_PATHS: tuple[str, ...] = (
    "coverage.xml",
    "cobertura.xml",
    "coverage/cobertura-coverage.xml",
    "reports/coverage.xml",
    "build/reports/cobertura/coverage.xml",
)

# Files that carry no logic to cover. Excluding them is BrownKit's
# "significant_files excludes DTOs, generated code, entry-point thin wrappers
# and configuration", ported as the deterministic subset of that rule.
_BARRELS: frozenset[str] = frozenset(
    {
        "__init__.py",
        "index.ts",
        "index.js",
        "index.tsx",
        "index.jsx",
        "mod.rs",
        "package-info.java",
    }
)
_GENERATED = re.compile(
    r"(^|/)(node_modules|vendor|dist|build|out|\.next|\.nuxt|target|"
    r"migrations|generated|__generated__|proto)/"
)


def _significant(path: str) -> bool:
    return (
        path.endswith(SOURCE_EXTENSIONS)
        and not is_test_path(path)
        and posixpath.basename(path) not in _BARRELS
        and not _GENERATED.search(path)
    )


def _from_report(text: str) -> tuple[list[CoverageRecord], int] | None:
    """(records, non-finite count) from Cobertura XML, or None when it does
    not parse. A truncated report is a fallback to the proxy, not a crash."""
    try:
        root = DET.fromstring(text)
    except (DefusedXmlException, DET.ParseError, ValueError):
        return None
    records: list[CoverageRecord] = []
    non_finite = 0
    for cls in root.iter("class"):
        filename = cls.get("filename") or ""
        if not filename:
            continue
        try:
            rate = float(cls.get("line-rate", "0"))
        except ValueError:
            continue
        if not math.isfinite(rate):
            non_finite += 1
            continue
        records.append(
            CoverageRecord(
                scope="file",
                path=filename,
                covered=Measurement.measured(max(0.0, min(100.0, rate * 100.0))),
                source="report",
                tool="cobertura",
                confidence=Confidence.HIGH,
            )
        )
    return sorted(records, key=lambda r: r.path), non_finite


def _proxy(paths: Sequence[str], upstream: ScanUpstream) -> list[CoverageRecord]:
    """min(1.0, tested_files / significant_files) per package -- BrownKit's
    formula, over QS1's mapping."""
    covered = {p for record in upstream.tests for p in record.covers}
    packages: dict[str, list[str]] = {}
    for path in sorted(paths):
        if _significant(path):
            packages.setdefault(posixpath.dirname(path) or ".", []).append(path)
    out: list[CoverageRecord] = []
    for package in sorted(packages):
        files = packages[package]
        tested = sum(1 for f in files if f in covered)
        out.append(
            CoverageRecord(
                scope="package",
                path=package,
                covered=Measurement.measured(min(1.0, tested / len(files)) * 100.0),
                source="proxy",
                confidence=Confidence.LOW,
            )
        )
    return out


def _row(collected: Measurement) -> ScanSignalResult:
    return ScanSignalResult(
        signal=ScanSignalId.QS2,
        family=family_of(ScanSignalId.QS2),
        version=VERSION,
        source=SignalSource.COMPUTED,
        collected=collected,
        categories={C_COVERAGE: collected},
    )


def evaluate(
    paths: Sequence[str], reports: Mapping[str, str], upstream: ScanUpstream
) -> SignalOutput:
    """`reports` is path -> text for whichever of REPORT_PATHS the tree
    carries; `upstream` carries QS1's records and row state."""
    for path in REPORT_PATHS:
        if path not in reports:
            continue
        parsed = _from_report(reports[path])
        if parsed is None:
            continue  # fall through to the proxy
        records, non_finite = parsed
        if records:
            collected = Measurement.measured(float(len(records)))
            return SignalOutput(row=_row(collected), coverage=records)
        if non_finite:
            # An attempt DID produce output and it is uninterpretable: that
            # is unknown, not not_collected (FR-915's own distinction).
            return SignalOutput(
                row=_row(
                    Measurement.unknown(
                        f"coverage: {path} parsed but every line-rate was "
                        f"non-finite ({non_finite} class(es))"
                    )
                )
            )

    if not upstream.measured(ScanSignalId.QS1):
        return SignalOutput(
            row=_row(
                Measurement.not_collected(
                    f"coverage: no committed report in {list(REPORT_PATHS)} and the "
                    f"proxy needs QS1's mapping, which did not collect "
                    f"({upstream.gap(ScanSignalId.QS1, 'coverage').reason})"
                )
            )
        )

    records = _proxy(paths, upstream)
    if not records:
        return SignalOutput(
            row=_row(
                Measurement.not_collected(
                    "coverage: no committed report and no significant source file to "
                    "compute a proxy over"
                )
            )
        )
    collected = Measurement.measured(float(len(records)))
    return SignalOutput(row=_row(collected), coverage=records)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_qs2_coverage.py -v`
Expected: PASS

- [ ] **Step 5: Give QS2 a real activity body**

In `src/sdlc/assessment/activities.py`, import `coverage as coverage_signal` (the name `coverage` collides with nothing here but reads ambiguously beside the `CoverageReport` family), move `QS2` from `OWED_BY` to `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_coverage(inp: ScanSignalInput) -> SignalOutput:
    """QS2 -- a committed report, else QS1's proxy. NEVER runs the suite
    (D12). Wave 2: consumes QS1."""
    if (hit := memo.load(ScanSignalId.QS2, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        tracked = set(paths)
        reports = _blobs_for(
            inp.repo_dir, inp.commit_sha, [p for p in coverage_signal.REPORT_PATHS if p in tracked]
        )
        out = coverage_signal.evaluate(paths, reports, inp.upstream)
    except Exception as exc:  # noqa: BLE001
        _log.warning("QS2 failed: %s", exc)
        return failed_signal(ScanSignalId.QS2, exc)
    memo.store(ScanSignalId.QS2, inp.tree_hash, out, inp.upstream)
    return out
```

- [ ] **Step 6: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/signals/coverage.py \
        src/sdlc/assessment/activities.py tests/test_scan_qs2_coverage.py
git commit -m "feat(scan): QS2 coverage -- committed Cobertura report, else QS1's proxy, never a suite run (E-46 plan 3)"
```

---

### Task 8: SS1 — TLS enforcement and input validation

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/security_static.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_security_static` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_ss1_security_static.py` (create)

**Interfaces:**
- Consumes: `ScanUpstream` (S3's entry points), `models.inherited_pending`, `triage.models.evidence_key`.
- Produces: `evaluate(blobs, upstream) -> SignalOutput`, `VALIDATION_MARKERS: re.Pattern[str]` (Task 9 does **not** reuse it — SS3's rules are its own).

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_ss1_security_static.py`:

```python
"""SS1's computed half. The inherited half (credential storage from triage's
secrets, app-level auth from misconfig) is derived in workflow code and folded
in by fold_row -- this signal never touches it (D7)."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_AUTHN_AUTHZ,
    C_CREDENTIAL_STORAGE,
    C_INPUT_VALIDATION,
    C_TLS,
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    ScanUpstream,
    SourceCandidate,
)
from sdlc.assessment.scan.signals import security_static
from sdlc.measurement import CollectionState, Measurement

BLOBS = {
    "src/client.py": ("import requests\ndef fetch(u):\n    return requests.get(u, verify=False)\n"),
    # NOT example.com/org/net: those are IETF documentation domains and the
    # rule excludes them, so a fixture using one would assert the opposite of
    # what it reads as.
    "src/config.py": "BASE = 'http://api.internal.acme/v1'\n",
    "src/routes/orders.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/orders')\n"
        "def create(payload: dict):\n    return payload\n"
    ),
    "src/routes/payments.py": (
        "from fastapi import APIRouter\n"
        "from pydantic import BaseModel\n"
        "class Payment(BaseModel):\n    amount: int\n"
        "router = APIRouter()\n"
        "@router.post('/api/payments')\n"
        "def create(payload: Payment):\n    return payload\n"
    ),
}


def _upstream(s3_ok: bool = True) -> ScanUpstream:
    if not s3_ok:
        return ScanUpstream(collected={ScanSignalId.S3: Measurement.not_collected("S3 failed")})
    return ScanUpstream(
        sources=[
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-order",
                name="orders",
                rule="s3_http_route",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[
                    CandidateMember(
                        kind=MemberKind.HTTP_ROUTE,
                        value="POST /api/orders",
                        path="src/routes/orders.py",
                        line=3,
                    )
                ],
            ),
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id="S3-payment",
                name="payments",
                rule="s3_http_route",
                detail="d",
                confidence_contribution=Confidence.LOW,
                members=[
                    CandidateMember(
                        kind=MemberKind.HTTP_ROUTE,
                        value="POST /api/payments",
                        path="src/routes/payments.py",
                        line=6,
                    )
                ],
            ),
        ],
        collected={ScanSignalId.S3: Measurement.measured(2.0)},
    )


def test_disabled_certificate_verification_is_a_high_hint():
    out = security_static.evaluate(BLOBS, _upstream())
    tls = [o for o in out.security if o.category == C_TLS]
    rules = {o.rule for o in tls}
    assert "ss1_tls_verification_disabled" in rules
    finding = next(o for o in tls if o.rule == "ss1_tls_verification_disabled")
    assert finding.severity_hint == "high"
    assert finding.signal is ScanSignalId.SS1
    assert finding.evidence.strip().startswith("return requests.get")


def test_a_plaintext_url_is_recorded_and_localhost_is_not():
    out = security_static.evaluate(
        dict(BLOBS, **{"src/dev.py": "LOCAL = 'http://localhost:8000'\n"}), _upstream()
    )
    paths = {o.path for o in out.security if o.rule == "ss1_plaintext_http_url"}
    assert "src/config.py" in paths
    assert "src/dev.py" not in paths


def test_an_entry_point_without_a_validation_marker_is_recorded():
    out = security_static.evaluate(BLOBS, _upstream())
    missing = [o for o in out.security if o.category == C_INPUT_VALIDATION]
    assert {o.path for o in missing} == {"src/routes/orders.py"}
    assert missing[0].rule == "ss1_entry_point_without_validation"


def test_input_validation_is_a_gap_when_s3_did_not_collect():
    """Section 5: the dependent category reports not_collected naming S3, and
    never a zero -- 'no entry point lacks validation' would be a lie."""
    out = security_static.evaluate(BLOBS, _upstream(s3_ok=False))
    category = out.row.categories[C_INPUT_VALIDATION]
    assert category.state is CollectionState.NOT_COLLECTED
    assert "S3" in category.reason
    # TLS is independent of S3 and still measured.
    assert out.row.categories[C_TLS].state is CollectionState.MEASURED
    assert not any(o.category == C_INPUT_VALIDATION for o in out.security)


def test_the_two_inherited_categories_are_declared_as_pending():
    """D7: a row must declare every category it owes, and the activity
    computes only its own half."""
    out = security_static.evaluate(BLOBS, _upstream())
    for key in (C_CREDENTIAL_STORAGE, C_AUTHN_AUTHZ):
        assert out.row.categories[key].state is CollectionState.NOT_COLLECTED
        assert "D7" in out.row.categories[key].reason


def test_output_is_byte_identical_across_input_orderings():
    reference = security_static.evaluate(BLOBS, _upstream()).model_dump_json()
    reordered = dict(reversed(list(BLOBS.items())))
    assert security_static.evaluate(reordered, _upstream()).model_dump_json() == reference
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_ss1_security_static.py -v`
Expected: FAIL with `AttributeError: module … has no attribute 'evaluate'`

- [ ] **Step 3: Write `scan/signals/security_static.py`**

```python
"""SS1 -- static security signals, computed half (FR-912).

Two categories here; two more are inherited from triage and folded in by the
workflow (D2/D7): credential storage from `secrets`, app-level authentication
from `misconfig`. This module never touches those -- one implementation per
signal, cited rather than copied (FR-902, extended cross-tier).

  * tls_enforcement   -- a function of the tree alone.
  * input_validation  -- a function of S3's entry points: does the file that
                         declares a route show a validation marker? When S3
                         did not collect, this category reports not_collected
                         naming S3, never a zero (section 5, D5).

`severity_hint`, never `severity`: deciding what a missing validator is worth
is E-49's job, and deciding whether a route SHOULD be authenticated is
explicitly out of scope (spec section 10).

Pure: blobs and the declared upstream in, records out.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from ....measurement import Measurement
from ....triage.models import evidence_key
from ..models import (
    C_AUTHN_AUTHZ,
    C_CREDENTIAL_STORAGE,
    C_INPUT_VALIDATION,
    C_TLS,
    Confidence,
    ScanSignalId,
    ScanSignalResult,
    ScanUpstream,
    SecurityObservation,
    SignalOutput,
    SignalSource,
    family_of,
    inherited_pending,
)

SIGNAL_ID = "SS1"
VERSION = 1

_MAX_EVIDENCE = 400

# (rule, severity_hint, confidence, pattern, detail)
TLS_RULES: tuple[tuple[str, str, Confidence, re.Pattern[str], str], ...] = (
    (
        "ss1_tls_verification_disabled",
        "high",
        Confidence.HIGH,
        re.compile(
            r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false"
            r"|InsecureSkipVerify\s*:\s*true|_create_unverified_context\s*\("
            r"|CURLOPT_SSL_VERIFYPEER\s*,\s*(?:false|0)"
            r"|ServerCertificateValidationCallback"
        ),
        "Certificate verification is switched off, so the connection is "
        "authenticated against nothing.",
    ),
    (
        "ss1_weak_tls_version",
        "medium",
        Confidence.HIGH,
        re.compile(
            r"PROTOCOL_TLSv1(?:_1)?\b|SSLv[23]\b|VersionTLS1[01]\b"
            r"|SecurityProtocolType\.(?:Ssl3|Tls|Tls11)\b"
        ),
        "A TLS version below 1.2 is selected explicitly.",
    ),
    (
        "ss1_plaintext_http_url",
        "medium",
        Confidence.MEDIUM,
        re.compile(
            r"""['"]http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]"""
            r"""|example\.(?:com|org|net)|schemas?\.|www\.w3\.org)"""
        ),
        "A cleartext http:// endpoint is hardcoded.",
    ),
)

# Markers that SOME validation happens in a file. Presence-based, deliberately:
# whether the validation is CORRECT is semantic analysis, and the spec puts
# that in E-49.
VALIDATION_MARKERS = re.compile(
    r"\bBaseModel\b|\bpydantic\b|@validator\b|@field_validator\b"
    r"|\bmarshmallow\b|\bcerberus\b|\bvoluptuous\b"
    r"|\bz\.(?:object|string|number)\s*\(|\bzod\b|class-validator"
    r"|\bjoi\b|\byup\b|express-validator"
    r"|@Valid\b|@Validated\b|FluentValidation|DataAnnotations"
    r"|\bvalidator\.\w+\(|\bvalidate\w*\s*\("
)


def _observation(
    category: str,
    rule: str,
    severity: str,
    confidence: Confidence,
    detail: str,
    path: str,
    line: int | None,
    quote: str,
) -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS1,
        category=category,
        rule=rule,
        detail=detail,
        severity_hint=severity,
        path=path,
        line=line,
        evidence=quote[:_MAX_EVIDENCE],
        key=evidence_key(quote[:_MAX_EVIDENCE]),
        confidence=confidence,
    )


def _tls(blobs: Mapping[str, str]) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for path in sorted(blobs):
        lines = blobs[path].splitlines()
        for index, line in enumerate(lines, start=1):
            for rule, severity, confidence, pattern, detail in TLS_RULES:
                if pattern.search(line):
                    out.append(
                        _observation(
                            C_TLS, rule, severity, confidence, detail, path, index, line.strip()
                        )
                    )
    return out


def _entry_point_files(upstream: ScanUpstream) -> dict[str, int | None]:
    """path -> the first entry-point line in it, over S3's members only."""
    out: dict[str, int | None] = {}
    for candidate in upstream.sources:
        if candidate.signal is not ScanSignalId.S3:
            continue
        for member in candidate.members:
            if not member.path:
                continue
            current = out.get(member.path)
            if member.path not in out or (
                member.line is not None and (current is None or member.line < current)
            ):
                out[member.path] = member.line
    return out


def _validation(blobs: Mapping[str, str], upstream: ScanUpstream) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for path, line in sorted(_entry_point_files(upstream).items()):
        text = blobs.get(path)
        if text is None or VALIDATION_MARKERS.search(text):
            continue
        lines = text.splitlines()
        quote = lines[line - 1].strip() if line and line <= len(lines) else path
        out.append(
            SecurityObservation(
                signal=ScanSignalId.SS1,
                category=C_INPUT_VALIDATION,
                rule="ss1_entry_point_without_validation",
                detail="This file declares an entry point and shows no schema or "
                "validator marker, so its input reaches the handler "
                "unchecked. Whether that matters is E-49's call.",
                severity_hint="medium",
                path=path,
                line=line,
                evidence=quote[:_MAX_EVIDENCE],
                key="",
                confidence=Confidence.MEDIUM,
            )
        )
    return out


def evaluate(blobs: Mapping[str, str], upstream: ScanUpstream) -> SignalOutput:
    """`blobs` is path -> text for readable source blobs; `upstream` carries
    S3's candidates and row state (P3-D4)."""
    tls = _tls(blobs)
    s3_ok = upstream.measured(ScanSignalId.S3)
    validation = _validation(blobs, upstream) if s3_ok else []

    observations = sorted(tls + validation, key=lambda o: (o.category, o.path, o.rule, o.line or 0))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS1,
            family=family_of(ScanSignalId.SS1),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=Measurement.measured(float(len(observations))),
            categories={
                C_TLS: Measurement.measured(float(len(tls))),
                C_INPUT_VALIDATION: (
                    Measurement.measured(float(len(validation)))
                    if s3_ok
                    else upstream.gap(ScanSignalId.S3, C_INPUT_VALIDATION)
                ),
                C_CREDENTIAL_STORAGE: inherited_pending(C_CREDENTIAL_STORAGE),
                C_AUTHN_AUTHZ: inherited_pending(C_AUTHN_AUTHZ),
            },
        ),
        security=observations,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_ss1_security_static.py -v`
Expected: PASS

- [ ] **Step 5: Give SS1 a real activity body**

In `src/sdlc/assessment/activities.py`, import `security_static`, move `SS1` from `OWED_BY` to `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_security_static(inp: ScanSignalInput) -> SignalOutput:
    """SS1 -- TLS enforcement and input validation. Wave 2: consumes S3."""
    if (hit := memo.load(ScanSignalId.SS1, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(inp.repo_dir, inp.commit_sha, paths, SOURCE_EXTENSIONS)
        out = security_static.evaluate(blobs, inp.upstream)
    except Exception as exc:  # noqa: BLE001
        _log.warning("SS1 failed: %s", exc)
        return failed_signal(ScanSignalId.SS1, exc)
    memo.store(ScanSignalId.SS1, inp.tree_hash, out, inp.upstream)
    return out
```

- [ ] **Step 6: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/signals/security_static.py \
        src/sdlc/assessment/activities.py tests/test_scan_ss1_security_static.py
git commit -m "feat(scan): SS1 TLS and input validation at S3's entry points (E-46 plan 3)"
```

---

### Task 9: SS3 — ports, environment divergence, database security, log masking

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/config_infra.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_config_infra` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_ss3_config_infra.py` (create)

**Interfaces:**
- Consumes: `models.inherited_pending`, `triage.models.evidence_key`.
- Produces: `is_config_path(path) -> bool`, `evaluate(blobs) -> SignalOutput`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_ss3_config_infra.py`:

```python
"""SS3's computed half: what the deployment declares about itself. The
framework-defaults category is triage's misconfig, cited not copied (D2)."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_DB_SECURITY,
    C_ENV_DIVERGENCE,
    C_EXPOSED_PORTS,
    C_FRAMEWORK_DEFAULTS,
    C_LOG_MASKING,
    ScanSignalId,
)
from sdlc.assessment.scan.signals import config_infra
from sdlc.measurement import CollectionState

BLOBS = {
    "Dockerfile": "FROM python:3.12\nEXPOSE 8000\nEXPOSE 5432\n",
    "docker-compose.yml": (
        "services:\n"
        "  db:\n"
        "    image: postgres:16\n"
        "    environment:\n"
        "      POSTGRES_HOST_AUTH_METHOD: trust\n"
        "    ports:\n"
        "      - '5432:5432'\n"
    ),
    ".env.development": "DEBUG=true\nDATABASE_URL=postgres://u:p@localhost/db?sslmode=disable\n",
    ".env.production": "DEBUG=true\n",
    "src/audit.py": "import logging\nlogging.info('token=%s', token)\n",
}


def test_exposed_ports_are_recorded_and_a_datastore_port_is_higher():
    out = config_infra.evaluate(BLOBS)
    ports = [o for o in out.security if o.category == C_EXPOSED_PORTS]
    assert {o.path for o in ports} == {"Dockerfile", "docker-compose.yml"}
    datastore = [o for o in ports if "5432" in o.evidence]
    assert datastore and all(o.severity_hint == "high" for o in datastore)


def test_database_security_rules_fire_on_the_compose_and_the_url():
    out = config_infra.evaluate(BLOBS)
    rules = {o.rule for o in out.security if o.category == C_DB_SECURITY}
    assert "ss3_db_trust_auth" in rules
    assert "ss3_db_ssl_disabled" in rules
    assert "ss3_db_credentials_in_url" in rules


def test_an_unsafe_value_in_a_production_env_file_is_recorded():
    out = config_infra.evaluate(BLOBS)
    unsafe = [o for o in out.security if o.rule == "ss3_unsafe_value_in_environment"]
    assert [o.path for o in unsafe] == [".env.production"]
    assert "DEBUG" in unsafe[0].detail


def test_a_key_present_in_one_environment_and_missing_in_another_is_recorded():
    out = config_infra.evaluate(BLOBS)
    missing = [o for o in out.security if o.rule == "ss3_env_key_missing"]
    assert any("DATABASE_URL" in o.detail for o in missing)
    assert all(o.path == ".env.production" for o in missing)


def test_divergence_needs_two_environment_files():
    """P3-D11: with one env file there is nothing to compare, which is
    unmeasurable rather than 'no divergence'."""
    out = config_infra.evaluate({".env": "DEBUG=true\n"})
    category = out.row.categories[C_ENV_DIVERGENCE]
    assert category.state is CollectionState.NOT_COLLECTED
    assert "two" in category.reason


def test_a_sensitive_value_reaching_a_log_call_is_recorded():
    out = config_infra.evaluate(BLOBS)
    logs = [o for o in out.security if o.category == C_LOG_MASKING]
    assert [o.path for o in logs] == ["src/audit.py"]


def test_a_tree_with_no_infrastructure_files_is_a_measured_zero_for_ports():
    """We read every config path in the tree; no EXPOSE anywhere is an
    answer, not a gap."""
    out = config_infra.evaluate({".env": "A=1\n", ".env.prod": "A=1\n"})
    assert out.row.categories[C_EXPOSED_PORTS].state is CollectionState.MEASURED
    assert out.row.categories[C_EXPOSED_PORTS].value == 0.0


def test_the_inherited_category_is_declared_as_pending():
    out = config_infra.evaluate(BLOBS)
    pending = out.row.categories[C_FRAMEWORK_DEFAULTS]
    assert pending.state is CollectionState.NOT_COLLECTED
    assert "D7" in pending.reason


def test_every_observation_declares_ss3():
    out = config_infra.evaluate(BLOBS)
    assert out.security
    assert all(o.signal is ScanSignalId.SS3 for o in out.security)


def test_is_config_path_selects_infrastructure_and_environment_files():
    for path in (
        "Dockerfile",
        "docker-compose.yml",
        ".env.production",
        "k8s/deployment.yaml",
        "infra/main.tf",
        "appsettings.Production.json",
    ):
        assert config_infra.is_config_path(path) is True
    assert config_infra.is_config_path("src/app.py") is False
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_ss3_config_infra.py -v`
Expected: FAIL with `AttributeError: module … has no attribute 'is_config_path'`

- [ ] **Step 3: Write `scan/signals/config_infra.py`**

```python
"""SS3 -- configuration and infrastructure, computed half (FR-912).

BrownKit reads (never executes) the deployment's own declarations. Four
categories here; framework defaults are triage's `misconfig`, inherited and
folded in by the workflow (D2/D7) rather than re-implemented.

  * exposed_ports   -- EXPOSE, compose port maps, k8s service types.
  * env_divergence  -- what one environment declares and another does not.
                       Needs TWO environment files: with one there is nothing
                       to compare, which is unmeasurable rather than "no
                       divergence" (P3-D11).
  * db_security     -- SSL, credential placement, trust auth, default admins.
  * log_masking     -- sensitive field names reaching a log call.

Log-masking scanning runs over source blobs as well as config, because a log
call lives in code -- so the activity hands this signal both, and
`is_config_path` decides which rules a path is eligible for.

Pure: blobs in, records out.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping

from ....measurement import Measurement
from ....triage.models import evidence_key
from ..models import (
    C_DB_SECURITY,
    C_ENV_DIVERGENCE,
    C_EXPOSED_PORTS,
    C_FRAMEWORK_DEFAULTS,
    C_LOG_MASKING,
    Confidence,
    ScanSignalId,
    ScanSignalResult,
    SecurityObservation,
    SignalOutput,
    SignalSource,
    family_of,
    inherited_pending,
)

SIGNAL_ID = "SS3"
VERSION = 1

_MAX_EVIDENCE = 400

_CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)Dockerfile[\w.-]*$"),
    re.compile(r"(^|/)docker-compose[\w.-]*\.ya?ml$"),
    re.compile(r"(^|/)\.env[\w.-]*$"),
    re.compile(r"(^|/)appsettings(\.\w+)?\.json$"),
    re.compile(r"(^|/)application(-[\w]+)?\.(ya?ml|properties)$"),
    re.compile(
        r"(^|/)(k8s|kubernetes|deploy|deployment|helm|charts)/.*"
        r"\.(ya?ml|tpl)$"
    ),
    re.compile(r"\.tf$|\.tfvars$|\.bicep$"),
    re.compile(r"(^|/)(nginx|haproxy)[\w.-]*\.conf$"),
)

_ENV_FILE = re.compile(
    r"(^|/)(\.env[\w.-]*|appsettings(\.\w+)?\.json"
    r"|application(-\w+)?\.(ya?ml|properties))$"
)
_PRODUCTION = re.compile(r"(?i)(prod|production|live)")

# Ports whose exposure is a materially different fact from exposing a web
# port: a datastore reachable from outside the deployment is the finding.
_DATASTORE_PORTS: frozenset[str] = frozenset(
    {
        "1433",
        "1521",
        "3306",
        "5432",
        "5984",
        "6379",
        "7000",
        "7001",
        "8086",
        "9042",
        "9200",
        "11211",
        "27017",
        "27018",
        "5672",
        "15672",
        "2379",
    }
)

_EXPOSE_RULES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "ss3_dockerfile_expose",
        re.compile(r"(?im)^\s*EXPOSE\s+(\d+)"),
        "The image declares this port.",
    ),
    (
        "ss3_compose_published_port",
        re.compile(r"""(?m)^\s*-\s*["']?(\d{2,5}):\d{2,5}["']?\s*$"""),
        "The compose file publishes this host port.",
    ),
    (
        "ss3_kubernetes_node_port",
        re.compile(r"(?m)^\s*nodePort:\s*(\d+)"),
        "A NodePort service publishes this port on every node.",
    ),
    (
        "ss3_kubernetes_load_balancer",
        re.compile(r"(?m)^\s*type:\s*(LoadBalancer)\s*$"),
        "A LoadBalancer service is addressable from outside the cluster.",
    ),
)

_DB_RULES: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "ss3_db_ssl_disabled",
        "high",
        re.compile(
            r"sslmode\s*=\s*(?:disable|allow)|[?&]ssl\s*=\s*false"
            r"|Encrypt\s*=\s*false|tls\s*=\s*false"
        ),
        "The database connection disables transport encryption.",
    ),
    (
        "ss3_db_credentials_in_url",
        "high",
        re.compile(
            r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)"
            r"://[^:/\s]+:[^@/\s]+@"
        ),
        "A database URL carries an inline username and password.",
    ),
    (
        "ss3_db_trust_auth",
        "critical",
        re.compile(
            r"POSTGRES_HOST_AUTH_METHOD\s*[:=]\s*[\"']?trust"
            r"|MYSQL_ALLOW_EMPTY_PASSWORD\s*[:=]\s*[\"']?(?:yes|true|1)"
            r"|ALLOW_EMPTY_PASSWORD\s*[:=]\s*[\"']?(?:yes|true|1)"
        ),
        "The database accepts connections without authenticating them.",
    ),
    (
        "ss3_db_default_admin_user",
        "medium",
        re.compile(
            r"POSTGRES_USER\s*[:=]\s*[\"']?postgres\b"
            r"|MONGO_INITDB_ROOT_USERNAME\s*[:=]\s*[\"']?(?:root|admin)\b"
            r"|MYSQL_USER\s*[:=]\s*[\"']?root\b"
        ),
        "The application connects as the database's default superuser.",
    ),
)

# Keys whose presence or value differs meaningfully between environments.
_SECURITY_KEY_FRAGMENTS: tuple[str, ...] = (
    "DEBUG",
    "SSL",
    "TLS",
    "VERIFY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "KEY",
    "ALLOWED_HOSTS",
    "CORS",
    "AUTH",
    "DATABASE_URL",
    "SENTRY",
    "LOG_LEVEL",
)

# (key fragment, unsafe value pattern, detail) -- checked only in a file whose
# name says production.
_UNSAFE_IN_PRODUCTION: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "DEBUG",
        re.compile(r"(?i)^(true|1|yes|on)$"),
        "DEBUG is enabled in a production configuration.",
    ),
    (
        "SSL",
        re.compile(r"(?i)^(false|0|no|off|disable[d]?|none)$"),
        "TLS is disabled in a production configuration.",
    ),
    (
        "TLS",
        re.compile(r"(?i)^(false|0|no|off|disable[d]?|none)$"),
        "TLS is disabled in a production configuration.",
    ),
    (
        "VERIFY",
        re.compile(r"(?i)^(false|0|no|off)$"),
        "Certificate verification is disabled in a production configuration.",
    ),
    (
        "ALLOWED_HOSTS",
        re.compile(r"^\s*\*\s*$"),
        "ALLOWED_HOSTS accepts every host in a production configuration.",
    ),
    ("CORS", re.compile(r"^\s*\*\s*$"), "CORS accepts every origin in a production configuration."),
)

_LOG_CALL = re.compile(
    r"(?i)\b(?:log(?:ger)?\.\w+|logging\.\w+|console\.(?:log|info|warn|error)"
    r"|print|fmt\.Print\w*)\s*\([^)\n]*"
    r"\b(password|passwd|secret|token|api[_-]?key|card|pan|cvv|ssn"
    r"|authorization|credential)\w*\b"
)

_KEY_VALUE = re.compile(r"""(?m)^\s*["']?([A-Za-z_][\w.\-]*)["']?\s*[:=]\s*["']?([^"'\n#]*)""")


def is_config_path(path: str) -> bool:
    """Whether SS3's configuration and infrastructure rules apply to a path.
    Log masking runs everywhere; everything else runs only here."""
    return any(pattern.search(path) for pattern in _CONFIG_PATTERNS)


def _observation(
    category: str,
    rule: str,
    severity: str,
    detail: str,
    path: str,
    line: int,
    quote: str,
    confidence: Confidence,
) -> SecurityObservation:
    return SecurityObservation(
        signal=ScanSignalId.SS3,
        category=category,
        rule=rule,
        detail=detail,
        severity_hint=severity,
        path=path,
        line=line,
        evidence=quote[:_MAX_EVIDENCE],
        key=evidence_key(quote[:_MAX_EVIDENCE]),
        confidence=confidence,
    )


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _ports(path: str, text: str) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for rule, pattern, detail in _EXPOSE_RULES:
        for match in pattern.finditer(text):
            value = match.group(1)
            severity = "high" if value in _DATASTORE_PORTS else "info"
            extra = (
                " This is a datastore port, which is a materially "
                "different exposure from a web port."
                if severity == "high"
                else ""
            )
            out.append(
                _observation(
                    C_EXPOSED_PORTS,
                    rule,
                    severity,
                    f"{detail}{extra}",
                    path,
                    _line_of(text, match.start()),
                    match.group(0).strip(),
                    Confidence.HIGH,
                )
            )
    return out


def _db(path: str, text: str) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    for rule, severity, pattern, detail in _DB_RULES:
        match = pattern.search(text)
        if match:
            out.append(
                _observation(
                    C_DB_SECURITY,
                    rule,
                    severity,
                    detail,
                    path,
                    _line_of(text, match.start()),
                    match.group(0).strip(),
                    Confidence.MEDIUM,
                )
            )
    return out


def _logs(path: str, text: str) -> list[SecurityObservation]:
    match = _LOG_CALL.search(text)
    if not match:
        return []
    return [
        _observation(
            C_LOG_MASKING,
            "ss3_sensitive_value_logged",
            "high",
            "A log call names a sensitive field, so the value may be written to "
            "wherever logs are forwarded. Whether it is masked at the sink is "
            "not readable from the tree.",
            path,
            _line_of(text, match.start()),
            match.group(0).strip(),
            Confidence.MEDIUM,
        )
    ]


def _env_keys(text: str) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for match in _KEY_VALUE.finditer(text):
        key = match.group(1).upper()
        if any(fragment in key for fragment in _SECURITY_KEY_FRAGMENTS):
            out.setdefault(key, (match.group(2).strip(), _line_of(text, match.start())))
    return out


def _divergence(env_files: dict[str, dict[str, tuple[str, int]]]) -> list[SecurityObservation]:
    out: list[SecurityObservation] = []
    declared = sorted({key for keys in env_files.values() for key in keys})
    for path in sorted(env_files):
        keys = env_files[path]
        for key in declared:
            if key in keys:
                continue
            out.append(
                _observation(
                    C_ENV_DIVERGENCE,
                    "ss3_env_key_missing",
                    "low",
                    f"{key} is declared in another environment file and absent "
                    f"here, so the two environments do not configure the same "
                    f"surface.",
                    path,
                    1,
                    f"{key} (absent)",
                    Confidence.MEDIUM,
                )
            )
        if not _PRODUCTION.search(posixpath.basename(path)):
            continue
        for key, (value, line) in sorted(keys.items()):
            for fragment, unsafe, detail in _UNSAFE_IN_PRODUCTION:
                if fragment in key and unsafe.match(value):
                    out.append(
                        _observation(
                            C_ENV_DIVERGENCE,
                            "ss3_unsafe_value_in_environment",
                            "high",
                            detail,
                            path,
                            line,
                            f"{key}={value}",
                            Confidence.HIGH,
                        )
                    )
    return out


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for readable config, infrastructure and source
    blobs. Config rules apply to config paths; log masking applies to all."""
    ports: list[SecurityObservation] = []
    database: list[SecurityObservation] = []
    logs: list[SecurityObservation] = []
    env_files: dict[str, dict[str, tuple[str, int]]] = {}

    for path in sorted(blobs):
        text = blobs[path]
        logs.extend(_logs(path, text))
        if not is_config_path(path):
            continue
        ports.extend(_ports(path, text))
        database.extend(_db(path, text))
        if _ENV_FILE.search(path):
            env_files[path] = _env_keys(text)

    divergence = _divergence(env_files) if len(env_files) > 1 else []
    if len(env_files) > 1:
        divergence_metric = Measurement.measured(float(len(divergence)))
    else:
        divergence_metric = Measurement.not_collected(
            f"env_divergence: {len(env_files)} environment file(s) found; "
            f"divergence needs at least two to compare, so this is "
            f"unmeasurable rather than absent (P3-D11)"
        )

    observations = sorted(
        ports + database + logs + divergence,
        key=lambda o: (o.category, o.path, o.rule, o.line or 0),
    )
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.SS3,
            family=family_of(ScanSignalId.SS3),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=Measurement.measured(float(len(observations))),
            categories={
                C_EXPOSED_PORTS: Measurement.measured(float(len(ports))),
                C_DB_SECURITY: Measurement.measured(float(len(database))),
                C_LOG_MASKING: Measurement.measured(float(len(logs))),
                C_ENV_DIVERGENCE: divergence_metric,
                C_FRAMEWORK_DEFAULTS: inherited_pending(C_FRAMEWORK_DEFAULTS),
            },
        ),
        security=observations,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_ss3_config_infra.py -v`
Expected: PASS

- [ ] **Step 5: Give SS3 a real activity body**

In `src/sdlc/assessment/activities.py`, import `config_infra`, move `SS3` from `OWED_BY` to `BUILT`, and replace the stub:

```python
@activity.defn
async def scan_config_infra(inp: ScanSignalInput) -> SignalOutput:
    """SS3 -- ports, env divergence, DB security, log masking.

    Reads config and infrastructure paths (which have no single extension)
    plus source blobs, because a log call lives in code.
    """
    if (hit := memo.load(ScanSignalId.SS3, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        wanted = sorted(
            {p for p in paths if config_infra.is_config_path(p) or p.endswith(SOURCE_EXTENSIONS)}
        )
        out = config_infra.evaluate(_blobs_for(inp.repo_dir, inp.commit_sha, wanted))
    except Exception as exc:  # noqa: BLE001
        _log.warning("SS3 failed: %s", exc)
        return failed_signal(ScanSignalId.SS3, exc)
    memo.store(ScanSignalId.SS3, inp.tree_hash, out)
    return out
```

- [ ] **Step 6: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/signals/config_infra.py \
        src/sdlc/assessment/activities.py tests/test_scan_ss3_config_infra.py
git commit -m "feat(scan): SS3 ports, env divergence, DB security and log masking (E-46 plan 3)"
```

---

### Task 10: QS4 — CI stages and environment drift

**Files:**
- Rewrite: `src/sdlc/assessment/scan/signals/ci.py`
- Modify: `src/sdlc/assessment/activities.py` (`scan_ci` body, `BUILT`, `OWED_BY`)
- Test: `tests/test_scan_qs4_ci.py` (create)

**Interfaces:**
- Consumes: `models.inherited_pending`, `yaml.safe_load`.
- Produces: `is_ci_path(path) -> bool`, `is_env_config_path(path) -> str`, `evaluate(paths, blobs) -> SignalOutput`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_qs4_ci.py`:

```python
"""QS4's computed half: what the pipeline does, and which environments the
repository declares on each side. ci_present is triage's baseline, inherited
and folded in by the workflow (D2/D7)."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_CI_PRESENT,
    C_CI_STAGES,
    C_ENV_DRIFT,
    TestLevel,
)
from sdlc.assessment.scan.signals import ci
from sdlc.measurement import CollectionState

WORKFLOW = """
name: ci
on: [push]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: ruff check .
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest -q
  e2e:
    runs-on: ubuntu-latest
    steps:
      - run: npx playwright test
  deploy:
    environment: production
    steps:
      - run: ./deploy.sh
"""

PATHS = [".github/workflows/ci.yml", ".env.production", ".env.staging", "src/app.py"]
BLOBS = {".github/workflows/ci.yml": WORKFLOW}


def test_every_job_becomes_a_stage_in_file_order():
    out = ci.evaluate(PATHS, BLOBS)
    assert [s.stage for s in out.ci] == ["lint", "test", "e2e", "deploy"]
    assert [s.order for s in out.ci] == [0, 1, 2, 3]


def test_a_job_that_runs_tests_declares_the_level_it_runs():
    out = ci.evaluate(PATHS, BLOBS)
    by_stage = {s.stage: s for s in out.ci}
    assert by_stage["test"].runs_tests is True
    assert by_stage["test"].test_levels == [TestLevel.UNIT]
    assert by_stage["e2e"].test_levels == [TestLevel.E2E]
    assert by_stage["lint"].runs_tests is False
    assert by_stage["lint"].test_levels == []


def test_a_deploy_job_names_its_environment():
    out = ci.evaluate(PATHS, BLOBS)
    deploy = next(s for s in out.ci if s.stage == "deploy")
    assert deploy.deploys_to == "production"


def test_blocking_is_not_collected_on_every_stage():
    """A required check is a branch-protection setting, not a tracked file."""
    out = ci.evaluate(PATHS, BLOBS)
    assert all(s.blocking.state is CollectionState.NOT_COLLECTED for s in out.ci)


def test_drift_is_computed_between_ci_and_config():
    """P3-D7: staging has a config file and no CI deploy job; production has
    both."""
    out = ci.evaluate(PATHS, BLOBS)
    by_name = {e.name: e for e in out.environments}
    assert by_name["production"].in_ci is True
    assert by_name["production"].in_config is True
    assert by_name["production"].drifted is False
    assert by_name["staging"].in_ci is False
    assert by_name["staging"].in_config is True
    assert by_name["staging"].drifted is True
    assert out.row.categories[C_ENV_DRIFT].value == 1.0


def test_drift_needs_a_ci_file_to_compare_against():
    """P3-D11: with no CI side there is nothing to compare, and E-56's
    declared scope is what would answer it instead."""
    out = ci.evaluate([".env.staging"], {})
    category = out.row.categories[C_ENV_DRIFT]
    assert category.state is CollectionState.NOT_COLLECTED
    assert "E-56" in category.reason


def test_an_unparseable_workflow_degrades_that_file_alone():
    blobs = {
        ".github/workflows/ci.yml": WORKFLOW,
        ".github/workflows/broken.yml": "jobs: [unbalanced\n",
    }
    out = ci.evaluate(PATHS + [".github/workflows/broken.yml"], blobs)
    assert [s.workflow for s in out.ci] == [".github/workflows/ci.yml"] * 4
    assert out.row.categories[C_CI_STAGES].state is CollectionState.MEASURED


def test_a_yaml_bomb_is_refused_rather_than_expanded():
    """P3-D8: safe_load does not execute code, but anchors still expand, and
    CI files come from an untrusted repository (NFR-9)."""
    bomb = "a: &a [x,x,x,x,x,x,x,x,x]\n" + "".join(
        f"{chr(98 + i)}: &{chr(98 + i)} [" + ",".join([f"*{chr(97 + i)}"] * 9) + "]\n"
        for i in range(8)
    )
    # 72 alias references, over MAX_ALIASES. Asserted on the guard itself:
    # the evaluate() assertion below would also pass if the document merely
    # parsed to something with no jobs, which is not what this test is about.
    assert ci._safe_yaml(bomb) is None
    out = ci.evaluate([".github/workflows/bomb.yml"], {".github/workflows/bomb.yml": bomb})
    assert out.ci == []
    assert out.row.categories[C_CI_STAGES].state is CollectionState.MEASURED


def test_a_gitlab_pipeline_is_parsed_too():
    blobs = {
        ".gitlab-ci.yml": (
            "stages: [build, test]\nunit:\n  stage: test\n  script:\n    - pytest -q\n"
        )
    }
    out = ci.evaluate([".gitlab-ci.yml"], blobs)
    assert [s.stage for s in out.ci] == ["unit"]
    assert out.ci[0].runs_tests is True


def test_the_inherited_category_is_declared_as_pending():
    out = ci.evaluate(PATHS, BLOBS)
    pending = out.row.categories[C_CI_PRESENT]
    assert pending.state is CollectionState.NOT_COLLECTED
    assert "D7" in pending.reason
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `pytest tests/test_scan_qs4_ci.py -v`
Expected: FAIL with `AttributeError: module … has no attribute 'evaluate'`

- [ ] **Step 3: Write `scan/signals/ci.py`**

```python
"""QS4 -- environment and CI signals, computed half (FR-912).

ci_present is triage's `baseline`, inherited and folded in by the workflow
(D2/D7). This module adds the two facts a boolean cannot carry: what the
pipeline's stages ARE, and which environments the repository declares on each
side.

Environment drift is CI-vs-CONFIG, not CI-vs-declared (P3-D7). BrownKit
compares against `qa_scope.environments`, which comes from /enrich -- E-56,
unbuilt. Rather than report the category permanently not_collected, drift is
computed between the two declarations the repository itself carries; when
there is no CI side at all the category says so and names E-56.

YAML is parsed with safe_load behind an expansion guard (P3-D8): safe_load
does not execute code, but anchors still expand, and a CI file comes from an
untrusted repository (NFR-9). A file that trips the guard, or that does not
parse, degrades ALONE -- the other workflows still report.

Pure: paths and blobs in, records out. Nothing here runs a pipeline.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence

import yaml

from ....measurement import Measurement
from ..models import (
    C_CI_PRESENT,
    C_CI_STAGES,
    C_ENV_DRIFT,
    CiStageRecord,
    EnvironmentRecord,
    EvidenceRef,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    TestLevel,
    family_of,
    inherited_pending,
)

SIGNAL_ID = "QS4"
VERSION = 1

# P3-D8's guard. A CI file larger than this, or with more alias references
# than this, is refused rather than expanded.
MAX_CI_BYTES = 256_000
MAX_ALIASES = 50
_ALIAS = re.compile(r"(?m)(?<![\w*])\*[A-Za-z_][\w-]*")

_CI_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"),
    re.compile(r"(^|/)\.gitlab-ci\.ya?ml$"),
    re.compile(r"(^|/)azure-pipelines\.ya?ml$"),
    re.compile(r"(^|/)\.circleci/config\.ya?ml$"),
    re.compile(r"(^|/)\.travis\.ya?ml$"),
    re.compile(r"(^|/)Jenkinsfile$"),
)

# The environment names a drift comparison is meaningful over. A free-form
# name would make every directory an "environment".
ENVIRONMENT_NAMES: frozenset[str] = frozenset(
    {
        "dev",
        "development",
        "test",
        "testing",
        "qa",
        "uat",
        "stage",
        "staging",
        "preprod",
        "pre-production",
        "prod",
        "production",
        "sandbox",
        "demo",
    }
)

_ENV_CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|/)\.env\.([A-Za-z0-9_-]+)$"),
    re.compile(r"(^|/)appsettings\.([A-Za-z]+)\.json$"),
    re.compile(r"(^|/)application-([A-Za-z0-9]+)\.(?:ya?ml|properties)$"),
    re.compile(r"(^|/)config/([A-Za-z0-9]+)\.(?:ya?ml|json|toml)$"),
    re.compile(
        r"(^|/)(?:k8s|kubernetes|deploy|overlays|helm)/"
        r"([A-Za-z0-9]+)/"
    ),
)

_TEST_CMD = re.compile(
    r"(?i)\b(pytest|tox\b|npm (?:run )?test|yarn test|pnpm test|go test"
    r"|mvn\b[^\n]*\btest|gradle\b[^\n]*\btest|jest|vitest|cargo test"
    r"|dotnet test|rspec|phpunit|playwright test|cypress run)"
)

# (level, pattern). Ordered: the strongest claim first, same rule as QS1's.
_LEVEL_HINTS: tuple[tuple[TestLevel, re.Pattern[str]], ...] = (
    (TestLevel.E2E, re.compile(r"(?i)\b(e2e|playwright|cypress|selenium)\b")),
    (TestLevel.PERFORMANCE, re.compile(r"(?i)\b(k6|locust|gatling|jmeter)\b")),
    (TestLevel.CONTRACT, re.compile(r"(?i)\b(pact|contract-test)\b")),
    (TestLevel.INTEGRATION, re.compile(r"(?i)\bintegration\b")),
)

_JENKINS_STAGE = re.compile(r"""stage\s*\(\s*['"]([^'"]+)['"]\s*\)""")


def is_ci_path(path: str) -> bool:
    return any(pattern.search(path) for pattern in _CI_PATTERNS)


def is_env_config_path(path: str) -> str:
    """The environment a config path names, or "" when it names none."""
    for pattern in _ENV_CONFIG_PATTERNS:
        match = pattern.search(path)
        if match:
            name = match.groups()[-1].lower()
            if name in ENVIRONMENT_NAMES:
                return name
    return ""


def _safe_yaml(text: str) -> dict | None:
    """A parsed mapping, or None when the document is too large, too
    alias-heavy, unparseable, or simply not a mapping (P3-D8)."""
    if len(text.encode("utf-8", "replace")) > MAX_CI_BYTES:
        return None
    if len(_ALIAS.findall(text)) > MAX_ALIASES:
        return None
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return doc if isinstance(doc, dict) else None


def _unreadable_blocking() -> Measurement:
    return Measurement.not_collected(
        "required checks are a branch-protection setting, not a tracked "
        "file, so they are not readable at a pinned commit (E-59)"
    )


def _levels(text: str, runs_tests: bool) -> list[TestLevel]:
    if not runs_tests:
        return []
    for level, pattern in _LEVEL_HINTS:
        if pattern.search(text):
            return [level]
    return [TestLevel.UNIT]


def _step_text(job: dict) -> str:
    steps = job.get("steps")
    parts: list[str] = []
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                parts.extend(str(step.get(k, "")) for k in ("run", "uses", "name"))
            elif isinstance(step, str):
                parts.append(step)
    script = job.get("script")
    if isinstance(script, list):
        parts.extend(str(s) for s in script)
    elif isinstance(script, str):
        parts.append(script)
    return "\n".join(p for p in parts if p)


def _environment(job: dict) -> str:
    value = job.get("environment")
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        return str(value.get("name", "")).strip().lower()
    return ""


def _jobs(doc: dict) -> list[tuple[str, dict]]:
    """(name, job) pairs. GitHub nests them under `jobs`; GitLab puts them at
    the top level, where a job is any mapping carrying a `script`."""
    jobs = doc.get("jobs")
    if isinstance(jobs, dict):
        return [(str(name), job) for name, job in jobs.items() if isinstance(job, dict)]
    return [
        (str(name), job) for name, job in doc.items() if isinstance(job, dict) and "script" in job
    ]


def _stages_from_yaml(path: str, text: str) -> list[CiStageRecord]:
    doc = _safe_yaml(text)
    if doc is None:
        return []
    out: list[CiStageRecord] = []
    for order, (name, job) in enumerate(_jobs(doc)):
        body = _step_text(job)
        runs_tests = bool(_TEST_CMD.search(body))
        out.append(
            CiStageRecord(
                workflow=path,
                stage=name,
                order=order,
                runs_tests=runs_tests,
                test_levels=_levels(f"{name}\n{body}", runs_tests),
                deploys_to=_environment(job),
                blocking=_unreadable_blocking(),
            )
        )
    return out


def _stages_from_jenkinsfile(path: str, text: str) -> list[CiStageRecord]:
    matches = list(_JENKINS_STAGE.finditer(text))
    out: list[CiStageRecord] = []
    for order, match in enumerate(matches):
        end = matches[order + 1].start() if order + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        runs_tests = bool(_TEST_CMD.search(body))
        out.append(
            CiStageRecord(
                workflow=path,
                stage=match.group(1),
                order=order,
                runs_tests=runs_tests,
                test_levels=_levels(f"{match.group(1)}\n{body}", runs_tests),
                blocking=_unreadable_blocking(),
            )
        )
    return out


def evaluate(paths: Sequence[str], blobs: Mapping[str, str]) -> SignalOutput:
    """`paths` is every tracked path (the config side of the drift
    comparison); `blobs` is path -> text for the CI files that were read."""
    ci_paths = sorted(p for p in paths if is_ci_path(p))
    stages: list[CiStageRecord] = []
    for path in ci_paths:
        text = blobs.get(path)
        if text is None:
            continue
        if posixpath.basename(path) == "Jenkinsfile":
            stages.extend(_stages_from_jenkinsfile(path, text))
        else:
            stages.extend(_stages_from_yaml(path, text))
    stages.sort(key=lambda s: (s.workflow, s.order, s.stage))

    in_ci = {s.deploys_to for s in stages if s.deploys_to}
    in_config: dict[str, list[str]] = {}
    for path in sorted(paths):
        name = is_env_config_path(path)
        if name:
            in_config.setdefault(name, []).append(path)

    environments = [
        EnvironmentRecord(
            name=name,
            in_ci=name in in_ci,
            in_config=name in in_config,
            evidence=[EvidenceRef(path=p) for p in in_config.get(name, [])],
        )
        for name in sorted(in_ci | set(in_config))
    ]

    if ci_paths:
        drift = Measurement.measured(float(sum(1 for e in environments if e.drifted)))
    else:
        drift = Measurement.not_collected(
            "env_drift: no CI configuration in the tree, so there is no "
            "pipeline side to compare the committed environment configs "
            "against (P3-D11). The declared-scope comparison BrownKit makes "
            "needs /enrich's qa_scope, which is E-56"
        )

    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.QS4,
            family=family_of(ScanSignalId.QS4),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=Measurement.measured(float(len(stages))),
            categories={
                C_CI_STAGES: Measurement.measured(float(len(stages))),
                C_ENV_DRIFT: drift,
                C_CI_PRESENT: inherited_pending(C_CI_PRESENT),
            },
        ),
        ci=stages,
        environments=environments,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_qs4_ci.py -v`
Expected: PASS

- [ ] **Step 5: Give QS4 a real activity body**

In `src/sdlc/assessment/activities.py`, import `ci as ci_signal`, move `QS4` from `OWED_BY` to `BUILT` (leaving `OWED_BY` empty), and replace the stub:

```python
@activity.defn
async def scan_ci(inp: ScanSignalInput) -> SignalOutput:
    """QS4 -- CI stages and environment drift. Reads the pipeline files; the
    config side of the drift comparison comes from the path list alone."""
    if (hit := memo.load(ScanSignalId.QS4, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        out = ci_signal.evaluate(
            paths,
            _blobs_for(inp.repo_dir, inp.commit_sha, [p for p in paths if ci_signal.is_ci_path(p)]),
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("QS4 failed: %s", exc)
        return failed_signal(ScanSignalId.QS4, exc)
    memo.store(ScanSignalId.QS4, inp.tree_hash, out)
    return out
```

- [ ] **Step 6: Run the scan suite**

Run: `pytest tests/test_scan_*.py tests/test_assessment_*.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/signals/ci.py src/sdlc/assessment/activities.py \
        tests/test_scan_qs4_ci.py
git commit -m "feat(scan): QS4 CI stages and CI-vs-config environment drift (E-46 plan 3)"
```

---

### Task 11: Close-out — summary, whole-set properties, and the roadmap

**Files:**
- Modify: `src/sdlc/assessment/scan/summary.py`
- Modify: `src/sdlc/assessment/activities.py` (assert `OWED_BY` is empty at import)
- Test: `tests/test_scan_summary.py` (extend)
- Test: `tests/test_scan_determinism.py` (extend to the whole signal set)
- Test: `tests/test_scan_rules_sha.py` (extend for `testpaths`)
- Test: `tests/test_scan_stub_activities.py` (the stub list is now empty — assert that)
- Test: `tests/test_assessment_workflow_e2e.py` (assert thirteen rows, none naming a plan)
- Modify: `ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md` (status line)

- [ ] **Step 1: Write the failing tests for the operator surface and the whole-set properties**

Append to `tests/test_scan_summary.py`:

```python
# --- plan 3: the counts BrownKit's scan reports -----------------------------


def test_the_summary_reports_the_coverage_source_and_headline():
    """Spec section 8: 'report <tool>' vs 'proxy' is the line that tells an
    operator whether the number is a measurement or an estimate."""
    from sdlc.assessment.scan.models import Confidence, CoverageRecord
    from sdlc.measurement import Measurement

    scan = _scan_result(
        coverage=[
            CoverageRecord(
                scope="package",
                path="src/a",
                covered=Measurement.measured(40.0),
                source="proxy",
                confidence=Confidence.LOW,
            ),
            CoverageRecord(
                scope="package",
                path="src/b",
                covered=Measurement.measured(60.0),
                source="proxy",
                confidence=Confidence.LOW,
            ),
        ]
    )
    out = render_scan_summary(scan)
    assert "coverage: proxy" in out
    assert "50.0%" in out


def test_the_summary_counts_security_observations_per_category():
    from sdlc.assessment.scan.models import (
        C_TLS,
        Confidence,
        ScanSignalId,
        SecurityObservation,
    )

    scan = _scan_result(
        security=[
            SecurityObservation(
                signal=ScanSignalId.SS1,
                category=C_TLS,
                rule="r",
                detail="d",
                severity_hint="high",
                path="p",
                confidence=Confidence.HIGH,
            )
        ]
    )
    out = render_scan_summary(scan)
    assert "tls_enforcement: 1" in out


def test_the_summary_names_drifted_environments():
    from sdlc.assessment.scan.models import EnvironmentRecord

    scan = _scan_result(
        environments=[
            EnvironmentRecord(name="staging", in_ci=False, in_config=True),
            EnvironmentRecord(name="production", in_ci=True, in_config=True),
        ]
    )
    out = render_scan_summary(scan)
    assert "staging" in out
    assert "environment drift" in out
```

Add the helper the three tests above use, beside the file's existing `_row` / `_result`:

```python
def _scan_result(**payload) -> ScanResult:
    """Every row MEASURED, so a payload is representable at all
    (_unmeasured_carries_no_payload), and each test states only the payload it
    is about."""
    return ScanResult(signals=[_row(s, True) for s in SCAN_ORDER], **payload)
```

and reword the file's `_row` fallback reason — `f"{sid.value} not implemented (plan 3)"` is a string no signal can produce any more, and a fixture that says it teaches the wrong shape:

```python
m = (
    Measurement.measured(1.0)
    if measured
    else Measurement.not_collected(f"{sid.value} activity failed")
)
```

Append to `tests/test_scan_determinism.py`:

```python
def test_every_pure_signal_module_is_order_independent():
    """NFR-10 over the whole set, not only the capability chain: each signal
    is a pure function of its inputs, so shuffling those inputs must not
    change a byte of the artifact."""
    import random

    from sdlc.assessment.scan.models import ScanUpstream
    from sdlc.assessment.scan.signals import (
        ci,
        config_infra,
        coverage,
        frontend,
        schema,
        security_static,
        sensitivity,
        testability,
        tests_inventory,
    )
    from sdlc.measurement import Measurement

    tree = {
        "package.json": '{"dependencies": {"next": "14.0.0"}}',
        "app/orders/page.tsx": "export default function P() {}\n",
        "migrations/0001.sql": "CREATE TABLE orders (id SERIAL, email TEXT);\n",
        "src/service.py": "import datetime\nx = datetime.datetime.now()\n",
        "tests/test_service.py": "import pytest\ndef test_x(): ...\n",
        ".env.production": "DEBUG=true\n",
        ".env.staging": "DEBUG=false\nSSL=true\n",
        ".github/workflows/ci.yml": "jobs:\n  test:\n    steps:\n      - run: pytest\n",
    }
    paths = sorted(tree)
    up = ScanUpstream(
        collected={
            s: Measurement.measured(1.0)
            for s in (ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.QS1)
        }
    )

    cases = [
        ("S2", lambda t, p: schema.evaluate(t)),
        ("S4", lambda t, p: frontend.evaluate(t)),
        ("SS1", lambda t, p: security_static.evaluate(t, up)),
        ("SS3", lambda t, p: config_infra.evaluate(t)),
        ("SS4", lambda t, p: sensitivity.evaluate(t, up)),
        ("QS1", lambda t, p: tests_inventory.evaluate(p, t)),
        ("QS2", lambda t, p: coverage.evaluate(p, {}, up)),
        ("QS3", lambda t, p: testability.evaluate(t)),
        ("QS4", lambda t, p: ci.evaluate(p, t)),
    ]
    for name, run in cases:
        reference = run(tree, paths).model_dump_json()
        for seed in range(3):
            items = list(tree.items())
            shuffled_paths = list(paths)
            random.Random(seed).shuffle(items)
            random.Random(seed).shuffle(shuffled_paths)
            assert run(dict(items), shuffled_paths).model_dump_json() == reference, name
```

Append to `tests/test_scan_rules_sha.py`:

```python
def test_the_testpaths_module_reaches_all_four_of_its_consumers(monkeypatch):
    """P3-D9: S2, QS1, QS2 and QS3 all decide what a test file is with the
    same table, so editing a glob must move all four keys."""
    testpaths = "sdlc.assessment.scan.testpaths"
    for sid in (ScanSignalId.S2, ScanSignalId.QS1, ScanSignalId.QS2, ScanSignalId.QS3):
        assert testpaths in SCAN_SIGNALS[sid].rule_modules
        before = rules_sha(sid)
        monkeypatch.setattr(
            "sdlc.assessment.scan.rules.module_sha",
            lambda dotted: "edited" if dotted == testpaths else module_sha(dotted),
        )
        assert rules_sha(sid) != before, sid.value
        monkeypatch.setattr("sdlc.assessment.scan.rules.module_sha", module_sha)


def test_s3s_module_reaches_ss4_now_that_ss4_consumes_it(monkeypatch):
    """P3-D3: SS4 reads S3's candidates for accessed_by, so S3's bytes are
    part of SS4's key -- an undeclared read would also be an unhashed one."""
    s3_module = SCAN_SIGNALS[ScanSignalId.S3].module
    before = rules_sha(ScanSignalId.SS4)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == s3_module else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.SS4) != before
```

Replace the stub-list machinery in `tests/test_scan_stub_activities.py` — every body has landed, so the parametrized stub tests have nothing to run over. Keep the file, and make it assert the end state:

```python
def test_nothing_is_owed_any_more():
    """Plan 3's headline: OWED_BY is empty, so no scan row can name a plan.
    unbuilt_signal survives as the mechanism a FUTURE signal would use."""
    assert scan_acts.OWED_BY == {}
    assert scan_acts.BUILT == {s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity}


def test_unbuilt_signal_still_works_for_a_future_signal():
    """The discipline outlives its current users: a fourteenth signal added
    later reports not_collected naming its owner rather than a zero."""
    with pytest.raises(KeyError):
        scan_acts.unbuilt_signal(ScanSignalId.S1)  # nothing owes S1
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `pytest tests/test_scan_summary.py tests/test_scan_determinism.py tests/test_scan_rules_sha.py tests/test_scan_stub_activities.py -v`
Expected: FAIL — the summary lacks the new lines; the determinism import fails only if a signal module was skipped.

- [ ] **Step 3: Extend the operator summary**

In `src/sdlc/assessment/scan/summary.py`, add three blocks before the not-collected list (which stays last, because it is the line that matters):

```python
by_category: dict[str, int] = {}
for observation in scan.security:
    by_category[observation.category] = by_category.get(observation.category, 0) + 1
if by_category:
    lines.append("  security observations:")
    for category in sorted(by_category):
        lines.append(f"    {category}: {by_category[category]}")

if scan.tests:
    levels: dict[str, int] = {}
    for record in scan.tests:
        levels[record.level.value] = levels.get(record.level.value, 0) + 1
    mapped = sum(1 for r in scan.tests if r.mapping_rule != "unmapped")
    lines.append(
        f"  tests: {len(scan.tests)} file(s) "
        f"({', '.join(f'{k} {v}' for k, v in sorted(levels.items()))}); "
        f"{mapped} mapped to a subject"
    )

if scan.coverage:
    # BrownKit's own rule: a coverage number is meaningless without its
    # source, because a proxy and a measurement read the same.
    source = scan.coverage[0].source
    tool = scan.coverage[0].tool
    measured = [
        r.covered.value
        for r in scan.coverage
        if r.covered.state is CollectionState.MEASURED and r.covered.value is not None
    ]
    headline = f"{sum(measured) / len(measured):.1f}%" if measured else "no measured record"
    lines.append(
        f"  coverage: {source}{f' ({tool})' if tool else ''} "
        f"{headline} over {len(scan.coverage)} record(s)"
    )

drifted = [e.name for e in scan.environments if e.drifted]
if drifted:
    lines.append(f"  environment drift: {', '.join(sorted(drifted))} (declared on one side only)")
```

- [ ] **Step 4: Assert the end state at import**

In `src/sdlc/assessment/activities.py`, below `BUILT` / `OWED_BY`:

```python
def _assert_bodies_are_accounted_for() -> None:
    """A body that lands without its OWED_BY entry removed reports 'not
    implemented' forever; removing the entry without landing the body is a
    KeyError in unbuilt_signal. Asserted at import, not at the first
    assessment -- the discipline validate_registry applies to agents.yaml.
    """
    declared = {s for s, spec in SCAN_SIGNALS.items() if spec.activity}
    if BUILT | set(OWED_BY) != declared or (BUILT & set(OWED_BY)):
        raise RuntimeError(
            f"BUILT {sorted(s.value for s in BUILT)} and OWED_BY "
            f"{sorted(s.value for s in OWED_BY)} must partition the declared "
            f"activities {sorted(s.value for s in declared)}"
        )


_assert_bodies_are_accounted_for()
```

- [ ] **Step 5: Run the whole unit suite**

Run: `pytest`
Expected: PASS (the default marker set — unit only).

- [ ] **Step 6: Update the temporal e2e's scan assertions**

In `tests/test_assessment_workflow_e2e.py`, extend `test_scan_phase_flips_terminal_status_to_partial` with the end-state claim. The fake worker points the activities at `repo_dir="/r"`, which does not exist, so every tree-reading signal degrades — the point of the assertion is that it degrades as a *failure*, never as an unbuilt stub:

```python
    # Plan 3: every body has landed, so no row may name a plan. The fake
    # worker's repo_dir does not exist, so the tree-reading signals report
    # a FAILURE -- which is a different sentence from "not implemented", and
    # the two must not converge (failed_signal vs unbuilt_signal).
    assert len(result.scan.signals) == 13
    for row in result.scan.signals:
        assert "not implemented" not in (row.collected.reason or "")
        assert "plan" not in (row.collected.reason or "").lower()
```

Run: `pytest -m temporal tests/test_assessment_workflow_e2e.py -v`
Expected: PASS

- [ ] **Step 7: Run a real scan against a fixture repository**

The spec's §7 note applies: a scan tested only against fixtures written by its own author tests the author's assumptions. Point the CLI at a repository in `benchmarks/cases/` and read the summary:

```bash
python -m sdlc.cli assess --repo-dir benchmarks/cases/<a-case-with-a-frontend> --no-build-probe
```

Expected: a `scan:` block naming candidate counts, security observations per category, a coverage source, and an explicit `not collected` list. **Record anything surprising in the plan's notes rather than "fixing" it silently** — a signal reporting `not_collected` on a real repository is information, and the reason string is what says whether it is a gap in the repository or a gap in the rules.

- [ ] **Step 8: Update the roadmap and the spec status**

In `ROADMAP.md`:

1. **§11 E-46** — `[ ] ⚠️` → `[x]`, and rewrite the body's last two sentences to record plan 3 landing: all thirteen signals compute or inherit; `OWED_BY` is empty; the plan-3 decisions worth carrying are **P3-D3** (SS4 declares S3, because `accessed_by` cites it and an undeclared read is an unhashed input), **P3-D5** (a wave-2 signal is never memoized when its upstream degraded), **P3-D7** (env drift is CI-vs-config, because the declared-scope comparison needs E-56) and **P3-D12** (SS4 owns two categories so an empty `accessed_by` cannot read as "no entry point touches PII").
2. **§2 FR-912** — `[ ] ⚠️` → `[x]`. Keep the `rules_sha` note; add that cross-source confidence can now reach HIGH, because S2 and S4 produce.
3. **§2 FR-911** — the stub count stays five (discover/assess/report/generate/finish); update the scan sentence to "the scan phase's own thirteen signals all report".
4. **§1 stage 2 (context / Cartographer)** — add: S1–S5 is now the whole extraction half of `CodebaseMap`; FR-102 still needs E-47b/E-47c.
5. **§3 NFR-10** — the deterministic half is now asserted for every signal module, not only the capability chain.
6. **§3 NFR-9** — extend E-46's note: plan 3 adds no execution of repository code either; QS2 parses a committed report rather than running the suite, and QS4 parses pipeline files rather than running them.
7. **§8 / §15 item 3** — E-46 is done; the remainder is E-47b/E-47c.
8. **Header "Last verified"** — add `2026-08-13 (E-46 plan 3 against src/sdlc/assessment/scan/ + unit suite green)`.

In `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md`:

- Status line → `Design approved 2026-08-12; plans 1, 2 and 3 implemented`.
- §4's `SignalOutput` NOTE — append one line: the five payload types plan 3 added (`SecurityObservation`, `TestFileRecord`, `CoverageRecord`, `CiStageRecord`, `EnvironmentRecord`), and that `PAYLOAD_FIELD` became signal → tuple to carry QS4's two.
- §9's staging table — mark plan 3 delivered, and record the four decisions it added (P3-D3, P3-D5, P3-D7, P3-D12) beside plan 2's two.
- §10 — `MemberKind → SignalTier` remains out of scope; nothing changes there.

- [ ] **Step 9: Verify the claims before making them**

Run, and read the output rather than assuming it:

```bash
pytest
pytest -m temporal tests/test_assessment_workflow_e2e.py -v
ruff check src/sdlc/assessment src/sdlc/workflows/assessment.py
```

Expected: unit suite green, the assessment e2e green, no lint findings. If any command fails, the roadmap edit in Step 8 is not yet true — fix the code, not the claim.

- [ ] **Step 10: Commit**

```bash
git add src/sdlc/assessment/scan/summary.py src/sdlc/assessment/activities.py \
        tests/test_scan_summary.py tests/test_scan_determinism.py \
        tests/test_scan_rules_sha.py tests/test_scan_stub_activities.py \
        tests/test_assessment_workflow_e2e.py ROADMAP.md \
        docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md
git commit -m "feat(scan): close E-46 -- all thirteen signals report, summary and roadmap updated"
```

---

## Notes for the executor

- **The reason strings are the product.** Three helpers produce a `not_collected`, and they must never converge: `unbuilt_signal` (nobody has written this), `failed_signal` (we tried and could not), and a signal's own `_gap` (we looked and the input is not there). A reviewer should be able to tell which happened from the artifact alone.
- **When a pattern table gets a false positive on a real repository, prefer narrowing the pattern to adding an exception list.** A false PII finding is the first thing a client checks, and a table of exceptions is a table nobody maintains.
- **Do not add a category or a payload field without adding it to `CATEGORIES` / `PAYLOAD_FIELD` in the same commit.** Both are the single declaration their validators read, and a drifted one fails at import — which is the intent.
