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
