# B0 — Module Shape, Code Rules, and Documentation Architecture: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the convention layer — the rules, templates, enforcement, and documentation architecture that the later module surgery (spec A) and UI/Claude Design work (spec C) are carried out against.

**Architecture:** Two pieces of engineering — a shrink-only file-size ratchet enforced by pre-commit and CI, and `scripts/verify.py`, the one command that answers "am I done" — plus a documentation reorganisation. Nothing in `src/sdlc/` changes: B0 defines the target shape, it does not move code toward it. Tasks 1–4 are mechanical and verifiable by command; tasks 5–8 author the documents that encode the rules.

**Scope boundary, in force for every task:** this plan changes how *this repository is developed* — its structure, documents, scripts, and the rules binding agents that edit it. None of it is product functionality. Nothing here may be implemented by adding anything to `src/sdlc/`, and the product's own evaluation, telemetry and benchmark machinery is not repurposed as our tooling. See the **Deferred** section for why that boundary is easy to cross here specifically.

**Tech Stack:** Python 3.11+, pytest, pre-commit, ruff, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-02-b0-module-shape-and-docs-architecture-design.md`

## Global Constraints

- **Python >= 3.11**; install with `pip install -e ".[dev]"`. Re-run it after adding a new module if you hit `ModuleNotFoundError` (editable installs do not auto-discover new files).
- **`pytest` alone runs the fast unit tier only.** `pyproject.toml` sets `addopts = "-q -m 'not slow and not temporal and not docker and not prompt_eval and not crew'"`. Everything this plan adds belongs to that fast tier — do not mark any new test.
- **Every commit passes `pre-commit`**: `ruff` (with `--fix`), `ruff format`, `mypy` (scoped to `^src/`, so `scripts/` is not type-checked), plus trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-added-large-files, check-merge-conflict.
- **CI runs** `ruff check .`, `ruff format --check .`, `mypy src`, `pytest`. Anything you add under `scripts/` is linted and format-checked even though it is not type-checked.
- **File-size ceiling: 1000 physical lines.** Physical lines = newline-terminated lines plus a final unterminated one. `wc -l` is **not** an implementation of this — it counts newlines only and under-reports by one for a file with no trailing newline.
- **Windows is the primary platform.** Never create a symlink. Use `git mv` for moves so history follows.
- **`docs/superpowers/**` is write-once.** Existing specs, plans and reviews are historical records. When a task moves a file, do **not** update references to it inside `docs/superpowers/**` — those documents describe the tree as it was on the day they were written, and rewriting them destroys that. This applies even though ~30 plan files are still git-tracked despite `.gitignore`.
- **All repository documentation is written in English**, matching every existing document in the tree.
- **Commit message trailers** — every commit in this plan ends with:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
  ```
- **One deviation from the spec's wording, already decided:** spec deliverable 7 says `docs/roadmap/tier-*.md`. Not every section being split is a "tier", so the actual filenames are descriptive slugs (`tier-0-triage.md`, `service-platform.md`, `crew.md`, …). Read the spec's `tier-*.md` as "one file per epic group". Task 4 fixes the spec's wording so the two agree.

---

### Task 1: The file-size ratchet

The only engineering in B0. A pre-commit hook that rejects new files over 1000 lines, rejects growth in already-oversized files, and automatically tightens the baseline when an oversized file shrinks. The core logic is pure functions so it can be tested without git or a filesystem.

**Files:**
- Create: `scripts/check_file_size.py`
- Create: `tests/test_check_file_size.py`
- Create: `.file-size-baseline.json`
- Modify: `.pre-commit-config.yaml` (append a `repo: local` block)
- Modify: `.github/workflows/ci.yml` (add a step after "Ruff format check")

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `scripts/check_file_size.py` exposing `CEILING: int = 1000`, `physical_lines(data: bytes) -> int | None`, `is_checked(path: str) -> bool`, and `evaluate(sizes: dict[str, int], baseline: dict[str, int], *, prune: bool) -> tuple[list[str], dict[str, int]]`. Task 4 relies on the hook tightening `ROADMAP.md` out of the baseline automatically.

- [ ] **Step 1: Write the failing test**

Create `tests/test_check_file_size.py`:

```python
"""The file-size ratchet (B0 §2.3).

Every test here drives the pure core -- physical_lines, is_checked,
evaluate -- so none of them touch git or write to the tree.
"""

from __future__ import annotations

from scripts.check_file_size import CEILING, evaluate, is_checked, physical_lines


def test_physical_lines_counts_a_final_unterminated_line():
    # The reason `wc -l` is not an implementation of the spec's definition:
    # it counts newlines, so it reports 1 for the second case, not 2.
    assert physical_lines(b"a\nb\n") == 2
    assert physical_lines(b"a\nb") == 2


def test_physical_lines_of_empty_file_is_zero():
    assert physical_lines(b"") == 0


def test_physical_lines_returns_none_for_binary():
    assert physical_lines(b"pre\x00post") is None


def test_in_scope_paths_are_checked():
    assert is_checked("src/sdlc/workflows/feature.py")
    assert is_checked("tests/test_something.py")
    assert is_checked("scripts/check_file_size.py")
    assert is_checked("docs/features/clarify.md")
    assert is_checked("ROADMAP.md")


def test_write_once_records_are_exempt():
    assert not is_checked("docs/superpowers/plans/2026-08-31-crew-step-2.md")
    assert not is_checked("docs/superpowers/specs/2026-09-01-e50-design.md")


def test_verbatim_vendored_data_is_exempt():
    assert not is_checked("tests/fixtures/hindsight-openapi.json")
    assert not is_checked(
        "benchmarks/cases/deveval-geotext/reference/geotext/data_file/cities15000.txt"
    )


def test_generated_and_machine_managed_files_are_exempt():
    assert not is_checked("docs/roadmap.html")
    assert not is_checked("docs/schemas/roadmap.html")
    assert not is_checked("records/2026-07-12-factory-console/support.js")
    assert not is_checked("uv.lock")
    assert not is_checked("interfaces/dashboard/frontend/package-lock.json")


def test_benchmark_corpus_is_out_but_its_reader_is_in():
    assert not is_checked("benchmarks/cases/cat-cafe-monitoring/oracle/test_risk.py")
    assert is_checked("src/sdlc/benchmarks/importers/deveval.py")


def test_new_file_over_the_ceiling_is_rejected():
    errors, baseline = evaluate({"src/new.py": CEILING + 1}, {}, prune=False)
    assert errors and "src/new.py" in errors[0]
    assert baseline == {}


def test_new_file_under_the_ceiling_passes():
    errors, baseline = evaluate({"src/new.py": CEILING}, {}, prune=False)
    assert errors == []
    assert baseline == {}


def test_baselined_file_that_grew_is_rejected():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1431}, {"src/sdlc/activities.py": 1430}, prune=False
    )
    assert errors and "grew" in errors[0]
    assert baseline == {"src/sdlc/activities.py": 1430}


def test_baselined_file_held_at_its_size_passes():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1430}, {"src/sdlc/activities.py": 1430}, prune=False
    )
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1430}


def test_baselined_file_that_shrank_tightens_its_entry():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1200}, {"src/sdlc/activities.py": 1430}, prune=False
    )
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1200}


def test_baselined_file_that_dropped_under_the_ceiling_leaves_the_baseline():
    errors, baseline = evaluate({"ROADMAP.md": 500}, {"ROADMAP.md": 1647}, prune=False)
    assert errors == []
    assert baseline == {}


def test_prune_drops_entries_for_files_that_are_gone():
    errors, baseline = evaluate(
        {"src/sdlc/activities.py": 1430},
        {"src/sdlc/activities.py": 1430, "src/sdlc/deleted.py": 1100},
        prune=True,
    )
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1430}


def test_without_prune_an_unseen_entry_survives():
    # The hook only sees staged files, so absence is not evidence of deletion.
    errors, baseline = evaluate({}, {"src/sdlc/activities.py": 1430}, prune=False)
    assert errors == []
    assert baseline == {"src/sdlc/activities.py": 1430}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_check_file_size.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'scripts.check_file_size'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/check_file_size.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_check_file_size.py -q`
Expected: 16 passed.

Note that `benchmarks/cases` being exempt is not an invention of this task — `pyproject.toml`'s `[tool.ruff]` already carries `extend-exclude = ["benchmarks/cases"]` with the comment "vendored fixtures (third-party reference repos and their oracle tests) — data, not product code." The ratchet is applying a judgment this repo already made for its linter.

- [ ] **Step 5: Seed the baseline and confirm it matches the spec**

Run: `python scripts/check_file_size.py --full`

Expected: the script writes `.file-size-baseline.json`, prints `baseline tightened…`, and exits 1 (this is the fixer contract firing on first run, not a failure).

Then run: `cat .file-size-baseline.json`

Expected exactly these six entries, matching spec §2.1:

```json
{
  "ROADMAP.md": 1647,
  "src/sdlc/activities.py": 1430,
  "src/sdlc/harness/adapters.py": 1092,
  "src/sdlc/models.py": 1334,
  "src/sdlc/workflows/feature.py": 3673,
  "tests/test_assessment_workflow_e2e.py": 1177
}
```

**If any other path appears, stop and report it** — it means the scope or exemption rules in `is_checked` disagree with spec §2.1, and the spec is what must be reconciled, not the baseline.

- [ ] **Step 6: Verify the ratchet is now quiet**

Run: `python scripts/check_file_size.py --full`
Expected: no output, exit code 0. Confirm with `echo $?`.

- [ ] **Step 7: Wire the pre-commit hook**

Append to `.pre-commit-config.yaml`:

```yaml
  - repo: local
    hooks:
      - id: check-file-size
        name: file-size ratchet (1000 lines)
        entry: python scripts/check_file_size.py
        language: system
        pass_filenames: true
```

- [ ] **Step 8: Wire the CI step**

In `.github/workflows/ci.yml`, insert immediately after the "Ruff format check" step:

```yaml
      - name: File-size ratchet
        run: python scripts/check_file_size.py --full
```

- [ ] **Step 9: Verify the hook fires on a real violation**

```bash
python - <<'PY'
from pathlib import Path
Path("src/sdlc/_ratchet_probe.py").write_text("# probe\n" * 1001, encoding="utf-8")
PY
git add src/sdlc/_ratchet_probe.py
pre-commit run check-file-size --files src/sdlc/_ratchet_probe.py
```

Expected: FAIL, with `src/sdlc/_ratchet_probe.py: 1001 lines exceeds the 1000-line ceiling.`

Clean up: `git rm -f --cached src/sdlc/_ratchet_probe.py && rm src/sdlc/_ratchet_probe.py`

- [ ] **Step 10: Run the full fast suite and the whole hook set**

Run: `pytest`
Expected: the pre-existing suite passes, plus the 15 new tests.

Run: `pre-commit run --all-files`
Expected: all hooks pass (the ratchet included — the baseline is already accurate).

- [ ] **Step 11: Write the failing test for `scripts/verify.py`**

An agent handed four separate commands runs two of them, misreads an exit code, and declares victory. `verify.py` is the single observable success condition that replaces that judgment call. Its one real failure mode is drifting out of step with CI — a local "all gates pass" that CI then contradicts is worse than no script at all — so that is what the test pins.

Create `tests/test_verify.py`:

```python
"""verify.py must run everything CI runs.

A local "all gates pass" that CI then contradicts is worse than no script,
because it turns a check into false confidence. This test fails the moment
the two drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.verify import GATES

CI = Path(".github/workflows/ci.yml")


def _ci_commands() -> list[str]:
    """Every `run:` value in the workflow."""
    return [
        line.split("run:", 1)[1].strip()
        for line in CI.read_text(encoding="utf-8").splitlines()
        if re.match(r"\s+run:\s+\S", line)
    ]


def _gate_key(command: str) -> str:
    """What a command *does*, ignoring how it is launched.

    The first two non-flag tokens: enough to tell `ruff check` from
    `ruff format`, and insensitive to `python -m pytest -q` versus a bare
    `pytest`.
    """
    parts = [
        token
        for token in command.replace(sys.executable, "python").split()
        if not token.startswith("-") and token not in ("python", "python3")
    ]
    return " ".join(parts[:2])


def test_every_ci_gate_is_in_verify():
    # `pip install -e` is setup, not a gate: verify.py runs in an
    # already-installed tree.
    ci = {_gate_key(c) for c in _ci_commands() if not c.startswith("pip install")}
    covered = {_gate_key(" ".join(cmd)) for _, cmd in GATES}
    missing = ci - covered
    assert not missing, f"CI runs {sorted(missing)} but scripts/verify.py does not"


def test_gates_are_ordered_cheapest_first():
    names = [name for name, _ in GATES]
    assert names.index("ruff") < names.index("mypy") < names.index("pytest")
```

- [ ] **Step 12: Run it to verify it fails**

Run: `pytest tests/test_verify.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'scripts.verify'`.

- [ ] **Step 13: Write `scripts/verify.py`**

```python
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

GATES: tuple[tuple[str, list[str]], ...] = (
    ("ruff", ["ruff", "check", "."]),
    ("ruff-format", ["ruff", "format", "--check", "."]),
    ("file-size", [sys.executable, "scripts/check_file_size.py", "--full"]),
    ("mypy", ["mypy", "src"]),
    ("pytest", [sys.executable, "-m", "pytest", "-q"]),
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
```

- [ ] **Step 14: Run the tests, then run the thing itself**

Run: `pytest tests/test_verify.py -q`
Expected: 2 passed.

Run: `python scripts/verify.py`
Expected: five `=== gate ===` banners, then `all gates pass`, exit 0.

- [ ] **Step 15: Commit**

```bash
git add scripts/check_file_size.py scripts/verify.py \
        tests/test_check_file_size.py tests/test_verify.py \
        .file-size-baseline.json .pre-commit-config.yaml .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
feat(tooling): file-size ratchet — 1000-line ceiling, shrink-only baseline

B0 §2. One hard ceiling, enforced as a ratchet: a file already over it is
recorded in .file-size-baseline.json and merely forbidden to grow, so the
six current offenders do not block commits while the surgery that shrinks
them is still in flight. Entries tighten automatically and are deleted
once a file drops under the ceiling, which makes the baseline a live
measure of how much of the migration is left.

Default mode checks the paths pre-commit passes; --full enumerates via
git ls-files and prunes stale entries, and runs in CI. Enumerating
tracked files rather than walking the tree keeps untracked working
artifacts out by construction.

Physical lines, not `wc -l` output: the definition counts a final
unterminated line, which wc does not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 2: Reorganise `docs/` — `reference/`, `reports/`, `schemas/`

Twelve files currently sit loose in `docs/`. Spec §3 gives them three homes, split by durability: a reference document is maintained when it goes stale, a report is a snapshot nobody updates, a schema page is generated.

**Files:**
- Move (12): see the table in Step 1
- Modify: `README.md:108-122`, `scripts/aggregate_benchmarks.py:9,590`, `src/sdlc/models.py:339`, `docs/reports/feature-coverage-audit-2026-07-05.md:10`
- Do **not** modify: anything under `docs/superpowers/**`

**Interfaces:**
- Consumes: Task 1's ratchet (the moved HTML pages must stay exempt — `is_checked` already carries the `docs/schemas/*` pattern for exactly this move).
- Produces: `docs/reference/`, `docs/reports/`, `docs/schemas/`. Tasks 6–8 write into a `docs/` tree that already has its final shape.

- [ ] **Step 1: Move the twelve files**

```bash
mkdir -p docs/reference docs/reports docs/schemas

git mv docs/foundation.md                        docs/reference/
git mv docs/architecture-review-2026-07.md       docs/reference/
git mv docs/presentation-pipeline-temporal.md    docs/reference/

git mv docs/feature-coverage-audit-2026-07-05.md docs/reports/
git mv docs/deveval-import-report-2026-08-09.md  docs/reports/
git mv docs/external-ideas-2026-09.md            docs/reports/

git mv docs/agents-schema.html                   docs/schemas/
git mv docs/architecture-schema.html             docs/schemas/
git mv docs/benchmark.html                       docs/schemas/
git mv docs/benchmark-analysis.html              docs/schemas/
git mv docs/research-stage-schema.html           docs/schemas/
git mv docs/roadmap.html                         docs/schemas/
```

- [ ] **Step 2: Verify `docs/` root is clean and the schema cross-links survived**

Run: `ls docs/`
Expected: only `reference`, `reports`, `schemas`, `superpowers`. Nothing loose.

The six HTML pages link each other with bare relative hrefs (`href="research-stage-schema.html"`). They moved together, so those remain valid. Confirm no schema page reached outside its own directory:

Run: `grep -o 'href="[^"]*"' docs/schemas/*.html | grep -v 'href="#' | grep '\.\./\|docs/' | head`
Expected: no output.

- [ ] **Step 3: Update `README.md`**

Rewrite the six link targets in `README.md:108-122`:

| Old | New |
|---|---|
| `docs/foundation.md` | `docs/reference/foundation.md` |
| `docs/architecture-review-2026-07.md` | `docs/reference/architecture-review-2026-07.md` |
| `docs/roadmap.html` | `docs/schemas/roadmap.html` |
| `docs/architecture-schema.html` | `docs/schemas/architecture-schema.html` |
| `docs/agents-schema.html` | `docs/schemas/agents-schema.html` |
| `docs/research-stage-schema.html` | `docs/schemas/research-stage-schema.html` |
| `docs/benchmark.html` | `docs/schemas/benchmark.html` |
| `docs/benchmark-analysis.html` | `docs/schemas/benchmark-analysis.html` |

Each appears twice per line — once as link text, once as href. Update both.

- [ ] **Step 4: Update the benchmark generator's default output path**

This one matters more than a link: `scripts/aggregate_benchmarks.py` writes its output to a hardcoded default, so leaving it would silently recreate a loose `docs/benchmark-analysis.html` on the next run.

At line 9 (docstring usage line) and line 590 (`ap.add_argument("--out", default=…)`), change `docs/benchmark-analysis.html` to `docs/schemas/benchmark-analysis.html`.

- [ ] **Step 5: Update the two remaining inbound references**

- `src/sdlc/models.py:339` — a docstring mentioning `docs/agents-schema.html`; change to `docs/schemas/agents-schema.html`.
- `docs/reports/feature-coverage-audit-2026-07-05.md:10` — references `docs/architecture-review-2026-07.md` and `docs/foundation.md`. Both moved to `reference/`, and this file itself moved to `reports/`. Change both to `docs/reference/…` (repo-root-relative, which is the style that line already uses).

- [ ] **Step 6: Verify no live reference points at an old path**

```bash
git grep -n -E 'docs/(foundation|architecture-review-2026-07|presentation-pipeline-temporal|feature-coverage-audit-2026-07-05|deveval-import-report-2026-08-09|external-ideas-2026-09)\.md' \
  -- . ':!docs/superpowers'
git grep -n -E 'docs/(agents-schema|architecture-schema|benchmark|benchmark-analysis|research-stage-schema|roadmap)\.html' \
  -- . ':!docs/superpowers'
```

Expected: **no output from either.** `AGENTS.md:102` also names `docs/foundation.md` — if it still appears here, that is expected at this point; Task 5 rewrites that file wholesale. Note it and move on.

The `:!docs/superpowers` exclusion is deliberate: those are write-once records and keep their original paths.

- [ ] **Step 7: Verify the ratchet still passes**

Run: `python scripts/check_file_size.py --full`
Expected: no output, exit 0. The five oversized schema pages moved from `docs/*.html` (exempt) to `docs/schemas/*` (also exempt), so the baseline must not have changed.

Run: `git diff --stat .file-size-baseline.json`
Expected: no output.

- [ ] **Step 8: Run tests and commit**

Run: `pytest -q`
Expected: pass.

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: rehome the twelve loose files into reference/, reports/, schemas/

B0 §3. Split by durability rather than by date: reference documents are
maintained when they go stale, reports are snapshots nobody updates, and
the schema pages are generated. Leaving a fifth of the docs tree
unaccounted for would have made the new architecture advisory.

The schema pages cross-link each other with bare relative hrefs and moved
together, so those links are untouched. aggregate_benchmarks.py's
hardcoded --out default moves with them -- otherwise the next run would
have silently recreated a loose docs/benchmark-analysis.html.

References inside docs/superpowers/** are deliberately left pointing at
the old paths: those are write-once records of the tree as it was.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 3: `records/`, and dissolving `design/`

**Files:**
- Move: `design/Factory Console.dc.html`, `design/support.js`, `design/.thumbnail` → `records/2026-07-12-factory-console/`
- Create: `records/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the `records/<YYYY-MM-DD>-<topic>/` convention that spec C will publish design exports into.

- [ ] **Step 1: Move the export**

The date is the commit that added the files (`2e7b6c0`, 2026-07-12), not today.

```bash
mkdir -p records/2026-07-12-factory-console
git mv "design/Factory Console.dc.html" records/2026-07-12-factory-console/
git mv design/support.js                 records/2026-07-12-factory-console/
git mv design/.thumbnail                 records/2026-07-12-factory-console/
```

- [ ] **Step 2: Verify `design/` is gone**

Run: `ls design 2>&1`
Expected: `ls: cannot access 'design': No such file or directory` (git removes the directory once empty).

Run: `ls -a records/2026-07-12-factory-console/`
Expected: `.thumbnail`, `Factory Console.dc.html`, `support.js`.

- [ ] **Step 3: Confirm the export still opens**

`Factory Console.dc.html` loads its runtime with `<script src="./support.js">`. Both moved together, so the relative reference holds.

Run: `grep -c 'src="./support.js"' "records/2026-07-12-factory-console/Factory Console.dc.html"`
Expected: `1`.

- [ ] **Step 4: Write `records/README.md`**

```markdown
# records/

Design exports, verbatim, one directory per session: `<YYYY-MM-DD>-<topic>/`.

These are raw Claude Design output (`*.dc.html` plus the `support.js`
runtime they load). They live here rather than under `docs/` on purpose:
they are a dated record of what a design looked like on a day, not
documentation anyone maintains. Nothing here is edited after it lands. If
a design is revised, that is a new dated directory.

Full dates, not months -- a topic can be revisited twice in one month, and
a date-ordered listing is the whole point of the directory.

What is *extracted* from a record -- design tokens, components, and the
feature-clause document for each component -- lives with the UI code and
is maintained there. The record is the source, never the reference.

Records are exempt from the file-size ceiling (`AGENTS.md`): they are not
authored here and cannot be split without ceasing to be what they vendor.
```

- [ ] **Step 5: Verify the ratchet accepts the move**

`design/support.js` (1687 lines) was out of scope under `design/`; at its new path it matches the `records/*` exemption.

Run: `python scripts/check_file_size.py --full`
Expected: no output, exit 0.

Run: `git diff --stat .file-size-baseline.json`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: dissolve design/ into records/2026-07-12-factory-console/

B0 §8. Design exports get dated directories under records/ at the repo
root -- tracked, but outside docs/, so raw visual artifacts never dilute
documentation anyone maintains. The existing Factory Console export
predates the scheme and becomes its first record rather than an orphan
directory at the root; it is dated by the commit that added it (2e7b6c0),
not by today.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 4: Split `ROADMAP.md`, and stop `ARCHITECTURE.md` lying

Two fixes to the documents an agent reads first. `ROADMAP.md` is 1647 lines across 18 sections; §§9–17 are epic detail that belongs in its own files. `ARCHITECTURE.md` calls the orchestrator `FactoryWorkflow` in four places; the class has been `FeatureWorkflow` since `src/sdlc/workflows/feature.py:825`.

This task is also the ratchet's first real exercise: `ROADMAP.md` drops under the ceiling, so the hook must tighten it out of the baseline.

**Files:**
- Modify: `ROADMAP.md` (keep lines 1–483, append an index)
- Create: `docs/roadmap/{filesystem-first,tier-0-triage,tier-2-edcr,service-platform,product-outcome,pipeline-as-data,ordering,agent-board,crew}.md`
- Modify: `ARCHITECTURE.md:36,59,73,336`
- Modify: `docs/superpowers/specs/2026-09-02-b0-module-shape-and-docs-architecture-design.md` (the `tier-*.md` wording)
- Modify: `.file-size-baseline.json` (via the hook)

**Interfaces:**
- Consumes: Task 1's ratchet.
- Produces: `docs/roadmap/` — Task 5's root `AGENTS.md` links to it.

- [ ] **Step 1: Split §§9–17 into nine files**

Section boundaries in the current `ROADMAP.md` (a section runs to the line before the next `## `; §17 runs to EOF at 1647):

| Lines | New file | Section |
|---|---|---|
| 484–905 | `docs/roadmap/filesystem-first.md` | §9 Filesystem-first work items (`E-`) |
| 906–1037 | `docs/roadmap/tier-0-triage.md` | §10 Tier 0 — repository triage & tidy-up |
| 1038–1240 | `docs/roadmap/tier-2-edcr.md` | §11 Tier 2 — the EDCR port |
| 1241–1281 | `docs/roadmap/service-platform.md` | §12 Service platform |
| 1282–1326 | `docs/roadmap/product-outcome.md` | §13 Product outcome |
| 1327–1449 | `docs/roadmap/pipeline-as-data.md` | §14 Pipeline as data |
| 1450–1501 | `docs/roadmap/ordering.md` | §15 Suggested ordering across §§10–14 |
| 1502–1570 | `docs/roadmap/agent-board.md` | §16 Agent board |
| 1571–1647 | `docs/roadmap/crew.md` | §17 The crew |

Move the text **verbatim**. Promote each file's leading `## N. Title` to `# Title` (it is now the document's own title), and drop the section number — numbering that survives the split becomes a lie the moment a file is added.

Do not reword, re-status, or "tidy" any item while moving it. `ROADMAP.md` tracks what is true on `main`; an edit smuggled into a move is invisible in a diff this large.

- [ ] **Step 2: Truncate `ROADMAP.md` and append the index**

Keep lines 1–483 (preamble plus §§0–8). Replace everything from line 484 to EOF with:

```markdown
## 9. Epics, by group

The per-epic detail lives in `docs/roadmap/`. This file keeps what is read
end-to-end — phase summary, requirements, criteria, ADR index, and the
ranked next increments above. Each file below tracks what is true on `main`;
in-flight work lives in its design doc until merge.

| Group | File |
|---|---|
| Filesystem-first work items (`E-`) | [`filesystem-first.md`](docs/roadmap/filesystem-first.md) |
| Tier 0 — repository triage & tidy-up (`E-40`…`E-44`) | [`tier-0-triage.md`](docs/roadmap/tier-0-triage.md) |
| Tier 2 — the EDCR port (`E-45`…`E-56`) | [`tier-2-edcr.md`](docs/roadmap/tier-2-edcr.md) |
| Service platform (`E-57`…`E-63`) | [`service-platform.md`](docs/roadmap/service-platform.md) |
| Product outcome (`E-64`…`E-71`) | [`product-outcome.md`](docs/roadmap/product-outcome.md) |
| Pipeline as data (`E-72`…`E-77`) | [`pipeline-as-data.md`](docs/roadmap/pipeline-as-data.md) |
| Suggested ordering across the groups | [`ordering.md`](docs/roadmap/ordering.md) |
| Agent board (`E-78`) | [`agent-board.md`](docs/roadmap/agent-board.md) |
| The crew (`E-88`) | [`crew.md`](docs/roadmap/crew.md) |
```

- [ ] **Step 3: Verify nothing was lost in the split**

Every `E-` identifier that existed before must still exist somewhere.

```bash
git show HEAD:ROADMAP.md | grep -oE '\bE-[0-9]+[a-z]?\b' | sort -u > /tmp/e-before.txt
cat ROADMAP.md docs/roadmap/*.md | grep -oE '\bE-[0-9]+[a-z]?\b' | sort -u > /tmp/e-after.txt
diff /tmp/e-before.txt /tmp/e-after.txt
```

Expected: no output.

Then check the line accounting:

```bash
wc -l ROADMAP.md docs/roadmap/*.md
```

Expected: `ROADMAP.md` around 500 lines (well under the ceiling), and the nine files summing to roughly 1164 plus one promoted-title line each.

- [ ] **Step 4: Let the ratchet tighten `ROADMAP.md` out of the baseline**

Run: `python scripts/check_file_size.py --full`

Expected: prints `baseline tightened…`, exits 1, and rewrites `.file-size-baseline.json`.

Run: `cat .file-size-baseline.json`

Expected: five entries — `ROADMAP.md` is gone.

Run again: `python scripts/check_file_size.py --full`
Expected: no output, exit 0.

This is the mechanism working as designed, not an error: the ratchet advanced on its own the moment the file dropped under the ceiling.

- [ ] **Step 5: Fix the `FactoryWorkflow` drift at all four sites**

In `ARCHITECTURE.md`, replace `FactoryWorkflow` with `FeatureWorkflow` at:

- `:36` — the §2 component diagram node: `FW[FactoryWorkflow + MaintenanceWorkflow…]`
- `:59` — the §2 responsibility table row
- `:73` — the §3 stage-DAG sentence: ``One `FactoryWorkflow` per run``
- `:336` — "`code_fix` actions start brownfield FactoryWorkflow children"

All four, not only §3: two of them precede §3, so fixing §3 alone would leave the document wrong in the first diagram a reader meets.

Verify: `grep -c FactoryWorkflow ARCHITECTURE.md`
Expected: `0`.

Then confirm the replacement names something real: `grep -n "class FeatureWorkflow" src/sdlc/workflows/feature.py`
Expected: one hit at `:825`.

- [ ] **Step 6: Reconcile the spec's filename wording**

The spec's deliverable 7 and §3 tree say `docs/roadmap/tier-*.md`, but only two of the nine files are tiers. In `docs/superpowers/specs/2026-09-02-b0-module-shape-and-docs-architecture-design.md`, change both occurrences of `tier-*.md` to `<group>.md`, and in the §3 tree comment change `# ROADMAP.md §§9-17, split by tier` to `# ROADMAP.md §§9-17, one file per epic group`.

A spec and its implementation disagreeing on a filename is exactly the drift §3 exists to prevent.

- [ ] **Step 7: Run everything and commit**

Run: `pytest -q && pre-commit run --all-files`
Expected: all pass.

```bash
git add -A
git commit -m "$(cat <<'EOF'
docs: split ROADMAP §§9-17 into docs/roadmap/, fix ARCHITECTURE drift

B0 §3. ROADMAP.md was 1647 lines across 18 sections -- the single worst
file in the repo to put in a context window. The nine epic groups move to
docs/roadmap/ behind a thin index; the root file keeps what is read
end-to-end (phase summary, requirements, criteria, ADR index, ranked next
increments) and lands near 500 lines. Text moved verbatim; every E-
identifier is accounted for.

ARCHITECTURE.md called the orchestrator FactoryWorkflow at lines 36, 59,
73 and 336 while the class has been FeatureWorkflow since feature.py:825.
All four, because two of them precede the section where the name is
explained -- a repo that teaches agents to read its architecture doc
first cannot have that doc wrong in its first diagram.

The baseline lost its ROADMAP.md entry on its own: the ratchet tightened
when the file dropped under the ceiling, which is the mechanism's first
real exercise.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 5: Root `AGENTS.md` and `CLAUDE.md`

The two documents every agent meets first. `AGENTS.md` gains the cutting principle, the size rule, both role rules, and the stage migration table that is authoritative during the transition. `CLAUDE.md` — currently zero bytes and untracked — becomes the pointer that makes the whole co-located layer function.

**Files:**
- Modify: `AGENTS.md` (add four sections; fix the stale `docs/` links at `:102`)
- Create: `CLAUDE.md` (and **commit it** — it exists on disk but is untracked)

**Interfaces:**
- Consumes: `docs/roadmap/` (Task 4), `docs/reference/` (Task 2).
- Produces: the migration table that spec A updates on every stage move.

- [ ] **Step 1: Write `CLAUDE.md` in full**

Exact content — it is short on purpose, and the middle paragraph is the load-bearing part:

```markdown
# CLAUDE.md

The conventions for editing this repository live in
[`AGENTS.md`](AGENTS.md). Read it first. It is the tool-agnostic file, and
everything in it applies to you.

**Before editing files in a subpackage or stage, read the nearest
`AGENTS.md` in that directory.** Rules that only hold locally -- a slice's
invariants, its Temporal traps, how to run just its tests -- live beside
the code rather than in this file, and they are not loaded for you
automatically.

Do not treat `agents/` (the directory) as instructions. That is the
product's own runtime role registry, loaded by
`src/sdlc/agents/loader.py`. `AGENTS.md` files are for whoever is editing
the repo. `AGENTS.md` explains the distinction.
```

Do not create a symlink. Windows is the primary platform here and symlinked instruction files are unreliable on it.

- [ ] **Step 2: Verify `CLAUDE.md` will actually be tracked**

Run: `git check-ignore -v CLAUDE.md; echo "exit=$?"`
Expected: `exit=1` (no ignore rule matches — the file can be added).

- [ ] **Step 3: Fix the stale references in `AGENTS.md`**

`AGENTS.md:102` reads:

> `docs/foundation.md`, `docs/BENCHMARK.md`, and the self-contained schema docs under `docs/*.html` for deeper contract- and benchmark-level detail.

Two things are wrong: `foundation.md` moved in Task 2, and `docs/BENCHMARK.md` has never existed — the file is `BENCHMARK.md` at the root. Replace with:

> `docs/reference/foundation.md`, `BENCHMARK.md`, and the generated schema pages under `docs/schemas/` for deeper contract- and benchmark-level detail.

Also update the "Further reading" entry for `ROADMAP.md` to mention that per-epic detail now lives in `docs/roadmap/`.

- [ ] **Step 4: Add the four new sections to `AGENTS.md`**

Append after the existing "Git worktrees are the norm here" section, before "Further reading". Each section states the rule and its reason — a rule an agent cannot see the point of is a rule it will optimise around.

**Section: "How this repo is cut"** — must state:
- Cut along the seams of the process; a stage is the unit of agent work. Not technical layers, not domain entities.
- The seam test is the common closure principle: things that change together live together.
- Vertical slices `src/sdlc/stages/<stage>/` for the pipeline; horizontal packages (`harness/`, `board/`, `channels/`, `memory/`, `observability/`, `artifacts/`) for generic subdomains, which are deliberately *not* forced into the stage shape.
- Recursive for non-pipeline domains: a slice is a phase of that subdomain's own process (`assessment` → scan / discover / risk / gates).
- **Cross-stage calls are banned**; the orchestrator is the sole coordinator. Importing a *type* another stage produces is not a call.
- **The producer owns its artifacts.** A stage's `models.py` holds what it produces; `core/` holds only what no stage produces — config and envelopes (`PipelineConfig`, `GateDecision`, `RoleConfig`, `IdeaBrief`).
- Link to `docs/framework.md` for the seam contract and to the spec for the reasoning.

**Section: "File size"** — must state:
- One hard ceiling: 1000 physical lines. No soft target, no waiver.
- Size is governed by the seam; the ceiling is a tripwire against monsters, not a design guide.
- `.file-size-baseline.json` records today's offenders. They may shrink, never grow. Entries delete themselves when a file drops under the ceiling.
- The scope and exemptions, in one sentence each, pointing at `scripts/check_file_size.py` as the authority.

**Section: "Who may change what"** — must state both rules:
- *The sandbox boundary.* Orchestrator agents in the primary checkout may edit specs, stage contracts and schemas. Sandboxed coding harnesses (`claude -p`, `opencode run`, inside a per-task worktree) may modify only code and tests, and may not edit `<stage>.md` files or root specs. Give the reason: when Kroker's pipeline runs against Kroker, a harness is editing this repo, and a harness that can rewrite the contract it is judged against has no contract.
- *The artifact boundary.* Whoever changes a stage's behaviour updates its clauses in the same diff. A clause without code and code without a clause are both defects.

**Section: "Where each stage lives"** — the migration table, with this exact preamble:

> Migration is piecemeal. **This table is the authoritative map** while it is in progress: look a stage up here rather than searching two locations. Updating it is part of moving a stage, not a follow-up.

Seed it with every stage in `FeatureWorkflow`'s DAG, all with status `in feature.py`:

| Stage | Lives in | Status |
|---|---|---|
| intake | `src/sdlc/workflows/feature.py` | in `feature.py` |
| context (brownfield) | `src/sdlc/workflows/feature.py` | in `feature.py` |
| research | `src/sdlc/workflows/feature.py` | in `feature.py` |
| clarify | `src/sdlc/workflows/feature.py` | **pilot — moves first (spec A)** |
| architecture | `src/sdlc/workflows/feature.py` | in `feature.py` |
| plan | `src/sdlc/workflows/feature.py` | in `feature.py` |
| code | `src/sdlc/workflows/feature.py` | in `feature.py` |
| review | `src/sdlc/workflows/feature.py` | in `feature.py` |
| qa | `src/sdlc/workflows/feature.py` | **pilot — moves first (spec A)** |
| analyze | `src/sdlc/workflows/feature.py` | in `feature.py` |
| merge | `src/sdlc/workflows/feature.py` | in `feature.py` |
| deploy | `src/sdlc/workflows/feature.py` | in `feature.py` |
| retro / reflect | `src/sdlc/workflows/feature.py` | in `feature.py` |

Follow it with the rule: **you touched a stage, you move it.**

- [ ] **Step 5: Verify**

Run: `git grep -n "docs/foundation.md\|docs/BENCHMARK.md" -- AGENTS.md`
Expected: no output.

Run: `python scripts/check_file_size.py --full && echo OK`
Expected: `OK` (`AGENTS.md` grows but stays far under 1000).

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(agents): the cutting principle, the size rule, role rules, stage map

B0 §6. AGENTS.md gains the four things an agent needs before it edits
anything here: how the repo is cut (process seams, stage as the unit,
producer owns its artifacts), the 1000-line ceiling and its ratchet, who
may change what (the sandbox boundary and the artifact boundary), and the
stage migration table that is authoritative while the move is in flight.

CLAUDE.md was zero bytes and untracked, so Claude Code started every
session knowing nothing about this repo. It is now a pointer carrying the
one directive the whole co-located layer depends on -- read the nearest
AGENTS.md before editing -- because nested-AGENTS.md discovery varies by
assistant and version, and an explicit instruction works under all of
them. Not a symlink: Windows is the primary platform here.

Also fixes two stale references at AGENTS.md:102 -- foundation.md moved to
docs/reference/, and docs/BENCHMARK.md never existed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 6: `docs/documentation-rules.md`

How to write documents in this repo. It is the file `docs/features/AGENTS.md` and every slice's `AGENTS.md` will point at, so it has to be specific enough to settle arguments.

**Files:**
- Create: `docs/documentation-rules.md`

**Interfaces:**
- Consumes: the tree from Tasks 2 and 4.
- Produces: the rules Tasks 7 and 8 cite rather than restate.

- [ ] **Step 1: Write the document**

Required sections and the exact rules each must carry:

**"Three documents, one job each"** — the table from spec §3 (`<stage>.md` = WHAT, `AGENTS.md` = HOW, module docstring = WHY), plus the reason they do not collapse: `<stage>.md` is evergreen product documentation, `AGENTS.md` carries tool-specific guardrails with a shorter lifetime. Name the failure mode explicitly so a reviewer can point at it: **an `AGENTS.md` that has grown into a restatement of its `<stage>.md` is a defect.** Cite `src/sdlc/dashboard/api.py:1-16` as the model docstring and say what makes it good — it explains why the module sits under `src/` at all, why there are three write routes rather than five, and where its security posture stops being acceptable.

**"What lives where"** — a table of the tree from spec §3, with the durability rule stated plainly: `reference/` is maintained when it goes stale, `reports/` are snapshots that are never updated, `schemas/` is generated (say which script regenerates `benchmark-analysis.html`), `roadmap/` tracks main, `superpowers/specs` and `superpowers/plans` are **write-once** — never edited after they land, and never updated when a file they mention moves.

**"`ARCHITECTURE.md` and `ROADMAP.md` describe `main` only"** — currently tribal knowledge and the reason this section exists. In-flight work lives in its design doc under `docs/superpowers/specs/` until merge. State the corollary: a spec is not documentation of the system, it is a record of a decision, so nothing should cite one as evidence of current behaviour.

**"`agents/` is not `AGENTS.md`"** — restate the distinction the root `AGENTS.md` already makes. `agents/` is the product's runtime role registry, loaded by `src/sdlc/agents/loader.py`; `AGENTS.md` files are instructions for whoever edits the repo. Adding `AGENTS.md` files throughout makes this more confusable, not less.

**"Documents move with their code"** — a co-located document that did not change in a diff that changed its module's behaviour is a review finding, not an oversight to fix later. This is the artifact boundary from `AGENTS.md`, stated for documents.

**"The root `AGENTS.md` is a router"** — from spec §6. It indexes where things live, which commands to run, which rules bind, and where the depth is; it never inlines a stage's contracts, schemas, or business logic. **Ceiling: 250 lines**, far below the repo-wide 1000, because a router that needs a thousand lines has stopped being one. Give the reason: an unbounded root instruction file spends context budget on every session and flattens everything it holds to the same priority, so the one rule that mattered reads like the twenty that did not. The migration table is the shape to imitate — paths and statuses, pointing outward.

**"What we write down, and which question each answers"** — from spec §4. The three-row table (spec = what we intend, clauses = what behaviour matters, the test suite = what we verify), the reason the second is not the first, and the honest note that *what actually happened* has no artifact here yet.

State the product/harness boundary explicitly in this section, because it is the confusion most likely to occur in this repo specifically: Kroker the product implements telemetry, evals and golden cases for the pipelines it runs on **other** repositories (`src/sdlc/observability/`, `src/sdlc/eval/`, `benchmarks/cases/`). Those are product features. This repository's own development harness — the environment agents editing Kroker work in — is a separate thing, and the rule runs both ways: **nothing about how we develop this repo is ever added to `src/sdlc` as product functionality, and the product's machinery is not silently repurposed as our tooling.**

**"Language and register"** — English; prose over bullet lists where a reason needs giving; anchor claims to files and line numbers so a reader can check them; no aspirational statements about what the system will do.

- [ ] **Step 2: Verify**

Run: `python scripts/check_file_size.py --full && echo OK`
Expected: `OK`.

Read the file end to end and confirm every rule it states is one this repo actually follows after Tasks 1–5. A rule that describes an intention rather than the tree is the failure this document exists to prevent.

- [ ] **Step 3: Commit**

```bash
git add docs/documentation-rules.md
git commit -m "$(cat <<'EOF'
docs: documentation-rules.md — how documents work in this repo

B0 §3. Three documents per unit with one job each and the reason they do
not collapse; what lives in each part of the docs tree, split by
durability; the main-only convention for ARCHITECTURE.md and ROADMAP.md,
which until now was tribal knowledge; the agents/ vs AGENTS.md
distinction; and the rule that a co-located document which did not move
in a behaviour-changing diff is a review finding.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 7: `docs/framework.md` — the stack, and the seam contract

The reference an agent reads before writing workflow code. Spec deliverable 5 lands here: `StageContext`, the step signature, the Temporal rules, and the activity registration contract are *documented* by B0; the code is spec A's.

**Files:**
- Create: `docs/framework.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the contract spec A implements against, and the four rules every slice `AGENTS.md` template (Task 8) points back to.

- [ ] **Step 1: Write the document**

Required sections:

**"The stack"** — Temporal (`temporalio` 1.30.0) orchestrates; Pydantic AI agents *think* and emit schema-validated artifacts, never touching tools; coding harnesses *do the work* inside sandboxed per-task git worktrees, and only their diff is admitted as an artifact. Two or three sentences each, pointing at `ARCHITECTURE.md` §1–2 rather than restating it.

**"The step contract"** — reproduce from spec §1.1:

```python
async def step(ctx: StageContext, ...) -> Artifact: ...
```

The eleven services, as the five-group table with its anchors (`emit` `feature.py:1226`, `stage` `:1234`, `run_role` `:1283`, `cached_stage` `:1145`, `revisable_stage` `:1773`, `record` `:1012`, `judge` `:1026`, `recall` `:1062`, `retain` `:1080`, `gate` `gates.py:168`, `ask_and_wait` `feature.py:2845-2887`). Then the two rules that keep the protocol from rotting:

- **Data travels in the signature; only capabilities go on the context.** The codebase map, integration head, brief digest and seeded work are values the orchestrator holds, not services. The review question for any proposed addition is "is this a service the orchestrator provides, or a value it holds?"
- **A step owns no run state across calls.** It takes parameters, returns an artifact. Use `_escalation_round` (`feature.py:865`, `:2025`) as the worked example, and cite `gates.py:84-88`, which already documents the identical hazard for gate confidence: gates interleave, wave mode runs `_dev_task` concurrently, and instance state gets silently overwritten.

**"What Temporal actually constrains"** — the four rules, each with its reason, because an agent that does not know why will work around them:

1. **Handlers live on the workflow class's MRO, never in a step module.** `GateHost` (`workflows/gates.py:54`) is a mixin carrying `@workflow.signal submit_gate_decision` (`:98`) and three `@workflow.query` handlers (`:108`, `:112`, `:116`), inherited by `FeatureWorkflow` — mixins are blessed. A handler in a step module is on no workflow class's MRO and is simply never registered.
2. **Mutable run state has exactly one owner: the workflow instance.**
3. **The passthrough principle.** A step module is imported inside the sandbox. Inside it, `workflow.unsafe.imports_passed_through()` covers anything with **host-shared identity or import-time effects**; ordinary sandboxed import is for pure workflow-side helpers only. Give the four resolved categories — third-party/IO-adjacent; model modules; the agent registry; workflow classes used as child handles — and give the identity reason for model modules in full, because it is the one that surprises people: payloads survive a duplicate class fine (they are untyped JSON), but `X is EnumCopy.MEMBER` across a host/sandbox pair is silently always `False`, and `feature.py` performs nine such comparisons, three of them load-bearing for the pilots (`:1891`, `:1927` inside `_dev_task`; `:2293` at the task gate). Say plainly that this is a **stricter discipline than `feature.py` follows today** — its block spans `:20-223` and passes through roughly thirty internal modules including pure helpers.
4. **A step module's module level is constants only.** No clock, no environment reads, no I/O at import. `feature.py:225+` is the model.

Then the carve-out: **workflow classes used as child-workflow handles are passed through** (`CrewTaskWorkflow.run` at `:1938`, `DeploymentWorkflow.run` at `:3601`) — importing a `@workflow.defn` module inside the sandbox re-executes it and duplicates the class identity.

Close with the payload note: `pydantic_data_converter`'s `PydanticPayloadConverter.to_payload` writes only `metadata={"encoding": "json/plain"}` and reconstructs from the current signature's `type_hint` (`temporalio/contrib/pydantic.py:66-99`), so relocating a Pydantic model between modules is invisible to in-flight histories. The residual: a model's **field shape** must not change mid-deploy. There is no `workflow.patch` / `workflow.deprecated` anywhere in `src/`.

**"Activity registration"** — each slice exports `ACTIVITIES: list[Callable]`; `src/sdlc/stages/__init__.py` holds `STAGE_MODULES`; the worker composes `[a for m in STAGE_MODULES for a in m.ACTIVITIES]`. Explicit, never auto-discovered — registration must stay deterministic and greppable. Note what it replaces: `worker.py:29-131`, a 103-line import block that every new activity extends.

**"Ownership of types"** — the producer owns its artifacts; `core/` holds only what no stage produces. State the rejected reading and why: "any type two stages touch belongs in `core/`" would empty every slice's `models.py` back into a single file, since `ClarifiedRequirements` alone is referenced across six `src/` files.

**"Moving a symbol"** — call sites re-point, **no re-export shims**. Two reasons: two legal import paths for one symbol is exactly the confusion the migration table exists to prevent, and shims hold `models.py` and `activities.py` at their current size, defeating the ratchet.

- [ ] **Step 2: Verify every anchor in the document**

The document is mostly line-anchored claims, and a wrong anchor is worse than no anchor. Check each:

```bash
sed -n '825p;1145p;1226p;1234p;1283p;1773p;1938p;2025p;3601p' src/sdlc/workflows/feature.py
sed -n '54p;98p;108p;168p' src/sdlc/workflows/gates.py
sed -n '1891p;1927p;2293p' src/sdlc/workflows/feature.py
grep -c FactoryWorkflow ARCHITECTURE.md
```

Expected: each line is what the document claims it is (`class FeatureWorkflow`, `_cached_stage`, `_emit`, `_stage`, `_run_role`, `_revisable_stage`, the `CrewTaskWorkflow.run` child start, the `_escalation_round` increment, the `DeploymentWorkflow.run` child start; `class GateHost`, `submit_gate_decision`, the first `@workflow.query`, `_gate`; the three enum `is` comparisons), and `0` for the drift check.

- [ ] **Step 3: Commit**

```bash
git add docs/framework.md
git commit -m "$(cat <<'EOF'
docs: framework.md — the stack and the seam contract

B0 deliverable 5, as documentation; the code is spec A's. Carries the
step signature, StageContext's eleven services with their anchors, the
data-in-the-signature rule that keeps the protocol from accreting, and
the state-ownership rule with _escalation_round as its worked example.

The four Temporal rules are stated with their reasons, because an agent
that does not know why will work around them. The one that surprises:
importing a model module inside the sandbox duplicates every class in it,
and while payloads survive (untyped JSON), enum identity does not --
feature.py performs nine `is` comparisons, three of them inside the code
the pilots move. This is a stricter discipline than feature.py follows
today and the document says so rather than implying it is the status quo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

### Task 8: `docs/modes/`, `docs/features/AGENTS.md`, and the templates

The methodology guides and the two templates every future slice is stamped from. Templates come with their guides because a template nobody knows how to fill in is a template that gets copied wrong.

**Files:**
- Create: `docs/modes/feature-clause-writing.md`
- Create: `docs/modes/slice-migration.md`
- Create: `docs/modes/focused-specs.md`
- Create: `docs/modes/report-first.md`
- Create: `docs/modes/lesson-to-skill.md`
- Create: `docs/features/AGENTS.md`
- Create: `docs/templates/stage.md`
- Create: `docs/templates/stage-AGENTS.md`

**Interfaces:**
- Consumes: `docs/documentation-rules.md` (Task 6), `docs/framework.md` (Task 7) — cite them, do not restate them.
- Produces: the templates spec A copies for `clarify` and `qa`.

- [ ] **Step 1: Write `docs/templates/stage.md`**

Exact content — this is the WHAT document, and its shape is the contract:

```markdown
# <Stage> Stage

One paragraph: what this stage does in the pipeline, what it consumes,
what it produces. Name the artifact type and where it lives.

What the caller owns versus what this stage owns. Be specific -- the
boundary is the whole point of the document.

## Requirements

<STAGE>-1. A requirement, stated as a property of the stage's behaviour,
in one sentence. [FR-xxx]

<STAGE>-1.1. A sub-clause narrowing the parent: an edge case, a failure
mode, or a state transition the parent implies but does not pin down.
[FR-xxx]

<STAGE>-2. The next requirement. Each clause carries exactly one
obligation -- if you need "and", it is two clauses. [E-xx]

## Failure modes

What this stage does when its inputs are wrong, when a model returns
something unusable, and when a human never answers. Each one anchored to
the clause that governs it.
```

- [ ] **Step 2: Write `docs/templates/stage-AGENTS.md`**

Exact content — the HOW document:

```markdown
# AGENTS.md — <stage>

Local rules for editing this slice. Repo-wide rules are in the root
[`AGENTS.md`](../../../../AGENTS.md); the seam contract and the Temporal
rules are in [`docs/framework.md`](../../../../docs/framework.md). This
file carries only what is true *here*.

## Invariants

What must not change without changing `<stage>.md` first. What this slice
owns and what it must never reach for.

## Temporal notes for this slice

Which of `framework.md`'s four rules bite here, and where. Name the
specific imports that must be passed through and why -- model modules for
enum identity, the agent registry for import-time construction, any child
workflow class this stage starts. If none of them bite, say so; an empty
section is information.

## State

Which values arrive as parameters and which come from `StageContext`.
Any per-loop counter this slice keeps, and where it lives (never on the
workflow instance -- see `gates.py:84-88` for why).

## Activities

The `@activity.defn` functions this slice owns, and confirmation that all
of them are listed in `ACTIVITIES`.

## Tests

    pytest tests/<stage>/ -q

Anything a test here needs that is not obvious: fixtures, markers, why a
test is in `tests/integration/` instead.
```

- [ ] **Step 3: Write `docs/modes/feature-clause-writing.md`**

Must carry:
- The clause ID scheme: `<STAGE>-N` and `<STAGE>-N.M`, each anchored to an existing `FR-xxx`, `NFR-x`, or `E-xx`. **`ADR-xx` is not an anchor** — an ADR records a decision, not a requirement, so a clause citing one describes rationale rather than obligation.
- Why anchoring at all: those ids already span `PRD.md`, `ROADMAP.md` and `ARCHITECTURE.md`, and an unanchored local namespace would be a shadow taxonomy competing with them. Why local clauses at all: an `FR` is too coarse to describe the atomic state transition a test needs to cite.
- How to write one: a property of behaviour, not an implementation step; one obligation per clause (if it needs "and", it is two); present tense; the subject is the stage, not the developer.
- Worked examples, good and bad. At minimum: `CLARIFY-1. Every open question the clarifier emits is either answered by a human or falls back to its suggested answer before the stage returns. [FR-xxx]` against the bad version `CLARIFY-1. The clarify stage should handle open questions properly.`
- A note that whether pytest gains a clause-citing marker is deferred to spec A, where a real migrated slice exists to try it on.

- [ ] **Step 4: Write `docs/modes/slice-migration.md`**

The procedure for moving one stage out of `feature.py`, as an ordered checklist. Must carry, in order:
1. Read the stage's block in `_pipeline` and list every `self.` it touches. That list is what the migration must eliminate or route through `StageContext`.
2. Create `src/sdlc/stages/<stage>/` with the six files from spec's slice layout.
3. Move models the stage **produces** (not those it merely consumes — the producer owns them).
4. Move the `@activity.defn` functions it owns; export `ACTIVITIES`; add the module to `STAGE_MODULES`; delete the corresponding imports from `worker.py`.
5. Write `step(ctx, …)`, passing run context as parameters. Any `self._x` that is not one of the eleven services becomes a parameter or a return value.
6. Replace the inline block in `_pipeline` with the call. The activity sequence must be identical — this is what keeps replay safe.
7. Move tests to `tests/<stage>/`, keeping full descriptive basenames (`test_clarify_routing.py`, never shortened to `test_routing.py`) — there is no `tests/__init__.py`, so pytest requires globally unique basenames.
8. Write `<stage>.md` and `AGENTS.md` from the templates.
9. Update the migration table in the root `AGENTS.md`.
10. Re-point every call site of every moved symbol. **No re-export shims.**
11. Run `pytest -m "not slow and not temporal"` then `pytest -m temporal`, and `python scripts/check_file_size.py --full`.

Add the two traps in a closing section: passing a step module itself through the sandbox (wrong — only its third-party, model, registry and child-workflow imports go through), and carrying `_escalation_round`-shaped instance state across into the slice instead of fixing it.

- [ ] **Step 5: Write `docs/modes/focused-specs.md`**

How a design spec is written here, harvested from what the existing 61 specs in `docs/superpowers/specs/` actually do. Must carry:
- The metadata block: `Date`, `Status`, `Scope`, `Satisfies`, `Baseline` (a commit sha), `Does not cover`. Point at `2026-09-01-e50-assessment-gate-checks-design.md` as the model.
- `Does not cover` is not optional. A spec that does not say what it excludes will be read as covering it.
- Anchor claims to `file:line`. A spec asserting behaviour without an anchor is asserting a memory.
- `Problem` before `Decision`, and the problem states what is broken today, with evidence.
- Specs are **write-once after they land**: superseding work gets a new spec that cites the old one; the old one is never edited to stay current.

- [ ] **Step 5a: Write `docs/modes/report-first.md`**

The highest-leverage document in this task, because spec A is a brownfield archaeology problem before it is a refactoring problem: nobody can safely cut a 3673-line workflow they have only skimmed.

Must carry:

- **The rule.** For work on unfamiliar or heavily-coupled code, the first task produces a *diagnostic artifact and no code changes at all*. The edit ban is the mechanism, not a formality — an agent permitted to "just fix this one thing" while mapping stops mapping.
- **Why.** A reviewer can read a two-page artifact and say "your model of this is wrong" before any code moved. The same correction after the refactor costs the refactor. And an agent that has written down what it believes can be contradicted; one that has only read cannot.
- **What the artifact contains**, adapted from legacy-archaeology practice to this repo: entry points; a map of the unit under study; its coupling — what it reaches for and what reaches for it; data flows; the places behaviour is load-bearing but undocumented; missing tests; and an explicit **hypotheses** list, each one phrased so it can be checked.
- **Where it goes: `docs/reports/`.** No new directory. That directory's existing definition — dated one-offs, true when written, never updated — is exactly an archaeology report, and `feature-coverage-audit-2026-07-05.md` already living there is a diagnostic snapshot of the same shape. Do **not** put these in `records/` (reserved for verbatim exports, and ceiling-exempt on a rationale that does not cover authored artifacts) or in `.workspace/` (gitignored, so the artifact could never be reviewed in a diff or cited later — which defeats the point).
- **The worked example, written as spec A's opening task:** before any code moves, produce `docs/reports/<date>-feature-py-archaeology.md` covering, per stage in `_pipeline`: the stage's line range, every `self._x` it touches, which of `StageContext`'s eleven services that maps to, what it needs that no service covers, the enum-identity comparison sites in its body, and any child workflow it starts. That table *is* the migration order — the stages needing least become the pilots' successors — and it is what makes each later slice move mechanical rather than exploratory.
- **When it does not apply:** a change inside code the author already understands does not need a report. This is a tool for unfamiliar ground, not a ceremony for every diff.

- [ ] **Step 5b: Write `docs/modes/lesson-to-skill.md`**

How a mistake becomes something that cannot repeat. Must carry:

- **The loop:** task → failure → reflection → lesson → a durable, executable artifact → future runs. The point is the last step: a lesson that stays in a transcript is gone when the session ends; one that becomes a rule, a check, or a test is enforced without anyone remembering it.
- **Where a lesson can land, in ascending order of strength**, and the instruction to always prefer the strongest that fits:
  1. a sentence in the relevant `AGENTS.md` — weakest; relies on being read;
  2. a rule in `docs/documentation-rules.md` or a `docs/modes/` guide — reviewable, still advisory;
  3. **a test** — the failure cannot recur silently;
  4. **a hook or a gate in `scripts/verify.py`** — the failure cannot be committed.
- The bar for promotion: a lesson that has cost time twice belongs at level 3 or 4, not level 1. Restating a rule that already exists at level 1 and was ignored is not a lesson; it is evidence that level was too weak.
- **Two worked examples from this repo's own history**, both real: `_escalation_round` as workflow-instance state is a defect `gates.py:84-88` had already diagnosed for a sibling value and written down as prose — a level-2 lesson that did not prevent the level-2 recurrence, which is exactly the argument for level 3. And the file-size ceiling: "keep files small" was advice nobody enforced until `scripts/check_file_size.py` made it level 4.
- **Scope:** these lessons are about developing *this repository*. A lesson about how the Kroker pipeline behaves for its users is a product concern and belongs in the product's own docs, never here.

- [ ] **Step 6: Write `docs/features/AGENTS.md`**

Rules for the area documents in `docs/features/`. Must state:
- An area document is **narrative across the DAG** — how several stages compose to serve an outcome. It is not a per-stage contract; that is the slice's `<stage>.md`, and duplicating it here creates two documents that drift.
- An area document links down to slice documents and never restates their clauses.
- It tracks `main`, like `ARCHITECTURE.md`.
- Who may edit it: orchestrator agents only (the sandbox boundary from the root `AGENTS.md`).

- [ ] **Step 7: Verify**

Run: `python scripts/check_file_size.py --full && echo OK`
Expected: `OK`.

Check the template's relative links resolve from where a slice will sit. `docs/templates/stage-AGENTS.md` is written for a file that will live at `src/sdlc/stages/<stage>/AGENTS.md`, four levels below the root:

```bash
python - <<'PY'
from pathlib import Path
base = Path("src/sdlc/stages/clarify")
for target in ["../../../../AGENTS.md", "../../../../docs/framework.md"]:
    print(target, "->", (base / target).resolve().exists())
PY
```

Expected: both `True`.

Run: `pre-commit run --all-files`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add docs/modes docs/features docs/templates
git commit -m "$(cat <<'EOF'
docs: modes/, features/AGENTS.md, and the two slice templates

report-first.md is the one spec A depends on: cutting a 3673-line
workflow is a brownfield archaeology problem before it is a refactoring
problem, so A opens with a no-edits diagnostic task producing a per-stage
map of every self._x touched, which StageContext service it maps to, and
the enum-identity sites -- and that table is the migration order.
Artifacts go in docs/reports/, whose existing "dated one-off, never
updated" semantics already fit; not records/ (ceiling-exempt on a
rationale that does not cover authored files) and not .workspace/
(gitignored, so nothing could review it).

lesson-to-skill.md ranks where a lesson can land -- prose, rule, test,
gate -- and requires the strongest that fits, with _escalation_round as
the worked example of a level-2 lesson that failed to prevent its own
recurrence.

B0 deliverables 3 and 4. feature-clause-writing.md fixes the clause
scheme -- local <STAGE>-N.M ids anchored to an existing FR/NFR/E, with
ADR excluded because an ADR records a decision rather than an obligation.
slice-migration.md is the ordered procedure for moving one stage out of
feature.py, including the two traps: passing a step module itself through
the sandbox, and carrying _escalation_round-shaped instance state across
instead of fixing it. focused-specs.md harvests what the existing 61
specs already do.

The templates ship with the guides because a template nobody knows how to
fill in gets copied wrong.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GGcBUbL41c17uKbzeEBaEe
EOF
)"
```

---

## Deferred — the harness backlog

Triaged 2026-09-02 against `.workspace/notes/2026-09-02-ai-native-harness-engineering-research.md` (the Abdullin/Kunafin harness-engineering digest). Recorded here so the ideas are not lost, and so a later spec can pick one up without re-deriving it.

**Every item below is about developing *this repository*.** None of it is product functionality, and none of it may be implemented by adding anything to `src/sdlc`. Kroker the product already ships telemetry, evals and golden cases for the pipelines it runs on other people's repositories; those are not our development harness, and the resemblance is a trap, not a shortcut. The honest one-line summary of this triage: **Kroker has built for its customers the feedback system it has not built for itself.**

| # | Item | Why deferred |
|---|---|---|
| D1 | **Claude Code hooks as executable policy** — `PostToolUse(Edit)` → lint/test with the result fed back, `Stop` → verify and return a reason. Today `.claude/settings.local.json` carries only a `permissions` block; there are no hooks at all. This is the largest single gap between what the research describes and what this repo has. | Changes agent behaviour for every session on this machine, depends on local runtime and shell specifics, and is untested on Windows. `scripts/verify.py` (Task 1) is the piece a `Stop` hook would call, so B0 makes this cheap later rather than blocking on it now. |
| D2 | **`/goal` conventions** — expressing a task as an observable success condition rather than an instruction. | Depends on D1's shape and on `verify.py` existing. A convention written before either is speculation. |
| D3 | **Repo-authored skills in `.claude/skills/`** — closing the lesson → skill loop with executable artifacts. Today that directory holds only vendored third-party skills (pydantic, logfire); this repo has authored none. | `docs/modes/lesson-to-skill.md` (Task 8) establishes the method. Skills should be harvested from real lessons, not invented up front — writing them now would produce exactly the speculative content the method warns against. |
| D4 | **A golden set for the repo's own harness** — fixed cases measuring whether an agent editing Kroker follows Kroker's conventions. Deliberately *not* `benchmarks/cases/`: those measure the product pipeline's ability to build a feature end-to-end on a target repo, judged by a model. A different subject needs different machinery. | Nothing to evaluate until the conventions exist and slices have moved. `evals/golden/` was considered for B0 and rejected: an empty directory with no runner to consume it is scaffolding that invites three incompatible interpretations. |
| D5 | **Telemetry over this repo's own agent runs** — what actually happened when an agent worked here, as opposed to what the product's Logfire records about pipeline runs. This is the missing fourth artifact named in spec §4. | No consumer for it yet. It becomes worth having once D1 and D4 exist and there is something to correlate against. |
| D6 | **BDD Given-When-Then executable specs citing clause ids** — the full behaviour layer the reference stack has via `Covers(clauses:)`. | B0 §4 already defers the narrower question (a pytest marker citing clause ids) to spec A, where a real migrated slice exists to try it on. The full BDD layer is a larger decision that should follow that experiment, not precede it. |
| D7 | **Deterministic environment (Nix flake or equivalent)** — pinned toolchain so every agent gets identical versions. | Real value, entirely orthogonal to B0, and a large change to how everyone runs the repo. Deserves its own spec and its own decision. |
| D8 | **Interactive HTML/SVG diagnostic reports** — dependency maps, request-flow diagrams, rendered rather than described. | Overlaps spec C's design work substantially; the two should be decided together. `docs/modes/report-first.md` (Task 8) deliberately specifies Markdown artifacts so the practice can start immediately without waiting for this. |

Two research items need no work: the **control centre** for multi-agent operations is already Herdr (`.workspace/bin/herdr-plan`, `herdr-exec`), and the **docs-tree-not-one-giant-prompt** principle is what B0 §3 builds.

## Done when

- **`python scripts/verify.py` exits 0 and prints `all gates pass`.** That is the single observable condition this plan is finished against; the four bullets it subsumes are below, for diagnosis when it does not.
- `.file-size-baseline.json` holds exactly five entries: `feature.py` 3673, `activities.py` 1430, `models.py` 1334, `test_assessment_workflow_e2e.py` 1177, `adapters.py` 1092. `ROADMAP.md` is gone from it.
- `pytest` passes; `pre-commit run --all-files` passes.
- `docs/modes/` holds five guides: `feature-clause-writing.md`, `slice-migration.md`, `focused-specs.md`, `report-first.md`, `lesson-to-skill.md`.
- The root `AGENTS.md` is under 250 lines — it routes, it does not explain.
- `grep -c FactoryWorkflow ARCHITECTURE.md` returns `0`.
- `ls docs/` shows only `documentation-rules.md`, `framework.md`, `features`, `modes`, `reference`, `reports`, `roadmap`, `schemas`, `superpowers`, `templates`.
- `design/` does not exist; `records/2026-07-12-factory-console/` holds three files and a `records/README.md` sits beside it.
- `CLAUDE.md` is tracked and carries the "read the nearest `AGENTS.md`" directive.
- The root `AGENTS.md` carries the migration table with `clarify` and `qa` marked as pilots.

Nothing under `src/sdlc/` has changed. That is the point: B0 sets the target, spec A moves the code toward it.
