"""C2 Tasks 5-7: the flag's journey from the loop to the fence."""

from __future__ import annotations

from sdlc.core.models import HarnessKind
from sdlc.harness.base import HarnessRequest
from sdlc.harness.registry import HARNESSES
from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment


def test_coding_task_input_defaults_to_free_first_pass():
    assert (
        CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="p", worktree="/wt").repair is False
    )


def test_resolve_containment_forwards_repair_to_the_compiled_fence(tmp_path):
    """The end-to-end bit: an input marked repair must produce a settings
    file whose hook command carries --repair."""
    import json
    from pathlib import Path

    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        repair=True,
    )
    harness = HARNESSES[HarnessKind.CLAUDE_CODE]
    req = HarnessRequest(prompt="p", cwd=str(tmp_path), repair=inp.repair)
    _resolve_containment(harness, inp, req)
    settings_path = req.extra_args[req.extra_args.index("--settings") + 1]
    doc = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    assert "--repair" in doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def test_crew_turn_input_carries_repair():
    from sdlc.crew.activities import CrewTurnInput

    t = CrewTurnInput(
        worktree="/wt",
        layout="code",
        role="lead",
        harness=HarnessKind.CLAUDE_CODE,
        model="m",
        prompt="p",
        round=1,
        attempt=1,
        turn_timeout_s=60,
        task_id="t1",
        repair=True,
    )
    assert t.repair is True


def test_every_crew_turn_input_construction_passes_repair():
    """Guards fact 5: both sites hardcode attempt=1, so if `repair` is ever
    dropped at one of them that path silently runs unfrozen and no
    attempt-based test would notice."""
    import ast
    import inspect

    from sdlc.workflows import crew as crew_mod

    tree = ast.parse(inspect.getsource(crew_mod))
    sites = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "CrewTurnInput"
    ]
    assert len(sites) == 2, f"expected 2 CrewTurnInput sites, found {len(sites)}"
    for site in sites:
        assert any(kw.arg == "repair" for kw in site.keywords), (
            "a CrewTurnInput site does not pass repair -- that path runs unfrozen"
        )


# --- plan Task 6: glob loading, vacuity, strict -----------------------------

import pytest  # noqa: E402

from sdlc.harness.containment import ContainmentError  # noqa: E402
from sdlc.stages.code.activities import DriftGlobsInput, load_drift_globs  # noqa: E402


@pytest.mark.asyncio
async def test_load_drift_globs_splits_fence_from_report(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "drift_paths: ['pyproject.toml']\n"
        "rules:\n"
        "  - id: freeze\n"
        "    layer: native\n"
        "    phase: repair\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: frozen\n",
        encoding="utf-8",
    )
    out = await load_drift_globs(DriftGlobsInput(policy_path=str(p)))
    assert out.fence == ["tests/**"]
    assert out.report == ["pyproject.toml"]


def test_strict_refuses_a_repair_run_whose_policy_fences_nothing(tmp_path):
    """A policy with no repair-phase rule is the ASSET LYING about what is in
    force. That is what strict is for."""
    from sdlc.core.models import HarnessKind
    from sdlc.harness.registry import HARNESSES
    from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment

    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: cfg\n"
        "    layer: native\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['**/.claude/**']\n"
        "    reason: no\n",
        encoding="utf-8",
    )
    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_strict=True,
        containment_policy_path=str(p),
        repair=True,
    )
    with pytest.raises(ContainmentError, match="repair"):
        _resolve_containment(HARNESSES[HarnessKind.CLAUDE_CODE], inp)


def test_strict_does_not_refuse_a_merely_vacuous_glob_set(tmp_path):
    """A vacuous G is a LAYOUT MISMATCH (a Go task under Python-shaped
    globs), not a lie. Refusing mid-loop would kill a healthy run and make
    the safe configuration strictly worse to enable. Deliberate reversal of
    an earlier draft of this design -- do not restore it."""
    from sdlc.core.models import HarnessKind
    from sdlc.harness.registry import HARNESSES
    from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment

    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: freeze\n"
        "    layer: native\n"
        "    phase: repair\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['nothing_matches_this/**']\n"
        "    reason: frozen\n",
        encoding="utf-8",
    )
    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_strict=True,
        containment_policy_path=str(p),
        repair=True,
    )
    _, report = _resolve_containment(HARNESSES[HarnessKind.CLAUDE_CODE], inp)
    assert report.freeze_vacuous is True  # recorded, not refused
