# Quickstart: validating architect-research-surface in the dev container

All commands run in `kroker-dev` with the feature worktree mounted at `/app`. One pytest invocation per command; `addopts` already carries `-q`, do not add another. Capture with `> <log> 2>&1; echo RC=$?`. Never run alongside a live pipeline run. Never set `SDLC_CAPTURE_HISTORIES`. No heredocs.

## Prerequisites

- Worktree on branch `architect-research-surface`, based on main. No credentials, no network and no model calls needed.
- Read `.workspace/tasks/` for host hazards before any tier run.

## 0. The channel still holds (once, before any source edit)

```bash
MSYS_NO_PATHCONV=1 docker exec -i -w /app kroker-dev python - < .workspace/tmp/c12-spike/c12_e1_toolreturn_visibility.py
MSYS_NO_PATHCONV=1 docker exec -i -w /app kroker-dev python - < .workspace/tmp/c12-spike/c12_e2_durable_roundtrip.py
```

Expect: E1 reports the metadata in `all_messages()` and the model-visible streams identical apart from the metadata field; E2 reports the metadata intact workflow-side after the durable round trip.

## 1. The report and its reader

```bash
pytest tests/test_sub_run_usage.py
pytest tests/test_role_usage.py
```

Expect: the payload has the five fields; malformed or absent reports yield nothing and raise nothing; `add_spend` leaves a bag's model and call count alone.

## 2. The tool reports, is limited, and degrades (6.2, N3)

```bash
pytest tests/architecture/test_architect_research_report.py
pytest tests/architecture/test_architect_research_tool.py
```

Expect: the tool returns the brief with a report beside it; the inner run carries the request limit; a limit stop and a budget stop both return a gap-only brief and still report their spend.

## 3. The deps carry the configured bounds (N2, N3)

```bash
pytest tests/architecture/test_architect_research_deps.py
```

Expect: a non-default ceiling and limit reach the deps; the default-config payload is unchanged.

## 4. The run accounts the spend (6.2)

```bash
pytest tests/test_run_role_sub_run_harvest.py
pytest tests/test_run_role_guard.py
```

Expect: research usage grows by exactly the reported counts; one pricing activity per answering model; the architect bag keeps its label and call count; no report means no extra tracking and no extra activity.

## 5. The model sees nothing new

```bash
pytest tests/durability/test_sub_run_usage_wire.py
pytest -m temporal tests/durability/test_sub_run_usage_wire.py
pytest -m temporal tests/durability/test_provider_payload_parity.py
```

Expect: all green. The fast run is layer 2 (request bodies byte-equal for the openai-chat and anthropic mappings); the `temporal` run is layer 1 (recordings differ only by the tool-return metadata key; tool definitions equal). The parity fixture is untouched.

## 6. Replay

```bash
pytest tests/replay/test_architect_research_usage_replay.py
pytest tests/replay
git status --short tests/replay/histories tests/replay/golden tests/replay/fixtures tests/durability/fixtures
```

Expect: the new history replays; every existing history replays; the only change under those directories is the one added file `architect_research_usage.json`.

## 7. Whole feature

```bash
pytest
pytest -m temporal tests/durability
pytest -m temporal tests/research
pytest -m temporal tests/replay
pytest tests/graph_workflow
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
```

Expect: fast tier green, pass count = baseline + this feature's new tests; lint, format, types and file-size gates clean (mypy: no new errors against the baseline).

## Reference: capturing the fixture (once, after the harvest lands)

```bash
SDLC_CAPTURE_ARCHITECT_RESEARCH_USAGE=1 pytest -m temporal tests/replay/test_architect_research_usage_replay.py::test_capture_architect_research_usage_history
```

Expect: writes `tests/replay/histories/architect_research_usage.json`. Not part of validation and never repeated.
