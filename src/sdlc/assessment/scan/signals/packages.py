"""S1 -- package structure (FR-912).

BrownKit scans top-level modules/packages/directories at depth 1-3 and rates
each grouping by whether its name suggests a business domain. Ported with the
classification carried as the RULE that fired rather than a boolean, because
E-48's guardrail -- delivery channels and deployment boundaries are not
capabilities -- needs the distinction, not just its outcome.

Pure: text and paths in, records out. The activity reads the tree.
"""
from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence

from ....measurement import Measurement
from ..models import (
    C_PACKAGES, CandidateMember, Confidence, EvidenceRef, MemberKind,
    ScanSignalId, ScanSignalResult, SignalOutput, SignalSource, SourceCandidate,
    family_of,
)
from ..naming import GENERIC_NAMES, LAYER_NAMES
from ..sources import SOURCE_EXTENSIONS

SIGNAL_ID = "S1"
VERSION = 1

# BrownKit's worked list, kept short on purpose. A term absent from here is
# NOT dismissed -- it falls to s1_unclassified_name at MEDIUM. Growing this
# table raises confidence; it never creates or destroys a candidate.
DOMAIN_TERMS: frozenset[str] = frozenset({
    "payment", "payments", "billing", "invoice", "invoices", "customer",
    "customers", "order", "orders", "inventory", "catalog", "product",
    "products", "shipping", "delivery", "account", "accounts", "auth",
    "identity", "kyc", "compliance", "notification", "notifications",
    "messaging", "search", "reporting", "analytics", "subscription",
    "subscriptions", "pricing", "checkout", "cart", "refund", "refunds",
    "booking", "bookings", "reservation", "reservations", "ledger",
    "settlement", "onboarding", "loyalty", "review", "reviews",
})

MAX_DEPTH = 3

M_FILE_COUNT = "file_count"
M_LOC_ESTIMATE = "loc_estimate"


def _classify(name: str) -> tuple[str, Confidence, str]:
    """(rule, contribution, detail) for a directory name.

    Layer is checked before generic because a few words are arguably both,
    and the more specific claim is the more useful one to E-48.
    """
    key = name.lower()
    if key in LAYER_NAMES:
        return ("s1_layer_name", Confidence.LOW,
                f"{name!r} names a technical layer, not a capability.")
    if key in GENERIC_NAMES:
        return ("s1_generic_name", Confidence.LOW,
                f"{name!r} is a generic container name.")
    if key in DOMAIN_TERMS:
        return ("s1_domain_term", Confidence.HIGH,
                f"{name!r} is a business-domain term.")
    return ("s1_unclassified_name", Confidence.MEDIUM,
            f"{name!r} is a specific name absent from the domain-term table; "
            f"it is not generic, but nothing here vouches for it.")


def _slug(directory: str) -> str:
    """A local_id fragment. '--' joins path segments so the depth is
    recoverable from the id and no separator collides with signal_of's '-'
    split on the FIRST hyphen."""
    return "--".join(directory.split("/"))


def _directories(paths: Sequence[str]) -> dict[str, list[str]]:
    """directory -> its source files, for every directory at depth 1..3 that
    contains a source file recursively. Sorted at every level so traversal
    order cannot reach the artifact."""
    out: dict[str, list[str]] = {}
    for path in sorted(paths):
        if not path.endswith(SOURCE_EXTENSIONS):
            continue
        segments = path.split("/")[:-1]
        for depth in range(1, min(len(segments), MAX_DEPTH) + 1):
            out.setdefault("/".join(segments[:depth]), []).append(path)
    return out


def evaluate(paths: Sequence[str], loc: Mapping[str, int],
             skipped: Sequence[str] = ()) -> SignalOutput:
    """`paths` is every tracked path; `loc` is path -> line count for the
    blobs that were read; `skipped` is the paths whose blob was unreadable or
    over MAX_BLOB_BYTES (spec section 6)."""
    skipped_set = set(skipped)
    candidates: list[SourceCandidate] = []

    for directory, files in sorted(_directories(paths).items()):
        name = posixpath.basename(directory)
        rule, contribution, detail = _classify(name)
        direct = [f for f in files
                  if posixpath.dirname(f) == directory]

        members = [CandidateMember(kind=MemberKind.PACKAGE_PATH,
                                   value=directory, path=directory)]
        members += [CandidateMember(kind=MemberKind.FILE_PATH, value=f,
                                    path=f)
                    for f in direct]

        missing = sorted(f for f in files
                         if f in skipped_set or f not in loc)
        if missing:
            loc_metric = Measurement.not_collected(
                f"line counts unavailable for {len(missing)} of "
                f"{len(files)} file(s) (first: {missing[0]}); a partial sum "
                f"must not pass as a complete one")
        else:
            loc_metric = Measurement.measured(
                float(sum(loc[f] for f in files)))

        candidates.append(SourceCandidate(
            signal=ScanSignalId.S1, local_id=f"S1-{_slug(directory)}",
            name=name, rule=rule, detail=detail,
            confidence_contribution=contribution,
            members=members,
            evidence=[EvidenceRef(path=directory)],
            metrics={
                M_FILE_COUNT: Measurement.measured(float(len(files))),
                M_LOC_ESTIMATE: loc_metric,
            }))

    candidates.sort(key=lambda c: c.local_id)
    # A repository with no source files is a MEASURED zero, not a gap: we
    # looked, and there is none. This is scaffold.py's precedent for the
    # structure dimension, and it is the one place in this module where zero
    # is the honest answer -- S3 reaches the opposite conclusion for a
    # reason its own docstring gives (P2-D1).
    collected = Measurement.measured(float(len(candidates)))
    return SignalOutput(
        row=ScanSignalResult(
            signal=ScanSignalId.S1, family=family_of(ScanSignalId.S1),
            version=VERSION, source=SignalSource.COMPUTED,
            collected=collected, categories={C_PACKAGES: collected}),
        sources=candidates)
