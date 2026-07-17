# Agents as folders (E-1, E-2)

**Date:** 2026-07-17
**Roadmap:** §9.1 `E-1`, `E-2` (unblocks `E-4`), §7 "prompts as versioned assets"
**Requirements:** No FR moves. A strict refactor: §7 drift closure, plus the seam the research role needs.
**Builds on:** `2026-07-16-registry-drives-every-role-design.md` — **shipped** (`022d524`…`c33c42e`).
That spec is history; this is the next increment, not an amendment to it.
**Blocks:** `2026-07-17-research-agent-grounded-briefs-design.md`
**Design input:** [`vercel/eve`](https://github.com/vercel/eve) — "the filesystem is the authoring interface"

## Problem

A role's definition is split three ways. `config/agents.yaml` carries `kind`/`harness`/`model`;
prompts are inline Python constants in `agents/roles.py`; the `Agent(...)` construction — `name`,
`output_type` — is eight more literals in the same file. §7 has recorded the prompt half as known
drift since it was written.

That split is tolerable for eleven roles that are each a prompt and a model. It stops being tolerable
when a role arrives that is not — and one is arriving.

## Findings

1. **The memoization argument for E-1/E-2 is dead and must stay dead.** The registry spec's finding 1
   established that `content_key` already takes a `prompt_sha` and `PROMPT_SHAS` already hashes the
   prompt *text*, so editing `REVIEWER_PROMPT` already invalidates exactly the review stage's memo.
   Moving that text into `instructions.md` hashes the same bytes. **This increment claims no
   memoization capability.** A future reader tempted to justify it on cache grounds should stop: that
   reasoning was checked and found wrong.

2. **The live argument is a role a folder *describes* rather than decorates.** The research role
   holds instructions, four tools, a provider choice, a fake corpus and a budget. For that role a
   directory is the honest shape. Finding 1 does not speak to it — finding 1 reasoned about prompts,
   and the case did not exist when it was written.

3. **Without this increment, research reopens the hole the registry spec just closed.** The
   alternative is `agents/research/` beside eleven YAML entries: **two registries**, a different
   flavour of the registry spec's finding 4, in the codebase whose last five commits existed to
   eliminate it. A directory that is the registry for one role and a YAML that is the registry for
   eleven is neither.

4. **The landed registry is preserved, not redesigned.** `loader.py` at HEAD has `HARNESS_ROLES`,
   `PROPOSER_ROLES`, `REQUIRED_ROLES`, `load_registry()` parsing *and* validating so nothing
   unvalidated escapes, ADR-6 aimed at `dev`, and `_validate_pipeline_mirror`. Every one survives
   unchanged in effect.

5. **An optional role must still be a known one.** Research is optional — `research_enabled` defaults
   `False` — but a fail-closed unknown-directory check would reject `agents/research/`.
   `REQUIRED_ROLES` cannot be the whole answer, and the research spec must not have to *weaken* a
   fail-closed check to extend it.

6. **`PROMPT_SHAS` values must not move.** A migration, not a prompt edit. Every hash is over the same
   bytes before and after. If a value changes, a prompt changed during a move that promised not to
   touch it. Only a test pinning the hashes catches that.

7. **Agent *names* are Temporal activity names, and the role name is not the agent name.**
   `roles.py`'s module docstring: *"agent names and toolset ids become Temporal activity names. Set
   them explicitly and never rename after deploying to production."* Two roles already break the
   obvious mapping — role `qa` builds `qa_analyst_agent`, and role `devops_planner` builds
   `devops_agent` (the collision the registry spec's finding 6 renamed the *role* to break, leaving
   the *agent* name alone). Distributing construction across eleven files puts that invariant in
   eleven places. It is the main risk this increment takes on, and it is why §5 pins the names in a
   test rather than trusting the move.

8. **Dynamic imports must not run before validation.** The registry spec's finding 3 was that
   `roles.py` calls `load_registry()` at *import* time, ahead of `worker.py`'s boot validator, so a
   bad registry died with a raw `KeyError`. `load_registry` now validates before returning, which
   closed it. Importing eleven `agent.py` modules re-opens the same shape unless the ordering is
   explicit: **validate the entire registry, then import.** Stated as a design rule below because it
   is the one thing about `agent.py` that is easy to get wrong and expensive to notice.

9. **The containerized worker cannot boot today, and an editable install is why nobody noticed.**
   `Dockerfile` copies only `pyproject.toml` and `src` — **`config/` is never copied.**
   `docker-compose.yml` mounts no repo (only the `worker-worktrees` and `worker-repos` volumes), and
   `SDLC_AGENTS_CONFIG` is set in neither `.env` nor `.env.example`. So `DEFAULT_AGENTS_CONFIG` —
   `Path(__file__).resolve().parents[3] / "config" / "agents.yaml"` — resolves to
   `/usr/local/lib/python3.13/config/agents.yaml` in the image, which does not exist. `roles.py` calls
   `load_registry()` at module scope and `worker.py` imports `roles`, so `python -m sdlc.worker` dies
   with `FileNotFoundError` before Temporal is reached.

   Locally, `env/Lib/site-packages/__editable__.ai_sdlc_temporal-0.1.0.pth` makes `sdlc` resolve to
   `src/sdlc`, so `parents[3]` lands on the repo root and the file is there. **`parents[3]` is a lie
   the editable install told us**, and the 353 passing tests say nothing about the image.

   **Pre-existing** — it arrived with FR-201's registry, not with the registry increment. In scope
   here because this increment moves the registry and would otherwise carry the bug forward unchanged,
   and because it gets worse in kind: `agent.py` is *code that must be imported*, living outside
   `src/`, so a missing `COPY` becomes an `ImportError` at boot rather than a stale config.

## Scope

**In:**

- `agents/<role>/` replaces `config/agents.yaml` as the registry. The directory name is the role name.
- Each role directory carries `agent.yaml`; proposer roles also carry `instructions.md` and `agent.py`.
- `agent.py` constructs the role's `Agent` — eve's `agent.ts`, in Python.
- `RoleConfig` gains `instructions: str | None`.
- `load_registry()` walks a directory.
- **Resolution stops trusting `__file__`** (finding 9): `SDLC_AGENTS_DIR` replaces
  `SDLC_AGENTS_CONFIG`, `Dockerfile` ships `agents/`, and a test proves a non-editable install finds
  the registry.
- `KNOWN_ROLES = REQUIRED_ROLES | OPTIONAL_ROLES`; `OPTIONAL_ROLES` is empty here (finding 5).
- `config/agents.yaml` is deleted.

**Out:**

- `tools/` discovery. No role has tools until research does; that clause belongs to the research spec.
- `kind: research`, `RoleConfig.provider`, anything research-shaped.
- Any change to what a prompt *says* (finding 6), or to any agent `name` (finding 7).
- Any change to ADR-6, the mirror-check, `STAGE_MODELS`, `PROMPT_SHAS`' keyspace, `content_key`, or
  the module-level names `feature.py`/`worker.py` import (`clarify_agent`, `t_clarify`,
  `ALL_TEMPORAL_AGENTS`, …). All shipped; all preserved.
- The eval loop (E-4). Unblocked by this, not delivered by it.

## Design

### 1. The directory is the role

```
agents/
  registry.yaml              # {version: 1} — nothing else; a version inside one
                             # role's file would be eleven versions

  # harness-execution roles — mirrored by PipelineConfig.roles.
  # No instructions.md, no agent.py: a harness role runs a CLI. There is no
  # pydantic-ai Agent to construct and no prompt of ours to carry.
  dev/agent.yaml             # {kind: harness, harness: opencode, model: zai-coding-plan/glm-5.2}
  test/agent.yaml
  devops/agent.yaml          # RUNS devops tasks; see devops_planner

  # proposer roles
  clarify/       {agent.yaml, instructions.md, agent.py}
  architect/     {agent.yaml, instructions.md, agent.py}
  planner/       {agent.yaml, instructions.md, agent.py}
  qa/            {agent.yaml, instructions.md, agent.py}   # builds qa_analyst_agent
  reviewer/      {agent.yaml, instructions.md, agent.py}
  analyst/       {agent.yaml, instructions.md, agent.py}
  merge_verdict/ {agent.yaml, instructions.md, agent.py}
  devops_planner/{agent.yaml, instructions.md, agent.py}   # builds devops_agent
```

`agent.yaml` carries what the role's YAML block carries today, minus its name — the directory
supplies that. `config/agents.yaml` is **deleted**, not kept as a fallback: a fallback is finding 3's
two registries wearing a compatibility shim.

**Naming hazard, recorded:** the registry root is `agents/` and the code package is
`src/sdlc/agents/`. They are different things one word apart. Modules load by file path (§3), never
by package name, so the two never resolve against each other — but the next reader deserves the
warning.

### 1a. How `agents/` reaches the worker (finding 9)

`DEFAULT_AGENTS_CONFIG` and its `parents[3]` walk are **deleted**, not repointed at `agents/`.
Repointing preserves the bug: the path is computed from where the *code* is installed, which under a
non-editable install has no relationship to where the *registry* is.

Resolution order becomes explicit, with no `__file__` in it:

1. **Explicit argument** — `load_registry(path)`. What tests use.
2. **`$SDLC_AGENTS_DIR`** — what production uses. Set to `/app/agents` in the image.
3. **Repo-root discovery** — walk up from `Path.cwd()` for a directory containing **both**
   `pyproject.toml` and `agents/registry.yaml`. Dev-and-tests convenience only. Looking for two
   specific markers, rather than counting `..` a fixed number of times, is what makes this honest: it
   either finds a real registry or it does not.
4. Otherwise `RegistryError` naming all three mechanisms. Never a bare `FileNotFoundError`.

**`SDLC_AGENTS_CONFIG` is renamed to `SDLC_AGENTS_DIR`, and the old name becomes a boot error.** The
value's *meaning* changes from a file to a directory, so silently accepting the old name would let a
stale `SDLC_AGENTS_CONFIG=/path/agents.yaml` resolve to a file where a directory is expected and fail
somewhere less obvious. A rename plus an explicit "this was renamed to `SDLC_AGENTS_DIR`" error is
fail-closed and tells the operator what to do.

The image ships the registry:

```dockerfile
COPY pyproject.toml ./
COPY src ./src
COPY agents ./agents           # NEW — without this the worker cannot boot
RUN pip install --no-cache-dir .
ENV SDLC_AGENTS_DIR=/app/agents  # NEW — never rely on cwd for this
```

Setting `SDLC_AGENTS_DIR` explicitly rather than leaning on mechanism 3 matters: `WORKDIR /app` makes
cwd-discovery *appear* to work, so the two mechanisms would mask each other and the first `docker run`
with a different working directory would fail in production instead of in CI.

`agents/` must not be in `.dockerignore`. It currently is not; the test in §Testing is what keeps that
true.

### 2. The `agent.py` contract

Each proposer folder exposes exactly one callable:

```python
# agents/clarify/agent.py
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from sdlc.models import ClarifiedRequirements


def build(model: str, instructions: str, model_settings: ModelSettings) -> Agent:
    return Agent(
        model,
        name="clarify_agent",          # Temporal activity name — NEVER rename (finding 7)
        output_type=ClarifiedRequirements,
        model_settings=model_settings,
        system_prompt=instructions,
    )
```

**`agent.py` declares the role's shape; the loader supplies its configuration.** `name` and
`output_type` are code — a Temporal activity identity and a typed contract `feature.py` imports.
`model` and `instructions` are assets, and they arrive as arguments rather than being read from disk
by the module. The rule this follows, and the one to apply to anything added later: *assets are what
you edit to change behaviour; code is what makes them work.* An `agent.py` that opens a file has
crossed the line.

`model_settings` is passed in so `MODEL_SETTINGS` stays one shared object honouring
`SDLC_MODEL_MAX_TOKENS` — eleven copies of that env read is precisely the drift being removed.

### 3. Validate everything, then import anything

Finding 8 is a rule, not a note:

```python
def load_registry(path=None) -> dict[str, RoleConfig]:
    roles = _parse(path)          # walk dirs; read agent.yaml + instructions.md
    validate_registry(roles)      # UNCHANGED — same dict, same checks, same order
    return roles                  # no agent.py has been imported yet


def build_agents(roles) -> dict[str, Agent]:
    """Called by roles.py AFTER load_registry has returned."""
```

`validate_registry` is not re-implemented — it is re-fed. It receives the same
`dict[str, RoleConfig]` it receives today and cannot tell the medium changed. `REQUIRED_ROLES` first,
then ADR-6 against `dev`, then the harness-reviewer clause, then `_validate_pipeline_mirror`. **An
ADR-6-violating registry therefore fails before a single `agent.py` is imported**, which is finding 3
staying closed rather than being reopened by the new mechanism.

Modules load by file path via `importlib.util.spec_from_file_location`, under a private module name
(`_sdlc_agent_<role>`), so no `agents/` package is created and no name resolves against
`src/sdlc/agents/`.

Structural errors, all `RegistryError`, raised during the walk:

| Condition | Why |
|---|---|
| Directory not in `KNOWN_ROLES` | The filename is the API; an unknown name is a typo, not an extension point |
| Proposer role missing `instructions.md` or `agent.py` | Same class as a missing role |
| Harness directory carrying either | It would never be read — silent dead config |
| `agent.yaml` naming a role other than its directory | A filename disagreeing with its contents |
| `instructions.md` empty or whitespace-only | An empty system prompt is a boot bug, not a runtime surprise |
| `agent.py` with no `build`, or `build` with the wrong signature | Fail at boot, naming the file |
| Two roles building agents with the same `name` | Colliding Temporal activity names (finding 7) |

### 4. What `roles.py` keeps

`roles.py` shrinks to wiring and stops being where roles are defined:

```python
REGISTRY = load_registry()
AGENTS   = build_agents(REGISTRY)

clarify_agent   = AGENTS["clarify"]          # module-level names preserved verbatim:
architect_agent = AGENTS["architect"]        # feature.py and worker.py do not change
qa_analyst_agent = AGENTS["qa"]              # role 'qa'            -> qa_analyst_agent
devops_agent     = AGENTS["devops_planner"]  # role 'devops_planner' -> devops_agent
...
t_clarify = TemporalAgent(clarify_agent, activity_config=AGENT_ACTIVITY_CONFIG)
```

The eight prompt constants and the eight `Agent(...)` literals are deleted. `STAGE_MODELS`,
`PROMPT_SHAS`, `MODEL_SETTINGS`, `ALL_TEMPORAL_AGENTS` and every `t_*` stay exactly as they are.
`PROMPT_SHAS[<stage>]` hashes `RoleConfig.instructions`.

Finding 6 is the constraint on the prompt move: the constants are implicitly-concatenated Python
string literals, so the migration is mechanical and the **trailing newline is the whole risk** —
`instructions.md` is written with no trailing newline, or the hashes move.

## Testing

TDD, per the repo's habit. Three tests carry this increment; each exists because the medium changed
under an invariant that must not.

0. **A non-editable install finds the registry** (finding 9) — the test that would have caught a live
   bug and did not exist. `pip install .` (not `-e`) into a tmp venv, then run
   `python -c "from sdlc.agents.loader import load_registry; load_registry()"` from a directory that
   is **not** the repo root, with `SDLC_AGENTS_DIR` pointed at the repo's `agents/`. It must succeed.
   Then unset `SDLC_AGENTS_DIR` and assert it raises `RegistryError` naming all three mechanisms —
   never `FileNotFoundError`.

   Marked `@pytest.mark.slow` (it builds a venv). If that proves too slow for the default suite, the
   fallback is asserting `Dockerfile` contains `COPY agents ./agents` and `ENV SDLC_AGENTS_DIR` by
   source inspection — the same technique `test_worker_registry_gate.py` already uses. **Weaker, and
   worth saying why:** source inspection proves the line exists, not that the import works. Prefer the
   venv test; take the inspection only with evidence the venv test is unworkable in CI.

1. **Every `PROMPT_SHAS` value equals its pre-migration hash**, pinned as literals computed from
   `roles.py` at HEAD *before* the constants are deleted. Catches a prompt "improving" during a move
   that promised not to touch it (finding 6). Nothing else would.
2. **Every agent `name` equals its pre-migration name**, pinned as a literal
   `{role: agent_name}` map including the two that break the obvious mapping (`qa` →
   `qa_analyst_agent`, `devops_planner` → `devops_agent`). A renamed agent is a renamed Temporal
   activity, which is a production break that no other test in the suite would surface (finding 7).

Also:

- Each structural error in §3's table, one assertion each, naming the offending directory — including
  the duplicate-`name` case, which is only reachable now that construction is distributed.
- **ADR-6 still bites through the new loader:** a tmp tree whose `reviewer` shares a family with `dev`
  fails. The registry spec's regression test, re-run against directories — this is what proves
  "strict refactor" is true rather than aspirational.
- **Validation precedes import (finding 8):** an ADR-6-violating tree whose `agent.py` files would
  raise on import fails with `RegistryError`, not the import error. Asserts the *ordering*, not just
  the outcome.
- `_validate_pipeline_mirror` still fires on drift.
- `SDLC_AGENTS_DIR` pointing at a tmp *directory* overrides the shipped registry; the old
  `SDLC_AGENTS_CONFIG`, if set, raises `RegistryError` naming the new variable rather than being
  ignored.
  `_complete_registry` becomes `_complete_registry_dir(tmp_path, **overrides)`, writing a tmp tree.
- `test_factory_purity.py` stays green: `feature.py` imports `roles` inside
  `workflow.unsafe.imports_passed_through()`, and the dynamic imports run under it. If purity breaks,
  the increment is wrong and the fallback is building agents at worker boot rather than at
  `roles.py` import — decide that on evidence, not in advance.

`validate_registry` is untouched, so its own tests are untouched. If a test that exercises
`validate_registry` on a dict needs editing, the refactor has leaked and that is a design bug, not a
test-maintenance chore. `test_worker_registry_gate.py` inspects `worker.py` by source; `worker.py:53`
is not touched.

## Roadmap amendments

- **§9.1 E-1, E-2** — `[x]` when this lands. The tracker records the revival reason: **not** the
  memoization argument finding 1 killed, but the research role being the first role a folder describes
  rather than decorates.
- **§9.1 E-3** — already rewritten by the registry spec; unaffected.
- **§9.1 E-4** — its "Blocked on E-2" note goes. Still unscheduled.
- **§7 "prompts as versioned assets"** — the first clause closes; "with an eval loop" stays open on E-4.
- **§9.7 ordering** — item 2's `E-1 → E-2` become this increment; `E-3` was subsumed by the registry
  spec.
