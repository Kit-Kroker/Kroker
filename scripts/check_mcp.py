"""The MCP gate (spec 022, plan T050). One entry point for every Rust +
parity check the MCP adapter owes.

Invoked identically by .github/workflows/ci.yml and scripts/verify.py.
tests/test_verify.py reduces a command to its first two non-flag tokens,
so both sides naming ``python scripts/check_mcp.py`` is what keeps the
parity test green while cargo runs underneath. A bare ``run: cargo
test`` in ci.yml fails that test, and hiding the mcp job in a second
workflow file is worse: test_verify.py:16 reads ci.yml by fixed path, so
parity would silently stop being checked.

cargo is resolved through shutil.which (cargo.exe on Windows); the
parity step's SDLC_MCP_BIN gets the same treatment. Steps run cheapest
first and STOP at the first failure — unlike check_ui.py's collect-all,
because each cargo step is a full recompile and a late step's output
would bury the first real cause.

cargo absent means skip loudly and exit 0, following the check_ui.py
precedent: on a machine without Rust, "all gates pass" does not cover
the MCP adapter, and CI is the only place it is truly gated (CI=1 makes
the absence an error instead).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

CRATE = Path(__file__).resolve().parents[1] / "interfaces" / "mcp"
BIN = Path("interfaces/mcp/target/release/kroker-mcp")


def steps(cargo: str) -> list[tuple[str, list[str], Path | None]]:
    """(label, argv, cwd), cheapest first, stop at the first failure.

    The cargo steps run with cwd INSIDE the crate: rust-toolchain.toml is
    resolved by working directory (rustup ignores --manifest-path), and
    the repo root's default toolchain lacks the rustfmt/clippy components
    the pinned one carries. The manifest path is therefore ABSOLUTE (a
    root-relative one would not resolve from the crate dir). The parity
    step must run from the repo root (conftest, the parity test's
    relative paths, the fake bridge's registry walk).
    """
    manifest = str(CRATE / "Cargo.toml")
    return [
        (
            "cargo-fmt",
            [cargo, "fmt", "--manifest-path", manifest, "--check"],
            CRATE,
        ),
        (
            "cargo-clippy",
            [cargo, "clippy", "--manifest-path", manifest, "--all-targets", "--", "-D", "warnings"],
            CRATE,
        ),
        ("cargo-test", [cargo, "test", "--manifest-path", manifest], CRATE),
        (
            "cargo-build-release",
            [cargo, "build", "--release", "--manifest-path", manifest],
            CRATE,
        ),
        (
            "parity",
            [
                sys.executable,
                "-m",
                "pytest",
                "-m",
                "mcp",
                "tests/test_operator_mcp_parity.py",
                "-q",
            ],
            None,
        ),
    ]


def main() -> int:
    cargo = shutil.which("cargo")
    if cargo is None:
        if os.environ.get("CI"):
            print("mcp gate: FAILED (cargo not found in CI)", file=sys.stderr)
            return 1
        print("mcp gate: SKIPPED (cargo not found)")
        return 0

    bin_name = str(BIN) + (".exe" if sys.platform == "win32" else "")
    env = {**os.environ, "SDLC_MCP_BIN": bin_name}

    for label, argv, cwd in steps(cargo):
        print(f"=== mcp: {label} ===", flush=True)
        step_env = env if label == "parity" else None
        if subprocess.run(argv, env=step_env, cwd=cwd, check=False).returncode != 0:
            print(f"\nMCP FAILED: {label}", file=sys.stderr)
            return 1

    print("mcp gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
