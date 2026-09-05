# promptfoo Prompt Gate (E-82) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a prompt regression gate that A/B-scores a working-tree `instructions.md` against its committed baseline, using promptfoo as the runner while every judgment that carries project meaning stays in Kroker's code.

**Architecture:** Extract the six inline prompt-composition expressions from `feature.py` into a pure `src/sdlc/prompts.py`, called by both production and a deterministic fixture generator — so fixtures cannot drift from what the pipeline actually sends. promptfoo drives the eval loop through a Python custom provider wrapping `run_variant()`; deterministic assertions are absolute and gate, the cross-family judge is advisory, and the cross-provider regression verdict is computed by Kroker from promptfoo's `--output results.json` (promptfoo structurally cannot compare across providers). The gate surfaces as a `prompt_eval`-marked pytest test, opt-in via an env var, reusing the repo's existing `live` convention.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, promptfoo (MIT, `pip install promptfoo`), Pydantic AI, PyYAML.

## Global Constraints

- **Design doc:** `docs/superpowers/specs/2026-08-11-promptfoo-prompt-gate-design.md`. Read it before starting.
- **A default `pytest` run must make ZERO model calls.** Every task except 10 is tested with fakes/`TestModel`. Never add a test that calls a real model outside the `prompt_eval` marker.
- **`prompts.py` output must be byte-identical to the current inline expressions.** This is the only change that can break production. Characterization tests come before the swap.
- **ADR-6:** the judge model's family must differ from the author model's family. `model_family()` lives at `src/sdlc/agents/loader.py:71`. An ADR-6 violation is a hard failure, never degraded to advisory.
- **Not-measured ≠ passed.** A judge that errored must render as `unavailable`, never as "no regression".
- **Prompt-gate results NEVER enter the `BenchmarkRecord` stream.** They are written to `runs/prompt_evals/` and joined to benchmarks only by `prompt_sha`. Do not import `benchmarks.recorder` or emit `BenchmarkRecord` anywhere in this work.
- **promptfoo goes in a NEW `eval` extra**, not `dev`.
- `feature.py` is Temporal workflow code. New imports go inside the existing `with workflow.unsafe.imports_passed_through():` block at `feature.py:16`.
- Re-run `pip install -e .` after adding any new module — setuptools' editable wheel does not auto-discover new files.
- Role models are `anthropic:glm-5.2` (family `anthropic`); `benchmarks/config.yaml` has `default_judge_model: openai/gpt-5.2` (family `openai`). These satisfy ADR-6.

---

## File Structure

**Created:**
- `src/sdlc/prompts.py` — six pure prompt builders + two shared block helpers. No I/O.
- `src/sdlc/eval/promptfoo/__init__.py`
- `src/sdlc/eval/promptfoo/provider.py` — promptfoo custom provider → `run_variant()`.
- `src/sdlc/eval/promptfoo/assertion.py` — promptfoo custom assertion → `judge_artifact()` + ADR-6.
- `src/sdlc/eval/promptfoo/absolute.py` — output-type validation assertion.
- `src/sdlc/eval/promptfoo/config.py` — generates `promptfooconfig.yaml`.
- `src/sdlc/eval/verdict.py` — pure verdict + noise floor over a results dict.
- `benchmarks/cases/cat-cafe-monitoring/seeds/architecture.json`, `assertions.json`, `qa_raw.json`, `diff.json`
- `tests/test_prompts_characterization.py`, `test_eval_fixture_build.py`, `test_promptfoo_provider.py`, `test_promptfoo_assertion.py`, `test_promptfoo_absolute.py`, `test_promptfoo_config.py`, `test_eval_verdict.py`, `test_promptfoo_contract.py`, `test_prompt_gate.py`

**Modified:**
- `src/sdlc/workflows/feature.py` — six call sites swapped.
- `src/sdlc/eval/fixtures.py` — `build_fixture()` added; capture half removed.
- `src/sdlc/eval/cli.py` — shells to promptfoo; `run_capture` removed.
- `src/sdlc/cli.py` — `eval` parser gains `--gate`/`--view`; `capture` target removed.
- `pyproject.toml` — `eval` extra + `prompt_eval` marker.

**Deleted:**
- `src/sdlc/eval/compare.py` (logic migrates to `assertion.py` + `verdict.py`)

---

### Task 1: Pure prompt builders (additive — production untouched)

**Files:**
- Create: `src/sdlc/prompts.py`
- Test: `tests/test_prompts_characterization.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `clarify_prompt(idea_json: str, memory: Sequence[str]) -> str`, `planner_prompt(arch_json: str, memory: Sequence[str], guidance: str | None) -> str`, `qa_prompt(assertions: Sequence[str], qa_raw_json: str, diff_stat: str, diff_patch: str) -> str`, `reviewer_prompt(assertions: Sequence[str], qa_raw_json: str, diff_patch: str) -> str`, `analyst_prompt(criteria_lines: str, qa_lines: str, diff_stat: str, diff_patch: str) -> str`, `merge_verdict_prompt(task_results: Sequence[dict]) -> str`

This task is purely additive: it creates the module and proves each function reproduces the current inline expression byte-for-byte. `feature.py` is not touched until Task 2.

- [ ] **Step 1: Write the failing characterization tests**

Create `tests/test_prompts_characterization.py`. Each expected value is the **current inline expression from `feature.py`, transcribed literally** — that is what makes these characterization tests rather than guesses.

```python
"""Characterization: prompts.py must reproduce feature.py's inline
expressions byte-for-byte. Expected values are transcribed from the
current source, NOT re-derived. See feature.py:1893, :2040, :1403,
:1414, :2192, :2360."""

from __future__ import annotations

from sdlc.prompts import (
    analyst_prompt,
    clarify_prompt,
    merge_verdict_prompt,
    planner_prompt,
    qa_prompt,
    reviewer_prompt,
)

IDEA = '{"title":"T","description":"D"}'
ARCH = '{"stack":"python"}'


def test_clarify_no_memory():
    # feature.py:1893 -- idea.model_dump_json() + ("" when no items)
    assert clarify_prompt(IDEA, []) == IDEA


def test_clarify_with_memory():
    assert clarify_prompt(IDEA, ["a", "b"]) == (IDEA + "\nRelevant memory:\n- a\n- b")


def test_planner_no_memory_no_guidance():
    assert planner_prompt(ARCH, [], None) == ARCH


def test_planner_memory_and_guidance():
    assert planner_prompt(ARCH, ["m1"], "fix it") == (
        ARCH + "\nRelevant memory:\n- m1" + "\nRevision guidance from reviewer:\nfix it"
    )


def test_planner_guidance_empty_string_is_omitted():
    # feature.py uses `if guidance else ""` -- "" is falsy, so no block.
    assert planner_prompt(ARCH, [], "") == ARCH


def test_qa_includes_diff_stat():
    assert qa_prompt(["a1", "a2"], '{"passed":true}', "STAT", "PATCH") == (
        "Frozen contract assertions:\n- a1\n- a2"
        + '\nTest results: {"passed":true}'
        + "\nDiff stat:\nSTAT"
        + "\nDiff:\nPATCH"
    )


def test_reviewer_omits_diff_stat():
    # feature.py:1417 -- reviewer gets Diff: but NOT Diff stat:. Asymmetry
    # is preserved deliberately; see design doc section 4.1.
    assert reviewer_prompt(["a1"], '{"passed":true}', "PATCH") == (
        "Frozen contract assertions:\n- a1" + '\nTest results: {"passed":true}' + "\nDiff:\nPATCH"
    )


def test_analyst():
    assert analyst_prompt("CRIT", "QA", "STAT", "PATCH") == (
        "Acceptance criteria (task_id in brackets):\nCRIT"
        + "\nAggregate test output:\nQA"
        + "\nIntegration diff stat:\nSTAT"
        + "\nIntegration diff:\nPATCH"
    )


def test_merge_verdict_preserves_em_dash_and_repr():
    # feature.py:2361-2362 -- f-string interpolates the LIST, so Python's
    # repr of list-of-dicts is what reaches the model. Preserve exactly.
    assert merge_verdict_prompt([{"id": 1}]) == (
        "Advisory only — the deterministic gate already passed. Task results: [{'id': 1}]"
    )


def test_empty_assertions_still_emits_header():
    # "\n- ".join([]) == "" -- the header survives with a trailing "- ".
    assert qa_prompt([], "{}", "S", "P").startswith("Frozen contract assertions:\n- \n")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_prompts_characterization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.prompts'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/prompts.py`:

```python
"""Pure prompt composition for the proposer roles.

Extracted verbatim from FeatureWorkflow's inline expressions so that the
production pipeline and the eval fixture generator build the same string
from the same code. Divergence is now a code change, not silent rot.

No I/O, no imports beyond typing: this module is imported inside
feature.py's `workflow.unsafe.imports_passed_through()` block and must
stay deterministic and sandbox-safe.

Every function here is pinned byte-for-byte by
tests/test_prompts_characterization.py. Changing an output string changes
the prompt the pipeline sends AND invalidates the memoization content_key
-- treat it as a behavior change, never a tidy-up.
"""

from __future__ import annotations

from typing import Sequence


def _memory_block(items: Sequence[str]) -> str:
    """feature.py:1894-1895, :2041-2042 -- shared by clarify and planner."""
    if not items:
        return ""
    return "\nRelevant memory:\n- " + "\n- ".join(items)


def _frozen_contract_block(assertions: Sequence[str]) -> str:
    """feature.py:1404, :1415 -- shared by qa and reviewer."""
    return "Frozen contract assertions:\n- " + "\n- ".join(assertions)


def clarify_prompt(idea_json: str, memory: Sequence[str]) -> str:
    """feature.py:1893."""
    return idea_json + _memory_block(memory)


def planner_prompt(arch_json: str, memory: Sequence[str], guidance: str | None) -> str:
    """feature.py:2040-2044."""
    return (
        arch_json
        + _memory_block(memory)
        + (f"\nRevision guidance from reviewer:\n{guidance}" if guidance else "")
    )


def qa_prompt(assertions: Sequence[str], qa_raw_json: str, diff_stat: str, diff_patch: str) -> str:
    """feature.py:1404-1407."""
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff stat:\n{diff_stat}"
        + f"\nDiff:\n{diff_patch}"
    )


def reviewer_prompt(assertions: Sequence[str], qa_raw_json: str, diff_patch: str) -> str:
    """feature.py:1415-1417. NOTE: no `Diff stat:` block -- qa gets one and
    reviewer does not. Preserved from the original; see design doc 4.1."""
    return (
        _frozen_contract_block(assertions)
        + f"\nTest results: {qa_raw_json}"
        + f"\nDiff:\n{diff_patch}"
    )


def analyst_prompt(criteria_lines: str, qa_lines: str, diff_stat: str, diff_patch: str) -> str:
    """feature.py:2192-2195."""
    return (
        "Acceptance criteria (task_id in brackets):\n"
        + criteria_lines
        + "\nAggregate test output:\n"
        + qa_lines
        + f"\nIntegration diff stat:\n{diff_stat}"
        + f"\nIntegration diff:\n{diff_patch}"
    )


def merge_verdict_prompt(task_results: Sequence[dict]) -> str:
    """feature.py:2361-2362. The f-string interpolates the LIST, so Python's
    repr of list-of-dicts is what reaches the model. Do not "fix" this to
    JSON -- it would change the prompt."""
    return (
        f"Advisory only — the deterministic gate already passed. Task results: {list(task_results)}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pip install -e . && python -m pytest tests/test_prompts_characterization.py -v`
Expected: PASS — 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/prompts.py tests/test_prompts_characterization.py
git commit -m "feat(prompts): pure prompt builders extracted from feature.py (E-82)"
```

---

### Task 2: Swap `feature.py` to the extracted builders

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (import block at :16; call sites :1403, :1414, :1893, :2040, :2192, :2360)

**Interfaces:**
- Consumes: all six builders from Task 1.
- Produces: nothing new — behavior-preserving refactor.

The gate on this task is the **existing full test suite**, which already covers `FeatureWorkflow` behavior. There is no new test: Task 1's characterization tests are the proof of equivalence, and this task's job is to not break anything else.

- [ ] **Step 1: Record the pre-change baseline**

Run: `python -m pytest -q`
Write down the exact pass/fail counts. This is the number Step 4 must match.

- [ ] **Step 2: Add the import**

In `src/sdlc/workflows/feature.py`, inside the existing `with workflow.unsafe.imports_passed_through():` block (starts at line 16), add alongside the other relative imports:

```python
from ..prompts import (
    analyst_prompt,
    clarify_prompt,
    merge_verdict_prompt,
    planner_prompt,
    qa_prompt,
    reviewer_prompt,
)
```

- [ ] **Step 3: Replace the six call sites**

Replace each expression with a call. Keep every surrounding line (the `_run_role` arguments, `into=`, `.output`) exactly as-is.

`feature.py:1893` — clarify:
```python
                idea.model_dump_json()
                + ("\nRelevant memory:\n- " + "\n- ".join(snapshot.items)
                   if snapshot.items else ""), into=clarify_spend)).output
```
becomes:
```python
                clarify_prompt(idea.model_dump_json(), snapshot.items),
                into=clarify_spend)).output
```

`feature.py:2040-2044` — planner:
```python
prompt = planner_prompt(arch.model_dump_json(), snapshot.items, guidance)
```

`feature.py:1404-1407` — qa:
```python
                qa_prompt(assertions, qa_raw.model_dump_json(),
                          diff["stat"], diff["patch"]), into=qa_spend)).output
```

`feature.py:1415-1417` — reviewer:
```python
                    reviewer_prompt(assertions, qa_raw.model_dump_json(),
                                    diff["patch"]))).output
```

`feature.py:2192-2195` — analyst:
```python
            analyst_prompt(_criteria_lines, _qa_lines,
                           integration_diff["stat"],
                           integration_diff["patch"]), into=analyst_spend)).output
```

`feature.py:2361-2362` — merge_verdict:
```python
                    merge_verdict_prompt([r.model_dump()
                                          for r in done.values()])
                )).output
```

- [ ] **Step 4: Run the full suite and compare to the baseline**

Run: `python -m pytest -q`
Expected: identical pass/fail counts to Step 1. Any new failure means the extraction was not byte-identical — fix `prompts.py` and add the missing case to `tests/test_prompts_characterization.py`.

- [ ] **Step 5: Verify the workflow still imports under the Temporal sandbox**

Run: `python -m pytest -m temporal -q -k feature`
Expected: PASS. This catches a sandbox-hostile import, which a plain unit run would not.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/workflows/feature.py
git commit -m "refactor(feature): compose proposer prompts via prompts.py (E-82)"
```

---

### Task 3: Deterministic fixture construction for `clarify`

**Files:**
- Modify: `src/sdlc/eval/fixtures.py`
- Test: `tests/test_eval_fixture_build.py`

**Interfaces:**
- Consumes: `clarify_prompt` (Task 1).
- Produces: `build_fixture(role: str, case_id: str, cases_root: Path, agents_dir: Path) -> EvalFixture`, and `FixtureError`.

`EvalFixture` keeps its existing fields (`role`, `case`, `prompt`, `model`, `source_run_id`, `captured_at`). For a built fixture, `source_run_id` is the literal `"_built"` — mirroring the `"_production"` / `"_drift"` convention benchmarks already uses for non-run-sourced records.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_fixture_build.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.eval.fixtures import FixtureError, build_fixture

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"
AGENTS = Path(__file__).resolve().parents[1] / "agents"


def test_clarify_fixture_is_deterministic():
    a = build_fixture("clarify", "add-login-greenfield", CASES, AGENTS)
    b = build_fixture("clarify", "add-login-greenfield", CASES, AGENTS)
    assert a.prompt == b.prompt


def test_clarify_prompt_matches_what_the_workflow_sends():
    """The fixture must equal clarify_prompt(IdeaBrief.model_dump_json(), [])
    built the same way BenchmarkWorkflow builds its IdeaBrief
    (benchmarks/workflow.py:157-158)."""
    import yaml
    from sdlc.models import IdeaBrief, ProjectMode
    from sdlc.prompts import clarify_prompt

    spec = yaml.safe_load(
        (CASES / "add-login-greenfield" / "case.yaml").read_text(encoding="utf-8")
    )
    idea = IdeaBrief(
        title=spec["case_id"],
        description=spec["description"],
        mode=ProjectMode(spec["mode"]),
        repo_url=spec.get("repo_url"),
    )
    expected = clarify_prompt(idea.model_dump_json(), [])

    assert build_fixture("clarify", "add-login-greenfield", CASES, AGENTS).prompt == expected


def test_fixture_carries_the_role_registry_model():
    fx = build_fixture("clarify", "add-login-greenfield", CASES, AGENTS)
    assert fx.model == "anthropic:glm-5.2"
    assert fx.source_run_id == "_built"
    assert fx.role == "clarify"
    assert fx.case == "add-login-greenfield"


def test_unknown_case_raises_with_the_path():
    with pytest.raises(FixtureError) as e:
        build_fixture("clarify", "no-such-case", CASES, AGENTS)
    assert "no-such-case" in str(e.value)


def test_deps_role_is_refused():
    with pytest.raises(FixtureError) as e:
        build_fixture("architect", "add-login-greenfield", CASES, AGENTS)
    assert "deps" in str(e.value).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_eval_fixture_build.py -v`
Expected: FAIL — `ImportError: cannot import name 'FixtureError'`

- [ ] **Step 3: Write the implementation**

In `src/sdlc/eval/fixtures.py`, **delete** `fixtures_from_events`, `extract_user_prompt`, `_role_for_activity`, `AGENT_TO_ROLE`, `_ROLE_TO_AGENT`, and `_REQUEST_SUFFIX` (the capture half). Keep `EvalFixture`, `write_fixtures`, `load_fixture`, `SUPPORTED_ROLES`, `DEPS_ROLES`. Then add:

```python
import yaml

from ..models import IdeaBrief, ProjectMode
from ..prompts import clarify_prompt


class FixtureError(Exception):
    """A fixture could not be built (unknown case/role, missing seed)."""


def _load_case(case_id: str, cases_root: Path) -> dict:
    p = cases_root / case_id / "case.yaml"
    if not p.is_file():
        raise FixtureError(f"no case.yaml at {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _role_model(role: str, agents_dir: Path) -> str:
    p = agents_dir / role / "agent.yaml"
    if not p.is_file():
        raise FixtureError(f"no agent.yaml at {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    model = data.get("model")
    if not model:
        raise FixtureError(f"no model declared in {p}")
    return model


def _idea_brief(spec: dict) -> IdeaBrief:
    """Mirrors BenchmarkWorkflow's construction (workflow.py:157-158) so a
    fixture's idea is identical to a benchmark cell's."""
    return IdeaBrief(
        title=spec["case_id"],
        description=spec["description"],
        mode=ProjectMode(spec.get("mode", "greenfield")),
        repo_url=spec.get("repo_url"),
    )


def build_fixture(role: str, case_id: str, cases_root: Path, agents_dir: Path) -> EvalFixture:
    """Construct a role's frozen input from a golden case, deterministically.

    Memory items are empty by construction: a fixture must not depend on a
    live memory backend, and an empty snapshot is what an unattended cell
    sees anyway.
    """
    if role in DEPS_ROLES:
        raise FixtureError(
            f"role '{role}' carries deps; a prompt-string fixture cannot "
            f"reconstruct a live deps object"
        )
    if role not in SUPPORTED_ROLES:
        raise FixtureError(
            f"unknown role '{role}'; supported: {', '.join(sorted(SUPPORTED_ROLES))}"
        )
    spec = _load_case(case_id, cases_root)
    model = _role_model(role, agents_dir)

    if role == "clarify":
        prompt = clarify_prompt(_idea_brief(spec).model_dump_json(), [])
    else:
        prompt = _seeded_prompt(role, case_id, cases_root)

    return EvalFixture(role=role, case=case_id, prompt=prompt, model=model, source_run_id="_built")


def _seeded_prompt(role: str, case_id: str, cases_root: Path) -> str:
    raise FixtureError(
        f"role '{role}' needs a frozen seed under "
        f"{cases_root / case_id / 'seeds'}; seeded roles land in Task 4"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_fixture_build.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Verify nothing else imported the deleted capture half**

Run: `python -m pytest -q`
Expected: failures only in tests that exercise `fixtures_from_events` / `run_capture`. Delete those tests — the capability is intentionally retired (design doc §4.2). Re-run until green.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/eval/fixtures.py tests/test_eval_fixture_build.py
git commit -m "feat(eval): build fixtures deterministically, retire capture (E-82)"
```

---

### Task 4: Frozen seeds for `planner` and `qa`

**Files:**
- Create: `benchmarks/cases/cat-cafe-monitoring/seeds/architecture.json`, `seeds/assertions.json`, `seeds/qa_raw.json`, `seeds/diff.json`
- Modify: `src/sdlc/eval/fixtures.py` (`_seeded_prompt`)
- Test: `tests/test_eval_fixture_build.py` (extend)

**Interfaces:**
- Consumes: `planner_prompt`, `qa_prompt` (Task 1); `build_fixture` (Task 3).
- Produces: the `seeds/` convention — `architecture.json` (one `ArchitectureSpec`), `assertions.json` (`{"assertions": [str]}`), `qa_raw.json` (arbitrary JSON object, serialized verbatim into the prompt), `diff.json` (`{"stat": str, "patch": str}`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_eval_fixture_build.py`:

```python
def test_planner_fixture_uses_the_frozen_architecture_seed():
    import json

    from sdlc.prompts import planner_prompt

    arch = json.loads(
        (CASES / "cat-cafe-monitoring" / "seeds" / "architecture.json").read_text(encoding="utf-8")
    )
    expected = planner_prompt(json.dumps(arch, separators=(",", ":")), [], None)
    fx = build_fixture("planner", "cat-cafe-monitoring", CASES, AGENTS)
    assert fx.prompt == expected


def test_qa_fixture_uses_the_frozen_seeds():
    import json

    from sdlc.prompts import qa_prompt

    seeds = CASES / "cat-cafe-monitoring" / "seeds"
    assertions = json.loads((seeds / "assertions.json").read_text(encoding="utf-8"))["assertions"]
    qa_raw = (seeds / "qa_raw.json").read_text(encoding="utf-8").strip()
    diff = json.loads((seeds / "diff.json").read_text(encoding="utf-8"))
    expected = qa_prompt(assertions, qa_raw, diff["stat"], diff["patch"])
    assert build_fixture("qa", "cat-cafe-monitoring", CASES, AGENTS).prompt == expected


def test_missing_seed_names_the_directory():
    with pytest.raises(FixtureError) as e:
        build_fixture("planner", "add-login-greenfield", CASES, AGENTS)
    assert "seeds" in str(e.value)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_eval_fixture_build.py -v -k "seed"`
Expected: FAIL — `FixtureError: role 'planner' needs a frozen seed`

- [ ] **Step 3: Author the seed files**

`benchmarks/cases/cat-cafe-monitoring/seeds/architecture.json` — `ArchitectureSpec` requires `overview` and `decisions`; each decision requires `id`, `decision`, `rationale`:

```json
{
  "overview": "Single-process Python ASGI service exposing app:app. In-memory ring buffer per cat holds the last 24h of readings; activity is derived per reading from breathing rate plus nearest-zone distance on the floor plan. Telemetry generation is a separate entrypoint so importing app:app never starts it.",
  "decisions": [
    {
      "id": "AD-1",
      "decision": "FastAPI over a bare ASGI app",
      "rationale": "The frozen contract needs four typed JSON routes with path params and 404 semantics; FastAPI gives validation and error shapes without hand-rolling them.",
      "alternatives_considered": ["Starlette directly", "Flask + ASGI adapter"]
    },
    {
      "id": "AD-2",
      "decision": "In-memory per-cat deque, no database",
      "rationale": "The 24h window is computed relative to each cat's newest reading, not wall clock, and the case explicitly asks to keep it as simple as possible.",
      "alternatives_considered": ["SQLite", "Redis"]
    },
    {
      "id": "AD-3",
      "decision": "Simulation runs only under `python app.py`",
      "rationale": "The frozen contract requires that importing app:app must not auto-start the generator, so the driver lives behind __main__.",
      "alternatives_considered": ["Background task on startup event"]
    }
  ],
  "affected_modules": ["app.py"],
  "new_components": ["telemetry ingest", "activity detection", "risk analysis"],
  "risks": ["Activity thresholds are heuristic and unvalidated against real collar data"]
}
```

`seeds/assertions.json`:
```json
{
  "assertions": [
    "POST /telemetry accepts {cat_id, x, y, breathing_rate, timestamp} and returns 2xx",
    "GET /floorplan returns 200 with zones[] of kind rest_area|litter_box|water_bowl|food_bowl",
    "GET /cats returns 200 with [{id, x, y, activity, at_risk}]",
    "GET /cats/{id} returns 200 with the last 24h of readings, 404 for unknown id",
    "Importing app:app does not auto-start the telemetry generator"
  ]
}
```

`seeds/qa_raw.json`:
```json
{"tests_passed": false, "passed": 4, "failed": 1, "failing_tests": ["test_cat_detail_404"]}
```

`seeds/diff.json`:
```json
{"stat": " app.py | 42 ++++++++++\n 1 file changed, 42 insertions(+)", "patch": "diff --git a/app.py b/app.py\n@@\n+from fastapi import FastAPI\n+app = FastAPI()\n"}
```

- [ ] **Step 4: Implement `_seeded_prompt`**

Replace the stub in `src/sdlc/eval/fixtures.py`:

```python
def _read_seed(case_id: str, cases_root: Path, name: str) -> str:
    p = cases_root / case_id / "seeds" / name
    if not p.is_file():
        raise FixtureError(
            f"role needs a frozen seed at {p}. Author it (see design doc "
            f"section 4.2 for the per-role seed contents) before evaluating "
            f"this (role, case) pair."
        )
    return p.read_text(encoding="utf-8")


def _seeded_prompt(role: str, case_id: str, cases_root: Path) -> str:
    import json

    if role == "planner":
        arch = json.loads(_read_seed(case_id, cases_root, "architecture.json"))
        return planner_prompt(json.dumps(arch, separators=(",", ":")), [], None)
    if role == "qa":
        assertions = json.loads(_read_seed(case_id, cases_root, "assertions.json"))["assertions"]
        qa_raw = _read_seed(case_id, cases_root, "qa_raw.json").strip()
        diff = json.loads(_read_seed(case_id, cases_root, "diff.json"))
        return qa_prompt(assertions, qa_raw, diff["stat"], diff["patch"])
    raise FixtureError(
        f"role '{role}' has no seed recipe; add one alongside planner/qa "
        f"in _seeded_prompt (design doc section 4.2 lists the contents)"
    )
```

Add `planner_prompt, qa_prompt` to the `..prompts` import at the top of the file.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_fixture_build.py -v`
Expected: PASS — 8 passed

- [ ] **Step 6: Commit**

```bash
git add benchmarks/cases/cat-cafe-monitoring/seeds src/sdlc/eval/fixtures.py tests/test_eval_fixture_build.py
git commit -m "feat(eval): frozen seeds for planner and qa fixtures (E-82)"
```

---

### Task 5: promptfoo custom provider

**Files:**
- Create: `src/sdlc/eval/promptfoo/__init__.py`, `src/sdlc/eval/promptfoo/provider.py`
- Modify: `src/sdlc/eval/runner.py` (add `run_variant_detailed`)
- Test: `tests/test_promptfoo_provider.py`

**Interfaces:**
- Consumes: `run_variant` (`src/sdlc/eval/runner.py:23`), `load_fixture` (Task 3).
- Produces: `run_variant_detailed(role, instructions_text, fixture, agents_dir, *, model_override=None) -> tuple[str, Any]` (output JSON + the run's `Usage`); `call_api(prompt: str, options: dict, context: dict) -> dict` returning `{"output": str, "error": str | None, "tokenUsage": dict, "cost": float | None, "latencyMs": int}`; `resolve_instructions(role: str, ref: str, repo_root: Path, agents_dir: Path) -> str`.

`tokenUsage` and `cost` must be populated, not stubbed — the config's native `cost` and `latency` assertions (Task 8) are absolute gating checks and would be vacuous otherwise.

`options["config"]` carries `{role, instructions_ref, fixture_path, agents_dir, repo_root}`. `instructions_ref` is either `"worktree"` or a git ref (`"HEAD"`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_promptfoo_provider.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from pydantic_ai.models.test import TestModel

from sdlc.eval.fixtures import EvalFixture
from sdlc.eval.promptfoo.provider import call_api, resolve_instructions

AGENTS = Path(__file__).resolve().parents[1] / "agents"
ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    fx = EvalFixture(
        role="clarify",
        case="c",
        prompt="build a login page",
        model="anthropic:glm-5.2",
        source_run_id="_built",
    )
    p = tmp_path / "c.json"
    p.write_text(fx.model_dump_json(), encoding="utf-8")
    return p


def _opts(tmp_path: Path, ref: str = "worktree") -> dict:
    return {
        "config": {
            "role": "clarify",
            "instructions_ref": ref,
            "fixture_path": str(_fixture(tmp_path)),
            "agents_dir": str(AGENTS),
            "repo_root": str(ROOT),
        }
    }


def test_returns_output_key_with_serialized_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr("sdlc.eval.promptfoo.provider._MODEL_OVERRIDE", TestModel())
    res = call_api("ignored", _opts(tmp_path), {})
    assert "output" in res
    assert res.get("error") is None
    json.loads(res["output"])  # proposer output serializes to JSON


def test_always_returns_output_even_on_error(tmp_path):
    opts = _opts(tmp_path)
    opts["config"]["role"] = "no-such-role"
    res = call_api("ignored", opts, {})
    assert res["output"] == ""
    assert res["error"]


def test_never_raises_on_missing_fixture(tmp_path):
    opts = _opts(tmp_path)
    opts["config"]["fixture_path"] = str(tmp_path / "absent.json")
    res = call_api("ignored", opts, {})
    assert res["output"] == ""
    assert "absent.json" in res["error"]


def test_reports_latency(tmp_path, monkeypatch):
    monkeypatch.setattr("sdlc.eval.promptfoo.provider._MODEL_OVERRIDE", TestModel())
    res = call_api("ignored", _opts(tmp_path), {})
    assert isinstance(res["latencyMs"], int)
    assert res["latencyMs"] >= 0


def test_reports_token_usage(tmp_path, monkeypatch):
    """The config's native `cost` assert is an ABSOLUTE gating check; it is
    vacuous unless the provider actually reports usage."""
    monkeypatch.setattr("sdlc.eval.promptfoo.provider._MODEL_OVERRIDE", TestModel())
    res = call_api("ignored", _opts(tmp_path), {})
    assert set(res["tokenUsage"]) >= {"prompt", "completion", "total"}
    assert res["tokenUsage"]["total"] >= 0


def test_resolve_instructions_worktree_reads_the_file():
    text = resolve_instructions("clarify", "worktree", ROOT, AGENTS)
    assert text == (AGENTS / "clarify" / "instructions.md").read_text(encoding="utf-8")


def test_resolve_instructions_git_ref_reads_from_git():
    text = resolve_instructions("clarify", "HEAD", ROOT, AGENTS)
    assert isinstance(text, str) and text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_promptfoo_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.promptfoo'`

- [ ] **Step 3: Add `run_variant_detailed` to `src/sdlc/eval/runner.py`**

`run_variant` returns only the serialized output, so usage is lost. Add a sibling that surfaces it, and make the existing function delegate — no caller changes:

```python
def run_variant_detailed(
    role: str,
    instructions_text: str,
    fixture: EvalFixture,
    agents_dir: Path,
    *,
    model_override: Any | None = None,
) -> tuple[str, Any]:
    """As run_variant, but also returns the run's Usage so the promptfoo
    provider can report tokenUsage/cost -- the native `cost` assertion is an
    absolute gating check and needs real numbers."""
    build = _load_build(role, agents_dir / role)
    model = model_override if model_override is not None else fixture.model
    agent = build(model, instructions_text, MODEL_SETTINGS)
    result = agent.run_sync(fixture.prompt)
    return _to_json(result.output), result.usage()


def run_variant(
    role: str,
    instructions_text: str,
    fixture: EvalFixture,
    agents_dir: Path,
    *,
    model_override: Any | None = None,
) -> str:
    return run_variant_detailed(
        role, instructions_text, fixture, agents_dir, model_override=model_override
    )[0]
```

- [ ] **Step 4: Write the provider**

Create `src/sdlc/eval/promptfoo/__init__.py` (empty), then `src/sdlc/eval/promptfoo/provider.py`:

```python
"""promptfoo custom provider: one variant of one role on one fixture.

promptfoo's PROVIDER axis is the A/B axis -- the same file appears twice in
the config with different `instructions_ref`, so baseline vs working-tree
renders as a native side-by-side matrix and no custom compare loop exists.

Contract (promptfoo docs, providers/python): return a dict that ALWAYS
carries "output", even on failure. This function therefore never raises.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from ..fixtures import load_fixture
from ..runner import run_variant_detailed

# Tests inject a TestModel/FunctionModel here so no real model is called.
# Production leaves it None and the fixture's captured author model is used.
_MODEL_OVERRIDE: Any | None = None


def _token_usage(usage: Any) -> dict:
    """pydantic-ai Usage -> promptfoo's tokenUsage shape. Defensive about
    attribute names so a pydantic-ai bump degrades to zeros rather than
    crashing a gate run."""
    prompt = getattr(usage, "input_tokens", 0) or 0
    completion = getattr(usage, "output_tokens", 0) or 0
    return {"prompt": prompt, "completion": completion, "total": prompt + completion}


def _cost_usd(usage: Any, model: str) -> float | None:
    """USD via genai-prices (already a project dependency). None when the
    model is unknown to the price table -- a missing price must not fail a
    gate, and verdict.py treats None as not-measured."""
    try:
        from genai_prices import calc_price

        price = calc_price(
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            model_ref=model,
        )
        return float(price.total_price)
    except Exception:
        return None


def resolve_instructions(role: str, ref: str, repo_root: Path, agents_dir: Path) -> str:
    """Instructions text at `ref`: the worktree file, or `git show`."""
    if ref == "worktree":
        return (agents_dir / role / "instructions.md").read_text(encoding="utf-8")
    rel = f"agents/{role}/instructions.md"
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel}"], cwd=repo_root, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise FileNotFoundError(f"{rel} does not exist at ref '{ref}': {proc.stderr.strip()}")
    return proc.stdout


def call_api(prompt: str, options: dict, context: dict) -> dict:
    """`prompt` is ignored: the frozen input comes from the fixture, not from
    promptfoo's prompt axis, so both providers see byte-identical input."""
    started = time.monotonic()
    try:
        cfg = options["config"]
        agents_dir = Path(cfg["agents_dir"])
        instructions = resolve_instructions(
            cfg["role"], cfg["instructions_ref"], Path(cfg["repo_root"]), agents_dir
        )
        fixture = load_fixture(Path(cfg["fixture_path"]))
        out, usage = run_variant_detailed(
            cfg["role"], instructions, fixture, agents_dir, model_override=_MODEL_OVERRIDE
        )
        return {
            "output": out,
            "error": None,
            "tokenUsage": _token_usage(usage),
            "cost": _cost_usd(usage, fixture.model),
            "latencyMs": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:  # never raise -- see docstring
        return {
            "output": "",
            "error": f"{type(exc).__name__}: {exc}",
            "latencyMs": int((time.monotonic() - started) * 1000),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pip install -e . && python -m pytest tests/test_promptfoo_provider.py -v`
Expected: PASS — 7 passed

If `_cost_usd` cannot resolve `genai_prices.calc_price`, check the installed API with `python -c "import genai_prices; print(dir(genai_prices))"` and adjust the call — the `except Exception: return None` fallback means a wrong guess degrades to not-measured rather than breaking the gate, but a permanently-None cost makes the `cost` assertion vacuous, so get it right.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/eval/promptfoo src/sdlc/eval/runner.py tests/test_promptfoo_provider.py
git commit -m "feat(eval): promptfoo custom provider over run_variant (E-82)"
```

---

### Task 6: Judge assertion (advisory, carries ADR-6)

**Files:**
- Create: `src/sdlc/eval/promptfoo/assertion.py`
- Test: `tests/test_promptfoo_assertion.py`

**Interfaces:**
- Consumes: `judge_artifact.sync`, `JudgeInput` (`src/sdlc/benchmarks/judge.py`), `model_family` (`src/sdlc/agents/loader.py:71`).
- Produces: `grade(output: str, context: dict) -> dict` returning `{"pass": bool, "score": float, "reason": str}`; `load_rubric(case, role, cases_root) -> str`; `RUBRIC_KEY: dict[str, str]` (migrated from the deleted `compare.py`).

The judge is **advisory**: `pass` is always `True` unless ADR-6 is violated. Its number feeds Task 9's regression check; it never gates alone.

- [ ] **Step 1: Write the failing test**

Create `tests/test_promptfoo_assertion.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from sdlc.benchmarks.judge import _set_judge_fn
from sdlc.eval.promptfoo.assertion import grade, load_rubric

CASES = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"


def _ctx(**over) -> dict:
    ctx = {
        "vars": {
            "role": "clarify",
            "case": "cat-cafe-monitoring",
            "author_model": "anthropic:glm-5.2",
            "judge_model": "openai/gpt-5.2",
            "cases_root": str(CASES),
        }
    }
    ctx["vars"].update(over)
    return ctx


def test_good_score_passes_and_reports(monkeypatch):
    _set_judge_fn(lambda inp: json.dumps({"score": 0.82, "components": {"clarity": 0.9}}))
    try:
        res = grade('{"open_questions": []}', _ctx())
    finally:
        _set_judge_fn(None)
    assert res["pass"] is True
    assert res["score"] == 0.82


def test_judge_error_is_advisory_pass_and_says_unavailable():
    _set_judge_fn(lambda inp: "not json at all")
    try:
        res = grade('{"open_questions": []}', _ctx())
    finally:
        _set_judge_fn(None)
    assert res["pass"] is True  # advisory: never gates alone
    assert res["score"] is None  # NOT 0.0 -- not-measured
    assert "unavailable" in res["reason"].lower()


def test_adr6_violation_is_a_hard_fail():
    res = grade("{}", _ctx(judge_model="anthropic:claude-sonnet-4-6"))
    assert res["pass"] is False
    assert "adr-6" in res["reason"].lower()
    assert "anthropic" in res["reason"]


def test_adr6_check_is_case_insensitive_on_family():
    res = grade("{}", _ctx(judge_model="ANTHROPIC:something"))
    assert res["pass"] is False


def test_missing_rubric_names_the_file_to_author():
    res = grade("{}", _ctx(case="add-login-greenfield", role="planner"))
    assert res["pass"] is False
    assert "rubric-planner.md" in res["reason"]


def test_load_rubric_reads_the_case_file():
    text = load_rubric("cat-cafe-monitoring", "clarify", CASES)
    assert text.strip()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_promptfoo_assertion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.promptfoo.assertion'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/eval/promptfoo/assertion.py`:

```python
"""promptfoo custom assertion: the cross-family judge, kept in Kroker's code.

ADVISORY by design (design doc 4.5): `pass` is True whatever the score, so a
noisy rubric number can never fail the gate on its own. The score is carried
out for the cross-provider regression check in eval/verdict.py, which
promptfoo structurally cannot do -- an assertion sees one output, and
assertScoringFunction sees one test, so neither can compare providers.

The ONE hard failure here is an ADR-6 violation: a judge sharing a model
family with the author is a configuration error, not a measurement.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from ...agents.loader import model_family
from ...benchmarks.judge import JudgeInput, judge_artifact

# role -> the key used in case.yaml's `rubrics:` map. Migrated verbatim from
# the retired eval/compare.py.
RUBRIC_KEY: dict[str, str] = {
    "clarify": "clarifier",
    "planner": "planner",
    "qa": "qa",
    "reviewer": "reviewer",
    "analyst": "analyst",
    "merge_verdict": "merge_verdict",
}


class RubricError(Exception):
    """No rubric registered or on disk for this (case, role)."""


def load_rubric(case: str, role: str, cases_root: Path) -> str:
    case_yaml = cases_root / case / "case.yaml"
    if not case_yaml.is_file():
        raise RubricError(f"no case.yaml at {case_yaml}")
    rubrics = (yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}).get("rubrics") or {}
    key = RUBRIC_KEY.get(role, role)
    rel = rubrics.get(key)
    if not rel:
        raise RubricError(
            f"no rubric for role '{role}' (key '{key}') in {case_yaml}. "
            f"Author {cases_root / case}/rubric-{key}.md and list it under "
            f"`rubrics:` before evaluating this role."
        )
    path = cases_root / case / rel
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RubricError(f"rubric file {path} named in {case_yaml} does not exist")


def grade(output: str, context: dict) -> dict:
    v = context.get("vars", {})
    author, judge = v.get("author_model", ""), v.get("judge_model", "")

    if model_family(judge) == model_family(author):
        return {
            "pass": False,
            "score": None,
            "reason": f"ADR-6 violation: judge '{judge}' shares family "
            f"'{model_family(judge)}' with author '{author}'. "
            f"Pick a different family.",
        }
    try:
        rubric = load_rubric(v["case"], v["role"], Path(v["cases_root"]))
    except RubricError as e:
        return {"pass": False, "score": None, "reason": str(e)}

    qs = judge_artifact.sync(
        JudgeInput(artifact_json=output, rubric=rubric, author_model=author, judge_model=judge)
    )
    if qs.score is None:
        return {
            "pass": True,
            "score": None,
            "reason": "judge unavailable (errored) — advisory, excluded from the mean",
        }
    return {"pass": True, "score": qs.score, "reason": f"advisory rubric score {qs.score:.2f}"}


def main() -> None:
    """promptfoo invokes this file with argv[1]=output, argv[2]=context JSON
    and reads a GradingResult JSON object from stdout."""
    import json

    print(json.dumps(grade(sys.argv[1], json.loads(sys.argv[2]))))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_promptfoo_assertion.py -v`
Expected: PASS — 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/eval/promptfoo/assertion.py tests/test_promptfoo_assertion.py
git commit -m "feat(eval): advisory judge assertion carrying ADR-6 (E-82)"
```

---

### Task 7: Absolute assertion — output-type validation

**Files:**
- Create: `src/sdlc/eval/promptfoo/absolute.py`
- Test: `tests/test_promptfoo_absolute.py`

**Interfaces:**
- Consumes: `_load_build` (`src/sdlc/agents/loader.py:329`) to discover a role's `output_type`.
- Produces: `validates_as_output_type(output: str, role: str, agents_dir: Path) -> dict` returning `{"pass": bool, "score": float, "reason": str}`; `output_type_for(role, agents_dir) -> type`.

This one **gates**. A proposer whose output no longer parses into its declared type is broken regardless of what any rubric says.

Reference — the real required fields (confirmed via `model_json_schema()`):

- `ClarifiedRequirements`: `summary`, `functional_requirements`, `non_functional_requirements`, `out_of_scope`, `open_questions`
- `ArchitectureSpec`: `overview`, `decisions`; each decision requires `id`, `decision`, `rationale`

- [ ] **Step 1: Write the failing test**

Create `tests/test_promptfoo_absolute.py`:

```python
from __future__ import annotations

from pathlib import Path

from sdlc.eval.promptfoo.absolute import output_type_for, validates_as_output_type

AGENTS = Path(__file__).resolve().parents[1] / "agents"

# Every required field of ClarifiedRequirements. open_questions=[] is a
# legitimate outcome (the clarifier had nothing to ask), so an empty LIST is
# never a failure -- see test_empty_required_list_is_allowed below.
GOOD = json.dumps(
    {
        "summary": "Add a login page with email and password.",
        "functional_requirements": ["User can submit email + password"],
        "non_functional_requirements": ["Passwords are hashed at rest"],
        "out_of_scope": ["OAuth providers"],
        "open_questions": [],
    }
)


def test_output_type_for_clarify():
    from sdlc.models import ClarifiedRequirements

    assert output_type_for("clarify", AGENTS) is ClarifiedRequirements


def test_valid_artifact_passes():
    res = validates_as_output_type(GOOD, "clarify", AGENTS)
    assert res["pass"] is True, res["reason"]


def test_non_json_fails_with_the_type_name():
    res = validates_as_output_type("not json", "clarify", AGENTS)
    assert res["pass"] is False
    assert "ClarifiedRequirements" in res["reason"]


def test_empty_output_fails():
    # A provider error surfaces as "" -- it must NOT read as a valid artifact.
    res = validates_as_output_type("", "clarify", AGENTS)
    assert res["pass"] is False


def test_wrong_shape_fails():
    res = validates_as_output_type('{"unexpected": 1}', "clarify", AGENTS)
    assert res["pass"] is False


def test_blank_required_string_fails():
    """Spec 4.5 "required fields non-empty": a schema-valid artifact whose
    summary is whitespace is still a broken proposer."""
    bad = json.loads(GOOD)
    bad["summary"] = "   "
    res = validates_as_output_type(json.dumps(bad), "clarify", AGENTS)
    assert res["pass"] is False
    assert "summary" in res["reason"]


def test_empty_required_list_is_allowed():
    """Deliberate non-check: open_questions=[] means "nothing to ask", not a
    failure. Only required STRING fields are checked for emptiness, so the
    gate never invents a regression."""
    res = validates_as_output_type(GOOD, "clarify", AGENTS)
    assert res["pass"] is True
```

Add `import json` to the test file's imports.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_promptfoo_absolute.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.promptfoo.absolute'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/eval/promptfoo/absolute.py`:

```python
"""ABSOLUTE assertions -- the checks that gate (design doc 4.5, ADR-11).

An output that no longer parses into the role's declared output_type is
broken whatever a rubric says, so this never degrades to advisory.

The output_type is read off the role's real agent.py rather than a hardcoded
map, so a role that changes its type needs no edit here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ValidationError

from ...agents.loader import _load_build
from ...agents.roles import MODEL_SETTINGS


@lru_cache(maxsize=None)
def output_type_for(role: str, agents_dir: Path) -> type[BaseModel]:
    """Build the role's agent with a throwaway model id and read its declared
    output type. No model call happens -- Agent construction is lazy."""
    build = _load_build(role, agents_dir / role)
    agent = build("test", "", MODEL_SETTINGS)
    return agent.output_type


def _blank_required_strings(t: type[BaseModel], data: dict) -> list[str]:
    """Required fields typed `str` that are blank.

    Only strings are checked. A required LIST may legitimately be empty --
    ClarifiedRequirements.open_questions == [] means "nothing to ask" -- and
    failing on that would invent regressions the prompt did not cause.
    """
    schema = t.model_json_schema()
    props = schema.get("properties", {})
    out = []
    for name in schema.get("required", []):
        if props.get(name, {}).get("type") != "string":
            continue
        value = data.get(name)
        if isinstance(value, str) and not value.strip():
            out.append(name)
    return out


def validates_as_output_type(output: str, role: str, agents_dir: Path) -> dict:
    t = output_type_for(role, Path(agents_dir))
    name = getattr(t, "__name__", str(t))
    if not output.strip():
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"empty output — cannot validate as {name} "
            f"(check the provider's `error` field)",
        }
    try:
        data = json.loads(output)
        t.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as e:
        return {"pass": False, "score": 0.0, "reason": f"output does not validate as {name}: {e}"}
    blank = _blank_required_strings(t, data)
    if blank:
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"{name} validates but required string field(s) "
            f"are blank: {', '.join(blank)}",
        }
    return {"pass": True, "score": 1.0, "reason": f"validates as {name}"}


def main() -> None:
    import sys

    ctx = json.loads(sys.argv[2])
    v = ctx.get("vars", {})
    print(json.dumps(validates_as_output_type(sys.argv[1], v["role"], Path(v["agents_dir"]))))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_promptfoo_absolute.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/eval/promptfoo/absolute.py tests/test_promptfoo_absolute.py
git commit -m "feat(eval): absolute output-type assertion (E-82)"
```

---

### Task 8: Config generation

**Files:**
- Create: `src/sdlc/eval/promptfoo/config.py`
- Test: `tests/test_promptfoo_config.py`

**Interfaces:**
- Consumes: `build_fixture` (Task 3/4).
- Produces: `build_config(role, case, *, repo_root, cases_root, agents_dir, judge_model, out_dir, repeat=3, baseline_ref="HEAD", max_cost_usd=0.50, max_latency_ms=120000) -> Path` writing `promptfooconfig.yaml` and the fixture JSON into `out_dir`.

Generated, never committed — a hand-maintained config would drift from the registry.

`baseline_ref` is threaded rather than hardcoded so `sdlc eval --against <ref>` (Task 12) stays meaningful instead of being a dead flag.

- [ ] **Step 1: Write the failing test**

Create `tests/test_promptfoo_config.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from sdlc.eval.promptfoo.config import build_config

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks" / "cases"
AGENTS = ROOT / "agents"


def _cfg(tmp_path: Path) -> dict:
    p = build_config(
        "clarify",
        "add-login-greenfield",
        repo_root=ROOT,
        cases_root=CASES,
        agents_dir=AGENTS,
        judge_model="openai/gpt-5.2",
        out_dir=tmp_path,
    )
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_emits_exactly_two_providers_labelled_baseline_and_working(tmp_path):
    labels = [p["label"] for p in _cfg(tmp_path)["providers"]]
    assert labels == ["baseline", "working"]


def test_providers_differ_only_in_instructions_ref(tmp_path):
    base, work = _cfg(tmp_path)["providers"]
    assert base["config"]["instructions_ref"] == "HEAD"
    assert work["config"]["instructions_ref"] == "worktree"
    assert base["id"] == work["id"]
    assert base["config"]["fixture_path"] == work["config"]["fixture_path"]


def test_carries_both_assertion_families(tmp_path):
    asserts = _cfg(tmp_path)["defaultTest"]["assert"]
    values = [str(a.get("value")) for a in asserts]
    assert any("absolute.py" in v for v in values)
    assert any("assertion.py" in v for v in values)


def test_carries_the_native_cost_and_latency_gates(tmp_path):
    """Spec 4.5 lists cost and latency as ABSOLUTE gating checks."""
    types = {a["type"] for a in _cfg(tmp_path)["defaultTest"]["assert"]}
    assert "cost" in types
    assert "latency" in types


def test_baseline_ref_is_threaded_not_hardcoded(tmp_path):
    p = build_config(
        "clarify",
        "add-login-greenfield",
        repo_root=ROOT,
        cases_root=CASES,
        agents_dir=AGENTS,
        judge_model="openai/gpt-5.2",
        out_dir=tmp_path,
        baseline_ref="main",
    )
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert cfg["providers"][0]["config"]["instructions_ref"] == "main"


def test_vars_carry_what_the_assertions_read(tmp_path):
    v = _cfg(tmp_path)["defaultTest"]["vars"]
    for key in ("role", "case", "author_model", "judge_model", "cases_root", "agents_dir"):
        assert key in v, key


def test_fixture_is_written_next_to_the_config(tmp_path):
    build_config(
        "clarify",
        "add-login-greenfield",
        repo_root=ROOT,
        cases_root=CASES,
        agents_dir=AGENTS,
        judge_model="openai/gpt-5.2",
        out_dir=tmp_path,
    )
    assert (tmp_path / "fixture.json").is_file()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_promptfoo_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.promptfoo.config'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/eval/promptfoo/config.py`:

```python
"""Generate promptfooconfig.yaml for one (role, case) pair.

Generated into a scratch dir and never committed: a hand-maintained config
would drift from agents/<role>/agent.yaml. The two providers differ ONLY in
instructions_ref -- that is the A/B axis (design doc 4.3).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..fixtures import build_fixture

_HERE = Path(__file__).resolve().parent


def build_config(
    role: str,
    case: str,
    *,
    repo_root: Path,
    cases_root: Path,
    agents_dir: Path,
    judge_model: str,
    out_dir: Path,
    repeat: int = 3,
    baseline_ref: str = "HEAD",
    max_cost_usd: float = 0.50,
    max_latency_ms: int = 120_000,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fixture = build_fixture(role, case, cases_root, agents_dir)
    fixture_path = out_dir / "fixture.json"
    fixture_path.write_text(fixture.model_dump_json(indent=2), encoding="utf-8")

    provider_cfg = {
        "role": role,
        "fixture_path": str(fixture_path),
        "agents_dir": str(agents_dir),
        "repo_root": str(repo_root),
    }
    provider_id = f"file://{_HERE / 'provider.py'}:call_api"

    cfg = {
        "description": f"prompt gate: {role} on {case}",
        "prompts": ["{{input}}"],  # unused: the fixture is the input
        "providers": [
            {
                "id": provider_id,
                "label": "baseline",
                "config": {**provider_cfg, "instructions_ref": baseline_ref},
            },
            {
                "id": provider_id,
                "label": "working",
                "config": {**provider_cfg, "instructions_ref": "worktree"},
            },
        ],
        "defaultTest": {
            "vars": {
                "role": role,
                "case": case,
                "author_model": fixture.model,
                "judge_model": judge_model,
                "cases_root": str(cases_root),
                "agents_dir": str(agents_dir),
            },
            # ABSOLUTE first (they gate), advisory judge last. Order is
            # cosmetic to promptfoo but keeps results.json readable.
            "assert": [
                {"type": "python", "value": f"file://{_HERE / 'absolute.py'}"},
                {"type": "cost", "threshold": max_cost_usd},
                {"type": "latency", "threshold": max_latency_ms},
                {"type": "python", "value": f"file://{_HERE / 'assertion.py'}"},
            ],
        },
        "tests": [{"vars": {"input": fixture.prompt}}],
        "repeat": repeat,
    }
    path = out_dir / "promptfooconfig.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_promptfoo_config.py -v`
Expected: PASS — 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/eval/promptfoo/config.py tests/test_promptfoo_config.py
git commit -m "feat(eval): generate promptfooconfig from the role registry (E-82)"
```

---

### Task 9: Verdict + noise floor (pure)

**Files:**
- Create: `src/sdlc/eval/verdict.py`
- Test: `tests/test_eval_verdict.py`

**Interfaces:**
- Consumes: nothing (pure over a results dict).
- Produces: `GateVerdict` (enum: `PASS`, `FAIL_ABSOLUTE`, `FAIL_REGRESSION`, `ERRORED`), `JudgeStatus` (enum: `MEASURED`, `UNAVAILABLE`, `NO_BASELINE`), `PromptGateResult` (pydantic model), `decide(results: dict, *, delta_min: float = 0.05) -> PromptGateResult`, `write_result(result, out_dir) -> Path`.

This is where most of the design's logic lives, and it is fully testable with a fake results dict and zero model calls.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_verdict.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from sdlc.eval.verdict import GateVerdict, JudgeStatus, decide, write_result


def _results(
    baseline: list, working: list, *, absolute_ok: bool = True, provider_error: str | None = None
) -> dict:
    """Shape of promptfoo's --output results.json, reduced to what we read."""

    def rows(label, scores):
        out = []
        for s in scores:
            out.append(
                {
                    "provider": {"label": label},
                    "error": provider_error,
                    "gradingResult": {
                        "componentResults": [
                            {
                                "assertion": {"value": "absolute.py"},
                                "pass": absolute_ok,
                                "reason": "r",
                            },
                            {
                                "assertion": {"value": "assertion.py"},
                                "pass": True,
                                "score": s,
                                "reason": "r",
                            },
                        ]
                    },
                }
            )
        return out

    return {"results": {"results": rows("baseline", baseline) + rows("working", working)}}


def test_improvement_passes():
    r = decide(_results([0.70, 0.70, 0.70], [0.85, 0.85, 0.85]))
    assert r.verdict is GateVerdict.PASS
    assert r.delta > 0


def test_dip_within_noise_passes():
    r = decide(_results([0.80, 0.80, 0.80], [0.78, 0.78, 0.78]))
    assert r.verdict is GateVerdict.PASS  # 0.02 < delta_min 0.05


def test_clear_regression_fails():
    r = decide(_results([0.85, 0.85, 0.85], [0.50, 0.50, 0.50]))
    assert r.verdict is GateVerdict.FAIL_REGRESSION
    assert "0.35" in r.reason or "-0.35" in r.reason


def test_noisy_data_widens_the_floor_and_passes():
    """Same means as the failing case, but high variance -- 2*pooled_stderr
    exceeds the gap, so the gate must NOT fire."""
    r = decide(_results([0.2, 0.9, 0.2, 0.9], [0.1, 0.8, 0.1, 0.8]))
    assert r.verdict is GateVerdict.PASS


def test_absolute_failure_beats_a_good_score():
    r = decide(_results([0.9], [0.9], absolute_ok=False))
    assert r.verdict is GateVerdict.FAIL_ABSOLUTE


def test_native_cost_gate_failure_is_absolute():
    """Native cost/latency asserts carry no `value` path -- they must be
    recognised by `type` or the budget gates silently do nothing."""
    res = _results([0.9], [0.9])
    for row in res["results"]["results"]:
        row["gradingResult"]["componentResults"].append(
            {
                "assertion": {"type": "cost", "threshold": 0.5},
                "pass": False,
                "reason": "cost 0.91 > 0.5",
            }
        )
    r = decide(res)
    assert r.verdict is GateVerdict.FAIL_ABSOLUTE
    assert "cost" in r.reason


def test_provider_error_is_errored_not_failed():
    r = decide(_results([0.9], [0.9], provider_error="API down"))
    assert r.verdict is GateVerdict.ERRORED
    assert "API down" in r.reason


def test_all_judges_errored_is_unavailable_never_a_silent_pass():
    r = decide(_results([None, None], [None, None]))
    assert r.judge_status is JudgeStatus.UNAVAILABLE
    assert r.verdict is GateVerdict.PASS
    assert "unavailable" in r.reason.lower()


def test_partial_judge_errors_are_excluded_from_the_mean():
    r = decide(_results([0.8, None, 0.8], [0.8, None, 0.8]))
    assert r.judge_status is JudgeStatus.MEASURED
    assert r.mean_baseline == 0.8


def test_no_baseline_rows_reports_no_baseline():
    r = decide(_results([], [0.8]))
    assert r.judge_status is JudgeStatus.NO_BASELINE
    assert r.verdict is GateVerdict.PASS


def test_k_of_one_falls_back_to_delta_min():
    """One sample each -> no stderr -> the 0.05 floor decides."""
    assert decide(_results([0.80], [0.78])).verdict is GateVerdict.PASS
    assert decide(_results([0.80], [0.60])).verdict is (GateVerdict.FAIL_REGRESSION)


def test_write_result_round_trips(tmp_path):
    r = decide(_results([0.8], [0.8]))
    r.role, r.case = "clarify", "cat-cafe-monitoring"
    r.prompt_sha_baseline, r.prompt_sha_working = "a1b2", "c3d4"
    p = write_result(r, tmp_path)
    data = json.loads(Path(p).read_text(encoding="utf-8"))
    assert data["prompt_sha_working"] == "c3d4"
    assert data["verdict"] == "pass"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_eval_verdict.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.verdict'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/eval/verdict.py`:

```python
"""The cross-provider gate verdict -- pure, over promptfoo's results.json.

promptfoo cannot decide this: an assertion sees one output and
assertScoringFunction sees one test, so neither can compare providers
(design doc 4.5). Keeping it here makes the subtlest logic in the increment
a pure function, exhaustively testable with zero model calls.

Not-measured is never rendered as passed: an all-errored judge yields
JudgeStatus.UNAVAILABLE, mirroring WasteBag's rule that a None bag must not
be confused with an all-zero one.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

_ABSOLUTE_MARKER = "absolute.py"
_JUDGE_MARKER = "assertion.py"
# Native promptfoo assertion types that gate (design doc 4.5). They carry no
# `value` path, so they are recognised by `type` instead of by marker.
_ABSOLUTE_TYPES = {"cost", "latency"}


class GateVerdict(str, Enum):
    PASS = "pass"
    FAIL_ABSOLUTE = "fail_absolute"
    FAIL_REGRESSION = "fail_regression"
    ERRORED = "errored"


class JudgeStatus(str, Enum):
    MEASURED = "measured"
    UNAVAILABLE = "unavailable"
    NO_BASELINE = "no_baseline"


class PromptGateResult(BaseModel):
    verdict: GateVerdict
    judge_status: JudgeStatus
    reason: str
    role: str = ""
    case: str = ""
    prompt_sha_baseline: str = ""
    prompt_sha_working: str = ""
    mean_baseline: float | None = None
    mean_working: float | None = None
    delta: float | None = None
    floor: float | None = None
    n_baseline: int = 0
    n_working: int = 0
    absolute_failures: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _rows(results: dict) -> list[dict]:
    return (results.get("results") or {}).get("results") or []


def _components(row: dict) -> list[dict]:
    return (row.get("gradingResult") or {}).get("componentResults") or []


def _label(row: dict) -> str:
    return (row.get("provider") or {}).get("label", "")


def _scores(rows: list[dict]) -> list[float | None]:
    out: list[float | None] = []
    for row in rows:
        for c in _components(row):
            if _JUDGE_MARKER in str((c.get("assertion") or {}).get("value")):
                out.append(c.get("score"))
    return out


def _absolute_failures(rows: list[dict]) -> list[str]:
    """Failures of any ABSOLUTE check: the output-type assertion (matched by
    file marker) and the native cost/latency gates (matched by type)."""
    out: list[str] = []
    for row in rows:
        for c in _components(row):
            a = c.get("assertion") or {}
            is_absolute = (
                _ABSOLUTE_MARKER in str(a.get("value")) or a.get("type") in _ABSOLUTE_TYPES
            )
            if is_absolute and not c.get("pass", True):
                out.append(c.get("reason") or f"{a.get('type', 'absolute')} assertion failed")
    return out


def _stderr(vals: list[float]) -> float:
    """Standard error of the mean. Zero for n < 2 -- with one sample there is
    no variance estimate, so the fixed floor decides (design doc 4.5)."""
    if len(vals) < 2:
        return 0.0
    return statistics.stdev(vals) / (len(vals) ** 0.5)


def decide(results: dict, *, delta_min: float = 0.05) -> PromptGateResult:
    rows = _rows(results)
    base_rows = [r for r in rows if _label(r) == "baseline"]
    work_rows = [r for r in rows if _label(r) == "working"]

    errors = [r["error"] for r in rows if r.get("error")]
    if errors:
        return PromptGateResult(
            verdict=GateVerdict.ERRORED,
            judge_status=JudgeStatus.UNAVAILABLE,
            reason=f"gate could not run — provider error: {errors[0]} "
            f"(this is NOT a prompt regression)",
        )

    failures = _absolute_failures(work_rows)
    if failures:
        return PromptGateResult(
            verdict=GateVerdict.FAIL_ABSOLUTE,
            judge_status=JudgeStatus.UNAVAILABLE,
            absolute_failures=failures,
            reason=f"absolute check failed: {failures[0]}",
        )

    base = [s for s in _scores(base_rows) if s is not None]
    work = [s for s in _scores(work_rows) if s is not None]

    if not base_rows:
        return PromptGateResult(
            verdict=GateVerdict.PASS,
            judge_status=JudgeStatus.NO_BASELINE,
            mean_working=statistics.fmean(work) if work else None,
            n_working=len(work),
            reason="no committed baseline — working-tree score only",
        )

    if not base or not work:
        return PromptGateResult(
            verdict=GateVerdict.PASS,
            judge_status=JudgeStatus.UNAVAILABLE,
            n_baseline=len(base),
            n_working=len(work),
            reason="judge unavailable on at least one side — regression NOT "
            "evaluated (not measured, not passed)",
        )

    mb, mw = statistics.fmean(base), statistics.fmean(work)
    delta = mw - mb
    pooled = (_stderr(base) ** 2 + _stderr(work) ** 2) ** 0.5
    floor = max(delta_min, 2 * pooled)

    regressed = mw < mb - floor
    return PromptGateResult(
        verdict=GateVerdict.FAIL_REGRESSION if regressed else GateVerdict.PASS,
        judge_status=JudgeStatus.MEASURED,
        mean_baseline=mb,
        mean_working=mw,
        delta=delta,
        floor=floor,
        n_baseline=len(base),
        n_working=len(work),
        reason=(
            f"{'regression' if regressed else 'within noise'}: "
            f"baseline {mb:.2f} -> working {mw:.2f} "
            f"(delta {delta:+.2f}, floor {floor:.2f})"
        ),
    )


def write_result(result: PromptGateResult, out_dir: Path) -> Path:
    """Prompt-gate results live in runs/prompt_evals/ and are joined to
    BenchmarkRecord ONLY by prompt_sha. They must never be written into the
    benchmark record stream -- build_heatmap divides by distinct run_id, so
    runless records would deflate real cases' rework density (design doc 2)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = result.created_at.strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{ts}-{result.role or 'role'}-{result.case or 'case'}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_eval_verdict.py -v`
Expected: PASS — 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/eval/verdict.py tests/test_eval_verdict.py
git commit -m "feat(eval): pure gate verdict with noise-aware floor (E-82)"
```

---

### Task 10: promptfoo contract test (no API keys)

**Files:**
- Modify: `pyproject.toml` (add the `eval` extra)
- Test: `tests/test_promptfoo_contract.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — it proves the *installed promptfoo* accepts our config shape.
- Produces: `promptfoo_available() -> bool` (importable by Task 11).

This catches promptfoo changing its config schema on a version bump, and costs nothing: the provider is a canned file returning a fixed string.

- [ ] **Step 1: Add the `eval` extra**

In `pyproject.toml` under `[project.optional-dependencies]`, add:

```toml
eval = ["promptfoo>=0.118"]
```

Keep it out of `dev` so `pip install -e .[dev]` does not pull a Node-backed tool on contributors who only run unit tests.

- [ ] **Step 2: Write the failing test**

Create `tests/test_promptfoo_contract.py`:

```python
"""Does the INSTALLED promptfoo still accept our config shape?

Needs promptfoo on PATH but no API keys: the provider is canned. This is the
test that catches a promptfoo version bump changing the schema.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
import yaml

pytestmark = pytest.mark.skipif(
    shutil.which("promptfoo") is None, reason="promptfoo not installed (pip install -e .[eval])"
)

CANNED = """
def call_api(prompt, options, context):
    return {"output": "canned-" + options["config"]["tag"], "error": None}
"""


def test_config_shape_is_accepted(tmp_path):
    (tmp_path / "canned.py").write_text(CANNED, encoding="utf-8")
    cfg = {
        "description": "contract",
        "prompts": ["{{input}}"],
        "providers": [
            {
                "id": f"file://{tmp_path / 'canned.py'}:call_api",
                "label": "baseline",
                "config": {"tag": "a"},
            },
            {
                "id": f"file://{tmp_path / 'canned.py'}:call_api",
                "label": "working",
                "config": {"tag": "b"},
            },
        ],
        "defaultTest": {"assert": [{"type": "contains", "value": "canned-"}]},
        "tests": [{"vars": {"input": "x"}}],
    }
    (tmp_path / "promptfooconfig.yaml").write_text(
        yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8"
    )

    out = tmp_path / "results.json"
    proc = subprocess.run(
        ["promptfoo", "eval", "-c", str(tmp_path / "promptfooconfig.yaml"), "--output", str(out)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert out.is_file(), f"promptfoo produced no output.\n{proc.stderr}"

    data = json.loads(out.read_text(encoding="utf-8"))
    rows = data["results"]["results"]
    labels = {r["provider"]["label"] for r in rows}
    assert labels == {"baseline", "working"}, f"provider labels moved in results.json: {labels}"
    assert all("gradingResult" in r for r in rows), (
        "gradingResult key moved — eval/verdict.py reads it"
    )
```

- [ ] **Step 3: Install promptfoo and run the test**

Run: `pip install -e .[eval] && python -m pytest tests/test_promptfoo_contract.py -v`
Expected: PASS. If the assertions about `results.results`, `provider.label`, or `gradingResult` fail, promptfoo's output schema has moved — update `src/sdlc/eval/verdict.py`'s accessors (`_rows`, `_label`, `_components`) to match, and re-run Task 9's tests.

- [ ] **Step 4: Verify a bare install still skips cleanly**

Run: `python -m pytest tests/test_promptfoo_contract.py -v` in an environment without promptfoo (or temporarily rename the binary).
Expected: SKIPPED with the "promptfoo not installed" reason — never an error.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_promptfoo_contract.py
git commit -m "test(eval): promptfoo config-shape contract test + eval extra (E-82)"
```

---

### Task 11: The gate — runner + pytest marker

**Files:**
- Create: `src/sdlc/eval/gate.py`
- Modify: `pyproject.toml` (add the `prompt_eval` marker)
- Test: `tests/test_prompt_gate.py`

**Interfaces:**
- Consumes: `build_config` (Task 8), `decide` / `write_result` / `GateVerdict` / `JudgeStatus` / `PromptGateResult` (Task 9), `resolve_instructions` (Task 5).
- Produces: `run_gate(role, case, *, repo_root, cases_root, agents_dir, judge_model, repeat=3, delta_min=0.05, baseline_ref="HEAD", max_calls=40, out_dir=None) -> PromptGateResult`; `GateUnavailable`; `prompt_sha(role, ref, repo_root, agents_dir) -> str`.

`max_calls` is the spec §6 runaway guard. It is **pre-flight**, not post-hoc: the planned call count is fully known before anything runs (`repeat × 2 providers × 2 calls each` — one agent, one judge), so the guard actually prevents the spend rather than reporting it afterwards.

- [ ] **Step 1: Add the marker**

In `pyproject.toml` under `[tool.pytest.ini_options] markers`, add:

```toml
    "prompt_eval: A/B-scores a role prompt against a fixture; spends tokens; skipped unless SDLC_PROMPT_EVAL=1",
```

Then extend `addopts` so it is excluded by default, matching the existing style:

```toml
addopts = "-q -m 'not slow and not temporal and not docker and not prompt_eval'"
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_prompt_gate.py`:

```python
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from sdlc.eval.gate import GateUnavailable, prompt_sha, run_gate
from sdlc.eval.verdict import GateVerdict

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "benchmarks" / "cases"
AGENTS = ROOT / "agents"

_OPT_IN = os.environ.get("SDLC_PROMPT_EVAL") == "1"


def test_prompt_sha_matches_the_registry_hash():
    """The join key to BenchmarkRecord.prompt_sha must be the same sha256
    over the same bytes (agents/roles.py:108-111)."""
    import hashlib

    text = (AGENTS / "clarify" / "instructions.md").read_text(encoding="utf-8")
    assert prompt_sha("clarify", "worktree", ROOT, AGENTS) == (
        hashlib.sha256(text.encode()).hexdigest()
    )


def test_missing_promptfoo_raises_when_explicitly_opted_in(monkeypatch):
    """Opt-in means 'I intend to run this'. Silently skipping an explicitly
    requested gate is the worst outcome available (design doc 6)."""
    monkeypatch.setattr("sdlc.eval.gate.shutil.which", lambda _: None)
    with pytest.raises(GateUnavailable) as e:
        run_gate(
            "clarify",
            "add-login-greenfield",
            repo_root=ROOT,
            cases_root=CASES,
            agents_dir=AGENTS,
            judge_model="openai/gpt-5.2",
        )
    assert "eval" in str(e.value)


def test_unchanged_prompt_passes_without_calling_a_model(monkeypatch, tmp_path):
    """Working tree == HEAD -> early exit, zero model calls."""
    monkeypatch.setattr("sdlc.eval.gate.shutil.which", lambda _: "promptfoo")
    monkeypatch.setattr(
        "sdlc.eval.gate._run_promptfoo", lambda *a, **k: pytest.fail("must not run promptfoo")
    )
    res = run_gate(
        "clarify",
        "add-login-greenfield",
        repo_root=ROOT,
        cases_root=CASES,
        agents_dir=AGENTS,
        judge_model="openai/gpt-5.2",
        out_dir=tmp_path,
    )
    assert res.verdict is GateVerdict.PASS
    assert "unchanged" in res.reason.lower()


def test_planned_call_count_over_the_ceiling_is_refused(monkeypatch, tmp_path):
    """Spec 6 runaway guard: refuse BEFORE spending, not after."""
    monkeypatch.setattr("sdlc.eval.gate.shutil.which", lambda _: "promptfoo")
    monkeypatch.setattr(
        "sdlc.eval.gate.prompt_sha", lambda role, ref, *a: ref
    )  # force base != working
    monkeypatch.setattr(
        "sdlc.eval.gate._run_promptfoo", lambda *a, **k: pytest.fail("must not run promptfoo")
    )
    with pytest.raises(GateUnavailable) as e:
        run_gate(
            "clarify",
            "add-login-greenfield",
            repo_root=ROOT,
            cases_root=CASES,
            agents_dir=AGENTS,
            judge_model="openai/gpt-5.2",
            repeat=50,
            max_calls=40,
            out_dir=tmp_path,
        )
    assert "200" in str(e.value)  # 50 * 2 providers * 2 calls


@pytest.mark.prompt_eval
@pytest.mark.skipif(not _OPT_IN, reason="set SDLC_PROMPT_EVAL=1 to run")
@pytest.mark.skipif(shutil.which("promptfoo") is None, reason="promptfoo not installed")
@pytest.mark.parametrize(
    "role,case",
    [
        ("clarify", "add-login-greenfield"),
        ("clarify", "cat-cafe-monitoring"),
        ("clarify", "todo-api-greenfield"),
        ("planner", "cat-cafe-monitoring"),
        ("qa", "cat-cafe-monitoring"),
    ],
)
def test_prompt_gate(role, case, tmp_path):
    res = run_gate(
        role,
        case,
        repo_root=ROOT,
        cases_root=CASES,
        agents_dir=AGENTS,
        judge_model="openai/gpt-5.2",
        out_dir=tmp_path,
    )
    assert res.verdict in (GateVerdict.PASS,), f"{role}/{case}: {res.verdict.value} — {res.reason}"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_prompt_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.gate'`

- [ ] **Step 4: Write the implementation**

Create `src/sdlc/eval/gate.py`:

```python
"""Run the prompt gate: generate config, run promptfoo, decide, record.

Surfaced as a pytest marker rather than a CI workflow because this repo has
no CI yet (design doc 4.7). It becomes a one-line CI step unchanged.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .promptfoo.config import build_config
from .promptfoo.provider import resolve_instructions
from .verdict import GateVerdict, JudgeStatus, PromptGateResult, decide, write_result

_DEFAULT_OUT = Path("runs") / "prompt_evals"
# One agent call + one judge call, per provider, per repetition.
_CALLS_PER_REPEAT = 2 * 2


class GateUnavailable(Exception):
    """The gate was explicitly requested but cannot run."""


def prompt_sha(role: str, ref: str, repo_root: Path, agents_dir: Path) -> str:
    """sha256 over the instructions bytes — the same hash agents/roles.py:108
    puts on BenchmarkRecord.prompt_sha, so the two instruments join."""
    text = resolve_instructions(role, ref, repo_root, agents_dir)
    return hashlib.sha256(text.encode()).hexdigest()


def _run_promptfoo(config_path: Path, out_path: Path) -> None:
    proc = subprocess.run(
        ["promptfoo", "eval", "-c", str(config_path), "--output", str(out_path)],
        capture_output=True,
        text=True,
        cwd=config_path.parent,
    )
    if not out_path.is_file():
        raise GateUnavailable(
            f"promptfoo produced no results.json (exit {proc.returncode}): "
            f"{proc.stderr.strip()[:400]}"
        )


def run_gate(
    role: str,
    case: str,
    *,
    repo_root: Path,
    cases_root: Path,
    agents_dir: Path,
    judge_model: str,
    repeat: int = 3,
    delta_min: float = 0.05,
    baseline_ref: str = "HEAD",
    max_calls: int = 40,
    out_dir: Path | None = None,
) -> PromptGateResult:
    if shutil.which("promptfoo") is None:
        raise GateUnavailable(
            "promptfoo is not installed. `pip install -e .[eval]` — the gate "
            "was explicitly requested, so this is a failure, not a skip."
        )

    sha_base = prompt_sha(role, baseline_ref, repo_root, agents_dir)
    sha_work = prompt_sha(role, "worktree", repo_root, agents_dir)

    if sha_base == sha_work:
        result = PromptGateResult(
            verdict=GateVerdict.PASS,
            judge_status=JudgeStatus.NO_BASELINE,
            role=role,
            case=case,
            prompt_sha_baseline=sha_base,
            prompt_sha_working=sha_work,
            reason=f"prompt unchanged vs {baseline_ref} — no model calls made",
        )
    else:
        planned = repeat * _CALLS_PER_REPEAT
        if planned > max_calls:
            raise GateUnavailable(
                f"planned {planned} model calls (repeat={repeat} × 2 "
                f"providers × 2 calls) exceeds max_calls={max_calls}. "
                f"Lower --n or raise the ceiling deliberately."
            )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
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
            )
            results_path = tmp_path / "results.json"
            _run_promptfoo(cfg, results_path)
            results = json.loads(results_path.read_text(encoding="utf-8"))
        result = decide(results, delta_min=delta_min)
        result.role, result.case = role, case
        result.prompt_sha_baseline = sha_base
        result.prompt_sha_working = sha_work

    write_result(result, out_dir or (repo_root / _DEFAULT_OUT))
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pip install -e . && python -m pytest tests/test_prompt_gate.py -v`
Expected: PASS — 4 passed, 5 skipped (the parametrized gate is opt-in)

- [ ] **Step 6: Verify the default suite still excludes the gate**

Run: `python -m pytest -q`
Expected: green, and no `prompt_eval` test runs. Confirm with `python -m pytest --collect-only -q -m prompt_eval | tail -3` (5 selected, 0 run under default addopts).

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/eval/gate.py tests/test_prompt_gate.py pyproject.toml
git commit -m "feat(eval): prompt gate as an opt-in pytest marker (E-82)"
```

---

### Task 12: CLI rewiring; retire `compare.py`

**Files:**
- Modify: `src/sdlc/eval/cli.py`, `src/sdlc/cli.py`
- Delete: `src/sdlc/eval/compare.py`
- Test: `tests/test_eval_cli_wiring.py` (create)

**Interfaces:**
- Consumes: `run_gate`, `GateUnavailable` (Task 11); `FixtureError` (Task 3); `RubricError` (Task 6).
- Produces: `run_eval(role, *, case, against, k, judge_model, gate) -> str` (rendered report), `EvalError` re-exported from `sdlc.eval.cli`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_cli_wiring.py`:

```python
from __future__ import annotations

from sdlc.cli import build_parser


def test_eval_parser_has_gate_and_no_capture_target():
    args = build_parser().parse_args(["eval", "clarify", "--gate"])
    assert args.cmd == "eval"
    assert args.target == "clarify"
    assert args.gate is True


def test_eval_defaults_to_advisory_report():
    assert build_parser().parse_args(["eval", "clarify"]).gate is False


def test_eval_accepts_case_and_repeat():
    args = build_parser().parse_args(
        ["eval", "planner", "--case", "cat-cafe-monitoring", "--n", "5"]
    )
    assert args.case == "cat-cafe-monitoring"
    assert args.k == 5


def test_against_is_threaded_to_the_baseline_ref(monkeypatch):
    """--against must reach run_gate as baseline_ref, not be a dead flag."""
    seen = {}

    def _fake(role, case, **kw):
        seen.update(kw)
        from sdlc.eval.verdict import GateVerdict, JudgeStatus, PromptGateResult

        return PromptGateResult(
            verdict=GateVerdict.PASS, judge_status=JudgeStatus.NO_BASELINE, reason="ok"
        )

    monkeypatch.setattr("sdlc.eval.cli.run_gate", _fake)
    from sdlc.eval.cli import run_eval

    run_eval(
        "clarify",
        case="add-login-greenfield",
        against="main",
        k=1,
        judge_model="openai/gpt-5.2",
        gate=False,
    )
    assert seen["baseline_ref"] == "main"


def test_eval_stays_client_free():
    """`eval` must not require a Temporal client — capture was the only
    target that did, and it is retired."""
    from sdlc.cli import _needs_temporal_client

    args = build_parser().parse_args(["eval", "clarify"])
    assert _needs_temporal_client(args) is False


def test_render_report_shows_verdict_and_delta():
    from sdlc.eval.cli import render_report
    from sdlc.eval.verdict import GateVerdict, JudgeStatus, PromptGateResult

    text = render_report(
        PromptGateResult(
            verdict=GateVerdict.FAIL_REGRESSION,
            judge_status=JudgeStatus.MEASURED,
            role="clarify",
            case="c",
            mean_baseline=0.85,
            mean_working=0.50,
            delta=-0.35,
            floor=0.05,
            reason="regression: baseline 0.85 -> working 0.50",
        )
    )
    assert "fail_regression" in text
    assert "-0.35" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_eval_cli_wiring.py -v`
Expected: FAIL — `AttributeError: 'Namespace' object has no attribute 'gate'`

- [ ] **Step 3: Rewrite `src/sdlc/eval/cli.py`**

Delete `run_capture`, `_history_to_events`, `_resolve_case`'s fixture-globbing branch, and the `compare` import. Replace with:

```python
"""CLI glue for `sdlc eval`: case resolution, gate invocation, rendering."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..agents.loader import _resolve_agents_dir
from .fixtures import FixtureError
from .gate import GateUnavailable, run_gate
from .verdict import GateVerdict, PromptGateResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASES_ROOT = _REPO_ROOT / "benchmarks" / "cases"
_BENCH_CONFIG = _REPO_ROOT / "benchmarks" / "config.yaml"

# (role, case) pairs the gate covers today. Grows as rubrics and seeds are
# authored -- no machinery change needed (design doc 8).
DEFAULT_PAIRS: list[tuple[str, str]] = [
    ("clarify", "add-login-greenfield"),
    ("clarify", "cat-cafe-monitoring"),
    ("clarify", "todo-api-greenfield"),
    ("planner", "cat-cafe-monitoring"),
    ("qa", "cat-cafe-monitoring"),
]


class EvalError(Exception):
    """A user-facing eval failure. The CLI prints it and exits non-zero."""


def default_judge_model(config_path: Path = _BENCH_CONFIG) -> str:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model = data.get("default_judge_model")
    if not model:
        raise EvalError(f"no default_judge_model in {config_path}; pass --judge-model")
    return model


def _resolve_case(role: str, case: str | None) -> str:
    if case:
        return case
    found = [c for r, c in DEFAULT_PAIRS if r == role]
    if len(found) == 1:
        return found[0]
    if not found:
        raise EvalError(
            f"role '{role}' has no gated case; add a (role, case) pair to "
            f"DEFAULT_PAIRS once its rubric and seed exist."
        )
    raise EvalError(f"role '{role}' covers multiple cases ({', '.join(found)}); pass --case.")


def render_report(r: PromptGateResult) -> str:
    head = f"eval {r.role} (case {r.case}) -> {r.verdict.value}"
    lines = [head, f"  {r.reason}"]
    if r.mean_baseline is not None:
        lines.append(f"  baseline  {r.mean_baseline:.2f}  (n={r.n_baseline})")
        lines.append(f"  working   {r.mean_working:.2f}  (n={r.n_working})")
        lines.append(f"  delta     {r.delta:+.2f}   floor {r.floor:.2f}")
    for f in r.absolute_failures:
        lines.append(f"  ABSOLUTE  {f}")
    return "\n".join(lines)


def run_eval(
    role: str, *, case: str | None, against: str, k: int, judge_model: str, gate: bool
) -> str:
    try:
        result = run_gate(
            role,
            _resolve_case(role, case),
            repo_root=_REPO_ROOT,
            cases_root=_CASES_ROOT,
            agents_dir=_resolve_agents_dir(),
            judge_model=judge_model,
            repeat=k,
            baseline_ref=against,
        )
    except (GateUnavailable, FixtureError) as e:
        raise EvalError(str(e)) from e
    text = render_report(result)
    if gate and result.verdict is not GateVerdict.PASS:
        raise EvalError(text)
    return text
```

- [ ] **Step 4: Rewire `src/sdlc/cli.py`**

In the `eval` parser block (`cli.py:223-229`): change the `target` help to `"a role name"`, delete the `--from` argument, and add:

```python
ev.add_argument("--gate", action="store_true", help="exit non-zero on a failing verdict")
ev.add_argument("--view", action="store_true", help="open the promptfoo viewer after the run")
```

At `cli.py:105`, simplify the local-only clause (capture was the only client-needing target):

```python
        or args.cmd == "eval"
```

Delete the `eval capture` validation block at `cli.py:300-303`.

Replace the dispatch at `cli.py:400-416` with:

```python
if args.cmd == "eval":
    from .eval.cli import EvalError, default_judge_model, run_eval

    try:
        judge = args.judge_model or default_judge_model()
        print(
            run_eval(
                args.target,
                case=args.case,
                against=args.against,
                k=args.k,
                judge_model=judge,
                gate=args.gate,
            )
        )
    except EvalError as e:
        print(f"eval error: {e}")
        raise SystemExit(1)
    if args.view:
        import subprocess

        subprocess.run(["promptfoo", "view"])
    return
```

Update the usage examples at `cli.py:15-16`:

```
  python -m sdlc.cli eval clarify --case add-login-greenfield --gate
  python -m sdlc.cli eval planner --case cat-cafe-monitoring --n 5
```

- [ ] **Step 5: Delete `compare.py` and run the full suite**

```bash
git rm src/sdlc/eval/compare.py
python -m pytest -q
```
Expected: green. Delete any remaining test that imported `compare` (`tests/test_eval_*.py` referencing `EvalReport` / `RunScore` / `compare`) — that surface is intentionally retired; `verdict.py` replaces it and is covered by Task 9.

- [ ] **Step 6: Verify the CLI end to end**

Run: `python -m sdlc.cli eval clarify --case add-login-greenfield`
Expected: with an unchanged prompt — `eval clarify (case add-login-greenfield) -> pass` and `prompt unchanged vs HEAD — no model calls made`.

- [ ] **Step 7: Update the README**

In `README.md`, replace the `sdlc eval capture` example with the two from Step 4, and add one line under **Develop**:

```markdown
- Prompt changes are gated: `SDLC_PROMPT_EVAL=1 python -m pytest -m prompt_eval`
  A/B-scores each changed `agents/<role>/instructions.md` against its committed
  baseline (needs `pip install -e .[eval]`; spends tokens). Results land in
  `runs/prompt_evals/` and join the benchmark record stream by `prompt_sha`
  only — they are never merged into the heatmap or SC rollup.
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(cli): sdlc eval runs the promptfoo gate; retire compare.py (E-82)"
```

---

## Verification

After Task 12, confirm all four global constraints hold:

```bash
python -m pytest -q                                   # green, zero model calls
python -m pytest --collect-only -q -m prompt_eval     # 5 selected, 0 run
git grep -n "BenchmarkRecord" src/sdlc/eval/          # must return nothing
git grep -n "compare\|run_capture" src/sdlc/          # must return nothing
```

Then run the gate itself once against an intentionally-degraded prompt to prove it fires:

```bash
# temporarily truncate a prompt, confirm FAIL_REGRESSION, then restore
git stash list && cp agents/clarify/instructions.md /tmp/keep.md
printf 'Answer briefly.\n' > agents/clarify/instructions.md
SDLC_PROMPT_EVAL=1 python -m sdlc.cli eval clarify --case add-login-greenfield --gate
cp /tmp/keep.md agents/clarify/instructions.md
```

Expected: non-zero exit with `fail_regression` (or `fail_absolute` if the truncated prompt stops producing a valid `ClarifiedRequirements` — either is a correct gate firing).
