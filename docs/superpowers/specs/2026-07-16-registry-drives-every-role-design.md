# Registry drives every role (FR-201, FR-103)

**Date:** 2026-07-16
**Roadmap:** §9.1 (supersedes `E-3` as written), §2 FR-201, FR-103
**Requirements:** FR-201 (completes), FR-103 (fixes a latent correctness bug)
**Design input:** [`vercel/eve`](https://github.com/vercel/eve) — "the filesystem is the authoring interface"

## Problem

`config/agents.yaml` is documented as the versioned agent registry, and its header comment
claims "editing a model here is a per-project configuration change, not a code change
(US-4/US-5)". That is true for exactly one role.

`roles.py:35` defines `MODEL = "anthropic:glm-5.2"` as a module constant. Six of the eight
agents (`clarify`, `architect`, `planner`, `qa`, `analyst`, `merge_verdict`, `devops`) bind
that constant directly. Only `reviewer` reads the registry, via
`REVIEWER_MODEL = load_registry()["reviewer"].model` (`roles.py:38`) — and only because
ADR-6's family-inequality check forced the issue. The registry defines an `analyst` role
that `analyst_agent` ignores entirely.

So FR-201 is checked `[x]` in the tracker on the strength of a file that governs one of
nine roles.

## Findings that changed the task as written

Three facts from the code contradict §9.1's framing of E-1/E-2/E-3. The roadmap is amended
as part of this work (see Roadmap amendments).

1. **E-3's payoff is already banked.** E-3 reads: "Wire prompt-file content into
   `content_key` (FR-103) so a prompt edit invalidates that stage's memo and no other. *This
   is the payoff item — E-1/E-2 without E-3 is filing, not capability.*" But `content_key`
   already accepts a `prompt_sha` (`memoization/cache.py:17`), and `PROMPT_SHAS`
   (`roles.py:206`) already hashes the prompt *text*. Editing `REVIEWER_PROMPT` today
   already invalidates exactly the review stage's memo. Moving that text from a Python
   literal into `instructions.md` hashes the same bytes. E-3 is, as written, done — which
   means E-1/E-2 are the filing that E-3's note warns against, not a route to capability.

2. **The real FR-103 gap is the model, not the prompt.** `content_key`'s other input is
   `model_id`, and `feature.py:642,692,731` pass the same `MODEL` constant for every stage.
   This is harmless *only* because all six proposers currently share one model. The moment
   `agents.yaml` gives `architect` a different model — the exact change FR-201 promises is
   configuration-only — the memo key would not move, and the architect stage would serve a
   cache entry computed by the **previous** model. Per-role models without per-role
   `model_id` in the key is a silent correctness bug that the hardcoded constant is
   currently masking. FR-103's memoization invariant and FR-201's registry are the same
   work; that is why this increment does both or neither.

3. **The registry's fail-closed gate can be bypassed by import order.** `roles.py:38` calls
   `load_registry()["reviewer"]` at **import** time; `validate_registry()` runs at worker
   boot (`worker.py:53`), *after* `worker.py:35` has already imported the agents. A registry
   missing its `reviewer` role therefore dies with a raw `KeyError: 'reviewer'` at import
   and never reaches the validator that exists to produce a deliberate error. The ADR-6
   family check survives only because comparing two families requires both roles to exist.
   Pulling nine roles at import multiplies the ways to trip this.

## Scope

**In:**

- Every agent's model resolves from `config/agents.yaml`; the `MODEL` constant is deleted.
- `load_registry()` validates before returning; `validate_registry()` gains a required-roles
  check.
- `STAGE_MODELS` makes each stage's real model an input to its `content_key`.
- `PROMPT_SHAS` gains its missing `qa` and `merge_verdict` entries.

**Out:**

- Agents-as-folders (E-1/E-2) — where prompt text *lives* is a separate call, and finding 1
  removes the memoization argument that made it urgent.
- The prompt eval loop (E-4).
- Any change to what a prompt *says*.
- `RoleConfig` schema changes — `kind`/`harness`/`model` already suffice.

## Design

### 1. Registry shape — nine explicit roles, no defaults

`config/agents.yaml` gets one entry per agent. A `defaults:` block was considered and
rejected: it lets a role exist implicitly, which stops the file being a complete inventory
of the fleet and forces the ADR-6 check to reason about inherited values.

```yaml
version: 1
roles:
  clarify:       {kind: proposer, model: anthropic:glm-5.2}
  architect:     {kind: proposer, model: anthropic:glm-5.2}
  planner:       {kind: proposer, model: anthropic:glm-5.2}
  qa:            {kind: proposer, model: anthropic:glm-5.2}
  reviewer:      {kind: proposer, model: anthropic:glm-5.2}
  analyst:       {kind: proposer, model: anthropic:glm-5.2}
  merge_verdict: {kind: proposer, model: anthropic:glm-5.2}
  devops:        {kind: proposer, model: anthropic:glm-5.2}
  developer:     {kind: harness, harness: opencode, model: zai-coding-plan/glm-5.2}
```

Role names match the **agent** names in `roles.py`, not the stage names in `feature.py`.
Those two already diverge (`planner`/`plan`, `reviewer`/`review`, `analyst`/`analyze`), and
the registry describes agents. Introducing a third naming scheme to reconcile them is not
worth it; §3 handles the mapping in one place.

### 2. Loader fails closed

`load_registry()` parses and then calls `validate_registry()` before returning, so no
unvalidated registry escapes the module:

```python
def load_registry(path=None) -> dict[str, RoleConfig]:
    roles = _parse(path)      # existing parse logic, extracted
    validate_registry(roles)
    return roles
```

`validate_registry()` gains a `REQUIRED_ROLES` frozenset of all nine names; a missing role
raises `RegistryError` naming it. The existing ADR-6 family-inequality check and the
harness-reviewer clause are **unchanged and must keep biting identically at boot** — this
increment is additive to them.

Finding 3 resolves as a side effect: `roles.py`'s import-time call now raises the real
`RegistryError`. `worker.py:53` is untouched and keeps its explicit boot gate, which
`test_worker_registry_gate.py` asserts on by source inspection.

**Consequence for tests:** `test_agents_registry.py:40` and friends call `validate_registry`
on hand-built one- and two-role registries. With a required-roles check those now raise for
the *wrong reason* — "missing clarify" before reaching the ADR-6 assertion under test. They
get a `_complete_registry(**overrides)` helper that builds a valid nine-role registry and
perturbs the one field being tested. Each test then asserts one thing.

### 3. `roles.py` binds each agent to its own role

`REGISTRY = load_registry()` at module top; each `Agent(...)` takes
`REGISTRY["<role>"].model`. `REVIEWER_MODEL` folds into that pattern and stops being a
special case — that is the point of the increment.

`MODEL` is **deleted**, not aliased. Keeping a deprecated alias would let new code keep
reaching for a fleet-wide default, which is precisely the drift being removed. Its importers
(`feature.py:26` and three memo call sites, plus the judge — see §5) move with it.

### 4. `STAGE_MODELS` — the FR-103 fix

A `STAGE_MODELS: dict[str, str]` in `roles.py`, keyed by **stage** name exactly as
`PROMPT_SHAS` already is, resolving each stage to its role's model. This is the single place
the agent-name/stage-name divergence from §1 is reconciled.

`_cached_stage` (`feature.py:293`) drops its `model_id` parameter and looks up
`STAGE_MODELS[stage]` internally, mirroring its existing `PROMPT_SHAS[stage]` lookup. One
resolution point means the two stage-keyed dicts cannot disagree about what a stage is.

`PROMPT_SHAS` gains `qa` and `merge_verdict` entries, so both dicts span the same keyspace.
Their absence is latent breakage today: the moment anyone memoizes the QA stage,
`PROMPT_SHAS["qa"]` raises `KeyError`.

### 5. The benchmark judge

`_judge` (`feature.py:229`) passes `author_model=MODEL`, and its docstring at `:243`
documents this exact limitation ("proposer agents bind roles.MODEL today — foundation
limitation — they don't yet honor cfg.roles").

It cannot simply index `STAGE_MODELS`: its `stage` parameter is a **rubric key**
(`"clarifier"`, `"architect"`, `"planner"`), a third keyspace, as its own docstring at `:240`
warns. The three call sites (`:662`, `:699`, `:737`) instead pass the author explicitly from
the caller, which knows both names:

```python
_quality = await self._judge(cfg, reqs.model_dump_json(), "clarifier",
                             author_model=STAGE_MODELS["clarify"])
```

The stale docstring paragraph goes. ADR-6 cross-family for the judge is unaffected: the
judge model still comes from `cfg.benchmark.judge_model`.

## Testing

TDD, per the repo's habit. New:

- `validate_registry` rejects a registry missing each required role, naming it.
- `load_registry` raises `RegistryError` (not `KeyError`) on an incomplete registry.
- Each agent binds the model its registry role declares, via an `SDLC_AGENTS_CONFIG` fixture
  registry (the env override at `loader.py:18` already supports this).
- `STAGE_MODELS.keys() == PROMPT_SHAS.keys()` — what keeps §4 true after we stop looking.
- **The load-bearing one:** changing one role's model in the registry changes that stage's
  `content_key` and no other stage's. This is the regression test for finding 2.

Existing tests needing updates: `test_agents_registry.py` (the `_complete_registry` helper),
`test_memoization_wiring.py`, `test_analyst_wiring.py`, `test_reviewer_agent.py` — wherever
they assume the `MODEL` constant.

## Roadmap amendments

- **§9.1 E-3** — rewritten. The prompt-sha half was already wired before the item was
  written; the model half was the real gap and is what this increment closes. E-3's note
  that "E-1/E-2 without E-3 is filing" stands, but now argues *against* E-1/E-2 rather than
  for them.
- **§9.1 E-1/E-2** — re-ranked. With the memoization argument gone, they are a reorganisation
  justified by §7's prompts-as-assets drift and by E-4's eval loop, nothing more. Still worth
  doing; no longer next.
- **§9.7 ordering** — item 2 (`E-1 → E-2 → E-3`) replaced by this increment.
- **§2 FR-201** — note that the registry now governs all nine roles, not one.
- **§2 FR-103** — note the per-stage `model_id` fix.
