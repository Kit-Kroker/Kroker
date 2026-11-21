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
from collections.abc import Callable
from types import ModuleType
from typing import Any

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


# ------------------------------------------------- root inputs carry harness_queue
# 024 T022 (P-FR-005/011; R1; W-1). RED until T023 adds the field to the 8 models.
# Invalid-name rejection and pre-024 payload validation are owned by qa-chaos.

_INPUT_NAMES = [
    "PipelineConfig",
    "TriageInput",
    "AssessmentInput",
    "TidyUpInput",
    "DeploymentInput",
    "CrewTaskInput",
    "CaseSpec",
    "MaintenanceConfig",
]


def _make_input(name: str, **kw: Any) -> Any:
    """Minimal valid instance of root input ``name``, reusing the existing tests' kwargs."""
    from sdlc.benchmarks.models import CaseSpec
    from sdlc.core.models import DeployConfig, PipelineConfig
    from sdlc.maintenance.models import MaintenanceConfig
    from sdlc.stages.deploy.models import DeployPlan
    from sdlc.workflows.assessment import AssessmentInput
    from sdlc.workflows.crew import CrewTaskInput
    from sdlc.workflows.deployment import DeploymentInput
    from sdlc.workflows.tidyup import TidyUpInput
    from sdlc.workflows.triage import TriageInput

    role = {
        "name": "coder",
        "harness": "opencode",
        "model": "glm-5.3",
        "writes": True,
        "skill": "coder",
    }
    factories: dict[str, Callable[..., Any]] = {
        "PipelineConfig": lambda **k: PipelineConfig(**k),
        "TriageInput": lambda **k: TriageInput(repo_dir="/r", **k),
        "AssessmentInput": lambda **k: AssessmentInput(repo_dir="/r", **k),
        "TidyUpInput": lambda **k: TidyUpInput(repo_dir="/r", **k),
        "DeploymentInput": lambda **k: DeploymentInput(
            plan=DeployPlan(environment="staging", version="v2"),
            cfg=DeployConfig(adapter="script"),
            repo_path="/r",
            **k,
        ),
        "CrewTaskInput": lambda **k: CrewTaskInput(
            layout="code", lead="coder", roles=[role], prompt="p", worktree="/w", **k
        ),
        "CaseSpec": lambda **k: CaseSpec(
            case_id="add-login",
            idea_summary="add login",
            mode="greenfield",
            harnesses=["claude_code"],
            models=["anthropic:claude-sonnet-4-6"],
            judge_model="openai/gpt-5.2",
            rubrics={},
            **k,
        ),
        "MaintenanceConfig": lambda **k: MaintenanceConfig(
            project="p", repo_dir="/r", build_probe=False, **k
        ),
    }
    return factories[name](**kw)


@pytest.mark.parametrize("name", _INPUT_NAMES)
def test_inputs_omit_none(name: str) -> None:
    from sdlc.converter import sdlc_data_converter

    m = _make_input(name)

    assert "harness_queue" not in m.model_dump_json()
    wire = sdlc_data_converter.payload_converter.to_payloads([m])[0].data
    assert b"harness_queue" not in wire


@pytest.mark.parametrize("name", _INPUT_NAMES)
def test_inputs_roundtrip_queue(name: str) -> None:
    m = _make_input(name, harness_queue="q")

    assert m.harness_queue == "q"
    assert type(m).model_validate_json(m.model_dump_json()).harness_queue == "q"


# ---- chaos: the field never holds an invalid value; pre-024 payloads still load

_VALID_QUEUES = ["a" * 200, "my.q-1", "a_b.C-9", "q"]
_INVALID_QUEUES = ["bad q", "a" * 201, ""]


@pytest.mark.parametrize("bad", _INVALID_QUEUES, ids=["space", "len201", "empty"])
@pytest.mark.parametrize("name", _INPUT_NAMES)
def test_inputs_reject_invalid_queue_name(name: str, bad: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError) as exc:
        _make_input(name, harness_queue=bad)

    # extra="forbid" models also raise today, for the wrong reason (field missing).
    assert all(e["type"] != "extra_forbidden" for e in exc.value.errors())


@pytest.mark.parametrize("good", _VALID_QUEUES, ids=["len200", "dotted", "mixed", "one"])
@pytest.mark.parametrize("name", _INPUT_NAMES)
def test_inputs_accept_boundary_valid_queue_name(name: str, good: str) -> None:
    m = _make_input(name, harness_queue=good)

    assert m.harness_queue == good
    assert type(m).model_validate_json(m.model_dump_json()).harness_queue == good


@pytest.mark.parametrize("name", _INPUT_NAMES)
def test_inputs_pre_024_payload_validates_to_none(name: str) -> None:
    m = _make_input(name)
    payload = m.model_dump_json()

    assert "harness_queue" not in payload
    assert type(m).model_validate_json(payload).harness_queue is None


def test_maintenance_config_forbid_accepts_harness_queue_key() -> None:
    from sdlc.maintenance.models import MaintenanceConfig

    payload = '{"project": "p", "repo_dir": "/r", "build_probe": false, "harness_queue": "q"}'

    assert MaintenanceConfig.model_validate_json(payload).harness_queue == "q"
