"""D2/D7: the Tier 0 read-through.

Five scan signals inherit a base from RepoTriage. This module derives that
base and NOTHING else: the computed halves belong to the activities, and the
workflow unions the two.

Pure -- and deliberately so, because it must run in workflow code. Triage
findings are not a function of the tree (build_probe executes the repository's
own code and can time out), so this half must never enter a tree-keyed memo
(D7). Re-deriving it every run is free.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ...measurement import CollectionState, Measurement
from ...triage.models import RepoTriage, SignalResult, finding_identity
from .models import (
    C_AUTHN_AUTHZ,
    C_CI_PRESENT,
    C_CREDENTIAL_STORAGE,
    C_DIRECT_DEPS,
    C_FRAMEWORK_DEFAULTS,
    C_TESTS_PRESENT,
    InheritedProducer,
    ScanSignalId,
)

# Which triage rules feed each inherited category. Declared rather than
# inferred from the signal name: `misconfig` feeds BOTH SS1's authn_authz
# (unauthenticated_app) and SS3's framework_defaults (everything else), so a
# whole-signal tally would double-count one signal into two categories.
_AUTHZ_RULES = ("unauthenticated_app",)
_CI_RULES = ("no_ci",)


def _by_signal(triage: RepoTriage) -> dict[str, SignalResult]:
    return {s.signal: s for s in triage.signals}


def _absent(signal: str) -> Measurement:
    return Measurement.not_collected(f"triage signal {signal!r} is not present in this triage")


def _unavailable(sig: SignalResult) -> Measurement | None:
    """The category's Measurement when the producing signal did not collect,
    or None when it did. Propagates the reason so the assessment says WHY."""
    if sig.collected.state is CollectionState.MEASURED:
        return None
    return Measurement.not_collected(
        f"triage signal {sig.signal!r} reported {sig.collected.state.value}: {sig.collected.reason}"
    )


def _tally(sig: SignalResult, rules: tuple[str, ...] | None = None) -> Measurement:
    """Count of matching findings, or not_collected when the signal did not
    collect. `rules=None` counts every finding."""
    if (unavailable := _unavailable(sig)) is not None:
        return unavailable
    if rules is None:
        return Measurement.measured(float(len(sig.findings)))
    return Measurement.measured(float(sum(1 for f in sig.findings if f.rule in rules)))


def _absence_of(sig: SignalResult, rules: tuple[str, ...]) -> Measurement:
    """1.0 when none of `rules` fired, else 0.0.

    baseline reports a finding when CI is MISSING, so ci_present is the
    INVERSE of its tally. This inversion is why the mapping is a declared
    function per category rather than a generic finding count.
    """
    if (unavailable := _unavailable(sig)) is not None:
        return unavailable
    fired = any(f.rule in rules for f in sig.findings)
    return Measurement.measured(0.0 if fired else 1.0)


def _metric(sig: SignalResult, key: str) -> Measurement:
    """A metric the producing signal already computed, passed through
    unchanged -- including its own not_collected state."""
    if (unavailable := _unavailable(sig)) is not None:
        return unavailable
    return sig.metrics.get(
        key, Measurement.not_collected(f"triage signal {sig.signal!r} reported no {key!r} metric")
    )


def _producer(sig: SignalResult, rules: tuple[str, ...] | None = None) -> InheritedProducer:
    """Cite the producing signal and the findings this row rests on.

    version is PINNED, so a triage version bump changes the assessment
    visibly rather than silently.
    """
    cited = [f for f in sig.findings if rules is None or f.rule in rules]
    return InheritedProducer(
        producer=f"triage:{sig.signal}",
        version=sig.version,
        finding_ids=[finding_identity(f) for f in cited],
    )


class InheritedHalf(BaseModel):
    """One signal's inherited contribution: who produced it and which
    categories it answers. The workflow unions this with the activity's
    computed half (D7)."""

    producer: InheritedProducer
    categories: dict[str, Measurement] = Field(default_factory=dict)


def _merge_producers(*producers: InheritedProducer) -> InheritedProducer:
    """SS1 inherits from two triage signals. The row carries one producer, so
    the two are folded with a composite name and the union of their citations;
    `version` becomes the max, which is the coarse-but-honest choice -- a bump
    in either producer moves it."""
    names = ",".join(sorted(p.producer for p in producers))
    ids: list[str] = []
    for p in producers:
        ids.extend(p.finding_ids)
    return InheritedProducer(
        producer=names, version=max(p.version for p in producers), finding_ids=ids
    )


def inherited_halves(triage: RepoTriage) -> dict[ScanSignalId, InheritedHalf]:
    """The inherited half of every signal that has one (D2).

    Five signals, each mapped explicitly. A generic "same-named signal" rule
    was rejected: misconfig feeds two different scan signals with different
    rule subsets, and baseline feeds one category as a metric and another as
    the ABSENCE of a finding.
    """
    found = _by_signal(triage)

    def sig(name: str) -> SignalResult | None:
        return found.get(name)

    out: dict[ScanSignalId, InheritedHalf] = {}

    # SS1 -- credential storage from secrets, app-level auth from misconfig.
    secrets, misconfig = sig("secrets"), sig("misconfig")
    out[ScanSignalId.SS1] = InheritedHalf(
        producer=_merge_producers(
            _producer(secrets)
            if secrets
            else InheritedProducer(producer="triage:secrets", version=0),
            _producer(misconfig, _AUTHZ_RULES)
            if misconfig
            else InheritedProducer(producer="triage:misconfig", version=0),
        ),
        categories={
            C_CREDENTIAL_STORAGE: (_tally(secrets) if secrets else _absent("secrets")),
            C_AUTHN_AUTHZ: (_tally(misconfig, _AUTHZ_RULES) if misconfig else _absent("misconfig")),
        },
    )

    # SS2 -- purely inherited; D12 cut transitive enumeration.
    deps = sig("dependencies")
    out[ScanSignalId.SS2] = InheritedHalf(
        producer=(
            _producer(deps)
            if deps
            else InheritedProducer(producer="triage:dependencies", version=0)
        ),
        categories={C_DIRECT_DEPS: (_tally(deps) if deps else _absent("dependencies"))},
    )

    # SS3 -- framework defaults: every misconfig finding (an unauthenticated
    # app is one unsafe framework default, so it is counted here even though
    # SS1's authn_authz counts it too -- cited twice, copied nowhere).
    out[ScanSignalId.SS3] = InheritedHalf(
        producer=(
            _producer(misconfig)
            if misconfig
            else InheritedProducer(producer="triage:misconfig", version=0)
        ),
        categories={
            C_FRAMEWORK_DEFAULTS: (_tally(misconfig, None) if misconfig else _absent("misconfig")),
        },
    )

    # QS1 -- the test COUNT, which baseline carries as a metric.
    baseline = sig("baseline")
    out[ScanSignalId.QS1] = InheritedHalf(
        producer=(
            _producer(baseline)
            if baseline
            else InheritedProducer(producer="triage:baseline", version=0)
        ),
        categories={
            C_TESTS_PRESENT: (
                _metric(baseline, "tests_present") if baseline else _absent("baseline")
            ),
        },
    )

    # QS4 -- ci_present is the ABSENCE of baseline's no_ci finding.
    out[ScanSignalId.QS4] = InheritedHalf(
        producer=(
            _producer(baseline, _CI_RULES)
            if baseline
            else InheritedProducer(producer="triage:baseline", version=0)
        ),
        categories={
            C_CI_PRESENT: (_absence_of(baseline, _CI_RULES) if baseline else _absent("baseline")),
        },
    )

    return out
