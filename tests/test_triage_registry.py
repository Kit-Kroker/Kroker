"""The registry is the one place that says which signals exist. It must not
be able to drift from the modules it names."""
from sdlc.triage import activities as triage_activities
from sdlc.triage.registry import SIGNALS, SignalSpec
from sdlc.triage.signals import (
    baseline, build_probe, dependencies, scaffold, secrets,
)

_MODULES = {"baseline": baseline, "secrets": secrets,
            "build_probe": build_probe, "dependencies": dependencies,
            "scaffold": scaffold}


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
