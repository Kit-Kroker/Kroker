"""Temporal activities for the qa stage (spec A §5)."""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import re
import sys
from dataclasses import dataclass

from temporalio import activity

from ...measurement import CollectionState
from ...process import kill_process_tree
from ...toolchain.adapters import ToolchainKind, detect
from .models import QAReport, SecurityFinding, SecurityReport, SecuritySeverity

_log = logging.getLogger(__name__)


@dataclass
class QAInput:
    worktree: str
    test_cmd: str = "pytest -q --maxfail=25"
    timeout_s: int = 600


@dataclass
class LintInput:
    worktree: str
    lint_cmd: str = "ruff check ."
    timeout_s: int = 600


@dataclass
class SecurityScanInput:
    worktree: str


# Matches an explicit Windows `py -X.Y` launcher pin, e.g. the `py -3.11
# -m pytest` a contract writes when AGENTS.md mandates "Python 3.11".
_PY_LAUNCHER_VERSION_RE = re.compile(r"(?<![\w.-])py\s+-(\d+\.\d+)\b")


async def _bounded_shell(
    cmd: str, cwd: str, timeout_s: int, env: dict[str, str] | None = None
) -> tuple[int, str]:
    """Run a shell command bounded by timeout_s, combining stdout+stderr.
    On timeout: kill and return (-1, message). See run_test_suite's docstring
    for why an unbounded shell command is dangerous in an activity.

    env=None inherits the activity process's own environment (the prior,
    only behaviour); passing an override (e.g. a worktree-local venv's PATH
    from _ensure_python_env) does NOT merge with it automatically — callers
    must pass a full environment dict."""
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return -1, f"command timed out after {timeout_s}s (cmd: {cmd!r})"
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
    return (proc.returncode or 0), out_b.decode(errors="replace")


async def _ensure_py_launcher_versions(cmd: str, cwd: str) -> str | None:
    """A contract's test/lint command may pin an exact interpreter via the
    Windows `py -X.Y` launcher, mirroring an AGENTS.md-mandated stack
    (e.g. "Python 3.11 is the mandated stack"). That pin is worthless if
    the version was never installed on this host: `py -X.Y` fails
    immediately with "No runtime installed that matches X.Y" *before* the
    command's own install step (e.g. `pip install -e .[dev]`) ever runs —
    so a fully correct implementation reads back as a QA failure with a
    launcher error, indistinguishable from a real test failure.

    Best-effort provision any missing version via `py install X.Y` so the
    command the contract actually wrote gets a chance to run. Windows-only
    (the `py` launcher doesn't exist elsewhere) and never raises — a
    provisioning failure just falls through to the command's own (equally
    informative) launcher error."""
    if not sys.platform.startswith("win"):
        return None
    versions = sorted(set(_PY_LAUNCHER_VERSION_RE.findall(cmd)))
    notes = []
    for version in versions:
        code, _ = await _bounded_shell(f"py -{version} --version", cwd, 15)
        if code == 0:
            continue
        install_code, out = await _bounded_shell(f"py install {version}", cwd, 300)
        notes.append(
            f"py -{version} was not installed on this host; "
            f"auto-provisioned via `py install {version}` "
            + ("succeeded" if install_code == 0 else f"failed: {out[-500:]}")
        )
    return "\n".join(notes) if notes else None


# Provisioned by _ensure_python_env inside the worktree; declared up here
# because _SCAN_SKIP_DIRS (evaluated at import) must exclude it.
_VENV_DIR_NAME = ".sdlc-venv"

# Ordered: the base file first, so a dev file's own `-r requirements.txt`
# is already satisfied and a pin in the dev file wins on conflict.
_REQUIREMENTS_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements/base.txt",
    "requirements/dev.txt",
)


async def _ensure_python_env(
    worktree: str, timeout_s: int
) -> tuple[dict[str, str] | None, str | None]:
    """ToolchainAdapter is intentionally PURE (ADR-15): it returns bare
    command strings like "pytest -q ..." / "ruff check .", never touching a
    subprocess. Those bare commands only mean anything if pytest/ruff are
    on PATH *and* the produced project's own dependencies are importable —
    neither is true of the activity worker's ambient environment, which has
    no relationship to whatever stack a given benchmark case's produced repo
    declares. Running the adapter's commands unmodified there reads back as
    a QA failure indistinguishable from a real bug in the generated code.

    Provisions an isolated venv at ``<worktree>/.sdlc-venv``, reused across
    calls (idempotent — created once, installed into on every call so a
    later merge's new dependencies are picked up). Returns an environment
    dict with that venv's script directory prepended to PATH, for the
    caller to pass into _bounded_shell. Install failures are tolerated, not
    fatal: a produced project with no packaging metadata (e.g. a flat
    single-module fixture) still gets a real pytest/ruff via the explicit
    fallback install below, exactly as the pre-venv bare-PATH behaviour
    depended on pytest's own same-directory import fallback — only venv
    creation itself (i.e. "this host has no usable Python at all") is
    fatal, exactly like a missing toolchain adapter is non-fatal one level
    up."""
    venv_dir = os.path.join(worktree, _VENV_DIR_NAME)
    bin_dir = "Scripts" if sys.platform.startswith("win") else "bin"
    venv_bin = os.path.join(venv_dir, bin_dir)
    exe_suffix = ".exe" if sys.platform.startswith("win") else ""
    py_exe = os.path.join(venv_bin, f"python{exe_suffix}")

    if not os.path.isdir(venv_dir):
        code, out = await _bounded_shell(
            f'"{sys.executable}" -m venv "{venv_dir}"', worktree, timeout_s
        )
        if code != 0:
            return None, f"venv creation failed: {out[-1000:]}"

    # Best-effort: install the produced project's own declared deps first
    # (so pydantic etc. resolve), then unconditionally guarantee the tools
    # the adapter's commands need — belt-and-suspenders for a project whose
    # [dev] extra forgot pytest/ruff, or has no packaging metadata at all.
    await _bounded_shell(f'"{py_exe}" -m pip install -q -e ".[dev]"', worktree, timeout_s)
    await _bounded_shell(f'"{py_exe}" -m pip install -q -e "{worktree}"', worktree, timeout_s)
    # Both `-e` installs above hard-error on a project carrying no
    # pyproject.toml/setup.py ("does not appear to be a Python project") —
    # yet `requirements.txt` is itself one of PythonToolchain's markers, so
    # such a project IS routed here and would otherwise get a venv holding
    # pytest and none of its own dependencies. Every task then failed on
    # ModuleNotFoundError regardless of code quality
    # (bench-todo-api-greenfield-1785444047: 12/12 code attempts; the same
    # tree passed 41/41 once requirements.txt was installed).
    for req in _REQUIREMENTS_FILES:
        if os.path.isfile(os.path.join(worktree, req)):
            await _bounded_shell(f'"{py_exe}" -m pip install -q -r "{req}"', worktree, timeout_s)
    await _bounded_shell(
        f'"{py_exe}" -m pip install -q pytest pytest-cov ruff', worktree, timeout_s
    )

    env = dict(os.environ)
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    env["VIRTUAL_ENV"] = venv_dir
    env.pop("PYTHONHOME", None)
    return env, None


@activity.defn
async def run_test_suite(inp: QAInput) -> QAReport:
    """Bounded by timeout_s (default 10 min): a contract-specified command
    can accidentally chain in a long-running process (e.g. `npm run dev`,
    which never exits) instead of a one-shot test run. Without a bound
    here, that hang is only caught by the activity's heartbeat_timeout
    (60 min by default) — and since run_test_suite never heartbeats, a
    genuine hang burns the full hour AND, once retries are exhausted,
    fails as an uncaught activity error that crashes the whole workflow
    rather than being handled as a normal (fixable) task failure.

    Runs against a provisioned per-worktree venv (`_ensure_python_env`),
    exactly like run_integration_checks -- this is the per-TASK QA gate, so
    running the bare test_cmd against the activity worker's ambient
    environment (which has no relationship to the produced project's own
    dependencies) would fail every task on ModuleNotFoundError regardless
    of code quality, indistinguishable from a real bug (see
    bench-cat-cafe-monitoring-1785186777: 45/45 code-stage attempts failed
    this way while the same worktrees passed cleanly once re-run against a
    real venv)."""
    provisioning = await _ensure_py_launcher_versions(inp.test_cmd, inp.worktree)
    if provisioning:
        _log.info("run_test_suite: %s", provisioning)
    env = None
    adapter = detect(inp.worktree)
    if adapter is not None and adapter.kind is ToolchainKind.PYTHON:
        env, setup_error = await _ensure_python_env(inp.worktree, inp.timeout_s)
        if setup_error:
            issues = [setup_error]
            if provisioning:
                issues.insert(0, provisioning)
            return QAReport(tests_passed=False, failing_tests=[], issues=issues)
    proc = await asyncio.create_subprocess_shell(
        inp.test_cmd,
        cwd=inp.worktree,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=inp.timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return QAReport(
            tests_passed=False,
            failing_tests=[],
            issues=[
                f"test command timed out after {inp.timeout_s}s "
                f"(cmd: {inp.test_cmd!r}) — likely hung on a "
                "long-running process (e.g. a dev server) rather "
                "than exiting after a one-shot test run"
            ],
        )
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
    out = out_b.decode(errors="replace")
    failing = [ln.split(" ")[0] for ln in out.splitlines() if ln.startswith("FAILED")]
    # pytest's dedicated exit code for "collected zero tests" (distinct from
    # 1 = tests ran and some failed). A task whose own scope doesn't add
    # tests yet (e.g. an early module task in a task-per-commit greenfield
    # build, before the dedicated test-writing tasks land) legitimately has
    # nothing to fail — scoring that identically to a real test failure
    # makes the task's QA gate unpassable no matter what the agent writes.
    # Gated on the exit code AND pytest's own "no tests ran" text so an
    # unrelated non-pytest command that happens to also exit 5 is never
    # mistaken for this case.
    if proc.returncode == 5 and "no tests ran" in out:
        return QAReport(tests_passed=True, failing_tests=[], issues=[])
    issues = []
    if proc.returncode != 0:
        issues = [_diagnostic_slice(out)]
        if provisioning:
            issues.insert(0, provisioning)
    return QAReport(
        tests_passed=proc.returncode == 0,
        failing_tests=failing[:50],
        issues=issues,
        stopped_early=_stopped_early(out),
    )


_FAILURES_BANNER = "= FAILURES ="
_WARNINGS_BANNER = "= warnings summary ="
_SUMMARY_BANNER = "= short test summary info ="
_STOP_MARKER = "stopping after"
_QA_OUTPUT_MAX = 2000


def _stopped_early(out: str) -> bool:
    """Whether the runner aborted before the end of the suite.

    pytest announces it: ``!!!! stopping after 1 failures !!!!`` for both -x
    and --maxfail. Anything after the stopping point never ran.
    """
    return _STOP_MARKER in out


def _diagnostic_slice(out: str, limit: int = _QA_OUTPUT_MAX) -> str:
    """The part of a test run that explains the failure, within `limit`.

    pytest orders its output FAILURES (tracebacks) -> warnings summary ->
    short test summary info, so keeping the TAIL keeps warnings and discards
    tracebacks. On this repository the warnings block alone exceeds the whole
    budget, which left every retry prompt carrying a failing test's name and
    no diagnostic at all -- and four consecutive tasks responded by guessing
    at the named file, each widening further than the last (P2 demonstration,
    2026-08-19).

    So: prefer the FAILURES section, and reserve room for the short summary
    because it names *every* failing test while the traceback shows only what
    fits. Within the failures section the tail is the useful end -- that is
    where the assertion and the exception live.

    Falls back to the plain tail when there is no FAILURES section, which is
    any non-pytest runner (FR-803 lets a contract name any test command) and
    also a collection error, where the traceback is already at the end.
    """
    start = out.find(_FAILURES_BANNER)
    if start == -1:
        return out[-limit:]
    rest = out[start:]

    summary_at = rest.find(_SUMMARY_BANNER)
    warnings_at = rest.find(_WARNINGS_BANNER)
    ends = [i for i in (warnings_at, summary_at) if i != -1]
    failures = rest[: min(ends)] if ends else rest

    # A third of the budget is plenty for the summary's one line per test, and
    # never lets it crowd out the tracebacks the way the warnings block did.
    summary = rest[summary_at:][: limit // 3] if summary_at != -1 else ""
    return failures[-max(limit - len(summary), 0) :] + summary


@activity.defn
async def run_lint(inp: LintInput) -> tuple[bool, str]:
    """Run a linter; return (clean, detail). P1 runs the repo's configured
    linter; non-zero exit = not clean. `detail` is the tail of stdout for
    the gate's CheckResult.detail. Bounded by timeout_s — see
    run_test_suite's docstring for why an unbounded shell command is
    dangerous here."""
    provisioning = await _ensure_py_launcher_versions(inp.lint_cmd, inp.worktree)
    if provisioning:
        _log.info("run_lint: %s", provisioning)
    proc = await asyncio.create_subprocess_shell(
        inp.lint_cmd,
        cwd=inp.worktree,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,  # C6: whole tree killable as a group
    )
    try:
        out_b, _ = await asyncio.wait_for(proc.communicate(), timeout=inp.timeout_s)
    except TimeoutError:
        await asyncio.shield(kill_process_tree(proc))
        return False, (f"lint command timed out after {inp.timeout_s}s (cmd: {inp.lint_cmd!r})")
    except asyncio.CancelledError:
        await asyncio.shield(kill_process_tree(proc))
        raise
    out = out_b.decode(errors="replace")
    detail = out[-2000:]
    if provisioning and proc.returncode != 0:
        detail = f"{provisioning}\n{detail}"
    return proc.returncode == 0, detail


# Minimal deterministic security ruleset (FR-106 absolute floor). Each entry
# is (compiled_regex, severity, rule_name, human_detail). Intentionally small
# and offline; the seam for a real SAST is this function's return type.
_SECURITY_RULES: list[tuple[re.Pattern, SecuritySeverity, str, str]] = [
    (
        re.compile(r"(?i)(aws_secret_access_key|secret_key)\s*=\s*['\"][A-Za-z0-9/+]{20,}['\"]"),
        "critical",
        "hardcoded-secret",
        "hardcoded credential/secret literal",
    ),
    (re.compile(r"\beval\s*\("), "critical", "dangerous-eval", "use of eval() on untrusted input"),
    (
        re.compile(r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True"),
        "high",
        "shell-injection",
        "subprocess call with shell=True",
    ),
]

_SECURITY_SCAN_EXTENSIONS = (".py", ".js", ".ts", ".go", ".rb", ".java")

# Directories that hold dependency source rather than the work under review.
# `.sdlc-venv` is ours -- _ensure_python_env creates it INSIDE the worktree,
# so by merge time the scan would walk a whole site-packages tree. Stdlib and
# vendored packages are dense with `eval(` and `shell=True`, which made the
# ABSOLUTE security_no_critical check unpassable for any Python case once QA
# had run (bench-todo-api-greenfield-1785444047: 14 critical findings, all 14
# inside .sdlc-venv, none from produced code). The rest are the equivalent
# conventions a produced project brings on its own.
_SCAN_SKIP_DIRS = frozenset(
    {
        ".git",
        _VENV_DIR_NAME,
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "site-packages",
        "vendor",
        "dist",
        "build",
        ".next",
    }
)


@activity.defn
async def security_scan(inp: SecurityScanInput) -> SecurityReport:
    """Scan source files under the integration worktree against a minimal
    deterministic ruleset. Pure filesystem read — no network, no git — so it
    is reproducible across Temporal retries."""
    findings: list[SecurityFinding] = []
    root = inp.worktree
    for dirpath, dirnames, filenames in os.walk(root):
        # In-place slice assignment is what prunes os.walk's descent.
        dirnames[:] = [d for d in dirnames if d not in _SCAN_SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(_SECURITY_SCAN_EXTENSIONS):
                continue
            fpath = os.path.join(dirpath, fname)
            try:
                text = pathlib.Path(fpath).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = os.path.relpath(fpath, root)
            for pattern, severity, rule, detail in _SECURITY_RULES:
                if pattern.search(text):
                    findings.append(
                        SecurityFinding(severity=severity, rule=rule, detail=detail, path=rel)
                    )
    critical = sum(1 for f in findings if f.severity == "critical")
    return SecurityReport(critical=critical, findings=findings, state=CollectionState.MEASURED)


ACTIVITIES = [run_test_suite, run_lint, security_scan]
