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

# (label, npm argv). Cheapest first, same principle as verify.py GATES.
STEPS: tuple[tuple[str, list[str]], ...] = (
    ("install", ["ci"]),
    ("typecheck", ["run", "typecheck", "--workspace", DASH]),
    ("typecheck-ui", ["run", "typecheck", "--workspace", UI]),
    ("build-dashboard", ["run", "build", "--workspace", DASH]),
    # @kroker/ui's vite root is showcase/ (vite.config.ts): this build is what
    # ds-bundle's vite.preview() serves next -- without it, build-ds-bundle.ts
    # silently falls back to a URL with nothing listening on it.
    ("build-ui", ["run", "build", "--workspace", UI]),
    ("vitest-dashboard", ["run", "test", "--workspace", DASH]),
    ("playwright-browser", ["exec", "--", "playwright", "install", "--with-deps", "chromium"]),
    # Populates dist-ds/ (gitignored, spec C Task 12/13's DesignSync payload)
    # before vitest-ui runs: build-ds-bundle.spec.ts asserts against those
    # files and has no fixture of its own.
    ("ds-bundle", ["run", "ds:bundle", "--workspace", UI]),
    ("vitest-ui", ["run", "test", "--workspace", UI]),
    ("playwright", ["run", "test:pw", "--workspace", UI]),
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
        if subprocess.run([npm, *args]).returncode != 0:
            failed.append(label)

    if failed:
        print(f"\nUI FAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nui gate passes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
