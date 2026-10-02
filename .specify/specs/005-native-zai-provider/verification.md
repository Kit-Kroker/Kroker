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
**No change made to the test or the recording; failure left visible.**

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
