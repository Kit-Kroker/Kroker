# Scan Phase — Plan 2 of 3: S1, S3, S5 and the Naming Rules

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land E-46's capability core — S1 (package structure), S3 (backend entry points), S5 (cross-source merge and confidence) and the `naming.py` tables they share — so `ScanResult.candidates` carries real merged candidates and the scan memo gets its first production caller.

**Architecture:** Three pure signal modules under `src/sdlc/assessment/scan/` computing records from blob text, plus the shared normalizer in `naming.py` that both S3's grouping and S5's merge read. S1 and S3 gain real Temporal activity bodies that wrap the pure functions in `memo.load`/`memo.store` (plan 1 built the memo; nothing has called it yet). S5 is `in_workflow=True`, so its merge runs in `_scan` beside SS2's inheritance, never as an activity.

**Tech Stack:** Python 3.12, Pydantic v2, Temporal (`temporalio`), pytest.

## Global Constraints

- **Purity.** Every module under `assessment/scan/` may import Pydantic, `..measurement`, `..triage.models` and `..toolchain.adapters` **only**. Never `sdlc.models`, `sdlc.activities`, `sdlc.triage.signals.*` or `temporalio`. A dependency there would appear as a reviewable import. This is why S1 re-declares its own source-extension list instead of importing `triage/signals/scaffold.py`'s.
- **FR-915.** A value that was never measured must not be representable as a measured value. Never `Measurement.measured(0.0)` for something that did not run.
- **Determinism (NFR-10).** Iterate `SCAN_ORDER`, never a bare `set` or `dict`. Sort every list before it enters an artifact. The same tree must yield byte-identical output.
- **No repository code executes.** Every signal is a blob read at the pinned commit. The `init` phase's build probe stays the only place the assessed repo runs (NFR-9, D12).
- **Derived, never assigned.** `ScanCandidate.confidence` comes from `confidence_from(...)`; a signal's wave comes from `consumes`; `Assessment.terminal_status` comes from its phases.
- **Activities never raise.** A signal that fails returns a `not_collected` row for itself. `run_or_degrade` covers timeouts and lost workers; the activity's own `try/except` covers everything inside it.
- **Spec:** `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md`. Decision ids (D1–D14) refer to its §2. Two decisions this plan adds are labelled **P2-D1** and **P2-D2** below.
- **Prior plan:** `docs/superpowers/plans/2026-08-12-scan-phase-signals-plan-1.md` — contracts, registry, seam, inherited halves.
- **Test commands:** `pytest tests/<file> -v` for unit; `pytest -m temporal tests/<file> -v` for workflow e2e. Default `pytest` runs unit only.

### Plan-level decisions

**P2-D1 — S3 fails closed on an unfingerprinted framework.** Plan 1's
`ScanResult._unmeasured_carries_no_payload` forbids a non-`MEASURED` row from
carrying records, so "extracted part of the backend" is not representable in the
contract. Given that, D5's rule resolves one way only: if S3 detects a backend
framework it has no fingerprint for, it reports `not_collected` naming that
framework and emits **zero** candidates, even when another framework did match.
This is D5's own reasoning applied literally — S3's members become
`CapabilityFingerprint`'s Contract tier at weight 0.55, and a silently-partial
Contract tier makes E-47a's matcher renormalize onto weaker tiers and risk
handing a stored `BC-NNN` to an unrelated capability. A repo with no recognized
framework at all is also `not_collected`: "this repo has no backend" and "this
backend uses something we cannot parse" are not distinguishable without a
fingerprint, and only one of them is safe to assert.

**P2-D2 — the name tables live in `naming.py`, so S1 declares it too.** S1's
generic/layer classification and S3's stem fallback need the same "is this a
technical layer word?" fact. Two copies would agree only by coincidence (the
reason D9 sited normalization once already), so `GENERIC_NAMES` and
`LAYER_NAMES` join `LAYER_SUFFIXES` in `naming.py` — and S1's registry entry
therefore gains `rule_modules=(_NAMING,)`. Without that edit, editing a layer
word would change S1's output while S1's memo key stood still, which is exactly
the stale-cache class D10 exists to prevent.

---

## File Structure

| File | Responsibility |
|---|---|
| `scan/naming.py` **(modify)** | Layer suffixes, singularization, `normalize`, and the generic/layer name tables. Shared by S1, S3, S5. |
| `scan/signals/packages.py` **(modify)** | S1: directory groupings at depth 1–3, classified by name. Pure. |
| `scan/signals/entrypoints.py` **(modify)** | S3: framework detection + route/job/CLI extraction, grouped by business operation. Pure. |
| `scan/merge.py` **(modify)** | S5: group by normalized name, derive confidence, flag non-collapsed overlaps. Pure. |
| `scan/summary.py` **(create)** | Operator-facing render of a `ScanResult` (spec §8). Pure. |
| `scan/registry.py` **(modify)** | S1 gains `rule_modules=(_NAMING,)` (P2-D2). |
| `assessment/activities.py` **(modify)** | Real `scan_packages` / `scan_entrypoints` bodies with memo wrapping; `OWED_BY` loses S1/S3; `BUILT` guards the two against drift. |
| `workflows/assessment.py` **(modify)** | `_scan` runs S5's merge and puts candidates on `ScanResult`. |
| `cli.py` **(modify)** | `assess show` prints the summary; `--json` keeps the raw dump. |

---

### Task 1: `naming.py` — the shared rule tables

**Files:**
- Modify: `src/sdlc/assessment/scan/naming.py`
- Modify: `src/sdlc/assessment/scan/registry.py:90-92` (S1 gains `rule_modules`)
- Test: `tests/test_scan_naming.py` (create)
- Test: `tests/test_scan_rules_sha.py` (add one test)

**Interfaces:**
- Produces: `LAYER_SUFFIXES: tuple[str, ...]`, `GENERIC_NAMES: frozenset[str]`, `LAYER_NAMES: frozenset[str]`, `singularize(word: str) -> str`, `head_token(name: str) -> str`, `normalize(name: str) -> str`. Tasks 3 and 4 consume `normalize`; Task 3 also consumes `head_token` and both name sets; Task 2 consumes the two name sets only.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scan_naming.py`:

```python
"""D9: S3's grouping and S5's merge must share one normalizer. Two copies
would agree only by coincidence."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan.naming import (
    GENERIC_NAMES,
    LAYER_NAMES,
    LAYER_SUFFIXES,
    head_token,
    normalize,
    singularize,
)


@pytest.mark.parametrize(
    "word,expected",
    [
        ("payments", "payment"),
        ("categories", "category"),
        ("classes", "class"),
        ("boxes", "box"),
        ("batches", "batch"),
        ("dishes", "dish"),
        ("status", "status"),  # "ss" is not a plural marker
        ("address", "address"),
        ("api", "api"),
        ("s", "s"),  # too short to strip
    ],
)
def test_singularize(word, expected):
    assert singularize(word) == expected


@pytest.mark.parametrize(
    "name",
    [
        "PaymentController",
        "PaymentService",
        "PaymentRepository",
        "PaymentHandler",
        "payments",
        "payment_service",
        "Payments",
    ],
)
def test_the_payments_family_normalizes_to_one_token(name):
    """D9's worked example: PaymentController (S3) + payments/ (S1) must
    reach the same key or S5 cannot merge them."""
    assert normalize(name) == "payment"


@pytest.mark.parametrize(
    "name,expected",
    [
        ("PaymentSettlementJob", "Payment"),
        ("PaymentEventConsumer", "Payment"),
        ("PaymentController", "Payment"),
        ("payment_settlement_job", "payment"),
        ("payments", "payments"),
        ("catcafe", "catcafe"),
        ("HTTPServer", "HTTP"),  # an acronym run is one token
    ],
)
def test_head_token(name, expected):
    assert head_token(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "PaymentController",
        "PaymentSettlementJob",
        "PaymentEventConsumer",
    ],
)
def test_the_three_channel_names_reach_one_merge_key(name):
    """BrownKit's rule verbatim: PaymentController + PaymentSettlementJob +
    PaymentEventConsumer is ONE candidate, not three. Suffix-stripping alone
    does not get there -- 'PaymentSettlementJob' loses only 'Job' and lands
    on 'paymentsettlement' -- so S3 groups on the HEAD token."""
    assert normalize(head_token(name)) == "payment"


def test_the_longest_suffix_wins_not_the_first_declared():
    """Declaration order must not decide behaviour: 'Utils' and 'Util' both
    match, and stripping the shorter one leaves a trailing 's'."""
    assert normalize("StringUtils") == "string"
    assert normalize("StringUtil") == "string"


def test_a_bare_suffix_is_not_stripped_to_nothing():
    """'Service' alone is the whole name; stripping it would yield ''."""
    assert normalize("Service") == "service"


def test_normalize_is_idempotent():
    for name in ("PaymentController", "payments", "OrderService"):
        assert normalize(normalize(name)) == normalize(name)


def test_the_name_tables_are_disjoint():
    """A word classified as both generic and layer would make S1's rule
    depend on check order (P2-D2)."""
    assert not (GENERIC_NAMES & LAYER_NAMES)


def test_every_layer_suffix_is_capitalized():
    """The suffixes are matched case-insensitively, but they are declared in
    the form they appear in source so the table reads as documentation."""
    for suffix in LAYER_SUFFIXES:
        assert suffix[0].isupper(), suffix
```

Add to `tests/test_scan_rules_sha.py`:

```python
def test_the_naming_module_reaches_s1_too(monkeypatch):
    """P2-D2: S1 reads the generic/layer name tables, so it declares
    scan.naming. Without the declaration, editing a layer word would change
    S1's output while its memo key stood still."""
    naming = SCAN_SIGNALS[ScanSignalId.S3].rule_modules[0]
    assert naming in SCAN_SIGNALS[ScanSignalId.S1].rule_modules
    before = rules_sha(ScanSignalId.S1)
    monkeypatch.setattr(
        "sdlc.assessment.scan.rules.module_sha",
        lambda dotted: "edited" if dotted == naming else module_sha(dotted),
    )
    assert rules_sha(ScanSignalId.S1) != before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_scan_naming.py tests/test_scan_rules_sha.py -v`
Expected: FAIL — `ImportError: cannot import name 'GENERIC_NAMES'`, and the new `rules_sha` test fails its `assert naming in ...`.

- [ ] **Step 3: Fill in `naming.py`**

Replace the whole of `src/sdlc/assessment/scan/naming.py`:

```python
"""Name normalization shared by S1's classification, S3's grouping and S5's
merge (D9, P2-D2).

Sited once because all three need the same rules -- S3 groups
PaymentController + PaymentSettlementJob + PaymentEventConsumer into one
candidate, S5 merges that candidate with S1's payments/ package, and S1 asks
of a directory name the same "is this a technical layer word?" question S3
asks of a file stem. Two copies would agree only by coincidence.

VERSION is decorative here: this module is a `rule_modules` entry, so
rules_sha hashes its BYTES (D10). Editing a table below moves S1's, S3's and
S5's memo keys by construction, which is the property test_scan_rules_sha
asserts.

Known limitation, recorded as OQ-12: suffix stripping and singularization
assume English identifiers. A non-English codebase degrades to
LOW-confidence single-source candidates rather than to wrong ones.
"""

from __future__ import annotations

VERSION = 1

# Suffixes that describe a technical layer rather than a capability (D9).
# Declared capitalized because that is how they appear in source; matching is
# case-insensitive and picks the LONGEST match, so this tuple's order carries
# no meaning ("Utils" must beat "Util" whichever is declared first).
LAYER_SUFFIXES: tuple[str, ...] = (
    "Controller",
    "Service",
    "Repository",
    "Handler",
    "Manager",
    "Resource",
    "Router",
    "Route",
    "Consumer",
    "Listener",
    "Subscriber",
    "Publisher",
    "Job",
    "Worker",
    "Task",
    "Scheduler",
    "Client",
    "Gateway",
    "Provider",
    "Factory",
    "Builder",
    "Helper",
    "Helpers",
    "Utils",
    "Util",
    "Impl",
    "Dao",
    "Dto",
    "Mapper",
    "Middleware",
    "ViewSet",
    "View",
    "Serializer",
    "Schema",
    "Model",
    "Entity",
    "Repo",
    "Api",
    "Endpoint",
)

# Directory / module names that name no business capability. LOW contribution
# and `s1_generic_name` (BrownKit's own list, extended with the container
# directories a monorepo adds).
GENERIC_NAMES: frozenset[str] = frozenset(
    {
        "util",
        "utils",
        "common",
        "core",
        "lib",
        "libs",
        "helper",
        "helpers",
        "shared",
        "misc",
        "base",
        "internal",
        "pkg",
        "src",
        "app",
        "apps",
        "packages",
        "modules",
        "code",
        "scripts",
        "tools",
        "vendor",
        "third_party",
    }
)

# Names that describe a technical layer. Also LOW, but a DIFFERENT rule
# (`s1_layer_name`), because E-48's guardrail -- "delivery channels and
# deployment boundaries are not capabilities" -- needs the distinction, not
# just its outcome (SourceCandidate's docstring).
LAYER_NAMES: frozenset[str] = frozenset(
    {
        "controller",
        "controllers",
        "service",
        "services",
        "repository",
        "repositories",
        "model",
        "models",
        "dto",
        "dtos",
        "api",
        "apis",
        "handler",
        "handlers",
        "route",
        "routes",
        "router",
        "routers",
        "view",
        "views",
        "serializer",
        "serializers",
        "middleware",
        "adapter",
        "adapters",
        "interface",
        "interfaces",
        "schema",
        "schemas",
        "entity",
        "entities",
        "config",
        "configs",
        "migration",
        "migrations",
        "test",
        "tests",
        "mapper",
        "mappers",
        "dao",
        "daos",
        "resource",
        "resources",
        # Delivery channels. E-48's guardrail names them explicitly: "delivery
        # channels and deployment boundaries are not capabilities", so a file
        # called cli.py or server.js names the channel, not the operation, and
        # S3 falls back to its parent directory.
        "cli",
        "server",
        "index",
        "main",
        "worker",
        "consumer",
        "job",
        "jobs",
    }
)


def singularize(word: str) -> str:
    """English singularization, deliberately small: the rules that fire on
    real identifiers and nothing more. Over-reaching here would collapse
    unrelated names into one merge key, which is worse than missing a merge
    (D9 rule 2 -- S5 never has to be right, only never silently wrong)."""
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    for group in ("sses", "shes", "ches", "xes", "zes"):
        if len(word) > len(group) and word.endswith(group):
            return word[:-2]
    if len(word) > 2 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def head_token(name: str) -> str:
    """The leading camelCase / snake_case token of an identifier.

    S3 groups on this, because suffix-stripping alone does not reach D9's
    worked example: 'PaymentSettlementJob' loses only 'Job' and lands on
    'PaymentSettlement', which shares no key with 'PaymentController'. The
    head token is what those three names actually agree on.

    An acronym run counts as one token ('HTTPServer' -> 'HTTP'), so a name
    is never split mid-initialism.
    """
    first = name.strip().replace("-", "_").split("_")[0]
    if not first:
        return name.strip()
    out = [first[0]]
    for index, char in enumerate(first[1:], start=1):
        previous = first[index - 1]
        starts_word = char.isupper() and (
            previous.islower()  # payMent
            or (index + 1 < len(first) and first[index + 1].islower())
        )
        if starts_word:  # HTTPServer -> HTTP
            break
        out.append(char)
    return "".join(out)


def _strip_layer_suffix(name: str) -> str:
    """Strip the LONGEST matching layer suffix, never the first declared.

    Longest-match rather than first-match so the tuple's order cannot change
    behaviour: 'StringUtils' stripped of 'Util' leaves a trailing 's' that
    singularize would then eat, reaching the same answer by luck rather than
    by rule.
    """
    lowered = name.lower()
    matches = [s for s in LAYER_SUFFIXES if lowered.endswith(s.lower()) and len(name) > len(s)]
    if not matches:
        return name
    return name[: -len(max(matches, key=len))]


def normalize(name: str) -> str:
    """The normalized form two candidates must share to be merged."""
    out = _strip_layer_suffix(name.strip())
    out = out.strip("_-").lower()
    return singularize(out)
```

- [ ] **Step 4: Declare `naming` on S1 (P2-D2)**

In `src/sdlc/assessment/scan/registry.py`, change S1's entry:

```python
    ScanSignalId.S1: _spec(
        ScanSignalId.S1, 1, SignalSource.COMPUTED,
        module=f"{_SIG}.packages", activity="scan_packages",
        rule_modules=(_NAMING,)),
```

Leave `version` at `1`: version 1 is the first body this signal ever had, and
`rules_sha` already moves on the byte change. Bumping it would imply a
released v1 that never existed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_scan_naming.py tests/test_scan_rules_sha.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/scan/naming.py src/sdlc/assessment/scan/registry.py tests/test_scan_naming.py tests/test_scan_rules_sha.py
git commit -m "feat(scan): the shared naming rules; S1 declares them too (E-46 D9/P2-D2)"
```

---

### Task 2: S1 — package structure

**Files:**
- Modify: `src/sdlc/assessment/scan/signals/packages.py`
- Test: `tests/test_scan_s1_packages.py` (create)

**Interfaces:**
- Consumes: `normalize`, `GENERIC_NAMES`, `LAYER_NAMES` from Task 1.
- Produces: `SOURCE_EXTENSIONS: tuple[str, ...]`, `DOMAIN_TERMS: frozenset[str]`, and
  `evaluate(paths: Sequence[str], loc: Mapping[str, int], skipped: Sequence[str] = ()) -> SignalOutput`.
  Task 5's `scan_packages` activity is the only caller.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_s1_packages.py`:

```python
"""S1 -- directory groupings at depth 1-3, classified by name.

BrownKit: domain-suggestive names contribute HIGH, generic and framework/layer
names LOW. The classification is carried as the RULE that fired, not as a
boolean, because E-48's "delivery channels and deployment boundaries are not
capabilities" guardrail needs the distinction (SourceCandidate's docstring).
"""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_PACKAGES,
    Confidence,
    MemberKind,
    ScanSignalId,
)
from sdlc.assessment.scan.signals import packages
from sdlc.measurement import CollectionState

TREE = [
    "README.md",
    "pyproject.toml",
    "src/payments/__init__.py",
    "src/payments/api.py",
    "src/payments/settle.py",
    "src/utils/strings.py",
    "src/controllers/health.py",
    "src/catcafe/booking.py",
]
LOC = {p: 20 for p in TREE if p.endswith(".py")}


def _by_id(out):
    return {c.local_id: c for c in out.sources}


def test_a_domain_term_contributes_high():
    out = packages.evaluate(TREE, LOC)
    pay = _by_id(out)["S1-src--payments"]
    assert pay.rule == "s1_domain_term"
    assert pay.confidence_contribution is Confidence.HIGH


def test_a_generic_name_contributes_low_under_its_own_rule():
    out = packages.evaluate(TREE, LOC)
    utils = _by_id(out)["S1-src--utils"]
    assert utils.rule == "s1_generic_name"
    assert utils.confidence_contribution is Confidence.LOW


def test_a_layer_name_is_a_different_rule_from_a_generic_one():
    """E-48's guardrail needs 'this is a technical layer' distinguishable
    from 'this is a vague bucket'."""
    out = packages.evaluate(TREE, LOC)
    assert _by_id(out)["S1-src--controllers"].rule == "s1_layer_name"
    assert _by_id(out)["S1-src--utils"].rule == "s1_generic_name"


def test_an_unlisted_specific_name_is_neither_vouched_for_nor_dismissed():
    """'catcafe' is not in DOMAIN_TERMS, but it is not generic either.
    Calling it a domain term would be a fabrication; calling it generic would
    lose a real candidate. MEDIUM under its own rule."""
    out = packages.evaluate(TREE, LOC)
    cc = _by_id(out)["S1-src--catcafe"]
    assert cc.rule == "s1_unclassified_name"
    assert cc.confidence_contribution is Confidence.MEDIUM


def test_the_local_id_carries_the_path_not_just_the_leaf():
    """Two directories can share a basename (api/models, web/models); the id
    must not collide, and the slug's '--' keeps signal_of's split on the
    FIRST hyphen unambiguous."""
    out = packages.evaluate(TREE, LOC)
    assert "S1-src--payments" in _by_id(out)
    assert "S1-src" in _by_id(out)


def test_members_are_the_package_and_the_files_directly_in_it():
    out = packages.evaluate(TREE, LOC)
    pay = _by_id(out)["S1-src--payments"]
    kinds = {m.kind for m in pay.members}
    assert MemberKind.PACKAGE_PATH in kinds
    assert MemberKind.FILE_PATH in kinds
    values = {m.value for m in pay.members}
    assert "src/payments" in values
    assert "src/payments/api.py" in values
    # NOT a file from another package
    assert "src/utils/strings.py" not in values


def test_a_parent_directory_carries_only_its_own_files():
    """src/ groups recursively for its metrics but must not carry every
    descendant as a member -- an 800-file candidate is not evidence."""
    out = packages.evaluate(TREE, LOC)
    src = _by_id(out)["S1-src"]  # noqa: E501 -- depth-1 slug has no separator
    files = [m for m in src.members if m.kind is MemberKind.FILE_PATH]
    assert files == []  # src/ directly contains no source
    assert src.metrics["file_count"].value == 6.0  # recursive


def test_loc_estimate_is_not_collected_when_a_blob_was_skipped():
    """FR-915: a partial sum must not pass as a complete one."""
    out = packages.evaluate(TREE, LOC, skipped=["src/payments/settle.py"])
    pay = _by_id(out)["S1-src--payments"]
    assert pay.metrics["loc_estimate"].state is CollectionState.NOT_COLLECTED
    assert "settle.py" in pay.metrics["loc_estimate"].reason
    # the count is still knowable
    assert pay.metrics["file_count"].state is CollectionState.MEASURED


def test_depth_is_bounded_at_three():
    tree = ["a/b/c/d/deep.py"]
    out = packages.evaluate(tree, {"a/b/c/d/deep.py": 5})
    depths = {len(c.local_id.removeprefix("S1-").split("--")) for c in out.sources}
    assert max(depths) <= 3


def test_a_repo_with_no_source_is_a_measured_zero_not_a_gap():
    """We looked and there is none -- scaffold.py's precedent for structure."""
    out = packages.evaluate(["README.md", "LICENSE"], {})
    assert out.row.collected.state is CollectionState.MEASURED
    assert out.row.collected.value == 0.0
    assert out.sources == []


def test_the_row_reports_its_category_and_nothing_else():
    out = packages.evaluate(TREE, LOC)
    assert set(out.row.categories) == {C_PACKAGES}
    assert out.row.signal is ScanSignalId.S1


def test_output_is_order_independent():
    """NFR-10: the same tree in a different order is the same artifact."""
    a = packages.evaluate(TREE, LOC)
    b = packages.evaluate(list(reversed(TREE)), LOC)
    assert a.model_dump_json() == b.model_dump_json()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_scan_s1_packages.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.assessment.scan.signals.packages' has no attribute 'evaluate'`.

- [ ] **Step 3: Implement S1**

Replace the whole of `src/sdlc/assessment/scan/signals/packages.py`:

```python
"""S1 -- package structure (FR-912).

BrownKit scans top-level modules/packages/directories at depth 1-3 and rates
each grouping by whether its name suggests a business domain. Ported with the
classification carried as the RULE that fired rather than a boolean, because
E-48's guardrail -- delivery channels and deployment boundaries are not
capabilities -- needs the distinction, not just its outcome.

Pure: text and paths in, records out. The activity reads the tree.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence

from ....measurement import Measurement
from ..models import (
    C_PACKAGES,
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
from ..naming import GENERIC_NAMES, LAYER_NAMES

SIGNAL_ID = "S1"
VERSION = 1

# Language-agnostic, and deliberately NOT ToolchainAdapter.source_extensions:
# only PythonToolchain exists, so gating on the adapter would make S1 report
# nothing for the JS/TS repositories Tier 0 actually receives. This mirrors
# the reasoning in triage/signals/scaffold.py's own _SOURCE_EXTENSIONS, whose
# list is re-declared here rather than imported -- scan/ may not import
# triage/signals/ (module purity, spec section 3).
SOURCE_EXTENSIONS: tuple[str, ...] = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".rb",
    ".php",
    ".cs",
    ".kt",
    ".swift",
    ".scala",
    ".ex",
    ".exs",
)

# BrownKit's worked list, kept short on purpose. A term absent from here is
# NOT dismissed -- it falls to s1_unclassified_name at MEDIUM. Growing this
# table raises confidence; it never creates or destroys a candidate.
DOMAIN_TERMS: frozenset[str] = frozenset(
    {
        "payment",
        "payments",
        "billing",
        "invoice",
        "invoices",
        "customer",
        "customers",
        "order",
        "orders",
        "inventory",
        "catalog",
        "product",
        "products",
        "shipping",
        "delivery",
        "account",
        "accounts",
        "auth",
        "identity",
        "kyc",
        "compliance",
        "notification",
        "notifications",
        "messaging",
        "search",
        "reporting",
        "analytics",
        "subscription",
        "subscriptions",
        "pricing",
        "checkout",
        "cart",
        "refund",
        "refunds",
        "booking",
        "bookings",
        "reservation",
        "reservations",
        "ledger",
        "settlement",
        "onboarding",
        "loyalty",
        "review",
        "reviews",
    }
)

MAX_DEPTH = 3

M_FILE_COUNT = "file_count"
M_LOC_ESTIMATE = "loc_estimate"


def _classify(name: str) -> tuple[str, Confidence, str]:
    """(rule, contribution, detail) for a directory name.

    Layer is checked before generic because a few words are arguably both,
    and the more specific claim is the more useful one to E-48.
    """
    key = name.lower()
    if key in LAYER_NAMES:
        return (
            "s1_layer_name",
            Confidence.LOW,
            f"{name!r} names a technical layer, not a capability.",
        )
    if key in GENERIC_NAMES:
        return ("s1_generic_name", Confidence.LOW, f"{name!r} is a generic container name.")
    if key in DOMAIN_TERMS:
        return ("s1_domain_term", Confidence.HIGH, f"{name!r} is a business-domain term.")
    return (
        "s1_unclassified_name",
        Confidence.MEDIUM,
        f"{name!r} is a specific name absent from the domain-term table; "
        f"it is not generic, but nothing here vouches for it.",
    )


def _slug(directory: str) -> str:
    """A local_id fragment. '--' joins path segments so the depth is
    recoverable from the id and no separator collides with signal_of's '-'
    split on the FIRST hyphen."""
    return "--".join(directory.split("/"))


def _directories(paths: Sequence[str]) -> dict[str, list[str]]:
    """directory -> its source files, for every directory at depth 1..3 that
    contains a source file recursively. Sorted at every level so traversal
    order cannot reach the artifact."""
    out: dict[str, list[str]] = {}
    for path in sorted(paths):
        if not path.endswith(SOURCE_EXTENSIONS):
            continue
        segments = path.split("/")[:-1]
        for depth in range(1, min(len(segments), MAX_DEPTH) + 1):
            out.setdefault("/".join(segments[:depth]), []).append(path)
    return out


def evaluate(
    paths: Sequence[str], loc: Mapping[str, int], skipped: Sequence[str] = ()
) -> SignalOutput:
    """`paths` is every tracked path; `loc` is path -> line count for the
    blobs that were read; `skipped` is the paths whose blob was unreadable or
    over MAX_BLOB_BYTES (spec section 6)."""
    skipped_set = set(skipped)
    candidates: list[SourceCandidate] = []

    for directory, files in sorted(_directories(paths).items()):
        name = posixpath.basename(directory)
        rule, contribution, detail = _classify(name)
        direct = [f for f in files if posixpath.dirname(f) == directory]

        members = [CandidateMember(kind=MemberKind.PACKAGE_PATH, value=directory, path=directory)]
        members += [CandidateMember(kind=MemberKind.FILE_PATH, value=f, path=f) for f in direct]

        missing = sorted(f for f in files if f in skipped_set or f not in loc)
        if missing:
            loc_metric = Measurement.not_collected(
                f"line counts unavailable for {len(missing)} of "
                f"{len(files)} file(s) (first: {missing[0]}); a partial sum "
                f"must not pass as a complete one"
            )
        else:
            loc_metric = Measurement.measured(float(sum(loc[f] for f in files)))

        candidates.append(
            SourceCandidate(
                signal=ScanSignalId.S1,
                local_id=f"S1-{_slug(directory)}",
                name=name,
                rule=rule,
                detail=detail,
                confidence_contribution=contribution,
                members=members,
                evidence=[EvidenceRef(path=directory)],
                metrics={
                    M_FILE_COUNT: Measurement.measured(float(len(files))),
                    M_LOC_ESTIMATE: loc_metric,
                },
            )
        )

    candidates.sort(key=lambda c: c.local_id)
    # A repository with no source files is a MEASURED zero, not a gap: we
    # looked, and there is none. This is scaffold.py's precedent for the
    # structure dimension, and it is the one place in this module where zero
    # is the honest answer -- S3 reaches the opposite conclusion for a
    # reason its own docstring gives (P2-D1).
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S1,
            family=family_of(ScanSignalId.S1),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={C_PACKAGES: collected},
        ),
        sources=candidates,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_s1_packages.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/signals/packages.py tests/test_scan_s1_packages.py
git commit -m "feat(scan): S1 package structure, classified by the rule that fired (E-46)"
```

---

### Task 3: S3 — backend entry points

**Files:**
- Modify: `src/sdlc/assessment/scan/signals/entrypoints.py`
- Test: `tests/test_scan_s3_entrypoints.py` (create)

**Interfaces:**
- Consumes: `normalize`, `LAYER_NAMES`, `GENERIC_NAMES` from Task 1.
- Produces: `FRAMEWORKS: tuple[Framework, ...]`, `UNSUPPORTED_FRAMEWORKS: tuple[Detector, ...]`, and
  `evaluate(blobs: Mapping[str, str]) -> SignalOutput`. Task 5's `scan_entrypoints` activity is the only caller.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_s3_entrypoints.py`:

```python
"""S3 -- backend entry points, the Contract tier.

Two rules carry the weight: BrownKit's "group by business operation, not
technical type", and P2-D1's fail-closed reading of D5.
"""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_BACKEND_ENTRY,
    Confidence,
    MemberKind,
    ScanSignalId,
)
from sdlc.assessment.scan.signals import entrypoints
from sdlc.measurement import CollectionState

FASTAPI = {
    "src/payments/api.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "\n"
        "@router.post('/api/payments')\n"
        "def create_payment():\n"
        "    ...\n"
        "\n"
        "@router.get('/api/payments/{payment_id}')\n"
        "def get_payment():\n"
        "    ...\n"
    ),
}


def _by_id(out):
    return {c.local_id: c for c in out.sources}


def test_fastapi_routes_become_http_route_members():
    out = entrypoints.evaluate(FASTAPI)
    pay = _by_id(out)["S3-payment"]
    values = {m.value for m in pay.members}
    assert "POST /api/payments" in values
    assert "GET /api/payments/{payment_id}" in values
    assert all(m.kind is MemberKind.HTTP_ROUTE for m in pay.members)


def test_routes_and_jobs_and_consumers_group_into_one_candidate():
    """D9's ported rule: PaymentController + PaymentSettlementJob +
    PaymentEventConsumer is ONE candidate, not three. Do not split by
    channel."""
    blobs = dict(FASTAPI)
    blobs["src/jobs/PaymentSettlementJob.py"] = (
        "from celery import shared_task\n@shared_task\ndef settle_daily():\n    ...\n"
    )
    out = entrypoints.evaluate(blobs)
    assert set(_by_id(out)) == {"S3-payment"}
    kinds = {m.kind for m in _by_id(out)["S3-payment"].members}
    assert kinds == {MemberKind.HTTP_ROUTE, MemberKind.SCHEDULED_JOB}


def test_cross_channel_corroboration_contributes_high():
    blobs = dict(FASTAPI)
    blobs["src/jobs/PaymentSettlementJob.py"] = (
        "from celery import shared_task\n@shared_task\ndef settle():\n    ...\n"
    )
    out = entrypoints.evaluate(blobs)
    assert _by_id(out)["S3-payment"].confidence_contribution is Confidence.HIGH


def test_a_single_entry_point_contributes_low():
    out = entrypoints.evaluate(
        {
            "src/health.py": (
                "from fastapi import FastAPI\napp = FastAPI()\n"
                "@app.get('/health')\ndef health():\n    ...\n"
            )
        }
    )
    assert list(_by_id(out).values())[0].confidence_contribution is Confidence.LOW


def test_a_route_prefix_is_not_the_business_name():
    """/api/payments groups under 'payment', never under 'api'."""
    out = entrypoints.evaluate(FASTAPI)
    assert "S3-api" not in _by_id(out)
    assert "S3-payment" in _by_id(out)


def test_express_routes_are_extracted_without_a_toolchain_adapter():
    """D4: fingerprints live in the signal module, so a TS/JS repo is
    scannable before E-30b exists."""
    out = entrypoints.evaluate(
        {
            "server/orders.js": (
                "const express = require('express')\n"
                "const router = express.Router()\n"
                "router.post('/orders', createOrder)\n"
            )
        }
    )
    assert "S3-order" in _by_id(out)


def test_click_commands_become_cli_command_members():
    """And 'cli.py' names the delivery channel, not the capability, so the
    candidate takes its parent directory -- E-48's guardrail applied at
    extraction time rather than left for the proposer."""
    out = entrypoints.evaluate(
        {"src/billing/cli.py": ("import click\n@click.command()\ndef reconcile():\n    ...\n")}
    )
    assert "S3-billing" in _by_id(out)
    cand = _by_id(out)["S3-billing"]
    assert cand.members[0].kind is MemberKind.CLI_COMMAND
    assert cand.rule == "s3_cli_command"


def test_an_unfingerprinted_framework_fails_the_signal_closed():
    """P2-D1: extracting only the FastAPI half would hand E-47a a partial
    Contract tier at weight 0.55, which is what D5 forbids."""
    blobs = dict(FASTAPI)
    blobs["src/legacy/views.py"] = (
        "from django.http import JsonResponse\n"
        "def legacy_view(request):\n    return JsonResponse({})\n"
    )
    out = entrypoints.evaluate(blobs)
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "django" in out.row.collected.reason
    assert out.sources == []  # and nothing partial survives


def test_no_recognized_framework_is_a_gap_not_a_zero():
    """D5 literally: never an empty route list. 'This repo has no backend'
    and 'this backend uses something we cannot parse' are not
    distinguishable, and only one of them is safe to assert."""
    out = entrypoints.evaluate({"src/lib/math.py": "def add(a, b):\n    return a + b\n"})
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert "no recognized backend framework" in out.row.collected.reason
    assert out.sources == []


def test_the_row_reports_its_category_and_nothing_else():
    out = entrypoints.evaluate(FASTAPI)
    assert set(out.row.categories) == {C_BACKEND_ENTRY}
    assert out.row.signal is ScanSignalId.S3


def test_evidence_cites_the_file_and_line():
    out = entrypoints.evaluate(FASTAPI)
    ev = _by_id(out)["S3-payment"].evidence
    assert any(e.path == "src/payments/api.py" and e.lines for e in ev)


def test_output_is_order_independent():
    """NFR-10: dict iteration order must not reach the artifact."""
    blobs = dict(FASTAPI)
    blobs["src/orders/api.py"] = (
        "from fastapi import APIRouter\nrouter = APIRouter()\n"
        "@router.get('/orders')\ndef list_orders():\n    ...\n"
    )
    a = entrypoints.evaluate(blobs)
    b = entrypoints.evaluate(dict(reversed(list(blobs.items()))))
    assert a.model_dump_json() == b.model_dump_json()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_scan_s3_entrypoints.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'evaluate'`.

- [ ] **Step 3: Implement S3**

Replace the whole of `src/sdlc/assessment/scan/signals/entrypoints.py`:

```python
"""S3 -- backend entry points (FR-912). The Contract tier.

Pattern fingerprints declared here rather than parsed through a
ToolchainAdapter (D4): Python is the only adapter, so parser-only extraction
would make Tier 2 Python-only in practice, and scaffold.FINGERPRINTS already
shows the JS/TS repositories Tier 0 actually receives.

FAIL-CLOSED (P2-D1). If a recognized framework has no fingerprint here, the
whole signal reports not_collected naming it and emits NO candidates -- even
when another framework did match. S3's members become CapabilityFingerprint's
Contract tier at weight 0.55, and D5's stated hazard is that a silently-empty
Contract tier makes E-47a's matcher renormalize onto weaker tiers and risk
handing a stored BC-NNN to an unrelated capability. Plan 1's
_unmeasured_carries_no_payload forbids records on a non-MEASURED row anyway,
so "partially extracted" is not representable in the contract.

Pure: blobs in, records out.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping

from pydantic import BaseModel

from ....measurement import Measurement
from ..models import (
    C_BACKEND_ENTRY,
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
from ..naming import GENERIC_NAMES, LAYER_NAMES, head_token, normalize

SIGNAL_ID = "S3"
VERSION = 1


class Framework(BaseModel):
    """One framework we can both DETECT and EXTRACT from."""

    name: str
    detect: tuple[str, ...]  # substrings proving the framework is present
    pattern: str  # regex; groups are (method, path) or (name,)
    kind: MemberKind
    method_group: int = 0  # 0 = no method group; the verb is implicit
    value_group: int = 1


class Detector(BaseModel):
    """A framework we RECOGNIZE but cannot extract from. Its presence fails
    the signal closed (P2-D1) -- naming the gap is the whole point."""

    name: str
    detect: tuple[str, ...]


# Extraction is deliberately conservative: a decorator or router call on one
# line with a literal path. A route assembled at runtime is not extracted,
# which is a miss, not a fabrication.
FRAMEWORKS: tuple[Framework, ...] = (
    Framework(
        name="fastapi",
        detect=("from fastapi", "import fastapi"),
        pattern=r"@(?:\w+)\.(get|post|put|patch|delete)\(\s*['\"]([^'\"]+)",
        kind=MemberKind.HTTP_ROUTE,
        method_group=1,
        value_group=2,
    ),
    Framework(
        name="flask",
        detect=("from flask", "import flask"),
        pattern=r"@(?:\w+)\.route\(\s*['\"]([^'\"]+)",
        kind=MemberKind.HTTP_ROUTE,
        value_group=1,
    ),
    Framework(
        name="express",
        detect=("require('express')", 'require("express")', "from 'express'", 'from "express"'),
        pattern=r"\b(?:app|router)\.(get|post|put|patch|delete)"
        r"\(\s*['\"]([^'\"]+)",
        kind=MemberKind.HTTP_ROUTE,
        method_group=1,
        value_group=2,
    ),
    Framework(
        name="nestjs",
        detect=("@nestjs/common",),
        pattern=r"@(Get|Post|Put|Patch|Delete)\(\s*['\"]?([^'\")]*)",
        kind=MemberKind.HTTP_ROUTE,
        method_group=1,
        value_group=2,
    ),
    Framework(
        name="click",
        detect=("import click", "from click"),
        pattern=r"@\w+\.command\([^)]*\)\s*\ndef\s+(\w+)",
        kind=MemberKind.CLI_COMMAND,
        value_group=1,
    ),
    Framework(
        name="celery",
        detect=("from celery", "import celery"),
        pattern=r"@(?:shared_task|\w+\.task)\b[^\n]*\n(?:@[^\n]*\n)*"
        r"def\s+(\w+)",
        kind=MemberKind.SCHEDULED_JOB,
        value_group=1,
    ),
)

UNSUPPORTED_FRAMEWORKS: tuple[Detector, ...] = (
    Detector(name="django", detect=("from django", "import django")),
    Detector(name="spring", detect=("org.springframework",)),
    Detector(name="rails", detect=("Rails.application", "ActionController")),
    Detector(name="laravel", detect=("Illuminate\\",)),
    Detector(name="gin", detect=("github.com/gin-gonic/gin",)),
    Detector(name="echo", detect=("github.com/labstack/echo",)),
    Detector(name="aspnet", detect=("Microsoft.AspNetCore",)),
    Detector(name="grpc", detect=("grpc.ServiceProvider", "grpc.Server(")),
)

# Route segments that prefix an API rather than name a business operation.
_PATH_PREFIXES: frozenset[str] = frozenset(
    {
        "api",
        "apis",
        "rest",
        "graphql",
        "v1",
        "v2",
        "v3",
        "internal",
        "public",
        "admin",
        "_next",
    }
)

# Which member kind is most contract-ish, for choosing the rule a mixed
# candidate reports. Ordered, not a set: the answer must be deterministic.
_KIND_RULE: tuple[tuple[MemberKind, str], ...] = (
    (MemberKind.HTTP_ROUTE, "s3_http_route"),
    (MemberKind.GRPC_METHOD, "s3_grpc_method"),
    (MemberKind.QUEUE_TOPIC, "s3_queue_consumer"),
    (MemberKind.SCHEDULED_JOB, "s3_scheduled_job"),
    (MemberKind.CLI_COMMAND, "s3_cli_command"),
)


def detected(blobs: Mapping[str, str]) -> tuple[set[str], set[str]]:
    """(supported, unsupported) framework names present in the tree."""
    text = "\n".join(blobs[p] for p in sorted(blobs))
    supported = {f.name for f in FRAMEWORKS if any(marker in text for marker in f.detect)}
    unsupported = {
        d.name for d in UNSUPPORTED_FRAMEWORKS if any(marker in text for marker in d.detect)
    }
    return supported, unsupported


def _business_name(value: str, path: str, kind: MemberKind) -> str:
    """The business operation an entry point belongs to.

    For a route, the first path segment that is not a prefix or a parameter.
    For everything else, the HEAD TOKEN of the file stem -- which is what
    makes D9's worked example work: PaymentController, PaymentSettlementJob
    and PaymentEventConsumer share 'Payment' and nothing shorter. Stripping
    suffixes alone would leave 'PaymentSettlement' and split the candidate
    three ways, which is precisely the split-by-channel BrownKit forbids.

    A stem that names a delivery channel rather than an operation
    ('cli.py', 'routes.py') falls back to the parent directory: 'routes.py'
    names no capability, but 'payments/routes.py' does.
    """
    if kind is MemberKind.HTTP_ROUTE:
        for segment in value.split()[-1].split("/"):
            if not segment or segment[0] in "{:<*":
                continue
            if segment.lower() in _PATH_PREFIXES:
                continue
            return segment
    stem = posixpath.splitext(posixpath.basename(path))[0]
    if stem.lower() in LAYER_NAMES or stem.lower() in GENERIC_NAMES:
        parent = posixpath.basename(posixpath.dirname(path))
        if parent:
            return head_token(parent)
    return head_token(stem)


def _members(blobs: Mapping[str, str], active: set[str]) -> list[tuple[CandidateMember, str]]:
    """(member, business name) for every extractable entry point."""
    out: list[tuple[CandidateMember, str]] = []
    for framework in FRAMEWORKS:
        if framework.name not in active:
            continue
        regex = re.compile(framework.pattern)
        for path in sorted(blobs):
            for match in regex.finditer(blobs[path]):
                raw = match.group(framework.value_group)
                if framework.method_group:
                    value = f"{match.group(framework.method_group).upper()} {raw}"
                elif framework.kind is MemberKind.HTTP_ROUTE:
                    # Flask's @route defaults to GET when no methods= is given;
                    # naming the verb keeps every HTTP member one shape.
                    value = f"GET {raw}"
                else:
                    value = raw
                line = blobs[path].count("\n", 0, match.start()) + 1
                out.append(
                    (
                        CandidateMember(kind=framework.kind, value=value, path=path, line=line),
                        _business_name(value, path, framework.kind),
                    )
                )
    return out


def _contribution(members: list[CandidateMember]) -> Confidence:
    """Corroboration WITHIN S3: several channels agreeing on one operation is
    the strongest thing one source can say. Still one source, so S5's
    cross-source rule (D8) is unaffected -- this is advisory metadata for
    E-48."""
    if len({m.kind for m in members}) > 1:
        return Confidence.HIGH
    return Confidence.MEDIUM if len(members) > 1 else Confidence.LOW


def _gap(reason: str) -> SignalOutput:
    nc = Measurement.not_collected(reason)
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S3,
            family=family_of(ScanSignalId.S3),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=nc,
            categories={C_BACKEND_ENTRY: nc},
        )
    )


def evaluate(blobs: Mapping[str, str]) -> SignalOutput:
    """`blobs` is path -> text for every readable, in-bound source blob."""
    supported, unsupported = detected(blobs)

    if unsupported:
        return _gap(
            f"backend_entry_points: detected framework(s) "
            f"{sorted(unsupported)} have no fingerprint in FRAMEWORKS; "
            f"extracting only {sorted(supported)} would hand a partial "
            f"Contract tier downstream, which D5 forbids (P2-D1)"
        )
    if not supported:
        return _gap(
            f"backend_entry_points: no recognized backend framework in "
            f"{sorted(f.name for f in FRAMEWORKS)}; a repository with no "
            f"parseable entry points is not a repository with none (D5)"
        )

    grouped: dict[str, list[CandidateMember]] = {}
    for member, name in _members(blobs, supported):
        grouped.setdefault(normalize(name) or name.lower(), []).append(member)

    candidates: list[SourceCandidate] = []
    for key, members in sorted(grouped.items()):
        by_kind = sorted({m.kind for m in members}, key=lambda k: k.value)
        rule = next((r for kind, r in _KIND_RULE if kind in by_kind), "s3_entry_point")
        counts = ", ".join(
            f"{sum(1 for m in members if m.kind is kind)} {kind.value.replace('_', ' ')}(s)"
            for kind in by_kind
        )
        candidates.append(
            SourceCandidate(
                signal=ScanSignalId.S3,
                local_id=f"S3-{key}",
                name=key,
                rule=rule,
                detail=f"{counts} grouped by business operation, not by technical type.",
                confidence_contribution=_contribution(members),
                members=members,
                evidence=[EvidenceRef(path=m.path, lines=str(m.line)) for m in members if m.path],
            )
        )

    candidates.sort(key=lambda c: c.local_id)
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S3,
            family=family_of(ScanSignalId.S3),
            version=VERSION,
            source=SignalSource.COMPUTED,
            collected=collected,
            categories={C_BACKEND_ENTRY: collected},
        ),
        sources=candidates,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_s3_entrypoints.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/signals/entrypoints.py tests/test_scan_s3_entrypoints.py
git commit -m "feat(scan): S3 entry points, grouped by operation and failing closed (E-46 D5/P2-D1)"
```

---

### Task 4: S5 — cross-source merge and confidence

**Files:**
- Modify: `src/sdlc/assessment/scan/merge.py`
- Test: `tests/test_scan_merge.py` (create)

**Interfaces:**
- Consumes: `normalize` from Task 1; `SourceCandidate` / `ScanCandidate` / `confidence_from` from `scan/models.py`.
- Produces: `CANDIDATE_BAND: tuple[int, int]`, `MergeOutput` (fields `candidates: list[ScanCandidate]`, `collected: Measurement`), and
  `merge(sources: Sequence[SourceCandidate], upstream: Mapping[ScanSignalId, Measurement]) -> MergeOutput`.
  Task 6's `_scan` and Task 7's summary are the callers.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_merge.py`:

```python
"""S5 -- the merge. Two rules and no more (D9), and a confidence that is
derived from distinct SOURCES, never from the depth of one (D8)."""

from __future__ import annotations

from sdlc.assessment.scan.merge import CANDIDATE_BAND, merge
from sdlc.assessment.scan.models import (
    CandidateMember,
    Confidence,
    MemberKind,
    ScanSignalId,
    SourceCandidate,
)
from sdlc.measurement import CollectionState, Measurement

MEASURED = {
    s: Measurement.measured(1.0)
    for s in (ScanSignalId.S1, ScanSignalId.S2, ScanSignalId.S3, ScanSignalId.S4)
}


def _sc(
    signal: ScanSignalId, slug: str, name: str, members: list[CandidateMember] | None = None
) -> SourceCandidate:
    return SourceCandidate(
        signal=signal,
        local_id=f"{signal.value}-{slug}",
        name=name,
        rule="r",
        detail="d",
        confidence_contribution=Confidence.LOW,
        members=members or [CandidateMember(kind=MemberKind.PACKAGE_PATH, value=f"src/{slug}")],
    )


def test_three_sources_on_one_name_merge_to_high():
    out = merge(
        [
            _sc(ScanSignalId.S1, "payments", "payments"),
            _sc(ScanSignalId.S3, "payment", "PaymentController"),
            _sc(ScanSignalId.S4, "pay", "Payments"),
        ],
        MEASURED,
    )
    assert len(out.candidates) == 1
    assert out.candidates[0].confidence is Confidence.HIGH
    assert len(out.candidates[0].sources) == 3


def test_two_sources_are_medium_and_one_is_low():
    two = merge(
        [_sc(ScanSignalId.S1, "orders", "orders"), _sc(ScanSignalId.S3, "order", "OrderService")],
        MEASURED,
    )
    assert two.candidates[0].confidence is Confidence.MEDIUM
    one = merge([_sc(ScanSignalId.S1, "orders", "orders")], MEASURED)
    assert one.candidates[0].confidence is Confidence.LOW


def test_two_candidates_from_the_SAME_signal_do_not_corroborate():
    """D8: distinct SIGNALS, not distinct candidates -- two S1 groupings are
    one source's opinion twice."""
    out = merge(
        [_sc(ScanSignalId.S1, "payments", "payments"), _sc(ScanSignalId.S1, "payment", "Payment")],
        MEASURED,
    )
    assert len(out.candidates) == 1
    assert out.candidates[0].confidence is Confidence.LOW


def test_overlapping_members_under_different_names_are_not_collapsed():
    """D9 rule 2, ported verbatim: emit both, flag each. /discover decides
    MERGE vs SPLIT -- S5 never has to be right, only never silently wrong."""
    shared = CandidateMember(kind=MemberKind.FILE_PATH, value="src/billing/core.py")
    out = merge(
        [
            _sc(ScanSignalId.S1, "payments", "payments", [shared]),
            _sc(ScanSignalId.S3, "refund", "Refunds", [shared]),
        ],
        MEASURED,
    )
    assert len(out.candidates) == 2
    ids = {c.candidate_id for c in out.candidates}
    for c in out.candidates:
        assert c.possible_duplicate_of == sorted(ids - {c.candidate_id})


def test_non_overlapping_candidates_carry_no_duplicate_flag():
    out = merge(
        [_sc(ScanSignalId.S1, "payments", "payments"), _sc(ScanSignalId.S3, "orders", "Orders")],
        MEASURED,
    )
    assert all(c.possible_duplicate_of == [] for c in out.candidates)


def test_candidate_ids_are_assigned_in_sorted_order_and_zero_padded():
    out = merge(
        [_sc(ScanSignalId.S1, "orders", "orders"), _sc(ScanSignalId.S3, "billing", "Billing")],
        MEASURED,
    )
    assert [c.candidate_id for c in out.candidates] == ["C-01", "C-02"]
    # The display name is one a SOURCE used ("Billing"), never one this
    # function invented by title-casing the normalized key.
    assert [c.name for c in out.candidates] == ["Billing", "orders"]


def test_a_candidate_id_is_not_a_capability_id():
    """BC-NNN is E-47a's surrogate key, allocated after discover. Minting one
    here would put capability identity two phases early."""
    out = merge([_sc(ScanSignalId.S1, "orders", "orders")], MEASURED)
    assert not out.candidates[0].candidate_id.startswith("BC-")


def test_members_from_every_source_reach_the_merged_candidate():
    a = CandidateMember(kind=MemberKind.PACKAGE_PATH, value="src/payments")
    b = CandidateMember(
        kind=MemberKind.HTTP_ROUTE, value="POST /api/payments", path="src/api.py", line=4
    )
    out = merge(
        [
            _sc(ScanSignalId.S1, "payments", "payments", [a]),
            _sc(ScanSignalId.S3, "payment", "PaymentController", [b]),
        ],
        MEASURED,
    )
    assert set(out.candidates[0].members) == {a, b}


def test_no_sources_from_signals_that_all_failed_is_a_gap():
    """FR-915: merging nothing because there was nothing to merge is not a
    measured zero."""
    nc = Measurement.not_collected("S3 activity failed")
    out = merge([], {ScanSignalId.S1: nc, ScanSignalId.S3: nc})
    assert out.collected.state is CollectionState.NOT_COLLECTED
    assert "S1" in out.collected.reason and "S3" in out.collected.reason
    assert out.candidates == []


def test_no_sources_from_signals_that_measured_is_a_real_zero():
    out = merge([], MEASURED)
    assert out.collected.state is CollectionState.MEASURED
    assert out.collected.value == 0.0


def test_the_candidate_band_is_a_constant_not_a_gate():
    """D11: BrownKit hard-gates on 15-25; ported as advisory, because a
    40-file Next.js app legitimately has four capabilities."""
    assert CANDIDATE_BAND == (15, 25)
    out = merge([_sc(ScanSignalId.S1, "orders", "orders")], MEASURED)
    assert out.collected.state is CollectionState.MEASURED  # not a failure


def test_output_is_order_independent():
    args = [
        _sc(ScanSignalId.S1, "payments", "payments"),
        _sc(ScanSignalId.S3, "payment", "PaymentController"),
        _sc(ScanSignalId.S4, "orders", "Orders"),
    ]
    a = merge(args, MEASURED)
    b = merge(list(reversed(args)), MEASURED)
    assert a.model_dump_json() == b.model_dump_json()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_scan_merge.py -v`
Expected: FAIL — `ImportError: cannot import name 'merge'`.

- [ ] **Step 3: Implement S5**

Replace the whole of `src/sdlc/assessment/scan/merge.py`:

```python
"""S5 -- cross-source merge and confidence (FR-912, D8/D9).

Runs in WORKFLOW code (in_workflow=True): it is a pure derivation over other
signals' output and reads no tree, so an activity would buy nothing and cost
a round trip. Same reason compute_readiness runs inside TriageWorkflow.

Two merge rules and no more:

  1. Merge on normalized name (naming.normalize -- strip layer suffix,
     lowercase, singularize).
  2. Overlapping members under different names -> do NOT merge. Emit both,
     flag each with possible_duplicate_of.

Rule 2 is BrownKit's non-collapse rule ported verbatim, and it is what makes
S5 safe: it never has to be RIGHT, only never silently wrong. Deciding a
genuine merge is E-48's D2 (CONFIRM | SPLIT | MERGE | DE-SCOPE | FLAG), a
proposer with the context to do it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from ...measurement import CollectionState, Measurement
from .models import (
    CandidateMember,
    ScanCandidate,
    ScanSignalId,
    SourceCandidate,
    confidence_from,
    signal_of,
)
from .naming import normalize

SIGNAL_ID = "S5"
VERSION = 1

# D11: BrownKit hard-gates /scan on producing 15-25 candidates and re-extracts
# when under. Ported as an ADVISORY only -- its band comes from enterprise
# Java monoliths, and Tier 0's rationale is that target repositories are small
# and vibe-coded, where a 40-file Next.js application legitimately has four
# capabilities. A binding version belongs in E-51's CheckResults.
CANDIDATE_BAND: tuple[int, int] = (15, 25)


class MergeOutput(BaseModel):
    candidates: list[ScanCandidate] = Field(default_factory=list)
    collected: Measurement


def _overlaps(a: frozenset[CandidateMember], b: frozenset[CandidateMember]) -> bool:
    """Sharing ANY member is enough to flag. Deliberately generous: an
    over-flag costs E-48 one decision it was going to make anyway, while an
    under-flag is a silent collapse -- the exact failure rule 2 exists to
    prevent."""
    return bool(a & b)


def merge(
    sources: Sequence[SourceCandidate], upstream: Mapping[ScanSignalId, Measurement]
) -> MergeOutput:
    """`upstream` is each consumed signal's row-level `collected`, which is
    what separates "merged zero because there was nothing" (a gap) from
    "merged zero because the sources found none" (a real zero)."""
    groups: dict[str, list[SourceCandidate]] = {}
    for candidate in sources:
        key = normalize(candidate.name) or candidate.name.strip().lower()
        groups.setdefault(key, []).append(candidate)

    ordered = sorted(groups.items())
    member_sets = [frozenset(m for c in group for m in c.members) for _, group in ordered]
    ids = [f"C-{i:02d}" for i in range(1, len(ordered) + 1)]

    candidates: list[ScanCandidate] = []
    for index, (key, group) in enumerate(ordered):
        local_ids = sorted({c.local_id for c in group})
        candidates.append(
            ScanCandidate(
                candidate_id=ids[index],
                # The alphabetically-first raw name, so the display name is a
                # name a source actually used rather than one this function
                # invented from the normalized key.
                name=sorted(c.name for c in group)[0],
                sources=local_ids,
                confidence=confidence_from(signal_of(i) for i in local_ids),
                members=sorted(member_sets[index], key=CandidateMember.sort_key),
                possible_duplicate_of=sorted(
                    ids[other]
                    for other in range(len(ordered))
                    if other != index and _overlaps(member_sets[index], member_sets[other])
                ),
            )
        )

    if candidates:
        return MergeOutput(
            candidates=candidates, collected=Measurement.measured(float(len(candidates)))
        )

    unmeasured = sorted(
        s.value for s, m in upstream.items() if m.state is not CollectionState.MEASURED
    )
    if unmeasured:
        # Merging nothing because every source failed is not a measured zero
        # (FR-915). Naming the signals is what tells an operator whether the
        # repository has no capabilities or the scan could not see them.
        return MergeOutput(
            collected=Measurement.not_collected(
                f"candidate_merge: no source candidates, and {unmeasured} did "
                f"not collect -- a merge over nothing is not a measured zero"
            )
        )
    return MergeOutput(collected=Measurement.measured(0.0))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_scan_merge.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/assessment/scan/merge.py tests/test_scan_merge.py
git commit -m "feat(scan): S5 merge -- derived confidence, never a silent collapse (E-46 D8/D9)"
```

---

### Task 5: The two activity bodies and the memo's first caller

**Files:**
- Modify: `src/sdlc/assessment/activities.py`
- Test: `tests/test_scan_activities_s1_s3.py` (create)
- Test: `tests/test_scan_stub_activities.py` (refit)

**Interfaces:**
- Consumes: `packages.evaluate` (Task 2), `entrypoints.evaluate` (Task 3), `memo.load` / `memo.store` (plan 1, no caller until now).
- Produces: `BUILT: frozenset[ScanSignalId]`, `failed_signal(signal_id, exc) -> SignalOutput`, and real `scan_packages` / `scan_entrypoints` bodies.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_activities_s1_s3.py`:

```python
"""Plan 2 gives the scan memo its FIRST production caller. Plan 1 built
memo.load/store and shipped eleven stubs, none of which could ever store --
memo.store refuses anything not MEASURED."""

from __future__ import annotations

import subprocess

import pytest

from sdlc.assessment import activities as acts
from sdlc.assessment.scan import memo
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.measurement import CollectionState

TREE = 40 * "ab"  # any stable 40-hex-shaped string


def _repo(tmp_path):
    """A real git repo, because these activities read blobs at a commit."""

    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "T")
    src = tmp_path / "src" / "payments"
    src.mkdir(parents=True)
    (src / "api.py").write_text(
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/payments')\n"
        "def create():\n    ...\n"
    )
    run("add", "-A")
    run("commit", "-q", "-m", "init")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True
    ).stdout.strip()
    return str(tmp_path), sha


def _input(repo, sha, tree=TREE):
    return acts.ScanSignalInput(repo_dir=repo, commit_sha=sha, tree_hash=tree)


@pytest.mark.asyncio
async def test_s1_reports_the_payments_package(tmp_path):
    repo, sha = _repo(tmp_path)
    out = await acts.scan_packages(_input(repo, sha))
    assert out.row.collected.state is CollectionState.MEASURED
    assert any(c.local_id == "S1-src--payments" for c in out.sources)


@pytest.mark.asyncio
async def test_s3_reports_the_route(tmp_path):
    repo, sha = _repo(tmp_path)
    out = await acts.scan_entrypoints(_input(repo, sha))
    assert out.row.collected.state is CollectionState.MEASURED
    assert any("POST /api/payments" in m.value for c in out.sources for m in c.members)


@pytest.mark.asyncio
async def test_a_measured_result_is_stored_and_served_from_the_memo(tmp_path, monkeypatch):
    repo, sha = _repo(tmp_path)
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "cache"))
    first = await acts.scan_packages(_input(repo, sha))
    assert memo.load(ScanSignalId.S1, TREE) is not None
    # A second run must not re-read the tree: point it at a repo that is gone.
    second = await acts.scan_packages(_input("/nonexistent", sha))
    assert second.model_dump_json() == first.model_dump_json()


@pytest.mark.asyncio
async def test_a_failed_signal_is_not_cached(tmp_path, monkeypatch):
    """D10: memoizing a failure would return it as a cache hit forever."""
    monkeypatch.setenv("SDLC_MEMOIZATION_CACHE_ROOT", str(tmp_path / "cache"))
    out = await acts.scan_packages(_input("/nonexistent", "deadbeef"))
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert memo.load(ScanSignalId.S1, TREE) is None


@pytest.mark.asyncio
async def test_an_activity_never_raises(tmp_path):
    """A signal that fails degrades ALONE; run_or_degrade covers timeouts,
    this covers everything inside the activity."""
    out = await acts.scan_entrypoints(_input("/nonexistent", "deadbeef"))
    assert out.row.collected.state is CollectionState.NOT_COLLECTED
    assert out.sources == []


def test_built_and_owed_partition_the_activity_signals():
    """A body that lands without its OWED_BY entry removed would report
    'not implemented' forever; the reverse would KeyError at runtime."""
    declared = {s for s in acts.SCAN_SIGNALS if acts.SCAN_SIGNALS[s].activity}
    assert acts.BUILT | set(acts.OWED_BY) == declared
    assert not (acts.BUILT & set(acts.OWED_BY))


def test_the_two_built_signals_are_s1_and_s3():
    assert acts.BUILT == {ScanSignalId.S1, ScanSignalId.S3}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_scan_activities_s1_s3.py -v`
Expected: FAIL — `AttributeError: module 'sdlc.assessment.activities' has no attribute 'BUILT'`, and the S1/S3 activities return `not_collected` stubs.

- [ ] **Step 3: Replace the two stub bodies**

In `src/sdlc/assessment/activities.py`, extend the imports:

```python
from ..triage.activities import tracked_paths
from ..triage.gitread import is_over_size_limit, read_tree
from .scan import memo
from .scan.models import (
    CATEGORIES,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
from .scan.registry import SCAN_SIGNALS
from .scan.signals import entrypoints, packages
```

Replace the `OWED_BY` block with:

```python
# Signals whose body has landed. Kept beside OWED_BY and asserted disjoint
# from it: a body that lands without its OWED_BY entry removed would report
# "not implemented" forever, and removing the entry without landing the body
# is a KeyError in unbuilt_signal.
BUILT: frozenset[ScanSignalId] = frozenset(
    {
        ScanSignalId.S1,
        ScanSignalId.S3,
    }
)

# Which plan owes each remaining signal's body.
OWED_BY: dict[ScanSignalId, str] = {
    ScanSignalId.S2: "plan 3",
    ScanSignalId.S4: "plan 3",
    ScanSignalId.SS1: "plan 3",
    ScanSignalId.SS3: "plan 3",
    ScanSignalId.SS4: "plan 3",
    ScanSignalId.QS1: "plan 3",
    ScanSignalId.QS2: "plan 3",
    ScanSignalId.QS3: "plan 3",
    ScanSignalId.QS4: "plan 3",
}
```

Add the failure helper beside `unbuilt_signal`:

```python
def failed_signal(signal_id: ScanSignalId, exc: Exception) -> SignalOutput:
    """A signal whose body raised. Never re-raised: one signal that cannot
    read the tree must not take the other twelve down with it (E-41 D3).
    Distinct from unbuilt_signal because "we tried and could not" is not
    "nobody has written this yet" -- the reason strings must not converge."""
    reason = f"{signal_id.value} failed: {type(exc).__name__}: {exc}"[:300]
    return SignalOutput(
        row=ScanSignalResult(
            signal=signal_id,
            family=family_of(signal_id),
            version=SCAN_SIGNALS[signal_id].version,
            source=SignalSource.COMPUTED,
            collected=Measurement.not_collected(reason),
            categories={k: Measurement.not_collected(reason) for k in CATEGORIES[signal_id]},
        )
    )


def _source_blobs(
    repo_dir: str, commit_sha: str, paths: list[str], extensions: tuple[str, ...]
) -> tuple[dict[str, str], list[str]]:
    """(blobs, skipped) for source files at the pinned commit.

    `skipped` carries the oversized ones so a caller can report a partial
    count as not_collected rather than as a smaller number (spec section 6).
    """
    wanted = sorted(p for p in paths if p.endswith(extensions))
    blobs: dict[str, str] = {}
    for path, text in read_tree(repo_dir, commit_sha, wanted):
        if is_over_size_limit(text):
            continue
        blobs[path] = text
    return blobs, [p for p in wanted if p not in blobs]
```

Replace `scan_packages` and `scan_entrypoints`:

```python
@activity.defn
async def scan_packages(inp: ScanSignalInput) -> SignalOutput:
    """S1 -- package structure at depth 1-3.

    The scan memo's first production caller: plan 1 built load/store, and
    every stub it shipped was refused by store's not-MEASURED rule.
    """
    if (hit := memo.load(ScanSignalId.S1, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, skipped = _source_blobs(
            inp.repo_dir, inp.commit_sha, paths, packages.SOURCE_EXTENSIONS
        )
        loc = {p: text.count("\n") + 1 for p, text in blobs.items()}
        out = packages.evaluate(paths, loc, skipped)
    except Exception as exc:  # noqa: BLE001 -- see helper
        _log.warning("S1 failed: %s", exc)
        return failed_signal(ScanSignalId.S1, exc)
    memo.store(ScanSignalId.S1, inp.tree_hash, out)
    return out


@activity.defn
async def scan_entrypoints(inp: ScanSignalInput) -> SignalOutput:
    """S3 -- backend entry points, the Contract tier."""
    if (hit := memo.load(ScanSignalId.S3, inp.tree_hash)) is not None:
        return hit
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        blobs, _ = _source_blobs(inp.repo_dir, inp.commit_sha, paths, packages.SOURCE_EXTENSIONS)
        out = entrypoints.evaluate(blobs)
    except Exception as exc:  # noqa: BLE001
        _log.warning("S3 failed: %s", exc)
        return failed_signal(ScanSignalId.S3, exc)
    memo.store(ScanSignalId.S3, inp.tree_hash, out)
    return out
```

- [ ] **Step 4: Refit the stub test**

In `tests/test_scan_stub_activities.py`, replace `_activity_signals` and its
uses so the parametrized stub assertions run over the signals that are still
stubs, while the existence check stays over every declared activity:

```python
def _activity_signals() -> list[ScanSignalId]:
    """Every signal the registry says has an activity -- built or not."""
    return [s for s in SCAN_ORDER if SCAN_SIGNALS[s].activity]


def _stub_signals() -> list[ScanSignalId]:
    """The ones still owed a body. S1 and S3 landed in plan 2, so
    unbuilt_signal would KeyError on them."""
    return [s for s in SCAN_ORDER if s in scan_acts.OWED_BY]
```

Change the three `@pytest.mark.parametrize(...)` decorators on
`test_stub_reports_not_collected_naming_the_plan`,
`test_stub_reports_every_category_it_owes` and `test_stub_carries_no_records`
from `_activity_signals()` to `_stub_signals()`. Leave
`test_every_declared_activity_exists_on_the_module` on `_activity_signals()`.

Update the module docstring's last line:

```python
"""Plan 1 shipped the eleven activities as stubs reporting not_collected and
naming the plan that owes them -- E-45's unbuilt() discipline, one level
down. Plan 2 replaced S1's and S3's bodies; the remaining nine are still
stubs, and OWED_BY is what says so."""
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_scan_activities_s1_s3.py tests/test_scan_stub_activities.py tests/test_scan_memo.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/assessment/activities.py tests/test_scan_activities_s1_s3.py tests/test_scan_stub_activities.py
git commit -m "feat(scan): real S1/S3 activities; the scan memo gets its first caller (E-46)"
```

---

### Task 6: Wire S5's merge into `_scan`

**Files:**
- Modify: `src/sdlc/workflows/assessment.py:44-56` (imports), `:353-384` (the post-wave block)
- Test: `tests/test_assessment_scan_phase.py` (extend)

**Interfaces:**
- Consumes: `merge` / `MergeOutput` (Task 4), `_upstream_for` (plan 1).
- Produces: a `ScanResult` whose `candidates` are populated and whose S5 row is real.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_assessment_scan_phase.py`:

```python
def test_s5_row_is_built_from_the_merge_not_from_a_stub():
    """E-45 D6's derivation was the plan-1 claim; this is the plan-2 one:
    S5's row comes from merge(), so nothing in the artifact names a plan."""
    from sdlc.assessment.scan.merge import merge
    from sdlc.assessment.scan.models import C_MERGE
    from sdlc.workflows.assessment import _merged_row

    out = merge(
        [_candidate(ScanSignalId.S1, "S1-payments"), _candidate(ScanSignalId.S3, "S3-payments")],
        {ScanSignalId.S1: Measurement.measured(1.0), ScanSignalId.S3: Measurement.measured(1.0)},
    )
    row = _merged_row(out)
    assert row.signal is ScanSignalId.S5
    assert row.source is SignalSource.COMPUTED
    assert row.producer is None
    assert set(row.categories) == {C_MERGE}
    assert row.collected.state is CollectionState.MEASURED
    assert "plan" not in (row.collected.reason or "").lower()


def test_s5_reports_a_gap_when_every_source_signal_failed():
    from sdlc.assessment.scan.merge import merge
    from sdlc.workflows.assessment import _merged_row

    nc = Measurement.not_collected("S1 activity failed or timed out")
    row = _merged_row(merge([], {ScanSignalId.S1: nc, ScanSignalId.S3: nc}))
    assert row.collected.state is CollectionState.NOT_COLLECTED
    assert "S1" in row.collected.reason
```

Note: `_candidate` and `_measured_row` already exist in this file (lines
152–160); reuse them rather than redefining.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_assessment_scan_phase.py -v`
Expected: FAIL — `ImportError: cannot import name '_merged_row'`.

- [ ] **Step 3: Add `_merged_row` and call the merge**

In `src/sdlc/workflows/assessment.py`, extend the guarded import block:

```python
from ..assessment.scan.merge import MergeOutput, merge
from ..assessment.scan.models import (
    C_MERGE,
    CATEGORIES,
    SCAN_ORDER,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SignalOutput,
    SignalSource,
    SourceCandidate,
    family_of,
)
```

Add beside `_inherited_row`:

```python
def _merged_row(out: MergeOutput) -> ScanSignalResult:
    """S5's row. COMPUTED with no producer: S5 inherits nothing -- it is a
    derivation over signals this phase computed, which is why it runs in
    workflow code rather than as an activity (D6)."""
    return ScanSignalResult(
        signal=ScanSignalId.S5,
        family=family_of(ScanSignalId.S5),
        version=SCAN_SIGNALS[ScanSignalId.S5].version,
        source=SignalSource.COMPUTED,
        collected=out.collected,
        categories={C_MERGE: out.collected},
    )
```

Replace the post-wave block in `_scan` (currently the `for sid in SCAN_ORDER`
loop through the `ScanResult(...)` construction) with:

```python
# SS2 is purely inherited (D12 cut its computed half), so the half IS
# the signal: it reads INHERITED and collected when triage collected,
# not as a skipped stub.
for sid in SCAN_ORDER:
    if sid in outputs or SCAN_SIGNALS[sid].activity or sid is ScanSignalId.S5:
        continue
    half = halves.get(sid)
    outputs[sid] = SignalOutput(
        row=_inherited_row(sid, half)
        if half is not None
        else skipped_scan_signal(sid, f"{sid.value} has no activity and no inherited half")
    )

# S5 last: it is a merge over the other source signals' candidates,
# filtered by its declared `consumes` (the same declaration that
# drives its wave and its memo key), so it cannot read undeclared
# data. Its candidates are the phase's headline output.
merged = merge(
    _upstream_for(ScanSignalId.S5, outputs),
    {
        sid: outputs[sid].row.collected
        for sid in SCAN_SIGNALS[ScanSignalId.S5].consumes
        if sid in outputs
    },
)
outputs[ScanSignalId.S5] = SignalOutput(row=_merged_row(merged))

# Activity signals get their inherited half folded in (D7); the
# synthesized rows above are already final (SS2 IS its half; S5 has
# no half to fold), so fold_row would wrongly promote SS2 to EXTENDED.
rows = [
    fold_row(outputs[sid].row, halves.get(sid)) if SCAN_SIGNALS[sid].activity else outputs[sid].row
    for sid in SCAN_ORDER
]
sources = sorted(
    (c for out in outputs.values() for c in out.sources), key=lambda c: (c.signal.value, c.local_id)
)
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
)
```

Update `_scan`'s docstring line about S5 and the module docstring's phase list
(`scan is E-46` → note scan is built, discover E-48 onward).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_assessment_scan_phase.py tests/test_scan_result.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/assessment.py tests/test_assessment_scan_phase.py
git commit -m "feat(scan): S5's merge runs in _scan; ScanResult carries candidates (E-46)"
```

---

### Task 7: The operator summary (spec §8)

**Files:**
- Create: `src/sdlc/assessment/scan/summary.py`
- Modify: `src/sdlc/cli.py:282-299` (parser), `:493-499` (`assess show`)
- Test: `tests/test_scan_summary.py` (create)

**Interfaces:**
- Consumes: `ScanResult`, `CANDIDATE_BAND` (Task 4).
- Produces: `render_scan_summary(scan: ScanResult) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_summary.py`:

```python
"""Spec section 8. The last line is the one that matters: it is how an
operator sees what the assessment did NOT measure -- FR-915 made visible at
the surface rather than only in the artifact."""

from __future__ import annotations

from sdlc.assessment.scan.models import (
    C_PACKAGES,
    CATEGORIES,
    Confidence,
    CandidateMember,
    MemberKind,
    SCAN_ORDER,
    ScanCandidate,
    ScanResult,
    ScanSignalId,
    ScanSignalResult,
    SignalSource,
    family_of,
)
from sdlc.assessment.scan.summary import render_scan_summary
from sdlc.measurement import Measurement


def _row(sid: ScanSignalId, measured: bool = True) -> ScanSignalResult:
    m = (
        Measurement.measured(1.0)
        if measured
        else Measurement.not_collected(f"{sid.value} not implemented (plan 3)")
    )
    source = SignalSource.INHERITED if sid is ScanSignalId.SS2 else SignalSource.COMPUTED
    producer = None
    if source is SignalSource.INHERITED:
        from sdlc.assessment.scan.models import InheritedProducer

        producer = InheritedProducer(producer="triage:dependencies", version=1)
    return ScanSignalResult(
        signal=sid,
        family=family_of(sid),
        version=1,
        source=source,
        collected=m,
        categories={k: m for k in CATEGORIES[sid]},
        producer=producer,
    )


def _result(candidates: list[ScanCandidate]) -> ScanResult:
    measured = {ScanSignalId.S1, ScanSignalId.S3, ScanSignalId.S5, ScanSignalId.SS2}
    return ScanResult(signals=[_row(s, s in measured) for s in SCAN_ORDER], candidates=candidates)


def _candidate(cid: str, confidence: Confidence, sources: list[str]):
    return ScanCandidate(
        candidate_id=cid,
        name=cid.lower(),
        sources=sources,
        confidence=confidence,
        members=[CandidateMember(kind=MemberKind.PACKAGE_PATH, value="src/x")],
    )


def test_candidates_are_counted_by_confidence():
    out = render_scan_summary(
        _result(
            [
                _candidate("C-01", Confidence.MEDIUM, ["S1-a", "S3-a"]),
                _candidate("C-02", Confidence.LOW, ["S1-b"]),
            ]
        )
    )
    assert "high 0" in out
    assert "medium 1" in out
    assert "low 1" in out


def test_not_collected_categories_are_listed_with_their_reasons():
    out = render_scan_summary(_result([]))
    assert "not collected" in out.lower()
    assert "plan 3" in out  # the reason, carried verbatim
    assert "schema_clusters" in out  # S2's category key


def test_the_candidate_band_is_advisory_and_says_so():
    """D11: never a gate. The word 'advisory' is the contract with the
    operator, and with E-51, which is where a binding version would live."""
    out = render_scan_summary(_result([_candidate("C-01", Confidence.LOW, ["S1-a"])]))
    assert "advisory" in out.lower()
    assert "15" in out and "25" in out


def test_a_full_band_draws_no_advisory_line():
    cands = [_candidate(f"C-{i:02d}", Confidence.LOW, [f"S1-{i}"]) for i in range(1, 17)]
    out = render_scan_summary(_result(cands))
    assert "advisory" not in out.lower()


def test_an_inherited_row_names_its_producer():
    """D2: an inherited row cites, and the operator should see the citation."""
    out = render_scan_summary(_result([]))
    assert "triage:dependencies" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_scan_summary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.assessment.scan.summary'`.

- [ ] **Step 3: Write the summary renderer**

Create `src/sdlc/assessment/scan/summary.py`:

```python
"""The scan phase's operator surface (spec section 8).

`sdlc assess` adds no verb; it gains counts. The not-collected list is the
line that matters: it is how an operator sees what the assessment did NOT
measure, which is FR-915's claim made visible at the surface rather than only
in the artifact.

Pure, and deliberately not a method on ScanResult: rendering is a surface
concern and the artifact is a contract shared with E-52's bundle.
"""

from __future__ import annotations

from ...measurement import CollectionState
from .merge import CANDIDATE_BAND
from .models import Confidence, ScanResult, SignalFamily


def render_scan_summary(scan: ScanResult) -> str:
    lines: list[str] = ["scan:"]

    counts = {c: sum(1 for cand in scan.candidates if cand.confidence is c) for c in Confidence}
    lines.append(
        f"  candidates: {len(scan.candidates)} "
        f"(high {counts[Confidence.HIGH]}, "
        f"medium {counts[Confidence.MEDIUM]}, "
        f"low {counts[Confidence.LOW]})"
    )

    low, high = CANDIDATE_BAND
    if scan.candidates and not low <= len(scan.candidates) <= high:
        # ADVISORY, never a gate (D11). BrownKit hard-gates here; its band
        # comes from enterprise Java monoliths, and a 40-file Next.js
        # application legitimately has four capabilities. A binding version
        # belongs in E-51's CheckResults.
        lines.append(
            f"  advisory: {len(scan.candidates)} candidates is outside "
            f"BrownKit's {low}-{high} band. Not a gate -- small repositories "
            f"legitimately have few capabilities (D11)."
        )

    for family in SignalFamily:
        rows = [r for r in scan.signals if r.family is family]
        measured = sum(1 for r in rows if r.collected.state is CollectionState.MEASURED)
        lines.append(f"  {family.value}: {measured}/{len(rows)} signals collected")

    inherited = [r for r in scan.signals if r.producer is not None]
    if inherited:
        lines.append("  inherited (cited, never copied):")
        for row in inherited:
            lines.append(
                f"    {row.signal.value} <- {row.producer.producer} "
                f"v{row.producer.version} "
                f"({len(row.producer.finding_ids)} finding(s))"
            )

    gaps = [
        (r.signal.value, key, m)
        for r in scan.signals
        for key, m in sorted(r.categories.items())
        if m.state is not CollectionState.MEASURED
    ]
    if gaps:
        lines.append(f"  not collected ({len(gaps)} categories):")
        for signal, key, m in gaps:
            lines.append(f"    {signal}.{key}: {m.reason}")
    else:
        lines.append("  not collected: none")

    return "\n".join(lines)
```

- [ ] **Step 4: Wire it into `assess show`**

In `src/sdlc/cli.py`, add the flag to the `assess show` subparser (after
`ash = asrsub.add_parser("show")` / `ash.add_argument("--id", required=True)`
— match the surrounding names in that block):

```python
ash.add_argument(
    "--json",
    action="store_true",
    dest="as_json",
    help="print the raw Assessment JSON instead of the summary",
)
```

Replace the `assess show` handler:

```python
if args.cmd == "assess" and args.assess_cmd == "show":
    handle = client.get_workflow_handle(args.id)
    # Query by METHOD, not by name -- see the triage show handler.
    report = await handle.query(AssessmentWorkflow.assessment)
    if report is None:
        print("no assessment yet")
        return
    if args.as_json:
        print(report.model_dump_json(indent=2))
        return
    print(f"{report.terminal_status}  ({report.commit_sha[:12]})")
    print(f"admitted: {report.admitted} -- {report.admission_reason}")
    for phase in report.phases:
        state = phase.collected.state.value
        detail = f" -- {phase.collected.reason}" if phase.collected.reason else ""
        print(f"  {phase.phase.value}: {state}{detail}")
    if report.scan is not None:
        from .assessment.scan.summary import render_scan_summary

        print(render_scan_summary(report.scan))
    return
```

- [ ] **Step 5: Add the parser test**

Append to `tests/test_assessment_cli_wiring.py`:

```python
def test_parser_accepts_assess_show_json():
    """The raw dump stays reachable; the summary is the new default."""
    args = build_parser().parse_args(["assess", "show", "--id", "assess-r-x", "--json"])
    assert args.as_json is True
    assert build_parser().parse_args(["assess", "show", "--id", "assess-r-x"]).as_json is False
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_scan_summary.py tests/test_assessment_cli_wiring.py -v`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/assessment/scan/summary.py src/sdlc/cli.py tests/test_scan_summary.py tests/test_assessment_cli_wiring.py
git commit -m "feat(scan): operator summary -- candidates by confidence and what was not collected (E-46)"
```

---

### Task 8: The determinism property and the e2e refit

**Files:**
- Test: `tests/test_scan_determinism.py` (create)
- Modify: `tests/test_assessment_workflow_e2e.py:257-261`

**Interfaces:**
- Consumes: everything from Tasks 2, 3, 4, 6.

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_determinism.py`:

```python
"""NFR-10's deterministic half: the same tree yields a byte-identical
ScanResult. Asserted on the SERIALIZED artifact, as E-47a asserts for
identity allocation -- an equal-comparing model with a differently-ordered
list is not the same artifact to a memo or a bundle."""

from __future__ import annotations

import random

from sdlc.assessment.scan.merge import merge
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.signals import entrypoints, packages
from sdlc.measurement import Measurement

TREE = [
    "pyproject.toml",
    "src/payments/__init__.py",
    "src/payments/api.py",
    "src/orders/api.py",
    "src/utils/strings.py",
]
BLOBS = {
    "src/payments/api.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/api/payments')\n"
        "def create():\n    ...\n"
    ),
    "src/orders/api.py": (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/api/orders')\n"
        "def list_orders():\n    ...\n"
    ),
    "src/utils/strings.py": "def slug(s):\n    return s\n",
    "src/payments/__init__.py": "",
}
LOC = {p: t.count("\n") + 1 for p, t in BLOBS.items()}
MEASURED = {ScanSignalId.S1: Measurement.measured(1.0), ScanSignalId.S3: Measurement.measured(1.0)}


def test_s1_is_byte_identical_across_input_orderings():
    reference = packages.evaluate(TREE, LOC).model_dump_json()
    for seed in range(5):
        shuffled = list(TREE)
        random.Random(seed).shuffle(shuffled)
        assert packages.evaluate(shuffled, LOC).model_dump_json() == reference


def test_s3_is_byte_identical_across_input_orderings():
    reference = entrypoints.evaluate(BLOBS).model_dump_json()
    for seed in range(5):
        items = list(BLOBS.items())
        random.Random(seed).shuffle(items)
        assert entrypoints.evaluate(dict(items)).model_dump_json() == reference


def test_the_whole_capability_chain_is_byte_identical():
    """S1 -> S3 -> S5 end to end, which is what the memo caches and what
    NFR-10 will be measured against."""

    def run(order_seed: int) -> str:
        paths = list(TREE)
        items = list(BLOBS.items())
        random.Random(order_seed).shuffle(paths)
        random.Random(order_seed).shuffle(items)
        s1 = packages.evaluate(paths, LOC)
        s3 = entrypoints.evaluate(dict(items))
        return merge(s1.sources + s3.sources, MEASURED).model_dump_json()

    assert run(1) == run(2) == run(3)


def test_merging_the_same_sources_twice_yields_one_artifact():
    s1 = packages.evaluate(TREE, LOC)
    s3 = entrypoints.evaluate(BLOBS)
    a = merge(s1.sources + s3.sources, MEASURED)
    b = merge(s3.sources + s1.sources, MEASURED)
    assert a.model_dump_json() == b.model_dump_json()
```

- [ ] **Step 2: Run the test to verify it passes or fails honestly**

Run: `pytest tests/test_scan_determinism.py -v`
Expected: PASS if Tasks 2–4 sorted correctly. A FAIL here is a real
determinism bug in those modules — fix the module, never the test.

- [ ] **Step 3: Refit the e2e's S5 assertion**

In `tests/test_assessment_workflow_e2e.py`, replace the S5 block (currently
lines 257–261, asserting `"plan 2" in s5.collected.reason`):

```python
    # S5's merge is real as of plan 2. This worker points the activities at a
    # repo_dir that does not exist, so S1-S4 degrade and S5 correctly reports
    # a GAP naming them -- not a measured zero, and not a plan.
    s5 = next(s for s in result.scan.signals if s.signal is ScanSignalId.S5)
    assert s5.collected.state is CollectionState.NOT_COLLECTED
    assert "plan" not in s5.collected.reason.lower()
    assert "S1" in s5.collected.reason
    assert result.scan.candidates == []
```

Ensure `CollectionState` is imported in that module (add to the
`from sdlc.measurement import ...` line if absent).

- [ ] **Step 4: Run the full suite**

Run: `pytest -q`
Expected: PASS. Then the temporal e2e:

Run: `pytest -m temporal tests/test_assessment_workflow_e2e.py -v`
Expected: PASS — `test_scan_phase_flips_terminal_status_to_partial` still
reports `assessed:partial` (nine signals are still stubs), now with S5
reporting a real gap.

- [ ] **Step 5: Commit**

```bash
git add tests/test_scan_determinism.py tests/test_assessment_workflow_e2e.py
git commit -m "test(scan): byte-identical output across input orderings (NFR-10)"
```

---

### Task 9: Record what landed

**Files:**
- Modify: `ROADMAP.md` (§11 E-46 entry, FR-912, FR-911, §2 header line)
- Modify: `docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md` (status row, §9)

- [ ] **Step 1: Update the spec's status and staging**

In the spec's header table, change:

```
| Status | Design approved 2026-08-12; plans 1 and 2 of 3 implemented |
```

Append to §9's table, below it:

```markdown
Plan 2 added two decisions the design left open, both recorded in
`docs/superpowers/plans/2026-08-13-scan-phase-signals-plan-2.md`:
**P2-D1** — S3 fails closed on an unfingerprinted framework, because
`_unmeasured_carries_no_payload` makes "partially extracted" unrepresentable
and D5's own reasoning prefers an absent Contract tier to a partial one.
**P2-D2** — the generic/layer name tables live in `naming.py`, so S1 declares
it as a `rule_module`; without that, editing a layer word would change S1's
output while its memo key stood still.
```

- [ ] **Step 2: Update ROADMAP.md**

Replace the E-46 entry (§11) with:

```markdown
- [ ] ⚠️ **E-46 — scan phase** → FR-912. S1–S5 capability signals, SS1–SS4
  security, QS1–QS4 QA. Cross-source confidence: three or more independent
  sources = high, two = medium, one = low — never the depth of one source. Memo
  key `(repository tree hash, signal version)` per FR-103, so re-assessing an
  unchanged repo is a cache hit and editing one signal's logic invalidates
  exactly that signal. **Plan 1 landed 2026-08-12:** contracts, `SCAN_SIGNALS`,
  the memoized activity seam, and the five inherited halves
  (`src/sdlc/assessment/scan/`). **Plan 2 landed 2026-08-13:** S1, S3, S5 and
  the shared `naming.py` rules — the capability core, so `ScanResult.candidates`
  carries real merged candidates and the memo has its first production caller
  (every plan-1 stub was refused by `store`'s not-MEASURED rule). Nine bodies
  remain stubs naming plan 3. Two plan-level decisions: **S3 fails closed** on a
  recognized-but-unfingerprinted framework (P2-D1) — `_unmeasured_carries_no_payload`
  makes a partial Contract tier unrepresentable, and D5 prefers absent to
  partial; and the **name tables live in `naming.py`**, so S1 declares it as a
  `rule_module` (P2-D2) or editing a layer word would move S1's output without
  moving its key.
```

Replace the FR-912 line (§2) with:

```markdown
- [ ] ⚠️ **FR-912** deterministic scan memoized on `(tree hash, signal version)`; cross-source confidence (E-46). **Plans 1–2 of 3 landed (2026-08-12, 2026-08-13).** The memo key is `(tree_hash, signal_version, rules_sha)` — `rules_sha` beyond the specified two terms, hashed transitively over shared rule modules and consumed signals, because a hand-maintained version int misses a real input (spec D10). All thirteen signal rows report; S1/S3/S5 compute, SS2 inherits, and nine bodies are still stubs naming plan 3. Cross-source confidence is live and derived (D8), but it cannot reach HIGH until plan 3 lands S2 and S4: two of S5's four sources do not yet produce.
```

In the FR-911 line, change "the stub count dropped from six to five" note to
add: `**2026-08-13 (E-46 plan 2):** the scan phase's own stub count drops from
eleven signal bodies to nine.`

Update the header table's "Last verified" line to lead with:
`2026-08-13 (E-46 plan 2 against `src/sdlc/assessment/scan/` + unit suite green);`
followed by the existing text.

- [ ] **Step 3: Verify the docs claim only what the code does**

Run: `pytest -q`
Expected: PASS. Confirm the counts written above match reality:

```bash
python -c "from sdlc.assessment.activities import BUILT, OWED_BY; print('built', sorted(s.value for s in BUILT)); print('owed', len(OWED_BY))"
```
Expected: `built ['S1', 'S3']` and `owed 9`.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md docs/superpowers/specs/2026-08-12-scan-phase-capability-security-qa-signals-design.md
git commit -m "docs: record E-46 plan 2 -- the capability core lands, nine bodies pending"
```

---

## Self-Review

**Spec coverage.** Plan 2's slice per §9 is "S1, S3, S5 + `naming.py`", plus §8's
CLI surface (assigned to this plan by decision). Mapping:

| Spec item | Task |
|---|---|
| D4 — pattern fingerprints in signal modules, no new adapter | 3 (`FRAMEWORKS`) |
| D5 — unmatched framework reports `not_collected`, never zero | 3 (P2-D1) |
| D8 — confidence derived from distinct source signals | 4 (`confidence_from`) |
| D9 — merge on normalized name; overlapping-but-differently-named do not collapse | 1, 4 |
| D9 — S3 groups by business operation, not technical type | 1 (`head_token`), 3 |
| D10 — `rules_sha` covers shared rule modules | 1 (S1 declares `naming`) |
| D11 — 15–25 band is advisory, never a gate | 4 (`CANDIDATE_BAND`), 7 |
| §5 step 5 — S5's merge in workflow code | 6 |
| §6 — determinism, blob size bound, never raise | 2, 3, 5, 8 |
| §7 — byte-identical property, order independence | 8 |
| §8 — CLI counts + `not_collected` list | 7 |
| §11 — roadmap consequences | 9 |

Not in this plan, by the staging table: S2, S4, SS4, QS3 bodies and the SS1 /
SS3 / QS1 / QS2 / QS4 extension halves (plan 3), plus the five payload types
plan 3 must add to `SignalOutput` (recorded in `scan/models.py`'s NOTE).

**Known consequence, stated rather than hidden.** S5 consumes S1–S4 and only
two of the four produce after this plan, so **no candidate can reach `HIGH`
until plan 3** — `confidence_from` needs three distinct signals. The mechanism
is complete and tested (Task 4 asserts the HIGH path with synthetic S4
candidates); the live artifact just cannot exercise it yet. This is expected,
not a defect, and it is why Task 9's FR-912 line says so explicitly.

**Type consistency.** `evaluate` returns `SignalOutput` in both signal modules
(matching `unbuilt_signal`'s return type, so the activities are drop-in);
`merge` returns `MergeOutput`, consumed only by Task 6's `_merged_row` and
Task 4's tests. `normalize` is the single name used across Tasks 1–4 (never
`normalise` or `canonicalize`). Category constants are imported from
`scan/models.py`, never re-declared. Relative import depths differ by
directory and are written out per file: `signals/*.py` reaches
`measurement.py` with four dots, `scan/*.py` with three.

**Three corrections made during this review, recorded because a reader of an
earlier draft would otherwise inherit them:**

1. **`head_token` was missing and D9's worked example could not have passed.**
   Suffix-stripping alone takes `PaymentSettlementJob` to
   `paymentsettlement`, which shares no merge key with `PaymentController`'s
   `payment` — so BrownKit's "one candidate, not three" rule would have
   produced three. Added to `naming.py` in Task 1 and used by S3's
   `_business_name`, which also strengthens P2-D2: `naming.py` is now
   genuinely shared by all three signals rather than by two.
2. **S1's local ids carry the whole path** (`S1-src--payments`, not
   `S1-payments`), because two directories can share a basename
   (`api/models`, `web/models`) and colliding ids would silently merge
   unrelated packages. Task 2's tests were written against the leaf form and
   are corrected.
3. **The memo cache env var is `SDLC_MEMOIZATION_CACHE_ROOT`**, not the
   `SDLC_CACHE_DIR` an earlier draft of Task 5 monkeypatched — verified
   against `memoization/cache.py:14`. A wrong name would have written the
   test's cache into the developer's real store and made
   `test_a_failed_signal_is_not_cached` pass for the wrong reason.
