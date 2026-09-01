"""Which probes may run, per project mode. Pure -- no model, no I/O.

MAC's supervisor holds no domain database and handles only ambiguity that
general reasoning settles; its experts hold the schemas. Our split is the
same, drawn along SWE-RPG's taxonomy instead of MAC's five booking domains.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models import ClarificationDimension as CD
from ..models import ProjectMode

# The supervisor's two: answerable without reading any code.
SUPERVISOR_DIMENSIONS: tuple[CD, ...] = (CD.FUNCTIONAL_INTENT, CD.BUSINESS_SEMANTICS)

# The probes' four, in canonical order. All four are map-grounded in
# brownfield; C4 and C6 survive greenfield because a contract or an invariant
# can be underspecified before any code exists.
PROBE_DIMENSIONS: tuple[CD, ...] = (
    CD.TECHNICAL_CONTEXT,
    CD.INTERFACE_SPEC,
    CD.CODE_STRUCTURE,
    CD.DATA_SEMANTICS,
)

# E-85 D5: with no tree, these two could only ask which architecture or which
# conventions we SHOULD adopt -- authoring a decision that belongs to the
# architect, not resolving an ambiguity. Same boundary agents/discover polices.
_GREENFIELD_SKIP: frozenset[CD] = frozenset({CD.TECHNICAL_CONTEXT, CD.CODE_STRUCTURE})


def permitted_dimensions(mode: ProjectMode) -> tuple[CD, ...]:
    """The probe dimensions this project mode allows at all."""
    if mode is ProjectMode.GREENFIELD:
        return tuple(d for d in PROBE_DIMENSIONS if d not in _GREENFIELD_SKIP)
    return PROBE_DIMENSIONS


def live_dimensions(requested: Iterable[CD], mode: ProjectMode) -> tuple[CD, ...]:
    """The supervisor's request, narrowed by what the mode permits.

    Returned in canonical C1..C6 order regardless of the order asked for, so
    a probe burst is deterministic and a replay cannot reorder it.
    """
    asked = set(requested)
    return tuple(d for d in permitted_dimensions(mode) if d in asked)


def grounded_dimensions(mode: ProjectMode) -> frozenset[CD]:
    """Dimensions whose questions MUST cite repo evidence to survive merge.

    Brownfield probes read the codebase map, so a question that cannot point
    at a path or symbol is speculation (spec §13). Greenfield probes have no
    tree to cite, so nothing is required of them.
    """
    if mode is ProjectMode.GREENFIELD:
        return frozenset()
    return frozenset(PROBE_DIMENSIONS)
