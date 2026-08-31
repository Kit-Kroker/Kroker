# The crew: a Temporal-native multi-agent coding stage (E-88)

**Date:** 2026-08-31
**Roadmap:** new — `E-88`, supersedes `E-87` / `E-87b` (herdr interactive harness)
**Requirements:** No FR moves. `HarnessKind` gains `CREW`; the stage DAG, gate semantics, and
artifact contracts are untouched. One call site in `feature.py` changes shape.
**Baseline:** `main` at `2f0dc2f`. E-87/E-87b live only on `feat/e-87-herdr-harness` and were never
merged, so every `herdr/*` and `src/sdlc/herdr/*` path cited below is **branch-only** and is quoted
as evidence, not as something this work edits. All other line anchors are `main`'s.
**Builds on:** `2026-08-20-herdr-interactive-harness-design.md` (its round protocol, role taxonomy,
and escalation policy are inherited nearly verbatim) and `2026-08-30-herdr-coding-layout-design.md`
(its §7.1/§7.2 live outcomes are the measured baseline this design must reproduce).
**Design input:** [Temporal design patterns catalog](https://temporal-design-patterns.fly.dev/) —
Child Workflows, Parallel Execution, Pick First, Long-Running Activity, Resumable Activity,
Non-Retryable Errors, Approval, Worker-Specific Task Queues.

## Problem

E-87 bought one thing — several long-lived agent sessions collaborating in one worktree — and paid
for it with a second stateful container. The bill is itemised in E-87's own text and in E-87b's
live-verification section: a UDS socket that must travel on a named volume because Docker Desktop
for Windows cannot share one over a bind mount; a worktree volume that must be mounted at an
*identical* absolute path in two services or the failure presents as worktree corruption; pane
state that is not durable, so a server restart leaves bare shells; orphan tabs and an
`agent_name_taken` collision on any retry after a `deferred` ending; a per-pane scrollback ceiling
that must be computed rather than discovered as an OOM taking every live tab with it; opencode's
auto-updater replacing the pinned binary inside a running container; and a crash loop caused by a
file mount inside the data directory defeating the entrypoint's symlink swap.

None of these are accidents. They are the ordinary diseases of a shared mutable singleton that owns
live processes, and every one was found the expensive way — which is the whole value of the branch,
and the reason it is quoted here rather than merged.

Underneath the operational bill sits a structural one. `TabDriver` is 782 lines implementing a
round state machine, deadlines, heartbeats, recovery after an activity retry, a cost brake, and
HITL routing — inside an activity, in a codebase whose entire premise is that Temporal owns exactly
those concerns. `journal.jsonl` exists because the activity has no durable history of its own. The
§3 disagreement table exists because a TUI screen heuristic was pressed into service as a control
signal. Both are compensations for running an orchestrator where an orchestrator already runs.

And the layout the factory can actually reach — `code.yaml`, the only one, because
`HarnessKind.HERDR` is selectable only through `HARNESS_ROLES` and all three of those are coding
roles — is `rounds.max: 1`, `splits: []`: a single opencode session, invoked once. The multi-agent
value E-87 was written for is not on the reachable path, while its full operational cost is.

## Findings

1. **A live pane is not required for context continuity.** Every subprocess adapter already resumes
   a prior session: `--resume <id>` for claude (`adapters.py:314`), `-s <id>` for opencode
   (`adapters.py:620`), `--resume <id>` for cursor (`adapters.py:822`). The session store is the
   CLI's own, on a volume. A round can therefore be an ordinary batch invocation that continues the
   same conversation, which removes the only reason a process had to stay alive between rounds.

2. **The workflow layer already proves the pattern.** `feature.py:1534` runs a loop that invokes the
   harness, inspects `run.deferred`, opens a durable gate, and re-invokes with
   `session_id=run.session_id` plus grants. That is a multi-turn, session-resuming, human-gated
   agent loop hosted in a Temporal workflow, in production, today. The crew is this shape
   generalised from one agent to several.

3. **`GateHost` was extracted for exactly this.** Its docstring: "Extracted from FeatureWorkflow
   (E-42 D2) so a second workflow can host a gate without restating 'first decision for
   (gate, round) wins'" (`gates.py:1`). `TriageWorkflow` is already the second host. A crew workflow
   is the third, and inherits policy resolution, `(gate, round)` identity, the notification
   schedule, and the timeout decision without restating any of them.

4. **The inbox discovers gate hosts by workflow type, client-side.** `list_open_run_ids`
   (`inbox.py:66`) filters `WorkflowType='FeatureWorkflow' AND ExecutionStatus='Running'`, and the
   comment beside it says why: other types on the same task queue "never expose pending_decisions".
   A new gate-hosting workflow type is therefore one disjunct in one string, and `_fetch_one`,
   `fetch_pending`, and `submit` operate on handles and need no change at all.

5. **ADR-6 is already a pre-DAG check, and already the right check.** `validate_run_roles`
   (`loader.py:248`) is documented as "per-run ADR-6 enforcement at a boundary that constructs a
   non-default role→model map (benchmark arm, CLI `--role-model`)", and `build_role_overrides`
   (`cli_roles.py:36`) calls it while parsing arguments, before any workflow starts. Its notion of
   correlation is **model-family inequality**, not string inequality — the correct granularity,
   since two models from one family are a correlated second opinion regardless of their names. The
   crew's roles need to enter that same map; they do not need a new mechanism, and must not get a
   runtime one.

6. **Containment stops being an intersection.** E-87 finding 3 had to compute a tab's containment as
   the intersection over its panes, because one tab was one harness run — so the weakest pane fenced
   the writing one, and role assignment "follows from enforceability rather than taste". When each
   turn is its own harness run with its own policy, each role is fenced by its own harness's best
   tier and a weak advisor cannot weaken the lead. `_resolve_containment`'s ADR-17 refusal
   (`activities.py:502`) still applies per role, which is now a statement about the crew's
   composition and therefore checkable when the layout loads.

7. **Cost is already in the stream the adapters parse.** claude and cursor report `total_cost_usd`
   (`adapters.py:504`, `:849`); opencode reports per-step cost in `step_finish` (`:743`). E-87 §6
   needed `CostProbe` — 345 lines reading CLI session logs keyed by herdr's `agent_session` — only
   because a TUI pane emits no such stream. Batch turns emit it. One exception, recorded rather than
   glossed: the cursor adapter's cost line carries `# ASSUMPTION: may be absent`.

8. **The session id is known long before a turn ends, and is lost anyway.** `adapters.py:127` reads
   it from `step_start`, seconds into the run; but an activity that dies returns nothing, so a retry
   would start a fresh session and re-pay the entire context. Temporal's heartbeat payload plus
   `activity.info().heartbeat_details` closes exactly this gap — the catalog's **Resumable
   Activity**.

9. **A turn is not idempotent, and the two failure classes want opposite policies.** A turn spends
   money and mutates the worktree. An infrastructure failure (dead worker, OOM, provider timeout)
   should retry, and with finding 8 it retries cheaply into the same session. An agent-level failure
   (non-zero exit, missing round file, schema violation, refusal) is a *result*, and retrying it
   with the same prompt is spend without signal. A blanket `maximum_attempts=1` is therefore too
   coarse; the split is by class.

10. **Cross-vendor composition has exactly two usable vendors today.** `main`'s `HarnessKind` is
    `CLAUDE_CODE`, `OPENCODE`, `CURSOR`, and `HARNESSES` registers all three — but `CursorHarness`
    carries `expected_version = None` ("Set once the CLI is installed", `adapters.py:807`) and
    inherits `frozenset()` containment, so under ADR-17 "cursor cells drop out of a contained
    benchmark sweep" (`adapters.py:830`). `ANTIGRAVITY` exists only on the herdr branch, where
    `models.py` records that it is deliberately absent from `HARNESSES` so "a role cannot select it
    until E-87b writes one"; it is not on `main` at all. A crew therefore ships with two vendors and
    grows to three when cursor is installed or an `agy` batch adapter is written — the latter being
    *less* work than a pane was, because a pane also required a `CostProbe`.

11. **Human intervention was labelled, not prevented.** E-87 §7 conceded that a human attaching to a
    pane makes the result non-reproducible and journals `manual_intervention` as "an honest label,
    not a prohibition". With no terminal to attach to, the only human input is a gate decision,
    which lives in workflow history and replays. Reproducibility becomes structural.

12. **One external consumer keys on the activity name.** `benchmarks/drift.py:71` skips events whose
    `activity != "run_coding_task"`. A crew turn is a different activity, so without a change drift
    is silently not computed for crew tasks — a lost signal rather than a failure, which is the kind
    that goes unnoticed.

## Design

### §1 Boundaries and the contract upward

`HarnessKind.HERDR` becomes `HarnessKind.CREW = "crew"`. The `herdr/` configuration directory
becomes `crew/`; roles and skills move with their contents intact.

**One call site changes.** `feature.py:1534` invokes the `run_coding_task` activity. For a role whose
harness is `crew`, it starts a child workflow instead:

```python
run = await workflow.execute_child_workflow(
    CrewTaskWorkflow.run,
    CrewTaskInput(layout=role_cfg.layout, prompt=prompt, worktree=worktree,
                  lead_model=role_cfg.model, sessions=sessions, ...),
    id=f"{workflow.info().workflow_id}-crew-{task.id}-{attempt}",
)
```

Everything wrapped around that call is unchanged: `escalations_from_denials`, cost accumulation
under the executing role, `_session_refs`, `near_context_ceiling`, the fix-attempt budget, and the
stage gates. The child returns the same `HarnessRunResult`.

**One wrapper type, not a change to the shared contract.** `HarnessRunResult.session_id` is a single
string and a crew needs one per role. Rather than widen a model read by the heatmap, the benchmark
recorder, and `drift.py`, the child returns:

```python
class CrewRunResult(BaseModel):
    run: HarnessRunResult            # the LEAD's: its tokens, its window, its summary
    sessions: dict[str, str]         # role -> session_id
    session_refs: list[ArtifactRef]  # one scrubbed transcript per turn
    rounds: list[RoundRecord]
```

`run.session_id` stays the lead's, which is honest: E-87 §4's rule that the token fields describe the
lead pane rather than a meaningless sum across three context windows is preserved unchanged.

**An abstraction is never bent in the first place.** E-87 finding 1 had to strip `@abstractmethod`
from `build_cmd` and give it a raising default, because a tab had no single command line, and
`HerdrHarness` overrode `run()` outright to feed `parse()` a synthetic journal. On `main`
`build_cmd` is still `@abstractmethod` (`adapters.py:156`), and this design keeps it that way:
composition lives in the workflow, so `CodingHarness` stays batch-only and no composite harness
object is ever added.

**Transcripts improve.** A turn is an ordinary harness run, so `capture_session`
(`activities.py:569`) runs per turn: N real scrubbed transcripts through the existing E-38/ADR-16
path. The branch's synthetic tab journal and its `_publish_herdr_journal` publisher are simply never
written.

The worktree is one per task and shared by the crew, as before. Containment is per role by path
prefix: the lead may write repository files, non-lead roles are confined to
`.workspace/orchestration/<layout>/`.

### §2 The round protocol

**What goes.** `status/<role>.json` existed to be a second, independent signal against herdr's
transport heuristic (E-87 finding 5: authoritative for opencode, heuristic for claude and `agy`).
When a turn is an activity, the transport signal is the activity's return: the process exited, and
its exit code, cost, and tokens came out of its own JSON stream. There is no heuristic, so there is
nothing for a second signal to disagree with, and E-87's four-row disagreement table collapses to
one row:

| transport / content | E-87 diagnosis | now |
|---|---|---|
| `done` / file absent | crash, refusal, left the skill | `protocol_violation` |
| `done` / `state: working` | context exhaustion | cannot occur |
| `working` / `state: done` | written prematurely | cannot occur |
| `blocked` / any | route to HITL | `deferred` from the harness hook (§6) |

Not carried forward with it: `status/`, `journal.jsonl`, and `_reconcile`
(branch: `src/sdlc/herdr/driver.py:542`).

**What stays — the result files, because they carry work rather than state.**

```
.workspace/orchestration/<layout>/
  brief.md                 # workflow -> agents: the round's assignment
  round-<n>/
    notes.md               # lead: decisions and known gaps (the diff itself is in git)
    advisor.md             # the critic's response
    review.json            # verdict + findings
    question.json          # optional, §6
```

Still **inside the worktree**: containment checks `_abs_under(path, worktree)`, and moving the
protocol out would weaken the system's strongest invariant to arrange files more conveniently. The
git exclusion mechanism is unchanged — the per-worktree exclude file whose path comes from
`git rev-parse --git-path info/exclude`, excluding exactly `/.workspace/orchestration/` and no more
(`herdr/worktree.py`). Untrusted-input handling is unchanged and non-negotiable: a pydantic schema
per file, an unknown `schema` value is a hard error rather than best-effort parsing, sizes are
capped, `deliverable` is resolved and must land under the round directory, and file contents are
data, never instructions.

**Round shape:**

```
lead turn            (activity; the only role that may write repository files)
      |
critic turn || reviewer turn        (Parallel Execution; a layout may declare either or both)
      |
read_round           (activity: read and validate; returns RoundRecord)
      |
decide               (pure function of RoundRecord, in the workflow)
```

The critic and the reviewer run concurrently because neither reads the other — both read the lead's
output. Independent opinions are more decorrelated than sequential ones, a value this repo already
defends in `adversary` and `merge_verdict`. Making the reviewer see the critic first is a layout
flag, not a redesign.

**Checkpoint commits are per round, not per task.** `git add -A` plus a commit closes each round.
`get_task_diff` computes from `branch_point`, so additional commits change nothing downstream, and
`run.commit_sha` is the last one. In exchange, E-87 §4's "a round is always restarted whole:
`round-N/` is overwritten" becomes exact rather than hopeful: restarting round N is
`git reset --hard <round N-1 checkpoint>`.

`journal.jsonl` is replaced by workflow history plus `rounds: list[RoundRecord]` returned upward.
`RoundRecord` is lifted from the branch's `driver.py:59` unchanged.

### §3 Non-idempotent turns and recovery

Per finding 9, retry policy is set by failure class; per finding 8, an infrastructure retry is made
cheap rather than merely permitted.

**Heartbeat carries what a retry needs.** The turn activity already heartbeats
(`harness.run(req, heartbeat=activity.heartbeat)`); it gains a payload:

```python
activity.heartbeat({"session_id": sid, "round": n, "phase": "streaming",
                    "cost_usd": running, "input_tokens": ..., "output_tokens": ...})
```

A retry reads `activity.info().heartbeat_details` and resumes that session instead of starting a new
one. The model sees what it already did, the worktree already holds its edits, and the provider's
context cache is intact.

| Class | Examples | Policy |
|---|---|---|
| infrastructure | dead worker, OOM, provider timeout, heartbeat timeout | `maximum_attempts=2`, resume the session from heartbeat details, leave the worktree alone |
| agent-level | non-zero exit, round file absent, schema violation, refusal | `ApplicationError(non_retryable=True)`; the decision rises to the workflow |

**An abandoned attempt's cost is recovered, not lost.** E-87 §6's rule — restarted rounds count in
full, records keyed by `(role, round, attempt)` — is kept, with a new source. On a timeout the
workflow reads `TimeoutError.last_heartbeat_details`; on an `ApplicationError` it reads the `details`
the activity attached. When neither is available the round is marked `cost_incomplete` and that
reaches the result, rather than silently understating the budget — the same discipline as E-87's "a
missing record is `protocol_violation`, never a silent `None`".

**Worktree state after a failure is a decision, not a side effect.** An infrastructure retry resumes
into the dirty worktree and keeps the work. A workflow-level round restart resets to the previous
round's checkpoint (§2), which is clean and reproducible.

**Whole-worker loss.** The workflow replays from history: closed rounds are facts, and only the
in-flight turn is re-dispatched. E-87 §4's three recovery scenarios (tab alive → reattach; server
restarted → relaunch panes; no tab → rebuild) and its `driver.py:353 attach()` have no counterpart
here, because there is no live state to reattach to.

**One new constraint, stated plainly.** Session resume requires the CLI's session store to be
reachable by whichever worker takes the retry. Today that is the `agent-sessions` volume, and
`worker-worktrees` already imposes the identical requirement, so this is not a regression. It does
not survive a move to multiple hosts on its own; the catalog's answer there is **Worker-Specific Task
Queues**, pinning a crew's turns to the worker holding its worktree. Recorded as a known boundary,
not scheduled.

### §4 Budget and brakes

| Brake | E-87 | Now |
|---|---|---|
| `rounds.max` | counter in `TabDriver` | loop bound in the workflow — same semantics, replayable and visible in history |
| `wall_clock_s` | compared against `time.monotonic()` inside the activity | a workflow timer raced against the round — **Pick First** |
| `pane_idle_timeout_s` | `min(idle, remaining)` as the whole turn's deadline | `turn_timeout_s` → `start_to_close_timeout`, plus `heartbeat_timeout` as the honest analogue of "state stopped changing" |
| `cost_usd` | `cost.py` reading CLI session logs via herdr's `agent_session` | an accumulator in durable workflow state; figures from the CLI's own JSON stream |

**The crew deadline is an in-workflow timer, not the child's `execution_timeout`.** This is E-87's own
reasoning one level up: if an outer timeout kills the execution before our brake fires, the diagnosis
and the accumulated cost are lost and a bare timeout travels upward. So the workflow ends itself with
a classified reason, and `execution_timeout` on the child stays as a strictly larger backstop. The
loader check survives, retargeted from the activity's `start_to_close_timeout` to the child
workflow's `execution_timeout`.

**A turn timeout no longer destroys work.** `herdr/layouts/code.yaml` documents the observed defect:
the value doubles as the whole turn's deadline, and `_reconcile` turns a timeout into `idle_timeout`,
"which discards the round AND the work already done in the worktree". With per-round checkpoints (§2)
there is nothing to discard — earlier rounds are commits, and the current round's edits survive
uncommitted for the resumed session (§3). This is the precondition that makes `turn_timeout_s` safe
to set aggressively.

**Cost changes source, not rules.** The check still happens at a round boundary: an agent must not be
cut off mid-answer over a cent, but a round boundary is an honest decision point. Never written:
the branch's `cost.py` (345 lines) and the loader's "every harness in a layout has a working
`CostProbe`" boot check, both obsolete per finding 7.

**Round structure becomes native observability.** `{crew, round, phase, role}` heartbeats remain for
the turn in flight, but round boundaries are now history events, so the Temporal UI shows the
structure without heartbeat prose.

### §5 Configuration and cross-vendor composition

Two layers, and they do not compete.

**Layer 1 — `agents/dev/agent.yaml`:** what the factory selects for the stage.

```yaml
kind: harness
harness: crew
layout: code
model: zai-coding-plan/glm-5.2   # the LEAD's model; see the precedence rule
```

**Layer 2 — `crew/layouts/<name>.yaml` plus `crew/roles/*.yaml`:** who is on the crew. This is where
cross-vendor composition lives.

```yaml
# crew/layouts/code.yaml -- what ships, given the CLIs actually installed today
layout: code
lead: coder
crew: [coder, critic]
rounds: {max: 2, require_reviewer_approval: false}
deliverable: {path: notes.md, schema: notes-v1}
limits: {wall_clock_s: 3000, turn_timeout_s: 1800, cost_usd: 25.0}
```

```yaml
# crew/roles/coder.yaml          crew/roles/critic.yaml
harness: opencode                harness: claude_code
model: zai-coding-plan/glm-5.3   model: anthropic:claude-opus-5
writes: true                     writes: false
skill: coder                     skill: critic
```

**The reviewer slot is the general form, and it is gated on a third vendor.** §2's round shape
(`critic || reviewer`) is what a layout may declare; a layout may also omit the reviewer, and the
shipped `code.yaml` does, because a third vendor is not available today. `CursorHarness` exists but
its CLI is not installed — `expected_version = None`, "Set once the CLI is installed" — and it
inherits `frozenset()` containment, so per ADR-17 it fails closed and "cursor cells drop out of a
contained benchmark sweep" (`adapters.py:830`). `agy` has no adapter at all (finding 10). Naming a
reviewer before one of those is resolved would put a model string in this spec that nobody can run.
Adding the reviewer is therefore its own step, not a hidden prerequisite of this one.

**Every crew role must declare a model.** This mirrors `validate_registry`'s existing "role 'dev'
must declare a model" and is load-bearing here for a second reason: a role that lets its CLI pick a
default cannot enter `role_models`, and a role outside `role_models` is a role ADR-6 cannot check.

**`splits` disappears.** It described screen geometry —
`{from: planner, to: advisor, direction: right, ratio: 0.5}`. With no screen, the layout is a flat
`crew` list: it stops describing a window and starts describing a team. `_pane_model`, `pane.split`,
`set_split_ratio`, and `agent.rename` go with it.

**Precedence: the request's model wins over the role file, but only for the lead.** This is not taste;
it is what makes a benchmark cell measurable, and `herdr/roles/coder.yaml` already argues it — a cell
that varied harness and model at once would compare two things. Non-lead roles always take their
model from their own file, so `code | crew | <model>` varies exactly one variable.

**Decorrelation is validated before the DAG starts, per finding 5.** When a harness role resolves to
`crew`, the loader expands its layout and contributes the crew into the same `role_models` map that
`check_adr6_families` already validates:

```python
{"dev": "zai-coding-plan/glm-5.3",              # the lead's model for THIS run
 "reviewer": "...",                              # the stage reviewer, as today
 "crew:code:critic": "anthropic:claude-opus-5",
 "crew:code:reviewer": "..."}
```

with one added rule, stated in the same terms as the existing `dev`/`reviewer` pair: **every
non-writing crew role must differ in model family from that crew's lead.** Consequences:

- A run whose sweep collides never starts. The error surfaces where "unknown role" already surfaces —
  in `parse_role_models` while parsing `--role-model`, or in the benchmark arm while building the
  cell.
- No third policy is needed. "Auto-substitute the reviewer" and "run with a `correlated_crew` flag"
  exist only for finding out too late, and we do not find out too late.
- The limit is honest: this catches collisions the configuration *declares*. A provider silently
  serving one model under two names defeats it — exactly as it defeats ADR-6 today. Not widened here.

**Changing a provider or harness for a role.** Model or harness is a one-line YAML edit as long as the
harness is in `HARNESSES` (`claude_code`, `opencode`, `cursor`). Three frictions are real and are not
hidden:

1. **Auth and the model catalog.** Each CLI resolves providers its own way; compose already carries
   opencode's `auth.json` and `models.json` from the host for this reason. Pointing a role at a
   provider its CLI is not logged into currently fails at runtime, after other roles have spent. The
   loader therefore gains a boot check: for every role in a layout, its harness can resolve its
   model. This replaces the `CostProbe` boot check removed in §4, and is a better use of the same
   discipline.
2. **The model string stays pass-through.** E-87 refused to normalise it — "a 'common' format would
   need a translation table that eventually lies" — and that holds. Each adapter's `build_cmd` knows
   its own flag syntax, so changing a role's harness means rewriting its model string in the new
   CLI's format. No mechanical conversion is offered.
3. **Containment tiers differ** — `claude_code` declares `NATIVE|HOOK` (`adapters.py:317`), `opencode`
   `NATIVE` (`:630`), `cursor` none. Per finding 6 the intersection rule is gone, so a weak critic no
   longer weakens the lead; but in a contained run a role on a harness with no layer is still
   inadmissible, and that is now checked against the crew's composition at load rather than
   discovered mid-task.

### §6 Human-in-the-loop

**The gate is hosted by the child, not bubbled to the parent.** `CrewTaskWorkflow` subclasses
`GateHost` (finding 3). Returning `deferred` upward would mean rebuilding all round state on the
retry — precisely the reattach machinery §3 deletes — so the gate stays where the state is.

```
turn(role) -> run.deferred is not None
   -> self._gate("tool_approval", ..., default_policy=HARD)   # GateHost, in the child
   -> turn(role) again, with grants and the resumed session (§3)
```

E-17's rules are preserved verbatim: resuming for an approval costs neither a fix attempt nor the
FR-802 resume budget; `max_tool_escalations` caps, and the final resume exists only to deliver the
denial; `escalations_from_denials` records escalations.

**The inbox needs one disjunct.** Per finding 4, `list_open_run_ids`'s visibility filter becomes
`(WorkflowType='FeatureWorkflow' OR WorkflowType='CrewTaskWorkflow') AND ExecutionStatus='Running'`.
Everything downstream operates on handles and is unchanged.

So the operator sees a crew item as part of its run rather than as an orphan, `PendingDecision` gains
an optional `parent_run_id` which the child stamps and the renderer groups by, falling back to the
handle id. A field, deliberately, rather than parsing the deterministic workflow-id prefix from §1:
the prefix is a fact about ids, not a contract for display.

**Question classification is policy and does not change.** E-87 §7's table stands: settled upstream →
answered by `brief.md`; a trade-off between knowable options → answered by the critic; a genuine gap
in user intent → answered by a human via `PendingDecision` → inbox → `answer_question`. So does its
guard: a question carrying neither a class nor evidence is not a question, and is rejected as
`protocol_violation` rather than forwarded. Only delivery changes — `question.json` is read and
validated by `read_round`, and the human's answer arrives in the next round's `brief.md` instead of
"delivered to the pane as the next brief after reattach".

**The escalation budget stays at two per crew**, as a counter in durable workflow state. Exhaustion
ends the crew as `intent_gap`, still journalled as a metric, because a lead hitting an intent gap is
evidence that `clarify` under-performed on this task.

**What disappears with the panes.** herdr's `blocked` state and its classification,
`_dismiss_startup_block` (`driver.py:275`), and per finding 11 the whole `manual_intervention` story.
E-87's principle — "a second approval channel is not permitted: a decision taken in a pane never
enters the run's history" — was held by prohibition; it is now held by construction.

### §7 Inventory and verification

Because E-87 never reached `main`, most of what E-87b's design would have had to delete is instead
simply **not carried forward**. That is the single biggest consequence of building from `main`: this
is not a removal project.

**Not carried forward** — it exists only on `feat/e-87-herdr-harness`, and stays there:

| Item | Lines | Why it has no successor |
|---|---|---|
| `src/sdlc/herdr/driver.py` | 782 | the round machine is the workflow (`RoundRecord`, `driver.py:59`, is lifted out first) |
| `src/sdlc/herdr/cost.py` | 345 | cost comes from the CLI stream (finding 7) |
| `src/sdlc/herdr/adapter.py` | 178 | there is no composite harness (§1) |
| `src/sdlc/herdr/client.py` | 139 | NDJSON over a UDS |
| `src/sdlc/herdr/protocol.py` | 132 | the socket API schema |
| `herdr/config.toml` | — | it configured a server |
| `Dockerfile` stage `herdr` | 77 of the branch's 185 | 42% of that file |
| `scripts/kroker-pane`, `herdr-entrypoint.sh`, `herdr-api-key-helper.sh` | — | pane plumbing |
| `activities.py::_publish_herdr_journal` | ~55 | there is no journal |
| `adapters.py::_register_herdr` | ~30 | and its import-cycle commentary with it |
| compose: service `herdr`, volumes `herdr-sock` and `herdr-state`, the `auth.json` staging workaround | — | `main`'s compose never grew them |
| `HarnessKind.HERDR` and `ANTIGRAVITY` | — | `main` has neither; only `CREW` is added |
| 13 of the 15 `tests/test_herdr_*.py` files | ~2390 | their subject is transport (see below) |

**Carried across from the branch**, because their meaning survives the change of mechanism:

| From | To | Change on arrival |
|---|---|---|
| `herdr/{layouts,roles,skills}/` | `crew/` | `splits` dropped; roles reduced to `coder` + `critic` (§5) |
| `src/sdlc/herdr/loader.py` | `src/sdlc/crew/loader.py` | rules change per §1/§5; "fail at boot, not mid-run" does not |
| `src/sdlc/herdr/worktree.py` | `src/sdlc/crew/worktree.py` | unchanged — its docstring states an invariant this design keeps |
| `RoundRecord` (`driver.py:59`) | `src/sdlc/crew/models.py` | unchanged |
| `benchmarks/cases/herdr-probe/` | `benchmarks/cases/crew-probe/` | rename only; its recorded numbers are the baseline below |
| `tests/test_herdr_{loader,worktree}.py` | `tests/test_crew_*.py` | retargeted, not rewritten |

**What this design actually edits on `main`** is therefore small and worth listing in full: add
`HarnessKind.CREW`; add `CrewTaskWorkflow` and four activities; change one call site
(`feature.py:1534`); extend `check_adr6_families` and `validate_run_roles` (§5); add one disjunct to
`_OPEN_FEATURE_QUERY` (`inbox.py:66`); add `parent_run_id` to `PendingDecision`; teach
`benchmarks/drift.py:71` the crew turn's activity name (finding 12); register the new workflow and
activities in `worker.py`; and add `claude_code`'s CLI to the worker image, which today ships
opencode only.

**Added:** `CrewTaskWorkflow(GateHost)` and four activities — `prepare_crew` (exclude file and the
first brief), `run_crew_turn` (a thin wrapper over the existing harness path), `read_round` (read and
validate the round's files), `checkpoint_round` (`git add -A` plus the commit).

**One easily missed external consumer:** per finding 12, `benchmarks/drift.py:71` filters on
`activity != "run_coding_task"` and must learn the crew turn's activity name, or drift is silently
uncomputed for crew tasks.

**Tests.** The 2625 lines across 15 `test_herdr_*.py` files are mostly about transport:
`test_herdr_client` (a fake UDS), `test_herdr_protocol`, `test_herdr_driver` (918 lines of state
machine), `test_herdr_recovery`, `test_herdr_diagnoses` (the disagreement table), and
`test_herdr_compose`. They stay on the branch with their subject; only `test_herdr_loader` and
`test_herdr_worktree` come across. The replacement sits at three levels:

| Level | How | Covers |
|---|---|---|
| pure functions | plain `pytest` | the round decision, all four brakes, the ADR-6 collision, layout and round-file validation |
| workflow | `WorkflowEnvironment.start_time_skipping`, marker `temporal` | the deadline race, the escalation budget, `deferred` → gate → resume, an abandoned attempt's cost, replay after worker loss |
| live contract | marker `crew`, replacing `herdr` | one round against a real CLI |

The cost is named rather than assumed: `pyproject.toml:43` warns that the existing 22 `temporal`
tests "contend and freeze the suite when run together", and these add to that count. It remains far
cheaper than the three-live-pane races today's tests do not cover at all.

**Acceptance is a reproduced measurement, not a green suite.** E-87b §7.2 records a real baseline from
2026-08-30 on the branch: case `herdr-probe`, cell `code | herdr | zai-coding-plan/glm-5.3`, three
attempts, each
leaving a cost record (7235 in / 923 out; 5550 / 765; similar) and a well-formed prose note, with
the last attempt correctly escalating instead of inventing when it found the environment broken.

Acceptance is that `code | crew | zai-coding-plan/glm-5.3` on `crew-probe` — the same case, renamed
— matches that baseline on
its **mechanical** signals: three attempts each drive a real round, each leaves a cost record with
non-null token counts, each produces a `notes-v1` note that validates, and the broken-environment
attempt still escalates rather than fabricating. Quality is explicitly **not** a criterion here —
that run scored 0.000 for an environment reason E-87b §7.2 identifies (the retry brief references
`/srv/scratch-repos/...`, a worker-only mount the pane could not see), and that gap belongs to the
benchmark case, not to this design. Comparing quality across the two would measure the mount.

Two defects that run exposed are removed by construction: `agent_name_taken` on retries (no pane
names exist) and work lost to `idle_timeout` (per-round checkpoints, §2).

**Known losses and one open risk.** Lost deliberately: live attachment to an agent's terminal
(accepted as a non-requirement), and opencode's per-turn lifecycle authority, which existed only to
backstop a heuristic that is gone. Open: `CursorHarness` parses cost under
`# ASSUMPTION: may be absent` (`adapters.py:849`), so a cursor role may yield `cost_incomplete`. Not
a blocker; recorded rather than glossed.

## Migration

E-87's code reached a working, measured state on `feat/e-87-herdr-harness` and was never merged:
`main` is at `2f0dc2f`, the branch is 39 commits ahead of it, and 38 of those are herdr. The one
that is not — `d53b884`, a planner retry fix — has been cherry-picked to `main` already.

**The branch is not merged and not deleted.** Merging it to delete it a step later would put a
stateful container, a UDS socket, and a Dockerfile stage into `main` for a capability `main` does
not gain: the only reachable layout is `rounds.max: 1, splits: []`, one opencode session wrapped in
a container — strictly less than the `OpenCodeHarness` subprocess path `main` already has. Deleting
the branch would throw away the only place the E-87b measurement can be reproduced live. So it stays
as an archived ref, and this spec quotes it.

**Three reviewable steps on `feat/e-88-crew`, cut from `main`:**

1. **The spine.** `CrewTaskWorkflow` with a single-role crew (lead only), the four activities,
   heartbeat-details resume, and the brakes. The carry-across table's `crew/`, `loader.py`,
   `worktree.py`, and `RoundRecord` land here. Acceptance: the `crew-probe` baseline above, matched
   by a one-role crew. This is the step that proves the mechanism against a measurement.
2. **The crew.** The critic role, parallel turns, `read_round` validation of `advisor.md` /
   `review.json` / `question.json`, the ADR-6 extension in `validate_run_roles`, the loader's
   model-resolvability boot check, `GateHost` and the inbox disjunct, and `PendingDecision`'s
   `parent_run_id`.
3. **The seams.** `drift.py`'s activity name, the `crew` pytest marker, the worker image gaining
   `claude_code`, and the retargeted `test_crew_{loader,worktree}.py`.

There is no removal step, because there is nothing on `main` to remove.

The reviewer role is deliberately outside all three, per §5 and finding 10: it is unblocked by
installing `cursor-agent` or writing an `agy` adapter, and should be tracked as its own item rather
than carried as an assumption inside this one.
