"""E-41 signal activities (FR-902). One activity per signal, deliberately:
a signal that crashes or times out yields not_collected for ITSELF while every
other signal still reports (spec D3).

Findings are read from the pinned commit through git, never from the working
checkout (spec D6): a gitignored local .env cannot produce a false positive,
untracked build output produces no noise, and every evidence citation is true
against path@sha by construction.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import posixpath
import shutil
import sys
import tempfile
from dataclasses import dataclass

from temporalio import activity

from ..activities import _bounded_shell, _git
from ..grounding import Profile, verify_quote
from ..measurement import CollectionState, Measurement
from ..toolchain.adapters import detect_with_marker, detect_with_marker_from_paths
from .advisories import resolve_advisory_source
from .gitread import is_over_size_limit, read_tree
from .models import SignalResult
from .signals import (
    baseline, build_probe, dependencies, misconfig, outliers, scaffold,
    secrets,
)

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
        for path, blob in read_tree(inp.repo_dir, inp.commit_sha,
                                    sorted(paths)):
            if is_over_size_limit(blob):
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


def _verified(result: SignalResult, blobs: dict[str, str]) -> SignalResult:
    """Drop any finding whose evidence does not verify against the bytes it
    cites (spec D5).

    For deterministic rules the quote is verbatim by construction, so this is
    a DRIFT guard -- it catches a citation that no longer resolves at that
    path and sha -- not a hallucination guard. It becomes load-bearing when
    E-48's LLM proposers cite the same way (FR-914).
    """
    kept = []
    for finding in result.findings:
        if not finding.evidence:
            kept.append(finding)
            continue
        blob = blobs.get(finding.path)
        if blob is not None and verify_quote(
                finding.evidence, blob, Profile.VERBATIM_BYTES):
            kept.append(finding)
        else:
            _log.warning("triage %s: dropping unverifiable evidence for %s "
                         "at %s", result.signal, finding.rule, finding.path)
    # collected.value is the finding COUNT. Dropping a finding without
    # updating it reports a count the artifact's findings list contradicts.
    update: dict[str, object] = {"findings": kept}
    if result.collected.state is CollectionState.MEASURED:
        update["collected"] = Measurement.measured(float(len(kept)))
    return result.model_copy(update=update)


@dataclass
class TriageDependencyInput:
    repo_dir: str
    commit_sha: str
    # Spec D11: the default collects nothing. Naming a source here is an
    # explicit operator act, and it is a declared outbound egress (FR-703).
    advisory_source: str = "none"


@activity.defn
async def triage_dependencies(inp: TriageDependencyInput) -> SignalResult:
    """FR-902 dependency health (E-41a). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        adapter = found[0] if found else None

        manifest_names = set(adapter.manifests) if adapter else set()
        source_exts = tuple(adapter.source_extensions) if adapter else ()
        wanted = sorted(
            p for p in paths
            if posixpath.basename(p) in manifest_names
            or (source_exts and p.endswith(source_exts)))

        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))
        manifests = {p: t for p, t in blobs.items()
                     if posixpath.basename(p) in manifest_names}
        sources = [t for p, t in blobs.items() if p not in manifests]

        declared = dependencies.parse_manifests(manifests)
        lockfile_present = bool(adapter) and any(
            lf in set(paths) for lf in adapter.lockfiles)
        advisories = resolve_advisory_source(inp.advisory_source).lookup(
            adapter.ecosystem if adapter else None,
            sorted({d.name for d in declared}))

        result = dependencies.evaluate(
            declared, lockfile_present,
            dependencies.imported_modules(sources), advisories)
        return _verified(result, blobs)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage dependencies signal failed: %s", exc)
        return SignalResult(
            signal=dependencies.SIGNAL_ID, version=dependencies.VERSION,
            collected=Measurement.not_collected(
                f"dependencies signal raised: {type(exc).__name__}: {exc}"))


def commit_touch_counts(repo_dir: str, commit_sha: str,
                        max_commits: int = 2000) -> dict[str, int] | None:
    """path -> commits touching it, over at most `max_commits` commits ending
    at `commit_sha`. None when history yields no usable signal (spec D13).

    A single-commit repository returns None rather than "everything touched
    once": the latter is true and useless, and it would escalate every
    fingerprinted file in exactly the repositories Tier 0 sees most.

    Deterministic given the same repository and sha (NFR-10). What history
    does not survive is a squash or re-import, which changes stability across
    re-creations, not reproducibility at a pinned commit -- and since history
    only adjusts severity, a re-import degrades sharpness, never correctness.
    """
    proc = _git(["log", f"--max-count={max_commits}", "--name-only",
                 "--format=%x00", commit_sha], cwd=repo_dir)
    if proc.returncode != 0:
        return None
    if proc.stdout.count("\x00") <= 1:
        return None
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if not line or line.startswith("\x00"):
            continue
        counts[line.strip()] = counts.get(line.strip(), 0) + 1
    return counts


@activity.defn
async def triage_scaffold(inp: TriageSignalInput) -> SignalResult:
    """FR-902 generator scaffolding and dead code (E-41b). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        adapter = found[0] if found else None
        exts = tuple(adapter.source_extensions) if adapter else ()

        # Fingerprints target specific paths; source extensions cover the
        # dead-code half and the structure ratio. Reading their union keeps
        # this to one pass.
        wanted = sorted({
            p for p in paths
            if (exts and p.endswith(exts))
            or any(fnmatch.fnmatch(p, fp.path_glob)
                   for fp in scaffold.FINGERPRINTS)})
        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))

        result = scaffold.evaluate(
            paths, blobs,
            commit_touch_counts(inp.repo_dir, inp.commit_sha),
            adapter)
        return _verified(result, blobs)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage scaffold signal failed: %s", exc)
        return SignalResult(
            signal=scaffold.SIGNAL_ID, version=scaffold.VERSION,
            collected=Measurement.not_collected(
                f"scaffold signal raised: {type(exc).__name__}: {exc}"))


@activity.defn
async def triage_misconfig(inp: TriageSignalInput) -> SignalResult:
    """FR-902 framework-default misconfiguration (E-41c). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        exts = tuple(found[0].source_extensions) if found else ()
        # Config lives beside source: storage rules and IaC policies are the
        # world_readable_storage rule's whole subject and carry no source
        # extension.
        config_suffixes = (".rules", ".json", ".yml", ".yaml", ".toml",
                           ".ini", ".cfg", ".env")
        wanted = sorted(p for p in paths
                        if (exts and p.endswith(exts))
                        or p.endswith(config_suffixes))
        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))
        return _verified(misconfig.evaluate(blobs), blobs)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage misconfig signal failed: %s", exc)
        return SignalResult(
            signal=misconfig.SIGNAL_ID, version=misconfig.VERSION,
            collected=Measurement.not_collected(
                f"misconfig signal raised: {type(exc).__name__}: {exc}"))


@activity.defn
async def triage_outliers(inp: TriageSignalInput) -> SignalResult:
    """FR-902 size and duplication outliers (E-41d). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        adapter = found[0] if found else None
        exts = tuple(adapter.source_extensions) if adapter else ()
        wanted = sorted(p for p in paths if exts and p.endswith(exts))
        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))
        # No evidence quotes: a size or duplication finding cites a file and
        # a line, not a line's text, so _verified would be a no-op.
        return outliers.evaluate(blobs, adapter)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage outliers signal failed: %s", exc)
        return SignalResult(
            signal=outliers.SIGNAL_ID, version=outliers.VERSION,
            collected=Measurement.not_collected(
                f"outliers signal raised: {type(exc).__name__}: {exc}"))


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
