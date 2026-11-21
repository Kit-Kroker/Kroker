"""FR-918 (E-51): the per-phase exits -- FD4's small seed list, finalized.

Each exit is a CheckResult under an `exit:<phase>:` wire name (FD10, never
renamed): scan -- thirteen signal rows report, candidates non-empty;
discover -- the identity lock held, every file bucketed, ownership
resolved-or-surfaced; assess -- the risk map covers the locked set, the
judgment honest. report/generate are unbuilt phases (E-52): their exits are
owed rows, never CheckResults, because `owed` is not CheckResult-shaped --
that is why they live in `owed` (FD14). There are no `exit:finish:*` rows:
finish's own exits ARE the 14 criteria plus the walk (design section 5).

FD11's three states apply to exits verbatim: a producer phase absent is an
owed row in the pinned format naming the phase and its reason; a measured
producer with a not_collected sub-artifact (a signal row, the attribution
or ownership report) is an evaluated fail carrying that reason; measured
inputs are pass/fail by predicate. FD3 holds throughout: an absent producer
never reads as a failure.

Pure by design -- the Pydantic models it walks, `...gate`, `...measurement`
and this package's own modules only. This module must never import
assessment/models.py, activities.py, or temporalio, exactly as checks.py
must not.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...gate import CheckClass, CheckResult, build_check
from ...measurement import CollectionState, Measurement
from ..discover.map import CapabilityMap
from ..discover.models import FileBucket
from ..risk.models import UnifiedRiskMap
from ..scan.models import ScanResult

# Wire names (FD10): never renamed once landed -- the GUARD_PATCH_ID rule.
SCAN_SIGNALS = "exit:scan:signals_measured"
SCAN_CANDIDATES = "exit:scan:candidates_present"
DISCOVER_LOCK = "exit:discover:identity_lock_held"
DISCOVER_ORPHANS = "exit:discover:orphans_classified"
DISCOVER_OWNERSHIP = "exit:discover:ownership_resolved"
ASSESS_COVERAGE = "exit:assess:covers_locked_set"
ASSESS_JUDGMENT = "exit:assess:judgment_honest"

# FD9's classification table: the documented shortfalls (an honest empty
# candidate set, ownership surfaced instead of resolved, a recorded judgment
# mode) are ADVISORY; structural identity and completeness are ABSOLUTE.
_ADVISORY: frozenset[str] = frozenset({SCAN_CANDIDATES, DISCOVER_OWNERSHIP, ASSESS_JUDGMENT})

# The unbuilt phases (E-52), pinned verbatim -- E-52 inherits the wording,
# as c13's classification was declared for it in checks.py.
E52_OWED: tuple[str, ...] = (
    "exit:generate:seeds_emitted: not collected (E-52)",
    "exit:report:reports_emitted: not collected (E-52)",
)

DETAIL_BUDGET = 300


def _owed(name: str, phase: str, state: Measurement) -> str:
    """The pinned owed format (FD11 rule 1), shared with checks.py: the
    phase's not_collected reason verbatim, never a paraphrase."""
    return f"{name}: not collected ({phase}: {state.reason})"


def _check(name: str, passed: bool, detail: str = "") -> CheckResult:
    """build_check at the exit's declared classification (FD9)."""
    return build_check(
        name, passed, CheckClass.ADVISORY if name in _ADVISORY else CheckClass.ABSOLUTE, detail
    )


def _bounded(items: Iterable[str]) -> str:
    """Joined, sorted, truncated at the detail budget (checks.py's rule): a
    census over many named items must stay one readable line."""
    joined = ", ".join(sorted(items))
    if len(joined) <= DETAIL_BUDGET:
        return joined
    return joined[: DETAIL_BUDGET - 3] + "..."


def _scan_exits(scan: ScanResult) -> tuple[CheckResult, ...]:
    """`exit:scan:signals_measured` (ABSOLUTE): all thirteen signal rows
    report -- a row whose collected state is not MEASURED did not, and its
    own reason travels in the detail (FD11 rule 2). ScanResult guarantees
    the whole ordered set, so the lookup is total.
    `exit:scan:candidates_present` (ADVISORY): an honest empty repository
    emits nothing (scan D11's ruling, c10's precedent)."""
    silent = [
        f"{row.signal.value} {row.collected.state.value} ({row.collected.reason})"
        for row in scan.signals
        if row.collected.state is not CollectionState.MEASURED
    ]
    signals = _check(
        SCAN_SIGNALS,
        not silent,
        "" if not silent else f"signal rows did not report: {_bounded(silent)}",
    )
    candidates = _check(
        SCAN_CANDIDATES,
        bool(scan.candidates),
        "" if scan.candidates else "no candidates emitted",
    )
    return signals, candidates


def _discover_exits(discover: CapabilityMap) -> tuple[CheckResult, ...]:
    """`exit:discover:identity_lock_held` (ABSOLUTE): every capability in the
    map carries a non-empty bc_id and no two share one -- the lock defect
    DD9 refuses to admit, audited here belt-and-suspenders over the final
    artifact (the xref walk's precedent).
    `exit:discover:orphans_classified` (ABSOLUTE): every file bucket counted.
    An absent attribution report is FD11 rule 2's evaluated fail; a present
    one's counts are schema-derived from its files, so presence is the live
    question.
    `exit:discover:ownership_resolved` (ADVISORY): resolved-or-surfaced --
    every entity ended OWNED or in one of the three surfaced outcomes, which
    the outcome enum makes structural, so the live question is whether the
    ownership map happened at all (absent, or not_collected)."""
    ids = [c.bc_id for c in discover.capabilities]
    duplicated = sorted({bc for bc in ids if ids.count(bc) > 1})
    empty = any(not bc.strip() for bc in ids)
    defects = [*duplicated, *(["empty bc_id"] if empty else [])]
    lock = _check(
        DISCOVER_LOCK,
        not defects,
        "" if not defects else f"identity lock defect: {_bounded(defects)}",
    )
    attribution = discover.attribution
    if attribution is None:
        orphans = _check(DISCOVER_ORPHANS, False, "attribution report absent")
    else:
        missing = [b.value for b in FileBucket if b not in attribution.counts]
        orphans = _check(
            DISCOVER_ORPHANS,
            not missing,
            "" if not missing else f"buckets not counted: {_bounded(missing)}",
        )
    ownership = discover.ownership
    if ownership is None:
        owned = _check(DISCOVER_OWNERSHIP, False, "ownership report absent")
    elif ownership.collected.state is not CollectionState.MEASURED:
        owned = _check(
            DISCOVER_OWNERSHIP,
            False,
            f"ownership not collected ({ownership.collected.reason})",
        )
    else:
        owned = _check(DISCOVER_OWNERSHIP, True)
    return lock, orphans, owned


def _covers_locked_set(discover: CapabilityMap, risk: UnifiedRiskMap) -> CheckResult:
    """`exit:assess:covers_locked_set` (ABSOLUTE): the risk map's rows cover
    exactly the identity lock's set -- c03's comparison shape, evaluated as
    the phase's own exit."""
    locked = {c.bc_id for c in discover.capabilities}
    got = {c.bc_id for c in risk.capabilities}
    missing = sorted(locked - got)
    extra = sorted(got - locked)
    parts = []
    if missing:
        parts.append(f"missing {missing}")
    if extra:
        parts.append(f"unexpected {extra}")
    return _check(
        ASSESS_COVERAGE,
        not parts,
        "" if not parts else f"locked-set mismatch: {'; '.join(parts)}",
    )


def _judgment_honest(risk: UnifiedRiskMap) -> CheckResult:
    """`exit:assess:judgment_honest` (ADVISORY): the judgment MEASURED, or
    degraded carrying its own recorded reason (RD7's baseline-only-vs-
    degraded distinction). Measurement enforces a reason on every
    non-measured state; the guard keeps the exit honest if that ever
    loosens."""
    judgment = risk.judgment
    honest = judgment.state is CollectionState.MEASURED or bool(judgment.reason.strip())
    return _check(
        ASSESS_JUDGMENT,
        honest,
        "" if honest else f"judgment {judgment.state.value} without a recorded reason",
    )


def evaluate_exits(
    *,
    scan: ScanResult | None,
    scan_state: Measurement,
    discover: CapabilityMap | None,
    discover_state: Measurement,
    risk: UnifiedRiskMap | None,
    risk_state: Measurement,
) -> tuple[tuple[CheckResult, ...], tuple[str, ...]]:
    """The per-phase exits: (evaluated checks, owed rows), both sorted by
    name so the caller can slot them straight into FinishReport (NFR-10).

    FD11 rule 1: a phase whose state is not MEASURED makes its exits owed
    rows in the pinned format -- never a pass, never a fail (FD3).
    `exit:assess:covers_locked_set` reads both phases and owes the records
    side first -- without discover's locked set the comparison is undefined,
    the same precedence xref_domains owes in. report and generate are owed
    to E-52 on every run (FD14).
    """
    scan_ok = scan_state.state is CollectionState.MEASURED
    discover_ok = discover_state.state is CollectionState.MEASURED
    risk_ok = risk_state.state is CollectionState.MEASURED
    checks: list[CheckResult] = []
    owed: list[str] = list(E52_OWED)

    if scan_ok:
        assert scan is not None  # measured producers carry their artifact
        checks.extend(_scan_exits(scan))
    else:
        owed.append(_owed(SCAN_SIGNALS, "scan", scan_state))
        owed.append(_owed(SCAN_CANDIDATES, "scan", scan_state))

    if discover_ok:
        assert discover is not None  # measured producers carry their artifact
        checks.extend(_discover_exits(discover))
    else:
        owed.append(_owed(DISCOVER_LOCK, "discover", discover_state))
        owed.append(_owed(DISCOVER_ORPHANS, "discover", discover_state))
        owed.append(_owed(DISCOVER_OWNERSHIP, "discover", discover_state))

    if not risk_ok:
        owed.append(_owed(ASSESS_COVERAGE, "risk", risk_state))
        owed.append(_owed(ASSESS_JUDGMENT, "risk", risk_state))
    elif not discover_ok:
        owed.append(_owed(ASSESS_COVERAGE, "discover", discover_state))
        assert risk is not None
        checks.append(_judgment_honest(risk))  # lives entirely on risk
    else:
        assert risk is not None and discover is not None
        checks.extend((_covers_locked_set(discover, risk), _judgment_honest(risk)))

    return tuple(sorted(checks, key=lambda c: c.name)), tuple(sorted(owed))
