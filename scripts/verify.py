"""One command that answers "am I done?" (B0).

An agent handed four separate commands runs two of them, misreads an exit
code, and reports success. This runs every gate the repo enforces and exits
non-zero if any fails, so "did it pass" is one observable condition rather
than four judgments.

Every gate runs even after one fails: an agent that has to re-run the whole
thing to discover the second problem will fix the first and stop. Order is
cheapest-first so the common failures surface in seconds.

These are exactly the gates CI runs -- tests/test_verify.py enforces that.
If this passes and CI does not, this script has a bug.
"""

from __future__ import annotations

import subprocess
import sys

# The gate/wait temporal tests deadlock in the local Windows environment
# (surgery plan Follow-up 1 documents the class); on Windows the local run
# of this tier skips them, CI on Linux runs the tier whole.
_TEMPORAL_IGNORES = (
    [
        f"--ignore=tests/{name}"
        for name in (
            "test_tool_approval_gate.py",
            "test_board_workflow.py",
            "test_budget_gate.py",
            "test_model_usage_capture.py",
            "test_e2e_greenfield.py",
            "test_dashboard_e2e.py",
        )
    ]
    if sys.platform == "win32"
    else []
)

GATES: tuple[tuple[str, list[str]], ...] = (
    ("ruff", ["ruff", "check", "."]),
    ("ruff-format", ["ruff", "format", "--check", "."]),
    ("file-size", [sys.executable, "scripts/check_file_size.py", "--full"]),
    ("mypy", ["mypy", "src"]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
    (
        "pytest-temporal",
        [sys.executable, "-m", "pytest", "-m", "temporal", "-q", *_TEMPORAL_IGNORES],
    ),
    ("ui", [sys.executable, "scripts/check_ui.py"]),
)


def main() -> int:
    failed: list[str] = []
    for name, command in GATES:
        print(f"=== {name} ===", flush=True)
        if subprocess.run(command).returncode != 0:
            failed.append(name)
    if failed:
        print(f"\nFAILED: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("\nall gates pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
