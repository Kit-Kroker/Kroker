"""Contract tests for the pure surface of ``sdlc.pools`` (024 T002; data-model §pools).

RED until T003 creates ``src/sdlc/pools.py``. ``sdlc.pools`` is imported inside
each test (not at module top) so every case fails on its own rather than the
whole file erroring at collection.
"""

from __future__ import annotations

import enum
import importlib
import subprocess
import sys
from types import ModuleType

import pytest

QUEUE_ENV = "KROKER_HARNESS_QUEUE"


def _pools() -> ModuleType:
    return importlib.import_module("sdlc.pools")


# --------------------------------------------------------------------- constants


def test_harness_queue_default_value() -> None:
    assert _pools().HARNESS_QUEUE_DEFAULT == "ai-sdlc-harness"


def test_pool_mode_values() -> None:
    mode = _pools().PoolMode
    assert issubclass(mode, enum.StrEnum)
    assert {m.name: m.value for m in mode} == {
        "ALL": "all",
        "CORE": "core",
        "HARNESS": "harness",
    }
    assert mode("harness") is mode.HARNESS


# -------------------------------------------------------------------- on_harness


@pytest.mark.parametrize("queue", [None, ""])
def test_on_harness_without_queue_is_an_equal_copy(queue: str | None) -> None:
    opts = {"start_to_close_timeout": 30, "retry_policy": "rp"}
    snapshot = dict(opts)

    out = _pools().on_harness(opts, queue)

    assert out == snapshot
    assert "task_queue" not in out
    assert opts == snapshot  # input not mutated


def test_on_harness_with_queue_adds_task_queue() -> None:
    opts = {"start_to_close_timeout": 30}

    out = _pools().on_harness(opts, "q")

    assert out == {"start_to_close_timeout": 30, "task_queue": "q"}
    assert "task_queue" not in opts  # input not mutated
    assert out is not opts


def test_on_harness_result_splats_into_keywords() -> None:
    def call(**kw: object) -> dict[str, object]:
        return kw

    assert call(**_pools().on_harness({"a": 1}, "q")) == {"a": 1, "task_queue": "q"}
    assert call(**_pools().on_harness({"a": 1}, None)) == {"a": 1}


# ----------------------------------------------------- resolve_harness_queue


def test_resolve_unset_is_none() -> None:
    assert _pools().resolve_harness_queue({}) is None


@pytest.mark.parametrize("blank", ["", " ", "   "])
def test_resolve_blank_is_none(blank: str) -> None:
    assert _pools().resolve_harness_queue({QUEUE_ENV: blank}) is None


def test_resolve_default_sentinel_maps_to_default_queue() -> None:
    pools = _pools()
    assert pools.resolve_harness_queue({QUEUE_ENV: "default"}) == pools.HARNESS_QUEUE_DEFAULT


def test_resolve_valid_name_is_itself() -> None:
    assert _pools().resolve_harness_queue({QUEUE_ENV: "my.q-1"}) == "my.q-1"


def test_resolve_accepts_200_char_name() -> None:
    name = "a" * 200
    assert _pools().resolve_harness_queue({QUEUE_ENV: name}) == name


@pytest.mark.parametrize("bad", ["bad q", "a" * 201, "q/x", "q:1"])
def test_resolve_invalid_name_raises_value_error(bad: str) -> None:
    with pytest.raises(ValueError):
        _pools().resolve_harness_queue({QUEUE_ENV: bad})


def test_resolve_reads_process_environment_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(QUEUE_ENV, "from-os-environ")
    assert _pools().resolve_harness_queue() == "from-os-environ"
    monkeypatch.delenv(QUEUE_ENV)
    assert _pools().resolve_harness_queue() is None


# ------------------------------------------------------------------ import hygiene


def test_importing_pools_does_not_import_worker() -> None:
    """``sdlc.pools`` is a leaf: workflow code imports it, so it must not drag in the worker."""
    code = "import sys; import sdlc.pools; sys.exit(1 if 'sdlc.worker' in sys.modules else 0)"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr or "sdlc.pools imported sdlc.worker"


# ------------------------------------------------- chaos pass (024 T002, edge cases)


def test_on_harness_with_queue_on_empty_opts_returns_a_new_dict() -> None:
    opts: dict[str, object] = {}

    out = _pools().on_harness(opts, "q")

    assert out == {"task_queue": "q"}
    assert out is not opts
    assert opts == {}  # the caller's empty dict is not mutated


def test_pool_mode_all_by_value_is_all() -> None:
    mode = _pools().PoolMode
    assert mode("all") is mode.ALL


def test_pool_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        _pools().PoolMode("bogus")


@pytest.mark.parametrize("sentinel", [" default", "default "])
def test_resolve_default_sentinel_is_exact_no_trimming(sentinel: str) -> None:
    """Only the exact string ``default`` is the sentinel; padded forms are invalid names."""
    with pytest.raises(ValueError):
        _pools().resolve_harness_queue({QUEUE_ENV: sentinel})


def test_resolve_accepts_one_char_name() -> None:
    assert _pools().resolve_harness_queue({QUEUE_ENV: "a"}) == "a"


@pytest.mark.parametrize(
    "bad",
    ["a\n", "a\nb", "a\tb", "café", "q#x"],
    ids=["trailing-newline", "embedded-newline", "tab", "unicode-accent", "hash"],
)
def test_resolve_rejects_control_unicode_and_punctuation_names(bad: str) -> None:
    with pytest.raises(ValueError):
        _pools().resolve_harness_queue({QUEUE_ENV: bad})
