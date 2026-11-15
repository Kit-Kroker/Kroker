"""Fixture git repo and ``RepoTriage`` builders for the maintenance tier (023a T003).

Two halves, both deterministic:

* **The fixture git repo** is a real work tree with a genuinely valid little
  Python package, so the CLI's enable-time git check and the SC-002 no-write
  asserts (``git for-each-ref`` / ``git worktree list`` / HEAD) have something
  real to bite on. The fault helpers commit a build break, a committed ``.env``
  (the MECHANICAL secret half) and a provider-credential line (JUDGEMENT).
* **The RepoTriage builder** exists because the workflow tier runs with
  ``advisory_source=none`` (no OSV egress in tests), so advisory faults are
  exercised at the pure tier: findings per signal, collected/not-collected,
  and signal versions, with a helper seeding a critical advisory finding.

The workflow tier never actually probes the fixture repo -- each test fakes
the triage activities and keys their canned findings off the faults committed
here, which keeps every cycle seconds-long and hermetic.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from temporalio import activity

from sdlc.maintenance.models import RepairProposal
from sdlc.measurement import Measurement
from sdlc.notify.contract import NotifyInput, Results
from sdlc.triage.models import (
    FixClass,
    Readiness,
    RepoTriage,
    SignalResult,
    TriageFinding,
    Verdict,
)
from sdlc.triage.signals import build_probe, dependencies, secrets

# The three detect signals, in a stable order (identities sort anyway, but a
# deterministic builder makes failures easier to eyeball).
DETECT_ORDER: tuple[str, ...] = (
    build_probe.SIGNAL_ID,
    dependencies.SIGNAL_ID,
    secrets.SIGNAL_ID,
)

DEFAULT_VERSIONS: dict[str, int] = {
    build_probe.SIGNAL_ID: build_probe.VERSION,
    dependencies.SIGNAL_ID: dependencies.VERSION,
    secrets.SIGNAL_ID: secrets.VERSION,
}

_READY = Readiness(
    buildable=Measurement.measured(1.0),
    runnable=Measurement.measured(1.0),
    tests_present=Measurement.measured(1.0),
    structure_discernible=Measurement.measured(1.0),
    verdict=Verdict.READY,
)

_PYPROJECT = """\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "fixture-pkg"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]
"""


# --------------------------------------------------------------------------
# the fixture git repo
# --------------------------------------------------------------------------


def git(repo: Path, *args: str) -> str:
    """Run git in the fixture repo; raise with stderr on any failure."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def head_sha(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def make_repo(tmp_path: Path) -> Path:
    """A tmp git work tree with a passing build: setuptools package, one
    function, one test. Every helper below commits to it on ``main``."""
    repo = tmp_path / "fixture-repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Fixture Repo")
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    pkg = repo / "src" / "fixture_pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_add.py").write_text(
        "from fixture_pkg import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(".venv/\n__pycache__/\n", encoding="utf-8")
    git(repo, "add", "pyproject.toml", "src", "tests", ".gitignore")
    git(repo, "commit", "-m", "fixture: passing build")
    return repo


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def commit_build_break(repo: Path) -> str:
    """A syntax error in the package: the probe's ``build_failed`` cause."""
    (repo / "src" / "fixture_pkg" / "__init__.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a +  # build break\n", encoding="utf-8"
    )
    git(repo, "add", "src")
    git(repo, "commit", "-m", "break the build")
    return head_sha(repo)


def commit_env_file(repo: Path) -> str:
    """A committed ``.env``: the MECHANICAL half is ``env_file_tracked``
    (gitignore it, remove from index); ``secret_committed`` is its JUDGEMENT
    twin (rotation). Mirrors ``signals/secrets.py::env_file_findings``."""
    (repo / ".env").write_text("API_TOKEN=0123456789abcdef0123\n", encoding="utf-8")
    git(repo, "add", ".env")
    git(repo, "commit", "-m", "commit a .env")
    return head_sha(repo)


def commit_provider_credential(repo: Path) -> str:
    """A committed AWS access key id: ``aws_access_key_id``, critical and
    JUDGEMENT -- rotation is a human act (``signals/secrets.py`` D7)."""
    conf = repo / "config"
    conf.mkdir(exist_ok=True)
    (conf / "settings.ini").write_text(
        "[default]\naws_access_key_id = AKIAIOSFODNN7EXAMPLE\n", encoding="utf-8"
    )
    git(repo, "add", "config")
    git(repo, "commit", "-m", "commit a provider credential")
    return head_sha(repo)


# --------------------------------------------------------------------------
# findings that mirror what the real signals emit for the faults above
# --------------------------------------------------------------------------


def build_break_finding() -> TriageFinding:
    return TriageFinding(
        signal=build_probe.SIGNAL_ID,
        rule="build_failed",
        severity="critical",
        detail="Build failed (exit 1). fixture: syntax error.",
        fix_class=FixClass.JUDGEMENT,
    )


def env_file_findings() -> list[TriageFinding]:
    """Both halves of spec D7, identity-compatible with env_file_findings."""
    return [
        TriageFinding(
            signal=secrets.SIGNAL_ID,
            rule="secret_committed",
            severity="critical",
            detail=".env is committed. Every value in it must be treated as disclosed and rotated.",
            fix_class=FixClass.JUDGEMENT,
            path=".env",
        ),
        TriageFinding(
            signal=secrets.SIGNAL_ID,
            rule="env_file_tracked",
            severity="high",
            detail=".env is tracked; add it to .gitignore and remove it from the index.",
            fix_class=FixClass.MECHANICAL,
            path=".gitignore",
        ),
    ]


def credential_finding(path: str = "config/settings.ini") -> TriageFinding:
    return TriageFinding(
        signal=secrets.SIGNAL_ID,
        rule="aws_access_key_id",
        severity="critical",
        detail="AWS access key id committed to the repository. Rotate the "
        "credential; deleting the file does not revoke it.",
        fix_class=FixClass.JUDGEMENT,
        path=path,
        line=2,
        evidence="aws_access_key_id = AKIAIOSFODNN7EXAMPLE",
        key="d4a3a2b1",  # stand-in for evidence_key(); identity stability is what matters
    )


def critical_advisory(
    package: str = "requests", advisory_id: str = "GHSA-0000-0000-0000"
) -> TriageFinding:
    """A critical ``known_vulnerable`` advisory, shaped exactly like
    ``signals/dependencies.py`` emits it (JUDGEMENT, key=<pkg>:<id>)."""
    return TriageFinding(
        signal=dependencies.SIGNAL_ID,
        rule="known_vulnerable",
        severity="critical",
        detail=f"{package} matches {advisory_id}: fixture advisory.",
        path="pyproject.toml",
        line=8,
        evidence=f'{package}=="2.0.0"',
        fix_class=FixClass.JUDGEMENT,
        key=f"{package}:{advisory_id}",
    )


# --------------------------------------------------------------------------
# the RepoTriage builder
# --------------------------------------------------------------------------


def make_triage(
    findings: dict[str, list[TriageFinding]] | None = None,
    *,
    not_collected: Iterable[str] = (),
    versions: dict[str, int] | None = None,
    commit_sha: str = "f" * 40,
    repo_dir: str = "/fixture/repo",
) -> RepoTriage:
    """A filtered triage over the three detect signals, all MEASURED with no
    findings unless a test says otherwise. ``not_collected`` takes signal ids;
    ``versions`` overrides the real signal versions (for re-baseline tests)."""
    per_signal = findings or {}
    nc = set(not_collected)
    v = {**DEFAULT_VERSIONS, **(versions or {})}
    signals = [
        SignalResult(
            signal=sig,
            version=v[sig],
            collected=(
                Measurement.not_collected(f"{sig}: did not collect")
                if sig in nc
                else Measurement.measured(float(len(per_signal.get(sig, []))))
            ),
            findings=[] if sig in nc else list(per_signal.get(sig, [])),
        )
        for sig in DETECT_ORDER
    ]
    return RepoTriage(
        repo_dir=repo_dir,
        commit_sha=commit_sha,
        toolchain="python",
        readiness=_READY,
        signals=signals,
    )


# --------------------------------------------------------------------------
# 023b T003: fix builders for the stub repair child, and the worker helper
# --------------------------------------------------------------------------

# Same marker the build-probe fake keys on (fake_triage.BREAK_MARKER); kept
# here so the fix builders stay a conftest-only concern.
_BREAK_MARKER = "build break"

_PASSING_INIT = "def add(a: int, b: int) -> int:\n    return a + b\n"


def seeded_findings(repo: Path) -> list[TriageFinding]:
    """The faults currently seeded in the fixture repo, as findings, in a
    stable order (build break, .env pair, provider credential). The stub's
    ``fix:`` script fixes exactly these."""
    out: list[TriageFinding] = []
    init = repo / "src" / "fixture_pkg" / "__init__.py"
    if init.exists() and _BREAK_MARKER in init.read_text(encoding="utf-8"):
        out.append(build_break_finding())
    tracked = set(git(repo, "ls-files").split())
    if ".env" in tracked:
        out.extend(env_file_findings())
    if "config/settings.ini" in tracked:
        out.append(credential_finding())
    return out


def fix_commit(repo: Path, finding: TriageFinding) -> str:
    """Commit THE fix for one seeded finding on ``repo`` (the integration
    worktree). Returns the new head. No-op commit-free when already fixed."""
    if finding.rule == "build_failed":
        init = repo / "src" / "fixture_pkg" / "__init__.py"
        if _BREAK_MARKER not in init.read_text(encoding="utf-8"):
            return head_sha(repo)
        init.write_text(_PASSING_INIT, encoding="utf-8")
        git(repo, "add", "src")
        git(repo, "commit", "-m", "fix: restore the return expression")
    elif finding.rule in ("env_file_tracked", "secret_committed"):
        tracked = set(git(repo, "ls-files").split())
        if ".env" not in tracked:
            return head_sha(repo)
        gitignore = repo / ".gitignore"
        ignore = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        if ".env" not in ignore.split():
            gitignore.write_text(ignore + ".env\n", encoding="utf-8")
            git(repo, "add", ".gitignore")
        git(repo, "rm", "--cached", "--quiet", ".env")
        git(repo, "commit", "-m", "fix: untrack .env")
    elif finding.rule == "aws_access_key_id":
        tracked = set(git(repo, "ls-files").split())
        if "config/settings.ini" not in tracked:
            return head_sha(repo)
        git(repo, "rm", "--quiet", "config/settings.ini")
        git(repo, "commit", "-m", "fix: remove the committed provider credential")
    else:  # pragma: no cover - the fixture seeds no other rule
        raise AssertionError(f"no fix builder for rule {finding.rule!r}")
    return head_sha(repo)


def nonfix_commit(repo: Path) -> str:
    """A real commit that fixes nothing: the ``nofix:`` script's payload."""
    notes = repo / "NOTES.md"
    notes.write_text(
        (notes.read_text(encoding="utf-8") if notes.exists() else "") + "non-fix note\n",
        encoding="utf-8",
    )
    git(repo, "add", "NOTES.md")
    git(repo, "commit", "-m", "non-fix: touch notes")
    return head_sha(repo)


@activity.defn(name="notify")
async def fake_notify(inp: NotifyInput) -> Results:
    """Delivery-free notify: every route reports success-with-nothing."""
    return Results(results=[])


# The 023b maintenance activities, as they land: is_ancestor and
# remove_verification_tree join at T012, probe_repair_child at T014.
# (Extended by their tasks; never smuggled in from elsewhere.)
MAINT_023B_ACTIVITIES: list = []


@asynccontextmanager
async def maint_worker(
    env,
    *,
    task_queue: str,
    proposal: RepairProposal,
    extra_activities: Sequence[object] = (),
    extra_workflows: Sequence[type] = (),
    max_cached_workflows: int | None = None,
):
    """The 023b workflow-tier worker (T003): ``MaintenanceWorkflow``,
    ``TriageWorkflow`` and the stub repair child registered under the real
    ``GraphWorkflow`` wire name, plus every activity the execute paths
    touch — triage fakes, the maintainer fake producing ``proposal``, the
    notify fake, the vcs activities, the stub's own activities and the 023b
    maintenance activities. ``extra_activities`` carries per-test fakes."""
    from temporalio.worker import Worker

    from sdlc.agents.runner import SdlcPydanticAIPlugin
    from sdlc.vcs import build_verification_branch, setup_integration_branch
    from sdlc.workflows.maintenance import MaintenanceWorkflow
    from sdlc.workflows.triage import TriageWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

    from .fake_triage import TRIAGE_ACTIVITIES
    from .stub_child import STUB_ACTIVITIES, StubRepairChild

    kwargs: dict = {}
    if max_cached_workflows is not None:
        kwargs["max_cached_workflows"] = max_cached_workflows
    async with Worker(
        env.client,
        task_queue=task_queue,
        workflows=[MaintenanceWorkflow, TriageWorkflow, StubRepairChild, *extra_workflows],
        plugins=[SdlcPydanticAIPlugin()],
        activities=[
            *TRIAGE_ACTIVITIES,
            *fake_agent_activities([("maintainer_agent", RepairProposal, proposal)]),
            fake_notify,
            setup_integration_branch,
            build_verification_branch,
            *STUB_ACTIVITIES,
            *MAINT_023B_ACTIVITIES,
            *extra_activities,
        ],
        **kwargs,
    ):
        yield
