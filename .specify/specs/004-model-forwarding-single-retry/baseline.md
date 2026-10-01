# Baseline: 004-model-forwarding-single-retry

Recorded on the base sha before any source edit (Phase A).

| Item | Value |
|---|---|
| Base sha (main) | `730f085` |
| Branch | `004-model-forwarding-single-retry` |
| `uv sync --frozen --extra dev --extra logfire` in `kroker-dev` | RC=0, 104 packages checked |

## T002 pass counts

Measured on the clean base sha `730f085` (QA-prewritten 004 test files stashed during
the runs; restored afterwards). All runs in `kroker-dev`, one pytest per command.

| Tier | Result | Notes |
|---|---|---|
| `pytest -q` (fast) | **5382 passed, 11 skipped, 230 deselected**, RC=0, 579.57s | no failures |
| `pytest -m temporal -q` (chunked per file, 41 files, `timeout 300` per command) | **166 passed, 20 skipped, 1 xfailed, 0 failed**, every file RC=0 | no timeout-kills |

003-era temporal baseline was 165 passed / 21 skipped / 1 xfailed; the one-test shift
(one skip now passes) predates this feature and is recorded, not investigated.

Flake note: in one polluted-tree run before stashing,
`tests/test_promptfoo_provider.py::test_provider_imports_fast_enough_for_the_promptfoo_worker`
failed once on timing; it passes on the clean base and is environment-flaky, not a
pre-existing failure.

## T003 wire fixture verdict (R2)

Fixture `tests/durability/fixtures/wire_no_override.json` (frozen; regeneration only
via `SDLSC_WIRE_REGEN=1` on an unmodified base, executor-only). The greenfield_happy
no-override capture schedules 40 activities; all 6 `agent__*__model_request` inputs
carry the **registry string `anthropic:glm-5.2`**, not null. **R2 verdict: the model
id crosses the wire as the registry string** (advisor's reading; the worker-side
resolver chain sees the id for no-override runs too). Determinism confirmed: a second
live run equals the frozen fixture (test green, RC=0).

## T004 first-workflow-task timing

Measured on the clean base `730f085` in `kroker-dev` with a one-off replica of
`tests/durability/test_first_workflow_task_time.py`'s measurement (same
greenfield_happy scenario, sandboxed runner via `SdlcPydanticAIPlugin`,
`auto_time_skipping_disabled`): **first WorkflowTaskCompleted at 0.130s** from
`start_workflow` — far under the 1.5s assert budget (2s TMPRL1101 threshold minus
0.5s margin). The test itself is green on base (fast-tier baseline run, RC=0).

## T009 stacked-retry count on main

(to be recorded; needs the stub from T008)
