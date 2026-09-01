# src/sdlc/assessment/verification.py
"""RD6 (E-49): one fail-closed grounding invariant, at two row types.

Pure by design -- Pydantic, grounding.py and scan/models.py only. This module
must never import discover/ or risk/: it is the floor both stand on, and an
import upward would make it one of them.

Lifted out of discover/verify.py rather than copied. Two fail-closed
grounding invariants that must never disagree is the shape
triage/admission.py already refactored away into "one function at two
strictnesses", after workflows/tidyup.py documented the trap two copies
create.

A violation drops the ROW, never the phase. guard_reason() is the phase-level
term; what a tripped guard COSTS is the caller's to decide, and the two
callers deliberately decide differently (E-48 DD8 fails the phase; E-49 RD7
degrades the judgment layer).

The blobs are read by the CALLING activity and passed in; this module
decides.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from ..grounding import Profile, verify_quote
from .scan.models import EvidenceRef

# The one threshold. Two numbers agreeing by coincidence is what RD6 exists
# to remove; E-47b's DEAD_GUARD_MAX_UNRESOLVED is set to the same value for
# the same reason, and is a different guard over a different population.
CITATION_GUARD_MAX_UNRESOLVED: float = 0.10


class VerifiableRow(Protocol):
    """Evidence and an optional quote.

    The id is a CALLABLE passed to verify_rows rather than an attribute on
    this protocol: discover names it `candidate_id` and risk names it
    `row_id`, and renaming either would change a landed contract for the
    verifier's convenience.
    """

    evidence: tuple[EvidenceRef, ...]
    quote: str


R = TypeVar("R", bound=VerifiableRow)


class Fabricating(Protocol):
    """What guard_reason needs. A protocol rather than a concrete type so the
    typed wrappers (RefVerification, RiskVerification) can each keep their own
    Pydantic shape for the Temporal boundary."""

    total_references: int
    unresolved_references: int

    @property
    def fabrication_rate(self) -> float: ...


@dataclass(frozen=True)
class RowVerification(Generic[R]):
    """What survived, what was refused, and the guard's two terms.

    Deliberately NOT a Pydantic model: it never crosses the Temporal
    boundary. The activity repackages it into its own typed result, which is
    also where the survivors are re-split by row family.

    `refusals` is row_id -> (rule, detail) rather than a rewritten row: the
    caller owns the row shape, and building one here would be a second
    producer of the same row (E-48 P3-D1).
    """

    survivors: tuple[R, ...]
    refusals: dict[str, tuple[str, str]]
    total_references: int
    unresolved_references: int

    @property
    def fabrication_rate(self) -> float:
        """Zero references is a zero rate, never a division. A proposer that
        cited nothing fabricated nothing -- it is unevidenced, which is a
        different complaint and not this guard's."""
        if self.total_references == 0:
            return 0.0
        return self.unresolved_references / self.total_references


def _line_span(text: str) -> int:
    """Lines in the file. A file with no trailing newline still has its last
    line, and "" is one empty line -- both match how a reader counts."""
    return len(text.splitlines()) or 1


def _range_refusal(ref: EvidenceRef, body: str) -> str:
    """ "" when the range lies inside the file. `lines` is "" for a whole-file
    reference, "42" for one line, "42-78" for a span."""
    if not ref.lines:
        return ""
    raw = ref.lines.split("-")
    try:
        start = int(raw[0])
        end = int(raw[-1])
    except ValueError:
        return "dropped_ref_line_range"
    if start < 1 or end < start or end > _line_span(body):
        return "dropped_ref_line_range"
    return ""


def _refuse(row: VerifiableRow, blobs: Mapping[str, str | None]) -> tuple[str, str, int]:
    """(rule, detail, unresolved_count) for one row.

    ("", "", 0) means every reference resolved. The unresolved count is over
    REFERENCES, so a row citing three fabricated paths contributes three --
    the guard measures citation quality, not row count (E-48 P3-D2).
    """
    unresolved = 0
    first_rule = ""
    first_detail = ""

    for ref in row.evidence:
        body = blobs.get(ref.path)
        # None is unresolved; "" is a resolved EMPTY file. Truthiness would
        # collapse them (read_committed_bytes' docstring states the rule).
        if body is None:
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_ref_unresolved"
                first_detail = f"evidence path {ref.path!r} does not resolve at the pinned commit"
            continue
        refusal = _range_refusal(ref, body)
        if refusal:
            unresolved += 1
            if not first_rule:
                first_rule = refusal
                first_detail = (
                    f"evidence lines {ref.lines!r} lie outside {ref.path!r}, "
                    f"which has {_line_span(body)} line(s)"
                )

    if row.quote:
        if not row.quote.strip():
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_quote_empty"
                first_detail = (
                    "the quote is blank, and an empty quote grounds trivially "
                    "against any file (E-43)"
                )
        elif not row.evidence:
            unresolved += 1
            if not first_rule:
                first_rule = "dropped_quote_unanchored"
                first_detail = (
                    "the quote names no evidence path, so there is nothing to verify it against"
                )
        else:
            body = blobs.get(row.evidence[0].path)
            if body is not None and not verify_quote(row.quote, body, Profile.VERBATIM_BYTES):
                unresolved += 1
                if not first_rule:
                    first_rule = "dropped_quote_unverified"
                    first_detail = (
                        f"the quote does not byte-verify against "
                        f"{row.evidence[0].path!r} under VERBATIM_BYTES"
                    )

    return first_rule, first_detail, unresolved


def verify_rows(
    rows: Iterable[R], blobs: Mapping[str, str | None], *, id_of: Callable[[R], str]
) -> RowVerification[R]:
    """Every reference resolved, every quote byte-verified.

    `blobs` maps every path the rows cited to their bytes at the pinned
    commit, or None when the path did not resolve. The caller reads them;
    this function decides.
    """
    survivors: list[R] = []
    refusals: dict[str, tuple[str, str]] = {}
    total = 0
    unresolved_total = 0

    for row in rows:
        total += len(row.evidence) + (1 if row.quote else 0)
        rule, detail, unresolved = _refuse(row, blobs)
        unresolved_total += unresolved
        if rule:
            # Last writer wins is fine: both callers refuse a duplicated id
            # downstream, so two refusals for one id cannot both reach an
            # artifact.
            refusals[id_of(row)] = (rule, detail)
        else:
            survivors.append(row)

    return RowVerification(
        survivors=tuple(survivors),
        refusals=refusals,
        total_references=total,
        unresolved_references=unresolved_total,
    )


def cited_paths_of(rows: Iterable[VerifiableRow]) -> tuple[str, ...]:
    """Every path the rows cite, sorted and deduped -- the activity's read
    list. Sorted because the activity's git reads must not depend on row
    order (NFR-10)."""
    return tuple(sorted({ref.path for row in rows for ref in row.evidence}))


def guard_reason(v: Fabricating) -> str:
    """The phase-level guard: the reason a caller must treat the whole
    proposal as unusable, or "" when it is usable.

    Deliberately returns a REASON rather than a bool. The caller puts this
    string on its artifact, and a bare True would leave it to reinvent the
    explanation -- which is how two reasons that must not converge start
    converging.
    """
    if v.fabrication_rate <= CITATION_GUARD_MAX_UNRESOLVED:
        return ""
    return (
        f"the proposer's citation fabrication rate is "
        f"{v.unresolved_references}/"
        f"{v.total_references} = "
        f"{v.fabrication_rate:.2f}, past the "
        f"{CITATION_GUARD_MAX_UNRESOLVED:.2f} guard -- too many "
        f"references failed to resolve for the surviving ones to be "
        f"evidence"
    )
