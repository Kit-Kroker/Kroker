# Prompt Eval Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a stage-isolated, on-demand tool that A/B-scores a prompt edit — run one proposer agent on a frozen input with the working-tree `instructions.md` vs a committed one, judge both outputs against the case rubric, print the delta.

**Architecture:** A new `src/sdlc/eval/` module, independent of Temporal for the replay path. `sdlc eval capture --from <run_id>` harvests a proposer's input from a completed run's history (reusing `drift.py`'s `HistoryProvider` pattern) into `agents/<role>/fixtures/<case>.json`. `sdlc eval <role> [--against <ref>]` builds the proposer's `Agent` twice via `agents/<role>/agent.py`'s `build()`, runs each on the fixture, scores both with the existing `judge.py`, and renders the delta. Pure core (`fixtures`, `runner`, `compare`) is separated from the thin CLI shell.

**Tech Stack:** Python 3.11+, Pydantic v2, pydantic-ai (`TemporalAgent`, `Agent.run_sync`), PyYAML, git (subprocess), pytest. No Temporal for the eval command; a Temporal client only for `capture`.

**Spec:** `docs/superpowers/specs/2026-07-18-prompt-eval-loop-design.md`

## Global Constraints

- **Six supported roles only:** `clarify`, `planner`, `qa`, `reviewer`, `analyst`, `merge_verdict`. `architect` and `research` carry `deps` and are **refused** with a clear message — never silently degraded (spec finding 5).
- **Reuse, do not reinvent.** Scoring is `judge.py`'s `judge_artifact.sync` / `_set_judge_fn` unchanged. Rubrics are the existing `benchmarks/cases/<case>/` assets read via `case.yaml`'s `rubrics` map. The judge-vs-author cross-family check is `sdlc.agents.loader.model_family` (ADR-6). Agent construction is the loader's existing `_load_build`.
- **Do not touch** `feature.py`, `judge.py`, `drift.py`, the registry loader's contract, `PROMPT_SHAS`, or any `instructions.md` content. This increment only *adds* `src/sdlc/eval/`, wires the CLI, and adds a `fixtures/` regression test.
- **The eval command is synchronous and local-only** (no Temporal client, no asyncio) — mirrors `cli.py`'s `_local_only` path. Only `eval capture` connects a client.
- **Agent/role name split is real:** role `qa` → agent `qa_analyst_agent`, role `merge_verdict` → agent `merge_verdict_agent`. The reverse map (agent → role) is pinned in Task 1; verified against `roles.py` at HEAD.
- **Rubrics are per-case.** A role has an eval-able rubric only if `case.yaml`'s `rubrics` map contains its rubric-key. Today only `clarify` (key `clarifier`) does; the others become eval-able when someone authors `rubric-<key>.md` and lists it. A missing rubric is a clear error, not a crash.
- Run the full suite with `python -m pytest` from the repo root. All new tests are deterministic — no real model or judge calls (a `FunctionModel`/`TestModel` stub, a fake judge via `_set_judge_fn`, synthetic history, a tmp git repo).

---

### Task 1: `EvalFixture` + capture core (`fixtures.py`)

Defines the fixture model and the pure `capture()` that turns a completed run's (normalized) history into fixtures on disk. Message-shape parsing is validated against **real** serialized pydantic-ai messages so nothing is guessed. The live Temporal→events adapter is a documented seam, exactly as `drift.py` ships its real provider unimplemented and fake-tested.

**Files:**
- Create: `src/sdlc/eval/__init__.py` (empty)
- Create: `src/sdlc/eval/fixtures.py`
- Test: `tests/test_eval_fixtures.py`

**Interfaces:**
- Consumes: `sdlc.benchmarks.drift.HistoryProvider` (the Protocol — `fetch_history(run_id)`); `pydantic_ai.messages` message types (test only).
- Produces:
  - `SUPPORTED_ROLES: frozenset[str]` and `DEPS_ROLES: frozenset[str]`.
  - `AGENT_TO_ROLE: dict[str, str]` — reverse of `roles.py`'s role→agent-name map, limited to supported roles.
  - `class EvalFixture(BaseModel)` — `role, case, prompt, model, source_run_id, captured_at`.
  - `extract_user_prompt(messages: list[dict]) -> str | None` — first `UserPromptPart` text from a serialized message list.
  - `fixtures_from_events(run_id, case, events, registry) -> list[EvalFixture]` — pure; consumes normalized event dicts.
  - `write_fixtures(fixtures, agents_dir) -> list[Path]` — writes `agents/<role>/fixtures/<case>.json`.
  - `load_fixture(path) -> EvalFixture` — read one fixture back (consumed by Task 3).

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_fixtures.py`:

```python
"""Capture: a completed run's history -> agents/<role>/fixtures/<case>.json.

Pure core only (no live Temporal), mirroring tests/test_drift_harvester.py.
The message-shape assertion uses REAL pydantic-ai message objects serialized
to dicts, so extract_user_prompt is pinned to the shape the runtime actually
produces rather than a guessed one.
"""
import json
from datetime import datetime

from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

from sdlc.eval.fixtures import (
    AGENT_TO_ROLE, DEPS_ROLES, SUPPORTED_ROLES, EvalFixture,
    extract_user_prompt, fixtures_from_events, write_fixtures,
)


def _serialized_messages(system: str, user: str) -> list[dict]:
    """One ModelRequest with a system part and a user part, dumped the way the
    Temporal activity payload carries it."""
    req = ModelRequest(parts=[SystemPromptPart(content=system),
                              UserPromptPart(content=user)])
    return [req.model_dump(mode="json")]


def test_supported_and_deps_role_sets():
    assert SUPPORTED_ROLES == frozenset(
        {"clarify", "planner", "qa", "reviewer", "analyst", "merge_verdict"})
    assert DEPS_ROLES == frozenset({"architect", "research"})
    # the two roles whose agent name is not their role name
    assert AGENT_TO_ROLE["qa_analyst_agent"] == "qa"
    assert AGENT_TO_ROLE["merge_verdict_agent"] == "merge_verdict"


def test_extract_user_prompt_from_real_messages():
    msgs = _serialized_messages("SYS", "the user prompt")
    assert extract_user_prompt(msgs) == "the user prompt"


def test_extract_user_prompt_none_when_absent():
    req = ModelRequest(parts=[SystemPromptPart(content="only system")])
    assert extract_user_prompt([req.model_dump(mode="json")]) is None


def test_fixtures_from_events_builds_one_per_supported_proposer():
    events = [
        {"activity": "clarify_agent__model_request",
         "input": {"messages": _serialized_messages("s", "clarify input")}},
        {"activity": "reviewer_agent__model_request",
         "input": {"messages": _serialized_messages("s", "review input")}},
        {"activity": "architect_agent__model_request",       # deps role: skip
         "input": {"messages": _serialized_messages("s", "arch input")}},
        {"activity": "run_coding_task", "input": {}},         # not a proposer
    ]
    registry = {"clarify": type("R", (), {"model": "anthropic:glm-5.2"})(),
                "reviewer": type("R", (), {"model": "anthropic:glm-5.2"})()}
    fx = fixtures_from_events("feature-1", "add-login-greenfield", events, registry)
    got = {f.role: f for f in fx}
    assert set(got) == {"clarify", "reviewer"}
    assert got["clarify"].prompt == "clarify input"
    assert got["reviewer"].model == "anthropic:glm-5.2"
    assert got["clarify"].source_run_id == "feature-1"


def test_write_fixtures_lands_beside_the_asset(tmp_path):
    agents = tmp_path / "agents"
    (agents / "clarify").mkdir(parents=True)
    fx = EvalFixture(role="clarify", case="add-login-greenfield",
                     prompt="p", model="anthropic:glm-5.2",
                     source_run_id="feature-1", captured_at=datetime(2026, 7, 18))
    paths = write_fixtures([fx], agents)
    assert paths == [agents / "clarify" / "fixtures" / "add-login-greenfield.json"]
    loaded = json.loads(paths[0].read_text(encoding="utf-8"))
    assert loaded["prompt"] == "p" and loaded["role"] == "clarify"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_eval_fixtures.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval'`

- [ ] **Step 3: Create the empty package marker**

Create `src/sdlc/eval/__init__.py` with a single line:

```python
"""Prompt eval loop (E-4): stage-isolated A/B scoring of a prompt edit."""
```

- [ ] **Step 4: Write `fixtures.py`**

Create `src/sdlc/eval/fixtures.py`:

```python
"""Fixtures for the prompt eval loop: a proposer's frozen input, captured
from a completed run's history.

Pure core here; the live Temporal->events adapter is a documented seam (see
capture_cli in cli.py), mirroring drift.py whose real HistoryProvider ships
unimplemented and fake-tested. A fixture is trivial JSON, so it can also be
hand-authored when a live run is not available.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Role name is not always the agent name (roles.py). Reverse map, limited to
# the six pure prompt-in/artifact-out proposers.
_ROLE_TO_AGENT = {
    "clarify": "clarify_agent",
    "planner": "planner_agent",
    "qa": "qa_analyst_agent",
    "reviewer": "reviewer_agent",
    "analyst": "analyst_agent",
    "merge_verdict": "merge_verdict_agent",
}
AGENT_TO_ROLE: dict[str, str] = {a: r for r, a in _ROLE_TO_AGENT.items()}
SUPPORTED_ROLES: frozenset[str] = frozenset(_ROLE_TO_AGENT)

# architect + research pass deps to .run(); a prompt-string fixture cannot
# reconstruct a live deps object, so they are refused (spec finding 5).
DEPS_ROLES: frozenset[str] = frozenset({"architect", "research"})

# TemporalModel names its request activity "<agent_name>__model_request"
# (pydantic_ai/durable_exec/temporal/_model.py).
_REQUEST_SUFFIX = "__model_request"


class EvalFixture(BaseModel):
    role: str
    case: str
    prompt: str
    model: str
    source_run_id: str
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc))


def _role_for_activity(activity: str) -> str | None:
    if not activity.endswith(_REQUEST_SUFFIX):
        return None
    agent = activity[: -len(_REQUEST_SUFFIX)]
    return AGENT_TO_ROLE.get(agent)          # None for deps/unsupported roles


def extract_user_prompt(messages: list[dict[str, Any]]) -> str | None:
    """First UserPromptPart's text from a serialized message list. The initial
    request's user prompt is the frozen input; later requests (tool retries)
    are ignored by taking the first."""
    for msg in messages:
        for part in msg.get("parts", []):
            if part.get("part_kind") == "user-prompt":
                content = part.get("content")
                if isinstance(content, str):
                    return content
                # content can be a list of parts; join the string ones
                if isinstance(content, list):
                    text = "".join(c for c in content if isinstance(c, str))
                    if text:
                        return text
    return None


def fixtures_from_events(run_id: str, case: str, events: list[dict[str, Any]],
                         registry: dict[str, Any]) -> list[EvalFixture]:
    """Pure: normalized history events -> one fixture per supported proposer.

    A normalized event is a dict with "activity" (str) and "input" (dict with
    "messages": list[serialized ModelMessage]). The model is read from the
    registry (a role's declared model), not the event: TemporalModel omits
    model_id from the payload when the default model is used."""
    out: dict[str, EvalFixture] = {}
    for ev in events:
        activity = ev.get("activity")
        if not isinstance(activity, str):
            continue
        role = _role_for_activity(activity)
        if role is None or role in out:          # skip unsupported + keep first
            continue
        cfg = registry.get(role)
        if cfg is None:                          # role not in this registry
            continue
        messages = (ev.get("input") or {}).get("messages")
        if not isinstance(messages, list):
            continue
        prompt = extract_user_prompt(messages)
        if prompt is None:
            continue
        out[role] = EvalFixture(role=role, case=case, prompt=prompt,
                                model=cfg.model, source_run_id=run_id)
    return list(out.values())


def write_fixtures(fixtures: list[EvalFixture], agents_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for fx in fixtures:
        d = agents_dir / fx.role / "fixtures"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{fx.case}.json"
        p.write_text(fx.model_dump_json(indent=2), encoding="utf-8")
        paths.append(p)
    return paths


def load_fixture(path: Path) -> EvalFixture:
    return EvalFixture.model_validate_json(path.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_eval_fixtures.py -v`
Expected: 5 passed.

If `test_extract_user_prompt_from_real_messages` fails on the `part_kind`/`content` shape, print the actual dict and align `extract_user_prompt` to it — the test is the source of truth for the runtime shape, never the other way around:
```python
python -c "from pydantic_ai.messages import ModelRequest, UserPromptPart; import json; print(json.dumps(ModelRequest(parts=[UserPromptPart(content='x')]).model_dump(mode='json'), indent=2))"
```

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/eval/__init__.py src/sdlc/eval/fixtures.py tests/test_eval_fixtures.py
git commit -m "feat(eval): EvalFixture + pure capture core (E-4)

Turns a completed run's normalized history into agents/<role>/fixtures/<case>.json
for the six supported proposers. Agent->role reverse map handles the qa /
merge_verdict name split. Message parsing is pinned against real serialized
pydantic-ai messages. Deps roles (architect/research) are skipped. The live
Temporal->events adapter is a seam wired in Task 4, as drift.py does.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Replay one variant (`runner.py`)

Builds a proposer `Agent` from supplied instructions text and runs it on a fixture prompt, returning the serialized output. The load-bearing guarantee: the supplied text actually becomes the system prompt.

**Files:**
- Create: `src/sdlc/eval/runner.py`
- Test: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `sdlc.agents.loader._load_build` (per-role `agent.py` importer, E-1); `sdlc.agents.roles.MODEL_SETTINGS`; `EvalFixture` (Task 1).
- Produces: `run_variant(role, instructions_text, fixture, agents_dir, *, model_override=None) -> str` — the agent output serialized to a JSON string.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_runner.py`:

```python
"""run_variant builds the proposer agent from SUPPLIED instructions text and
runs it. The critical assertion: the supplied text reaches the system prompt.
A run_variant that ignored its argument and read the shipped file would score
both variants identically and silently defeat the whole tool."""
from datetime import datetime, timezone

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from sdlc.eval.fixtures import EvalFixture
from sdlc.eval.runner import run_variant
from tests.conftest import write_registry_dir

seen_system: list[str] = []


def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    # first message is the ModelRequest carrying the system prompt
    for part in messages[0].parts:
        if part.part_kind == "system-prompt":
            seen_system.append(part.content)
    return ModelResponse(parts=[TextPart("canned output")])


def _fixture(role="reviewer"):
    return EvalFixture(role=role, case="c", prompt="the frozen input",
                       model="anthropic:glm-5.2", source_run_id="r",
                       captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))


def test_run_variant_puts_supplied_text_in_system_prompt(tmp_path):
    seen_system.clear()
    root = write_registry_dir(tmp_path / "agents")
    out = run_variant("reviewer", "VARIANT-B INSTRUCTIONS", _fixture(),
                      root, model_override=FunctionModel(_fn))
    assert out == '"canned output"' or "canned output" in out
    assert seen_system == ["VARIANT-B INSTRUCTIONS"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_eval_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.runner'`

- [ ] **Step 3: Write `runner.py`**

Create `src/sdlc/eval/runner.py`:

```python
"""Replay: build a proposer agent from supplied instructions text and run it
on a fixture prompt. No Temporal — a plain synchronous model call."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..agents.loader import _load_build
from ..agents.roles import MODEL_SETTINGS
from .fixtures import EvalFixture


def _to_json(output: Any) -> str:
    """Proposer outputs are pydantic models; a bare-string test agent is not.
    Serialize either to a JSON string."""
    dump = getattr(output, "model_dump_json", None)
    if callable(dump):
        return dump()
    return json.dumps(output)


def run_variant(role: str, instructions_text: str, fixture: EvalFixture,
                agents_dir: Path, *, model_override: Any | None = None) -> str:
    """Build agents/<role>/agent.py's Agent with instructions_text as its
    system prompt, run it on the fixture prompt, return serialized output.

    model_override lets tests inject a FunctionModel/TestModel; production
    passes nothing and the captured author model (fixture.model) is used, so
    both variants run under the same model and only the prompt differs.
    """
    build = _load_build(role, agents_dir / role)
    model = model_override if model_override is not None else fixture.model
    agent = build(model, instructions_text, MODEL_SETTINGS)
    result = agent.run_sync(fixture.prompt)
    return _to_json(result.output)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_eval_runner.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the fixtures test too (no regression)**

Run: `python -m pytest tests/test_eval_fixtures.py tests/test_eval_runner.py -v`
Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/eval/runner.py tests/test_eval_runner.py
git commit -m "feat(eval): run_variant replays a proposer with supplied instructions (E-4)

Builds agents/<role>/agent.py's Agent via the loader's _load_build, sets the
supplied text as system_prompt, runs run_sync on the fixture prompt. A
FunctionModel test pins that the supplied text actually reaches the system
prompt -- the anti-no-op guard. model_override injects the test model; prod
uses the captured author model so only the prompt differs between A and B.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Compare A vs B and score (`compare.py`)

Reads both instruction variants (working tree + a git ref), loads the case rubric, runs each variant, judges both, and returns a pure `EvalReport`.

**Files:**
- Create: `src/sdlc/eval/compare.py`
- Test: `tests/test_eval_compare.py`

**Interfaces:**
- Consumes: `run_variant` (Task 2); `load_fixture`, `EvalFixture`, `SUPPORTED_ROLES`, `DEPS_ROLES` (Task 1); `sdlc.benchmarks.judge` (`JudgeInput`, `judge_artifact`, `_set_judge_fn`); `sdlc.agents.loader.model_family`.
- Produces:
  - `class EvalError(Exception)`.
  - `RUBRIC_KEY: dict[str, str]` — role → rubric-key used in `case.yaml`'s `rubrics` map.
  - `class RunScore(BaseModel)` — `score_a, score_b, delta, components_a, components_b`.
  - `class EvalReport(BaseModel)` — `role, case, judge_model, against_ref, unchanged, no_baseline, runs, mean_a, mean_b, mean_delta`.
  - `read_ref_text(ref, rel_path, repo_root) -> str | None` — `git show <ref>:<rel_path>`, `None` if absent.
  - `load_rubric(case, role, cases_root) -> str` — from `case.yaml`'s `rubrics` map; raises `EvalError` if none.
  - `compare(role, case, *, against_ref, k, agents_dir, cases_root, repo_root, judge_model) -> EvalReport`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_compare.py`:

```python
"""compare() orchestration, with a fake judge (no model calls). git-ref and
rubric IO exercised against tmp dirs."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sdlc.benchmarks.judge import _set_judge_fn
from sdlc.eval.compare import (
    EvalError, RUBRIC_KEY, compare, load_rubric, read_ref_text,
)
from sdlc.eval.fixtures import EvalFixture, write_fixtures


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True,
                   capture_output=True, text=True)


def _repo_with_instructions(root: Path, role: str, committed: str, working: str):
    role_dir = root / "agents" / role
    role_dir.mkdir(parents=True)
    (role_dir / "instructions.md").write_bytes(committed.encode())
    _git(root, "init"); _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init")
    (role_dir / "instructions.md").write_bytes(working.encode())   # dirty tree


def _case_with_rubric(cases_root: Path, case: str, role: str, rubric_body: str):
    cdir = cases_root / case
    cdir.mkdir(parents=True)
    key = RUBRIC_KEY[role]
    (cdir / f"rubric-{key}.md").write_bytes(rubric_body.encode())
    (cdir / "case.yaml").write_text(
        f"case_id: {case}\nrubrics:\n  {key}: rubric-{key}.md\n", encoding="utf-8")


def test_read_ref_text_reads_committed_version(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "COMMITTED", "WORKING")
    got = read_ref_text("HEAD", "agents/reviewer/instructions.md", tmp_path)
    assert got == "COMMITTED"


def test_read_ref_text_none_when_missing(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "X", "Y")
    assert read_ref_text("HEAD", "agents/reviewer/fixtures/nope.md", tmp_path) is None


def test_load_rubric_from_case_yaml(tmp_path):
    _case_with_rubric(tmp_path, "c1", "clarify", "RUBRIC TEXT")
    assert load_rubric("c1", "clarify", tmp_path) == "RUBRIC TEXT"


def test_load_rubric_missing_raises(tmp_path):
    (tmp_path / "c1").mkdir()
    (tmp_path / "c1" / "case.yaml").write_text("case_id: c1\nrubrics: {}\n",
                                               encoding="utf-8")
    with pytest.raises(EvalError, match="rubric"):
        load_rubric("c1", "reviewer", tmp_path)


def test_compare_scores_both_and_reports_delta(tmp_path, monkeypatch):
    _repo_with_instructions(tmp_path, "reviewer", "OLD PROMPT", "NEW PROMPT")
    _case_with_rubric(tmp_path / "cases", "c1", "reviewer", "be good")
    fx = EvalFixture(role="reviewer", case="c1", prompt="input",
                     model="anthropic:glm-5.2", source_run_id="r",
                     captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))
    write_fixtures([fx], tmp_path / "agents")

    # runner returns the system prompt it saw, so the fake judge can score A!=B
    monkeypatch.setattr("sdlc.eval.compare.run_variant",
                        lambda role, text, fixture, agents_dir, **k: text)
    _set_judge_fn(lambda inp: '{"score": %s, "components": {}}'
                  % ("0.9" if "NEW" in inp.artifact_json else "0.5"))
    try:
        rep = compare("reviewer", "c1", against_ref="HEAD", k=1,
                      agents_dir=tmp_path / "agents", cases_root=tmp_path / "cases",
                      repo_root=tmp_path, judge_model="openai/gpt-5.2")
    finally:
        _set_judge_fn(None)
    assert rep.mean_a == 0.5 and rep.mean_b == 0.9
    assert round(rep.mean_delta, 2) == 0.4
    assert not rep.unchanged


def test_compare_short_circuits_when_unchanged(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "SAME", "SAME")
    _case_with_rubric(tmp_path / "cases", "c1", "reviewer", "r")
    fx = EvalFixture(role="reviewer", case="c1", prompt="i",
                     model="anthropic:glm-5.2", source_run_id="r",
                     captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))
    write_fixtures([fx], tmp_path / "agents")
    rep = compare("reviewer", "c1", against_ref="HEAD", k=1,
                  agents_dir=tmp_path / "agents", cases_root=tmp_path / "cases",
                  repo_root=tmp_path, judge_model="openai/gpt-5.2")
    assert rep.unchanged and rep.runs == []


def test_compare_rejects_same_family_judge(tmp_path):
    _repo_with_instructions(tmp_path, "reviewer", "A", "B")
    _case_with_rubric(tmp_path / "cases", "c1", "reviewer", "r")
    fx = EvalFixture(role="reviewer", case="c1", prompt="i",
                     model="anthropic:glm-5.2", source_run_id="r",
                     captured_at=datetime(2026, 7, 18, tzinfo=timezone.utc))
    write_fixtures([fx], tmp_path / "agents")
    with pytest.raises(EvalError, match="family"):
        compare("reviewer", "c1", against_ref="HEAD", k=1,
                agents_dir=tmp_path / "agents", cases_root=tmp_path / "cases",
                repo_root=tmp_path, judge_model="anthropic:other")  # same family
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_eval_compare.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.eval.compare'`

- [ ] **Step 3: Write `compare.py`**

Create `src/sdlc/eval/compare.py`:

```python
"""Compare a working-tree prompt against a committed one: run each variant on
the fixture, judge both against the case rubric, return a pure EvalReport."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..agents.loader import model_family
from ..benchmarks.judge import JudgeInput, judge_artifact
from .fixtures import DEPS_ROLES, SUPPORTED_ROLES, load_fixture
from .runner import run_variant


class EvalError(Exception):
    """A user-facing eval failure (bad role, missing fixture/rubric, same-family
    judge). The CLI turns it into a message + non-zero exit."""


# role -> the key used in case.yaml's `rubrics:` map. Only `clarifier` has a
# shipped rubric today; the rest become eval-able when a rubric-<key>.md is
# authored and listed in a case.yaml.
RUBRIC_KEY: dict[str, str] = {
    "clarify": "clarifier",
    "planner": "planner",
    "qa": "qa",
    "reviewer": "reviewer",
    "analyst": "analyst",
    "merge_verdict": "merge_verdict",
}


class RunScore(BaseModel):
    score_a: float | None
    score_b: float | None
    delta: float | None
    components_a: dict[str, float] = Field(default_factory=dict)
    components_b: dict[str, float] = Field(default_factory=dict)


class EvalReport(BaseModel):
    role: str
    case: str
    judge_model: str
    against_ref: str
    unchanged: bool = False
    no_baseline: bool = False
    runs: list[RunScore] = Field(default_factory=list)
    mean_a: float | None = None
    mean_b: float | None = None
    mean_delta: float | None = None


def read_ref_text(ref: str, rel_path: str, repo_root: Path) -> str | None:
    """`git show <ref>:<rel_path>`; None if the path does not exist at ref."""
    proc = subprocess.run(["git", "show", f"{ref}:{rel_path}"],
                          cwd=repo_root, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def load_rubric(case: str, role: str, cases_root: Path) -> str:
    case_yaml = cases_root / case / "case.yaml"
    if not case_yaml.is_file():
        raise EvalError(f"no case.yaml at {case_yaml}")
    rubrics = (yaml.safe_load(case_yaml.read_text(encoding="utf-8")) or {}
               ).get("rubrics") or {}
    key = RUBRIC_KEY[role]
    rel = rubrics.get(key)
    if not rel:
        raise EvalError(
            f"no rubric for role '{role}' (key '{key}') in {case_yaml}. "
            f"Author benchmarks/cases/{case}/rubric-{key}.md and add it under "
            f"`rubrics:` before evaluating this role.")
    return (cases_root / case / rel).read_text(encoding="utf-8")


def _mean(vals: list[float | None]) -> float | None:
    nums = [v for v in vals if v is not None]
    return sum(nums) / len(nums) if nums else None


def compare(role: str, case: str, *, against_ref: str, k: int,
            agents_dir: Path, cases_root: Path, repo_root: Path,
            judge_model: str) -> EvalReport:
    if role in DEPS_ROLES:
        raise EvalError(
            f"role '{role}' carries deps; deps-aware eval is future work")
    if role not in SUPPORTED_ROLES:
        raise EvalError(f"unknown role '{role}'; supported: "
                        f"{', '.join(sorted(SUPPORTED_ROLES))}")

    fixture_path = agents_dir / role / "fixtures" / f"{case}.json"
    if not fixture_path.is_file():
        raise EvalError(
            f"no fixture at {fixture_path}. Create one with "
            f"`sdlc eval capture --from <run_id> --case {case}`.")
    fixture = load_fixture(fixture_path)

    if model_family(judge_model) == model_family(fixture.model):
        raise EvalError(
            f"judge model '{judge_model}' shares a family with the author "
            f"model '{fixture.model}' (ADR-6); pick a different family.")

    report = EvalReport(role=role, case=case, judge_model=judge_model,
                        against_ref=against_ref)

    rel = f"agents/{role}/instructions.md"
    b_text = (agents_dir / role / "instructions.md").read_text(encoding="utf-8")
    a_text = read_ref_text(against_ref, rel, repo_root)
    if a_text is None:
        report.no_baseline = True
    elif a_text == b_text:
        report.unchanged = True
        return report

    rubric = load_rubric(case, role, cases_root)

    def _score(artifact_json: str) -> tuple[float | None, dict[str, float]]:
        qs = judge_artifact.sync(JudgeInput(
            artifact_json=artifact_json, rubric=rubric,
            author_model=fixture.model, judge_model=judge_model))
        return qs.score, qs.components

    for _ in range(k):
        out_b = run_variant(role, b_text, fixture, agents_dir)
        score_b, comp_b = _score(out_b)
        if report.no_baseline:
            report.runs.append(RunScore(score_a=None, score_b=score_b,
                                        delta=None, components_b=comp_b))
            continue
        out_a = run_variant(role, a_text, fixture, agents_dir)
        score_a, comp_a = _score(out_a)
        delta = (None if score_a is None or score_b is None
                 else score_b - score_a)
        report.runs.append(RunScore(score_a=score_a, score_b=score_b,
                                    delta=delta, components_a=comp_a,
                                    components_b=comp_b))

    report.mean_a = _mean([r.score_a for r in report.runs])
    report.mean_b = _mean([r.score_b for r in report.runs])
    report.mean_delta = _mean([r.delta for r in report.runs])
    return report
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_eval_compare.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/eval/compare.py tests/test_eval_compare.py
git commit -m "feat(eval): compare A/B variants and score against the case rubric (E-4)

Reads the working-tree instructions.md and the committed version (git show
<ref>:...), loads the rubric from case.yaml's rubrics map, runs each variant
on the fixture, judges both with the existing judge_artifact, returns a pure
EvalReport (per-run scores + means + delta). Short-circuits on an unchanged
prompt; refuses a same-family judge (ADR-6); handles a missing baseline and a
missing rubric with clear EvalErrors.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: CLI wiring + capture command (`cli.py`) and the registry regression test

Wires `sdlc eval capture` and `sdlc eval <role>` into the operator CLI, renders the report, and pins that a `fixtures/` directory does not break the registry loader.

**Files:**
- Create: `src/sdlc/eval/cli.py`
- Modify: `src/sdlc/cli.py` (add the `eval` subparser + dispatch; extend `_local_only`)
- Test: `tests/test_eval_cli.py`, `tests/test_registry_ignores_fixtures.py`

**Interfaces:**
- Consumes: `compare`, `EvalReport`, `EvalError` (Task 3); `fixtures_from_events`, `write_fixtures`, `SUPPORTED_ROLES`, `DEPS_ROLES` (Task 1); `sdlc.agents.roles.REGISTRY`; a default judge model from `benchmarks/config.yaml`.
- Produces:
  - `render_report(report: EvalReport) -> str`.
  - `default_judge_model(config_path) -> str`.
  - `run_eval(role, *, against, case, k, judge_model, agents_dir, cases_root, repo_root) -> str` — resolves the case, calls `compare`, returns the rendered string; raises `EvalError`.
  - `add_eval_subparser(sub)` — registers `eval` on the top-level parser.

- [ ] **Step 1: Write the failing test**

Create `tests/test_eval_cli.py`:

```python
"""CLI-level behavior: rendering, role refusal, case resolution, defaults."""
import pytest

from sdlc.eval.cli import default_judge_model, render_report, run_eval
from sdlc.eval.compare import EvalError, EvalReport, RunScore


def test_render_shows_head_working_and_delta():
    rep = EvalReport(role="reviewer", case="c1", judge_model="openai/gpt-5.2",
                     against_ref="HEAD", mean_a=0.71, mean_b=0.83,
                     mean_delta=0.12, runs=[RunScore(score_a=0.71, score_b=0.83,
                                                     delta=0.12)])
    text = render_report(rep)
    assert "0.71" in text and "0.83" in text and "+0.12" in text


def test_render_unchanged():
    rep = EvalReport(role="reviewer", case="c1", judge_model="m",
                     against_ref="HEAD", unchanged=True)
    assert "no change" in render_report(rep).lower()


def test_render_no_baseline():
    rep = EvalReport(role="reviewer", case="c1", judge_model="m",
                     against_ref="HEAD", no_baseline=True, mean_b=0.8,
                     runs=[RunScore(score_a=None, score_b=0.8, delta=None)])
    assert "no committed baseline" in render_report(rep).lower()


def test_run_eval_refuses_deps_role(tmp_path):
    with pytest.raises(EvalError, match="deps"):
        run_eval("architect", against="HEAD", case="c1", k=1,
                 judge_model="openai/gpt-5.2", agents_dir=tmp_path,
                 cases_root=tmp_path, repo_root=tmp_path)


def test_default_judge_model_reads_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("default_judge_model: openai/gpt-5.2\n", encoding="utf-8")
    assert default_judge_model(cfg) == "openai/gpt-5.2"
```

Create `tests/test_registry_ignores_fixtures.py`:

```python
"""A fixtures/ directory beside instructions.md must not break the loader:
fixtures live inside the role folder, and the loader only reads agent.yaml /
instructions.md / agent.py."""
from sdlc.agents.loader import load_registry
from tests.conftest import write_registry_dir


def test_load_registry_ignores_a_fixtures_dir(tmp_path):
    root = write_registry_dir(tmp_path / "agents")
    fx = root / "reviewer" / "fixtures"
    fx.mkdir()
    (fx / "add-login.json").write_text('{"role": "reviewer"}', encoding="utf-8")
    roles = load_registry(root)          # must not raise
    assert "reviewer" in roles
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_eval_cli.py tests/test_registry_ignores_fixtures.py -v`
Expected: `test_eval_cli` FAILs with `ModuleNotFoundError: No module named 'sdlc.eval.cli'`. `test_registry_ignores_fixtures` should **pass already** (the loader iterates role dirs and reads named files); if it fails, the loader is walking into subdirs and that is a real bug to fix in `_parse_role` before continuing.

- [ ] **Step 3: Write `eval/cli.py`**

Create `src/sdlc/eval/cli.py`:

```python
"""CLI glue for `sdlc eval`: rendering, case resolution, capture wiring.

The eval (non-capture) path is synchronous and local-only. capture needs a
Temporal history source; the live adapter is a documented seam (below),
mirroring benchmarks/drift.py whose real provider is operator-runtime wiring.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .compare import EvalError, EvalReport, compare
from .fixtures import (DEPS_ROLES, SUPPORTED_ROLES, fixtures_from_events,
                       write_fixtures)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENTS_DIR = _REPO_ROOT / "agents"
_CASES_ROOT = _REPO_ROOT / "benchmarks" / "cases"
_BENCH_CONFIG = _REPO_ROOT / "benchmarks" / "config.yaml"


def default_judge_model(config_path: Path = _BENCH_CONFIG) -> str:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    model = data.get("default_judge_model")
    if not model:
        raise EvalError(f"no default_judge_model in {config_path}; "
                        f"pass --judge-model")
    return model


def _resolve_case(role: str, case: str | None, agents_dir: Path) -> str:
    if case:
        return case
    fx_dir = agents_dir / role / "fixtures"
    found = sorted(fx_dir.glob("*.json")) if fx_dir.is_dir() else []
    if len(found) == 1:
        return found[0].stem
    if not found:
        raise EvalError(f"no fixtures for role '{role}' under {fx_dir}; "
                        f"capture one first.")
    raise EvalError(f"role '{role}' has multiple fixtures "
                    f"({', '.join(p.stem for p in found)}); pass --case.")


def render_report(report: EvalReport) -> str:
    head = (f"eval {report.role}  (case {report.case}, "
            f"judge {report.judge_model}, against {report.against_ref})")
    if report.unchanged:
        return f"{head}\n  no change vs {report.against_ref}"
    lines = [head]
    if report.no_baseline:
        lines.append(f"  no committed baseline at {report.against_ref}; "
                     f"working-tree score only")
        lines.append(f"  working   {_fmt(report.mean_b)}")
        return "\n".join(lines)
    lines.append(f"  {report.against_ref:<8}  {_fmt(report.mean_a)}")
    lines.append(f"  working   {_fmt(report.mean_b)}")
    lines.append(f"  delta     {_fmt_delta(report.mean_delta)}")
    errs = sum(1 for r in report.runs if r.score_a is None or r.score_b is None)
    if errs:
        lines.append(f"  ({errs} judge error{'s' if errs > 1 else ''})")
    return "\n".join(lines)


def _fmt(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.2f}"


def _fmt_delta(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.2f}"


def run_eval(role: str, *, against: str, case: str | None, k: int,
             judge_model: str, agents_dir: Path = _AGENTS_DIR,
             cases_root: Path = _CASES_ROOT,
             repo_root: Path = _REPO_ROOT) -> str:
    if role in DEPS_ROLES:
        raise EvalError(
            f"role '{role}' carries deps; deps-aware eval is future work")
    resolved_case = _resolve_case(role, case, agents_dir)
    report = compare(role, resolved_case, against_ref=against, k=k,
                     agents_dir=agents_dir, cases_root=cases_root,
                     repo_root=repo_root, judge_model=judge_model)
    return render_report(report)


async def run_capture(client, run_id: str, case: str,
                      agents_dir: Path = _AGENTS_DIR) -> list[Path]:
    """Live capture: fetch a run's history, normalize to events, write fixtures.

    SEAM: `_history_to_events` converts a Temporal history into the normalized
    event dicts fixtures_from_events consumes. Like drift.py's real provider it
    needs a live run to validate; the pure core it feeds is fully tested. A
    fixture is trivial JSON, so hand-authoring is the offline fallback.
    """
    from ..agents.roles import REGISTRY
    history = await client.get_workflow_handle(run_id).fetch_history()
    events = _history_to_events(history)
    fixtures = fixtures_from_events(run_id, case, events, REGISTRY)
    return write_fixtures(fixtures, agents_dir)


def _history_to_events(history) -> list[dict]:
    """Temporal history -> normalized {activity, input:{messages}} dicts for
    ActivityTaskScheduled events of proposer model-request activities. Reads
    each scheduled event's activity_type name and decoded input payload."""
    events: list[dict] = []
    for ev in getattr(history, "events", history):
        attrs = getattr(ev, "activity_task_scheduled_event_attributes", None)
        if attrs is None:
            continue
        activity = attrs.activity_type.name
        try:
            inp = attrs.input.payloads[0].data
            import json
            messages_payload = json.loads(inp)
        except Exception:
            continue
        events.append({"activity": activity, "input": messages_payload})
    return events
```

- [ ] **Step 4: Run the CLI test to verify it passes**

Run: `python -m pytest tests/test_eval_cli.py tests/test_registry_ignores_fixtures.py -v`
Expected: all passed. (`run_capture`/`_history_to_events` are the untested live seam — the pure path they call is covered by Task 1.)

- [ ] **Step 5: Wire `eval` into the operator CLI**

In `src/sdlc/cli.py`, after the `benchmark` subparser block (around line 76), add the `eval` parser. The command is modeled as `eval <target>` where `target` is a role name or the literal `capture` — a single positional rather than nested subparsers, so an arbitrary role name and the fixed `capture` verb share one parser:

```python
    ev = sub.add_parser("eval")
    ev.add_argument("target", help="a role name, or 'capture'")
    ev.add_argument("--from", dest="from_run", help="run id (capture only)")
    ev.add_argument("--case", default=None)
    ev.add_argument("--against", default="HEAD")
    ev.add_argument("--n", type=int, default=1, dest="k")
    ev.add_argument("--judge-model", default=None, dest="judge_model")
```

Extend `_local_only` (line 80) so a non-capture eval needs no client:

```python
    _local_only = (args.cmd == "benchmark"
                   or (args.cmd == "schedules" and args.sched_cmd == "list")
                   or (args.cmd == "eval" and args.target != "capture"))
```

Add dispatch — place it immediately before the `handle = client.get_workflow_handle_for(...)` line (~138):

```python
    if args.cmd == "eval":
        from .eval.cli import default_judge_model, run_capture, run_eval
        from .eval.compare import EvalError
        if args.target == "capture":
            if not (args.from_run and args.case):
                print("eval capture requires --from <run_id> and --case <name>")
                return
            paths = await run_capture(client, args.from_run, args.case)
            print(f"captured {len(paths)} fixtures:")
            for p in paths:
                print(f"  {p}")
            return
        judge = args.judge_model or default_judge_model()
        try:
            print(run_eval(args.target, against=args.against, case=args.case,
                           k=args.k, judge_model=judge))
        except EvalError as e:
            print(f"eval error: {e}")
            raise SystemExit(1)
        return
```

Update the module docstring's usage block (lines 1-11) to add:

```
  python -m sdlc.cli eval capture --from feature-add-sso --case add-login-greenfield
  python -m sdlc.cli eval reviewer --against HEAD
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest`
Expected: all prior tests + the new eval tests pass, 0 failed. If `sdlc.cli` fails to import, check that the `eval` dispatch block sits inside `main()` and before the generic handle lookup.

- [ ] **Step 7: Smoke-test the eval path offline**

Confirm the modules import and a deps-role refusal works with no model or Temporal:
```bash
ANTHROPIC_API_KEY=dummy python -c "
import sdlc.cli
from sdlc.eval.cli import run_eval
from sdlc.eval.compare import EvalError
try:
    run_eval('architect', against='HEAD', case='c', k=1, judge_model='openai/gpt-5.2')
    raise SystemExit('should have refused architect')
except EvalError as e:
    assert 'deps' in str(e)
    print('cli imports OK; deps role refused')
"
```
Expected: `cli imports OK; deps role refused`.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/eval/cli.py src/sdlc/cli.py \
        tests/test_eval_cli.py tests/test_registry_ignores_fixtures.py
git commit -m "feat(eval): wire sdlc eval {capture,<role>} into the operator CLI (E-4)

`eval <role>` is synchronous and local-only (no Temporal); it resolves the
case, runs compare, and renders HEAD-vs-working with the delta. `eval capture`
fetches a run's history and writes fixtures -- its Temporal->events adapter is
a documented seam like drift.py's provider, feeding the fully-tested pure core.
A fixtures/ dir beside instructions.md is pinned not to break the loader.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Roadmap amendments

**Files:**
- Modify: `ROADMAP.md` §9.1 (E-4), §7 (prompts-as-assets)

- [ ] **Step 1: Mark E-4 done in §9.1**

In `ROADMAP.md` §9.1, replace the E-4 line:

```markdown
- [x] **E-4** Prompt eval loop over the `agents/` assets — `sdlc eval <role>` A/B-scores a
  working-tree `instructions.md` against a committed one on a captured fixture, judged by the
  existing cross-family `judge_artifact` + the case rubric; `sdlc eval capture` harvests fixtures
  from a run's history. Stage-isolated and on-demand (an exploration tool). Six pure proposers;
  architect/research refused (carry deps). Closes §7's "with an eval loop" clause. The
  regression-gate half (a committed baseline + a CI check) is a named future increment (OQ-E2).
  Spec: `docs/superpowers/specs/2026-07-18-prompt-eval-loop-design.md`.
```

- [ ] **Step 2: Close the §7 clause**

In `ROADMAP.md` §7, replace the prompts-as-assets item:

```markdown
- [x] `prompts/` as versioned assets **with an eval loop** — prompts live in
  `agents/<role>/instructions.md` and hash into `PROMPT_SHAS` from file content (E-2 ✅); a prompt
  edit is now measurable via `sdlc eval <role>` (E-4 ✅).
```

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): E-4 prompt eval loop landed; §7 clause closed

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Not in this plan

- **Live-Temporal capture validation.** `_history_to_events` is a seam that needs a real run to
  verify against actual history payloads, exactly as `drift.py`'s real provider does. The pure core
  it feeds is fully tested, and fixtures can be hand-authored (trivial JSON) as the offline fallback.
- **Rubrics for planner/qa/reviewer/analyst/merge_verdict.** Only `clarify` (key `clarifier`) has a
  shipped rubric today, so it is the one immediately-runnable supported role. Authoring the others'
  rubrics is per-case asset work (benchmark spec OQ-B1), not eval-engine work — the eval reports a
  clear error until a rubric exists.
- **Regression gate / committed baselines / CI check** (OQ-E2), **deps-aware eval for
  architect/research** (OQ-E1), **`k>1` variance surfacing** (OQ-E3), **full-pipeline prompt matrix.**
  All deferred, named in the spec.
```
