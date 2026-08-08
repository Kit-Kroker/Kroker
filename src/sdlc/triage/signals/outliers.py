"""FR-902 size and duplication outliers (E-41d).

ABSOLUTE thresholds from the adapter, never percentiles of the repository's
own distribution (spec D14). Tier 0 asks what state this repository is in,
not which file is worst inside it: a percentile rule always finds 5% of
files, reports nothing on a uniformly bad repository, and yields numbers
that cannot be compared across repositories or across E-44's before/after
delta.

Both size rules are STRUCTURAL. Splitting a file or a function is design
work, and E-44 must not pick it up as a mechanical PR.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from ...measurement import Measurement
from ...toolchain.adapters import ToolchainAdapter
from ..models import FixClass, SignalResult, TriageFinding

SIGNAL_ID = "outliers"
VERSION = 1

M_MAX_FILE_LOC = "max_file_loc_seen"
M_FUNCTION_LOC = "max_function_loc_seen"
M_DUP_RATIO = "duplicated_loc_ratio"

# Bounds on the duplication pass. Exceeding either makes the ratio
# not_collected rather than reporting a partial scan as if it covered the
# tree (spec D16).
MAX_FILES = 2000
MAX_LINES = 400_000

# Whole-line comments in the two syntaxes that cover every language we have
# an adapter for or plan one for. Deliberately crude: this normalizes for
# CLONE COMPARISON, not for parsing, and an inline trailing comment left in
# place simply makes two blocks compare unequal, which is the safe direction.
_COMMENT_LINE = re.compile(r"^\s*(?:#|//|/\*|\*)")


def normalized_lines(text: str) -> list[tuple[int, str]]:
    """(original line number, stripped text) for every line that carries
    content. Blank lines and whole-line comments are dropped; indentation is
    stripped, so a block that was merely re-indented still compares equal."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or _COMMENT_LINE.match(raw):
            continue
        out.append((lineno, line))
    return out


def clone_groups(blobs: Mapping[str, str],
                 window: int) -> list[list[tuple[str, int]]]:
    """Groups of identical `window`-line normalized blocks spanning two or
    more FILES, as [(path, first original line number), ...].

    The window IS the minimum clone length, so a hit is already a clone of at
    least `window` lines and no length-merging step is needed. What DOES need
    merging is overlap: a 40-line duplicate scanned with a 30-line window
    produces eleven consecutive hits, and reporting eleven findings for one
    clone makes the report unreadable. A window whose every hit is the
    one-position continuation of an already-reported group is the same clone.

    Candidates are ordered by position, not by hash, because the continuation
    check depends on having seen the predecessor first.

    Within-file repetition is not reported: a file that repeats itself is
    this signal's oversized_file finding, not a cross-file duplication one.
    """
    index: dict[str, list[tuple[str, int, int]]] = {}
    for path in sorted(blobs):
        lines = normalized_lines(blobs[path])
        for i in range(len(lines) - window + 1):
            chunk = "\n".join(text for _, text in lines[i:i + window])
            key = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            # (path, normalized index, original line number): the index drives
            # continuation, the line number is what a human is shown.
            index.setdefault(key, []).append((path, i, lines[i][0]))

    candidates: list[list[tuple[str, int, int]]] = []
    for key in sorted(index):
        hits = sorted(index[key])
        if len({path for path, _, _ in hits}) >= 2:
            candidates.append(hits)
    candidates.sort(key=lambda hits: hits[0][:2])

    reported: set[tuple[str, int]] = set()
    groups: list[list[tuple[str, int]]] = []
    for hits in candidates:
        continuation = all((path, i - 1) in reported for path, i, _ in hits)
        reported.update((path, i) for path, i, _ in hits)
        if not continuation:
            groups.append([(path, lineno) for path, _, lineno in hits])
    return groups


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def evaluate(blobs: Mapping[str, str],
             toolchain: ToolchainAdapter | None) -> SignalResult:
    """Size and duplication over source blobs the caller already filtered to
    the adapter's source extensions."""
    findings: list[TriageFinding] = []

    if toolchain is None:
        reason = "no toolchain marker resolved, so no size thresholds apply"
        file_metric = Measurement.not_collected(reason)
        fn_metric = Measurement.not_collected(reason)
    else:
        max_seen = 0
        for path in sorted(blobs):
            loc = len(blobs[path].splitlines())
            max_seen = max(max_seen, loc)
            if toolchain.max_file_loc and loc > toolchain.max_file_loc:
                findings.append(_finding(
                    "oversized_file", "medium",
                    f"{path} is {loc} lines, above the {toolchain.max_file_loc}"
                    f"-line limit for this stack. Splitting it is design work.",
                    FixClass.STRUCTURAL, path))
        file_metric = Measurement.measured(float(max_seen))

        max_fn = 0
        parsed_any = False
        for path in sorted(blobs):
            spans = toolchain.function_spans(blobs[path])
            if spans is None:
                continue
            parsed_any = True
            for name, start, end in spans:
                loc = end - start + 1
                max_fn = max(max_fn, loc)
                if toolchain.max_function_loc \
                        and loc > toolchain.max_function_loc:
                    findings.append(_finding(
                        "oversized_function", "medium",
                        f"{name}() in {path} is {loc} lines, above the "
                        f"{toolchain.max_function_loc}-line limit. Splitting "
                        f"it is design work.",
                        FixClass.STRUCTURAL, path, start))
        fn_metric = (
            Measurement.measured(float(max_fn)) if parsed_any
            else Measurement.not_collected(
                "this toolchain declares no function parser, so function "
                "length was not measured"))

    total_lines = sum(len(t.splitlines()) for t in blobs.values())
    window = toolchain.min_clone_loc if toolchain else 30
    if len(blobs) > MAX_FILES or total_lines > MAX_LINES:
        dup_metric = Measurement.not_collected(
            f"{len(blobs)} files / {total_lines} lines exceeds the "
            f"{MAX_FILES}/{MAX_LINES} duplication cap; a partial scan is not "
            f"a scan")
    else:
        groups = clone_groups(blobs, window)
        duplicated = len(groups) * window
        for group in groups:
            paths = sorted({path for path, _ in group})
            path, line = group[0]
            findings.append(_finding(
                "duplicated_block", "medium",
                f"A {window}-line block is identical across "
                f"{', '.join(paths)}. Deduplicating requires deciding where "
                f"the shared code belongs.",
                FixClass.JUDGEMENT, path, line))
        # An approximation, and deliberately the understating one: merged
        # groups are counted at one window each even when the clone is longer,
        # and total_lines counts raw lines including blanks. A duplication
        # ratio that reads low on a bad repo costs a nudge; one that reads
        # high on a clean repo costs the report's credibility.
        dup_metric = Measurement.measured(
            duplicated / total_lines if total_lines else 0.0)

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={M_MAX_FILE_LOC: file_metric,
                 M_FUNCTION_LOC: fn_metric,
                 M_DUP_RATIO: dup_metric})
