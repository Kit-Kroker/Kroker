# E-50 Assessment Gate Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `UnifiedRiskMap` into a BLOCK/WARN/PASS verdict (FR-917), open a `GateHost` gate on BLOCK the way the FR-903 readiness gate does, and persist false-positive dispositions across re-runs as audited FR-304 decisions.

**Architecture:** A new pure package `src/sdlc/assessment/gates/` (checks + contracts) evaluates the risk map plus the discover-phase `CapabilityMap` plus persisted dispositions into a `RiskGateReport`. A new top-level package `src/sdlc/dispositions/` (mirroring `capability/` exactly) persists audited dispositions in the E-78 board's SQLite file, with a CLI-only recording surface. `AssessmentWorkflow` opens a `"risk"` gate right after `_assess` when the verdict is BLOCK; APPROVE stamps a per-run `RiskGateOverride` and lets REPORT/GENERATE/FINISH proceed, REJECT leaves them unreached.

**Tech Stack:** Python 3.11+, Pydantic v2, Temporal (`temporalio`), pytest, sqlite3.

**Spec:** `docs/superpowers/specs/2026-09-01-e50-assessment-gate-checks-design.md`

## Global Constraints

Copied verbatim from the spec; every task's requirements implicitly include this section.

- **Purity.** `assessment/gates/models.py` and `assessment/gates/checks.py` import only Pydantic, `measurement.py`, `gate.py`'s `CheckResult`/`CheckClass`, and pure-to-pure siblings (`risk.models`, `discover.map`, `scan.models`, `dispositions.models`). `dispositions/models.py` imports only Pydantic. **Never** `assessment/models.py`, `activities.py`, or `temporalio` from any of these four files. `dispositions/store.py`, `dispositions/cli.py`, and `assessment/activities.py`'s new activity are the impure siblings, exactly as `capability/store.py` is to `capability/models.py`.
- **FR-915: an unmeasured clause never reads as a pass.** A clause that could not be evaluated contributes no `CheckResult` at all and is named in `RiskGateReport.deferred` instead — never a `CheckResult` with some third `passed` state.
- **One `CheckResult` per CLAUSE, never per capability or per finding (GD5).** `detail` names every contributing `bc_id`/key so a single row stays self-describing.
- **Sorted-and-deduped is asserted, never repaired.** `RiskGateReport.checks` sorted by `.name`; `.deferred`/`.reasons` sorted-and-deduped string tuples. A producer emitting discovery order is an NFR-10 determinism bug; repairing it in a validator hides that bug.
- **No new `PhaseId` / DAG stage (GD1).** The roadmap states `/gate` is not a stage. `Assessment.gates` agrees with `Assessment.risk` being present, not with a `phases` row.
- **`terminal_status` is unchanged (GD2).** A rejected risk gate is represented by each skipped phase's own `Measurement.reason` naming FR-917, never a new top-level status constant.
- **Join keys.** `Vulnerability.key` (= `security_identity`) and `testability_identity()` (from `scan/models.py`) are the two join keys. `FindingDisposition`'s `(kind, key)` composite primary key — not prefix-sniffing — is what keeps the two finding families from colliding.
- **WARN never opens a gate and never notifies (GD4).** Only BLOCK does.
- **CLI, not HTTP, for dispositions (GD7).** Mirrors `capability/cli.py`'s OQ-11 reasoning exactly: an unauthenticated route cannot provide provenance for `approved_by` on an audited write.
- **Order-independence (NFR-10).** `assessment/gates/checks.py` carries its own byte-identical-across-input-order test in its own test file.
- **Test commands.** Unit: `pytest tests/<file> -v`. Full unit suite: `pytest -m "not temporal"`. Temporal e2e: `pytest -m temporal`.

---

### Task 1: `assessment/gates/models.py` — the verdict, the report, the override

**Files:**
- Create: `src/sdlc/assessment/gates/__init__.py`
- Create: `src/sdlc/assessment/gates/models.py`
- Test: `tests/test_gates_models.py`

**Interfaces:**
- Consumes: `sdlc.gate.CheckResult`, `sdlc.gate.CheckClass`
- Produces: `RiskGateVerdict(BLOCK|WARN|PASS)`; `RiskGateReport(verdict, checks: tuple[CheckResult, ...], deferred: tuple[str, ...], reasons: tuple[str, ...])`; `RiskGateOverride(approved_by: Literal["human","policy","timeout"], reviewer, reason, decided_at, gate_round)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gates_models.py
"""FR-917 (E-50): RiskGateReport's structural rules, and RiskGateOverride
mirrors ReadinessOverride field-for-field (GD5)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sdlc.assessment.gates.models import RiskGateOverride, RiskGateReport, RiskGateVerdict
from sdlc.gate import CheckClass, CheckResult


def _check(name: str, passed: bool = True) -> CheckResult:
    return CheckResult(name=name, passed=passed, classification=CheckClass.ABSOLUTE)


def test_a_pass_report_may_carry_no_checks_or_deferrals():
    r = RiskGateReport(verdict=RiskGateVerdict.PASS)
    assert r.checks == ()
    assert r.deferred == ()
    assert r.reasons == ()


def test_checks_must_be_sorted_by_name():
    with pytest.raises(ValidationError, match="sorted"):
        RiskGateReport(
            verdict=RiskGateVerdict.BLOCK,
            checks=(
                _check("risk_no_unaccepted_confirmed_vuln"),
                _check("risk_composite_below_threshold"),
            ),
        )


def test_duplicate_check_names_are_rejected():
    with pytest.raises(ValidationError, match="duplicate"):
        RiskGateReport(
            verdict=RiskGateVerdict.BLOCK,
            checks=(
                _check("risk_no_unaccepted_confirmed_vuln"),
                _check("risk_no_unaccepted_confirmed_vuln"),
            ),
        )


def test_deferred_must_be_sorted():
    with pytest.raises(ValidationError, match="not sorted and deduped"):
        RiskGateReport(verdict=RiskGateVerdict.PASS, deferred=("z", "a"))


def test_deferred_must_be_deduped():
    with pytest.raises(ValidationError, match="not sorted and deduped"):
        RiskGateReport(verdict=RiskGateVerdict.PASS, deferred=("a", "a"))


def test_reasons_must_be_sorted_and_deduped():
    with pytest.raises(ValidationError, match="not sorted and deduped"):
        RiskGateReport(verdict=RiskGateVerdict.BLOCK, reasons=("z", "a"))


def test_a_risk_gate_override_round_trips():
    o = RiskGateOverride(
        approved_by="human",
        reviewer="alice",
        reason="reviewed and accepted",
        decided_at=datetime.now(UTC),
        gate_round=1,
    )
    assert o.approved_by == "human"
    assert o.gate_round == 1


def test_a_risk_gate_override_rejects_an_unknown_approver_class():
    with pytest.raises(ValidationError):
        RiskGateOverride(
            approved_by="robot", reason="x", decided_at=datetime.now(UTC), gate_round=1
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gates_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.gates'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/assessment/gates/__init__.py
"""FR-917 (E-50): the risk gate — BLOCK/WARN/PASS over UnifiedRiskMap."""
```

```python
# src/sdlc/assessment/gates/models.py
"""FR-917 (E-50): the risk gate's own contracts.

Pure by design -- Pydantic, measurement.py and gate.py's CheckResult/
CheckClass only. This module must never import assessment/models.py,
activities.py, or temporalio, exactly as risk/models.py and discover/map.py
must not: a dependency here would appear as a reviewable import.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from ...gate import CheckResult


class RiskGateVerdict(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    PASS = "pass"


class RiskGateReport(BaseModel):
    """FR-917's trichotomy over UnifiedRiskMap + dispositions (GD4).

    `checks` carries at most three rows -- one per CLAUSE, never one per
    capability or per finding (GD5): a clause with nothing to decide
    contributes no row, never a row with some third `passed` state.
    `deferred` names every clause, or per-capability/per-finding instance,
    that could not be evaluated, so a PASS with a non-empty `deferred` is
    visibly different from a clean one (FR-915).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    verdict: RiskGateVerdict
    checks: tuple[CheckResult, ...] = ()
    deferred: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _checks_are_sorted(self) -> RiskGateReport:
        names = [c.name for c in self.checks]
        if names != sorted(names):
            raise ValueError(
                f"checks must be sorted by name, got {names} -- a producer "
                f"emitting discovery order is an NFR-10 determinism bug, and "
                f"repairing it here would hide that bug"
            )
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate check name in {names}")
        return self

    @model_validator(mode="after")
    def _deferred_and_reasons_are_sorted_and_deduped(self) -> RiskGateReport:
        for field_name in ("deferred", "reasons"):
            values = list(getattr(self, field_name))
            if values != sorted(set(values)):
                raise ValueError(
                    f"{field_name} {values} is not sorted and deduped -- a "
                    f"producer emitting evaluation order is an NFR-10 "
                    f"determinism bug, and repairing it here would hide "
                    f"that bug"
                )
        return self


class RiskGateOverride(BaseModel):
    """FR-304: an audited decision to proceed despite a BLOCK verdict, for
    THIS run only (GD10) -- field-for-field on triage/models.py's
    ReadinessOverride, for the same reason: local and pure, so a
    GateDecision cannot appear here and AssessmentWorkflow maps one to the
    other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    approved_by: Literal["human", "policy", "timeout"]
    reviewer: str | None = None
    reason: str
    decided_at: datetime
    gate_round: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gates_models.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/gates/__init__.py src/sdlc/assessment/gates/models.py tests/test_gates_models.py
git commit -m "feat(gates): RiskGateReport/RiskGateOverride contracts (E-50 FR-917/FR-304)"
```

---

### Task 2: `dispositions/models.py` — the audited finding disposition

**Files:**
- Create: `src/sdlc/dispositions/__init__.py`
- Create: `src/sdlc/dispositions/models.py`
- Test: `tests/test_dispositions_models.py`

**Interfaces:**
- Consumes: nothing beyond Pydantic
- Produces: `Disposition(FALSE_POSITIVE|MITIGATED_ELSEWHERE|ACCEPTED_RISK)`; `FindingDisposition(kind: Literal["vulnerability","testability"], key, disposition, approved_by, reason, decided_at)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispositions_models.py
"""FR-304 (E-50): FindingDisposition is an audited decision, and `kind` is
an explicit discriminator, not a key-prefix sniff (GD7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sdlc.dispositions.models import Disposition, FindingDisposition


def _fd(**kw) -> FindingDisposition:
    base = dict(
        kind="vulnerability",
        key="SS1:hardcoded-secret:src/a.py:",
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed, tolerated for this release",
        decided_at=datetime.now(UTC),
    )
    base.update(kw)
    return FindingDisposition(**base)


def test_round_trips_a_vulnerability_disposition():
    d = _fd()
    assert d.kind == "vulnerability"
    assert d.disposition is Disposition.ACCEPTED_RISK


def test_a_testability_disposition_uses_the_testability_identity_shape():
    d = _fd(kind="testability", key="QS3:static-clock-access:src/a.py:")
    assert d.kind == "testability"


def test_an_unattributed_disposition_is_refused():
    with pytest.raises(ValidationError, match="approved_by"):
        _fd(approved_by="")


def test_a_disposition_with_no_reason_is_refused():
    with pytest.raises(ValidationError, match="reason"):
        _fd(reason="   ")


def test_a_disposition_with_no_key_is_refused():
    with pytest.raises(ValidationError, match="key"):
        _fd(key="")


def test_kind_is_restricted_to_the_two_finding_families():
    with pytest.raises(ValidationError):
        _fd(kind="capability")


def test_disposition_has_exactly_the_three_fr917_values():
    assert {d.value for d in Disposition} == {
        "false_positive",
        "mitigated_elsewhere",
        "accepted_risk",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dispositions_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.dispositions'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/dispositions/__init__.py
"""FR-304/FR-917 (E-50): audited findings dispositions, persisted across
re-runs."""
```

```python
# src/sdlc/dispositions/models.py
"""FR-304/FR-917 (E-50): a false-positive disposition over one finding.

Pure by design -- Pydantic only. This module must never import
assessment/models.py, activities.py, or temporalio -- store.py is the one
impure sibling, exactly as capability/store.py is to capability/models.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Disposition(StrEnum):
    FALSE_POSITIVE = "false_positive"
    MITIGATED_ELSEWHERE = "mitigated_elsewhere"
    ACCEPTED_RISK = "accepted_risk"


class FindingDisposition(BaseModel):
    """One audited human decision over one finding. `kind` is an explicit
    discriminator rather than a prefix-sniff over `key`: Vulnerability.key
    (security_identity) and testability_identity() happen never to collide
    today, but a kind field makes that a stated invariant rather than an
    accident the store's row lookup silently relies on (GD7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["vulnerability", "testability"]
    key: str
    disposition: Disposition
    approved_by: str
    reason: str
    decided_at: datetime

    @model_validator(mode="after")
    def _audited(self) -> FindingDisposition:
        if not self.approved_by.strip():
            raise ValueError(
                "approved_by is required -- an unattributed disposition is not an audited one"
            )
        if not self.reason.strip():
            raise ValueError("reason is required")
        if not self.key.strip():
            raise ValueError("key is required")
        return self
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dispositions_models.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/dispositions/__init__.py src/sdlc/dispositions/models.py tests/test_dispositions_models.py
git commit -m "feat(dispositions): FindingDisposition, kind-discriminated (E-50 GD7)"
```

---

### Task 3: `dispositions/store.py` — the board-backed persistence

**Files:**
- Modify: `src/sdlc/board/schema.py`
- Create: `src/sdlc/dispositions/store.py`
- Test: `tests/test_dispositions_store.py`

**Interfaces:**
- Consumes: `sdlc.board.schema.apply_schema`, `sdlc.board.schema.connect`, `sdlc.board.schema.db_path`, `dispositions.models.FindingDisposition`, `dispositions.models.Disposition`
- Produces: `FindingDispositionStore` (ABC): `load(project) -> list[FindingDisposition]`; `registry_version(project) -> int`; `apply(project, disposition, *, expected_version, actor, operation="dispose", detail=None) -> int`. `BoardFindingDispositionStore(FindingDispositionStore)`; `FindingDispositionConflictError`; `FindingDispositionStoreError`

- [ ] **Step 1: Add the DDL**

Modify `src/sdlc/board/schema.py`: append three tables to the `DDL` string, right after the existing `capability_event` table and before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS finding_disposition_registry (
    project          TEXT PRIMARY KEY,
    registry_version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS finding_disposition (
    project     TEXT NOT NULL,
    kind        TEXT NOT NULL,
    key         TEXT NOT NULL,
    disposition TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    reason      TEXT NOT NULL,
    decided_at  TEXT NOT NULL,
    PRIMARY KEY (project, kind, key)
);

CREATE TABLE IF NOT EXISTS finding_disposition_event (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    project    TEXT NOT NULL,
    kind       TEXT NOT NULL,
    key        TEXT NOT NULL,
    actor      TEXT NOT NULL,
    operation  TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_dispositions_store.py
"""FR-304 (E-50): finding-disposition persistence, mirroring E-47a's
BoardIdentityStore discipline exactly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import (
    BoardFindingDispositionStore,
    FindingDispositionConflictError,
)


@pytest.fixture()
def store(tmp_path):
    s = BoardFindingDispositionStore(db=tmp_path / "board.sqlite3")
    yield s
    s.close()


def _fd(kind="vulnerability", key="SS1:hardcoded-secret:src/a.py:", **kw) -> FindingDisposition:
    base = dict(
        kind=kind,
        key=key,
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed, tolerated",
        decided_at=datetime.now(UTC),
    )
    base.update(kw)
    return FindingDisposition(**base)


def test_empty_project_loads_empty_at_version_zero(store):
    assert store.load("p") == []
    assert store.registry_version("p") == 0


def test_apply_round_trips_a_disposition(store):
    store.apply("p", _fd(), expected_version=0, actor="maks")
    (got,) = store.load("p")
    assert got.key == "SS1:hardcoded-secret:src/a.py:"
    assert got.disposition is Disposition.ACCEPTED_RISK


def test_apply_bumps_registry_version(store):
    assert store.apply("p", _fd(), expected_version=0, actor="maks") == 1
    assert store.apply("p", _fd(key="SS1:x:src/b.py:"), expected_version=1, actor="maks") == 2


def test_stale_expected_version_conflicts(store):
    store.apply("p", _fd(), expected_version=0, actor="maks")
    with pytest.raises(FindingDispositionConflictError):
        store.apply("p", _fd(key="SS1:x:src/b.py:"), expected_version=0, actor="maks")


def test_a_second_apply_on_the_same_kind_and_key_revises_it_not_accumulates(store):
    """A human revising a prior call, not a growing history of live rows."""
    store.apply("p", _fd(disposition=Disposition.FALSE_POSITIVE), expected_version=0, actor="maks")
    store.apply(
        "p",
        _fd(disposition=Disposition.ACCEPTED_RISK, reason="changed my mind"),
        expected_version=1,
        actor="maks",
    )
    rows = store.load("p")
    assert len(rows) == 1
    assert rows[0].disposition is Disposition.ACCEPTED_RISK


def test_two_applies_to_the_same_kind_and_key_leave_two_event_rows(store):
    """The spec's testing bullet: revising a disposition updates the live
    row but the audit trail keeps both events (mirrors capability_event)."""
    store.apply("p", _fd(disposition=Disposition.FALSE_POSITIVE), expected_version=0, actor="maks")
    store.apply(
        "p",
        _fd(disposition=Disposition.ACCEPTED_RISK, reason="changed my mind"),
        expected_version=1,
        actor="maks",
    )
    rows = store._conn.execute(
        "SELECT operation FROM finding_disposition_event WHERE project = ? AND kind = ? "
        "AND key = ? ORDER BY id",
        ("p", "vulnerability", "SS1:hardcoded-secret:src/a.py:"),
    ).fetchall()
    assert [r[0] for r in rows] == ["dispose", "dispose"]


def test_vulnerability_and_testability_dispositions_on_the_same_key_do_not_collide(store):
    """The (kind, key) composite primary key, not prefix sniffing, keeps
    the two finding families apart (GD7)."""
    store.apply("p", _fd(kind="vulnerability", key="SHARED"), expected_version=0, actor="maks")
    store.apply("p", _fd(kind="testability", key="SHARED"), expected_version=1, actor="maks")
    rows = {(r.kind, r.key): r for r in store.load("p")}
    assert len(rows) == 2


def test_projects_are_isolated(store):
    store.apply("p", _fd(), expected_version=0, actor="maks")
    assert store.load("other") == []


def test_load_returns_rows_sorted_by_kind_then_key(store):
    store.apply("p", _fd(kind="vulnerability", key="b"), expected_version=0, actor="maks")
    store.apply("p", _fd(kind="testability", key="a"), expected_version=1, actor="maks")
    store.apply("p", _fd(kind="vulnerability", key="a"), expected_version=2, actor="maks")
    assert [(r.kind, r.key) for r in store.load("p")] == [
        ("testability", "a"),
        ("vulnerability", "a"),
        ("vulnerability", "b"),
    ]


def test_reopening_the_same_db_sees_prior_state(tmp_path):
    db = tmp_path / "board.sqlite3"
    first = BoardFindingDispositionStore(db=db)
    first.apply("p", _fd(), expected_version=0, actor="maks")
    first.close()
    second = BoardFindingDispositionStore(db=db)
    assert [r.key for r in second.load("p")] == ["SS1:hardcoded-secret:src/a.py:"]
    second.close()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_dispositions_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.dispositions.store'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/sdlc/dispositions/store.py
"""FR-304/FR-917 (E-50): finding-disposition persistence.

ADR-19 -- adapters, not substrate. BoardFindingDispositionStore is the one
reference implementation, backed by the E-78 board's SQLite file and
reusing BoardIdentityStore's optimistic-concurrency discipline rather than
inventing a second scheme in the same database.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from ..board.schema import apply_schema, connect, db_path
from .models import Disposition, FindingDisposition


class FindingDispositionStoreError(Exception):
    """Base for finding-disposition write rejections."""


class FindingDispositionConflictError(FindingDispositionStoreError):
    """Optimistic-concurrency failure: caller's expected_version is stale."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class FindingDispositionStore(ABC):
    @abstractmethod
    def load(self, project: str) -> list[FindingDisposition]:
        """Every live disposition for the project, sorted by (kind, key)."""

    @abstractmethod
    def registry_version(self, project: str) -> int:
        """0 for a project that has never been written."""

    @abstractmethod
    def apply(
        self,
        project: str,
        disposition: FindingDisposition,
        *,
        expected_version: int,
        actor: str,
        operation: str = "dispose",
        detail: str | None = None,
    ) -> int:
        """Upsert one disposition, keyed on (project, kind, key). Returns
        the new registry_version."""


class BoardFindingDispositionStore(FindingDispositionStore):
    def __init__(self, db: str | os.PathLike | None = None) -> None:
        self._conn = connect(db if db is not None else db_path())
        apply_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    def load(self, project: str) -> list[FindingDisposition]:
        rows = self._conn.execute(
            "SELECT kind, key, disposition, approved_by, reason, decided_at "
            "FROM finding_disposition WHERE project = ? ORDER BY kind, key",
            (project,),
        ).fetchall()
        return [
            FindingDisposition(
                kind=r[0],
                key=r[1],
                disposition=Disposition(r[2]),
                approved_by=r[3],
                reason=r[4],
                decided_at=r[5],
            )
            for r in rows
        ]

    def registry_version(self, project: str) -> int:
        row = self._conn.execute(
            "SELECT registry_version FROM finding_disposition_registry WHERE project = ?",
            (project,),
        ).fetchone()
        return row[0] if row else 0

    def apply(
        self,
        project: str,
        disposition: FindingDisposition,
        *,
        expected_version: int,
        actor: str,
        operation: str = "dispose",
        detail: str | None = None,
    ) -> int:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            current = self.registry_version(project)
            if current != expected_version:
                raise FindingDispositionConflictError(
                    f"registry_version for '{project}' is {current}, caller "
                    f"expected {expected_version}; reload before disposing again"
                )
            self._conn.execute(
                "INSERT INTO finding_disposition_registry (project, registry_version) "
                "VALUES (?, 0) ON CONFLICT(project) DO NOTHING",
                (project,),
            )
            self._conn.execute(
                "INSERT INTO finding_disposition (project, kind, key, disposition, "
                "approved_by, reason, decided_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(project, kind, key) DO UPDATE SET "
                "disposition=excluded.disposition, approved_by=excluded.approved_by, "
                "reason=excluded.reason, decided_at=excluded.decided_at",
                (
                    project,
                    disposition.kind,
                    disposition.key,
                    disposition.disposition.value,
                    disposition.approved_by,
                    disposition.reason,
                    disposition.decided_at.isoformat(),
                ),
            )
            self._conn.execute(
                "INSERT INTO finding_disposition_event (project, kind, key, actor, "
                "operation, detail, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    project,
                    disposition.kind,
                    disposition.key,
                    actor,
                    operation,
                    detail if detail is not None else disposition.disposition.value,
                    _now(),
                ),
            )
            self._conn.execute(
                "UPDATE finding_disposition_registry SET registry_version = ? WHERE project = ?",
                (expected_version + 1, project),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return expected_version + 1
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_dispositions_store.py -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/schema.py src/sdlc/dispositions/store.py tests/test_dispositions_store.py
git commit -m "feat(dispositions): board-backed persistence, (kind,key) primary key (E-50 GD7)"
```

---

### Task 4: `dispositions/cli.py` — the human entry point

**Files:**
- Create: `src/sdlc/dispositions/cli.py`
- Modify: `src/sdlc/cli.py`
- Test: `tests/test_dispositions_cli.py`

**Interfaces:**
- Consumes: `dispositions.store.BoardFindingDispositionStore`, `dispositions.models.FindingDisposition`, `dispositions.models.Disposition`
- Produces: `add_dispositions_parser(sub) -> None`; `run_dispositions(args) -> int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dispositions_cli.py
"""FR-304 (E-50): `sdlc risk dispose|list|export`, mirroring
capability/cli.py's shape and its CLI-not-HTTP reasoning (OQ-11)."""

from __future__ import annotations

import argparse
import json

import pytest

from sdlc.dispositions.cli import add_dispositions_parser, run_dispositions
from sdlc.dispositions.models import Disposition
from sdlc.dispositions.store import BoardFindingDispositionStore


def _parse(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_dispositions_parser(sub)
    return p.parse_args(argv)


def test_dispose_applies_and_reports_success(tmp_path, capsys):
    db = tmp_path / "board.sqlite3"
    args = _parse(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "SS1:hardcoded-secret:src/a.py:",
            "--disposition",
            "accepted_risk",
            "--reason",
            "reviewed, tolerated",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    assert run_dispositions(args) == 0
    assert "SS1:hardcoded-secret:src/a.py:" in capsys.readouterr().out
    store = BoardFindingDispositionStore(db=db)
    rows = store.load("p")
    store.close()
    assert rows[0].disposition is Disposition.ACCEPTED_RISK


def test_a_second_dispose_on_the_same_key_revises_it(tmp_path):
    db = tmp_path / "board.sqlite3"
    for disposition in ("false_positive", "accepted_risk"):
        args = _parse(
            [
                "risk",
                "dispose",
                "--project",
                "p",
                "--kind",
                "testability",
                "--key",
                "QS3:static-clock-access:src/a.py:",
                "--disposition",
                disposition,
                "--reason",
                "reviewed",
                "--by",
                "maks",
                "--db",
                str(db),
            ]
        )
        assert run_dispositions(args) == 0
    store = BoardFindingDispositionStore(db=db)
    rows = store.load("p")
    store.close()
    assert len(rows) == 1
    assert rows[0].disposition is Disposition.ACCEPTED_RISK


def test_list_prints_every_disposition(tmp_path, capsys):
    db = tmp_path / "board.sqlite3"
    args = _parse(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "SS1:x:src/a.py:",
            "--disposition",
            "mitigated_elsewhere",
            "--reason",
            "compensating control added",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    run_dispositions(args)
    args = _parse(["risk", "list", "--project", "p", "--db", str(db)])
    assert run_dispositions(args) == 0
    assert "SS1:x:src/a.py:" in capsys.readouterr().out


def test_export_writes_every_disposition(tmp_path):
    db = tmp_path / "board.sqlite3"
    args = _parse(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "SS1:x:src/a.py:",
            "--disposition",
            "accepted_risk",
            "--reason",
            "reviewed",
            "--by",
            "maks",
            "--db",
            str(db),
        ]
    )
    run_dispositions(args)
    target = tmp_path / ".sdlc" / "dispositions.json"
    args = _parse(["risk", "export", "--project", "p", "--out", str(target), "--db", str(db)])
    assert run_dispositions(args) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["dispositions"][0]["key"] == "SS1:x:src/a.py:"


def test_an_invalid_disposition_choice_is_rejected_by_argparse():
    with pytest.raises(SystemExit):
        _parse(
            [
                "risk",
                "dispose",
                "--project",
                "p",
                "--kind",
                "vulnerability",
                "--key",
                "k",
                "--disposition",
                "bogus",
                "--reason",
                "r",
                "--by",
                "maks",
            ]
        )


def test_build_parser_wires_the_risk_subcommand():
    """The main CLI dispatcher recognizes `risk`, not just the isolated
    parser this file otherwise tests against."""
    from sdlc.cli import build_parser

    args = build_parser().parse_args(
        [
            "risk",
            "dispose",
            "--project",
            "p",
            "--kind",
            "vulnerability",
            "--key",
            "k",
            "--disposition",
            "accepted_risk",
            "--reason",
            "r",
            "--by",
            "maks",
        ]
    )
    assert args.cmd == "risk"
    assert args.risk_cmd == "dispose"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dispositions_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.dispositions.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/dispositions/cli.py
"""FR-304 (E-50): the human entry point for finding dispositions.

CLI, not HTTP -- the same reasoning capability/cli.py states: a disposition
is an audited write, and the board API serves unauthenticated with a
self-asserted X-Actor header (OQ-11), which cannot provide provenance for
approved_by. Lives beside cli approve/reject/revise in vocabulary: --by is
the approver, --reason is retained as calibration signal.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .models import Disposition, FindingDisposition
from .store import BoardFindingDispositionStore, FindingDispositionStoreError


def add_dispositions_parser(sub) -> None:
    risk = sub.add_parser("risk")
    risksub = risk.add_subparsers(dest="risk_cmd", required=True)

    d = risksub.add_parser("dispose")
    d.add_argument("--project", required=True)
    d.add_argument("--kind", required=True, choices=("vulnerability", "testability"))
    d.add_argument("--key", required=True)
    d.add_argument(
        "--disposition",
        required=True,
        choices=("false_positive", "mitigated_elsewhere", "accepted_risk"),
    )
    d.add_argument("--reason", required=True)
    d.add_argument("--by", required=True, help="approver identity")
    d.add_argument("--db", default=None)

    ls = risksub.add_parser("list")
    ls.add_argument("--project", required=True)
    ls.add_argument("--db", default=None)

    ex = risksub.add_parser("export")
    ex.add_argument("--project", required=True)
    ex.add_argument("--out", required=True)
    ex.add_argument("--db", default=None)


def run_dispositions(args) -> int:
    store = BoardFindingDispositionStore(db=args.db)
    try:
        if args.risk_cmd == "list":
            for row in store.load(args.project):
                print(f"{row.kind}:{row.key}  {row.disposition.value}  by {row.approved_by}")
            return 0

        if args.risk_cmd == "export":
            rows = store.load(args.project)
            payload = {
                "project": args.project,
                "dispositions": [r.model_dump(mode="json") for r in rows],
            }
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"wrote {out}")
            return 0

        fd = FindingDisposition(
            kind=args.kind,
            key=args.key,
            disposition=Disposition(args.disposition),
            approved_by=args.by,
            reason=args.reason,
            decided_at=datetime.now(UTC),
        )
        version = store.apply(
            args.project,
            fd,
            expected_version=store.registry_version(args.project),
            actor=args.by,
        )
        print(f"dispose: {args.kind}:{args.key} -> registry_version {version}")
        return 0
    except (ValueError, FindingDispositionStoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
```

Modify `src/sdlc/cli.py`:

1. In `_needs_temporal_client` (around line 108), add `"risk"` to the local-only set:

```python
    local_only = (
        args.cmd == "benchmark"
        or (args.cmd == "schedules" and args.sched_cmd == "list")
        or args.cmd == "eval"
        or args.cmd == "calibrate"
        or args.cmd == "capability"
        or args.cmd == "risk"
    )
```

2. In `build_parser()`, the existing `from .capability.cli import add_capability_parser` /
   `add_capability_parser(sub)` pair is already there (`src/sdlc/cli.py:256-258`) — leave it
   untouched. Insert these two new lines immediately after it:

```python
    from .dispositions.cli import add_dispositions_parser

    add_dispositions_parser(sub)
```

3. In `main()`, the existing `if args.cmd == "capability":` block
   (`src/sdlc/cli.py:517-520`) is already there — leave it untouched. Insert this new block
   immediately after it:

```python
    if args.cmd == "risk":
        from .dispositions.cli import run_dispositions

        raise SystemExit(run_dispositions(args))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dispositions_cli.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/dispositions/cli.py src/sdlc/cli.py tests/test_dispositions_cli.py
git commit -m "feat(dispositions): sdlc risk dispose|list|export CLI (E-50 GD7)"
```

---

### Task 5: `assessment/gates/checks.py` — the two live clauses

**Files:**
- Create: `src/sdlc/assessment/gates/checks.py`
- Modify: `tests/helpers_risk.py`
- Test: `tests/test_gates_checks.py`

**Interfaces:**
- Consumes: `risk.models.UnifiedRiskMap`, `risk.models.VulnerabilityClass`, `risk.models.Criticality`, `discover.map.CapabilityMap`, `scan.models.testability_identity`, `dispositions.models.FindingDisposition`, `gate.CheckResult`, `gate.CheckClass`
- Produces: `unaccepted_confirmed_vulnerabilities(risk_map, dispositions) -> CheckResult | None`; `high_criticality_testability_blockers(risk_map, capability_map, dispositions) -> tuple[CheckResult | None, tuple[str, ...]]`; `tests.helpers_risk.capability_risk(bc_id="BC-001", **kw) -> CapabilityRisk`; `tests.helpers_risk.capability_map(*caps) -> CapabilityMap`

- [ ] **Step 1: Add the shared `CapabilityRisk` and `CapabilityMap` test helpers**

Modify `tests/helpers_risk.py` — add imports and two builders every gates test shares, mirroring the file's own `capability()` builder. `capability_map()` mirrors `tests/test_risk_build.py`'s own `_cmap` exactly: `CapabilityMap._counts_are_derived` (`discover/map.py`) rejects any capability whose `disposition.action` is absent from `by_action`, so every `CapabilityMap` fixture in this plan must derive it rather than omit it.

```python
from sdlc.assessment.discover.map import CapabilityMap  # add to the existing discover.map import
from sdlc.assessment.risk.models import (
    CapabilityRisk,
    Composite,
    ControlCoverage,
    ControlFamily,
    CriticalityRating,
    StrideCategory,
    ThreatAssessment,
)


def capability_risk(bc_id: str = "BC-001", **kw) -> CapabilityRisk:
    """A structurally complete CapabilityRisk with sensible defaults,
    shared by every gates test so a contract change lands in one place."""
    no_score = Composite(value=Measurement.not_collected("no factors"))
    base = dict(
        bc_id=bc_id,
        criticality=CriticalityRating(collected=Measurement.not_collected("SS4 did not collect")),
        threats=tuple(
            ThreatAssessment(category=c, applicable=False, rationale="no data flow of this shape")
            for c in StrideCategory
        ),
        controls=tuple(
            ControlCoverage(family=f, collected=Measurement.not_collected("x"), rule="r")
            for f in ControlFamily
        ),
        security=no_score,
        qa=no_score,
        unified=no_score,
    )
    base.update(kw)
    return CapabilityRisk(**base)


def capability_map(*caps) -> CapabilityMap:
    """A CapabilityMap with by_action derived from the given capabilities'
    dispositions -- `_counts_are_derived` rejects an action present on a
    capability but absent from by_action, so every fixture must supply it
    (mirrors test_risk_build.py's _cmap)."""
    actions: dict = {}
    for c in caps:
        actions[c.disposition.action] = actions.get(c.disposition.action, 0) + 1
    return CapabilityMap(
        capabilities=tuple(caps), by_action=actions, collected=Measurement.measured(1.0)
    )
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_gates_checks.py
"""FR-917 (E-50 GD3): the two live clauses -- confirmed-vulnerability and
high-criticality testability blocker."""

from __future__ import annotations

import random

from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.gates.checks import (
    high_criticality_testability_blockers,
    unaccepted_confirmed_vulnerabilities,
)
from sdlc.assessment.risk.models import (
    Criticality,
    CriticalityRating,
    RiskSource,
    Severity,
    StrideCategory,
    UnifiedRiskMap,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.assessment.scan.models import testability_identity
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.measurement import CollectionState, Measurement

from tests.helpers_risk import capability, capability_map, capability_risk

MEASURED_JUDGMENT = Measurement.measured(1.0)


def _vuln(
    key="SS1:hardcoded-secret:src/a.py:",
    classification=VulnerabilityClass.CONFIRMED,
    source=RiskSource.BASELINE,
) -> Vulnerability:
    return Vulnerability(
        key=key,
        classification=classification,
        severity=Severity.HIGH,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="src/a.py",
        source=source,
    )


def _disposition(
    key, kind="vulnerability", disposition=Disposition.ACCEPTED_RISK
) -> FindingDisposition:
    from datetime import UTC, datetime

    return FindingDisposition(
        kind=kind,
        key=key,
        disposition=disposition,
        approved_by="maks",
        reason="reviewed",
        decided_at=datetime.now(UTC),
    )


# --- unaccepted_confirmed_vulnerabilities --------------------------------


def test_a_confirmed_unaccepted_vulnerability_fails_the_check():
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    check = unaccepted_confirmed_vulnerabilities(m, ())
    assert check is not None
    assert check.passed is False
    assert "SS1:hardcoded-secret:src/a.py:" in check.detail


def test_a_disposition_on_the_same_key_clears_the_check():
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    dispositions = (_disposition("SS1:hardcoded-secret:src/a.py:"),)
    check = unaccepted_confirmed_vulnerabilities(m, dispositions)
    assert check.passed is True


def test_a_potential_vulnerability_does_not_fail_the_check():
    m = UnifiedRiskMap(
        capabilities=(
            capability_risk(vulnerabilities=(_vuln(classification=VulnerabilityClass.POTENTIAL),)),
        ),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    check = unaccepted_confirmed_vulnerabilities(m, ())
    assert check.passed is True


def test_the_clause_defers_when_judgment_did_not_run():
    """GD3: CONFIRMED is only reachable through the judgment layer, so a map
    that never ran one must not read as a clean PASS -- even when a row is
    already CONFIRMED-shaped. A BASELINE-sourced row is structurally legal
    (nothing couples classification to source at the type), so this pins
    the implementation actually gating on judgment.state rather than
    happening to see no vulnerabilities to check (a weaker map would pass
    the check for the wrong reason)."""
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=Measurement.not_collected("no risk proposer ran"),
    )
    assert unaccepted_confirmed_vulnerabilities(m, ()) is None


def test_a_disposition_for_a_different_key_is_inert():
    """A stale or unrelated disposition must not clear the real finding
    (failure-modes table: 'inert for this run')."""
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    stale = (_disposition("SS1:some-other-finding:src/z.py:"),)
    check = unaccepted_confirmed_vulnerabilities(m, stale)
    assert check.passed is False


def test_a_testability_kind_disposition_does_not_clear_a_vulnerability():
    m = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    dispositions = (_disposition("SS1:hardcoded-secret:src/a.py:", kind="testability"),)
    check = unaccepted_confirmed_vulnerabilities(m, dispositions)
    assert check.passed is False


def test_vulnerability_clause_is_order_independent():
    """NFR-10."""
    vulns = [_vuln("SS1:a:x:"), _vuln("SS1:b:x:"), _vuln("SS1:c:x:")]
    first = None
    for _ in range(5):
        random.shuffle(vulns)
        m = UnifiedRiskMap(
            capabilities=(capability_risk(vulnerabilities=tuple(vulns)),),
            collected=Measurement.measured(1.0),
            judgment=MEASURED_JUDGMENT,
        )
        out = unaccepted_confirmed_vulnerabilities(m, ()).model_dump_json()
        first = first if first is not None else out
        assert out == first


# --- high_criticality_testability_blockers -------------------------------


def _map_with(bc_id, findings) -> CapabilityMap:
    return capability_map(capability(bc_id=bc_id, testability=tuple(findings)))


def _blocker(path="src/a.py", pattern="singleton-access"):
    from sdlc.assessment.scan.models import TestabilityFinding

    return TestabilityFinding(
        severity="blocks",
        pattern=pattern,
        detail="reaches a global instance",
        recommended_seam="pass the collaborator in",
        path=path,
        line=3,
        evidence="Singleton.getInstance()",
    )


def _high(bc_id="BC-001"):
    return capability_risk(
        bc_id=bc_id,
        criticality=CriticalityRating(level=Criticality.HIGH, collected=Measurement.measured(1.0)),
    )


def test_a_blocker_on_a_high_capability_fails_the_check():
    cmap = _map_with("BC-001", [_blocker()])
    rmap = UnifiedRiskMap(capabilities=(_high(),), collected=Measurement.measured(1.0))
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is False
    assert deferred == ()


def test_a_disposition_on_the_finding_clears_it():
    cmap = _map_with("BC-001", [_blocker()])
    rmap = UnifiedRiskMap(capabilities=(_high(),), collected=Measurement.measured(1.0))
    key = testability_identity(_blocker())
    dispositions = (_disposition(key, kind="testability"),)
    check, _ = high_criticality_testability_blockers(rmap, cmap, dispositions)
    assert check.passed is True


def test_a_blocker_on_a_measured_medium_capability_does_not_fail_or_defer():
    cmap = _map_with("BC-001", [_blocker()])
    medium = capability_risk(
        bc_id="BC-001",
        criticality=CriticalityRating(
            level=Criticality.MEDIUM, collected=Measurement.measured(1.0)
        ),
    )
    rmap = UnifiedRiskMap(capabilities=(medium,), collected=Measurement.measured(1.0))
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is True
    assert deferred == ()


def test_an_uncollected_criticality_defers_its_own_blocker_even_with_a_measured_sibling():
    """The mixed-criticality fix: one uncollected capability must not read
    as a silent pass because a DIFFERENT capability happens to be rated."""
    cmap = capability_map(
        capability(bc_id="BC-001", testability=(_blocker(path="src/a.py"),)),
        capability(bc_id="BC-002", testability=()),
    )
    uncollected = capability_risk(bc_id="BC-001")  # default: criticality not_collected
    measured_low = capability_risk(
        bc_id="BC-002",
        criticality=CriticalityRating(level=Criticality.LOW, collected=Measurement.measured(1.0)),
    )
    rmap = UnifiedRiskMap(
        capabilities=(measured_low, uncollected), collected=Measurement.measured(1.0)
    )
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is True  # nothing MEASURED high fired
    assert len(deferred) == 1
    assert "BC-001" in deferred[0]


def test_a_blocker_on_a_bc_id_absent_from_the_risk_map_is_deferred_not_skipped():
    """GD3's rationale forbids a silent skip: a capability the discover
    phase carries but the risk phase never scored (an unjoinable bc_id)
    must be visible in `deferred`, not quietly dropped."""
    cmap = capability_map(capability(bc_id="BC-001", testability=(_blocker(),)))
    rmap = UnifiedRiskMap(capabilities=(), collected=Measurement.measured(1.0))
    check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
    assert check.passed is True
    assert len(deferred) == 1
    assert "BC-001" in deferred[0]


def test_a_stale_testability_disposition_is_inert():
    """A disposition for a different finding must not clear this one."""
    cmap = _map_with("BC-001", [_blocker()])
    rmap = UnifiedRiskMap(capabilities=(_high(),), collected=Measurement.measured(1.0))
    stale = (_disposition("QS3:some-other-pattern:src/z.py:", kind="testability"),)
    check, _ = high_criticality_testability_blockers(rmap, cmap, stale)
    assert check.passed is False


def test_testability_clause_is_order_independent():
    """NFR-10. CapabilityMap enforces no sort on its capabilities (unlike
    UnifiedRiskMap, which forces canonical order at construction) -- the
    genuinely permutable axis here is capability_map's tuple order, plus
    the findings list within one capability."""
    caps = [
        capability(bc_id="BC-001", testability=(_blocker("src/a.py", "singleton-access"),)),
        capability(bc_id="BC-002", testability=(_blocker("src/b.py", "sleep-in-production"),)),
    ]
    rmap = UnifiedRiskMap(
        capabilities=(_high("BC-001"), _high("BC-002")), collected=Measurement.measured(1.0)
    )
    first = None
    for _ in range(5):
        random.shuffle(caps)
        cmap = capability_map(*caps)
        check, deferred = high_criticality_testability_blockers(rmap, cmap, ())
        out = check.model_dump_json() + "|" + "|".join(deferred)
        first = first if first is not None else out
        assert out == first
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_gates_checks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.gates.checks'`

- [ ] **Step 4: Write minimal implementation**

```python
# src/sdlc/assessment/gates/checks.py
"""FR-917 (E-50): the risk gate's pure evaluation -- GD3/GD4's clauses.

Pure by design -- see the package docstring in models.py.
"""

from __future__ import annotations

from ...gate import CheckClass, CheckResult
from ...measurement import CollectionState
from ..discover.map import CapabilityMap
from ..risk.models import Criticality, UnifiedRiskMap, VulnerabilityClass
from ..scan.models import testability_identity
from ...dispositions.models import FindingDisposition


def unaccepted_confirmed_vulnerabilities(
    risk_map: UnifiedRiskMap, dispositions: tuple[FindingDisposition, ...]
) -> CheckResult | None:
    """GD3: defers when the judgment layer did not run -- CONFIRMED is only
    reachable through it (risk/build.py stamps every baseline row
    POTENTIAL), so a map with no judgment layer must not read as clean.
    """
    if risk_map.judgment.state is not CollectionState.MEASURED:
        return None

    accepted = {d.key for d in dispositions if d.kind == "vulnerability"}
    offending = sorted(
        {
            v.key
            for cap in risk_map.capabilities
            for v in cap.vulnerabilities
            if v.classification is VulnerabilityClass.CONFIRMED and v.key not in accepted
        }
    )
    passed = not offending
    return CheckResult(
        name="risk_no_unaccepted_confirmed_vuln",
        passed=passed,
        classification=CheckClass.ABSOLUTE,
        detail="" if passed else f"unaccepted confirmed vulnerabilities: {offending}",
    )


def high_criticality_testability_blockers(
    risk_map: UnifiedRiskMap,
    capability_map: CapabilityMap,
    dispositions: tuple[FindingDisposition, ...],
) -> tuple[CheckResult | None, tuple[str, ...]]:
    """GD3: evaluated per (bc_id, finding) pair. An uncollected criticality
    -- or a bc_id with no matching row in the risk map at all -- defers
    only its own pair, never the whole clause: a sibling capability being
    measured must not silently clear it (the mixed-criticality fix), and a
    bc_id the risk phase never scored must not silently drop its blocker
    either (the same silent-skip shape, one join away).
    """
    testability_by_bc_id = {cap.bc_id: cap.testability for cap in capability_map.capabilities}
    criticality_by_bc_id = {c.bc_id: c.criticality for c in risk_map.capabilities}
    accepted = {d.key for d in dispositions if d.kind == "testability"}

    offending: set[str] = set()
    deferred: list[str] = []
    for bc_id in sorted(testability_by_bc_id):
        blockers = [f for f in testability_by_bc_id[bc_id] if f.severity == "blocks"]
        if not blockers:
            continue
        rating = criticality_by_bc_id.get(bc_id)
        if rating is None:
            deferred.extend(
                f"testability blocker for {bc_id} ({testability_identity(f)}): "
                f"no matching capability in the risk map"
                for f in sorted(blockers, key=testability_identity)
            )
        elif rating.collected.state is not CollectionState.MEASURED:
            deferred.extend(
                f"testability blocker for {bc_id} ({testability_identity(f)}): "
                f"criticality is not_collected"
                for f in sorted(blockers, key=testability_identity)
            )
        elif rating.level is Criticality.HIGH:
            offending.update(
                testability_identity(f) for f in blockers if testability_identity(f) not in accepted
            )

    offending_sorted = sorted(offending)
    check = CheckResult(
        name="risk_no_high_criticality_testability_blocker",
        passed=not offending_sorted,
        classification=CheckClass.ABSOLUTE,
        detail=(
            ""
            if not offending_sorted
            else f"testability blockers on HIGH capabilities: {offending_sorted}"
        ),
    )
    return check, tuple(sorted(deferred))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_gates_checks.py -v`
Expected: PASS (14 tests)

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/gates/checks.py tests/helpers_risk.py tests/test_gates_checks.py
git commit -m "feat(gates): the two live clauses -- vuln (judgment-gated) and testability (per-pair, never silently skipped) (E-50 GD3)"
```

---

### Task 6: `assessment/gates/checks.py` — the composite clause and `evaluate()`

**Files:**
- Modify: `src/sdlc/assessment/gates/checks.py`
- Test: `tests/test_gates_checks.py`

**Interfaces:**
- Consumes: Task 5's clause functions, `gates.models.RiskGateReport`, `gates.models.RiskGateVerdict`
- Produces: `composite_threshold(risk_map) -> tuple[CheckResult | None, RiskGateVerdict | None, tuple[str, ...]]`; `evaluate(risk_map, capability_map, dispositions) -> RiskGateReport`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_gates_checks.py`:

```python
from sdlc.assessment.gates.checks import composite_threshold, evaluate
from sdlc.assessment.gates.models import RiskGateVerdict
from sdlc.assessment.risk.models import Composite, Factor


def _scored(bc_id, value) -> "CapabilityRisk":
    from tests.helpers_risk import capability_risk

    return capability_risk(
        bc_id=bc_id,
        unified=Composite(
            value=Measurement.measured(value),
            factors=(Factor(key="x", value=Measurement.measured(value)),),
        ),
    )


# --- composite_threshold --------------------------------------------------


def test_a_measured_capability_at_or_above_0_8_fires_block():
    m = UnifiedRiskMap(capabilities=(_scored("BC-001", 0.85),), collected=Measurement.measured(1.0))
    check, warn, deferred = composite_threshold(m)
    assert check.passed is False
    assert warn is None
    assert deferred == ()


def test_one_block_capability_fires_regardless_of_a_second_partial_one():
    partial = capability_risk("BC-002")  # default unified: not_collected
    m = UnifiedRiskMap(
        capabilities=(_scored("BC-001", 0.9), partial), collected=Measurement.measured(1.0)
    )
    check, warn, deferred = composite_threshold(m)
    assert check.passed is False
    assert "BC-002" in deferred[0]


def test_a_measured_capability_in_the_warn_band_with_no_block_warns():
    m = UnifiedRiskMap(capabilities=(_scored("BC-001", 0.65),), collected=Measurement.measured(1.0))
    check, warn, deferred = composite_threshold(m)
    assert check.passed is True
    assert warn is RiskGateVerdict.WARN


def test_all_capabilities_partial_defers_the_whole_clause():
    """RD3's headline consequence: today's reality until E-56 lands."""
    m = UnifiedRiskMap(
        capabilities=(capability_risk("BC-001"), capability_risk("BC-002")),
        collected=Measurement.measured(1.0),
    )
    check, warn, deferred = composite_threshold(m)
    assert check is None
    assert warn is None
    assert len(deferred) == 2


# NOTE: composite_threshold has no order-independence test of its own.
# UnifiedRiskMap._capabilities_are_sorted forces risk_map.capabilities into
# canonical order at CONSTRUCTION time -- there is no valid way to build an
# UnifiedRiskMap whose capability order differs, so shuffling a list and
# re-sorting it before construction (an earlier version of this test) was
# vacuous: the re-sort silently undid the shuffle. The genuinely free axes
# for this module -- capability_map's tuple order (CapabilityMap enforces
# no sort) and the dispositions tuple order -- are permuted below, at the
# evaluate() level, which is where both axes are actually consumed.


# --- evaluate --------------------------------------------------------------


def _empty_map() -> CapabilityMap:
    return CapabilityMap(collected=Measurement.measured(1.0))


def test_evaluate_passes_when_nothing_fires():
    rmap = UnifiedRiskMap(capabilities=(capability_risk(),), collected=Measurement.measured(1.0))
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.PASS


def test_evaluate_blocks_on_a_confirmed_unaccepted_vulnerability():
    rmap = UnifiedRiskMap(
        capabilities=(capability_risk(vulnerabilities=(_vuln(),)),),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.BLOCK
    assert "risk_no_unaccepted_confirmed_vuln" in [c.name for c in report.checks]


def test_a_block_clause_wins_over_a_warn_band_composite():
    rmap = UnifiedRiskMap(
        capabilities=(
            capability_risk(bc_id="BC-001", vulnerabilities=(_vuln(),)),
            _scored("BC-002", 0.65),
        ),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.BLOCK


def test_evaluate_warns_when_only_the_composite_warn_band_fires():
    rmap = UnifiedRiskMap(
        capabilities=(_scored("BC-001", 0.65),), collected=Measurement.measured(1.0)
    )
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.WARN
    # GD5: detail names every contributing bc_id, even on a PASSED check --
    # a WARN report must not be silent about which capability warned.
    assert any("BC-001" in r for r in report.reasons)


def test_a_pass_with_deferrals_names_them():
    """FR-915: a PASS that skipped a clause must say so."""
    rmap = UnifiedRiskMap(capabilities=(capability_risk(),), collected=Measurement.measured(1.0))
    report = evaluate(rmap, _empty_map(), ())
    assert report.verdict is RiskGateVerdict.PASS
    assert any("unified composite" in d for d in report.deferred)
    assert any("judgment layer" in d for d in report.deferred)


def test_no_check_row_is_ever_emitted_for_a_deferred_clause():
    rmap = UnifiedRiskMap(capabilities=(capability_risk(),), collected=Measurement.measured(1.0))
    report = evaluate(rmap, _empty_map(), ())
    # judgment not measured -> vuln check absent; composite fully partial -> absent
    assert [c.name for c in report.checks] == ["risk_no_high_criticality_testability_blocker"]


def test_evaluate_is_order_independent():
    """NFR-10. risk_map.capabilities is fixed (the type forces canonical
    order); the genuinely free axes are capability_map's tuple order and
    the dispositions tuple order, both shuffled here across >= 2 elements
    each -- a 1-element list cannot exercise a shuffle at all."""
    rmap = UnifiedRiskMap(
        capabilities=(
            capability_risk(bc_id="BC-001", vulnerabilities=(_vuln("SS1:a:x:"),)),
            _scored("BC-002", 0.7),
        ),
        collected=Measurement.measured(1.0),
        judgment=MEASURED_JUDGMENT,
    )
    caps = [
        capability(bc_id="BC-001", testability=()),
        capability(bc_id="BC-002", testability=()),
    ]
    dispositions = [
        _disposition("SS1:a:x:", disposition=Disposition.MITIGATED_ELSEWHERE),
        _disposition("QS3:unrelated:src/z.py:", kind="testability"),
    ]
    first = None
    for _ in range(5):
        random.shuffle(caps)
        random.shuffle(dispositions)
        out = evaluate(rmap, capability_map(*caps), tuple(dispositions)).model_dump_json()
        first = first if first is not None else out
        assert out == first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gates_checks.py -v`
Expected: FAIL — `ImportError: cannot import name 'composite_threshold'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/assessment/gates/checks.py` (and add the two new imports at the top):

```python
from .models import RiskGateReport, RiskGateVerdict


def composite_threshold(
    risk_map: UnifiedRiskMap,
) -> tuple[CheckResult | None, RiskGateVerdict | None, tuple[str, ...]]:
    """GD4: per capability, worst-instance semantics -- CapabilityRisk.unified
    is the only place a composite exists; there is no single map-level value.
    """
    measured_block: list[str] = []
    measured_warn: list[str] = []
    deferred: list[str] = []
    any_measured = False

    for cap in sorted(risk_map.capabilities, key=lambda c: c.bc_id):
        m = cap.unified.value
        if m.state is not CollectionState.MEASURED:
            deferred.append(f"unified composite for {cap.bc_id}: {m.reason}")
            continue
        any_measured = True
        assert m.value is not None
        if m.value >= 0.8:
            measured_block.append(cap.bc_id)
        elif m.value >= 0.6:
            measured_warn.append(cap.bc_id)

    if not any_measured:
        return None, None, tuple(sorted(deferred))

    # GD5: detail names every contributing bc_id even when the check PASSES
    # -- a WARN-band-only capability must still be visible in the report's
    # `reasons` (evaluate() surfaces every non-empty detail regardless of
    # passed/failed), not just a BLOCK-band one.
    detail_parts = []
    if measured_block:
        detail_parts.append(f"unified composite >= 0.8 for: {sorted(measured_block)}")
    if measured_warn:
        detail_parts.append(f"unified composite in [0.6, 0.8) for: {sorted(measured_warn)}")
    check = CheckResult(
        name="risk_composite_below_threshold",
        passed=not measured_block,
        classification=CheckClass.ABSOLUTE,
        detail="; ".join(detail_parts),
    )
    warn = RiskGateVerdict.WARN if (not measured_block and measured_warn) else None
    return check, warn, tuple(sorted(deferred))


def evaluate(
    risk_map: UnifiedRiskMap,
    capability_map: CapabilityMap,
    dispositions: tuple[FindingDisposition, ...],
) -> RiskGateReport:
    """FR-917: the three clauses, GD4's precedence -- BLOCK > WARN > PASS."""
    vuln_check = unaccepted_confirmed_vulnerabilities(risk_map, dispositions)
    testability_check, testability_deferred = high_criticality_testability_blockers(
        risk_map, capability_map, dispositions
    )
    composite_check, composite_warn, composite_deferred = composite_threshold(risk_map)

    checks = tuple(
        sorted(
            (c for c in (vuln_check, testability_check, composite_check) if c is not None),
            key=lambda c: c.name,
        )
    )

    deferred: list[str] = [*testability_deferred, *composite_deferred]
    if vuln_check is None:
        deferred.append(
            "unaccepted-confirmed-vulnerability clause: judgment layer did not run "
            f"({risk_map.judgment.reason})"
        )

    blocking = [c.name for c in checks if not c.passed]
    if blocking:
        verdict = RiskGateVerdict.BLOCK
    elif composite_warn is RiskGateVerdict.WARN:
        verdict = RiskGateVerdict.WARN
    else:
        verdict = RiskGateVerdict.PASS

    reasons = tuple(sorted({c.detail for c in checks if c.detail}))
    return RiskGateReport(
        verdict=verdict,
        checks=checks,
        deferred=tuple(sorted(set(deferred))),
        reasons=reasons,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gates_checks.py -v`
Expected: PASS (25 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/gates/checks.py tests/test_gates_checks.py
git commit -m "feat(gates): per-capability composite clause and evaluate()'s BLOCK>WARN>PASS precedence (E-50 GD4)"
```

---

### Task 7: `assessment/models.py` — `Assessment.gates` / `.gate_override`

**Files:**
- Modify: `src/sdlc/assessment/models.py`
- Modify: `tests/test_assessment_models.py`
- Test: `tests/test_assessment_models.py`

**Interfaces:**
- Consumes: `gates.models.RiskGateReport`, `gates.models.RiskGateOverride`, `gates.models.RiskGateVerdict`
- Produces: `Assessment.gates: RiskGateReport | None`; `Assessment.gate_override: RiskGateOverride | None`

**Two pre-existing tests break once `_gates_agrees_with_risk` lands, because they construct an `Assessment`/call `assemble()` with `risk` present and no `gates`:**
- `tests/test_assessment_models.py::test_a_measured_assess_phase_with_a_payload_constructs` — fixed in this task's Step 3, since `Assessment(...)` already accepts a `gates` kwarg the moment the field exists.
- `tests/test_assessment_workflow.py::test_assemble_reports_assessed_once_every_phase_collects` — calls `assemble(..., risk=UnifiedRiskMap(...))` with no `gates=`. `assemble()` itself does not gain a `gates` parameter until **Task 9** (it is the task that rewires `run()` and `assemble()` together), so this specific test **stays red between this task and Task 9** — a tracked, deliberate gap, not an oversight. Task 9's own Step 3 fixes it alongside `assemble()`'s signature change; this task's Step 4 explicitly confirms it is the one known-red test at that point, so "PASS" claims elsewhere stay honest.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_models.py`:

```python
# --- E-50: the risk gate result and its agreement with `risk` ------------
from sdlc.assessment.gates.models import RiskGateOverride, RiskGateReport, RiskGateVerdict


def _gate_report(verdict=RiskGateVerdict.PASS) -> RiskGateReport:
    return RiskGateReport(verdict=verdict)


def _override() -> RiskGateOverride:
    from datetime import UTC, datetime

    return RiskGateOverride(
        approved_by="human", reason="reviewed", decided_at=datetime.now(UTC), gate_round=1
    )


def test_a_measured_risk_map_must_carry_a_gates_report():
    phases = _assess_dag(assess_measured=True)
    with pytest.raises(ValidationError, match="gates must be present"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=_scan_result(),
            risk=UnifiedRiskMap(collected=Measurement.measured(1.0)),
            gates=None,
        )


def test_an_uncollected_risk_map_must_not_carry_a_gates_report():
    phases = _assess_dag(assess_measured=False)
    with pytest.raises(ValidationError, match="gates must be present"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=_scan_result(),
            risk=None,
            gates=_gate_report(),
        )


def test_gate_override_requires_a_block_verdict():
    phases = _assess_dag(assess_measured=True)
    with pytest.raises(ValidationError, match="did not BLOCK"):
        Assessment(
            repo_dir="/r",
            triage=_triage(),
            admitted=True,
            admission_reason="verdict ready",
            phases=phases,
            terminal_status=terminal_status(True, phases),
            scan=_scan_result(),
            risk=UnifiedRiskMap(collected=Measurement.measured(1.0)),
            gates=_gate_report(RiskGateVerdict.PASS),
            gate_override=_override(),
        )


def test_gate_override_is_accepted_on_a_block_verdict():
    phases = _assess_dag(assess_measured=True)
    a = Assessment(
        repo_dir="/r",
        triage=_triage(),
        admitted=True,
        admission_reason="verdict ready",
        phases=phases,
        terminal_status=terminal_status(True, phases),
        scan=_scan_result(),
        risk=UnifiedRiskMap(collected=Measurement.measured(1.0)),
        gates=_gate_report(RiskGateVerdict.BLOCK),
        gate_override=_override(),
    )
    assert a.gate_override is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_models.py -v`
Expected: FAIL, but not with a `TypeError` — `Assessment` carries no `model_config = ConfigDict(extra=...)`, so Pydantic's default (`extra="ignore"`) silently drops the unrecognized `gates=`/`gate_override=` kwargs at construction rather than rejecting them. The three validator tests
(`test_a_measured_risk_map_must_carry_a_gates_report`, `test_an_uncollected_risk_map_must_not_carry_a_gates_report`, `test_gate_override_requires_a_block_verdict`) fail with
`Failed: DID NOT RAISE <class 'pydantic_core._pydantic_core.ValidationError'>` (construction succeeds because no validator exists yet to reject the mismatch). `test_gate_override_is_accepted_on_a_block_verdict` fails with `AttributeError: 'Assessment' object has no attribute 'gate_override'` on its final `assert a.gate_override is not None` — the kwarg was accepted and discarded, so the attribute was never set.

- [ ] **Step 3: Write minimal implementation**

Modify `src/sdlc/assessment/models.py`:

Add the import alongside the existing `risk.models` import:

```python
from .gates.models import RiskGateOverride, RiskGateReport, RiskGateVerdict
```

Add the two fields to `Assessment`, right after `risk`:

```python
    # E-50's typed field (FR-917). Agrees with `risk` being present, not a
    # phases row -- there is no PhaseId for the risk gate (GD1).
    gates: RiskGateReport | None = None
    # E-50's typed field (FR-304): the audited THIS-RUN override, stamped
    # only when the risk gate opened and was approved (GD2/GD10).
    gate_override: RiskGateOverride | None = None
```

Add the two validators, right after `_assess_agrees_with_its_phase`:

```python
@model_validator(mode="after")
def _gates_agrees_with_risk(self) -> Assessment:
    """The fourth instance of _scan_agrees_with_its_phase's pattern, but
    keyed off `risk` rather than a phase row: E-50's check is not a DAG
    stage (GD1)."""
    if (self.risk is not None) != (self.gates is not None):
        raise ValueError(
            "gates must be present iff risk is present -- there is no "
            "PhaseId for the risk gate (E-50 GD1), so it agrees with "
            "the risk payload instead of a phase row"
        )
    return self


@model_validator(mode="after")
def _override_only_on_block(self) -> Assessment:
    if self.gate_override is not None and (
        self.gates is None or self.gates.verdict is not RiskGateVerdict.BLOCK
    ):
        raise ValueError(
            "gate_override is present but the risk gate did not BLOCK -- "
            "an override on a WARN or PASS run is a contradiction, since "
            "no gate opened to decide (E-50 GD5)"
        )
    return self
```

**Fix the one pre-existing test this task's validator can already fix.**

In `tests/test_assessment_models.py`, `test_a_measured_assess_phase_with_a_payload_constructs` (currently around line 432) constructs an `Assessment` with `risk=UnifiedRiskMap(...)` and no `gates=` — add one (`RiskGateReport`/`RiskGateVerdict` are already imported a few lines above this test by Step 1's own append):

```python
def test_a_measured_assess_phase_with_a_payload_constructs():
    phases = _assess_dag(assess_measured=True)
    a = Assessment(
        repo_dir="/r",
        triage=_triage(),
        admitted=True,
        admission_reason="verdict ready",
        phases=phases,
        terminal_status=terminal_status(True, phases),
        scan=_scan_result(),
        risk=UnifiedRiskMap(collected=Measurement.measured(1.0)),
        gates=RiskGateReport(verdict=RiskGateVerdict.PASS),
    )
    assert a.risk is not None
```

`tests/test_assessment_workflow.py::test_assemble_reports_assessed_once_every_phase_collects` calls `assemble(...)` directly, and `assemble()` does not accept a `gates` keyword until **Task 9** changes its signature — this test cannot be fixed here. Leave it red; Task 9's own Step 3 fixes it alongside `assemble()`'s signature change, and Task 9's own Step 4 is where the full suite is confirmed green again.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assessment_models.py -v`
Expected: PASS (every test in this file, including the newly-fixed
`test_a_measured_assess_phase_with_a_payload_constructs`).

Run: `pytest tests/test_assessment_workflow.py -v`
Expected: every test PASSES **except** `test_assemble_reports_assessed_once_every_phase_collects`. Neither `assemble()`'s signature nor this test file changed in this task, so the call site is still valid Python — but `assemble()` now constructs `Assessment(..., risk=<UnifiedRiskMap>, gates=None)` internally (its body is unchanged, so it never supplies `gates`), which trips `_gates_agrees_with_risk` and raises `pydantic.ValidationError` instead of returning. This ONE known-red test is expected and tracked here; it is not a regression to chase down now, and Task 9 is where it turns green again.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/models.py tests/test_assessment_models.py
git commit -m "feat(assessment): Assessment.gates/.gate_override, agreeing with risk not a phase row (E-50 GD5)"
```

---

### Task 8: `assessment/activities.py` — `load_dispositions`

**Files:**
- Modify: `src/sdlc/assessment/activities.py`
- Test: `tests/test_load_dispositions_activity.py`

**Interfaces:**
- Consumes: `dispositions.store.BoardFindingDispositionStore`, `dispositions.models.FindingDisposition`
- Produces: `LoadDispositionsInput(project: str)`; `load_dispositions(inp: LoadDispositionsInput) -> tuple[FindingDisposition, ...]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_load_dispositions_activity.py
"""FR-304 (E-50 GD8): re-runs read persisted dispositions through one
activity, never memoized -- a disposition recorded between runs must be
visible on the very next one."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sdlc.assessment.activities import LoadDispositionsInput, load_dispositions
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import BoardFindingDispositionStore

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def board(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    return tmp_path / "board.sqlite3"


def _fd(**kw) -> FindingDisposition:
    base = dict(
        kind="vulnerability",
        key="SS1:hardcoded-secret:src/a.py:",
        disposition=Disposition.ACCEPTED_RISK,
        approved_by="maks",
        reason="reviewed, tolerated",
        decided_at=datetime.now(UTC),
    )
    base.update(kw)
    return FindingDisposition(**base)


async def test_no_dispositions_yet_returns_empty():
    out = await load_dispositions(LoadDispositionsInput(project="acme"))
    assert out == ()


async def test_a_persisted_disposition_is_read_back():
    store = BoardFindingDispositionStore()
    store.apply("acme", _fd(), expected_version=0, actor="maks")
    store.close()

    out = await load_dispositions(LoadDispositionsInput(project="acme"))
    assert len(out) == 1
    assert out[0].key == "SS1:hardcoded-secret:src/a.py:"


async def test_projects_are_isolated():
    store = BoardFindingDispositionStore()
    store.apply("acme", _fd(), expected_version=0, actor="maks")
    store.close()

    out = await load_dispositions(LoadDispositionsInput(project="other"))
    assert out == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_load_dispositions_activity.py -v`
Expected: FAIL — `ImportError: cannot import name 'LoadDispositionsInput'`

- [ ] **Step 3: Write minimal implementation**

Modify `src/sdlc/assessment/activities.py`:

Add the two imports alongside the existing `from ..capability.store import BoardIdentityStore`:

```python
from ..dispositions.models import FindingDisposition
from ..dispositions.store import BoardFindingDispositionStore
```

Add, right after `verify_risk_refs`:

```python
class LoadDispositionsInput(BaseModel):
    project: str


@activity.defn
async def load_dispositions(inp: LoadDispositionsInput) -> tuple[FindingDisposition, ...]:
    """FR-304 (E-50 GD8): dispositions persisted from a prior run, read
    fresh every run -- never memoized, since a disposition recorded between
    runs must be visible on the very next one."""
    store = BoardFindingDispositionStore()
    try:
        return tuple(store.load(inp.project))
    finally:
        store.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_load_dispositions_activity.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/activities.py tests/test_load_dispositions_activity.py
git commit -m "feat(assessment): load_dispositions activity, uncached (E-50 GD8)"
```

---

### Task 9: `workflows/assessment.py` — the gate, and BLOCK's two outcomes

**Files:**
- Modify: `src/sdlc/workflows/assessment.py`
- Test: `tests/test_assessment_workflow_risk_gate_e2e.py`

**Interfaces:**
- Consumes: Tasks 1–8's `evaluate`, `RiskGateReport`, `RiskGateVerdict`, `RiskGateOverride`, `load_dispositions`, `LoadDispositionsInput`, `Assessment.gates`/`.gate_override`
- Produces: `RiskGateStepOutcome(gates: RiskGateReport | None, override: RiskGateOverride | None, blocked: bool)`; `AssessmentWorkflow._risk_gate(...)`; `risk_gate_skipped(phase) -> PhaseResult`; `assemble(..., gates=None, gate_override=None)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_assessment_workflow_risk_gate_e2e.py
"""E-50 end to end: the risk gate opens on BLOCK, mirrors the readiness
gate's mechanics, and REJECT vs APPROVE diverge exactly as GD2 states."""

from __future__ import annotations

import subprocess
import uuid
from datetime import UTC, datetime

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from sdlc.assessment.activities import (
    assessment_resolve_tree,
    discover_context,
    load_dispositions,
    scan_ci,
    scan_config_infra,
    scan_coverage,
    scan_entrypoints,
    scan_frontend,
    scan_packages,
    scan_schema,
    scan_security_static,
    scan_sensitivity,
    scan_testability,
    scan_tests_inventory,
)
from sdlc.assessment.discover.map import CapabilityMap
from sdlc.assessment.gates.models import RiskGateVerdict
from sdlc.assessment.models import PARTIAL, PhaseId
from sdlc.assessment.risk.models import (
    Criticality,
    CriticalityRating,
    UnifiedRiskMap,
)
from sdlc.assessment.scan.models import TestabilityFinding
from sdlc.dispositions.models import Disposition, FindingDisposition
from sdlc.dispositions.store import BoardFindingDispositionStore
from sdlc.measurement import CollectionState, Measurement
from sdlc.models import GateDecision, GateOutcome
from sdlc.triage.activities import TriagePin, TriagePinInput, TriageProbeInput, TriageSignalInput
from sdlc.triage.models import SignalResult
from sdlc.workflows.assessment import AssessmentInput, AssessmentWorkflow, risk_gate_skipped
from sdlc.workflows.triage import TriageWorkflow

from tests.helpers_risk import capability, capability_map, capability_risk

pytestmark = [pytest.mark.temporal, pytest.mark.asyncio]

TASK_QUEUE = "risk-gate-test"


def _ok(signal, version, metrics=None):
    return SignalResult(
        signal=signal, version=version, collected=Measurement.measured(0.0), metrics=metrics or {}
    )


@activity.defn(name="triage_baseline")
async def fake_baseline(inp: TriageSignalInput) -> SignalResult:
    return _ok("baseline", 2, {"tests_present": Measurement.measured(3.0)})


@activity.defn(name="triage_scaffold")
async def fake_scaffold(inp: TriageSignalInput) -> SignalResult:
    return _ok("scaffold", 1, {"structure_discernible": Measurement.measured(1.0)})


@activity.defn(name="triage_build_probe")
async def fake_probe(inp: TriageProbeInput) -> SignalResult:
    return _ok(
        "build_probe",
        1,
        {"buildable": Measurement.measured(1.0), "runnable": Measurement.measured(1.0)},
    )


@activity.defn(name="triage_secrets")
async def fake_secrets(inp: TriageSignalInput) -> SignalResult:
    return _ok("secrets", 2)


@activity.defn(name="triage_misconfig")
async def fake_misconfig(inp: TriageSignalInput) -> SignalResult:
    return _ok("misconfig", 1)


@activity.defn(name="triage_outliers")
async def fake_outliers(inp: TriageSignalInput) -> SignalResult:
    return _ok("outliers", 1)


@activity.defn(name="triage_dependencies")
async def fake_deps(inp) -> SignalResult:
    return _ok("dependencies", 1)


SCAN_ACTS = [
    scan_packages,
    scan_schema,
    scan_entrypoints,
    scan_frontend,
    scan_security_static,
    scan_config_infra,
    scan_sensitivity,
    scan_tests_inventory,
    scan_coverage,
    scan_testability,
    scan_ci,
]
WORKFLOWS = [AssessmentWorkflow, TriageWorkflow]


def _blocker() -> TestabilityFinding:
    return TestabilityFinding(
        severity="blocks",
        pattern="singleton-access",
        detail="reaches a global instance",
        recommended_seam="pass the collaborator in",
        path="payments/api.py",
        line=3,
        evidence="Singleton.getInstance()",
    )


def _blocking_capability_map() -> CapabilityMap:
    # capability_map() (tests/helpers_risk.py) derives by_action -- a raw
    # CapabilityMap(capabilities=(...)) with no by_action trips
    # _counts_are_derived's "unlisted" branch (discover/map.py) the instant
    # a capability carries a disposition action absent from that dict.
    return capability_map(capability(bc_id="BC-001", testability=(_blocker(),)))


def _clean_capability_map() -> CapabilityMap:
    return capability_map(capability(bc_id="BC-001"))


def _high_risk_map() -> UnifiedRiskMap:
    cap = capability_risk(
        bc_id="BC-001",
        criticality=CriticalityRating(level=Criticality.HIGH, collected=Measurement.measured(1.0)),
    )
    return UnifiedRiskMap(capabilities=(cap,), collected=Measurement.measured(1.0))


def _git(args, cwd):
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def gate_repo(tmp_path):
    # Exact content of test_assessment_workflow_e2e.py's `assessed_repo`
    # fixture, proven to carry S5/discover_context all the way to MEASURED
    # (test_assess_phase_measures_with_no_model_registered). This test does
    # not need THAT content specifically -- discover_memo_load and
    # risk_memo_load are faked below, so nothing here needs to resolve to
    # any particular capability or finding -- it only needs SCAN and
    # discover_context to succeed for real before the memo fakes take over.
    (tmp_path / "package.json").write_text('{"dependencies": {"next": "14.0.0"}}\n')
    (tmp_path / "app" / "payments").mkdir(parents=True)
    (tmp_path / "app" / "payments" / "page.tsx").write_text(
        "export default function PaymentsPage() { return null; }\n"
    )
    (tmp_path / "payments").mkdir()
    (tmp_path / "payments" / "api.py").write_text(
        "from fastapi import FastAPI\n"
        "from payments.models import Order\n"
        "app = FastAPI()\n"
        "@app.post('/api/payments')\ndef charge(): pass\n"
    )
    (tmp_path / "payments" / "models.py").write_text(
        "class Order(Base):\n    __tablename__ = 'payments'\n    id = Column(Integer)\n"
    )
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    ).stdout.strip()
    return str(tmp_path), sha


async def _await_gate(env, wf_id, gate_name, *, max_polls: int = 30):
    """Bounded on purpose: before Task 9's implementation exists, `run()`
    never opens a "risk" gate at all, so an unbounded version of this
    helper would hang forever (the workflow completes normally in the
    background while polling keeps returning an empty list) rather than
    failing the test cleanly."""
    for _ in range(max_polls):
        try:
            items = await env.client.get_workflow_handle(wf_id).query(
                AssessmentWorkflow.pending_decisions
            )
            if items and items[0].gate == gate_name:
                return items
        except Exception:  # noqa: BLE001 -- not started
            pass
        await env.sleep(1)
    raise AssertionError(f"no {gate_name!r} gate became pending after {max_polls} polls")


def _acts(sha, discover_hit, risk_hit):
    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    @activity.defn(name="discover_memo_load")
    async def fake_discover_hit(inp) -> CapabilityMap:
        return discover_hit

    @activity.defn(name="risk_memo_load")
    async def fake_risk_hit(inp) -> UnifiedRiskMap:
        return risk_hit

    return [
        real_pin,
        fake_baseline,
        fake_scaffold,
        fake_probe,
        fake_secrets,
        fake_misconfig,
        fake_outliers,
        fake_deps,
        assessment_resolve_tree,
        *SCAN_ACTS,
        discover_context,
        fake_discover_hit,
        fake_risk_hit,
        load_dispositions,
    ]


async def test_a_rejected_block_leaves_report_generate_finish_skipped(
    gate_repo, tmp_path, monkeypatch
):
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            items = await _await_gate(env, wf_id, "risk")
            assert items[0].gate == "risk"

            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(
                    gate="risk",
                    round=1,
                    outcome=GateOutcome.REJECT,
                    decided_by="human",
                    reviewer="alice",
                    comments="not overriding",
                ),
            )
            result = await handle.result()

    assert result.gates is not None
    assert result.gates.verdict == RiskGateVerdict.BLOCK
    assert result.gate_override is None
    assert result.terminal_status == PARTIAL
    for phase_id in (PhaseId.REPORT, PhaseId.GENERATE, PhaseId.FINISH):
        row = next(p for p in result.phases if p.phase is phase_id)
        assert row.collected.state is CollectionState.NOT_COLLECTED
        assert "risk gate" in row.collected.reason


async def test_an_approved_block_stamps_an_override_and_continues(gate_repo, tmp_path, monkeypatch):
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, wf_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(
                    gate="risk",
                    round=1,
                    outcome=GateOutcome.APPROVE,
                    decided_by="human",
                    reviewer="alice",
                    comments="known issue, ticket filed",
                ),
            )
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.BLOCK
    assert result.gate_override is not None
    assert result.gate_override.approved_by == "human"
    assert result.terminal_status == PARTIAL  # E-51/E-52 still unbuilt
    for phase_id in (PhaseId.REPORT, PhaseId.GENERATE, PhaseId.FINISH):
        row = next(p for p in result.phases if p.phase is phase_id)
        # Distinguishable from the rejected case's reason (GD2's whole
        # point) -- compared against risk_gate_skipped() itself, not a
        # hardcoded "not implemented" substring, so this stays true once
        # E-51/E-52 land and REPORT/GENERATE/FINISH stop being unbuilt
        # stubs (their MEASURED reason, whatever it becomes, will still
        # differ from risk_gate_skipped()'s).
        assert row.collected.reason != risk_gate_skipped(phase_id).collected.reason


async def test_a_revised_block_is_treated_as_rejected(gate_repo, tmp_path, monkeypatch):
    """GD2's amendment, pinned: REVISE has no round concept for this gate,
    so it leaves REPORT/GENERATE/FINISH unreached exactly like REJECT."""
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, wf_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(
                    gate="risk",
                    round=1,
                    outcome=GateOutcome.REVISE,
                    decided_by="human",
                    comments="try again?",
                ),
            )
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.BLOCK
    assert result.gate_override is None
    for phase_id in (PhaseId.REPORT, PhaseId.GENERATE, PhaseId.FINISH):
        row = next(p for p in result.phases if p.phase is phase_id)
        assert row.collected.reason == risk_gate_skipped(phase_id).collected.reason


async def test_load_dispositions_failing_falls_back_to_zero_not_a_crash(
    gate_repo, tmp_path, monkeypatch
):
    """Failure-modes row: 'load_dispositions activity fails -> treated as
    zero dispositions loaded for this run.' A real disposition sits in the
    board, but the activity always raises, so run_or_degrade's fallback
    must still let BLOCK fire -- proving the fallback is conservative
    (nothing is treated as accepted that couldn't be confirmed), not a
    silent 'assume everything is dispositioned.'"""
    repo_dir, sha = gate_repo
    db = tmp_path / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(db))
    key = testability_identity(_blocker())

    store = BoardFindingDispositionStore(db=db)
    store.apply(
        "acme",
        FindingDisposition(
            kind="testability",
            key=key,
            disposition=Disposition.ACCEPTED_RISK,
            approved_by="maks",
            reason="pre-seeded, should be unreachable",
            decided_at=datetime.now(UTC),
        ),
        expected_version=0,
        actor="maks",
    )
    store.close()

    @activity.defn(name="triage_resolve_commit")
    async def real_pin(inp: TriagePinInput) -> TriagePin:
        return TriagePin(commit_sha=sha, toolchain="python")

    @activity.defn(name="discover_memo_load")
    async def fake_discover_hit(inp) -> CapabilityMap:
        return _blocking_capability_map()

    @activity.defn(name="risk_memo_load")
    async def fake_risk_hit(inp) -> UnifiedRiskMap:
        return _high_risk_map()

    @activity.defn(name="load_dispositions")
    async def failing_load_dispositions(inp):
        raise RuntimeError("board unavailable")

    acts = [
        real_pin,
        fake_baseline,
        fake_scaffold,
        fake_probe,
        fake_secrets,
        fake_misconfig,
        fake_outliers,
        fake_deps,
        assessment_resolve_tree,
        *SCAN_ACTS,
        discover_context,
        fake_discover_hit,
        fake_risk_hit,
        failing_load_dispositions,
    ]
    wf_id = f"assess-{uuid.uuid4()}"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=wf_id,
                task_queue=TASK_QUEUE,
            )
            # The pre-seeded disposition would clear this BLOCK if it were
            # read; the gate must still open, proving it was not.
            items = await _await_gate(env, wf_id, "risk")
            assert items[0].gate == "risk"
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(gate="risk", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.BLOCK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_workflow_risk_gate_e2e.py -v -m temporal`
Expected: FAIL — `AssertionError: no 'risk' gate became pending after 30 polls`. Before this task's implementation, `run()` never calls `_risk_gate` at all, so the workflow completes normally in the background (the old code path) while `_await_gate` polls `pending_decisions` and only ever sees an empty list. `_await_gate`'s poll cap turns that into a clean, bounded failure rather than a hang.

- [ ] **Step 3: Write minimal implementation**

Modify `src/sdlc/workflows/assessment.py`:

Add to the `with workflow.unsafe.imports_passed_through():` import block, alongside the existing `from ..assessment.activities import (...)`:

```python
    from ..assessment.activities import (
        ...,  # existing names
        load_dispositions,
        LoadDispositionsInput,
    )
    from ..assessment.gates.checks import evaluate
    from ..assessment.gates.models import RiskGateOverride, RiskGateReport, RiskGateVerdict
    from ..dispositions.models import FindingDisposition
    from ..models import GateDecision
    from ..pending import GateContext
```

Add near `no_assess`, before `assemble`:

```python
class RiskGateStepOutcome(BaseModel):
    """_risk_gate's result: the report (None only when ASSESS did not
    measure), the audited override (None unless BLOCK was approved), and
    whether REPORT/GENERATE/FINISH must be skipped (GD1/GD2)."""

    gates: RiskGateReport | None = None
    override: RiskGateOverride | None = None
    blocked: bool = False


def risk_gate_skipped(phase: PhaseId) -> PhaseResult:
    """A phase that exists but was never reached because the risk gate
    (FR-917) BLOCKed and was not overridden (E-50 GD2)."""
    return PhaseResult(
        phase=phase,
        collected=Measurement.not_collected(
            "not run: risk gate BLOCKed and was not overridden (FR-917)"
        ),
    )


def _risk_gate_summary(report: RiskGateReport) -> str:
    lines = [f"verdict: {report.verdict.value}"]
    if report.reasons:
        lines.append("reasons:")
        lines.extend(f"  {r}" for r in report.reasons)
    if report.deferred:
        lines.append("deferred:")
        lines.extend(f"  {d}" for d in report.deferred)
    return "\n".join(lines)


def risk_override_from(decision: GateDecision) -> RiskGateOverride | None:
    """FR-304, mirroring triage.py's override_from -- every APPROVE records
    an override, with approved_by carrying decided_by VERBATIM (E-50 GD5)."""
    if not decision.approved:
        return None
    return RiskGateOverride(
        approved_by=decision.decided_by,
        reviewer=decision.reviewer,
        reason=decision.comments or "",
        decided_at=decision.decided_at or workflow.now(),
        gate_round=decision.round,
    )
```

Modify `assemble()`'s signature and body to accept and pass through `gates`/`gate_override`:

```python
def assemble(
    repo_dir: str,
    init: InitOutcome,
    admitted: bool,
    reason: str,
    rest: list[PhaseResult] | None = None,
    scan: ScanResult | None = None,
    discover: CapabilityMap | None = None,
    risk: UnifiedRiskMap | None = None,
    gates: RiskGateReport | None = None,
    gate_override: RiskGateOverride | None = None,
) -> Assessment:
    ...  # unchanged body up to the return
    return Assessment(
        repo_dir=repo_dir,
        commit_sha=t.commit_sha if t else "",
        toolchain=t.toolchain if t else None,
        triage=t,
        admitted=admitted,
        admission_reason=reason,
        phases=phases,
        terminal_status=terminal_status(admitted, phases),
        scan=scan,
        discover=discover,
        risk=risk,
        gates=gates,
        gate_override=gate_override,
    )
```

Add `_risk_gate` to `AssessmentWorkflow`, right after `_judge`:

```python
    async def _risk_gate(
        self, inp: AssessmentInput, discover_out: DiscoverOutcome, assess_out: AssessOutcome
    ) -> RiskGateStepOutcome:
        """E-50 (FR-917, GD1/GD2). The checks run right after ASSESS. A
        BLOCK opens a HARD gate the same way the readiness gate does;
        APPROVE stamps an audited override and REPORT/GENERATE/FINISH
        proceed; REJECT (or a HOLD timeout) leaves them unreached.

        GD2 names only APPROVE/REJECT; GateOutcome also has REVISE
        (TriageWorkflow's readiness gate uses it to mean "fix the build and
        re-triage," a round-based retry). The risk gate has no round or
        retry concept -- a deterministic verdict over the current risk map
        does not change by asking again -- so REVISE is deliberately
        treated identically to REJECT here: `decision.approved` is False
        for both, and only an explicit APPROVE unblocks. This is a decision
        recorded once, here, not an unexamined fallthrough.
        """
        if assess_out.risk is None:
            return RiskGateStepOutcome()

        dispositions = await run_or_degrade(
            load_dispositions,
            LoadDispositionsInput(project=inp.project_key),
            ASSESS_ACT,
            fallback=lambda: (),
        )
        report = evaluate(assess_out.risk, discover_out.map, dispositions)
        if report.verdict is not RiskGateVerdict.BLOCK:
            return RiskGateStepOutcome(gates=report)

        decision = await self._gate(
            "risk", inp.gates, context=GateContext(spec_summary=_risk_gate_summary(report))
        )
        if decision.approved:
            return RiskGateStepOutcome(gates=report, override=risk_override_from(decision))
        return RiskGateStepOutcome(gates=report, blocked=True)
```

Modify `run()`:

```python
@workflow.run
async def run(self, inp: AssessmentInput) -> Assessment:
    init = await self._init(inp)
    if init.triage is None:
        return self._done(assemble(inp.repo_dir, init, False, init.result.collected.reason))

    ok, why = admits(init.triage, require_human=True)
    if not ok:
        return self._done(assemble(inp.repo_dir, init, False, why))

    self._status = "running"
    scan_out = await self._scan(inp, init.triage)
    discover_out = await self._discover(inp, init.triage, scan_out)
    assess_out = await self._assess(inp, init.triage, discover_out, scan_out)
    gate_out = await self._risk_gate(inp, discover_out, assess_out)

    if gate_out.blocked:
        rest = [
            scan_out.result,
            discover_out.result,
            assess_out.result,
            risk_gate_skipped(PhaseId.REPORT),
            risk_gate_skipped(PhaseId.GENERATE),
            risk_gate_skipped(PhaseId.FINISH),
        ]
    else:
        rest = [
            scan_out.result,
            discover_out.result,
            assess_out.result,
            await self._report(inp),
            await self._generate(inp),
            await self._finish(inp),
        ]
    return self._done(
        assemble(
            inp.repo_dir,
            init,
            True,
            why,
            rest,
            scan=scan_out.scan,
            discover=discover_out.map,
            risk=assess_out.risk,
            gates=gate_out.gates,
            gate_override=gate_out.override,
        )
    )
```

Update the class docstring (it currently says the gate is future work):

```python
@workflow.defn
class AssessmentWorkflow(GateHost):
    """Inherits GateHost for two gates: the readiness gate is the CHILD
    TriageWorkflow's; the risk gate (E-50, FR-917) is this workflow's own,
    opened by _risk_gate right after ASSESS."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assessment_workflow_risk_gate_e2e.py -v -m temporal`
Expected: PASS (4 tests)

Then run the full existing e2e suite to confirm nothing regressed:

Run: `pytest tests/test_assessment_workflow_e2e.py -v -m temporal`
Expected: PASS (all previously-passing tests still pass — `assemble()`'s new keyword-only parameters default to `None`, so every existing call site is unaffected)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/assessment.py tests/test_assessment_workflow_risk_gate_e2e.py
git commit -m "feat(assessment): wire the risk gate into run() -- BLOCK pauses, APPROVE overrides, REJECT skips (E-50 GD1/GD2)"
```

---

### Task 10: WARN's non-blocking path, and a disposition clearing a BLOCK on re-run

**Files:**
- Modify: `tests/test_assessment_workflow_risk_gate_e2e.py`

**Interfaces:**
- Consumes: Task 9's fixtures and helpers, `dispositions.store.BoardFindingDispositionStore`, `dispositions.models.FindingDisposition`, `scan.models.testability_identity`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_workflow_risk_gate_e2e.py`:

```python
from sdlc.assessment.risk.models import (
    Composite,
    Factor,
    RiskSource,
    Severity,
    StrideCategory,
    Vulnerability,
    VulnerabilityClass,
)
from sdlc.assessment.scan.models import testability_identity


def _warn_risk_map() -> UnifiedRiskMap:
    cap = capability_risk(
        bc_id="BC-001",
        unified=Composite(
            value=Measurement.measured(0.65),
            factors=(Factor(key="x", value=Measurement.measured(0.65)),),
        ),
    )
    return UnifiedRiskMap(capabilities=(cap,), collected=Measurement.measured(1.0))


async def test_a_warn_verdict_opens_no_gate_and_phases_proceed(gate_repo, tmp_path, monkeypatch):
    repo_dir, sha = gate_repo
    monkeypatch.setenv("SDLC_BOARD_DB", str(tmp_path / "board.sqlite3"))
    acts = _acts(sha, _clean_capability_map(), _warn_risk_map())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=f"assess-{uuid.uuid4()}",
                task_queue=TASK_QUEUE,
            )
            # No signal is sent: a WARN must never leave the workflow waiting.
            result = await handle.result()

    assert result.gates.verdict == RiskGateVerdict.WARN
    assert result.gate_override is None
    row = next(p for p in result.phases if p.phase is PhaseId.REPORT)
    assert "not implemented" in row.collected.reason  # phases ran normally


async def test_a_testability_disposition_clears_the_block_on_rerun(
    gate_repo, tmp_path, monkeypatch
):
    """FR-917's persistence promise, end to end: the SAME finding BLOCKs the
    first run and does not even open a gate on the second, once dispositioned."""
    repo_dir, sha = gate_repo
    db = tmp_path / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(db))
    acts = _acts(sha, _blocking_capability_map(), _high_risk_map())
    key = testability_identity(_blocker())

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            first_id = f"assess-{uuid.uuid4()}"
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=first_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, first_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(gate="risk", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            first_result = await handle.result()
            assert first_result.gates.verdict == RiskGateVerdict.BLOCK

            store = BoardFindingDispositionStore(db=db)
            store.apply(
                "acme",
                FindingDisposition(
                    kind="testability",
                    key=key,
                    disposition=Disposition.ACCEPTED_RISK,
                    approved_by="maks",
                    reason="known pattern, ticket filed",
                    decided_at=datetime.now(UTC),
                ),
                expected_version=0,
                actor="maks",
            )
            store.close()

            second_id = f"assess-{uuid.uuid4()}"
            handle2 = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=second_id,
                task_queue=TASK_QUEUE,
            )
            second_result = await handle2.result()

    assert second_result.gates.verdict == RiskGateVerdict.PASS
    assert second_result.gate_override is None


def _confirmed_vuln_risk_map(bc_id="BC-001") -> UnifiedRiskMap:
    vuln = Vulnerability(
        key="SS1:hardcoded-secret:payments/api.py:",
        classification=VulnerabilityClass.CONFIRMED,
        severity=Severity.HIGH,
        stride_category=StrideCategory.INFORMATION_DISCLOSURE,
        path="payments/api.py",
        source=RiskSource.BASELINE,
    )
    cap = capability_risk(bc_id=bc_id, vulnerabilities=(vuln,))
    # judgment MEASURED: CONFIRMED is only reachable through the judgment
    # layer (GD3) -- unlike the testability fixtures above, this map must
    # carry it directly since faking risk_memo_load bypasses _judge() (the
    # method that would otherwise stamp it) entirely.
    return UnifiedRiskMap(
        capabilities=(cap,), collected=Measurement.measured(1.0), judgment=Measurement.measured(1.0)
    )


async def test_a_vulnerability_disposition_clears_the_block_on_rerun(
    gate_repo, tmp_path, monkeypatch
):
    """The spec's own first e2e case: a confirmed vulnerability opens the
    gate, and `sdlc risk dispose --kind vulnerability` clears it on
    re-run -- mirrors the testability version above but for the OTHER live
    clause, which the testability case alone does not exercise."""
    repo_dir, sha = gate_repo
    db = tmp_path / "board.sqlite3"
    monkeypatch.setenv("SDLC_BOARD_DB", str(db))
    acts = _acts(sha, _clean_capability_map(), _confirmed_vuln_risk_map())
    key = "SS1:hardcoded-secret:payments/api.py:"

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=acts):
            first_id = f"assess-{uuid.uuid4()}"
            handle = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=first_id,
                task_queue=TASK_QUEUE,
            )
            await _await_gate(env, first_id, "risk")
            await handle.signal(
                AssessmentWorkflow.submit_gate_decision,
                GateDecision(gate="risk", round=1, outcome=GateOutcome.REJECT, decided_by="human"),
            )
            first_result = await handle.result()
            assert first_result.gates.verdict == RiskGateVerdict.BLOCK

            store = BoardFindingDispositionStore(db=db)
            store.apply(
                "acme",
                FindingDisposition(
                    kind="vulnerability",
                    key=key,
                    disposition=Disposition.ACCEPTED_RISK,
                    approved_by="maks",
                    reason="known issue, ticket filed",
                    decided_at=datetime.now(UTC),
                ),
                expected_version=0,
                actor="maks",
            )
            store.close()

            second_id = f"assess-{uuid.uuid4()}"
            handle2 = await env.client.start_workflow(
                AssessmentWorkflow.run,
                AssessmentInput(
                    repo_dir=repo_dir,
                    project_key="acme",
                    propose_discover=False,
                    propose_risk=False,
                ),
                id=second_id,
                task_queue=TASK_QUEUE,
            )
            second_result = await handle2.result()

    assert second_result.gates.verdict == RiskGateVerdict.PASS
    assert second_result.gate_override is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_assessment_workflow_risk_gate_e2e.py -v -m temporal -k "warn or disposition or vulnerability"`
Expected: FAIL if run against a pre-Task-9 tree (`ImportError`); once Task 9 has landed, this step instead confirms the two NEW tests fail before this task's fixtures exist — since Task 9 already wired `_risk_gate` fully, these two tests should in fact PASS immediately against Task 9's implementation with no further production code change. Run them to confirm.

- [ ] **Step 3: No production code changes are needed**

Task 9's `_risk_gate`/`evaluate`/`load_dispositions` wiring already implements WARN's non-blocking path and disposition persistence in full; this task exists to pin both properties with their own dedicated, independently-reviewable e2e coverage (the persistence promise is FR-917's headline requirement and deserves its own test, not a footnote on Task 9's BLOCK tests).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_assessment_workflow_risk_gate_e2e.py -v -m temporal`
Expected: PASS (7 tests total in this file)

- [ ] **Step 5: Commit**

```bash
git add tests/test_assessment_workflow_risk_gate_e2e.py
git commit -m "test(assessment): WARN opens no gate; a disposition clears a BLOCK on re-run (E-50 FR-917 persistence)"
```

---

## Final verification

- [ ] Run the full unit suite: `pytest -m "not temporal"` — expect PASS, no regressions in `capability/`, `risk/`, `discover/`, `scan/`, or `assessment/` tests.
- [ ] Run the full temporal suite: `pytest -m temporal` — expect PASS, including the untouched `test_assessment_workflow_e2e.py` and `test_triage_workflow_e2e.py` (or equivalent) files.
- [ ] `sdlc risk dispose --help` and `sdlc risk list --help` resolve through `build_parser()` with no import errors.
- [ ] Confirm no pure module under `assessment/gates/` or `dispositions/models.py` imports `assessment/models.py`, `activities.py`, or `temporalio` (`grep -rn "^from \.\.\.models\|^from \.\.\.activities\|temporalio" src/sdlc/assessment/gates/ src/sdlc/dispositions/models.py` should return nothing).
