"""RD5: FR-916's five control families over the three the scan collects.

Pure by design -- see the package docstring in models.py.
"""

from __future__ import annotations

from ...measurement import Measurement
from ..discover.map import Capability
from ..scan.models import EvidenceRef
from .models import ControlCoverage, ControlFamily, ControlState
from .rules import CONTROL_SOURCES, NO_SOURCE_REASON


def controls(
    cap: Capability, *, collected_categories: frozenset[str]
) -> tuple[ControlCoverage, ...]:
    """Always five rows, in ControlFamily declaration order.

    `collected_categories` is the set of scan categories that reported. A
    family whose categories did not report is not_collected -- a signal that
    did not run is not a clean control.
    """
    out: list[ControlCoverage] = []
    for family in ControlFamily:
        sources = CONTROL_SOURCES[family]
        if not sources:
            out.append(
                ControlCoverage(
                    family=family,
                    rule="no_source",
                    collected=Measurement.not_collected(NO_SOURCE_REASON[family]),
                )
            )
            continue

        missing = tuple(c for c in sources if c not in collected_categories)
        if missing:
            out.append(
                ControlCoverage(
                    family=family,
                    rule="upstream_not_collected",
                    collected=Measurement.not_collected(
                        f"{family.value}: category/categories "
                        f"{list(missing)} did not report, and a signal that did "
                        f"not run is not a clean control"
                    ),
                )
            )
            continue

        hits = tuple(
            sorted(
                (o for o in cap.security if o.category in sources),
                key=lambda o: (o.signal.value, o.rule, o.path, o.line or 0),
            )
        )
        # An observation IS a weakness: its presence means the control is not
        # doing its job for this capability.
        state = ControlState.ABSENT if hits else ControlState.PRESENT
        out.append(
            ControlCoverage(
                family=family,
                state=state,
                collected=Measurement.measured(1.0),
                evidence=tuple(
                    EvidenceRef(path=o.path, lines=str(o.line) if o.line else "") for o in hits
                ),
                rule="observations_in_family",
            )
        )
    return tuple(out)
