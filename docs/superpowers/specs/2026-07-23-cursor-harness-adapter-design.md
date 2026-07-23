# E-35 — `cursor` harness adapter (design)

| | |
|---|---|
| Date | 2026-07-23 |
| Roadmap item | E-35 (§9.8), folds the intent of E-24 |
| Anchors | FR-203 (harness-agnostic adapters), ADR-2/ADR-16, E-38 (session capture), E-33 (economics fields) |
| Depends on | E-33 (landed — cost/token fields on `HarnessRunResult`), E-38 (landed — `HarnessSession` capture) |
| Status | Approved for planning |

## 1. Why

The harness axis currently has two points: `claude -p` (`ClaudeCodeHarness`) and
`opencode run` (`OpenCodeHarness`). E-35 adds a third — `cursor-agent` — so the
benchmark can measure **`claude` vs `opencode` vs `cursor` through the
`DeterministicQualityGate` on the held-out oracles (E-31)**, a comparison no
external leaderboard provides. Value is *decorrelated harness points measured on
the same gate*, not "cursor in the abstract".

E-35 also folds **the intent of E-24**: pin each harness CLI's version and check
it at boot, so eve's dependency-drift failure mode (a CLI silently upgrading and
breaking the adapter's `parse`) becomes visible instead of silent.

## 2. Scope

### In scope
- `HarnessKind.CURSOR` enum value.
- `CursorHarness(CodingHarness)` in `src/sdlc/harness/adapters.py`
  (`build_cmd` / `parse` / `normalise_session`), registered in `HARNESSES`.
- Boot-time version-pin check for **all three** harnesses, warn-on-drift,
  skip-when-CLI-absent.
- Unit tests mirroring `tests/test_harness_parse.py`.

### Explicitly out of scope (YAGNI)
- **No live `cursor-agent` run**, no CLI install, no auth wiring. The CLI is not
  present in this environment (`cursor-agent` not on PATH, no `CURSOR_API_KEY`),
  so — exactly as with the existing two adapters — the deliverable is the adapter
  plus unit tests against captured/documented output shapes. The live axis is a
  flagged follow-on.
- **Not** enabling cursor on any existing benchmark case's `harnesses` list. The
  adapter is made *available*/selectable only. Turning it on for a case is a
  live-run decision for when the CLI exists.
- **No changes** to `digest_of` / `scrub_session` / session capture — they are
  already harness-agnostic (they consume canonical `SessionEvent`s).
- No handling for Cursor's opaque underlying model beyond the documented caveat
  in §6.

## 3. The seam this plugs into (verified against current code)

- `CodingHarness` (ABC) declares `build_cmd`, `parse`, and a default
  `normalise_session`. `run()` (shared) spawns the subprocess, pumps
  stdout/stderr, calls `parse`, and stashes raw stdout on `_raw_stdout`
  (`PrivateAttr`) for activity-side capture.
- `HARNESSES: dict[HarnessKind, CodingHarness]` is the registry; `run_coding_task`
  does `HARNESSES[inp.harness]` — generic over `HarnessKind`.
- `benchmarks/matrix.py::expand_matrix` iterates `spec.harnesses` — generic;
  adding cursor to a case's list is all it takes to sweep it (deliberately not
  done this increment).
- `normalise_session` → `harness/session.py::digest_of` maps `SessionEvent.kind`
  (`file_read`/`file_write`/`command`/`model_turn`/`compaction`/…) into the
  BENCHMARK §4.3 waste aggregates. **Harness-agnostic**: a correct Cursor
  `normalise_session` needs only emit the right `kind`/`tool`/`target`/`exit_code`.
- Boot: `worker.py::main()` calls `validate_registry(load_registry())` first.
  The version check goes immediately after it.

## 4. `CursorHarness`

`cursor-agent` deliberately models its non-interactive output on Claude Code's
Agent SDK stream-json: a `system`/init event, `assistant`/`user` message events
carrying content blocks (`text`, `tool_use`, `tool_result`), and a final
`result` event with `session_id`, usage, and (assumed) cost. The adapter is
therefore structurally a near-twin of `ClaudeCodeHarness`.

### `build_cmd(req)`
```
cursor-agent -p <prompt>
  --output-format stream-json
  [--model <model>]
  [--resume <session_id>]
  --force              # headless auto-approve (≈ claude --permission-mode
                       #   acceptEdits / opencode --auto)
  <extra_args...>
```

### `parse(stdout, exit_code) -> HarnessRunResult`
- Walk NDJSON lines; keep the `type == "result"` event.
- From it: `session_id`, `cost_usd = total_cost_usd`, `summary = result`,
  `input_tokens`/`output_tokens` from `usage`.
- No result event → `_log.warning` + raw-stdout fallback as `summary`
  (same defensive shape as the other two adapters).

### `normalise_session(stdout) -> HarnessSession`
- `system` init event → `model`.
- `assistant`/`user` message content blocks:
  - `text` → `SessionEvent(kind="model_turn", text=...)`
  - `tool_use` → `file_read` / `file_write` / `command` via `_TOOL_MAP`,
    falling back to `tool_call` for unmapped tools.
  - `tool_result` → `SessionEvent(kind="tool_result", exit_code=1 if error, text=...)`
- `result` event → tokens/cost onto the `HarnessSession`.
- `_TOOL_MAP` (Cursor tool name → canonical kind + target field), e.g.
  `read_file`→(`file_read`,`path`), `edit_file`/`write`→(`file_write`,`path`),
  `run_terminal_cmd`/`shell`→(`command`,`command`). **See §5.**

### Context windows
`CONTEXT_WINDOWS` already substring-matches `sonnet`/`opus`/`gpt-5`/`glm`/`haiku`,
covering Cursor's typical `--model` names. `auto` → `None` → falls back to the
resume counter. No change required.

## 5. Documented assumptions (verify before trusting the live axis)

Because the adapter is written against Cursor's *documented* schema, not a
captured live transcript, the spec names the fields to confirm against real
`cursor-agent --output-format stream-json` output before the live cursor axis is
trusted:

- `_TOOL_MAP` keys (Cursor's exact tool names).
- `usage` token key names (`input_tokens`/`output_tokens` vs other spellings).
- Whether Cursor emits `total_cost_usd` at all. **If it does not, cursor cells
  are quality-only** — `cost_usd`/tokens read `None`, which is exactly the
  "quality-only until the adapter fills the economics fields" state E-35
  predicts. The gate grade (E-31 oracles) is unaffected either way.

These are called out here and as code comments so a later live-capture pass has
a checklist, not a re-reading of the whole adapter.

## 6. ADR-6 opacity caveat (documented, not built)

Cursor's declared `--model` may be backed by an opaque underlying model.
`model_family()` (loader) operates on the *declared* string, so if a project
sets cursor as the production `dev` role, the anti-collusion check
(`reviewer` family ≠ `dev` family) constrains the declared family only. This is
the same latent property as any harness with an opaque model; it is flagged, not
solved, in this increment. E-35's primary use is the benchmark *harness axis*
(`BenchmarkCell.harness`), where the ADR-6 rule enforced by `expand_matrix` is on
*author vs judge model families*, not on the harness.

## 7. Version pin at boot (folded E-24)

- Add `expected_version: str | None = None` and `version_cmd` (default
  `[<cli>, "--version"]`) to `CodingHarness` (overridable per adapter).
- New `check_harness_versions(harnesses=HARNESSES)` in `adapters.py`:
  - For each adapter declaring a pin: `shutil.which(cli)`.
    - **Absent → skip** (debug log). This is the CI/fakes case and must be quiet.
    - **Present →** run `version_cmd`, parse the leading version token, compare:
      - **mismatch → `_log.warning`** (drift is visible).
      - match → debug log.
  - **Never raises** — a patch bump must not brick the worker (warn-on-drift,
    per the approved decision).
- Called from `worker.py::main()` immediately after `validate_registry(...)`.
- Seed pins from the versions installed in this environment:
  - `claude` → `2.1.218`
  - `opencode` → `1.18.4`
  - `cursor` → documented placeholder (`None`/`TODO`), set once the CLI is
    installed. A `None` pin means "declared but unpinned" → the check skips it,
    so shipping without a real cursor version does not warn spuriously.
- Version parsing tolerates suffixes: `claude --version` prints
  `2.1.218 (Claude Code)`, `opencode --version` prints `1.18.4`; the check
  compares the leading dotted token, not the whole line.

## 8. Tests — `tests/test_cursor_harness.py`

Mirrors `tests/test_harness_parse.py`:

1. `parse` extracts `session_id`/`cost_usd`/`input_tokens`/`output_tokens` from a
   synthetic one-line `result` event.
2. `parse` raw-stdout fallback on non-JSON / no result event.
3. `normalise_session` on a synthetic multi-event stream yields canonical events;
   feeding the result through `digest_of` asserts the waste aggregates
   (`files_written`, `failed_commands`, `model_turns`) — proves the E-38
   integration end-to-end at the adapter boundary.
4. `build_cmd` contains `-p`, `--model`, `--resume`, `--force`,
   `--output-format stream-json`, and appends `extra_args`.
5. `check_harness_versions`: warns on a mismatched installed version; skips
   (no warning) when `shutil.which` returns `None`; silent on match. Monkeypatch
   `shutil.which` and the version subprocess — no real CLI required.
6. `HARNESSES[HarnessKind.CURSOR]` resolves to a `CursorHarness`.

## 9. Files touched

- `src/sdlc/models.py` — `HarnessKind.CURSOR`.
- `src/sdlc/harness/adapters.py` — `CursorHarness`, `HARNESSES` entry,
  `expected_version`/`version_cmd` on `CodingHarness`, `check_harness_versions`.
- `src/sdlc/worker.py` — call `check_harness_versions()` after `validate_registry`.
- `tests/test_cursor_harness.py` — new.

No changes to `session.py`, benchmark matrix, or any case manifest.
