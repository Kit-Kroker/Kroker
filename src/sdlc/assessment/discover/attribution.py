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

from ...measurement import Measurement
from ..scan.configpaths import is_config_path
from ..scan.sources import SOURCE_EXTENSIONS
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
    return FileAttribution(
        path=path, bucket=FileBucket.DEAD,
        rule="no_static_inbound_reference",
        detail="no import edge connects this file to a capability")


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

    context = _Context(
        member_of=member_of, neighbours=neighbours,
        skipped=set(skipped_in), parsed=set(graph.parsed),
        entry_points=set(entry_points), guard_tripped=False)

    files = tuple(_classify(path, context) for path in denominator)
    counts = {b: sum(1 for f in files if f.bucket is b) for b in FileBucket}
    accounted = sum(counts[b] for b in ACCOUNTED_FOR)
    coverage = Measurement.measured(accounted / len(denominator))

    return AttributionReport(
        files=files, counts=counts, coverage=coverage, floor=floor,
        meets_floor=coverage.value >= floor, dead_guard_tripped=False,
        graph=graph, skipped=tuple(skipped_in))
