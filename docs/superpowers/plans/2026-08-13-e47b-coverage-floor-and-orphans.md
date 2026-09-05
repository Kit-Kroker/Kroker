# E-47b — Capability coverage floor and orphan classification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute, from a pinned tree and an identified capability set, what
fraction of the repository the capability model explains, and classify every
unexplained file as `attached`, `infrastructure`, `dead` or `unclassified`.

**Architecture:** Three pure modules in a new `src/sdlc/assessment/discover/`
package. `refgraph.py` extracts and resolves import edges; `attribution.py`
walks a fixed bucket precedence and computes the ratio; `models.py` holds the
typed artifact whose validators make a wrong report unconstructible. Nothing is
wired into a workflow — `_discover` keeps reporting `not_collected` and E-48
calls `attribute()` when it lands.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-13-e47b-coverage-floor-and-orphans-design.md`

## Global Constraints

- **Purity.** `discover/` imports Pydantic, stdlib, `sdlc.measurement`, and the
  three pure `scan/` rule modules (`sources.py`, `testpaths.py`,
  `configpaths.py`). It must NEVER import `sdlc.models`, `sdlc.activities`,
  `temporalio`, or `scan/signals/*`. A dependency there is a reviewable import.
- **No execution of repository code.** Every input is a function parameter. No
  disk reads, no subprocess, no git. (NFR-9.)
- **Determinism (NFR-10).** Every collection is sorted before it enters an
  artifact. Same inputs → byte-identical `model_dump_json()`.
- **FR-915.** A value that was not measured is `Measurement.not_collected(reason)`,
  never `measured(0.0)` and never `measured(1.0)`.
- **Derived, never assigned.** `meets_floor` and `counts` are validated against
  their own derivation, following `_confidence_is_derived` and
  `_terminal_status_matches_derivation`.
- `DEFAULT_COVERAGE_FLOOR = 0.90`, `DEAD_GUARD_MAX_UNRESOLVED = 0.10`.
- Line width 79. Run `pytest -q` from the repo root.

### Plan-level decisions (not in the spec; recorded here)

- **P-D1 — an all-dotted tree does not trip the dead guard.** The guard reads
  the unresolved *relative* rate. A tree with no relative imports (an all-Java
  or all-C# repository) yields `not_collected` for that rate, and the guard does
  NOT trip. Absence of relative imports is not evidence of extractor failure,
  and treating it as failure would disable dead detection for entire language
  families. The guard trips only on `MEASURED` and `> max_unresolved`.
- **P-D2 — determinism is asserted in the discover tests, not by extending
  `test_every_pure_signal_module_is_order_independent`.** That test's name and
  docstring scope it to *signal* modules; `discover/` holds none. The spec said
  "join rather than grow a second test"; the honest reading is to apply the same
  standard (shuffled inputs, `model_dump_json()` equality) in the module's own
  test file. Same assertion, correct name.

---

### Task 1: Promote `is_config_path` to a shared rule module

Spec D10. Two consumers now read this table, which is the condition that
produced `scan/testpaths.py` and `scan/sources.py`. The second half — SS3
declaring it in `rule_modules` — is the load-bearing part: `rules_sha` hashes
declared rule modules into the memo key, so a shared table SS3 reads but does
not declare means editing a config pattern silently serves a stale SS3.

**Files:**
- Create: `src/sdlc/assessment/scan/configpaths.py`
- Modify: `src/sdlc/assessment/scan/signals/config_infra.py:42-52,135-139,262`
- Modify: `src/sdlc/assessment/scan/registry.py:95` (add `_CONFIGPATHS`), `:130-133` (SS3 spec)
- Modify: `src/sdlc/assessment/activities.py:291`
- Test: `tests/test_scan_configpaths.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `sdlc.assessment.scan.configpaths.is_config_path(path: str) -> bool`
  and `CONFIG_PATTERNS: tuple[re.Pattern[str], ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scan_configpaths.py
"""D10: the config-path table is shared, so SS3 must declare it."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan import rules
from sdlc.assessment.scan.configpaths import is_config_path
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.registry import SCAN_SIGNALS

_CONFIGPATHS = "sdlc.assessment.scan.configpaths"


@pytest.mark.parametrize(
    "path",
    [
        "Dockerfile",
        "svc/Dockerfile.prod",
        "docker-compose.yml",
        ".env",
        ".env.production",
        "appsettings.Development.json",
        "src/main/resources/application-prod.yaml",
        "k8s/deploy.yaml",
        "infra/main.tf",
        "nginx.conf",
    ],
)
def test_config_paths_are_recognized(path):
    assert is_config_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/payments/api.py",
        "README.md",
        "tests/test_api.py",
        "app/page.tsx",
    ],
)
def test_non_config_paths_are_not(path):
    assert not is_config_path(path)


def test_ss3_declares_the_shared_table():
    assert _CONFIGPATHS in SCAN_SIGNALS[ScanSignalId.SS3].rule_modules


def test_editing_the_table_moves_ss3s_memo_key(monkeypatch):
    """The declaration is only real if rules_sha actually hashes it."""
    before = rules.rules_sha(ScanSignalId.SS3)
    real = rules.module_sha

    def shifted(dotted: str) -> str:
        return "deadbeef" if dotted == _CONFIGPATHS else real(dotted)

    monkeypatch.setattr(rules, "module_sha", shifted)
    assert rules.rules_sha(ScanSignalId.SS3) != before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scan_configpaths.py -v`
Expected: FAIL — `ModuleNotFoundError: sdlc.assessment.scan.configpaths`

- [ ] **Step 3: Create the shared module**

```python
# src/sdlc/assessment/scan/configpaths.py
"""Which paths are CONFIGURATION / INFRASTRUCTURE paths -- shared by SS3 and
by discover/attribution.py's infrastructure bucket (E-47b D10).

A scan-level constant belonging to no single signal, sited here for the reason
sources.py and testpaths.py are: two consumers now read it, so SS3 declares it
as a `rule_module` and rules_sha hashes it into SS3's memo key. Without that,
adding a pattern would move SS3's output while its key stood still -- the
E-3 / D10 hazard.
"""

from __future__ import annotations

import re

CONFIG_PATTERNS: tuple[re.Pattern[str], ...] = (
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


def is_config_path(path: str) -> bool:
    """Whether configuration and infrastructure rules apply to a path."""
    return any(pattern.search(path) for pattern in CONFIG_PATTERNS)
```

- [ ] **Step 4: Point the old call sites at it**

In `src/sdlc/assessment/scan/signals/config_infra.py`, delete the
`_CONFIG_PATTERNS` tuple (lines 42-52) and the `is_config_path` definition
(lines 135-139), and add to the import block:

```python
from ..configpaths import is_config_path
```

The internal call at line 262 (`if not is_config_path(path):`) keeps working
unchanged.

**Do not remove that import as "unused".** It is doing two jobs:
`config_infra.py` calls it at line 262, and
`tests/test_scan_ss3_config_infra.py:96-101` reaches it as
`config_infra.is_config_path(...)`. Keeping the name bound in `config_infra`
is what makes this task behaviour-preserving for SS3's existing tests. A later
increment may repoint that test at `configpaths` directly; this one does not,
because a refactor that also rewrites the tests proving it is behaviour-
preserving proves less.

Verify nothing else used the deleted tuple:

```bash
grep -rn "_CONFIG_PATTERNS" src/ tests/
```

Expected: no matches.

In `src/sdlc/assessment/activities.py`, line 291 reads
`if config_infra.is_config_path(p)`. Change it to use the new home — leaving a
signal module as a pass-through re-export is the coupling this task removes.
Add `from .scan.configpaths import is_config_path` to that module's imports and
change the call to `if is_config_path(p)`.

- [ ] **Step 5: Declare it on SS3**

In `src/sdlc/assessment/scan/registry.py`, after the `_TESTPATHS` constant
(line 95) add:

```python
# scan.configpaths, shared by SS3 (config rules) and E-47b's attribution
# module. SS3 hashes it, or editing a pattern would move SS3's output while
# its key stood still (D10).
_CONFIGPATHS = f"{_SIG.rsplit('.', 1)[0]}.configpaths"
```

and change the SS3 entry (lines 130-133) to:

```python
    ScanSignalId.SS3: _spec(
        ScanSignalId.SS3, 1, SignalSource.EXTENDED,
        module=f"{_SIG}.config_infra", activity="scan_config_infra",
        inherits=("triage:misconfig",),
        rule_modules=(_CONFIGPATHS,)),
```

- [ ] **Step 6: Run the new test and the SS3 suite**

Run: `pytest tests/test_scan_configpaths.py tests/test_scan_ss3_config_infra.py tests/test_scan_rules_sha.py tests/test_scan_registry.py -v`
Expected: PASS — SS3's existing tests are unchanged, which is the point: the
move is behaviour-preserving.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/configpaths.py \
        src/sdlc/assessment/scan/signals/config_infra.py \
        src/sdlc/assessment/scan/registry.py \
        src/sdlc/assessment/activities.py \
        tests/test_scan_configpaths.py
git commit -m "refactor(scan): promote is_config_path to a shared rule module; SS3 declares it (E-47b D10)"
```

---

### Task 2: `discover/models.py` — the artifact and its validators

Spec "Data model". The validators are the deliverable: a `dead` file citing a
capability, a `counts` map disagreeing with `files`, or a `not_collected`
coverage that claims to meet the floor must all be unconstructible.

**Files:**
- Create: `src/sdlc/assessment/discover/__init__.py` (empty)
- Create: `src/sdlc/assessment/discover/models.py`
- Test: `tests/test_discover_models.py`

**Interfaces:**
- Consumes: `sdlc.measurement.Measurement`, `CollectionState`.
- Produces: `FileBucket`, `BUCKET_PRECEDENCE`, `ACCOUNTED_FOR`,
  `CITES_CAPABILITIES`, `FileAttribution`, `UnresolvedEdge`, `ReferenceGraph`,
  `AttributionReport`, `DEFAULT_COVERAGE_FLOOR`, `DEAD_GUARD_MAX_UNRESOLVED`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_models.py
"""E-47b: the report's validators, which are the artifact's real contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sdlc.assessment.discover.models import (
    ACCOUNTED_FOR,
    BUCKET_PRECEDENCE,
    DEFAULT_COVERAGE_FLOOR,
    AttributionReport,
    FileAttribution,
    FileBucket,
    ReferenceGraph,
)
from sdlc.measurement import Measurement

EMPTY_GRAPH = ReferenceGraph(
    unresolved_relative_rate=Measurement.not_collected("no relative imports")
)


def _report(files, coverage, *, floor=DEFAULT_COVERAGE_FLOOR, meets=None, tripped=False):
    counts = {b: sum(1 for f in files if f.bucket is b) for b in FileBucket}
    if meets is None:
        meets = coverage.value is not None and coverage.value >= floor
    return AttributionReport(
        files=tuple(files),
        counts=counts,
        coverage=coverage,
        floor=floor,
        meets_floor=meets,
        dead_guard_tripped=tripped,
        graph=EMPTY_GRAPH,
    )


def test_precedence_is_declaration_order():
    assert BUCKET_PRECEDENCE == (
        FileBucket.MEMBER,
        FileBucket.INFRASTRUCTURE,
        FileBucket.ATTACHED,
        FileBucket.DEAD,
        FileBucket.UNCLASSIFIED,
    )
    assert ACCOUNTED_FOR == frozenset(BUCKET_PRECEDENCE[:3])


def test_member_must_cite_a_capability():
    with pytest.raises(ValidationError, match="must cite"):
        FileAttribution(path="a.py", bucket=FileBucket.MEMBER, rule="capability_member")


def test_dead_must_not_cite_a_capability():
    with pytest.raises(ValidationError, match="must not cite"):
        FileAttribution(
            path="a.py",
            bucket=FileBucket.DEAD,
            rule="no_static_inbound_reference",
            capabilities=("BC-001",),
        )


def test_capabilities_must_be_sorted_and_deduped():
    with pytest.raises(ValidationError, match="sorted"):
        FileAttribution(
            path="a.py",
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            capabilities=("BC-002", "BC-001"),
        )


def test_counts_must_agree_with_files():
    good = FileAttribution(
        path="a.py", bucket=FileBucket.MEMBER, rule="capability_member", capabilities=("BC-001",)
    )
    with pytest.raises(ValidationError, match="counts"):
        AttributionReport(
            files=(good,),
            counts={b: 0 for b in FileBucket},
            coverage=Measurement.measured(1.0),
            meets_floor=True,
            dead_guard_tripped=False,
            graph=EMPTY_GRAPH,
        )


def test_counts_must_carry_every_bucket_including_zeros():
    with pytest.raises(ValidationError, match="every bucket"):
        AttributionReport(
            files=(),
            counts={FileBucket.MEMBER: 0},
            coverage=Measurement.not_collected("no source files"),
            meets_floor=False,
            dead_guard_tripped=False,
            graph=EMPTY_GRAPH,
        )


def test_meets_floor_is_derived_not_assigned():
    files = [
        FileAttribution(
            path="a.py",
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            capabilities=("BC-001",),
        )
    ]
    with pytest.raises(ValidationError, match="derived"):
        _report(files, Measurement.measured(1.0), meets=False)


def test_not_collected_coverage_never_meets_the_floor():
    with pytest.raises(ValidationError, match="derived"):
        _report([], Measurement.not_collected("no capabilities"), meets=True)


def test_not_collected_coverage_with_meets_false_constructs():
    report = _report([], Measurement.not_collected("no capabilities"), meets=False)
    assert report.meets_floor is False


def test_exactly_the_floor_meets_it():
    files = [
        FileAttribution(
            path=f"m{i}.py",
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            capabilities=("BC-001",),
        )
        for i in range(9)
    ] + [FileAttribution(path="d.py", bucket=FileBucket.DEAD, rule="no_static_inbound_reference")]
    assert _report(files, Measurement.measured(0.90)).meets_floor is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_models.py -v`
Expected: FAIL — `ModuleNotFoundError: sdlc.assessment.discover`

- [ ] **Step 3: Write the models**

```python
# src/sdlc/assessment/discover/models.py
"""FR-913 (E-47b): capability coverage and orphan classification contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as capability/models.py
and assessment/models.py must not: a dependency here would appear as a
reviewable import.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ...measurement import CollectionState, Measurement

DEFAULT_COVERAGE_FLOOR = 0.90
DEAD_GUARD_MAX_UNRESOLVED = 0.10


class FileBucket(str, Enum):
    """Declaration order IS precedence order (see BUCKET_PRECEDENCE), so
    there is no second list to disagree with this one -- PHASE_ORDER's rule.
    """

    MEMBER = "member"
    INFRASTRUCTURE = "infrastructure"
    ATTACHED = "attached"
    DEAD = "dead"
    UNCLASSIFIED = "unclassified"


BUCKET_PRECEDENCE: tuple[FileBucket, ...] = tuple(FileBucket)

# D4: a file counts FOR coverage when the assessment can say what it is.
ACCOUNTED_FOR: frozenset[FileBucket] = frozenset(
    {FileBucket.MEMBER, FileBucket.INFRASTRUCTURE, FileBucket.ATTACHED}
)

# Only these two buckets name capabilities. A dead file citing one, or an
# attached file citing none, is a contradiction the type should not express.
CITES_CAPABILITIES: frozenset[FileBucket] = frozenset({FileBucket.MEMBER, FileBucket.ATTACHED})


class FileAttribution(BaseModel):
    """One file's verdict, carrying the rule that produced it.

    Frozen, so `capabilities` is asserted sorted rather than sorted in place:
    a producer that emits discovery order is a determinism bug (NFR-10), and
    silently repairing it here would hide that.
    """

    model_config = {"frozen": True}
    path: str
    bucket: FileBucket
    rule: str
    detail: str = ""
    capabilities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _capabilities_match_bucket(self) -> "FileAttribution":
        cites = self.bucket in CITES_CAPABILITIES
        if cites and not self.capabilities:
            raise ValueError(
                f"bucket={self.bucket.value} must cite at least one "
                f"capability -- it is defined by its relation to one"
            )
        if not cites and self.capabilities:
            raise ValueError(
                f"bucket={self.bucket.value} must not cite capabilities "
                f"(got {self.capabilities}) -- an orphan by definition "
                f"belongs to none"
            )
        return self

    @model_validator(mode="after")
    def _capabilities_are_sorted(self) -> "FileAttribution":
        if list(self.capabilities) != sorted(set(self.capabilities)):
            raise ValueError(
                f"capabilities {self.capabilities} are not sorted and "
                f"deduped -- discovery order must not reach the artifact"
            )
        return self


class UnresolvedEdge(BaseModel):
    """An import we saw and could not turn into an edge. `relative` is the
    field the dead guard reads: a dotted import matching nothing is an
    external package, but a RELATIVE one is extractor failure (D6)."""

    model_config = {"frozen": True}
    source_path: str
    target: str  # the raw module string, verbatim
    form: str  # "python_relative", "js_bare", ...
    reason: str  # "no_matching_path" | "ambiguous_suffix"
    relative: bool


class ReferenceGraph(BaseModel):
    edges: tuple[tuple[str, str], ...] = ()  # (importer, imported)
    unresolved: tuple[UnresolvedEdge, ...] = ()
    parsed: tuple[str, ...] = ()  # extractor covers these
    unparsed: tuple[str, ...] = ()  # extension not in the table
    unresolved_relative_rate: Measurement


class AttributionReport(BaseModel):
    files: tuple[FileAttribution, ...] = ()
    counts: dict[FileBucket, int] = Field(default_factory=dict)
    coverage: Measurement  # the ratio, or not_collected
    floor: float = DEFAULT_COVERAGE_FLOOR
    meets_floor: bool
    dead_guard_tripped: bool = False
    graph: ReferenceGraph
    skipped: tuple[str, ...] = ()  # blobs that could not be read

    @model_validator(mode="after")
    def _counts_agree_with_files(self) -> "AttributionReport":
        missing = [b.value for b in FileBucket if b not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every bucket, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true"
            )
        for bucket in FileBucket:
            actual = sum(1 for f in self.files if f.bucket is bucket)
            if self.counts[bucket] != actual:
                raise ValueError(
                    f"counts[{bucket.value}]={self.counts[bucket]} but "
                    f"{actual} file(s) carry that bucket -- counts are "
                    f"derived from files, never assigned"
                )
        return self

    @model_validator(mode="after")
    def _meets_floor_is_derived(self) -> "AttributionReport":
        """Derived, never assigned, so a deserialized payload cannot disagree
        with its own arithmetic. A not_collected coverage NEVER meets the
        floor: an assessment that could not measure must not read as one that
        measured and passed (FR-915)."""
        expected = (
            self.coverage.state is CollectionState.MEASURED
            and self.coverage.value is not None
            and self.coverage.value >= self.floor
        )
        if self.meets_floor != expected:
            raise ValueError(
                f"meets_floor={self.meets_floor} does not match the derived "
                f"{expected} for coverage={self.coverage.state.value} "
                f"floor={self.floor} -- meets_floor is derived, never assigned"
            )
        return self
```

Also create an empty `src/sdlc/assessment/discover/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_models.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/ tests/test_discover_models.py
git commit -m "feat(discover): E-47b contracts -- buckets, attribution, derived meets_floor"
```

---

### Task 3: `discover/refgraph.py` — import-form extraction

Spec D6, first half. This task only extracts raw `(form, target)` pairs; Task 4
resolves them to paths. Split because a reviewer can reject a regex table while
accepting the resolver, and vice versa.

**Files:**
- Create: `src/sdlc/assessment/discover/refgraph.py`
- Test: `tests/test_discover_refgraph_forms.py`

**Interfaces:**
- Consumes: Task 2's models (not yet — this step is standalone).
- Produces:
  - `ImportForm` (NamedTuple: `name: str`, `extensions: frozenset[str]`,
    `pattern: re.Pattern[str]`, `relative: bool | None`)
  - `IMPORT_FORMS: tuple[ImportForm, ...]`
  - `EXTRACTOR_EXTENSIONS: frozenset[str]`
  - `extract(path: str, text: str) -> list[tuple[str, str]]` — `(form_name, target)`
  - `is_relative(form_name: str, target: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_refgraph_forms.py
"""D6: one fixture per import form. Breadth is the design choice; these
tests are what keep it from being breadth-without-evidence."""

from __future__ import annotations

import pytest

from sdlc.assessment.discover.refgraph import (
    EXTRACTOR_EXTENSIONS,
    extract,
    is_relative,
)


@pytest.mark.parametrize(
    "path,text,expected",
    [
        ("a.py", "import os\n", "os"),
        ("a.py", "from pkg.mod import thing\n", "pkg.mod"),
        ("a.py", "from . import sibling\n", "."),
        ("a.py", "from ..pkg import thing\n", "..pkg"),
        ("a.ts", "import x from './rel'\n", "./rel"),
        ("a.ts", "import 'side-effect'\n", "side-effect"),
        ("a.js", "const x = require('./dep')\n", "./dep"),
        ("a.js", "const x = await import('./lazy')\n", "./lazy"),
        ("a.ts", "export { x } from './re-export'\n", "./re-export"),
        ("a.go", '\timport "example.com/pkg/svc"\n', "example.com/pkg/svc"),
        ("A.java", "import com.acme.Orders;\n", "com.acme.Orders"),
        ("A.kt", "import com.acme.Orders\n", "com.acme.Orders"),
        ("a.rb", "require_relative 'helper'\n", "helper"),
        ("a.rb", "require 'json'\n", "json"),
        ("a.php", "use Acme\\Orders\\Service;\n", "Acme\\Orders\\Service"),
        ("a.php", "require_once 'bootstrap.php';\n", "bootstrap.php"),
        ("a.cs", "using Acme.Orders;\n", "Acme.Orders"),
        ("a.rs", "use crate::orders::api;\n", "crate::orders::api"),
        ("a.rs", "mod helpers;\n", "helpers"),
        ("a.ex", "alias Acme.Orders\n", "Acme.Orders"),
        ("a.swift", "import Orders\n", "Orders"),
    ],
)
def test_each_form_extracts_its_target(path, text, expected):
    assert expected in [target for _, target in extract(path, text)]


def test_an_unknown_extension_extracts_nothing():
    assert extract("a.md", "import os\n") == []
    assert ".md" not in EXTRACTOR_EXTENSIONS


def test_extraction_is_deduped_and_sorted():
    text = "import b\nimport a\nimport b\n"
    assert extract("m.py", text) == [("python_import", "a"), ("python_import", "b")]


@pytest.mark.parametrize(
    "form,target,expected",
    [
        ("python_from", ".sibling", True),
        ("python_from", "pkg.mod", False),
        ("js_from", "./rel", True),
        ("js_from", "../up", True),
        ("js_from", "react", False),
        ("ruby_require_relative", "helper", True),
        ("ruby_require", "json", False),
        ("rust_mod", "helpers", True),
        ("rust_use", "crate::a", False),
        ("jvm_import", "com.acme.X", False),
    ],
)
def test_relativeness(form, target, expected):
    assert is_relative(form, target) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_refgraph_forms.py -v`
Expected: FAIL — `ModuleNotFoundError: ...discover.refgraph`

- [ ] **Step 3: Write the extraction half**

```python
# src/sdlc/assessment/discover/refgraph.py
"""E-47b D6: import-edge extraction and resolution.

Broad and shallow by decision: one regex table keyed by import FORM, covering
the 18 languages in SOURCE_EXTENSIONS, rather than a per-language AST. The
accepted cost is that dynamic references (DI containers, reflection,
string-keyed module loading) are invisible; the dead guard (D7, attribution.py)
bounds what that costs, and test_discover_mutation_corpus pins the known false
positive rather than leaving it a docstring caveat.

Pure: text and paths in, a graph out. No disk, no subprocess (NFR-9).
"""

from __future__ import annotations

import posixpath
import re
from typing import NamedTuple


class ImportForm(NamedTuple):
    name: str
    extensions: frozenset[str]
    pattern: re.Pattern[str]  # group 1 is the target
    relative: bool | None = None  # None: decide from the target string


_PY = frozenset({".py"})
_JS = frozenset({".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"})
_JVM = frozenset({".java", ".kt", ".scala"})
_RB = frozenset({".rb"})
_PHP = frozenset({".php"})
_CS = frozenset({".cs"})
_RS = frozenset({".rs"})
_EX = frozenset({".ex", ".exs"})
_SWIFT = frozenset({".swift"})
_GO = frozenset({".go"})

IMPORT_FORMS: tuple[ImportForm, ...] = (
    ImportForm("python_from", _PY, re.compile(r"(?m)^\s*from\s+([.\w]+)\s+import\b")),
    ImportForm("python_import", _PY, re.compile(r"(?m)^\s*import\s+([\w.]+)")),
    ImportForm("js_from", _JS, re.compile(r"""(?m)\bfrom\s+['"]([^'"]+)['"]""")),
    ImportForm("js_bare", _JS, re.compile(r"""(?m)^\s*import\s+['"]([^'"]+)['"]""")),
    ImportForm("js_require", _JS, re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]""")),
    ImportForm("js_dynamic", _JS, re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]""")),
    ImportForm("go_import", _GO, re.compile(r"""(?m)^\s*(?:import\s+)?_?\s*"([\w./-]+)"\s*$""")),
    ImportForm(
        "jvm_import", _JVM, re.compile(r"(?m)^\s*import\s+(?:static\s+)?([\w.]+)"), relative=False
    ),
    ImportForm(
        "ruby_require_relative",
        _RB,
        re.compile(r"""(?m)^\s*require_relative\s+['"]([^'"]+)['"]"""),
        relative=True,
    ),
    ImportForm("ruby_require", _RB, re.compile(r"""(?m)^\s*require\s+['"]([^'"]+)['"]""")),
    ImportForm("php_use", _PHP, re.compile(r"(?m)^\s*use\s+([\w\\]+)"), relative=False),
    ImportForm(
        "php_include",
        _PHP,
        re.compile(
            r"""\b(?:require|include)(?:_once)?\s*\(?\s*"""
            r"""['"]([^'"]+)['"]"""
        ),
    ),
    ImportForm("csharp_using", _CS, re.compile(r"(?m)^\s*using\s+([\w.]+)\s*;"), relative=False),
    ImportForm("rust_use", _RS, re.compile(r"(?m)^\s*(?:pub\s+)?use\s+([\w:]+)"), relative=False),
    ImportForm("rust_mod", _RS, re.compile(r"(?m)^\s*(?:pub\s+)?mod\s+(\w+)\s*;"), relative=True),
    ImportForm(
        "elixir_alias", _EX, re.compile(r"(?m)^\s*(?:alias|import)\s+([\w.]+)"), relative=False
    ),
    ImportForm("swift_import", _SWIFT, re.compile(r"(?m)^\s*import\s+(\w+)"), relative=False),
)

# D7 clause 1's "extractor table": a file whose extension is absent here was
# never parsed, so it can never be called dead.
EXTRACTOR_EXTENSIONS: frozenset[str] = frozenset(
    ext for form in IMPORT_FORMS for ext in form.extensions
)

_BY_NAME: dict[str, ImportForm] = {f.name: f for f in IMPORT_FORMS}


def extension_of(path: str) -> str:
    return posixpath.splitext(path)[1].lower()


def extract(path: str, text: str) -> list[tuple[str, str]]:
    """(form_name, raw target) pairs, sorted and deduped (NFR-10)."""
    ext = extension_of(path)
    found: set[tuple[str, str]] = set()
    for form in IMPORT_FORMS:
        if ext not in form.extensions:
            continue
        for match in form.pattern.finditer(text):
            target = match.group(1).strip()
            if target:
                found.add((form.name, target))
    return sorted(found)


def is_relative(form_name: str, target: str) -> bool:
    """Relative imports are the ones whose failure is EXTRACTOR failure; a
    dotted import matching nothing is just an external package (D6)."""
    form = _BY_NAME[form_name]
    if form.relative is not None:
        return form.relative
    return target.startswith(".")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_refgraph_forms.py -v`
Expected: PASS (33 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/refgraph.py \
        tests/test_discover_refgraph_forms.py
git commit -m "feat(discover): import-form extraction across 18 languages (E-47b D6)"
```

---

### Task 4: `discover/refgraph.py` — resolution and `build()`

Spec D6, second half. The rule that carries the weight: **an ambiguous match is
recorded unresolved, never a guessed edge.** A wrong edge makes a dead file look
live *and* an attached file look attached to the wrong capability — one guess
corrupts two answers.

**Files:**
- Modify: `src/sdlc/assessment/discover/refgraph.py` (append)
- Test: `tests/test_discover_refgraph_resolve.py`

**Interfaces:**
- Consumes: Task 2's `ReferenceGraph`, `UnresolvedEdge`; Task 3's `extract`,
  `is_relative`, `EXTRACTOR_EXTENSIONS`, `extension_of`.
- Produces: `build(inventory: Mapping[str, str]) -> ReferenceGraph`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_refgraph_resolve.py
"""D6 resolution: an edge only exists when exactly one path matches."""

from __future__ import annotations

from sdlc.assessment.discover.refgraph import build
from sdlc.measurement import CollectionState


def test_relative_import_resolves_to_a_sibling():
    graph = build(
        {
            "src/app.py": "from . import helper\n",
            "src/helper.py": "x = 1\n",
        }
    )
    assert ("src/app.py", "src/helper.py") in graph.edges


def test_dotted_import_resolves_by_suffix():
    graph = build(
        {
            "src/app.py": "from pkg.helper import thing\n",
            "src/pkg/helper.py": "thing = 1\n",
        }
    )
    assert ("src/app.py", "src/pkg/helper.py") in graph.edges


def test_js_relative_import_resolves_through_index():
    graph = build(
        {
            "web/app.ts": "import x from './widgets'\n",
            "web/widgets/index.ts": "export const x = 1\n",
        }
    )
    assert ("web/app.ts", "web/widgets/index.ts") in graph.edges


def test_package_import_resolves_through_init():
    graph = build(
        {
            "src/app.py": "from pkg import thing\n",
            "src/pkg/__init__.py": "thing = 1\n",
        }
    )
    assert ("src/app.py", "src/pkg/__init__.py") in graph.edges


def test_ambiguous_suffix_yields_no_edge():
    graph = build(
        {
            "src/app.py": "from pkg.helper import thing\n",
            "a/pkg/helper.py": "thing = 1\n",
            "b/pkg/helper.py": "thing = 1\n",
        }
    )
    assert graph.edges == ()
    assert [u.reason for u in graph.unresolved] == ["ambiguous_suffix"]


def test_external_package_is_not_recorded_as_failure():
    graph = build({"src/app.py": "import requests\nimport os\n"})
    assert graph.unresolved == ()
    assert graph.unresolved_relative_rate.state is CollectionState.NOT_COLLECTED


def test_unresolved_relative_import_is_extractor_failure():
    graph = build(
        {
            "src/app.py": "from . import missing\n",
            "src/other.py": "from . import app\n",
        }
    )
    reasons = {u.reason for u in graph.unresolved}
    assert reasons == {"no_matching_path"}
    assert graph.unresolved_relative_rate.state is CollectionState.MEASURED
    assert graph.unresolved_relative_rate.value == 0.5


def test_parsed_and_unparsed_are_split_by_extension():
    graph = build({"a.py": "", "notes.md": "", "b.go": ""})
    assert graph.parsed == ("a.py", "b.go")
    assert graph.unparsed == ("notes.md",)


def test_build_is_byte_identical_across_input_orderings():
    import random

    tree = {
        "src/app.py": "from . import helper\nimport requests\n",
        "src/helper.py": "x = 1\n",
        "web/a.ts": "import b from './b'\n",
        "web/b.ts": "export const b = 1\n",
    }
    reference = build(tree).model_dump_json()
    for seed in range(3):
        items = list(tree.items())
        random.Random(seed).shuffle(items)
        assert build(dict(items)).model_dump_json() == reference
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_refgraph_resolve.py -v`
Expected: FAIL — `ImportError: cannot import name 'build'`

- [ ] **Step 3: Append the resolver and `build()`**

Add to the imports at the top of `refgraph.py`:

```python
from collections.abc import Mapping

from ...measurement import Measurement
from ..scan.sources import SOURCE_EXTENSIONS
from .models import ReferenceGraph, UnresolvedEdge
```

Then append:

```python
# A directory is referenced through one of these when it is imported by name.
_INDEX_NAMES: tuple[str, ...] = ("index", "__init__", "mod", "main")

# Segment separators across the dotted/namespaced forms: a.b.c, A\B,
# crate::a::b, example.com/pkg/svc.
_SEGMENTS = re.compile(r"[.\\/]+|::")

# Leading segments that name the current crate/package rather than a directory.
_ROOT_WORDS: frozenset[str] = frozenset({"crate", "self", "super"})


def _candidate_paths(fragment: str) -> tuple[str, ...]:
    """Repo paths a extension-free fragment could name."""
    if not fragment:
        return ()
    direct = tuple(f"{fragment}{ext}" for ext in SOURCE_EXTENSIONS)
    indexed = tuple(f"{fragment}/{name}{ext}" for name in _INDEX_NAMES for ext in SOURCE_EXTENSIONS)
    return direct + indexed


def _relative_fragment(importer: str, target: str) -> str:
    base = posixpath.dirname(importer)
    if target.startswith("./") or target.startswith("../"):
        return posixpath.normpath(posixpath.join(base, target))
    if target.startswith("."):
        # Python: one dot is "this package", each extra dot walks up one.
        dots = len(target) - len(target.lstrip("."))
        rest = target[dots:].replace(".", "/")
        up = base
        for _ in range(dots - 1):
            up = posixpath.dirname(up)
        return posixpath.normpath(posixpath.join(up, rest)) if rest else up
    # rust `mod x;` and ruby require_relative: sibling of the importer.
    return posixpath.normpath(posixpath.join(base, target))


def _dotted_fragment(target: str) -> str:
    parts = [p for p in _SEGMENTS.split(target) if p]
    while parts and parts[0] in _ROOT_WORDS:
        parts = parts[1:]
    return "/".join(parts)


def _matches(fragment: str, inventory: Mapping[str, str], *, exact: bool) -> list[str]:
    """Paths the fragment names. `exact` for relative imports (the fragment
    is a full repo path); suffix matching for dotted ones."""
    candidates = _candidate_paths(fragment)
    if exact:
        return sorted(c for c in candidates if c in inventory)
    return sorted(
        path
        for path in inventory
        for candidate in candidates
        if path == candidate or path.endswith(f"/{candidate}")
    )


def build(inventory: Mapping[str, str]) -> ReferenceGraph:
    """The reference graph over one tree. Only files whose extension is in
    EXTRACTOR_EXTENSIONS are parsed; the rest are reported unparsed and can
    never be called dead (D7 clause 1)."""
    paths = sorted(inventory)
    parsed = tuple(p for p in paths if extension_of(p) in EXTRACTOR_EXTENSIONS)
    unparsed = tuple(p for p in paths if extension_of(p) not in EXTRACTOR_EXTENSIONS)

    edges: set[tuple[str, str]] = set()
    unresolved: list[UnresolvedEdge] = []
    relative_total = relative_failed = 0

    for path in parsed:
        for form_name, target in extract(path, inventory[path]):
            relative = is_relative(form_name, target)
            if relative:
                relative_total += 1
                fragment = _relative_fragment(path, target)
            else:
                fragment = _dotted_fragment(target)
            found = [m for m in _matches(fragment, inventory, exact=relative) if m != path]
            if len(found) == 1:
                edges.add((path, found[0]))
                continue
            if len(found) > 1:
                reason = "ambiguous_suffix"
            elif relative:
                reason = "no_matching_path"
            else:
                continue  # external package: expected, not a failure
            if relative:
                relative_failed += 1
            unresolved.append(
                UnresolvedEdge(
                    source_path=path,
                    target=target,
                    form=form_name,
                    reason=reason,
                    relative=relative,
                )
            )

    if relative_total:
        rate = Measurement.measured(relative_failed / relative_total)
    else:
        # P-D1: no relative imports is no EVIDENCE of extractor failure, not
        # evidence of failure. The dead guard trips only on MEASURED.
        rate = Measurement.not_collected(
            "no relative imports in the tree to check resolution against"
        )

    return ReferenceGraph(
        edges=tuple(sorted(edges)),
        unresolved=tuple(
            sorted(unresolved, key=lambda u: (u.source_path, u.form, u.target, u.reason))
        ),
        parsed=parsed,
        unparsed=unparsed,
        unresolved_relative_rate=rate,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_refgraph_resolve.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/refgraph.py \
        tests/test_discover_refgraph_resolve.py
git commit -m "feat(discover): edge resolution -- an ambiguous match is never a guessed edge (E-47b D6)"
```

---

### Task 5: `discover/attribution.py` — buckets and the ratio

Spec D3, D4, D5. The dead guard is Task 6; this task classifies everything else
and computes the ratio, treating `dead` as a plain "no member connection" case
so Task 6 has something to tighten.

**Files:**
- Create: `src/sdlc/assessment/discover/attribution.py`
- Test: `tests/test_discover_attribution.py`

**Interfaces:**
- Consumes: Task 2's models; Task 4's `build`.
- Produces:
  - `BUILD_TOOLING_NAMES: frozenset[str]`
  - `attribute(inventory, skipped, members, entry_points, *, floor=DEFAULT_COVERAGE_FLOOR, max_unresolved=DEAD_GUARD_MAX_UNRESOLVED) -> AttributionReport`
    where `inventory: Mapping[str, str]`, `skipped: Sequence[str]`,
    `members: Mapping[str, Sequence[str]]` (bc_id → member paths),
    `entry_points: Sequence[str]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_attribution.py
"""E-47b D3/D4/D5: the denominator, the numerator, and bucket precedence."""

from __future__ import annotations

import random

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket
from sdlc.measurement import CollectionState

MEMBERS = {"BC-001": ["src/payments/api.py"]}


def _bucket(report, path):
    return next(f.bucket for f in report.files if f.path == path)


def test_a_member_file_is_a_member():
    report = attribute({"src/payments/api.py": "x = 1\n"}, [], MEMBERS, [])
    assert _bucket(report, "src/payments/api.py") is FileBucket.MEMBER
    assert report.files[0].capabilities == ("BC-001",)


def test_non_source_extensions_are_outside_the_denominator():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "README.md": "# hi\n", "Dockerfile": "FROM python\n"},
        [],
        MEMBERS,
        [],
    )
    assert [f.path for f in report.files] == ["src/payments/api.py"]
    assert report.coverage.value == 1.0


def test_build_tooling_in_the_denominator_is_infrastructure():
    report = attribute(
        {
            "src/payments/api.py": "x = 1\n",
            "setup.py": "setup()\n",
            "webpack.config.js": "module.exports = {}\n",
        },
        [],
        MEMBERS,
        [],
    )
    assert _bucket(report, "setup.py") is FileBucket.INFRASTRUCTURE
    assert _bucket(report, "webpack.config.js") is FileBucket.INFRASTRUCTURE
    assert report.coverage.value == 1.0  # D4: all accounted for


def test_member_beats_infrastructure():
    """Precedence rule 1 beats rule 2 -- a capability that claims setup.py
    owns it."""
    report = attribute({"setup.py": "setup()\n"}, [], {"BC-001": ["setup.py"]}, [])
    assert _bucket(report, "setup.py") is FileBucket.MEMBER


def test_a_file_a_member_imports_is_attached():
    report = attribute(
        {"src/payments/api.py": "from . import helper\n", "src/payments/helper.py": "x = 1\n"},
        [],
        MEMBERS,
        [],
    )
    attached = next(f for f in report.files if f.path == "src/payments/helper.py")
    assert attached.bucket is FileBucket.ATTACHED
    assert attached.capabilities == ("BC-001",)


def test_a_test_importing_a_member_is_attached():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "tests/test_api.py": "from src.payments.api import x\n"},
        [],
        MEMBERS,
        [],
    )
    assert _bucket(report, "tests/test_api.py") is FileBucket.ATTACHED


def test_infrastructure_beats_attached():
    report = attribute(
        {
            "src/payments/api.py": "from . import helper\n",
            "src/payments/helper.py": "x = 1\n",
            "setup.py": "from src.payments import api\n",
        },
        [],
        MEMBERS,
        [],
    )
    assert _bucket(report, "setup.py") is FileBucket.INFRASTRUCTURE


def test_a_file_referenced_only_by_a_non_member_is_unclassified():
    report = attribute(
        {
            "src/payments/api.py": "x = 1\n",
            "src/loose/a.py": "from src.loose import b\n",
            "src/loose/b.py": "y = 1\n",
        },
        [],
        MEMBERS,
        [],
    )
    assert _bucket(report, "src/loose/b.py") is FileBucket.UNCLASSIFIED


def test_a_skipped_blob_is_unclassified_and_stays_in_the_denominator():
    report = attribute({"src/payments/api.py": "x = 1\n"}, ["src/broken.py"], MEMBERS, [])
    assert _bucket(report, "src/broken.py") is FileBucket.UNCLASSIFIED
    assert report.skipped == ("src/broken.py",)
    assert report.coverage.value == 0.5


def test_the_ratio_counts_accounted_for_over_the_whole_denominator():
    report = attribute(
        {
            "src/payments/api.py": "x = 1\n",  # member
            "setup.py": "setup()\n",  # infrastructure
            "src/orphan_a.py": "x = 1\n",  # dead
            "src/orphan_b.py": "x = 1\n",
        },  # dead
        [],
        MEMBERS,
        [],
    )
    assert report.coverage.value == 0.5
    assert report.counts[FileBucket.MEMBER] == 1
    assert report.counts[FileBucket.INFRASTRUCTURE] == 1
    assert report.counts[FileBucket.DEAD] == 2
    assert report.meets_floor is False


def test_an_all_infrastructure_tree_is_fully_accounted_for():
    report = attribute(
        {"setup.py": "setup()\n", "noxfile.py": "x = 1\n"}, [], {"BC-001": ["setup.py"]}, []
    )
    assert report.coverage.value == 1.0
    assert report.meets_floor is True


def test_attribution_is_byte_identical_across_input_orderings():
    """P-D2: NFR-10's standard, asserted where the module lives."""
    tree = {
        "src/payments/api.py": "from . import helper\n",
        "src/payments/helper.py": "x = 1\n",
        "setup.py": "setup()\n",
        "src/orphan.py": "x = 1\n",
        "tests/test_api.py": "from src.payments.api import x\n",
    }
    reference = attribute(tree, [], MEMBERS, []).model_dump_json()
    for seed in range(3):
        items = list(tree.items())
        random.Random(seed).shuffle(items)
        assert attribute(dict(items), [], MEMBERS, []).model_dump_json() == reference
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_attribution.py -v`
Expected: FAIL — `ModuleNotFoundError: ...discover.attribution`

- [ ] **Step 3: Write the classifier**

```python
# src/sdlc/assessment/discover/attribution.py
"""FR-913 (E-47b): file->capability coverage and orphan classification.

The denominator is STRICT (D3): every source-extension blob at the pinned
commit, tests and build tooling included, nothing filtered out. The numerator
is ACCOUNTED-FOR (D4): a file counts for coverage when the assessment can say
what it is, and against it only when the assessment cannot. Together the floor
means "the tree is explained", not "the tree is capability-owned".

Pure: every input is a parameter. No disk, no subprocess, no repository code
executed (NFR-9).
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence

from ...measurement import Measurement
from ..scan.configpaths import is_config_path
from ..scan.sources import SOURCE_EXTENSIONS
from . import refgraph
from .models import (
    ACCOUNTED_FOR,
    DEAD_GUARD_MAX_UNRESOLVED,
    DEFAULT_COVERAGE_FLOOR,
    AttributionReport,
    FileAttribution,
    FileBucket,
    ReferenceGraph,
)

# Source-language build and tooling config. `is_config_path` alone would leave
# the infrastructure bucket nearly empty: it matches Dockerfile, compose and
# .env, none of which are in D3's source-extension denominator.
#
# Deliberately NOT promoted to a scan/ rule module: it has exactly one
# consumer, and sources.py's rationale is that a table moves out when a SECOND
# one appears.
BUILD_TOOLING_NAMES: frozenset[str] = frozenset(
    {
        "setup.py",
        "conftest.py",
        "manage.py",
        "noxfile.py",
        "tasks.py",
        "webpack.config.js",
        "vite.config.ts",
        "rollup.config.js",
        "jest.config.js",
        "karma.conf.js",
        "next.config.js",
        "babel.config.js",
        "tailwind.config.js",
        "gulpfile.js",
        "build.rs",
    }
)

_SOURCE_EXTENSIONS = frozenset(SOURCE_EXTENSIONS)


def _in_denominator(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in _SOURCE_EXTENSIONS


def _empty_report(
    reason: str, graph: ReferenceGraph, floor: float, skipped: Sequence[str]
) -> AttributionReport:
    """FR-915: attribution did not happen, so there is no ratio -- not a
    zero, and certainly not a one."""
    return AttributionReport(
        files=(),
        counts={b: 0 for b in FileBucket},
        coverage=Measurement.not_collected(reason),
        floor=floor,
        meets_floor=False,
        dead_guard_tripped=False,
        graph=graph,
        skipped=tuple(sorted(skipped)),
    )


def attribute(
    inventory: Mapping[str, str],
    skipped: Sequence[str],
    members: Mapping[str, Sequence[str]],
    entry_points: Sequence[str],
    *,
    floor: float = DEFAULT_COVERAGE_FLOOR,
    max_unresolved: float = DEAD_GUARD_MAX_UNRESOLVED,
) -> AttributionReport:
    """Classify every file in the denominator and compute the coverage ratio.

    `inventory` is path -> blob text at the pinned commit; `skipped` names
    blobs that could not be read; `members` maps bc_id -> member paths;
    `entry_points` names paths hosting an S3 entry point.
    """
    readable = {p: t for p, t in inventory.items() if _in_denominator(p)}
    graph = refgraph.build(readable)

    # A file that could not be read is still a file the model failed to
    # attribute: dropping it would let an unreadable tree score 1.0.
    skipped_in = sorted({p for p in skipped if _in_denominator(p)})
    denominator = sorted(set(readable) | set(skipped_in))

    if not denominator:
        return _empty_report("no source files in the tree", graph, floor, skipped_in)
    if not members:
        return _empty_report("no capabilities to attribute against", graph, floor, skipped_in)

    member_of: dict[str, list[str]] = {}
    for bc_id, paths in members.items():
        for path in paths:
            member_of.setdefault(path, []).append(bc_id)

    neighbours: dict[str, set[str]] = {}
    for src, dst in graph.edges:
        neighbours.setdefault(src, set()).add(dst)
        neighbours.setdefault(dst, set()).add(src)

    context = _Context(
        member_of=member_of,
        neighbours=neighbours,
        skipped=set(skipped_in),
        parsed=set(graph.parsed),
        entry_points=set(entry_points),
        guard_tripped=False,
    )

    files = tuple(_classify(path, context) for path in denominator)
    counts = {b: sum(1 for f in files if f.bucket is b) for b in FileBucket}
    accounted = sum(counts[b] for b in ACCOUNTED_FOR)
    coverage = Measurement.measured(accounted / len(denominator))

    return AttributionReport(
        files=files,
        counts=counts,
        coverage=coverage,
        floor=floor,
        meets_floor=coverage.value >= floor,
        dead_guard_tripped=False,
        graph=graph,
        skipped=tuple(skipped_in),
    )
```

Add the `_Context` holder and `_classify` above `attribute`:

```python
class _Context(NamedTuple):
    member_of: dict[str, list[str]]
    neighbours: dict[str, set[str]]
    skipped: set[str]
    parsed: set[str]
    entry_points: set[str]
    guard_tripped: bool


def _classify(path: str, ctx: _Context) -> FileAttribution:
    """BUCKET_PRECEDENCE, in order. The first rule that fires wins."""
    if path in ctx.member_of:
        return FileAttribution(
            path=path,
            bucket=FileBucket.MEMBER,
            rule="capability_member",
            detail="claimed by a capability's member set",
            capabilities=tuple(sorted(set(ctx.member_of[path]))),
        )
    if path in ctx.skipped:
        return FileAttribution(
            path=path,
            bucket=FileBucket.UNCLASSIFIED,
            rule="blob_unreadable",
            detail="the blob could not be read at the pinned commit",
        )
    if is_config_path(path):
        return FileAttribution(
            path=path,
            bucket=FileBucket.INFRASTRUCTURE,
            rule="config_path",
            detail="matches a configuration/infrastructure path rule",
        )
    if posixpath.basename(path) in BUILD_TOOLING_NAMES:
        return FileAttribution(
            path=path,
            bucket=FileBucket.INFRASTRUCTURE,
            rule="build_tooling",
            detail="a build or tooling configuration file",
        )
    attached = sorted(
        {
            bc
            for neighbour in ctx.neighbours.get(path, ())
            for bc in ctx.member_of.get(neighbour, ())
        }
    )
    if attached:
        return FileAttribution(
            path=path,
            bucket=FileBucket.ATTACHED,
            rule="graph_connected_to_member",
            detail="shares an import edge with a capability member",
            capabilities=tuple(attached),
        )
    return FileAttribution(
        path=path,
        bucket=FileBucket.DEAD,
        rule="no_static_inbound_reference",
        detail="no import edge connects this file to a capability",
    )
```

Add `NamedTuple` to the `typing` import.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_discover_attribution.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/attribution.py \
        tests/test_discover_attribution.py
git commit -m "feat(discover): bucket precedence and the accounted-for ratio (E-47b D3-D5)"
```

---

### Task 6: The dead guard

Spec D7. The load-bearing task: `dead` is the one orphan verdict a customer acts
on by deleting code. Task 5 calls a file dead whenever nothing connects it to a
member; this task adds the four clauses that must ALL hold first.

**Files:**
- Modify: `src/sdlc/assessment/discover/attribution.py` (`_classify`, `attribute`)
- Test: `tests/test_discover_dead_guard.py`

**Interfaces:**
- Consumes: Task 5's `_classify`, `_Context`, `attribute`.
- Produces: no new public names. `AttributionReport.dead_guard_tripped` becomes
  meaningful.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_dead_guard.py
"""D7: `dead` is the claim a customer acts on by deleting code, so it needs
four clauses, not one. One test per clause."""

from __future__ import annotations

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket

MEMBERS = {"BC-001": ["src/payments/api.py"]}


def _bucket(report, path):
    return next(f.bucket for f in report.files if f.path == path)


def _rule(report, path):
    return next(f.rule for f in report.files if f.path == path)


def test_clause_1_an_unparsed_language_is_never_dead():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "legacy/report.scala": "object R\n"}, [], MEMBERS, []
    )
    # .scala IS in the extractor table; use a source extension that is not.
    assert _bucket(report, "legacy/report.scala") is not FileBucket.UNCLASSIFIED


def test_clause_1_a_source_extension_outside_the_extractor_table():
    """.swift is parsed; .vue is parsed; pick one SOURCE_EXTENSIONS entry the
    form table does not cover."""
    from sdlc.assessment.discover.refgraph import EXTRACTOR_EXTENSIONS
    from sdlc.assessment.scan.sources import SOURCE_EXTENSIONS

    uncovered = sorted(set(SOURCE_EXTENSIONS) - EXTRACTOR_EXTENSIONS)
    assert uncovered, "if every source extension is parsed, drop this test"
    path = f"src/thing{uncovered[0]}"
    report = attribute({"src/payments/api.py": "x = 1\n", path: "code\n"}, [], MEMBERS, [])
    assert _bucket(report, path) is FileBucket.UNCLASSIFIED
    assert _rule(report, path) == "language_not_parsed"


def test_clause_3_an_entry_point_is_never_dead():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "src/jobs/nightly.py": "def run(): ...\n"},
        [],
        MEMBERS,
        ["src/jobs/nightly.py"],
    )
    assert _bucket(report, "src/jobs/nightly.py") is FileBucket.UNCLASSIFIED
    assert _rule(report, "src/jobs/nightly.py") == "framework_discovered_entry_point"


def test_clause_3_a_test_path_is_never_dead():
    """conftest.py is collected by convention and imported by nothing. Without
    this clause the first repository scanned is told its test suite is dead."""
    report = attribute(
        {
            "src/payments/api.py": "x = 1\n",
            "tests/conftest.py": "import pytest\n",
            "tests/test_lonely.py": "def test_x(): ...\n",
        },
        [],
        MEMBERS,
        [],
    )
    for path in ("tests/conftest.py", "tests/test_lonely.py"):
        assert _bucket(report, path) is FileBucket.UNCLASSIFIED
        assert _rule(report, path) == "framework_discovered_test"


def test_clause_4_broad_extractor_failure_collapses_the_dead_bucket():
    """Every relative import fails to resolve, so the graph cannot be trusted
    and no file may be called dead."""
    tree = {
        "src/payments/api.py": "from . import gone_a\n",
        "src/orphan_one.py": "from . import gone_b\n",
        "src/orphan_two.py": "from . import gone_c\n",
    }
    report = attribute(tree, [], MEMBERS, [])
    assert report.dead_guard_tripped is True
    assert report.counts[FileBucket.DEAD] == 0
    assert _rule(report, "src/orphan_one.py") == "dead_guard_tripped"


def test_all_four_clauses_passing_yields_dead():
    report = attribute(
        {"src/payments/api.py": "x = 1\n", "src/orphan.py": "x = 1\n"}, [], MEMBERS, []
    )
    assert report.dead_guard_tripped is False
    assert _bucket(report, "src/orphan.py") is FileBucket.DEAD
    assert _rule(report, "src/orphan.py") == "no_static_inbound_reference"


def test_p_d1_a_tree_with_no_relative_imports_does_not_trip_the_guard():
    """An all-dotted tree gives no evidence of extractor failure. Treating
    that as failure would disable dead detection for whole language families."""
    report = attribute(
        {"src/payments/api.py": "import os\n", "src/orphan.py": "import sys\n"}, [], MEMBERS, []
    )
    assert report.dead_guard_tripped is False
    assert _bucket(report, "src/orphan.py") is FileBucket.DEAD
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_discover_dead_guard.py -v`
Expected: FAIL — several tests report `FileBucket.DEAD` where
`FileBucket.UNCLASSIFIED` is expected, and `dead_guard_tripped` is always False.

- [ ] **Step 3: Add the guard to `_classify`**

Add the import at the top of `attribution.py`:

```python
from ..scan.testpaths import is_test_path
```

Replace the final `return` of `_classify` (the unconditional DEAD case) with:

```python
# D7: `dead` is the claim a customer acts on by deleting code. All four
# clauses must hold; any failure sends the file to unclassified, never to
# a weaker positive.
if path not in ctx.parsed:
    return FileAttribution(
        path=path,
        bucket=FileBucket.UNCLASSIFIED,
        rule="language_not_parsed",
        detail="no import extractor covers this file's language",
    )
if path in ctx.entry_points:
    return FileAttribution(
        path=path,
        bucket=FileBucket.UNCLASSIFIED,
        rule="framework_discovered_entry_point",
        detail="hosts an entry point, so it is reached by dispatch",
    )
if is_test_path(path):
    return FileAttribution(
        path=path,
        bucket=FileBucket.UNCLASSIFIED,
        rule="framework_discovered_test",
        detail="collected by a test runner by convention, not by import",
    )
if ctx.neighbours.get(path):
    return FileAttribution(
        path=path,
        bucket=FileBucket.UNCLASSIFIED,
        rule="referenced_by_unattributed_file",
        detail="referenced, but by nothing that reaches a capability",
    )
if ctx.guard_tripped:
    return FileAttribution(
        path=path,
        bucket=FileBucket.UNCLASSIFIED,
        rule="dead_guard_tripped",
        detail="too many relative imports failed to resolve for an "
        "absence of references to be evidence",
    )
return FileAttribution(
    path=path,
    bucket=FileBucket.DEAD,
    rule="no_static_inbound_reference",
    detail="nothing in this tree statically references this file",
)
```

In `attribute`, compute the guard before classifying and thread it through:

```python
rate = graph.unresolved_relative_rate
guard_tripped = (
    rate.state is CollectionState.MEASURED
    and rate.value is not None
    and rate.value > max_unresolved
)

context = _Context(
    member_of=member_of,
    neighbours=neighbours,
    skipped=set(skipped_in),
    parsed=set(graph.parsed),
    entry_points=set(entry_points),
    guard_tripped=guard_tripped,
)
```

and change the final construction's `dead_guard_tripped=False` to
`dead_guard_tripped=guard_tripped`. Add `CollectionState` to the
`...measurement` import.

- [ ] **Step 4: Run both attribution suites**

Run: `pytest tests/test_discover_dead_guard.py tests/test_discover_attribution.py -v`
Expected: PASS. If `test_a_file_referenced_only_by_a_non_member_is_unclassified`
from Task 5 now reports rule `referenced_by_unattributed_file`, that is correct
— the bucket it asserts is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/discover/attribution.py \
        tests/test_discover_dead_guard.py
git commit -m "feat(discover): the dead guard -- four clauses before a file is called dead (E-47b D7)"
```

---

### Task 7: FR-915 degradation

Spec "Failure modes". Each case asserts `not_collected` *with a reason*, and
asserts explicitly that it is not `measured(0.0)` or `measured(1.0)` — the
conflation this whole contract family exists to prevent.

**Files:**
- Test: `tests/test_discover_degradation.py`
- Modify: `src/sdlc/assessment/discover/attribution.py` only if a case fails.

**Interfaces:**
- Consumes: Task 5/6's `attribute`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_discover_degradation.py
"""FR-915 at the coverage ratio: a value that was never measured must not be
representable as a measured one."""

from __future__ import annotations

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket
from sdlc.measurement import CollectionState

MEMBERS = {"BC-001": ["src/payments/api.py"]}


def test_an_empty_capability_set_is_not_collected():
    report = attribute({"src/a.py": "x = 1\n"}, [], {}, [])
    assert report.coverage.state is CollectionState.NOT_COLLECTED
    assert "no capabilities" in report.coverage.reason
    assert report.coverage.value is None
    assert report.meets_floor is False


def test_an_empty_denominator_is_not_collected_not_perfect():
    """A division by zero must never read as perfect coverage."""
    report = attribute({"README.md": "# hi\n"}, [], MEMBERS, [])
    assert report.coverage.state is CollectionState.NOT_COLLECTED
    assert "no source files" in report.coverage.reason
    assert report.coverage.value is None
    assert report.meets_floor is False


def test_a_not_collected_report_still_carries_every_bucket_count():
    report = attribute({}, [], MEMBERS, [])
    assert set(report.counts) == set(FileBucket)
    assert sum(report.counts.values()) == 0


def test_skipped_blobs_are_named_in_the_report():
    report = attribute(
        {"src/payments/api.py": "x = 1\n"}, ["src/broken.py", "notes.md"], MEMBERS, []
    )
    assert report.skipped == ("src/broken.py",)  # notes.md is not source
    assert report.counts[FileBucket.UNCLASSIFIED] == 1


def test_an_unreadable_tree_cannot_score_one():
    """Every source file skipped: the model attributed nothing, and dropping
    skipped files from the denominator would have scored 1.0."""
    report = attribute({}, ["src/a.py", "src/b.py"], MEMBERS, [])
    assert report.coverage.state is CollectionState.MEASURED
    assert report.coverage.value == 0.0
    assert report.meets_floor is False
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `pytest tests/test_discover_degradation.py -v`
Expected: PASS if Tasks 5-6 were implemented exactly; any FAIL is a real defect
in `attribute`'s early-return ordering — fix `attribution.py`, do not weaken the
test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_discover_degradation.py src/sdlc/assessment/discover/
git commit -m "test(discover): FR-915 degradation -- a gap never reads as a zero or a one (E-47b)"
```

---

### Task 8: Mechanical mutation corpus

Spec testing item 4. E-47a's primary investment, same technique: generate ground
truth by applying *known* mutations rather than hand-labelling. The third case
deliberately pins a known false positive so a later increment that adds
dynamic-form detection gets a failing test telling it what it fixed.

**Files:**
- Test: `tests/test_discover_mutation_corpus.py`

**Interfaces:**
- Consumes: Task 5/6's `attribute`.
- Produces: nothing new.

- [ ] **Step 1: Write the test**

```python
# tests/test_discover_mutation_corpus.py
"""E-47b: known mutations against a synthetic tree, each with a labelled
expected outcome. Generates ground truth instead of hand-labelling it, which
is what E-47a's refactor corpus does for identity."""

from __future__ import annotations

from sdlc.assessment.discover.attribution import attribute
from sdlc.assessment.discover.models import FileBucket

BASE = {
    "src/payments/api.py": "from . import service\nimport requests\n",
    "src/payments/service.py": "from . import repo\n",
    "src/payments/repo.py": "x = 1\n",
    "src/shared/util.py": "y = 1\n",
    "setup.py": "setup()\n",
    "tests/test_api.py": "from src.payments.api import x\n",
}
MEMBERS = {"BC-001": ["src/payments/api.py", "src/payments/service.py"]}


def _bucket(report, path):
    return next(f.bucket for f in report.files if f.path == path)


def test_baseline_attributes_the_import_chain():
    report = attribute(BASE, [], MEMBERS, [])
    assert _bucket(report, "src/payments/repo.py") is FileBucket.ATTACHED
    assert _bucket(report, "setup.py") is FileBucket.INFRASTRUCTURE
    assert _bucket(report, "tests/test_api.py") is FileBucket.ATTACHED
    # src/shared/util.py is imported by nothing at all.
    assert _bucket(report, "src/shared/util.py") is FileBucket.DEAD


def test_mutation_deleting_the_only_import_makes_a_file_dead():
    tree = dict(BASE)
    tree["src/payments/service.py"] = "pass\n"  # no longer imports repo
    report = attribute(tree, [], MEMBERS, [])
    assert _bucket(report, "src/payments/repo.py") is FileBucket.DEAD


def test_mutation_moving_a_file_leaves_coverage_unchanged():
    before = attribute(BASE, [], MEMBERS, []).coverage.value
    tree = dict(BASE)
    tree["src/payments/storage.py"] = tree.pop("src/payments/repo.py")
    tree["src/payments/service.py"] = "from . import storage\n"
    after = attribute(tree, [], MEMBERS, []).coverage.value
    assert before == after


def test_known_false_positive_a_dynamic_reference_reads_as_dead():
    """D6 accepts that dynamic references are invisible to a regex table.
    Pinned as a test, not a docstring caveat: an increment that adds dynamic-
    form detection will fail here, which is exactly the notification it wants.
    """
    tree = dict(BASE)
    tree["src/payments/service.py"] = (
        "import importlib\nrepo = importlib.import_module('src.payments.repo')\n"
    )
    report = attribute(tree, [], MEMBERS, [])
    assert _bucket(report, "src/payments/repo.py") is FileBucket.DEAD


def test_mutation_claiming_an_orphan_raises_coverage():
    before = attribute(BASE, [], MEMBERS, []).coverage.value
    wider = dict(MEMBERS)
    wider["BC-002"] = ["src/shared/util.py"]
    after = attribute(BASE, [], wider, []).coverage.value
    assert after > before
    assert after == 1.0
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_discover_mutation_corpus.py -v`
Expected: PASS (5 tests). A failure here means `attribute` disagrees with the
spec's worked semantics — fix the implementation.

- [ ] **Step 3: Run the whole suite**

Run: `pytest -q`
Expected: PASS, with no regression in `tests/test_scan_*` or
`tests/test_assessment_*`. Task 1 touched SS3's memo key input, so
`test_scan_rules_sha.py` and `test_scan_registry.py` are the ones to watch.

- [ ] **Step 4: Commit**

```bash
git add tests/test_discover_mutation_corpus.py
git commit -m "test(discover): mutation corpus, incl. the pinned dynamic-reference false positive (E-47b)"
```

---

### Task 9: Roadmap deltas

The spec's "Roadmap deltas" table. `ROADMAP.md` is a living tracker whose
accuracy is load-bearing — an item marked done that is not wired is the kind of
drift §0 exists to catch, so the wording must say what actually landed.

**Files:**
- Modify: `ROADMAP.md` (§11 E-47b, §2 FR-913, §1 stage 2, §3 NFR-9/NFR-10, line 6)

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Update E-47b in §11**

Change the `- [ ] **E-47b — coverage floor + orphans**` bullet to `[x]` and
append, preserving the file's existing voice:

> **Landed 2026-08-13.** Pure and unwired by design (D1): `_discover` still
> reports `not_collected` naming E-48, which calls `attribute()` when it lands.
> The two decisions worth carrying: the denominator is **strict** (every
> `SOURCE_EXTENSIONS` blob, tests and build tooling included) while the
> numerator is **accounted-for** (members + infrastructure + attached), so the
> floor means *the tree is explained* rather than *the tree is
> capability-owned*; and `dead` requires **four** clauses (parsed language, zero
> inbound edges, not framework-discovered, tree-wide resolution healthy),
> because it is the one orphan verdict a customer acts on by deleting code.
> D6 buys breadth with a shallow regex table and pays for it in dynamic
> references — `test_known_false_positive_a_dynamic_reference_reads_as_dead`
> pins that cost as a test rather than a caveat. Spec
> `docs/superpowers/specs/2026-08-13-e47b-coverage-floor-and-orphans-design.md`,
> plan `docs/superpowers/plans/2026-08-13-e47b-coverage-floor-and-orphans.md`.

- [ ] **Step 2: Update the FR and stage rows**

- **FR-913** (§2): note the coverage-floor/orphan clause is satisfied; the item
  stays `[ ] ⚠️` because E-47c (L2 + entity ownership) is open.
- **§1 stage 2 · context**: add "**E-47b (2026-08-13):** attribution and orphan
  classification land; FR-102 still needs E-47c."
- **NFR-9** (§3): "**E-47b (2026-08-13)** adds no execution of repository code:
  every input is a parameter and the graph is built from blobs already read."
- **NFR-10** (§3): note two more pure modules under the order-independence
  standard.
- Line 6 `Last verified`: prepend
  `2026-08-13 (E-47b against src/sdlc/assessment/discover/ + unit suite green);`.

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs: record E-47b -- coverage floor and orphan classification landed"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: D1/D2 → Tasks 2-5
(placement, nothing wired); D3/D4/D5 → Task 5; D6 → Tasks 3-4; D7 → Task 6;
D8 → satisfied by omission (no `CheckResult` is built anywhere); D9 → Task 2's
naming; D10 → Task 1. Data model → Task 2. Failure modes → Task 7. Testing
items 1-8 → Tasks 3-8 (item 8's `rules_sha` assertion is Task 1). Roadmap
deltas → Task 9.

**Type consistency.** `attribute()`'s signature is identical in the spec, Task
5's Interfaces block and its implementation. `FileBucket` members are used by
the same names throughout. `build()` returns `ReferenceGraph` in Tasks 4, 5 and
6. `is_config_path` is imported from `..scan.configpaths` in both Task 1's call
sites and Task 5's classifier.

**Known rough edge, deliberately left to the implementer.** Task 6's
`test_clause_1_a_source_extension_outside_the_extractor_table` computes
`SOURCE_EXTENSIONS - EXTRACTOR_EXTENSIONS` at runtime rather than hardcoding an
extension, and asserts the difference is non-empty. If Task 3's form table ends
up covering all 18 extensions, that assertion fires with a message telling the
implementer to drop the test — which is the correct outcome, not a plan defect.
The neighbouring `test_clause_1_an_unparsed_language_is_never_dead` is a weaker
smoke check and may be deleted if it proves redundant.
