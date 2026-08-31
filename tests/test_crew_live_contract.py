# tests/test_crew_live_contract.py
"""One real round against a real CLI. Behind its own marker and off by
default: it spends tokens. It exists to catch the failures a fake harness
cannot -- a CLI that does not resume, a note the skill did not produce."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from sdlc.crew.activities import (
    CrewTurnInput, PrepareCrewInput, ReadRoundInput, prepare_crew, read_round,
    run_crew_turn,
)
from sdlc.crew.loader import load_layout, read_skill
from sdlc.crew.worktree import round_dir

pytestmark = [pytest.mark.crew, pytest.mark.asyncio]

PROMPT = ("Add a file hello.py containing a function greet() that returns "
          "the string 'hello'.")


@pytest.mark.skipif(os.environ.get("SDLC_LIVE_TESTS") != "1",
                    reason="spends tokens; set SDLC_LIVE_TESTS=1")
async def test_one_real_round(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v],
                       check=True)
    layout, roles = load_layout("code")
    lead = roles[layout.lead]
    # Compose the turn prompt the way CrewTaskWorkflow._round_brief does:
    # the lead's skill (the round protocol) first, the assignment after —
    # this is the delivery path production runs on.
    turn_prompt = f"{read_skill(lead.skill)}\n\n{PROMPT}"

    await prepare_crew(PrepareCrewInput(worktree=str(tmp_path),
                                        layout=layout.layout, brief=PROMPT))
    d = round_dir(tmp_path, layout.layout, 1)

    out = await run_crew_turn(CrewTurnInput(
        worktree=str(tmp_path), layout=layout.layout, role=lead.name,
        harness=lead.harness, model=lead.model, prompt=turn_prompt,
        round=1, attempt=1, turn_timeout_s=900, task_id="live"))

    # The work/notes inversion: source in the worktree, prose in the note.
    assert (tmp_path / "hello.py").is_file()
    reading = await read_round(ReadRoundInput(
        worktree=str(tmp_path), layout=layout.layout, round=1,
        deliverable_path=layout.deliverable.path))
    assert reading.missing is False
    assert reading.note_summary
    note = json.loads((d / layout.deliverable.path).read_text(
        encoding="utf-8"))
    assert note["schema"] == "notes-v1"
    # Costing worked end to end -- the whole reason CostProbe is gone.
    assert out.record.cost_incomplete is False
    assert out.record.session_id
