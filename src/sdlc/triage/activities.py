"""E-41 signal activities (FR-902). One activity per signal, deliberately:
a signal that crashes or times out yields not_collected for ITSELF while every
other signal still reports (spec D3).

Findings are read from the pinned commit through git, never from the working
checkout (spec D6): a gitignored local .env cannot produce a false positive,
untracked build output produces no noise, and every evidence citation is true
against path@sha by construction.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass

from temporalio import activity

from ..activities import _bounded_shell, _git
from ..grounding import Profile, verify_quote
from ..measurement import Measurement
from ..toolchain.adapters import detect_with_marker, detect_with_marker_from_paths
from .models import SignalResult
from .signals import baseline, build_probe, secrets

_log = logging.getLogger(__name__)


@dataclass
class TriageSignalInput:
    repo_dir: str
    commit_sha: str


def tracked_paths(repo_dir: str, commit_sha: str) -> list[str]:
    """Repo-relative posix paths tracked at commit_sha. Raises RuntimeError
    when the sha does not resolve -- the activity turns that into
    not_collected, which is the only honest report for a tree we cannot read."""
    proc = _git(["ls-tree", "-r", "--name-only", commit_sha], cwd=repo_dir)
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-tree failed for {commit_sha}: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def read_blob(repo_dir: str, commit_sha: str, path: str) -> str | None:
    """The file's bytes at the pinned commit, or None when the path does not
    resolve to a blob. Mirrors activities.read_committed_bytes -- same `git
    cat-file -t` guard, because `git show sha:dir` exits 0 with a tree
    listing, which is not the file's bytes."""
    ref = f"{commit_sha}:{path}"
    kind = _git(["cat-file", "-t", ref], cwd=repo_dir)
    if kind.returncode != 0 or kind.stdout.strip() != "blob":
        return None
    proc = _git(["show", ref], cwd=repo_dir)
    return proc.stdout if proc.returncode == 0 else None


@activity.defn
async def triage_baseline(inp: TriageSignalInput) -> SignalResult:
    """FR-902 baseline practice. Never raises: an unreadable tree is a
    not_collected report, not a failed triage."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        gitignore = ""
        if ".gitignore" in paths:
            gitignore = read_blob(inp.repo_dir, inp.commit_sha,
                                  ".gitignore") or ""
        found = detect_with_marker_from_paths(paths)
        return baseline.evaluate(paths, gitignore,
                                 found[0] if found else None)
    except Exception as exc:                       # noqa: BLE001 -- see docstring
        _log.warning("triage baseline signal failed: %s", exc)
        return SignalResult(
            signal=baseline.SIGNAL_ID, version=baseline.VERSION,
            collected=Measurement.not_collected(
                f"baseline signal raised: {type(exc).__name__}: {exc}"))


@activity.defn
async def triage_secrets(inp: TriageSignalInput) -> SignalResult:
    """FR-902 secret scan over the tracked tree at the pinned commit.

    Every emitted finding's evidence is re-verified against the bytes it cites
    (spec D5). For these deterministic rules the quote is verbatim by
    construction, so this is a DRIFT guard -- it catches a citation that no
    longer resolves at that path and sha -- not a hallucination guard. It
    becomes load-bearing when E-48's LLM proposers cite the same way, and it
    is FR-914's first commit-source consumer.
    """
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        findings = list(secrets.env_file_findings(paths))
        for path in paths:
            blob = read_blob(inp.repo_dir, inp.commit_sha, path)
            if blob is None or secrets.is_over_size_limit(blob):
                continue
            if "\x00" in blob:                     # binary; nothing to quote
                continue
            for finding in secrets.scan_text(path, blob):
                if finding.evidence and not verify_quote(
                        finding.evidence, blob, Profile.VERBATIM_BYTES):
                    _log.warning(
                        "triage secrets: dropping unverifiable evidence for "
                        "%s at %s", finding.rule, path)
                    continue
                findings.append(finding)
        return SignalResult(
            signal=secrets.SIGNAL_ID, version=secrets.VERSION,
            collected=Measurement.measured(float(len(findings))),
            findings=findings)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage secrets signal failed: %s", exc)
        return SignalResult(
            signal=secrets.SIGNAL_ID, version=secrets.VERSION,
            collected=Measurement.not_collected(
                f"secrets signal raised: {type(exc).__name__}: {exc}"))


@dataclass
class TriageProbeInput:
    repo_dir: str
    commit_sha: str
    install_timeout_s: int = 600
    build_timeout_s: int = 300
    test_timeout_s: int = 600


def _venv_env(venv_dir: str) -> dict[str, str]:
    bin_dir = "Scripts" if sys.platform.startswith("win") else "bin"
    venv_bin = os.path.join(venv_dir, bin_dir)
    env = dict(os.environ)
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_dir
    env.pop("PYTHONHOME", None)
    return env


@activity.defn
async def triage_build_probe(inp: TriageProbeInput) -> SignalResult:
    """FR-901's buildable/runnable dimensions.

    THIS EXECUTES THE TRIAGED REPOSITORY'S OWN CODE -- postinstall hooks,
    setup.py, build scripts -- as the worker user, with network access, and
    FR-703's egress policy is tool-level so it does not see a socket opened
    from inside that call. The trust boundary is the OPERATOR'S
    AUTHORIZATION (spec D2). E-57 (untrusted-input threat model) and E-21
    (container tier) are what remove this debt; until they land, triage must
    not be offered self-serve (NFR-9).

    Runs in a throwaway clone at the pinned commit, never the operator's
    checkout (spec D8): the artifact claims to describe commit_sha, and
    `pip install` plus a test run write into whatever directory they are
    given. The venv lives outside the clone for the same reason.

    Configure with retry_policy=RetryPolicy(maximum_attempts=1): a ten-minute
    timeout retried three times is a thirty-minute triage, and a deterministic
    build failure does not become a success on attempt two.
    """
    workdir = tempfile.mkdtemp(prefix="sdlc-triage-")
    clone = os.path.join(workdir, "repo")
    venv_dir = os.path.join(workdir, "venv")
    try:
        code, out = await _bounded_shell(
            f'git clone --local --quiet "{inp.repo_dir}" "{clone}"',
            workdir, 300)
        if code != 0:
            raise RuntimeError(f"clone failed: {out[-1000:]}")
        code, out = await _bounded_shell(
            f'git -c advice.detachedHead=false checkout --quiet '
            f'"{inp.commit_sha}"', clone, 120)
        if code != 0:
            raise RuntimeError(f"checkout of {inp.commit_sha} failed: "
                               f"{out[-1000:]}")

        found = detect_with_marker(clone)
        if found is None:
            return build_probe.interpret(False, None, None, None, None)
        adapter, marker = found

        code, out = await _bounded_shell(
            f'"{sys.executable}" -m venv "{venv_dir}"', workdir, 300)
        if code != 0:
            raise RuntimeError(f"venv creation failed: {out[-1000:]}")
        env = _venv_env(venv_dir)

        install = None
        install_command = adapter.install_cmd(marker)
        if install_command is not None:
            code, out = await _bounded_shell(
                install_command, clone, inp.install_timeout_s, env=env)
            install = build_probe.StepOutcome(code=code, output=out)

        build = None
        build_command = adapter.build_cmd()
        if build_command is not None and install is not None \
                and install.code == 0:
            code, out = await _bounded_shell(
                build_command, clone, inp.build_timeout_s, env=env)
            build = build_probe.StepOutcome(code=code, output=out)

        test = None
        verdict = None
        if install is None or install.code == 0:
            # The runner itself is installed AFTER the project's own install,
            # so its exit code never masks an install failure. A project that
            # does not declare pytest is a dependency-health finding (E-41a),
            # not a reason to leave runnability unmeasured.
            await _bounded_shell(
                "pip install -q pytest", clone, inp.install_timeout_s, env=env)
            code, out = await _bounded_shell(
                adapter.test_cmd(coverage=False), clone, inp.test_timeout_s,
                env=env)
            test = build_probe.StepOutcome(code=code, output=out)
            if code != build_probe.TIMEOUT_CODE:
                verdict = adapter.classify_test_exit(code)

        return build_probe.interpret(True, install, build, test, verdict)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage build probe failed: %s", exc)
        return SignalResult(
            signal=build_probe.SIGNAL_ID, version=build_probe.VERSION,
            collected=Measurement.not_collected(
                f"build probe raised: {type(exc).__name__}: {exc}"))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
