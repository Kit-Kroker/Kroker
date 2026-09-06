# C2: Freeze The Contract's Tests During Fix Loops Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A harness session running a *repair* attempt must not be able to edit, delete, or hide changes to the test files its frozen Validation Contract judges it by — while the first implementation pass stays completely free to author those tests.

**Architecture:** One glob set, defined once in the hashed policy asset, projected twice. The **fence** is an ordinary `path_matches` deny rule in `policy/containment.yaml` carrying a new `phase: repair` field; adapters and the hook filter rules by phase using a `repair: bool` that rides `HarnessRequest` exactly the way `write_root` already does — nothing is synthesized at runtime, so what the hook enforces is the digest of the file in git. The **deterministic backstop** is a new git activity that measures content drift under those same globs against an anchor commit `A`, catching everything the tool-level fence structurally cannot (Bash writes, deletes, and index-metadata evasion). A human at the fix-loop gate can thaw the freeze for exactly one attempt, which also moves `A`.

**Tech Stack:** Python 3.11+, pydantic v2, `fnmatch`, `git` via the existing `_git` helper, Temporal workflows/activities. No new dependencies.

**Spec:** No separate spec file. This plan was settled in a brainstorming session with the user, with per-decision consensus from an `advisor` agent and a full independent design review from a `reviewer` agent (both via `herdr agent prompt` in this repo's planning tab). Working artifacts — `advisor-1..5.md`, `reviewer-1.md`, `c2-design.md` — were written to `.workspace/tmp/`, which is **gitignored**, so every conclusion they reached is reproduced inline below; do not go looking for them. The originating defect is row **C2** in `docs/reports/external-ideas-2026-09.md`.

## Global Constraints

- **Pass 1 stays free.** The dev writes the contract's tests on the first attempt. Every mechanism here activates only on repair attempts (`attempt >= 2`), and never on attempt 1.
- **The policy stays a static hashed asset.** No synthesized policy documents, no runtime-mutated rules. The per-task overlay is a **boolean parameter** over an unchanged YAML file — the `write_root` precedent (`src/sdlc/harness/base.py:117-122`). This was an explicit design constraint from the user and the merge-a-tempfile alternative was considered and rejected.
- **Deterministic backstop pairs with the advisory fence** (the C4 pairing rule). Anything the hook cannot catch must be caught deterministically at the git layer.
- **Crew's `write_root` semantics must not change.** Non-lead roles stay fenced to their orchestration dir (`src/sdlc/crew/activities.py:271`); the freeze composes with that fence rather than replacing it.
- **No new third-party dependencies.** No `pathspec`, no `gitpython`.
- **One term for one bit: `repair`.** Everywhere — `Phase.REPAIR`, `Rule.phase`, `HarnessRequest.repair`, `evaluate(repair=)`, `--repair`, `CodingTaskInput.repair`, `CrewTaskInput.repair`, `CrewTurnInput.repair`. Never introduce a second name (`test_freeze`, `frozen`, `is_fix`) for the same boolean. Two words for one bit will read as two concepts.
- **Windows is the dev box, Linux is CI.** Every git behaviour asserted in this plan was verified on the Windows dev box before being written down (the transcripts are in Task 4 and Task 3). Do not re-derive them from memory.
- **C2 rides the containment flag.** `G` lives only in the policy asset, so the fence *and* the backstop are inert when `containment_enabled=False` — which is the **default** (`src/sdlc/core/models.py:371`). This is correct per ADR-17 (containment-off means unpoliced by choice; a second source for `G` would drift), but it caps what this row buys the default deployment. Say so in the register row update (Task 9); do not let "we landed C2" read as coverage the default deployment does not have.

---

## Terminology (used throughout; fixed, do not rename)

| Term | Meaning |
|---|---|
| **`G`** | The **fence set**. Test-path globs carried by repair-phase `deny` rules in `policy/containment.yaml`. Denied at the hook/native layer *and* measured by the backstop. |
| **`C`** | The **report-only set** (`Policy.drift_paths`). Test/build-config and dependency-manifest globs. Never denied — these are sometimes legitimately edited during repair — but always measured. |
| **`D`** | The **drift set**, `D = G ∪ C`. What the backstop activity measures. |
| **`A`** | The **anchor**: the checkpoint commit of the last attempt in which tests were freely writable — attempt 1, plus any thawed attempt. |
| **repair attempt** | Any outer-loop iteration with `attempt >= 2` in `src/sdlc/stages/code/step.py`, including the operator-REVISE continuation. Never attempt 1. |
| **thaw** | A human decision at the fix-loop gate that runs exactly one attempt with `repair=False` and re-anchors `A` on that attempt's completion. |

---

## Verified facts this plan depends on

Each was checked against the source or reproduced on the dev box. Do not re-derive; do not "correct" them from memory.

1. **Containment already reaches opencode**, at the NATIVE layer only. `OpenCodeHarness.apply_containment` (`src/sdlc/harness/opencode.py:83-144`) compiles `path_matches` rules into `permission.edit` denies in an in-worktree `opencode.json`. So a native `path_matches` freeze enforces on *both* harnesses. This is why the freeze rule's action is `deny` and not `escalate` — see fact 2.
2. **`escalate` is hook-layer-only by validation** (`src/sdlc/harness/containment.py:131-137`). opencode has no hook layer, so an escalating freeze would land in `rules_unenforceable` there; `containment_strict` would then refuse opencode repair runs outright (`src/sdlc/stages/code/activities.py:72-77`) and non-strict would run them completely unfrozen. **The freeze rule must be `action: deny`.**
3. **`PATH_MATCHES` never fires on `Bash`.** Two independent reasons: `no-agent-config-write` does not list `Bash` in its `tools` (`policy/containment.yaml:34`), *and* `target_of` returns the **command string** for Bash (`src/sdlc/harness/containment.py:153-159`) which `fnmatch`ing against path globs will never match. **Corollary: do not "fix" `G` by adding `Bash` to its `tools` list — it would be dead code.** The Bash channel belongs entirely to the backstop.
4. **`CrewTurnInput` is constructed at exactly TWO sites**: `src/sdlc/workflows/crew.py:175` (lead) and `:321` (critics). `crew.py:511` is a `TurnRecord`, not a `CrewTurnInput`. An earlier draft of this design said three; it was wrong.
5. **`CrewTaskInput.attempt` (`crew.py:77`) is never read inside the child workflow**, and both `CrewTurnInput` sites hardcode `attempt=1`. **Therefore `repair` must never be inferred from `attempt` at the activity or turn level** — it would leave every crew repair attempt silently unfrozen. The loop is the authority; the flag is explicit.
6. **Crew already delivers `commit_sha` to the step loop.** `checkpoint_round` returns the sha, the child stores it and puts it on the returned run (`crew.py:442`, `commit_sha=commit_sha`), and `step.py:262` propagates that run intact. So `run.commit_sha` works for crew **unchanged** — no special field-read is needed. An earlier draft claimed otherwise; it was wrong, in the direction of inventing work.
7. **The real "no anchor" channels** are (a) a swallowed checkpoint-commit failure — `src/sdlc/stages/code/activities.py:147-148` sets `commit_sha` only on `returncode == 0` and returns normally either way; and (b) a crew round-1 deadline breaking *before any checkpoint* (`crew.py:156-163`), which returns a normal result with `commit_sha` still `None`. A harness **timeout** is *not* such a channel: it raises out of the activity, `step.py:511-525` has no catch, and the workflow fails — the loop never reaches attempt 2.
8. **A green attempt never reaches a gate.** `step.py:742` returns `TaskResult` on the passing path. This is the decisive reason drift must force `task_passed = False` rather than merely annotating the gate: an annotation can never fire on the case it exists for.
9. **`opencode.json` permission keys accumulate and are never removed** (`opencode.py:131-136`, `existing.setdefault(tool, {}).update(rules)`). Without explicit bookkeeping, freeze patterns written on attempt 2 persist into a thawed attempt 3 and **the human thaw silently fails on opencode**. Claude is immune: its settings tempfile is written fresh per run (`claude_code.py:119-126`).
10. **`git ls-files -v` tag semantics**, measured:
    - `S` = skip-worktree
    - any **lowercase** tag (e.g. `h`) = assume-unchanged
    - `H` = **an ordinary tracked file**
    Flagging `H` would flag every tracked file in the repo. Only `S` and lowercase tags are findings.
11. **Clearing both index bits in ONE `git update-index` invocation silently fails.** Measured: `git update-index --no-skip-worktree --no-assume-unchanged <paths>` leaves skip-worktree **set** (last flag wins) while reporting success. **Two separate invocations are required.**
12. **Git's default pathspec and Python's `fnmatch` agree exactly** on the pattern forms this plan uses, and `:(glob)` does **not** — see the measured table in Task 3. **Never use `:(glob)` in a pathspec built from these patterns.**

---

## File Structure

- **Modify:** `src/sdlc/harness/containment.py` — add `Phase` enum, `Rule.phase`, `Policy.drift_paths`, `repair` parameter on `evaluate()`, and `repair_patterns()` / `drift_globs()` accessors. Stays pure: no subprocess, no CLI knowledge.
- **Modify:** `src/sdlc/harness/hook.py` — `--repair` flag, threaded through `main()` → `decide()` → `evaluate()`.
- **Modify:** `src/sdlc/harness/base.py` — `HarnessRequest.repair: bool = False`.
- **Modify:** `src/sdlc/harness/claude_code.py` — phase-filter the native deny list *and* the hook matcher; append `--repair` in `_hook_command`.
- **Modify:** `src/sdlc/harness/opencode.py` — phase-filter the compile loop; add owned-key bookkeeping so a thaw actually removes freeze patterns.
- **Modify:** `src/sdlc/harness/models.py` — `ContainmentReport.freeze_vacuous` / `freeze_probe_matched`.
- **Modify:** `policy/containment.yaml` — the `no-test-edit-during-repair` rule (`G`) and the top-level `drift_paths` list (`C`).
- **Modify:** `src/sdlc/vcs/git.py` — new `check_test_drift` activity plus `DriftInput` / `DriftReport`.
- **Modify:** `src/sdlc/vcs/__init__.py` — export the new activity and types.
- **Modify:** `src/sdlc/stages/code/activities.py` — `CodingTaskInput.repair`, thread into `HarnessRequest`, vacuity probe, strict refusal.
- **Modify:** `src/sdlc/crew/activities.py` — `CrewTurnInput.repair`, thread into `HarnessRequest`.
- **Modify:** `src/sdlc/workflows/crew.py` — `CrewTaskInput.repair`, pass at both `CrewTurnInput` sites.
- **Modify:** `src/sdlc/stages/code/step.py` — anchor `A`, the `repair` flag, the drift call, the consequence, the thaw.
- **Modify:** `src/sdlc/core/models.py` — `GateDecision.thaw_tests`.
- **Modify:** `src/sdlc/channels/contract.py` — `Reply.thaw_tests` + one pass-through line in `default_translate`.
- **Modify:** `src/sdlc/cli.py` — `--thaw-tests` on the `revise` parser; pass through in `selector_for`.
- **Modify:** `src/sdlc/dashboard/api.py` — `DecideBody.thaw_tests`, threaded into the `Reply`.
- **Create:** `tests/test_containment_phase.py`, `tests/test_containment_dialects.py`, `tests/test_drift_backstop.py`, `tests/test_fix_loop_freeze.py`, `tests/test_thaw_plumbing.py`.
- **Modify:** `docs/reports/external-ideas-2026-09.md` — the C2 row.

**Deliberately NOT modified, and the plan must not "complete" these later:**

- **`src/sdlc/operator/tools.py`** — the MCP `decide_gate` tool does **not** get `thaw_tests`. That is an *agent* tool surface (`OperatorDeps`, `@guard`, docstrings addressed to an LLM intermediary, self-asserted actor string at `tools.py:473`). Wiring the thaw there would let an LLM intermediary set it, crossing the human-only boundary the thaw exists to draw. **This omission is the feature working.**
- **`src/sdlc/gate.py`** — no `CheckResult`, and emphatically not `ABSOLUTE_FLOOR`. Drift already forces `task_passed = False` upstream of everything `evaluate_quality_gate` judges, and floor checks ignore overrides (`gate.py:87-88`), which would directly contradict the approved thaw.
- **Slack thaw.** Slack is human-direct and shares `default_translate`, but a thaw there needs block-action plumbing. Surfaces are interchangeable *per decision*, so a Slack operator uses the dashboard or CLI for that one reply. Documented as a known limitation in Task 9.

---

### Task 1: `Phase`, `drift_paths`, and the `repair` parameter in the pure policy module + hook

**Files:**
- Modify: `src/sdlc/harness/containment.py`
- Modify: `src/sdlc/harness/hook.py`
- Test: `tests/test_containment_phase.py`

**Interfaces:**
- Produces: `Phase(StrEnum)` with members `ALWAYS = "always"` and `REPAIR = "repair"`, importable as `from sdlc.harness.containment import Phase`.
- Produces: `Rule.phase: Phase = Phase.ALWAYS`.
- Produces: `Policy.drift_paths: list[str] = []`.
- Produces: `evaluate(policy, tool, tool_input, worktree, repair: bool = False) -> Verdict` — the new parameter is keyword-or-positional-last with a default, so every existing caller and test stays valid.
- Produces: `repair_patterns(policy: Policy) -> list[str]` — every pattern from every `phase == REPAIR` rule. Used by adapters (Task 2) and the backstop (Task 4).
- Produces: `drift_globs(policy: Policy) -> list[str]` — `repair_patterns(policy) + policy.drift_paths`, de-duplicated, order-stable. This is `D`.
- Produces: `has_repair_rule(policy: Policy) -> bool` — used by the strict check in Task 8.
- Produces: `hook.decide(payload, policy, worktree, grants=None, repair: bool = False) -> dict`.

**Design notes carried into the code (write these as comments where indicated — they are the reasoning a future reader will otherwise have to re-derive):**

- **`Phase` goes beside `Predicate` and `Action`** (`containment.py:44-59`), which is the file's established idiom for a deliberately tiny vocabulary. `Predicate`'s docstring says adding to the vocabulary is "a code change plus a schema version bump" — that is the philosophy, not a prohibition; this *is* a deliberate code change.
- **NO version bump.** `policy` stays `version: 1`. Write the reasoning into the YAML header in Task 3 and as a comment on `Phase`: pydantic ignores unknown fields by default, so an *old* reader encountering `phase: repair` drops the field and enforces the rule **always** — over-enforcement, which is the *safe* direction for a fence, and it is *observable* because the denial carries the rule id (`hook.py:39-43`). The reverse skew (old policy, new code) is trivially benign: no `phase` key → `ALWAYS`. And the hook runs on the worker's own interpreter (`sys.executable`, `claude_code.py:151-157`), so in-tree skew is structurally zero — skew can only enter via a foreign `policy_path` override. The version guard at `containment.py:117-120` is reserved for a field whose old-code misread is silent **and unsafe**; this one is neither.
- **`repair` is a PARAMETER, never computed.** Mirror the existing wording on `evaluate` (`containment.py:234-237`, "`worktree` is a PARAMETER, never computed") — the same discipline, the same reason: the caller is the only actor that knows.
- **`drift_paths` is a top-level policy key, not a rule.** It is measured, never enforced, so it has no `tools`, no `predicate`, and no `action` — modelling it as a `Rule` would require a fake tool list and a fake predicate for something that is never evaluated against a tool call. Keeping it a plain list of globs makes the fence/report split *data in one hashed asset*, which is the whole point, without inventing a rule that isn't one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_containment_phase.py`:

```python
"""C2 Task 1: phase vocabulary, the repair parameter, and drift-set accessors."""

from __future__ import annotations

import pytest

from sdlc.harness.containment import (
    Action,
    ContainmentError,
    Phase,
    Policy,
    Predicate,
    Rule,
    drift_globs,
    evaluate,
    has_repair_rule,
    load_policy,
    repair_patterns,
)
from sdlc.harness.hook import decide
from sdlc.harness.models import ContainmentLayer


def _freeze_rule() -> Rule:
    return Rule(
        id="no-test-edit-during-repair",
        layer=ContainmentLayer.NATIVE,
        action=Action.DENY,
        phase=Phase.REPAIR,
        tools=["Write", "Edit", "NotebookEdit"],
        predicate=Predicate.PATH_MATCHES,
        patterns=["tests/**", "**/tests/**"],
        reason="Tests are frozen during repair.",
    )


def _always_rule() -> Rule:
    return Rule(
        id="no-agent-config-write",
        layer=ContainmentLayer.NATIVE,
        tools=["Write", "Edit"],
        predicate=Predicate.PATH_MATCHES,
        patterns=["**/.claude/**"],
        reason="The agent may not rewrite its own permission config.",
    )


WT = "/wt"


@pytest.mark.parametrize(
    "rule,target,repair,expect_allow",
    [
        # The freeze rule is INERT on pass 1 and BITES during repair.
        (_freeze_rule(), "tests/test_a.py", False, True),
        (_freeze_rule(), "tests/test_a.py", True, False),
        # A phase-less (ALWAYS) rule is unaffected by the repair bit.
        (_always_rule(), "/wt/.claude/settings.json", False, False),
        (_always_rule(), "/wt/.claude/settings.json", True, False),
        # A repair rule still only matches its own patterns.
        (_freeze_rule(), "src/app.py", True, True),
    ],
)
def test_evaluate_respects_phase(rule, target, repair, expect_allow):
    policy = Policy(version=1, rules=[rule])
    verdict = evaluate(policy, "Write", {"file_path": target}, WT, repair=repair)
    assert verdict.allow is expect_allow


def test_repair_defaults_to_false_so_existing_callers_are_unchanged():
    """Every pre-C2 call site omits `repair`; omitting it must mean pass 1."""
    policy = Policy(version=1, rules=[_freeze_rule()])
    assert evaluate(policy, "Write", {"file_path": "tests/test_a.py"}, WT).allow is True


def test_rule_without_phase_key_defaults_to_always(tmp_path):
    """Old-policy compat: a YAML with no `phase` anywhere parses and behaves
    all-always, so no version bump is needed."""
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: r1\n"
        "    layer: native\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: legacy\n",
        encoding="utf-8",
    )
    policy = load_policy(p)
    assert policy.rules[0].phase is Phase.ALWAYS
    assert policy.drift_paths == []
    # An ALWAYS rule fires in both phases.
    for repair in (False, True):
        assert evaluate(policy, "Write", {"file_path": "tests/x.py"}, WT, repair=repair).allow is False


def test_unknown_phase_value_is_a_containment_error(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: r1\n"
        "    layer: native\n"
        "    phase: sometimes\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: bad\n",
        encoding="utf-8",
    )
    with pytest.raises(ContainmentError):
        load_policy(p)


def test_drift_paths_parse_and_compose_the_drift_set(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "drift_paths:\n"
        "  - 'pyproject.toml'\n"
        "  - '**/pyproject.toml'\n"
        "rules:\n"
        "  - id: freeze\n"
        "    layer: native\n"
        "    phase: repair\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: frozen\n",
        encoding="utf-8",
    )
    policy = load_policy(p)
    assert policy.drift_paths == ["pyproject.toml", "**/pyproject.toml"]
    assert repair_patterns(policy) == ["tests/**"]
    # D = G then C, order-stable, de-duplicated.
    assert drift_globs(policy) == ["tests/**", "pyproject.toml", "**/pyproject.toml"]
    assert has_repair_rule(policy) is True


def test_drift_globs_dedupes_without_reordering():
    policy = Policy(
        version=1,
        rules=[
            Rule(
                id="freeze",
                layer=ContainmentLayer.NATIVE,
                phase=Phase.REPAIR,
                tools=["Write"],
                predicate=Predicate.PATH_MATCHES,
                patterns=["tests/**", "conftest.py"],
                reason="frozen",
            )
        ],
        drift_paths=["conftest.py", "pyproject.toml"],
    )
    assert drift_globs(policy) == ["tests/**", "conftest.py", "pyproject.toml"]


def test_has_repair_rule_false_when_policy_carries_none():
    assert has_repair_rule(Policy(version=1, rules=[_always_rule()])) is False


def test_repair_patterns_ignores_always_rules():
    policy = Policy(version=1, rules=[_always_rule(), _freeze_rule()])
    assert repair_patterns(policy) == ["tests/**", "**/tests/**"]


# --- hook ---------------------------------------------------------------

def _payload(target: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": target}, "tool_use_id": "tu_1"}


def test_hook_decide_allows_test_write_on_pass_one():
    policy = Policy(version=1, rules=[_freeze_rule()])
    out = decide(_payload("tests/test_a.py"), policy, WT, repair=False)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_hook_decide_denies_test_write_during_repair():
    policy = Policy(version=1, rules=[_freeze_rule()])
    out = decide(_payload("tests/test_a.py"), policy, WT, repair=True)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    # The rule id must ride the reason -- normalise_denials reads it back out.
    assert hso["permissionDecisionReason"].startswith("[no-test-edit-during-repair] ")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_containment_phase.py -q`
Expected: FAIL — `ImportError: cannot import name 'Phase' from 'sdlc.harness.containment'`.

- [ ] **Step 3: Add `Phase`, `Rule.phase`, `Policy.drift_paths` and the accessors**

In `src/sdlc/harness/containment.py`, add after the `Action` class (which ends at line 59):

```python
class Phase(StrEnum):
    """WHEN a rule is active. `always` is every rule that existed before C2
    and stays the default, so an old policy file parses unchanged.

    Deliberately not version-bumped (the asset stays `version: 1`). An OLD
    reader encountering `phase: repair` drops the unknown field (pydantic
    ignores extras) and enforces the rule ALWAYS -- over-enforcement, which
    is the safe direction for a fence, and observable because the denial
    carries the rule id. The reverse skew is benign: no key -> ALWAYS. The
    hook runs on the worker's own interpreter, so in-tree skew is zero; it
    can only enter through a foreign `policy_path` override. The version
    guard is reserved for a field whose old-code misread is silent AND
    unsafe."""

    ALWAYS = "always"
    REPAIR = "repair"
```

Add the field to `Rule` (after `action`, so the declaration order reads `layer, action, phase`):

```python
    phase: Phase = Phase.ALWAYS  # C2: `repair` rules are inert on pass 1
```

Add the field to `Policy` (after `rules`):

```python
    # C2: globs that are MEASURED by the drift backstop but never enforced
    # by any adapter -- test/build config and dependency manifests, which
    # are sometimes legitimately edited during repair. Not modelled as a
    # Rule: a rule needs `tools`/`predicate`/`action` to be evaluated
    # against a tool call, and these are only ever evaluated against a diff.
    drift_paths: list[str] = Field(default_factory=list)
```

In `load_policy`, pass the new key through when constructing the `Policy` (the `rules` loop is unchanged — pydantic validates `phase` for free and an unknown value raises inside the existing `except Exception` that re-types to `ContainmentError`):

```python
    drift_paths = list(raw.get("drift_paths") or [])
    return Policy(
        version=version, rules=rules, drift_paths=drift_paths, source_path=p.resolve()
    )
```

Add the accessors after `evaluate`:

```python
def repair_patterns(policy: Policy) -> list[str]:
    """Every pattern carried by a repair-phase rule -- the fence set G.

    One definition, read by three consumers: the two adapters compile it
    into their own deny syntax, and the drift backstop measures content
    under it. Two notions of "the tests" would drift apart; this one
    cannot."""
    return [pat for rule in policy.rules if rule.phase is Phase.REPAIR for pat in rule.patterns]


def drift_globs(policy: Policy) -> list[str]:
    """The drift set D = G u C: fenced paths plus report-only paths.

    De-duplicated, order-stable (G first) so a pathspec built from it is
    deterministic across replays."""
    out: list[str] = []
    for pat in [*repair_patterns(policy), *policy.drift_paths]:
        if pat not in out:
            out.append(pat)
    return out


def has_repair_rule(policy: Policy) -> bool:
    """Whether this policy fences anything at all during repair. A policy
    with none leaves repair sessions hook-unfrozen (the backstop still
    runs), which `containment_strict` refuses -- see the strict check in
    stages/code/activities.py."""
    return any(rule.phase is Phase.REPAIR for rule in policy.rules)
```

Finally, thread the parameter through `_rule_denies` and `evaluate`:

```python
def evaluate(
    policy: Policy, tool: str, tool_input: dict, worktree: str, repair: bool = False
) -> Verdict:
    """First matching rule wins. `worktree` and `repair` are both
    PARAMETERS, never computed: create_worktree may return <task>.N after a
    Windows lock fallback and its returned path is authoritative
    (activities.py:260-274); and only the fix loop knows whether this is a
    repair attempt -- `attempt` is hardcoded to 1 at both CrewTurnInput
    construction sites, so inferring it activity-side would silently unfreeze
    every crew repair attempt."""
    for rule in policy.rules:
        if rule.phase is Phase.REPAIR and not repair:
            continue
        if _rule_denies(rule, tool, tool_input, worktree):
            return Verdict(allow=False, rule_id=rule.id, reason=rule.reason, action=rule.action)
    return Verdict(allow=True)
```

- [ ] **Step 4: Add the `--repair` flag to the hook**

In `src/sdlc/harness/hook.py`, change `decide` and `main`:

```python
def decide(
    payload: dict,
    policy: Policy,
    worktree: str,
    grants: list[ToolGrant] | None = None,
    repair: bool = False,
) -> dict:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return _decision("allow")
    verdict = evaluate(policy, tool, tool_input, worktree, repair=repair)
    ...
```

(the body below `verdict = ...` is unchanged)

and in `main`:

```python
    ap.add_argument("--grants", default=None)
    # C2: set by the adapter when this invocation is a REPAIR attempt. The
    # flag lives in the out-of-worktree settings file, so the agent cannot
    # flip it.
    ap.add_argument("--repair", action="store_true")
    args = ap.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
        policy = load_policy(args.policy)
        grants = load_grants(args.grants)
        out = decide(payload, policy, args.worktree, grants, repair=args.repair)
```

Also extend the module docstring's contract paragraph with one line:

```
C2: `--repair` activates `phase: repair` rules (the contract's test files).
Absent = pass 1 = those rules are inert, which is how the dev is free to
author the tests in the first place.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_containment_phase.py -q`
Expected: PASS (all tests).

- [ ] **Step 6: Run the existing containment suite to prove nothing regressed**

Run: `python -m pytest tests/ -q -k "containment or hook"`
Expected: PASS. The `repair` default of `False` means every pre-C2 call site keeps its exact previous behaviour.

- [ ] **Step 7: Commit**

```bash
git add src/sdlc/harness/containment.py src/sdlc/harness/hook.py tests/test_containment_phase.py
git commit -m "feat(containment): add repair phase to the rule vocabulary

A rule may declare `phase: repair`, making it inert on the first
implementation pass and active only during bounded repair attempts.
`repair` is a parameter on evaluate() and a --repair flag on the hook,
never inferred -- CrewTurnInput hardcodes attempt=1 at both construction
sites, so activity-side inference would unfreeze every crew repair.

Also adds `drift_paths`: globs measured by the deterministic backstop but
never enforced by an adapter. No policy version bump: an old reader drops
an unknown `phase` and over-enforces, which is the safe direction.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 2: Phase-aware compilation in both adapters, with the opencode thaw fix

**Files:**
- Modify: `src/sdlc/harness/base.py` (add `HarnessRequest.repair`)
- Modify: `src/sdlc/harness/claude_code.py`
- Modify: `src/sdlc/harness/opencode.py`
- Test: `tests/test_containment_dialects.py`

**Interfaces:**
- Consumes: `Phase`, `repair_patterns` from Task 1.
- Produces: `HarnessRequest.repair: bool = False` — the field both adapters read, set by the activities in Task 5.
- Produces: `OpenCodeHarness._owned_patterns(policy) -> list[str]` — the freeze patterns this adapter is responsible for adding *or removing* from `opencode.json`.

**Design notes carried into the code:**

- **Three enforcement sites must agree**, or the layers contradict each other — e.g. the native floor denying test writes on pass 1 while the hook allows. All three read the bit off the `req` they already receive:
  1. `claude_code.py:110-115` — the native `permissions.deny` list.
  2. `claude_code.py:94-108` — the hook **matcher**. Filter this too, so that on pass 1 the compiled settings file is byte-identical to today's and no Write/Edit pays a hook process spawn that can only ever return `allow`.
  3. `opencode.py:103-118` — the compile loop.
  Plus `_hook_command` appends `--repair`.
- **The opencode thaw fix (fact 9).** `apply_containment` must compute the freeze pattern set from the policy **regardless of phase**, then *add or remove* exactly those keys per `req.repair`. Removal must be conservative: only delete a key whose pattern is one of ours **and** whose current value is exactly `"deny"`. If the repo's own `opencode.json` already carried e.g. `"tests/**": "allow"`, attempt 2's `update()` would overwrite it and an unconditional removal would then delete the repo's key outright — "preserved" failing precisely when it matters. The residual (a repo key whose pattern collides with `G` *and* whose value is `"deny"` is indistinguishable from ours, and gets removed on thaw) is accepted and must be written as a comment.
- **Scope removal to the `edit` bucket only.** `G` is `PATH_MATCHES`, which compiles to `edit`. A future `COMMAND_MATCHES` repair rule would live in `bash`; removing blindly across buckets would be wrong the day that lands.

- [ ] **Step 1: Write the failing dialect + compilation tests**

Create `tests/test_containment_dialects.py`:

```python
"""C2 Task 2: the same G, compiled by every engine, must select the same files.

The failure this file exists to catch: a pattern that is PRESENT in an
engine's output but MATCHES NOTHING there. Presence assertions ("the freeze
pattern is in the deny list") sail straight past it. Every assertion here
evaluates a TARGET.
"""

from __future__ import annotations

import fnmatch
import json
import subprocess
from pathlib import Path

import pytest

from sdlc.harness.base import HarnessRequest
from sdlc.harness.claude_code import ClaudeCodeHarness
from sdlc.harness.containment import (
    Action,
    Phase,
    Policy,
    Predicate,
    Rule,
    evaluate,
    repair_patterns,
)
from sdlc.harness.models import ContainmentLayer
from sdlc.harness.opencode import OpenCodeHarness

# The three probe shapes. The ROOT-FILENAME probe is the one that catches
# the `**/`-prefix trap: `**/conftest.py` matches tests/unit/conftest.py but
# NOT a repo-root conftest.py, in git's pathspec AND in fnmatch alike.
NESTED_REL = "tests/unit/test_auth.py"
NESTED_ABS = "/wt/tests/unit/test_auth.py"
ROOT_REL = "conftest.py"


def _policy() -> Policy:
    return Policy(
        version=1,
        rules=[
            Rule(
                id="no-test-edit-during-repair",
                layer=ContainmentLayer.NATIVE,
                action=Action.DENY,
                phase=Phase.REPAIR,
                tools=["Write", "Edit", "NotebookEdit"],
                predicate=Predicate.PATH_MATCHES,
                patterns=["tests/**", "**/tests/**", "conftest.py", "**/conftest.py"],
                reason="Tests are frozen during repair.",
            )
        ],
    )


@pytest.mark.parametrize("target", [NESTED_REL, NESTED_ABS, ROOT_REL])
def test_hook_engine_denies_every_probe_shape_during_repair(target):
    """Engine 1: fnmatch, via evaluate(). All three shapes must be covered
    by the paired pattern forms."""
    v = evaluate(_policy(), "Write", {"file_path": target}, "/wt", repair=True)
    assert v.allow is False, f"{target} escaped the fence"


@pytest.mark.parametrize("target", [NESTED_REL, NESTED_ABS, ROOT_REL])
def test_hook_engine_allows_every_probe_shape_on_pass_one(target):
    v = evaluate(_policy(), "Write", {"file_path": target}, "/wt", repair=False)
    assert v.allow is True


@pytest.mark.parametrize("target", [NESTED_REL, NESTED_ABS, ROOT_REL])
def test_claude_native_deny_globs_select_every_probe_shape(target):
    """Engine 2: claude's `Tool(pattern)` deny syntax. We cannot run claude
    here, so evaluate the PATTERN half of each emitted entry with the same
    glob semantics claude applies, and assert a match."""
    h = ClaudeCodeHarness()
    req = HarnessRequest(prompt="p", cwd="/wt", repair=True)
    h.apply_containment(_policy(), req)
    settings = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))
    deny = settings["permissions"]["deny"]
    pats = [e[e.index("(") + 1 : -1] for e in deny if e.startswith("Write(")]
    assert any(fnmatch.fnmatch(target, p) for p in pats), f"{target} matched none of {pats}"


def test_claude_emits_no_freeze_rule_on_pass_one():
    h = ClaudeCodeHarness()
    req = HarnessRequest(prompt="p", cwd="/wt", repair=False)
    h.apply_containment(_policy(), req)
    settings = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))
    assert settings["permissions"]["deny"] == []
    # And the hook matcher must be empty too, so pass 1 spawns no hook at all.
    assert settings["hooks"]["PreToolUse"] == []


def test_claude_hook_command_carries_repair_only_during_repair():
    h = ClaudeCodeHarness()
    for repair in (True, False):
        req = HarnessRequest(prompt="p", cwd="/wt", repair=repair)
        h.apply_containment(_policy(), req)
        settings = json.loads(Path(_settings_path(req)).read_text(encoding="utf-8"))
        hooks = settings["hooks"]["PreToolUse"]
        if repair:
            assert "--repair" in hooks[0]["hooks"][0]["command"]
        else:
            assert hooks == []


def _settings_path(req: HarnessRequest) -> str:
    """The tempfile path apply_containment appended as `--settings <path>`."""
    return req.extra_args[req.extra_args.index("--settings") + 1]


@pytest.mark.parametrize("target", [NESTED_REL, ROOT_REL])
def test_opencode_edit_bucket_selects_every_relative_probe(tmp_path, target):
    """Engine 3: opencode's permission.edit globs. opencode resolves paths
    relative to the worktree, so the absolute probe does not apply here."""
    h = OpenCodeHarness()
    req = HarnessRequest(prompt="p", cwd=str(tmp_path), repair=True)
    h.apply_containment(_policy(), req)
    doc = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    pats = [p for p, v in doc["permission"]["edit"].items() if v == "deny"]
    assert any(fnmatch.fnmatch(target, p) for p in pats), f"{target} matched none of {pats}"


def test_opencode_thaw_removes_the_freeze_it_added(tmp_path):
    """The defect this exists for: opencode's merge is append-only, so
    without owned-key bookkeeping the freeze RATCHETS and a human thaw
    silently fails on this harness."""
    h = OpenCodeHarness()
    cfg = tmp_path / "opencode.json"

    # attempt 2: frozen
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=True))
    frozen = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["edit"]
    assert "tests/**" in frozen

    # attempt 3: THAWED -- the freeze keys must be gone from the file on disk
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=False))
    thawed = json.loads(cfg.read_text(encoding="utf-8"))["permission"]["edit"]
    assert "tests/**" not in thawed
    assert "conftest.py" not in thawed


def test_opencode_preserves_repo_authored_permission_keys_across_freeze_and_thaw(tmp_path):
    cfg = tmp_path / "opencode.json"
    cfg.write_text(
        json.dumps({"permission": {"edit": {"secrets/**": "deny"}}, "plugin": ["x"]}),
        encoding="utf-8",
    )
    h = OpenCodeHarness()
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=True))
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=False))
    doc = json.loads(cfg.read_text(encoding="utf-8"))
    assert doc["permission"]["edit"]["secrets/**"] == "deny"  # repo key survives both
    assert doc["plugin"] == ["x"]  # unrelated config survives


def test_opencode_removal_is_scoped_to_the_edit_bucket(tmp_path):
    """G is PATH_MATCHES -> `edit`. A same-named key in `bash` is not ours."""
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"permission": {"bash": {"tests/**": "deny"}}}), encoding="utf-8")
    h = OpenCodeHarness()
    h.apply_containment(_policy(), HarnessRequest(prompt="p", cwd=str(tmp_path), repair=False))
    doc = json.loads(cfg.read_text(encoding="utf-8"))
    assert doc["permission"]["bash"]["tests/**"] == "deny"


@pytest.mark.parametrize("target", [NESTED_REL, ROOT_REL])
def test_git_pathspec_selects_every_relative_probe(tmp_path, target):
    """Engine 4: git pathspec, used by the drift backstop. MEASURED, not
    assumed: git's DEFAULT pathspec agrees with fnmatch on these forms;
    `:(glob)` does NOT, which is why the backstop must never use it."""
    repo = tmp_path / "r"
    (repo / "tests" / "unit").mkdir(parents=True)
    run = lambda *a: subprocess.run(
        ["git", *a], cwd=repo, check=True, capture_output=True, text=True
    )
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    for f in (NESTED_REL, ROOT_REL):
        (repo / f).write_text("x\n", encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "base")
    anchor = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    (repo / target).write_text("WEAKENED\n", encoding="utf-8")

    pats = repair_patterns(_policy())
    out = subprocess.run(
        ["git", "diff", "--name-only", anchor, "--", *pats],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert target in out, f"{target} invisible to the git dialect via {pats}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_containment_dialects.py -q`
Expected: FAIL — `TypeError: HarnessRequest.__init__() got an unexpected keyword argument 'repair'`.

- [ ] **Step 3: Add `repair` to `HarnessRequest`**

In `src/sdlc/harness/base.py`, after the `write_root` field (line 122):

```python
    # C2: whether this is a REPAIR attempt (attempt >= 2 in the code stage's
    # fix loop, including the operator-REVISE continuation), which activates
    # `phase: repair` policy rules -- the contract's test files. Set by the
    # LOOP, never inferred here: both CrewTurnInput construction sites
    # hardcode attempt=1, so an activity-side inference would silently
    # unfreeze every crew repair attempt. A thawed attempt sets this back to
    # False for exactly one attempt.
    repair: bool = False
```

- [ ] **Step 4: Phase-filter the claude adapter and pass `--repair`**

In `src/sdlc/harness/claude_code.py`, replace the body of `apply_containment` between `grants_path = ...` and `doc = {...}`:

```python
        grants_path = self._write_grants(grants)
        # C2: rules whose phase does not match this invocation are compiled
        # into NEITHER layer. Filtering the MATCHER too (not just the deny
        # list) keeps a pass-1 settings file byte-identical to pre-C2: with
        # no repair rules active, no Write/Edit pays a hook spawn that could
        # only ever return allow.
        active = [
            r for r in policy.rules if r.phase is not Phase.REPAIR or req.repair
        ]
        hooks = (
            [
                {
                    "matcher": "|".join(sorted({t for r in active for t in r.tools})),
                    "hooks": [
                        {
                            "type": "command",
                            "command": self._hook_command(
                                req, policy.source_path, grants_path
                            ),
                        }
                    ],
                }
            ]
            if active
            else []
        )

        deny = [
            p
            for r in active
            if ContainmentLayer.NATIVE is r.layer
            for p in self._native_patterns(r)
        ]
```

and change the `ContainmentReport` construction at the end to report on `active`:

```python
        return ContainmentReport(
            enabled=True,
            layers_active=[ContainmentLayer.NATIVE, ContainmentLayer.HOOK],
            rules_enforced=[r.id for r in active],
            rules_unenforceable=[],
            rules_escalatable=[r.id for r in active if r.action is Action.ESCALATE],
        )
```

In `_hook_command`, append the flag (it already receives `req`):

```python
        if grants_path is not None:
            cmd += f' --grants "{Path(grants_path).as_posix()}"'
        # C2: activates `phase: repair` rules for this invocation. The hook
        # command line lives in the OUT-OF-WORKTREE settings file, so the
        # agent cannot flip it.
        if req.repair:
            cmd += " --repair"
        return cmd
```

Add `Phase` to the existing `from .containment import (...)` block.

- [ ] **Step 5: Phase-filter opencode and add owned-key bookkeeping**

In `src/sdlc/harness/opencode.py`, add `Phase` and `repair_patterns` to the containment import, then add the helper and rewrite the merge:

```python
    @staticmethod
    def _owned_patterns(policy: Policy) -> list[str]:
        """The freeze patterns THIS adapter is responsible for adding and
        removing. Computed from the policy REGARDLESS of phase, because on a
        thawed attempt we must still know which keys to take back out."""
        return repair_patterns(policy)
```

and in `apply_containment`, filter the compile loop:

```python
        for rule in policy.rules:
            if rule.phase is Phase.REPAIR and not req.repair:
                continue  # C2: inert on the free first pass
            if ContainmentLayer.HOOK is rule.layer:
```

then replace the merge block (currently `existing = doc.get("permission") ...`) with:

```python
        # Merge into the worktree's opencode.json so an existing config
        # (e.g. the repo's plugin block) is preserved, not clobbered.
        #
        # C2: this merge is APPEND-ONLY by construction (`update()` never
        # removes), which would make the freeze RATCHET: patterns written on
        # a repair attempt would survive into a thawed one and the human's
        # thaw would silently fail on this harness. So freeze keys we own are
        # explicitly taken back out when this invocation is not a repair.
        # Conservative on purpose: we only remove a key whose pattern is ours
        # AND whose current value is exactly "deny". RESIDUAL, accepted: a
        # repo-authored key that collides with one of our patterns and is
        # also "deny" is indistinguishable from ours and will be removed on
        # thaw. Scoped to the `edit` bucket because G is PATH_MATCHES; a
        # future COMMAND_MATCHES repair rule would live in `bash`.
        existing = doc.get("permission")
        if isinstance(existing, dict):
            for tool, rules in perms.items():
                existing.setdefault(tool, {}).update(rules)
            perms = existing
        if not req.repair:
            edit = perms.get("edit")
            if isinstance(edit, dict):
                for pat in self._owned_patterns(policy):
                    if edit.get(pat) == "deny":
                        edit.pop(pat, None)
        doc["permission"] = perms
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_containment_dialects.py -q`
Expected: PASS. If `test_git_pathspec_selects_every_relative_probe` fails for `ROOT_REL`, the pattern list is missing a bare (non-`**/`-prefixed) form — fix `_policy()`'s patterns, not the test.

- [ ] **Step 7: Run the full harness suite**

Run: `python -m pytest tests/ -q -k "harness or containment or opencode or claude"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/harness/base.py src/sdlc/harness/claude_code.py src/sdlc/harness/opencode.py tests/test_containment_dialects.py
git commit -m "feat(harness): compile repair-phase rules per attempt in both adapters

HarnessRequest.repair rides alongside write_root and is read by all three
enforcement sites: claude's native deny list, claude's hook matcher (so a
pass-1 settings file stays byte-identical to pre-C2), and opencode's
permission.edit bucket. _hook_command appends --repair.

opencode's merge is append-only, so freeze patterns would ratchet and a
human thaw would silently fail there; the adapter now takes back out the
keys it owns when an attempt is not a repair, conservatively (ours AND
value == deny), scoped to the edit bucket.

The dialect test evaluates targets rather than asserting pattern presence:
a pattern present but matching nothing in an engine is the failure mode
that presence assertions cannot see.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 3: The policy asset — `G`, `C`, and the reason string

**Files:**
- Modify: `policy/containment.yaml`
- Test: `tests/test_containment_dialects.py` (add a test that runs the *shipped* policy through the same probes)

**Interfaces:**
- Consumes: `Phase`, `drift_paths`, `repair_patterns`, `drift_globs` from Task 1.
- Produces: rule id `no-test-edit-during-repair` — referenced by the strict check (Task 8) and by the denial-reason assertions.

**The measured dialect table this rule's shape is derived from.** Run on the Windows dev box against real git; reproduce it before changing any pattern:

| pattern | git **default** pathspec | python `fnmatch` |
|---|---|---|
| `*_test.py` | `root_test.py`, `tests/unit/deep_test.py` | identical |
| `**/*_test.py` | `tests/unit/deep_test.py` **only** | identical |
| `conftest.py` | `conftest.py` **only** | identical |
| `**/conftest.py` | `tests/unit/conftest.py` **only** | identical |
| `tests/**` | both nested files | identical |
| `**/tests/**` | **nothing** | **nothing** |

Two conclusions, both load-bearing:
1. **Git's default pathspec and `fnmatch` agree exactly.** `:(glob)` does **not** (`:(glob)**/*_test.py` starts matching root-level files). **The backstop must build a plain pathspec and never prefix `:(glob)`.**
2. **`**/tests/**` matches nothing relative.** It earns its place only because the hook sees *absolute* `file_path` targets inside the worktree. **Every convention therefore needs both forms** — the bare relative one for git and for relative tool targets, the `**/`-prefixed one for absolute tool targets.

**Design notes:**

- **The denial reason is an instruction surface.** It reaches the model verbatim (`hook.py:8-10`). Write what to do *instead*, not only what is forbidden — this measurably reduces fence-bashing retry loops and costs one sentence of YAML.
- **`G` errs broad-but-shaped.** The governing asymmetry: over-breadth costs a thaw (recoverable, human-visible); under-breadth costs integrity (silent).
- **`contract.stack` is deliberately unused.** Per-stack derivation of `G` was considered and rejected — the contract is frozen before code exists, so it could only carry guesses, and a derived-from-attempt-1 file list is blind to the pre-existing suite a brownfield task never touched (which `pytest -q` still collects and judges).

- [ ] **Step 1: Write the failing test against the shipped policy**

Append to `tests/test_containment_dialects.py`:

```python
def test_shipped_policy_freezes_every_probe_shape_during_repair():
    """The rule that actually ships must pass the same probes as the fixture.

    A fixture-only guarantee is worthless: the fixture is not what runs."""
    from sdlc.harness.containment import load_policy

    policy = load_policy(Path(__file__).resolve().parents[1] / "policy" / "containment.yaml")
    for target in (NESTED_REL, NESTED_ABS, ROOT_REL, "/wt/conftest.py", "src/util_test.go"):
        assert (
            evaluate(policy, "Write", {"file_path": target}, "/wt", repair=True).allow is False
        ), f"shipped policy lets {target} through during repair"
        assert (
            evaluate(policy, "Write", {"file_path": target}, "/wt", repair=False).allow is True
        ), f"shipped policy blocks {target} on the FREE first pass"


def test_shipped_policy_does_not_list_bash_on_the_freeze_rule():
    """PATH_MATCHES can never fire on Bash -- target_of returns the COMMAND
    string for it. Listing Bash would be dead code that reads like coverage.
    The Bash channel belongs to the drift backstop."""
    from sdlc.harness.containment import load_policy

    policy = load_policy(Path(__file__).resolve().parents[1] / "policy" / "containment.yaml")
    freeze = next(r for r in policy.rules if r.id == "no-test-edit-during-repair")
    assert "Bash" not in freeze.tools


def test_shipped_policy_drift_set_covers_test_config():
    from sdlc.harness.containment import drift_globs, load_policy

    policy = load_policy(Path(__file__).resolve().parents[1] / "policy" / "containment.yaml")
    d = drift_globs(policy)
    for expected in ("pyproject.toml", "pytest.ini", "tests/**", "requirements.txt"):
        assert expected in d, f"{expected} missing from the drift set D"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_containment_dialects.py -q -k shipped`
Expected: FAIL — `StopIteration` (no rule with that id yet).

- [ ] **Step 3: Add the freeze rule and the drift paths to the policy asset**

Append to `policy/containment.yaml` (and add the `drift_paths` block at the top level, after `version: 1`):

```yaml
# C2: paths the deterministic drift backstop MEASURES but no adapter ever
# denies. Test/build config and dependency manifests are sometimes
# legitimately edited during a repair attempt (a dependency bump is a real
# fix), so fencing them would block honest work -- but a repair attempt that
# disables the suite via `addopts = "--ignore=tests"` must never complete
# silently green. Measured, reported to the human at the fix-loop gate.
drift_paths:
  - "pyproject.toml"
  - "**/pyproject.toml"
  - "setup.cfg"
  - "**/setup.cfg"
  - "pytest.ini"
  - "**/pytest.ini"
  - "tox.ini"
  - "**/tox.ini"
  - "jest.config.*"
  - "**/jest.config.*"
  - "vitest.config.*"
  - "**/vitest.config.*"
  - ".github/workflows/**"
  - "**/.github/workflows/**"
  - "requirements.txt"
  - "**/requirements.txt"
  - "requirements-dev.txt"
  - "**/requirements-dev.txt"
  - "package.json"
  - "**/package.json"
  - "go.mod"
  - "**/go.mod"
  - "Cargo.toml"
  - "**/Cargo.toml"
```

and the rule itself:

```yaml
  # C2. `phase: repair` makes this rule INERT on the first implementation
  # pass -- the dev must be free to author the contract's tests -- and active
  # only during bounded repair attempts, where editing the tests that judge
  # you is the reward hack this row exists to close.
  #
  # PATTERN FORMS ARE PAIRED ON PURPOSE. `**/tests/**` matches nothing
  # relative; `tests/**` matches nothing absolute. The hook sees ABSOLUTE
  # file_path targets, git's pathspec (used by the drift backstop) sees
  # RELATIVE ones. Measured: git's DEFAULT pathspec and Python's fnmatch
  # agree exactly on these forms. Dropping either half of a pair makes one
  # engine silently vacuous. See tests/test_containment_dialects.py.
  #
  # `tools` deliberately EXCLUDES Bash: PATH_MATCHES compares against
  # target_of(), which returns the COMMAND STRING for Bash, so a Bash entry
  # here would be dead code that reads like coverage. `sed -i`, `cat >`,
  # `python -c` and `git rm` are caught deterministically by the drift
  # backstop instead (src/sdlc/vcs/git.py:check_test_drift).
  - id: no-test-edit-during-repair
    layer: native               # enforced by BOTH adapters; opencode has no hook
    action: deny                # NOT escalate: escalate is hook-only by
                                # validation, opencode has no hook layer, so an
                                # escalating freeze would be unenforceable there
    phase: repair
    tools: [Write, Edit, NotebookEdit]
    predicate: path_matches
    patterns:
      # directories
      - "tests/**"
      - "**/tests/**"
      - "test/**"
      - "**/test/**"
      - "spec/**"
      - "**/spec/**"
      - "__tests__/**"
      - "**/__tests__/**"
      - "src/test/**"
      - "**/src/test/**"
      # file shapes (Go and flat-layout Python have no directory to catch)
      - "test_*.py"
      - "**/test_*.py"
      - "*_test.py"
      - "**/*_test.py"
      - "*_test.go"
      - "**/*_test.go"
      - "*.test.*"
      - "**/*.test.*"
      - "*.spec.*"
      - "**/*.spec.*"
      - "*Test.php"
      - "**/*Test.php"
      # framework plumbing: conftest.py is the collection-time skip channel,
      # and a weakened snapshot is a weakened assertion
      - "conftest.py"
      - "**/conftest.py"
      - "__snapshots__/**"
      - "**/__snapshots__/**"
      - "*.snap"
      - "**/*.snap"
    reason: >-
      Tests are frozen during repair attempts: you may not edit, create or
      delete test files while fixing the code they judge. If you believe a
      test itself is wrong, do NOT try to change it -- say so explicitly in
      your final summary, with the file and the assertion, and an operator
      will decide at the review gate.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_containment_dialects.py -q`
Expected: PASS (all, including the shipped-policy probes).

- [ ] **Step 5: Verify no existing behaviour changed on pass 1**

Run: `python -m pytest tests/ -q -k "containment or policy"`
Expected: PASS. The new rule is `phase: repair`, so with `repair=False` (every pre-C2 call site) the compiled output is unchanged.

- [ ] **Step 6: Commit**

```bash
git add policy/containment.yaml tests/test_containment_dialects.py
git commit -m "feat(policy): add the repair-phase test freeze rule and the drift set

G (the fence): paired relative/absolute glob forms for tests dirs, pytest
and Go file shapes, conftest.py and snapshots. Paired on purpose --
'**/tests/**' matches nothing relative and 'tests/**' nothing absolute,
while the hook sees absolute targets and git's pathspec relative ones.

C (drift_paths, measured never fenced): test/build config and dependency
manifests, which repair attempts sometimes legitimately edit -- but which
must not let a suite-disabling edit complete silently green.

The reason string is an instruction surface (it reaches the model
verbatim), so it says what to do instead of editing a test.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 4: The drift backstop activity

**Files:**
- Modify: `src/sdlc/vcs/git.py`
- Modify: `src/sdlc/vcs/__init__.py`
- Test: `tests/test_drift_backstop.py`

**Interfaces:**
- Consumes: `drift_globs` / `repair_patterns` from Task 1 (the *caller* resolves the globs; the activity takes them as data, so it stays independent of policy loading).
- Produces: `@dataclass DriftInput(worktree: str, anchor: str, fence_globs: list[str], report_globs: list[str])`.
- Produces: `class DriftReport(BaseModel)` with `available: bool`, `unavailable_reason: str = ""`, `fence_paths: list[str]`, `report_paths: list[str]`, `index_bit_paths: list[str]`, `patch: str`, and a property `found: bool` (true when any of the three path lists is non-empty).
- Produces: `@activity.defn async def check_test_drift(inp: DriftInput) -> DriftReport`.

**Why a new sibling activity rather than a field on `get_task_diff`:** `get_task_diff` has other callers (analyze, review, handoff) that would inherit a field they cannot interpret; its anchor semantics differ (`branch_point...HEAD` at `git.py:98` vs `A..worktree` here); `DiffInput` would grow anchor/glob parameters meaningless to every other caller; and drift output must be structured per-path status and **untruncated**, unlike the 60k-capped patch at `git.py:102`.

**Design notes carried into the code — this is the task where a plausible-looking implementation is wrong:**

- **Order is detect → record → clear → diff, and all four steps are required.** Detection without clearing hands the human an accusation with no patch (the diff genuinely reports nothing while the bit is set). Clearing without recording destroys the only evidence of intent, because the bit is index-local state that is never committed — once cleared, the revealed content change is indistinguishable from ordinary drift. The bit-setting is a **different finding** (evasion) from the revealed content change (weakening); both must reach the human.
- **`git ls-files -v` tags (measured, fact 10):** `S` = skip-worktree, **any lowercase** tag = assume-unchanged, `H` = an ordinary tracked file. **Flagging `H` would flag every tracked file in the repo.**
- **Clearing needs TWO invocations (measured, fact 11).** `git update-index --no-skip-worktree --no-assume-unchanged <paths>` silently leaves skip-worktree set — the last flag wins — while exiting 0. Issue `--no-skip-worktree` and `--no-assume-unchanged` separately.
- **Never use `:(glob)`** when building the pathspec (fact 12 / Task 3's table).
- **Any error is `available=False`, never a clean pass.** A drift check whose transient failure reads as "no drift" reopens exactly the hole ADR-17 closes for the fence. Mirror the fail-closed posture: on any git failure or unresolvable anchor, return `available=False` with the reason, and let the caller surface it.
- **Clearing index bits under a live, resumable session is safe.** `update-index` touches only index metadata — no checkout, no merge, no content operation. The drift activity runs between attempts (the harness process has exited; crew turns are sequential), so there is no concurrent git and no `index.lock` contention. A resumed session that re-sets the bit is simply detected again; the finding is idempotent.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_drift_backstop.py`:

```python
"""C2 Task 4: the deterministic backstop.

Real git fixtures throughout: drift semantics cannot be faked with dicts,
and the delete and index-bit channels only exist in a real repository.
"""

from __future__ import annotations

import subprocess

import pytest

from sdlc.vcs import DriftInput, DriftReport, check_test_drift

FENCE = ["tests/**", "**/tests/**", "conftest.py", "**/conftest.py"]
REPORT = ["pyproject.toml", "**/pyproject.toml"]


def _git(repo, *args) -> str:
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    (r / "tests").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "."], cwd=r, check=True)
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    (r / "tests" / "test_auth.py").write_text("def test_a():\n    assert 1 == 2\n", encoding="utf-8")
    (r / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (r / "src.py").write_text("x = 1\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r


def _anchor(repo) -> str:
    return _git(repo, "rev-parse", "HEAD").strip()


async def _run(repo, anchor) -> DriftReport:
    return await check_test_drift(
        DriftInput(
            worktree=str(repo), anchor=anchor, fence_globs=FENCE, report_globs=REPORT
        )
    )


@pytest.mark.asyncio
async def test_clean_worktree_reports_no_drift(repo):
    r = await _run(repo, _anchor(repo))
    assert r.available is True
    assert r.found is False


@pytest.mark.asyncio
async def test_source_only_change_is_not_drift(repo):
    a = _anchor(repo)
    (repo / "src.py").write_text("x = 2\n", encoding="utf-8")
    r = await _run(repo, a)
    assert r.found is False


@pytest.mark.asyncio
async def test_bash_channel_write_to_a_test_is_fence_drift(repo):
    """The channel the hook structurally cannot see: no Write/Edit tool call
    was made at all."""
    a = _anchor(repo)
    (repo / "tests" / "test_auth.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    r = await _run(repo, a)
    assert r.fence_paths == ["tests/test_auth.py"]
    assert "assert True" in r.patch


@pytest.mark.asyncio
async def test_deleted_test_is_fence_drift(repo):
    a = _anchor(repo)
    (repo / "tests" / "test_auth.py").unlink()
    r = await _run(repo, a)
    assert r.fence_paths == ["tests/test_auth.py"]


@pytest.mark.asyncio
async def test_created_test_is_fence_drift(repo):
    """Weakening-by-creation: a new conftest.py with a collection-wide skip
    never edits an existing test."""
    a = _anchor(repo)
    (repo / "conftest.py").write_text("collect_ignore_glob = ['*']\n", encoding="utf-8")
    _git(repo, "add", "-A")
    r = await _run(repo, a)
    assert "conftest.py" in r.fence_paths


@pytest.mark.asyncio
async def test_config_change_is_report_drift_not_fence_drift(repo):
    a = _anchor(repo)
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = '--ignore=tests'\n", encoding="utf-8"
    )
    r = await _run(repo, a)
    assert r.report_paths == ["pyproject.toml"]
    assert r.fence_paths == []
    assert r.found is True


@pytest.mark.asyncio
async def test_skip_worktree_evasion_is_detected_cleared_and_revealed(repo):
    """THE case. Verified by hand first: with the bit set, `git add -A`
    stages nothing and `git diff` reports nothing, so the committed content
    stays the ORIGINAL failing test while pytest runs the weakened file."""
    a = _anchor(repo)
    _git(repo, "update-index", "--skip-worktree", "tests/test_auth.py")
    (repo / "tests" / "test_auth.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")

    # Pre-condition: prove the naive check really is blind here.
    naive = _git(repo, "diff", "--name-only", a, "--", *FENCE).split()
    assert naive == [], "fixture no longer reproduces the evasion"

    r = await _run(repo, a)
    assert r.index_bit_paths == ["tests/test_auth.py"]   # the evasion
    assert r.fence_paths == ["tests/test_auth.py"]        # the weakening
    assert "assert True" in r.patch                       # adjudicable by a human
    # The bit is cleared, so a later honest check sees the truth too.
    assert "S tests/test_auth.py" not in _git(repo, "ls-files", "-v", "--", *FENCE)


@pytest.mark.asyncio
async def test_assume_unchanged_evasion_is_detected(repo):
    a = _anchor(repo)
    _git(repo, "update-index", "--assume-unchanged", "tests/test_auth.py")
    (repo / "tests" / "test_auth.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    r = await _run(repo, a)
    assert r.index_bit_paths == ["tests/test_auth.py"]
    assert r.fence_paths == ["tests/test_auth.py"]


@pytest.mark.asyncio
async def test_ordinary_tracked_files_are_never_index_bit_findings(repo):
    """`H` is the tag for every ordinary tracked file. Flagging it would
    report the entire repository as evasion."""
    r = await _run(repo, _anchor(repo))
    assert r.index_bit_paths == []


@pytest.mark.asyncio
async def test_unresolvable_anchor_is_unavailable_never_a_clean_pass(repo):
    r = await _run(repo, "0" * 40)
    assert r.available is False
    assert r.found is False
    assert r.unavailable_reason


@pytest.mark.asyncio
async def test_non_repo_is_unavailable_never_a_clean_pass(tmp_path):
    r = await check_test_drift(
        DriftInput(
            worktree=str(tmp_path), anchor="HEAD", fence_globs=FENCE, report_globs=REPORT
        )
    )
    assert r.available is False
    assert r.unavailable_reason
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_drift_backstop.py -q`
Expected: FAIL — `ImportError: cannot import name 'DriftInput' from 'sdlc.vcs'`.

- [ ] **Step 3: Implement the activity**

In `src/sdlc/vcs/git.py`, after `get_task_diff`:

```python
@dataclass
class DriftInput:
    worktree: str
    anchor: str  # commit sha A -- the last attempt in which tests were free
    fence_globs: list[str]  # G: denied at the hook AND measured here
    report_globs: list[str]  # C: measured only (config, manifests)
    max_chars: int = 60_000


class DriftReport(BaseModel):
    """C2's deterministic backstop result.

    Three independent finding channels, because they are three different
    accusations and a human adjudicates them differently:
      fence_paths     -- a protected test path changed (weakening)
      report_paths    -- test/build config changed (possibly legitimate)
      index_bit_paths -- skip-worktree/assume-unchanged was set (evasion)
    """

    available: bool = True
    unavailable_reason: str = ""
    fence_paths: list[str] = Field(default_factory=list)
    report_paths: list[str] = Field(default_factory=list)
    index_bit_paths: list[str] = Field(default_factory=list)
    patch: str = ""

    @property
    def found(self) -> bool:
        return bool(self.fence_paths or self.report_paths or self.index_bit_paths)


def _index_bit_paths(worktree: str, globs: list[str]) -> list[str]:
    """Paths hidden from the diff by index metadata.

    `git ls-files -v` tags, MEASURED (do not "correct" this from memory):
      S            = skip-worktree
      any lowercase = assume-unchanged
      H            = an ORDINARY TRACKED FILE
    Flagging H would report every tracked file in the repo as evasion.
    """
    out = _git(["ls-files", "-v", "--", *globs], worktree)
    if out.returncode != 0:
        return []
    hidden: list[str] = []
    for line in out.stdout.splitlines():
        if len(line) < 3 or line[1] != " ":
            continue
        tag, path = line[0], line[2:].strip()
        if tag == "S" or tag.islower():
            hidden.append(path)
    return sorted(hidden)


@activity.defn
async def check_test_drift(inp: DriftInput) -> DriftReport:
    """Did this repair attempt change anything under the drift set?

    Order is detect -> record -> clear -> diff, and every step is load-bearing.
    Detection without clearing hands the human an accusation with no patch:
    while a skip-worktree bit is set, `git add -A` stages nothing and
    `git diff` reports nothing, so the checkpoint commits the ORIGINAL test
    while pytest executes the weakened file on disk. Clearing without
    recording destroys the only evidence of intent, because the bit is
    index-local state that is never committed -- once cleared, the revealed
    change is indistinguishable from ordinary drift.

    Any failure is `available=False`, NEVER an empty (clean) report. A
    backstop whose transient failure reads as "no drift" reopens the exact
    hole ADR-17 closes for the fence.

    Clearing index bits is safe under a resumable session: update-index
    touches only index metadata (no checkout, no merge, no content write),
    and this runs between attempts when no harness process is alive.
    """
    globs = [*inp.fence_globs, *inp.report_globs]
    if not globs:
        return DriftReport(available=False, unavailable_reason="empty drift set")

    probe = _git(["rev-parse", "--verify", f"{inp.anchor}^{{commit}}"], inp.worktree)
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip()
        return DriftReport(
            available=False, unavailable_reason=f"anchor {inp.anchor} unresolvable: {detail}"
        )

    hidden = _index_bit_paths(inp.worktree, globs)
    # Two SEPARATE invocations. Combining the flags silently leaves
    # skip-worktree SET while exiting 0 -- the last flag wins.
    for path in hidden:
        _git(["update-index", "--no-skip-worktree", path], inp.worktree)
        _git(["update-index", "--no-assume-unchanged", path], inp.worktree)

    # Plain pathspec, never `:(glob)`: git's DEFAULT pathspec agrees with
    # Python's fnmatch on the policy's pattern forms, and `:(glob)` does not
    # (it makes `**/x` start matching root-level x). One pattern list, four
    # engines, one meaning -- see tests/test_containment_dialects.py.
    status = _git(["diff", "--name-status", inp.anchor, "--", *globs], inp.worktree)
    if status.returncode != 0:
        detail = (status.stderr or status.stdout).strip()
        return DriftReport(available=False, unavailable_reason=f"diff failed: {detail}")

    changed = [ln.split("\t", 1)[1].strip() for ln in status.stdout.splitlines() if "\t" in ln]
    fence = sorted({p for p in changed if _matches_any(p, inp.fence_globs)})
    report = sorted({p for p in changed if p not in fence})
    patch = ""
    if changed:
        pr = _git(["diff", inp.anchor, "--", *globs], inp.worktree)
        patch = pr.stdout[: inp.max_chars] if pr.returncode == 0 else ""
    return DriftReport(
        fence_paths=fence, report_paths=report, index_bit_paths=hidden, patch=patch
    )


def _matches_any(path: str, globs: list[str]) -> bool:
    """fnmatch, matching containment.PATH_MATCHES exactly -- the fence and
    the backstop must classify a path identically or a human reads two
    different accusations for one act."""
    norm = PurePosixPath(path).as_posix()
    return any(fnmatch.fnmatch(norm, g) for g in globs)
```

Add the imports `fnmatch`, `from pathlib import PurePosixPath`, and `from pydantic import BaseModel, Field` at the top of `git.py`.

- [ ] **Step 4: Export from the package**

In `src/sdlc/vcs/__init__.py`, add `DriftInput`, `DriftReport`, `check_test_drift` to the imports and `__all__`, and register `check_test_drift` in whatever `ACTIVITIES` list the module already exposes (follow the pattern `get_task_diff` uses — grep for it and mirror it exactly).

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_drift_backstop.py -q`
Expected: PASS. If `test_skip_worktree_evasion_is_detected_cleared_and_revealed` fails at its pre-condition assert, git's behaviour differs on this host — stop and report, do not weaken the test.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/vcs/git.py src/sdlc/vcs/__init__.py tests/test_drift_backstop.py
git commit -m "feat(vcs): add the test-drift backstop activity

Measures content drift under the drift set against an anchor commit, in
the order detect -> record -> clear -> diff. The clear step exists because
a session can set skip-worktree/assume-unchanged on a protected path and
edit it freely: git add -A then stages nothing, git diff reports nothing,
the checkpoint commits the ORIGINAL test, and pytest runs the weakened
file. Detection alone gives the human an accusation with no patch;
clearing alone destroys the evidence of intent -- so both, as separate
findings.

Index-bit tags are S and any lowercase; H is an ordinary tracked file.
Clearing needs two separate update-index invocations: combining the flags
silently leaves skip-worktree set. Pathspec is plain, never :(glob).

Any failure is available=False, never an empty clean report.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 5: Thread `repair` through the activity inputs (incl. both crew sites)

**Files:**
- Modify: `src/sdlc/stages/code/activities.py`
- Modify: `src/sdlc/crew/activities.py`
- Modify: `src/sdlc/workflows/crew.py`
- Test: `tests/test_fix_loop_freeze.py` (threading tests only; the loop tests land in Task 6)

**Interfaces:**
- Consumes: `HarnessRequest.repair` from Task 2.
- Produces: `CodingTaskInput.repair: bool = False`, `CrewTaskInput.repair: bool = False`, `CrewTurnInput.repair: bool = False`.

**Design notes:**

- **`repair` must never be derived from `attempt` here** (fact 5). Both `CrewTurnInput` sites hardcode `attempt=1` and `CrewTaskInput.attempt` is never read in the child, so an `attempt >= 2` inference would leave every crew repair attempt unfrozen while every unit test that only exercised the non-crew path stayed green. The flag is explicit and set by the loop.
- **Both `CrewTurnInput` sites get it — the lead (`crew.py:175`) and the critics (`crew.py:321`).** The lead is the role that writes the repository; the critics are already fenced to the orchestration dir by `write_root`, and the freeze composes with that fence. Note that on opencode, `write_root`'s `path_outside_worktree` predicate is statically inexpressible and lands in `rules_unenforceable` (`opencode.py:111-115`), so a native `path_matches` freeze is the *only* native-layer repo protection a non-lead opencode role gets during repair — one extra line of coverage, no conflict.

- [ ] **Step 1: Write the failing threading tests**

Create `tests/test_fix_loop_freeze.py` with just this section for now:

```python
"""C2 Tasks 5-7: the flag's journey from the loop to the fence."""

from __future__ import annotations

from sdlc.core.models import HarnessKind
from sdlc.harness.base import HarnessRequest
from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment
from sdlc.harness.registry import HARNESSES


def test_coding_task_input_defaults_to_free_first_pass():
    assert CodingTaskInput(harness=HarnessKind.CLAUDE_CODE, prompt="p", worktree="/wt").repair is False


def test_resolve_containment_forwards_repair_to_the_compiled_fence(tmp_path):
    """The end-to-end bit: an input marked repair must produce a settings
    file whose hook command carries --repair."""
    import json
    from pathlib import Path

    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        repair=True,
    )
    harness = HARNESSES[HarnessKind.CLAUDE_CODE]
    req = HarnessRequest(prompt="p", cwd=str(tmp_path), repair=inp.repair)
    _resolve_containment(harness, inp, req)
    settings_path = req.extra_args[req.extra_args.index("--settings") + 1]
    doc = json.loads(Path(settings_path).read_text(encoding="utf-8"))
    assert "--repair" in doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def test_crew_turn_input_carries_repair():
    from sdlc.crew.activities import CrewTurnInput

    t = CrewTurnInput(
        worktree="/wt",
        layout="code",
        role="lead",
        harness=HarnessKind.CLAUDE_CODE,
        model="m",
        prompt="p",
        round=1,
        attempt=1,
        turn_timeout_s=60,
        task_id="t1",
        repair=True,
    )
    assert t.repair is True


def test_every_crew_turn_input_construction_passes_repair():
    """Guards fact 5: both sites hardcode attempt=1, so if `repair` is ever
    dropped at one of them that path silently runs unfrozen and no
    attempt-based test would notice."""
    import ast
    import inspect

    from sdlc.workflows import crew as crew_mod

    tree = ast.parse(inspect.getsource(crew_mod))
    sites = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "CrewTurnInput"
    ]
    assert len(sites) == 2, f"expected 2 CrewTurnInput sites, found {len(sites)}"
    for site in sites:
        assert any(
            kw.arg == "repair" for kw in site.keywords
        ), "a CrewTurnInput site does not pass repair -- that path runs unfrozen"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_fix_loop_freeze.py -q`
Expected: FAIL — `TypeError: CodingTaskInput.__init__() got an unexpected keyword argument 'repair'`.

- [ ] **Step 3: Add the field to `CodingTaskInput` and thread it**

In `src/sdlc/stages/code/activities.py`, after the `grants` field:

```python
    # C2: this is a REPAIR attempt, which activates `phase: repair` policy
    # rules (the contract's test files). Set by the fix loop, NEVER derived
    # from `attempt` here -- CrewTurnInput hardcodes attempt=1 at both of its
    # construction sites, so an activity-side inference would leave every
    # crew repair attempt silently unfrozen.
    repair: bool = False
```

and in `run_coding_task`, pass it into the request:

```python
    req = HarnessRequest(
        prompt=inp.prompt,
        cwd=inp.worktree,
        model=inp.model,
        session_id=inp.session_id,
        timeout_s=inp.timeout_s,
        repair=inp.repair,
    )
```

- [ ] **Step 4: Add the field to `CrewTurnInput` and thread it**

In `src/sdlc/crew/activities.py`, add to `CrewTurnInput` after `grants`:

```python
    repair: bool = False  # C2: see CodingTaskInput.repair
```

and in `run_crew_turn`, add `repair=inp.repair` to the `HarnessRequest(...)` construction (alongside the existing `write_root=write_root`).

- [ ] **Step 5: Add the field to `CrewTaskInput` and pass it at both turn sites**

In `src/sdlc/workflows/crew.py`, add to `CrewTaskInput` (beside the existing containment fields):

```python
    repair: bool = False  # C2: forwarded to every turn in this attempt
```

and add `repair=inp.repair,` to **both** `CrewTurnInput(...)` constructions — `crew.py:175` (lead) and `crew.py:321` (critics). Leave `attempt=1` exactly as it is: it is a turn-level counter with its own meaning and this plan does not repurpose it.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_fix_loop_freeze.py -q`
Expected: PASS.

- [ ] **Step 7: Run the crew and code-stage suites**

Run: `python -m pytest tests/ -q -k "crew or code_stage or coding"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/stages/code/activities.py src/sdlc/crew/activities.py src/sdlc/workflows/crew.py tests/test_fix_loop_freeze.py
git commit -m "feat(harness): thread the repair flag to every coding activity

CodingTaskInput, CrewTaskInput and CrewTurnInput each carry `repair`, set
by the fix loop and forwarded into HarnessRequest. Explicit rather than
derived from `attempt`: both CrewTurnInput sites hardcode attempt=1 and
CrewTaskInput.attempt is never read in the child, so inference would leave
every crew repair attempt unfrozen while non-crew tests stayed green.

An AST test pins the site count at two and asserts each passes the flag.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 6: Policy-globs activity, the vacuity probe, and strict refusal

**Files:**
- Modify: `src/sdlc/stages/code/activities.py`
- Modify: `src/sdlc/harness/models.py`
- Test: `tests/test_fix_loop_freeze.py` (append)

**Interfaces:**
- Produces: `@dataclass DriftGlobsInput(policy_path: str | None)`.
- Produces: `class DriftGlobs(BaseModel)` with `fence: list[str]`, `report: list[str]`.
- Produces: `@activity.defn async def load_drift_globs(inp: DriftGlobsInput) -> DriftGlobs` — used by the loop in Task 7. Exists because the workflow sandbox cannot read files; the same split the containment flags already follow.
- Produces: `ContainmentReport.freeze_vacuous: bool = False` and `ContainmentReport.freeze_files_matched: int | None = None`.

**Design notes:**

- **The vacuity probe is repo-side I/O and belongs in the ACTIVITY**, not in `apply_containment`. The adapters are per-CLI compilers and the policy module is documented pure; a `git ls-files` call in either is out of place.
- **Strict refuses on a MISSING RULE only, never on a vacuous glob set.** These are different categories. A policy carrying no repair-phase rule is the *asset lying* about what is in force — a static authoring defect, visible at load time, exactly the nature of `rules_unenforceable` which `strict` already judges. A vacuous `G` is a *mismatch between our conventions and the target repo's layout* — an environment property the policy author never controlled, detected mid-task at repair engagement, where refusing would kill a healthy run and the operator's only escape would be disabling strict globally. **This reverses an earlier position in this design's own history; the reversal is deliberate and is recorded here so nobody restores the old rule with the old reasoning.**
- **Vacuity is still a durable signal** — it rides `ContainmentReport` into the run record and is appended to the gate analysis, where the human already is.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fix_loop_freeze.py`:

```python
# --- Task 8: glob loading, vacuity, strict ---------------------------------

from sdlc.harness.containment import ContainmentError
from sdlc.stages.code.activities import DriftGlobsInput, load_drift_globs


@pytest.mark.asyncio
async def test_load_drift_globs_splits_fence_from_report(tmp_path):
    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "drift_paths: ['pyproject.toml']\n"
        "rules:\n"
        "  - id: freeze\n"
        "    layer: native\n"
        "    phase: repair\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['tests/**']\n"
        "    reason: frozen\n",
        encoding="utf-8",
    )
    out = await load_drift_globs(DriftGlobsInput(policy_path=str(p)))
    assert out.fence == ["tests/**"]
    assert out.report == ["pyproject.toml"]


def test_strict_refuses_a_repair_run_whose_policy_fences_nothing(tmp_path):
    """A policy with no repair-phase rule is the ASSET LYING about what is in
    force. That is what strict is for."""
    from sdlc.core.models import HarnessKind
    from sdlc.harness.registry import HARNESSES
    from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment

    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: cfg\n"
        "    layer: native\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['**/.claude/**']\n"
        "    reason: no\n",
        encoding="utf-8",
    )
    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_strict=True,
        containment_policy_path=str(p),
        repair=True,
    )
    with pytest.raises(ContainmentError, match="repair"):
        _resolve_containment(HARNESSES[HarnessKind.CLAUDE_CODE], inp)


def test_strict_does_not_refuse_a_merely_vacuous_glob_set(tmp_path):
    """A vacuous G is a LAYOUT MISMATCH (a Go task under Python-shaped
    globs), not a lie. Refusing mid-loop would kill a healthy run and make
    the safe configuration strictly worse to enable. Deliberate reversal of
    an earlier draft of this design -- do not restore it."""
    from sdlc.core.models import HarnessKind
    from sdlc.harness.registry import HARNESSES
    from sdlc.stages.code.activities import CodingTaskInput, _resolve_containment

    p = tmp_path / "containment.yaml"
    p.write_text(
        "version: 1\n"
        "rules:\n"
        "  - id: freeze\n"
        "    layer: native\n"
        "    phase: repair\n"
        "    tools: [Write]\n"
        "    predicate: path_matches\n"
        "    patterns: ['nothing_matches_this/**']\n"
        "    reason: frozen\n",
        encoding="utf-8",
    )
    inp = CodingTaskInput(
        harness=HarnessKind.CLAUDE_CODE,
        prompt="p",
        worktree=str(tmp_path),
        containment_enabled=True,
        containment_strict=True,
        containment_policy_path=str(p),
        repair=True,
    )
    _, report = _resolve_containment(HARNESSES[HarnessKind.CLAUDE_CODE], inp)
    assert report.freeze_vacuous is True  # recorded, not refused
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_fix_loop_freeze.py -q -k "drift_globs or strict"`
Expected: FAIL — `ImportError: cannot import name 'DriftGlobsInput'`.

- [ ] **Step 3: Add the report fields**

In `src/sdlc/harness/models.py`, on `ContainmentReport`:

```python
    # C2: the freeze compiled, but its globs match nothing in this repo --
    # protection that LOOKS active and fences nothing. A warning, not a
    # refusal: usually an alien repo layout (a Go task under Python-shaped
    # globs), not an attack. None means "not probed" (not a repair attempt,
    # or containment disabled).
    freeze_vacuous: bool = False
    freeze_files_matched: int | None = None
```

- [ ] **Step 4: Add the globs activity, the probe and the strict rule**

In `src/sdlc/stages/code/activities.py`:

```python
@dataclass
class DriftGlobsInput:
    policy_path: str | None = None


class DriftGlobs(BaseModel):
    fence: list[str] = Field(default_factory=list)
    report: list[str] = Field(default_factory=list)


@activity.defn
async def load_drift_globs(inp: DriftGlobsInput) -> DriftGlobs:
    """Resolve the drift set activity-side.

    The workflow sandbox cannot read files, so the loop cannot load the
    policy itself -- the same split the containment flags already follow.
    Returned split rather than merged because the two halves carry different
    accusations: a fenced path that changed went AROUND a deny rule; a
    report-only path may have been edited legitimately."""
    policy = load_policy(inp.policy_path)
    return DriftGlobs(fence=repair_patterns(policy), report=list(policy.drift_paths))
```

and extend `_resolve_containment`, after the existing `containment_strict` block:

```python
    if getattr(inp, "repair", False):
        if not has_repair_rule(policy):
            if inp.containment_strict:
                raise ContainmentError(
                    "containment_strict is set and this is a repair attempt, but the "
                    "policy carries no `phase: repair` rule -- the contract's tests "
                    "would be unfrozen while the report claims containment is active."
                )
        else:
            # Vacuity probe: repo-side I/O, so it lives here rather than in
            # apply_containment (adapters are per-CLI compilers; the policy
            # module is pure). A WARNING even under strict -- a vacuous glob
            # set is a layout mismatch, not the asset lying.
            probe = _git(["ls-files", "--", *repair_patterns(policy)], inp.worktree)
            matched = len([x for x in probe.stdout.splitlines() if x.strip()])
            report.freeze_files_matched = matched
            report.freeze_vacuous = matched == 0
```

Add `has_repair_rule`, `repair_patterns` to the containment import, and `BaseModel`, `Field` from pydantic.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_fix_loop_freeze.py -q -k "drift_globs or strict"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sdlc/stages/code/activities.py src/sdlc/harness/models.py tests/test_fix_loop_freeze.py
git commit -m "feat(containment): resolve the drift set activity-side; probe for a vacuous freeze

load_drift_globs loads the policy in an activity (the workflow sandbox
cannot read files) and returns the fence and report halves separately,
because they carry different accusations.

containment_strict refuses a repair attempt whose policy carries NO
repair-phase rule -- that is the asset lying about what is in force. It
deliberately does NOT refuse a merely vacuous glob set: that is a layout
mismatch, detected mid-task, where refusing would kill a healthy run and
make the safe configuration worse to enable. Vacuity is recorded on the
report and surfaced at the gate instead.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 7: The loop — anchor `A`, the repair flag, and the drift consequence

**Files:**
- Modify: `src/sdlc/stages/code/step.py`
- Test: `tests/test_fix_loop_freeze.py` (append)

**Interfaces:**
- Consumes: `CodingTaskInput.repair` / `CrewTaskInput.repair` (Task 5); `check_test_drift`, `DriftInput`, `DriftReport` (Task 4); `drift_globs`, `repair_patterns` (Task 1).
- Produces: `_is_repair_attempt(attempt: int, thawed: bool) -> bool` and `_next_anchor(current: str | None, commit_sha: str | None, thawed: bool) -> str | None` — the two rules that decide *when* the fence is on and *what* the backstop measures against, extracted as pure helpers so both are testable as tables rather than only through the loop.
- Produces: `_drift_note(report: DriftReport) -> str` — the human-facing rendering appended to the gate analysis, importable for tests.

**Design notes carried into the code:**

- **`repair` is `attempt > 1`.** Attempt 1 is the free pass. The escalation inner loop (`step.py:511-612`) re-executes the *same* attempt after a grant decision, so the flag is constant across it — the tests' protected status must not flicker mid-attempt. The operator-REVISE continuation (`step.py:765-787`) increments `attempt` with a fresh session, and is a repair attempt like any other unless the operator thawed it (Task 7).
- **Anchor `A` is captured ONCE**, from the first attempt that returns a `commit_sha`, and never re-anchored to the previous attempt. Per-attempt re-anchoring would let attempt 2 weaken a test and attempt 3 inherit the weakened state as its baseline — the ratchet this design exists to prevent. The only exception is a thaw (Task 7). `run.commit_sha` works for crew unchanged (fact 6).
- **Missing `A` is skip-and-record, never a `branch_point` fallback.** Falling back to `branch_point` would report attempt 1's own legitimate test authoring as drift on every remaining attempt, with no affordance for the human to suppress it — an unsilenceable false positive trains operators to click gates through. The real channels are a swallowed commit failure and a crew round-1 deadline (fact 7).
- **Drift forces `task_passed = False` and short-circuits the budget.** `qa_raw.tests_passed` is the manipulated signal; drift is ground truth. Short-circuit (`budget = attempt`, the existing precedent at `step.py:755-763`) rather than spending another attempt, because a frozen session **cannot honestly restore what it broke** — restoring a test file is itself a write to a protected path — so a retry could only succeed by going around the fence again. Route to the gate with the patch as `analysis`; never auto-revert (it makes the transcript lie about worktree state) and never auto-quarantine (`black tests/` fires drift with zero intent to weaken, so a human adjudicates).
- **One consequence for all three channels.** Fence, config and index-bit findings differ in *what they accuse* — which is data the human reads — but share one code path. Do not build a per-channel control flow: the principled asymmetry lives entirely in the policy asset (which globs are fenced vs measured), and a second asymmetry in the loop is what an implementer gets wrong.

- [ ] **Step 1: Write the failing loop tests**

Append to `tests/test_fix_loop_freeze.py`:

```python
# --- Task 6: loop semantics ------------------------------------------------

import pytest

from sdlc.stages.code.step import _drift_note, _is_repair_attempt, _next_anchor
from sdlc.vcs import DriftReport


@pytest.mark.parametrize(
    "attempt,thawed,expect",
    [
        (1, False, False),  # the free first pass
        (2, False, True),   # first repair
        (5, False, True),
        (3, True, False),   # a thawed attempt runs unfrozen
    ],
)
def test_is_repair_attempt(attempt, thawed, expect):
    assert _is_repair_attempt(attempt, thawed) is expect


def test_drift_note_names_each_channel_distinctly():
    """A human adjudicates 'evasion' differently from 'a test changed'."""
    note = _drift_note(
        DriftReport(
            fence_paths=["tests/test_a.py"],
            report_paths=["pyproject.toml"],
            index_bit_paths=["tests/test_a.py"],
            patch="--- a\n+++ b\n",
        )
    )
    assert "tests/test_a.py" in note
    assert "pyproject.toml" in note
    assert "skip-worktree" in note or "assume-unchanged" in note
    assert "--- a" in note  # the patch, so weakening is adjudicable in one look


def test_drift_note_reports_unavailability_rather_than_silence():
    note = _drift_note(DriftReport(available=False, unavailable_reason="anchor missing"))
    assert "unavailable" in note.lower()
    assert "anchor missing" in note


def test_drift_note_is_empty_when_clean():
    assert _drift_note(DriftReport()) == ""


# --- anchor semantics: the two tests most likely to be written wrong --------

def test_anchor_never_creeps_to_the_previous_attempt():
    """RATCHET. If A moved to each attempt's checkpoint, attempt 2 could
    weaken a test and attempt 3 would inherit the weakened state as its own
    baseline -- drift would report clean and the weakening would launder
    itself over two attempts."""
    a1 = _next_anchor(None, "sha1", thawed=False)      # attempt 1 sets A
    assert a1 == "sha1"
    a2 = _next_anchor(a1, "sha2", thawed=False)        # attempt 2: frozen
    assert a2 == "sha1"
    a3 = _next_anchor(a2, "sha3", thawed=False)        # attempt 3: still A1
    assert a3 == "sha1"


def test_a_thawed_attempt_re_anchors_and_the_next_one_measures_from_it():
    """RE-ANCHORING, asserted on the ANCHOR rather than on a flag. A test
    that only asserts `thawed is False` afterwards passes while the feature
    self-defeats: the human's authorized edits would fire drift forever."""
    a = _next_anchor(None, "sha1", thawed=False)
    a = _next_anchor(a, "sha2", thawed=False)          # frozen attempt
    assert a == "sha1"
    a = _next_anchor(a, "sha3", thawed=True)           # THAWED attempt
    assert a == "sha3", "a thaw must move A, or its own edits fire drift"
    a = _next_anchor(a, "sha4", thawed=False)          # back to frozen
    assert a == "sha3", "later attempts measure from the thawed baseline"


def test_a_missing_checkpoint_leaves_the_anchor_alone():
    """Fact 7's channels (a swallowed commit failure; a crew round-1
    deadline) yield no sha. Never fall back to branch_point: that would
    report attempt 1's own legitimate test authoring as drift on every
    remaining attempt, with no way for a human to suppress it."""
    assert _next_anchor(None, None, thawed=False) is None
    assert _next_anchor("sha1", None, thawed=False) == "sha1"
    assert _next_anchor("sha1", None, thawed=True) == "sha1"


def test_repair_is_constant_across_the_escalation_inner_loop():
    """The inner loop re-executes the SAME attempt after a tool-grant
    decision (step.py:511-612). The tests' protected status must not flicker
    mid-attempt, or a session could bank a denial, get one grant, and find
    the fence gone on the re-entry."""
    attempt, thawed = 3, False
    assert {_is_repair_attempt(attempt, thawed) for _ in range(5)} == {True}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_fix_loop_freeze.py -q -k "repair_attempt or drift_note"`
Expected: FAIL — `ImportError: cannot import name '_drift_note'`.

- [ ] **Step 3: Add the helpers to `step.py`**

Near the other module-level helpers in `src/sdlc/stages/code/step.py`:

```python
def _is_repair_attempt(attempt: int, thawed: bool) -> bool:
    """Attempt 1 is the FREE pass -- the dev authors the contract's tests
    there. Every later attempt is a repair attempt, including the
    operator-REVISE continuation, unless a human explicitly thawed it for
    exactly this attempt."""
    return attempt > 1 and not thawed


def _next_anchor(current: str | None, commit_sha: str | None, thawed: bool) -> str | None:
    """The C2 anchor rule, as a table rather than as inline loop conditions.

    A is the checkpoint of the last attempt in which tests were FREELY
    WRITABLE: attempt 1, plus any attempt a human thawed. It is captured once
    and then held -- moving it to each attempt's checkpoint would let attempt
    2 weaken a test that attempt 3 inherits as its baseline, laundering the
    weakening over two attempts. A thaw is the ONLY thing that moves it, and
    it must, or the backstop would flag the very edits the operator just
    authorized.

    `commit_sha` is None when an attempt produced no checkpoint (a swallowed
    commit failure, or a crew round-1 deadline). Then A simply does not move;
    there is deliberately no branch_point fallback."""
    if commit_sha and (current is None or thawed):
        return commit_sha
    return current


def _drift_note(report: DriftReport) -> str:
    """The deterministic finding, rendered for the human at the fix-loop gate.

    Three channels, named separately on purpose: 'the session hid a change'
    is a different accusation from 'a test changed', and a human decides them
    differently. The patch is included so weakening is distinguishable from a
    formatter run in one look."""
    if not report.available:
        return (
            "TEST-FREEZE BACKSTOP UNAVAILABLE: "
            f"{report.unavailable_reason}. Test drift was NOT checked for this attempt."
        )
    if not report.found:
        return ""
    lines: list[str] = []
    if report.index_bit_paths:
        lines.append(
            "EVASION: the session set skip-worktree/assume-unchanged on protected "
            "paths, hiding edits from the diff: " + ", ".join(report.index_bit_paths)
        )
    if report.fence_paths:
        lines.append(
            "FROZEN TESTS CHANGED during a repair attempt: "
            + ", ".join(report.fence_paths)
        )
    if report.report_paths:
        lines.append(
            "TEST CONFIGURATION CHANGED during a repair attempt: "
            + ", ".join(report.report_paths)
        )
    if report.patch:
        lines.append("\nDrift patch:\n" + report.patch)
    return "\n".join(lines)
```

- [ ] **Step 4: Wire the anchor, the flag and the drift call into the loop**

Before the `while True:` at `step.py:499`, add the anchor state:

```python
    # C2 anchor A: the checkpoint of the last attempt in which tests were
    # freely writable -- attempt 1, plus any thawed attempt. Captured once
    # and never re-anchored to the PREVIOUS attempt, or attempt 2 could
    # weaken a test and attempt 3 would inherit the weakened state as its
    # baseline. Plain workflow state derived from activity output: replay-safe.
    anchor: str | None = None
    thawed = False  # set by an operator thaw for exactly one attempt (below)
```

Pass the flag into `_execute_coding_task` — add a `repair: bool` parameter to that helper and forward it into both `CodingTaskInput(...)` and `CrewTaskInput(...)`. At the call site inside the loop:

```python
            exec_out = await _execute_coding_task(
                role_cfg=role_cfg,
                prompt=prompt,
                worktree=worktree,
                session_id=session_id,
                task_id=task.id,
                attempt=attempt,
                repair=_is_repair_attempt(attempt, thawed),
                grants=grants,
                ...
            )
```

After the escalation inner loop breaks and before the `test_cmd` / `run_test_suite` block, capture the anchor and run the backstop:

```python
        # Capture A on the first attempt that produced a checkpoint; a thawed
        # attempt RE-anchors on completion so the human-authorized edits
        # become the new baseline rather than firing drift forever after.
        # The rule is a pure helper so the ratchet is testable as a table.
        anchor = _next_anchor(anchor, run.commit_sha, thawed)

        drift = DriftReport()
        if cfg.containment_enabled and anchor is not None and _is_repair_attempt(attempt, thawed):
            policy_globs = await workflow.execute_activity(
                load_drift_globs,
                DriftGlobsInput(policy_path=cfg.containment.policy_path),
                **ACT,
            )
            drift = await workflow.execute_activity(
                check_test_drift,
                DriftInput(
                    worktree=worktree,
                    anchor=anchor,
                    fence_globs=policy_globs.fence,
                    report_globs=policy_globs.report,
                ),
                **ACT,
            )
        thawed = False  # a thaw is single-attempt by construction
```

(`load_drift_globs` / `DriftGlobsInput` / `DriftGlobs` landed in Task 6 — the policy must be loaded activity-side because the workflow sandbox cannot read files.)

Then change the pass condition and the budget short-circuit:

```python
        task_passed = bool(qa_raw.tests_passed and not qa.issues and not drift.found)
```

and immediately after the `issues = ...` line at `step.py:754`:

```python
        drift_note = _drift_note(drift)
        if drift.found:
            # Ground truth beats the manipulated signal, and a frozen session
            # cannot honestly restore what it broke -- restoring a protected
            # test is itself a denied write -- so another attempt could only
            # succeed by going around the fence again. Straight to the human,
            # with the patch.
            budget = attempt
            issues = "\n- ".join(x for x in (issues, drift_note) if x)
```

and include the note in the gate context:

```python
            analysis = _fix_loop_issues(qa, qa_raw, review) if qa else ""
            analysis = "\n".join(x for x in (analysis, drift_note) if x)
```

Add the imports at the top of `step.py`:

```python
from ...vcs import DriftInput, DriftReport, check_test_drift
```

- [ ] **Step 5: Surface vacuity in the gate analysis**

In `src/sdlc/stages/code/step.py`, extend the `analysis` assembly in the gate branch:

```python
            if getattr(getattr(run, "containment", None), "freeze_vacuous", False):
                analysis += (
                    "\nNOTE: the test-freeze globs matched 0 files in this repo, so the "
                    "freeze fenced nothing this attempt (likely an unfamiliar test layout)."
                )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_fix_loop_freeze.py -q`
Expected: PASS.

- [ ] **Step 7: Run the code-stage suite**

Run: `python -m pytest tests/ -q -k "code or fix_loop or step"`
Expected: PASS. `containment_enabled` defaults to `False`, so every existing loop test takes the `drift = DriftReport()` path and is unaffected.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/stages/code/step.py tests/test_fix_loop_freeze.py
git commit -m "feat(code): freeze contract tests from the second attempt onward

The loop is the authority on what counts as repair: attempt 1 is free,
every later attempt sets repair=True (constant across the escalation inner
loop, which re-enters the same attempt).

Anchor A is captured once from the first checkpoint and never moved to the
previous attempt, so attempt 2 cannot weaken a test that attempt 3 then
inherits as baseline. Missing A is skip-and-record: a branch_point
fallback would report attempt 1's own legitimate test authoring as drift
on every remaining attempt, with no way for a human to suppress it.

Drift forces task_passed=False even on a green suite -- tests_passed is
the manipulated signal -- and short-circuits the budget to the gate with
the patch attached.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 8: The audited single-attempt thaw

**Files:**
- Modify: `src/sdlc/core/models.py` (`GateDecision.thaw_tests`)
- Modify: `src/sdlc/channels/contract.py` (`Reply.thaw_tests` + `default_translate`)
- Modify: `src/sdlc/cli.py` (`--thaw-tests` on `revise`; pass through in `selector_for`)
- Modify: `src/sdlc/dashboard/api.py` (`DecideBody.thaw_tests`)
- Modify: `src/sdlc/stages/code/step.py` (honour it, re-anchor, skip the drift check, record it)
- Test: `tests/test_thaw_plumbing.py`

**Interfaces:**
- Consumes: `_is_repair_attempt`, `_next_anchor`, the `thawed` loop variable (Task 7).
- Produces: `GateDecision.thaw_tests: bool = False`, `Reply.thaw_tests: bool = False`, `DecideBody.thaw_tests: bool = False`.

**Design notes carried into the code:**

- **A thawed attempt SKIPS the drift check entirely** (both `G` and `C`), and `A` re-anchors to its checkpoint on completion. Without the skip, the human-authorised edits fire drift at that very attempt — because `A` is still the old anchor when the check runs — and the thaw self-defeats. Task 6's `_is_repair_attempt(attempt, thawed)` guard already gates the check; the re-anchor is the `or thawed` clause in the capture.
- **Never infer a thaw from guidance text.** An operator whose REVISE comment names a test file has *not* thawed. Inference would train operators to expect the affordance whenever the analysis mentions a test, and would hand a cheating session a text channel into its own unfreezing.
- **The bounding rule for `Reply`** (write it as a comment on the new field): a field lands on the surface-neutral `Reply` only when (1) at least one human-direct surface collects it structurally, (2) exactly one gate kind reads it, and (3) no agent surface exposes it. `thaw_tests` satisfies all three; `Reply.outcome` is already gate-specific precedent.
- **`operator/tools.py` is deliberately not wired** — see the File Structure section. Do not "complete" it.
- **`cli.py` builds `approve`/`reject`/`revise` in one loop** (`cli.py:122-130`); add the flag conditionally inside that loop rather than splitting `revise` out.

- [ ] **Step 1: Write the failing thaw tests**

Create `tests/test_thaw_plumbing.py`:

```python
"""C2 Task 7: the human-only, single-attempt thaw."""

from __future__ import annotations

import pytest

from sdlc.channels.contract import Reply, default_translate
from sdlc.core.models import GateDecision, GateOutcome
from sdlc.pending import TaskEscalationPending
from sdlc.stages.code.step import _is_repair_attempt


def _pending() -> TaskEscalationPending:
    return TaskEscalationPending(key="task:t1", gate="task:t1", round=1)


def test_thaw_defaults_off_everywhere():
    assert Reply(outcome=GateOutcome.REVISE, text="x").thaw_tests is False
    assert GateDecision(gate="g", outcome=GateOutcome.REVISE, decided_by="human").thaw_tests is False


def test_translate_carries_the_thaw_into_the_decision():
    call = default_translate(
        _pending(), Reply(outcome=GateOutcome.REVISE, text="the assertion is wrong", thaw_tests=True)
    )
    assert call.decision.thaw_tests is True
    assert call.decision.guidance == "the assertion is wrong"


def test_translate_defaults_the_thaw_off():
    call = default_translate(_pending(), Reply(outcome=GateOutcome.REVISE, text="try again"))
    assert call.decision.thaw_tests is False


def test_guidance_text_naming_a_test_file_does_not_imply_a_thaw():
    """NO-INFERENCE REGRESSION. Guards the explicitness rule against a future
    'helpful' inference, and against a session that writes gate-facing prose
    designed to induce one."""
    call = default_translate(
        _pending(),
        Reply(
            outcome=GateOutcome.REVISE,
            text="the assertion in tests/test_auth.py is wrong, please fix the test",
        ),
    )
    assert call.decision.thaw_tests is False


def test_a_thawed_attempt_is_not_a_repair_attempt():
    assert _is_repair_attempt(3, thawed=True) is False
    assert _is_repair_attempt(3, thawed=False) is True


def test_cli_revise_accepts_thaw_and_other_verbs_do_not():
    import argparse

    from sdlc.cli import add_decision_parsers

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    add_decision_parsers(sub)
    args = p.parse_args(["revise", "--id", "r1", "--comment", "c", "--thaw-tests"])
    assert args.thaw_tests is True
    with pytest.raises(SystemExit):
        p.parse_args(["approve", "--id", "r1", "--thaw-tests"])


def test_cli_selector_forwards_the_thaw():
    import argparse

    from sdlc.cli import add_decision_parsers, selector_for

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    add_decision_parsers(sub)
    _, reply = selector_for(p.parse_args(["revise", "--id", "r1", "--comment", "c", "--thaw-tests"]))
    assert reply.thaw_tests is True


def test_dashboard_decide_body_carries_the_thaw():
    from sdlc.dashboard.api import DecideBody

    assert DecideBody(key="k", outcome=GateOutcome.REVISE).thaw_tests is False
    assert DecideBody(key="k", outcome=GateOutcome.REVISE, thaw_tests=True).thaw_tests is True


def test_mcp_operator_surface_does_not_expose_the_thaw():
    """DELIBERATE. decide_gate is an AGENT tool surface; exposing the thaw
    there would let an LLM intermediary unfreeze the tests. This assertion
    exists so nobody 'completes' the plumbing later without reading why."""
    import inspect

    from sdlc.operator import tools

    assert "thaw" not in inspect.getsource(tools.decide_gate)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_thaw_plumbing.py -q`
Expected: FAIL — `ValidationError`/`AttributeError` on `Reply.thaw_tests`.

- [ ] **Step 3: Add the model fields**

`src/sdlc/core/models.py`, on `GateDecision` after `guidance`:

```python
    # C2: authorize the NEXT attempt to edit the contract's frozen tests.
    # Read only by the code-stage task gate, and only on `revise` -- inert
    # everywhere else, exactly like `guidance` on a non-revise outcome.
    # Never inferred from `guidance` text: a session that writes gate-facing
    # prose about a "wrong test" must not be able to unfreeze itself.
    thaw_tests: bool = False
```

`src/sdlc/channels/contract.py`, on `Reply`:

```python
    # C2 (gate replies, code-stage task gate only). A field lands on this
    # surface-neutral model only when: a human-direct surface collects it
    # structurally; exactly one gate kind reads it; and NO agent surface
    # exposes it. `outcome` is the existing gate-specific precedent.
    thaw_tests: bool = False
```

and in `default_translate`'s `GateDecision(...)` construction:

```python
                guidance=guidance,
                thaw_tests=reply.thaw_tests and reply.outcome is GateOutcome.REVISE,
```

- [ ] **Step 4: Wire the two human-direct surfaces**

`src/sdlc/cli.py`, inside the existing parser loop:

```python
    for name in ("approve", "reject", "revise"):
        g = sub.add_parser(name)
        g.add_argument("--id", required=True)
        g.add_argument("--gate", default=None, help="gate name; omit if exactly one gate is pending")
        g.add_argument("--comment", default=None, help="comment; required for revise (becomes guidance)")
        if name == "revise":
            # C2: only `revise` resumes the fix loop, so a thaw is
            # meaningless on approve/reject.
            g.add_argument(
                "--thaw-tests",
                action="store_true",
                help="authorize the next attempt to edit the contract's frozen tests",
            )
```

and in `selector_for`:

```python
        Reply(
            outcome=_OUTCOME[args.cmd],
            text=args.comment,
            thaw_tests=getattr(args, "thaw_tests", False),
        ),
```

`src/sdlc/dashboard/api.py`, on `DecideBody`:

```python
    thaw_tests: bool = False  # C2, revise only
```

and in the `Reply(...)` construction at `api.py:167`:

```python
            Reply(outcome=body.outcome, text=body.text or None, thaw_tests=body.thaw_tests),
```

- [ ] **Step 5: Honour the thaw in the loop and record it**

In `src/sdlc/stages/code/step.py`, in the REVISE branch (`step.py:774-787`), set the flag before `continue`:

```python
            if decision.outcome is GateOutcome.REVISE and gate_round <= cfg.max_gate_rounds:
                guidance = decision.guidance or decision.comments or ""
                budget = attempt + 1
                session_id = None
                # C2: single-attempt, human-only, and it also RE-ANCHORS A
                # (see the capture above) -- without that, the backstop would
                # flag the very edits the operator just authorized.
                thawed = bool(decision.thaw_tests)
                if thawed:
                    await _record_thaw(ctx, cfg, task, decision, attempt + 1)
                prompt = (
```

and add the audit record helper beside `_record_escalation`:

```python
async def _record_thaw(
    ctx: StageContext, cfg: PipelineConfig, task: DevTask, decision, attempt: int
) -> None:
    """A thaw is a human override of a deterministic fence, so it gets the
    same treatment as one: a trace event AND a benchmark record with
    judge='human_override'. Gate history alone would not show that attempt N
    ran with the tests writable."""
    ctx.emit(
        RunEventKind.TOOL_ESCALATION,
        stage="tool_approval",
        task_id=task.id,
        tool="TestFreeze",
        rule_id="no-test-edit-during-repair",
        outcome="thawed",
        decided_by=decision.decided_by,
        round=str(attempt),
    )
    now = _now()
    await ctx.record(
        cfg,
        stage_record(
            cfg,
            stage="tool_approval",
            role="human",
            started=now,
            ended=now,
            quality_score=None,
            judge="human_override",
            outcome=BenchmarkOutcome.ESCALATED,
            model="human",
            task_id=task.id,
        ),
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_thaw_plumbing.py -q`
Expected: PASS.

- [ ] **Step 7: Run the channels, CLI and dashboard suites**

Run: `python -m pytest tests/ -q -k "channel or cli or dashboard or operator or gate"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/sdlc/core/models.py src/sdlc/channels/contract.py src/sdlc/cli.py src/sdlc/dashboard/api.py src/sdlc/stages/code/step.py tests/test_thaw_plumbing.py
git commit -m "feat(gates): add the audited single-attempt test-freeze thaw

An operator who concludes the contract's test is itself wrong can
authorize exactly one unfrozen attempt. Explicit field, never inferred
from guidance text -- a session that writes gate-facing prose about a
'wrong test' must not be able to unfreeze itself.

The thaw also re-anchors A to that attempt's checkpoint and skips its
drift check; without both, the backstop would flag the very edits the
operator just authorized and the thaw would self-defeat.

Wired on the two human-direct surfaces (CLI revise, dashboard) and
deliberately NOT on the MCP operator tool, which is an agent surface --
exposing it there would let an LLM intermediary unfreeze the tests. A test
pins that omission so nobody completes it without reading why.

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

### Task 9: Full-suite verification and the register row

**Files:**
- Modify: `docs/reports/external-ideas-2026-09.md`

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest tests/ -q`
Expected: PASS. Investigate any failure rather than skipping it; `containment_enabled` defaults to `False`, so an unrelated failure is a real regression.

- [ ] **Step 2: Run the linters**

Run: `python -m ruff check src tests && python -m ruff format --check src tests`
Expected: clean. (`mypy` is scoped to `src/` with ~122 known pre-existing errors — check that your changes add none: `python -m mypy src/sdlc/harness src/sdlc/vcs`.)

- [ ] **Step 3: Update the C2 register row**

In `docs/reports/external-ideas-2026-09.md`, change the C2 row's Status to `✅ **Fixed**` and replace the "Where it lands" cell with a summary carrying the three things a future reader must not have to rediscover:

```
`harness/containment.py` gains a `phase: repair` field; the fence is an
ordinary `deny` rule in `policy/containment.yaml` and the overlay is a
`repair: bool` parameter on `HarnessRequest` (the `write_root` pattern) —
nothing is synthesized, so the enforced policy is the file in git. Paired
with a deterministic backstop (`vcs/git.py:check_test_drift`) that measures
content drift under the same globs against an anchor commit, closing the
Bash channel (`PATH_MATCHES` can never fire on Bash — `target_of` returns
the command string) and the `git update-index --skip-worktree` evasion.
A human at the fix-loop gate can thaw for exactly one attempt, which also
re-anchors. **Rides `containment_enabled`, which is off by default.**
Residual, named not fixed: the QA venv (`.sdlc-venv`, inside the worktree —
manifest-declared installs are caught via the drift set, undeclared
`pip install` and site-packages patching are not), and gitignored paths,
which `git diff` cannot see. Slack has no thaw affordance; operators use the
dashboard or CLI for that one reply.
```

- [ ] **Step 4: Commit**

```bash
git add docs/reports/external-ideas-2026-09.md
git commit -m "docs: mark C2 fixed, with its residuals named

Refs C2 in docs/reports/external-ideas-2026-09.md

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01DjV3tXwKFT6UWxLwRdtHcj"
```

---

## Known residuals — named, not fixed

Write these into the register row (Task 9). They are deliberate scope decisions, each with its reason:

1. **The QA venv.** `_ensure_python_env` provisions `<worktree>/.sdlc-venv` (`stages/qa/activities.py:112`, `:136`) and re-converges it on every QA call, and `run_test_suite` runs the contract's command under it. A repair session could `pip install` a collection-altering package or patch `site-packages` directly: outside `G`, outside the drift set, and gitignored. The *cheap* version of this attack — declaring the package in a manifest — **is** caught, because every manifest is in `C`. What remains is an undeclared install (high-knowledge, against QA internals) and hand-patched module bytes, which a `pip freeze` snapshot could not see anyway since freeze reads metadata. Building partial machinery for an undemonstrated threat is gold-plating by this row's own rule; revisit if the benchmark loop ever exhibits one.
2. **Gitignored paths.** `git diff` cannot see them, full stop. This bounds the free side-benefit — the same drift check over `.claude/**` / `.opencode/**` closes the pre-existing Bash hole in `no-agent-config-write` — to *tracked* agent-config paths, leaving `.claude/settings.local.json` outside. Creations are **not** a gap: each attempt's checkpoint `git add -A` runs before the drift check, so a new untracked-but-not-ignored file is committed and visible in the same attempt. A `git status --porcelain --ignored` probe was considered and cut: pre-existing ignored files would flood every attempt unless snapshotted at attempt 1, which is snapshot machinery for a channel that is exotic for tests and marginal for agent config.
3. **Narrative pressure on the thaw.** The denial reason reaches the model verbatim (`hook.py:8-10`) and the gate analysis mixes deterministic evidence with model-authored QA/review text (`_fix_loop_issues`, `stages/qa/step.py:67-113` — note it is *mixed*, not purely model-authored; `qa_raw.tests_passed` is deterministic and the qa slice's own invariant forbids models overriding it). So a cheating session's best play is prose aimed at inducing a human thaw. Mitigated, not eliminated: the thaw is a separate explicit field never inferred from text; it is single-attempt and re-anchors, so N thaws are N visible events rather than laundered drift; and the human is shown the drift *patch*, not just paths.
4. **Config-shaped weakening outside `C`.** `C` covers the common runners and manifests. An exotic build system's config is not fenced and not measured until someone adds its globs to `drift_paths`.

## Explicitly rejected alternatives — do not re-propose without new information

- **Deriving the protected paths from attempt 1's diff.** Blind to the pre-existing suite a brownfield task never touched, which `pytest -q` still collects and judges; needs its own frozen artifact plus a fallback that *is* the glob set anyway.
- **A `test_paths` field on `ValidationContract`.** The contract is frozen before code exists (`stages/architecture/models.py:61`), so it could only carry planner guesses.
- **Parsing `test_commands` for paths, or asking the runner via `pytest --collect-only`.** The default command names no path; the runner probe is runner-specific, can hang, and misses collected-out files.
- **Merging a synthesized policy tempfile per task.** Its only unique capability is per-task *patterns*, which the path-source decision already rejected; it costs a second digest to audit and a serialize/re-parse round-trip that turns a bug into a `ContainmentError` mid-repair.
- **`action: escalate` for the freeze.** Hook-layer-only by validation, so unenforceable on opencode; competes for the escalation cap; the operator gate is already the designed human unlock.
- **A `CheckResult` in `gate.py` / `ABSOLUTE_FLOOR`.** Drift already forces `task_passed = False` upstream, and a floor check ignores overrides — which would fight the thaw.
- **Adding `Bash` to the freeze rule's `tools`.** Dead code: `PATH_MATCHES` compares against `target_of`, which returns the command string for Bash.
- **A `:(glob)` pathspec in the backstop.** Changes semantics away from `fnmatch`, breaking the one-pattern-list-four-engines property.
