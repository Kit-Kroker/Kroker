# QA Stage

The QA stage performs clean-context validation of task deliverables against the frozen contract.
It runs the deterministic test suite activity within a provisioned worktree environment, produces
materialized diffs, generates the clean-context QA prompt, and executes the QA analyst proposer role.
It evaluates test results against contract assertions without access to conversational narrative or
prior attempt history.

The caller (`TaskHost._dev_task`) coordinates the fix loop, records deterministic and model benchmark
records, and orchestrates review. The stage owns clean-context prompt assembly, test runner execution,
linter and static security scan activities, and fix-loop diagnostic synthesis.

## Requirements

### QA-1.1
The QA step receives a `StageContext` protocol and required collaborators as keyword arguments,
and never receives the workflow instance or calls a gate directly. [FR-804]

### QA-1.2
Clean-context validation evaluates the task diff and deterministic test output against the frozen
contract assertions without conversational narrative or prior attempt context. [FR-804]

### QA-1.3
Deterministic ground truth (`qa_raw.tests_passed`) from subprocess execution is strictly preserved
and never overwritten by LLM self-reports or model opinions. [Finding 4]

### QA-1.4
Fix-loop analysis (`_fix_loop_issues`) unifies deterministic runner diagnostics and actionable findings
from both QA and reviewer judges into structured retry instructions, detecting stopped-early suites. [FR-802]

### QA-1.5
The slice exports `step` and `ACTIVITIES` (`run_test_suite`, `run_lint`, `scoped_security_scan`), which run
in isolated worktree environments with bounded timeouts and group process management. [FR-106]

### QA-1.6
The security scan measures the change, not the tree. `scan_paths` is a pure read over an explicit path list that emits one finding per match, each carrying its normalized source line. It skips paths under Kroker's own `_SCAN_SKIP_DIRS`, and any listed file it cannot read makes the point `NOT_COLLECTED`. `scoped_security_scan` lists tracked files (`git ls-files`) at the integration head and at the pinned base worktree, and returns a `ScopedSecurityReport`. `introduced` is the head-minus-base multiset over `(rule, path, line)`, with base paths mapped through the change's renames; pre-existing and resolved findings are counts. A report that is not `MEASURED` carries no findings and no counts. There is no exemption of any kind: pre-existing fixtures are pre-existing at the base, and new fixtures assemble their trigger text at runtime. [SC-5, FR-106, FR-915; diff-scoped gates DS4/DS7/DS9]

## Failure modes

- **Test failure**: Subprocess returns non-zero; failure traceback and short test summary info are captured for the fix loop.
- **Hung process**: Test or lint command hangs on dev server or long-running process; terminated on timeout and surfaced as an actionable timeout diagnostic.
- **Stopped early**: Suite aborted early (`-x` / `--maxfail`); flagged via `stopped_early` so the agent recognizes partial evidence.
- **Zero tests collected**: Pytest exits 5 with "no tests ran"; treated as vacuous pass when a task does not introduce tests yet.
- **Missing python dependencies**: Worktree venv provisions dependencies from `pyproject.toml` or `requirements.txt` to avoid ambient environment contamination.
- **Base not materialized / tracked file unreadable / `git ls-files` failed**: the scoped scan is `NOT_COLLECTED` with the reason, and the merge gate's absolute `security_scan_collected` fails.
