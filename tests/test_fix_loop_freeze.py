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
