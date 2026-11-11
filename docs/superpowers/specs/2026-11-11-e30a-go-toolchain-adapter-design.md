# E-30a — Go `ToolchainAdapter` (design)

**Date:** 2026-11-11
**Satisfies:** E-30a (`docs/roadmap/filesystem-first.md` §9.8), FR-108 (second
adapter; validates the abstraction on a non-Python language)
**Related:** ADR-15, E-30 (Python reference), diff-scoped gates
(`2026-09-11-diff-scoped-gates-design.md`, DS5/DS6), E-41 (triage fields)
**Status:** approved in conversation 2026-11-11 (lint posture: `go vet`, the
user's call, overriding the roadmap's corpus-first ordering for E-30a/b/c)

## Intent and why

The deterministic quality gate must grade whatever language was actually
built (FR-108). Today only Python resolves: `TOOLCHAINS` has one entry, so a
produced repo with a `go.mod` marker degrades to the contract-lint fallback.
E-30a adds the second adapter — same shape as the Python reference — which is
also the first real test of the adapter abstraction on a language whose test
tooling is package-shaped, not file-shaped.

## Goals

- `GoToolchain` implementing the **full post-2026-09-11 contract**: scoped
  lint (`lint_json_cmd`/`parse_lint`, policy globs, suppression pattern),
  scoped tests (`integration_test_cmd` no-early-stop + JUnit, collect /
  selected re-runs), `oracle_test_cmd`, plus the E-41 triage fields.
- Marker resolution: `go.mod` → the adapter, via the existing registry (all
  three `detect*` forms unchanged).
- Fail-closed: absent converters (`gocover-cobertura`, `go-junit-report`)
  produce `NOT_COLLECTED`, never a vacuous pass.
- Pure unit tests over command strings and parser fixtures — no Go toolchain
  in CI (none is installed here; verified).

## Non-goals

- No benchmark case in a Go language (E-34 authoring is separate).
- No `golangci-lint` (rejected in conversation: an external binary whose
  absence would fail the absolute lint check of every Go run).
- No Go source parser — `function_spans` stays `None` (metric reads
  `not_collected`, never a fake zero).
- No change to `gate.py`, workflow code, or the Python adapter's behavior.

## Anti-goals

- Vacuous passes: a missing tool must read as collection failure, not as
  "clean". A pre-existing failing Go test must never be attributed to the
  change (false absolute block), and an introduced one must never be excused
  as pre-existing (false pass).

## Approaches considered

1. **Lint: `go vet -json` floor (chosen).** Ships with the Go toolchain, so
   lint collection never fails because a linter is missing. Coarser rules
   than golangci-lint; no inline-suppression syntax (`suppression_pattern
   = ""`, honest). Trade accepted in conversation.
2. **Lint: `golangci-lint --out-format=json --issues-exit-code=0` (rejected).**
   Richer findings, but an external binary; absent → `NOT_COLLECTED` → every
   Go merge blocked at an absolute check until it is installed.
3. **Test-id forms.** (a) *File-shaped* `pkg/x_test.go::TestX` — impossible:
   Go tooling cannot attribute a test to its file (JUnit carries only the
   package import path). (b) *Directory-shaped* — still fails the base
   locator check and needs dir↔import-path math. (c) *Import-path-shaped*
   `example.com/pkg::TestX` (chosen): natural from both the JUnit classname
   and `go test -list` output, and `go test` accepts import paths as package
   arguments directly, so collect/selected commands need no path mapping at
   all. Requires the locator hook below.

## Decisions (how it gets made)

- **Node ids:** `<import-path>::<TestName>` everywhere (head JUnit classname,
  collected ids, selected re-runs).
- **Commands:**
  - `test_cmd(coverage=False)` → `go test ./...`; with coverage →
    `go test ./... -coverprofile=cover.out -covermode=atomic` piped through
    `gocover-cobertura` into `coverage.xml`.
  - `integration_test_cmd` → `go test -v ./...` (already no-early-stop:
    packages run in parallel, one failing package does not stop the others)
    piped through `go-junit-report` into the JUnit path; coverage variant
    appends the Cobertura conversion.
  - `lint_cmd` → `go vet ./...`; `lint_json_cmd` → `go vet -json ./...`.
  - `oracle_test_cmd` → `go test -v <path>/...` piped through
    `go-junit-report`.
  - `build_cmd` → `go build ./...` — the first non-`None` build command; the
    triage consumer (`triage/activities.py:469`) already handles it.
  - `install_cmd` → `go mod download` (module cache, does not mutate the
    tree under audit).
- **`parse_lint`:** exit 0 = clean (empty stream → `[]`); exit 1 = findings
  (parse the concatenated per-package JSON objects via incremental decode);
  any other exit = `None` (tool failure). The scoped seam passes the exit
  code in (`scoping.py:33-36`) — no `--exit-zero` trick exists for vet and
  none is needed. Rule = diagnostic `category` (else `"vet"`); path =
  `location.file.filename` relativized against root; row = `location.line`.
- **`classify_test_exit`:** 0/1 → `ran` (Go's 1 is "tests failed", not "did
  not run"); anything else → `failed_to_run`. Go has no "no tests collected"
  exit — a package without tests reports `no test files` and exits 0.
- **Triage fields (E-41):** `markers=("go.mod",)`, `lockfiles=("go.sum",)`,
  `manifests=("go.mod",)`, `ecosystem="Go"`, `source_extensions=(".go",)`,
  `test_globs=("*_test.go",)`, `max_file_loc=800`, `max_function_loc=100`
  (same ceilings as Python — the numbers are policy, not language facts).
- **`parse_collected_ids`:** `go test -list '.*' <pkgs>` output — test names
  grouped under their package's `ok <import-path>` line; id =
  `<import-path>::<name>`.
- **`selected_tests_cmd`:** group ids by package, one
  `go test -v -run '^(A|B)$' <pkgs> | go-junit-report > out` per chunk,
  `shell_safe`-checked like the Python adapter.

## The one seam extension: `base_locator_exists`

DS6 attribution (`scoping.py:208-237`) pre-filters a failed head id by
checking its part before `::` with `os.path.isfile` at the base worktree —
a Python-shaped assumption. Import-path ids would fail it and every failing
Go test would misread as introduced (false absolute block).

- `ToolchainAdapter.base_locator_exists(root, locator) -> bool`, **default:
  exactly today's `os.path.isfile(os.path.join(root, locator))`** —
  Python's behavior is bit-identical.
- `GoToolchain` overrides it: read `<root>/go.mod`, strip the `module` prefix
  from the locator, `os.path.isdir` the remainder. Unparseable `go.mod` →
  `False` (the id goes to the collect step's authoritative judgment anyway —
  the pre-filter is an optimization, collect/re-run is the mechanism).
- `scoping.py:217` calls the hook instead of the bare `isfile`. This is the
  `classify_test_exit` precedent — a per-language *interpretation* member on
  the adapter, not per-language branching in the seam.

This is the only shared-code change; `gate.py` and workflow code are
untouched, per FR-108 and the approved non-goals.

## Coverage degradation (recorded behavior)

If `gocover-cobertura` is absent, the JUnit pipe still lands (tests grade
absolutely, `build_integration_green` real) and only `coverage.xml` is
missing — the advisory coverage check then reads its own `NOT_COLLECTED`
reason. Degrading an absolute check is impossible by construction here:
test collection failures still fail `NOT_COLLECTED` via the JUnit read.

## Already satisfied (verified, no work needed)

- Oracle node ids: `grade_testcases_from_junit` already prefers `file` then
  falls back to `classname::name` (`benchmarks/oracle.py:105-110`).
- Security: semgrep→SARIF is language-agnostic (E-30's format decision (b)).
- `build_cmd` consumer exists (`triage/activities.py:469`).

## Tests (pure, fixture-driven — no Go toolchain required)

New `tests/test_toolchain_go.py` + extension of the scoped-contract tests:
- marker/registry resolution; triage fields; `install_cmd`; `build_cmd`
- exact command strings for every `*_cmd` member, both coverage branches
- `parse_lint`: findings fixture (multi-package JSON stream), clean-empty →
  `[]`, garbage stdout → `None`, non-0/1 exit → `None`
- `parse_collected_ids` fixture (names + `ok` lines, interleaved packages)
- `selected_tests_cmd`: package grouping, regex alternation, `shell_safe`
  refusal
- `classify_test_exit` mapping
- `base_locator_exists`: default (Python, file), Go (module prefix strip,
  dir check, unparseable go.mod) — with fixture `go.mod` files in tmp dirs
- seam: `scoped_tests` pre-filter routes through the hook (default path
  unchanged for Python — existing tests must stay green untouched)

## Tracker updates (same change)

- `docs/roadmap/filesystem-first.md` E-30a → `[x]` with landed note.
- `ROADMAP.md` FR-108 note: E-30a implements the 2026-09-11 contract; b/c
  remain open.
