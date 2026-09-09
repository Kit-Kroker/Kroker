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

from ..stages.architecture.models import (
    ArchitectureDecision,
    ArchitectureSpec,
    ValidationContract,
)
from ..stages.clarify.models import ClarifiedRequirements, OpenQuestion
from ..stages.context.models import BrownfieldDelta
from ..stages.plan.models import DevTask, ImplementationPlan
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


RENDERERS: dict[str, tuple[type[BaseModel], Callable[[Any], list[str]]]] = {
    "requirements": (ClarifiedRequirements, _requirements_body),
    "architecture": (ArchitectureSpec, _architecture_body),
    "plan": (ImplementationPlan, _plan_body),
}


def render_version_markdown(key: str, raw: bytes, *, project: str, version: ArtifactVersion) -> str:
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
