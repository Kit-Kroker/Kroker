"""Name normalization shared by S3's grouping and S5's merge (D9).

Sited once because both need the same rule -- S3 groups
PaymentController + PaymentSettlementJob + PaymentEventConsumer into one
candidate, and S5 merges that candidate with S1's payments/ package. Two
copies would agree only by coincidence.

Plan 2 fills in the tables. This module exists now because the registry
declares it as a rule module and rules_sha must be able to hash it.
"""
from __future__ import annotations

VERSION = 1

# Suffixes that describe a technical layer rather than a capability. Plan 2
# populates this; an empty tuple normalizes to lowercase-only, which is
# correct-but-weak rather than wrong.
LAYER_SUFFIXES: tuple[str, ...] = ()


def normalize(name: str) -> str:
    """The normalized form two candidates must share to be merged."""
    out = name.strip()
    for suffix in LAYER_SUFFIXES:
        if out.lower().endswith(suffix.lower()) and len(out) > len(suffix):
            out = out[: -len(suffix)]
            break
    return out.strip("_-").lower()
