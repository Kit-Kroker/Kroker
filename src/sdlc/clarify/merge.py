"""Deterministic merge of the supervisor's and the probes' questions.

Pure: no model call. Ranking and truncation are POLICY, not judgement, and a
model here would be a third opinion with no grounding. Pure code also makes
the cap testable without a model.

Two different removals happen here and they mean different things:
  - DISCARD: a grounded question with no evidence. It is speculation and is
    not recorded anywhere -- it was never a real candidate.
  - DROP: a real question that lost the ranking cut. It IS recorded, on
    `dropped`, so the benchmark can score "material question never asked".
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..models import (ClarificationDimension, ClarifiedRequirements,
                      OpenQuestion)
from .models import ClarifyRoute, ProbeResult

_CANONICAL = {d: i for i, d in enumerate(ClarificationDimension)}
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Dedup key: case, surrounding space, inner whitespace runs and a
    trailing question mark are all noise. Two specialists reaching the same
    question from different angles is the signal we are collapsing."""
    return _WS.sub(" ", text.strip().lower()).rstrip("?").strip()


def _sort_key(q: OpenQuestion) -> tuple[float, int, str]:
    """Materiality descending with None last, then canonical dimension order
    with no-dimension last, then id. Total and stable, so a replay of the
    same inputs produces the same batch."""
    # None -> +1.0 sorts after every real score, since real scores negate to
    # <= 0.0 and are compared ascending.
    materiality = -q.materiality if q.materiality is not None else 1.0
    dim = _CANONICAL.get(q.dimension, len(_CANONICAL))
    return (materiality, dim, q.id)


def merge_clarification(
    route: ClarifyRoute,
    probes: Sequence[ProbeResult],
    *,
    cap: int,
    grounded: frozenset[ClarificationDimension],
) -> ClarifiedRequirements:
    """Fold the supervisor's body and every question into one artifact."""
    candidates: list[OpenQuestion] = list(route.questions)
    for probe in probes:
        for q in probe.questions:
            # The probe's own dimension is authoritative, unconditionally:
            # the burst knows which probe it dispatched, and the model's own
            # self-report cannot be trusted to agree. A disagreeing value
            # left in place would let a grounded probe's question dodge the
            # evidence-required discard below by mislabelling itself into an
            # ungrounded dimension.
            candidates.append(q.model_copy(update={"dimension": probe.dimension}))

    # DISCARD ungrounded speculation before anything else, so it cannot win a
    # slot or pollute the dedup.
    candidates = [q for q in candidates
                  if q.dimension not in grounded or q.evidence]

    # DEDUP, keeping the strongest claim for each distinct question.
    best: dict[str, OpenQuestion] = {}
    for q in candidates:
        key = _norm(q.question)
        incumbent = best.get(key)
        if incumbent is None or _sort_key(q) < _sort_key(incumbent):
            best[key] = q

    # A collided id would break answer_question's per-question routing, so
    # suffix duplicates deterministically after ranking.
    ranked = sorted(best.values(), key=_sort_key)
    seen: dict[str, int] = {}
    unique: list[OpenQuestion] = []
    for q in ranked:
        n = seen.get(q.id, 0)
        seen[q.id] = n + 1
        unique.append(q if n == 0 else q.model_copy(update={"id": f"{q.id}-{n}"}))

    return ClarifiedRequirements(
        summary=route.summary,
        functional_requirements=route.functional_requirements,
        non_functional_requirements=route.non_functional_requirements,
        out_of_scope=route.out_of_scope,
        open_questions=unique[:cap],
        dropped=unique[cap:],
        dimensions_probed=sorted((p.dimension for p in probes),
                                 key=lambda d: _CANONICAL[d]),
    )
