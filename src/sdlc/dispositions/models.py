"""FR-304/FR-917 (E-50): a false-positive disposition over one finding.

Pure by design -- Pydantic only. This module must never import
assessment/models.py, activities.py, or temporalio -- store.py is the one
impure sibling, exactly as capability/store.py is to capability/models.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class Disposition(StrEnum):
    FALSE_POSITIVE = "false_positive"
    MITIGATED_ELSEWHERE = "mitigated_elsewhere"
    ACCEPTED_RISK = "accepted_risk"


class FindingDisposition(BaseModel):
    """One audited human decision over one finding. `kind` is an explicit
    discriminator rather than a prefix-sniff over `key`: Vulnerability.key
    (security_identity) and testability_identity() happen never to collide
    today, but a kind field makes that a stated invariant rather than an
    accident the store's row lookup silently relies on (GD7).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["vulnerability", "testability"]
    key: str
    disposition: Disposition
    approved_by: str
    reason: str
    decided_at: datetime

    @model_validator(mode="after")
    def _audited(self) -> FindingDisposition:
        if not self.approved_by.strip():
            raise ValueError(
                "approved_by is required -- an unattributed disposition is not an audited one"
            )
        if not self.reason.strip():
            raise ValueError("reason is required")
        if not self.key.strip():
            raise ValueError("key is required")
        return self
