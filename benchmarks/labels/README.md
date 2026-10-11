# Root-Cause Labels

This directory holds human-curated root-cause labels for benchmark failures
(round 015, Phase 6, User Story 3).

## Purpose

When a benchmark run completes:
- Lost runs are automatically classified by last stage:
  - `research`, `clarify`, `architecture`, `plan`: **planning**
  - `code`, task-loop stages (`tool_approval`, `qa`, `review`, `adversary`, `deep_review`, `handoff`), and post-code stages (`analyze`, `merge`, `deploy`): **execution**
- Failed requirements of graded runs (oracle-task score < 1.0) remain **unattributed** unless a person assigns a specific root cause via a label file in this directory.

No cause is assigned automatically to graded runs; human labels attribute specific failures to planning, execution, or verification.

## File Location

Labels are stored per case and per benchmark run:

```text
benchmarks/labels/<case_id>/<bench_run_id>.yaml
```

For example:
`benchmarks/labels/cat-cafe-monitoring/2026-07-20T10-00-00.yaml`

If the directory or a bench run file does not exist, all failed requirements remain unattributed.

## File Format

A YAML document containing a top-level `labels` list. Each item has:

- `run_id` (str, required): The run ID of the benchmark run (e.g., `2026-07-20T10-00-00/cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.2`).
- `task_id` (str, required): The requirement ID from the case's `tasks.yaml` mapping.
- `cause` (str, required): One of the four root causes:
  - `planning`
  - `execution`
  - `verification`
  - `unattributed`
- `note` (str, optional): A brief explanation of why this cause was assigned.

## Example

```yaml
labels:
  - run_id: 2026-07-20T10-00-00/cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.2
    task_id: req_occupancy_rule
    cause: planning
    note: Architect omitted occupancy threshold in specification
  - run_id: 2026-07-20T10-00-00/cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.2
    task_id: req_alert_cooldown
    cause: verification
    note: QA gate passed despite broken cooldown timer
```

## Validation Rules

When loaded by `sdlc.benchmarks.root_cause.load_labels`, each entry is validated against:

1. **Known cause**: `cause` must be one of `planning`, `execution`, `verification`, `unattributed`. Unknown causes raise a `ValueError`.
2. **Mapped task**: When the case has a `tasks.yaml` mapping, `task_id` must match a task in the suite. An unknown task ID raises a `ValueError`.
3. **Known run**: `run_id` must appear among the records of the specified `bench_run_id`. An unknown run ID raises a `ValueError`.
4. **Matching case**: `run_id` must belong to the directory's `<case_id>`, not another case. A cross-case run ID raises a `ValueError`.
5. **Absent directory**: If `<labels root>/<case_id>` does not exist, `load_labels` returns an empty list without raising.
