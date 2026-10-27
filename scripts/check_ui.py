"""The Node gate (spec C §9). One entry point for every JavaScript check.

Invoked identically by .github/workflows/ci.yml and scripts/verify.py.
tests/test_verify.py reduces a command to its first two non-flag tokens,
so both sides naming ``python scripts/check_ui.py`` is what keeps the
parity test green while npm runs underneath. A bare ``run: npm ci`` in
ci.yml fails that test, and hiding the UI job in a second workflow file
is worse: test_verify.py:16 reads ci.yml by fixed path, so parity would
silently stop being checked.

npm is npm.cmd on Windows. subprocess.run(["npm", ...]) raises
FileNotFoundError there rather than failing a gate, so every invocation
resolves the real executable through shutil.which first.

Node absent means skip loudly and exit 0, following the _TEMPORAL_IGNORES
precedent (verify.py:24). The cost is deliberate and stated in spec C
section 9: on a machine without Node, "all gates pass" does not cover the UI,
and CI is the only place the UI is truly gated.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DASH = "sdlc-dashboard"
UI = "@kroker/ui"

# T2 (sbatch 2026-10-19): the per-test budget the wrapper forwards to the
# two vitest steps. vitest's 5000 ms default is a container-load trap: the
# 006 SG-2 fire failed the wrapper 3/3 on one jsdom-heavy file timing out
# (environment setup alone measured ~30 s in kroker-dev) while the direct
# `npx vitest run` passed 374/374 twice — the timeout tracks wrapper +
# container load, not test content (.workspace/tmp/executor-006-SG2-report.md).
# 60 s = 12x the default and 2x the worst observed setup, still a real hang
# detector. The flag rides after the bare `--` so npm forwards it to vitest
# instead of consuming it; a value <= 5000 would be a no-op dressed as a fix.
VITEST_TEST_TIMEOUT_MS = 60_000

# (label, argv). Cheapest first, same principle as verify.py GATES. Every
# entry is a full command; "npm" entries get the resolved npm.cmd swapped
# in at run time, python entries carry the running interpreter already.
STEPS: tuple[tuple[str, list[str]], ...] = (
    ("install", ["npm", "ci"]),
    ("typecheck", ["npm", "run", "typecheck", "--workspace", DASH]),
    # 018 R-10: tokens-only colours/fonts, before any build output exists.
    (
        "raw-colours",
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts" / "check_raw_colours.py"),
        ],
    ),
    ("typecheck-ui", ["npm", "run", "typecheck", "--workspace", UI]),
    ("build-dashboard", ["npm", "run", "build", "--workspace", DASH]),
    # @kroker/ui's vite root is showcase/ (vite.config.ts): this build is what
    # ds-bundle's vite.preview() serves next -- without it, build-ds-bundle.ts
    # silently falls back to a URL with nothing listening on it.
    ("build-ui", ["npm", "run", "build", "--workspace", UI]),
    (
        "vitest-dashboard",
        [
            "npm",
            "run",
            "test",
            "--workspace",
            DASH,
            "--",
            f"--testTimeout={VITEST_TEST_TIMEOUT_MS}",
        ],
    ),
    (
        "playwright-browser",
        ["npm", "exec", "--", "playwright", "install", "--with-deps", "chromium"],
    ),
    # Populates dist-ds/ (gitignored, spec C Task 12/13's DesignSync payload)
    # before vitest-ui runs: build-ds-bundle.spec.ts asserts against those
    # files and has no fixture of its own.
    ("ds-bundle", ["npm", "run", "ds:bundle", "--workspace", UI]),
    (
        "vitest-ui",
        ["npm", "run", "test", "--workspace", UI, "--", f"--testTimeout={VITEST_TEST_TIMEOUT_MS}"],
    ),
    ("playwright", ["npm", "run", "test:pw", "--workspace", UI]),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    if sys.platform == "win32" and "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        pw_dir = Path("D:/own/.pw-browsers")
        if pw_dir.parent.exists():
            pw_dir.mkdir(parents=True, exist_ok=True)
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(pw_dir)

    npm = shutil.which("npm")
    if npm is None:
        print(
            "SKIPPED: npm is not on PATH, so the UI gate did not run.\n"
            "         This machine's `all gates pass` does NOT cover the UI.\n"
            "         CI runs this gate on every push (spec C, section 9).",
            flush=True,
        )
        return 0

    failed: list[str] = []
    for label, args in STEPS:
        print(f"=== ui: {label} ===", flush=True)
        cmd = [npm, *args[1:]] if args[0] == "npm" else args
        if subprocess.run(cmd).returncode != 0:
            failed.append(label)

    if failed:
        print(f"\nUI FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nui gate passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
