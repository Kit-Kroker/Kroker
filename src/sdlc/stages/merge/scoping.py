"""Activity-side helpers for the diff-scoped merge gate (DS5, DS6).

Called from run_integration_checks, never from workflow code: they run tools
and read files. Every failure to compute a delta returns a NOT_COLLECTED
report with its reason, so the absolute check fails closed (DS7).
"""

from __future__ import annotations

import fnmatch
import os
import pathlib
import re
from collections.abc import Awaitable, Callable

from ...change_scope import FindingKey, delta, normalize_line, rename_map
from ...measurement import CollectionState
from ...process import _bounded_shell
from ...stages.qa.activities import _diagnostic_slice, _stopped_early
from ...toolchain.adapters import ToolchainAdapter
from ...toolchain.junit import shell_safe, testcase_outcomes
from ...vcs.git import _git
from .models import LintFinding, ScopedLintReport, ScopedTestReport


def _lint_nc(reason: str) -> ScopedLintReport:
    return ScopedLintReport(state=CollectionState.NOT_COLLECTED, reason=reason)


async def _lint_point(
    adapter: ToolchainAdapter, wt: str, env: dict[str, str] | None, timeout_s: int
) -> list[LintFinding] | str:
    code, out = await _bounded_shell(adapter.lint_json_cmd(), wt, timeout_s, env=env)
    rows = adapter.parse_lint(code, out, wt)
    if rows is None:
        return f"lint tool failed (exit {code}): {out[-300:]}"
    lines: dict[str, list[str]] = {}
    found: list[LintFinding] = []
    for rule, path, row in rows:
        if path not in lines:
            try:
                content = pathlib.Path(wt, path).read_text(encoding="utf-8", errors="replace")
                lines[path] = content.splitlines()
            except OSError:
                return f"could not read {path} to identify its lint finding"
        text = lines[path][row - 1] if 0 < row <= len(lines[path]) else ""
        found.append(LintFinding(rule=rule, path=path, line=normalize_line(text)))
    return found


def _policy_and_suppressions(
    adapter: ToolchainAdapter, head_wt: str, base_sha: str
) -> tuple[list[str], int] | str:
    rng = f"{base_sha}...HEAD"
    names = _git(["diff", "--name-only", rng], head_wt)
    patch = _git(["diff", "-U0", rng], head_wt)
    if names.returncode != 0 or patch.returncode != 0:
        return f"git diff against base {base_sha!r} failed"
    policy = sorted(
        n
        for n in names.stdout.splitlines()
        if any(fnmatch.fnmatch(n, g) for g in adapter.lint_policy_globs)
    )
    pattern = re.compile(adapter.suppression_pattern) if adapter.suppression_pattern else None
    added = sum(
        1
        for ln in patch.stdout.splitlines()
        if pattern is not None
        and ln.startswith("+")
        and not ln.startswith("+++")
        and pattern.search(ln)
    )
    return policy, added


def _lint_key(f: LintFinding) -> FindingKey:
    return ("lint", f.rule, f.path, f.line)


async def scoped_lint(
    adapter: ToolchainAdapter,
    head_wt: str,
    base_wt: str | None,
    base_reason: str,
    base_sha: str,
    renames: list[list[str]],
    env: dict[str, str] | None,
    timeout_s: int,
) -> ScopedLintReport:
    """DS5: the same binary (the head env's) lints both points, each under its
    own tree's configuration, so a version skew cannot manufacture a delta."""
    if base_wt is None:
        return _lint_nc(f"base not materialized: {base_reason or 'no reason given'}")
    head = await _lint_point(adapter, head_wt, env, timeout_s)
    if isinstance(head, str):
        return _lint_nc(f"head point: {head}")
    base = await _lint_point(adapter, base_wt, env, timeout_s)
    if isinstance(base, str):
        return _lint_nc(f"base point: {base}")
    extra = _policy_and_suppressions(adapter, head_wt, base_sha)
    if isinstance(extra, str):
        return _lint_nc(extra)
    introduced, pre, res = delta(base, head, _lint_key, rename_map(renames))
    return ScopedLintReport(
        state=CollectionState.MEASURED,
        introduced=introduced,
        preexisting=pre,
        resolved=res,
        policy_paths_changed=extra[0],
        suppressions_added=extra[1],
    )


JUNIT = ".sdlc-junit.xml"
BASE_JUNIT = ".sdlc-junit-base.xml"
BASE_ATTEMPTS = 4  # DS6: one base run plus up to three corroborating re-runs
ID_CHUNK = 50  # node ids per command: cmd.exe caps a command line at 8191 chars
_PYTEST_USAGE_ERROR = 4

Provision = Callable[[], Awaitable[tuple[dict[str, str] | None, str | None]]]


def _test_nc(reason: str) -> ScopedTestReport:
    return ScopedTestReport(state=CollectionState.NOT_COLLECTED, reason=reason)


def _read_report(wt: str, name: str) -> dict[str, bool] | None:
    try:
        return testcase_outcomes(pathlib.Path(wt, name).read_text(encoding="utf-8"))
    except OSError:
        return None


def _clear(wt: str, name: str) -> None:
    try:
        os.remove(os.path.join(wt, name))
    except FileNotFoundError:
        pass


async def _head_run(adapter, head_wt, env, timeout_s) -> tuple[dict[str, bool], str] | str:
    _clear(head_wt, JUNIT)
    code, out = await _bounded_shell(
        adapter.integration_test_cmd(JUNIT, True), head_wt, timeout_s, env=env
    )
    if code == _PYTEST_USAGE_ERROR:  # coverage tooling unavailable: honest run without it
        _clear(head_wt, JUNIT)
        code, out = await _bounded_shell(
            adapter.integration_test_cmd(JUNIT, False), head_wt, timeout_s, env=env
        )
    if code == -1:
        return f"head test run timed out after {timeout_s}s"
    if _stopped_early(out):
        return "head test run stopped early: tests after the stop never ran"
    kind = adapter.classify_test_exit(code)
    if kind == "no_tests":
        return "head test run collected no tests"
    outcomes = _read_report(head_wt, JUNIT)
    if outcomes is None:
        return f"head test run (exit {code}) wrote no parseable JUnit report"
    if kind == "failed_to_run" and all(outcomes.values()):
        return f"head test run failed to run (exit {code})"
    return outcomes, out


async def _base_outcomes(adapter, base_wt, ids, env, timeout_s) -> dict[str, bool] | str:
    merged: dict[str, bool] = {}
    for i in range(0, len(ids), ID_CHUNK):
        _clear(base_wt, BASE_JUNIT)
        # The exit code is ignored on purpose: every failing base test exits 1.
        # Attribution reads JUnit presence/absence; absence => introduced.
        await _bounded_shell(
            adapter.selected_tests_cmd(ids[i : i + ID_CHUNK], BASE_JUNIT),
            base_wt,
            timeout_s,
            env=env,
        )
        got = _read_report(base_wt, BASE_JUNIT)
        if got is None:
            return "base re-run wrote no parseable JUnit report"
        merged.update(got)
    return merged


async def scoped_tests(
    adapter: ToolchainAdapter,
    head_wt: str,
    base_wt: str | None,
    base_reason: str,
    renames: list[list[str]],
    env: dict[str, str] | None,
    provision_base: Provision,
    timeout_s: int,
) -> ScopedTestReport:
    """DS6: the whole suite at head; attribution by targeted base corroboration."""
    if base_wt is None:
        return _test_nc(f"base not materialized: {base_reason or 'no reason given'}")
    head = await _head_run(adapter, head_wt, env, timeout_s)
    if isinstance(head, str):
        return _test_nc(head)
    outcomes, out = head
    failed = sorted(n for n, ok in outcomes.items() if not ok)
    if not failed:
        return ScopedTestReport(state=CollectionState.MEASURED)

    to_base_path = {new: old for old, new in rename_map(renames).items()}

    def to_base(nid: str) -> str:
        file, sep, rest = nid.partition("::")
        return to_base_path.get(file, file) + sep + rest

    introduced: list[str] = []
    present: dict[str, str] = {}  # base id -> head id
    for n in failed:
        b = to_base(n)
        file = b.partition("::")[0]
        if not shell_safe(b) or not os.path.isfile(os.path.join(base_wt, file)):
            introduced.append(n)
        else:
            present[b] = n

    base_env, err = await provision_base()
    if err:
        return _test_nc(f"base environment provisioning failed: {err}")

    needs_collect = sorted({b.partition("::")[0] for b in present if "::" in b})
    collected: set[str] = set()
    for i in range(0, len(needs_collect), ID_CHUNK):
        code, cout = await _bounded_shell(
            adapter.collect_ids_cmd(needs_collect[i : i + ID_CHUNK]),
            base_wt,
            timeout_s,
            env=base_env,
        )
        if code not in (0, 1, 2, 5):
            return _test_nc(f"base collection failed (exit {code})")
        collected |= adapter.parse_collected_ids(cout)
    for b in [b for b in present if "::" in b and b not in collected]:
        introduced.append(present.pop(b))

    preexisting: list[str] = []
    flaky: list[str] = []
    passing = sorted(present)
    for attempt in range(1, BASE_ATTEMPTS + 1):
        if not passing:
            break
        got = await _base_outcomes(adapter, base_wt, passing, base_env, timeout_s)
        if isinstance(got, str):
            return _test_nc(got)
        still = []
        for b in passing:
            if b not in got:
                introduced.append(present[b])  # collected but never reported: unattributable
            elif not got[b]:
                (preexisting if attempt == 1 else flaky).append(present[b])
            else:
                still.append(b)
        passing = still
    introduced.extend(present[b] for b in passing)  # passed every base attempt

    return ScopedTestReport(
        state=CollectionState.MEASURED,
        introduced=sorted(introduced),
        preexisting=sorted(preexisting),
        preexisting_flaky=sorted(flaky),
        head_failed=len(failed),
        diagnostic=_diagnostic_slice(out),
    )
