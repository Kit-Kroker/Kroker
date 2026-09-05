# Judge Sensitivity and Plan Adherence (E-83) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the prompt gate teeth it can be shown to have — deterministic rubric vetoes plus a staged judge — and record the one plan-execution signal the pipeline does not measure.

**Architecture:** Rubric criteria that state an absolute override ("scores 0 regardless") become **typed, declarative vetoes evaluated in Python over the parsed artifact** — no model call. The LLM judge becomes two staged calls (rubric → evaluation steps, cached by rubric sha; then artifact → per-component scores), with vetoes overriding its output rather than being argued into it. Plan adherence splits by provenance: a deterministic `PlanDrift` on the record, and an advisory narrative folded into the existing `deep_review` lens rather than a fifth lens.

**Tech Stack:** Python 3.11+, Pydantic v2, pydantic-ai, promptfoo (Node ≥ 22.22, `eval` extra), pytest with opt-in markers, Temporal (`temporalio`).

## Global Constraints

- **No new runtime dependency.** DeepEval is rejected (spec §3). Everything here uses `pydantic`, `pydantic-ai`, `pyyaml` — all already in `pyproject.toml`.
- **Vetoes are deterministic.** Zero model calls, evaluated over the parsed artifact.
- **A broken measurement must never masquerade as a measurement.** `None` means NOT MEASURED and must never render as zero or as a pass.
- **Prompt-gate results never enter the `BenchmarkRecord` stream.** They join by `prompt_sha` only (E-82 spec §2). Nothing in this plan changes that.
- **ADR-6 is untouched.** The family and identity checks stay at `assertion.py:64-85` and run before any judge call.
- **Every test outside Task 12 makes zero model calls.** Default `pytest` must stay free.
- **Judge literal:** the new value is exactly `"staged_rubric"`. Not `"geval"`, not `"llm_judge_v2"`.
- **Python files:** 4-space indent, `from __future__ import annotations` first, module docstring explaining *why*, matching the surrounding style.

## File Structure

**Created:**
- `src/sdlc/benchmarks/vetoes.py` — the veto vocabulary + pure check engine. One responsibility: given a parsed artifact and a list of vetoes, return failures.
- `tests/test_vetoes.py` — table-driven veto engine tests.
- `tests/test_staged_judge.py` — staged judge composition tests.
- `tests/test_plan_drift.py` — `PlanDrift` computation tests.
- `tests/test_prompt_gate_mutations.py` — the mutation suite (opt-in, spends tokens).
- `benchmarks/cases/cat-cafe-monitoring/vetoes-clarifier.yaml`
- `benchmarks/cases/cat-cafe-monitoring/vetoes-qa.yaml`

**Modified:**
- `src/sdlc/eval/verdict.py:145-172` — populate means in the `UNAVAILABLE` branch; carry per-row scores.
- `src/sdlc/eval/cli.py:60-70` — `render_report` must guard each optional field independently.
- `src/sdlc/eval/promptfoo/absolute.py` — vetoes gate at Layer 2.
- `src/sdlc/eval/promptfoo/provider.py:63-104` — literal-instructions override for mutations.
- `src/sdlc/eval/promptfoo/config.py:33-86` — pass vetoes + mutation through.
- `src/sdlc/eval/gate.py:59-114` — `mutation` parameter.
- `src/sdlc/benchmarks/judge.py` — staged judge, veto application, `vetoes_yaml`.
- `src/sdlc/benchmarks/models.py:57-58` — `judge` Literal gains `"staged_rubric"`.
- `src/sdlc/benchmarks/models.py:108-128` — `BenchmarkRecord.plan_drift`.
- `src/sdlc/benchmarks/score.py` — judge-mix note.
- `src/sdlc/benchmarks/workflow.py:164` — load veto assets.
- `src/sdlc/models.py` — `PlanDrift`, `PlanDeviation`, `DeepReviewReport.plan_deviations`, `CaseSpec.vetoes`, `BenchmarkConfig.vetoes`.
- `src/sdlc/handoff.py:91-115` — `verified_plan_deviations`.
- `src/sdlc/workflows/feature.py:576-601, 952-1016` — `plan_drift` on records, deep_review extension.
- `agents/deep_review/instructions.md` — plan-deviation reporting.
- `tests/test_judge_literal.py:13-16` — new literal.
- `tests/test_eval_verdict.py` — means-populated cases.
- `benchmarks/cases/cat-cafe-monitoring/case.yaml` — `vetoes:` block.

---

## Phase 1 — Prove the instrument (spec §4.1)

Ordered first because a sharper judge fixes none of the ten recorded failures, and because no sensitivity claim is reproducible until the numbers survive to disk.

### Task 1: Populate means when the judge is one-sided

`verdict.py`'s `UNAVAILABLE` branch returns `n_baseline` / `n_working` but never `mean_baseline` / `mean_working` — unlike the `no_baseline` branch directly above it. A real judge score gets recorded as a bare count and the number dies with the scratch dir.

**Files:**
- Modify: `src/sdlc/eval/verdict.py:152-157`
- Modify: `src/sdlc/eval/cli.py:60-70`
- Test: `tests/test_eval_verdict.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `PromptGateResult.mean_baseline` / `.mean_working` are populated whenever that side produced at least one score, on **every** verdict path. `delta` and `floor` remain `None` unless a regression comparison actually ran.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eval_verdict.py`:

```python
def test_one_sided_judge_still_records_the_measured_mean():
    """A judge score that WAS produced must survive to the record.

    The regression is correctly not evaluated -- but reporting only n=1 and
    dropping the 1.00 is how OQ-P5's evidence was lost."""
    r = decide(_results([], [1.0]))
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.verdict is GateVerdict.PASS
    assert r.n_working == 1
    assert r.mean_working == 1.0
    assert r.mean_baseline is None
    # NOT a regression comparison -- these must stay unset.
    assert r.delta is None
    assert r.floor is None


def test_one_sided_baseline_records_its_mean_too():
    r = decide(_results([0.4, 0.6], []))
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.mean_baseline == 0.5
    assert r.mean_working is None
    assert r.n_baseline == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_verdict.py::test_one_sided_judge_still_records_the_measured_mean -v`
Expected: FAIL — `assert None == 1.0`, because `mean_working` is never set on that branch.

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/eval/verdict.py`, replace the `if not base or not work:` block (currently lines 152-157) with:

```python
if not base or not work:
    # The measured side's mean IS reported. The regression is NOT
    # evaluated -- delta/floor stay None -- but a score that was
    # produced must reach the record. Dropping it is how OQ-P5's
    # "scored 1.00" observation became unrecoverable: the number lived
    # only in the results.json that run_gate deletes in its finally.
    return PromptGateResult(
        verdict=GateVerdict.PASS,
        judge_status=JudgeStatus.UNAVAILABLE,
        mean_baseline=statistics.fmean(base) if base else None,
        mean_working=statistics.fmean(work) if work else None,
        n_baseline=len(base),
        n_working=len(work),
        reason="judge unavailable on at least one side — regression NOT "
        "evaluated (not measured, not passed)",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_verdict.py -v`
Expected: PASS, all cases including the pre-existing ones.

- [ ] **Step 5: Write the failing test for the renderer**

`render_report` gates every optional field behind `if r.mean_baseline is not None:` and then formats `mean_working`, `delta` and `floor`. Task 1 makes a one-sided baseline result populate `mean_baseline` while leaving the others `None`, so the renderer now raises `TypeError: unsupported format string passed to NoneType.__format__`.

Create `tests/test_eval_cli_render.py`:

```python
"""render_report must not assume the optional numbers travel together.

After E-83 Task 1 a one-sided judge populates mean_baseline while leaving
delta and floor None, which the old single `if` formatted unconditionally."""

from sdlc.eval.cli import render_report
from sdlc.eval.verdict import GateVerdict, JudgeStatus, PromptGateResult


def test_render_handles_baseline_mean_without_delta():
    r = PromptGateResult(
        verdict=GateVerdict.PASS,
        judge_status=JudgeStatus.UNAVAILABLE,
        role="clarify",
        case="cat-cafe-monitoring",
        reason="one-sided",
        mean_baseline=0.5,
        n_baseline=2,
    )
    text = render_report(r)
    assert "baseline  0.50" in text
    assert "delta" not in text


def test_render_shows_delta_when_the_comparison_ran():
    r = PromptGateResult(
        verdict=GateVerdict.PASS,
        judge_status=JudgeStatus.MEASURED,
        role="clarify",
        case="c",
        reason="ok",
        mean_baseline=0.80,
        mean_working=0.85,
        delta=0.05,
        floor=0.05,
        n_baseline=3,
        n_working=3,
    )
    text = render_report(r)
    assert "delta     +0.05" in text
```

- [ ] **Step 6: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_cli_render.py -v`
Expected: FAIL — `TypeError: unsupported format string passed to NoneType.__format__` on the first test.

- [ ] **Step 7: Fix the renderer**

In `src/sdlc/eval/cli.py`, replace the `render_report` body's optional-number block with:

```python
def render_report(r: PromptGateResult) -> str:
    head = f"eval {r.role} (case {r.case}) -> {r.verdict.value}"
    lines = [head, f"  {r.reason}"]
    # Each number is guarded independently: a one-sided judge reports its
    # measured mean with no delta or floor, because no comparison ran.
    if r.mean_baseline is not None:
        lines.append(f"  baseline  {r.mean_baseline:.2f}  (n={r.n_baseline})")
    if r.mean_working is not None:
        lines.append(f"  working   {r.mean_working:.2f}  (n={r.n_working})")
    if r.delta is not None and r.floor is not None:
        lines.append(f"  delta     {r.delta:+.2f}   floor {r.floor:.2f}")
    for f in r.absolute_failures:
        lines.append(f"  ABSOLUTE  {f}")
    return "\n".join(lines)
```

- [ ] **Step 8: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/eval/verdict.py src/sdlc/eval/cli.py tests/test_eval_verdict.py tests/test_eval_cli_render.py
git commit -m "fix(eval): a one-sided judge's measured mean must reach the record (E-83)"
```

---

### Task 2: Persist the per-row judge scores

Without the individual scores, no sensitivity claim about this gate is reproducible after `run_gate` removes its scratch dir (`gate.py:107`).

**Files:**
- Modify: `src/sdlc/eval/verdict.py`
- Test: `tests/test_eval_verdict.py`

**Interfaces:**
- Consumes: Task 1's `decide()`.
- Produces: `PromptGateResult.scores_baseline: list[float]` and `.scores_working: list[float]`, populated on every path where scores exist. Bounded by `repeat` (default 3).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_eval_verdict.py`:

```python
def test_individual_scores_are_persisted():
    r = decide(_results([0.70, 0.80], [0.90, 0.95]))
    assert r.scores_baseline == [0.70, 0.80]
    assert r.scores_working == [0.90, 0.95]


def test_unavailable_rows_are_excluded_from_persisted_scores():
    """A JUDGE_UNAVAILABLE row carries a placeholder number that must not
    be persisted as if it were a measurement."""
    from sdlc.eval.verdict import JUDGE_UNAVAILABLE

    res = _results([0.5], [0.5])
    working_row = res["results"]["results"][-1]
    working_row["gradingResult"]["componentResults"][1]["reason"] = (
        f"{JUDGE_UNAVAILABLE}: judge errored"
    )
    r = decide(res)
    assert r.scores_baseline == [0.5]
    assert r.scores_working == []


def test_scores_persisted_on_the_one_sided_path():
    r = decide(_results([], [1.0]))
    assert r.scores_working == [1.0]
    assert r.scores_baseline == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_eval_verdict.py::test_individual_scores_are_persisted -v`
Expected: FAIL — `AttributeError: 'PromptGateResult' object has no attribute 'scores_baseline'`.

- [ ] **Step 3: Add the fields**

In `src/sdlc/eval/verdict.py`, add to `PromptGateResult` immediately after `n_working`:

```python
    # The individual judge scores behind the means. Bounded by `repeat`
    # (default 3), so this is a handful of floats. Persisted because the
    # scratch results.json is deleted (gate.py:107) and without them no
    # sensitivity claim about this gate is reproducible after the fact.
    scores_baseline: list[float] = Field(default_factory=list)
    scores_working: list[float] = Field(default_factory=list)
```

- [ ] **Step 4: Populate them on every return path**

In `decide()`, immediately after the `base` / `work` list comprehensions, bind a helper and pass it to each remaining `PromptGateResult(...)`:

```python
    base = [s for s in _scores(base_rows) if s is not None]
    work = [s for s in _scores(work_rows) if s is not None]
    kept = {"scores_baseline": base, "scores_working": work}
```

Then add `**kept` to the three `PromptGateResult(...)` constructions that follow — the `no_baseline` return, the `not base or not work` return, and the final regression return. The two early returns above the comprehensions (`ERRORED` and `FAIL_ABSOLUTE`) are left unchanged: neither reached the judge.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_verdict.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/eval/verdict.py tests/test_eval_verdict.py
git commit -m "feat(eval): persist per-row judge scores on the gate result (E-83)"
```

---

## Phase 2 — Vetoes (spec §4.2)

### Task 3: The veto vocabulary and check engine

A closed, typed vocabulary — three kinds, validated at load, no expression evaluation and no code under `benchmarks/cases/`.

**Files:**
- Create: `src/sdlc/benchmarks/vetoes.py`
- Test: `tests/test_vetoes.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Veto` — discriminated union of `MentionsAll | NotBoth | NonEmpty`.
  - `VetoFailure(veto_id: str, reason: str)`.
  - `parse_vetoes(text: str) -> list[Veto]` — YAML text → typed vetoes; raises `VetoConfigError`.
  - `check(artifact: dict, vetoes: list[Veto]) -> list[VetoFailure]` — pure.
  - `validate_fields(vetoes: list[Veto], output_type: type[BaseModel]) -> None` — raises `VetoConfigError` naming unknown fields.
  - `VetoConfigError(Exception)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vetoes.py`:

```python
"""The veto engine: rubric criteria that state an absolute override.

Three rubrics on disk say a component "scores 0 regardless of how good the
rest is". A mean-of-components LLM judge structurally cannot express that,
and rubric-qa.md:15's veto is a boolean over three typed fields. These run
deterministically, with zero model calls."""

import pytest
from pydantic import BaseModel

from sdlc.benchmarks.vetoes import VetoConfigError, check, parse_vetoes, validate_fields

CLARIFY_YAML = """
- id: scope_preserved
  kind: mentions_all
  terms: [sleeping, eating, drinking, litter box, playing, fighting]
  fields: [functional_requirements, open_questions]
"""

QA_YAML = """
- id: internal_consistency
  kind: not_both
  field: tests_passed
  equals: true
  and_any_nonempty: [failing_tests, issues]
"""


def test_mentions_all_passes_when_every_term_present():
    artifact = {
        "functional_requirements": [
            "detect sleeping, eating and drinking",
            "detect litter box, playing and fighting",
        ],
        "open_questions": [],
    }
    assert check(artifact, parse_vetoes(CLARIFY_YAML)) == []


def test_mentions_all_fails_and_names_the_missing_terms():
    artifact = {"functional_requirements": ["detect sleeping and eating"], "open_questions": []}
    failures = check(artifact, parse_vetoes(CLARIFY_YAML))
    assert len(failures) == 1
    assert failures[0].veto_id == "scope_preserved"
    assert "drinking" in failures[0].reason
    assert "fighting" in failures[0].reason
    assert "sleeping" not in failures[0].reason  # present, not reported


def test_mentions_all_is_case_insensitive():
    artifact = {
        "functional_requirements": ["SLEEPING, Eating, DRINKING, Litter Box, playing, FIGHTING"],
        "open_questions": [],
    }
    assert check(artifact, parse_vetoes(CLARIFY_YAML)) == []


def test_mentions_all_with_no_fields_searches_the_whole_artifact():
    vetoes = parse_vetoes("- id: v\n  kind: mentions_all\n  terms: [alpha]\n")
    assert check({"anything": {"nested": "alpha"}}, vetoes) == []
    assert len(check({"anything": "beta"}, vetoes)) == 1


def test_not_both_fails_on_the_contradiction():
    artifact = {"tests_passed": True, "failing_tests": ["t::a"], "issues": []}
    failures = check(artifact, parse_vetoes(QA_YAML))
    assert len(failures) == 1
    assert failures[0].veto_id == "internal_consistency"
    assert "failing_tests" in failures[0].reason


def test_not_both_passes_when_the_trigger_field_does_not_match():
    artifact = {"tests_passed": False, "failing_tests": ["t::a"], "issues": []}
    assert check(artifact, parse_vetoes(QA_YAML)) == []


def test_not_both_passes_when_all_listed_fields_are_empty():
    artifact = {"tests_passed": True, "failing_tests": [], "issues": []}
    assert check(artifact, parse_vetoes(QA_YAML)) == []


def test_nonempty_fails_on_an_empty_field():
    vetoes = parse_vetoes("- id: v\n  kind: nonempty\n  fields: [summary]\n")
    assert len(check({"summary": ""}, vetoes)) == 1
    assert len(check({"summary": "   "}, vetoes)) == 1
    assert check({"summary": "real"}, vetoes) == []


def test_nonempty_fails_on_a_missing_field():
    """A field the artifact does not carry cannot be non-empty. Treating
    absence as a pass would make the veto vacuous."""
    vetoes = parse_vetoes("- id: v\n  kind: nonempty\n  fields: [summary]\n")
    assert len(check({}, vetoes)) == 1


def test_unknown_kind_is_a_config_error():
    with pytest.raises(VetoConfigError) as e:
        parse_vetoes("- id: v\n  kind: vibes\n")
    assert "vibes" in str(e.value)


def test_malformed_yaml_is_a_config_error():
    with pytest.raises(VetoConfigError):
        parse_vetoes("- id: v\n  kind: mentions_all\n")  # terms missing


def test_empty_text_yields_no_vetoes():
    assert parse_vetoes("") == []


class _Output(BaseModel):
    tests_passed: bool
    failing_tests: list[str] = []
    issues: list[str] = []


def test_validate_fields_accepts_known_fields():
    validate_fields(parse_vetoes(QA_YAML), _Output)


def test_validate_fields_rejects_an_unknown_field():
    bad = parse_vetoes("- id: v\n  kind: nonempty\n  fields: [not_a_field]\n")
    with pytest.raises(VetoConfigError) as e:
        validate_fields(bad, _Output)
    assert "not_a_field" in str(e.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vetoes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.benchmarks.vetoes'`.

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/benchmarks/vetoes.py`:

```python
"""Rubric vetoes: the absolute overrides, evaluated deterministically.

Three rubrics on disk state a veto in prose -- rubric-clarifier.md:12,
rubric-qa.md:15, rubric-research.md:12 -- each saying a component "scores 0
regardless of how good the rest is". The judge is asked for
`{"score": <mean>, "components": {...}}`, and a weighted mean cannot express
an absolute override. In the QA case the veto is a boolean over three typed
Pydantic fields being asked of an LLM.

So vetoes are evaluated HERE, in Python, over the parsed artifact: zero model
calls, exhaustively testable, and impossible for the graded model to argue
with. This is DAG's short-circuit mechanism without DAG's framework.

The vocabulary is a CLOSED set of three kinds, deliberately minimal: it covers
every veto currently written in rubric prose and nothing more. A fourth kind
is added when a fourth rubric needs one, not in anticipation.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Union

import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError


class VetoConfigError(Exception):
    """A veto file that does not parse, or names a field the output_type
    lacks. Loud by design: a veto that does not parse is not a passing veto."""


class MentionsAll(BaseModel):
    kind: Literal["mentions_all"]
    id: str
    terms: list[str]
    # Empty = search the whole serialized artifact.
    fields: list[str] = Field(default_factory=list)


class NotBoth(BaseModel):
    kind: Literal["not_both"]
    id: str
    field: str
    equals: bool | str | int
    and_any_nonempty: list[str]


class NonEmpty(BaseModel):
    kind: Literal["nonempty"]
    id: str
    fields: list[str]


Veto = Annotated[Union[MentionsAll, NotBoth, NonEmpty], Field(discriminator="kind")]
_ADAPTER = TypeAdapter(list[Veto])


class VetoFailure(BaseModel):
    veto_id: str
    reason: str


def parse_vetoes(text: str) -> list[Veto]:
    """YAML text -> typed vetoes. Raises VetoConfigError on anything else."""
    if not text or not text.strip():
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise VetoConfigError(f"veto file is not valid YAML: {e}") from e
    if data is None:
        return []
    try:
        return _ADAPTER.validate_python(data)
    except ValidationError as e:
        raise VetoConfigError(f"veto file does not validate: {e}") from e


def _haystack(artifact: dict, fields: list[str]) -> str:
    """Lowercased text to search. No fields = the whole artifact, so a veto
    need not know which field the model chose to put something in."""
    if not fields:
        return json.dumps(artifact, default=str).lower()
    parts = [json.dumps(artifact.get(f, ""), default=str) for f in fields]
    return " ".join(parts).lower()


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return False


def _check_one(artifact: dict, v: Veto) -> VetoFailure | None:
    if isinstance(v, MentionsAll):
        hay = _haystack(artifact, v.fields)
        missing = [t for t in v.terms if t.lower() not in hay]
        if missing:
            return VetoFailure(
                veto_id=v.id, reason=f"required term(s) absent: {', '.join(missing)}"
            )
        return None

    if isinstance(v, NotBoth):
        if artifact.get(v.field) != v.equals:
            return None
        populated = [f for f in v.and_any_nonempty if not _is_empty(artifact.get(f))]
        if populated:
            return VetoFailure(
                veto_id=v.id,
                reason=f"{v.field} == {v.equals!r} contradicts non-empty {', '.join(populated)}",
            )
        return None

    # NonEmpty. A missing field cannot be non-empty; treating absence as a
    # pass would make the veto vacuous.
    blank = [f for f in v.fields if _is_empty(artifact.get(f))]
    if blank:
        return VetoFailure(veto_id=v.id, reason=f"field(s) empty or absent: {', '.join(blank)}")
    return None


def check(artifact: dict, vetoes: list[Veto]) -> list[VetoFailure]:
    """Pure. Every veto is evaluated -- the caller sees all failures, not
    just the first, because a rubric author fixing one wants to see the rest."""
    out = []
    for v in vetoes:
        failure = _check_one(artifact, v)
        if failure is not None:
            out.append(failure)
    return out


def _referenced_fields(v: Veto) -> list[str]:
    if isinstance(v, MentionsAll):
        return list(v.fields)
    if isinstance(v, NotBoth):
        return [v.field, *v.and_any_nonempty]
    return list(v.fields)


def validate_fields(vetoes: list[Veto], output_type: type[BaseModel]) -> None:
    """Every field a veto names must exist on the role's real output_type.

    Checked at LOAD, not at judge time: this is catchable without a model
    call, and deferring it wastes a whole gate run to learn about a typo.
    """
    known = set(output_type.model_fields)
    for v in vetoes:
        unknown = [f for f in _referenced_fields(v) if f not in known]
        if unknown:
            raise VetoConfigError(
                f"veto '{v.id}' names field(s) absent from "
                f"{output_type.__name__}: {', '.join(unknown)}. "
                f"Known fields: {', '.join(sorted(known))}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vetoes.py -v`
Expected: PASS, all 16 tests.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/vetoes.py tests/test_vetoes.py
git commit -m "feat(bench): typed, deterministic rubric vetoes (E-83)"
```

---

### Task 4: Author the veto files and register them

**Files:**
- Create: `benchmarks/cases/cat-cafe-monitoring/vetoes-clarifier.yaml`
- Create: `benchmarks/cases/cat-cafe-monitoring/vetoes-qa.yaml`
- Modify: `benchmarks/cases/cat-cafe-monitoring/case.yaml`
- Modify: `src/sdlc/models.py` (`CaseSpec.vetoes`)
- Test: `tests/test_vetoes.py`

**Interfaces:**
- Consumes: `parse_vetoes`, `validate_fields`, `VetoConfigError` from Task 3.
- Produces: `CaseSpec.vetoes: dict[str, str]` — rubric-key → veto filename, mirroring `CaseSpec.rubrics` exactly.

`research` is deliberately NOT authored: it is a `DEPS_ROLES` role whose agent cannot be constructed, so `validate_fields` could not run against its `output_type`. See spec §8.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_vetoes.py`:

```python
def test_shipped_veto_files_parse_and_match_their_output_types():
    """The two authored veto files must parse AND name only real fields.

    This is the load-time check the design puts ahead of judge time, run
    against the real ClarifiedRequirements and QAReport."""
    from pathlib import Path

    from sdlc.models import ClarifiedRequirements, QAReport

    case = Path(__file__).resolve().parents[1] / "benchmarks" / "cases" / "cat-cafe-monitoring"
    for filename, output_type in (
        ("vetoes-clarifier.yaml", ClarifiedRequirements),
        ("vetoes-qa.yaml", QAReport),
    ):
        vetoes = parse_vetoes((case / filename).read_text(encoding="utf-8"))
        assert vetoes, f"{filename} declares no vetoes"
        validate_fields(vetoes, output_type)


def test_case_yaml_registers_both_veto_files():
    from pathlib import Path

    import yaml as _yaml

    case = Path(__file__).resolve().parents[1] / "benchmarks" / "cases" / "cat-cafe-monitoring"
    data = _yaml.safe_load((case / "case.yaml").read_text(encoding="utf-8"))
    assert data["vetoes"] == {"clarifier": "vetoes-clarifier.yaml", "qa": "vetoes-qa.yaml"}
    for rel in data["vetoes"].values():
        assert (case / rel).is_file()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vetoes.py::test_shipped_veto_files_parse_and_match_their_output_types -v`
Expected: FAIL — `FileNotFoundError: ...vetoes-clarifier.yaml`.

- [ ] **Step 3: Author the clarifier vetoes**

Create `benchmarks/cases/cat-cafe-monitoring/vetoes-clarifier.yaml`:

```yaml
# Executable form of rubric-clarifier.md:12 -- "Silently dropping an activity,
# the risk analysis, the red marking, or the 24h history scores 0 on this
# component regardless of how good the rest is."
#
# The rubric states an absolute override; a mean-of-components judge cannot
# express one. This runs in Python, over the parsed ClarifiedRequirements,
# with zero model calls.
- id: scope_preserved
  kind: mentions_all
  terms:
    - sleeping
    - eating
    - drinking
    - litter box
    - playing
    - fighting
    - risk
    - red
    - 24
  fields:
    - summary
    - functional_requirements
    - open_questions
    - non_functional_requirements

# rubric-clarifier.md:16 -- out_of_scope must be explicit. An empty list is
# not scope discipline; it is a missing answer.
- id: scope_discipline_declared
  kind: nonempty
  fields:
    - out_of_scope
```

- [ ] **Step 4: Author the QA vetoes**

Create `benchmarks/cases/cat-cafe-monitoring/vetoes-qa.yaml`:

```yaml
# Executable form of rubric-qa.md:13-17 -- internal_consistency. Both
# directions of the contradiction the rubric names, each a boolean over typed
# QAReport fields. This is the clearest case in the repository of a check that
# was being asked of an LLM inside a weighted mean.
- id: internal_consistency_passing
  kind: not_both
  field: tests_passed
  equals: true
  and_any_nonempty:
    - failing_tests
    - issues
```

- [ ] **Step 5: Register them in case.yaml**

Append to `benchmarks/cases/cat-cafe-monitoring/case.yaml`, directly below the existing `rubrics:` block:

```yaml
# Deterministic absolute overrides for the rubrics above (E-83). Same
# key vocabulary as `rubrics:`. A rubric may have no veto file; a veto file
# without a matching rubric key is never loaded.
vetoes:
  clarifier: vetoes-clarifier.yaml
  qa: vetoes-qa.yaml
```

- [ ] **Step 6: Add the CaseSpec field**

In `src/sdlc/models.py`, in `CaseSpec`, directly below the `rubrics` field (currently line 147):

```python
    # E-83: stage -> veto file. Mirrors `rubrics`. Absent = no vetoes for
    # that stage, which is not an error -- vetoes are opt-in per case.
    vetoes: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_vetoes.py tests/test_golden_case_loads.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add benchmarks/cases/cat-cafe-monitoring/ src/sdlc/models.py tests/test_vetoes.py
git commit -m "feat(bench): author clarifier + qa vetoes for cat-cafe-monitoring (E-83)"
```

---

### Task 5: Vetoes gate at Layer 2 (the prompt gate)

This is where the gate gains content teeth. OQ-P5 recorded that the absolute tier's only teeth were cost/latency budgets and a blank-string check.

**Files:**
- Modify: `src/sdlc/eval/promptfoo/absolute.py`
- Modify: `src/sdlc/eval/promptfoo/config.py:61-80`
- Test: `tests/test_eval_absolute_vetoes.py`

**Interfaces:**
- Consumes: `parse_vetoes`, `check`, `validate_fields`, `VetoConfigError` (Task 3); `vetoes-*.yaml` + `case.yaml` (Task 4); `output_type_for` (existing, `absolute.py:24`).
- Produces: `load_vetoes(case: str, role: str, cases_root: Path) -> list[Veto]` in `absolute.py`. A veto failure becomes an ABSOLUTE failure, so `verdict.decide` returns `FAIL_ABSOLUTE`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_absolute_vetoes.py`:

```python
"""Vetoes gate at Layer 2: a veto failure is an ABSOLUTE failure.

Zero model calls -- the veto engine is pure and get_assert takes the output
as a string."""

import json

from sdlc.eval.promptfoo.absolute import get_assert, load_vetoes

_GOOD = {
    "summary": "Detect sleeping, eating, drinking, litter box, playing and "
    "fighting; risk analysis marks at-risk cats red; 24h history.",
    "functional_requirements": ["detect all six activities"],
    "non_functional_requirements": ["5s telemetry cadence"],
    "out_of_scope": ["no real collar hardware"],
    "open_questions": [],
}


def _ctx(cases_root, agents_dir, case="cat-cafe-monitoring", role="clarify"):
    return {
        "vars": {
            "role": role,
            "case": case,
            "agents_dir": str(agents_dir),
            "cases_root": str(cases_root),
        }
    }


def test_load_vetoes_reads_the_registered_file(repo_cases_root):
    vetoes = load_vetoes("cat-cafe-monitoring", "clarify", repo_cases_root)
    assert {v.id for v in vetoes} == {"scope_preserved", "scope_discipline_declared"}


def test_load_vetoes_returns_empty_for_an_unregistered_case_role(repo_cases_root):
    """No vetoes registered is NOT an error -- vetoes are opt-in per case."""
    assert load_vetoes("add-login-greenfield", "clarify", repo_cases_root) == []


def test_complete_artifact_passes(repo_cases_root, repo_agents_dir):
    r = get_assert(json.dumps(_GOOD), _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is True


def test_dropped_activity_fails_absolutely(repo_cases_root, repo_agents_dir):
    """The scope_dropped mutation's target: an artifact that validates as
    ClarifiedRequirements but silently lost three activities."""
    bad = dict(_GOOD)
    bad["summary"] = "Detect sleeping, eating and drinking. 24h history, risk, red."
    bad["functional_requirements"] = ["detect three activities"]
    r = get_assert(json.dumps(bad), _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is False
    assert r["score"] == 0.0
    assert "scope_preserved" in r["reason"]
    assert "fighting" in r["reason"]


def test_empty_out_of_scope_fails_absolutely(repo_cases_root, repo_agents_dir):
    bad = dict(_GOOD, out_of_scope=[])
    r = get_assert(json.dumps(bad), _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is False
    assert "scope_discipline_declared" in r["reason"]


def test_output_type_failure_still_wins_over_vetoes(repo_cases_root, repo_agents_dir):
    """An output that does not parse is broken whatever a veto says, and the
    reason must name the type failure -- not a confusing veto message about
    fields that were never populated."""
    r = get_assert("not json at all", _ctx(repo_cases_root, repo_agents_dir))
    assert r["pass"] is False
    assert "does not validate" in r["reason"]
```

Add the two fixtures to `tests/conftest.py`:

```python
@pytest.fixture
def repo_cases_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[1] / "benchmarks" / "cases"


@pytest.fixture
def repo_agents_dir():
    from sdlc.agents.loader import _resolve_agents_dir

    return _resolve_agents_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_eval_absolute_vetoes.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_vetoes'`.

- [ ] **Step 3: Implement `load_vetoes` and wire it into `get_assert`**

In `src/sdlc/eval/promptfoo/absolute.py`, add the imports and the loader:

```python
import yaml

from sdlc.benchmarks.vetoes import Veto, VetoConfigError, check, parse_vetoes, validate_fields
from sdlc.eval.promptfoo.assertion import RUBRIC_KEY
```

```python
def load_vetoes(case: str, role: str, cases_root: Path) -> list[Veto]:
    """Vetoes registered for (case, role), or [] when none are.

    Absence is NOT an error: vetoes are opt-in per case and the absolute tier
    keeps its previous behaviour without them. A veto file that is REGISTERED
    but malformed IS an error -- a veto that does not parse is not a passing
    veto.
    """
    case_yaml = Path(cases_root) / case / "case.yaml"
    if not case_yaml.is_file():
        return []
    data = yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
    rel = (data.get("vetoes") or {}).get(RUBRIC_KEY.get(role, role))
    if not rel:
        return []
    path = Path(cases_root) / case / rel
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise VetoConfigError(f"veto file {path} named in {case_yaml} does not exist") from e
    return parse_vetoes(text)
```

Replace `get_assert` with:

```python
def get_assert(output: str, context) -> dict:
    """promptfoo's Python assertion entry point -- the name is fixed by
    promptfoo (`getattr(script_module, "get_assert")`). Returns a
    GradingResult dict: {pass, score, reason}."""
    v = (
        context if isinstance(context, dict) else {"vars": getattr(context, "vars", {}) or {}}
    ).get("vars", {})
    role, agents_dir = v["role"], Path(v["agents_dir"])

    # Type validity first: an output that does not parse is broken whatever a
    # veto says, and a veto message about never-populated fields would only
    # obscure that.
    result = validates_as_output_type(output, role, agents_dir)
    if not result["pass"]:
        return result

    try:
        vetoes = load_vetoes(v["case"], role, Path(v["cases_root"]))
        validate_fields(vetoes, output_type_for(role, agents_dir))
    except VetoConfigError as e:
        return {"pass": False, "score": 0.0, "reason": f"veto configuration error: {e}"}

    failures = check(json.loads(output), vetoes)
    if failures:
        return {
            "pass": False,
            "score": 0.0,
            "reason": "; ".join(f"veto {f.veto_id}: {f.reason}" for f in failures),
        }
    return result
```

- [ ] **Step 4: Pass `cases_root` where the assertion can see it**

`config.py` already puts `cases_root` in `defaultTest.vars` (line 67), so `absolute.py` receives it with no config change. Confirm by reading `src/sdlc/eval/promptfoo/config.py:61-69` — no edit is needed if `"cases_root": str(cases_root)` is present.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_absolute_vetoes.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 6: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/eval/promptfoo/absolute.py tests/test_eval_absolute_vetoes.py tests/conftest.py
git commit -m "feat(eval): vetoes gate in the absolute tier (E-83)"
```

---

### Task 6: Vetoes reach Layer 3 (the benchmark judge)

This is the task a reviewer could reject while keeping Task 5: it changes the scale every stored `quality_score` was measured on. The discontinuity marker (`"staged_rubric"`) arrives in Task 8; this task carries the plumbing and the veto override.

**Files:**
- Modify: `src/sdlc/benchmarks/judge.py`
- Modify: `src/sdlc/models.py` (`BenchmarkConfig.vetoes`)
- Modify: `src/sdlc/benchmarks/workflow.py:164`
- Modify: `src/sdlc/workflows/feature.py:696`
- Test: `tests/test_benchmark_judge.py`

**Interfaces:**
- Consumes: `check`, `parse_vetoes`, `VetoConfigError` (Task 3).
- Produces:
  - `JudgeInput.vetoes_yaml: str = ""` — raw YAML text, empty means none.
  - `_build_judge_input(..., vetoes: dict[str, str] | None = None)` — same stage-keyed map shape as `rubrics`.
  - `BenchmarkConfig.vetoes: dict[str, str]` — stage → veto YAML **text** (the file contents, loaded by `load_case_assets`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_benchmark_judge.py`:

```python
def test_veto_failure_forces_score_zero_regardless_of_the_judge():
    """The judge's own number is overridden. This is the whole point: an
    LLM asked to enforce an absolute override inside a weighted mean does
    not reliably do it."""
    from sdlc.benchmarks.judge import JudgeInput, _set_judge_fn, judge_artifact

    _set_judge_fn(lambda _inp: '{"score": 0.95, "components": {"internal_consistency": 0.9}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true, "failing_tests": ["t::a"], "issues": []}',
                rubric="anything",
                author_model="anthropic:glm-5.2",
                judge_model="google:gemini-3.5-flash",
                vetoes_yaml="- id: internal_consistency\n"
                "  kind: not_both\n"
                "  field: tests_passed\n"
                "  equals: true\n"
                "  and_any_nonempty: [failing_tests, issues]\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score == 0.0
    assert qs.components["internal_consistency"] == 0.0


def test_no_vetoes_leaves_the_judge_score_untouched():
    from sdlc.benchmarks.judge import JudgeInput, _set_judge_fn, judge_artifact

    _set_judge_fn(lambda _inp: '{"score": 0.95, "components": {"a": 0.9}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true}',
                rubric="r",
                author_model="a",
                judge_model="b",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score == 0.95


def test_veto_wins_when_the_judge_errors():
    """A veto is a measurement that SUCCEEDED. Reporting not-measured would
    discard a real deterministic finding."""
    from sdlc.benchmarks.judge import JudgeInput, _set_judge_fn, judge_artifact

    def _boom(_inp):
        raise RuntimeError("judge down")

    _set_judge_fn(_boom)
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true, "issues": ["x"]}',
                rubric="r",
                author_model="a",
                judge_model="b",
                vetoes_yaml="- id: ic\n  kind: not_both\n  field: tests_passed\n"
                "  equals: true\n  and_any_nonempty: [issues]\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score == 0.0
    assert qs.judge != "error"


def test_malformed_vetoes_yaml_is_not_measured():
    """A veto file that does not parse is a config error, and a config error
    is NOT a zero -- it is an absent measurement."""
    from sdlc.benchmarks.judge import JudgeInput, _set_judge_fn, judge_artifact

    _set_judge_fn(lambda _inp: '{"score": 0.9, "components": {}}')
    try:
        qs = judge_artifact.sync(
            JudgeInput(
                artifact_json='{"tests_passed": true}',
                rubric="r",
                author_model="a",
                judge_model="b",
                vetoes_yaml="- id: v\n  kind: vibes\n",
            )
        )
    finally:
        _set_judge_fn(None)
    assert qs.score is None
    assert qs.judge == "error"


def test_build_judge_input_carries_the_stage_veto_text():
    ji = _build_judge_input(
        artifact_json="{}",
        rubrics={"qa": "rubric text"},
        stage="qa",
        author_model="a",
        judge_model="b",
        vetoes={"qa": "- id: v\n  kind: nonempty\n  fields: [x]\n"},
    )
    assert ji is not None
    assert "nonempty" in ji.vetoes_yaml


def test_build_judge_input_defaults_vetoes_to_empty():
    ji = _build_judge_input(
        artifact_json="{}", rubrics={"qa": "r"}, stage="qa", author_model="a", judge_model="b"
    )
    assert ji is not None
    assert ji.vetoes_yaml == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_benchmark_judge.py -k veto -v`
Expected: FAIL — `TypeError: JudgeInput.__init__() got an unexpected keyword argument 'vetoes_yaml'`.

- [ ] **Step 3: Add the field and the map parameter**

In `src/sdlc/benchmarks/judge.py`, add to the `JudgeInput` dataclass:

```python
    # E-83: raw YAML text of this stage's vetoes. A STRING, not parsed
    # objects: JudgeInput crosses a Temporal activity boundary, and plain
    # text serializes under any converter -- the same reason `rubric` and
    # `artifact_json` are strings. Empty means no vetoes.
    vetoes_yaml: str = ""
```

Extend `_build_judge_input`'s signature with `vetoes: dict[str, str] | None = None` and pass it through:

```python
    return JudgeInput(
        artifact_json=artifact_json,
        rubric=rubric,
        author_model=author_model,
        judge_model=judge_model,
        vetoes_yaml=(vetoes or {}).get(stage, ""),
    )
```

- [ ] **Step 4: Apply vetoes in `_judge_sync`**

Replace `_judge_sync` in `src/sdlc/benchmarks/judge.py`:

```python
def _judge_sync(inp: JudgeInput) -> QualityScore:
    # Vetoes FIRST and outside the judge's try: they are deterministic, so a
    # malformed veto file is a config error (not measured), while a veto that
    # FIRES is a measurement that succeeded and must survive a judge failure.
    try:
        vetoes = parse_vetoes(inp.vetoes_yaml)
        artifact = json.loads(inp.artifact_json) if vetoes else {}
        failures = check(artifact, vetoes) if vetoes else []
    except (VetoConfigError, json.JSONDecodeError):
        return QualityScore(score=None, judge="error")

    fn = _judge_fn or _default_judge
    try:
        payload = json.loads(fn(inp))
        score = max(0.0, min(1.0, float(payload.get("score", 0.0))))
        components = dict(payload.get("components") or {})
    except Exception:
        if not failures:
            return QualityScore(score=None, judge="error")
        # A veto fired. That IS a finding, and discarding it because the
        # advisory judge fell over would throw away the sharper signal.
        score, components = 0.0, {}

    if failures:
        for f in failures:
            components[f.veto_id] = 0.0
        score = 0.0
    return QualityScore(score=score, components=components, judge="llm_judge")
```

Add to the imports at the top of `judge.py`:

```python
from .vetoes import VetoConfigError, check, parse_vetoes
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark_judge.py -v`
Expected: PASS, including every pre-existing test — the `_set_judge_fn` seam is unchanged.

- [ ] **Step 6: Plumb vetoes from the case spec to the judge**

In `src/sdlc/models.py`, add to `BenchmarkConfig` below `rubrics` (line 797):

```python
vetoes: dict[str, str] = Field(default_factory=dict)  # stage -> veto YAML text
```

In `src/sdlc/benchmarks/workflow.py`, directly after the existing `load_case_assets` call at line 164, add a second call using the same generic activity — it reads `{stage: path}` into `{stage: text}` and does not care that the text is YAML:

```python
veto_assets = (
    await workflow.execute_activity(load_case_assets, args=[spec.case_id, dict(spec.vetoes)], **ACT)
    if spec.vetoes
    else {}
)
```

Then include `vetoes=veto_assets` wherever that function builds its `BenchmarkConfig`.

In `src/sdlc/workflows/feature.py:696`, add the map to the existing `_build_judge_input(...)` call:

```python
vetoes = (cfg.benchmark.vetoes,)
```

- [ ] **Step 7: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/benchmarks/judge.py src/sdlc/models.py src/sdlc/benchmarks/workflow.py src/sdlc/workflows/feature.py tests/test_benchmark_judge.py
git commit -m "feat(bench): vetoes override the judge at Layer 3 (E-83)"
```

---

## Phase 3 — The staged judge (spec §4.3)

### Task 7: Generate evaluation steps from a rubric, cached by sha

**Files:**
- Modify: `src/sdlc/benchmarks/judge.py`
- Test: `tests/test_staged_judge.py`

**Interfaces:**
- Consumes: `_run_judge_agent` (existing, `judge.py:77`).
- Produces: `generate_steps(rubric: str, judge_model: str) -> list[str]`, memoized on `(sha256(rubric), judge_model)`; `_clear_step_cache()` for tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_staged_judge.py`:

```python
"""The staged judge: rubric -> evaluation steps -> score.

A single-shot "score this against the rubric" prompt gave a gutted clarify
prompt 1.00 (OQ-P5). Generating explicit evaluation steps first is G-Eval's
actual mechanism, and the one half of it that works without logprobs --
which google:gemini-3.5-flash does not expose."""

import pytest

from sdlc.benchmarks import judge as judge_mod
from sdlc.benchmarks.judge import _clear_step_cache, generate_steps


@pytest.fixture(autouse=True)
def _clean_cache():
    _clear_step_cache()
    yield
    _clear_step_cache()


def test_generate_steps_parses_the_step_list(monkeypatch):
    calls = []

    def _fake(model, system_prompt, user_prompt):
        calls.append(model)
        return '{"steps": ["Check every activity is named", "Check red marking"]}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    steps = generate_steps("some rubric", "google:gemini-3.5-flash")
    assert steps == ["Check every activity is named", "Check red marking"]
    assert calls == ["google:gemini-3.5-flash"]


def test_generate_steps_is_cached_per_rubric_sha(monkeypatch):
    """One call per rubric per process. Baseline and working must be scored
    against IDENTICAL steps or the comparison is not a comparison."""
    calls = []

    def _fake(model, system_prompt, user_prompt):
        calls.append(user_prompt)
        return '{"steps": ["a"]}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    generate_steps("rubric one", "m")
    generate_steps("rubric one", "m")
    assert len(calls) == 1

    generate_steps("rubric two", "m")
    assert len(calls) == 2


def test_generate_steps_recaches_per_judge_model(monkeypatch):
    calls = []
    monkeypatch.setattr(
        judge_mod, "_run_judge_agent", lambda m, s, u: calls.append(m) or '{"steps": ["a"]}'
    )
    generate_steps("r", "model-a")
    generate_steps("r", "model-b")
    assert calls == ["model-a", "model-b"]


def test_generate_steps_raises_on_unparseable_output(monkeypatch):
    monkeypatch.setattr(judge_mod, "_run_judge_agent", lambda m, s, u: "not json")
    with pytest.raises(Exception):
        generate_steps("r", "m")


def test_generate_steps_raises_on_an_empty_step_list(monkeypatch):
    """Zero steps would silently degrade phase 2 back to the single-shot
    judge under the new label -- the discontinuity marker would then lie."""
    monkeypatch.setattr(judge_mod, "_run_judge_agent", lambda m, s, u: '{"steps": []}')
    with pytest.raises(Exception):
        generate_steps("r", "m")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_staged_judge.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_steps'`.

- [ ] **Step 3: Implement step generation**

In `src/sdlc/benchmarks/judge.py`, add below `_JUDGE_SYSTEM_PROMPT`:

```python
_STEPS_SYSTEM_PROMPT = (
    "You convert a grading rubric into an explicit, ordered checklist an "
    "impartial judge will follow. Each step must be a single concrete "
    "check, phrased so two judges would agree on whether it holds, and must "
    "name the rubric component it belongs to. Do not score anything. "
    "Respond with ONLY a JSON object of exactly this shape and nothing else "
    "(no prose, no markdown fences):\n"
    '  {"steps": ["<step>", "<step>", ...]}'
)

# (sha256(rubric), judge_model) -> steps. Baseline and working MUST be scored
# against identical steps or the A/B comparison is not a comparison; caching
# is what guarantees that within a process, and is why one rubric costs one
# generation call rather than one per artifact.
_STEP_CACHE: dict[tuple[str, str], list[str]] = {}


def _clear_step_cache() -> None:
    _STEP_CACHE.clear()


def generate_steps(rubric: str, judge_model: str) -> list[str]:
    """Phase 1: rubric text -> ordered evaluation steps.

    Raises on any failure. The caller turns that into
    QualityScore(score=None, judge="error") -- falling back to the raw rubric
    would silently restore the single-shot judge under the staged label.
    """
    key = (hashlib.sha256(rubric.encode()).hexdigest(), judge_model)
    if key in _STEP_CACHE:
        return _STEP_CACHE[key]
    raw = _run_judge_agent(judge_model, _STEPS_SYSTEM_PROMPT, f"Rubric:\n{rubric}")
    steps = json.loads(raw).get("steps") or []
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"step generation returned no steps for rubric sha {key[0][:12]}")
    _STEP_CACHE[key] = [str(s) for s in steps]
    return _STEP_CACHE[key]
```

Add `import hashlib` to the imports at the top of `judge.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_staged_judge.py -v`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/judge.py tests/test_staged_judge.py
git commit -m "feat(bench): phase-1 evaluation-step generation, cached by rubric sha (E-83)"
```

---

### Task 8: Score against the steps and flip the judge literal

**Files:**
- Modify: `src/sdlc/benchmarks/judge.py`
- Modify: `src/sdlc/benchmarks/models.py:57-58`
- Modify: `tests/test_judge_literal.py:13-16`
- Test: `tests/test_staged_judge.py`

**Interfaces:**
- Consumes: `generate_steps` (Task 7); veto application in `_judge_sync` (Task 6).
- Produces: `QualityScore.judge == "staged_rubric"` on every successful judgment from `_default_judge`. `JudgeFn` keeps its `Callable[[JudgeInput], str]` shape, so every existing `_set_judge_fn` test is unaffected.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_staged_judge.py`:

```python
def test_default_judge_runs_both_phases(monkeypatch):
    prompts = []

    def _fake(model, system_prompt, user_prompt):
        prompts.append(system_prompt)
        if "checklist" in system_prompt:
            return '{"steps": ["Check the six activities are all named"]}'
        assert "Check the six activities are all named" in user_prompt
        return '{"score": 0.4, "components": {"scope_preserved": 0.4}}'

    monkeypatch.setattr(judge_mod, "_run_judge_agent", _fake)
    qs = judge_mod.judge_artifact.sync(
        judge_mod.JudgeInput(
            artifact_json='{"summary": "x"}',
            rubric="the rubric",
            author_model="anthropic:glm-5.2",
            judge_model="google:gemini-3.5-flash",
        )
    )
    assert len(prompts) == 2
    assert qs.score == 0.4
    assert qs.judge == "staged_rubric"


def test_step_generation_failure_is_not_measured(monkeypatch):
    """NOT a fallback to the old judge: that would make the discontinuity
    marker lie about which instrument produced the number."""
    monkeypatch.setattr(judge_mod, "_run_judge_agent", lambda m, s, u: "garbage")
    qs = judge_mod.judge_artifact.sync(
        judge_mod.JudgeInput(artifact_json="{}", rubric="r", author_model="a", judge_model="b")
    )
    assert qs.score is None
    assert qs.judge == "error"


def test_injected_judge_fn_still_short_circuits_both_phases():
    """The _set_judge_fn seam is unchanged, so every existing test that
    injects a fake keeps working and makes no model call."""
    judge_mod._set_judge_fn(lambda _i: '{"score": 0.7, "components": {}}')
    try:
        qs = judge_mod.judge_artifact.sync(
            judge_mod.JudgeInput(artifact_json="{}", rubric="r", author_model="a", judge_model="b")
        )
    finally:
        judge_mod._set_judge_fn(None)
    assert qs.score == 0.7
    assert qs.judge == "staged_rubric"
```

And append to `tests/test_judge_literal.py`'s `EMITTED_JUDGES` list — replace the list with:

```python
EMITTED_JUDGES = [
    "contract",
    "llm_judge",
    "human_override",
    "error",
    "oracle",
    "deep_review",
    "adversary",
    "handoff",
    # E-83: the staged judge. "llm_judge" is retained, not retired -- every
    # record written before E-83 carries it, and that is exactly what makes
    # the measurement discontinuity queryable rather than silent.
    "staged_rubric",
]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_staged_judge.py::test_default_judge_runs_both_phases tests/test_judge_literal.py -v`
Expected: FAIL — the literal rejects `"staged_rubric"`, and `_default_judge` makes one call, not two.

- [ ] **Step 3: Add the literal**

In `src/sdlc/benchmarks/models.py`, replace the `judge` field on `QualityScore`:

```python
judge: Literal[
    "contract",
    "llm_judge",
    "human_override",
    "error",
    "oracle",
    "deep_review",
    "adversary",
    "handoff",
    "staged_rubric",
]
```

- [ ] **Step 4: Rewrite `_default_judge` as two phases**

In `src/sdlc/benchmarks/judge.py`, replace `_default_judge`:

```python
def _default_judge(inp: JudgeInput) -> str:
    """Production default: two staged calls on the configured cross-family
    judge model. Phase 1 turns the rubric into an explicit checklist (cached
    per rubric sha); phase 2 scores the artifact against that checklist.

    Returns the raw JSON string; parsing, clamping, veto application and
    error-handling live in _judge_sync.
    """
    if inp.judge_model is None:
        raise RuntimeError(
            "no judge_model configured; cannot run production judge "
            "(set BenchmarkConfig.judge_model or inject a fn via "
            "_set_judge_fn)"
        )
    steps = generate_steps(inp.rubric, inp.judge_model)
    checklist = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    user_prompt = (
        f"Evaluation steps:\n{checklist}\n\n"
        f"Rubric (for component names and weights):\n{inp.rubric}\n\n"
        f"Artifact:\n{inp.artifact_json}"
    )
    return _run_judge_agent(inp.judge_model, _JUDGE_SYSTEM_PROMPT, user_prompt)
```

- [ ] **Step 5: Update the score system prompt to reference the steps**

Replace `_JUDGE_SYSTEM_PROMPT` in `src/sdlc/benchmarks/judge.py`:

```python
_JUDGE_SYSTEM_PROMPT = (
    "You are an impartial quality judge. Work through the supplied "
    "evaluation steps in order and score the artifact against them. "
    "Respond with ONLY a JSON object of exactly this shape and nothing else "
    "(no prose, no markdown fences):\n"
    '  {"score": <float between 0.0 and 1.0>, '
    '"components": {<name>: <float between 0.0 and 1.0>}}\n'
    'The overall "score" must reflect the artifact\'s rubric compliance; '
    "each component score must be grounded in a named rubric criterion. "
    "Do not invent components the rubric does not name."
)
```

- [ ] **Step 6: Set the new literal in `_judge_sync`**

In `_judge_sync` (rewritten in Task 6, Step 4), change the final return's judge value:

```python
return QualityScore(score=score, components=components, judge="staged_rubric")
```

and in the veto-wins-on-judge-failure path, the same value is already produced by that final return.

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_staged_judge.py tests/test_judge_literal.py tests/test_benchmark_judge.py -v`
Expected: PASS.

- [ ] **Step 8: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS. If any test asserts `judge == "llm_judge"` on a *newly produced* score, update it to `"staged_rubric"`; do not change assertions about historical or hand-constructed records.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/benchmarks/judge.py src/sdlc/benchmarks/models.py tests/test_staged_judge.py tests/test_judge_literal.py
git commit -m "feat(bench): staged judge replaces the single-shot rubric prompt (E-83)"
```

---

### Task 9: Make the measurement discontinuity visible in scoring

**Files:**
- Modify: `src/sdlc/benchmarks/score.py`
- Test: `tests/test_score_judge_mix.py`

**Interfaces:**
- Consumes: `BenchmarkRecord`, `QualityScore.judge` (Task 8).
- Produces: `judge_mix_notes(records: list[BenchmarkRecord]) -> list[str]` — pure; one note per case whose scored records span more than one *scoring* judge kind.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_score_judge_mix.py`:

```python
"""Averaging across the E-83 judge change must be visible, not implicit.

Same discipline WasteBag applies to not-measured: a number whose provenance
changed mid-corpus is not the same number."""

from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    QualityScore,
    SpeedBag,
)
from sdlc.benchmarks.score import judge_mix_notes


def _rec(case, judge, score=0.8):
    return BenchmarkRecord(
        run_id="r1",
        bench_run_id="b1",
        case_id=case,
        scope=BenchmarkScope.STAGE,
        stage="clarify",
        role="clarify",
        model="m",
        quality=QualityScore(score=score, judge=judge),
        speed=SpeedBag(wall_clock_s=1.0),
        outcome=BenchmarkOutcome.PASS,
    )


def test_single_judge_kind_produces_no_note():
    assert judge_mix_notes([_rec("c1", "llm_judge"), _rec("c1", "llm_judge")]) == []


def test_mixed_judge_kinds_in_one_case_produce_a_note():
    notes = judge_mix_notes([_rec("c1", "llm_judge"), _rec("c1", "staged_rubric")])
    assert len(notes) == 1
    assert "c1" in notes[0]
    assert "llm_judge" in notes[0] and "staged_rubric" in notes[0]


def test_notes_are_per_case():
    notes = judge_mix_notes(
        [_rec("c1", "llm_judge"), _rec("c1", "staged_rubric"), _rec("c2", "staged_rubric")]
    )
    assert len(notes) == 1


def test_non_scoring_judges_do_not_count_as_a_mix():
    """'oracle', 'contract' and the lenses are different INSTRUMENTS, not
    two versions of one scale. Flagging them would cry wolf on every corpus."""
    assert (
        judge_mix_notes(
            [
                _rec("c1", "staged_rubric"),
                _rec("c1", "oracle"),
                _rec("c1", "deep_review"),
                _rec("c1", "contract"),
            ]
        )
        == []
    )


def test_unscored_records_are_ignored():
    assert judge_mix_notes([_rec("c1", "staged_rubric"), _rec("c1", "error", score=None)]) == []


def test_notes_are_ascii_only():
    """report.py:70-74 -- the notes block is ASCII."""
    notes = judge_mix_notes([_rec("c1", "llm_judge"), _rec("c1", "staged_rubric")])
    notes[0].encode("ascii")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_score_judge_mix.py -v`
Expected: FAIL — `ImportError: cannot import name 'judge_mix_notes'`.

- [ ] **Step 3: Implement the note builder**

In `src/sdlc/benchmarks/score.py`, add below `load_config_weights`:

```python
# The judge kinds that produce a rubric SCORE on one comparable scale. The
# lenses and the deterministic instruments are excluded: they are different
# instruments, not two versions of one scale, and flagging them would raise
# a warning on every corpus.
_SCORING_JUDGES = {"llm_judge", "staged_rubric"}


def judge_mix_notes(records) -> list[str]:
    """One note per case whose scored records span more than one scoring
    judge kind (E-83 spec 2.1).

    E-83 replaced the single-shot rubric judge with a staged one, which moves
    the scale quality_score is measured on. The `judge` field makes the
    boundary queryable; this makes averaging across it visible in report.md
    instead of implicit. Pure -- score.py owns the filesystem, not this.
    """
    from collections import defaultdict

    by_case = defaultdict(set)
    for r in records:
        if r.quality.score is None:
            continue
        if r.quality.judge in _SCORING_JUDGES:
            by_case[r.case_id].add(r.quality.judge)
    return [
        f"case {case}: quality scores span {len(kinds)} judge instruments "
        f"({', '.join(sorted(kinds))}) - E-83 changed the judge, so means "
        f"across this boundary mix two scales"
        for case, kinds in sorted(by_case.items())
        if len(kinds) > 1
    ]
```

- [ ] **Step 4: Wire the notes into the report**

In `write_score`, directly after `notes = list(ev.notes)`:

```python
    notes += judge_mix_notes(ev.records)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_score_judge_mix.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/benchmarks/score.py tests/test_score_judge_mix.py
git commit -m "feat(bench): report.md names the E-83 judge discontinuity (E-83)"
```

---

## Phase 4 — The mutation suite (spec §4.4)

### Task 10: A seam for injecting mutated instructions

Mutations must never edit `agents/<role>/instructions.md`: the gate resolves its baseline with `git show`, so a working-tree edit would move both sides.

**Files:**
- Modify: `src/sdlc/eval/promptfoo/provider.py:78-104`
- Modify: `src/sdlc/eval/promptfoo/config.py:33-60`
- Modify: `src/sdlc/eval/gate.py:59-114`
- Test: `tests/test_eval_mutation_seam.py`

**Interfaces:**
- Consumes: `run_gate`, `build_config`, `call_api` (all existing).
- Produces:
  - `build_config(..., mutation: str | None = None)` — when set, the **working** provider gets `config["instructions_text"]`; baseline is untouched.
  - `run_gate(..., mutation: str | None = None)` — when set, `prompt_sha_working` is the sha of the mutation text, so the unchanged-prompt early exit does not fire.
  - `call_api` prefers `config["instructions_text"]` over `instructions_ref`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_mutation_seam.py`:

```python
"""Mutations are injected, never written to the worktree.

run_gate resolves its baseline with `git show HEAD:agents/<role>/...`, so
editing the file on disk would move BOTH sides and measure nothing."""

from pathlib import Path

import yaml

from sdlc.agents.loader import _resolve_agents_dir
from sdlc.eval.promptfoo.config import build_config
from sdlc.eval.promptfoo.provider import call_api

_REPO = Path(__file__).resolve().parents[1]
_CASES = _REPO / "benchmarks" / "cases"


def test_mutation_lands_only_on_the_working_provider(tmp_path):
    cfg_path = build_config(
        "clarify",
        "add-login-greenfield",
        repo_root=_REPO,
        cases_root=_CASES,
        agents_dir=_resolve_agents_dir(),
        judge_model="google:gemini-3.5-flash",
        out_dir=tmp_path,
        mutation="Answer briefly.",
    )
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    baseline, working = cfg["providers"]
    assert baseline["label"] == "baseline"
    assert "instructions_text" not in baseline["config"]
    assert baseline["config"]["instructions_ref"] == "HEAD"
    assert working["config"]["instructions_text"] == "Answer briefly."


def test_no_mutation_leaves_the_config_unchanged(tmp_path):
    cfg_path = build_config(
        "clarify",
        "add-login-greenfield",
        repo_root=_REPO,
        cases_root=_CASES,
        agents_dir=_resolve_agents_dir(),
        judge_model="google:gemini-3.5-flash",
        out_dir=tmp_path,
    )
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    for p in cfg["providers"]:
        assert "instructions_text" not in p["config"]


def test_call_api_prefers_literal_text_over_the_git_ref(monkeypatch, tmp_path):
    """No model call and no `git show`: the literal body must win outright."""
    import sdlc.eval.promptfoo.provider as prov

    seen = {}

    class _Usage:
        input_tokens = 1
        output_tokens = 1
        cache_read_tokens = 0
        cache_write_tokens = 0

    def _fake_run_variant_detailed(role, instructions, fixture, agents_dir, *, model_override=None):
        seen["instructions"] = instructions
        return "{}", _Usage()

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "resolve_instructions must not be called when instructions_text is supplied"
        )

    monkeypatch.setattr(prov, "run_variant_detailed", _fake_run_variant_detailed)
    monkeypatch.setattr(prov, "resolve_instructions", _must_not_be_called)

    # EvalFixture requires role, case, prompt, model, source_run_id.
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        '{"role": "clarify", "case": "add-login-greenfield", '
        '"prompt": "p", "model": "anthropic:glm-5.2", '
        '"source_run_id": "test"}',
        encoding="utf-8",
    )

    out = call_api(
        "",
        {
            "config": {
                "role": "clarify",
                "fixture_path": str(fixture_path),
                "agents_dir": str(_resolve_agents_dir()),
                "repo_root": str(_REPO),
                "instructions_ref": "HEAD",
                "instructions_text": "Answer briefly.",
            }
        },
        {},
    )
    assert out["error"] is None
    assert seen["instructions"] == "Answer briefly."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_eval_mutation_seam.py -v`
Expected: FAIL — `TypeError: build_config() got an unexpected keyword argument 'mutation'`.

- [ ] **Step 3: Add the provider override**

In `src/sdlc/eval/promptfoo/provider.py`, inside `call_api`'s `try:` block, replace the `instructions = resolve_instructions(...)` call with:

```python
# A literal instructions body wins over the git ref. This is the
# mutation seam (E-83): the suite must degrade a prompt WITHOUT
# touching agents/<role>/instructions.md, because the baseline side
# is resolved with `git show` and a worktree edit would move both.
literal = cfg.get("instructions_text")
instructions = (
    literal
    if literal is not None
    else resolve_instructions(
        cfg["role"], cfg["instructions_ref"], Path(cfg["repo_root"]), agents_dir
    )
)
```

- [ ] **Step 4: Thread the mutation through `build_config`**

In `src/sdlc/eval/promptfoo/config.py`, add `mutation: str | None = None` to `build_config`'s keyword-only parameters, and replace the `providers` list with:

```python
    working_cfg = {**provider_cfg, "instructions_ref": "worktree"}
    if mutation is not None:
        working_cfg["instructions_text"] = mutation
```

```python
        "providers": [
            {"id": provider_id, "label": "baseline",
             "config": {**provider_cfg, "instructions_ref": baseline_ref}},
            {"id": provider_id, "label": "working", "config": working_cfg},
        ],
```

- [ ] **Step 5: Thread the mutation through `run_gate`**

In `src/sdlc/eval/gate.py`, add `mutation: str | None = None` to `run_gate`'s keyword-only parameters. Replace the `sha_work` assignment:

```python
sha_base = prompt_sha(role, baseline_ref, repo_root, agents_dir)
# A mutation IS the working-tree prompt for this run. Hashing it rather
# than the file is what stops the unchanged-prompt early exit from
# skipping the whole suite.
sha_work = (
    hashlib.sha256(mutation.encode()).hexdigest()
    if mutation is not None
    else prompt_sha(role, "worktree", repo_root, agents_dir)
)
```

and pass it to `build_config`:

```python
cfg = build_config(
    role,
    case,
    repo_root=repo_root,
    cases_root=cases_root,
    agents_dir=agents_dir,
    judge_model=judge_model,
    out_dir=tmp_path,
    repeat=repeat,
    baseline_ref=baseline_ref,
    mutation=mutation,
)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_mutation_seam.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/eval/promptfoo/provider.py src/sdlc/eval/promptfoo/config.py src/sdlc/eval/gate.py tests/test_eval_mutation_seam.py
git commit -m "feat(eval): inject mutated instructions without touching the worktree (E-83)"
```

---

### Task 11: The mutation suite — the increment's acceptance criterion

This is the deliverable that converts "operational" into "sensitive". It spends tokens and is opt-in.

**Files:**
- Create: `tests/test_prompt_gate_mutations.py`
- Test: itself

**Interfaces:**
- Consumes: `run_gate(..., mutation=...)` (Task 10); vetoes at Layer 2 (Task 5); the staged judge (Task 8).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the suite**

Create `tests/test_prompt_gate_mutations.py`:

```python
"""The sensitivity proof (E-83 spec 4.4).

OQ-P5 asked: "what prompt degradation would this gate actually catch?" An
assertion is not an answer. This suite answers it by degrading a prompt in
known ways and requiring the gate to notice.

Opt-in and token-spending, exactly like the gate it exercises:
    SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval -k mutations
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sdlc.agents.loader import _resolve_agents_dir
from sdlc.eval.cli import default_judge_model
from sdlc.eval.gate import run_gate
from sdlc.eval.verdict import GateVerdict

pytestmark = pytest.mark.prompt_eval

_REPO = Path(__file__).resolve().parents[1]
_CASES = _REPO / "benchmarks" / "cases"
_CASE = "cat-cafe-monitoring"
_ROLE = "clarify"

# Degradations, each targeting a different failure the gate should catch.
_TRUNCATED = "Answer briefly."

_SCOPE_DROPPED = """You clarify a feature request into structured requirements.

Cover ONLY these cat activities: sleeping, eating, and drinking. Do not
mention any other activity. Keep the output short.

Fill every field of the output schema.
"""

_INVERTED = """You clarify a feature request into structured requirements.

Produce open questions, but do NOT suggest an answer to any of them -- leave
every suggested answer empty. Do not list anything as out of scope.
"""


def _gate(mutation: str | None):
    return run_gate(
        _ROLE,
        _CASE,
        repo_root=_REPO,
        cases_root=_CASES,
        agents_dir=_resolve_agents_dir(),
        judge_model=default_judge_model(),
        repeat=3,
        mutation=mutation,
    )


@pytest.mark.skipif(
    os.getenv("SDLC_PROMPT_EVAL") != "1", reason="spends tokens; set SDLC_PROMPT_EVAL=1"
)
def test_control_passes_and_costs_nothing():
    """The unchanged prompt must not fail. A gate that fails its own control
    is measuring noise, and nothing below it is interpretable."""
    r = _gate(None)
    assert r.verdict is GateVerdict.PASS
    assert "unchanged" in r.reason


@pytest.mark.skipif(
    os.getenv("SDLC_PROMPT_EVAL") != "1", reason="spends tokens; set SDLC_PROMPT_EVAL=1"
)
def test_scope_dropped_fails_absolutely():
    """The proof that E-83 gave the gate teeth.

    This must fail via FAIL_ABSOLUTE -- the scope_preserved veto -- not via
    the advisory judge. A judge-mediated failure here would be luck; the
    veto is deterministic."""
    r = _gate(_SCOPE_DROPPED)
    assert r.verdict is GateVerdict.FAIL_ABSOLUTE, r.reason
    assert any("scope_preserved" in f for f in r.absolute_failures), r.absolute_failures


@pytest.mark.skipif(
    os.getenv("SDLC_PROMPT_EVAL") != "1", reason="spends tokens; set SDLC_PROMPT_EVAL=1"
)
def test_inverted_instruction_is_caught():
    """out_of_scope emptied by instruction trips scope_discipline_declared."""
    r = _gate(_INVERTED)
    assert r.verdict in (GateVerdict.FAIL_ABSOLUTE, GateVerdict.FAIL_REGRESSION), r.reason


@pytest.mark.skipif(
    os.getenv("SDLC_PROMPT_EVAL") != "1", reason="spends tokens; set SDLC_PROMPT_EVAL=1"
)
def test_truncated_prompt_outcome_is_recorded_either_way():
    """OQ-P5's original case, and the one this suite does NOT presume.

    If it still passes with vetoes and the staged judge in place, that is a
    FINDING about structured-output roles -- output_type tool-calling plus
    the schema's own field descriptions carry the instruction -- not a bug.
    The test records which it was; it fails only if the gate could not run.
    """
    r = _gate(_TRUNCATED)
    assert r.verdict is not GateVerdict.ERRORED, r.reason
    print(f"\nOQ-P5 truncated-prompt outcome: {r.verdict.value} - {r.reason}")
    print(f"  baseline scores: {r.scores_baseline}")
    print(f"  working  scores: {r.scores_working}")
```

- [ ] **Step 2: Verify the suite is skipped by default**

Run: `python -m pytest -q tests/test_prompt_gate_mutations.py`
Expected: 4 deselected/skipped, 0 failed — the `prompt_eval` marker is excluded by `addopts` in `pyproject.toml:47`.

- [ ] **Step 3: Run the suite for real**

Run: `SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval -k mutations -v -s`

(PowerShell: `$env:SDLC_PROMPT_EVAL=1; python -m pytest -m prompt_eval -k mutations -v -s`)

Expected: `test_control_passes_and_costs_nothing` and `test_scope_dropped_fails_absolutely` PASS. Record the printed OQ-P5 outcome — it is the answer to the increment's central question.

- [ ] **Step 4: Record the OQ-P5 outcome in the spec**

Append the observed result to the `OQ-P5` bullet in `docs/superpowers/specs/2026-08-12-judge-sensitivity-and-plan-adherence-design.md` §9, stating the verdict, the scores from both sides, and whether the gate is now demonstrably sensitive. If `truncated` still passes, write that as a finding about structured-output roles — do not soften it and do not treat it as a failure of the increment.

- [ ] **Step 5: Commit**

```bash
# NOT runs/prompt_evals/ -- runs/ is gitignored (.gitignore:4). The evidence
# lives in the spec's OQ-P5 entry, which is why Step 4 writes the numbers
# into it rather than relying on the record files surviving.
git add tests/test_prompt_gate_mutations.py docs/superpowers/specs/2026-08-12-judge-sensitivity-and-plan-adherence-design.md
git commit -m "test(eval): mutation suite proves gate sensitivity; record OQ-P5 outcome (E-83)"
```

---

## Phase 5 — Plan adherence (spec §5)

### Task 12: `PlanDrift` — the deterministic core

**Files:**
- Modify: `src/sdlc/models.py`
- Modify: `src/sdlc/benchmarks/models.py:108-128`
- Modify: `src/sdlc/workflows/feature.py:576-601`
- Test: `tests/test_plan_drift.py`

**Interfaces:**
- Consumes: `DevTask.files_hint` (`models.py:312`).
- Produces:
  - `PlanDrift` in `src/sdlc/models.py`.
  - `compute_plan_drift(task: DevTask, files_touched: list[str]) -> PlanDrift | None` in `src/sdlc/models.py`.
  - `BenchmarkRecord.plan_drift: PlanDrift | None = None`.
  - `_stage_record(..., plan_drift: "PlanDrift | None" = None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plan_drift.py`:

```python
"""Plan drift: what the planner expected to be touched vs what was.

A SIGNAL, never a gate. files_hint is named a hint; a planner that guessed
wrong is a normal outcome, and the drift is interesting precisely because it
is not an error."""

from sdlc.models import DevTask, compute_plan_drift


def _task(**kw):
    return DevTask(id="t1", title="t", description="d", acceptance_criteria=["ac"], **kw)


def test_exact_adherence_reports_zero_drift():
    d = compute_plan_drift(_task(files_hint=["a.py", "b.py"]), ["a.py", "b.py"])
    assert d is not None
    assert d.files_hinted == 2
    assert d.files_touched == 2
    assert d.hinted_untouched == []
    assert d.touched_unhinted == []


def test_unhinted_file_is_reported():
    d = compute_plan_drift(_task(files_hint=["a.py"]), ["a.py", "c.py"])
    assert d.touched_unhinted == ["c.py"]
    assert d.hinted_untouched == []


def test_hinted_but_untouched_file_is_reported():
    d = compute_plan_drift(_task(files_hint=["a.py", "b.py"]), ["a.py"])
    assert d.hinted_untouched == ["b.py"]


def test_lists_are_sorted_for_stable_records():
    d = compute_plan_drift(_task(files_hint=[]), ["z.py", "a.py"])
    assert d.touched_unhinted == ["a.py", "z.py"]


def test_paths_are_compared_normalised():
    """A planner writing 'src\\\\app.py' and a diff reporting 'src/app.py' is
    the same file. Reporting it as drift would manufacture a finding."""
    d = compute_plan_drift(_task(files_hint=["src\\app.py"]), ["src/app.py"])
    assert d.hinted_untouched == []
    assert d.touched_unhinted == []


def test_no_hint_is_not_measured():
    """An empty files_hint means the planner made no prediction. Zero drift
    would claim perfect adherence to a prediction that was never made."""
    assert compute_plan_drift(_task(files_hint=[]), ["a.py"]) is None


def test_no_diff_is_not_measured():
    assert compute_plan_drift(_task(files_hint=["a.py"]), []) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plan_drift.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_plan_drift'`.

- [ ] **Step 3: Add the model and the computation**

In `src/sdlc/models.py`, directly below `DevTask` (after line 318):

```python
class PlanDrift(BaseModel):
    """Deterministic plan-vs-execution drift for one task (E-83).

    None on a record means NOT MEASURED. An all-zero PlanDrift would be
    indistinguishable from a task that executed exactly to plan -- the same
    rule WasteBag states for its own bag.

    A SIGNAL, never a gate: `files_hint` is named a hint, and a planner that
    guessed wrong is a normal outcome. What it measures is planner
    calibration across many runs, not any single run's correctness.
    """

    files_hinted: int
    files_touched: int
    hinted_untouched: list[str] = Field(default_factory=list)
    touched_unhinted: list[str] = Field(default_factory=list)


def _norm_path(p: str) -> str:
    """Windows-authored hints and POSIX diff paths name the same file."""
    return p.replace("\\", "/").strip().lstrip("./")


def compute_plan_drift(task: "DevTask", files_touched: list[str]) -> PlanDrift | None:
    """Pure. None when either side is absent -- a prediction that was never
    made cannot be adhered to, and a diff that does not exist cannot be
    compared."""
    if not task.files_hint or not files_touched:
        return None
    hinted = {_norm_path(p) for p in task.files_hint}
    touched = {_norm_path(p) for p in files_touched}
    return PlanDrift(
        files_hinted=len(hinted),
        files_touched=len(touched),
        hinted_untouched=sorted(hinted - touched),
        touched_unhinted=sorted(touched - hinted),
    )
```

- [ ] **Step 4: Carry it on the record**

In `src/sdlc/benchmarks/models.py`, add to `BenchmarkRecord` below `waste` (line 125):

```python
plan_drift: "PlanDrift | None" = None  # None = not measured (E-83)
```

and add the import at the top of the file:

```python
from ..models import PlanDrift
```

In `src/sdlc/workflows/feature.py`, add `plan_drift: "PlanDrift | None" = None` to `_stage_record`'s keyword parameters (below `waste`, line 585) and `plan_drift=plan_drift,` to the `BenchmarkRecord(...)` construction (below `waste=waste,`, line 599).

- [ ] **Step 5: Populate it at the code stage**

In `src/sdlc/workflows/feature.py`, at the code-stage `_stage_record(...)` call that already passes `waste=`, add:

```python
plan_drift = (compute_plan_drift(task, diff.get("files", [])),)
```

Import `compute_plan_drift` and `PlanDrift` inside the existing `workflow.unsafe.imports_passed_through()` block alongside the other `sdlc.models` imports. If the materialized diff dict does not carry a `files` key, derive it from the same source `HandoffSummary.files_touched` uses — the workflow-computed file list, never a model-reported one.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_plan_drift.py -q && python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/models.py src/sdlc/benchmarks/models.py src/sdlc/workflows/feature.py tests/test_plan_drift.py
git commit -m "feat(bench): deterministic PlanDrift on the code-stage record (E-83)"
```

---

### Task 13: Plan deviations in the `deep_review` lens

Not a new lens. `heatmap.py:16-21` warns that accumulating lenses costs the stage axis its meaning; `deep_review` already loads the transcript, already receives the contract assertions, and already runs once per task.

**Files:**
- Modify: `src/sdlc/models.py` (`PlanDeviation`, `DeepReviewReport`)
- Modify: `src/sdlc/handoff.py:91-115`
- Modify: `src/sdlc/workflows/feature.py:952-1016`
- Modify: `agents/deep_review/instructions.md`
- Test: `tests/test_plan_deviations.py`

**Interfaces:**
- Consumes: `verify_quote`, `Profile.VERBATIM_BYTES` (existing in `handoff.py`).
- Produces:
  - `PlanDeviation` in `src/sdlc/models.py`.
  - `DeepReviewReport.plan_deviations: list[PlanDeviation]`.
  - `verified_plan_deviations(deviations, session_text) -> tuple[list[PlanDeviation], int]` in `src/sdlc/handoff.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_plan_deviations.py`:

```python
"""Plan deviations ride the deep_review lens and obey its evidence rule.

An accusation must quote a line the transcript actually contains. Dropping,
never failing -- this lens must never fail delivery."""

from sdlc.handoff import verified_plan_deviations
from sdlc.models import PlanDeviation

_TRANSCRIPT = "file_read src/app.py\nfile_write src/billing.py\ncommand pytest -q exit=0\n"


def _dev(evidence, kind="unplanned_scope"):
    return PlanDeviation(kind=kind, detail="d", evidence=evidence)


def test_deviation_with_real_evidence_is_kept():
    kept, dropped = verified_plan_deviations([_dev("file_write src/billing.py")], _TRANSCRIPT)
    assert len(kept) == 1
    assert dropped == 0


def test_deviation_with_invented_evidence_is_dropped():
    kept, dropped = verified_plan_deviations([_dev("file_write src/nowhere.py")], _TRANSCRIPT)
    assert kept == []
    assert dropped == 1


def test_paraphrased_evidence_is_dropped():
    kept, dropped = verified_plan_deviations(
        [_dev("the agent wrote to the billing module")], _TRANSCRIPT
    )
    assert kept == []
    assert dropped == 1


def test_empty_evidence_survives():
    """Same three rules as verified_integrity_flags: an empty quote survives."""
    kept, dropped = verified_plan_deviations([_dev("")], _TRANSCRIPT)
    assert len(kept) == 1
    assert dropped == 0


def test_missing_transcript_skips_verification():
    kept, dropped = verified_plan_deviations([_dev("anything")], None)
    assert len(kept) == 1
    assert dropped == 0


def test_report_defaults_to_no_deviations():
    from sdlc.models import DeepReviewReport

    assert DeepReviewReport().plan_deviations == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plan_deviations.py -v`
Expected: FAIL — `ImportError: cannot import name 'PlanDeviation'`.

- [ ] **Step 3: Add the model**

In `src/sdlc/models.py`, directly above `DeepReviewReport` (before line 577):

```python
class PlanDeviation(BaseModel):
    """One way the session departed from the task it was given (E-83).

    Evidence-first, exactly like IntegrityFlag: a deviation whose quote is
    not in the transcript is dropped, because an advisory lens that can
    invent evidence is worse than no lens.
    """

    kind: Literal["unplanned_scope", "skipped_criterion", "approach_changed"]
    detail: str
    evidence: str  # a VERBATIM span from the scrubbed transcript
```

Add to `DeepReviewReport`, below `integrity_flags`:

```python
    plan_deviations: list[PlanDeviation] = Field(default_factory=list)
```

- [ ] **Step 4: Add the verifier**

In `src/sdlc/handoff.py`, below `verified_integrity_flags` (after line 115):

```python
def verified_plan_deviations(
    deviations: list[PlanDeviation],
    session_text: str | None,
) -> tuple[list[PlanDeviation], int]:
    """Drop plan deviations whose evidence quote is not in the transcript
    (E-83). Returns (kept, dropped).

    Identical rules to verified_integrity_flags, for the identical reason:
    an empty quote survives, a missing haystack skips verification, and the
    profile is VERBATIM_BYTES because a stored transcript is bytes we wrote.
    """
    if session_text is None:
        return list(deviations), 0
    kept: list[PlanDeviation] = []
    dropped = 0
    for d in deviations:
        if d.evidence.strip() and not verify_quote(
            d.evidence, session_text, Profile.VERBATIM_BYTES
        ):
            dropped += 1
            continue
        kept.append(d)
    return kept, dropped
```

Add `PlanDeviation` to the `sdlc.models` import at the top of `handoff.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_plan_deviations.py -v`
Expected: PASS, all 6 tests.

- [ ] **Step 6: Give the lens the task and verify its deviations**

In `src/sdlc/workflows/feature.py`, in `_run_deep_review`, extend the prompt (currently lines 975-978) to include the task:

```python
                "Frozen contract assertions:\n- " + "\n- ".join(assertions)
                + f"\nThe task as planned:\n{task.model_dump_json()}"
                + f"\nDiff:\n{diff['patch']}"
                + "\nScrubbed harness transcript (how the diff was reached):\n"
                + transcript, into=spend)).output
```

Directly after the existing `verified_integrity_flags` block (lines 983-990), add:

```python
kept_devs, dropped_devs = verified_plan_deviations(report.plan_deviations, transcript)
if dropped_devs:
    workflow.logger.warning(
        "deep_review: dropped %d plan deviation(s) for task %s "
        "whose evidence is not in the transcript",
        dropped_devs,
        task.id,
    )
```

and extend the existing `report.model_copy(update=...)` call to carry both:

```python
report = report.model_copy(update={"integrity_flags": kept_flags, "plan_deviations": kept_devs})
```

Add `verified_plan_deviations` to the `sdlc.handoff` import at `feature.py:88`.

- [ ] **Step 7: Extend the lens instructions**

Append to `agents/deep_review/instructions.md`, before the final advisory paragraph:

```
You also receive the task as it was planned — its title, description,
acceptance criteria, and the files the planner expected to be touched. Report
each departure from it as a plan_deviation with its kind, a detail, and a
VERBATIM span from the transcript as evidence:
- unplanned_scope: the session did substantial work the task did not ask for.
- skipped_criterion: an acceptance criterion has no corresponding work in the
  session or the diff.
- approach_changed: the session solved the task a materially different way
  than the description sets out.

Deviating from files_hint is NOT itself a deviation — it is a hint, and the
drift is measured deterministically elsewhere. Report a deviation only when
the task's stated intent was departed from, and quote the transcript exactly:
a paraphrase is discarded automatically.
```

- [ ] **Step 8: Run the full fast suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/models.py src/sdlc/handoff.py src/sdlc/workflows/feature.py agents/deep_review/instructions.md tests/test_plan_deviations.py
git commit -m "feat(review): deep_review reports verified plan deviations (E-83)"
```

---

### Task 14: Documentation

**Files:**
- Modify: `README.md:95-104`
- Modify: `BENCHMARK.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Update the README prompt-gate paragraph**

In `README.md`, in the "Prompt changes are gated (E-82)" bullet, replace the sentence describing the absolute tier with:

```
Deterministic checks — output validates as the role's `output_type`,
per-case rubric **vetoes** (`benchmarks/cases/<case>/vetoes-*.yaml`),
cost/latency budgets — are absolute and gate; the cross-family judge is
staged (rubric → evaluation steps → score) and advisory, failing only on a
regression past a noise-aware floor. Sensitivity is proven by the mutation
suite: `SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval -k mutations`.
```

- [ ] **Step 2: Record the increment in BENCHMARK.md**

Add an E-83 entry to the increment list describing: the veto vocabulary and where veto files live, the staged judge, the `staged_rubric` judge value and the measurement discontinuity it marks, `PlanDrift`, and the `deep_review` plan-deviation extension. State plainly that quality scores from before and after E-83 sit on different scales and that `report.md` names the boundary.

- [ ] **Step 3: Record OQ-P6/OQ-P7/OQ-P8 in ROADMAP.md**

Add the three new open questions from the spec's §9 to the roadmap's open-question list, and mark OQ-P5 with its Task 11 outcome.

- [ ] **Step 4: Commit**

```bash
git add README.md BENCHMARK.md ROADMAP.md
git commit -m "docs: record E-83 vetoes, staged judge, and plan drift"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §4.1 instrument fixes | 1, 2 |
| §4.2 vetoes (vocabulary, engine) | 3 |
| §4.2 veto authorship + registration | 4 |
| §4.2 Layer 2 teeth | 5 |
| §4.2 Layer 3 override | 6 |
| §4.3 staged judge phase 1 | 7 |
| §4.3 staged judge phase 2 + literal | 8 |
| §2.1 discontinuity visible in scoring | 9 |
| §4.4 mutation seam | 10 |
| §4.4 mutation suite | 11 |
| §5.1 `PlanDrift` | 12 |
| §5.2 `deep_review` extension | 13 |
| §6 error handling | Task 3 (config errors), Task 5 (Layer 2 paths), Task 6 (not-measured vs veto-wins), Task 12/13 (`None` = not measured, drop-never-fail) |
| §7 testing | every task's steps 1-2 |
| Docs | 14 |

No gaps.

**Placeholder scan:** every code step carries runnable code; no "TBD", no "add error handling", no "similar to Task N".

**Type consistency:** `Veto` / `VetoFailure` / `VetoConfigError` / `parse_vetoes` / `check` / `validate_fields` (Task 3) are used under those exact names in Tasks 4, 5, 6. `JudgeInput.vetoes_yaml` (Task 6) is read by `_judge_sync` in Tasks 6 and 8. `generate_steps` / `_clear_step_cache` (Task 7) are used in Task 8. `compute_plan_drift` / `PlanDrift` (Task 12) are used in Task 12 only. `PlanDeviation` / `verified_plan_deviations` (Task 13) match between model, verifier, and workflow. `judge_mix_notes` (Task 9) is defined and called in `score.py` alone. `"staged_rubric"` is spelled identically in Tasks 8, 9, and the Global Constraints.

**Ordering note:** Task 6 sets `judge="llm_judge"` and Task 8 changes it to `"staged_rubric"`. That is deliberate — Task 6 is reviewable on the veto override alone, and a reviewer can reject Task 8's scale change without losing Task 6.
