"""F2 doctor: binaries and git identity (spec section 5 rows 4-7, section 6).

Row 5 is the headline check. An unresolvable committer identity makes every
checkpoint commit fail, and stages/code/activities.py:197-202 swallows that
failure with no raise and no log -- so commit_sha stays None and the C2
test-freeze anchor never advances (freeze.py:46-51).
"""

from pathlib import Path

from sdlc.doctor import checks
from sdlc.doctor.models import Status


class _Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- rows 4 and 6: binaries on PATH -----------------------------------------


def test_git_present_reports_pass_with_the_version(monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda c: "/usr/bin/git")
    monkeypatch.setattr(
        checks.subprocess, "run", lambda *a, **k: _Completed(stdout="git version 2.47.1")
    )
    r = checks.check_git_binary()
    assert r.status is Status.PASS
    assert "2.47.1" in r.detail


def test_git_absent_reports_fail(monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda c: None)
    r = checks.check_git_binary()
    assert r.status is Status.FAIL
    assert "not on PATH" in r.detail


def test_gh_absent_reports_fail_and_names_the_late_failure(monkeypatch):
    """gh is checked inside open_pull_request (merge/activities.py:219) --
    the LAST step of a run, after every gate is green."""
    monkeypatch.setattr(checks.shutil, "which", lambda c: None)
    r = checks.check_gh_binary()
    assert r.status is Status.FAIL
    assert "pull request" in r.detail.lower()


def test_gh_absent_tells_benchmark_operators_they_may_ignore_it(monkeypatch):
    """Benchmark runs have no remote and skip the PR step outright
    (merge/step.py:521). FAIL is right for the default path, but the detail
    must say who may ignore it -- doctor models no profile (spec section 8)."""
    monkeypatch.setattr(checks.shutil, "which", lambda c: None)
    assert "benchmark" in checks.check_gh_binary().detail.lower()


# --- row 5: git committer identity ------------------------------------------


def test_identity_resolves_reports_pass(monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda c: "/usr/bin/git")
    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *a, **k: _Completed(stdout="A Dev <dev@example.com> 1789075726 +0200"),
    )
    r = checks.check_git_identity()
    assert r.status is Status.PASS
    assert "dev@example.com" in r.detail


def test_identity_unresolvable_reports_fail_naming_the_silent_consequence(monkeypatch):
    """git var exits 128 with its own 'Please tell me who you are' text."""
    monkeypatch.setattr(checks.shutil, "which", lambda c: "/usr/bin/git")
    monkeypatch.setattr(
        checks.subprocess,
        "run",
        lambda *a, **k: _Completed(
            returncode=128, stderr="fatal: unable to auto-detect email address"
        ),
    )
    r = checks.check_git_identity()
    assert r.status is Status.FAIL
    assert "auto-detect email address" in r.detail
    assert "silently" in r.detail.lower()
    assert "anchor" in r.detail.lower()


def test_identity_probe_runs_outside_any_repository(monkeypatch):
    """A repo-local identity in THIS checkout proves nothing about a run: the
    task worktree carries the TARGET repo's config (vcs/worktree.py:150-165).
    Running outside a repo resolves the system + global + env layers a fresh
    clone inherits -- so the probe's cwd must not be a git repository."""
    seen = {}

    def _run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["cwd"] = kwargs.get("cwd")
        return _Completed(stdout="A Dev <dev@example.com> 1 +0000")

    monkeypatch.setattr(checks.shutil, "which", lambda c: "/usr/bin/git")
    monkeypatch.setattr(checks.subprocess, "run", _run)
    checks.check_git_identity()
    assert seen["cmd"][1:] == ["var", "GIT_COMMITTER_IDENT"]
    assert seen["cwd"] is not None
    assert not (Path(seen["cwd"]) / ".git").exists()


def test_identity_skips_when_git_is_absent(monkeypatch):
    """Row 4 already reports the missing binary; row 5 must not repeat it as
    a second FAIL for the same cause."""
    monkeypatch.setattr(checks.shutil, "which", lambda c: None)
    r = checks.check_git_identity()
    assert r.status is Status.SKIP
    assert "git is not on PATH" in r.detail


def test_identity_survives_a_git_that_will_not_execute(monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda c: "/usr/bin/git")

    def _boom(*a, **k):
        raise OSError("Exec format error")

    monkeypatch.setattr(checks.subprocess, "run", _boom)
    r = checks.check_git_identity()
    assert r.status is Status.FAIL
    assert "Exec format error" in r.detail


# --- row 7: GH_TOKEN --------------------------------------------------------


def test_gh_token_real_value_reports_pass(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_realtokenvalue123")
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    assert checks.check_gh_token().status is Status.PASS


def test_gh_token_unset_reports_fail(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr(checks, "parse_env_example", lambda: {})
    r = checks.check_gh_token()
    assert r.status is Status.FAIL
    assert "not set" in r.detail


def test_gh_token_placeholder_reports_fail(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "your-github-token")
    monkeypatch.setattr(checks, "parse_env_example", lambda: {"GH_TOKEN": "your-github-token"})
    r = checks.check_gh_token()
    assert r.status is Status.FAIL
    assert ".env.example" in r.detail
