"""Deterministic merge of the supervisor's and the probes' questions.

Pure: no model call. Ranking and truncation are POLICY, not judgement, and a
model here would be a third opinion with no grounding. Pure code also makes
the cap testable without a model.

Two different removals happen here and they mean different things:
  - DISCARD: a question that was never a real candidate -- a grounded
    question with no evidence, or one scored below MATERIALITY_FLOOR. Not
    recorded anywhere.
  - DROP: a real question that lost the ranking cut. It IS recorded, on
    `dropped`, so the benchmark can score "material question never asked".
"""
from __future__ import annotations

import re
from collections.abc import Sequence

from ..models import (ClarificationDimension, ClarifiedRequirements,
                      OpenQuestion)
from .models import ClarifyRoute, ProbeResult
from .routing import SUPERVISOR_DIMENSIONS

_CANONICAL = {d: i for i, d in enumerate(ClarificationDimension)}
_WS = re.compile(r"\s+")

# Both prompts define this line themselves -- "below 0.3 -- do not ask it".
# Enforcing it here is what keeps the cap a CEILING instead of an ATTRACTOR:
# without a floor, `unique[:cap]` hands the human exactly `cap` questions
# whenever the candidate pool is larger, which is the inversion of MAC's
# result (success up, dialogue DOWN) that spec §13 names as the risk
# deciding whether E-85 was worth building. Merge is the policy layer (§3),
# so the number lives here rather than being left to prompt compliance.
#
# Keep this in sync with the 0.3 boundary written into ROUTE_SCOPE and
# PROBE_PREFIX in prompts.py; the scale is defined there, enforced here.
MATERIALITY_FLOOR = 0.3


def _norm(text: str) -> str:
    """Dedup key: case, surrounding space, inner whitespace runs and a
    trailing question mark are all noise. Two specialists reaching the same
    question from different angles is the signal we are collapsing."""
    return _WS.sub(" ", text.strip().lower()).rstrip("?").strip()


def _sort_key(q: OpenQuestion) -> tuple[float, int, str]:
    """Materiality descending, then canonical dimension order with
    no-dimension last, then id. Total and stable, so a replay of the same
    inputs produces the same batch."""
    # The None branch is defensive only: the floor below removes unscored
    # questions before anything is sorted. +1.0 sorts after every real
    # score, since real scores negate to <= 0.0 and are compared ascending.
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
    # The supervisor owns C1/C2 and nothing else, so CLAMP its self-reported
    # dimension exactly as a probe's is clamped below. Without this a
    # supervisor question mislabelled into a grounded dimension (C3-C6) --
    # against its instructions, but models drift -- would carry no evidence,
    # fail the evidence-required discard, and vanish into neither
    # open_questions NOR dropped. None is the honest fallback: the question
    # is real, its dimension is not knowable.
    candidates: list[OpenQuestion] = [
        q if q.dimension in SUPERVISOR_DIMENSIONS
        else q.model_copy(update={"dimension": None})
        for q in route.questions
    ]
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

    # DISCARD anything below the bar both prompts already state. A sub-floor
    # question was never material, so it is NOT recorded on `dropped` --
    # `dropped` means "material but lost the cap", and blurring the two
    # would make the benchmark's "is the cap discarding material work?"
    # metric unreadable. An unscored question is treated the same way: an
    # author that skipped the scale did not clear it either, and keeping
    # such questions would let them ride into a capped batch ahead of
    # genuinely scored ones the moment the pool is smaller than the cap.
    candidates = [q for q in candidates
                  if q.materiality is not None
                  and q.materiality >= MATERIALITY_FLOOR]

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
