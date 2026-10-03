# Quickstart: validating 007 in the dev container

All commands run in `kroker-dev` with the feature worktree mounted at `/app`. One pytest invocation per command; `addopts` already carries `-q`, do not add another. Capture with `> <log> 2>&1; echo RC=$?`.

## Prerequisites

- Worktree based on main `721a802`. No credentials and no model calls needed.
- Read `.workspace/tasks/` for host hazards before any tier run. The `temporal` tier runs in the container only.

## 1. The guard, fast tier

```bash
pytest tests/durability/test_payload_guard.py
```

Expect: an over-limit request raises a non-retryable `ApplicationError` of type `ProposerPayloadTooLarge` whose message starts with the agent name and carries the size and the limit; at and under the limit the request goes through; outside a workflow nothing is checked; with the patch marker absent on replay nothing is raised; a history that grows across requests fails on the request that crosses the limit, and that request is never sent.

## 2. Coverage and boot check

```bash
pytest tests/durability
```

Expect: every agent in `ALL_TEMPORAL_AGENTS` carries the guard; the loader pins show three capabilities on the durable path and one on the eval path; the worker refuses to compose activities for an agent without the guard.

## 3. In a real workflow (temporal tier)

```bash
pytest -m temporal tests/durability/test_payload_guard_workflow.py
```

Expect: the over-limit run fails (it does not hang), with a patch marker and no model-request activity in its history; the under-limit run completes with no marker; the over-limit history replays cleanly.

## 4. Nothing else moved

```bash
pytest -m temporal tests/replay
pytest -m temporal tests/durability/test_wire_neutrality.py
git status --short tests/replay/histories tests/replay/golden
```

Expect: replay and golden suites green with no file under `histories/` or `golden/` modified.

## 5. Whole feature

```bash
pytest
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
git diff 721a802 --stat -- src/sdlc/stages src/sdlc/workflows/role_host.py pyproject.toml uv.lock agents
```

Expect: fast tier green, pass count = baseline + this feature's new tests; lint, format, types and file-size gates clean (mypy: no new errors against the baseline); the last diff is empty.

## Reference: today's behaviour (already measured)

Research R1 records the reproduction. To see it again, the probe is `.workspace/tmp/probe-007/probe.py`; it needs a dedicated dev server (never the live one on 7233).
