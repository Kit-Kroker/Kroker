# src/sdlc/assessment/discover/apply.py
"""FR-913 (E-48 DD6/DD7/DD8): dispositions in, the locked candidate set out.

Pure by design -- Pydantic, measurement.py and capability/models.py only. This
module must never import models.py, activities.py, or temporalio, exactly as
the rest of discover/ must not.

Four things happen here and they are deliberately separate functions:
`baseline_dispositions` is DD6's code-computed verdict, `stamp` is DD8's
structural verification plus DD7's two fallbacks, `apply` turns verified
dispositions into the boundaries the lock will identify, and `build_map` is
the artifact's one constructor. Splitting them is what lets plan 3 insert a
proposer between the first and the second without touching either.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ValidationError, model_validator

from ...capability.models import Advisory, CapabilityFingerprint
from ...measurement import Measurement
from ..scan.models import CandidateMember, Confidence
from .map import (
    REJECTING_ACTIONS, Capability, CandidateContext, CandidateDisposition,
    CapabilityMap, DiscoverAction, DiscoverContext, DiscoverProposal,
    DispositionSource, ProposedDisposition,
)
from .models import AttributionReport, DecompositionReport, OwnershipReport
from .tiers import group_by_tier


def baseline(context: CandidateContext) -> CandidateDisposition:
    """DD6's table, read top to bottom. Declaration order IS precedence
    order, following BUCKET_PRECEDENCE -- there is no second list to disagree
    with this one.

    The guardrail outranks the duplicate flag deliberately (P2-D1): a
    candidate named like a layer is not a capability whichever other
    candidate it overlaps, and FLAGging it would ask a human to adjudicate a
    boundary clause D2 already rejects.
    """
    row = dict(candidate_id=context.candidate_id,
               source=DispositionSource.BASELINE)
    if context.guardrail_only:
        return CandidateDisposition(
            **row, action=DiscoverAction.DE_SCOPE, rule="baseline_guardrail")
    if context.possible_duplicate_of:
        return CandidateDisposition(
            **row, action=DiscoverAction.FLAG,
            rule="baseline_possible_duplicate")
    return CandidateDisposition(
        **row, action=DiscoverAction.CONFIRM, rule="baseline_confirm")


def baseline_dispositions(
        context: DiscoverContext) -> tuple[CandidateDisposition, ...]:
    """One baseline per candidate, in the context's order -- which
    build_context already sorted by candidate_id (NFR-10)."""
    return tuple(baseline(c) for c in context.candidates)
