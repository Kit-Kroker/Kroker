# Triage — The Remaining Four Hygiene Signals (E-41a–d) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take FR-902 from three of seven hygiene-signal families to seven of seven, by adding dependency health, generator-scaffold/dead code, framework misconfiguration, and size/duplication outliers behind E-41's existing signal seam.

**Architecture:** Four peer signals, each a pure module under `src/sdlc/triage/signals/` plus one Temporal activity that never raises, exactly as `baseline` / `secrets` / `build_probe` are built. Two new shared pieces land first: a batched `git cat-file --batch` reader that replaces today's two-subprocesses-per-file `read_blob`, and an `AdvisorySource` seam whose default collects nothing. The `ToolchainAdapter` gains pure per-language facts (manifest names, source extensions, size thresholds, a function-span parser). No workflow and no gate — those are E-42.

**Tech Stack:** Python 3.14, Pydantic v2, Temporal (`temporalio`), pytest + pytest-asyncio, stdlib `ast` / `tomllib` / `urllib` / `hashlib`.

## Global Constraints

- **Signal modules stay pure.** They may import Pydantic, the stdlib, `..measurement`, `..grounding`, `...toolchain.adapters` and `..models` only. They must **never** import `sdlc/models.py`, `sdlc/activities.py`, or `temporalio`. A dependency there would appear as a reviewable import.
- **Every activity is `try`/`except Exception` wrapped and returns `SignalResult(collected=Measurement.not_collected(...))` on any escape.** A signal that crashes must never fail the other six (spec D3).
- **`Measurement.not_collected` requires a non-empty reason**, and `Measurement(NOT_COLLECTED, value=0.0)` does not construct. Never substitute `0.0` for a value you did not measure (spec D16).
- **Content comes from the pinned commit through git, never the working checkout** (spec D6).
- **Every finding carrying a quote must re-verify** with `verify_quote(quote, blob, Profile.VERBATIM_BYTES)`; an unverifiable quote **drops the finding** (spec D5).
- **One rule id means one thing across the whole tier.** Do not reuse a rule name another signal already owns.
- **Exactly one signal may report each readiness key.** `compute_readiness` raises on a duplicate.
- Run tests with the repo root importable — `tests` is not a package and there is no root `conftest.py`:
  `PYTHONPATH=. uv run pytest <args>`
- The default pytest run excludes `slow`, `temporal` and `docker` markers. Everything in this plan is a fast unit test; none of it needs those markers.

---

### Task 1: Batched tree reader (`gitread.py`), and migrate `secrets` onto it

Spec D10. `read_blob` spawns two git processes per file (`cat-file -t`, then `show`). `secrets` calls it over every tracked path, and three of the four new signals also need whole-tree content. One long-lived `git cat-file --batch` process replaces the pair, and the type guard arrives in the response header instead of costing a spawn.

**Files:**
- Create: `src/sdlc/triage/gitread.py`
- Modify: `src/sdlc/triage/signals/secrets.py` (delete `MAX_BLOB_BYTES` and `is_over_size_limit`)
- Modify: `src/sdlc/triage/activities.py` (`triage_secrets` reads through `read_tree`)
- Modify: `tests/test_triage_secrets.py:179-186` (import the moved helper)
- Test: `tests/test_triage_gitread.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `gitread.MAX_BLOB_BYTES: int` = `1_000_000`
  - `gitread.is_over_size_limit(text: str) -> bool`
  - `gitread.TreeReader(repo_dir: str, commit_sha: str)`, a context manager with `read(path: str) -> str | None`
  - `gitread.read_tree(repo_dir: str, commit_sha: str, paths: Sequence[str]) -> Iterator[tuple[str, str]]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_gitread.py`:

```python
"""The batched reader must match read_blob exactly (spec D10)."""
import subprocess

import pytest

from sdlc.triage.activities import read_blob, tracked_paths
from sdlc.triage.gitread import (
    MAX_BLOB_BYTES, TreeReader, is_over_size_limit, read_tree,
)


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL)


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    sha = _commit_repo(tmp_path, {
        "pyproject.toml": "[project]\nname = 'x'\n",
        "src/app.py": "x = 1\n",
        "empty.txt": "",
    })
    return str(tmp_path), sha


def test_reader_matches_read_blob_on_blob_tree_and_missing(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        for path in ("pyproject.toml", "src/app.py", "empty.txt",
                     "src", "nope.py"):
            assert reader.read(path) == read_blob(repo_dir, sha, path), path


def test_a_directory_reads_as_none_not_a_tree_listing(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("src") is None


def test_an_empty_file_reads_as_empty_string_not_none(repo):
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("empty.txt") == ""


def test_the_stream_stays_in_sync_after_a_missing_path(repo):
    # A missing path answers a one-line "<input> missing" with no payload.
    # Mis-handling it desynchronises every later read, which is the failure
    # mode a batched reader has and a per-file spawn cannot.
    repo_dir, sha = repo
    with TreeReader(repo_dir, sha) as reader:
        assert reader.read("nope.py") is None
        assert reader.read("src/app.py") == "x = 1\n"
        assert reader.read("also-nope") is None
        assert reader.read("pyproject.toml") == "[project]\nname = 'x'\n"


def test_read_tree_skips_binary_and_unreadable_paths(tmp_path):
    sha = _commit_repo(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"})
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01\x02")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "two"], tmp_path)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                         capture_output=True, encoding="utf-8",
                         check=True).stdout.strip()
    paths = tracked_paths(str(tmp_path), sha)
    got = dict(read_tree(str(tmp_path), sha, paths))
    assert got == {"a.py": "x = 1\n", "b.py": "y = 2\n"}


def test_is_over_size_limit_counts_bytes_not_characters():
    assert not is_over_size_limit("x" * MAX_BLOB_BYTES)
    assert is_over_size_limit("x" * (MAX_BLOB_BYTES + 1))
    # Three-byte characters exceed the byte limit at a third of the count.
    assert is_over_size_limit("\uffff" * 333334)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_gitread.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage.gitread'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/triage/gitread.py`:

```python
"""Batched blob reads at a pinned commit (E-41a-d, spec D10).

`read_blob` spawns two git subprocesses per file -- `cat-file -t` to guard
against a tree path, then `show`. `secrets` calls it over every tracked path,
and three of the four signals added by E-41a-d also need whole-tree content,
so the naive extension takes a 5,000-file repository from roughly 10,000
spawns to roughly 40,000. One long-lived `git cat-file --batch` process
replaces the pair: the type guard arrives in the response header instead of
costing a spawn.

Pure of temporalio, like the signal modules. The single-blob `read_blob` in
activities.py survives for the genuinely single-file case (baseline's
.gitignore).
"""
from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence

# The bound `secrets` applied per blob, hoisted here so every consumer of the
# reader inherits it rather than re-deciding. A minified bundle or a
# checked-in asset costs more to scan than the finding is worth, and E-41d
# owns size outliers.
MAX_BLOB_BYTES = 1_000_000


def is_over_size_limit(text: str) -> bool:
    """True when the text's UTF-8 byte length exceeds MAX_BLOB_BYTES.

    Compares bytes, not ``len(str)`` characters, so multibyte content is
    bounded honestly (a minified CJK bundle is far larger in bytes than in
    characters). `TreeReader` applies the same bound from cat-file's header,
    which is already a byte count; this function is for callers holding text.
    """
    return len(text.encode("utf-8")) > MAX_BLOB_BYTES


class TreeReader:
    """Reads blobs at one commit through a single `git cat-file --batch`.

    Carries `_git`'s ``-c safe.directory=*`` bypass forward: git's ownership
    check fires whenever the worker's SID differs from the worktree's owner,
    and that does not stop being true because the process is long-lived.

    Unlike `_git`, stdin is a PIPE rather than DEVNULL -- this is the one git
    invocation in the codebase that genuinely reads it.

    Use as a context manager; `read` outside one raises.
    """

    def __init__(self, repo_dir: str, commit_sha: str) -> None:
        self._repo_dir = repo_dir
        self._commit_sha = commit_sha
        self._proc: subprocess.Popen | None = None

    def __enter__(self) -> "TreeReader":
        self._proc = subprocess.Popen(
            ["git", "-c", "safe.directory=*", "cat-file", "--batch"],
            cwd=self._repo_dir,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        return self

    def __exit__(self, *exc) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            proc.stdin.close()
            proc.wait(timeout=30)
        except Exception:                          # noqa: BLE001
            proc.kill()
            proc.wait()

    def read(self, path: str) -> str | None:
        """The file's text at the pinned commit, or None when the path does
        not resolve to a readable blob.

        Matches `read_blob`'s contract exactly -- a directory answers type
        `tree`, an absent path answers `missing`, and both yield None. That
        equivalence is what makes the `secrets` migration safe, and it is
        asserted in tests rather than assumed.

        An over-size blob yields None, but its payload is still consumed:
        leaving bytes in the pipe would desynchronise every later read.
        """
        proc = self._proc
        if proc is None:
            raise RuntimeError("TreeReader used outside its context manager")
        proc.stdin.write(f"{self._commit_sha}:{path}\n".encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode(errors="replace").strip()
        parts = header.split()
        # "<oid> SP blob SP <size>" on success; "<input> SP missing" and
        # "<input> SP ambiguous" carry no payload; a tree/tag/commit object
        # is a well-formed header we still refuse.
        if len(parts) != 3 or parts[1] != "blob":
            return None
        size = int(parts[2])
        payload = proc.stdout.read(size)
        proc.stdout.read(1)                        # the trailing LF
        if size > MAX_BLOB_BYTES:
            return None
        return payload.decode(errors="replace")


def read_tree(repo_dir: str, commit_sha: str,
              paths: Sequence[str]) -> Iterator[tuple[str, str]]:
    """(path, text) for every path resolving to a readable text blob.

    Skips non-blobs, over-size blobs and binary content -- the three skips
    `secrets` applies today, hoisted so every signal inherits them instead of
    re-deciding. Paths are read in the order given, so a caller's sorted input
    yields deterministic output.
    """
    with TreeReader(repo_dir, commit_sha) as reader:
        for path in paths:
            text = reader.read(path)
            if text is None or "\x00" in text:     # binary; nothing to quote
                continue
            yield path, text
```

- [ ] **Step 4: Run the new test to verify it passes**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_gitread.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Migrate `secrets` onto the reader**

In `src/sdlc/triage/signals/secrets.py`, delete these lines (currently 26–35):

```python
# Blobs larger than this are skipped: a minified bundle or a checked-in asset
# costs more to regex than the finding is worth, and E-41d owns size outliers.
MAX_BLOB_BYTES = 1_000_000


def is_over_size_limit(text: str) -> bool:
    """True when the blob's UTF-8 byte length exceeds MAX_BLOB_BYTES. Compares
    bytes, not ``len(str)`` characters, so multibyte content is bounded honestly
    (a minified CJK bundle is far larger in bytes than in characters)."""
    return len(text.encode("utf-8")) > MAX_BLOB_BYTES
```

In `src/sdlc/triage/activities.py`, add the import beside the existing ones:

```python
from .gitread import read_tree
```

and replace the body of `triage_secrets`'s `try` block (currently lines 94–113) with:

```python
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        findings = list(secrets.env_file_findings(paths))
        for path, blob in read_tree(inp.repo_dir, inp.commit_sha,
                                    sorted(paths)):
            for finding in secrets.scan_text(path, blob):
                if finding.evidence and not verify_quote(
                        finding.evidence, blob, Profile.VERBATIM_BYTES):
                    _log.warning(
                        "triage secrets: dropping unverifiable evidence for "
                        "%s at %s", finding.rule, path)
                    continue
                findings.append(finding)
        return SignalResult(
            signal=secrets.SIGNAL_ID, version=secrets.VERSION,
            collected=Measurement.measured(float(len(findings))),
            findings=findings)
```

In `tests/test_triage_secrets.py`, replace lines 179–186 with:

```python
def test_is_over_size_limit_counts_bytes_not_characters():
    # Moved to gitread (spec D10): one size bound for every consumer of the
    # reader, not one per signal.
    from sdlc.triage.gitread import MAX_BLOB_BYTES, is_over_size_limit
    assert not is_over_size_limit("x" * MAX_BLOB_BYTES)
    assert is_over_size_limit("x" * (MAX_BLOB_BYTES + 1))
    # Three-byte characters exceed the byte limit at a third of the count,
    # even though their character count is well under MAX_BLOB_BYTES.
    assert is_over_size_limit("\uffff" * 333334)
```

- [ ] **Step 6: Run the triage suite to verify the migration is behaviour-preserving**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_secrets.py tests/test_triage_gitread.py tests/test_triage_baseline.py -q`
Expected: PASS, no test changes beyond the moved helper's import.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/triage/gitread.py src/sdlc/triage/signals/secrets.py \
        src/sdlc/triage/activities.py tests/test_triage_gitread.py \
        tests/test_triage_secrets.py
git commit -m "perf(triage): batched cat-file reader replaces per-file spawn pair

read_blob spawned two git processes per file and secrets called it over
every tracked path. One long-lived cat-file --batch process replaces the
pair; the blob/tree/missing guard arrives in the response header instead
of costing a spawn. Three of the four E-41a-d signals need whole-tree
content, so this lands before them (spec D10)."
```

---

### Task 2: FR-108 adapter extension

Spec §4 and D15. The adapter carries language-level facts only; framework rules stay in signals. `function_spans` is the first pure *parser* member beside the command strings — the same kind of member as `classify_test_exit`.

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py` (`ToolchainAdapter` base, `PythonToolchain`)
- Test: `tests/test_toolchain_triage_extension.py` (append; the file exists)

**Interfaces:**
- Consumes: nothing.
- Produces, on `ToolchainAdapter`:
  - `manifests: tuple[str, ...]` (default `()`)
  - `ecosystem: str | None` (default `None`)
  - `source_extensions: tuple[str, ...]` (default `()`)
  - `max_file_loc: int` (default `0`, meaning disabled)
  - `max_function_loc: int` (default `0`, meaning disabled)
  - `min_clone_loc: int` (default `30`)
  - `function_spans(self, text: str) -> list[tuple[str, int, int]] | None` — `(name, first_line, last_line)`, `None` when the language has no parser here

- [ ] **Step 1: Write the failing test**

Append to `tests/test_toolchain_triage_extension.py`:

```python
# ---- E-41a-d adapter extension ---------------------------------------

from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter


class _Bare(ToolchainAdapter):
    """An adapter that has not thought about triage. It must instantiate and
    degrade, not fail (spec §4)."""
    kind = None
    markers = ()

    def test_cmd(self, coverage: bool = True) -> str:
        return "true"

    def lint_cmd(self) -> str:
        return "true"

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        return "true"


def test_a_triage_unaware_adapter_degrades_rather_than_failing():
    a = _Bare()
    assert a.manifests == ()
    assert a.ecosystem is None
    assert a.source_extensions == ()
    assert a.max_file_loc == 0          # 0 disables the rule
    assert a.max_function_loc == 0
    assert a.min_clone_loc == 30
    assert a.function_spans("def f():\n    pass\n") is None


def test_python_declares_its_triage_facts():
    a = PythonToolchain()
    assert a.manifests == ("pyproject.toml", "requirements.txt")
    assert a.ecosystem == "PyPI"
    assert a.source_extensions == (".py",)
    assert a.max_file_loc == 800
    assert a.max_function_loc == 100


def test_function_spans_reports_name_and_line_range():
    text = ("import os\n"
            "\n"
            "def small():\n"
            "    return 1\n"
            "\n"
            "async def big():\n"
            "    x = 1\n"
            "    return x\n")
    spans = PythonToolchain().function_spans(text)
    assert ("small", 3, 4) in spans
    assert ("big", 6, 8) in spans


def test_function_spans_finds_methods_inside_classes():
    text = "class C:\n    def m(self):\n        return 1\n"
    assert ("m", 2, 3) in PythonToolchain().function_spans(text)


def test_unparseable_python_is_an_empty_list_not_none():
    # None means "this language has no parser here", which makes the metric
    # not_collected. A file we CAN parse and that simply is not valid Python
    # has no spans -- that is a measured zero, and conflating the two would
    # report an unparseable file as an unmeasurable language.
    assert PythonToolchain().function_spans("def (:\n") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_toolchain_triage_extension.py -q`
Expected: FAIL — `AttributeError: 'PythonToolchain' object has no attribute 'manifests'`

- [ ] **Step 3: Extend the base class**

In `src/sdlc/toolchain/adapters.py`, replace the existing E-41 block on `ToolchainAdapter` (currently lines 35–39):

```python
    # E-41 (FR-902). Concrete defaults, not abstract: a new adapter that has
    # not thought about triage yet degrades to "no install command" and the
    # probe records not_collected, rather than failing to instantiate.
    test_globs: tuple[str, ...] = ()
    lockfiles: tuple[str, ...] = ()
```

with:

```python
    # E-41 (FR-902). Concrete defaults, not abstract: a new adapter that has
    # not thought about triage yet degrades to "no install command" and the
    # probe records not_collected, rather than failing to instantiate.
    test_globs: tuple[str, ...] = ()
    lockfiles: tuple[str, ...] = ()

    # E-41a-d (spec §4). Same degradation rule: empty tuples and disabled
    # thresholds mean "rule skipped, metric not_collected", never a silent
    # zero. Language-level facts ONLY -- framework fingerprints and
    # misconfiguration rules live in their signal modules, because one
    # language serves many frameworks (spec D15).
    manifests: tuple[str, ...] = ()          # files declaring direct deps
    ecosystem: str | None = None             # OSV ecosystem name
    source_extensions: tuple[str, ...] = ()  # what counts as source
    max_file_loc: int = 0                    # 0 disables the rule
    max_function_loc: int = 0                # 0 disables the rule
    min_clone_loc: int = 30                  # duplication window, in lines

    def function_spans(self, text: str) -> list[tuple[str, int, int]] | None:
        """(name, first line, last line) for every function in `text`, or
        None when this language has no parser here.

        None is what makes E-41d's `oversized_function` metric
        not_collected rather than absent: a language we cannot parse is not
        a language with no long functions.

        Pure -- text in, spans out, no subprocess and no filesystem. The same
        kind of member as `classify_test_exit`: a per-language
        *interpretation*, not a command string (ADR-15, spec D15).
        """
        return None
```

- [ ] **Step 4: Extend `PythonToolchain`**

Add `import ast` to the imports at the top of `src/sdlc/toolchain/adapters.py`, then add to `PythonToolchain`, directly below its existing `lockfiles` line:

```python
    manifests = ("pyproject.toml", "requirements.txt")
    ecosystem = "PyPI"
    source_extensions = (".py",)
    # Absolute, not percentile (spec D14): Tier 0 asks what state this
    # repository is in, not which file is worst inside it, and E-44's
    # before/after delta needs numbers comparable across repositories.
    max_file_loc = 800
    max_function_loc = 100

    def function_spans(self, text: str) -> list[tuple[str, int, int]] | None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            # We CAN parse Python; this file simply is not valid Python. That
            # is a measured zero spans, not an unmeasurable language, so it
            # must not return None.
            return []
        return sorted(
            (node.name, node.lineno, node.end_lineno or node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. uv run pytest tests/test_toolchain_triage_extension.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/toolchain/adapters.py tests/test_toolchain_triage_extension.py
git commit -m "feat(toolchain): triage facts and function_spans on the adapter

FR-108/ADR-15 gains its first pure per-language parser member beside its
command strings. Every field defaults to disabled, so an adapter that has
not thought about triage degrades to rule-skipped/metric-not_collected
rather than failing to instantiate (spec D15, section 4)."
```

---

### Task 3: `AdvisorySource` seam

Spec D11. The default collects nothing. A lookup that did not happen reading as zero vulnerabilities is the malformed-SARIF hole E-40 closed on the absolute floor.

**Files:**
- Create: `src/sdlc/triage/advisories.py`
- Test: `tests/test_triage_advisories.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Advisory(package: str, constraint: str, advisory_id: str, severity: str, summary: str)`
  - `AdvisoryResult(collected: Measurement, advisories: list[Advisory])`
  - `AdvisorySource` ABC with `name: str` and `lookup(ecosystem: str | None, packages: Sequence[str]) -> AdvisoryResult`
  - `NoneAdvisorySource(reason: str = ...)`, `OsvAdvisorySource(url=..., timeout_s=..., max_packages=...)`
  - `ADVISORY_SOURCES: dict[str, type[AdvisorySource]]`, `resolve_advisory_source(name: str) -> AdvisorySource`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_advisories.py`:

```python
"""Spec D11: the default collects nothing, and every failure path is
not_collected rather than an empty advisory list."""
import json
from unittest.mock import patch

import pytest

from sdlc.measurement import CollectionState
from sdlc.triage.advisories import (
    NoneAdvisorySource, OsvAdvisorySource, resolve_advisory_source,
)


def test_the_default_source_collects_nothing():
    r = NoneAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.advisories == []
    assert "no advisory source configured" in r.collected.reason


def test_an_unknown_name_resolves_to_none_and_says_which_name():
    src = resolve_advisory_source("nosuchsource")
    r = src.lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "nosuchsource" in r.collected.reason


def test_the_registry_resolves_both_shipped_sources():
    assert isinstance(resolve_advisory_source("none"), NoneAdvisorySource)
    assert isinstance(resolve_advisory_source("osv"), OsvAdvisorySource)


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _osv_payload():
    return {"vulns": [{
        "id": "GHSA-1234",
        "summary": "Request smuggling in requests",
        "database_specific": {"severity": "HIGH"},
    }]}


def test_osv_maps_a_hit_to_a_typed_advisory():
    with patch("sdlc.triage.advisories.urllib.request.urlopen",
               return_value=_FakeResponse(_osv_payload())):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.MEASURED
    assert r.collected.value == 1.0
    assert r.advisories[0].advisory_id == "GHSA-1234"
    assert r.advisories[0].severity == "high"
    assert r.advisories[0].package == "requests"


def test_osv_no_hits_is_a_measured_zero_not_not_collected():
    with patch("sdlc.triage.advisories.urllib.request.urlopen",
               return_value=_FakeResponse({"vulns": []})):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.MEASURED
    assert r.collected.value == 0.0


@pytest.mark.parametrize("boom", [
    TimeoutError("timed out"),
    OSError("connection refused"),
    ValueError("not json"),
])
def test_every_osv_failure_path_is_not_collected(boom):
    with patch("sdlc.triage.advisories.urllib.request.urlopen",
               side_effect=boom):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.advisories == []


def test_a_non_200_is_not_collected():
    with patch("sdlc.triage.advisories.urllib.request.urlopen",
               return_value=_FakeResponse({}, status=503)):
        r = OsvAdvisorySource().lookup("PyPI", ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "503" in r.collected.reason


def test_no_ecosystem_is_not_collected():
    r = OsvAdvisorySource().lookup(None, ["requests"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert "ecosystem" in r.collected.reason


def test_exceeding_the_package_cap_is_not_collected_not_a_partial_answer():
    src = OsvAdvisorySource(max_packages=2)
    r = src.lookup("PyPI", ["a", "b", "c"])
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.advisories == []


def test_an_empty_package_list_is_a_measured_zero():
    r = OsvAdvisorySource().lookup("PyPI", [])
    assert r.collected.state is CollectionState.MEASURED
    assert r.collected.value == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_advisories.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'sdlc.triage.advisories'`

- [ ] **Step 3: Write the implementation**

Create `src/sdlc/triage/advisories.py`:

```python
"""E-41a's advisory-source seam (spec D11).

THE DEFAULT COLLECTS NOTHING. Vulnerability data requires an advisory
database, which means sending a client repository's dependency list off-box;
that is a trust-boundary decision, not an implementation detail. The seam
mirrors MemoryConfig.backend defaulting to `fake` and ADR-19's
adapters-not-substrate rule: an offline no-op default plus one reference
implementation, opt-in per run.

Every failure path returns not_collected. NONE returns an empty advisory
list. A lookup that did not happen reading as zero vulnerabilities is the
malformed-SARIF hole E-40 closed on the absolute floor (FR-915), and
installing the same conflation in a new signal would be indefensible.

`OsvAdvisorySource` is an outbound call about a client repository and is
recorded as a declared, opt-in, off-by-default egress under FR-703.

Pure of temporalio, like the signal modules: the HTTP happens inside an
activity, never in workflow code.
"""
from __future__ import annotations

import json
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Sequence

from pydantic import BaseModel, Field

from ..measurement import Measurement


class Advisory(BaseModel):
    package: str            # the normalized distribution name queried
    constraint: str = ""    # the declaration as written, when the caller has it
    advisory_id: str        # e.g. "GHSA-xxxx-xxxx-xxxx" / "PYSEC-2024-1"
    severity: str           # critical | high | medium | low
    summary: str = ""


class AdvisoryResult(BaseModel):
    """`collected` is a Measurement, not len(advisories): "we did not look"
    and "we looked and found none" are different facts (D11/D16). When
    MEASURED, its value is the number of advisories returned."""
    collected: Measurement
    advisories: list[Advisory] = Field(default_factory=list)


class AdvisorySource(ABC):
    name: str

    @abstractmethod
    def lookup(self, ecosystem: str | None,
               packages: Sequence[str]) -> AdvisoryResult:
        """Advisories for `packages` in `ecosystem`. MUST NOT raise: an
        unreachable database is a not_collected report, not a failed signal."""


class NoneAdvisorySource(AdvisorySource):
    """The default. Collects nothing, and says so with a reason the report
    carries, so "no vulnerabilities listed" is never mistaken for "none
    exist"."""
    name = "none"

    def __init__(self, reason: str = "no advisory source configured") -> None:
        self._reason = reason

    def lookup(self, ecosystem: str | None,
               packages: Sequence[str]) -> AdvisoryResult:
        return AdvisoryResult(
            collected=Measurement.not_collected(self._reason))


OSV_URL = "https://api.osv.dev/v1/query"
OSV_TIMEOUT_S = 20
OSV_MAX_PACKAGES = 200

# GHSA supplies MODERATE where our TriageFinding vocabulary says medium.
_SEVERITY_WORDS = {
    "CRITICAL": "critical", "HIGH": "high",
    "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low",
}


def _severity(vuln: dict) -> str:
    """The advisory's severity label, defaulting to `high`.

    The default is not a fabricated measurement: the vulnerability itself is
    measured -- OSV returned it -- and only its LABEL is missing. Defaulting
    down would under-report a known vulnerability, which is the wrong way to
    be wrong on a security signal.
    """
    # `or {}` not a .get default: OSV sends an explicit null here, and
    # None.get would raise inside the one function that must not.
    specific = vuln.get("database_specific") or {}
    word = str(specific.get("severity", "")).upper()
    return _SEVERITY_WORDS.get(word, "high")


class OsvAdvisorySource(AdvisorySource):
    """The one reference implementation (ADR-19: adapters, not substrate).

    Uses /v1/query per package rather than /v1/querybatch: batch returns only
    ids, so severity would need a second round-trip per hit, and a severity
    we did not fetch is exactly the value this seam refuses to invent.

    `max_packages` bounds the call count. Exceeding it reports not_collected
    rather than answering for a prefix of the list -- a partial lookup
    presented as a lookup is the D16 error.
    """
    name = "osv"

    def __init__(self, url: str = OSV_URL, timeout_s: int = OSV_TIMEOUT_S,
                 max_packages: int = OSV_MAX_PACKAGES) -> None:
        self._url = url
        self._timeout_s = timeout_s
        self._max_packages = max_packages

    def lookup(self, ecosystem: str | None,
               packages: Sequence[str]) -> AdvisoryResult:
        if not ecosystem:
            return AdvisoryResult(collected=Measurement.not_collected(
                "the resolved toolchain declares no OSV ecosystem"))
        if len(packages) > self._max_packages:
            return AdvisoryResult(collected=Measurement.not_collected(
                f"{len(packages)} packages exceeds the {self._max_packages} "
                f"query cap; a partial lookup is not a lookup"))
        if not packages:
            return AdvisoryResult(collected=Measurement.measured(0.0))

        found: list[Advisory] = []
        for name in packages:
            body = json.dumps(
                {"package": {"name": name, "ecosystem": ecosystem}}).encode()
            try:
                req = urllib.request.Request(
                    self._url, data=body,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(
                        req, timeout=self._timeout_s) as resp:
                    if resp.status != 200:
                        return AdvisoryResult(
                            collected=Measurement.not_collected(
                                f"OSV returned HTTP {resp.status} for "
                                f"{name!r}"))
                    payload = json.loads(resp.read().decode())
            except Exception as exc:               # noqa: BLE001 -- docstring
                return AdvisoryResult(collected=Measurement.not_collected(
                    f"OSV lookup failed for {name!r}: "
                    f"{type(exc).__name__}: {exc}"))
            for vuln in payload.get("vulns") or []:
                found.append(Advisory(
                    package=name,
                    advisory_id=str(vuln.get("id", "")),
                    severity=_severity(vuln),
                    summary=str(vuln.get("summary", ""))[:300]))
        return AdvisoryResult(
            collected=Measurement.measured(float(len(found))),
            advisories=found)


ADVISORY_SOURCES: dict[str, type[AdvisorySource]] = {
    NoneAdvisorySource.name: NoneAdvisorySource,
    OsvAdvisorySource.name: OsvAdvisorySource,
}


def resolve_advisory_source(name: str) -> AdvisorySource:
    """The named source, or the collecting-nothing default.

    An operator typo must not fail a triage, but it must not vanish either:
    the fallback carries the unknown name in its reason, so the report says
    which source was asked for and never found.
    """
    cls = ADVISORY_SOURCES.get(name)
    if cls is None:
        return NoneAdvisorySource(
            f"unknown advisory source {name!r}; no lookup was performed")
    return cls()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_advisories.py -q`
Expected: PASS (11 tests). **No test may touch the network** — every OSV test patches `urlopen`.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/triage/advisories.py tests/test_triage_advisories.py
git commit -m "feat(triage): AdvisorySource seam whose default collects nothing

Spec D11. Offline no-op default plus one OSV reference implementation,
opt-in per run. Every failure path -- timeout, non-200, malformed JSON,
missing ecosystem, cap exceeded -- returns not_collected; none returns an
empty advisory list, because a lookup that did not happen reading as zero
vulnerabilities is the hole E-40 closed on the absolute floor."
```

---

### Task 4: `dependencies` signal (E-41a)

Spec §5.

**Files:**
- Create: `src/sdlc/triage/signals/dependencies.py`
- Modify: `src/sdlc/triage/activities.py` (add `triage_dependencies`)
- Modify: `src/sdlc/triage/registry.py` (add the entry)
- Modify: `src/sdlc/worker.py` (register the activity)
- Test: `tests/test_triage_dependencies.py`

**Interfaces:**
- Consumes: `gitread.read_tree` (Task 1); `ToolchainAdapter.manifests` / `.ecosystem` / `.source_extensions` (Task 2); `advisories.AdvisoryResult` / `resolve_advisory_source` (Task 3).
- Produces:
  - `dependencies.SIGNAL_ID = "dependencies"`, `dependencies.VERSION = 1`
  - `Declared(name: str, raw: str, manifest: str, constraint: str, line: int | None)`
  - `parse_requirements(manifest: str, text: str) -> list[Declared]`
  - `parse_pyproject(manifest: str, text: str) -> list[Declared]`
  - `imported_modules(texts: Iterable[str]) -> set[str]`
  - `evaluate(declared, lockfile_present, imported, advisories) -> SignalResult`
  - `activities.TriageDependencyInput(repo_dir, commit_sha, advisory_source="none")`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_dependencies.py`:

```python
"""FR-902 dependency health (E-41a)."""
from sdlc.measurement import CollectionState, Measurement
from sdlc.triage.advisories import Advisory, AdvisoryResult
from sdlc.triage.models import FixClass
from sdlc.triage.signals import dependencies as dep

PYPROJECT = """\
[project]
name = "app"
dependencies = ["requests>=2.0", "pydantic==2.9.0", "pillow"]

[project.optional-dependencies]
dev = ["pytest>=8"]
"""

REQUIREMENTS = """\
# a comment
requests==2.31.0
flask
-r other.txt
uvicorn[standard]>=0.30
"""


def _rules(result):
    return {f.rule for f in result.findings}


def _no_advisories():
    return AdvisoryResult(
        collected=Measurement.not_collected("no advisory source configured"))


# ---- manifest parsing -------------------------------------------------

def test_pyproject_parses_required_and_optional_dependencies():
    got = {d.name: d.constraint
           for d in dep.parse_pyproject("pyproject.toml", PYPROJECT)}
    assert got == {"requests": ">=2.0", "pydantic": "==2.9.0",
                   "pillow": "", "pytest": ">=8"}


def test_requirements_skips_comments_and_include_directives():
    got = {d.name: d.constraint
           for d in dep.parse_requirements("requirements.txt", REQUIREMENTS)}
    assert got == {"requests": "==2.31.0", "flask": "",
                   "uvicorn": ">=0.30"}


def test_names_are_normalized_pep503():
    text = '[project]\ndependencies = ["Python_Dateutil>=2"]\n'
    assert dep.parse_pyproject("pyproject.toml", text)[0].name \
        == "python-dateutil"


# ---- rules ------------------------------------------------------------

def test_unpinned_fires_for_floating_and_absent_constraints():
    declared = dep.parse_pyproject("pyproject.toml", PYPROJECT)
    r = dep.evaluate(declared, lockfile_present=False,
                     imported={"requests", "pydantic", "PIL", "pytest"},
                     advisories=_no_advisories())
    unpinned = {f.path + ":" + f.detail.split()[0]
                for f in r.findings if f.rule == "unpinned_dependency"}
    assert len(unpinned) == 3        # requests, pillow, pytest; not pydantic


def test_unpinned_detail_records_whether_a_lockfile_mitigates():
    declared = dep.parse_pyproject("pyproject.toml",
                                   '[project]\ndependencies = ["requests"]\n')
    with_lock = dep.evaluate(declared, True, {"requests"}, _no_advisories())
    without = dep.evaluate(declared, False, {"requests"}, _no_advisories())
    assert "lockfile" in with_lock.findings[0].detail
    assert "no lockfile" in without.findings[0].detail


def test_duplicate_fires_only_on_conflicting_constraints():
    same = [dep.Declared(name="requests", raw="requests==2.0",
                         manifest="pyproject.toml", constraint="==2.0"),
            dep.Declared(name="requests", raw="requests==2.0",
                         manifest="requirements.txt", constraint="==2.0")]
    conflicting = [same[0],
                   dep.Declared(name="requests", raw="requests==3.0",
                                manifest="requirements.txt",
                                constraint="==3.0")]
    assert "duplicate_dependency" not in _rules(
        dep.evaluate(same, True, {"requests"}, _no_advisories()))
    assert "duplicate_dependency" in _rules(
        dep.evaluate(conflicting, True, {"requests"}, _no_advisories()))


def test_known_vulnerable_is_judgement_not_mechanical():
    declared = [dep.Declared(name="requests", raw="requests==2.0",
                             manifest="requirements.txt", constraint="==2.0")]
    adv = AdvisoryResult(
        collected=Measurement.measured(1.0),
        advisories=[Advisory(package="requests", advisory_id="GHSA-1",
                             severity="critical", summary="bad")])
    r = dep.evaluate(declared, True, {"requests"}, adv)
    f = next(f for f in r.findings if f.rule == "known_vulnerable")
    assert f.fix_class is FixClass.JUDGEMENT
    assert f.severity == "critical"
    assert "GHSA-1" in f.detail


def test_known_vulnerable_metric_is_not_collected_under_the_default_source():
    r = dep.evaluate([], True, set(), _no_advisories())
    assert r.metrics["known_vulnerable"].state is CollectionState.NOT_COLLECTED
    # The SIGNAL still collected -- it read the manifests.
    assert r.collected.state is CollectionState.MEASURED


# ---- the unused-dependency false-positive guards ----------------------

def test_an_aliased_distribution_is_not_reported_unused():
    declared = [dep.Declared(name="pillow", raw="pillow", manifest="m",
                             constraint="")]
    r = dep.evaluate(declared, True, {"PIL"}, _no_advisories())
    assert "unused_dependency" not in _rules(r)


def test_tooling_is_never_reported_unused():
    declared = [dep.Declared(name=n, raw=n, manifest="m", constraint="")
                for n in ("pytest", "ruff", "pytest-asyncio", "types-requests")]
    r = dep.evaluate(declared, True, set(), _no_advisories())
    assert "unused_dependency" not in _rules(r)


def test_a_genuinely_unimported_dependency_is_reported_low():
    declared = [dep.Declared(name="tensorflow", raw="tensorflow",
                             manifest="m", constraint="")]
    r = dep.evaluate(declared, True, {"os"}, _no_advisories())
    f = next(f for f in r.findings if f.rule == "unused_dependency")
    assert f.severity == "low"
    assert f.fix_class is FixClass.MECHANICAL


def test_underscore_and_dash_forms_both_count_as_imported():
    declared = [dep.Declared(name="typing-extensions", raw="typing-extensions",
                             manifest="m", constraint="")]
    r = dep.evaluate(declared, True, {"typing_extensions"}, _no_advisories())
    assert "unused_dependency" not in _rules(r)


# ---- import extraction ------------------------------------------------

def test_imported_modules_reads_both_import_forms():
    src = ("import os, sys\n"
           "from pathlib import Path\n"
           "from sdlc.triage import models\n"
           "    import json\n")
    assert dep.imported_modules([src]) == {"os", "sys", "pathlib", "sdlc",
                                           "json"}


def test_direct_dependencies_metric_counts_distinct_names():
    declared = dep.parse_pyproject("pyproject.toml", PYPROJECT)
    r = dep.evaluate(declared, True, set(), _no_advisories())
    assert r.metrics["direct_dependencies"].value == 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_dependencies.py -q`
Expected: FAIL — `ImportError: cannot import name 'dependencies'`

- [ ] **Step 3: Write the signal module**

Create `src/sdlc/triage/signals/dependencies.py`:

```python
"""FR-902 dependency health (E-41a). Pure logic over parsed manifests.

The advisory half arrives as an AdvisoryResult the activity fetched: this
module never performs I/O, so "we did not look" reaches it as a Measurement
rather than as an empty list (spec D11/D16).
"""
from __future__ import annotations

import posixpath
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence

from pydantic import BaseModel

from ...measurement import Measurement
from ..advisories import AdvisoryResult
from ..models import FixClass, SignalResult, TriageFinding

SIGNAL_ID = "dependencies"
VERSION = 1

M_DIRECT = "direct_dependencies"
M_VULNERABLE = "known_vulnerable"

# Distribution name -> the module(s) it actually provides. Hand-maintained and
# deliberately SHORT: every entry is a false positive worth pre-empting, not a
# catalogue of PyPI. The table cannot be complete, which is exactly why
# unused_dependency is low severity and influences no readiness dimension.
IMPORT_ALIASES: dict[str, tuple[str, ...]] = {
    "pillow": ("PIL",),
    "beautifulsoup4": ("bs4",),
    "pyyaml": ("yaml",),
    "python-dateutil": ("dateutil",),
    "python-dotenv": ("dotenv",),
    "scikit-learn": ("sklearn",),
    "opencv-python": ("cv2",),
    "attrs": ("attr", "attrs"),
    "protobuf": ("google",),
    "psycopg2-binary": ("psycopg2",),
    "python-multipart": ("multipart",),
}

# Packages that are legitimately never imported: runners, linters, build
# backends, and plugins loaded through entry points.
TOOLING_NAMES = frozenset({
    "pytest", "ruff", "mypy", "coverage", "black", "flake8", "isort", "tox",
    "hatchling", "setuptools", "wheel", "build", "twine", "pre-commit",
    "pip", "uv", "poetry", "nox", "bandit", "pylint",
})
TOOLING_PREFIXES = ("pytest-", "types-", "flake8-", "sphinx", "mypy-",
                    "pytest_")


class Declared(BaseModel):
    """One direct dependency as a manifest declares it."""
    name: str                 # PEP 503 normalized
    raw: str                  # the declaration verbatim -- used as evidence
    manifest: str             # repo-relative path it came from
    constraint: str = ""      # "" when unconstrained
    line: int | None = None


def normalize(name: str) -> str:
    """PEP 503 normalization: runs of -, _ and . collapse to a single -."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


# name, optional [extras], then everything up to a marker or comment.
_REQ = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"\s*(?:\[[^\]]*\])?"
    r"\s*(?P<spec>[^;#]*)")


def _declared(name: str, raw: str, manifest: str, spec: str,
              line: int | None = None) -> Declared:
    return Declared(name=normalize(name), raw=raw.strip(), manifest=manifest,
                    constraint=spec.strip(), line=line)


def parse_requirements(manifest: str, text: str) -> list[Declared]:
    """Direct dependencies from a requirements.txt.

    Skips comments, blank lines, option lines (-r/-e/--index-url) and URLs:
    an included file is a different manifest, and a VCS or path install has
    no name we can normalize honestly.
    """
    out: list[Declared] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "://" in line:
            continue
        match = _REQ.match(line)
        if match:
            out.append(_declared(match.group("name"), line, manifest,
                                 match.group("spec"), lineno))
    return out


def parse_pyproject(manifest: str, text: str) -> list[Declared]:
    """Direct dependencies from [project] and [project.optional-dependencies].

    A malformed pyproject yields no declarations rather than raising: the
    activity turns a raise into not_collected for the whole signal, and one
    unparseable manifest should not erase a sibling requirements.txt.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    project = data.get("project") or {}
    specs: list[str] = list(project.get("dependencies") or [])
    for group in (project.get("optional-dependencies") or {}).values():
        specs.extend(group or [])
    out: list[Declared] = []
    for spec in specs:
        match = _REQ.match(str(spec))
        if match:
            out.append(_declared(match.group("name"), str(spec), manifest,
                                 match.group("spec")))
    return out


PARSERS = {
    "pyproject.toml": parse_pyproject,
    "requirements.txt": parse_requirements,
}


def parse_manifests(blobs: Mapping[str, str]) -> list[Declared]:
    """Every declaration across the manifests we recognize, keyed by the
    manifest's BASENAME so a monorepo's apps/web/requirements.txt parses too."""
    out: list[Declared] = []
    for path in sorted(blobs):
        parser = PARSERS.get(posixpath.basename(path))
        if parser is not None:
            out.extend(parser(path, blobs[path]))
    return out


_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+(?P<from>[A-Za-z_][\w.]*)"
    r"|import[ \t]+(?P<import>[A-Za-z_][\w.]*"
    r"(?:[ \t]*,[ \t]*[A-Za-z_][\w.]*)*))",
    re.MULTILINE)


def imported_modules(texts: Iterable[str]) -> set[str]:
    """Top-level module names imported anywhere in the given source.

    Regex, not AST, deliberately: this runs over every source file and must
    survive a file that does not parse, which is common in the repositories
    Tier 0 triages.
    """
    out: set[str] = set()
    for text in texts:
        for match in _IMPORT.finditer(text):
            chunk = match.group("from") or match.group("import") or ""
            for part in chunk.split(","):
                top = part.strip().split(".")[0]
                if top:
                    out.add(top)
    return out


def _is_pinned(constraint: str) -> bool:
    """A constraint pins iff it fixes an exact version. `>=`, `~=` and a bare
    name all float; `!=` alone excludes without fixing."""
    return "==" in constraint


def _is_tooling(name: str) -> bool:
    return name in TOOLING_NAMES or name.startswith(TOOLING_PREFIXES)


def _provides(name: str) -> tuple[str, ...]:
    """The module names a distribution may supply: its alias-table entry if it
    has one, otherwise both the dashed and underscored forms of its name."""
    if name in IMPORT_ALIASES:
        return IMPORT_ALIASES[name]
    return (name, name.replace("-", "_"))


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def evaluate(declared: Sequence[Declared], lockfile_present: bool,
             imported: set[str],
             advisories: AdvisoryResult) -> SignalResult:
    """Dependency health over parsed declarations.

    `imported` is the top-level module set from `imported_modules`.
    `advisories` carries its own Measurement, which becomes the
    known_vulnerable metric unchanged -- this function never converts a
    not_collected lookup into a zero.
    """
    findings: list[TriageFinding] = []

    for d in sorted(declared, key=lambda d: (d.manifest, d.name)):
        if not _is_pinned(d.constraint):
            mitigation = ("a lockfile is tracked, so resolution is still "
                          "reproducible" if lockfile_present
                          else "no lockfile is tracked, so two installs can "
                               "resolve to different versions")
            findings.append(_finding(
                "unpinned_dependency", "medium",
                f"{d.name} is declared without an exact version and "
                f"{mitigation}.",
                FixClass.MECHANICAL, d.manifest, d.line, d.raw))

    by_name: dict[str, set[str]] = {}
    origin: dict[str, Declared] = {}
    for d in declared:
        by_name.setdefault(d.name, set()).add(d.constraint)
        origin.setdefault(d.name, d)
    for name in sorted(by_name):
        if len(by_name[name]) > 1:
            constraints = ", ".join(sorted(c or "(none)"
                                           for c in by_name[name]))
            findings.append(_finding(
                "duplicate_dependency", "medium",
                f"{name} is declared more than once with conflicting "
                f"constraints ({constraints}); which one wins depends on "
                f"install order.",
                FixClass.MECHANICAL, origin[name].manifest))

    for adv in advisories.advisories:
        d = origin.get(normalize(adv.package))
        findings.append(_finding(
            "known_vulnerable", adv.severity,
            f"{adv.package} matches {adv.advisory_id}"
            f"{': ' + adv.summary if adv.summary else ''}. Upgrading is a "
            f"one-line edit; deciding the upgrade is safe is not.",
            # JUDGEMENT per spec D7's shape -- E-44 promises a MECHANICAL
            # finding can be closed by a PR without judgement, and a version
            # bump can break the build.
            FixClass.JUDGEMENT,
            d.manifest if d else "", d.line if d else None,
            d.raw if d else ""))

    for name in sorted(by_name):
        if _is_tooling(name):
            continue
        if any(module in imported for module in _provides(name)):
            continue
        d = origin[name]
        findings.append(_finding(
            "unused_dependency", "low",
            f"{name} is declared but no source file imports it. Distribution "
            f"names and import names diverge, so confirm before removing.",
            FixClass.MECHANICAL, d.manifest, d.line, d.raw))

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={
            M_DIRECT: Measurement.measured(float(len(by_name))),
            # Passed through unchanged: a not_collected lookup stays
            # not_collected here (D16).
            M_VULNERABLE: advisories.collected,
        })
```

- [ ] **Step 4: Run the pure-logic tests to verify they pass**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_dependencies.py -q`
Expected: PASS (13 tests)

- [ ] **Step 5: Add the activity**

In `src/sdlc/triage/activities.py`, add `import posixpath` to the stdlib imports (repo-relative paths are always posix, and `os.path` would split on `\` on Windows), then add:

```python
from .advisories import resolve_advisory_source
from .signals import baseline, build_probe, dependencies, secrets
```

(replace the existing `from .signals import baseline, build_probe, secrets`)

Then append this activity:

```python
@dataclass
class TriageDependencyInput:
    repo_dir: str
    commit_sha: str
    # Spec D11: the default collects nothing. Naming a source here is an
    # explicit operator act, and it is a declared outbound egress (FR-703).
    advisory_source: str = "none"


@activity.defn
async def triage_dependencies(inp: TriageDependencyInput) -> SignalResult:
    """FR-902 dependency health (E-41a). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        adapter = found[0] if found else None

        manifest_names = set(adapter.manifests) if adapter else set()
        source_exts = tuple(adapter.source_extensions) if adapter else ()
        wanted = sorted(
            p for p in paths
            if posixpath.basename(p) in manifest_names
            or (source_exts and p.endswith(source_exts)))

        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))
        manifests = {p: t for p, t in blobs.items()
                     if posixpath.basename(p) in manifest_names}
        sources = [t for p, t in blobs.items() if p not in manifests]

        declared = dependencies.parse_manifests(manifests)
        lockfile_present = bool(adapter) and any(
            lf in set(paths) for lf in adapter.lockfiles)
        advisories = resolve_advisory_source(inp.advisory_source).lookup(
            adapter.ecosystem if adapter else None,
            sorted({d.name for d in declared}))

        result = dependencies.evaluate(
            declared, lockfile_present,
            dependencies.imported_modules(sources), advisories)
        return _verified(result, blobs)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage dependencies signal failed: %s", exc)
        return SignalResult(
            signal=dependencies.SIGNAL_ID, version=dependencies.VERSION,
            collected=Measurement.not_collected(
                f"dependencies signal raised: {type(exc).__name__}: {exc}"))
```

Add this shared helper above the activities (it is reused by Tasks 5–7):

```python
def _verified(result: SignalResult, blobs: dict[str, str]) -> SignalResult:
    """Drop any finding whose evidence does not verify against the bytes it
    cites (spec D5).

    For deterministic rules the quote is verbatim by construction, so this is
    a DRIFT guard -- it catches a citation that no longer resolves at that
    path and sha -- not a hallucination guard. It becomes load-bearing when
    E-48's LLM proposers cite the same way (FR-914).
    """
    kept = []
    for finding in result.findings:
        if not finding.evidence:
            kept.append(finding)
            continue
        blob = blobs.get(finding.path)
        if blob is not None and verify_quote(
                finding.evidence, blob, Profile.VERBATIM_BYTES):
            kept.append(finding)
        else:
            _log.warning("triage %s: dropping unverifiable evidence for %s "
                         "at %s", result.signal, finding.rule, finding.path)
    return result.model_copy(update={"findings": kept})
```

- [ ] **Step 6: Register the signal**

In `src/sdlc/triage/registry.py`, change the import and add the entry:

```python
from .signals import baseline, build_probe, dependencies, secrets
```

```python
    dependencies.SIGNAL_ID: SignalSpec(
        id=dependencies.SIGNAL_ID, version=dependencies.VERSION,
        activity="triage_dependencies"),
```

In `src/sdlc/worker.py`, extend the import (line 57–59) and the activity list (line 118):

```python
from .triage.activities import (
    triage_baseline, triage_build_probe, triage_dependencies, triage_secrets,
)
```

```python
            triage_baseline, triage_secrets, triage_build_probe,
            triage_dependencies,
```

- [ ] **Step 7: Write the activity test**

Append to `tests/test_triage_dependencies.py`:

```python
# ---- activity ---------------------------------------------------------

import subprocess

import pytest

from sdlc.triage.activities import TriageDependencyInput, triage_dependencies


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL)


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()


@pytest.mark.asyncio
async def test_activity_reads_manifests_at_the_pinned_commit(tmp_path):
    sha = _commit_repo(tmp_path, {
        "pyproject.toml": PYPROJECT,
        "src/app.py": "import requests\nimport pydantic\nfrom PIL import Image\n",
    })
    r = await triage_dependencies(TriageDependencyInput(
        repo_dir=str(tmp_path), commit_sha=sha))
    assert r.signal == "dependencies"
    assert r.collected.state is CollectionState.MEASURED
    assert "unpinned_dependency" in _rules(r)
    # pillow is imported as PIL, and pytest is tooling.
    assert "unused_dependency" not in _rules(r)
    assert r.metrics["known_vulnerable"].state is CollectionState.NOT_COLLECTED


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _commit_repo(tmp_path, {"pyproject.toml": PYPROJECT})
    r = await triage_dependencies(TriageDependencyInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []
```

- [ ] **Step 8: Run the full test file**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_dependencies.py tests/test_triage_registry.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/sdlc/triage/signals/dependencies.py src/sdlc/triage/activities.py \
        src/sdlc/triage/registry.py src/sdlc/worker.py \
        tests/test_triage_dependencies.py
git commit -m "feat(triage): dependency health signal (E-41a)

FR-902's fourth signal family: unpinned, duplicated, known-vulnerable and
unused direct dependencies, behind the FR-108 adapter's manifest names and
OSV ecosystem. known_vulnerable is JUDGEMENT (spec D7) and its metric
passes the advisory lookup's Measurement through unchanged, so the default
source reports not_collected rather than zero."
```

---

### Task 5: `scaffold` signal (E-41b) and the `M_STRUCTURE` migration

Spec §6, D12, D13. **This task moves a readiness key between signals.** Do the migration and its regression guard in one commit — a half-applied move either raises at `compute_readiness` or silently loses the dimension.

**Files:**
- Create: `src/sdlc/triage/signals/scaffold.py`
- Modify: `src/sdlc/triage/signals/baseline.py` (drop `M_STRUCTURE` and `_SOURCE_EXTENSIONS`, `VERSION = 2`)
- Modify: `src/sdlc/triage/activities.py` (add `triage_scaffold` and `commit_touch_counts`)
- Modify: `src/sdlc/triage/registry.py`, `src/sdlc/worker.py`
- Modify: `tests/test_triage_baseline.py` (drop the two `M_STRUCTURE` assertions)
- Test: `tests/test_triage_scaffold.py`

**Interfaces:**
- Consumes: `gitread.read_tree` (Task 1); `ToolchainAdapter.source_extensions` / `.test_globs` (Task 2); `dependencies.imported_modules` (Task 4).
- Produces:
  - `scaffold.SIGNAL_ID = "scaffold"`, `scaffold.VERSION = 1`, `scaffold.SCAFFOLD_RATIO_THRESHOLD = 0.9`
  - `scaffold.M_HISTORY_BASIS = "history_basis"`, `scaffold.M_SCAFFOLD_FILES = "scaffold_files"`
  - `Fingerprint(generator: str, path_glob: str, marker: str)`, `FINGERPRINTS: tuple[Fingerprint, ...]`
  - `scaffolded_paths(blobs) -> dict[str, str]` — path → generator
  - `evaluate(paths, blobs, touch_counts, toolchain) -> SignalResult`
  - `activities.commit_touch_counts(repo_dir, commit_sha, max_commits=2000) -> dict[str, int] | None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_scaffold.py`:

```python
"""FR-902 generator scaffolding and dead code (E-41b), and the new owner of
structure_discernible (spec D12)."""
from sdlc.measurement import CollectionState
from sdlc.toolchain.adapters import PythonToolchain
from sdlc.triage.models import (
    FixClass, M_STRUCTURE, SignalResult, compute_readiness,
)
from sdlc.triage.signals import baseline, scaffold

CRA_APP = ("function App() {\n"
           "  return <p>Edit <code>src/App.js</code> and save to reload.</p>;\n"
           "}\n")
NEXT_README = ("# app\n\nThis is a [Next.js](https://nextjs.org) project "
               "bootstrapped with [`create-next-app`](https://x).\n")
DJANGO_MANAGE = ('"""Django\'s command-line utility for administrative '
                 'tasks."""\nimport os\n')


def _rules(result):
    return {f.rule for f in result.findings}


# ---- fingerprints -----------------------------------------------------

def test_fingerprints_match_known_generator_output():
    got = scaffold.scaffolded_paths({
        "src/App.js": CRA_APP,
        "README.md": NEXT_README,
        "manage.py": DJANGO_MANAGE,
    })
    assert got == {"src/App.js": "create-react-app",
                   "README.md": "create-next-app",
                   "manage.py": "django-admin"}


def test_a_hand_edited_file_is_not_scaffolding():
    edited = "function App() {\n  return <p>My real app</p>;\n}\n"
    assert scaffold.scaffolded_paths({"src/App.js": edited}) == {}


def test_a_matching_path_with_no_marker_is_not_scaffolding():
    assert scaffold.scaffolded_paths({"README.md": "# My project\n"}) == {}


# ---- history corroboration (D13) --------------------------------------

def test_history_escalates_an_untouched_scaffold_file():
    touched = scaffold.evaluate(
        ["src/App.js"], {"src/App.js": CRA_APP}, {"src/App.js": 4}, None)
    untouched = scaffold.evaluate(
        ["src/App.js"], {"src/App.js": CRA_APP}, {"src/App.js": 1}, None)
    assert touched.findings[0].severity == "low"
    assert untouched.findings[0].severity == "medium"
    assert "untouched since import" in untouched.findings[0].detail


def test_no_history_leaves_severity_at_the_fingerprint_level():
    r = scaffold.evaluate(["src/App.js"], {"src/App.js": CRA_APP}, None, None)
    assert r.findings[0].severity == "low"
    assert r.metrics[scaffold.M_HISTORY_BASIS].state \
        is CollectionState.NOT_COLLECTED
    # The SIGNAL still collected -- the fingerprints ran.
    assert r.collected.state is CollectionState.MEASURED


def test_scaffolding_is_judgement_not_mechanical():
    r = scaffold.evaluate(["src/App.js"], {"src/App.js": CRA_APP}, None, None)
    assert r.findings[0].fix_class is FixClass.JUDGEMENT


# ---- dead code --------------------------------------------------------

def test_an_unimported_module_is_reported_unreferenced():
    r = scaffold.evaluate(
        ["src/app.py", "src/orphan.py"],
        {"src/app.py": "import os\n", "src/orphan.py": "x = 1\n"},
        None, PythonToolchain())
    assert "unreferenced_module" in _rules(r)
    assert [f.path for f in r.findings
            if f.rule == "unreferenced_module"] == ["src/orphan.py"]


def test_entrypoint_conventions_are_never_unreferenced():
    paths = ["main.py", "__init__.py", "conftest.py", "manage.py",
             "tests/test_a.py", "__main__.py"]
    r = scaffold.evaluate(paths, {p: "x = 1\n" for p in paths}, None,
                          PythonToolchain())
    assert "unreferenced_module" not in _rules(r)


def test_an_imported_module_is_not_unreferenced():
    r = scaffold.evaluate(
        ["src/app.py", "src/helper.py"],
        {"src/app.py": "from helper import go\n", "src/helper.py": "def go():\n    pass\n"},
        None, PythonToolchain())
    assert "unreferenced_module" not in _rules(r)


# ---- M_STRUCTURE, the migrated dimension (D12) ------------------------

def test_structure_is_not_collected_without_a_toolchain():
    r = scaffold.evaluate(["src/a.py"], {"src/a.py": "x = 1\n"}, None, None)
    m = r.metrics[M_STRUCTURE]
    assert m.state is CollectionState.NOT_COLLECTED
    assert "marker" in m.reason


def test_structure_is_zero_when_a_toolchain_resolves_but_no_source_exists():
    r = scaffold.evaluate(["README.md"], {"README.md": "x\n"}, None,
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 0.0


def test_structure_is_one_for_real_source():
    r = scaffold.evaluate(["src/a.py"], {"src/a.py": "x = 1\n"}, None,
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 1.0


def test_structure_is_zero_when_source_is_almost_all_scaffolding():
    paths = ["manage.py"]
    r = scaffold.evaluate(paths, {"manage.py": DJANGO_MANAGE}, None,
                          PythonToolchain())
    assert r.metrics[M_STRUCTURE].value == 0.0


# ---- the migration regression guard (D12) -----------------------------

def test_baseline_no_longer_reports_structure():
    r = baseline.evaluate(["pyproject.toml", "src/a.py"], "",
                          PythonToolchain())
    assert M_STRUCTURE not in r.metrics
    assert baseline.VERSION == 2


def test_two_signals_reporting_structure_still_raises():
    # The invariant the migration must not break: exactly one owner per
    # readiness key. If a future edit re-adds M_STRUCTURE to baseline, this
    # fails loudly instead of silently preferring a producer.
    import pytest
    from sdlc.measurement import Measurement
    a = SignalResult(signal="a", version=1,
                     collected=Measurement.measured(0.0),
                     metrics={M_STRUCTURE: Measurement.measured(1.0)})
    b = SignalResult(signal="b", version=1,
                     collected=Measurement.measured(0.0),
                     metrics={M_STRUCTURE: Measurement.measured(0.0)})
    with pytest.raises(ValueError, match="more than one signal"):
        compute_readiness([a, b])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_scaffold.py -q`
Expected: FAIL — `ImportError: cannot import name 'scaffold'`

- [ ] **Step 3: Write the signal module**

Create `src/sdlc/triage/signals/scaffold.py`:

```python
"""FR-902 generator scaffolding and dead code (E-41b).

THE OWNER OF structure_discernible (spec D12). `compute_readiness` admits
exactly one signal per readiness key, so "E-41b sharpens the dimension"
cannot mean "E-41b also reports it" -- ownership moved here and baseline
dropped it. The consequence is deliberate: a scaffold signal that fails
leaves the dimension unmeasured, which forces INDETERMINATE, and "we could
not tell whether this is real code or a generator's output" is the honest
readiness verdict for that state.

Fingerprint-first, history-corroborating (spec D13). History alone misfires
hardest on exactly the repositories Tier 0 targets: a vibe-coded repo is
often one enormous initial commit, where "untouched since import" is true of
every file including the hand-written ones. As corroboration it is additive
and cannot invent a finding.
"""
from __future__ import annotations

import fnmatch
import posixpath
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from ...measurement import Measurement
from ...toolchain.adapters import ToolchainAdapter
from ..models import FixClass, M_STRUCTURE, SignalResult, TriageFinding
from .dependencies import imported_modules

SIGNAL_ID = "scaffold"
VERSION = 1

M_HISTORY_BASIS = "history_basis"
M_SCAFFOLD_FILES = "scaffold_files"

# A repository whose source is this share of fingerprinted generator output
# is not structurally discernible. Not 1.0: a real project keeps its
# generator's manage.py, and one surviving default file is not scaffolding.
SCAFFOLD_RATIO_THRESHOLD = 0.9

# Paths that are entrypoints by convention and therefore never "unreferenced"
# merely because nothing imports them.
_ENTRYPOINT_STEMS = frozenset({
    "__init__", "__main__", "main", "manage", "conftest", "setup", "wsgi",
    "asgi", "app",
})


class Fingerprint(BaseModel):
    """A generator's output, identified by a path convention AND a content
    marker that survives only while nobody has edited the file. Both halves
    are required: the path alone would flag every README."""
    generator: str
    path_glob: str
    marker: str


FINGERPRINTS: tuple[Fingerprint, ...] = (
    Fingerprint(generator="create-next-app", path_glob="README.md",
                marker="bootstrapped with [`create-next-app`]"),
    Fingerprint(generator="create-next-app", path_glob="app/page.tsx",
                marker="Get started by editing"),
    Fingerprint(generator="create-next-app", path_glob="app/page.js",
                marker="Get started by editing"),
    Fingerprint(generator="create-next-app", path_glob="pages/index.js",
                marker="Get started by editing"),
    Fingerprint(generator="create-react-app", path_glob="src/App.js",
                marker="Edit <code>src/App.js</code> and save to reload."),
    Fingerprint(generator="create-react-app", path_glob="src/App.tsx",
                marker="Edit <code>src/App.tsx</code> and save to reload."),
    Fingerprint(generator="vite", path_glob="index.html",
                marker="<title>Vite +"),
    Fingerprint(generator="django-admin", path_glob="manage.py",
                marker="Django's command-line utility for administrative "
                       "tasks"),
    Fingerprint(generator="django-admin", path_glob="*/settings.py",
                marker="SECRET_KEY = 'django-insecure-"),
)


def scaffolded_paths(blobs: Mapping[str, str]) -> dict[str, str]:
    """path -> generator, for every blob still carrying its generator's
    marker. A path that matches a glob but whose marker is gone has been
    edited and is not reported."""
    out: dict[str, str] = {}
    for path in sorted(blobs):
        for fp in FINGERPRINTS:
            if fnmatch.fnmatch(path, fp.path_glob) \
                    and fp.marker in blobs[path]:
                out[path] = fp.generator
                break
    return out


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         evidence=evidence)


def evaluate(paths: Sequence[str], blobs: Mapping[str, str],
             touch_counts: Mapping[str, int] | None,
             toolchain: ToolchainAdapter | None) -> SignalResult:
    """`paths` is every tracked path; `blobs` is text for the readable ones;
    `touch_counts` is path -> commits touching it, or None when the repository
    yields no usable history (D13)."""
    scaffolded = scaffolded_paths(blobs)
    findings: list[TriageFinding] = []

    for path, generator in sorted(scaffolded.items()):
        untouched = touch_counts is not None \
            and touch_counts.get(path, 0) <= 1
        findings.append(_finding(
            "generator_scaffold", "medium" if untouched else "low",
            f"{path} is unmodified {generator} output"
            f"{', untouched since import' if untouched else ''}. Removing or "
            f"replacing generator output is a decision about what the "
            f"application is.",
            FixClass.JUDGEMENT, path,
            # The marker itself is verbatim in the blob by construction, so
            # it is the natural evidence quote.
            next(fp.marker for fp in FINGERPRINTS
                 if fnmatch.fnmatch(path, fp.path_glob)
                 and fp.marker in blobs[path])))

    exts = tuple(toolchain.source_extensions) if toolchain else ()
    test_globs = tuple(toolchain.test_globs) if toolchain else ()
    source = [p for p in sorted(paths) if exts and p.endswith(exts)]

    if source:
        imported = imported_modules(
            blobs[p] for p in source if p in blobs)
        for path in source:
            stem = posixpath.splitext(posixpath.basename(path))[0]
            if stem in _ENTRYPOINT_STEMS:
                continue
            if any(fnmatch.fnmatch(path, g)
                   or fnmatch.fnmatch(posixpath.basename(path), g)
                   for g in test_globs):
                continue
            if stem in imported:
                continue
            findings.append(_finding(
                "unreferenced_module", "low",
                f"{path} is not imported by any tracked source file. "
                f"Deleting code is a decision, not a mechanical patch.",
                FixClass.JUDGEMENT, path))

    if toolchain is None:
        structure = Measurement.not_collected(
            "no toolchain marker resolved, so structure is not assessable")
    elif not source:
        structure = Measurement.measured(0.0)
    else:
        ratio = len([p for p in source if p in scaffolded]) / len(source)
        structure = Measurement.measured(
            0.0 if ratio >= SCAFFOLD_RATIO_THRESHOLD else 1.0)

    history = (Measurement.measured(1.0) if touch_counts is not None
               else Measurement.not_collected(
                   "no usable commit history: a single-commit repository says "
                   "nothing about what has been touched"))

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={
            M_STRUCTURE: structure,
            M_HISTORY_BASIS: history,
            M_SCAFFOLD_FILES: Measurement.measured(float(len(scaffolded))),
        })
```

- [ ] **Step 4: Migrate `baseline` to version 2**

In `src/sdlc/triage/signals/baseline.py`:

1. Change `VERSION = 1` to `VERSION = 2`.
2. Delete the `_SOURCE_EXTENSIONS` block (lines 24–28) — it lives on the adapter now (`source_extensions`).
3. Delete the `M_STRUCTURE` import from the `..models` import list, leaving `FixClass, M_TESTS_PRESENT, SignalResult, TriageFinding`.
4. Delete the structure computation (lines 123–128):

```python
    if toolchain is None:
        structure = Measurement.not_collected(
            "no toolchain marker resolved, so structure is not assessable")
    else:
        has_source = any(p.endswith(_SOURCE_EXTENSIONS) for p in tracked)
        structure = Measurement.measured(1.0 if has_source else 0.0)
```

5. Replace the `metrics=` block in the return with:

```python
        metrics={
            # structure_discernible moved to the scaffold signal (E-41b,
            # spec D12): exactly one signal may own a readiness key, and the
            # sharpened dimension needs fingerprints this signal does not have.
            M_TESTS_PRESENT: Measurement.measured(float(len(test_files))),
        })
```

In `tests/test_triage_baseline.py`, delete the two assertions that read `M_STRUCTURE` from `baseline` (line 58 `assert r.metrics[M_STRUCTURE].value == 1.0`, and the whole of `test_structure_not_collected_without_a_toolchain` and `test_structure_is_zero_when_toolchain_resolves_but_no_source_exists`), and drop `M_STRUCTURE` from its `..models` import. Those cases now live in `tests/test_triage_scaffold.py`.

- [ ] **Step 5: Run the migration guard**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_scaffold.py tests/test_triage_baseline.py tests/test_triage_readiness.py -q`
Expected: PASS. If `test_two_signals_reporting_structure_still_raises` fails, the migration is half-applied.

- [ ] **Step 6: Add the activity and the history reader**

In `src/sdlc/triage/activities.py`, add `scaffold` to the `.signals` import, then append:

```python
def commit_touch_counts(repo_dir: str, commit_sha: str,
                        max_commits: int = 2000) -> dict[str, int] | None:
    """path -> commits touching it, over at most `max_commits` commits ending
    at `commit_sha`. None when history yields no usable signal (spec D13).

    A single-commit repository returns None rather than "everything touched
    once": the latter is true and useless, and it would escalate every
    fingerprinted file in exactly the repositories Tier 0 sees most.

    Deterministic given the same repository and sha (NFR-10). What history
    does not survive is a squash or re-import, which changes stability across
    re-creations, not reproducibility at a pinned commit -- and since history
    only adjusts severity, a re-import degrades sharpness, never correctness.
    """
    proc = _git(["log", f"--max-count={max_commits}", "--name-only",
                 "--format=%x00", commit_sha], cwd=repo_dir)
    if proc.returncode != 0:
        return None
    if proc.stdout.count("\x00") <= 1:
        return None
    counts: dict[str, int] = {}
    for line in proc.stdout.splitlines():
        if not line or line.startswith("\x00"):
            continue
        counts[line.strip()] = counts.get(line.strip(), 0) + 1
    return counts


@activity.defn
async def triage_scaffold(inp: TriageSignalInput) -> SignalResult:
    """FR-902 generator scaffolding and dead code (E-41b). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        adapter = found[0] if found else None
        exts = tuple(adapter.source_extensions) if adapter else ()

        # Fingerprints target specific paths; source extensions cover the
        # dead-code half and the structure ratio. Reading their union keeps
        # this to one pass.
        wanted = sorted({
            p for p in paths
            if (exts and p.endswith(exts))
            or any(fnmatch.fnmatch(p, fp.path_glob)
                   for fp in scaffold.FINGERPRINTS)})
        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))

        result = scaffold.evaluate(
            paths, blobs,
            commit_touch_counts(inp.repo_dir, inp.commit_sha),
            adapter)
        return _verified(result, blobs)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage scaffold signal failed: %s", exc)
        return SignalResult(
            signal=scaffold.SIGNAL_ID, version=scaffold.VERSION,
            collected=Measurement.not_collected(
                f"scaffold signal raised: {type(exc).__name__}: {exc}"))
```

Add `import fnmatch` to the top of `activities.py`.

- [ ] **Step 7: Register the signal**

In `src/sdlc/triage/registry.py`, add `scaffold` to the `.signals` import and add:

```python
    scaffold.SIGNAL_ID: SignalSpec(
        id=scaffold.SIGNAL_ID, version=scaffold.VERSION,
        activity="triage_scaffold"),
```

In `src/sdlc/worker.py`, add `triage_scaffold` to both the import and the activity list.

- [ ] **Step 8: Write the activity test**

Append to `tests/test_triage_scaffold.py`:

```python
# ---- activity ---------------------------------------------------------

import subprocess

import pytest

from sdlc.triage.activities import (
    TriageSignalInput, commit_touch_counts, triage_scaffold,
)


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL)


def _init(root):
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)


def _commit(root, files: dict[str, str], message: str) -> str:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", message], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True).stdout.strip()


def test_touch_counts_is_none_for_a_single_commit_repo(tmp_path):
    _init(tmp_path)
    sha = _commit(tmp_path, {"a.py": "x = 1\n"}, "one")
    assert commit_touch_counts(str(tmp_path), sha) is None


def test_touch_counts_counts_commits_per_path(tmp_path):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 1\n"}, "one")
    sha = _commit(tmp_path, {"a.py": "x = 2\n"}, "two")
    counts = commit_touch_counts(str(tmp_path), sha)
    assert counts["a.py"] == 2
    assert counts["b.py"] == 1


@pytest.mark.asyncio
async def test_activity_escalates_untouched_scaffolding(tmp_path):
    _init(tmp_path)
    _commit(tmp_path, {"pyproject.toml": "[project]\n",
                       "manage.py": DJANGO_MANAGE,
                       "src/app.py": "import os\n"}, "one")
    sha = _commit(tmp_path, {"src/app.py": "import os\nimport sys\n"}, "two")
    r = await triage_scaffold(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha=sha))
    assert r.collected.state is CollectionState.MEASURED
    f = next(f for f in r.findings if f.rule == "generator_scaffold")
    assert f.severity == "medium"
    assert r.metrics[scaffold.M_HISTORY_BASIS].state \
        is CollectionState.MEASURED


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _init(tmp_path)
    _commit(tmp_path, {"a.py": "x = 1\n"}, "one")
    r = await triage_scaffold(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []
```

- [ ] **Step 9: Run the whole triage suite**

Run: `PYTHONPATH=. uv run pytest tests/ -k triage -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add src/sdlc/triage/signals/scaffold.py src/sdlc/triage/signals/baseline.py \
        src/sdlc/triage/activities.py src/sdlc/triage/registry.py \
        src/sdlc/worker.py tests/test_triage_scaffold.py \
        tests/test_triage_baseline.py
git commit -m "feat(triage): generator-scaffold and dead-code signal (E-41b)

Fingerprint-first with git history only corroborating (spec D13): history
alone misfires on the single-initial-commit repositories Tier 0 targets, so
it adjusts severity and can never invent a finding. A single-commit repo
reports history_basis not_collected and stays MEASURED.

Also migrates structure_discernible from baseline to this signal (spec
D12), because compute_readiness admits exactly one owner per readiness key.
baseline goes to version 2. The floor is RAISED, not removed: an
unfingerprinted generator's output still passes the dimension."
```

---

### Task 6: `misconfig` signal (E-41c)

Spec §7. Includes the `secrets` exclusion that keeps the two signals from double-reporting the same line.

**Files:**
- Create: `src/sdlc/triage/signals/misconfig.py`
- Modify: `src/sdlc/triage/signals/secrets.py` (exclude the Django placeholder from `generic_secret_assignment`; `VERSION = 2`)
- Modify: `src/sdlc/triage/activities.py`, `src/sdlc/triage/registry.py`, `src/sdlc/worker.py`
- Test: `tests/test_triage_misconfig.py`

**Interfaces:**
- Consumes: `gitread.read_tree` (Task 1); `ToolchainAdapter.source_extensions` (Task 2); `activities._verified` (Task 4).
- Produces:
  - `misconfig.SIGNAL_ID = "misconfig"`, `misconfig.VERSION = 1`
  - `misconfig.M_FRAMEWORKS = "frameworks_detected"`
  - `detect_frameworks(blobs) -> set[str]`
  - `evaluate(blobs) -> SignalResult`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_misconfig.py`:

```python
"""FR-902 framework-default misconfiguration (E-41c)."""
from sdlc.measurement import CollectionState
from sdlc.triage.models import FixClass
from sdlc.triage.signals import misconfig, secrets


def _rules(result):
    return {f.rule for f in result.findings}


def test_permissive_cors_fires_on_fastapi_and_flask_forms():
    fastapi = ('from fastapi import FastAPI\n'
               'app.add_middleware(CORSMiddleware, allow_origins=["*"])\n')
    flask = ('from flask import Flask\n'
             'CORS(app, origins="*")\n')
    assert "permissive_cors" in _rules(misconfig.evaluate({"a.py": fastapi}))
    assert "permissive_cors" in _rules(misconfig.evaluate({"b.py": flask}))


def test_credentialed_wildcard_cors_is_critical():
    text = ('from fastapi import FastAPI\n'
            'app.add_middleware(CORSMiddleware, allow_origins=["*"], '
            'allow_credentials=True)\n')
    f = next(f for f in misconfig.evaluate({"a.py": text}).findings
             if f.rule == "permissive_cors")
    assert f.severity == "critical"


def test_debug_enabled_fires_for_django_and_flask():
    django = "from django.conf import settings\nDEBUG = True\n"
    flask = "from flask import Flask\napp.run(debug=True)\n"
    assert "debug_enabled" in _rules(misconfig.evaluate({"s.py": django}))
    assert "debug_enabled" in _rules(misconfig.evaluate({"a.py": flask}))


def test_debug_false_does_not_fire():
    assert "debug_enabled" not in _rules(
        misconfig.evaluate({"s.py": "from django.conf import x\nDEBUG = False\n"}))


def test_allowed_hosts_wildcard_fires():
    text = "from django.conf import x\nALLOWED_HOSTS = ['*']\n"
    assert "allowed_hosts_wildcard" in _rules(misconfig.evaluate({"s.py": text}))


def test_the_django_placeholder_key_is_misconfig_and_judgement():
    text = ("from django.conf import x\n"
            "SECRET_KEY = 'django-insecure-abc123defg456hijk789lmno'\n")
    f = next(f for f in misconfig.evaluate({"settings.py": text}).findings
             if f.rule == "django_insecure_secret_key")
    assert f.severity == "critical"
    assert f.fix_class is FixClass.JUDGEMENT


def test_secrets_does_not_also_report_the_django_placeholder():
    # Spec section 7: secrets owns credential MATERIAL, misconfig owns
    # generator DEFAULTS. One line must not produce two findings from two
    # signals, or a report double-counts its own severity.
    text = "SECRET_KEY = 'django-insecure-abc123defg456hijk789lmno'\n"
    assert secrets.scan_text("settings.py", text) == []


def test_secrets_still_reports_a_real_secret_key_assignment():
    text = "SECRET_KEY = 'p8Fq2XvR7nZk4LmT9wYc'\n"
    rules = {f.rule for f in secrets.scan_text("settings.py", text)}
    assert "generic_secret_assignment" in rules


def test_world_readable_storage_fires_on_firebase_and_iac():
    firebase = "service firebase.storage {\n  allow read, write: if true;\n}\n"
    iam = '{"Statement": [{"Principal": "*"}]}\n'
    assert "world_readable_storage" in _rules(
        misconfig.evaluate({"storage.rules": firebase}))
    assert "world_readable_storage" in _rules(
        misconfig.evaluate({"policy.json": iam}))


# ---- unauthenticated_app, the whole-app rule --------------------------

def test_unauthenticated_app_fires_once_for_the_repository():
    a = ('from fastapi import FastAPI\napp = FastAPI()\n'
         '@app.post("/items")\ndef create():\n    return 1\n')
    b = ('@app.delete("/items/{i}")\ndef remove(i):\n    return 1\n')
    r = misconfig.evaluate({"a.py": a, "b.py": b})
    assert [f.rule for f in r.findings].count("unauthenticated_app") == 1


def test_declared_auth_anywhere_suppresses_it():
    a = ('from fastapi import FastAPI\napp = FastAPI()\n'
         '@app.post("/items")\ndef create():\n    return 1\n')
    b = 'from fastapi.security import OAuth2PasswordBearer\n'
    assert "unauthenticated_app" not in _rules(
        misconfig.evaluate({"a.py": a, "b.py": b}))


def test_a_read_only_app_does_not_fire():
    a = ('from fastapi import FastAPI\napp = FastAPI()\n'
         '@app.get("/items")\ndef read():\n    return 1\n')
    assert "unauthenticated_app" not in _rules(misconfig.evaluate({"a.py": a}))


def test_no_framework_detected_means_no_whole_app_finding():
    a = '@app.post("/x")\ndef create():\n    return 1\n'
    r = misconfig.evaluate({"a.py": a})
    assert "unauthenticated_app" not in _rules(r)
    assert r.metrics[misconfig.M_FRAMEWORKS].value == 0.0


def test_frameworks_detected_metric_counts_distinct_frameworks():
    r = misconfig.evaluate({"a.py": "import fastapi\n",
                            "b.py": "from flask import Flask\n"})
    assert r.metrics[misconfig.M_FRAMEWORKS].value == 2.0


def test_a_clean_app_yields_no_findings():
    text = ('from fastapi import FastAPI\n'
            'from fastapi.security import HTTPBearer\n'
            'app = FastAPI()\n'
            '@app.get("/health")\ndef health():\n    return "ok"\n')
    r = misconfig.evaluate({"a.py": text})
    assert r.findings == []
    assert r.collected.state is CollectionState.MEASURED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_misconfig.py -q`
Expected: FAIL — `ImportError: cannot import name 'misconfig'`

- [ ] **Step 3: Write the signal module**

Create `src/sdlc/triage/signals/misconfig.py`:

```python
"""FR-902 framework-default misconfiguration (E-41c).

Framework-scoped and FILE-SHAPED: every rule is a pattern a deterministic
scan can defend. Two boundaries are load-bearing.

`secrets` owns credential MATERIAL; this signal owns generator DEFAULTS. The
`django-insecure-` prefix is written by `django-admin startproject`, so it
belongs here, and `secrets` excludes it so one line never yields two findings.

`unauthenticated_app` is WHOLE-APPLICATION scoped, never per-route. Deciding
whether a particular route should be authenticated is semantic analysis and
belongs to E-46/E-49; a per-route rule computed from decorators would be a
false-positive generator, and a triage report a client cannot trust is worse
than a shorter one.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from ...measurement import Measurement
from ..models import FixClass, SignalResult, TriageFinding

SIGNAL_ID = "misconfig"
VERSION = 1

M_FRAMEWORKS = "frameworks_detected"

_FRAMEWORKS: dict[str, re.Pattern[str]] = {
    "fastapi": re.compile(r"\b(?:from|import)\s+fastapi\b"),
    "flask": re.compile(r"\b(?:from|import)\s+flask\b", re.IGNORECASE),
    "django": re.compile(r"\b(?:from|import)\s+django\b"),
}

# (rule, pattern, severity, fix_class, detail)
_RULES: tuple[tuple[str, re.Pattern[str], str, FixClass, str], ...] = (
    ("permissive_cors",
     re.compile(r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]"
                r"|CORS\([^)]*origins\s*=\s*[\"']\*[\"']"),
     "high", FixClass.MECHANICAL,
     "CORS is configured to accept every origin."),
    ("debug_enabled",
     re.compile(r"^\s*DEBUG\s*=\s*True\b|\.run\([^)]*debug\s*=\s*True",
                re.MULTILINE),
     "high", FixClass.MECHANICAL,
     "Debug mode is enabled in committed configuration. It serves stack "
     "traces to clients and, in Django, an settings dump."),
    ("allowed_hosts_wildcard",
     re.compile(r"ALLOWED_HOSTS\s*=\s*\[\s*[\"']\*[\"']\s*\]"),
     "medium", FixClass.MECHANICAL,
     "ALLOWED_HOSTS accepts every host, which defeats Host-header "
     "validation."),
    ("django_insecure_secret_key",
     re.compile(r"SECRET_KEY\s*=\s*[\"']django-insecure-"),
     "critical", FixClass.JUDGEMENT,
     "The generator's placeholder SECRET_KEY is still in use and committed. "
     "Rotate it; deleting the literal does not invalidate already-signed "
     "cookies."),
    ("world_readable_storage",
     re.compile(r"allow\s+read\s*,\s*write\s*:\s*if\s+true"
                r"|[\"']Principal[\"']\s*:\s*[\"']\*[\"']"),
     "critical", FixClass.MECHANICAL,
     "Storage rules grant read and write to everyone."),
)

# Credentialed wildcard CORS is the one combination worth escalating: it is
# the configuration people reach for when a wildcard alone stopped working.
_CREDENTIALED = re.compile(r"allow_credentials\s*=\s*True"
                           r"|supports_credentials\s*=\s*True")

_AUTH_MARKERS = re.compile(
    r"login_required|LoginRequiredMixin|IsAuthenticated|permission_classes"
    r"|HTTPBearer|OAuth2PasswordBearer|APIKeyHeader|jwt_required"
    r"|AuthenticationMiddleware|flask_login|verify_token|current_user")

_MUTATING_ROUTE = re.compile(
    r"@\w+\.(?:post|put|patch|delete)\s*\("
    r"|methods\s*=\s*\[[^\]]*[\"'](?:POST|PUT|PATCH|DELETE)[\"']")


def detect_frameworks(blobs: Mapping[str, str]) -> set[str]:
    """Which web frameworks the repository imports anywhere."""
    return {name for name, pattern in _FRAMEWORKS.items()
            if any(pattern.search(text) for text in blobs.values())}


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def evaluate(blobs: Mapping[str, str]) -> SignalResult:
    """Every rule against every readable blob, plus the one whole-application
    rule."""
    findings: list[TriageFinding] = []

    for path in sorted(blobs):
        text = blobs[path]
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule, pattern, severity, fix_class, detail in _RULES:
                if not pattern.search(line):
                    continue
                if rule == "permissive_cors" and _CREDENTIALED.search(line):
                    severity = "critical"
                    detail = (detail + " Credentials are allowed alongside "
                                       "the wildcard.")
                findings.append(_finding(rule, severity, detail, fix_class,
                                         path, lineno, line.strip()[:400]))

    frameworks = detect_frameworks(blobs)
    if frameworks:
        has_auth = any(_AUTH_MARKERS.search(t) for t in blobs.values())
        mutating = sorted(p for p, t in blobs.items()
                          if _MUTATING_ROUTE.search(t))
        if mutating and not has_auth:
            findings.append(_finding(
                "unauthenticated_app", "high",
                f"The application ({', '.join(sorted(frameworks))}) declares "
                f"no authentication mechanism anywhere, and defines mutating "
                f"routes in {', '.join(mutating[:5])}. Reported once for the "
                f"repository: deciding which individual route needs auth is "
                f"design work, not a scan.",
                FixClass.STRUCTURAL, mutating[0]))

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={M_FRAMEWORKS: Measurement.measured(float(len(frameworks)))})
```

- [ ] **Step 4: Add the `secrets` exclusion**

In `src/sdlc/triage/signals/secrets.py`, change `VERSION = 1` to `VERSION = 2`, add this constant beside `_looks_random`:

```python
# Owned by the misconfig signal (E-41c), not by this one: `django-insecure-`
# is a value `django-admin startproject` writes, which makes it a framework
# DEFAULT rather than credential MATERIAL. One line must not yield a finding
# from two signals, or the report double-counts its own severity.
_GENERATOR_PLACEHOLDER = re.compile(r"^django-insecure-")
```

and add the guard inside `scan_text`'s generic-assignment branch, changing:

```python
            if (value and _looks_random(value)
                    and _SECRET_KEYWORD_RE.search(ident)):
```

to:

```python
            if (value and _looks_random(value)
                    and _SECRET_KEYWORD_RE.search(ident)
                    and not _GENERATOR_PLACEHOLDER.match(value)):
```

- [ ] **Step 5: Add the activity and register it**

In `src/sdlc/triage/activities.py`, add `misconfig` to the `.signals` import and append:

```python
@activity.defn
async def triage_misconfig(inp: TriageSignalInput) -> SignalResult:
    """FR-902 framework-default misconfiguration (E-41c). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        exts = tuple(found[0].source_extensions) if found else ()
        # Config lives beside source: storage rules and IaC policies are the
        # world_readable_storage rule's whole subject and carry no source
        # extension.
        config_suffixes = (".rules", ".json", ".yml", ".yaml", ".toml",
                           ".ini", ".cfg", ".env")
        wanted = sorted(p for p in paths
                        if (exts and p.endswith(exts))
                        or p.endswith(config_suffixes))
        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))
        return _verified(misconfig.evaluate(blobs), blobs)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage misconfig signal failed: %s", exc)
        return SignalResult(
            signal=misconfig.SIGNAL_ID, version=misconfig.VERSION,
            collected=Measurement.not_collected(
                f"misconfig signal raised: {type(exc).__name__}: {exc}"))
```

In `src/sdlc/triage/registry.py`, add `misconfig` to the import and add:

```python
    misconfig.SIGNAL_ID: SignalSpec(
        id=misconfig.SIGNAL_ID, version=misconfig.VERSION,
        activity="triage_misconfig"),
```

In `src/sdlc/worker.py`, add `triage_misconfig` to the import and the activity list.

- [ ] **Step 6: Run tests to verify they pass**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_misconfig.py tests/test_triage_secrets.py tests/test_triage_registry.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/triage/signals/misconfig.py src/sdlc/triage/signals/secrets.py \
        src/sdlc/triage/activities.py src/sdlc/triage/registry.py \
        src/sdlc/worker.py tests/test_triage_misconfig.py
git commit -m "feat(triage): framework-default misconfiguration signal (E-41c)

Permissive CORS, debug mode, wildcard ALLOWED_HOSTS, the Django placeholder
SECRET_KEY, and world-readable storage rules. unauthenticated_app is
whole-application scoped and fires once per repository: per-route auth
reasoning is semantic analysis (E-46/E-49) and a decorator-derived rule
would be a false-positive generator.

secrets goes to version 2 with a django-insecure- exclusion, so the
placeholder key yields one finding from one signal rather than two."
```

---

### Task 7: `outliers` signal (E-41d)

Spec §8, D14.

**Files:**
- Create: `src/sdlc/triage/signals/outliers.py`
- Modify: `src/sdlc/triage/activities.py`, `src/sdlc/triage/registry.py`, `src/sdlc/worker.py`
- Test: `tests/test_triage_outliers.py`

**Interfaces:**
- Consumes: `gitread.read_tree` (Task 1); `ToolchainAdapter.max_file_loc` / `.max_function_loc` / `.min_clone_loc` / `.source_extensions` / `.function_spans` (Task 2); `activities._verified` (Task 4).
- Produces:
  - `outliers.SIGNAL_ID = "outliers"`, `outliers.VERSION = 1`
  - `outliers.M_MAX_FILE_LOC = "max_file_loc_seen"`, `outliers.M_DUP_RATIO = "duplicated_loc_ratio"`, `outliers.M_FUNCTION_LOC = "max_function_loc_seen"`
  - `outliers.MAX_FILES = 2000`, `outliers.MAX_LINES = 400_000`
  - `normalized_lines(text) -> list[tuple[int, str]]`
  - `clone_groups(blobs, window) -> list[list[tuple[str, int]]]`
  - `evaluate(blobs, toolchain) -> SignalResult`

- [ ] **Step 1: Write the failing test**

Create `tests/test_triage_outliers.py`:

```python
"""FR-902 size and duplication outliers (E-41d)."""
from sdlc.measurement import CollectionState
from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter
from sdlc.triage.models import FixClass
from sdlc.triage.signals import outliers


class _NoParser(ToolchainAdapter):
    """A language with thresholds but no function parser."""
    kind = None
    markers = ()
    source_extensions = (".xx",)
    max_file_loc = 10
    max_function_loc = 5
    min_clone_loc = 3

    def test_cmd(self, coverage: bool = True) -> str:
        return "true"

    def lint_cmd(self) -> str:
        return "true"

    def oracle_test_cmd(self, oracle_path: str, report_out: str) -> str:
        return "true"


def _rules(result):
    return {f.rule for f in result.findings}


# ---- normalization ----------------------------------------------------

def test_normalized_lines_drops_blanks_and_whole_line_comments():
    text = "x = 1\n\n# a comment\n// another\n  y = 2\n"
    assert outliers.normalized_lines(text) == [(1, "x = 1"), (5, "y = 2")]


def test_normalized_lines_keeps_the_original_line_numbers():
    text = "\n\n\nz = 3\n"
    assert outliers.normalized_lines(text) == [(4, "z = 3")]


# ---- size rules -------------------------------------------------------

def test_oversized_file_fires_above_the_adapter_threshold():
    big = "".join(f"x{i} = {i}\n" for i in range(900))
    r = outliers.evaluate({"big.py": big}, PythonToolchain())
    f = next(f for f in r.findings if f.rule == "oversized_file")
    assert f.fix_class is FixClass.STRUCTURAL
    assert f.path == "big.py"


def test_a_file_under_the_threshold_does_not_fire():
    r = outliers.evaluate({"small.py": "x = 1\n"}, PythonToolchain())
    assert "oversized_file" not in _rules(r)


def test_oversized_function_fires_and_names_the_function():
    body = "".join(f"    y{i} = {i}\n" for i in range(150))
    r = outliers.evaluate({"m.py": f"def huge():\n{body}"}, PythonToolchain())
    f = next(f for f in r.findings if f.rule == "oversized_function")
    assert "huge" in f.detail
    assert f.fix_class is FixClass.STRUCTURAL


def test_function_metric_is_not_collected_when_the_language_has_no_parser():
    r = outliers.evaluate({"a.xx": "line\n" * 3}, _NoParser())
    assert r.metrics[outliers.M_FUNCTION_LOC].state \
        is CollectionState.NOT_COLLECTED
    assert "oversized_function" not in _rules(r)
    # The SIGNAL still collected -- it measured file sizes.
    assert r.collected.state is CollectionState.MEASURED


def test_no_toolchain_leaves_both_size_metrics_not_collected():
    r = outliers.evaluate({"a.py": "x = 1\n"}, None)
    assert r.metrics[outliers.M_MAX_FILE_LOC].state \
        is CollectionState.NOT_COLLECTED
    assert r.metrics[outliers.M_FUNCTION_LOC].state \
        is CollectionState.NOT_COLLECTED
    assert r.findings == []


# ---- duplication ------------------------------------------------------

def test_a_clone_across_two_files_is_reported_once():
    block = "".join(f"a{i} = {i}\n" for i in range(40))
    r = outliers.evaluate({"one.py": block, "two.py": block},
                          PythonToolchain())
    dups = [f for f in r.findings if f.rule == "duplicated_block"]
    # ONE finding, not eleven: a 40-line clone scanned with a 30-line window
    # produces eleven overlapping hits, and clone_groups merges them.
    assert len(dups) == 1
    assert dups[0].fix_class is FixClass.JUDGEMENT
    assert "one.py" in dups[0].detail and "two.py" in dups[0].detail


def test_duplication_within_one_file_is_not_a_clone_group():
    block = "".join(f"a{i} = {i}\n" for i in range(40))
    r = outliers.evaluate({"one.py": block + block}, PythonToolchain())
    assert "duplicated_block" not in _rules(r)


def test_a_short_repeated_block_is_below_the_window():
    block = "a = 1\nb = 2\n"
    r = outliers.evaluate({"one.py": block, "two.py": block},
                          PythonToolchain())
    assert "duplicated_block" not in _rules(r)


def test_indentation_only_differences_still_count_as_a_clone():
    block = "".join(f"a{i} = {i}\n" for i in range(40))
    indented = "".join(f"    a{i} = {i}\n" for i in range(40))
    r = outliers.evaluate({"one.py": block, "two.py": indented},
                          PythonToolchain())
    assert "duplicated_block" in _rules(r)


def test_exceeding_the_file_cap_makes_the_ratio_not_collected():
    blobs = {f"f{i}.py": "x = 1\n" for i in range(outliers.MAX_FILES + 1)}
    r = outliers.evaluate(blobs, PythonToolchain())
    assert r.metrics[outliers.M_DUP_RATIO].state \
        is CollectionState.NOT_COLLECTED
    assert "duplicated_block" not in _rules(r)


def test_the_duplication_ratio_is_measured_on_a_clean_repo():
    r = outliers.evaluate({"a.py": "x = 1\n"}, PythonToolchain())
    m = r.metrics[outliers.M_DUP_RATIO]
    assert m.state is CollectionState.MEASURED
    assert m.value == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_outliers.py -q`
Expected: FAIL — `ImportError: cannot import name 'outliers'`

- [ ] **Step 3: Write the signal module**

Create `src/sdlc/triage/signals/outliers.py`:

```python
"""FR-902 size and duplication outliers (E-41d).

ABSOLUTE thresholds from the adapter, never percentiles of the repository's
own distribution (spec D14). Tier 0 asks what state this repository is in,
not which file is worst inside it: a percentile rule always finds 5% of
files, reports nothing on a uniformly bad repository, and yields numbers
that cannot be compared across repositories or across E-44's before/after
delta.

Both size rules are STRUCTURAL. Splitting a file or a function is design
work, and E-44 must not pick it up as a mechanical PR.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from ...measurement import Measurement
from ...toolchain.adapters import ToolchainAdapter
from ..models import FixClass, SignalResult, TriageFinding

SIGNAL_ID = "outliers"
VERSION = 1

M_MAX_FILE_LOC = "max_file_loc_seen"
M_FUNCTION_LOC = "max_function_loc_seen"
M_DUP_RATIO = "duplicated_loc_ratio"

# Bounds on the duplication pass. Exceeding either makes the ratio
# not_collected rather than reporting a partial scan as if it covered the
# tree (spec D16).
MAX_FILES = 2000
MAX_LINES = 400_000

# Whole-line comments in the two syntaxes that cover every language we have
# an adapter for or plan one for. Deliberately crude: this normalizes for
# CLONE COMPARISON, not for parsing, and an inline trailing comment left in
# place simply makes two blocks compare unequal, which is the safe direction.
_COMMENT_LINE = re.compile(r"^\s*(?:#|//|/\*|\*)")


def normalized_lines(text: str) -> list[tuple[int, str]]:
    """(original line number, stripped text) for every line that carries
    content. Blank lines and whole-line comments are dropped; indentation is
    stripped, so a block that was merely re-indented still compares equal."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or _COMMENT_LINE.match(raw):
            continue
        out.append((lineno, line))
    return out


def clone_groups(blobs: Mapping[str, str],
                 window: int) -> list[list[tuple[str, int]]]:
    """Groups of identical `window`-line normalized blocks spanning two or
    more FILES, as [(path, first original line number), ...].

    The window IS the minimum clone length, so a hit is already a clone of at
    least `window` lines and no length-merging step is needed. What DOES need
    merging is overlap: a 40-line duplicate scanned with a 30-line window
    produces eleven consecutive hits, and reporting eleven findings for one
    clone makes the report unreadable. A window whose every hit is the
    one-position continuation of an already-reported group is the same clone.

    Candidates are ordered by position, not by hash, because the continuation
    check depends on having seen the predecessor first.

    Within-file repetition is not reported: a file that repeats itself is
    this signal's oversized_file finding, not a cross-file duplication one.
    """
    index: dict[str, list[tuple[str, int, int]]] = {}
    for path in sorted(blobs):
        lines = normalized_lines(blobs[path])
        for i in range(len(lines) - window + 1):
            chunk = "\n".join(text for _, text in lines[i:i + window])
            key = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
            # (path, normalized index, original line number): the index drives
            # continuation, the line number is what a human is shown.
            index.setdefault(key, []).append((path, i, lines[i][0]))

    candidates: list[list[tuple[str, int, int]]] = []
    for key in sorted(index):
        hits = sorted(index[key])
        if len({path for path, _, _ in hits}) >= 2:
            candidates.append(hits)
    candidates.sort(key=lambda hits: hits[0][:2])

    reported: set[tuple[str, int]] = set()
    groups: list[list[tuple[str, int]]] = []
    for hits in candidates:
        continuation = all((path, i - 1) in reported for path, i, _ in hits)
        reported.update((path, i) for path, i, _ in hits)
        if not continuation:
            groups.append([(path, lineno) for path, _, lineno in hits])
    return groups


def _finding(rule: str, severity: str, detail: str, fix_class: FixClass,
             path: str = "", line: int | None = None,
             evidence: str = "") -> TriageFinding:
    return TriageFinding(signal=SIGNAL_ID, rule=rule, severity=severity,
                         detail=detail, fix_class=fix_class, path=path,
                         line=line, evidence=evidence)


def evaluate(blobs: Mapping[str, str],
             toolchain: ToolchainAdapter | None) -> SignalResult:
    """Size and duplication over source blobs the caller already filtered to
    the adapter's source extensions."""
    findings: list[TriageFinding] = []

    if toolchain is None:
        reason = "no toolchain marker resolved, so no size thresholds apply"
        file_metric = Measurement.not_collected(reason)
        fn_metric = Measurement.not_collected(reason)
    else:
        max_seen = 0
        for path in sorted(blobs):
            loc = len(blobs[path].splitlines())
            max_seen = max(max_seen, loc)
            if toolchain.max_file_loc and loc > toolchain.max_file_loc:
                findings.append(_finding(
                    "oversized_file", "medium",
                    f"{path} is {loc} lines, above the {toolchain.max_file_loc}"
                    f"-line limit for this stack. Splitting it is design work.",
                    FixClass.STRUCTURAL, path))
        file_metric = Measurement.measured(float(max_seen))

        max_fn = 0
        parsed_any = False
        for path in sorted(blobs):
            spans = toolchain.function_spans(blobs[path])
            if spans is None:
                continue
            parsed_any = True
            for name, start, end in spans:
                loc = end - start + 1
                max_fn = max(max_fn, loc)
                if toolchain.max_function_loc \
                        and loc > toolchain.max_function_loc:
                    findings.append(_finding(
                        "oversized_function", "medium",
                        f"{name}() in {path} is {loc} lines, above the "
                        f"{toolchain.max_function_loc}-line limit. Splitting "
                        f"it is design work.",
                        FixClass.STRUCTURAL, path, start))
        fn_metric = (
            Measurement.measured(float(max_fn)) if parsed_any
            else Measurement.not_collected(
                "this toolchain declares no function parser, so function "
                "length was not measured"))

    total_lines = sum(len(t.splitlines()) for t in blobs.values())
    window = toolchain.min_clone_loc if toolchain else 30
    if len(blobs) > MAX_FILES or total_lines > MAX_LINES:
        dup_metric = Measurement.not_collected(
            f"{len(blobs)} files / {total_lines} lines exceeds the "
            f"{MAX_FILES}/{MAX_LINES} duplication cap; a partial scan is not "
            f"a scan")
    else:
        groups = clone_groups(blobs, window)
        duplicated = len(groups) * window
        for group in groups:
            paths = sorted({path for path, _ in group})
            path, line = group[0]
            findings.append(_finding(
                "duplicated_block", "medium",
                f"A {window}-line block is identical across "
                f"{', '.join(paths)}. Deduplicating requires deciding where "
                f"the shared code belongs.",
                FixClass.JUDGEMENT, path, line))
        # An approximation, and deliberately the understating one: merged
        # groups are counted at one window each even when the clone is longer,
        # and total_lines counts raw lines including blanks. A duplication
        # ratio that reads low on a bad repo costs a nudge; one that reads
        # high on a clean repo costs the report's credibility.
        dup_metric = Measurement.measured(
            duplicated / total_lines if total_lines else 0.0)

    return SignalResult(
        signal=SIGNAL_ID, version=VERSION,
        collected=Measurement.measured(float(len(findings))),
        findings=findings,
        metrics={M_MAX_FILE_LOC: file_metric,
                 M_FUNCTION_LOC: fn_metric,
                 M_DUP_RATIO: dup_metric})
```

- [ ] **Step 4: Run the pure-logic tests**

Run: `PYTHONPATH=. uv run pytest tests/test_triage_outliers.py -q`
Expected: PASS (14 tests)

- [ ] **Step 5: Add the activity and register it**

In `src/sdlc/triage/activities.py`, add `outliers` to the `.signals` import and append:

```python
@activity.defn
async def triage_outliers(inp: TriageSignalInput) -> SignalResult:
    """FR-902 size and duplication outliers (E-41d). Never raises."""
    try:
        paths = tracked_paths(inp.repo_dir, inp.commit_sha)
        found = detect_with_marker_from_paths(paths)
        adapter = found[0] if found else None
        exts = tuple(adapter.source_extensions) if adapter else ()
        wanted = sorted(p for p in paths if exts and p.endswith(exts))
        blobs = dict(read_tree(inp.repo_dir, inp.commit_sha, wanted))
        # No evidence quotes: a size or duplication finding cites a file and
        # a line, not a line's text, so _verified would be a no-op.
        return outliers.evaluate(blobs, adapter)
    except Exception as exc:                       # noqa: BLE001
        _log.warning("triage outliers signal failed: %s", exc)
        return SignalResult(
            signal=outliers.SIGNAL_ID, version=outliers.VERSION,
            collected=Measurement.not_collected(
                f"outliers signal raised: {type(exc).__name__}: {exc}"))
```

In `src/sdlc/triage/registry.py`, add `outliers` to the import and add:

```python
    outliers.SIGNAL_ID: SignalSpec(
        id=outliers.SIGNAL_ID, version=outliers.VERSION,
        activity="triage_outliers"),
```

In `src/sdlc/worker.py`, add `triage_outliers` to the import and the activity list.

- [ ] **Step 6: Strengthen the registry test**

Append to `tests/test_triage_registry.py`:

```python
def test_all_seven_signal_families_are_registered():
    # FR-902 names seven families. E-41 shipped three; E-41a-d added four.
    from sdlc.triage.registry import SIGNALS
    assert set(SIGNALS) == {"baseline", "secrets", "build_probe",
                            "dependencies", "scaffold", "misconfig",
                            "outliers"}


def test_every_registered_activity_is_registered_on_the_worker():
    import sdlc.triage.activities as acts
    from sdlc.triage.registry import SIGNALS
    for spec in SIGNALS.values():
        assert hasattr(acts, spec.activity), spec.activity


def test_baseline_and_secrets_carry_their_bumped_versions():
    from sdlc.triage.registry import SIGNALS
    assert SIGNALS["baseline"].version == 2      # dropped M_STRUCTURE (D12)
    assert SIGNALS["secrets"].version == 2       # django-insecure- exclusion
```

- [ ] **Step 7: Run the whole triage suite**

Run: `PYTHONPATH=. uv run pytest tests/ -k triage -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/triage/signals/outliers.py src/sdlc/triage/activities.py \
        src/sdlc/triage/registry.py src/sdlc/worker.py \
        tests/test_triage_outliers.py tests/test_triage_registry.py
git commit -m "feat(triage): size and duplication outlier signal (E-41d)

Absolute adapter-supplied thresholds rather than percentiles (spec D14), so
a repository of uniformly enormous files reports every one of them and the
numbers stay comparable across E-44's before/after delta. Both size rules
are STRUCTURAL -- splitting is design work, not a mechanical PR.

Duplication uses a min_clone_loc-line sliding window, so a hit is already a
clone of at least that length. Exceeding the file or line cap makes the
ratio not_collected rather than reporting a partial scan as a whole one.

FR-902 is now seven of seven signal families."
```

---

### Task 8: Roadmap and requirement-doc consequences

Spec §12. The tracker's own claims about this area are now stale in four specific places; leaving them is the drift the roadmap's method exists to prevent.

**Files:**
- Modify: `ROADMAP.md` (§1 stage 12 note is unaffected; §2 FR-902 and FR-703; §10 E-41 and E-41a–d)
- Modify: `ARCHITECTURE.md` (ADR-15's adapter description)

- [ ] **Step 1: Update FR-902 in ROADMAP.md §2**

Replace the FR-902 entry:

```markdown
- [x] **FR-902** hygiene signal set via FR-108 adapters, one implementation
  per signal — **seven of seven landed**: build probe, secrets (incl.
  client-bundle reachability), baseline practice (E-41), plus dependency
  health, generator-scaffold and dead code, framework-default misconfig, and
  size/duplication outliers (E-41a–d, 2026-08-08).
```

- [ ] **Step 2: Update §10's E-41 entries**

Change E-41's `[ ] ⚠️` to `[x]`, drop the "Remaining four families are E-41a–d" clause, and replace the four sub-items with:

```markdown
- [x] **E-41a** dependency health — unpinned / duplicated / known-vulnerable /
  unused direct dependencies behind the FR-108 adapter's `manifests` and
  `ecosystem`. The advisory database is an `AdvisorySource` seam whose
  default collects nothing: a lookup that did not happen reports
  `not_collected`, never zero vulnerabilities. `OsvAdvisorySource` is the one
  reference implementation, opt-in and off by default.
- [x] **E-41b** dead and generator-scaffold code, and **the new owner of
  `structure_discernible`** — `compute_readiness` admits exactly one signal
  per readiness key, so the dimension moved off `baseline` (now v2) rather
  than being reported twice. Detection is fingerprint-first with git history
  corroborating severity only: history alone misfires hardest on the
  single-initial-commit repositories Tier 0 targets. **The floor is raised,
  not removed** — a repository that is entirely untouched output of a
  generator we hold no fingerprint for still passes the dimension.
- [x] **E-41c** framework-default misconfiguration — permissive CORS, debug
  mode, wildcard `ALLOWED_HOSTS`, the Django placeholder `SECRET_KEY`, and
  world-readable storage rules. `unauthenticated_app` is whole-application
  scoped and fires once per repository; per-route auth reasoning is E-46/E-49.
  `secrets` (now v2) excludes the Django placeholder, so one line yields one
  finding from one signal.
- [x] **E-41d** size and duplication outliers — absolute adapter-supplied
  thresholds, not percentiles, so the numbers survive E-44's before/after
  delta. Both size rules are STRUCTURAL.
```

- [ ] **Step 3: Record the new egress on FR-703**

In ROADMAP.md §2, append to the FR-703 entry:

```markdown
  *2026-08-08 (E-41a):* `OsvAdvisorySource` adds the pipeline's **second**
  outbound egress after research (FR-107) — declared, opt-in, and off by
  default. It is still env/tool-level only; E-21 remains the network tier.
```

- [ ] **Step 4: Update ADR-15's description in ARCHITECTURE.md**

Find ADR-15's entry and append:

```markdown
  *2026-08-08 (E-41a–d):* the adapter gains its first pure per-language
  **parser** member, `function_spans`, beside its command strings. It runs no
  subprocess and touches no filesystem, so ADR-15's purity rule holds; it is
  the same kind of member as `classify_test_exit` — a per-language
  interpretation rather than a command. Framework fingerprints and
  misconfiguration rules deliberately do **not** live here: one language
  serves many frameworks.
```

- [ ] **Step 5: Verify nothing else claims three-of-seven**

Run: `PYTHONPATH=. uv run rg -n "three of seven|3 of 7|three signals" ROADMAP.md ARCHITECTURE.md PRD.md docs/`
Expected: no stale hits outside the E-41 spec's own historical record (the spec describes what *that* increment built and stays accurate).

- [ ] **Step 6: Run the full fast suite**

Run: `PYTHONPATH=. uv run pytest -q`
Expected: PASS, no new failures. (Note: on a machine whose shell has no valid stdin handle, subprocess-spawning tests fail at `DuplicateHandle` with `WinError 6` before reaching any assertion — that is environmental, not a regression. Run in a normal terminal.)

- [ ] **Step 7: Commit**

```bash
git add ROADMAP.md ARCHITECTURE.md
git commit -m "docs: FR-902 is seven of seven signal families (E-41a-d)

Records the four consequences the tracker's method requires: FR-902 closes,
E-41a-d close, FR-703 gains a second declared opt-in egress, and ADR-15
gains its first pure per-language parser member. E-41b's 'deliberate floor'
note is rewritten rather than deleted -- fingerprinting raises the floor, an
unfingerprinted generator still passes."
```

---

## Notes for the implementer

**The two places this plan is most likely to bite:**

1. **Task 1's stream synchronisation.** `git cat-file --batch` answers a missing path with a single line and no payload. If you consume a payload that is not there, every subsequent read returns the tail of the previous object and the whole signal set produces plausible nonsense. `test_the_stream_stays_in_sync_after_a_missing_path` is the guard; do not skip it.

2. **Task 5's readiness-key migration.** `compute_readiness` raises when two signals report `M_STRUCTURE`, so a half-applied migration fails loudly — but the *other* half-application (baseline drops it, scaffold never adds it) fails silently by forcing every verdict to `INDETERMINATE`. Both directions are covered by `test_baseline_no_longer_reports_structure` and `test_two_signals_reporting_structure_still_raises`; run them together.

**The rule most likely to be got wrong on review:** `unused_dependency`'s alias table cannot be complete, which is *why* the rule is `low` severity, `MECHANICAL`, and influences no readiness dimension. If a reviewer proposes raising its severity, the table has to grow first.
