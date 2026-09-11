"""F2 doctor: the twelve checks and the CHECKS registry (spec section 5).

Every check returns a CheckResult and NEVER raises -- a check owns its own
failure modes, so run_doctor needs no rescue wrapper that would swallow the
next check's bug into a generic message (SG-3).

Doctor is READ-ONLY. No function here creates, writes, moves, or deletes
anything. Two traps worth naming because the obvious implementation trips
them: board.schema.connect() makes directories and the sqlite file
(board/schema.py:162-174), so row 9 uses os.access instead; and `git var`
must not be handed a directory doctor created for the purpose.

Names are module-level so tests can monkeypatch the UPSTREAM function rather
than the rule -- doctor owns no second copy of any rule (spec section 3).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile

from sdlc.agents.loader import RegistryError, load_registry, validate_registry
from sdlc.crew.loader import CrewConfigError, crew_dir, validate_crew_clis
from sdlc.harness.containment import ContainmentError, load_policy
from sdlc.harness.registry import HARNESSES, check_harness_versions
from sdlc.notify.routes import NotifyConfigError, load_routes

from .env import classify_key, parse_env_example
from .models import CheckResult

# Import only what THIS task's code uses -- ruff's select includes F401
# (pyproject.toml:60), so an import staged for a later task fails this task's
# own lint step. Tasks 4 and 5 each add their own.


def _crew_layouts_present() -> bool:
    """validate_crew_clis returns early and silently when there are no crew
    assets (crew/loader.py:210-211). Doctor must render that as SKIP, not
    PASS, so it asks the same question separately."""
    root = crew_dir()
    return root is not None and (root / "layouts").is_dir()


def _pinned_harness_clis_on_path() -> list[str]:
    """Which harness CLIs check_harness_versions actually examined. It skips
    an absent or unpinned CLI silently (harness/registry.py:33-37); when it
    examined none, an empty drift list means 'nothing checked', not 'clean'."""
    return [
        h.cli
        for h in HARNESSES.values()
        if h.expected_version and h.cli and shutil.which(h.cli) is not None
    ]


def check_agents_registry() -> CheckResult:
    """Row 1. Delegates to the boot validator (agents/loader.py:210,276)."""
    name = "agents registry"
    try:
        roles = load_registry()
        validate_registry(roles)
    except RegistryError as e:
        return CheckResult.fail(name, f"{e} (first error only; re-run doctor after fixing)")
    except Exception as e:  # noqa: BLE001 -- a check never raises (SG-3)
        return CheckResult.fail(name, f"could not load the registry: {e}")
    return CheckResult.ok(name, f"{len(roles)} roles; ADR-6 family inequality holds")


def check_crew_clis() -> CheckResult:
    """Row 2. Delegates to crew/loader.py:195."""
    name = "crew CLIs"
    try:
        if not _crew_layouts_present():
            return CheckResult.skip(name, "no crew/layouts in this checkout")
        validate_crew_clis()
    except CrewConfigError as e:
        return CheckResult.fail(name, str(e))
    except Exception as e:  # noqa: BLE001
        return CheckResult.fail(name, f"could not validate crew layouts: {e}")
    return CheckResult.ok(name, "every layout role's CLI is on PATH")


def check_harness_drift() -> CheckResult:
    """Row 3. Reads the findings check_harness_versions returns (RULING 1)."""
    name = "harness versions"
    try:
        examined = _pinned_harness_clis_on_path()
        if not examined:
            return CheckResult.skip(
                name, "pinned harness CLIs are not on PATH; nothing was checked"
            )
        drifts = check_harness_versions()
    except Exception as e:  # noqa: BLE001
        return CheckResult.warn(name, f"could not check harness versions: {e}")
    if drifts:
        return CheckResult.warn(name, "; ".join(drifts))
    return CheckResult.ok(name, f"{', '.join(examined)} match their pins")


def check_containment_policy() -> CheckResult:
    """Row 11. WARN, not FAIL (RULING 2): containment_enabled defaults False
    (core/models.py:377), so a malformed asset is named without blocking an
    operator whose setup is otherwise sound."""
    name = "containment policy"
    try:
        policy = load_policy()
    except ContainmentError as e:
        return CheckResult.warn(name, str(e))
    except Exception as e:  # noqa: BLE001
        return CheckResult.warn(name, f"could not load the containment policy: {e}")
    return CheckResult.ok(name, f"parses (v{policy.version}, {len(policy.rules)} rules)")


def check_notify_routes() -> CheckResult:
    """Row 12. WARN for the same reason as row 11 (RULING 2): the shipped
    policy/notifications.yaml routes everything to `log`."""
    name = "notify routes"
    try:
        routes = load_routes()
    except NotifyConfigError as e:
        return CheckResult.warn(name, str(e))
    except Exception as e:  # noqa: BLE001
        return CheckResult.warn(name, f"could not load the notification routes: {e}")
    return CheckResult.ok(name, f"parses (v{routes.version})")


# Resolved once at import -- see check_git_identity on why not per call.
_TEMPDIR = tempfile.gettempdir()

_BENCHMARK_NOTE = (
    "benchmark-only operators may ignore this: a benchmark run has no remote "
    "and skips the PR step (merge/step.py:521)"
)


def _version_of(path: str) -> str:
    """First line of `<binary> --version`, or "" if it will not run. Never
    raises: a version string is decoration, not the verdict."""
    try:
        out = subprocess.run(
            [path, "--version"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (out.stdout or "").strip().splitlines()[0] if out.stdout else ""


def check_git_binary() -> CheckResult:
    """Row 4. Every worktree, checkout and diff in the pipeline shells out to
    git (vcs/git.py:41)."""
    name = "git"
    path = shutil.which("git")
    if path is None:
        return CheckResult.fail(name, "git is not on PATH; the pipeline cannot create a worktree")
    return CheckResult.ok(name, _version_of(path) or f"found at {path}")


def check_git_identity() -> CheckResult:
    """Row 5, the headline check (spec section 1 and section 6).

    `git var GIT_COMMITTER_IDENT` is git's OWN resolution, so no rule is
    duplicated. It runs with cwd OUTSIDE any repository on purpose: a
    repo-local identity in this checkout proves nothing about a run, because
    `git worktree add` gives the task worktree the TARGET repo's config
    (vcs/worktree.py:150-165). Outside a repo, git resolves exactly the
    system + global + env layers a freshly cloned target inherits.

    Honest limit (spec section 6): on a host with a resolvable hostname git
    may auto-detect a junk identity and exit 0. This proves an identity can
    be PRODUCED, not that it is the right one.
    """
    name = "git identity"
    path = shutil.which("git")
    if path is None:
        return CheckResult.skip(name, "git is not on PATH (see the git check)")
    # _TEMPDIR is resolved once at import, not per call: CPython's
    # gettempdir() may create and immediately delete a probe file on its
    # first call in a process (tempfile._get_default_tempdir). That is
    # outside any tree doctor diagnoses and is gone before the call returns,
    # but hoisting it keeps the per-check path free of it entirely.
    try:
        out = subprocess.run(
            [path, "var", "GIT_COMMITTER_IDENT"],
            cwd=_TEMPDIR,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return CheckResult.fail(name, f"could not run `git var GIT_COMMITTER_IDENT`: {e}")
    if out.returncode != 0:
        detail = (out.stderr or out.stdout or "").strip().splitlines()
        first = next((ln for ln in detail if ln.startswith("fatal:")), detail[-1] if detail else "")
        return CheckResult.fail(
            name,
            f"no committer identity ({first}). Every checkpoint commit will "
            f"fail SILENTLY -- the failure is swallowed at "
            f"stages/code/activities.py:197-202 -- so commit_sha stays None "
            f"and the C2 test-freeze anchor never advances. Set user.email "
            f"and user.name globally.",
        )
    return CheckResult.ok(name, (out.stdout or "").strip())


def check_gh_binary() -> CheckResult:
    """Row 6. gh is checked inside open_pull_request (merge/activities.py:219)
    -- the last step of a run, after every gate is green."""
    name = "gh"
    path = shutil.which("gh")
    if path is None:
        return CheckResult.fail(
            name,
            f"gh is not on PATH; a run reaches the pull request step with "
            f"every gate green and then fails. {_BENCHMARK_NOTE}",
        )
    return CheckResult.ok(name, _version_of(path) or f"found at {path}")


def check_gh_token() -> CheckResult:
    """Row 7. Presence and placeholder only -- never `gh auth status`, which
    is a live call to GitHub (spec section 5, 'not in scope')."""
    name = "GH_TOKEN"
    usable, reason = classify_key("GH_TOKEN", shipped=parse_env_example())
    if not usable:
        return CheckResult.fail(name, f"{reason}. {_BENCHMARK_NOTE}")
    return CheckResult.ok(name, "set")
