"""Contract for ``sdlc.benchmarks.cli.bench_workflow_id`` (024 T013; R8, W-5, P-FR-009).

Today the benchmark workflow id is ``bench-<case_id>-<epoch seconds>``, so two fleet
starts of one case in the same second collide. T014 extracts a pure
``bench_workflow_id(case_id, now=time.time)`` that appends a 6-hex random suffix.

RED until T014: ``bench_workflow_id`` does not exist yet, so every case fails on the
missing attribute. ``sdlc.benchmarks.cli`` is imported inside each test so each case
fails on its own instead of erroring at collection.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from typing import Any

import pytest

FROZEN = 1234.5
EPOCH = int(FROZEN)  # 1234 — the epoch is int(now()), truncated, not rounded


def _frozen() -> float:
    return FROZEN


def _bench_workflow_id() -> Callable[..., str]:
    from sdlc.benchmarks import cli

    return cli.bench_workflow_id  # type: ignore[attr-defined,no-any-return]


def _pattern(case_id: str) -> re.Pattern[str]:
    return re.compile(rf"bench-{re.escape(case_id)}-{EPOCH}-[0-9a-f]{{6}}")


def test_fifty_same_second_calls_are_all_distinct() -> None:
    make = _bench_workflow_id()

    ids = [make("case-a", _frozen) for _ in range(50)]

    assert len(set(ids)) == 50, f"same-second collisions: {len(ids) - len(set(ids))}"


def test_id_shape_is_prefix_int_epoch_and_six_lowercase_hex() -> None:
    make = _bench_workflow_id()

    for _ in range(50):
        wid = make("case-a", _frozen)
        assert _pattern("case-a").fullmatch(wid), wid


def test_different_case_ids_in_the_same_second_have_disjoint_id_sets() -> None:
    make = _bench_workflow_id()

    a = {make("case-a", _frozen) for _ in range(50)}
    b = {make("case-b", _frozen) for _ in range(50)}

    assert not a & b
    assert all(i.startswith("bench-case-a-") for i in a)
    assert all(i.startswith("bench-case-b-") for i in b)


def test_two_calls_with_the_same_inputs_differ() -> None:
    # The suffix is entropy (uuid), not a hash of the inputs.
    make = _bench_workflow_id()

    assert make("case-a", _frozen) != make("case-a", _frozen)


def test_injected_now_means_time_time_and_environment_are_never_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make = _bench_workflow_id()

    def no_clock() -> float:
        raise AssertionError("time.time() must not be read when now is injected")

    class NoEnv(dict[str, str]):
        def __getitem__(self, key: str) -> str:
            raise AssertionError(f"environment read: {key!r}")

        def get(self, key: str, default: Any = None) -> Any:
            raise AssertionError(f"environment read: {key!r}")

        def __contains__(self, key: object) -> bool:
            raise AssertionError(f"environment read: {key!r}")

    monkeypatch.setattr(time, "time", no_clock)
    monkeypatch.setattr(os, "environ", NoEnv())

    wid = make("case-a", _frozen)

    assert _pattern("case-a").fullmatch(wid), wid


@pytest.mark.parametrize("case_id", ["case.v2-x", "a", "UPPER_snake.1"])
def test_case_id_passes_through_verbatim_into_the_prefix(case_id: str) -> None:
    make = _bench_workflow_id()

    wid = make(case_id, _frozen)

    assert wid.startswith(f"bench-{case_id}-{EPOCH}-")
    assert _pattern(case_id).fullmatch(wid), wid


# ------------------------------------------------ happy-path core (024 T013, QA happy pass)
# The id shape itself is pinned above (``test_id_shape_...``); these add what it does not.


def test_signature_is_case_id_then_now_with_a_default() -> None:
    import inspect

    params = inspect.signature(_bench_workflow_id()).parameters

    assert list(params)[:2] == ["case_id", "now"]
    assert params["now"].default is not inspect.Parameter.empty


def test_consecutive_nows_keep_epoch_order_in_the_id() -> None:
    make = _bench_workflow_id()

    first = make("case-1", lambda: 1234.5)
    second = make("case-1", lambda: 1235.0)

    def epoch(wid: str) -> int:
        m = re.fullmatch(r"bench-case-1-([0-9]+)-[0-9a-f]{6}", wid)
        assert m, wid
        return int(m.group(1))

    assert epoch(first) == 1234
    assert epoch(second) == 1235
    assert epoch(first) < epoch(second)


def test_omitting_now_reads_the_real_clock() -> None:
    make = _bench_workflow_id()

    before = int(time.time())
    wid = make("case-1")
    after = int(time.time())

    m = re.fullmatch(r"bench-case-1-([0-9]+)-[0-9a-f]{6}", wid)
    assert m, wid
    assert before <= int(m.group(1)) <= after
