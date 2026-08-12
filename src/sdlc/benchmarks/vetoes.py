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
import re
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


Veto = Annotated[Union[MentionsAll, NotBoth, NonEmpty],
                 Field(discriminator="kind")]
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
        # Word-boundary match, NOT bare substring: otherwise "eating" matches
        # "creating", "red" matches "required"/"reduced", "playing" matches
        # "replaying". That false negative made the scope_dropped veto pass on
        # words that merely CONTAIN the term, not name it -- which made the
        # OQ-P5 result unreliable (E-83 review).
        missing = [t for t in v.terms
                   if not re.search(r"\b" + re.escape(t.lower()) + r"\b", hay)]
        if missing:
            return VetoFailure(
                veto_id=v.id,
                reason=f"required term(s) absent: {', '.join(missing)}")
        return None

    if isinstance(v, NotBoth):
        if artifact.get(v.field) != v.equals:
            return None
        populated = [f for f in v.and_any_nonempty
                     if not _is_empty(artifact.get(f))]
        if populated:
            return VetoFailure(
                veto_id=v.id,
                reason=f"{v.field} == {v.equals!r} contradicts non-empty "
                       f"{', '.join(populated)}")
        return None

    # NonEmpty. A missing field cannot be non-empty; treating absence as a
    # pass would make the veto vacuous.
    blank = [f for f in v.fields if _is_empty(artifact.get(f))]
    if blank:
        return VetoFailure(veto_id=v.id,
                           reason=f"field(s) empty or absent: "
                                  f"{', '.join(blank)}")
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
                f"Known fields: {', '.join(sorted(known))}")
