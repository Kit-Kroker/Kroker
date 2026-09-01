"""D14: the degrade-alone rule has one home. Two copies of it in two
workflows agree only by coincidence -- the reason E-42 D2 extracted
GateHost."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from sdlc.workflows import fanout, triage


def test_triage_no_longer_owns_its_own_try_except():
    """The refit is the point: TriageWorkflow._one must DELEGATE, not keep a
    second copy of the rule."""
    src = inspect.getsource(triage.TriageWorkflow._one)
    assert "run_or_degrade" in src
    assert "except Exception" not in src


def test_fanout_module_is_the_only_place_the_rule_lives():
    src = inspect.getsource(fanout.run_or_degrade)
    assert "except Exception" in src


def test_fallback_is_called_with_no_arguments_on_failure(monkeypatch):
    """Pure-Python exercise of the contract; workflow-level behaviour is
    covered by tests/test_triage_workflow_e2e.py, which stays green."""
    calls: list[str] = []

    async def boom(*a, **kw):
        raise RuntimeError("worker lost")

    monkeypatch.setattr(fanout.workflow, "execute_activity", boom)

    def fallback():
        calls.append("fallback")
        return "degraded"

    got = asyncio.run(fanout.run_or_degrade("act", "arg", {}, fallback=fallback))
    assert got == "degraded"
    assert calls == ["fallback"]


def test_success_returns_the_activity_result(monkeypatch):
    async def ok(activity, arg, **kw):
        return f"ran:{arg}"

    monkeypatch.setattr(fanout.workflow, "execute_activity", ok)
    got = asyncio.run(
        fanout.run_or_degrade("act", "arg", {}, fallback=lambda: pytest.fail("not reached"))
    )
    assert got == "ran:arg"
