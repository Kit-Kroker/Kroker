# Contract: Grace gate runbook (FR-001, FR-002; Q2 = A)

**Not run during planning.** Tasks T030 (gate run 1) and T090 (gate run 2)
run these commands, and only those tasks.

## Target store

The compose dev server:
- container `kroker-temporal-1`;
- volume `temporal-state`;
- reached from the host at `127.0.0.1:7233`;
- namespace `default`. Nothing in the repo sets a namespace, and
  `worker.py:277` and `cli.py:489` use `TEMPORAL_HOST` alone.

If the worker that will be restarted points elsewhere, check its
`TEMPORAL_HOST` in `docker-compose.yml` and use that address instead.

```bash
ADDR=127.0.0.1:7233; NS=default
```

## Commands

Record every command verbatim in `verification.md`, with its full output.

```bash
date -u +%Y-%m-%dT%H:%M:%SZ
docker inspect -f '{{.Id}} {{.State.StartedAt}}' kroker-temporal-1
git rev-parse HEAD

# G0: identity checks, so an empty or wrong store cannot pass
temporal workflow count --address "$ADDR" --namespace "$NS"
temporal schedule list  --address "$ADDR" --namespace "$NS"

# G1: no Running FeatureWorkflow
temporal workflow list --address "$ADDR" --namespace "$NS" \
  --query "ExecutionStatus='Running' AND WorkflowType='FeatureWorkflow'"

# G2: no Running parent that can start a pipeline child, of ANY start time (Q2 = A)
temporal workflow list --address "$ADDR" --namespace "$NS" \
  --query "ExecutionStatus='Running' AND (WorkflowType='TidyUpWorkflow' OR WorkflowType='BenchmarkWorkflow')"
```

## Pass rule

The gate passes only when **all** of these hold:
1. G0's count is greater than 0. A store with zero workflows is the wrong
   store.
2. G0's schedule list has no schedule whose action starts `FeatureWorkflow`,
   `TidyUpWorkflow` or `BenchmarkWorkflow`.
3. G1 lists zero rows.
4. G2 lists zero rows.

Anything else is a **FAIL**:
- record the ids;
- stop: no deletion commit for run 1, no deploy for run 2;
- wait for drain and re-run the gate.

There is no override.

## Placement

- **Run 1 (T030)**: after PR-1 is merged and before the first PR-2 commit
  that removes code.
- **Run 2 (T090)**: immediately before the irreversible step, which is the
  first of these:
  - `docker compose pull worker && docker compose up -d worker` with a
    PR-2 image;
  - a local `docker compose up -d --build worker` on PR-2;
  - pushing a `v*` tag that contains PR-2 (`release.yml` publishes the
    image, and compose defaults `KROKER_IMAGE_TAG` to `latest`).

  Run 2 must be **less than 1 hour** before that step, and nothing that
  starts runs may happen in between.
- Merging PR-2 deploys nothing (checked: `ci.yml` and `docs.yml` have no
  deploy step).

## Recovery (roll-forward only)

- **A FeatureWorkflow Running after the restart**: its tasks fail as
  "type not registered". Run
  `temporal workflow terminate --workflow-id <id> --reason "020 post-cutover cleanup"`
  and re-submit the idea with `sdlc start`.
- **A Tidy/Benchmark workflow task failing with a nondeterminism error**:
  ship a roll-forward fix to `pipeline_child.py`'s `deprecate_patch` path.
  Do not re-register FeatureWorkflow.
- **A query on a closed pre-cutover parent failing** (`sdlc tidyup report`):
  expected and accepted (research R-1). Record it and take no action.
