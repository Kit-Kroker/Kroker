# C3 required-checks manifest + C4 pairing audit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the deterministic quality gate fail closed on a required check it never received (C3), and ship a written audit mapping every advisory LLM pass to the deterministic mechanism behind it (C4).

**Architecture:** C3 adds one module-level manifest constant to `src/sdlc/gate.py` and two pure helpers inside `evaluate_quality_gate` — one that re-asserts `ABSOLUTE_FLOOR` on the input list, one that synthesizes a failing `MISCONFIGURED` check for every manifest name the caller did not hand in. No signature changes, no new enum member, no config surface. C4 writes a dated report under `docs/reports/` and updates the candidate register; it ships no code.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest (fast unit tier — no marker), ruff, mypy, pre-commit.

**Spec:** [`docs/superpowers/specs/2026-09-06-c3-required-checks-c4-pairing-audit-design.md`](../specs/2026-09-06-c3-required-checks-c4-pairing-audit-design.md) — approved, committed at `844b8a4`. Read it before starting; every design decision below argues from it and its decisions are closed.

**Branch:** `c3-required-checks-c4-pairing-audit`, off `main` at `03e0663`.

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include this section.

- **File size ceiling:** 1000 physical lines per file. No soft target, no waiver. `scripts/check_file_size.py` is the authority and runs as a pre-commit hook. (Current sizes: `gate.py` 93, `merge/step.py` 444, `merge.md` 28 — none is near the ceiling.)
- **The artifact boundary:** "Whoever changes a stage's behaviour must update its clauses in the same diff. A clause without code and code without a clause are both defects." C3's code lives in `gate.py`, but the behaviour is the merge stage's — Task 1's doc obligations are not optional follow-up.
- **No new verdict enum member; no `PipelineConfig` surface.** `MISCONFIGURED` is detail text. `CheckClass` stays two-valued. (Spec §2.4d, §2.6.)
- **Synthesize through `build_check`, never by constructing `CheckResult` directly** (spec §2.4a).
- **Synthesized checks MUST appear in `GateReport.checks`** (spec §2.4b) — `merge/step.py:321-325` and `:353-357` derive the absolute/advisory split by iterating that list.
- **Copy, then append. The caller's list is never mutated** (spec §2.4c).
- **The demotion fix is a pre-loop normalization of the input list, not a branch inside the loop** (spec §2.5).
- **C4's diff is words only.** "Any change under `src/`, `tests/`, `agents/`, prompts, or config in C4's diff is a defect" (spec §3.7). See Task 2's preamble for the one planned refinement to the file enumeration.
- **Two commits, in order:** C3's code diff, then C4's docs diff (spec §4). Never `git commit --no-verify`; pre-commit hooks (ruff, ruff-format, mypy, file-size ratchet) must pass on their own.
- **Do not touch `ARCHITECTURE.md` or `ROADMAP.md`** in either task. They describe `main`; this work is in flight until the branch integrates.
- **Do not regenerate `docs/schemas/`.** C3 changes no Pydantic model and no roadmap input, so nothing there goes stale.
- **Two explicit non-goals (spec §2.6), so nobody implements them opportunistically.** *Vacuous-present checks:* `merge/step.py:303-313` emits `coverage` unconditionally and passes it when coverage is unmeasured. C3 polices presence, not validity — leave that asymmetry alone. *Duplicate names:* duplicates cannot manufacture a false green (only absence can), so add no de-duplication; a name-keyed reduction would be a behaviour change, not a cleanup.

## Dispositions carried in from the spec's open questions

The spec's §5 left three questions to the human orchestrator. All three are answered; executors do not re-decide them.

1. The adversary-lens correction (spec §3.4 row 3) **stands as written**. The originating brief called the adversary "signal only"; `code/step.py:812` shows otherwise, and the audit is written on the corrected reading.
2. `workflows/feature.py:340` (the second handoff-extractor site) is **cited as found, not chased**. Record it; do not investigate whether it is live.
3. The stale `foundation.md:81` sentence is **fixed inside Task 1's diff**, and Task 1's commit message names the fix as deliberate.

## Finish line

Stop after Task 2's commit. **Do not open a pull request.** Integration is a fast-forward of `main` by the orchestrator, not an executor action.

---

## Task 1: C3 — fail closed on an absent required check

**Files:**
- Modify: `src/sdlc/gate.py` (module docstring; new constant and two helpers after `ABSOLUTE_FLOOR:60-68`; `evaluate_quality_gate:77-93`)
- Modify: `tests/conftest.py` (add the `required_checks` fixture)
- Create: `tests/test_required_checks_manifest.py`
- Modify: `tests/test_quality_gate.py:25-32,45-52`
- Modify: `tests/test_security_collection_gate.py:52-54`
- Modify: `tests/merge/test_merge_gate_wiring.py:79-86`
- Modify: `src/sdlc/stages/merge/merge.md` (new MERGE-1.6; cross-refs in MERGE-1.2/1.3; one "Failure modes" bullet)
- Modify: `src/sdlc/stages/merge/AGENTS.md` (Invariants list)
- Modify: `docs/reference/foundation.md:73-86`
- Modify: `docs/reference/presentation-pipeline-temporal.md:179-201`
- Modify: `docs/reports/external-ideas-2026-09.md:51` (the C3 row only — Task 2 owns the C4 row and the legend)

**Interfaces:**
- Consumes: nothing from earlier tasks. Existing public names in `src/sdlc/gate.py`: `CheckClass` (`StrEnum`, members `ABSOLUTE`/`ADVISORY`), `CheckResult(name: str, passed: bool, classification: CheckClass, detail: str = "")`, `GateOverride(check: str, approved_by: str, reason: str)`, `GateReport(passed: bool, blocking: list[str], overridden: list[str], checks: list[CheckResult])`, `ABSOLUTE_FLOOR: frozenset[str]`, `build_check(name: str, passed: bool, requested: CheckClass, detail: str = "") -> CheckResult`, `evaluate_quality_gate(checks: list[CheckResult], overrides: list[GateOverride] | None = None) -> GateReport`.
- Produces: `MERGE_REQUIRED_CHECKS: Final[Mapping[str, CheckClass]]` in `src/sdlc/gate.py` — the seven-name manifest, importable as `from sdlc.gate import MERGE_REQUIRED_CHECKS`. Two private helpers `_normalized(checks: list[CheckResult]) -> list[CheckResult]` and `_synthesized(present: set[str]) -> list[CheckResult]`. A pytest fixture `required_checks` in `tests/conftest.py` whose value is a builder `(**passed: bool) -> list[CheckResult]`. Task 2 consumes none of these; it reads `gate.py` only to cite it.
- Exit path, if a second caller of `evaluate_quality_gate` ever appears (spec §2.7): the manifest promotes to a **required** field on `QualityGateInput` — never to a defaulted parameter, because a default is itself the fail-open mechanism C3 exists to kill. Not work for this task; recorded so nobody adds the parameter pre-emptively.

- [ ] **Step 1: Add the `required_checks` fixture to `tests/conftest.py`**

Append at the end of the file. The import is function-level deliberately (precedent: `tests/test_security_floor.py:130`), so conftest's module-level environment setup is untouched.

```python
@pytest.fixture
def required_checks():
    """Build the full MERGE_REQUIRED_CHECKS list, every check passing.

    `required_checks()` -> seven passing checks.
    `required_checks(coverage=False)` -> the same seven with `coverage`
    failing at its manifest classification.

    Returns a fresh list on every call, so no test shares a list object or
    depends on another test not mutating one. Driven by the manifest rather
    than a hardcoded seven, so these tests keep asserting mechanics if the
    manifest ever grows.
    """
    from sdlc.gate import MERGE_REQUIRED_CHECKS, CheckResult, build_check

    def _build(**passed: bool) -> list[CheckResult]:
        return [
            build_check(name, passed.get(name, True), klass)
            for name, klass in MERGE_REQUIRED_CHECKS.items()
        ]

    return _build
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_required_checks_manifest.py` with exactly this content:

```python
"""C3: the gate fails closed on a required check it was never handed.

`evaluate_quality_gate` used to judge only the checks it received, so a
required check that was absent from the list was invisible and the run went
quietly green. These tests pin the manifest, the synthesis, the echo into
`GateReport.checks`, and the floor re-assertion that close that hole.
"""

import ast
import pathlib

from sdlc.gate import (
    ABSOLUTE_FLOOR,
    MERGE_REQUIRED_CHECKS,
    CheckClass,
    CheckResult,
    GateOverride,
    build_check,
    evaluate_quality_gate,
)

MERGE_STEP = pathlib.Path("src/sdlc/stages/merge/step.py")


def test_missing_absolute_check_blocks_and_ignores_its_override(required_checks):
    checks = [c for c in required_checks() if c.name != "lint_clean"]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="lint_clean", approved_by="alice", reason="ship it")],
    )
    assert report.passed is False
    assert "lint_clean" in report.blocking
    assert report.overridden == []


def test_missing_advisory_check_blocks_without_an_override(required_checks):
    checks = [c for c in required_checks() if c.name != "coverage"]
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "coverage" in report.blocking


def test_missing_advisory_check_is_waivable_by_an_audited_override(required_checks):
    checks = [c for c in required_checks() if c.name != "coverage"]
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage", approved_by="alice", reason="legacy gap")],
    )
    assert report.passed is True
    assert report.overridden == ["coverage"]
    assert report.blocking == []


def test_a_typo_in_a_required_name_blocks_instead_of_passing_quietly(required_checks):
    """The typo'd check is inert; the real name synthesizes and blocks. This is
    the sharpest demonstration of what C3 buys."""
    checks = [c for c in required_checks() if c.name != "security_no_critical"]
    checks.append(build_check("security_no_crtical", True, CheckClass.ABSOLUTE))
    report = evaluate_quality_gate(checks)
    assert report.passed is False
    assert "security_no_critical" in report.blocking


def test_an_empty_checks_list_synthesizes_every_required_name():
    report = evaluate_quality_gate([])
    assert report.passed is False
    assert sorted(report.blocking) == sorted(MERGE_REQUIRED_CHECKS)


def test_synthesized_checks_are_echoed_in_the_report(required_checks):
    """merge/step.py:321-325 and :353-357 split absolute from advisory by
    iterating report.checks. A synthesized name that never lands there
    misroutes into the human escalation path."""
    checks = [c for c in required_checks() if c.name != "security_scan_collected"]
    report = evaluate_quality_gate(checks)
    echoed = [c for c in report.checks if c.name == "security_scan_collected"]
    assert len(echoed) == 1
    assert echoed[0].passed is False
    assert echoed[0].classification is CheckClass.ABSOLUTE
    assert "MISCONFIGURED" in echoed[0].detail


def test_evaluating_twice_neither_mutates_nor_duplicates(required_checks):
    """merge/step.py evaluates once clean (:316-318) and again with overrides
    (:378-380), passing the same list object both times."""
    checks = [c for c in required_checks() if c.name != "coverage"]
    before = [c.name for c in checks]
    first = evaluate_quality_gate(checks)
    # The caller's list is never mutated: nothing appended, nothing replaced.
    # (Identity of the elements is deliberately not asserted — _normalized
    # returns new objects for floor names.)
    assert [c.name for c in checks] == before
    second = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage", approved_by="alice", reason="waived")],
    )
    assert [c.name for c in second.checks].count("coverage") == 1
    assert first.blocking == ["coverage"]
    assert second.passed is True


def test_a_directly_constructed_floor_check_cannot_be_demoted(required_checks):
    """build_check forces the floor at construction; a raw CheckResult skips
    it. The re-assertion must reach the echoed list too, or merge/step.py
    routes a demoted absolute into the human-waivable advisory split."""
    checks = [c for c in required_checks() if c.name != "security_no_critical"]
    checks.append(
        CheckResult(
            name="security_no_critical",
            passed=False,
            classification=CheckClass.ADVISORY,
            detail="1 critical finding",
        )
    )
    report = evaluate_quality_gate(
        checks,
        overrides=[
            GateOverride(check="security_no_critical", approved_by="alice", reason="yolo")
        ],
    )
    assert report.passed is False
    assert "security_no_critical" in report.blocking
    assert report.overridden == []
    echoed = next(c for c in report.checks if c.name == "security_no_critical")
    assert echoed.classification is CheckClass.ABSOLUTE


def test_every_floor_name_is_required_and_absolute():
    for name in ABSOLUTE_FLOOR:
        assert name in MERGE_REQUIRED_CHECKS
        assert MERGE_REQUIRED_CHECKS[name] is CheckClass.ABSOLUTE


def test_the_manifest_pins_the_checks_the_merge_step_builds():
    """Source needle: the manifest is the merge gate's production contract.

    Deliberately does NOT use the required_checks fixture — the fixture is
    built from the manifest, so it cannot be the census of the manifest.
    """
    tree = ast.parse(MERGE_STEP.read_text(encoding="utf-8"))
    built = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "build_check"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }
    assert built == set(MERGE_REQUIRED_CHECKS)
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `pytest tests/test_required_checks_manifest.py -v`
Expected: collection error — `ImportError: cannot import name 'MERGE_REQUIRED_CHECKS' from 'sdlc.gate'`. Every test in the file errors. This is the correct red.

- [ ] **Step 4: Add the manifest constant to `src/sdlc/gate.py`**

Add three imports to the existing import block. `ruff`'s isort rule is enabled (`pyproject.toml:60` selects `I`), so the order matters: the block must end up **exactly** as below, or Step 10 fails on I001 with no obvious cause.

```python
from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final
```

Add only those three lines. Do not reorder or reformat the imports already present, and do not touch the `from __future__` or `from pydantic` lines — an I001 failure here is fixed by placing the new imports correctly, never by churning the existing block.

Then insert immediately after the `ABSOLUTE_FLOOR` definition (currently ending at line 68) and before `def build_check`:

```python
# The checks the merge gate must see. Absence is as severe as failure: a name
# missing from the evaluated input is synthesized as a failing check at the
# classification it carries here. Edits deserve ABSOLUTE_FLOOR-grade scrutiny —
# after C3, deleting an entry is the only way to make a dropped check quiet
# again, so the pressure point moved from the producer to this constant.
MERGE_REQUIRED_CHECKS: Final[Mapping[str, CheckClass]] = MappingProxyType(
    {
        "build_integration_green": CheckClass.ABSOLUTE,
        "lint_clean": CheckClass.ABSOLUTE,
        "security_scan_collected": CheckClass.ABSOLUTE,
        "security_no_critical": CheckClass.ABSOLUTE,
        "review_severity": CheckClass.ADVISORY,
        "traceability": CheckClass.ADVISORY,
        "coverage": CheckClass.ADVISORY,
    }
)
```

- [ ] **Step 5: Add the two helpers and rewrite `evaluate_quality_gate`**

Insert both helpers after `build_check` and before `evaluate_quality_gate`:

```python
def _normalized(checks: list[CheckResult]) -> list[CheckResult]:
    """Re-assert the floor on checks that were handed in, not built.

    `build_check` forces ABSOLUTE_FLOOR names to ABSOLUTE at construction, but
    `CheckResult` is a plain model: a caller can construct one directly, demote
    a floor check to ADVISORY, and waive it with a single override. Rebuilding
    here — before the loop, not inside it — means the loop, the echoed
    `GateReport.checks`, and the merge step's absolute/advisory split all read
    the same classification.
    """
    return [
        build_check(c.name, c.passed, c.classification, c.detail)
        if c.name in ABSOLUTE_FLOOR
        else c
        for c in checks
    ]


def _synthesized(present: set[str]) -> list[CheckResult]:
    """A failing check for every required name the caller did not hand in.

    FR-915 ruled once that "the scan could not run" is as absolute as "the scan
    found a critical"; this generalizes that ruling from one check to the
    manifest. Built through `build_check` so a manifest entry that named a floor
    check ADVISORY would still come back ABSOLUTE.
    """
    return [
        build_check(
            name,
            False,
            MERGE_REQUIRED_CHECKS[name],
            detail=f"MISCONFIGURED: required check {name!r} absent from gate input",
        )
        for name in MERGE_REQUIRED_CHECKS
        if name not in present
    ]
```

Then replace the body of `evaluate_quality_gate` (currently lines 81-93) so it evaluates and echoes the augmented list. The signature does not change:

```python
def evaluate_quality_gate(
    checks: list[CheckResult],
    overrides: list[GateOverride] | None = None,
) -> GateReport:
    normalized = _normalized(checks)
    # Copy-then-append: the caller's list is never mutated. merge/step.py hands
    # the same list object to both of its evaluations (:316-318, :378-380).
    evaluated = normalized + _synthesized({c.name for c in normalized})
    override_names = {o.check for o in (overrides or [])}
    blocking: list[str] = []
    overridden: list[str] = []
    for c in evaluated:
        if c.passed:
            continue
        if c.classification is CheckClass.ABSOLUTE:
            blocking.append(c.name)  # absolute: override ignored
        elif c.name in override_names:
            overridden.append(c.name)  # advisory: audited waiver
        else:
            blocking.append(c.name)
    return GateReport(
        passed=not blocking, blocking=blocking, overridden=overridden, checks=evaluated
    )
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `pytest tests/test_required_checks_manifest.py -v`
Expected: PASS, 10 passed.

- [ ] **Step 7: Run the full fast tier to surface the planned migrations**

Run: `pytest -q`
Expected: exactly 4 failures, all of them tests that assert a clean or exact outcome from a partial list (spec §2.10):
- `tests/test_quality_gate.py::test_advisory_failure_passes_with_override`
- `tests/test_quality_gate.py::test_all_pass_is_clean`
- `tests/test_security_collection_gate.py::test_measured_clean_scan_passes_both`
- `tests/merge/test_merge_gate_wiring.py::test_advisory_failure_passes_with_audited_override`

If any *other* test fails, stop — the census in spec §2.10 is wrong and the discrepancy needs reporting before proceeding.

- [ ] **Step 8: Migrate the four tests**

In `tests/test_quality_gate.py`, replace `test_advisory_failure_passes_with_override` and `test_all_pass_is_clean` with:

```python
def test_advisory_failure_passes_with_override(required_checks):
    checks = required_checks(coverage=False)
    rep = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage", approved_by="alice", reason="legacy gap")],
    )
    assert rep.passed is True
    assert rep.overridden == ["coverage"]
    assert rep.blocking == []


def test_all_pass_is_clean(required_checks):
    rep = evaluate_quality_gate(required_checks())
    assert rep.passed is True
    assert rep.blocking == []
```

In `tests/test_security_collection_gate.py`, replace `test_measured_clean_scan_passes_both` with:

```python
def test_measured_clean_scan_passes_both(required_checks):
    report = SecurityReport(critical=0, state=CollectionState.MEASURED)
    others = [
        c
        for c in required_checks()
        if c.name not in {"security_scan_collected", "security_no_critical"}
    ]
    assert evaluate_quality_gate(others + _checks(report)).blocking == []
```

In `tests/merge/test_merge_gate_wiring.py`, replace `test_advisory_failure_passes_with_audited_override` with the version below. Note it drops the name `coverage_gate`, which no production code ever built — a fictional check name that had been sitting in the suite, and exactly the hazard `test_a_typo_in_a_required_name_blocks_instead_of_passing_quietly` now covers deliberately:

```python
def test_advisory_failure_passes_with_audited_override(required_checks):
    checks = required_checks(coverage=False)
    report = evaluate_quality_gate(
        checks,
        overrides=[GateOverride(check="coverage", approved_by="human", reason="accepted")],
    )
    assert report.passed
    assert "coverage" in report.overridden
```

- [ ] **Step 9: Run the full fast tier to verify green**

Run: `pytest -q`
Expected: PASS, 0 failures.

- [ ] **Step 10: Run lint, format and typecheck**

Run: `ruff check .` then `ruff format .` then `mypy` (the AGENTS.md-documented trio; `ruff format` in write mode, so a formatting delta is fixed here rather than puzzled over when pre-commit enforces it at Step 18).
Expected: `ruff check` clean, `ruff format` reporting files left unchanged or reformatting only files this task touched, `mypy` clean. `mypy` is scoped to `src/` by config (`pyproject.toml:75`); if it reports pre-existing errors elsewhere in `src/`, confirm none of them names `gate.py`.

- [ ] **Step 11: Update the merge stage contract — `src/sdlc/stages/merge/merge.md`**

Append this new clause after MERGE-1.5:

```markdown
### MERGE-1.6
The deterministic gate fails closed on a required check it never received. `MERGE_REQUIRED_CHECKS` (`src/sdlc/gate.py`) is the authoritative list of the checks the merge gate must see. Every manifest name absent from the evaluated input is synthesized as a **failing** `CheckResult` at its manifest classification, carrying `MISCONFIGURED: required check '<name>' absent from gate input` as its detail, and is echoed in `GateReport.checks`. An absent absolute check is an absolute failure, handled per MERGE-1.2; an absent advisory check is an advisory failure, handled — including its audited override path — per MERGE-1.3. Separately, a check whose name is in `ABSOLUTE_FLOOR` is re-asserted as ABSOLUTE on input, so a directly-constructed `CheckResult` cannot be demoted to advisory and waived by one override. [SC-5, FR-915]
```

Append one sentence to the end of MERGE-1.2:

```markdown
An absolute check that is *absent* from the gate input is an absolute failure by this same route — see MERGE-1.6.
```

Append one sentence to the end of MERGE-1.3:

```markdown
An advisory check that is *absent* from the gate input is an advisory failure by this same route, and reaches the human gate carrying its `MISCONFIGURED` detail — see MERGE-1.6.
```

Add one bullet to the "Failure modes" list:

```markdown
- **Missing required check**: a name in `MERGE_REQUIRED_CHECKS` that never reached the gate is synthesized as a failing `MISCONFIGURED` check at its manifest classification — terminal if absolute, human-waivable if advisory (MERGE-1.6).
```

- [ ] **Step 12: Update `src/sdlc/stages/merge/AGENTS.md`**

Replace the existing invariant line `- Absolute checks are non-overridable: on failure, the stage fails closed immediately.` with these two:

```markdown
- Absolute checks are non-overridable: on failure, the stage fails closed immediately. The floor is re-asserted on input inside `evaluate_quality_gate`, so a directly-constructed `CheckResult` cannot demote a floor check to advisory.
- A required check that never reaches the gate is a failing check, not a silent pass: `MERGE_REQUIRED_CHECKS` (`gate.py`) is the authoritative list, and absence synthesizes a failing `MISCONFIGURED` result at the manifest classification.
```

- [ ] **Step 13: Update the `gate.py` module docstring**

Append this paragraph to the existing module docstring, after the sentence ending "after this gate has already passed.":

```
Two properties make the gate fail closed on its own inputs. `MERGE_REQUIRED_CHECKS`
is the manifest of checks the merge gate must see: any name absent from the
evaluated list is synthesized as a failing MISCONFIGURED check at its manifest
classification, so a check that silently stopped being produced blocks instead of
passing quietly. And `ABSOLUTE_FLOOR` is re-asserted on input rather than only at
construction, so a directly-constructed CheckResult cannot demote a floor check
and waive it with a single override.
```

- [ ] **Step 14: Update `docs/reference/foundation.md`**

Two edits in the `sdlc/gate.py` section (currently lines 73-86).

First, fix the stale floor sentence. It currently reads `forces \`ABSOLUTE_FLOOR\` names (\`security_no_critical\`) to \`ABSOLUTE\``. This has been stale since FR-915 added the second name — the fix is deliberate, not drive-by, and Task 1's commit message says so. Replace the parenthetical so it reads:

```markdown
- **`build_check(name, passed, requested, detail="")`** forces
  `ABSOLUTE_FLOOR` names (`security_no_critical`, `security_scan_collected`) to
  `ABSOLUTE` even if a project marks them advisory.
```

Second, add one bullet immediately after the `evaluate_quality_gate` bullet that ends the section:

```markdown
- **`MERGE_REQUIRED_CHECKS`** is the manifest of checks the merge gate must see.
  `evaluate_quality_gate` synthesizes a failing `MISCONFIGURED` check for every
  manifest name absent from its input, at that name's manifest classification,
  and echoes it in `GateReport.checks` — an absent check blocks rather than
  passing silently. The same function re-asserts `ABSOLUTE_FLOOR` on input, so a
  directly-constructed `CheckResult` cannot demote a floor check.
```

- [ ] **Step 15: Update `docs/reference/presentation-pipeline-temporal.md`**

Section 5b (currently lines 175-207) is the repo's most detailed gate prose and is stale in two independent ways. `docs/reference/` is "Maintained — maintained when stale" per `docs/documentation-rules.md:44`, and C3 changes exactly this section's semantics.

Change the line `Six checks, in two classes:` to `Seven checks, in two classes:`, and add this row to the table immediately after the `lint_clean` row:

```markdown
| `security_scan_collected` | **ABSOLUTE** | security scan: the scan actually ran |
```

Then replace the floor paragraph (currently beginning `**The floor.** \`ABSOLUTE_FLOOR = {"security_no_critical"}\``) with:

```markdown
**The floor.** `ABSOLUTE_FLOOR = {"security_no_critical",
"security_scan_collected"}`: those checks are forced to ABSOLUTE by
`build_check()` even if a project's config asks for advisory, and re-asserted by
`evaluate_quality_gate()` on any check handed to it directly. A project can tune
its own strictness; it cannot configure away "no critical vulnerabilities", nor
demote "the scan actually ran" (FR-915 — a scan that could not run is as absolute
as a scan that found a critical). Worth saying out loud — it is the clearest
example of policy living in code rather than in a prompt.

**And the gate fails closed on its own inputs.** `MERGE_REQUIRED_CHECKS` names
the seven checks above as the set the merge gate must see. A name absent from the
evidence handed to the gate is synthesized as a *failing* check at its manifest
classification, with `MISCONFIGURED` in its detail — so a check that quietly
stopped being produced blocks the merge instead of passing unnoticed. Absolute
absence is terminal; advisory absence reaches the human gate as a waivable
finding.
```

- [ ] **Step 16: Flip the C3 row in the register**

In `docs/reports/external-ideas-2026-09.md`, edit **only** the C3 row (line 51). Task 2 owns the C4 row, the Status legend, and any new rows — do not touch them here. Set Status to `✅ **Fixed**` and replace the "Where it lands" cell, correcting its two stale line cites (`:57` and `:66`; the real lines are `:60` and `:71`):

```markdown
| C3 | **Fail-closed on a missing gate** — an absent/unconfigured required check yields `MISCONFIGURED` and a failing verdict, never a quiet green run | factory | ✅ **Fixed** | `gate.py`: `MERGE_REQUIRED_CHECKS` (the manifest, beside `ABSOLUTE_FLOOR` at `:60`) is the set the merge gate must see; `evaluate_quality_gate` synthesizes a failing `MISCONFIGURED` check through `build_check` (`:71`) for every absent name, at that name's manifest classification, and echoes it in `GateReport.checks`. Absolute absence is terminal, advisory absence is waivable at the audited human gate. No new verdict enum. The same pass re-asserts `ABSOLUTE_FLOOR` on input, closing the sibling hole where a directly-constructed `CheckResult` demotes a floor check and waives it. Contract: `merge.md` MERGE-1.6. |
```

Leave the priority shortlist (lines 108-127) alone — shipped items stay listed unmarked there, as C2 and C6 already do.

- [ ] **Step 17: Verify the whole task before committing**

Run: `pytest -q && ruff check . && ruff format --check . && mypy && python scripts/check_file_size.py`
Expected: tests pass, lint/format/type clean, file-size check exits 0.

- [ ] **Step 18: Commit**

Write the message to `.workspace/tmp/c3-commit-msg.txt` first, then commit with `-F`. Do **not** use a shell heredoc or a multi-line `-m`: the executor shell on this machine may be PowerShell 5.1, where heredocs are not valid syntax. `git add` takes one path per argument on one line for the same reason.

```
git add src/sdlc/gate.py tests/conftest.py tests/test_required_checks_manifest.py tests/test_quality_gate.py tests/test_security_collection_gate.py tests/merge/test_merge_gate_wiring.py src/sdlc/stages/merge/merge.md src/sdlc/stages/merge/AGENTS.md docs/reference/foundation.md docs/reference/presentation-pipeline-temporal.md docs/reports/external-ideas-2026-09.md
git commit -F .workspace/tmp/c3-commit-msg.txt
```

The message file's exact content:

```
feat(gates): fail closed on absent required merge checks

evaluate_quality_gate judged only the checks it was handed, so a required
check that was absent from the list was invisible and the run went quietly
green. MERGE_REQUIRED_CHECKS names the seven checks the merge gate must see;
every absent name is now synthesized through build_check as a failing
MISCONFIGURED result at its manifest classification and echoed in
GateReport.checks, where merge/step.py reads the absolute/advisory split.
Absolute absence is terminal; advisory absence is waivable at the audited
human gate. This generalizes FR-915's ruling for security_scan_collected from
one check to the required set: not-produced is produced-and-failed.

The same pre-loop pass re-asserts ABSOLUTE_FLOOR on the input list, closing
the sibling hole: build_check forces the floor at construction, but
CheckResult is a plain model, so a directly-constructed check could demote
security_no_critical to advisory and be waived by one override.

Contract updated in the same diff: merge.md gains MERGE-1.6 with cross-refs
from MERGE-1.2/1.3 and a failure-modes entry; merge/AGENTS.md invariants;
the gate.py module docstring.

The docs/reference/foundation.md floor fix is deliberate, not drive-by: its
ABSOLUTE_FLOOR list has been stale since FR-915 added
security_scan_collected, and the sentence was rewritten while the section was
open. presentation-pipeline-temporal.md section 5b was stale the same way
(six checks, one-name floor) and is corrected alongside.

Co-Authored-By: Claude Code <noreply@anthropic.com>
```

---

## Task 2: C4 — the advisory/deterministic pairing audit

**Files:**
- Create: `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md`
- Modify: `docs/reports/external-ideas-2026-09.md` (the C4 row at line 52; the Status legend at lines 19-23; two new rows C7 and C8 at the end of section C)
- Modify: `docs/documentation-rules.md` (one reconciling paragraph — see the preamble)

**Interfaces:**
- Consumes: nothing executable. Reads `src/sdlc/**` to verify cites, and the spec's §3 for row content.
- Produces: a dated report and three register edits. No code, no importable names.

**Preamble — a deviation from spec §3.7, and why it is a refinement rather than a breach.**

> Spec §3.7 enumerates two files for Task 2. Planning surfaced that `docs/documentation-rules.md:45,55` declares this task's primary edit target's directory immutable — "`docs/reports/` … true when written, never updated" — which Task 2's register edit contradicts. The spec cannot be amended after approval (`documentation-rules.md:47`: specs are write-once), so the plan is the correct artifact for the deviation. Task 2 therefore carries a third file: one reconciling paragraph in `docs/documentation-rules.md`, given verbatim below. §3.7's defect clause — "any change under `src/`, `tests/`, `agents/`, prompts, or config" — does not cover it, and the tripwire's purpose (words only, no code, no behaviour) is intact.

The contradiction is not new: the C2 and C6 rows were both updated in the same directory without anyone reconciling the rule. C4 is the first to notice it, in a task whose deliverable exists to name gaps honestly, so it is fixed here rather than inherited.

- [ ] **Step 1: Re-run the census greps and record the commit**

Run each of these from the repo root and keep the output — it goes into the document verbatim in Step 3. `grep` is not on PATH in PowerShell on this machine: either run these in git-bash, or use the `rg` equivalents below. **Print in the document whichever form you actually ran** — the audit's reproducibility depends on the command that was executed, not on one that merely sounds canonical.

```
git rev-parse --short HEAD
rg -n "run_role\(" src/sdlc -g "*.py"
rg -n "run_adversary|run_deep_review" src/sdlc/stages -g "*.py"
rg -n "revisable" src/sdlc -g "*.py"
rg -n "GOTCHA|GATE_FEEDBACK|STAGE_SUMMARY" src/sdlc -g "*.py"
```

The header cites the commit these greps were **last run against** — that is Task 1's commit, not the spec's `03e0663` baseline, because Task 1 has already landed on this branch. Every `file:line` in the document must be live against that commit.

Expected `run_role(` sites, from the census done at design time: `review/step.py:127,195,289`; `analyze/step.py:121`; `clarify/step.py:78,84,146,161`; `architecture/step.py:138`; `code/step.py:417`; `plan/step.py:88`; `merge/step.py:391`; `qa/step.py:175`; plus the workflow-side twins `workflows/feature.py:340` and `workflows/role_host.py:133` / `core/context.py:33`. If the line numbers have shifted, use the ones you observe — Task 1 touched none of the files in this census, so no shift is expected.

- [ ] **Step 2: Verify the eight rows' cites still resolve**

For each row in spec §3.4, open the cited file:line and confirm the claim. These four are the load-bearing ones the design corrected against the originating brief — do not take them on trust:

- `src/sdlc/stages/code/step.py:812` — `if adversary is None or adversary.approve or not adversary.blocking_findings:` guards the done-return. The adversary blocks; it is not signal-only.
- `src/sdlc/stages/code/step.py:750` — `task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)`. The QA LLM's `qa.issues` is a conjunct of the pass verdict, despite the "Never calls a gate" docstring at `qa/step.py:129-131`.
- `src/sdlc/stages/review/step.py:114-115` — `if not cfg.review_enabled or reviewer_agent is None: return None`, read as approval at `code/step.py:797`, and compounding at `code/step.py:801` where the adversary runs only `if review is not None`.
- `src/sdlc/workflows/role_host.py:64-65` — the `None`-confidence guard (the spec's earlier `:60-62` cite pointed at the docstring; use `:64-65`).

Two more cite corrections carried in from review, to apply as you write rather than repeat: the watermark-freeze mechanism lives at `role_host.py:122` and MemoryHost, not `core/context.py:55` (which is the `recall` protocol stub).

- [ ] **Step 3: Write the audit document**

Create `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md` with this structure. Row content comes from spec §3.4 — that spec is committed and travels with this plan; transcribe each row's failure mode, enforcement, backstop and verdict from it, with the cite corrections from Step 2 applied. Each of the three middle table columns is a one-phrase compression of the corresponding §3.4 paragraph; the subsection beneath the table carries that row's full argument. The out-of-scope table's rows are enumerated from the Step 1 grep output, not from memory.

```markdown
# Advisory LLM passes and the deterministic mechanisms behind them

| | |
|---|---|
| Date | 2026-09-06 |
| Commit | `<short hash from Step 1>` |
| Register row | C4, `docs/reports/external-ideas-2026-09.md` |
| Method | Census by grep over `src/sdlc` (reproduced in full below), then a two-prong scope criterion applied to every hit. |

## What this audits, and what "behind it" means

[The C4 principle: every advisory LLM check ships with a deterministic
enforcement path behind it. State the two-direction test explicitly, so the
next auditor re-runs it instead of trusting the table: *if it blocks, what
makes the block stick?* and *if it wrongly passes, what catches it?*]

## Scope criterion

[Spec §3.2 verbatim in substance: Prong A (judgment) and Prong B (evidence);
generators are out; a generator's self-reported confidence is in under Prong A
because it short-circuits a human gate; the unit of the audit is the judgment,
not the stage. Enumerate the admission boundaries.]

## Verdicts

[The four-member closed set from spec §3.3 — PAIRED, ENFORCED, FILTERED,
UNPAIRED — one line of definition each.]

## The census

| # | Pass (file:line) | Failure mode if wrong | Enforcement | Backstop | Verdict |
|---|---|---|---|---|---|
| 1 | MergeVerdict — `merge/models.py:21`, consulted `merge/step.py:399` | | | | PAIRED |
| 2 | Primary reviewer — `code/step.py:797`, `merge/step.py:287-292` | | | | ENFORCED |
| 3 | Adversary lens — invoked `code/step.py:802`, consulted `:812` | | | | ENFORCED (fail-open leg UNPAIRED) |
| 4 | deep_review — `code/step.py:813`, `:894` | | | | FILTERED |
| 5 | Handoff extractor — `code/step.py:417` | | | | FILTERED |
| 6 | Analyst — `analyze/step.py:121` | | | | ENFORCED |
| 7 | QA LLM pass — `qa/step.py:175` | | | | PAIRED |
| 8 | Confidence auto-approve — `role_host.py:55-75`, consumed `:224` | | | | UNPAIRED |

[Then one subsection per row, expanding the table cell into the argument, with
file:line for BOTH the pass and the mechanism. Row 1 carries a cross-reference
to row 8. Row 3 names the fail-open leg and states the analogy explicitly: it
is C3's hole one layer up — a check that did not run, read as a check that
passed. Row 5 cites the second extractor site at `workflows/feature.py:340` as
found, without investigating whether it is live. Row 7 states the
`code/step.py:750` conjunct and names the residual: a wrong-yes on a
non-test-detectable issue has no backstop in QA's own jurisdiction.]

## Row 8 is the headline

[Why the UNPAIRED confidence short-circuit is the most interesting finding: it
runs in the direction the C4 principle does not anticipate. The LLM output does
not *add* a check — it *removes* a human one. Name the guards that do exist
(`role_host.py:64-65`, `:236-239`) so the row is fair.]

## The memory channel

[Spec §3.5: retained LLM text recalled into later runs as a declared, hashed,
watermark-frozen stage input; the deterministic guard is replayability, not
judgment; this is the mechanism by which an UNPAIRED pass's wrongness compounds
across runs. Include the retro finding — retro has no LLM pass of its own.]

## Out of scope

| Pass (file:line) | Why out |
|---|---|

[One line per excluded `run_role` site from the Step 1 grep — the generators
(architect, planner, clarify ×4, research, the code task prompt), the
workflow-side twins, and the `reflect` consolidation. Account for every line the
grep returned: a census that lists only its hits cannot be audited for misses.
Rule explicitly on `ctx.judge` (benchmark quality scoring) and the crew
workflow's roles (E-88) rather than leaving a reader to wonder whether they were
missed or dodged. Record that intake and deploy have no `run_role` sites at all,
so the census dates itself. Note in the architect's line that it is the
best-backed generator — `check_brownfield_delta` (`context/delta.py`
`DELTA_CHECK`, consumed `architecture/step.py:162-184`) stands behind it — while
the plan stage has nothing analogous.]

## Census method

[The five commands from Step 1, verbatim, in a fenced block, so a reader can
re-run them and diff this table.]

## What remains open

[The gaps that became register rows C7 and C8, one line each, pointing at the
register. Per spec §3.7, recommendations live only as register rows — a
one-line candidate-remedy sketch here is allowed; a second actionable list is
not.]

## A note on timing

[C3 landed between this census and publication, and hardened exactly the
quiet-green hole row 3's analogy names: `evaluate_quality_gate` now synthesizes
absent required checks. Row 1's mechanism is therefore stronger than it was when
the C4 row was written.]
```

- [ ] **Step 4: Verify the document satisfies its own completion criterion**

Check all five of spec §3.6 against what you wrote, and fix anything missing:
1. Every in-scope row carries a verdict with `file:line` for both pass and mechanism.
2. The census greps are printed verbatim.
3. The out-of-scope table is present and accounts for every grep hit.
4. Every UNPAIRED item has a named follow-up register row (C7, C8 below) or an argued signal-only justification stating blast radius.
5. The C4 register row points at the document and names the real row count — eight.

- [ ] **Step 5: Add the reconciling paragraph to `docs/documentation-rules.md`**

Insert as a standalone paragraph immediately after the three-bullet "durability split" list and before the `## ARCHITECTURE.md and ROADMAP.md describe main only` heading:

```markdown
**The register in `reports/` is living, not a snapshot.**
`external-ideas-2026-09.md` is revised as candidates land — Status flips when an
item ships, corrections are dated inline ("Corrected 2026-09-01") — so the
never-updated rule above does not apply to it. The same liberty extends only to
*status stamps* on otherwise-frozen snapshots: a dated report may later be
marked superseded or closed, as `feature-coverage-audit-2026-07-05.md` was.
Anything beyond a status stamp belongs in a new dated report.
```

An earlier draft of this paragraph claimed the register was the directory's *only* exception and that its name deliberately departs from the `<YYYY-MM-DD>-<topic>.md` pattern. Both claims are false — `git log --follow docs/reports/feature-coverage-audit-2026-07-05.md` shows two in-place amendments (`0980f85`, `f906309`), and three files there already use topic-first names. Do not reintroduce the exclusivity claim; a paragraph in a docs-rules file that the repo's own history disproves is exactly the credibility failure this audit exists to avoid.

- [ ] **Step 6: Extend the register's Status legend**

In `docs/reports/external-ideas-2026-09.md`, append to the "What Status means" paragraph (lines 19-23), immediately after "…until someone settles what it means.":

```markdown
`Fixed` — shipped; residuals, if any, are named in the row. `Audited` — resolved
as a written audit rather than a build; the row points at the document and names
what remains open.
```

("shipped", not "shipped to main": at this commit C3's own flip sits on the branch, and integration is the orchestrator's later fast-forward. The definition has to be true at every moment it is read.)

`Fixed` is already used by the C2, C3 and C6 rows and was never defined; defining both tokens here costs one sentence and closes that debt at the moment `Audited` makes it load-bearing.

- [ ] **Step 7: Update the C4 row**

Replace line 52. Status becomes `✅ **Audited**` — not `Fixed`, because nothing was fixed: an audit was produced and the gaps it found remain open. `Source` stays `playbook`; provenance does not change when an idea is executed. The pointer goes in the "Where it lands" column, whose job is the landing site:

```markdown
| C4 | **Advisory + deterministic pairing rule** — every LLM check ships with a deterministic enforcement path behind it (the playbook's "skill makes violations rare, hook makes them near-impossible") | playbook | ✅ **Audited** | shipped as the pairing audit — `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md`; a census of **eight** in-scope passes (2 PAIRED · 3 ENFORCED · 2 FILTERED · 1 UNPAIRED) against the two-prong scope criterion, with the deterministic mechanism behind each cited at `file:line`. Open gaps filed as C7 and C8 |
```

- [ ] **Step 8: File the two follow-up rows**

Append to section C, after the C6 row and its explanatory block:

```markdown
| C7 | **Nothing stands behind self-reported confidence** — under SOFT policy a proposer's own `confidence >= threshold` skips the human gate outright (`role_host.py:55-75`, consumed `:224`; merge's copy at `merge/step.py:84-100`, consulted `:399`) | *found in audit* | ✅ Gap verified | the C4 audit's headline row, and the direction the pairing principle does not anticipate: the LLM output does not add a check, it removes a human one. Real guards exist (`None` confidence never auto-approves, `role_host.py:64-65`; exhausted rounds force a final gate, `:236-239`) — what is missing is any deterministic evidence that the confidence is calibrated. Candidate shape: score confidence against retained outcomes before honouring it, which is C5's calibration loop pointed at gates rather than at findings |
| C8 | **A lens that did not run is indistinguishable from a lens that approved** — the fail-open legs of the review stage leave no tombstone | *found in audit* | ✅ Gap verified | `run_adversary` returns `None` on exception, disabled config, or missing agent (`review/step.py:179-183`, `:234-240`) and `code/step.py:812` reads `None` as agreement; the primary reviewer's own leg (`review/step.py:114-115` → `code/step.py:797`) compounds it, because `code/step.py:801` runs the adversary only `if review is not None`. This is C3's hole one layer up — a check that never ran, read as a check that passed — and the C3 fix does not reach it, because these lenses never travel through `evaluate_quality_gate`. Candidate shape: record an explicit absence tombstone that the task's success condition must see |
```

- [ ] **Step 9: Verify the diff is words only**

Run: `git status --short && git diff --stat`
Expected: exactly three modified/created paths — `docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md`, `docs/reports/external-ideas-2026-09.md`, `docs/documentation-rules.md`. **Anything under `src/`, `tests/`, `agents/`, prompts, or config in this diff is a defect** — revert it and report rather than committing.

Run: `python scripts/check_file_size.py`
Expected: exit 0. `docs/` counts toward the 1000-line ceiling.

Two things in the register that this task must leave alone: the rendered-register artifact link in the header table (line 9) is stale by nature and is not this task's problem, and the priority shortlist (lines 108-127) keeps shipped items listed unmarked.

- [ ] **Step 10: Commit**

Write the message to `.workspace/tmp/c4-commit-msg.txt`, then commit with `-F`, for the same PowerShell reason as Task 1 Step 18 — no heredoc, no multi-line `-m`.

```
git add docs/reports/2026-09-06-advisory-deterministic-pairing-audit.md docs/reports/external-ideas-2026-09.md docs/documentation-rules.md
git commit -F .workspace/tmp/c4-commit-msg.txt
```

The message file's exact content:

```
docs: ship the C4 advisory/deterministic pairing audit

C4 was a principle with no completion criterion. This is the audit the
register row asked for: a census of every LLM pass on the verification
surface, mapped to the deterministic mechanism standing behind it, with the
gaps named rather than papered over.

Eight in-scope passes under a two-prong scope criterion (judgment, evidence),
each carrying file:line for both the pass and its mechanism, and one of four
verdicts separating "what makes a block stick" from "what catches a
wrong-yes". Two claims in the originating framing are corrected against the
code: the adversary lens is not signal-only (code/step.py:812 guards the
done-return on it; the real gap is its fail-open leg), and the QA pass's
"never calls a gate" docstring is incomplete (code/step.py:750 makes
qa.issues a conjunct of task_passed).

The headline is the confidence auto-approve short-circuit: UNPAIRED, and the
direction the pairing principle does not anticipate — the LLM output does not
add a check, it removes a human one. That gap and the fail-open lens gap are
filed as register rows C7 and C8.

documentation-rules.md gains one paragraph reconciling a standing
contradiction this task surfaced: the candidate register lives in
docs/reports/, which that file declares immutable, while the register is a
living document whose rows have been revised since C2.

Co-Authored-By: Claude Code <noreply@anthropic.com>
```
