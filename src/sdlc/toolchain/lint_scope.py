"""Diff-scoped lint: the merge gate's own measurement (DS5, DS7).

026 T011 (FR-010, research R4): moved VERBATIM from
stages/merge/{scoping,models}.py — byte-identical code, unchanged JSON
wire format — so the per-task lint can call merge's exact scoped_lint
without qa importing another stage (the reverse import would cycle:
merge/scoping imports qa/activities). merge re-imports and re-exports
every name here, so merge is untouched behaviorally.

Stage-neutral by construction: imports toolchain, vcs, process and
measurement only — never a stage. Called from activity code only, never
from workflow code: these run tools and read files. Every failure to
compute a delta returns a NOT_COLLECTED report with its reason, so the
absolute check fails closed (DS7).
"""

from __future__ import annotations

import fnmatch
import pathlib
import re

from pydantic import BaseModel, Field, model_validator

from ..change_scope import FindingKey, delta, normalize_line, rename_map
from ..measurement import CollectionState
from ..process import _bounded_shell
from ..vcs.git import _git
from .adapters import ToolchainAdapter


class LintFinding(BaseModel):
    rule: str
    path: str  # repo-relative POSIX
    line: str  # normalized source line: the DS3 identity text


def _unmeasured_is_empty(state: CollectionState, reason: str, **carried: object) -> None:
    """FR-915 at the type: an unmeasured delta carries nothing that could read
    as "zero introduced", and says why it is unmeasured."""
    if state is CollectionState.MEASURED:
        return
    loaded = [name for name, value in carried.items() if value]
    if loaded:
        raise ValueError(f"{state.value} report must not carry {loaded}")
    if not reason.strip():
        raise ValueError(f"{state.value} report requires a reason")


class ScopedLintReport(BaseModel):
    """DS5/DS7: lint at the pinned base and the integration head. `lint_clean`
    passes iff MEASURED and `introduced` is empty. Policy relaxation is
    reported, never gated (DS5's named residual)."""

    state: CollectionState
    reason: str = ""
    introduced: list[LintFinding] = Field(default_factory=list)
    preexisting: int = 0
    resolved: int = 0
    policy_paths_changed: list[str] = Field(default_factory=list)
    suppressions_added: int = 0

    @model_validator(mode="after")
    def _fail_closed(self) -> ScopedLintReport:
        _unmeasured_is_empty(
            self.state,
            self.reason,
            introduced=self.introduced,
            preexisting=self.preexisting,
            resolved=self.resolved,
            policy_paths_changed=self.policy_paths_changed,
            suppressions_added=self.suppressions_added,
        )
        return self


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
