"""Harness registry and CLI version drift detection."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from ..core.models import HarnessKind
from .base import CodingHarness
from .claude_code import ClaudeCodeHarness
from .cursor import CursorHarness
from .opencode import OpenCodeHarness

_log = logging.getLogger(__name__)

HARNESSES: dict[HarnessKind, CodingHarness] = {
    HarnessKind.CLAUDE_CODE: ClaudeCodeHarness(),
    HarnessKind.OPENCODE: OpenCodeHarness(),
    HarnessKind.CURSOR: CursorHarness(),
}

_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


def check_harness_versions(
    harnesses: dict[HarnessKind, CodingHarness] | None = None,
) -> list[str]:
    """E-24 (folded into E-35): warn when an installed harness CLI has drifted
    from its pinned version — the failure mode where a silent CLI upgrade
    breaks an adapter's parse. Never raises (a patch bump must not brick the
    worker). Skips silently when the CLI is absent (CI/fakes) or unpinned.

    Returns the drift messages as well as logging them (F2 RULING 1). The
    log call is what the worker boots on and what test_cursor_harness pins;
    the return value is what `sdlc doctor` reads, because a log line is an
    observability side-effect, not a domain interface. Both, deliberately —
    callers that ignore the list are unaffected.
    """
    drifts: list[str] = []
    for h in (harnesses or HARNESSES).values():
        if not h.expected_version or not h.cli:
            continue
        if shutil.which(h.cli) is None:
            _log.debug("harness version check: %s not on PATH, skipping", h.cli)
            continue
        try:
            out = subprocess.run(h.version_cmd(), capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            _log.debug("harness version check: %s --version failed: %s", h.cli, e)
            continue
        m = _VERSION_RE.search(out.stdout or "")
        found = m.group(1) if m else None
        if found != h.expected_version:
            message = (
                f"harness version drift: {h.cli} is {found}, pinned "
                f"{h.expected_version} (adapter parse may break; capture a "
                f"fresh transcript and update the pin)"
            )
            _log.warning(
                "harness version drift: %s is %s, pinned %s "
                "(adapter parse may break; capture a fresh transcript "
                "and update the pin)",
                h.cli,
                found,
                h.expected_version,
            )
            drifts.append(message)
        else:
            _log.debug("harness version ok: %s %s", h.cli, found)
    return drifts
