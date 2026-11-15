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


# =========================================================================== #
# ## post-hoc QA audit (qa-chaos, 2026-11-15)
#
# FINDING (see report): the executor's test_enable_invalid_config_refused_exit_1
# passed tmp_path — NOT a git repo — as --repo, so it exits 1 at the git-tree
# check and never reaches MaintenanceConfig validation. The bullet it claims
# to pin ("enable validates MaintenanceConfig") had no working refusal test.
# The tests below put a VALID git repo under an invalid config; contracts/
# cli.md says that is exit 1 with a one-line reason on stderr.
# =========================================================================== #


@pytest.mark.parametrize(
    "project,extra",
    [
        ("Demo", ["--no-build-probe"]),  # uppercase: regex refusal
        ("demo", ["--no-build-probe", "--threshold", "0.4"]),  # below the 0.5 bound
    ],
    ids=["bad-project", "bad-threshold"],
)
def test_enable_with_an_invalid_config_on_a_valid_git_repo_refuses_exit_1(
    repo_dir, capsys, project, extra
):
    client = _FakeClient()
    code = _run(["enable", project, "--repo", str(repo_dir), *extra], client, capsys)
    assert code == 1  # contracts/cli.md: a refused operation, not a traceback
    assert not client.start_workflow.started
    err = capsys.readouterr().err.strip()
    assert err, "a refusal carries a one-line reason on stderr"
    assert len(err.splitlines()) == 1


def test_incidents_on_a_not_enabled_project_is_refused_exit_1(capsys):
    class _DeadHandle:
        async def query(self, name, **kw):  # noqa: ANN001
            raise RuntimeError("workflow not found: maint-ghost")

    class _DeadClient:
        def get_workflow_handle(self, wid):  # noqa: ANN001
            return _DeadHandle()

    assert _run(["incidents", "ghost"], _DeadClient(), capsys) == 1
    assert "not enabled" in capsys.readouterr().err


# =========================================================================== #
# ## T030 happy path (023a, qa-happy, RED): nudge / disable verbs and the
# schedule sample. Every test here fails today: src/sdlc/maintenance/cli.py
# has no nudge or disable verb, so argparse exits 2 before run_maintain runs.
# Contract: contracts/cli.md (nudge / disable rows); FR-003/004/018.
# =========================================================================== #


class _SignalHandle:
    """Records every signal name sent to a maint-<p> handle."""

    def __init__(self, sink: list[tuple[str, str]], wid: str, error: Exception | None = None):
        self._sink = sink
        self._wid = wid
        self._error = error

    async def signal(self, name, *args, **kw):  # noqa: ANN001, ARG002
        if self._error is not None:
            raise self._error
        self._sink.append((self._wid, name))


class _SignalClient:
    """get_workflow_handle(wid) returns a handle that records signals."""

    def __init__(self, *, error: Exception | None = None):
        self.signals: list[tuple[str, str]] = []
        self._error = error

    def get_workflow_handle(self, wid):  # noqa: ANN001
        return _SignalHandle(self.signals, wid, self._error)


def test_nudge_signals_the_maint_workflow_and_exits_0(capsys):
    client = _SignalClient()
    assert _run(["nudge", "demo"], client, capsys) == 0
    assert client.signals == [("maint-demo", "nudge")]
    assert "demo" in capsys.readouterr().out


def test_disable_signals_the_maint_workflow_and_exits_0(capsys):
    client = _SignalClient()
    assert _run(["disable", "demo"], client, capsys) == 0
    assert client.signals == [("maint-demo", "disable")]
    assert "disabling maint-demo" in capsys.readouterr().out


def test_nudge_on_a_not_enabled_project_exits_1_with_the_contract_message(capsys):
    client = _SignalClient(error=RuntimeError("workflow not found: maint-ghost"))
    assert _run(["nudge", "ghost"], client, capsys) == 1
    assert "not enabled: ghost" in capsys.readouterr().err


def test_disable_on_a_not_enabled_project_exits_1_with_the_contract_message(capsys):
    client = _SignalClient(error=RuntimeError("workflow not found: maint-ghost"))
    assert _run(["disable", "ghost"], client, capsys) == 1
    assert "not enabled: ghost" in capsys.readouterr().err


def test_maint_example_sample_exists_and_is_not_loaded_as_a_schedule():
    from pathlib import Path

    from sdlc.schedules.loader import load_schedules

    schedules = Path(__file__).resolve().parents[2] / "schedules"
    sample = schedules / "maint-example.yaml.sample"
    assert sample.is_file(), "the maintenance schedule sample must ship with the repo"

    # The loader globs *.yaml, so the .sample must never be parsed as an asset.
    assets = load_schedules(schedules)
    assert [a.id for a in assets] == ["nightly-reflect"]


# =========================================================================== #
# ## chaos: nudge/disable edges (023a T030, RED) -- qa-chaos
#
# Happy paths and the not-enabled substring live above (qa-happy). Everything
# here is adversarial: signal-level failures, argument-shape refusals, the
# one-line stderr contract on exit 1, the stateless-shell rule, and the
# sample's content (not just its existence). Each test fails today because
# the verbs are not registered (argparse exit 2) or the sample is absent.
# =========================================================================== #


class _StrictSignalClient(_SignalClient):
    """A signal client that also records any start_workflow call, so a verb
    that quietly STARTS a workflow instead of signalling one is caught."""

    def __init__(self, *, error: Exception | None = None):
        super().__init__(error=error)
        self.start_workflow = _FakeStart()


@pytest.mark.parametrize("verb", ["nudge", "disable"])
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(TimeoutError("signal timed out after 30s"), id="timeout"),
        pytest.param(RuntimeError("connection reset by peer"), id="generic"),
    ],
)
def test_signal_failure_exits_1_with_one_stderr_line_and_no_traceback(verb, error, capsys):
    # contracts/cli.md: exit 1 is a refused operation with a ONE-LINE reason.
    # A transport failure mid-signal must not escape as a traceback.
    client = _StrictSignalClient(error=error)
    code = _run([verb, "demo"], client, capsys)
    assert code == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1
    assert client.start_workflow.started == []


@pytest.mark.parametrize("verb", ["nudge", "disable"])
def test_a_failing_handle_lookup_exits_1_not_a_traceback(verb, capsys):
    class _ExplodingClient:
        start_workflow = _FakeStart()

        def get_workflow_handle(self, wid):  # noqa: ANN001, ARG002
            raise ConnectionError("temporal frontend unreachable")

    code = _run([verb, "demo"], _ExplodingClient(), capsys)
    assert code == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert len(captured.err.strip().splitlines()) == 1


@pytest.mark.parametrize("verb", ["nudge", "disable"])
def test_signal_verbs_never_start_a_workflow(verb, capsys):
    # contracts/cli.md + FR-604: every verb is a stateless shell over an
    # EXISTING workflow. Only `enable` may start maint-<p>.
    client = _StrictSignalClient()
    assert _run([verb, "demo"], client, capsys) == 0
    assert client.start_workflow.started == []


@pytest.mark.parametrize("verb", ["nudge", "disable"])
def test_not_enabled_refusal_is_exactly_one_stderr_line(verb, capsys):
    # contracts/cli.md: the refusal carries a one-line reason. qa-happy pins
    # the substring; this pins the single-line shape.
    client = _SignalClient(error=RuntimeError("workflow not found: maint-ghost"))
    assert _run([verb, "ghost"], client, capsys) == 1
    err = capsys.readouterr().err
    assert len(err.strip().splitlines()) == 1
    assert "Traceback" not in err


@pytest.mark.parametrize("verb", ["nudge", "disable"])
def test_signal_verbs_take_exactly_one_project_argument(verb):
    # contracts/cli.md: `<project>` is the single positional. The valid parse
    # is asserted first, so this fails today (verb unregistered) rather than
    # passing on argparse's generic "invalid choice" exit 2.
    assert _args([verb, "demo"]).project == "demo"
    for bad in (
        [verb],  # no project
        [verb, "demo", "extra"],  # a second positional
        [verb, "demo", "--gate-policy", "off"],  # gate flags do not exist (R9)
        [verb, "demo", "--on-timeout", "approve"],
    ):
        with pytest.raises(SystemExit) as exc:
            _args(bad)
        assert exc.value.code == 2, f"argv {bad!r} must be a usage error"


def test_maint_example_sample_parses_as_yaml_and_kicks_maintenance():
    # qa-happy checks the sample exists and is not loaded. The copy-paste
    # promise is stronger: a human who uncomments or copies it gets valid
    # YAML naming the kick workflow (T030, FR-003/R10).
    from pathlib import Path

    import yaml

    sample = Path(__file__).resolve().parents[2] / "schedules" / "maint-example.yaml.sample"
    data = yaml.safe_load(sample.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "the sample must parse to a mapping, not be all comments"
    assert data["action"]["workflow"] == "MaintenanceKickWorkflow"
