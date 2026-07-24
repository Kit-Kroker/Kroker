# E-15/E-16 — `pre_tool` containment for coding harnesses (ADR-17)

| | |
|---|---|
| Date | 2026-07-24 |
| Status | Approved design |
| Roadmap | E-15, E-16, and the harness half of E-18 — §9.4 |
| Anchors | FR-703 (`pre_tool` hook + egress policy), NFR-5 (tiered containment), ARCHITECTURE §10 (risk classing lives in the hook, not `--allowedTools`) |
| PRD | **No new FR.** FR-703 already mandates the hook by name; it gains a partial-landed note |
| ADR | **ADR-17 (new)** — containment as a declared harness capability; native config inner, hook outer, fail closed |
| Out of scope | E-17 approval escalation into the gate machinery; the research stage's Python-side egress (FR-107); network-level egress, which is **E-21**'s OS/container tier |

## Problem

`ARCHITECTURE.md` §10 says risk classing lives in a `pre_tool` hook. FR-703
says destructive-action denial *shall* be enforced there. Neither exists.

What exists is one layer: the env allowlist (`adapters.py:56-71`), which
controls what secrets the child *starts* with and nothing about what it
subsequently *does*. Every harness is launched with its approval mechanism
explicitly disabled — `--permission-mode acceptEdits` (`adapters.py:246`),
`--auto` (`:364`), `--force` (`:508`) — because a non-interactive run
otherwise blocks forever on an approval that never arrives. So today: a
coding agent inside a worktree may write anywhere the worker user can write,
delete anything, and reach any host.

A worktree is not a sandbox, and right now it is not even a fence.

## The constraint that shapes everything

**There is no in-process tool-call boundary to hook.** All three harnesses
run as child processes (`adapters.py:144`, `create_subprocess_exec`); their
tool calls happen inside the child. A `pre_tool` "hook seam in
`harness/adapters.py`" therefore cannot be a Python callback per tool call.
It can only be *the adapter configuring the child CLI's own mechanism*.

Those mechanisms are unequal, which is the design's central difficulty:

| harness | native deny | hook | notes |
|---|---|---|---|
| claude | `permissions.deny` via `--settings` | `hooks.PreToolUse` | full |
| opencode | `permission` deny block (`--auto` = "auto-approve permissions **that are not explicitly denied**") | plugins only, and we pass `--pure` (`:364`) which disables them | native only |
| cursor | none surfaced | none surfaced | neither |

## Decisions (settled during brainstorming)

1. **Scope = the seam, deny-by-rule, and harness egress rules.** E-17 and
   the research egress path get their own specs.
2. **The child hook is the authoritative layer, capability-declared.**
   Policy is declared once; each adapter translates it and declares what it
   can enforce. A harness that can enforce *nothing* fails closed rather
   than running unpoliced (ADR-17).
3. **Policy is a versioned asset**, `policy/containment.yaml` — a policy
   change is a reviewable file diff, matching agents-as-folders (E-1/E-2)
   and schedules-as-files (E-12). *Corrected from `config/containment.yaml`
   during planning: there is no `config/` directory — E-1 migrated
   `config/agents.yaml` into `agents/`, and top-level asset directories
   (`agents/`, `schedules/`, `benchmarks/`) are the convention. Resolution
   mirrors `agents/loader.py`: explicit arg → `$SDLC_CONTAINMENT_POLICY`
   → repo-root discovery, with no `__file__` walk.*
4. **Hybrid enforcement: native config inner, hook outer** — FR-703
   verbatim. Verified against the installed CLI, this is an *invariant the
   CLI enforces for us*, not a convention we maintain (see §0 below).
5. **Denials normalise per adapter into a canonical `ToolDenial` list**,
   exactly the `normalise_session`/ADR-16 pattern.
6. **Tool-level, not network-level.** Stated as a limitation, not papered
   over; FR-703's egress clause is marked partial and points at E-21.

## 0. Verified against the installed CLI (2.1.219)

These are not assumptions; each was checked before the design settled.

- **`permissions.deny` strictly beats the hook.** Two fixed defects: a
  hook's `permissionDecision: "ask"` can no longer downgrade a deny rule,
  and a hook returning `"allow"` can no longer bypass one (including
  enterprise managed settings). **This is why the hybrid is safe:** a buggy
  or subverted hook cannot weaken the declarative layer. The layering in
  FR-703's "with native config as the inner layer" is structural.
- **`--include-hook-events` requires `--output-format stream-json`** —
  which `build_cmd` already passes (`:249`). Hook verdicts arrive in the
  *same stream* `normalise_session` already parses. **No side-channel log
  file and no new IPC path.**
- **Executed live against 2.1.219, and it works end-to-end**: a hook
  returning `{"hookSpecificOutput":{"permissionDecision":"deny",
  "permissionDecisionReason": ...}}` on stdout with exit 0 blocks the call,
  and the reason reaches the model verbatim (it quoted the rule text back).
- **The `result` event carries a structured `permission_denials` list**
  (`tool_name`, `tool_use_id`, `tool_input`) — a first-class denial record.
  `parse()` already reads that event (`:263`), so no extra parsing surface.
- **But the two layers are NOT equally observable.** A *hook* denial
  populates `permission_denials`; a *native* `permissions.deny` denial
  blocks correctly yet reports `permission_denials: []`, leaving only prose
  in the tool result. **Both verified live.** This inverts which layer is
  primary — see §4a.
- `permission_denials` carries no reason or rule id, so the hook **encodes
  the rule id into the reason string** (`"[rule-id] reason text"`). Belt;
  the `hook_response` event's `output` field is suspenders.
- **A `"defer"` permission decision exists**: headless sessions pause at a
  tool call and resume with `-p --resume` to have the hook re-evaluate.
  **This dissolves E-17's blocker** — the escalation never requires an
  activity to await a workflow signal. Recorded here; not built here.
- **On Windows, hooks execute via Git Bash, not cmd.exe.** This repo is
  win32, so the entry point must be invocable from that shell.
- **Version drift:** `adapters.py:239` pins `2.1.218`; installed is
  `2.1.219`. E-24's `check_harness_versions` will flag it.

## Design

### 1. Policy asset (`policy/containment.yaml`)

A fixed, small predicate vocabulary — deliberately not an expression
language (YAGNI). Each rule declares the layer it needs, so coverage is
computable rather than assumed.

```yaml
version: 1
rules:
  - id: no-out-of-worktree-write
    layer: hook                 # needs per-call path resolution
    tools: [Write, Edit, NotebookEdit]
    predicate: path_outside_worktree
    reason: "Writes are scoped to the task worktree."

  - id: no-recursive-force-delete
    layer: native
    tools: [Bash]
    predicate: command_matches
    patterns: ["rm -rf *", "rm -fr *"]
    reason: "Destructive recursive delete."

  - id: no-agent-config-write
    layer: native
    tools: [Write, Edit]
    predicate: path_matches
    patterns: [".claude/**", ".opencode/**", ".cursor/**"]
    reason: "The agent may not rewrite its own permission config."

  - id: egress-allowlist
    layer: hook
    tools: [WebFetch, WebSearch, Bash]
    predicate: host_not_allowlisted
    allow_hosts: ["api.anthropic.com", "github.com"]
    reason: "Egress restricted to the model API and the git remote."
```

Predicate vocabulary: `path_outside_worktree`, `path_matches`,
`command_matches`, `host_not_allowlisted`. Adding a fifth is a code change
plus a schema bump — intentionally.

Two things this schema deliberately fixes:

- **Patterns are ours, not any CLI's.** `patterns` use our glob/command
  syntax; each adapter *translates* them into its own (claude's
  `Bash(rm -rf:*)` deny form, opencode's `permission` block). The policy
  author never writes CLI-specific syntax — the same separation the
  toolchain adapter makes for coverage formats.
- **`host_not_allowlisted` over `Bash` is best-effort by construction.** It
  extracts hosts from the command line (a `curl`/`wget` URL, a `git remote`
  target). A host reached some other way from inside an allowed `Bash` call
  is invisible to it. This is the tool-level limitation in miniature, and
  the reason the rule is a fence rather than a boundary.

### 2. `src/sdlc/harness/containment.py` — pure policy

No I/O, no CLI knowledge, no subprocess. The entire risk-classing decision
lives here so it is unit-testable as a table.

```python
class ContainmentLayer(str, Enum):     # models.py convention, not StrEnum
    NATIVE = "native"   # declarative deny inside the CLI's own config
    HOOK   = "hook"     # per-call inspection callback

class Verdict(BaseModel):
    allow: bool
    rule_id: str | None = None
    reason: str | None = None

def load_policy(path: str) -> Policy: ...
def evaluate(policy: Policy, tool: str, tool_input: dict,
             worktree: str) -> Verdict: ...
```

`worktree` is a **parameter, never computed.** `create_worktree`
(`activities.py:260-274`) may return `<task>.N` instead of the canonical
path when a Windows lock forces a fallback, and its docstring makes the
returned path authoritative. A hook that recomputed the path would
mis-evaluate every out-of-worktree check on precisely the runs that already
hit trouble.

### 3. `src/sdlc/harness/hook.py` — the entry point

Invoked as `python -m sdlc.harness.hook` — **its own module, not a `cli.py`
subcommand.** There is no `sdlc` console script, and `cli.py:main()` builds a
Temporal client; the hook runs once per tool call, so importing the workflow
stack there would tax every tool the agent uses. Reads the `PreToolUse` JSON on stdin,
calls `evaluate`, writes the decision to stdout:

```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": "<rule reason>"}}
```

Deliberately dumb — no policy logic, so the hard part stays in-process and
testable. **Any internal exception exits as a deny**, never as an allow.
The exact JSON shape is pinned against 2.1.219 during implementation.

### 4. Adapter contract (ADR-17)

Three members on `CodingHarness`, beside the existing `normalise_session`:

```python
containment: frozenset[ContainmentLayer]           # what this CLI can enforce
def apply_containment(self, policy, req) -> None   # compile into flags/config
def normalise_denials(self, stdout) -> list[ToolDenial]
```

- **claude** → `{NATIVE, HOOK}`. Writes a temp settings JSON (`permissions.deny`
  + `hooks.PreToolUse` → `sdlc harness-hook`), passes `--settings <abs path>`
  and `--include-hook-events`. Denials parsed from the hook events in the
  stream.
- **opencode** → `{NATIVE}`. Emits a `permission` deny block; denials parsed
  from its event stream.
- **cursor** → `frozenset()`.

### 4a. `layer` is a *minimum*, and every adapter enforces at every layer it has

Because native denials are structurally unobservable (§0), a rule marked
`layer: native` is **not** compiled *only* to the native layer. `layer`
declares the **minimum capability the rule requires**; each adapter then
enforces it at *every* layer it possesses:

| rule | claude (`{NATIVE, HOOK}`) | opencode (`{NATIVE}`) |
|---|---|---|
| `layer: native` | native deny **and** hook | native deny |
| `layer: hook` | hook | *unenforceable — reported* |

The payoff: on claude every denial is observable via `permission_denials`,
while the native rule remains as the floor that a buggy hook cannot weaken
(§0, first bullet). The hook can trivially do the command/path matching the
native layer does, so the duplication costs nothing. Defense in depth and
full observability stop being a trade-off.

**The temp settings file lives outside the worktree**, in the activity's temp
dir, passed by absolute path. Writes *inside* the worktree are permitted by
design, so a settings file placed there is a file the agent may rewrite — it
could edit its own policy. `no-agent-config-write` closes the same door from
the other side; the precedence between our `--settings` and a worktree-local
settings file is pinned during implementation, but we deny the write rather
than depend on precedence.

### 5. Coverage is reported, not assumed

Fail-closed applies to *total* absence: containment enabled and
`containment == frozenset()` → `run_coding_task` refuses to start. Cursor is
the one that fails closed today; that is a known, deliberate cost.

Partial coverage does **not** refuse — it is *recorded*. A harness with only
`NATIVE` cannot enforce `layer: hook` rules, and silently varying containment
would confound the benchmark's harness axis. So the run carries:

```python
class ContainmentReport(BaseModel):
    enabled: bool
    layers_active: list[ContainmentLayer]
    rules_enforced: list[str]
    rules_unenforceable: list[str]
```

This makes variation *visible* rather than absent — the same discipline as
E-36's rule that a rubric number is never read without its trust level. An
operator wanting the stricter reading sets `ContainmentConfig.strict: true`,
which promotes partial coverage to a refusal.

### 6. Denial record

`ToolDenial` is small and bounded, and travels inline (same discipline as
`SessionDigest`):

```python
class ToolDenial(BaseModel):
    tool: str
    rule_id: str
    layer: ContainmentLayer
    reason: str
    target: str | None = None     # path or command, scrubbed
```

`HarnessRunResult` gains `denials: list[ToolDenial]` and
`containment: ContainmentReport | None`. Denial *events* also land in the
claim-checked `HarnessSession`; `SessionDigest` gains a `denials` count so
clean-green runs still report them.

For claude, `normalise_denials` reads `result.permission_denials` — the
structured, reliable spine — and recovers `rule_id`/`reason` from the
rule-id prefix the hook embeds. Native-only denials (no hook fired) are not
structurally reported by the CLI; §4a is what keeps that case empty in
practice on claude, and on opencode it is a known limit recorded in
`ContainmentReport`, not a silent gap.

**Denials are advisory in this increment.** The harness was already told
"no" and continued; a denial does not fail the task. It is recorded as a
stage-record signal for the E-36 heatmap. Escalation-on-denial is E-17, and
`defer` is what will carry it.

### 7. Config surface and flow

`PipelineConfig.containment_enabled: bool = False` — off by default,
matching `research_enabled` / `deep_review_enabled` / `memoization_enabled`
— plus a `ContainmentConfig` (policy path, `strict`). The workflow cannot
read files inside the sandbox, so it passes flags on `CodingTaskInput`; the
YAML loads **activity-side**, exactly as the agent registry does.

```
run_coding_task:
  load policy (activity-side)
    -> capability check; refuse if enabled and no layers
    -> harness.apply_containment(policy, req)
    -> harness.run(...)                      # existing path, unchanged
    -> harness.normalise_denials(raw_stdout)
    -> capture_session(...)                  # denials are in the same stream
```

**No memoization impact.** `_dev_task` (`feature.py:690`) is not memoized —
only clarify/architecture/plan use `_cached_stage` — so the policy does not
enter any `content_key`.

### 8. Error handling

| failure | behaviour |
|---|---|
| policy missing/invalid, containment enabled | refuse to start (fail-closed, as E-38's scrub and SC-5) |
| harness declares no layers, containment enabled | refuse to start |
| partial layer coverage | run; record `rules_unenforceable` (refuse if `strict`) |
| hook process raises internally | exit as **deny** with the reason |
| `normalise_denials` raises | best-effort, as `capture_session` — never fails the task |
| containment disabled | today's behaviour exactly, no new code path |

### 9. Testing

- `containment.py` is pure → the rule matrix is a plain unit-test table,
  including the `<task>.N` worktree-path case and symlink/relative-path
  escapes.
- `hook.py` → stdin→stdout contract tests, plus the exception-becomes-deny
  case.
- `apply_containment` → assert on the built command and the emitted settings
  JSON; no CLI executed.
- Capability/fail-closed → assert `run_coding_task` refuses for a
  zero-layer harness and records `rules_unenforceable` for a native-only one.
- One live end-to-end test (`claude -p` attempting a denied write) marked so
  CI can skip it, matching how the repo already treats live-harness tests.

## Limitation, stated plainly

**This increment buys tool-level egress denial, not network-level.** The
hook sees `Bash(curl ...)` and `WebFetch(url)` and can deny them. It does not
see a socket opened from a Python one-liner inside an allowed `Bash` call.
Real egress restriction needs the OS/proxy tier, which is **E-21**.

FR-703 is therefore marked ⚠️ partial: destructive-action denial ✅, egress
tool-level only. NFR-5's `pre_tool` clause closes; its OS-user/container
clause does not.

## Roadmap edits this implies

- E-15 `[x]`, E-16 `[x]`, E-18 `[ ]` ⚠️ partial (tool-level; network-level → E-21)
- FR-703 ⚠️ with the partial note; NFR-5 note
- §9.4 preamble updated
- **E-17 updated with the `defer` finding** — its blocker is dissolved
- E-24 note: pinned 2.1.218 vs installed 2.1.219
- ARCHITECTURE §12: **ADR-17**
