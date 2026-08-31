# E-88 step 2: the crew — critic, fence, and gates

**Date:** 2026-08-31
**Roadmap:** `E-88` step 2 of 3.
**Parent spec:** `2026-08-31-crew-temporal-native-multi-agent-design.md`. Its §1, §2, §5 and §6 are
the design; this addendum records only what reading step 1's *landed code* changed about them, and
why. Where the two disagree, this document wins for step 2 and says so explicitly.
**Baseline:** `feat/e-88-crew` at `e5fad5a`. Step 1 is accepted: `bench-crew-probe-1788180917` drove
the whole pipeline — code through qa/review/merge/handoff/deploy, 6 tasks, 11 real crew-turn
attempts, valid `notes-v1` notes.
**Requirements:** No FR moves. No change to the stage DAG, the gate semantics, or the artifact
contracts.

## Findings

These come from reading what step 1 shipped, not from the parent spec.

1. **The gate has no live trigger yet.** `run_crew_turn` (`crew/activities.py:168`) fails closed on
   any containment or grants — `CREW_CONTAINMENT_UNSUPPORTED`, with a comment saying step 2 wires
   the fence. But `run.deferred` exists only because a containment `escalate` rule matched. So §6's
   entire HITL path is unreachable until the fence is wired, and building the gate first would mean
   testing it against a fabricated `deferred` result and nothing else.

2. **A critic at `rounds.max: 1` is spend with no consumer.** `crew/layouts/code.yaml` ships
   `max: 1`, reasoned as "the factory already retries". The critic writes `advisor.md`, and the only
   thing that can read it is the *next* round's brief. At `max: 1` there is no next round.

3. **The critic's vendor is already a YAML field; the check that makes a wrong value loud is not.**
   `CrewRole` carries `harness` and `model`, and `validate_crew` verifies the skill file exists — but
   nothing verifies the role's harness can actually resolve its model. §5 friction 1 named this check
   and step 1 did not land it. Separately, the worker image installs opencode only, so
   `harness: claude_code` in a role file is currently unreachable; the parent spec lists that image
   change as step 3.

4. **The ADR-6 crew expansion cannot sit where the parent spec puts it.** `_cell_config`
   (`benchmarks/workflow.py:41`) runs inside the workflow sandbox — the module's own docstring says
   "workflow code never touches the filesystem" — so it cannot read `crew/layouts/*.yaml` to expand a
   crew into `role_models`.

5. **`answer_question` is not on `GateHost`.** It is defined on `FeatureWorkflow`
   (`feature.py:963`). §6 routes `question.json` to "`PendingDecision` → inbox → `answer_question`",
   which for a second workflow means duplicating the clarify signal, its pending registry, and its
   dedup rule — the exact "two copies that hold only while they agree" shape `GateHost` was extracted
   to prevent.

6. **Per-role write confinement needs no new predicate.** The claude hook already receives
   `--worktree` as an explicit argument built from `req.cwd` (`adapters.py:388`), and
   `path_outside_worktree` is exactly `_abs_under(target, worktree)` (`containment.py:206`).
   Confining a role to a subtree is therefore a change of *argument*, not a fifth predicate and not a
   policy schema bump — which matters, because `Predicate`'s own docstring says a fifth member is
   "deliberately not an expression language".

7. **The inbox query has a second consumer.** `dashboard/fleet.py:102` also calls
   `list_open_run_ids`. Widening its visibility filter to include crew children changes the fleet
   view too, which the parent spec does not mention.

8. **Token counts were null on every code record, not only crew ones.** Fixed at `e5fad5a` ahead of
   this step, because "each attempt leaves a cost record with non-null token counts" is a literal
   acceptance criterion and a green suite was hiding a failed one.

## Design

### §A The fence, per role

`CREW_CONTAINMENT_UNSUPPORTED` and its fail-closed branch are removed. `run_crew_turn` resolves
containment the way `run_coding_task` already does (`activities.py:502`): load the policy (fail
closed), refuse when `not harness.containment` (ADR-17), `apply_containment(policy, req, grants)`,
refuse on `rules_unenforceable` under `containment_strict`.

Per-role confinement (parent §1: the lead may write repository files, non-lead roles are confined to
`.workspace/orchestration/<layout>/`) is implemented per finding 6:

- `HarnessRequest` gains `write_root: str | None`, defaulting to `None`.
- `_hook_command` passes `--worktree <write_root or cwd>`.
- A non-lead turn sets `write_root` to its orchestration directory while `cwd` stays the worktree, so
  the role can **read** the repository and the diff it is criticising, and can **write** only under
  the protocol tree.

No new predicate, no policy version bump, and the shipped `no-out-of-worktree-write` rule does the
work unchanged.

**The honest limit.** `no-out-of-worktree-write` is `layer: hook`, and `OpenCodeHarness` compiles only
native-layer rules. So a role on opencode is not confined by this mechanism at all: the rule lands in
`rules_unenforceable`, and under `containment_strict` the turn refuses. This is not new — it already
governs an opencode *lead* today — but it becomes a statement about the crew's composition, which is
where parent finding 6 said it belonged. Consequence, stated plainly: **in a contained run, a
non-lead role wants a harness with a hook layer.** That is an argument for the critic being
`claude_code`, and it is checked when the crew loads rather than discovered mid-task.

### §B The critic and the round

`crew/layouts/code.yaml` becomes `crew: [coder, critic]` with `rounds.max: 2`. This reverses step 1's
`max: 1` decision, and the comment recording that decision is replaced by the reason it changed
(finding 2) rather than deleted.

The round is parent §2's shape with the reviewer slot left unbuilt:

```
lead turn -> critic turn -> read_round -> decide
```

**Not `asyncio.gather` yet.** Parent §2 draws `critic || reviewer` because two independent opinions
should not serialise. With one non-lead role there is nothing to parallelise, and `workflow.wait`
against the deadline timer already handles racing a turn. The fan-out arrives with the reviewer,
whose own arrival is gated on a third vendor (parent §5, finding 10). Shipping an untested `gather`
shape now buys nothing.

`read_round` gains three schemas beside `notes-v1`, under the same untrusted-input discipline
`RoundNote` already follows — exact schema, size-capped, an unknown `schema` value is a hard error,
contents are data and never instructions:

| File | Schema | Written by | Read for |
|---|---|---|---|
| `notes.md` | `notes-v1` | lead | `RoundRecord.note_summary`, `HarnessRunResult.summary` |
| `advisor.md` | `advisor-v1` | critic | round N+1's brief |
| `review.json` | `review-v1` | critic | `RoundRecord.verdict`, round N+1's brief |
| `question.json` | `question-v1` | any role | §C's `crew_question` gate |

`review-v1` carries a verdict plus findings. Its verdict populates `RoundRecord.verdict`, a field the
model already declares and nothing currently writes.

Round 2's brief carries the critic's findings **verbatim, inside a delimited block labelled as agent
output**. They are data, exactly like every other model-written file the protocol reads.

`require_reviewer_approval` stays `false` and stays unimplemented: it describes the reviewer, and the
reviewer is not in this step.

### §C Human-in-the-loop: two gates, one mechanism

`CrewTaskWorkflow` subclasses `GateHost`, per parent §6 — the gate stays where the round state is, so
an approval does not rebuild it.

**`tool_approval`** is parent §6 unchanged: `run.deferred is not None` → `self._gate("tool_approval",
..., default_policy=HARD)` → re-run the turn with grants and the resumed session. E-17's rules are
preserved verbatim — the approval resume costs neither a round nor a fix attempt,
`max_tool_escalations` caps, and the final resume exists only to deliver the denial.

**`crew_question`** departs from parent §6's letter, per finding 5. Rather than duplicate
`answer_question` into a second workflow, a validated `question.json` opens a gate: the question text
and its evidence become the gate's `spec_summary`, the human's answer arrives as `decision.comments`,
and the next round's brief carries it. One signal (`submit_gate_decision`), nothing new in
`GateHost`, nothing new in the inbox, and the "first decision for (gate, round) wins" rule is
inherited rather than restated.

What does **not** change: parent §6's classification policy stands — settled upstream is answered by
`brief.md`; a trade-off between knowable options is answered by the critic; a genuine gap in user
intent goes to a human. So does its guard: a question carrying neither a class nor evidence is not a
question, and is rejected as `protocol_violation` rather than forwarded. The escalation budget stays
at two per crew, a counter in durable workflow state; exhaustion ends the crew as `intent_gap`.

### §D ADR-6 and the boot checks

`check_crew_families(lead_model, roles)` lands in `crew/loader.py` as a **pure function** — no I/O, so
it is unit-testable and cannot drift between call sites. The rule is parent §5's: every non-writing
crew role must differ in **model family** from that crew's lead.

Two call sites, because finding 4 rules out the parent spec's single one:

1. The `load_crew` activity. It already fails closed when the lead's model did not come through a
   layer ADR-6 validates (`CREW_MODEL_UNRESOLVED`), and it always sees the run's *effective* lead
   harness and model after `resolve_crew_roles`. This site can never be bypassed.
2. A client-side pre-flight in `benchmarks/cli.py` and `cli_roles.build_role_overrides`, where the
   crew tree is readable. This is what keeps parent §5's promise that "a run whose sweep collides
   never starts".

Site 1 is the guarantee; site 2 is the early warning. One implementation serves both, so there is no
second policy and no way for the two to disagree.

**The model-resolvability boot check** (parent §5 friction 1) lands in `validate_crew`: for every role
in a layout, its harness can resolve its model. This is what turns the critic's vendor into a real
YAML knob — a `harness`/`model` pair the container cannot serve kills the worker at startup with a
message naming the role, instead of failing after the lead has already spent.

**The worker image gains `claude_code`,** pulled forward from step 3, so both values of that knob are
reachable and §A's "a non-lead role wants a hook layer" is not advice nobody can take. Which string
`crew/roles/critic.yaml` ships with is settled at implementation time by running the resolvability
check against the built image — it is a one-line edit either way, which is the whole point of the
knob.

### §E The inbox and `parent_run_id`

Parent §6 says the visibility filter gains one disjunct. It cannot simply gain one, per finding 7:
`_OPEN_FEATURE_QUERY` (`channels/inbox.py:66`) is a module constant with two callers that want
different answers. So the constant becomes a builder, and each caller states what it wants:

```python
def _open_runs_query(*types: str) -> str:
    disjuncts = " OR ".join(f"WorkflowType='{t}'" for t in types)
    return f"({disjuncts}) AND ExecutionStatus='Running'"
```

`list_open_run_ids(client, *types)` defaults to `("FeatureWorkflow",)` — the behaviour every existing
caller already has, so adding the parameter changes nothing on its own. The inbox passes
`"FeatureWorkflow", "CrewTaskWorkflow"`; `dashboard/fleet.py` passes nothing and keeps the narrow
view. Everything downstream operates on handles and is unchanged.

`PendingDecision`'s four variants each gain `parent_run_id: str | None = None`. `GateHost.__init__`
gains `self._parent_run_id = None`; `_gate` passes it to `gate_pending`; `CrewTaskWorkflow.run` sets
it from `workflow.info().parent`. `FeatureWorkflow` leaves it `None`. The renderer groups by it,
falling back to the handle id — a field rather than a parse of the workflow-id prefix, because the
prefix is a fact about ids and not a contract for display.

The reason fleet keeps the narrow view: the fleet page lists **runs**, and a crew child is part of a
run rather than a run of its own. The inbox is the opposite — it lists what a human owes a decision
on, and a crew's gate is exactly that. Widening one caller by widening a shared constant would have
silently changed the other, which is the whole reason for the builder above.

### §F Testing and acceptance

| Level | Subject |
|---|---|
| pure | `check_crew_families`; the resolvability check; `advisor-v1` / `review-v1` / `question-v1` validation *and* rejection; `write_root` confinement; the round decision with a critic |
| workflow (`temporal`) | `deferred` → `tool_approval` gate → resume; the `crew_question` gate and its answer reaching round 2's brief; the escalation budget exhausting to `intent_gap`; an abandoned attempt's cost |
| live (`crew`) | one contained two-role round against real CLIs |

**Acceptance** is the parent spec's, tightened by what this step adds: `crew-probe` run **with
containment enabled** and the two-role crew — three attempts, each driving two real rounds, each
leaving an `advisor.md` and a round-2 note that validates, each leaving a cost record with non-null
token counts, and at least one `deferred` escalation reaching the inbox grouped under its parent run.

Quality is explicitly not a criterion, for the reason the parent spec gives: that case's score
measures a worker-only mount, not the design.

## Scope

**In:** §A through §F above, plus the `claude_code` image line pulled forward from step 3.

**Out, and staying out:**

- The **reviewer** role and the `critic || reviewer` fan-out. Gated on a third vendor per parent §5
  and finding 10; tracked as its own item.
- `require_reviewer_approval`'s behaviour, which belongs to the reviewer.
- The rest of step 3 — `drift.py`'s crew activity name, the `crew` pytest marker, and the retargeted
  `test_crew_{loader,worktree}.py`.
- **Worker-Specific Task Queues.** Session resume still requires the CLI's session store to be
  reachable by whichever worker takes a retry. Recorded as a known boundary in parent §3, not
  scheduled here.
