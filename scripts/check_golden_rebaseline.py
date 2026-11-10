"""The golden re-baseline gate (020 T019, plan T042, FR-011, SC-003).

Round 020 re-captures the replay goldens from GraphWorkflow so every
fixture carries GraphWorkflow provenance before FeatureWorkflow is
deleted (US4). The gate proves the re-baseline is behaviourally empty:
for each `tests/replay/golden/*.json`, the JSON at `HEAD` and the JSON
in the working tree may differ in exactly two keys -- `workflow` and
`source_commit`, the provenance pair. Any other key that differs is a
STOP for the round (spec: "a non-empty commands, close or trace golden
diff").

Takes no arguments. Exits 0 when every golden is clean, or exits 1
naming each file and the offending key.

The comparison core (`golden_diffs`) is pure and is tested directly in
`tests/test_check_golden_rebaseline.py`; this module only adds the git
plumbing (`git show HEAD:<path>` for the old side) around it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "replay" / "golden"

# The provenance pair: the only keys a re-baseline may change.
ALLOWED_KEYS = frozenset({"workflow", "source_commit"})


def _canonical(value: object) -> str:
    """Canonical JSON text for a golden value. Comparing this rather than
    the parsed objects makes the comparison JSON-typed: 1, true and 1.0
    are equal as Python objects but differ as JSON, two identical NaNs
    are not equal as floats but are as text, and object key order stops
    mattering (020 T019, qa-chaos F1/F2)."""
    return json.dumps(value, sort_keys=True)


def golden_diffs(old: dict, new: dict) -> list[str]:
    """Names of every top-level key whose value differs between two
    goldens, excluding the provenance pair. A key present on only one
    side counts as differing (the provenance pair is exempt even
    one-sided: `write_fixtures` always writes both). Sorted, so output
    is deterministic."""
    offenders = []
    for key in sorted(set(old) | set(new)):
        if key in ALLOWED_KEYS:
            continue
        if _canonical(old.get(key)) != _canonical(new.get(key)):
            offenders.append(key)
    return offenders


def _head_json(path: Path) -> dict | None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    proc = subprocess.run(
        ["git", "show", f"HEAD:{rel}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None  # not in HEAD: reported as a whole-file difference
    return json.loads(proc.stdout)


def check() -> int:
    goldens = sorted(GOLDEN_DIR.glob("*.json"))
    failures: list[str] = []

    tracked = subprocess.run(
        ["git", "ls-files", "--", (GOLDEN_DIR.relative_to(REPO_ROOT)).as_posix()],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    if not goldens and not tracked:
        # An empty corpus would make the gate pass vacuously (qa-chaos F3).
        print(
            f"golden re-baseline gate: no goldens under {GOLDEN_DIR.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1

    for rel in tracked:
        if Path(rel).suffix == ".json" and not (REPO_ROOT / rel).exists():
            failures.append(f"{rel}: file deleted from the working tree")

    for path in goldens:
        rel = path.relative_to(REPO_ROOT).as_posix()
        new = json.loads(path.read_text(encoding="utf-8"))
        old = _head_json(path)
        if old is None:
            failures.append(f"{rel}: not in HEAD (new golden file)")
            continue
        for key in golden_diffs(old, new):
            failures.append(f"{rel}: {key}")

    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(
            f"golden re-baseline gate: {len(failures)} difference(s) outside "
            f"{sorted(ALLOWED_KEYS)}",
            file=sys.stderr,
        )
        return 1
    print(f"golden re-baseline gate: {len(goldens)} goldens differ only in {sorted(ALLOWED_KEYS)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print("usage: check_golden_rebaseline.py  (no arguments)", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(check())
