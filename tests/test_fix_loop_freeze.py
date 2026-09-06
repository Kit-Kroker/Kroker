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


# --- plan Task 7: loop semantics --------------------------------------------

from sdlc.stages.code.step import (  # noqa: E402
    _drift_note,
    _is_repair_attempt,
    _next_anchor,
)
from sdlc.vcs import DriftReport  # noqa: E402


@pytest.mark.parametrize(
    "attempt,thawed,expect",
    [
        (1, False, False),  # the free first pass
        (2, False, True),  # first repair
        (5, False, True),
        (3, True, False),  # a thawed attempt runs unfrozen
    ],
)
def test_is_repair_attempt(attempt, thawed, expect):
    assert _is_repair_attempt(attempt, thawed) is expect


def test_drift_note_names_each_channel_distinctly():
    """A human adjudicates 'evasion' differently from 'a test changed'."""
    note = _drift_note(
        DriftReport(
            fence_paths=["tests/test_a.py"],
            report_paths=["pyproject.toml"],
            index_bit_paths=["tests/test_a.py"],
            patch="--- a\n+++ b\n",
        )
    )
    assert "tests/test_a.py" in note
    assert "pyproject.toml" in note
    assert "skip-worktree" in note or "assume-unchanged" in note
    assert "--- a" in note  # the patch, so weakening is adjudicable in one look


def test_drift_note_reports_unavailability_rather_than_silence():
    note = _drift_note(DriftReport(available=False, unavailable_reason="anchor missing"))
    assert "unavailable" in note.lower()
    assert "anchor missing" in note


def test_drift_note_is_empty_when_clean():
    assert _drift_note(DriftReport()) == ""


# --- anchor semantics: the two tests most likely to be written wrong --------


def test_anchor_never_creeps_to_the_previous_attempt():
    """RATCHET. If A moved to each attempt's checkpoint, attempt 2 could
    weaken a test and attempt 3 would inherit the weakened state as its own
    baseline -- drift would report clean and the weakening would launder
    itself over two attempts."""
    a1 = _next_anchor(None, "sha1", freely_writable=True)  # attempt 1 sets A
    assert a1 == "sha1"
    a2 = _next_anchor(a1, "sha2", freely_writable=False)  # attempt 2: frozen
    assert a2 == "sha1"
    a3 = _next_anchor(a2, "sha3", freely_writable=False)  # attempt 3: still A1
    assert a3 == "sha1"


def test_a_thawed_attempt_re_anchors_and_the_next_one_measures_from_it():
    """RE-ANCHORING, asserted on the ANCHOR rather than on a flag. A test
    that only asserts `thawed is False` afterwards passes while the feature
    self-defeats: the human's authorized edits would fire drift forever."""
    a = _next_anchor(None, "sha1", freely_writable=True)
    a = _next_anchor(a, "sha2", freely_writable=False)  # frozen attempt
    assert a == "sha1"
    a = _next_anchor(a, "sha3", freely_writable=True)  # THAWED attempt
    assert a == "sha3", "a thaw must move A, or its own edits fire drift"
    a = _next_anchor(a, "sha4", freely_writable=False)  # back to frozen
    assert a == "sha3", "later attempts measure from the thawed baseline"


def test_a_missing_checkpoint_leaves_the_anchor_alone():
    """Fact 7's channels (a swallowed commit failure; a crew round-1
    deadline) yield no sha. Never fall back to branch_point: that would
    report attempt 1's own legitimate test authoring as drift on every
    remaining attempt, with no way for a human to suppress it."""
    assert _next_anchor(None, None, freely_writable=True) is None
    assert _next_anchor("sha1", None, freely_writable=False) == "sha1"
    assert _next_anchor("sha1", None, freely_writable=True) == "sha1"


def test_a_frozen_attempts_checkpoint_never_becomes_the_anchor():
    """fact 7a: attempt 1's checkpoint is swallowed, so A is still None when
    the FROZEN attempt 2 checkpoints. Anchoring there would make a repair
    attempt's tree the baseline -- attempt 3 inherits attempt 2's weakening
    as clean, which is the two-attempt laundering the ratchet exists to stop.
    A stays None and the backstop records itself unavailable instead."""
    a = _next_anchor(None, None, freely_writable=True)  # attempt 1, no checkpoint
    assert a is None
    a = _next_anchor(a, "sha2", freely_writable=False)  # attempt 2, frozen
    assert a is None, "a frozen attempt's checkpoint must never become A"
    a = _next_anchor(a, "sha3", freely_writable=True)  # a thaw re-opens capture
    assert a == "sha3"


def test_repair_is_constant_across_the_escalation_inner_loop():
    """The inner loop re-executes the SAME attempt after a tool-grant
    decision (step.py:511-612). The tests' protected status must not flicker
    mid-attempt, or a session could bank a denial, get one grant, and find
    the fence gone on the re-entry."""
    attempt, thawed = 3, False
    assert {_is_repair_attempt(attempt, thawed) for _ in range(5)} == {True}
