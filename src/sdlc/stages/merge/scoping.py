"""Activity-side helpers for the diff-scoped merge gate (DS5, DS6).

Called from run_integration_checks, never from workflow code: they run tools
and read files. Every failure to compute a delta returns a NOT_COLLECTED
report with its reason, so the absolute check fails closed (DS7).

026 T011: the lint half (_lint_nc, _lint_point, _policy_and_suppressions,
_lint_key, scoped_lint) moved verbatim to sdlc.toolchain.lint_scope and is
re-exported here unchanged, so callers (merge/activities) and the JSON
wire format are untouched.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Awaitable, Callable

from ...change_scope import rename_map
from ...measurement import CollectionState
from ...process import _bounded_shell
from ...stages.qa.activities import _diagnostic_slice, _stopped_early
from ...toolchain.adapters import ToolchainAdapter
from ...toolchain.junit import shell_safe, testcase_outcomes
from ...toolchain.lint_scope import (  # 026 T011: re-export, moved verbatim
    LintFinding as LintFinding,
)
from ...toolchain.lint_scope import (
    ScopedLintReport as ScopedLintReport,
)
from ...toolchain.lint_scope import (
    _lint_key as _lint_key,
)
from ...toolchain.lint_scope import (
    _lint_nc as _lint_nc,
)
from ...toolchain.lint_scope import (
    _lint_point as _lint_point,
)
from ...toolchain.lint_scope import (
    _policy_and_suppressions as _policy_and_suppressions,
)
from ...toolchain.lint_scope import (
    scoped_lint as scoped_lint,
)
from .models import ScopedTestReport

JUNIT = ".sdlc-junit.xml"
BASE_JUNIT = ".sdlc-junit-base.xml"
BASE_ATTEMPTS = 4  # DS6: one base run plus up to three corroborating re-runs
ID_CHUNK = 50  # node ids per command: cmd.exe caps a command line at 8191 chars
_PYTEST_USAGE_ERROR = 4
# Language-neutral "coverage tooling unavailable": the shell's
# command-not-found exits (POSIX sh: 127, cmd.exe: 9009). Any adapter whose
# coverage converter binary is missing (Go: gocover-cobertura) dies here
# AFTER the test run and its JUnit pipe already landed, so the honest move
# is the same as pytest's usage error: re-run without coverage. FR-915's
# fail-closed discipline survives: if the RUNNER itself is missing (not just
# the converter), the retry exits this set again, no JUnit lands, and the
# gate reads NOT_COLLECTED -- the safe direction is never traded away.
_COVERAGE_TOOLING_UNAVAILABLE = frozenset({127, 9009})

Provision = Callable[[], Awaitable[tuple[dict[str, str] | None, str | None]]]


def _test_nc(reason: str) -> ScopedTestReport:
    return ScopedTestReport(state=CollectionState.NOT_COLLECTED, reason=reason)


def _read_report(wt: str, name: str, adapter: ToolchainAdapter) -> dict[str, bool] | None:
    try:
        return testcase_outcomes(
            pathlib.Path(wt, name).read_text(encoding="utf-8"), adapter.node_id
        )
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
    if code == _PYTEST_USAGE_ERROR or code in _COVERAGE_TOOLING_UNAVAILABLE:
        # coverage tooling unavailable: honest run without it
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
    outcomes = _read_report(head_wt, JUNIT, adapter)
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
        got = _read_report(base_wt, BASE_JUNIT, adapter)
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
        if not shell_safe(b) or not adapter.base_locator_exists(base_wt, file):
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
