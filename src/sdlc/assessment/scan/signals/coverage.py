"""QS2 -- coverage (FR-912), without running the suite.

D12 cut the suite run for two reasons that both still hold: executing the
assessed repository's tests would widen NFR-9's exposure past E-41's build
probe, and a suite run is not a pure function of the tree, so it could not be
memoized under D10 anyway.

So: parse a coverage report the repository COMMITTED, else compute BrownKit's
proxy from QS1's mapping and mark it `proxy` / LOW. Never a bare percentage --
a coverage record carries its source and its confidence (BrownKit's own
acceptance gate 5), which is what stops a proxy reading as a measurement.

The XML comes from an untrusted repository, so it is parsed with defusedxml --
the same guard measure_coverage carries, for the same reason. That activity is
NOT reused: it reads a worktree and averages a diff-scoped subset, while this
reads a blob at a pinned commit and reports per file.

Pure: paths, report text and the declared upstream in, records out.
"""
from __future__ import annotations

import math
import posixpath
import re
from collections.abc import Mapping, Sequence

import defusedxml.ElementTree as DET
from defusedxml.common import DefusedXmlException

from ....measurement import Measurement
from ..models import (
    C_COVERAGE, Confidence, CoverageRecord, ScanSignalId, ScanSignalResult,
    ScanUpstream, SignalOutput, SignalSource, family_of,
)
from ..sources import SOURCE_EXTENSIONS
from ..testpaths import is_test_path

SIGNAL_ID = "QS2"
VERSION = 1

# Where a committed Cobertura report lives. Checked in this order; the first
# that parses wins, so a repository with several reports gets a deterministic
# answer.
REPORT_PATHS: tuple[str, ...] = (
    "coverage.xml",
    "cobertura.xml",
    "coverage/cobertura-coverage.xml",
    "reports/coverage.xml",
    "build/reports/cobertura/coverage.xml",
)

# Files that carry no logic to cover. Excluding them is BrownKit's
# "significant_files excludes DTOs, generated code, entry-point thin wrappers
# and configuration", ported as the deterministic subset of that rule.
_BARRELS: frozenset[str] = frozenset({
    "__init__.py", "index.ts", "index.js", "index.tsx", "index.jsx",
    "mod.rs", "package-info.java",
})
_GENERATED = re.compile(
    r"(^|/)(node_modules|vendor|dist|build|out|\.next|\.nuxt|target|"
    r"migrations|generated|__generated__|proto)/")


def _significant(path: str) -> bool:
    return (path.endswith(SOURCE_EXTENSIONS)
            and not is_test_path(path)
            and posixpath.basename(path) not in _BARRELS
            and not _GENERATED.search(path))


def _from_report(text: str) -> tuple[list[CoverageRecord], int] | None:
    """(records, non-finite count) from Cobertura XML, or None when it does
    not parse. A truncated report is a fallback to the proxy, not a crash."""
    try:
        root = DET.fromstring(text)
    except (DefusedXmlException, DET.ParseError, ValueError):
        return None
    records: list[CoverageRecord] = []
    non_finite = 0
    for cls in root.iter("class"):
        filename = cls.get("filename") or ""
        if not filename:
            continue
        try:
            rate = float(cls.get("line-rate", "0"))
        except ValueError:
            continue
        if not math.isfinite(rate):
            non_finite += 1
            continue
        records.append(CoverageRecord(
            scope="file", path=filename,
            covered=Measurement.measured(max(0.0, min(100.0, rate * 100.0))),
            source="report", tool="cobertura", confidence=Confidence.HIGH))
    return sorted(records, key=lambda r: r.path), non_finite


def _proxy(paths: Sequence[str],
           upstream: ScanUpstream) -> list[CoverageRecord]:
    """min(1.0, tested_files / significant_files) per package -- BrownKit's
    formula, over QS1's mapping."""
    covered = {p for record in upstream.tests for p in record.covers}
    packages: dict[str, list[str]] = {}
    for path in sorted(paths):
        if _significant(path):
            packages.setdefault(posixpath.dirname(path) or ".",
                                []).append(path)
    out: list[CoverageRecord] = []
    for package in sorted(packages):
        files = packages[package]
        tested = sum(1 for f in files if f in covered)
        out.append(CoverageRecord(
            scope="package", path=package,
            covered=Measurement.measured(
                min(1.0, tested / len(files)) * 100.0),
            source="proxy", confidence=Confidence.LOW))
    return out


def _row(collected: Measurement) -> ScanSignalResult:
    return ScanSignalResult(
        signal=ScanSignalId.QS2, family=family_of(ScanSignalId.QS2),
        version=VERSION, source=SignalSource.COMPUTED, collected=collected,
        categories={C_COVERAGE: collected})


def evaluate(paths: Sequence[str], reports: Mapping[str, str],
             upstream: ScanUpstream) -> SignalOutput:
    """`reports` is path -> text for whichever of REPORT_PATHS the tree
    carries; `upstream` carries QS1's records and row state."""
    for path in REPORT_PATHS:
        if path not in reports:
            continue
        parsed = _from_report(reports[path])
        if parsed is None:
            continue                              # fall through to the proxy
        records, non_finite = parsed
        if records:
            collected = Measurement.measured(float(len(records)))
            return SignalOutput(row=_row(collected), coverage=records)
        if non_finite:
            # An attempt DID produce output and it is uninterpretable: that
            # is unknown, not not_collected (FR-915's own distinction).
            return SignalOutput(row=_row(Measurement.unknown(
                f"coverage: {path} parsed but every line-rate was "
                f"non-finite ({non_finite} class(es))")))

    if not upstream.measured(ScanSignalId.QS1):
        return SignalOutput(row=_row(Measurement.not_collected(
            f"coverage: no committed report in {list(REPORT_PATHS)} and the "
            f"proxy needs QS1's mapping, which did not collect "
            f"({upstream.gap(ScanSignalId.QS1, 'coverage').reason})")))

    records = _proxy(paths, upstream)
    if not records:
        return SignalOutput(row=_row(Measurement.not_collected(
            "coverage: no committed report and no significant source file to "
            "compute a proxy over")))
    collected = Measurement.measured(float(len(records)))
    return SignalOutput(row=_row(collected), coverage=records)
