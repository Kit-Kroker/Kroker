# E-17 — approval escalation through the existing gate machinery (FR-703 / FR-301)

| | |
|---|---|
| Date | 2026-07-25 |
| Status | Approved design |
| Roadmap | E-17 — §9.4 |
| Anchors | FR-703 (`pre_tool` hook), FR-301/FR-302 (gate policy + idempotent signals), NFR-5, ARCHITECTURE §10 (risk classing lives in the hook) |
| PRD | **No new FR.** FR-703 mandates the hook; FR-301 gains the escalation clause |
| ADR | **ADR-17 extended** — `defer` as the escalation carrier; the solo-only constraint recorded |
| Builds on | E-15/E-16 (`2026-07-24-harness-containment-pre-tool-hook-design.md`) |
| Out of scope | Network-level egress (**E-21**); notification/reminder/fallback-approver for the raised gate (**E-9**); the dashboard and MCP surfaces that would render it (**E-10/E-11**) |

## Problem

E-16 landed deny-by-rule. Every containment outcome is therefore binary and
final: a rule either never fires or always refuses. Eve's `needsApproval` — and
FR-301's whole premise — is that some operations are a *maybe*, and the person
who can settle it is the human the gate machinery already knows how to reach.

§9.4's framing is that this is **one mechanism, not two**: "a denial is a policy
decision, an approval request is a gate." Growing a second approval subsystem
beside FR-301/FR-302 would be the failure mode. The gate already exists, is
durable, is idempotent per `(gate, round)`, and is first-decision-wins.

E-17's blocker used to be that a tool call happens inside a child process during
an activity, and **an activity cannot await a workflow signal.** That blocker is
gone, and §0 is why.

## 0. Verified live against claude 2.1.220

Checked before the design settled, in the manner of E-15 §0. The installed CLI
is **2.1.220**; `ClaudeCodeHarness.expected_version` pins `2.1.218` and E-15
verified against `2.1.219` — the drift E-24 exists to catch has moved again.

- **`permissionDecision` accepts `allow | deny | ask | defer`.** An unknown
  value raises inside the CLI, so the vocabulary is closed.
- **`defer` is print-mode only.** In interactive mode the CLI logs
  `returned permissionDecision=defer in interactive mode; ignoring (defer is
  print-mode only)` and moves on. We run `-p`; this is our mode.
- **A honoured defer terminates the run cleanly**, emitting a `result` event
  with `stop_reason: "tool_deferred"`, `subtype: "success"`, `result: ""`, and a
  structured `deferred_tool_use: {id, name, input}`. **This is the finding the
  whole design rests on:** no process is held during the human wait, so the
  activity returns in the ordinary way and the *workflow* owns the wait.
- **`--resume` replays the deferred call** and re-runs the hook against it. The
  CLI even carries a `terminal_reason: "tool_deferred_unavailable"` for
  *"Deferred tool resume: tool 'X' is no longer available (MCP server
  disconnected or tool removed)"* — proof that resume is defer's designed
  counterpart, and that the replay is keyed on the original `toolUseID`.
- ⚠️ **`defer` is solo-only.** When the assistant message carries more than one
  `tool_use` block, the CLI logs `returned permissionDecision=defer but N tool
  calls are in this batch; ignoring (defer is solo-only — siblings would be
  orphaned on resume)` and **breaks out of the hook loop**, letting the call
  fall through to the ordinary permission pipeline — which under our
  `--permission-mode acceptEdits --allowedTools Read,Edit,Write,Bash` **allows
  it**. A fail-open path inside a fail-closed subsystem; §3 is how we close it.
- **The `PreToolUse` payload is
  `{session_id, transcript_path, cwd, prompt_id, permission_mode, agent_id,
  agent_type, effort, hook_event_name, tool_name, tool_input, tool_use_id}`.**
  Two consequences: it carries **no sibling/batch information**, so the hook
  cannot learn it is in a batch from the payload alone; but it *does* carry
  `transcript_path` and `tool_use_id`, which is enough to find out (§3).

## Decisions (settled during brainstorming)

1. **`defer` carries the escalation.** The activity returns, the workflow gates,
   the activity resumes. No activity awaits a signal; no parallel mechanism.
2. **The solo-only fail-open is closed in the hook**, by counting siblings in
   the transcript, so we never emit a `defer` the CLI would discard (§3).
3. **An approval covers exactly one call** — bound to `tool_use_id` plus an
   input digest, never a standing waiver.
4. **Every non-approve path resumes with a rejecting grant** and the task
   continues. Rejection refuses a call; it does not throw away a session.
5. **One new policy field, `action: deny | escalate`**, defaulting to `deny`;
   the shipped asset promotes `no-out-of-worktree-write`, so the mechanism runs
   on the default policy rather than only in tests.
6. **Degradation is always toward deny** — batched, capped, uncapable harness,
   unreadable transcript, internal error: all deny.

## Design

### The shape

```
run_coding_task ──► claude -p … --settings S --grants G
                      │
    hook: escalate match, solo, no grant ──► defer
                      │
                    result{ stop_reason: "tool_deferred",
                            deferred_tool_use:{id,name,input} }
                      ▼
_dev_task sees run.deferred ──► self._gate("tool_approval", round=N)   ← FR-301/302, unchanged
                      ▼
run_coding_task(session_id=…, grants=[ToolGrant(approved=…)])
                      │
    hook: grant matches ──► allow / deny(with the human's reason)
                      ▼
                  …session continues…
```

### 1. Policy — one new field, one new invariant

```yaml
rules:
  - id: no-out-of-worktree-write
    layer: hook
    action: escalate            # NEW; default is deny
    tools: [Write, Edit, NotebookEdit]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."
```

`Action(str, Enum)` with `DENY`/`ESCALATE`; `Rule.action: Action = DENY`, so
every rule that landed with E-16 keeps its exact behaviour. `Verdict` gains the
matched rule's `action`. `evaluate()` keeps its shape and stays pure.

**Load-time invariant: `action: escalate` on a `layer: native` rule is a
`ContainmentError`.** E-15 §0 verified that `permissions.deny` strictly beats a
hook `allow`, so a natively-compiled rule could never be approved — the gate
would be theatre and the human's "yes" would silently not apply. The loader
refuses the policy rather than shipping an approval that cannot work.

The shipped asset needs no other change: `no-out-of-worktree-write` is already
`layer: hook`, and the three hard denials (`rm -rf`, agent-config rewrites,
non-allowlisted egress) stay `deny`. Promoting the out-of-worktree write is the
principled choice — an agent reaching a sibling path is sometimes right, whereas
a recursive force-delete is not a maybe.

### 2. Grants — single-use falls out of the CLI's own semantics

```python
class ToolGrant(BaseModel):
    tool_use_id: str          # the deferred call's own id
    tool: str
    input_digest: str         # sha256 over canonical json of tool_input
    rule_id: str
    approved: bool            # False = rejected / timed out / capped
    reason: str = ""          # the human's words; reaches the model verbatim
```

`digest_tool_input()` lives in `containment.py` and is used by **both** the
activity and the hook, so the two can never disagree about canonicalisation.

Single-use needs no state, no expiry, and no bookkeeping in the stateless hook:
the resumed replay reuses the **original `tool_use_id`** (§0), while a later,
genuinely new call gets a fresh id and matches nothing — so it escalates again
on its own merits. `input_digest` must also match; it is the belt to that
suspenders, guarding against id reuse.

Grants travel on `CodingTaskInput` and are written to a temp file **outside the
worktree**, by absolute path, for exactly the reason E-15 put the settings file
there: writes inside the worktree are permitted by design, so a grants file
inside it would be a file the agent could forge.

### 3. Hook — the whole decision, six branches

`--grants <path>` joins the existing `--worktree` / `--policy`.

| situation | decision |
|---|---|
| no rule matches | `allow` |
| matched, `action: deny` | `deny` (E-16 behaviour, unchanged) |
| matched, grant approved | `allow` — `[rule-id] approved by <who>` |
| matched, grant rejected | `deny` — `[rule-id] rejected: <comment>` |
| matched, no grant, **solo** | `defer` — reason carries `[rule-id]` |
| matched, no grant, **batched** | `deny` — `[rule-id] escalation unavailable (batched)` |
| transcript unreadable | `deny` — `[rule-id] escalation unavailable (transcript)` |
| any internal exception | `deny` — `[containment-error] …` (E-15, unchanged) |

**A declined escalation must be distinguishable from an ordinary denial**, or
the `BATCHED` outcome of §6 could never be counted: both are plain denials by
the time they leave the hook, and the workflow cannot read the policy to tell
which rules were escalatable. So the hook marks the reason string
`escalation unavailable (<why>)` after the existing `[rule-id] ` prefix, and
`normalise_denials` sets a new `ToolDenial.escalation_declined: bool` when it
sees that marker. The reason string is already the channel the rule id rides
(E-15 §0); this adds one more token to it rather than a second mechanism.

`sibling_count(transcript_path, tool_use_id) -> int` reads the transcript JSONL
**backwards** — the relevant assistant message is the most recent one — finds
the message whose content contains a block with `id == tool_use_id`, and counts
`type == "tool_use"` blocks in it. There is no race: the assistant message must
already be complete for the tool call to dispatch at all.

Two properties are load-bearing. First, **we never emit a `defer` the CLI would
discard**, so the fall-through that allows a batched call is never reached.
Second, **the fallback is deny**, which is precisely E-16's behaviour — the
agent sees a refusal with a reason and adapts, exactly as it does today.

`transcript_path` is an unpinned surface: nothing in the CLI's contract promises
that JSONL shape. That is the cost of this choice, and it is bounded by the
failure mode — an unreadable or unrecognised transcript denies, which is safe,
observable (`batched` outcome, §6), and no worse than not having E-17.

### 4. Adapters — escalation as a declared capability (ADR-17's pattern)

```python
supports_escalation: bool = False                        # base: no
def normalise_deferral(self, stdout) -> DeferredToolUse | None: ...
```

`normalise_deferral` joins `normalise_denials` and `normalise_session`: reading
the deferral off the `result` event is CLI-shaped work, and CLI-shaped work is
the adapter's job. It reads `stop_reason == "tool_deferred"` and
`deferred_tool_use{id, name, input}` from the stream `parse()` already walks —
no new parsing surface, no side channel.

- **claude** → `supports_escalation = True`. `apply_containment` writes the
  grants file when grants are present and adds `--grants <abs path>` to the hook
  command. Escalate rules are excluded from the native `permissions.deny` list
  (§1's invariant makes this structural rather than a convention to maintain).
- **opencode** → `False`. Its escalate rules are `layer: hook` and so already
  land in `rules_unenforceable` (E-15), unchanged.
- **cursor** → `False`, and still fails closed when containment is enabled.

A harness that has a hook but no `defer` — none today — degrades escalate rules
to plain denials rather than dropping them, and says so in
`ContainmentReport.rules_escalatable: list[str]`. Coverage stays computed and
reported rather than assumed, exactly as E-15 §5 established.

### 5. Workflow — where the gate is raised, and why it is safe in wave mode

The escalation loop wraps `run_coding_task` **inside** the existing attempt loop
in `_dev_task` (`feature.py:735-749`):

```python
grants: list[ToolGrant] = []
asked = 0                              # cap counter, per task attempt
while True:
    run = await workflow.execute_activity(
        run_coding_task, CodingTaskInput(..., session_id=session_id,
                                         grants=grants), **_long_act(role_cfg))
    if run.deferred is None:
        break
    session_id = run.session_id
    if asked >= cfg.max_tool_escalations:
        grants = [_rejecting_grant(run.deferred, "escalation cap reached")]
        continue                       # one more resume, only to deliver the deny
    asked += 1
    self._escalation_round += 1
    decision = await self._gate(
        "tool_approval", cfg, round=self._escalation_round,
        context=GateContext(spec_summary=_escalation_summary(task, run.deferred)),
        default_policy=GatePolicy.HARD)
    grants = [_grant_from(run.deferred, decision)]
```

**Two counters, deliberately.** `asked` is local to the task attempt and only
enforces the cap; `self._escalation_round` is workflow-wide and only supplies
gate identity. Collapsing them would either let two concurrent tasks collide on
`(gate, round)` or make the cap global, and neither is what is wanted.

`_escalation_summary()` renders what the human is deciding about — the task id
and title, the rule id and its reason, the tool, and the scrubbed target — into
the `GateContext.spec_summary` the E-6 channel contract already renders, the
same way E-33's budget gate puts its cost table there. No new channel variant
in this increment; `render` keeps working unchanged.

**A single workflow-wide `self._escalation_round` counter.** E-33's budget gate
had to be confined to serial points so gate rounds could not race; escalations
occur inside `_dev_task`, which runs *concurrently across tasks* in wave mode,
so that option is unavailable. It is also unnecessary: workflow code is
single-threaded and the increment order is recorded in history, so a monotonic
counter is replay-deterministic. This lets the gate name stay the stable,
per-project-configurable `"tool_approval"` — a dynamic per-task name would be a
name `cfg.gates` could never match, silently defeating US-4.

**An escalation is not a failure.** It consumes neither a fix attempt nor the
FR-802 `max_session_resumes` budget, and `_should_resume_session` is not
consulted for it. Resuming to deliver an approval is not the same event as
resuming after QA failed; conflating them would both truncate the resume budget
and inflate SC-3's fix-loop metric with human decisions that were never defects.

`PipelineConfig.max_tool_escalations: int = 3` bounds escalations per task. On
exhaustion the loop delivers a rejecting grant instead of asking again, so a
looping agent cannot spam a human or stall the run. There is no separate on/off
flag: `action: escalate` in the asset **is** the switch, under the existing
`containment_enabled`.

### 6. What is recorded

```python
class DeferredToolUse(BaseModel):     # from the CLI, on HarnessRunResult
    tool_use_id: str
    tool: str
    input_digest: str
    rule_id: str
    reason: str
    target: str | None = None         # scrubbed path/command, for the human

class EscalationOutcome(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT  = "timeout"
    CAPPED   = "capped"
    BATCHED  = "batched"              # denied without asking (§3)

class ToolEscalation(BaseModel):
    tool: str
    rule_id: str
    target: str | None = None
    outcome: EscalationOutcome
    decided_by: str = ""
    round: int = 0
```

`HarnessRunResult` gains `deferred: DeferredToolUse | None`. The *decision*
belongs to the workflow, not the activity, so `ToolEscalation` lands on the run
trace as a `TOOL_ESCALATION` event (E-22/E-32 → `events.jsonl` + `report.html`),
plus a stage record for the E-36 heatmap and a count on `SessionDigest` so
clean-green runs still report escalations.

`ToolDenial` gains `escalation_declined: bool = False` (§3). The workflow emits
`APPROVED`/`REJECTED`/`TIMEOUT`/`CAPPED` from the gate decision it made — with
`decided_by` taken straight from `GateDecision.decided_by`, so `timeout` is
distinguishable from a human `reject` — and emits `BATCHED` from each
`run.denials` entry carrying `escalation_declined`, for which no gate was ever
raised and `decided_by` is empty.

`BATCHED` is deliberately its own outcome rather than folded into `REJECTED`:
it is the **measurable size of the solo-only hole in real runs**, instead of a
limitation asserted in prose. `target` is scrubbed on the same path
`ToolDenial.target` already uses, before it reaches a gate context a human reads.

### 7. Error handling

| failure | behaviour |
|---|---|
| `action: escalate` on a `layer: native` rule | `ContainmentError` at load → refuse to start |
| harness has a hook but no `defer` | escalate rules degrade to deny; recorded in `rules_escalatable` |
| harness has no hook at all | already `rules_unenforceable` (E-15), unchanged |
| batched escalate-match | deny, `BATCHED` recorded via `escalation_declined`, no gate raised |
| transcript unreadable | deny, same `escalation_declined` marker and `BATCHED` record |
| hook internal exception | deny (E-15's fail-closed rule, unchanged; no marker) |
| gate times out | existing `_gate` REJECT → rejecting grant → session continues |
| escalation cap reached | rejecting grant, no gate raised, `CAPPED` recorded |
| `normalise_deferral` raises | best-effort like `normalise_denials`; no deferral → no escalation |
| deferred tool gone on resume | CLI's `tool_deferred_unavailable`; ordinary attempt failure, existing fix loop |
| containment disabled | today's path exactly; no new code path |

### 8. Testing

- **Pure tables** for `Action` parsing and the `escalate`+`native` refusal;
  grant matching (id match, digest mismatch, no match); `sibling_count` over
  fixture transcripts (solo, batched, id absent, malformed line, truncated file).
- **Hook contract tests** — stdin→stdout across all six branches of §3,
  including exception-becomes-deny and unreadable-transcript-becomes-deny.
- **Adapter tests** — assert the emitted grants file contents and the
  `--grants` argument; assert `normalise_deferral` against a **pinned
  `result`-event fixture** captured from the real CLI, so the parse is tested
  against bytes claude actually wrote rather than bytes we imagined.
- **Marker round-trip** — the hook's `escalation unavailable (<why>)` reason
  survives into `ToolDenial.escalation_declined`, asserted end-to-end from hook
  stdout through `normalise_denials`. Without this the `BATCHED` count is
  silently always zero, which is the failure mode E-27 was bitten by.
- **Workflow test** — a fake `run_coding_task` returning one deferral then a
  clean run; assert the gate is raised with the right `(gate, round)`, that the
  resume carries the grant and the same `session_id`, and **that the
  fix-attempt and session-resume counters are untouched**.
- **Cap and reject paths** — assert no gate is raised past the cap, and that a
  rejecting grant still reaches the harness (the deny must be *delivered*, not
  merely recorded).
- **One live test**, skippable in CI in the style of `test_containment_live.py`:
  a real `claude -p` writing outside its worktree, deferring, and resuming to a
  grant.

## Limitation, stated plainly

The solo-only hole is **narrowed to a recorded deny, not eliminated.** A batched
escalate-match is refused without asking anyone, so an agent whose legitimate
operation always arrives batched can never obtain approval for it. This is
countable via the `BATCHED` outcome; if it shows up in real runs the fix is
upstream — nudging the model toward solo calls — not more hook cleverness.

Unchanged from E-15: this is tool-level containment, not network-level. E-17
adds a human to the loop; it does not add a tier. **E-21** is still the
OS/container tier, and **E-9** is still what makes a raised gate reach anybody
who is not already watching a terminal.

## Roadmap edits this implies

- **E-17** `[x]`; §9.4 preamble updated — the hook now carries both halves
- **FR-703** note extended: deny-by-rule ✅, approval escalation ✅, egress
  tool-level only
- **FR-301** gains the escalation clause (a tool call can raise a gate)
- **ARCHITECTURE §10** — "risk classing lives in the hook" now includes approval
- **ADR-17** extended: `defer` as the escalation carrier; solo-only recorded as
  a constraint of the mechanism, not a bug in ours
- **E-24** version drift is now **2.1.218 pinned vs 2.1.220 installed** — it
  moved again during this session's verification
