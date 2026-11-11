# E-30a Go ToolchainAdapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `GoToolchain`, the second `ToolchainAdapter`, so the deterministic gate grades a `go.mod` repo end-to-end without gate/workflow changes.

**Architecture:** One adapter class in `src/sdlc/toolchain/adapters.py` beside the Python reference, plus one default-preserving interpretation hook (`base_locator_exists`) that lets the DS6 attribution pre-filter accept import-path-keyed test ids. Everything else is adapter-local; parsers are pure functions over fixture text, tested without a Go toolchain.

**Tech Stack:** Python 3.13, stdlib `json`/`re`/`os` only. External Go tools are *invoked by command string only* (`go`, `go-junit-report`, `gocover-cobertura`) and never required in CI.

**Spec:** `docs/superpowers/specs/2026-11-11-e30a-go-toolchain-adapter-design.md`

## Global Constraints

- `gate.py`, workflow code, and the Python adapter's behavior stay untouched; `tests/test_toolchain_scoped_contract.py` and `tests/test_toolchain_adapters.py` pass unchanged.
- The adapter is pure: no subprocess; filesystem reads only in `base_locator_exists` (the `go.mod` lookup, spec-sanctioned) and relpath math in `parse_lint`.
- All quoting in emitted commands is double quotes (`cmd.exe`- and POSIX-compatible; single quotes are not). Pipes, `&&`, `<`, `>` are the only shell syntax — all valid in `cmd.exe` (workers run on Windows; `ID_CHUNK` comment in `scoping.py:117`).
- Missing external tools fail closed: a failed command yields `NOT_COLLECTED`, never a vacuous pass.
- `ruff check`, `ruff format`, `mypy`, `scripts/check_file_size.py` clean; fast pytest tier green.
- Test-fixture convention DS9: no literal scanner-trigger text in test source; assemble at runtime where needed.

## Review Focus

1. `go vet` exit 1 with empty stdout claims findings but printed none → `parse_lint` returns `None`, not `[]` (Task 4).
2. Multi-package `go vet -json` stream (concatenated objects, not an array) → every finding attributed to the right file/line (Task 4).
3. `go.mod` module line with trailing comment or quoted path → still parsed; unparseable → `False` (Task 6).
4. Locator under a *nested* `go.mod` (submodule) → `False`, deferring to the authoritative collect step (Task 6).
5. `go test -list` output where a package prints `[no test files]` → contributes zero ids (Task 5).

---

### Task 1: `base_locator_exists` hook on the ABC + seam call

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py` (ABC, after `classify_test_exit`)
- Modify: `src/sdlc/stages/merge/scoping.py:217`
- Test: `tests/test_toolchain_base_locator.py` (new)

**Interfaces:**
- Produces: `ToolchainAdapter.base_locator_exists(self, root: str, locator: str) -> bool`; default body exactly `os.path.isfile(os.path.join(root, locator))`. Consumed by `scoped_tests` in Task 6's Go override.

- [ ] **Step 1: Write the failing tests**

```python
"""base_locator_exists: per-language base locator judgment (DS6 pre-filter)."""
import inspect

from sdlc.toolchain.adapters import PythonToolchain, ToolchainAdapter


def test_default_is_isfile(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "a_test.py").write_text("", encoding="utf-8")
    py = PythonToolchain()
    assert py.base_locator_exists(str(tmp_path), "a_test.py") is True
    assert py.base_locator_exists(str(tmp_path), "pkg") is False      # dir is not a file
    assert py.base_locator_exists(str(tmp_path), "nope.py") is False


def test_seam_routes_through_the_hook():
    src = inspect.getsource(__import__("sdlc.stages.merge.scoping", fromlist=["x"]))
    assert "adapter.base_locator_exists(" in src
    assert "os.path.isfile(os.path.join(base_wt, file))" not in src
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_toolchain_base_locator.py -q` → `AttributeError: ... no attribute 'base_locator_exists'`

- [ ] **Step 3: Implement** the default method on `ToolchainAdapter` (docstring: Python-shaped default; Go overrides; the pre-filter is an optimization — collect/re-run stays the authoritative attribution) and change `scoping.py:217` from `os.path.isfile(os.path.join(base_wt, file))` to `adapter.base_locator_exists(base_wt, file)`.

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/test_toolchain_base_locator.py tests/merge/ -q`

- [ ] **Step 5: Commit** — `git commit -m "feat(toolchain): base_locator_exists hook, default preserves isfile"`

### Task 2: `GoToolchain` identity, triage fields, build/install, exit classification

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py` (`ToolchainKind.GO`, `GoToolchain`, `TOOLCHAINS` — Python first, Go second, so a repo with both markers keeps resolving Python)
- Test: `tests/test_toolchain_go.py` (new)

**Interfaces:**
- Produces: `ToolchainKind.GO = "go"`; `GoToolchain` with `markers == ("go.mod",)`, `lockfiles == ("go.sum",)`, `manifests == ("go.mod",)`, `ecosystem == "Go"`, `source_extensions == (".go",)`, `test_globs == ("*_test.go",)`, `max_file_loc == 800`, `max_function_loc == 100`, `function_spans(text) is None` (inherited), `install_cmd("go.mod") == "go mod download"`, `build_cmd() == "go build ./..."`, `classify_test_exit: {0,1}→"ran", else→"failed_to_run"` (no `no_tests` exit in Go).

- [ ] **Step 1: Write failing tests** — detect-by-`go.mod` (tmp_path fixture), registry contains GO with those exact markers/fields, `detect` still prefers Python when both `pyproject.toml` and `go.mod` exist, the three value tests above.
- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/test_toolchain_go.py -q` → `AttributeError: GO`
- [ ] **Step 3: Implement** the class per Interfaces (docstring: second adapter, E-30a; `function_spans` deliberately inherited-`None`).
- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/test_toolchain_go.py tests/test_toolchain_adapters.py -q`
- [ ] **Step 5: Commit** — `git commit -m "feat(toolchain): GoToolchain identity and triage fields (E-30a)"`

### Task 3: Go command members

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py` (`GoToolchain` methods)
- Test: `tests/test_toolchain_go.py`

**Interfaces:**
- Produces exact strings (double-quoted args; `junit_out`/`report_out` interpolated verbatim after a `shell_safe` guard raising `ValueError`):
  - `test_cmd(True)` → `go test ./... -coverprofile=cover.out -covermode=atomic && gocover-cobertura < cover.out > coverage.xml`
  - `test_cmd(False)` → `go test ./...`
  - `lint_cmd()` → `go vet ./...`
  - `lint_json_cmd()` → `go vet -json ./...`
  - `integration_test_cmd(j, True)` → `go test -v ./... -coverprofile=cover.out -covermode=atomic | go-junit-report > {j} && gocover-cobertura < cover.out > coverage.xml`
  - `integration_test_cmd(j, False)` → `go test -v ./... | go-junit-report > {j}`
  - `oracle_test_cmd(p, r)` → `go test -v ./{p}/... | go-junit-report > {r}`
- Docstring records exit semantics: the pipe's exit is `go-junit-report`'s (0); outcomes come from the JUnit file, `_head_run` already treats it as ground truth.

- [ ] **Step 1: Write failing tests** asserting each exact string (both coverage branches) and the `shell_safe` refusal on `oracle_test_cmd("a;rm", "r.xml")`.
- [ ] **Step 2: Run, expect FAIL** (missing attributes).
- [ ] **Step 3: Implement** per Interfaces; reuse the Python adapter's `shell_safe` guard idiom.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(toolchain): Go command members (vet/test/junit/coverage pipes)"`

### Task 4: `parse_lint` — the `go vet -json` stream

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py`
- Test: `tests/test_toolchain_go.py`

**Interfaces:**
- Consumes: `normalize_path` (already imported in `adapters.py`).
- Produces: `parse_lint(code, out, root)` → `None` on `code not in (0, 1)`; `None` on code 1 with empty/unparseable stdout; `[]` on code 0 with empty stdout; else rows `(rule, posix_rel_path, line)` sorted, `rule = diagnostic.get("category") or "vet"`, path via `os.path.relpath(location["file"]["filename"], root)` + `normalize_path`, row = `location["line"]`. Parse concatenated JSON objects with `json.JSONDecoder().raw_decode` in a loop (vet streams one object per package — never a JSON array).

- [ ] **Step 1: Write failing tests** — Review Focus cases 1–2: a two-package concatenated-object fixture (one diagnostic with empty category → `"vet"`), clean-empty `[]`, code-2 → `None`, code-1-empty → `None`, trailing garbage after valid objects → `None`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(toolchain): parse go vet -json streams, fail closed on ambiguity"`

### Task 5: collect / selected test-id round-trip

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py`
- Test: `tests/test_toolchain_go.py`

**Interfaces:**
- Produces:
  - `collect_ids_cmd(pkgs)` → `go test -list ".*" "p1" "p2"` (`shell_safe` each, raise on unsafe)
  - `parse_collected_ids(out)` → ids `"<import-path>::<TestName>"`; names accumulate since the last package line; a package line is `ok\t<import-path>\t…` (emit+reset) or `?\t<import-path>\t[no test files]` (discard+reset); name lines match `^Test\w*$`.
  - `selected_tests_cmd(ids, junit)` → group ids by package, `go test -v -run "^(N1|N2)$" "pkg1" "pkg2" | go-junit-report > {junit}` — names `re.escape`d, alternation sorted for determinism, packages deduped and sorted, `shell_safe` each id.

- [ ] **Step 1: Write failing tests** — fixture with interleaved `ok`/`?` lines (Review Focus 5), unsafe-id refusal, package grouping + regex alternation string exactness.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run, expect PASS** — and `uv run pytest tests/test_scoped_tests.py -q` (seam consumers unaffected).
- [ ] **Step 5: Commit** — `git commit -m "feat(toolchain): Go test-id collect and selected re-run round-trip"`

### Task 6: `GoToolchain.base_locator_exists` override

**Files:**
- Modify: `src/sdlc/toolchain/adapters.py`
- Test: `tests/test_toolchain_base_locator.py`

**Interfaces:**
- Consumes: Task 1's hook signature.
- Produces: read `<root>/go.mod`, first `module` directive (tolerate trailing comments; strip surrounding quotes); locator under it (`module + "/"` prefix) → `os.path.isdir(join(root, rel))`; missing `go.mod`, unparseable module line, or a locator outside the module (nested `go.mod`) → `False`.

- [ ] **Step 1: Write failing tests** — tmp_path with `go.mod` (`module example.com/foo`) and `internal/store/` dir: `"example.com/foo/internal/store"` → `True`; bare `"example.com/foo"` (module root) → `True`; sibling `"other.io/x"` → `False`; `go.mod` with `module example.com/foo // v2` → still `True`; no `go.mod` → `False` (Review Focus 3–4).
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** per Interfaces.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(toolchain): Go base locator resolves import paths via go.mod"`

### Task 7: Full verification + tracker close-out

**Files:**
- Modify: `docs/roadmap/filesystem-first.md` (E-30a row), `ROADMAP.md` (FR-108 note)

- [ ] **Step 1: Verify** — `uv run pytest -q` (fast tier), `uv run pytest -q tests/merge/ tests/test_toolchain_go.py tests/test_toolchain_base_locator.py tests/test_scoped_lint.py tests/test_scoped_tests.py`, `ruff check .`, `ruff format --check .`, `mypy`, `uv run python scripts/check_file_size.py`. All green before touching trackers.
- [ ] **Step 2: Trackers** — E-30a → `[x]` with a landed note (adapter + `base_locator_exists` seam hook; fixture-tested, no Go toolchain in CI; first real `build_cmd`); FR-108's roadmap row: E-30a implements the 2026-09-11 contract, E-30b/c remain.
- [ ] **Step 3: Commit** — `git commit -m "docs: close E-30a — Go adapter landed"`
