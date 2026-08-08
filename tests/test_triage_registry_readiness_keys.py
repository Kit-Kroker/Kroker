"""E-42 D8a: which readiness dimensions a signal owes is DECLARED, so a
skipped or failed signal can report not_collected for exactly those keys
instead of leaving them unreported."""
from __future__ import annotations

from sdlc.triage.models import (
    M_BUILDABLE, M_RUNNABLE, M_STRUCTURE, M_TESTS_PRESENT, READINESS_KEYS,
)
from sdlc.triage.registry import SIGNALS


def test_build_probe_owns_buildable_and_runnable():
    assert SIGNALS["build_probe"].readiness_keys == (M_BUILDABLE, M_RUNNABLE)


def test_baseline_owns_tests_present():
    assert SIGNALS["baseline"].readiness_keys == (M_TESTS_PRESENT,)


def test_scaffold_owns_structure_discernible():
    """E-41b moved this dimension off baseline; the declaration must agree."""
    assert SIGNALS["scaffold"].readiness_keys == (M_STRUCTURE,)


def test_signals_owning_nothing_declare_nothing():
    for sid in ("secrets", "dependencies", "misconfig", "outliers"):
        assert SIGNALS[sid].readiness_keys == (), sid


def test_every_readiness_key_has_exactly_one_owner():
    """FR-902's one-implementation rule, now declarative. compute_readiness
    still detects a duplicate at runtime -- that is the backstop against this
    declaration drifting, not the only statement of the rule."""
    owners: dict[str, str] = {}
    for spec in SIGNALS.values():
        for key in spec.readiness_keys:
            assert key not in owners, (
                f"{key} claimed by {owners.get(key)} and {spec.id}")
            owners[key] = spec.id
    assert set(owners) == set(READINESS_KEYS)


def test_the_declaration_matches_what_the_signals_actually_report():
    """The drift guard. A static declaration that no test compares against
    real output is a second registry waiting to disagree with the first --
    which is the whole failure mode E-42 D2 exists to avoid.

    The three owning signals expose PURE evaluate/interpret functions, so this
    needs no repository and no Temporal: call them and read the metric keys.
    """
    from sdlc.triage.signals import baseline, build_probe, scaffold

    probe = build_probe.interpret(False, None, None, None, None)
    assert set(probe.metrics) == set(SIGNALS["build_probe"].readiness_keys)

    base = baseline.evaluate([], "", None)
    assert (set(base.metrics) & set(READINESS_KEYS)
            == set(SIGNALS["baseline"].readiness_keys))

    scaf = scaffold.evaluate([], {}, None, None)
    assert (set(scaf.metrics) & set(READINESS_KEYS)
            == set(SIGNALS["scaffold"].readiness_keys))
