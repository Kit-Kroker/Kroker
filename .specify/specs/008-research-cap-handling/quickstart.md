# Quickstart: validating 008 in the dev container

All commands run in `kroker-dev` with the feature worktree (`D:\own\Kroker-007`) mounted at `/app`. One pytest invocation per command; `addopts` already carries `-q`, do not add another. Capture with `> <log> 2>&1; echo RC=$?`. Never run alongside a live pipeline run.

## Prerequisites

- Worktree on branch `008-research-cap-handling`, based on main `c2d9b12`. No credentials, no network and no model calls needed.
- Read `.workspace/tasks/` for host hazards before any tier run.

## 1. Spend at the cap (H1)

```bash
pytest tests/research/test_research_cap_usage.py
```

Expect: a sub-question that exceeds its request limit, or whose tool is refused, returns a degraded finding with `failed` false and non-zero tokens; a run refused before any request returns today's zero usage; a clean run's usage is unchanged; the activity input serializes to the same bytes with or without a refusal record.

## 2. A refused charge writes nothing (H4)

```bash
pytest tests/research/test_research_budget_scope.py
```

Expect: a charge refused by the scope leaves the run counter unchanged, and the reverse; three concurrent charges against room for one leave both counters at one; the same for the architect scope; a refusal is noted on the deps with the counter named; a failure between the two writes leaves the scope one ahead and nothing else.

## 3. Retry exhaustion after a refusal (N4)

```bash
pytest tests/research/test_research_cap_retry_exhaustion.py
```

Expect: a model that keeps retrying a refused call yields one degraded finding with non-zero usage and a gap naming the refused bound; the same error with no refusal, or after a lock timeout, propagates.

## 4. The E1 scenarios (SC-003)

```bash
python - < .workspace/tmp/research-budget-enforcement-e1.py
```

Run from the host as `docker exec -i kroker-dev python - < .workspace/tmp/research-budget-enforcement-e1.py`. Expect, for S1, S2 and S3: the `run` counter shows 1 search and $0.01, equal to `sq-0` (baseline: 5, 2 and 12). For S4: the stage returns a finding with `failed` false and non-zero usage instead of raising.

## 5. Nothing else moved

```bash
pytest tests/research
pytest tests/test_model_forwarding.py
pytest tests/test_exa_wrapper.py
pytest -m temporal tests/replay
pytest -m temporal tests/durability/test_single_retry_layer.py
git status --short tests/replay/histories tests/replay/golden
git diff c2d9b12 --stat -- src/sdlc/stages/research/step.py src/sdlc/stages/research/toolset.py src/sdlc/stages/research/models.py src/sdlc/stages/research/retain.py src/sdlc/stages/research/verify.py src/sdlc/stages/architecture docs/reports/external-ideas-2026-09.md pyproject.toml uv.lock
```

Expect: all green; no file under `histories/` or `golden/` modified; the last diff is empty.

## 6. Whole feature

```bash
pytest
ruff check .
ruff format --check .
mypy
python scripts/check_file_size.py
```

Expect: fast tier green, pass count = baseline + this feature's new tests; lint, format, types and file-size gates clean (mypy: no new errors against the baseline).

## Reference: the baseline, already measured

E1/E2: `.workspace/tmp/research-budget-enforcement-experiments.md`. E3: `.workspace/tmp/research-cap-handling-e3.md`. E4: `.workspace/tmp/research-cap-handling-e4.md`.
