# One registry drives every role (ADR-6, FR-201, FR-103)

**Date:** 2026-07-16
**Roadmap:** §9.1 (supersedes `E-3` as written), §2 FR-201, FR-103, §5 US-5, §6 ADR-6
**Requirements:** ADR-6/US-5 (closes an invariant hole), FR-201 (completes), FR-103 (fixes a latent cache bug)
**Design input:** [`vercel/eve`](https://github.com/vercel/eve) — "the filesystem is the authoring interface"

## Problem

The tracker states ADR-6 is complete, US-5 is "enforced at boot", and FR-201 is done. All
three rest on `config/agents.yaml` and `validate_registry()`. Reading the call sites, the
registry governs one role, and the ADR-6 check it exists to enforce is aimed at the wrong
developer.

## Findings

Discovered by tracing call sites, in the order they were found. Each one changed the
increment; findings 4–6 arrived after the first version of this spec and rewrote it.

1. **E-3's payoff is already banked.** E-3 reads: "Wire prompt-file content into
   `content_key` (FR-103) so a prompt edit invalidates that stage's memo and no other. *This
   is the payoff item — E-1/E-2 without E-3 is filing, not capability.*" But `content_key`
   already accepts a `prompt_sha` (`memoization/cache.py:17`), and `PROMPT_SHAS`
   (`roles.py:206`) already hashes the prompt *text*. Editing `REVIEWER_PROMPT` today
   already invalidates exactly the review stage's memo. Moving that text into
   `instructions.md` hashes the same bytes. E-3 is, as written, done — so E-1/E-2 are the
   filing that E-3's own note warns against, not a route to capability.

2. **The real FR-103 gap is the model, not the prompt.** `content_key`'s other input is
   `model_id`, and `feature.py:642,692,731` pass the same `MODEL` constant for every stage.
   Harmless *only* because all proposers currently share one model. The moment any role gets
   its own model — the change FR-201 promises is configuration-only — the memo key would not
   move, and that stage would serve a cache entry computed by the **previous** model. Per-role
   models without per-role `model_id` in the key is a silent correctness bug that the
   hardcoded constant is masking.

3. **The registry's fail-closed gate can be bypassed by import order.** `roles.py:38` calls
   `load_registry()["reviewer"]` at **import** time; `validate_registry()` runs at boot
   (`worker.py:53`), *after* `worker.py:35` has imported the agents. A registry missing
   `reviewer` dies with a raw `KeyError` and never reaches the validator that exists to
   produce a deliberate error.

4. **There are two registries, and ADR-6 validates the wrong one.** `PipelineConfig.roles`
   (`models.py:448`) is a second registry, hardcoded as a `default_factory`, keyed
   `dev`/`test`/`reviewer`/`devops`. **It** selects the coding harness and model:
   `feature.py:434` does `role_cfg = cfg.roles.get(task.role, cfg.roles["dev"])` and `:519`
   records `role_cfg.model` as the author. `agents.yaml`'s `developer` entry is validated at
   boot and then **never used to run anything**.

   So `validate_registry` compares the reviewer (really used) against a `developer` entry
   (not used). Point `cfg.roles["dev"].model` at an `anthropic:` model and the real developer
   and the reviewer are the same family, while boot validation passes — it is checking a
   different developer. ADR-6's anti-collusion invariant, and US-5's "registry rejects
   same-family", hold only while two hardcoded lists happen to agree. **This is the hole the
   increment exists to close.**

   Mitigating: **nothing populates `cfg.roles` today.** `cli.py:94`,
   `benchmarks/workflow.py:71` and `feature.py:602` all take the default. The hole is latent,
   not live — cheap now, expensive once US-4's per-project role config makes `cfg.roles` vary.

5. **`PipelineConfig()` is constructed inside the workflow.** `feature.py:602` does
   `cfg = cfg or PipelineConfig()`. A `default_factory` that read `agents.yaml` would put
   file I/O inside the Temporal sandbox — the non-determinism `test_factory_purity.py`
   exists to prevent. **`cfg.roles` cannot resolve from the registry via `default_factory`.**

6. **`devops` names two different things.** `devops_agent` is a *proposer* emitting an
   `ImplementationPlan`; `cfg.roles["devops"]` is a *harness execution* role for running
   devops tasks (`DevTask.role: Literal["dev","test","devops"]`, `models.py:144`). One key,
   two animals. `dev`/`developer` is the same split under two spellings.

Two lesser items: `cfg.roles["reviewer"]` (`models.py:453`) is dead config — the reviewer
binds from `agents.yaml` at import and never reads it. And five hardcoded
`model="anthropic:glm-5.2"` literals in `feature.py`'s benchmark records (`:668`, `:706`,
`:744`, `:842`, `:1005`) record the author model independently of any registry; deleting the
`MODEL` constant would leave them silently lying.

## Scope

**In:**

- `agents.yaml` is the single registry, covering harness-execution *and* proposer roles.
- ADR-6's family check compares `reviewer` against `dev` — the model that actually codes.
- `PipelineConfig.roles`' hardcoded default is asserted at boot to mirror the registry.
- Every proposer's model resolves from the registry; the `MODEL` constant is deleted.
- `load_registry()` validates before returning; required-roles check added.
- `STAGE_MODELS` makes each stage's real model an input to its `content_key`.
- `PROMPT_SHAS` gains `qa` and `merge_verdict`; the five hardcoded record literals go.

**Out:**

- Agents-as-folders (E-1/E-2) and the eval loop (E-4). Finding 1 removes the memoization
  argument that made them urgent.
- Any change to what a prompt *says*.
- Making `cfg.roles` genuinely per-project (US-4). This increment makes the *default*
  trustworthy; per-project override is separate work that the mirror-check will constrain.
- `RoleConfig` schema changes — `kind`/`harness`/`model` already suffice.

## Design

### 1. One registry, two kinds of role, no name collisions

`config/agents.yaml` carries eleven roles. Harness-execution roles are named as
`DevTask.role` already names them (`dev`, `test`, `devops`) — that Literal is emitted by the
planner and is not ours to rename. Proposer roles are named for their agents, with
`devops_agent`'s entry called **`devops_planner`** to break finding 6's collision.

```yaml
version: 1
roles:
  # harness-execution roles — mirrored by PipelineConfig.roles (see §3)
  dev:           {kind: harness, harness: opencode, model: zai-coding-plan/glm-5.2}
  test:          {kind: harness, harness: opencode, model: zai-coding-plan/glm-5.2}
  devops:        {kind: harness, harness: opencode, model: zai-coding-plan/glm-5.2}
  # proposer roles — bound by agents/roles.py
  clarify:        {kind: proposer, model: anthropic:glm-5.2}
  architect:      {kind: proposer, model: anthropic:glm-5.2}
  planner:        {kind: proposer, model: anthropic:glm-5.2}
  qa:             {kind: proposer, model: anthropic:glm-5.2}
  reviewer:       {kind: proposer, model: anthropic:glm-5.2}
  analyst:        {kind: proposer, model: anthropic:glm-5.2}
  merge_verdict:  {kind: proposer, model: anthropic:glm-5.2}
  devops_planner: {kind: proposer, model: anthropic:glm-5.2}
```

`developer` is renamed to `dev`. A `defaults:` block was considered and rejected: it lets a
role exist implicitly, so the file stops being a complete inventory and the ADR-6 check must
reason about inherited values.

### 2. ADR-6 checks the developer that actually codes

`validate_registry()` compares `model_family(roles["reviewer"].model)` against
`model_family(roles["dev"].model)`. This is the finding-4 fix: `dev` is what
`feature.py:434` resolves for coding tasks, so the check now constrains the real pairing.

The check is otherwise unchanged and **must keep biting identically at boot**. The
harness-reviewer clause (`rev.kind == "harness" and rev.harness == dev.harness`) carries over
against `dev`.

### 3. The mirror-check — a guarded duplication

Finding 5 forbids `PipelineConfig.roles` loading from disk. So the duplication stays, and is
made fail-closed instead of silent:

- `PipelineConfig.roles`' default shrinks to `{dev, test, devops}` — the dead `reviewer`
  entry (finding 4's lesser item) is deleted.
- `validate_registry()` asserts that default equals the registry's three harness roles on
  `(kind, harness, model)`. A mismatch raises `RegistryError` naming the role and both values.

The invariant, stated for the next reader: **`agents.yaml` is authoritative; `models.py`'s
default is a purity-mandated mirror; drift fails the worker at boot.** `loader.py` already
imports from `..models` (`RoleConfig`), and `models.py` imports nothing from `loader`, so
this adds no cycle.

### 4. Loader fails closed

`load_registry()` parses then validates before returning, so no unvalidated registry escapes:

```python
def load_registry(path=None) -> dict[str, RoleConfig]:
    roles = _parse(path)  # existing parse logic, extracted
    validate_registry(roles)
    return roles
```

`validate_registry()` gains a `REQUIRED_ROLES` frozenset of all eleven names, checked
**first** so a missing role reports as itself rather than as a downstream `KeyError`. This
subsumes the existing "must define both developer and reviewer" check, which is deleted.

Finding 3 resolves as a side effect: `roles.py`'s import-time call now raises `RegistryError`.
`worker.py:53` is untouched and keeps its explicit boot gate, which
`test_worker_registry_gate.py` asserts on by source inspection.

**Consequence for tests:** `test_agents_registry.py` builds one- and two-role registries and
calls `validate_registry` on them (`:22`, `:31`, `:40`, `:45`); `test_load_registry_via_env_override`
(`:55`) writes a two-role yaml and calls `load_registry`. All now raise for the *wrong reason* —
"missing clarify" before the assertion under test. They get a `_complete_registry(**overrides)`
helper returning a valid eleven-role dict, perturbed one field at a time. Each test then
asserts one thing.

### 5. Proposers bind their own role

`REGISTRY = load_registry()` at `roles.py` top; each `Agent(...)` takes
`REGISTRY["<role>"].model`. `REVIEWER_MODEL` folds into that pattern and stops being a
special case — the point of the increment.

`MODEL` is **deleted**, not aliased. An alias would let new code keep reaching for a
fleet-wide default, which is the drift being removed.

### 6. `STAGE_MODELS` — the FR-103 fix

A `STAGE_MODELS: dict[str, str]` in `roles.py`, keyed by **stage** name exactly as
`PROMPT_SHAS` is, resolving each stage to its role's model. This is the one place the
stage-name/role-name divergence is reconciled:

| stage | role |
|---|---|
| `clarify` | `clarify` |
| `architect` | `architect` |
| `plan` | `planner` |
| `devops` | `devops_planner` |
| `review` | `reviewer` |
| `analyze` | `analyst` |
| `qa` | `qa` |
| `merge_verdict` | `merge_verdict` |

`_cached_stage` (`feature.py:293`) drops its `model_id` parameter and looks up
`STAGE_MODELS[stage]` internally, mirroring its existing `PROMPT_SHAS[stage]` lookup. One
resolution point means the two stage-keyed dicts cannot disagree about what a stage is.

`PROMPT_SHAS` gains `qa` and `merge_verdict`, spanning the same keyspace. Their absence is
latent breakage: the moment anyone memoizes the QA stage, `PROMPT_SHAS["qa"]` raises
`KeyError`.

### 7. Benchmark records stop lying

The five `model="anthropic:glm-5.2"` literals become `STAGE_MODELS[<stage>]`:
`:668` clarify, `:706` architect, `:744` plan, `:842` analyze, `:1005` merge_verdict.

`_judge` (`feature.py:229`) passes `author_model=MODEL` and its docstring at `:243` documents
this exact limitation ("proposer agents bind roles.MODEL today — foundation limitation — they
don't yet honor cfg.roles"). It cannot index `STAGE_MODELS`: its `stage` parameter is a
**rubric key** (`"clarifier"`, `"architect"`, `"planner"`), a third keyspace, as its own
docstring at `:240` warns. The three call sites (`:662`, `:699`, `:737`) pass the author
explicitly from the caller, which knows both names:

```python
_quality = await self._judge(
    cfg, reqs.model_dump_json(), "clarifier", author_model=STAGE_MODELS["clarify"]
)
```

The stale docstring paragraph goes. ADR-6 cross-family for the judge is unaffected — the
judge model still comes from `cfg.benchmark.judge_model`.

## Testing

TDD, per the repo's habit. New:

- **ADR-6 against `dev`:** a registry whose `reviewer` shares a family with `dev` is rejected;
  the finding-4 regression test. Explicitly: a registry that would have *passed* the old
  check (benign `developer`, colluding `dev`) must now fail.
- **Mirror-check:** perturbing `PipelineConfig.roles`' default away from the registry raises
  `RegistryError`; the shipped pair matches.
- `validate_registry` rejects a registry missing each required role, naming it.
- `load_registry` raises `RegistryError`, not `KeyError`, on an incomplete registry.
- Each agent binds the model its role declares, via an `SDLC_AGENTS_CONFIG` fixture registry
  (the env override at `loader.py:18` already supports this).
- `STAGE_MODELS.keys() == PROMPT_SHAS.keys()` — what keeps §6 true after we stop looking.
- **The load-bearing one:** changing one role's model in the registry changes that stage's
  `content_key` and no other stage's. The finding-2 regression test.

Existing tests needing updates: `test_agents_registry.py` (the `_complete_registry` helper,
and `developer` → `dev`), `test_reviewer_agent.py` (`reg["developer"]`),
`test_memoization_wiring.py`, `test_analyst_wiring.py` — wherever they assume the `MODEL`
constant or the old role names.

## Roadmap amendments

- **§6 ADR-6 / §5 US-5** — were `[x]` on the strength of a check aimed at an unused role.
  They become genuinely true here; the tracker gets a note that the pre-existing check was
  validating `agents.yaml`'s `developer` while `cfg.roles["dev"]` did the coding.
- **§2 FR-201** — the registry now governs all eleven roles, not one.
- **§2 FR-103** — the per-stage `model_id` fix.
- **§9.1 E-3** — rewritten. The prompt-sha half was already wired before the item was
  written; the model half was the real gap.
- **§9.1 E-1/E-2** — re-ranked. With the memoization argument gone they are a reorganisation
  justified by §7's prompts-as-assets drift and E-4's eval loop, nothing more. Still worth
  doing; no longer next.
- **§9.7 ordering** — item 2 (`E-1 → E-2 → E-3`) replaced by this increment.
- **New E-26** — make `cfg.roles` genuinely per-project (US-4) *without* reintroducing
  drift; the mirror-check is the constraint it must satisfy.
