# Baseline: architect-research-surface

Recorded 2026-10-05, T001, on the branch base before any source edit.

## Base

- Branch `architect-research-surface` cut from `main` at **e5c8ef8** in the
  worktree `D:\own\Kroker-007` (bound to `/app` in `kroker-dev`; the container
  confirms `git log -1` = e5c8ef8, branch = architect-research-surface).
- `bcfbffc` (the spec anchors' commit) is the parent-of-parent; e5c8ef8 is
  docs/`.specify`-only over it, so the code baseline equals the anchors.
- `uv sync --frozen --extra dev --extra logfire`: clean, 104 packages,
  no changes (RC=0).
- `git diff e5c8ef8 --stat -- src` at checkpoint: empty.

## Fast tier (pytest, container, whole default run)

- **5559 passed, 11 skipped, 252 deselected** in 706.17s — RC=0.
- Pre-existing failures: **none**.
- Log: `.workspace/tmp/c12-t001-pytest.log` (primary checkout, untracked).

## mypy (container)

- **Success: no issues found in 379 source files** — 0 errors, RC=0.
- Log: `.workspace/tmp/c12-t001-mypy.log`.

## Probes (SG-1 check)

Run as separate commands, piped from the primary checkout's
`.workspace/tmp/c12-spike/` into `kroker-dev` at `/app` (the branch base).

| Probe | Verdict | Log |
|---|---|---|
| E1 `c12_e1_toolreturn_visibility.py` | metadata present workflow-side in `all_messages()`; model-visible streams differ only by the tool-return `metadata` field (dict vs null), content identical — same result the spike recorded | `.workspace/tmp/c12-t001-e1.log` |
| E2 `c12_e2_durable_roundtrip.py` | **True** — metadata survives the durable `__call_tool` round-trip intact workflow-side; marker in the event history; outer run usage 134/48 does not auto-merge the inner 424242/777 | `.workspace/tmp/c12-t001-e2.log` |
| E3 `c12_e3_limit_and_parts.py` (new this task) | all three facts below | `.workspace/tmp/c12-t001-e3.log` |

**SG-1 does not fire.**

### E3 facts (verbatim)

- `str(UsageLimitExceeded)` of a real limit stop (FunctionModel tool loop,
  `UsageLimits(request_limit=2)`, caller-owned `usage=RunUsage()`):

  > The next request would exceed the request_limit of 2. Consider raising the limit, or see the docs on usage limits for budget-aware patterns: https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits

  It **carries the library's advice and a documentation URL** — confirms
  research R9 / spec AM2: `str(exc)` must never enter a brief.
- Caller-owned usage after the limit: `input_tokens=107 output_tokens=12`,
  `cache_read_tokens=0 cache_write_tokens=0`, `requests=2` — **non-zero**,
  so the degrade path can report its spend.
- Tool-return `part_kind` literal: **`tool-return`** (TestModel run; part
  type `ToolReturnPart`).

## File sizes at the base (content lines)

| File | Lines |
|---|---|
| `src/sdlc/stages/research/toolset.py` | 70 |
| `src/sdlc/stages/research/deps.py` | 116 |
| `src/sdlc/workflows/role_host.py` | 300 |
| `src/sdlc/stages/architecture/step.py` | 306 |
| `tests/durability/_http_stub.py` | 170 |
| `tests/replay/scenarios.py` | 906 |

Matches the plan's Constraints (scenarios.py: 906 content / 907 by
`check_file_size.py`'s count).
