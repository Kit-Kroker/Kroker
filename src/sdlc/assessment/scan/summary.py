"""The scan phase's operator surface (spec section 8).

`sdlc assess` adds no verb; it gains counts. The not-collected list is the
line that matters: it is how an operator sees what the assessment did NOT
measure, which is FR-915's claim made visible at the surface rather than only
in the artifact.

Pure, and deliberately not a method on ScanResult: rendering is a surface
concern and the artifact is a contract shared with E-52's bundle.
"""

from __future__ import annotations

from ...measurement import CollectionState
from .merge import CANDIDATE_BAND
from .models import Confidence, ScanResult, SignalFamily


def render_scan_summary(scan: ScanResult) -> str:
    lines: list[str] = ["scan:"]

    counts = {c: sum(1 for cand in scan.candidates if cand.confidence is c) for c in Confidence}
    lines.append(
        f"  candidates: {len(scan.candidates)} "
        f"(high {counts[Confidence.HIGH]}, "
        f"medium {counts[Confidence.MEDIUM]}, "
        f"low {counts[Confidence.LOW]})"
    )

    low, high = CANDIDATE_BAND
    if scan.candidates and not low <= len(scan.candidates) <= high:
        # ADVISORY, never a gate (D11). BrownKit hard-gates here; its band
        # comes from enterprise Java monoliths, and a 40-file Next.js
        # application legitimately has four capabilities. A binding version
        # belongs in E-51's CheckResults.
        lines.append(
            f"  advisory: {len(scan.candidates)} candidates is outside "
            f"BrownKit's {low}-{high} band. Not a gate -- small repositories "
            f"legitimately have few capabilities (D11)."
        )

    for family in SignalFamily:
        rows = [r for r in scan.signals if r.family is family]
        measured = sum(1 for r in rows if r.collected.state is CollectionState.MEASURED)
        lines.append(f"  {family.value}: {measured}/{len(rows)} signals collected")

    inherited = [(r, p) for r in scan.signals if (p := r.producer) is not None]
    if inherited:
        lines.append("  inherited (cited, never copied):")
        for row, producer in inherited:
            lines.append(
                f"    {row.signal.value} <- {producer.producer} "
                f"v{producer.version} "
                f"({len(producer.finding_ids)} finding(s))"
            )

    by_category: dict[str, int] = {}
    for observation in scan.security:
        by_category[observation.category] = by_category.get(observation.category, 0) + 1
    if by_category:
        lines.append("  security observations:")
        for category in sorted(by_category):
            lines.append(f"    {category}: {by_category[category]}")

    if scan.tests:
        levels: dict[str, int] = {}
        for record in scan.tests:
            levels[record.level.value] = levels.get(record.level.value, 0) + 1
        mapped = sum(1 for r in scan.tests if r.mapping_rule != "unmapped")
        lines.append(
            f"  tests: {len(scan.tests)} file(s) "
            f"({', '.join(f'{k} {v}' for k, v in sorted(levels.items()))}); "
            f"{mapped} mapped to a subject"
        )

    if scan.coverage:
        # BrownKit's own rule: a coverage number is meaningless without its
        # source, because a proxy and a measurement read the same.
        source = scan.coverage[0].source
        tool = scan.coverage[0].tool
        values = [
            v
            for r in scan.coverage
            if r.covered.state is CollectionState.MEASURED and (v := r.covered.value) is not None
        ]
        headline = f"{sum(values) / len(values):.1f}%" if values else "no measured record"
        lines.append(
            f"  coverage: {source}{f' ({tool})' if tool else ''} "
            f"{headline} over {len(scan.coverage)} record(s)"
        )

    drifted = [e.name for e in scan.environments if e.drifted]
    if drifted:
        lines.append(
            f"  environment drift: {', '.join(sorted(drifted))} (declared on one side only)"
        )

    gaps = [
        (r.signal.value, key, m)
        for r in scan.signals
        for key, m in sorted(r.categories.items())
        if m.state is not CollectionState.MEASURED
    ]
    if gaps:
        lines.append(f"  not collected ({len(gaps)} categories):")
        for signal, key, m in gaps:
            lines.append(f"    {signal}.{key}: {m.reason}")
    else:
        lines.append("  not collected: none")

    return "\n".join(lines)
