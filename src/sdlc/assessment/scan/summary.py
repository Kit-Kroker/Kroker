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

    counts = {c: sum(1 for cand in scan.candidates if cand.confidence is c)
              for c in Confidence}
    lines.append(
        f"  candidates: {len(scan.candidates)} "
        f"(high {counts[Confidence.HIGH]}, "
        f"medium {counts[Confidence.MEDIUM]}, "
        f"low {counts[Confidence.LOW]})")

    low, high = CANDIDATE_BAND
    if scan.candidates and not low <= len(scan.candidates) <= high:
        # ADVISORY, never a gate (D11). BrownKit hard-gates here; its band
        # comes from enterprise Java monoliths, and a 40-file Next.js
        # application legitimately has four capabilities. A binding version
        # belongs in E-51's CheckResults.
        lines.append(
            f"  advisory: {len(scan.candidates)} candidates is outside "
            f"BrownKit's {low}-{high} band. Not a gate -- small repositories "
            f"legitimately have few capabilities (D11).")

    for family in SignalFamily:
        rows = [r for r in scan.signals if r.family is family]
        measured = sum(1 for r in rows
                       if r.collected.state is CollectionState.MEASURED)
        lines.append(f"  {family.value}: {measured}/{len(rows)} signals "
                     f"collected")

    inherited = [r for r in scan.signals if r.producer is not None]
    if inherited:
        lines.append("  inherited (cited, never copied):")
        for row in inherited:
            lines.append(
                f"    {row.signal.value} <- {row.producer.producer} "
                f"v{row.producer.version} "
                f"({len(row.producer.finding_ids)} finding(s))")

    gaps = [(r.signal.value, key, m)
            for r in scan.signals
            for key, m in sorted(r.categories.items())
            if m.state is not CollectionState.MEASURED]
    if gaps:
        lines.append(f"  not collected ({len(gaps)} categories):")
        for signal, key, m in gaps:
            lines.append(f"    {signal}.{key}: {m.reason}")
    else:
        lines.append("  not collected: none")

    return "\n".join(lines)
