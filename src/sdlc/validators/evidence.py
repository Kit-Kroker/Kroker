"""Evidence schemas for ADR-24's verdict functions (FR-205 handoff).

First consumer: `sdlc.validators.verdicts` (FR-301) -- `Verdict` carries
`Finding`s and `plan_valid` builds them from the FR-205 checks' reasons.
They landed consumer-free in FR-205 deliberately, so ADR-24
("evidence before verdict; code computes the verdict", docs/adr.md) had a
FIXED INPUT SHAPE before its verdict functions existed -- `approve`,
`tests_passed`, `plan_valid` and their kin are meant to be pure functions
over typed evidence, never a model's say-so -- and so artifact models can
adopt them incrementally, one schema at a time.

The binding convention they hand forward (pinned in
tests/validators/test_evidence.py): on every model here, evidence fields
are declared BEFORE status fields.

Pure module: Pydantic only -- no temporalio, no I/O.
"""

from __future__ import annotations

from pydantic import BaseModel


class AssertionEvidence(BaseModel):
    """One checkable claim plus the evidence backing it.

    `source` defaults to "": prose-only evidence is legitimate -- ADR-24
    asks that claims be checkable where possible, not that every claim
    cite a file.
    """

    claim: str
    evidence: str
    source: str = ""  # file:line citation, when the evidence has one


class Finding(BaseModel):
    """One verdict-level finding: its evidence, a detail, and a status.

    The evidence field comes first, the status fields after -- the ADR-24
    ordering this module exists to hand forward. `blocking` defaults to
    False: a Finding records; only an explicit True gates.
    """

    evidence: AssertionEvidence
    detail: str = ""
    blocking: bool = False


class Coverage(BaseModel):
    """Requirement-coverage snapshot: which ids are covered, which are
    not, out of how many.

    `total` is carried as its own field rather than derived from
    `covered`/`uncovered` so a verdict function can tell "nothing to
    cover" apart from "empty coverage" without re-deriving the universe.
    """

    total: int
    covered: list[str]
    uncovered: list[str]
