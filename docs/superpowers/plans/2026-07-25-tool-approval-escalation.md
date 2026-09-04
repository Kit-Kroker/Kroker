# E-17 Tool-Approval Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A containment rule marked `action: escalate` suspends the harness at the offending tool call, raises a real FR-301/FR-302 gate, and resumes the same session with a single-use grant carrying the human's decision.

**Architecture:** claude's `permissionDecision: "defer"` ends the `-p` run with `stop_reason: "tool_deferred"` and a structured `deferred_tool_use`, so no activity ever awaits a signal — the *workflow* owns the durable wait using the gate machinery that already exists, then re-invokes `run_coding_task` with `--resume` and a grant file the hook reads. Because `defer` is silently discarded when the call is batched with siblings, the hook counts siblings in the transcript and emits `defer` only when solo, denying otherwise.

**Tech Stack:** Python 3.14, Pydantic v2, Temporal (`temporalio`), pytest / pytest-asyncio, PyYAML. Windows/win32 host; the hook is executed by claude through Git Bash.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-25-tool-approval-escalation-design.md`. Read it before Task 1.
- **Verified CLI:** claude **2.1.220**. `permissionDecision` ∈ `allow | deny | ask | defer`; `defer` is **print-mode only** and **solo-only**; a honoured defer yields `result` with `stop_reason: "tool_deferred"`, `subtype: "success"`, `deferred_tool_use: {id, name, input}`.
- **Fail closed, always.** Every unresolvable situation denies: batched call, unreadable transcript, missing grant, internal exception. Never allow on doubt (ADR-17).
- **`hook.py` stays import-light.** It must not import `temporalio`, `pydantic_ai`, or `sdlc.cli`. It runs once per tool call.
- **`containment.py` stays pure.** No subprocess, no CLI knowledge, no Temporal.
- **Default behaviour must not change.** `containment_enabled` defaults `False`; `Rule.action` defaults `DENY`. Every existing test must still pass unchanged after every task.
- **Never widen a rule.** Escalation only ever turns a *denial* into a *question*; it never makes a previously-allowed call denied, nor a denied rule permanently allowed.
- Run the full suite with `python -m pytest tests/ -q` before each commit.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/sdlc/harness/containment.py` | Pure policy: `Action`, `Verdict.action`, the escalate/native invariant, grant digest + matching, the declined-reason marker | 1, 3 |
| `policy/containment.yaml` | The FR-703 asset; promotes `no-out-of-worktree-write` to `escalate` | 1 |
| `src/sdlc/models.py` | Workflow-visible contracts: `DeferredToolUse`, `ToolGrant`, `EscalationOutcome`, `ToolEscalation`, `ToolDenial.escalation_declined`, `HarnessRunResult.deferred`, `ContainmentReport.rules_escalatable`, `SessionDigest.escalations`, `PipelineConfig.max_tool_escalations` | 2 |
| `src/sdlc/observability/trace.py` | `RunEventKind.TOOL_ESCALATION` | 2 |
| `src/sdlc/harness/hook.py` | The per-call decision: sibling counting, grant honouring, six branches | 4 |
| `src/sdlc/harness/adapters.py` | CLI-shaped work: grants file, `--grants`, `normalise_deferral`, `escalation_declined`, `supports_escalation` | 5 |
| `src/sdlc/activities.py` | `CodingTaskInput.grants`, threading grants into compile, populating `result.deferred` | 6 |
| `src/sdlc/workflows/feature.py` | The escalation loop, the two counters, the gate, the trace/benchmark records | 7 |

Test files, in order of the tasks that create them: `tests/test_containment_policy.py` (extended), `tests/test_containment_evaluate.py` (extended), `tests/test_containment_models.py` (extended), `tests/test_containment_grants.py` (**new**), `tests/test_containment_hook.py` (extended), `tests/test_containment_adapters.py` (extended), `tests/test_containment_activity.py` (extended), `tests/test_tool_approval_gate.py` (**new**), `tests/test_containment_live.py` (extended).

---

## Task 1: Policy — `action: deny | escalate` and the invariant that keeps approval honest

**Files:**
- Modify: `src/sdlc/harness/containment.py` (add `Action`, `Rule.action`, `Verdict.action`, the loader invariant)
- Modify: `policy/containment.yaml` (promote one rule)
- Test: `tests/test_containment_policy.py`, `tests/test_containment_evaluate.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `Action.DENY` / `Action.ESCALATE` (a `str`-valued `Enum` in `sdlc.harness.containment`); `Rule.action: Action` defaulting to `Action.DENY`; `Verdict.action: Action` defaulting to `Action.DENY`; `load_policy` raising `ContainmentError` for `action=escalate` with `layer=native`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_containment_policy.py`:

```python
def test_rules_default_to_deny(tmp_path):
    """Every rule that landed with E-16 keeps its exact behaviour."""
    p = tmp_path / "p.yaml"
    p.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    policy = load_policy(p)
    assert policy.rules[0].action is Action.DENY


def test_escalate_action_parses(tmp_path):
    p = tmp_path / "p.yaml"
    p.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    action: escalate\n"
        "    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    assert load_policy(p).rules[0].action is Action.ESCALATE


def test_escalate_on_a_native_rule_is_refused(tmp_path):
    """permissions.deny strictly beats a hook allow (E-15 §0), so a natively
    compiled rule could never be approved — the gate would be theatre."""
    p = tmp_path / "p.yaml"
    p.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: native\n    action: escalate\n"
        "    tools: [Bash]\n"
        "    predicate: command_matches\n    patterns: ['rm -rf *']\n"
        "    reason: nope\n",
        encoding="utf-8",
    )
    with pytest.raises(ContainmentError, match="escalate"):
        load_policy(p)


def test_shipped_asset_escalates_only_the_out_of_worktree_write():
    """The mechanism must run on the DEFAULT policy, not only in tests
    (E-27's lesson), and the hard denials must stay hard."""
    policy = load_policy(Path(__file__).parents[1] / "policy" / "containment.yaml")
    by_action = {r.id: r.action for r in policy.rules}
    assert by_action["no-out-of-worktree-write"] is Action.ESCALATE
    assert by_action["no-recursive-force-delete"] is Action.DENY
    assert by_action["no-agent-config-write"] is Action.DENY
    assert by_action["egress-allowlist"] is Action.DENY
```

Add to that file's imports (merge with what is already imported there):

```python
from pathlib import Path

import pytest

from sdlc.harness.containment import Action, ContainmentError, load_policy
```

Append to `tests/test_containment_evaluate.py`:

```python
def test_verdict_carries_the_matched_rules_action(tmp_path):
    policy = Policy(
        version=1,
        rules=[
            Rule(
                id="esc",
                layer=ContainmentLayer.HOOK,
                action=Action.ESCALATE,
                tools=["Write"],
                predicate="path_outside_worktree",
                reason="scoped",
            ),
        ],
    )
    v = evaluate(policy, "Write", {"file_path": "/etc/passwd"}, str(tmp_path))
    assert v.allow is False
    assert v.action is Action.ESCALATE


def test_allow_verdict_action_defaults_to_deny(tmp_path):
    """An allow verdict has no matched rule; `action` must not imply one."""
    policy = Policy(version=1, rules=[])
    v = evaluate(policy, "Write", {"file_path": f"{tmp_path}/a.py"}, str(tmp_path))
    assert v.allow is True
    assert v.action is Action.DENY
```

Ensure `Action` is in that file's `sdlc.harness.containment` import list.

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest tests/test_containment_policy.py tests/test_containment_evaluate.py -q
```

Expected: FAIL with `ImportError: cannot import name 'Action'`.

- [ ] **Step 3: Implement**

In `src/sdlc/harness/containment.py`, add after the `Predicate` enum:

```python
class Action(str, Enum):
    """What a matched rule does. DENY is E-16's behaviour and the default;
    ESCALATE raises a human gate through FR-301/FR-302 (E-17)."""

    DENY = "deny"
    ESCALATE = "escalate"
```

Add the field to `Rule` (immediately after `layer`):

```python
action: Action = Action.DENY  # E-17; DENY keeps every E-16 rule as-is
```

Add the field to `Verdict`:

```python
class Verdict(BaseModel):
    allow: bool
    rule_id: str | None = None
    reason: str | None = None
    action: Action = Action.DENY  # the matched rule's action; DENY when allowed
```

In `evaluate`, carry it on the deny branch:

```python
if _rule_denies(rule, tool, tool_input, worktree):
    return Verdict(allow=False, rule_id=rule.id, reason=rule.reason, action=rule.action)
```

In `load_policy`, after `rules.append(Rule.model_validate(entry))` succeeds, enforce the invariant. Place it inside the loop, right after the append:

```python
if rules[-1].action is Action.ESCALATE and rules[-1].layer is ContainmentLayer.NATIVE:
    raise ContainmentError(
        f"rule {rid!r} in {p} sets action: escalate with layer: "
        f"native. A native `permissions.deny` strictly beats a hook "
        f"allow, so an approved call would still be blocked — the "
        f"gate would be theatre. Escalating rules must be layer: hook."
    )
```

In `policy/containment.yaml`, add the field to the first rule only:

```yaml
  - id: no-out-of-worktree-write
    layer: hook                 # needs per-call path resolution
    action: escalate            # E-17: a maybe, not a never — a human decides
    tools: [Write, Edit, NotebookEdit]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_containment_policy.py tests/test_containment_evaluate.py -q
python -m pytest tests/ -q
```

Expected: all pass. The full suite matters here: `test_containment_adapters.py` compiles the shipped asset, and promoting a rule must not change what claude's native deny list contains (the rule was already `layer: hook`, so `_native_patterns` never saw it).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/containment.py policy/containment.yaml tests/test_containment_policy.py tests/test_containment_evaluate.py
git commit -m "feat(containment): action: deny|escalate, refused on native rules (E-17)"
```

---

## Task 2: Contracts — the models the workflow, activity and adapter all speak

**Files:**
- Modify: `src/sdlc/models.py`
- Modify: `src/sdlc/observability/trace.py` (one enum member)
- Test: `tests/test_containment_models.py`

**Interfaces:**
- Consumes: `Action` from Task 1 (not imported here — `models.py` must not import `containment.py`; the dependency runs the other way).
- Produces: `DeferredToolUse{tool_use_id: str, tool: str, input_digest: str, rule_id: str, reason: str, target: str | None}`; `EscalationOutcome` (`APPROVED`/`REJECTED`/`TIMEOUT`/`CAPPED`/`BATCHED`); `ToolEscalation{tool, rule_id, target, outcome, decided_by, round}`; `ToolGrant{tool_use_id, tool, input_digest, rule_id, approved, reason}`; `ToolDenial.escalation_declined: bool`; `HarnessRunResult.deferred: DeferredToolUse | None`; `ContainmentReport.rules_escalatable: list[str]`; `SessionDigest.escalations: int`; `PipelineConfig.max_tool_escalations: int = 3`; `RunEventKind.TOOL_ESCALATION`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containment_models.py`:

```python
def test_tool_grant_round_trips_through_json():
    """Grants travel on CodingTaskInput through the Temporal payload
    converter, so they must survive model_validate_json."""
    g = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest="deadbeef",
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="fine by me",
    )
    assert ToolGrant.model_validate_json(g.model_dump_json()) == g


def test_deferred_tool_use_target_is_optional():
    d = DeferredToolUse(
        tool_use_id="toolu_1", tool="Write", input_digest="deadbeef", rule_id="r", reason="why"
    )
    assert d.target is None


def test_tool_denial_declines_default_to_false():
    """E-16 denials must keep their exact shape and meaning."""
    d = ToolDenial(tool="Write", rule_id="r", layer=ContainmentLayer.HOOK, reason="nope")
    assert d.escalation_declined is False


def test_harness_run_result_has_no_deferral_by_default():
    r = HarnessRunResult(harness=HarnessKind.CLAUDE_CODE, exit_code=0)
    assert r.deferred is None


def test_escalations_are_capped_at_three_by_default():
    assert PipelineConfig().max_tool_escalations == 3


def test_escalation_outcome_distinguishes_never_asked_from_refused():
    """BATCHED is the measurable size of the solo-only hole; folding it into
    REJECTED would make it uncountable."""
    assert EscalationOutcome.BATCHED != EscalationOutcome.REJECTED
    assert EscalationOutcome.TIMEOUT != EscalationOutcome.REJECTED
```

Merge these into the file's existing import of `sdlc.models`:

```python
from sdlc.models import (
    ContainmentLayer,
    DeferredToolUse,
    EscalationOutcome,
    HarnessKind,
    HarnessRunResult,
    PipelineConfig,
    ToolDenial,
    ToolGrant,
)
```

- [ ] **Step 2: Run the test to verify it fails**

```
python -m pytest tests/test_containment_models.py -q
```

Expected: FAIL with `ImportError: cannot import name 'DeferredToolUse'`.

- [ ] **Step 3: Implement**

In `src/sdlc/models.py`, add `escalation_declined` to `ToolDenial`:

```python
class ToolDenial(BaseModel):
    """One blocked tool call. Small and bounded — travels inline on
    HarnessRunResult, same discipline as SessionDigest."""

    tool: str
    rule_id: str
    layer: ContainmentLayer
    reason: str
    target: str | None = None  # path or command line (scrubbed)
    # E-17: this denial was an ESCALATE rule the hook could not escalate
    # (batched call, or an unreadable transcript). No human was asked. It is
    # marked so the BATCHED outcome stays countable — see EscalationOutcome.
    escalation_declined: bool = False
```

Add `rules_escalatable` to `ContainmentReport`, after `rules_unenforceable`:

```python
    # E-17: rules that can actually raise a gate on THIS harness. Empty on a
    # harness without `defer`, so degradation is visible rather than silent.
    rules_escalatable: list[str] = Field(default_factory=list)
```

Add `escalations` to `SessionDigest`, immediately after `denials`:

```python
escalations: int = 0  # E-17: tool calls that raised a gate
```

Add the new models. Put them directly after `ContainmentConfig` so the whole containment vocabulary stays in one place:

```python
class DeferredToolUse(BaseModel):
    """A tool call the harness suspended at, awaiting a human decision
    (E-17). Built activity-side from the CLI's `deferred_tool_use` payload;
    travels inline on HarnessRunResult — bounded, like ToolDenial."""

    tool_use_id: str  # the CLI replays THIS id on resume
    tool: str
    input_digest: str  # canonical digest of tool_input
    rule_id: str
    reason: str
    target: str | None = None  # scrubbed path/command, for the human


class ToolGrant(BaseModel):
    """One human decision about one suspended call. Single-use falls out of
    tool_use_id: the replayed call reuses it, a genuinely new call gets a
    fresh one and matches nothing."""

    tool_use_id: str
    tool: str
    input_digest: str
    rule_id: str
    approved: bool  # False = rejected / timed out / capped
    reason: str = ""  # reaches the model verbatim


class EscalationOutcome(str, Enum):
    """How an escalation ended. BATCHED and CAPPED never reached a human."""

    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CAPPED = "capped"
    BATCHED = "batched"


class ToolEscalation(BaseModel):
    """The workflow's record of one escalation, for events.jsonl + E-36."""

    tool: str
    rule_id: str
    target: str | None = None
    outcome: EscalationOutcome
    decided_by: str = ""  # "" when nobody was asked
    round: int = 0  # the (gate, round) identity; 0 = no gate
```

Add `deferred` to `HarnessRunResult`, next to `denials`:

```python
deferred: DeferredToolUse | None = None  # E-17: suspended tool call
```

Add the bound to `PipelineConfig`, next to `max_fix_attempts`:

```python
max_tool_escalations: int = 3  # E-17: gates raised per task
# attempt; past this, deny
```

In `src/sdlc/observability/trace.py`, add to `RunEventKind`, after `FIX_ATTEMPT`:

```python
    TOOL_ESCALATION = "tool_escalation"
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_containment_models.py -q
python -m pytest tests/ -q
```

Expected: all pass. New fields are all defaulted, so nothing existing changes.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/models.py src/sdlc/observability/trace.py tests/test_containment_models.py
git commit -m "feat(models): deferral/grant/escalation contracts (E-17)"
```

---

## Task 3: Grants — digest, matching, loading, and the declined marker

**Files:**
- Modify: `src/sdlc/harness/containment.py`
- Test: `tests/test_containment_grants.py` (new)

**Interfaces:**
- Consumes: `ToolGrant` (Task 2), `Action` (Task 1).
- Produces, all in `sdlc.harness.containment`:
  - `digest_tool_input(tool_input: dict) -> str` — sha256 hex over canonical JSON.
  - `match_grant(grants: list[ToolGrant], tool: str, tool_use_id: str, tool_input: dict) -> ToolGrant | None`.
  - `load_grants(path: str | os.PathLike | None) -> list[ToolGrant]` — `[]` for `None` or a missing file.
  - `ESCALATION_UNAVAILABLE: str` (the marker literal) and `is_declined_reason(text: str) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_containment_grants.py`:

```python
"""E-17: grants are single-use by construction, and a declined escalation is
distinguishable from an ordinary denial."""

import json

from sdlc.harness.containment import (
    ESCALATION_UNAVAILABLE,
    digest_tool_input,
    is_declined_reason,
    load_grants,
    match_grant,
)
from sdlc.models import ToolGrant

INPUT = {"file_path": "/etc/passwd", "content": "x"}


def _grant(**over) -> ToolGrant:
    base = dict(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(INPUT),
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="ok",
    )
    return ToolGrant(**{**base, **over})


def test_digest_is_stable_across_key_order():
    a = digest_tool_input({"a": 1, "b": [1, 2]})
    b = digest_tool_input({"b": [1, 2], "a": 1})
    assert a == b


def test_digest_changes_with_content():
    assert digest_tool_input({"file_path": "/a"}) != digest_tool_input({"file_path": "/b"})


def test_matching_grant_is_returned():
    g = _grant()
    assert match_grant([g], "Write", "toolu_1", INPUT) is g


def test_a_different_tool_use_id_never_matches():
    """This is what makes the grant single-use: the replay reuses the id, a
    genuinely new call gets a fresh one."""
    assert match_grant([_grant()], "Write", "toolu_2", INPUT) is None


def test_a_mutated_input_never_matches():
    """Belt to tool_use_id's suspenders: the same id must not carry a
    different payload through."""
    other = {**INPUT, "content": "rm -rf /"}
    assert match_grant([_grant()], "Write", "toolu_1", other) is None


def test_a_different_tool_never_matches():
    assert match_grant([_grant()], "Bash", "toolu_1", INPUT) is None


def test_rejecting_grants_match_too():
    """A rejection must be DELIVERED, not merely recorded."""
    g = _grant(approved=False, reason="no")
    assert match_grant([g], "Write", "toolu_1", INPUT) is g


def test_load_grants_reads_a_json_array(tmp_path):
    p = tmp_path / "g.json"
    p.write_text(json.dumps([_grant().model_dump()]), encoding="utf-8")
    loaded = load_grants(p)
    assert len(loaded) == 1
    assert loaded[0].tool_use_id == "toolu_1"


def test_load_grants_is_empty_without_a_path():
    assert load_grants(None) == []


def test_load_grants_is_empty_for_a_missing_file(tmp_path):
    """A missing grants file means 'no decisions yet', never a crash — and
    an escalate rule with no grant escalates, which is the safe direction."""
    assert load_grants(tmp_path / "absent.json") == []


def test_declined_marker_round_trips():
    text = f"{ESCALATION_UNAVAILABLE} (batched): Writes are scoped."
    assert is_declined_reason(text) is True
    assert is_declined_reason("Writes are scoped.") is False
```

- [ ] **Step 2: Run the test to verify it fails**

```
python -m pytest tests/test_containment_grants.py -q
```

Expected: FAIL with `ImportError: cannot import name 'ESCALATION_UNAVAILABLE'`.

- [ ] **Step 3: Implement**

In `src/sdlc/harness/containment.py`, add `hashlib` and `json` to the imports, and `ToolGrant` to the `..models` import. Then append:

```python
# The hook writes this marker into the reason string after the `[rule-id] `
# prefix when it matched an ESCALATE rule but could not escalate. Both the
# hook (writer) and the adapter (reader) import it from here so the two can
# never drift apart.
ESCALATION_UNAVAILABLE = "escalation unavailable"


def is_declined_reason(text: str) -> bool:
    """True when a denial reason says an escalation was declined, not that a
    rule simply denies. The rule-id prefix has already been stripped."""
    return text.startswith(ESCALATION_UNAVAILABLE)


def digest_tool_input(tool_input: dict) -> str:
    """Canonical digest of a tool call's input. Used by BOTH the activity
    (building a grant) and the hook (matching one), so canonicalisation can
    never disagree between them."""
    canonical = json.dumps(
        tool_input, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def match_grant(
    grants: list[ToolGrant], tool: str, tool_use_id: str, tool_input: dict
) -> ToolGrant | None:
    """The grant for exactly this call, or None. All three of tool name,
    tool_use_id and input digest must agree — the id gives single-use (the
    CLI replays the original id; a new call gets a new one) and the digest
    guards against id reuse carrying a different payload."""
    if not tool_use_id:
        return None
    digest = digest_tool_input(tool_input)
    for g in grants:
        if g.tool_use_id == tool_use_id and g.tool == tool and g.input_digest == digest:
            return g
    return None


def load_grants(path: str | os.PathLike | None) -> list[ToolGrant]:
    """Read the grants asset the adapter wrote. A missing path or file means
    'no decision yet', which makes an escalate rule escalate — the safe
    direction. Malformed content raises: a grants file we cannot parse must
    not silently become 'no grants', which would re-ask a decided call."""
    if path is None:
        return []
    p = Path(path)
    if not p.is_file():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [ToolGrant.model_validate(e) for e in raw]
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_containment_grants.py -q
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/containment.py tests/test_containment_grants.py
git commit -m "feat(containment): single-use grants + declined-escalation marker (E-17)"
```

---

## Task 4: Hook — sibling counting and the six-branch decision

**Files:**
- Modify: `src/sdlc/harness/hook.py`
- Test: `tests/test_containment_hook.py`

**Interfaces:**
- Consumes: `Action`, `digest_tool_input`, `match_grant`, `load_grants`, `ESCALATION_UNAVAILABLE` (Tasks 1, 3); `ToolGrant` (Task 2).
- Produces:
  - `sibling_count(transcript_path: str | None, tool_use_id: str) -> int | None` — `None` means "could not determine", which callers must treat as batched.
  - `decide(payload: dict, policy: Policy, worktree: str, grants: list[ToolGrant] | None = None) -> dict` — the existing three-argument call must keep working.
  - `main(["--worktree", W, "--policy", P, "--grants", G])`, `--grants` optional.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containment_hook.py`:

```python
from sdlc.harness.containment import Action, digest_tool_input
from sdlc.harness.hook import decide, sibling_count
from sdlc.models import ToolGrant

ESC_POLICY = Policy(
    version=1,
    rules=[
        Rule(
            id="no-out-of-worktree-write",
            layer=ContainmentLayer.HOOK,
            action=Action.ESCALATE,
            tools=["Write"],
            predicate="path_outside_worktree",
            reason="Writes are scoped to the task worktree.",
        ),
    ],
)
OUTSIDE = {"file_path": "/etc/passwd"}


def _transcript(tmp_path, tool_use_ids):
    """One assistant message carrying `tool_use_ids` as parallel tool_use
    blocks — the shape claude writes to its session JSONL."""
    p = tmp_path / "transcript.jsonl"
    p.write_text(
        json.dumps({"type": "user", "message": {"content": "go"}})
        + "\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "working"},
                        *(
                            {"type": "tool_use", "id": i, "name": "Write", "input": {}}
                            for i in tool_use_ids
                        ),
                    ]
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return p


def _payload(tmp_path, tool_use_id="toolu_1", ids=("toolu_1",)):
    return {
        "tool_name": "Write",
        "tool_input": OUTSIDE,
        "tool_use_id": tool_use_id,
        "transcript_path": str(_transcript(tmp_path, ids)),
    }


def test_solo_escalate_call_defers(tmp_path):
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "defer"
    assert hso["permissionDecisionReason"].startswith("[no-out-of-worktree-write]")


def test_batched_escalate_call_denies_and_says_why(tmp_path):
    """defer is solo-only: the CLI would DISCARD it and acceptEdits would
    allow the call, so we must never emit it for a batched call."""
    out = decide(_payload(tmp_path, ids=("toolu_1", "toolu_2")), ESC_POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "escalation unavailable (batched)" in hso["permissionDecisionReason"]


def test_unreadable_transcript_denies(tmp_path):
    payload = {
        "tool_name": "Write",
        "tool_input": OUTSIDE,
        "tool_use_id": "toolu_1",
        "transcript_path": str(tmp_path / "gone.jsonl"),
    }
    out = decide(payload, ESC_POLICY, str(tmp_path))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "escalation unavailable (transcript)" in hso["permissionDecisionReason"]


def test_an_approved_grant_allows_exactly_that_call(tmp_path):
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="approved by maks",
    )
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path), [grant])
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"


def test_a_rejecting_grant_denies_with_the_humans_words(tmp_path):
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=False,
        reason="write it inside the worktree instead",
    )
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path), [grant])
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "write it inside the worktree instead" in hso["permissionDecisionReason"]


def test_a_grant_for_another_call_does_not_leak(tmp_path):
    """An approval covers exactly one call — never a standing waiver."""
    grant = ToolGrant(
        tool_use_id="toolu_OTHER",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=True,
    )
    out = decide(_payload(tmp_path), ESC_POLICY, str(tmp_path), [grant])
    assert out["hookSpecificOutput"]["permissionDecision"] == "defer"


def test_a_deny_rule_never_defers(tmp_path):
    """E-16 behaviour is untouched by E-17."""
    out = decide(_payload(tmp_path), POLICY, str(tmp_path))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "escalation unavailable" not in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_sibling_count_finds_the_message_holding_the_id(tmp_path):
    p = _transcript(tmp_path, ("toolu_1", "toolu_2", "toolu_3"))
    assert sibling_count(str(p), "toolu_2") == 3


def test_sibling_count_is_none_when_the_id_is_absent(tmp_path):
    p = _transcript(tmp_path, ("toolu_1",))
    assert sibling_count(str(p), "toolu_missing") is None


def test_sibling_count_survives_malformed_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        "not json\n"
        + json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "Write"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert sibling_count(str(p), "toolu_1") == 1


def test_sibling_count_is_none_for_a_missing_file(tmp_path):
    assert sibling_count(str(tmp_path / "nope.jsonl"), "toolu_1") is None


def test_main_accepts_a_grants_file(tmp_path, capsys, monkeypatch):
    pol = tmp_path / "p.yaml"
    pol.write_text(
        "version: 1\nrules:\n"
        "  - id: r\n    layer: hook\n    action: escalate\n"
        "    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: nope\n",
        encoding="utf-8",
    )
    grants = tmp_path / "g.json"
    grants.write_text(
        json.dumps(
            [
                {
                    "tool_use_id": "toolu_1",
                    "tool": "Write",
                    "input_digest": digest_tool_input(OUTSIDE),
                    "rule_id": "r",
                    "approved": True,
                    "reason": "yes",
                }
            ]
        ),
        encoding="utf-8",
    )
    payload = json.dumps(
        {
            "tool_name": "Write",
            "tool_input": OUTSIDE,
            "tool_use_id": "toolu_1",
            "transcript_path": str(_transcript(tmp_path, ("toolu_1",))),
        }
    )
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    rc = main(["--worktree", str(tmp_path), "--policy", str(pol), "--grants", str(grants)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
```

Add `Policy, Rule` and `ContainmentLayer` to that file's imports if they are not already present (the existing `POLICY` constant at the top of the file already imports them).

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest tests/test_containment_hook.py -q
```

Expected: FAIL with `ImportError: cannot import name 'sibling_count'`.

- [ ] **Step 3: Implement**

Rewrite `src/sdlc/harness/hook.py`'s body below the docstring:

```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..models import ToolGrant
from .containment import (
    ESCALATION_UNAVAILABLE,
    Action,
    Policy,
    evaluate,
    load_grants,
    load_policy,
    match_grant,
)

_EVENT = "PreToolUse"


def format_reason(rule_id: str, reason: str) -> str:
    """`result.permission_denials` carries tool_name/tool_use_id/tool_input
    but NO reason or rule id, so the rule id rides the reason string and
    normalise_denials reads it back out."""
    return f"[{rule_id}] {reason}"


def _decision(decision: str, reason: str | None = None) -> dict:
    hso: dict = {"hookEventName": _EVENT, "permissionDecision": decision}
    if reason is not None:
        hso["permissionDecisionReason"] = reason
    return {"hookSpecificOutput": hso}


def sibling_count(transcript_path: str | None, tool_use_id: str) -> int | None:
    """How many tool_use blocks share the assistant message that issued
    `tool_use_id`. None means we could not determine it.

    `defer` is solo-only: the CLI discards a defer whose message carries
    siblings, and the call then falls through to the ordinary permission
    pipeline — which under acceptEdits ALLOWS it. So an undeterminable count
    must be treated as batched, never as solo.

    There is no race: the assistant message is complete before any of its
    tool calls dispatch. Scanned newest-first because the message we want is
    the most recent one.
    """
    if not transcript_path or not tool_use_id:
        return None
    try:
        lines = Path(transcript_path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        message = ev.get("message")
        content = (message or {}).get("content") if isinstance(message, dict) else ev.get("content")
        if not isinstance(content, list):
            continue
        blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if any(b.get("id") == tool_use_id for b in blocks):
            return len(blocks)
    return None


def _escalate(
    payload: dict, tool: str, tool_input: dict, rule_id: str, reason: str, grants: list[ToolGrant]
) -> dict:
    """Decide an ESCALATE match. Every branch that is not a clean defer or a
    granted allow ends in a deny — degradation is always toward deny."""
    tool_use_id = payload.get("tool_use_id") or ""
    grant = match_grant(grants, tool, tool_use_id, tool_input)
    if grant is not None:
        if grant.approved:
            return _decision(
                "allow",
                format_reason(rule_id, f"approved: {grant.reason}" if grant.reason else "approved"),
            )
        return _decision(
            "deny",
            format_reason(rule_id, f"rejected: {grant.reason}" if grant.reason else "rejected"),
        )

    siblings = sibling_count(payload.get("transcript_path"), tool_use_id)
    if siblings is None:
        return _decision(
            "deny", format_reason(rule_id, f"{ESCALATION_UNAVAILABLE} (transcript): {reason}")
        )
    if siblings > 1:
        return _decision(
            "deny", format_reason(rule_id, f"{ESCALATION_UNAVAILABLE} (batched): {reason}")
        )
    return _decision("defer", format_reason(rule_id, reason))


def decide(
    payload: dict, policy: Policy, worktree: str, grants: list[ToolGrant] | None = None
) -> dict:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return _decision("allow")
    verdict = evaluate(policy, tool, tool_input, worktree)
    if verdict.allow:
        return _decision("allow")
    rule_id = verdict.rule_id or "unknown"
    reason = verdict.reason or "denied by containment policy"
    if verdict.action is Action.ESCALATE:
        return _escalate(payload, tool, tool_input, rule_id, reason, grants or [])
    return _decision("deny", format_reason(rule_id, reason))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sdlc.harness.hook")
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--policy", default=None)
    ap.add_argument("--grants", default=None)
    args = ap.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        policy = load_policy(args.policy)
        grants = load_grants(args.grants)
        out = decide(payload, policy, args.worktree, grants)
    except Exception as e:  # noqa: BLE001
        # Fail CLOSED. A hook that crashes open is worse than no hook: the
        # run would look contained while enforcing nothing.
        out = _decision("deny", f"[containment-error] containment hook failed: {e}")

    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Update the module docstring's first line to `"""PreToolUse hook process (E-15/E-17, FR-703).` and add to it:

```
E-17: an ESCALATE rule defers instead of denying, but ONLY when the call is
solo — `defer` is discarded by the CLI when the assistant message carries
sibling tool_use blocks, and the call would then fall through to
acceptEdits. Every other path denies.
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_containment_hook.py -q
python -m pytest tests/ -q
```

Expected: all pass, including the pre-existing hook tests that call `decide()` with three arguments.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/hook.py tests/test_containment_hook.py
git commit -m "feat(containment): hook defers solo escalate calls, denies batched (E-17)"
```

---

## Task 5: Adapter — grants file, `--grants`, and reading the deferral back

**Files:**
- Modify: `src/sdlc/harness/adapters.py`
- Modify: `src/sdlc/harness/session.py` (count the new event in `digest_of`)
- Test: `tests/test_containment_adapters.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces:
  - `CodingHarness.supports_escalation: bool = False`; `ClaudeCodeHarness.supports_escalation = True`.
  - `CodingHarness.apply_containment(self, policy, req, grants: list[ToolGrant] | None = None) -> ContainmentReport` — the two-argument call still works.
  - `CodingHarness.normalise_deferral(self, stdout: str) -> DeferredToolUse | None` — base returns `None`; `target` is **scrubbed** at construction.
  - `ToolDenial.escalation_declined` populated by `ClaudeCodeHarness.normalise_denials`.
  - `ContainmentReport.rules_escalatable` populated by `ClaudeCodeHarness.apply_containment`.
  - A `SessionEvent(kind="tool_deferred")` appended by `normalise_session`, counted into `SessionDigest.escalations` by `digest_of` — the exact pattern `tool_denied` → `SessionDigest.denials` already follows.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containment_adapters.py`:

```python
import json

from sdlc.harness.adapters import ClaudeCodeHarness, OpenCodeHarness
from sdlc.harness.containment import Action, Policy, Rule, digest_tool_input
from sdlc.models import ContainmentLayer, ToolGrant

ESC_RULE = Rule(
    id="no-out-of-worktree-write",
    layer=ContainmentLayer.HOOK,
    action=Action.ESCALATE,
    tools=["Write"],
    predicate="path_outside_worktree",
    reason="scoped",
)
OUTSIDE = {"file_path": "/etc/passwd"}


def _req(tmp_path):
    from sdlc.harness.adapters import HarnessRequest

    return HarnessRequest(prompt="go", cwd=str(tmp_path))


def _settings_of(req) -> dict:
    path = req.extra_args[req.extra_args.index("--settings") + 1]
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_claude_declares_escalation_support():
    assert ClaudeCodeHarness().supports_escalation is True
    assert OpenCodeHarness().supports_escalation is False


def test_escalate_rules_are_reported_as_escalatable(tmp_path):
    report = ClaudeCodeHarness().apply_containment(
        Policy(version=1, rules=[ESC_RULE]), _req(tmp_path)
    )
    assert report.rules_escalatable == ["no-out-of-worktree-write"]


def test_opencode_reports_no_escalatable_rules(tmp_path):
    """Degradation must be visible: opencode has no hook, so an escalate
    rule cannot raise a gate there."""
    report = OpenCodeHarness().apply_containment(
        Policy(version=1, rules=[ESC_RULE]), _req(tmp_path)
    )
    assert report.rules_escalatable == []


def test_escalate_rules_never_reach_the_native_deny_list(tmp_path):
    """A native deny beats a hook allow, so a natively denied rule could
    never be approved."""
    req = _req(tmp_path)
    ClaudeCodeHarness().apply_containment(Policy(version=1, rules=[ESC_RULE]), req)
    assert _settings_of(req)["permissions"]["deny"] == []


def test_grants_are_written_outside_the_worktree_and_passed_to_the_hook(tmp_path):
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest=digest_tool_input(OUTSIDE),
        rule_id="no-out-of-worktree-write",
        approved=True,
        reason="ok",
    )
    req = _req(tmp_path)
    ClaudeCodeHarness().apply_containment(Policy(version=1, rules=[ESC_RULE]), req, [grant])
    hook_cmd = _settings_of(req)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--grants" in hook_cmd
    grants_path = Path(hook_cmd.split('--grants "')[1].split('"')[0])
    # The agent may write anywhere inside its worktree, so a grants file
    # placed there would be a file it could forge.
    assert tmp_path not in grants_path.parents
    assert json.loads(grants_path.read_text(encoding="utf-8"))[0]["tool_use_id"] == "toolu_1"


def test_no_grants_means_no_grants_flag(tmp_path):
    req = _req(tmp_path)
    ClaudeCodeHarness().apply_containment(Policy(version=1, rules=[ESC_RULE]), req)
    hook_cmd = _settings_of(req)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--grants" not in hook_cmd


def test_normalise_deferral_reads_a_pinned_result_event():
    """Pinned against claude 2.1.220's real output: a honoured defer ends the
    run with stop_reason tool_deferred and a structured deferred_tool_use."""
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "defer",
                                "permissionDecisionReason": "[no-out-of-worktree-write] Writes are scoped.",
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "stop_reason": "tool_deferred",
                    "result": "",
                    "session_id": "sess-1",
                    "permission_denials": [],
                    "deferred_tool_use": {"id": "toolu_1", "name": "Write", "input": OUTSIDE},
                }
            ),
        ]
    )
    d = ClaudeCodeHarness().normalise_deferral(stdout)
    assert d is not None
    assert d.tool_use_id == "toolu_1"
    assert d.tool == "Write"
    assert d.rule_id == "no-out-of-worktree-write"
    assert d.target == "/etc/passwd"
    assert d.input_digest == digest_tool_input(OUTSIDE)


def test_normalise_deferral_is_none_on_an_ordinary_run():
    stdout = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "stop_reason": "completed",
            "result": "done",
            "session_id": "sess-1",
        }
    )
    assert ClaudeCodeHarness().normalise_deferral(stdout) is None


def test_declined_escalations_are_marked_on_the_denial():
    """Without this marker the BATCHED outcome would always count zero."""
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": "[no-out-of-worktree-write] escalation "
                                "unavailable (batched): Writes are scoped.",
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "s",
                    "permission_denials": [
                        {"tool_name": "Write", "tool_use_id": "toolu_1", "tool_input": OUTSIDE}
                    ],
                }
            ),
        ]
    )
    denials = ClaudeCodeHarness().normalise_denials(stdout)
    assert len(denials) == 1
    assert denials[0].escalation_declined is True
    assert denials[0].rule_id == "no-out-of-worktree-write"


def test_an_ordinary_denial_is_not_marked_declined():
    stdout = "\n".join(
        [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "hook_response",
                    "hook_event": "PreToolUse",
                    "output": json.dumps(
                        {
                            "hookSpecificOutput": {
                                "hookEventName": "PreToolUse",
                                "permissionDecision": "deny",
                                "permissionDecisionReason": "[no-recursive-force-delete] Destructive.",
                            }
                        }
                    ),
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "s",
                    "permission_denials": [
                        {
                            "tool_name": "Bash",
                            "tool_use_id": "toolu_9",
                            "tool_input": {"command": "rm -rf /"},
                        }
                    ],
                }
            ),
        ]
    )
    assert ClaudeCodeHarness().normalise_denials(stdout)[0].escalation_declined is False


DEFER_STDOUT = "\n".join(
    [
        json.dumps(
            {
                "type": "system",
                "subtype": "hook_response",
                "hook_event": "PreToolUse",
                "output": json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "defer",
                            "permissionDecisionReason": "[no-out-of-worktree-write] Writes are scoped.",
                        }
                    }
                ),
            }
        ),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "stop_reason": "tool_deferred",
                "result": "",
                "session_id": "sess-1",
                "permission_denials": [],
                "deferred_tool_use": {"id": "toolu_1", "name": "Write", "input": OUTSIDE},
            }
        ),
    ]
)


def test_a_deferral_becomes_a_session_event_and_a_digest_count():
    """Clean-green runs must still report escalations — the same reason
    tool_denied is in the transcript (OQ-B7's keep-the-aggregates rule)."""
    from sdlc.harness.session import digest_of

    session = ClaudeCodeHarness().normalise_session(DEFER_STDOUT)
    assert [e.kind for e in session.events].count("tool_deferred") == 1
    assert digest_of(session).escalations == 1


def test_a_deferral_target_is_scrubbed():
    """Unlike a denial target, this one is rendered into a gate a HUMAN
    reads, so it is scrubbed where it is built."""
    stdout = DEFER_STDOUT.replace(
        json.dumps(OUTSIDE), json.dumps({"file_path": "/tmp/x", "content": "y"})
    )
    d = ClaudeCodeHarness().normalise_deferral(stdout)
    assert d is not None
    # scrub() is identity for text carrying no secret; the point of the test
    # is that the value passed THROUGH scrub, asserted by patching it.
    from unittest.mock import patch

    with patch("sdlc.harness.adapters.scrub", side_effect=lambda s: f"SCRUBBED:{s}") as m:
        d2 = ClaudeCodeHarness().normalise_deferral(stdout)
    assert m.called
    assert d2.target.startswith("SCRUBBED:")
```

Add `from pathlib import Path` to the test file's imports if absent.

- [ ] **Step 2: Run the tests to verify they fail**

```
python -m pytest tests/test_containment_adapters.py -q
```

Expected: FAIL with `AttributeError: 'ClaudeCodeHarness' object has no attribute 'supports_escalation'`.

- [ ] **Step 3: Implement**

In `src/sdlc/harness/adapters.py`, extend the imports:

```python
from ..models import (
    ContainmentLayer,
    ContainmentReport,
    DeferredToolUse,
    HarnessKind,
    HarnessRunResult,
    HarnessSession,
    SessionEvent,
    ToolDenial,
    ToolGrant,
)
from .containment import (
    Action,
    Policy,
    Predicate,
    Rule,
    digest_tool_input,
    is_declined_reason,
    target_of,
)
```

On `CodingHarness`, beside the existing `containment` declaration:

```python
    # E-17: whether this CLI can SUSPEND a tool call for a human decision.
    # claude has `defer`; nothing else does. A harness declaring False keeps
    # escalate rules as plain denials, reported via rules_escalatable.
    supports_escalation: bool = False
```

Change the base `apply_containment` signature and add the base `normalise_deferral`:

```python
def apply_containment(
    self, policy: Policy, req: HarnessRequest, grants: list[ToolGrant] | None = None
) -> ContainmentReport:
    """Compile `policy` into this CLI's own mechanisms, mutating `req`.
    Base default: enforce nothing and say so."""
    return ContainmentReport(
        enabled=True, layers_active=[], rules_unenforceable=[r.id for r in policy.rules]
    )


def normalise_deferral(self, stdout: str) -> DeferredToolUse | None:
    """The tool call this run suspended at, if any (E-17, mirroring
    normalise_denials). Base default: this harness cannot suspend."""
    return None
```

On `ClaudeCodeHarness`, add the capability beside `containment`:

```python
    supports_escalation = True
```

Replace `ClaudeCodeHarness.apply_containment` with:

```python
def apply_containment(
    self, policy: Policy, req: HarnessRequest, grants: list[ToolGrant] | None = None
) -> ContainmentReport:
    """Both layers, deliberately overlapping (E-15 spec §4a).

    `permissions.deny` is the floor a buggy hook cannot weaken (verified:
    a hook's `allow` cannot bypass a deny rule). The hook is the layer
    that is OBSERVABLE — a native deny blocks correctly but reports
    `permission_denials: []`, so every rule is ALSO hooked here.

    E-17: an ESCALATE rule is hook-only by construction (load_policy
    refuses `escalate` + `layer: native`), because a native deny would
    block the very call the human approved.
    """
    grants_path = self._write_grants(grants)
    hooks = (
        [
            {
                "matcher": "|".join(sorted({t for r in policy.rules for t in r.tools})),
                "hooks": [
                    {
                        "type": "command",
                        "command": self._hook_command(req, policy.source_path, grants_path),
                    }
                ],
            }
        ]
        if policy.rules
        else []
    )

    deny = [
        p
        for r in policy.rules
        if ContainmentLayer.NATIVE is r.layer
        for p in self._native_patterns(r)
    ]

    doc = {"hooks": {"PreToolUse": hooks}, "permissions": {"deny": deny}}

    # OUTSIDE the worktree, always: writes inside the worktree are
    # permitted by design, so a settings file placed there is a file the
    # agent may rewrite — it could edit its own policy.
    fd, path = tempfile.mkstemp(prefix="sdlc-containment-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)

    req.extra_args = [*req.extra_args, "--settings", path, "--include-hook-events"]
    return ContainmentReport(
        enabled=True,
        layers_active=[ContainmentLayer.NATIVE, ContainmentLayer.HOOK],
        rules_enforced=[r.id for r in policy.rules],
        rules_unenforceable=[],
        rules_escalatable=[r.id for r in policy.rules if r.action is Action.ESCALATE],
    )


@staticmethod
def _write_grants(grants: list[ToolGrant] | None) -> str | None:
    """Grants live outside the worktree for the same reason the settings
    file does: the agent may write anywhere inside it, so an in-worktree
    grants file would be a file it could forge."""
    if not grants:
        return None
    fd, path = tempfile.mkstemp(prefix="sdlc-grants-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump([g.model_dump() for g in grants], fh)
    return path
```

Replace `_hook_command` with the three-argument form:

```python
@staticmethod
def _hook_command(
    req: HarnessRequest, source_path: "Path | None" = None, grants_path: str | None = None
) -> str:
    """Absolute interpreter path: the child's PATH is allowlisted and may
    resolve a different `python` than the worker's venv. Forward slashes
    because claude runs hooks through Git Bash on Windows. The policy
    path is passed explicitly because the hook's cwd is the worktree (a
    temp dir), where repo-root discovery would fail."""
    exe = Path(sys.executable).as_posix()
    wt = Path(req.cwd).as_posix()
    cmd = f'"{exe}" -m sdlc.harness.hook --worktree "{wt}"'
    if source_path is not None:
        cmd += f' --policy "{Path(source_path).as_posix()}"'
    if grants_path is not None:
        cmd += f' --grants "{Path(grants_path).as_posix()}"'
    return cmd
```

In `ClaudeCodeHarness.normalise_denials`, the `reasons` list is already collected in stream order; mark declines when building each `ToolDenial`. Replace the `denials.append(...)` block with:

```python
tool_input = pd.get("tool_input") or {}
denials.append(
    ToolDenial(
        tool=pd.get("tool_name") or "unknown",
        rule_id=rule_id,
        layer=ContainmentLayer.HOOK,
        reason=reason,
        escalation_declined=is_declined_reason(reason),
        target=target_of(pd.get("tool_name") or "", tool_input),
    )
)
```

Add `normalise_deferral` to `ClaudeCodeHarness`, directly after `normalise_denials`:

```python
def normalise_deferral(self, stdout: str) -> DeferredToolUse | None:
    """The `result` event carries `stop_reason: "tool_deferred"` plus a
    structured `deferred_tool_use` (verified against 2.1.220). The rule
    id and reason come from the hook's own defer event, the same channel
    normalise_denials reads."""
    rule_id, reason = "unknown", ""
    deferred = None
    for ln in stdout.strip().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            ev = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("subtype") == "hook_response" and ev.get("hook_event") == "PreToolUse":
            try:
                hso = json.loads(ev.get("output") or "{}")
                hso = hso.get("hookSpecificOutput") or {}
            except json.JSONDecodeError:
                continue
            if hso.get("permissionDecision") == "defer":
                rule_id, reason = _split_reason(hso.get("permissionDecisionReason") or "")
        elif ev.get("type") == "result" and ev.get("stop_reason") == "tool_deferred":
            deferred = ev.get("deferred_tool_use") or {}
    if not deferred:
        return None
    tool = deferred.get("name") or "unknown"
    tool_input = deferred.get("input") or {}
    raw_target = target_of(tool, tool_input)
    return DeferredToolUse(
        tool_use_id=deferred.get("id") or "",
        tool=tool,
        input_digest=digest_tool_input(tool_input),
        rule_id=rule_id,
        reason=reason,
        # Scrubbed here, not later: this target is rendered into a gate a
        # HUMAN reads, an exposure denial targets never had.
        target=scrub(raw_target) if raw_target else raw_target,
    )
```

Add the scrub import to `adapters.py`:

```python
from ..memory.scrub import scrub
```

Append the deferral to the transcript in `ClaudeCodeHarness.normalise_session`,
directly after the existing `tool_denied` loop, so a clean-green run still
reports escalations:

```python
deferred = self.normalise_deferral(stdout)
if deferred is not None:
    events.append(SessionEvent(kind="tool_deferred", tool=deferred.tool, target=deferred.target))
```

Count it in `src/sdlc/harness/session.py`'s `digest_of`, beside the denial
branch:

```python
        elif ev.kind == "tool_denied":
            d.denials += 1
        elif ev.kind == "tool_deferred":
            d.escalations += 1
```

Finally, change `OpenCodeHarness.apply_containment`'s signature to accept and ignore grants (it has no hook to pass them to):

```python
    def apply_containment(self, policy: Policy, req: HarnessRequest,
                          grants: list[ToolGrant] | None = None
                          ) -> ContainmentReport:
```

Leave its body unchanged: an escalate rule is `layer: hook`, so it already lands in `rules_unenforceable`, and `rules_escalatable` correctly stays empty.

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_containment_adapters.py tests/test_containment_adapters_other.py -q
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/harness/adapters.py src/sdlc/harness/session.py tests/test_containment_adapters.py
git commit -m "feat(harness): grants file, --grants, normalise_deferral (E-17)"
```

---

## Task 6: Activity — carry grants in, carry the deferral out

**Files:**
- Modify: `src/sdlc/activities.py` (`CodingTaskInput`, `_resolve_containment`, `run_coding_task`)
- Test: `tests/test_containment_activity.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 5.
- Produces: `CodingTaskInput.grants: list[ToolGrant]` (defaults to `[]`); `run_coding_task` returning a `HarnessRunResult` whose `deferred` is populated best-effort.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_containment_activity.py`:

```python
def test_grants_reach_the_compiled_hook_command(tmp_path, monkeypatch):
    """The activity's job is to get the workflow's decision to the hook."""
    policy = tmp_path / "containment.yaml"
    policy.write_text(
        "version: 1\nrules:\n"
        "  - id: no-out-of-worktree-write\n    layer: hook\n"
        "    action: escalate\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n    reason: scoped\n",
        encoding="utf-8",
    )
    grant = ToolGrant(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest="deadbeef",
        rule_id="no-out-of-worktree-write",
        approved=True,
    )
    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="go",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_policy_path=str(policy),
        grants=[grant],
    )
    req = HarnessRequest(prompt="go", cwd=str(tmp_path))
    _, report = _resolve_containment(HARNESSES[HarnessKind.CLAUDE_CODE], inp, req)
    settings = json.loads(
        Path(req.extra_args[req.extra_args.index("--settings") + 1]).read_text(encoding="utf-8")
    )
    hook_cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--grants" in hook_cmd
    assert report.rules_escalatable == ["no-out-of-worktree-write"]


def test_coding_task_input_defaults_to_no_grants(tmp_path):
    inp = CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="go", worktree=str(tmp_path))
    assert inp.grants == []
```

Merge `ToolGrant` into the file's `sdlc.models` import and `HarnessRequest` into its `sdlc.harness.adapters` import; add `import json` and `from pathlib import Path` if absent.

- [ ] **Step 2: Run the test to verify it fails**

```
python -m pytest tests/test_containment_activity.py -q
```

Expected: FAIL with `TypeError: CodingTaskInput.__init__() got an unexpected keyword argument 'grants'`.

- [ ] **Step 3: Implement**

In `src/sdlc/activities.py`, add `ToolGrant` to the `.models` import, and `field` to the `dataclasses` import. Extend `CodingTaskInput`:

```python
    containment_strict: bool = False
    # E-17: human decisions about suspended tool calls. Written to a grants
    # file activity-side and read by the hook; empty on a first attempt.
    grants: list[ToolGrant] = field(default_factory=list)
```

In `_resolve_containment`, pass them through:

```python
    report = harness.apply_containment(policy, req, inp.grants)
```

In `run_coding_task`, populate the deferral beside the denials:

```python
result.containment = report
try:
    result.denials = harness.normalise_denials(result._raw_stdout)
    result.deferred = harness.normalise_deferral(result._raw_stdout)
except Exception:  # noqa: BLE001
    # Best-effort, exactly like capture_session: losing the RECORD of a
    # denial must never fail a task whose denial was already enforced.
    # A lost deferral simply means no escalation is raised — the call
    # was already suspended by the hook, not allowed.
    _log.warning("denial normalisation failed", exc_info=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_containment_activity.py -q
python -m pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/activities.py tests/test_containment_activity.py
git commit -m "feat(activities): thread grants in, deferral out of run_coding_task (E-17)"
```

---

## Task 7: Workflow — the escalation loop and the gate

**Files:**
- Modify: `src/sdlc/workflows/feature.py` (`__init__`, a module-level helper, `_dev_task`'s harness call at `feature.py:739-749`)
- Test: `tests/test_tool_approval_gate.py` (new)

**Interfaces:**
- Consumes: Tasks 2, 6 (`HarnessRunResult.deferred`, `CodingTaskInput.grants`, `ToolGrant`, `EscalationOutcome`, `ToolEscalation`, `RunEventKind.TOOL_ESCALATION`, `PipelineConfig.max_tool_escalations`).
- Produces: a `"tool_approval"` gate whose round is `self._escalation_round`; `TOOL_ESCALATION` trace events; benchmark records with `stage="tool_approval"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_approval_gate.py`:

```python
"""E-17: a deferred tool call raises a real gate, the decision reaches the
resumed session as a grant, and escalating costs neither a fix attempt nor a
session resume."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from temporalio import activity, workflow
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin

from sdlc.activities import CodingTaskInput, evaluate_gate
from sdlc.models import (
    DeferredToolUse,
    GateDecision,
    GateOutcome,
    HarnessRunResult,
    ToolDenial,
    ContainmentLayer,
)
from sdlc.observability.activities import export_run_artifacts
from tests.fakes.canned import (
    AGENT_SPECS,
    QUESTION_IDS,
    e2e_config,
    greenfield_idea,
)
from tests.fakes.fake_activities import GIT_FAKES, fake_run_coding_task

with workflow.unsafe.imports_passed_through():
    from sdlc.workflows.feature import FeatureWorkflow
    from tests.fakes.fake_agents import fake_agent_activities

TASK_QUEUE = "toolapproval"

SEEN: list[CodingTaskInput] = []


def _deferral() -> DeferredToolUse:
    return DeferredToolUse(
        tool_use_id="toolu_1",
        tool="Write",
        input_digest="deadbeef",
        rule_id="no-out-of-worktree-write",
        reason="Writes are scoped to the task worktree.",
        target="/etc/passwd",
    )


@activity.defn(name="run_coding_task")
async def defer_once(inp: CodingTaskInput) -> HarnessRunResult:
    """First call suspends at a tool call; the resumed call succeeds."""
    SEEN.append(inp)
    base = dict(
        harness=inp.harness,
        session_id="s1",
        exit_code=0,
        input_tokens=1000,
        output_tokens=200,
        context_window=200000,
    )
    if len(SEEN) == 1:
        # summary is "" and there is no commit: the run ENDED at the tool
        # call, exactly as `stop_reason: tool_deferred` reports it.
        return HarnessRunResult(summary="", deferred=_deferral(), **base)
    return HarnessRunResult(summary="implemented", commit_sha="cafe1234", **base)


def _activities(coding):
    """Swap the canned harness fake for one that defers. Identity filtering,
    matching how test_budget_gate.py swaps price_usage."""
    fakes = [a for a in GIT_FAKES if a is not fake_run_coding_task]
    return [
        evaluate_gate,
        export_run_artifacts,
        coding,
        *fakes,
        *fake_agent_activities(AGENT_SPECS),
    ]


async def _wait_for_status(handle, target, timeout_s=10.0):
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        if await handle.query(FeatureWorkflow.pending_gate) == target:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(f"timed out waiting for {target!r}")


async def _drive_to_tasks(handle):
    await _wait_for_status(handle, "awaiting:clarify")
    for qid in QUESTION_IDS:
        await handle.signal(FeatureWorkflow.answer_question, args=[qid, "yes"])
    await _wait_for_status(handle, "awaiting:architecture")
    await handle.signal(
        FeatureWorkflow.submit_gate_decision,
        GateDecision(gate="architecture", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )
    await _wait_for_status(handle, "awaiting:plan")
    await handle.signal(
        FeatureWorkflow.submit_gate_decision,
        GateDecision(gate="plan", round=1, outcome=GateOutcome.APPROVE, decided_by="human"),
    )


@pytest.mark.asyncio
async def test_deferral_raises_a_gate_and_the_grant_reaches_the_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    SEEN.clear()
    cfg = e2e_config()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow],
                activities=_activities(defer_once),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"esc-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _drive_to_tasks(handle)
                    await _wait_for_status(handle, "awaiting:tool_approval")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tool_approval",
                            round=1,
                            outcome=GateOutcome.APPROVE,
                            decided_by="human",
                            comments="fine, that path is mine",
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:merge")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)

    assert result.startswith("deployed:"), result
    # The gate was real, and used the stable configurable name.
    gates = [g for g in summary.gates if g.gate == "tool_approval"]
    assert len(gates) == 1 and gates[0].round == 1 and gates[0].approved
    # The decision reached the resumed session as a grant, on the SAME session.
    assert len(SEEN) == 2
    assert SEEN[0].grants == []
    assert len(SEEN[1].grants) == 1
    grant = SEEN[1].grants[0]
    assert grant.tool_use_id == "toolu_1"
    assert grant.approved is True
    assert grant.reason == "fine, that path is mine"
    assert SEEN[1].session_id == "s1"
    # Escalating is not failing: one attempt, no extra fix attempt recorded.
    assert SEEN[1].attempt == 1


@pytest.mark.asyncio
async def test_rejection_is_delivered_and_the_task_continues(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    SEEN.clear()
    cfg = e2e_config()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow],
                activities=_activities(defer_once),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"esc-rej-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _drive_to_tasks(handle)
                    await _wait_for_status(handle, "awaiting:tool_approval")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tool_approval",
                            round=1,
                            outcome=GateOutcome.REJECT,
                            decided_by="human",
                            comments="write inside the worktree",
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:merge")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver

    # A refusal must be DELIVERED to the harness, not merely recorded.
    assert result.startswith("deployed:"), result
    assert len(SEEN) == 2
    grant = SEEN[1].grants[0]
    assert grant.approved is False
    assert grant.reason == "write inside the worktree"


@pytest.mark.asyncio
async def test_the_cap_stops_asking_and_the_loop_terminates(tmp_path, monkeypatch):
    """An agent that defers forever must not spam a human or hang the run."""
    monkeypatch.setenv("SDLC_EXPORT_ROOT", str(tmp_path))
    calls: list[CodingTaskInput] = []

    @activity.defn(name="run_coding_task")
    async def always_defer(inp: CodingTaskInput) -> HarnessRunResult:
        calls.append(inp)
        return HarnessRunResult(
            harness=inp.harness,
            session_id="s1",
            exit_code=0,
            summary="",
            input_tokens=10,
            output_tokens=2,
            context_window=200000,
            deferred=_deferral(),
        )

    cfg = e2e_config()
    cfg.max_tool_escalations = 1
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        with env.auto_time_skipping_disabled():
            async with Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[FeatureWorkflow],
                activities=_activities(always_defer),
                plugins=[PydanticAIPlugin()],
            ):
                handle = await env.client.start_workflow(
                    FeatureWorkflow.run,
                    args=[greenfield_idea(), cfg],
                    id=f"esc-cap-{uuid.uuid4()}",
                    task_queue=TASK_QUEUE,
                )

                async def drive():
                    await _drive_to_tasks(handle)
                    await _wait_for_status(handle, "awaiting:tool_approval")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="tool_approval",
                            round=1,
                            outcome=GateOutcome.APPROVE,
                            decided_by="human",
                        ),
                    )
                    # No second gate is ever raised: the cap refuses instead,
                    # so the next status to appear is the merge gate. (The
                    # fake QA passes, so the task never reaches escalation.)
                    await _wait_for_status(handle, "awaiting:merge")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="merge", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )
                    await _wait_for_status(handle, "awaiting:deploy")
                    await handle.signal(
                        FeatureWorkflow.submit_gate_decision,
                        GateDecision(
                            gate="deploy", round=1, outcome=GateOutcome.APPROVE, decided_by="human"
                        ),
                    )

                driver = asyncio.create_task(drive())
                result = await handle.result()
                await driver
                summary = await handle.query(FeatureWorkflow.run_summary)

    # Exactly one gate raised, then a refusal delivered, then no more
    # approval resumes — bounded regardless of how the harness behaves.
    assert len([g for g in summary.gates if g.gate == "tool_approval"]) == 1
    capped = [c for c in calls if c.grants and not c.grants[0].approved]
    assert len(capped) >= 1
    assert capped[0].grants[0].reason == "escalation cap reached"


def test_declined_denials_become_batched_escalation_records():
    """A denial the hook could not escalate must be countable (§6)."""
    from sdlc.workflows.feature import escalations_from_denials

    denials = [
        ToolDenial(
            tool="Write",
            rule_id="r",
            layer=ContainmentLayer.HOOK,
            reason="escalation unavailable (batched): scoped",
            target="/etc/passwd",
            escalation_declined=True,
        ),
        ToolDenial(
            tool="Bash",
            rule_id="d",
            layer=ContainmentLayer.HOOK,
            reason="Destructive.",
            target="rm -rf /",
        ),
    ]
    out = escalations_from_denials(denials)
    assert len(out) == 1
    assert out[0].outcome.value == "batched"
    assert out[0].decided_by == ""
    assert out[0].round == 0
```

- [ ] **Step 2: Run the test to verify it fails**

```
python -m pytest tests/test_tool_approval_gate.py -q
```

Expected: FAIL — `ImportError: cannot import name 'escalations_from_denials'`, and the gate tests time out waiting for `awaiting:tool_approval`.

- [ ] **Step 3: Implement**

In `src/sdlc/workflows/feature.py`, add to the `..models` import: `DeferredToolUse, EscalationOutcome, ToolDenial, ToolEscalation, ToolGrant`. Add `TOOL_ESCALATION` wherever `RunEventKind` members are used (it is imported as the enum, so no import change is needed).

Add two module-level pure helpers next to `_spec_summary`:

```python
def escalations_from_denials(denials: list[ToolDenial]) -> list[ToolEscalation]:
    """Denials the hook could not escalate (batched call, unreadable
    transcript). No human was asked, so there is no gate and no round — but
    they must still be countable, or the size of the solo-only hole would be
    invisible (E-17 §6)."""
    return [
        ToolEscalation(
            tool=d.tool, rule_id=d.rule_id, target=d.target, outcome=EscalationOutcome.BATCHED
        )
        for d in denials
        if d.escalation_declined
    ]


def _escalation_summary(task_id: str, title: str, deferred: DeferredToolUse) -> str:
    """What the human is actually deciding, rendered into the GateContext
    field the E-6 channel contract already renders (the same way the budget
    gate puts its cost table there)."""
    return (
        f"Task {task_id} ({title}) is blocked on a tool call.\n"
        f"  tool:   {deferred.tool}\n"
        f"  target: {deferred.target or '(none)'}\n"
        f"  rule:   {deferred.rule_id} — {deferred.reason}\n"
        "Approve to permit exactly this one call; reject to refuse it "
        "(the task continues either way)."
    )
```

In `FeatureWorkflow.__init__`, add the counter beside the budget state:

```python
        # E-17: monotonic gate round for tool-approval escalations. ONE
        # counter for the whole run: _dev_task runs concurrently across tasks
        # in wave mode, and workflow code is single-threaded, so a shared
        # counter keeps (gate, round) unique and replay-deterministic where a
        # per-task round would collide.
        self._escalation_round: int = 0
```

Add the recording helper as a method, next to `_check_budget`:

```python
async def _record_escalation(self, cfg: PipelineConfig, task: DevTask, esc: ToolEscalation) -> None:
    """Trace event (events.jsonl / report.html) plus a benchmark record
    so E-36's case x stage heatmap sees approval friction."""
    self._emit(
        RunEventKind.TOOL_ESCALATION,
        stage="tool_approval",
        task_id=task.id,
        tool=esc.tool,
        rule_id=esc.rule_id,
        outcome=esc.outcome.value,
        decided_by=esc.decided_by,
        round=str(esc.round),
        **({"target": esc.target} if esc.target else {}),
    )
    now = workflow.now()
    # `judge` is a constrained Literal on QualityScore — "policy" is not a
    # member. A gate-decided outcome is a human override; a capped or
    # batched one was decided deterministically, with nobody asked.
    judge = "human_override" if esc.decided_by == "human" else "contract"
    await self._record(
        cfg,
        self._stage_record(
            cfg,
            stage="tool_approval",
            role="human",
            started=now,
            ended=now,
            quality_score=None,
            judge=judge,
            outcome=(
                BenchmarkOutcome.PASS
                if esc.outcome is EscalationOutcome.APPROVED
                else BenchmarkOutcome.ESCALATED
            ),
            model="human",
            task_id=task.id,
        ),
    )
```

Now replace the harness invocation in `_dev_task` (`feature.py:739-749`) with the escalation loop. The existing code is:

```python
run = await workflow.execute_activity(
    run_coding_task,
    CodingTaskInput(
        harness=role_cfg.harness,
        prompt=prompt,
        worktree=worktree,
        model=role_cfg.model,
        session_id=session_id,
        task_id=task.id,
        attempt=attempt,
        containment_enabled=cfg.containment_enabled,
        containment_policy_path=cfg.containment.policy_path,
        containment_strict=cfg.containment.strict,
    ),
    **_long_act(role_cfg),
)
```

Replace it with:

```python
# E-17: the harness may SUSPEND at a tool call an escalate rule
# matched (claude's `defer`). The child process has already
# exited, so the durable wait belongs here, in the workflow —
# then we resume the same session with the human's decision.
grants: list[ToolGrant] = []
asked = 0
capped = False
while True:
    run = await workflow.execute_activity(
        run_coding_task,
        CodingTaskInput(
            harness=role_cfg.harness,
            prompt=prompt,
            worktree=worktree,
            model=role_cfg.model,
            session_id=session_id,
            task_id=task.id,
            attempt=attempt,
            containment_enabled=cfg.containment_enabled,
            containment_policy_path=cfg.containment.policy_path,
            containment_strict=cfg.containment.strict,
            grants=grants,
        ),
        **_long_act(role_cfg),
    )
    for esc in escalations_from_denials(run.denials):
        await self._record_escalation(cfg, task, esc)
    if run.deferred is None or capped:
        break
    # Resuming for an approval is NOT a failure resume: it costs
    # neither a fix attempt nor the FR-802 resume budget.
    session_id = run.session_id
    if asked >= cfg.max_tool_escalations:
        capped = True
        grants = [
            ToolGrant(
                tool_use_id=run.deferred.tool_use_id,
                tool=run.deferred.tool,
                input_digest=run.deferred.input_digest,
                rule_id=run.deferred.rule_id,
                approved=False,
                reason="escalation cap reached",
            )
        ]
        await self._record_escalation(
            cfg,
            task,
            ToolEscalation(
                tool=run.deferred.tool,
                rule_id=run.deferred.rule_id,
                target=run.deferred.target,
                outcome=EscalationOutcome.CAPPED,
                decided_by="policy",
            ),
        )
        continue  # one more resume, only to deliver the deny
    asked += 1
    self._escalation_round += 1
    decision = await self._gate(
        "tool_approval",
        cfg,
        round=self._escalation_round,
        context=GateContext(spec_summary=_escalation_summary(task.id, task.title, run.deferred)),
        default_policy=GatePolicy.HARD,
    )
    grants = [
        ToolGrant(
            tool_use_id=run.deferred.tool_use_id,
            tool=run.deferred.tool,
            input_digest=run.deferred.input_digest,
            rule_id=run.deferred.rule_id,
            approved=decision.approved,
            reason=decision.comments or "",
        )
    ]
    await self._record_escalation(
        cfg,
        task,
        ToolEscalation(
            tool=run.deferred.tool,
            rule_id=run.deferred.rule_id,
            target=run.deferred.target,
            outcome=(
                EscalationOutcome.APPROVED
                if decision.approved
                else EscalationOutcome.TIMEOUT
                if decision.decided_by == "timeout"
                else EscalationOutcome.REJECTED
            ),
            decided_by=decision.decided_by,
            round=self._escalation_round,
        ),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python -m pytest tests/test_tool_approval_gate.py -q
python -m pytest tests/ -q
```

Expected: all pass. If the first run fails on payload conversion of `CodingTaskInput.grants`, that is the nested-pydantic-in-dataclass case this test exists to catch — the fix is to confirm `pydantic_data_converter` is in use for the worker (it is, via `WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)`), not to flatten the model.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/workflows/feature.py tests/test_tool_approval_gate.py
git commit -m "feat(workflow): tool_approval gate raised from a deferred call (E-17)"
```

---

## Task 8: Live proof and the documentation the tracker depends on

**Files:**
- Modify: `tests/test_containment_live.py`
- Modify: `ROADMAP.md`, `ARCHITECTURE.md`, `PRD.md`
- Test: `tests/test_containment_live.py`

**Interfaces:**
- Consumes: Tasks 1–7. Produces: nothing further consumes this.

- [ ] **Step 1: Write the live test**

Append to `tests/test_containment_live.py`, matching the skip marker already used in that file for live-harness tests:

```python
@pytest.mark.live
@pytest.mark.asyncio
async def test_claude_defers_a_solo_escalate_call_and_honours_the_grant(tmp_path):
    """The one end-to-end proof: a real `claude -p` suspends at a write
    outside its worktree, and the resumed session performs it once granted.
    Verified against 2.1.220."""
    policy = tmp_path / "containment.yaml"
    outside = tmp_path / "outside.txt"
    worktree = tmp_path / "wt"
    worktree.mkdir()
    policy.write_text(
        "version: 1\nrules:\n"
        "  - id: no-out-of-worktree-write\n    layer: hook\n"
        "    action: escalate\n    tools: [Write]\n"
        "    predicate: path_outside_worktree\n"
        "    reason: Writes are scoped to the task worktree.\n",
        encoding="utf-8",
    )

    harness = ClaudeCodeHarness()
    loaded = load_policy(policy)
    req = HarnessRequest(
        prompt=f"Write the single word ok to {outside.as_posix()}. "
        "Use the Write tool once and then stop.",
        cwd=str(worktree),
    )
    harness.apply_containment(loaded, req)
    first = await harness.run(req)
    deferred = harness.normalise_deferral(first._raw_stdout)
    assert deferred is not None, first._raw_stdout[-2000:]
    assert deferred.rule_id == "no-out-of-worktree-write"
    assert not outside.exists()  # suspended, not performed

    grant = ToolGrant(
        tool_use_id=deferred.tool_use_id,
        tool=deferred.tool,
        input_digest=deferred.input_digest,
        rule_id=deferred.rule_id,
        approved=True,
        reason="approved for this test",
    )
    resume = HarnessRequest(prompt="", cwd=str(worktree), session_id=first.session_id)
    harness.apply_containment(loaded, resume, [grant])
    await harness.run(resume)
    assert outside.exists(), "the granted call did not run on resume"
```

Merge the needed names into that file's imports: `ClaudeCodeHarness`, `HarnessRequest` from `sdlc.harness.adapters`; `load_policy` from `sdlc.harness.containment`; `ToolGrant` from `sdlc.models`.

- [ ] **Step 2: Run the live test**

```
python -m pytest tests/test_containment_live.py -q -m live
```

Expected: PASS. It costs one real (small) claude session plus a resume. If `normalise_deferral` returns `None`, print the tail of `first._raw_stdout` and compare the `result` event's fields against the pinned fixture in Task 5 — a shape change there is exactly the drift E-24 tracks, and the fixture is what must be updated.

- [ ] **Step 3: Confirm the whole suite still passes without live tests**

```
python -m pytest tests/ -q
```

Expected: all pass, live tests deselected as usual.

- [ ] **Step 4: Update the documentation**

In `ROADMAP.md`:

- **E-17** — change to `[x]` and replace the body with the landed note:

```markdown
- [x] **E-17** Approval escalation: a `needsApproval`-class tool call raises a
  gate through existing FR-301/FR-302 machinery rather than a parallel
  mechanism. *Landed (2026-07-25):* `action: escalate` on a containment rule
  → the hook emits claude's `defer` → the run ends with
  `stop_reason: tool_deferred` → the **workflow** owns the durable wait
  (`tool_approval` gate) → the session resumes with a **single-use** grant
  bound to `tool_use_id` + input digest. `defer` is **solo-only**: the hook
  counts sibling `tool_use` blocks via `transcript_path` and denies rather
  than emitting a defer the CLI would discard (a discarded defer would fall
  through to `acceptEdits` and be ALLOWED). Every non-approve path — reject,
  timeout, cap, batched — resumes with a rejecting grant and the task
  continues, so a refusal never throws away a session. Spec
  `docs/superpowers/specs/2026-07-25-tool-approval-escalation-design.md`,
  plan `docs/superpowers/plans/2026-07-25-tool-approval-escalation.md`.
```

- **§9.4 preamble** — replace the closing sentence with: *"Both halves now exist: E-16 denies by rule, E-17 escalates by rule into the FR-301/302 gate. The remaining gap in §9.4 is E-18's network-level tier, which is E-21."*
- **FR-703** — extend the partial note: after `(tool-level)`, add `; approval escalation for `action: escalate` rules lands via the same hook (E-17)`.
- **FR-301** — append to the note: `Tool-call approval now escalates into this same machinery (E-17), so a `pre_tool` denial and a human gate are one mechanism.`
- **§9.7 item 4** — change `**E-15 → E-17**` to `~~**E-15 → E-17**~~ — landed.`
- **E-24** — update the drift note: `pins 2.1.218; installed is 2.1.220 (E-17 verified `defer` against it)`.
- **§8 item 4** — mark the `pre_tool` half done: change `**Harness containment** beyond env allowlist` to `~~**Harness containment**~~ — `pre_tool` hook ✅ (E-15/E-16) + approval escalation ✅ (E-17); egress beyond tool-level remains **E-21**.`

In `ARCHITECTURE.md`, extend the **ADR-17** entry in §12:

```markdown
  *Extended 2026-07-25 (E-17):* the same hook carries approval, not only
  denial. claude's `permissionDecision: "defer"` suspends the call and ends
  the print-mode run, so the durable wait lives in the workflow's existing
  gate rather than in an activity awaiting a signal. `defer` is print-mode
  only and **solo-only** — a defer emitted for a batched call is discarded
  and the call falls through to `acceptEdits` — so the hook counts sibling
  tool_use blocks and denies when it cannot guarantee a solo defer.
  Degradation is always toward deny.
```

In `PRD.md`, extend FR-703's text with one clause: `A rule may be declared `escalate` rather than `deny`, in which case the blocked call raises a human gate through FR-301/FR-302; an approval covers exactly one call.`

- [ ] **Step 5: Commit**

```bash
git add tests/test_containment_live.py ROADMAP.md ARCHITECTURE.md PRD.md
git commit -m "docs: E-17 landed; ADR-17 extended with defer + solo-only"
```

---

## Verification Checklist

Run at the end, before declaring the feature done:

- [ ] `python -m pytest tests/ -q` — full suite green.
- [ ] `python -m pytest tests/ -q -m live` — the live defer/resume proof passes.
- [ ] `python -m pytest tests/test_containment_hook.py tests/test_containment_evaluate.py tests/test_containment_policy.py -q` — E-16's behaviour is unchanged where `action` is `deny`.
- [ ] Confirm the default posture is untouched: `PipelineConfig().containment_enabled is False` and a policy without any `action:` key produces only `DENY` rules.
