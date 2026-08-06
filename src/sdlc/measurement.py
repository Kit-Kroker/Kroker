"""FR-915 (E-40): a value that was never measured must not be representable as
a measured value.

Imported wholesale from BrownKit's `not-collected` discipline, which treats it
as a first-class state with a recorded reason and forbids defaulting to zero.
The model validator is the mechanism: `Measurement(NOT_COLLECTED, value=0.0)`
does not construct, so the ambiguity cannot be reintroduced by a careless
producer.

Pure by design -- Pydantic only. This module must never import models.py,
activities.py, or temporalio; a dependency here would appear as a reviewable
import.
"""
from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, model_validator


class CollectionState(str, Enum):
    MEASURED = "measured"
    NOT_COLLECTED = "not_collected"   # we did not or could not measure
    UNKNOWN = "unknown"               # we tried; the result is uninterpretable


class Measurement(BaseModel):
    """A number we may not have, with the reason we do not have it.

    NOT_COLLECTED vs UNKNOWN: no coverage.xml is not_collected; a coverage.xml
    that parses but yields a non-finite rate is unknown. The distinction is
    whether an attempt produced output. Both require a reason.
    """
    state: CollectionState
    value: float | None = None
    reason: str = ""

    @model_validator(mode="after")
    def _value_matches_state(self) -> "Measurement":
        if self.state is CollectionState.MEASURED:
            if self.value is None:
                raise ValueError("MEASURED requires a value")
            if not math.isfinite(self.value):
                # nan/inf silently corrupt downstream comparisons (nan >=
                # threshold is False, fabricating an advisory failure). The
                # guard belongs in the type, not the producer: E-41 reuses
                # this type without inheriting measure_coverage's guard.
                raise ValueError(
                    f"MEASURED must be finite (got {self.value!r}) -- a "
                    f"non-finite value is the conflation this type exists "
                    f"to prevent")
        else:
            if self.value is not None:
                raise ValueError(
                    f"{self.state.value} must not carry a value "
                    f"(got {self.value!r}) -- that is the conflation this "
                    f"type exists to prevent")
            if not self.reason.strip():
                raise ValueError(f"{self.state.value} requires a reason")
        return self

    @classmethod
    def measured(cls, value: float) -> "Measurement":
        return cls(state=CollectionState.MEASURED, value=value)

    @classmethod
    def not_collected(cls, reason: str) -> "Measurement":
        return cls(state=CollectionState.NOT_COLLECTED, reason=reason)

    @classmethod
    def unknown(cls, reason: str) -> "Measurement":
        return cls(state=CollectionState.UNKNOWN, reason=reason)
