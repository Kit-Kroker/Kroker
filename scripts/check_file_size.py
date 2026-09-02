"""The file-size ratchet (B0 §2).

One hard ceiling of 1000 physical lines, enforced as a ratchet rather than a
flat rule: a file already over the ceiling is recorded in
`.file-size-baseline.json` and is merely forbidden to grow, so today's
monsters do not block a commit while the migration that shrinks them is still
in flight. Entries tighten automatically and are deleted once their file drops
under the ceiling, which makes the baseline a live measure of how much of the
surgery is left.

Two modes, because a pre-commit hook cannot see the whole tree. Default mode
takes the staged paths pre-commit passes and checks exactly those. `--full`
enumerates every tracked file via `git ls-files` and additionally prunes
entries whose file is gone; CI runs that one. Enumerating tracked files rather
than walking the filesystem keeps untracked working artifacts -- runs/,
artifacts/, .venv/, build/, .worktrees/ -- out by construction instead of by
an exemption list somebody has to maintain.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

CEILING = 1000
BASELINE_PATH = Path(".file-size-baseline.json")

# A path is checked iff it is in scope and matches no exemption.
IN_SCOPE_PREFIXES = (
    "src/",
    "tests/",
    "scripts/",
    "interfaces/",
    "agents/",
    "crew/",
    "blueprints/",
    "policy/",
    "docs/",
)

# NOTE: these are fnmatch patterns, not shell globs -- `*` matches `/` too, so
# "docs/superpowers/*" covers the whole subtree. Both "docs/*.html" and
# "docs/schemas/*" appear because the generated schema pages move into
# docs/schemas/ during this same change set and must stay exempt on both sides
# of that move.
EXEMPT_PATTERNS = (
    "docs/superpowers/*",  # write-once historical records
    "records/*",  # verbatim Claude Design exports
    "benchmarks/*",  # the measurement instrument's vendored corpus
    "tests/fixtures/hindsight-openapi.json",  # verbatim vendored schema
    "docs/*.html",  # generated schema pages
    "docs/schemas/*",  # ... and their post-move home
    "build/*",
    "*/dist/*",
    "*/node_modules/*",
    "uv.lock",
    "*-lock.json",
)


def physical_lines(data: bytes) -> int | None:
    """Newline-terminated lines plus a final unterminated one.

    Returns None for binary content, where a line count means nothing. The
    final-unterminated-line clause is why `wc -l` cannot implement this.
    """
    if b"\0" in data[:8192]:
        return None
    if not data:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def is_checked(path: str) -> bool:
    """True when the ceiling governs this path."""
    if any(fnmatch(path, pattern) for pattern in EXEMPT_PATTERNS):
        return False
    if path.startswith(IN_SCOPE_PREFIXES):
        return True
    # Root-level markdown: the living documents an agent reads first.
    return "/" not in path and path.endswith(".md")


def evaluate(
    sizes: dict[str, int], baseline: dict[str, int], *, prune: bool
) -> tuple[list[str], dict[str, int]]:
    """Judge measured sizes against the baseline.

    Returns the rejection messages and the baseline as it should now stand.
    `prune` drops entries for files that were not measured -- correct only in
    --full mode, where absence really does mean the file is gone.
    """
    errors: list[str] = []
    updated = dict(baseline)

    for path, size in sorted(sizes.items()):
        allowance = baseline.get(path)
        if allowance is None:
            if size > CEILING:
                errors.append(
                    f"{path}: {size} lines exceeds the {CEILING}-line ceiling. "
                    f"Split it along a process seam (see AGENTS.md)."
                )
            continue
        if size > allowance:
            errors.append(
                f"{path}: grew from {allowance} to {size} lines. Files in "
                f".file-size-baseline.json may shrink, never grow."
            )
        elif size <= CEILING:
            del updated[path]
        else:
            updated[path] = size

    if prune:
        for path in list(updated):
            if path not in sizes:
                del updated[path]

    return errors, updated


def _tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
    return [chunk.decode("utf-8", "surrogateescape") for chunk in out.split(b"\0") if chunk]


def _measure(paths: list[str]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for path in paths:
        if not is_checked(path):
            continue
        try:
            data = Path(path).read_bytes()
        except OSError:
            continue  # deleted or unreadable; --full's prune handles the entry
        count = physical_lines(data)
        if count is not None:
            sizes[path] = count
    return sizes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="paths to check (pre-commit passes these)")
    parser.add_argument(
        "--full",
        action="store_true",
        help="check every tracked file and prune stale baseline entries",
    )
    args = parser.parse_args(argv)

    baseline: dict[str, int] = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    paths = _tracked_files() if args.full else args.paths
    errors, updated = evaluate(_measure(paths), baseline, prune=args.full)

    for message in errors:
        print(message, file=sys.stderr)

    if updated != baseline:
        BASELINE_PATH.write_text(
            json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            "baseline tightened -- stage .file-size-baseline.json and re-commit",
            file=sys.stderr,
        )
        return 1

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
