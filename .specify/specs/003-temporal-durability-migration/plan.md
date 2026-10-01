# Implementation Plan: Migrate Durable Agents to TemporalDurability

**Branch**: none (spec directory `003-temporal-durability-migration`) | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: approved spec (GATE 1: A3 inventory-first deferred, B2 migration-only, C3 zai separate, D1 6.2/6.3 out; FR-019 default = heartbeat override to none).

## Summary

Replace the deprecated `TemporalAgent` wrapper on all 16 durable agents with the `TemporalDurability` capability, attached at construction, with **no change to agent names, toolset ids, scheduled activity sequence, retry/timeout attributes, or model behaviour**. The loader contract gains a keyword-only `capabilities` parameter fed by a per-role factory from `roles.py`; `worker.py` registers activities through `TemporalDurability.from_agent`; `t_*` stay as plain aliases. Replay safety is proven by frozen pre-migration fixtures and newly captured histories recorded **on unmodified main before any migration change**, plus a differential provider-payload capture and a sandbox-timing measurement. Research: [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.13 (image and dev container; host venv is not a verification environment)

**Primary Dependencies**: `pydantic-ai-slim[...temporal]>=2.51,<2.52`, `pydantic-ai-harness>=0.36,<0.37`, `temporalio` (pinned by uv.lock)

**Storage**: N/A (test fixtures under `tests/replay/`)

**Testing**: pytest tiers per `pyproject.toml`: fast default; `-m temporal` opt-in (excluded from fast); `-m slow`, `live`, ... not needed. Ruff, mypy (scoped to `src/`), `scripts/check_file_size.py`.

**Target Platform**: Linux container (production worker image = dev container base)

**Project Type**: single repo, Temporal worker + workflows

**Performance Goals**: workflow task must not trip the 2 s deadlock detector more often than today (T-D6)

**Constraints**: activity/agent/toolset names frozen; replay of every captured history green with no history/golden edit (SG-2/SG-3); 1000 lines/file; all runs in the dev container; nearest `AGENTS.md` read before editing a subpackage (`src/sdlc/workflows/AGENTS.md`, `src/sdlc/stages/research/AGENTS.md` if present, `tests/replay`)

**Scale/Scope**: 16 agents, 14 assets + 2 inline, ~13 test files, 4 docs

## Constitution Check

`.specify/memory/constitution.md` is the unfilled template (no ratified principles): no gates apply. Repo-level rules from `AGENTS.md` are carried as constraints above (file-size ratchet, artifact boundary: docs change in the same diff, sandbox/harness boundary: orchestrator edits contracts, not harnesses).

## Project Structure

### Documentation (this feature)

```text
.specify/specs/003-temporal-durability-migration/
├── spec.md
├── plan.md            # this file
├── research.md        # FR-020 outcomes, verified API facts, spike evidence
├── data-model.md      # entities and the frozen-fixture shapes
├── quickstart.md      # dev-container validation runbook
├── contracts/
│   └── loader-build-contract.md
├── checklists/
└── tasks.md           # /speckit-tasks (not this step)
```

### Source code touched

```text
src/sdlc/agents/loader.py        # durability factory, build(capabilities=), fail-closed checks
src/sdlc/agents/roles.py         # factories, fan-out agents, t_* aliases, ALL_TEMPORAL_AGENTS
src/sdlc/agents/settings.py      # docstring only
src/sdlc/worker.py               # activities via from_agent
src/sdlc/stages/research/{stage,toolset,budget_store,deps,verify}.py, src/sdlc/naming.py,
src/sdlc/workflows/{feature,assessment}.py   # comments/docstrings only
agents/<role>/agent.py (14)      # accept + forward capabilities
agents/research/exa_wrapper.py   # comment only
tests/fakes/fake_agents.py + ~12 tests using the wrapper
tests/replay/{fixtures,histories}/ (new files only), tests/durability/ (new contract + proof tests)
ARCHITECTURE.md (§4, §13, ADR-2, tech table, tree), README.md, docs/ living docs that name the mechanism
```

**Structure Decision**: no new package. One small module `src/sdlc/agents/durability.py` (activities-of helper, fixture dumper used by tests) only if the helper is needed by both worker and tests; otherwise inline in `roles.py`. `loader.py` stays free of temporal imports at module level (eval path, E-82); it imports `TemporalDurability` lazily inside `build_agents`.

## Design decisions (from research.md)

1. **Loader contract (D1)**: `build_agents(roles, model_settings, durability_factory=None, agents_dir=None)`. Per role: `dur = durability_factory()`; `build(model, instructions, model_settings, *, capabilities=[dur])`; research also `capabilities`. `durability_factory is None` keeps eval/import paths capability-free (tests of the loader itself). Assets forward `capabilities=[*capabilities, *own]` with durability **outermost** (research: before CodeMode/exa).
2. **Fail-closed checks** in `build_agents`, all `RegistryError` naming the role: old-shape `build` (TypeError) ; `from_agent(agent) is None` ; multiple durability (`UserError`) ; `activity_config` weakened vs the factory's (`start_to_close_timeout`, `maximum_attempts`) ; `heartbeat_timeout` not none ; `bound.name != agent.name`. Existing name-collision guard stays.
3. **Config (D3)**: `AGENT_DURABILITY = lambda: TemporalDurability(activity_config=AGENT_ACTIVITY_CONFIG, model_activity_config={"heartbeat_timeout": None})`; the fan-out agents use `CLARIFY_FANOUT_ACTIVITY_CONFIG` with the same override, kept as a separate named value.
4. **Aliases**: `t_x = x_agent`, optional ones stay `None`-able; `ALL_TEMPORAL_AGENTS` remains a list of agents. Rename deferred (no payoff, inflates replay diff).
5. **Registration**: `worker.py` uses `TemporalDurability.from_agent(a).temporal_activities` for each agent (or `AgentPlugin`); asserted exactly-once.
6. **Fakes/tests**: fakes become `Agent(TestModel, name=<prod name>, capabilities=[TemporalDurability(<same config>)])`, activities via `from_agent`; helper `activities_of(agent)` shared.

## Replay-proof strategy

1. **Phase A on unmodified main** (must be committed by the orchestrator before Phase B lands): (i) frozen fixture `tests/replay/fixtures/agent_activities_pre_migration.json` = per agent: agent name, toolset ids, **registered** activity names, **scheduled** names, model-activity command attributes (start-to-close, heartbeat, retry policy incl. non-retryable list, argument count); (ii) new captured histories: `architect_research_tool` (model turn -> `research` tool call -> answer), `clarify_fanout`, `assessment_discover_risk`; (iii) provider-request capture for the architect multi-turn run; (iv) baseline temporal-tier pass count.
2. **Phase D after migration**: all existing 16 histories + goldens replay unchanged; the new 3 histories replay; the fixture diff test asserts scheduled sets **exactly equal**, attributes **exactly equal** (heartbeat 0), every scheduled name registered exactly once, expected registered-set deltas listed; D8 pins green with no edit; mixed-prefix test (old-recorded architect prefix + new-code continuation) proves in-flight resume.
3. Research agent: name-level + in-activity path test (never scheduled by a workflow, R5).

## Phases

- **Phase A - Capture on main (pre-migration)**: dev-container baseline, fixtures, 3 histories, payload capture. No production code changes.
- **Phase B - Contract and loader (TDD)**: failing contract tests first; loader factory and checks; `roles.py` factories; fan-out agents.
- **Phase C - Migration**: 14 assets, aliases, worker registration, fakes and the ~12 tests, comments.
- **Phase D - Proofs and FR-020 outcomes**: replay suite, fixture diff, differential payload (a), no-`validate_args`/no-cancel scheduling (b, c), sandbox timing (d), strict-decode via architect history (e), nested research path, assessment e2e, failure-type pins, temporal tier + fast tier + lint/size.
- **Phase E - Docs and close**: ARCHITECTURE/README/docs wording, recorded FR-020 outcomes appended to research.md, file-size check, follow-up note left as filed.

## Risks

| Risk | Where | Mitigation / escalation |
|---|---|---|
| First workflow task trips the 2 s deadlock detector under the new path | spike: reproduced cold; old path did not | T-D6 measure with the real registry; mitigate (warm-up/passthrough) or **escalate to orchestrator** |
| `model_cancel_suspended_response` wire shape differs (1 -> 2 args) | source | T-D4 prove unreachable; report as residual risk; escalate if reachable |
| Provider request payload differs (no re-prepare) | FR-020a | T-A3/T-D5 differential; escalate on diff |
| Heartbeat side effect (cancellation now reaches model activities at next beat) | R3 | reported as a ruled-candidate difference; no attempt/spend effect |
| Handle mistake (`temporal_activities` on unbound instance = empty; run hangs) | spike | fail-closed check + exactly-once registration test |
| Capture after migration lands (fixtures meaningless) | process | Phase A committed by the orchestrator before Phase B lands (commit order is the guard); the fixture records the main commit it was dumped from (203e7dd) and the test asserts that field |
| Late `agent.tool(...)` after construction (architect, research) | advisor | architect history + research e2e |
| 1000-line ratchet on `roles.py` (293) / `loader.py` (464) | AGENTS.md | headroom ok; `scripts/check_file_size.py` in Phase E |

## Spec amendment (ACCEPTED by the orchestrator 2026-09-30; folded into spec.md, see its Change record)

Spec FR-005.5a requires a captured history for **both** `architect` and `research` and FR-005.6 speaks of "histories" (plural) as the mixed-prefix source. Verified in code (research.md R5): no workflow ever schedules a `research` agent activity; `t_research.run` runs only inside the architect's tool activity, in-process. A captured *workflow* history therefore cannot contain research-agent activities, so the MUST is unsatisfiable as written. Proposed wording: FR-005.5a lists only `architect` as requiring a captured history; `research` is covered by the name-level fixture plus the nested-path test (FR-011); FR-005.6/SC-006 use the single architect prefix. The plan does **not** edit the approved spec; tasks follow the proposal (T005, T033) and this deviation is reported.

## Complexity Tracking

No constitution violations. One deliberate extra: a captured-history phase (A) that precedes the change, because fixtures generated from migrated code prove nothing (spec FR-005.5, advisor-003-1).
