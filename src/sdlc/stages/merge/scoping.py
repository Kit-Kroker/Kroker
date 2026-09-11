"""Activity-side helpers for the diff-scoped merge gate (DS5, DS6).

Called from run_integration_checks, never from workflow code: they run tools
and read files. Every failure to compute a delta returns a NOT_COLLECTED
report with its reason, so the absolute check fails closed (DS7).
"""

from __future__ import annotations

import fnmatch
import pathlib
import re

from ...change_scope import FindingKey, delta, normalize_line, rename_map
from ...measurement import CollectionState
from ...process import _bounded_shell
from ...toolchain.adapters import ToolchainAdapter
from ...vcs.git import _git
from .models import LintFinding, ScopedLintReport


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
