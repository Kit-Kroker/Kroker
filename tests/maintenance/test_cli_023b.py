"""The 023b `sdlc maintain` CLI surface (T046, RED; contracts/cli.md, R14).

Subject: ``sdlc.maintenance.cli`` (``register_maintain_subparsers`` /
``run_maintain``) and ``sdlc.maintenance.render.incidents_table``. T047 lands
``--execute``, the four cap flags, the client-side preconditions, the help
note and the incident-table columns; until then the cells below fail.

Exit mechanism. Every refusal cell asserts the exit CODE 2 and a stderr
MESSAGE that names the specific missing thing. The helper ``_outcome`` accepts
either route the contract allows: argparse's own ``SystemExit(2)`` (a usage
error) or ``run_maintain`` returning 2 (a runtime precondition). T047 may
implement either; it must not exit 1 for these refusals (1 is the
"invalid configuration" path, a WRONG code here).

Tooling. The no-``gh`` cell patches ``shutil.which`` on the shared ``shutil``
module (the same function ``cli.py`` reaches through ``import shutil``).
Patching the dotted path ``sdlc.maintenance.cli.shutil.which`` would raise
AttributeError today, because ``cli.py`` does not import ``shutil`` yet, which
would be a test error rather than a message-level RED.

Builders and the origin remote are local to this file (no test-module
imports, no conftest git helper). ``_ready`` wires a local bare ``origin`` so
that only the cell's own missing item is absent.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sdlc.maintenance.models import ExecutionRecord, Incident, IncidentState
from sdlc.triage.models import FixClass, TriageFinding

PROJECT = "p"
EXECUTE_ARGV = ["enable", PROJECT, "--execute", "--ack-unattended-build-probe"]

# The help substring this suite pins (contracts/cli.md: "disable followed by
# re-enable resets the 7-day start window"). Whitespace is normalised, because
# argparse wraps help lines.
HELP_WINDOW_NOTE = "resets the 7-day start window"

CAP_FLAGS = [
    ("--max-starts-per-cycle", "2"),
    ("--max-starts-per-window", "5"),
    ("--max-reopens", "1"),
    ("--child-timeout-hours", "24"),
]

# (flag, bad value, lower bound, upper bound) per contracts/cli.md
OUT_OF_RANGE = [
    ("--max-starts-per-cycle", "0", 1, 3),
    ("--max-starts-per-cycle", "4", 1, 3),
    ("--max-starts-per-window", "0", 1, 10),
    ("--max-starts-per-window", "11", 1, 10),
    ("--max-reopens", "-1", 0, 2),
    ("--max-reopens", "3", 0, 2),
    ("--child-timeout-hours", "0", 1, 168),
    ("--child-timeout-hours", "169", 1, 168),
]


# ------------------------------------------------------------------ harness


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sdlc")
    msub = p.add_subparsers(dest="maintain_cmd", required=True)
    from sdlc.maintenance.cli import register_maintain_subparsers

    register_maintain_subparsers(msub)
    return p


class _FakeStart:
    def __init__(self) -> None:
        self.started: list[dict] = []

    async def __call__(self, wf, state, *, id: str, task_queue: str):  # noqa: A002
        self.started.append({"id": id, "task_queue": task_queue, "state": state})


class _FakeClient:
    def __init__(self) -> None:
        self.start_workflow = _FakeStart()


def _outcome(argv: list[str], client: _FakeClient, capsys) -> tuple[int, str, str]:  # noqa: ANN001
    """Run ``argv`` through the real parser and ``run_maintain``. Returns
    (exit code, stdout, stderr). An argparse usage error (SystemExit) and a returned
    code both count; the contract's code is 2 either way."""
    from sdlc.maintenance.cli import run_maintain

    try:
        args = _parser().parse_args(argv)
        code = asyncio.run(run_maintain(args, client))
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _ready(tmp_path: Path, repo: Path) -> Path:
    """Wire a local bare ``origin`` and push ``main`` to it, so ``origin``
    exists and ``main`` resolves both locally and on the remote."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "origin", "main")
    return repo


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture(autouse=True)
def _tools_on_path(monkeypatch):
    """Every tool the preconditions look for is on PATH unless a cell removes
    one (the no-``gh`` cell)."""
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")


# --------------------------------------------- 1-2. --execute needs the probe ack


def test_execute_without_the_probe_ack_is_refused_naming_the_ack(repo_dir, capsys):
    """Cell 1. The probe group is required and the ack is absent, so argparse
    already exits 2, but its message names only the group. The refusal must
    name --execute and the ack it is missing."""
    client = _FakeClient()
    argv = ["enable", PROJECT, "--repo", str(repo_dir), "--execute"]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert "--execute" in err
    assert "--ack-unattended-build-probe" in err
    assert not client.start_workflow.started


def test_execute_with_no_build_probe_is_refused_naming_the_probe(tmp_path, repo_dir, capsys):
    """Cell 2. --execute cannot run with the probe disabled. Today the message
    is only 'unrecognized arguments: --execute', which does not name the probe."""
    client = _FakeClient()
    argv = [
        "enable",
        PROJECT,
        "--repo",
        str(_ready(tmp_path, repo_dir)),
        "--execute",
        "--no-build-probe",
    ]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert "--no-build-probe" in err
    assert "--execute" in err
    assert not client.start_workflow.started


# ----------------------------------------------- 3. --execute needs gh on PATH


def test_execute_without_gh_on_path_is_refused_naming_gh(tmp_path, repo_dir, monkeypatch, capsys):
    """Cell 3, negative. The repo is otherwise ready (origin, main), so only gh
    is missing. The refusal must name gh."""
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "gh" else f"/usr/bin/{name}")
    client = _FakeClient()
    argv = [*EXECUTE_ARGV, "--repo", str(_ready(tmp_path, repo_dir))]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert "gh" in err
    assert not client.start_workflow.started


def test_execute_with_gh_on_path_proceeds_and_starts_the_loop(tmp_path, repo_dir, capsys):
    """Cell 3, positive control. The same argv with gh on PATH passes the
    precondition and reaches start: enable exits 0, prints 'enabled maint-p',
    and the started config carries execute=True. This proves the check order,
    and that a which-passing execute enable reaches start."""
    client = _FakeClient()
    argv = [*EXECUTE_ARGV, "--repo", str(_ready(tmp_path, repo_dir))]
    # Executor fix (disclosed): _outcome consumes the capsys capture and
    # returns stdout as its second element — re-reading capsys here yields ''.
    code, out, err = _outcome(argv, client, capsys)
    assert code == 0, err
    assert len(client.start_workflow.started) == 1
    started = client.start_workflow.started[0]
    assert started["id"] == f"maint-{PROJECT}"
    assert started["state"].config.execute is True
    assert f"enabled maint-{PROJECT}" in out


# ------------------------------------------------ 4-5. origin and default_branch


def test_execute_without_an_origin_remote_is_refused_naming_origin(repo_dir, capsys):
    """Cell 4. make_repo adds no remote; the precondition must name origin."""
    assert _git(repo_dir, "remote") == "", "precondition: the fixture repo has no remote"
    client = _FakeClient()
    argv = [*EXECUTE_ARGV, "--repo", str(repo_dir)]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert "origin" in err
    assert not client.start_workflow.started


def test_execute_with_an_unresolved_default_branch_is_refused_naming_the_branch(
    tmp_path, repo_dir, capsys
):
    """Cell 5. origin is present, but 'nope' resolves neither locally nor on
    the remote. The refusal must name the branch."""
    client = _FakeClient()
    argv = [*EXECUTE_ARGV, "--repo", str(_ready(tmp_path, repo_dir)), "--branch", "nope"]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert "nope" in err
    assert "branch" in err
    assert not client.start_workflow.started


# -------------------------------------------- 6. cap flags need --execute


@pytest.mark.parametrize(("flag", "value"), CAP_FLAGS, ids=[f for f, _ in CAP_FLAGS])
def test_a_cap_flag_without_execute_is_refused(repo_dir, flag, value, capsys):
    """Cell 6. A cap is meaningful only with --execute. The refusal text is
    'only meaningful with --execute'."""
    client = _FakeClient()
    argv = ["enable", PROJECT, "--repo", str(repo_dir), "--ack-unattended-build-probe", flag, value]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert flag in err
    assert "only meaningful with --execute" in err
    assert not client.start_workflow.started


# ------------------------------------------------- 7. out-of-range cap values


@pytest.mark.parametrize(
    ("flag", "value", "lo", "hi"),
    OUT_OF_RANGE,
    ids=[f"{f}={v}" for f, v, _, _ in OUT_OF_RANGE],
)
def test_an_out_of_range_cap_is_refused_naming_the_flag_and_its_range(
    tmp_path, repo_dir, flag, value, lo, hi, capsys
):
    """Cell 7. Full execute argv with one cap out of range. The refusal names
    the flag and its range, written as 'lo-hi', 'lo..hi' or 'lo to hi'. The exit
    code is 2, not the 1 of the 'invalid configuration' path."""
    client = _FakeClient()
    argv = [*EXECUTE_ARGV, "--repo", str(_ready(tmp_path, repo_dir)), flag, value]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 2
    assert flag in err
    assert re.search(rf"{lo}\s*(?:-|\.\.|to|and)\s*{hi}\b", err), err
    assert not client.start_workflow.started


# ------------------------------------------------------------- 8. help note


def test_enable_help_states_the_seven_day_window_reset(capsys):
    """Cell 8. The help text says disable followed by re-enable resets the 7-day
    start window. Whitespace is normalised because argparse wraps lines."""
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(["enable", "--help"])
    assert exc.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert HELP_WINDOW_NOTE in out


# ------------------------------------- 9. gate-policy / on-timeout stay absent


@pytest.mark.parametrize(
    ("argv", "flag"),
    [
        (["--gate-policy", "strict"], "--gate-policy"),
        (["--on-timeout", "abandon"], "--on-timeout"),
    ],
    ids=["gate-policy", "on-timeout"],
)
def test_gate_policy_and_on_timeout_stay_absent_on_enable(tmp_path, repo_dir, argv, flag, capsys):
    """Cell 9 (also pinned in test_cli.py). R9: there is no gate-policy or
    on-timeout flag, so argparse rejects both with exit 2 and names the
    rejected flag."""
    client = _FakeClient()
    full = ["enable", PROJECT, "--repo", str(repo_dir), "--ack-unattended-build-probe", *argv]
    code, _, err = _outcome(full, client, capsys)
    assert code == 2
    assert flag in err
    assert not client.start_workflow.started


# -------------------------------------------- 10. incidents table, 023b columns


def _finding(no: int) -> TriageFinding:
    return TriageFinding(
        signal="secrets",
        rule=f"rule_{no}",
        severity="high",
        detail="a tracked secret file",
        path=".gitignore",
        evidence="",
        fix_class=FixClass.MECHANICAL,
    )


def _execution(child_id: str) -> ExecutionRecord:
    return ExecutionRecord(
        attempt=1,
        child_id=child_id,
        base_sha="a" * 40,
        started_at=datetime(2026, 11, 15, tzinfo=UTC),
        outcome="awaiting_merge",
        detail="",
    )


def _inc(no: int, state: str, *, execution: ExecutionRecord | None = None) -> Incident:
    return Incident(
        no=no,
        key=f"secrets:rule_{no}::.gitignore",
        kind="finding",
        finding=_finding(no),
        commit_sha="b" * 40,
        first_seen_cycle=1,
        last_seen_cycle=1,
        state=IncidentState(state),
        attempt=1 if execution else 0,
        execution=execution,
        executions=[execution] if execution else [],
    )


VERIFIED_CHILD = "maint-demo-abcd1234-inc5-a1"
STATES = ["approved", "queued", "executing", "verifying", "verified", "reopened", "closed"]


def _table_incidents() -> list[Incident]:
    incidents = [_inc(no, state) for no, state in enumerate(STATES, start=1)]
    incidents[4] = _inc(5, "verified", execution=_execution(VERIFIED_CHILD))
    return incidents


def _table() -> str:
    from sdlc.maintenance.render import incidents_table

    return incidents_table(_table_incidents(), include_terminal=True)


def test_the_incidents_header_names_the_023b_columns():
    """Header. attempt, reopens and child are new columns (contracts/cli.md).
    Today's header is INC-n, state, key, seen, eff.conf, gate, so this is RED."""
    header = _table().splitlines()[0]
    for column in ("attempt", "reopens", "child"):
        assert column in header, header


@pytest.mark.parametrize(("no", "state"), list(enumerate(STATES, start=1)))
def test_each_023b_state_renders_verbatim_in_its_row(no, state):
    """Verbatim states. Each row carries its state string. The state column
    already exists, so this should pass today (pre-green)."""
    rows = {line.split()[0]: line for line in _table().splitlines()[1:] if line.strip()}
    assert f"INC-{no}" in rows, _table()
    assert state in rows[f"INC-{no}"]


def test_a_verified_incident_row_shows_its_child_id():
    """A verified incident's row carries its execution child id, so the
    operator can find the merge gate in `sdlc inbox`. Today the table has no
    child column, so this is RED."""
    rows = {line.split()[0]: line for line in _table().splitlines()[1:] if line.strip()}
    assert VERIFIED_CHILD in rows["INC-5"], rows["INC-5"]


# ------------------------------------------------ EDGE (023b T046) -- qa-chaos


@pytest.mark.parametrize(
    ("flag", "value", "dest"),
    [
        ("--max-starts-per-cycle", "1", "max_starts_per_cycle"),
        ("--max-starts-per-cycle", "3", "max_starts_per_cycle"),
        ("--max-starts-per-window", "1", "max_starts_per_window"),
        ("--max-starts-per-window", "10", "max_starts_per_window"),
        ("--max-reopens", "0", "max_reopens"),
        ("--max-reopens", "2", "max_reopens"),
        ("--child-timeout-hours", "1", "child_timeout_hours"),
        ("--child-timeout-hours", "168", "child_timeout_hours"),
    ],
    ids=[
        "max_starts_per_cycle=1",
        "max_starts_per_cycle=3",
        "max_starts_per_window=1",
        "max_starts_per_window=10",
        "max_reopens=0",
        "max_reopens=2",
        "child_timeout_hours=1",
        "child_timeout_hours=168",
    ],
)
def test_a_cap_at_its_contract_boundary_is_accepted_and_carried_into_the_config(
    tmp_path, repo_dir, flag, value, dest, capsys
):
    """Edge, RED today (unknown flags, so no start). Each cap's contract boundary
    values are ACCEPTED, not refused: the full execute argv with the boundary value
    exits 0, starts the loop once, and the started MaintenanceState.config carries
    exactly that value in its destination field. This pins the bounds T047 must
    implement precisely: an off-by-one bound, or a one-off clamp, fails here."""
    client = _FakeClient()
    argv = [*EXECUTE_ARGV, "--repo", str(_ready(tmp_path, repo_dir)), flag, value]
    code, _, err = _outcome(argv, client, capsys)
    assert code == 0, err
    assert len(client.start_workflow.started) == 1, "a boundary value starts the loop"
    config = client.start_workflow.started[0]["state"].config
    assert getattr(config, dest) == int(value), f"{dest} must carry {value} exactly"
