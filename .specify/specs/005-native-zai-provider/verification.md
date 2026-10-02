# Verification: 005-native-zai-provider

## T021 flip triage (R7 manifest vs actual)

Full default tier on the flipped registry (post-T020): **1 failed,
5464 passed, 11 skipped, 245 deselected**. Every red classified:

| Red test | Disposition | Action |
|---|---|---|
| `tests/test_eval_fixture_build.py::test_fixture_carries_the_role_registry_model` | **FLIP** — predicted by R7 ("if they resolve from the real registry — confirm by running"); it does | assertion updated to `zai:glm-5.3` with a dated comment |

Actual vs predicted: R7's FLIP row listed `tests/test_agents_registry.py:117`
(handled by the T019 rewrite, not by triage), the wire fixture (below), and
this eval-fixture case as "possibly". The other "possibly" —
`tests/test_benchmark_arms.py` — stayed green (its arms pin role/model pairs
per arm, not the shipped proposer default). No EXTEND-class red appeared in
the default tier; the manifest's EXTEND rows are additions (T026), not
failures. Post-fix file run: 8 passed RC=0.

## T021 wire fixture regeneration (FR-012, SG-3)

`SDLSC_WIRE_REGEN=1 pytest -m temporal tests/durability/test_wire_neutrality.py`
on the flipped registry: RC=0, 1 passed. Fixture diff
(`tests/durability/fixtures/wire_no_override.json`): 6 insertions / 6
deletions — exactly the six `model_id` values
`anthropic:glm-5.2` → `zai:glm-5.3` on activities
`agent__{clarify,architect,planner,qa_analyst,reviewer,analyst}_agent__model_request`.
Activity names, order, scheduling and every other field byte-identical.
**SG-3 clear.** Frozen-mode rerun after regen: RC=0, 1 passed (live run
equals the regenerated fixture).

## T025 temporal tier on the flipped registry

Per-file driver (45 files, `timeout 300` each, one pytest per file):
**181 passed, 20 skipped, 1 xfailed, 2 failed, 0 timeout-kills.**
T002 baseline was 179/20/1 (+1 pre-existing failure); the +2 passed are
T023's durable-path wire tests.

| Item | Result | Verdict |
|---|---|---|
| first-workflow-task timing (replica of T003's measurement, flipped registry, zai warm-up live) | **0.123s** (baseline 0.128s), no TMPRL1101 | **SG-4 clear** |
| `tests/durability/test_inflight_resume.py` | green (driver RC=0) | SG-2 evidence |
| replay tier (`tests/replay/*`) | all green except the ONE pre-existing base failure below | SG-2 evidence |
| `tests/replay/test_graph_golden.py[budget_arch_reject-sandboxed]` | 1 failed — **pre-existing on base 2196438** (baseline.md; reproduced 3/3 incl. kroker-baseline; failure mode identical on base) | recorded, not a 005 regression |
| `tests/durability/test_single_retry_layer.py` | was 4 failed (tests stubbed `ANTHROPIC_BASE_URL`; the registry model is now `zai:glm-5.3`, so the dummy-keyed call reached the real endpoint and got 401) — **FLIP**: stub switched to `ZAI_BASE_URL` (the route-policy override), docstring dated | fixed; 5 passed RC=0 |
| `tests/durability/test_priced_usage_parity.py` | 1 failed — see the SG-2 escalation below | **escalated** |

### SG-2 escalation: `test_live_priced_usage_matches_the_frozen_recording`

The test runs `greenfield_happy` LIVE and compares `price_usage` activity
inputs against the frozen recording `tests/replay/histories/greenfield_happy.json`
(captured pre-005). The live run schedules identical activity inputs
token-for-token (114/54/0/0); the ONLY difference is the model label:
`zai:glm-5.3` vs the recorded `anthropic:glm-5.2` — the deliberate 005
registry change. This is a golden-recording test red on the flipped
registry, i.e. SG-2's letter. Diagnosis: not a replay/in-flight failure
(the replay tier and `test_inflight_resume` are green); the recording is
captured history (standing rule: not edited; the one sanctioned regen was
the wire fixture in T021), and no task in tasks.md rules on this file —
R7's manifest missed it. Options for the orchestrator: (a) sanction a
one-time re-capture of `greenfield_happy.json` on the flipped registry
(analogous to the T021 wire regen); (b) re-scope the parity test to
compare per-role spend with the model label mapped across the 005 break
marker; (c) retire/replace the recording with a post-005 capture policy.
**RESOLVED — orchestrator ruling 2026-10-02: option (b), label-mapped
comparison.** The recording stays untouched (it anchors PRE-005 history;
003's SC-006a depends on that anchor). The test gained a dated
`_RECORDED_MODEL_MAP` (`anthropic:glm-5.2` → `zai:glm-5.3`, plus the bare
`glm-5.2` → `glm-5.3` — the recording's research sub-question price entry
carries the bare grammar; verified by decoding the frozen payload labels:
five prefixed + one bare) applied to the RECORDED side only; token parity
per role in order is still asserted exactly. The docstring states the
post-005 parity scope and that a future route change must extend the
mapping deliberately, never silently. Test-only edit; green: 1 passed RC=0.

## T030 live confirmation (FR-015, SC-007; quickstart step 6)

One clarify stage (real role build via `agents/clarify`, fixture prompt
`add-login-greenfield`, `MODEL_SETTINGS`) on the flipped registry in
`kroker-dev`, real `ZAI_API_KEY` via `docker exec -e`, **no `ZAI_BASE_URL`,
no override**. Two runs (the second only to read the response's reported
model name); scripts outside the repo in the container's /logs.

| Evidence | Value |
|---|---|
| Result | RC=0, one HTTP request per stage |
| Endpoint | `https://api.z.ai/api/coding/paas/v4/` (the client's base URL — the coding endpoint) |
| Model name the endpoint reported | **`glm-5.3`** (asked `zai:glm-5.3`, answered by glm-5.3) |
| Artifact | schema-validated `ClarifiedRequirements` (all fields present: summary, functional/non_functional_requirements, dimensions_probed, open_questions, out_of_scope, dropped, spec_ref; 10,077 bytes serialized) |
| Usage | 899 input / 5,124 output tokens (2,849 reasoning — thinking active), cost $0.0238, requests=1 |

SG-6 never fired: the key was present and the call succeeded for an
account reason never arose.

## T031 static gates (each its own command, in kroker-dev)

| Gate | Result |
|---|---|
| `ruff check .` | RC=0, all checks passed |
| `ruff format --check .` | RC=0, 1551 files already formatted |
| `mypy` | RC=0, no issues in 378 source files |
| `python scripts/check_file_size.py` | RC=0 |
| `git diff --stat 0f4ac11 -- pyproject.toml uv.lock src/sdlc/stages/code/step.py src/sdlc/harness/base.py agents/dev agents/test agents/devops` | **empty** (0 lines) — FR-010, FR-014, no dependency change, no harness-role edit |

## T032 close-out

### Requirement-by-requirement evidence (plan "Requirement coverage")

| Requirement | Evidence |
|---|---|
| FR-001, FR-002, FR-003 | `test_shipped_registry_models_are_the_005_targets` (11 roles = `zai:glm-5.3`, harness trio + claude roles unchanged, `validate_registry` passes); commit 352cc8e is exactly the 11-line diff; T031 forbidden-path diff empty |
| FR-004 | `.env.example` z.ai native block + Anthropic re-description (6ed6b77); README key list + E2 warning (1ed9c02) |
| FR-005 | doctor cases absent/placeholder/set/both-keys (T015, 2f5facf) green over the `zai` `_FAMILY_KEYS` entry (3d354d0) |
| FR-006 | T023 durable always-429 == `AGENT_ACTIVITY_MAX_ATTEMPTS`; T006/T008 retry-split pin |
| FR-007 | T025 timing 0.123s vs 0.128s baseline, no TMPRL1101; T024 zai warm-up |
| FR-008 | T027 price pins (1.400/4.400 native; 1.103/3.862 fallback) |
| FR-009 | T028 BENCHMARK.md break marker |
| FR-010, FR-014 | T031: forbidden-path diff vs 0f4ac11 empty |
| FR-011 | T021 triage table (1 predicted FLIP, fixed); default tier green with dummy keys (T014: 5460/11/245) |
| FR-012 | T021 fixture diff: only six `model_id` values (SG-3 clear) |
| FR-013 | T008/T010/T024/T027 docstrings + T029 comment sweep |
| FR-015 | T030 live confirmation table above |
| FR-016 (A1, A2, A3) | T006-T014 policy + guard; T009/T023 wire evidence per site category |
| E1, E4 (A4) | T025 (timing, tier counts); T032 operator note below |
| E2 | T017 `.env.example` + T018 README warning |
| E3 | T032 operator note below |
| E5, E7 | contract C5–C6; T023 always-400 rows |
| E6 | T015 both-keys case |

### Triage record

See the T021 section (default tier: one R7-predicted FLIP) and the T025
section (temporal tier: one FLIP stub swap, one pre-existing base failure,
one escalation). Actual vs predicted divergences are recorded in place.

### Operator note (E1/E3)

- **Drain or accept**: an open run's remaining stages resolve roles from the
  registry at execution time — after upgrading they run on `zai:glm-5.3`
  while completed stages replay from history. Drain open runs before
  upgrading, or accept a mixed-route run.
- **One-time memo miss**: the memoization cache keys include the model
  string; the first post-flip run of each role misses once and re-pays the
  full proposer cost for that role's first stage.
- **Rollback**: per role `--role-model <role>=anthropic:glm-5.2` (needs the
  `ANTHROPIC_*` variables); whole feature: revert the registry commit
  (352cc8e) — memo entries for the old strings are still on disk.

### Open item handed to the orchestrator

**SG-2 escalation** (see the T025 section): `test_priced_usage_parity` was
red on the flipped registry — live inputs token-identical to the frozen
recording, only the model label differed. **Ruled 2026-10-02: option (b)
applied; see the resolution note in the T025 section.** The temporal tier's
only remaining red is the pre-existing base failure recorded in baseline.md.

### Follow-ups to hand the orchestrator (T032 list)

1. **ADR-6 observation against OQ-A4 (GATE 1 Q5)**: post-flip, dev
   (`zai-coding-plan/glm-5.2`) and reviewer (`zai:glm-5.3`) differ in both
   family and model id — the OQ-A4 "same weights" concern no longer applies
   to the shipped registry, but ADR-6 itself was left untouched per Q5.
2. **Claude roles through z.ai's Anthropic endpoint (spec A9)**: adversary,
   discover and risk ride `ANTHROPIC_BASE_URL=api.z.ai/api/anthropic` —
   pre-existing, out of scope, reported.
3. **Registry-snapshot pinning for in-flight runs** (R9/D6): the mixed-run
   semantics are tested and documented, but pinning the registry into
   workflow state is a separate feature if stronger guarantees are wanted.
4. **Research budget retune**: research dollar budgets are reached 14–27%
   sooner on the same tokens (T028 marker); retuning is a product decision,
   not taken here.
