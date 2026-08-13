"""FR-913 (E-47b): file->capability coverage and orphan classification.

The denominator is STRICT (D3): every source-extension blob at the pinned
commit, tests and build tooling included, nothing filtered out. The numerator
is ACCOUNTED-FOR (D4): a file counts for coverage when the assessment can say
what it is, and against it only when the assessment cannot. Together the floor
means "the tree is explained", not "the tree is capability-owned".

Pure: every input is a parameter. No disk, no subprocess, no repository code
executed (NFR-9).
"""
from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
from typing import NamedTuple

from ...measurement import CollectionState, Measurement
from ..scan.configpaths import is_config_path
from ..scan.sources import SOURCE_EXTENSIONS
from ..scan.testpaths import is_test_path
from . import refgraph
from .models import (
    ACCOUNTED_FOR, DEAD_GUARD_MAX_UNRESOLVED, DEFAULT_COVERAGE_FLOOR,
    AttributionReport, FileAttribution, FileBucket, ReferenceGraph,
)

# Source-language build and tooling config. `is_config_path` alone would leave
# the infrastructure bucket nearly empty: it matches Dockerfile, compose and
# .env, none of which are in D3's source-extension denominator.
#
# Deliberately NOT promoted to a scan/ rule module: it has exactly one
# consumer, and sources.py's rationale is that a table moves out when a SECOND
# one appears. conftest.py is excluded -- it is a test fixture, collected by
# the test runner and reached via is_test_path (framework_discovered_test),
# not build tooling.
BUILD_TOOLING_NAMES: frozenset[str] = frozenset({
    "setup.py", "manage.py", "noxfile.py", "tasks.py",
    "webpack.config.js", "vite.config.ts", "rollup.config.js",
    "jest.config.js", "karma.conf.js", "next.config.js",
    "babel.config.js", "tailwind.config.js", "gulpfile.js", "build.rs",
})

_SOURCE_EXTENSIONS = frozenset(SOURCE_EXTENSIONS)


def _in_denominator(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in _SOURCE_EXTENSIONS


def _empty_report(reason: str, graph: ReferenceGraph, floor: float,
                  skipped: Sequence[str]) -> AttributionReport:
    """FR-915: attribution did not happen, so there is no ratio -- not a
    zero, and certainly not a one."""
    return AttributionReport(
        files=(), counts={b: 0 for b in FileBucket},
        coverage=Measurement.not_collected(reason), floor=floor,
        meets_floor=False, dead_guard_tripped=False, graph=graph,
        skipped=tuple(sorted(skipped)))


class _Context(NamedTuple):
    member_of: dict[str, list[str]]
    neighbours: dict[str, set[str]]
    skipped: set[str]
    parsed: set[str]
    entry_points: set[str]
    guard_tripped: bool


def _classify(path: str, ctx: _Context) -> FileAttribution:
    """BUCKET_PRECEDENCE, in order. The first rule that fires wins."""
    if path in ctx.member_of:
        return FileAttribution(
            path=path, bucket=FileBucket.MEMBER, rule="capability_member",
            detail="claimed by a capability's member set",
            capabilities=tuple(sorted(set(ctx.member_of[path]))))
    if path in ctx.skipped:
        return FileAttribution(
            path=path, bucket=FileBucket.UNCLASSIFIED, rule="blob_unreadable",
            detail="the blob could not be read at the pinned commit")
    if is_config_path(path):
        return FileAttribution(
            path=path, bucket=FileBucket.INFRASTRUCTURE, rule="config_path",
            detail="matches a configuration/infrastructure path rule")
    if posixpath.basename(path) in BUILD_TOOLING_NAMES:
        return FileAttribution(
            path=path, bucket=FileBucket.INFRASTRUCTURE, rule="build_tooling",
            detail="a build or tooling configuration file")
    attached = sorted({
        bc for neighbour in ctx.neighbours.get(path, ())
        for bc in ctx.member_of.get(neighbour, ())})
    if attached:
        return FileAttribution(
            path=path, bucket=FileBucket.ATTACHED,
            rule="graph_connected_to_member",
            detail="shares an import edge with a capability member",
            capabilities=tuple(attached))
    # D7: `dead` is the claim a customer acts on by deleting code. All four
    # clauses must hold; any failure sends the file to unclassified, never to
    # a weaker positive.
    if path not in ctx.parsed:
        return FileAttribution(
            path=path, bucket=FileBucket.UNCLASSIFIED,
            rule="language_not_parsed",
            detail="no import extractor covers this file's language")
    if path in ctx.entry_points:
        return FileAttribution(
            path=path, bucket=FileBucket.UNCLASSIFIED,
            rule="framework_discovered_entry_point",
            detail="hosts an entry point, so it is reached by dispatch")
    if is_test_path(path):
        return FileAttribution(
            path=path, bucket=FileBucket.UNCLASSIFIED,
            rule="framework_discovered_test",
            detail="collected by a test runner by convention, not by import")
    if ctx.neighbours.get(path):
        return FileAttribution(
            path=path, bucket=FileBucket.UNCLASSIFIED,
            rule="referenced_by_unattributed_file",
            detail="referenced, but by nothing that reaches a capability")
    if ctx.guard_tripped:
        return FileAttribution(
            path=path, bucket=FileBucket.UNCLASSIFIED,
            rule="dead_guard_tripped",
            detail="too many relative imports failed to resolve for an "
                   "absence of references to be evidence")
    return FileAttribution(
        path=path, bucket=FileBucket.DEAD,
        rule="no_static_inbound_reference",
        detail="nothing in this tree statically references this file")


def attribute(
    inventory: Mapping[str, str],
    skipped: Sequence[str],
    members: Mapping[str, Sequence[str]],
    entry_points: Sequence[str],
    *,
    floor: float = DEFAULT_COVERAGE_FLOOR,
    max_unresolved: float = DEAD_GUARD_MAX_UNRESOLVED,
) -> AttributionReport:
    """Classify every file in the denominator and compute the coverage ratio.

    `inventory` is path -> blob text at the pinned commit; `skipped` names
    blobs that could not be read; `members` maps bc_id -> member paths;
    `entry_points` names paths hosting an S3 entry point.
    """
    readable = {p: t for p, t in inventory.items() if _in_denominator(p)}
    graph = refgraph.build(readable)

    # A file that could not be read is still a file the model failed to
    # attribute: dropping it would let an unreadable tree score 1.0.
    skipped_in = sorted({p for p in skipped if _in_denominator(p)})
    denominator = sorted(set(readable) | set(skipped_in))

    if not denominator:
        return _empty_report("no source files in the tree", graph, floor,
                             skipped_in)
    if not members:
        return _empty_report("no capabilities to attribute against", graph,
                             floor, skipped_in)

    member_of: dict[str, list[str]] = {}
    for bc_id, paths in members.items():
        for path in paths:
            member_of.setdefault(path, []).append(bc_id)

    neighbours: dict[str, set[str]] = {}
    for src, dst in graph.edges:
        neighbours.setdefault(src, set()).add(dst)
        neighbours.setdefault(dst, set()).add(src)

    rate = graph.unresolved_relative_rate
    guard_tripped = (rate.state is CollectionState.MEASURED
                     and rate.value is not None
                     and rate.value > max_unresolved)

    context = _Context(
        member_of=member_of, neighbours=neighbours,
        skipped=set(skipped_in), parsed=set(graph.parsed),
        entry_points=set(entry_points), guard_tripped=guard_tripped)

    files = tuple(_classify(path, context) for path in denominator)
    counts = {b: sum(1 for f in files if f.bucket is b) for b in FileBucket}
    accounted = sum(counts[b] for b in ACCOUNTED_FOR)
    coverage = Measurement.measured(accounted / len(denominator))

    return AttributionReport(
        files=files, counts=counts, coverage=coverage, floor=floor,
        meets_floor=coverage.value >= floor,
        dead_guard_tripped=guard_tripped,
        graph=graph, skipped=tuple(skipped_in))
