# FR-202 close-out: the configured validation-retry count — design

Date: 2026-11-14
Status: implemented 2026-11-14 (branch feat/fr202-validation-retries)
Owner: brainstorming session (superpowers), picked approach: **A — registry default + per-role override, forwarded per call**

## Intent

Close FR-202's open half. PRD §6 (FR-202): *"Proposer agents SHALL emit
schema-validated Pydantic artifacts; validation failure SHALL re-prompt up to
a configured retry count."* The first SHALL is met — every proposer
constructs with `output_type=`. The second is half-met and hardcoded: four
roles pin `retries={"output": 3}` in their `agent.py` (planner `2f0dc2f5`
2026-08-30 after live pattern-completion degradation; research `28ccd85c`
2026-10-19 after a live `"Exceeded maximum output retries (1)"` killed a
sub-question; constitution and product copied the shape 2026-11-11/12),
twelve proposers sit at the pydantic-ai default 1 (= zero re-prompts), and
the *configured* count the clause demands exists nowhere: `RoleConfig` has
no field, `agent.yaml` carries only `kind`+`model`, and no `defaults:`
block is parsed.

SDLC-spec-v2 §2 (lines 189–191) already decided where the count belongs:
v1's custom `MAX_VALIDATION_RETRIES` loop was deleted *because* pydantic-ai
provides the re-prompt natively, with "the count moves to
`defaults.validation_retries`." The 2026-07-05 audit's stated blocker
("no registry to hold it") is stale — FR-201's registry landed since. This
design moves the count where the spec said it goes.

## Why

- FR-202 is the last open `[ ]` in the Agents family (ROADMAP §2). The
  other four FR-200 rows are `[x]`.
- The mechanism needs no invention: pydantic-ai 2.61.0 accepts `retries`
  **per call** (`Agent.run(..., retries={"output": n})`, verified against
  the installed signature). The knob can be forwarded only-when-set —
  the 004 D7a model-forwarding precedent — keeping unset runs
  replay-identical, without touching the loader→`build()` contract.
- One real inconsistency gets absorbed as a side effect: research's
  stage-local plan/synthesis agents (`stage.py:114`, `:464`) build with no
  `retries` (default 1) while the role's own sub-question agent carries 3.
  A role-scoped count makes "the research role retries validation three
  times" true of every agent serving the role.

## Goals

1. `registry.yaml` gains `defaults: {validation_retries: 1}`; each
   `agent.yaml` may override per role. Effective count =
   role override → registry default → 1.
2. The four evidenced roles express their 3 through the registry
   (`agents/{planner,research,product,constitution}/agent.yaml:
   validation_retries: 3`); their `agent.py`s drop the hardcoded
   `retries={"output": 3}`.
3. Every proposer's re-prompt count is a configured number — FR-202's
   clause reads true with no per-role code change required to tune it.
4. No-config-change runs stay replay-identical: forwarding happens only
   when the effective count ≠ 1, and the twelve default roles forward
   nothing.
5. Same-diff docs: ROADMAP FR-202 row + Last verified + log entry, the
   five pinning tests, the touched stage contracts and slice AGENTS.md
   files, the four `agent.py` comments.

## Non-goals

- **No raise of the twelve default roles.** Evidence covers planner and
  research only; planner's own comment hedges ("doesn't say every proposer
  role degrades the same way"). Raising a default later is a config edit
  plus one `prompt_eval` run, not code.
- **No per-run override** (`PipelineConfig` stays out of it). The count is
  registry-level, like `instructions.md`; a per-run story can be added
  later through the same forwarding seam if a benchmark arm ever needs it.
- **No new retry machinery.** pydantic-ai's output-retry loop is the
  mechanism (spec §2: v1's custom loop stays deleted). Gate rounds
  (FR-301), the architect delta check (E-84 D10), the fix loop (FR-105),
  Temporal activity attempts, and the crew rounds.max critique loop are
  untouched and remain distinct.
- **No memo-key change.** The retry loop runs inside one `agent.run`; it
  changes effort, not the artifact mapping, so `content_key` inputs are
  unchanged.

## Background — where the count must reach

Producer call sites, by execution shape (from the FR-202 investigation,
2026-11-14):

**Workflow-side, one seam plus two direct calls.** `RoleHost._run_role`
(`workflows/role_host.py:175`) is the single model-egress point for the
durable registry agents: clarify supervisor, architect, planner, qa,
reviewer, analyst, merge_verdict, devops_planner, deep_review, adversary,
handoff. One forwarding hook there covers those. **Two proposers bypass
it** (builder-check finding): the assessment workflow calls its agents
directly, with no `_run_role` and no existing 004 model-forwarding branch
to sit beside — `workflows/assessment.py:453` (`t_discover.run(...)`,
fail-closed degrade on any exception) and `:675` (`t_risk.run(...)`, same
shape). For these two, a validation retry is a degrade-avoidance device:
today one malformed output degrades the whole phase with a reason string.

**In-activity, direct imports.** These import the registry themselves and
forward locally, mirroring how they already handle the 004 model override:

| Site | Serves | Today |
|---|---|---|
| `research/stage.py:122` (plan) | research | default 1 |
| `research/stage.py:277–307` (sub-question) | research | 3 at construction |
| `research/stage.py:469` (synthesis) | research | default 1 |
| `research/toolset.py:92,100` (architect's research tool) | research | inherits agent's 3 |
| `requirements/stage.py` `_draft_requirements_impl` (3 run branches) | product | 3 at construction |
| `constitution/stage.py` (same shape, 3 branches) | constitution | 3 at construction |

**Fan-out agents.** `clarify_route_agent`/`clarify_probe_agent`
(`agents/roles.py:168,192`, consumed via `graph_nodes/precode.py:165`) are
built inline and reuse the clarify role; they take clarify's count
(default 1 → forward nothing → unchanged).

**Out of scope by construction.** Harness roles (`dev`, `devops`, `test`)
never emit schema-validated artifacts; the crew protocol's
`ValidationError`-as-critique path (`crew/activities.py:130`) is bounded
by `rounds.max`, not this knob.

## The design

### VR-1 — the config surface

`registry.yaml` gains an optional `defaults:` mapping beside `version`:

```yaml
version: 1
defaults:
  validation_retries: 1
```

`RoleConfig` (`core/models.py:185`) gains
`validation_retries: int | None = Field(default=None, ge=1, le=5)`; a
role's `agent.yaml` sets it to override the default. `None` means "inherit
the default" and never survives parsing: `_parse`
(`agents/loader.py:151`) reads the `defaults:` block, validates
`validation_retries` is an int in 1..5, and applies it to every role whose
own `agent.yaml` omits the key. An unknown key inside `defaults:` is a
`RegistryError` — the same fail-closed "no silent dead config" rule
`_parse_role` already enforces for harness roles carrying unread files.
The 1..5 bound is this design's call (my call): the only live evidence is
at 3, and every retry is a model request that must fit inside the role's
existing `UsageLimits` budget.

The pipeline mirror (`_validate_pipeline_mirror`, `loader.py:346`) spans
harness knobs only and is deliberately NOT extended — proposer knobs have
no `PipelineConfig` mirror to drift from.

**VR-1b — fail-closed against dead config** (builder-check finding): the
key is legal **only** on `kind: proposer` and `kind: research` roles. A
`validation_retries` on a harness role (`dev`, `devops`, `test` — they run
CLIs and never emit validated artifacts) is a boot-time `RegistryError`,
per `_parse_role`'s own "silent dead config" rule for harness roles
carrying unread files. With VR-3a below, every proposer/research role's
call sites are wired, so no legal key can parse into a value no site
reads.

### VR-2 — the effective value, computed once at import

`agents/loader.py` exposes
`effective_validation_retries(roles, role) -> int`; `agents/roles.py`
computes `OUTPUT_RETRIES: dict[str, int]` beside `STAGE_MODELS`
(role-keyed, like `REGISTRY`). Its keyspace is the **proposer+research**
roles — `{name for name, cfg in REGISTRY.items() if cfg.kind != "harness"}`
— asserted in tests, so a new proposer role cannot ship unwired silently.

### VR-3 — forwarding, only-when-set

The forwarding rule, identical at every call site:

```python
n = OUTPUT_RETRIES[role]
if n != 1:
    kwargs.setdefault("retries", {"output": n})
```

- `_run_role` applies it once for every workflow-side producer it serves. `setdefault`
  respects a hypothetical explicit caller value; no caller passes `retries`
  today.
- **VR-3a — the two direct assessment calls** (builder-check amendment):
  `assessment.py`'s `t_discover.run(...)` and `t_risk.run(...)` gain the
  same three lines inline — no `_run_role` refactor (routing them through
  the host would also pull in usage tracking/pricing changes this design
  does not make), no scope carve-out (the PRD clause covers every
  proposer; FR-202 cannot close with two of sixteen silently unwired).
- Each in-activity site (table above) applies it locally, next to its
  existing 004 D7a model-forwarding branch. No activity input payload
  changes: the count is registry-level and the registry is importable
  in-activity (these sites already do `from sdlc.agents.roles import ...`).
- The four evidenced `agent.py`s drop `retries={"output": 3}`; their
  comment blocks are rewritten to point at the registry value and keep the
  live-failure evidence (it is the reason the 3s exist).
- pydantic-ai semantics: `run(retries=...)` overrides the construction
  default for that run; construction stays at 1 everywhere. The durable
  engine already runs the output-retry loop through model-request
  activities (`tests/durability/test_payload_guard.py` D5 case 7), so the
  per-call override rides the same path — but this is *verified*, not
  assumed (VR-5).

### VR-4 — behavior deltas, stated

| Roles/agents | Before | After |
|---|---|---|
| planner, research (sub-q), product, constitution | 3 at construction | 3 forwarded — same value, same budget, no user-visible change |
| research plan + synthesis (`stage.py:114,464`) | 1 | **3** — the one real behavior change; research is off by default, fake-tested, and never run live (ROADMAP FR-107 residual) |
| architect's research tool (`toolset.py`) | inherits 3 | 3 forwarded — unchanged |
| discover, risk (assessment direct calls) | 1 | 1 — nothing forwarded at default; now *configurable*, and a configured value takes effect (the builder check's dead-config hazard, closed by VR-3a+VR-1b) |
| the twelve default roles + fan-out agents | 1 | 1 — nothing forwarded, calls byte-identical |

### VR-5 — tests

- Loader: `defaults:` parse (default, per-role override, out-of-range,
  unknown-key rejection); `effective_validation_retries` precedence;
  **harness-role `validation_retries` rejected at boot (VR-1b)**.
- `roles`: `OUTPUT_RETRIES` keyspace == proposer+research roles of
  `REGISTRY` (the STAGE_MODELS/STAGE_ROLES pattern).
- Forwarding: `_run_role` forwards `{"output": 3}` for a role configured 3
  and adds no kwarg for a role at 1 (fake-agent seams); each in-activity
  site asserts the same via its `_agent` test seam; the two assessment
  direct calls assert the same via their existing fake-agent seams.
- The five existing `_max_output_retries == 3` pins
  (`tests/plan/test_planner_agent_retries.py`,
  `tests/research/test_research_agent_retries{,_edges}.py`,
  `tests/constitution/test_role.py`, `tests/requirements/test_role.py`)
  are rewritten: construction default 1 + forwarded value 3 + registry
  row carrying the 3.
- Durability: one test pinning that a per-call `retries` override drives
  the output-retry loop under `TemporalDurability` (same scheduled
  command sequence as the old construction-time value on a
  validation-failure script) — VR-3's one unverified assumption, made
  explicit.

### VR-6 — docs in the same diff

ROADMAP FR-202 row → `[x]` with the one-sentence close-out; Last verified
cell refreshed, full entry prepended to
`docs/roadmap/last-verified-log.md`. SDLC-spec-v2 §2 needs no change (the
`defaults.validation_retries` sketch becomes true). Stage contracts:
`requirements.md:107–108` and `constitution.md:80–81` reword the
`retries={"output": 3}` mechanism line to the registry-forwarded form;
`architecture.md:13`'s FR-202 citation stands. Slice AGENTS.md files:
research, requirements, constitution each gain one line under their
single-retry-layer note (output-retry forwarding is semantic re-prompt,
not a stacked infra retry — the 004 single-layer rule is unbroken).
PRD FR-202 text unchanged — it is the requirement, now met.

## Approaches considered

- **A — registry default + per-role override, per-call forwarding
  (picked).** Spec-faithful (the count lands exactly where §2 said);
  replay-neutral (only-when-set forwarding, 004 D7a precedent); no
  loader→`build()` contract change; in-activity sites need no payload
  change. Cost: one new `defaults:` parse path.
- **B — construction-time through the build contract.** Loader passes the
  value into each `build()`. Touches all 16 `agent.py`s plus the loader
  build contract, and still cannot express a per-run value later. Pure
  churn for nothing A lacks.
- **C — run-level `PipelineConfig.validation_retries`.** One number for
  every role — loses the per-role tuning the live evidence argues for,
  and misplaces a knob the spec put in the registry. Rejected.

The twelve-role default (keep 1 vs raise) was the partner's second call:
**keep 1** — zero behavior change, clause satisfied because the count is
configured; raising later is config + one prompt-eval run.

## What's left to the builder

- Exact test-file placement for the forwarding tests (follow each slice's
  existing seams; the plan will name them).
- Whether `OUTPUT_RETRIES` also re-exports from `agents/loader.py` for the
  eval path (only if a consumer appears; none today).
- Comment wording in the four rewritten `agent.py`s, provided the
  live-failure evidence survives verbatim.

## Risks

- **Per-call `retries` under durability not yet pinned** (VR-5's durable
  test). If the capability ignored it, the four roles would silently fall
  back to 1 — the pinning tests catch exactly this. *(Builder check
  independently confirmed the durable wrapper forwards per-call `retries`
  at `durable_exec/temporal/_agent.py:549`; the test exists to keep it
  pinned.)*
- **Research plan/synthesis 1→3** raises worst-case requests per
  research run by at most 4 (two extra retries × two agents), inside the
  stage's existing `max_requests` budgets; exhaustion still degrades
  honestly (`UsageLimitExceeded` is never re-raised, requirements'
  degradation discipline).
- **Replays of in-flight runs**: a validation-failure history recorded
  under construction-time 3 replays under forwarded 3 — same effective
  budget, same command sequence; clean runs schedule nothing new either
  way. The only asymmetry would be a *config* change mid-run, which the
  registry's versioning already governs.
