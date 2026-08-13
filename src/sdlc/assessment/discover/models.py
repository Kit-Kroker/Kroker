"""FR-913 (E-47b): capability coverage and orphan classification contracts.

Pure by design -- Pydantic and measurement.py only. This module must never
import models.py, activities.py, or temporalio, exactly as capability/models.py
and assessment/models.py must not: a dependency here would appear as a
reviewable import.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from ...measurement import CollectionState, Measurement

DEFAULT_COVERAGE_FLOOR = 0.90
DEAD_GUARD_MAX_UNRESOLVED = 0.10


class FileBucket(str, Enum):
    """Declaration order IS precedence order (see BUCKET_PRECEDENCE), so
    there is no second list to disagree with this one -- PHASE_ORDER's rule.
    """
    MEMBER = "member"
    INFRASTRUCTURE = "infrastructure"
    ATTACHED = "attached"
    DEAD = "dead"
    UNCLASSIFIED = "unclassified"


BUCKET_PRECEDENCE: tuple[FileBucket, ...] = tuple(FileBucket)

# D4: a file counts FOR coverage when the assessment can say what it is.
ACCOUNTED_FOR: frozenset[FileBucket] = frozenset(
    {FileBucket.MEMBER, FileBucket.INFRASTRUCTURE, FileBucket.ATTACHED})

# Only these two buckets name capabilities. A dead file citing one, or an
# attached file citing none, is a contradiction the type should not express.
CITES_CAPABILITIES: frozenset[FileBucket] = frozenset(
    {FileBucket.MEMBER, FileBucket.ATTACHED})


class FileAttribution(BaseModel):
    """One file's verdict, carrying the rule that produced it.

    Frozen, so `capabilities` is asserted sorted rather than sorted in place:
    a producer that emits discovery order is a determinism bug (NFR-10), and
    silently repairing it here would hide that.
    """
    model_config = {"frozen": True}
    path: str
    bucket: FileBucket
    rule: str
    detail: str = ""
    capabilities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _capabilities_match_bucket(self) -> "FileAttribution":
        cites = self.bucket in CITES_CAPABILITIES
        if cites and not self.capabilities:
            raise ValueError(
                f"bucket={self.bucket.value} must cite at least one "
                f"capability -- it is defined by its relation to one")
        if not cites and self.capabilities:
            raise ValueError(
                f"bucket={self.bucket.value} must not cite capabilities "
                f"(got {self.capabilities}) -- an orphan by definition "
                f"belongs to none")
        return self

    @model_validator(mode="after")
    def _capabilities_are_sorted(self) -> "FileAttribution":
        if list(self.capabilities) != sorted(set(self.capabilities)):
            raise ValueError(
                f"capabilities {self.capabilities} are not sorted and "
                f"deduped -- discovery order must not reach the artifact")
        return self


class UnresolvedEdge(BaseModel):
    """An import we saw and could not turn into an edge. `relative` is the
    field the dead guard reads: a dotted import matching nothing is an
    external package, but a RELATIVE one is extractor failure (D6)."""
    model_config = {"frozen": True}
    source_path: str
    target: str                     # the raw module string, verbatim
    form: str                       # "python_relative", "js_bare", ...
    reason: str                     # "no_matching_path" | "ambiguous_suffix"
    relative: bool


class ReferenceGraph(BaseModel):
    edges: tuple[tuple[str, str], ...] = ()      # (importer, imported)
    unresolved: tuple[UnresolvedEdge, ...] = ()
    parsed: tuple[str, ...] = ()                 # extractor covers these
    unparsed: tuple[str, ...] = ()               # extension not in the table
    unresolved_relative_rate: Measurement


class AttributionReport(BaseModel):
    files: tuple[FileAttribution, ...] = ()
    counts: dict[FileBucket, int] = Field(default_factory=dict)
    coverage: Measurement                        # the ratio, or not_collected
    floor: float = DEFAULT_COVERAGE_FLOOR
    meets_floor: bool
    dead_guard_tripped: bool = False
    graph: ReferenceGraph
    skipped: tuple[str, ...] = ()                # blobs that could not be read

    @model_validator(mode="after")
    def _counts_agree_with_files(self) -> "AttributionReport":
        missing = [b.value for b in FileBucket if b not in self.counts]
        if missing:
            raise ValueError(
                f"counts must carry every bucket, including zeros (missing "
                f"{missing}) -- an absent key and a zero count are different "
                f"claims and only one of them is true")
        for bucket in FileBucket:
            actual = sum(1 for f in self.files if f.bucket is bucket)
            if self.counts[bucket] != actual:
                raise ValueError(
                    f"counts[{bucket.value}]={self.counts[bucket]} but "
                    f"{actual} file(s) carry that bucket -- counts are "
                    f"derived from files, never assigned")
        return self

    @model_validator(mode="after")
    def _meets_floor_is_derived(self) -> "AttributionReport":
        """Derived, never assigned, so a deserialized payload cannot disagree
        with its own arithmetic. A not_collected coverage NEVER meets the
        floor: an assessment that could not measure must not read as one that
        measured and passed (FR-915)."""
        expected = (self.coverage.state is CollectionState.MEASURED
                    and self.coverage.value is not None
                    and self.coverage.value >= self.floor)
        if self.meets_floor != expected:
            raise ValueError(
                f"meets_floor={self.meets_floor} does not match the derived "
                f"{expected} for coverage={self.coverage.state.value} "
                f"floor={self.floor} -- meets_floor is derived, "
                f"never assigned")
        return self
