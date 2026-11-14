"""The `sdlc maintain` CLI (023a T020, RED).

Authorship note: both QA seats are quota-blocked until 23:50; executor-
written under the degradation ruling — every case transcribes T020's task
text and contracts/cli.md. A post-hoc QA audit of this file is queued.

Subject: ``sdlc.maintenance.cli.register_maintain_subparsers`` /
``run_maintain`` (T021 implements; neither exists). Exit contract:
0 success, 2 argparse usage error, 1 refused operation (one line on
stderr).
"""

from __future__ import annotations

import argparse

import pytest
from temporalio.client import WorkflowFailureError

from sdlc.maintenance.cli import register_maintain_subparsers, run_maintain


def _parser() -> argparse.ArgumentParser:
    # A fresh parser per test, exercising register_maintain_subparsers
    # directly at its own level (cli.py nests it under "maintain").
    p = argparse.ArgumentParser(prog="sdlc")
    msub = p.add_subparsers(dest="maintain_cmd", required=True)
    register_maintain_subparsers(msub)
    return p


def _args(argv: list[str]) -> argparse.Namespace:
    return _parser().parse_args(argv)


class _FakeStart:
    def __init__(self, *, already_started: bool = False):
        self.already_started = already_started
        self.started: list[dict] = []

    async def __call__(self, wf, state, *, id: str, task_queue: str):  # noqa: A002
        if self.already_started:
            # The real client surfaces an already-started workflow as a
            # WorkflowFailureError carrying the already-started failure
            # in cause; args carries the legible message here.
            err = WorkflowFailureError(cause=None)
            err.args = (f"workflow id already started: {id}",)
            raise err
        self.started.append({"id": id, "task_queue": task_queue, "state": state})
        return None


class _FakeClient:
    def __init__(self, *, already_started: bool = False):
        self.start_workflow = _FakeStart(already_started=already_started)


def _run(argv: list[str], client, capsys) -> int:
    import asyncio

    args = _args(argv)
    return asyncio.run(run_maintain(args, client))


# ------------------------------- enable ------------------------------------- #


def test_enable_starts_maintain_id_and_prints_it(repo_dir, capsys):
    client = _FakeClient()
    code = _run(
        ["enable", "demo", "--repo", str(repo_dir), "--ack-unattended-build-probe"],
        client,
        capsys,
    )
    assert code == 0
    assert len(client.start_workflow.started) == 1
    started = client.start_workflow.started[0]
    assert started["id"] == "maint-demo"
    assert started["state"].config.project == "demo"
    assert started["state"].config.repo_dir == str(repo_dir)
    assert started["state"].baseline is None  # fresh: no baseline yet
    out = capsys.readouterr().out
    assert "enabled maint-demo" in out


def test_enable_refuses_a_non_git_path_exit_1(tmp_path, capsys):
    client = _FakeClient()
    code = _run(
        ["enable", "demo", "--repo", str(tmp_path / "not-a-repo"), "--no-build-probe"],
        client,
        capsys,
    )
    assert code == 1
    assert not client.start_workflow.started
    assert "git" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "argv",
    [
        ["enable", "demo", "--repo", "/tmp/r"],  # neither ack nor no-probe
        [
            "enable",
            "demo",
            "--repo",
            "/tmp/r",
            "--ack-unattended-build-probe",
            "--no-build-probe",
        ],  # both
    ],
)
def test_enable_requires_exactly_one_probe_flag_exit_2(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        _args(argv)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["enable", "demo", "--repo", "/tmp/r", "--no-build-probe", "--gate-policy", "off"],
        ["enable", "demo", "--repo", "/tmp/r", "--no-build-probe", "--on-timeout", "approve"],
    ],
)
def test_enable_refuses_gate_policy_flags_exit_2(argv):
    # contracts/cli.md: there are no gate-policy flags; argparse rejects
    # them as unknown arguments.
    with pytest.raises(SystemExit) as exc:
        _args(argv)
    assert exc.value.code == 2


def test_enable_invalid_config_refused_exit_1(tmp_path, capsys):
    client = _FakeClient()
    code = _run(
        [
            "enable",
            "Demo",
            "--repo",
            str(tmp_path),
            "--no-build-probe",
        ],
        client,
        capsys,
    )
    assert code == 1
    assert not client.start_workflow.started


def test_enable_already_enabled_exit_1(repo_dir, capsys):
    client = _FakeClient(already_started=True)
    code = _run(
        ["enable", "demo", "--repo", str(repo_dir), "--no-build-probe"],
        client,
        capsys,
    )
    assert code == 1
    assert "already enabled" in capsys.readouterr().err.lower()


# ------------------------------- incidents ----------------------------------- #


class _QueryClient:
    """get_workflow_handle(maint-<p>).query(incidents/maintenance_state)."""

    def __init__(self, incidents, summary):
        self._incidents = incidents
        self._summary = summary
        self.queried: list[str] = []

        class _Handle:
            async def query(hself, name, **kw):  # noqa: ANN001
                self.queried.append(name)
                if name == "incidents":
                    return self._incidents
                return self._summary

        self.get_workflow_handle = lambda wid: _Handle()


def test_incidents_renders_the_contract_table(capsys):
    from sdlc.maintenance.models import Incident, IncidentState, MaintenanceSummary

    inc = Incident(
        no=1,
        key="build_probe:build_failed::",
        kind="finding",
        commit_sha="a" * 40,
        first_seen_cycle=2,
        last_seen_cycle=2,
        state=IncidentState.AWAITING_DECISION,
    )
    summary = MaintenanceSummary(
        project="demo",
        cycle=3,
        baseline_recorded=True,
        running_cycle=False,
        open_gates=1,
        ack_unattended_build_probe=False,
    )
    client = _QueryClient([inc], summary)
    code = _run(["incidents", "demo"], client, capsys)
    assert code == 0
    out = capsys.readouterr().out
    assert "INC-1" in out
    assert "awaiting_decision" in out
    assert "build_probe:build_failed::" in out
    assert "repair:1" in out


def test_incidents_all_includes_terminal(capsys):
    from sdlc.maintenance.models import Incident, IncidentState, MaintenanceSummary

    terminal = Incident(
        no=2,
        key="secrets:env_file_tracked:.gitignore:",
        kind="finding",
        commit_sha="a" * 40,
        first_seen_cycle=2,
        last_seen_cycle=3,
        state=IncidentState.REJECTED,
    )
    summary = MaintenanceSummary(
        project="demo",
        cycle=4,
        baseline_recorded=True,
        running_cycle=False,
        open_gates=0,
        ack_unattended_build_probe=False,
    )
    client = _QueryClient([terminal], summary)
    assert _run(["incidents", "demo", "--all"], client, capsys) == 0
    out = capsys.readouterr().out
    assert "INC-2" in out
    client2 = _QueryClient([terminal], summary)
    assert _run(["incidents", "demo"], client2, capsys) == 0
    assert "INC-2" not in capsys.readouterr().out


def test_incidents_state_prints_the_summary(capsys):
    from sdlc.maintenance.models import MaintenanceSummary

    summary = MaintenanceSummary(
        project="demo",
        cycle=7,
        baseline_recorded=True,
        running_cycle=False,
        open_gates=2,
        not_collected_streak={"secrets": 1},
        ack_unattended_build_probe=True,
    )
    client = _QueryClient([], summary)
    assert _run(["incidents", "demo", "--state"], client, capsys) == 0
    out = capsys.readouterr().out
    assert "cycle 7" in out
    assert "open_gates" in out or "open gates" in out.lower()
    assert "ack" in out.lower()
