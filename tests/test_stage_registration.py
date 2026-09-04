from typing import Any


def test_stage_modules_is_explicit_and_every_entry_exports_activities():
    from sdlc import stages

    assert isinstance(stages.STAGE_MODULES, tuple)
    for module in stages.STAGE_MODULES:
        assert hasattr(module, "ACTIVITIES"), module.__name__
        assert isinstance(module.ACTIVITIES, list)


def test_registered_activity_names_are_unique():
    from sdlc import stages

    stage_names = [
        a.__temporal_activity_definition.name for m in stages.STAGE_MODULES for a in m.ACTIVITIES
    ]
    assert len(stage_names) == len(set(stage_names)), (
        f"duplicate: {[n for n in stage_names if stage_names.count(n) > 1]}"
    )

    # Advisor3 recommendation: assert over the worker's full registration set
    # to guard against collisions between legacy list and STAGE_MODULES.
    from sdlc.worker import get_worker_activities

    def activity_name(act: Any) -> str:
        defn = getattr(act, "__temporal_activity_definition", None)
        if defn is not None:
            return defn.name
        return getattr(act, "__name__", str(act))

    all_names = [activity_name(a) for a in get_worker_activities()]
    assert len(all_names) == len(set(all_names)), (
        f"duplicate in worker activities: {[n for n in all_names if all_names.count(n) > 1]}"
    )
