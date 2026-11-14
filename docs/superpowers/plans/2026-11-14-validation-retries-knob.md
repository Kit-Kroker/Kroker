# FR-202: the configured validation-retry count — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close FR-202 by making every proposer's output-validation retry count a registry-configured number (`defaults.validation_retries` + per-role override), forwarded to pydantic-ai per call, only-when-set.

**Architecture:** The count lives in the agents registry; `agents/loader.py` parses and materializes it onto `RoleConfig`; `agents/roles.py` computes an `OUTPUT_RETRIES` dict at import; every producer call site forwards `retries={"output": n}` to `agent.run(...)` only when `n != 1` (the 004 D7a only-when-set precedent, replay-neutral). The four roles that hardcode `retries={"output": 3}` today cut over to registry values; the twelve default roles forward nothing.

**Tech Stack:** Python 3.13, pydantic-ai 2.61.0 (pinned in `uv.lock`), Temporal (durable agents via `TemporalDurability`), pytest.

**Spec:** `docs/superpowers/specs/2026-11-14-validation-retries-knob-design.md` (VR-1…VR-6, VR-1b, VR-3a). The plan argues from the spec; executors read both.

## Global Constraints

- Registry version stays `1`; agent names and activity names are wire contracts — never renamed.
- Replay neutrality: forward `retries` ONLY when the effective count ≠ 1. A role at 1 must add no kwarg to any `agent.run` call.
- Forward `{"output": n}` only — never tool retries.
- Value domain 1..5, integer, everywhere the count appears.
- No custom re-prompt machinery: pydantic-ai's per-call `retries` kwarg is the only mechanism (spec §2: v1's loop stays deleted).
- Same-diff clause rule: a task that changes a slice's behavior ships its contract/AGENTS.md line in the same commit.
- `ruff check .`, `ruff format .`, `mypy` clean; `pytest` (default fast tier) green after every task.
- File ceiling 1000 lines (`scripts/check_file_size.py`) — no touched file approaches it.

## Review Focus

The five failure modes the spec implies but the happy path misses; each is pinned by the named test in its owning task:

1. **The durable wrapper ignores per-call `retries`** → the four roles silently fall back to 1. Pinned by Task 8 (`tests/durability/test_per_call_output_retries.py` — builder check already confirmed the forwarding at `durable_exec/temporal/_agent.py:549`; the test keeps it pinned).
2. **`validation_retries` on a harness role** parses as dead config. Pinned by Task 1 (`test_harness_role_carrying_the_key_is_rejected`).
3. **An unknown key inside `defaults:`** is silently ignored. Pinned by Task 1 (`test_defaults_unknown_key_rejected`).
4. **A configured value > 1 at a direct call site that forgets to forward** (discover/risk, the builder-check hazard) silently no-ops. Pinned by Task 7 (`test_discover_forwards_configured_retries` / `test_risk_forwards_configured_retries`).
5. **A role at 1 gains a spurious `retries` kwarg** — replay-breaking. Pinned by Task 3 (`test_role_at_default_forwards_nothing`).

---

### Task 1: Loader — `defaults:` block, `RoleConfig.validation_retries`, fail-closed rules

**Files:**
- Modify: `src/sdlc/core/models.py` (`RoleConfig`, ~line 185)
- Modify: `src/sdlc/agents/loader.py` (`_parse` ~151, `_parse_role` ~171)
- Modify: `agents/registry.yaml` (add `defaults:` block)
- Test: `tests/test_registry_validation_retries.py` (create; build tmp registries the way `tests/test_registry_ignores_fixtures.py` does)

**Interfaces:**
- Consumes: `RoleConfig`, `RegistryError`, `_parse`/`_parse_role` as they exist.
- Produces: `RoleConfig.validation_retries: int | None = Field(default=None, ge=1, le=5)` — after `_parse`, an int for every role (override → default materialized); `effective_validation_retries(roles: Mapping[str, RoleConfig], role: str) -> int` in `agents/loader.py` (returns the materialized value, final fallback 1).

- [x] **Step 1: Write the failing tests** — one tmp-registry builder, then: default applied when a role omits the key; per-role override wins over the default; `defaults:` carrying an unknown key → `RegistryError`; `defaults.validation_retries` of 0 or 6 → `RegistryError`; per-role value of 0 or 6 → pydantic `ValidationError`; a `kind: harness` role (reuse the dev-role shape from an existing fixture registry) carrying the key → `RegistryError` whose message names the role and the silent-dead-config rule; `effective_validation_retries` precedence (materialized value, 1 when the mapping hand-built with `None`, e.g. the graph fixtures' dict-built registries).

```python
def test_defaults_unknown_key_rejected(tmp_path):
    _write_registry(tmp_path, defaults={"validation_retries": 1, "made_up": 2})
    with pytest.raises(RegistryError, match="made_up"):
        load_registry(tmp_path)
```

- [x] **Step 2: Run to verify failure**

Run: `pytest tests/test_registry_validation_retries.py -v`
Expected: FAIL (`RoleConfig` has no field; `defaults` unread).

- [x] **Step 3: Implement in `core/models.py` + `agents/loader.py`**

`RoleConfig` gains the field (plain `int | None` with `Field(default=None, ge=1, le=5)`; no docstring essay — one line citing FR-202). In `_parse`: after the version check, read optional `defaults`; every key other than `validation_retries` → `RegistryError`; the value must be an `int` in 1..5 else `RegistryError`; stash it. In `_parse_role`: after `cfg = RoleConfig(**data)` — if `cfg.kind == "harness"` and `cfg.validation_retries is not None` → `RegistryError` (cite the same "silent dead config" rule `_parse_role` uses for unread files); else if `cfg.validation_retries is None` → materialize the default via `cfg.model_copy(update={"validation_retries": default})` (harness roles included — the value is simply unread there). Add `effective_validation_retries` as a two-line function.

- [x] **Step 4: Run tests — new file plus the registry neighbors**

Run: `pytest tests/test_registry_validation_retries.py tests/test_registry_mirror.py tests/test_registry_ignores_fixtures.py tests/durability/test_loader_contract_edges.py -v`
Expected: PASS (registries without `defaults:` stay legal — the block is optional).

- [x] **Step 5: Ship the real `defaults:` block** — `agents/registry.yaml`:

```yaml
version: 1
defaults:
  validation_retries: 1
```

- [x] **Step 6: Commit**

```bash
git add src/sdlc/core/models.py src/sdlc/agents/loader.py agents/registry.yaml tests/test_registry_validation_retries.py
git commit -m "feat(registry): defaults.validation_retries knob, fail-closed parse (FR-202)"
```

### Task 2: `OUTPUT_RETRIES` in `agents/roles.py`

**Files:**
- Modify: `src/sdlc/agents/roles.py` (beside `STAGE_MODELS`, ~line 236)
- Test: `tests/test_stage_models.py` (the STAGE_MODELS/STAGE_ROLES keyspace home)

**Interfaces:**
- Consumes: `REGISTRY: dict[str, RoleConfig]` (Task 1's materialized field).
- Produces: `OUTPUT_RETRIES: dict[str, int]` — proposer+research roles only (`kind != "harness"`), one entry each, value = the materialized count. Every later task imports it from `sdlc.agents.roles`.

- [x] **Step 1: Write the failing test** — keyspace equals `{n for n, c in REGISTRY.items() if c.kind != "harness"}`; every value is an `int >= 1`. Structural pins only — do NOT assert the shipped registry's concrete values (Tasks 3–6 add overrides, and those pins live in their own tests).

- [x] **Step 2: Run to verify failure** — `pytest tests/test_stage_models.py -v`, FAIL (no `OUTPUT_RETRIES`).

- [x] **Step 3: Implement** — one comprehension beside `STAGE_MODELS`, same comment shape (FR-202, role-keyed like `REGISTRY`, why harness roles are absent).

- [x] **Step 4: Run** — `pytest tests/test_stage_models.py -v`, PASS.

- [x] **Step 5: Commit** — `git commit -m "feat(agents): OUTPUT_RETRIES computed from the registry (FR-202)"`

### Task 3: `_run_role` forwarding + planner cutover (together — planner must never drop to 1 at any commit)

**Files:**
- Modify: `src/sdlc/workflows/role_host.py` (`_run_role` ~175; add `OUTPUT_RETRIES` to the passed-through `from ..agents.roles import` at ~22)
- Modify: `agents/planner/agent.py` (drop `retries={"output": 3}` at :40; rewrite the comment to point at the registry value, keep the live-failure evidence verbatim)
- Modify: `agents/planner/agent.yaml` (add `validation_retries: 3`)
- Test: `tests/test_run_role_output_retries.py` (create; fake-agent host pattern from `tests/test_run_role_sub_run_harvest.py:161`)
- Test: `tests/plan/test_planner_agent_retries.py` (rewrite)

**Interfaces:**
- Consumes: `OUTPUT_RETRIES` (Task 2).
- Produces: **the forwarding idiom every later task copies** — in `_run_role`, before the `agent.run` calls:

```python
n = OUTPUT_RETRIES.get(role, 1)
if n != 1:
    kwargs.setdefault("retries", {"output": n})
```

- [x] **Step 1: Write the failing tests** — in the new file, three cases against a recording fake agent and a monkeypatched `sdlc.workflows.role_host.OUTPUT_RETRIES`: role configured 3 → `run` receives `retries={"output": 3}`; role at 1 → no `retries` key in the recorded kwargs (`test_role_at_default_forwards_nothing`); an explicit caller `retries` is not clobbered (`setdefault` semantics). In the planner file: construction default is now 1 (`agent._max_output_retries == 1`) and `OUTPUT_RETRIES["planner"] == 3` because `agents/planner/agent.yaml` carries the key.

- [x] **Step 2: Run to verify failure** — `pytest tests/test_run_role_output_retries.py tests/plan/test_planner_agent_retries.py -v`, FAIL.

- [x] **Step 3: Implement all three edits** (idiom above; planner `agent.py` cutover; `agent.yaml` key). The planner comment keeps the 2026-09 live evidence and gains one line: the 3 now lives in `agents/planner/agent.yaml` (FR-202).

- [x] **Step 4: Run the touched paths** — `pytest tests/test_run_role_output_retries.py tests/plan/ tests/test_run_role_sub_run_harvest.py -v`, PASS.

- [x] **Step 5: Commit** — `git commit -m "feat(roles): forward configured output retries at the model-egress point; planner to registry (FR-202)"`

### Task 4: Research slice cutover — all four in-slice sites

**Files:**
- Modify: `agents/research/agent.py` (drop `retries=` at :79; comment keeps the live `"Exceeded maximum output retries (1)"` evidence, points at the yaml)
- Modify: `agents/research/agent.yaml` (add `validation_retries: 3`)
- Modify: `src/sdlc/stages/research/stage.py` (three run sites: plan ~122, sub-question ~277–307, synthesis ~469)
- Modify: `src/sdlc/stages/research/toolset.py` (two run sites ~92, ~100)
- Modify: `src/sdlc/stages/research/AGENTS.md` (one line under the single-retry-layer note: output-retry forwarding is a semantic re-prompt, not a stacked infra retry)
- Test: `tests/research/test_research_agent_retries.py`, `tests/research/test_research_agent_retries_edges.py` (rewrite pins)

**Interfaces:**
- Consumes: `OUTPUT_RETRIES` via the slice's existing in-function import precedent (`from sdlc.agents.roles import REGISTRY` at `stage.py:291` — import `OUTPUT_RETRIES` the same way, at each site; `toolset.py` likewise).
- Produces: nothing other tasks use.

- [x] **Step 1: Write the failing tests** — rewrite both pinning files: construction default 1; `OUTPUT_RETRIES["research"] == 3`; each of the four sites forwards `{"output": 3}` into the slice's existing `_agent`/fake seams (sub-question seam exists at `stage.py`; plan/synthesis via their `_model`-adjacent seams; toolset via its test seam — follow `tests/research/`'s existing fakes).

- [x] **Step 2: Run to verify failure** — `pytest tests/research/test_research_agent_retries.py tests/research/test_research_agent_retries_edges.py -v`, FAIL.

- [x] **Step 3: Implement** — drop the construction kwarg, add the yaml key, apply Task 3's idiom at all five `agent.run` calls (three in `stage.py`, two in `toolset.py`; `role` is `"research"` at every site — including the architect's tool, per spec VR-3). Add the AGENTS.md line.

- [x] **Step 4: Run the slice** — `pytest tests/research/ -q`, PASS (note: plan/synthesis go 1→3 — the spec's one flagged behavior delta, VR-4).

- [x] **Step 5: Commit** — `git commit -m "feat(research): registry-driven output retries at all research run sites (FR-202)"`

### Task 5: Constitution cutover

**Files:**
- Modify: `agents/constitution/agent.py` (drop `retries=` at :49, comment → yaml, keep evidence line)
- Modify: `agents/constitution/agent.yaml` (add `validation_retries: 3`)
- Modify: `src/sdlc/stages/constitution/stage.py` (the drafter's 3 run branches — hoist a `run_kwargs` dict carrying the only-when-set `retries` entry, pass it at all three branches)
- Modify: `src/sdlc/stages/constitution/constitution.md` (reword the `retries={"output": 3}` mechanism line at :80–81 to the registry-forwarded form) and `src/sdlc/stages/constitution/AGENTS.md` (one line, as research's)
- Test: `tests/constitution/test_role.py` (rewrite the `_max_output_retries == 3` pin at :84)

- [x] **Step 1: Write the failing test** — construction default 1; `OUTPUT_RETRIES["constitution"] == 3`; the `_agent` seam's recorded kwargs carry `retries={"output": 3}`.

- [x] **Step 2: Run to verify failure** — `pytest tests/constitution/ -v`, FAIL.

- [x] **Step 3: Implement** (idiom from Task 3, `role="constitution"`).

- [x] **Step 4: Run the slice** — `pytest tests/constitution/ -q`, PASS.

- [x] **Step 5: Commit** — `git commit -m "feat(constitution): registry-driven output retries on the drafter (FR-202)"`

### Task 6: Requirements cutover

Exactly Task 5's shape for the product drafter: `agents/product/agent.py` (:52), `agents/product/agent.yaml`, `src/sdlc/stages/requirements/stage.py` (`_draft_requirements_impl`'s 3 run branches), `src/sdlc/stages/requirements/requirements.md` (:107–108) + `AGENTS.md` line, `tests/requirements/test_role.py` (:85 pin).

- [x] **Step 1: Failing test** — as Task 5, `role="product"`. Run `pytest tests/requirements/ -v` → FAIL.
- [x] **Step 2: Implement.** Run `pytest tests/requirements/ -q` → PASS.
- [x] **Step 3: Commit** — `git commit -m "feat(requirements): registry-driven output retries on the drafter (FR-202)"`

### Task 7: Assessment direct calls — discover and risk (builder-check amendment VR-3a)

**Files:**
- Modify: `src/sdlc/workflows/assessment.py` (~453 `t_discover.run(...)`, ~675 `t_risk.run(...)`; import `OUTPUT_RETRIES` beside the existing `t_discover`/`t_risk` imports under `imports_passed_through`)
- Test: `tests/test_assessment_workflow.py` (its existing fake-agent injection pattern)

**Interfaces:**
- Consumes: `OUTPUT_RETRIES`; the try/except fail-closed wrappers stay untouched — forwarding goes inside the `try`, before the call.

- [x] **Step 1: Write the failing tests** — monkeypatch `sdlc.workflows.assessment.OUTPUT_RETRIES` to `{"discover": 3, "risk": 3}` and assert each fake agent's recorded kwargs carry `retries={"output": 3}`; unpatched (shipped registry: both 1) asserts NO `retries` kwarg (`test_discover_forwards_configured_retries`, `test_risk_forwards_configured_retries`).

- [x] **Step 2: Run to verify failure** — `pytest tests/test_assessment_workflow.py -v`, FAIL.

- [x] **Step 3: Implement** — the Task 3 idiom inline at both call sites (`role="discover"` / `role="risk"`; no `_run_role` refactor, per spec VR-3a).

- [x] **Step 4: Run** — `pytest tests/test_assessment_workflow.py tests/test_assessment_workflow_e2e.py -q`, PASS.

- [x] **Step 5: Commit** — `git commit -m "feat(assessment): forward configured output retries at the discover/risk direct calls (FR-202)"`

### Task 8: Durability pin — per-call `retries` drives the output-retry loop

**Files:**
- Test: `tests/durability/test_per_call_output_retries.py` (create; follow the stub-model harness of `tests/durability/test_payload_guard.py` D5 case 7 — "each model request of an output-retry loop enters the hook exactly once")

**Interfaces:**
- Consumes: pydantic-ai `Agent` + `TemporalDurability` as wired in `tests/durability/`; per-call `run(..., retries={"output": 2})`.

- [x] **Step 1: Write the failing-then-passing pin** — a stub model whose first final output fails `output_type` validation and second passes; assert (a) a per-call `retries={"output": 2}` schedules a second model request under the durability capability, (b) the same agent called WITHOUT the override (construction default 1) raises `UnexpectedModelBehavior` on the first malformed output. If the harness needs the ephemeral dev-server, mark the test `temporal` per house style and verify with `pytest -m temporal`.

- [x] **Step 2: Run** — `pytest tests/durability/test_per_call_output_retries.py -v` (plus `-m temporal` if marked), PASS. This is Review Focus #1's pin — it must exercise the durable wrapper, not a bare in-process agent.

- [x] **Step 3: Commit** — `git commit -m "test(durability): pin per-call output retries through TemporalDurability (FR-202)"`

### Task 9: Close-out — ROADMAP, last-verified log, spec status

**Files:**
- Modify: `ROADMAP.md` (FR-202 row → `[x]` with a one-sentence close-out; refresh the Last verified cell to one sentence, 2026-11-14)
- Modify: `docs/roadmap/last-verified-log.md` (prepend the full close-out entry: what landed, the four cutover roles, discover/risk wiring, the research plan/synthesis 1→3 delta)
- Modify: `docs/superpowers/specs/2026-11-14-validation-retries-knob-design.md` (Status → implemented)

- [x] **Step 1: Full verification** — `pytest` (fast tier), `pytest -m temporal tests/durability/ tests/research/ -q` if Task 8 marked temporal, `ruff check . && ruff format --check . && mypy`. All green before the docs flip.

- [x] **Step 2: Write the three doc edits** — the roadmap row cites the spec path and the one behavior delta; the log entry carries the detail.

- [x] **Step 3: Commit** — `git commit -m "docs: FR-202 closed — configured validation retries (ROADMAP, log, spec)"`
