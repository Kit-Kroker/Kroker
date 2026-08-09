"""The registry is the one place that says which signals exist. It must not
be able to drift from the modules it names."""
from sdlc.triage import activities as triage_activities
from sdlc.triage.registry import SIGNALS, SignalSpec
from sdlc.triage.signals import (
    baseline, build_probe, dependencies, misconfig, outliers, scaffold,
    secrets,
)

_MODULES = {"baseline": baseline, "secrets": secrets,
            "build_probe": build_probe, "dependencies": dependencies,
            "scaffold": scaffold, "misconfig": misconfig,
            "outliers": outliers}


def test_registry_covers_exactly_the_three_signals():
    assert set(SIGNALS) == set(_MODULES)


def test_each_spec_matches_its_module_id_and_version():
    for signal_id, spec in SIGNALS.items():
        module = _MODULES[signal_id]
        assert spec.id == module.SIGNAL_ID
        assert spec.version == module.VERSION


def test_each_spec_names_a_real_activity_function():
    for spec in SIGNALS.values():
        fn = getattr(triage_activities, spec.activity, None)
        assert callable(fn), f"{spec.activity} is not defined"


def test_every_registered_signal_is_registered_on_the_worker():
    from sdlc import worker
    import inspect

    source = inspect.getsource(worker)
    for spec in SIGNALS.values():
        assert spec.activity in source, (
            f"{spec.activity} is not registered in worker.py")


def test_all_seven_signal_families_are_registered():
    # FR-902 names seven families. E-41 shipped three; E-41a-d added four.
    from sdlc.triage.registry import SIGNALS
    assert set(SIGNALS) == {"baseline", "secrets", "build_probe",
                            "dependencies", "scaffold", "misconfig",
                            "outliers"}


def test_every_registered_activity_is_registered_on_the_worker():
    import sdlc.triage.activities as acts
    from sdlc.triage.registry import SIGNALS
    for spec in SIGNALS.values():
        assert hasattr(acts, spec.activity), spec.activity


def test_baseline_and_secrets_carry_their_bumped_versions():
    from sdlc.triage.registry import SIGNALS
    assert SIGNALS["baseline"].version == 2      # dropped M_STRUCTURE (D12)
    assert SIGNALS["secrets"].version == 3       # E-44 D3: finding `key`
