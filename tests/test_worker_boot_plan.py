"""Boot-plan contract for the two worker pools (024 T006; R5, data-model truth table).

RED until T007 adds ``pools.PoolBootPlan`` / ``pool_boot_plan`` / ``boot_plan_from_env``
and ``worker.core_activities`` / ``worker.harness_activities``. ``sdlc.pools`` and
``sdlc.worker`` are imported inside each test so each case fails on its own missing
attribute rather than erroring at collection.

Refusal messages must name the variable and the fix (contracts/worker-boot.md G-2); the
tests pin the variable name, never the full sentence.
"""

from __future__ import annotations

import dataclasses
import logging
import warnings
from types import ModuleType
from typing import Any

import pytest

Q = "pools-q"


def _pools() -> ModuleType:
    import sdlc.pools

    return sdlc.pools


def _plan(mode: str, queue: str | None, cap: int | None) -> Any:
    pools = _pools()
    return pools.pool_boot_plan(pools.PoolMode(mode), queue, cap)


def _expected(
    *,
    core: bool,
    harness: bool,
    janitor: bool,
    cap: int | None,
    queue: str | None,
) -> Any:
    return _pools().PoolBootPlan(
        core_worker=core, harness_worker=harness, janitor=janitor, cap=cap, queue=queue
    )


# --------------------------------------------------------------- the dataclass


def test_plan_is_a_frozen_dataclass_with_the_documented_fields() -> None:
    plan_cls = _pools().PoolBootPlan
    assert dataclasses.is_dataclass(plan_cls)
    assert {f.name for f in dataclasses.fields(plan_cls)} == {
        "core_worker",
        "harness_worker",
        "janitor",
        "cap",
        "queue",
    }
    plan = _plan("all", None, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.janitor = False  # type: ignore[misc]


# ------------------------------------------------------- truth table: accepted rows


@pytest.mark.parametrize(
    ("mode", "queue", "cap", "want"),
    [
        # all, no queue, no cap -> today, exactly
        ("all", None, None, dict(core=True, harness=False, janitor=True, cap=None, queue=None)),
        # all, queue, cap any
        ("all", Q, None, dict(core=True, harness=True, janitor=True, cap=None, queue=Q)),
        ("all", Q, 2, dict(core=True, harness=True, janitor=True, cap=2, queue=Q)),
        # core, queue, cap ignored (with a warning, see its own test)
        ("core", Q, None, dict(core=True, harness=False, janitor=False, cap=None, queue=Q)),
        ("core", Q, 2, dict(core=True, harness=False, janitor=False, cap=None, queue=Q)),
        # harness, queue, cap passed through
        ("harness", Q, None, dict(core=False, harness=True, janitor=True, cap=None, queue=Q)),
        ("harness", Q, 2, dict(core=False, harness=True, janitor=True, cap=2, queue=Q)),
    ],
    ids=[
        "all-noqueue-nocap",
        "all-queue-nocap",
        "all-queue-cap2",
        "core-queue-nocap",
        "core-queue-cap2-ignored",
        "harness-queue-nocap",
        "harness-queue-cap2",
    ],
)
def test_accepted_rows(mode: str, queue: str | None, cap: int | None, want: dict[str, Any]) -> None:
    got = _plan(mode, queue, cap)
    exp = _expected(**want)
    # Field-wise first so a failure names the field, then the whole value.
    for name in ("core_worker", "harness_worker", "janitor", "queue"):
        assert getattr(got, name) == getattr(exp, name), name
    assert got == exp


def test_core_ignores_the_cap_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        plan = _plan("core", Q, 2)

    assert plan.harness_worker is False
    assert plan.cap is None
    texts = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    texts += [str(w.message) for w in caught]
    assert any("cap" in t.lower() for t in texts), texts


# ------------------------------------------------------- truth table: refuse rows


@pytest.mark.parametrize(
    ("mode", "queue", "cap", "var"),
    [
        # all + cap without a queue
        ("all", None, 2, "KROKER_HARNESS_CAP"),
        # core / harness need a queue, whatever the cap
        ("core", None, None, "KROKER_HARNESS_QUEUE"),
        ("core", None, 2, "KROKER_HARNESS_QUEUE"),
        ("harness", None, None, "KROKER_HARNESS_QUEUE"),
        ("harness", None, 2, "KROKER_HARNESS_QUEUE"),
        # cap < 1 in every mode (queue set so only the cap is at fault)
        ("all", Q, 0, "KROKER_HARNESS_CAP"),
        ("all", Q, -1, "KROKER_HARNESS_CAP"),
        ("core", Q, 0, "KROKER_HARNESS_CAP"),
        ("core", Q, -1, "KROKER_HARNESS_CAP"),
        ("harness", Q, 0, "KROKER_HARNESS_CAP"),
        ("harness", Q, -1, "KROKER_HARNESS_CAP"),
    ],
)
def test_refuse_rows_raise_value_error_naming_the_variable(
    mode: str, queue: str | None, cap: int | None, var: str
) -> None:
    with pytest.raises(ValueError) as excinfo:
        _plan(mode, queue, cap)
    assert var in str(excinfo.value)


# ------------------------------------------------------------ boot_plan_from_env


def test_env_empty_is_the_single_pool_plan_today() -> None:
    assert _pools().boot_plan_from_env({}) == _expected(
        core=True, harness=False, janitor=True, cap=None, queue=None
    )


@pytest.mark.parametrize("pool", ["all", "core", "harness"])
@pytest.mark.parametrize("cap", ["0", "-1"])
def test_env_cap_below_one_refuses_in_every_mode(pool: str, cap: str) -> None:
    env = {"KROKER_WORKER_POOL": pool, "KROKER_HARNESS_QUEUE": Q, "KROKER_HARNESS_CAP": cap}
    with pytest.raises(ValueError) as excinfo:
        _pools().boot_plan_from_env(env)
    assert "KROKER_HARNESS_CAP" in str(excinfo.value)


def test_env_bogus_pool_refuses_naming_itself() -> None:
    with pytest.raises(ValueError) as excinfo:
        _pools().boot_plan_from_env({"KROKER_WORKER_POOL": "bogus"})
    assert "KROKER_WORKER_POOL" in str(excinfo.value)


def test_env_default_sentinel_resolves_to_the_default_queue() -> None:
    pools = _pools()
    env = {
        "KROKER_WORKER_POOL": "harness",
        "KROKER_HARNESS_QUEUE": "default",
        "KROKER_HARNESS_CAP": "2",
    }
    assert pools.boot_plan_from_env(env) == _expected(
        core=False, harness=True, janitor=True, cap=2, queue=pools.HARNESS_QUEUE_DEFAULT
    )


def test_env_defaults_to_pool_all_when_only_a_queue_is_set() -> None:
    plan = _pools().boot_plan_from_env({"KROKER_HARNESS_QUEUE": Q})
    assert plan == _expected(core=True, harness=True, janitor=True, cap=None, queue=Q)


# ------------------------------------------------------------------ the filters


def _names(activities: Any) -> list[str]:
    return [a.__temporal_activity_definition.name for a in activities]


def test_core_and_harness_activities_partition_the_registered_set() -> None:
    from sdlc import worker

    full = _names(worker.get_worker_activities())
    core = _names(worker.core_activities())
    harness = _names(worker.harness_activities())

    assert set(core) | set(harness) == set(full)
    assert not set(core) & set(harness)
    # No activity is lost or duplicated by the split.
    assert sorted(core + harness) == sorted(full)


def test_harness_activities_are_exactly_the_harness_class() -> None:
    from sdlc import worker
    from sdlc.pools import HARNESS_ACTIVITIES

    harness = set(_names(worker.harness_activities()))
    core = set(_names(worker.core_activities()))

    assert harness, "harness filter returned nothing"
    assert harness <= HARNESS_ACTIVITIES
    assert not core & HARNESS_ACTIVITIES


# ------------------------------------------------- chaos pass (024 T006, edge cases)

_SINGLE_POOL = dict(core=True, harness=False, janitor=True, cap=None, queue=None)


def test_env_empty_dict_does_not_fall_back_to_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An explicitly passed empty mapping is "no variables", not "use os.environ"
    # (the ``env or os.environ`` trap).
    monkeypatch.setenv("KROKER_WORKER_POOL", "harness")
    monkeypatch.setenv("KROKER_HARNESS_QUEUE", Q)
    monkeypatch.setenv("KROKER_HARNESS_CAP", "0")
    assert _pools().boot_plan_from_env({}) == _expected(**_SINGLE_POOL)


def test_env_unrelated_variables_only_is_the_single_pool_plan() -> None:
    env = {"PATH": "/usr/bin", "HOME": "/root", "KROKER_OTHER": "x"}
    assert _pools().boot_plan_from_env(env) == _expected(**_SINGLE_POOL)


@pytest.mark.parametrize("cap", ["abc", "2.5"])
def test_env_unparseable_cap_refuses_naming_the_variable(cap: str) -> None:
    env = {"KROKER_WORKER_POOL": "harness", "KROKER_HARNESS_QUEUE": Q, "KROKER_HARNESS_CAP": cap}
    with pytest.raises(ValueError) as excinfo:
        _pools().boot_plan_from_env(env)
    assert "KROKER_HARNESS_CAP" in str(excinfo.value)


@pytest.mark.parametrize("pool", ["ALL", "All", " all", "all ", "Harness", "CORE"])
def test_env_pool_mode_is_exact_lowercase_no_trim_no_casefold(pool: str) -> None:
    env = {"KROKER_WORKER_POOL": pool, "KROKER_HARNESS_QUEUE": Q}
    with pytest.raises(ValueError) as excinfo:
        _pools().boot_plan_from_env(env)
    assert "KROKER_WORKER_POOL" in str(excinfo.value)


def test_env_blank_queue_behaves_as_unset_in_all_mode() -> None:
    plan = _pools().boot_plan_from_env({"KROKER_WORKER_POOL": "all", "KROKER_HARNESS_QUEUE": ""})
    assert plan == _expected(**_SINGLE_POOL)


@pytest.mark.parametrize("pool", ["core", "harness"])
def test_env_blank_queue_refuses_in_core_and_harness(pool: str) -> None:
    env = {"KROKER_WORKER_POOL": pool, "KROKER_HARNESS_QUEUE": ""}
    with pytest.raises(ValueError) as excinfo:
        _pools().boot_plan_from_env(env)
    assert "KROKER_HARNESS_QUEUE" in str(excinfo.value)


@pytest.mark.parametrize(
    ("mode", "queue", "cap"),
    [("all", None, None), ("all", Q, 2), ("core", Q, 2), ("harness", Q, 2)],
)
def test_pool_boot_plan_accepts_mode_member_and_its_string_value(
    mode: str, queue: str | None, cap: int | None
) -> None:
    pools = _pools()
    by_member = pools.pool_boot_plan(pools.PoolMode(mode), queue, cap)
    by_string = pools.pool_boot_plan(mode, queue, cap)
    assert by_string == by_member


@pytest.mark.parametrize("field", ["core_worker", "harness_worker", "janitor", "cap", "queue"])
def test_plan_rejects_assignment_to_every_field(field: str) -> None:
    plan = _plan("harness", Q, 2)
    before = dataclasses.asdict(plan)
    with pytest.raises(AttributeError):  # FrozenInstanceError subclasses AttributeError
        setattr(plan, field, None)
    assert dataclasses.asdict(plan) == before
