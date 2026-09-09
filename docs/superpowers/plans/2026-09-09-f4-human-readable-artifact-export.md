# F4 — Human-Readable Artifact Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve each of the board's three typed artifacts as a generated Markdown document over the existing board API, so a non-engineer at a gate reads intent and spec instead of raw JSON.

**Architecture:** One new pure module, `src/sdlc/board/render.py`, holds a `key -> (model, body renderer)` registry and turns stored artifact bytes into a Markdown document with a provenance banner. It parses with `model_validate_json`, raises four typed errors, and knows nothing of HTTP or the filesystem. `src/sdlc/board/api.py` gains two routes that read the blob exactly as the existing JSON route does, map those typed errors onto status codes, and serve `text/markdown` with an `ETag` and handler-side `304`. A fifth change threads `project` into `NotifyInput` so gate notifications can carry a link — but only for gates whose artifact is already on the board (see the ordering audit below).

**Tech Stack:** Python 3.11+, Pydantic v2 (`>=2.13.5`), FastAPI (`>=0.141.1`), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-09-f4-human-readable-artifact-export-design.md` (committed at `71f7ee1`)

## Global Constraints

- **ASCII only in renderer literals.** Every string the renderer itself emits — headings, labels, separators, bullets — must be ASCII: use `-`, `--`, `->`, never typographic dashes or arrows. Reason: a Windows console's cp1252 codepage mangles non-ASCII when this text is printed (`benchmarks/report.py:80-82`, `channels/transport.py:12`). **Artifact content passes through verbatim and is NOT transliterated** — an LLM-authored requirement containing a curly quote must not be corrupted. The ASCII test therefore uses ASCII fixtures and asserts the scaffolding, never the data.
- **The renderer is framework-free and I/O-free.** It imports no `fastapi`, no `BoardStore`, no `pathlib`. It takes bytes plus metadata and returns a string. `tests/test_operator_layering.py` enforces the analogous rule one layer over; follow the same discipline here.
- **The renderer never runs inside a Temporal workflow or activity** (spec §6.1). Do not import `board/render.py` from anything under `src/sdlc/workflows/`, and do not register it as an activity.
- **Parse with `Model.model_validate_json(raw_bytes)`, never `json.loads` then `model_validate`.** The one-step form raises `ValidationError` for malformed JSON *and* invalid UTF-8 *and* schema mismatch; the two-step form leaks `json.JSONDecodeError` and `UnicodeDecodeError` past the handler into a 500. This is spec §5 case 3 and is load-bearing.
- **Size is checked before parse** (spec §5). A blob can be both oversize and unparseable; size wins because it is cheaper and more specific, and because the renderer must never parse an unbounded blob.
- **No silent field drops.** Every field of every artifact model must be either rendered or listed in `_OMITTED`. The omission set is exactly five `(model, field)` entries and must not grow without a recorded reason.
- **No template engine.** Build `lines: list[str]` and `"\n".join(...)`, matching `benchmarks/report.py:64`. Do not add `jinja2` or any dependency.
- **Do not change any of the three artifact models**, any stage's `step.py`, or any `<stage>.md` contract. No stage behaviour changes in this plan, so no clause updates are owed.
- **Do not add a CLI subcommand, a Vue/dashboard UI, or on-disk `.md` writing** (spec §8).
- **1000-line file ceiling** (`scripts/check_file_size.py`). `render.py` should land near 200 lines; if it approaches the ceiling, something has gone wrong.
- Run `pytest` (fast tier), `ruff check .`, `ruff format .`, and `mypy` before each commit.
- **No attribution trailers in any commit** — no `Co-Authored-By:`, no `Claude-Session:`. Commit via `git commit -F <msgfile>`, one path per `git add` argument, no heredocs.

---

## Audit: gate-notification ordering (done — do not re-derive)

The user ruled OQ-1 "yes, link the render from the gate notification". **That ruling is only partially implementable, and this section is why.** It was verified against `src/` before this plan was written; do not re-investigate.

**The artifact does not exist when its own gate notification is sent.**

| Step | Where | What happens |
|---|---|---|
| 1 | `workflows/gates.py:169` `_gate()` | creates the pending decision, sets `_pending[key]` |
| 2 | `workflows/gates.py:125` `_notify()` | **notification is sent here**, fire-and-forget |
| 3 | `workflows/gates.py:165` | `await workflow.wait_condition(decided)` — unbounded wait for the human |
| 4 | `stages/architecture/step.py:188` | `revisable_stage` returns `(arch, gate)` |
| 5 | `workflows/feature.py:585` | `_board_publish(cfg, "architecture", ...)` — **artifact reaches the board only now** |

So a link to `/projects/{p}/artifacts/architecture/current/markdown` in an architecture-gate notification **404s at the moment the human clicks it**. The same holds for `clarify` -> `requirements` (`feature.py:560`) and `plan` -> `plan` (`feature.py:602`).

The inversion is exact: the gates whose artifact *is* already published are `merge`, `deploy`, and `task:<id>` — gates that are not approving those artifacts. The three gates where the render would help most are precisely the three that cannot link it.

**Publishing as `PROPOSED` before the gate does not fix it, twice over.**

1. `board/store.py:206-211`: for any non-`CURRENT` status the store runs `INSERT INTO artifact(...) VALUES (?,?,?,?) ON CONFLICT(project,key) DO NOTHING` with `current_version=None`. A `PROPOSED` publish therefore leaves `current_version` unset, so `current/markdown` still 404s — or, if a *previous run's* `CURRENT` row already exists, the `DO NOTHING` leaves it in place and the link silently serves the wrong run's artifact. Linking would require the *versioned* route, hence the `version_id` at notify time, hence publishing before `_gate()` and threading its return value through to the notification — plus a promotion path to move `CURRENT` after approval, **for which no store method exists**; `publish_artifact_version` only ever appends. That is three new mechanisms, not one flag. (`_board_publish` does not even expose `status` — `board_host.py:49-50` takes `approved: bool` and maps it internally, so the plumbing would start there.)
2. Temporal replay. `grep -rn "workflow.patched\|workflow.get_version" src/ --include=*.py` returns **zero hits**: this repo uses no Temporal versioning API anywhere. Inserting a new activity execution before the gate would be its first non-patchable workflow change, and `gates.py:165` is an *unbounded* wait — a run parked at a gate across a deploy would replay an old history through a code path that now emits a command the history never recorded. That is textbook nondeterminism, and the mitigations (versioned task queue, drain in-flight runs) are heavier than the feature.

**What this plan does instead.** A gate links the artifacts already published when it opens — never its own. That mapping falls straight out of the publish order at `feature.py:560/585/602`:

| Gate | Links | Why |
|---|---|---|
| `clarify` | nothing | nothing is published yet |
| `architecture` | `requirements` | published at `feature.py:560`, before this gate |
| `plan` | `requirements`, `architecture` | both published before this gate |
| `merge`, `deploy`, `task:<id>` | all three | every publish has happened |

This keeps most of the ruling's value with zero pipeline change and zero dead URLs: the reviewer approving an architecture gets the requirements it is meant to satisfy, and the merge reviewer gets the whole chain. It complements what is already there rather than duplicating it — `GateContext(spec_summary=...)` (`workflows/role_host.py:230`) already carries the *under-review* artifact's summary inline, so the notification already says what is proposed; the links supply the background it should be judged against.

It is replay-safe: adding an optional-with-default field to `NotifyInput` deserializes cleanly from old histories, and the link string is built activity-side, outside workflow history.

**Known limitation, accepted: a cross-run stale link.** `current/markdown` resolves `BoardArtifact.current_version`, which is per `(project, key)` — not per run. Two concurrent runs on the same `project_key` share it, so run A's architecture-gate link can resolve to run B's requirements. This is why the banner carries `run_id` (Task 1): the mismatch is *visible* to the reader even though it is not prevented. Preventing it needs a version-pinned link, which needs the `version_id` at notify time, which is the same publish-reordering problem. Do not attempt it here.

**What it does not do**, and what needs a separate decision: linking a stage gate to its own not-yet-published artifact. That requires the publish reordering above and belongs in its own spec. **This is a GATE 2 question — see the report accompanying this plan.**

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `src/sdlc/board/render.py` (create) | typed artifact -> Markdown; registry, banner, three body renderers, four typed errors | 1-3 |
| `tests/test_board_render.py` (create) | unit tests over the pure functions, including the no-silent-field-drop enforcement | 1-3 |
| `src/sdlc/board/api.py` (modify) | two Markdown routes; error -> status mapping; ETag/304 | 4 |
| `tests/test_board_api_markdown.py` (create) | route tests | 4 |
| `README.md` (modify, `:73-78`) | document the two routes and the unauthenticated posture | 5 |
| `src/sdlc/notify/contract.py` (modify) | `NotifyInput.project` optional field | 6 |
| `src/sdlc/notify/render.py` (modify) | artifact links for post-publish gates | 6 |
| `policy/notifications.yaml` (modify) | correct the stale `base_url` comment | 6 |
| `tests/test_notify_render.py` (modify) | link rendering tests | 6 |

---

## Task 1: Renderer scaffold, banner, dispatch, and the requirements body

**Files:**
- Create: `src/sdlc/board/render.py`
- Create: `tests/test_board_render.py`

**Interfaces:**
- Consumes: `ArtifactVersion` (`src/sdlc/board/models.py:37`), `ClarifiedRequirements` and `OpenQuestion` (`src/sdlc/stages/clarify/models.py:30`, `:17`).
- Produces: `RENDER_VERSION: int`, `MAX_RENDER_BYTES: int`, `RENDERERS: dict[str, tuple[type[BaseModel], Callable]]`, `_OMITTED: dict[str, set[str]]`, exceptions `RenderError` / `UnknownArtifactKey` / `ArtifactTooLarge` / `ArtifactUnreadable`, and `render_version_markdown(key, raw, *, project, version) -> str`. Tasks 2, 3, 4 and 6 all depend on these names.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_board_render.py`:

```python
"""Board artifact -> Markdown renderer (F4)."""

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from sdlc.board.models import ArtifactVersion
from sdlc.board.render import (
    MAX_RENDER_BYTES,
    RENDER_VERSION,
    ArtifactTooLarge,
    ArtifactUnreadable,
    UnknownArtifactKey,
    render_version_markdown,
)
from sdlc.core.models import ClarificationDimension
from sdlc.stages.clarify.models import ClarifiedRequirements, OpenQuestion


def version(n: int = 3, vid: int = 41) -> ArtifactVersion:
    return ArtifactVersion(
        id=vid,
        project="acme",
        key="requirements",
        n=n,
        run_id="run-xyz",
        sha256="9f2c" + "0" * 60,
        uri="file:///tmp/x.json",
        created_at=datetime(2026, 9, 9, 8, 14, 2, tzinfo=timezone.utc),
    )


def full_requirements() -> ClarifiedRequirements:
    return ClarifiedRequirements(
        summary="SENTINEL_SUMMARY",
        functional_requirements=["SENTINEL_FR"],
        non_functional_requirements=["SENTINEL_NFR"],
        out_of_scope=["SENTINEL_OOS"],
        dimensions_probed=[ClarificationDimension.FUNCTIONAL_INTENT],
        open_questions=[
            OpenQuestion(
                id="SENTINEL_QID",
                question="SENTINEL_QUESTION",
                why_it_matters="SENTINEL_WHY",
                suggested_answer="SENTINEL_SUGGESTED",
                answer="SENTINEL_ANSWER",
                dimension=ClarificationDimension.BUSINESS_SEMANTICS,
                asked_by="SENTINEL_ASKEDBY",
                materiality=0.75,
                evidence="SENTINEL_EVIDENCE",
            )
        ],
        dropped=[
            OpenQuestion(
                id="SENTINEL_DROPPED_ID",
                question="SENTINEL_DROPPED_Q",
                why_it_matters="SENTINEL_DROPPED_WHY",
            )
        ],
    )


def render_requirements(model: ClarifiedRequirements) -> str:
    return render_version_markdown(
        "requirements", model.model_dump_json().encode("utf-8"),
        project="acme", version=version(),
    )


def test_banner_carries_provenance():
    out = render_requirements(full_requirements())
    assert out.startswith("# Requirements -- acme")
    assert "| artifact | requirements |" in out
    assert "| version | 3 (id 41) |" in out
    assert "| run | run-xyz |" in out
    assert "2026-09-09T08:14:02" in out
    assert "9f2c" in out


def test_requirements_body_renders_every_section():
    out = render_requirements(full_requirements())
    for sentinel in (
        "SENTINEL_SUMMARY", "SENTINEL_FR", "SENTINEL_NFR", "SENTINEL_OOS",
        "SENTINEL_QUESTION", "SENTINEL_WHY", "SENTINEL_SUGGESTED",
        "SENTINEL_ANSWER", "SENTINEL_ASKEDBY", "SENTINEL_EVIDENCE",
    ):
        assert sentinel in out, sentinel


def test_dropped_questions_render_under_their_own_heading():
    out = render_requirements(full_requirements())
    assert "SENTINEL_DROPPED_Q" in out
    head = out.index("Dropped")
    assert out.index("SENTINEL_DROPPED_Q") > head


def test_answered_and_unanswered_questions_are_distinguishable():
    # Anchored on the "-- " separator deliberately: "ANSWERED" is a
    # substring of "UNANSWERED", so a bare check would pass even if every
    # question rendered as unanswered.
    out = render_requirements(full_requirements())
    assert "-- ANSWERED" in out
    assert "-- UNANSWERED" in out


def test_renderer_scaffolding_is_ascii():
    # ASCII fixtures in, ASCII out: this pins the renderer's own literals.
    out = render_requirements(full_requirements())
    assert out.isascii()


def test_artifact_content_is_not_transliterated():
    model = full_requirements()
    model.summary = "café naïve"
    out = render_requirements(model)
    assert "café naïve" in out


def test_empty_collections_do_not_produce_dangling_headings():
    model = ClarifiedRequirements(
        summary="s", functional_requirements=[], non_functional_requirements=[],
        out_of_scope=[], open_questions=[],
    )
    out = render_requirements(model)
    assert "(none)" in out
    assert "\n\n\n\n" not in out


def test_unknown_key_is_refused():
    with pytest.raises(UnknownArtifactKey) as e:
        render_version_markdown("nope", b"{}", project="acme", version=version())
    assert "requirements" in str(e.value)


def test_oversize_blob_is_refused_before_parsing():
    with pytest.raises(ArtifactTooLarge):
        render_version_markdown(
            "requirements", b"x" * (MAX_RENDER_BYTES + 1),
            project="acme", version=version(),
        )


@pytest.mark.parametrize("raw", [b"not json at all", b'{"summary": "a", "trunc', b"\xff\xfe{}"])
def test_unparseable_bytes_raise_one_error_type(raw):
    # model_validate_json collapses malformed JSON and bad UTF-8 into
    # ValidationError; nothing else may escape.
    with pytest.raises(ArtifactUnreadable):
        render_version_markdown("requirements", raw, project="acme", version=version())


def test_schema_drift_raises_the_same_error():
    with pytest.raises(ArtifactUnreadable) as e:
        render_version_markdown(
            "requirements", b'{"summary": "only this"}',
            project="acme", version=version(),
        )
    assert "ClarifiedRequirements" in str(e.value)


def test_render_version_is_an_int():
    assert isinstance(RENDER_VERSION, int)


def test_render_cap_matches_the_json_route_cap():
    # Pinned deliberately: board/api.py defines its own MAX_CONTENT_BYTES and
    # render.py cannot import it without a cycle.
    from sdlc.board import api as api_mod

    assert MAX_RENDER_BYTES == api_mod.MAX_CONTENT_BYTES
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_board_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.board.render'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/board/render.py`:

```python
# src/sdlc/board/render.py
"""Typed board artifacts -> Markdown, for a human standing at a gate (F4).

A read-path projection, exactly as benchmarks/report.py is. Imported by
board/api.py and by nothing under workflows/: putting it in a workflow or
activity would drag three stage model modules through the Temporal sandbox
passthrough list for no benefit (spec section 6.1).

ARTIFACT BOUNDARY. The renderers below are a projection OF the three stage
artifact models. Whoever adds a field to ClarifiedRequirements,
ArchitectureSpec, ImplementationPlan, or any model nested inside them must
render it here or add it to _OMITTED in the same diff --
tests/test_board_render.py::test_no_field_is_silently_dropped fails until
one or the other happens.

ASCII only in the strings THIS module emits (benchmarks/report.py:80-82,
channels/transport.py:12): a Windows console's cp1252 codepage mangles
non-ASCII when the text is printed. Artifact content passes through
verbatim and is never transliterated -- corrupting an author's text would
be worse than an unprintable character.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from ..stages.clarify.models import ClarifiedRequirements, OpenQuestion
from .models import ArtifactVersion

# Bumped when a renderer changes its output. Part of the ETag: neither
# sha256 nor version_id moves when this module is edited, so without it a
# cache would keep serving the previous render.
RENDER_VERSION = 1

# Deliberately equal to board/api.py's MAX_CONTENT_BYTES. It is duplicated
# rather than imported because api.py imports this module, and
# test_board_render.py pins the two together.
MAX_RENDER_BYTES = 512 * 1024

_TITLES = {
    "requirements": "Requirements",
    "architecture": "Architecture",
    "plan": "Implementation plan",
}

# The complete set of fields deliberately not rendered, keyed by model name.
# See spec section 4.3. Growing this set is a decision, not a convenience.
_OMITTED: dict[str, set[str]] = {
    "ClarifiedRequirements": {"spec_ref"},
    "ArchitectureSpec": {"spec_ref"},
    "ImplementationPlan": {"plan_ref"},
    "ValidationContract": {"task_id", "frozen"},
}


class RenderError(Exception):
    """Base for every reason an artifact cannot be rendered."""


class UnknownArtifactKey(RenderError):
    """No renderer is registered for this artifact key."""


class ArtifactTooLarge(RenderError):
    """The stored blob exceeds MAX_RENDER_BYTES."""


class ArtifactUnreadable(RenderError):
    """The stored bytes do not yield a valid model."""


def _pct(v: float | None) -> str:
    return "not recorded" if v is None else f"{v * 100:.0f}%"


def _bullets(items: Sequence[str]) -> list[str]:
    return [f"- {i}" for i in items] if items else ["- (none)"]


def _inline(items: Sequence[str]) -> str:
    return ", ".join(items) if items else "(none)"


def _section(title: str, lines: Iterable[str]) -> list[str]:
    return [f"## {title}", "", *lines, ""]


def _banner(project: str, key: str, v: ArtifactVersion) -> list[str]:
    return [
        f"# {_TITLES[key]} -- {project}",
        "",
        "| | |",
        "|---|---|",
        f"| artifact | {key} |",
        f"| version | {v.n} (id {v.id}) |",
        f"| run | {v.run_id} |",
        f"| published | {v.created_at.isoformat()} |",
        f"| sha256 | {v.sha256} |",
        "",
    ]


def _question_block(q: OpenQuestion) -> list[str]:
    state = "ANSWERED" if q.answer else "UNANSWERED"
    materiality = "n/a" if q.materiality is None else f"{q.materiality:.2f}"
    return [
        f"### {q.id} -- {state}",
        "",
        q.question,
        "",
        f"- why it matters: {q.why_it_matters}",
        f"- suggested answer: {q.suggested_answer or '(none)'}",
        f"- answer: {q.answer or '(none yet)'}",
        f"- dimension: {q.dimension.value if q.dimension else 'n/a'}"
        f"; asked by: {q.asked_by or 'n/a'}"
        f"; materiality: {materiality}"
        f"; evidence: {q.evidence or 'n/a'}",
        "",
    ]


def _questions(items: Sequence[OpenQuestion]) -> list[str]:
    out: list[str] = []
    for q in items:
        out += _question_block(q)
    return out or ["- (none)"]


def _requirements_body(r: ClarifiedRequirements) -> list[str]:
    probed = _inline([d.value for d in r.dimensions_probed])
    return [
        *_section("Summary", [r.summary]),
        *_section("Functional requirements", _bullets(r.functional_requirements)),
        *_section("Non-functional requirements", _bullets(r.non_functional_requirements)),
        *_section("Out of scope", _bullets(r.out_of_scope)),
        *_section("Clarification coverage", [f"- dimensions probed: {probed}"]),
        *_section("Open questions", _questions(r.open_questions)),
        # `dropped` is what makes the cap honest (clarify/models.py:37-39):
        # always rendered, including when empty, so "the cap cut nothing" and
        # "we never looked" stay distinguishable.
        *_section("Dropped -- questions the cap cut", _questions(r.dropped)),
    ]


RENDERERS: dict[str, tuple[type[BaseModel], Callable[[Any], list[str]]]] = {
    "requirements": (ClarifiedRequirements, _requirements_body),
}


def render_version_markdown(
    key: str, raw: bytes, *, project: str, version: ArtifactVersion
) -> str:
    """One artifact version as a Markdown document.

    Pure: takes bytes and metadata, returns a string. Every failure is a
    RenderError subclass -- board/api.py maps them onto status codes.
    """
    entry = RENDERERS.get(key)
    if entry is None:
        raise UnknownArtifactKey(
            f"no Markdown renderer for artifact key {key!r}; "
            f"renderable keys are {', '.join(sorted(RENDERERS))}"
        )
    # Size before parse (spec section 5): a blob can be both oversize and
    # unparseable, and the renderer must never parse an unbounded blob.
    if len(raw) > MAX_RENDER_BYTES:
        raise ArtifactTooLarge(
            f"artifact {key!r} version {version.id} is {len(raw)} bytes, "
            f"over the {MAX_RENDER_BYTES}-byte render cap"
        )
    model_cls, body = entry
    try:
        # One-step parse: collapses malformed JSON, invalid UTF-8, and schema
        # mismatch into ValidationError. json.loads + model_validate would
        # leak JSONDecodeError/UnicodeDecodeError past this handler.
        obj = model_cls.model_validate_json(raw)
    except ValidationError as e:
        raise ArtifactUnreadable(
            f"artifact {key!r} version {version.id} does not parse as "
            f"{model_cls.__name__}: {e.error_count()} error(s); "
            f"first: {e.errors()[0]['loc']} {e.errors()[0]['msg']}"
        ) from e
    return "\n".join([*_banner(project, key, version), *body(obj)]).rstrip() + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_board_render.py -v`
Expected: PASS (all tests in this task's file)

- [ ] **Step 5: Run the checks**

Run: `ruff check . && ruff format . && mypy && python scripts/check_file_size.py`
Expected: clean

- [ ] **Step 6: Commit**

Write the message to a file, then:

```bash
git add src/sdlc/board/render.py
git add tests/test_board_render.py
git commit -F <msgfile>
```

Message subject: `feat(board): render requirements artifacts as Markdown`

---

## Task 2: The architecture body

**Files:**
- Modify: `src/sdlc/board/render.py`
- Modify: `tests/test_board_render.py`

**Interfaces:**
- Consumes: everything Task 1 produced; `ArchitectureSpec`, `ArchitectureDecision` (`stages/architecture/models.py:18`, `:11`), `BrownfieldDelta` (`stages/context/models.py:8`).
- Produces: `RENDERERS["architecture"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_board_render.py`:

```python
from sdlc.stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from sdlc.stages.context.models import BrownfieldDelta


def full_architecture() -> ArchitectureSpec:
    return ArchitectureSpec(
        overview="SENTINEL_OVERVIEW",
        confidence=0.82,
        decisions=[
            ArchitectureDecision(
                id="SENTINEL_DID",
                decision="SENTINEL_DECISION",
                rationale="SENTINEL_RATIONALE",
                alternatives_considered=["SENTINEL_ALT"],
            )
        ],
        new_components=["SENTINEL_NEWCOMP"],
        risks=["SENTINEL_RISK"],
        delta=BrownfieldDelta(
            added=["SENTINEL_ADDED"],
            modified=["SENTINEL_MODIFIED"],
            removed=["SENTINEL_REMOVED"],
        ),
    )


def render_architecture(model: ArchitectureSpec) -> str:
    v = version()
    v.key = "architecture"
    return render_version_markdown(
        "architecture", model.model_dump_json().encode("utf-8"),
        project="acme", version=v,
    )


def test_architecture_body_renders_every_section():
    out = render_architecture(full_architecture())
    for sentinel in (
        "SENTINEL_OVERVIEW", "SENTINEL_DID", "SENTINEL_DECISION",
        "SENTINEL_RATIONALE", "SENTINEL_ALT", "SENTINEL_NEWCOMP",
        "SENTINEL_RISK", "SENTINEL_ADDED", "SENTINEL_MODIFIED",
        "SENTINEL_REMOVED",
    ):
        assert sentinel in out, sentinel


def test_architecture_confidence_renders_as_a_percentage():
    assert "82%" in render_architecture(full_architecture())


def test_architecture_delta_separates_added_modified_removed():
    out = render_architecture(full_architecture())
    assert out.index("SENTINEL_ADDED") < out.index("SENTINEL_MODIFIED")
    assert out.index("SENTINEL_MODIFIED") < out.index("SENTINEL_REMOVED")


def test_architecture_without_delta_says_so():
    model = ArchitectureSpec(overview="o", decisions=[])
    out = render_architecture(model)
    assert "greenfield" in out
    assert "not recorded" in out  # confidence is None
```

Note for the implementer: `affected_modules` is deliberately absent from the fixture. `ArchitectureSpec`'s own validator (`stages/architecture/models.py:28-42`) derives it from `delta` whenever a delta is present, so setting it directly would be overwritten. The coverage test in Task 4 asserts it renders; the derived value (`SENTINEL_MODIFIED`, `SENTINEL_REMOVED`) is what appears.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_board_render.py -k architecture -v`
Expected: FAIL — `UnknownArtifactKey: no Markdown renderer for artifact key 'architecture'`

- [ ] **Step 3: Write the implementation**

Add the imports to `src/sdlc/board/render.py`:

```python
from ..stages.architecture.models import ArchitectureDecision, ArchitectureSpec
from ..stages.context.models import BrownfieldDelta
```

Add above `RENDERERS`:

```python
def _decision_block(d: ArchitectureDecision) -> list[str]:
    return [
        f"### {d.id} -- {d.decision}",
        "",
        f"- rationale: {d.rationale}",
        f"- alternatives considered: {_inline(d.alternatives_considered)}",
        "",
    ]


def _delta_block(delta: BrownfieldDelta | None) -> list[str]:
    if delta is None:
        return ["- (greenfield; no brownfield delta recorded)"]
    # Three lists, not one: added and modified have opposite grounding
    # rules (context/models.py:11-13) and a flat list loses that.
    return [
        "added:",
        *_bullets(delta.added),
        "",
        "modified:",
        *_bullets(delta.modified),
        "",
        "removed:",
        *_bullets(delta.removed),
    ]


def _architecture_body(a: ArchitectureSpec) -> list[str]:
    decisions: list[str] = []
    for d in a.decisions:
        decisions += _decision_block(d)
    return [
        *_section("Overview", [a.overview]),
        *_section("Confidence", [f"- confidence: {_pct(a.confidence)}"]),
        *_section("Decisions", decisions or ["- (none)"]),
        *_section("Risks", _bullets(a.risks)),
        *_section("Affected modules", _bullets(a.affected_modules)),
        *_section("New components", _bullets(a.new_components)),
        *_section("Brownfield delta", _delta_block(a.delta)),
    ]
```

Register it:

```python
RENDERERS: dict[str, tuple[type[BaseModel], Callable[[Any], list[str]]]] = {
    "requirements": (ClarifiedRequirements, _requirements_body),
    "architecture": (ArchitectureSpec, _architecture_body),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_board_render.py -v`
Expected: PASS

- [ ] **Step 5: Run the checks**

Run: `ruff check . && ruff format . && mypy && python scripts/check_file_size.py`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/render.py
git add tests/test_board_render.py
git commit -F <msgfile>
```

Message subject: `feat(board): render architecture artifacts as Markdown`

---

## Task 3: The plan body

**Files:**
- Modify: `src/sdlc/board/render.py`
- Modify: `tests/test_board_render.py`

**Interfaces:**
- Consumes: everything Tasks 1-2 produced; `ImplementationPlan`, `DevTask` (`stages/plan/models.py:67`, `:13`), `ValidationContract` (`stages/architecture/models.py:45`).
- Produces: `RENDERERS["plan"]` — completing the registry to all three keys.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_board_render.py`:

```python
from sdlc.stages.architecture.models import ValidationContract
from sdlc.stages.plan.models import DevTask, ImplementationPlan


def full_plan() -> ImplementationPlan:
    return ImplementationPlan(
        confidence=0.5,
        tasks=[
            DevTask(
                id="SENTINEL_TID",
                title="SENTINEL_TITLE",
                description="SENTINEL_DESC",
                depends_on=["SENTINEL_DEP"],
                acceptance_criteria=["SENTINEL_AC"],
                files_hint=["SENTINEL_HINT"],
                overlaps=["SENTINEL_OVERLAP"],
                role="devops",
                contract=ValidationContract(
                    task_id="SENTINEL_TID",
                    assertions=["SENTINEL_ASSERTION"],
                    test_commands=["SENTINEL_TESTCMD"],
                    lint_commands=["SENTINEL_LINTCMD"],
                    stack="SENTINEL_STACK",
                ),
            )
        ],
    )


def render_plan(model: ImplementationPlan) -> str:
    v = version()
    v.key = "plan"
    return render_version_markdown(
        "plan", model.model_dump_json().encode("utf-8"), project="acme", version=v
    )


def test_plan_body_renders_every_section():
    out = render_plan(full_plan())
    for sentinel in (
        "SENTINEL_TID", "SENTINEL_TITLE", "SENTINEL_DESC", "SENTINEL_DEP",
        "SENTINEL_AC", "SENTINEL_HINT", "SENTINEL_OVERLAP",
        "SENTINEL_ASSERTION", "SENTINEL_TESTCMD", "SENTINEL_LINTCMD",
        "SENTINEL_STACK",
    ):
        assert sentinel in out, sentinel


def test_plan_role_renders_under_a_label():
    # role has a closed vocabulary, so a bare substring check would pass
    # even if the field were dropped. The label is the anchor.
    assert "role: devops" in render_plan(full_plan())


def test_plan_reports_its_task_count():
    assert "1 task(s)" in render_plan(full_plan())


def test_plan_without_tasks_renders_cleanly():
    out = render_plan(ImplementationPlan(tasks=[]))
    assert "0 task(s)" in out
    assert "(none)" in out


def test_task_without_a_contract_says_so():
    plan = full_plan()
    plan.tasks[0].contract = None
    assert "validation contract: (none)" in render_plan(plan)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_board_render.py -k plan -v`
Expected: FAIL — `UnknownArtifactKey: no Markdown renderer for artifact key 'plan'`

- [ ] **Step 3: Write the implementation**

Add the imports to `src/sdlc/board/render.py`:

```python
from ..stages.architecture.models import ArchitectureDecision, ArchitectureSpec, ValidationContract
from ..stages.plan.models import DevTask, ImplementationPlan
```

Add above `RENDERERS`:

```python
def _contract_block(c: ValidationContract | None) -> list[str]:
    if c is None:
        return ["- validation contract: (none)"]
    return [
        "- validation contract:",
        f"  - stack: {c.stack or '(unspecified)'}",
        *[f"  - assertion: {a}" for a in c.assertions],
        *[f"  - test command: {t}" for t in c.test_commands],
        *[f"  - lint command: {t}" for t in c.lint_commands],
    ]


def _task_block(t: DevTask) -> list[str]:
    return [
        f"### {t.id} -- {t.title}",
        "",
        # `role` has a closed vocabulary ("dev"/"test"/"devops"), so it is
        # rendered under an explicit label: the coverage test anchors on
        # "role: <value>" because a bare "dev" collides with other output.
        f"- role: {t.role}",
        "",
        t.description,
        "",
        f"- depends on: {_inline(t.depends_on)}",
        f"- files hint: {_inline(t.files_hint)}",
        f"- overlaps: {_inline(t.overlaps)}",
        "- acceptance criteria:",
        *[f"  - {c}" for c in t.acceptance_criteria],
        *_contract_block(t.contract),
        "",
    ]


def _plan_body(p: ImplementationPlan) -> list[str]:
    tasks: list[str] = []
    for t in p.tasks:
        tasks += _task_block(t)
    return [
        *_section("Confidence", [f"- confidence: {_pct(p.confidence)}"]),
        *_section("Overview", [f"- {len(p.tasks)} task(s)"]),
        *_section("Tasks", tasks or ["- (none)"]),
    ]
```

Register it:

```python
RENDERERS: dict[str, tuple[type[BaseModel], Callable[[Any], list[str]]]] = {
    "requirements": (ClarifiedRequirements, _requirements_body),
    "architecture": (ArchitectureSpec, _architecture_body),
    "plan": (ImplementationPlan, _plan_body),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_board_render.py -v`
Expected: PASS

- [ ] **Step 5: Run the checks**

Run: `ruff check . && ruff format . && mypy && python scripts/check_file_size.py`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/render.py
git add tests/test_board_render.py
git commit -F <msgfile>
```

Message subject: `feat(board): render plan artifacts as Markdown`

---

## Task 4: The no-silent-field-drop test

**Files:**
- Modify: `tests/test_board_render.py`

**Interfaces:**
- Consumes: `RENDERERS`, `_OMITTED`, and the three `full_*()` fixtures from Tasks 1-3.
- Produces: nothing importable. The deliverable is the enforcement itself.

This is the task that makes "render *from* the typed artifact" a fact rather than an intention. It is a separate task because it can only be written once all three renderers exist, and because a reviewer could reasonably approve Tasks 1-3 and reject this one's design.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_board_render.py`:

```python
from typing import get_args

from sdlc.board.render import _OMITTED, RENDERERS

# Every (model, field) that IS rendered, mapped to a string that must appear
# in the rendered output of the fully-populated fixture. Adding a field to
# any artifact model fails test_no_field_is_silently_dropped until it is
# either listed here or added to _OMITTED.
#
# Free-text fields use their sentinel. Closed-vocabulary fields (role,
# dimension) must use a LABELLED anchor: "dev" and "test" occur incidentally
# in other output, so a bare value would pass even if the field were dropped.
_EXPECTED: dict[tuple[str, str], str] = {
    ("ClarifiedRequirements", "summary"): "SENTINEL_SUMMARY",
    ("ClarifiedRequirements", "functional_requirements"): "SENTINEL_FR",
    ("ClarifiedRequirements", "non_functional_requirements"): "SENTINEL_NFR",
    ("ClarifiedRequirements", "out_of_scope"): "SENTINEL_OOS",
    ("ClarifiedRequirements", "open_questions"): "SENTINEL_QUESTION",
    ("ClarifiedRequirements", "dimensions_probed"): "dimensions probed: C1",
    ("ClarifiedRequirements", "dropped"): "SENTINEL_DROPPED_Q",
    ("OpenQuestion", "id"): "SENTINEL_QID",
    ("OpenQuestion", "question"): "SENTINEL_QUESTION",
    ("OpenQuestion", "why_it_matters"): "SENTINEL_WHY",
    ("OpenQuestion", "suggested_answer"): "SENTINEL_SUGGESTED",
    ("OpenQuestion", "answer"): "SENTINEL_ANSWER",
    ("OpenQuestion", "dimension"): "dimension: C2",
    ("OpenQuestion", "asked_by"): "SENTINEL_ASKEDBY",
    ("OpenQuestion", "materiality"): "materiality: 0.75",
    ("OpenQuestion", "evidence"): "SENTINEL_EVIDENCE",
    ("ArchitectureSpec", "overview"): "SENTINEL_OVERVIEW",
    ("ArchitectureSpec", "decisions"): "SENTINEL_DECISION",
    # affected_modules is DERIVED from delta by ArchitectureSpec's validator
    # (architecture/models.py:28-42), so its sentinels also appear in the
    # delta section. Anchor on the heading or dropping either field would
    # still pass -- the same collision trap as `role` and `dimension`.
    ("ArchitectureSpec", "affected_modules"): "## Affected modules\n\n- SENTINEL_MODIFIED",
    ("ArchitectureSpec", "new_components"): "SENTINEL_NEWCOMP",
    ("ArchitectureSpec", "risks"): "SENTINEL_RISK",
    ("ArchitectureSpec", "confidence"): "82%",
    ("ArchitectureSpec", "delta"): "## Brownfield delta\n\nadded:",
    ("ArchitectureDecision", "id"): "SENTINEL_DID",
    ("ArchitectureDecision", "decision"): "SENTINEL_DECISION",
    ("ArchitectureDecision", "rationale"): "SENTINEL_RATIONALE",
    ("ArchitectureDecision", "alternatives_considered"): "SENTINEL_ALT",
    ("BrownfieldDelta", "added"): "added:\n- SENTINEL_ADDED",
    ("BrownfieldDelta", "modified"): "modified:\n- SENTINEL_MODIFIED",
    ("BrownfieldDelta", "removed"): "removed:\n- SENTINEL_REMOVED",
    ("ImplementationPlan", "tasks"): "SENTINEL_TID",
    ("ImplementationPlan", "confidence"): "50%",
    ("DevTask", "id"): "SENTINEL_TID",
    ("DevTask", "title"): "SENTINEL_TITLE",
    ("DevTask", "description"): "SENTINEL_DESC",
    ("DevTask", "depends_on"): "SENTINEL_DEP",
    ("DevTask", "acceptance_criteria"): "SENTINEL_AC",
    ("DevTask", "files_hint"): "SENTINEL_HINT",
    ("DevTask", "overlaps"): "SENTINEL_OVERLAP",
    ("DevTask", "contract"): "SENTINEL_ASSERTION",
    ("DevTask", "role"): "role: devops",
    ("ValidationContract", "assertions"): "SENTINEL_ASSERTION",
    ("ValidationContract", "test_commands"): "SENTINEL_TESTCMD",
    ("ValidationContract", "lint_commands"): "SENTINEL_LINTCMD",
    ("ValidationContract", "stack"): "SENTINEL_STACK",
}


def _model_types(anno) -> set[type[BaseModel]]:
    """Every BaseModel reachable through an annotation (list[X], X | None)."""
    found: set[type[BaseModel]] = set()
    if isinstance(anno, type) and issubclass(anno, BaseModel):
        found.add(anno)
    for arg in get_args(anno):
        found |= _model_types(arg)
    return found


def _walk(cls: type[BaseModel], seen: set[type[BaseModel]] | None = None):
    """cls plus every artifact model reachable through a RENDERED field.

    Omitted fields' subtrees are deliberately NOT walked. An omitted field's
    type is not part of the rendered surface, so its own fields cannot be
    "silently dropped" -- the whole field is dropped, on purpose, and that
    decision is already recorded in _OMITTED.

    Without this skip the walk reaches ArtifactRef through spec_ref and
    plan_ref, and then demands that ArtifactRef.kind/.uri/.sha256 be either
    rendered or omitted. Both ways out are wrong: rendering them contradicts
    section 4.3, and adding an "ArtifactRef" entry to _OMITTED breaks the
    pinned count of five. Skipping is the only correct answer, and it makes
    the walk return exactly the eight artifact models the spec names.
    """
    seen = seen if seen is not None else set()
    if cls in seen:
        return seen
    seen.add(cls)
    omitted = _OMITTED.get(cls.__name__, set())
    for name, f in cls.model_fields.items():
        if name in omitted:
            continue
        for nested in _model_types(f.annotation):
            _walk(nested, seen)
    return seen


def all_artifact_models() -> set[type[BaseModel]]:
    models: set[type[BaseModel]] = set()
    for model_cls, _ in RENDERERS.values():
        models |= _walk(model_cls)
    return models


def test_no_field_is_silently_dropped():
    """Every field of every artifact model is rendered or explicitly omitted.

    Recursion is what gives this teeth: DevTask's nine fields and
    OpenQuestion's nine are only reachable through nesting, and two of the
    three omissions sit two levels down in ValidationContract.
    """
    undeclared = []
    for model_cls in all_artifact_models():
        name = model_cls.__name__
        omitted = _OMITTED.get(name, set())
        for field in model_cls.model_fields:
            if field in omitted:
                continue
            if (name, field) not in _EXPECTED:
                undeclared.append(f"{name}.{field}")
    assert not undeclared, (
        "these artifact model fields are neither rendered nor in _OMITTED: "
        + ", ".join(sorted(undeclared))
        + " -- render them in board/render.py or record the omission"
    )


def test_every_declared_field_actually_reaches_the_output():
    rendered = "\n".join(
        [
            render_requirements(full_requirements()),
            render_architecture(full_architecture()),
            render_plan(full_plan()),
        ]
    )
    missing = [f"{m}.{f}" for (m, f), probe in _EXPECTED.items() if probe not in rendered]
    assert not missing, f"declared as rendered but absent from output: {missing}"


def test_omission_set_names_only_real_fields():
    by_name = {m.__name__: m for m in all_artifact_models()}
    for model_name, fields in _OMITTED.items():
        assert model_name in by_name, f"_OMITTED names unknown model {model_name}"
        for field in fields:
            assert field in by_name[model_name].model_fields, (
                f"_OMITTED names unknown field {model_name}.{field}"
            )


def test_the_omission_set_is_exactly_the_five_documented_entries():
    # Spec section 4.3. Growing this is a decision that belongs in the spec,
    # so it is pinned here rather than left to drift.
    assert sum(len(v) for v in _OMITTED.values()) == 5


def test_the_walk_reaches_exactly_the_eight_artifact_models():
    # Spec section 4.3 says eight. If ArtifactRef appears here, _walk has
    # stopped skipping omitted fields' subtrees and is walking into
    # claim-check plumbing.
    assert {m.__name__ for m in all_artifact_models()} == {
        "ClarifiedRequirements",
        "OpenQuestion",
        "ArchitectureSpec",
        "ArchitectureDecision",
        "BrownfieldDelta",
        "ImplementationPlan",
        "DevTask",
        "ValidationContract",
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_board_render.py -k dropped_or_omitted -v` then the whole file.
Expected: FAIL — `_OMITTED` and `RENDERERS` are importable, so the failure will be a real assertion (an undeclared field, or a declared probe absent from output), not an import error. Fix whichever it reports.

- [ ] **Step 3: Reconcile**

There is no new production code in this task. If `test_no_field_is_silently_dropped` reports an undeclared field, a Task 1-3 renderer missed it — go add it to the relevant `_*_body` and to `_EXPECTED`. If `test_every_declared_field_actually_reaches_the_output` reports a missing probe, the probe string does not match what the renderer emits — correct the probe, not the renderer, unless the renderer is genuinely wrong.

- [ ] **Step 4: Run the full file to verify it passes**

Run: `pytest tests/test_board_render.py -v`
Expected: PASS

- [ ] **Step 5: Run the checks**

Run: `ruff check . && ruff format . && mypy && python scripts/check_file_size.py`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add tests/test_board_render.py
git commit -F <msgfile>
```

Message subject: `test(board): fail when an artifact field is silently unrendered`

---

## Task 5: The two Markdown routes

**Files:**
- Modify: `src/sdlc/board/api.py`
- Create: `tests/test_board_api_markdown.py`

**Interfaces:**
- Consumes: `render_version_markdown`, `RENDER_VERSION`, and the four exceptions from Task 1; `BoardStore.get_artifact` / `get_version` (`board/store.py:224`, `:244`).
- Produces: two HTTP routes. Task 6 references their URL shape but does not import them.

**Already prototyped against `fastapi.testclient` — this shape works.** Both routes resolve; the existing `/versions/{version_id}` JSON route is unaffected by them (no ordering conflict, because `/markdown` is a literal segment — this is OQ-2's whole point); a matching `If-None-Match` returns `304` with an empty body; a stale one returns `200`; and the Markdown error path returns `text/markdown` starting with `# ` and containing no `detail` key. You are implementing a verified design, not exploring one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_board_api_markdown.py`:

```python
"""Board Markdown routes (F4): status mapping, headers, caching."""

import pytest
from fastapi.testclient import TestClient

from sdlc.artifacts.store import LocalFileStore, ref_to_path
from sdlc.board import api as api_mod
from sdlc.board.api import create_app
from sdlc.board.models import ArtifactStatus
from sdlc.board.store import BoardStore
from sdlc.stages.clarify.models import ClarifiedRequirements

MD = "text/markdown"


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "b.sqlite3"
    blobs = LocalFileStore(root=tmp_path / "runs")
    seed = BoardStore(db=db, blobs=blobs)
    seed.ensure_project("proj", repo="git@example:acme/x")

    good = ClarifiedRequirements(
        summary="a readable summary",
        functional_requirements=["it works"],
        non_functional_requirements=[],
        out_of_scope=[],
        open_questions=[],
    )
    # ORDER MATTERS. Publishing CURRENT moves the pointer, so the junk
    # version of `requirements` is seeded FIRST and the good one second --
    # that leaves v2 (good) current, while junk_v stays reachable by version
    # id for the 422 test. Seed them the other way round and
    # test_current_markdown_serves_a_document breaks.
    #
    # b"xxxx" is not JSON at all: it reaches the same ValidationError handler
    # as schema drift by a different failure class, which is why the spec
    # lists both.
    _, junk_v = seed.publish_artifact_version(
        "proj", "requirements", "run-1", b"xxxx", actor="workflow:run-1"
    )
    _, req_v = seed.publish_artifact_version(
        "proj", "requirements", "run-1",
        good.model_dump_json().encode("utf-8"), actor="workflow:run-1",
    )
    # Deliberately invalid: ArchitectureSpec requires `decisions`. Mirrors
    # the seed in tests/test_board_api_reads.py:21.
    _, arch_v = seed.publish_artifact_version(
        "proj", "architecture", "run-1", b'{"overview":"first"}', actor="workflow:run-1"
    )
    _, big_v = seed.publish_artifact_version(
        "proj", "plan", "run-1",
        b"x" * (api_mod.MAX_CONTENT_BYTES + 10), actor="workflow:run-1",
    )
    # A rejected gate writes history without moving the pointer
    # (workflows/board_host.py:52-53), leaving current_version NULL. This is
    # the only way to reach the "has versions but none current" branch.
    seed.publish_artifact_version(
        "proj", "rejected_key", "run-1", b"{}",
        status=ArtifactStatus.REJECTED, actor="workflow:run-1",
    )
    seed.close()

    app = create_app(lambda: BoardStore(db=db, blobs=blobs))
    c = TestClient(app)
    c.req_v, c.arch_v, c.big_v, c.junk_v = req_v, arch_v, big_v, junk_v
    c.blobs = blobs
    c.db = db
    return c


def md_url(key: str, version_id: int | None = None) -> str:
    base = f"/projects/proj/artifacts/{key}"
    return f"{base}/versions/{version_id}/markdown" if version_id else f"{base}/current/markdown"


def test_current_markdown_serves_a_document(client):
    r = client.get(md_url("requirements"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(MD)
    assert r.text.startswith("# Requirements -- proj")
    assert "a readable summary" in r.text


def test_versioned_markdown_serves_the_same_document(client):
    r = client.get(md_url("requirements", client.req_v))
    assert r.status_code == 200
    assert "a readable summary" in r.text


def test_content_disposition_names_the_file(client):
    r = client.get(md_url("requirements"))
    assert 'filename="proj-requirements-v1.md"' in r.headers["content-disposition"]


def test_unknown_key_is_404(client):
    r = client.get(md_url("nonsense"))
    assert r.status_code == 404


def test_key_with_versions_but_no_current_is_404_and_says_why(client):
    r = client.get("/projects/proj/artifacts/rejected_key/current/markdown")
    assert r.status_code == 404
    assert "no current version" in r.text.lower()
    assert "rejected" in r.text.lower()


def test_unknown_project_is_404(client):
    r = client.get("/projects/ghost/artifacts/requirements/current/markdown")
    assert r.status_code == 404


def test_schema_drift_is_422_and_names_the_escape_hatch(client):
    r = client.get(md_url("architecture", client.arch_v))
    assert r.status_code == 422
    assert "ArchitectureSpec" in r.text
    assert "/versions/" in r.text  # points at the raw-JSON route


@pytest.mark.parametrize(
    "url",
    [
        "/projects/proj/artifacts/nonsense/current/markdown",
        "/projects/ghost/artifacts/requirements/current/markdown",
    ],
)
def test_errors_are_markdown_not_json(client, url):
    # The whole point of these routes is that a non-engineer never meets raw
    # JSON. A failed link must not hand them {"detail": ...}.
    r = client.get(url)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith(MD)
    assert r.text.startswith("# ")
    assert "detail" not in r.text


def test_unparseable_bytes_are_422_at_the_route(client):
    # Distinct from schema drift: these bytes are not JSON at all. The spec
    # lists both because the one-step model_validate_json parse is what
    # collapses them into the same handler -- it deserves a route-level pin,
    # not only a unit test.
    r = client.get(md_url("requirements", client.junk_v))
    assert r.status_code == 422
    assert r.headers["content-type"].startswith(MD)


def test_oversize_blob_is_413(client):
    r = client.get(md_url("plan", client.big_v))
    assert r.status_code == 413


def test_pruned_blob_is_410(client):
    st = BoardStore(db=client.db, blobs=client.blobs)
    v = st.get_version("proj", client.req_v)
    st.close()
    ref_to_path(v).unlink()
    r = client.get(md_url("requirements", client.req_v))
    assert r.status_code == 410


def test_version_belonging_to_another_key_is_404(client):
    r = client.get(md_url("requirements", client.arch_v))
    assert r.status_code == 404


def test_etag_and_cache_control_are_set(client):
    r = client.get(md_url("requirements"))
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["etag"].startswith('W/"')


def test_matching_if_none_match_returns_304_with_no_body(client):
    first = client.get(md_url("requirements"))
    again = client.get(md_url("requirements"), headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.text == ""


def test_non_matching_if_none_match_returns_the_document(client):
    r = client.get(md_url("requirements"), headers={"If-None-Match": 'W/"stale"'})
    assert r.status_code == 200
    assert "a readable summary" in r.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_board_api_markdown.py -v`
Expected: FAIL — every route test returns 404 because the routes do not exist.

- [ ] **Step 3: Write the implementation**

In `src/sdlc/board/api.py`, add to the imports:

```python
from fastapi import Response
from fastapi.responses import PlainTextResponse

from .render import (
    RENDER_VERSION,
    ArtifactTooLarge,
    ArtifactUnreadable,
    UnknownArtifactKey,
    render_version_markdown,
)
```

Inside `create_app`, after the existing `get_version` route, add:

```python
    def _md_error(status: int, title: str, detail: str) -> PlainTextResponse:
        """An error a human can read.

        These routes exist so a non-engineer never meets raw JSON; handing
        them `{"detail": ...}` when a link fails would reintroduce exactly
        that. So the Markdown routes answer failures in Markdown, with the
        status code carrying the machine-readable half. The JSON routes are
        unchanged and keep their HTTPException bodies.
        """
        return PlainTextResponse(
            f"# {title}\n\n{detail}\n",
            status_code=status,
            media_type="text/markdown; charset=utf-8",
        )

    def _markdown_response(
        request: Request, store: BoardStore, project: str, key: str, version_id: int
    ) -> Response:
        """Shared body for both Markdown routes.

        Reuses get_version's guards verbatim; the only additions are the
        render, the RenderError -> status mapping, and revalidation.
        """
        try:
            _require_project(store, project)
        except HTTPException as e:
            return _md_error(404, "No such project", str(e.detail))
        try:
            v = store.get_version(project, version_id)
        except NotFoundError as e:
            return _md_error(404, "No such artifact version", str(e))
        if v.key != key:
            return _md_error(
                404,
                "Version belongs to another artifact",
                f"Version {version_id} belongs to `{v.key}`, not `{key}`.",
            )

        # The tag is a function of the version row alone, so revalidation
        # costs no blob read and no render.
        etag = f'W/"{RENDER_VERSION}-{v.id}-{v.sha256[:16]}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})

        json_route = f"/projects/{project}/artifacts/{key}/versions/{v.id}"

        path = ref_to_path(ArtifactRef(kind=v.key, uri=v.uri, sha256=v.sha256))
        if not path.exists():
            # Same reasoning as get_version: metadata outlives the blob, so
            # the row and its hash are still authoritative history.
            return _md_error(
                410,
                "This artifact's content has been pruned",
                f"The record survives but the stored document does not.\n\n"
                f"- sha256: `{v.sha256}`\n- uri: `{v.uri}`",
            )
        try:
            body = render_version_markdown(key, path.read_bytes(), project=project, version=v)
        except UnknownArtifactKey as e:
            return _md_error(404, "Nothing to render", str(e))
        except ArtifactTooLarge as e:
            return _md_error(
                413,
                "This artifact is too large to render",
                f"{e}\n\nRead it as JSON at `{json_route}`.",
            )
        except ArtifactUnreadable as e:
            return _md_error(
                422,
                "This artifact cannot be rendered",
                f"{e}\n\nThis means the stored document no longer matches the "
                f"schema it is rendered against -- a bug worth reporting, not "
                f"something you did.\n\nThe stored JSON is still readable at "
                f"`{json_route}`.",
            )
        return PlainTextResponse(
            body,
            media_type="text/markdown; charset=utf-8",
            headers={
                "ETag": etag,
                "Cache-Control": "no-cache",
                "Content-Disposition": f'inline; filename="{project}-{key}-v{v.n}.md"',
            },
        )

    @app.get("/projects/{project}/artifacts/{key}/current/markdown")
    def get_current_markdown(
        project: str, key: str, request: Request, store: BoardStore = Depends(get_store)
    ):
        try:
            _require_project(store, project)
        except HTTPException as e:
            return _md_error(404, "No such project", str(e.detail))
        try:
            art = store.get_artifact(project, key)
        except NotFoundError as e:
            return _md_error(404, "No such artifact", str(e))
        if art.current_version is None:
            # Reachable: a rejected gate writes history without moving the
            # pointer (workflows/board_host.py:52-53), so a rejected
            # architecture has versions but no current one.
            return _md_error(
                404,
                "No current version",
                f"`{key}` in `{project}` has published versions but none is "
                f"current -- this happens when a gate rejected it.\n\n"
                f"List its history at "
                f"`/projects/{project}/artifacts/{key}`, then open a specific "
                f"version at `.../versions/<id>/markdown`.",
            )
        return _markdown_response(request, store, project, key, art.current_version)

    @app.get("/projects/{project}/artifacts/{key}/versions/{version_id}/markdown")
    def get_version_markdown(
        project: str,
        key: str,
        version_id: int,
        request: Request,
        store: BoardStore = Depends(get_store),
    ):
        return _markdown_response(request, store, project, key, version_id)
```

Add `Request` to the existing `from fastapi import ...` line.

Note for the implementer: an unknown *key* on the versioned route surfaces as `NotFoundError` from `get_version` or the key-mismatch check before the renderer is reached, so `UnknownArtifactKey` mostly fires for a key that exists on the board but has no renderer. Both map to 404; keep the explicit `except` so a future unrenderable key cannot reach a 500.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_board_api_markdown.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite and the checks**

Run: `pytest && ruff check . && ruff format . && mypy && python scripts/check_file_size.py`
Expected: clean. `tests/test_board_api_reads.py` must still pass untouched — the existing JSON routes are unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/board/api.py
git add tests/test_board_api_markdown.py
git commit -F <msgfile>
```

Message subject: `feat(board): serve artifact renders over two Markdown routes`

---

## Task 6: Link the render from gate notifications where it resolves

**Files:**
- Modify: `src/sdlc/notify/contract.py`
- Modify: `src/sdlc/notify/render.py`
- Modify: `src/sdlc/workflows/gates.py:125-140`
- Modify: `src/sdlc/workflows/AGENTS.md` (the `_cfg` row's Readers column)
- Modify: `policy/notifications.yaml:15-17`
- Modify: `tests/test_notify_render.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-5 at the code level — it emits URLs matching Task 5's route shape but imports nothing from `board/`. Keep it that way: `notify/` must not import `board/`.
- Produces: `NotifyInput.project: str | None`, and `ARTIFACT_GATES` / `POST_PUBLISH_GATES` in `notify/render.py`.

**Read the ordering audit above before starting.** This task deliberately does NOT link a stage gate to its own artifact, because that artifact is not published yet. It links the already-published artifacts from the gates that come after them.

**The mapping below is prototyped and verified**: `architecture` emits only the requirements link; `plan` emits requirements + architecture and never its own; `merge`, `deploy` and `task:<id>` emit all three; `clarify`, an unknown gate, a missing `base_url`, and a missing `project` each emit nothing at all.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_notify_render.py`:

```python
def links_for(gate: str, *, base_url="http://localhost:8500/", project="acme",
              reason=NotifyReason.OPENED) -> str:
    return render_notification(
        pending=gate_pending_for(gate),
        reason=reason,
        run_id="run-1",
        opened_at=OPENED,
        now=NOW,
        deadline=None,
        base_url=base_url,
        project=project,
    )


def test_merge_gate_links_all_three_artifact_renders():
    text = links_for("merge")
    for key in ("requirements", "architecture", "plan"):
        assert f"/projects/acme/artifacts/{key}/current/markdown" in text


def test_architecture_gate_links_requirements_but_not_its_own_artifact():
    # requirements is published at feature.py:560, before this gate opens;
    # architecture is published only after it is decided (feature.py:585),
    # so linking it here would 404.
    text = links_for("architecture")
    assert "/artifacts/requirements/current/markdown" in text
    assert "/artifacts/architecture/current/markdown" not in text
    assert "/artifacts/plan/current/markdown" not in text


def test_plan_gate_links_the_two_earlier_artifacts_only():
    text = links_for("plan")
    assert "/artifacts/requirements/current/markdown" in text
    assert "/artifacts/architecture/current/markdown" in text
    assert "/artifacts/plan/current/markdown" not in text


def test_clarify_gate_links_nothing_because_nothing_is_published():
    assert "/markdown" not in links_for("clarify")


def test_task_escalation_gate_links_all_three():
    text = links_for("task:T01")
    for key in ("requirements", "architecture", "plan"):
        assert f"/artifacts/{key}/current/markdown" in text


def test_no_base_url_omits_the_links_without_erroring():
    text = links_for("merge", base_url=None)
    assert "/markdown" not in text
    assert "sdlc approve" in text  # the rest of the notification is intact


def test_no_project_omits_the_links_without_erroring():
    text = links_for("merge", project=None)
    assert "/markdown" not in text
    assert "sdlc approve" in text


def test_expired_notifications_carry_no_links():
    # EXPIRE already suppresses the command block; links follow it.
    assert "/markdown" not in links_for("merge", reason=NotifyReason.EXPIRE)
```

Reuse whatever `gate_pending_for` / `OPENED` / `NOW` helpers `tests/test_notify_render.py` already defines; read that file first and match its existing fixtures rather than inventing new ones.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_notify_render.py -v`
Expected: FAIL — `TypeError: render_notification() got an unexpected keyword argument 'project'`

- [ ] **Step 3: Write the implementation**

In `src/sdlc/notify/contract.py`, add to `NotifyInput`:

```python
    # F4: the board project whose artifact renders a notification may link.
    # Optional with a default so old workflow histories deserialize
    # unchanged -- this field is added to a payload that Temporal replays.
    project: str | None = None
```

In `src/sdlc/notify/render.py`, add above `render_notification`:

```python
# F4. Which artifact renders a gate's notification may link.
#
# A gate links what is ALREADY on the board when it opens, and never its own
# key: `_board_publish` runs only after a gate is decided
# (workflows/feature.py:560/585/602), so a gate's own artifact does not exist
# at notification time and a link to it would 404. The order below is the
# publish order.
_ALL_ARTIFACTS = ("requirements", "architecture", "plan")
_GATE_LINKS: dict[str, tuple[str, ...]] = {
    "clarify": (),  # nothing published yet
    "architecture": ("requirements",),
    "plan": ("requirements", "architecture"),
    "merge": _ALL_ARTIFACTS,
    "deploy": _ALL_ARTIFACTS,
    # Opened by the deploy stage after a failed smoke check
    # (stages/deploy/step.py:212). Every publish has happened by then, and
    # this is precisely a gate where a human needs the plan in front of them.
    "deploy_failed": _ALL_ARTIFACTS,
}


def _artifact_links(gate: str, base_url: str | None, project: str | None) -> list[str]:
    """Deep links to the readable renders. Empty whenever anything needed is
    missing -- an unset base_url or project omits the links and never fails
    the notification."""
    if not base_url or not project:
        return []
    # A per-task escalation gate is `task:<id>`; by then every publish has
    # happened, so it gets the full set.
    keys = _ALL_ARTIFACTS if gate.startswith("task:") else _GATE_LINKS.get(gate, ())
    if not keys:
        return []
    root = base_url.rstrip("/")
    return [
        "",
        "  background:",
        *[
            f"    {root}/projects/{project}/artifacts/{key}/current/markdown"
            for key in keys
        ],
    ]
```

Change `render_notification`'s signature to accept `project: str | None = None` (keyword, defaulted, so no existing caller breaks), then extend the existing link block at `notify/render.py:69-70`.

**Placement matters.** The new line goes at the same indentation as the existing `if base_url:` — that is, *inside* the `if reason is not NotifyReason.EXPIRE:` guard. An expired gate cannot be acted on, so it gets neither commands nor links, and `test_expired_notifications_carry_no_links` pins that:

```python
    lines.append("")
    if reason is not NotifyReason.EXPIRE:
        if gate:
            lines += [
                f"  sdlc approve {run_id} --gate {gate}",
                f"  sdlc reject {run_id} --gate {gate}",
            ]
        else:
            lines.append(f"  sdlc answer {run_id} --question {pending.key}")
        if base_url:
            lines.append(f"  {base_url.rstrip('/')}/runs/{run_id}")
        lines += _artifact_links(gate or "", base_url, project)   # <-- added

    return "\n".join(lines)
```

In `src/sdlc/notify/activities.py`, pass it through:

```python
        project=inp.project,
```

In `src/sdlc/workflows/gates.py`, inside `_notify` (at `:125`), read the project key defensively and pass it:

```python
        # GateHost is also the base of CrewTaskWorkflow, TriageWorkflow,
        # TidyUpWorkflow and AssessmentWorkflow (crew.py:112, triage.py:150,
        # tidyup.py:183, assessment.py:334), none of which has _cfg. getattr
        # is the documented pattern for exactly this -- see the `_status` row
        # in workflows/AGENTS.md, which reads via getattr for the same
        # reason. A host without a config simply sends no link.
        cfg = getattr(self, "_cfg", None)
        project = getattr(cfg, "project_key", None) if cfg else None
```

then add to the `NotifyInput(...)` construction at `:134`:

```python
                    project=project,
```

**Do not add a `_project_key` attribute.** `FeatureWorkflow._cfg` already holds the config (`feature.py:207`, assigned at `:413`, before any gate opens) and a new attribute would need its own ownership row for no gain.

**You must update `src/sdlc/workflows/AGENTS.md` in the same diff.** Its rule 3 is explicit: "Cross-host readers are permitted through the MRO (`self.<attr>`), but must be recorded here to prevent accidental coupling." Add `GateHost._notify` to the **Readers** column of the `_cfg` row. Leave Owning Host and Writers untouched — this is a read, not a write.

**Replay safety.** Adding a field to an activity's *input payload* is safe: old histories deserialize it with its default. Emitting a new *command* is not. So do not add an activity call, do not remove one, and do not change the order of any existing workflow command in this task.

In `policy/notifications.yaml`, correct the stale comment at `:15-16`:

```yaml
# Absolute base for deep links -- the origin serving both the dashboard and
# the board API (interfaces/dashboard/api/main.py composes them into one
# process). Null disables every link; notifications are still delivered.
base_url: null
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_notify_render.py tests/test_board_api_markdown.py -v`
Expected: PASS

- [ ] **Step 5: Run the full suite and the checks**

Run: `pytest && ruff check . && ruff format . && mypy && python scripts/check_file_size.py`
Expected: clean. Pay attention to `tests/test_board_wiring.py` and any gates test — the `NotifyInput` change touches a Temporal payload.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/notify/contract.py
git add src/sdlc/notify/render.py
git add src/sdlc/notify/activities.py
git add src/sdlc/workflows/gates.py
git add src/sdlc/workflows/AGENTS.md
git add policy/notifications.yaml
git add tests/test_notify_render.py
git commit -F <msgfile>
```

Message subject: `feat(notify): link artifact renders from post-publish gates`

---

## Task 7: Document the routes

**Files:**
- Modify: `README.md:73-78`

**Interfaces:**
- Consumes: the route shapes from Task 5.
- Produces: nothing importable.

- [ ] **Step 1: Read the current text**

Run: `sed -n 66,80p README.md`

- [ ] **Step 2: Extend the route list**

In the paragraph beginning ``GET /projects/{p}`` for artifacts + task rollup`, add the Markdown routes and extend the existing warning:

```markdown
`GET /projects/{p}` for artifacts + task rollup, `/artifacts/{key}` for version
lineage, `/tasks?status=`, `/events` for the change log, `/stats` for board
counters. Agents claim work with `POST /projects/{p}/tasks/{id}/claim` and an
`If-Match: <row_version>` header.

For humans rather than agents, `/artifacts/{key}/current/markdown` and
`/artifacts/{key}/versions/{id}/markdown` render `requirements`,
`architecture` and `plan` as Markdown generated from the stored typed
artifact — the same data the JSON routes serve, readable without a
dashboard. An artifact that no longer matches its model returns 422 rather
than a partial render; the JSON route stays available as the escape hatch.

**Bind to localhost** — there is no auth yet, and the `X-Actor` header
identifying a writer is self-asserted (ROADMAP OQ-11). The Markdown URLs are
designed to be pasted into a chat or a ticket, which makes this easier to
forget: pasting one shares a link that only works inside the trusted
network, and anyone who reaches that network can read it.
```

- [ ] **Step 3: Verify the file still passes the checks**

Run: `python scripts/check_file_size.py && ruff format --check .`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -F <msgfile>
```

Message subject: `docs(readme): document the board Markdown routes`

---

## Verification checklist (run before declaring the plan complete)

- [ ] `pytest` — fast tier green
- [ ] `pytest -m temporal` — the `NotifyInput` change in Task 6 touches a replayed payload
- [ ] `ruff check .` and `ruff format --check .`
- [ ] `mypy`
- [ ] `python scripts/check_file_size.py`
- [ ] `src/sdlc/board/render.py` imports no `fastapi`, no `BoardStore`, no `pathlib`
- [ ] Nothing under `src/sdlc/workflows/` imports `board.render`
- [ ] `src/sdlc/notify/` imports nothing from `src/sdlc/board/`
- [ ] `git log --format='%B' <range> | grep -iE 'co-authored-by|claude-session'` returns nothing
