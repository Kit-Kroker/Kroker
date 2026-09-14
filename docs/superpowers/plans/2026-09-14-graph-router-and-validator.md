# E-73 GraphRouter + validate.py Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship FR-1202's control-flow core in `src/sdlc/graph/`: `topology.py` (loop structure), `validate.py` (the single source of graph legality, the only producer of `Topology`) and `router.py` (`GraphRouter`, a pure reducer from `(RouterState, event)` to `Step`). Track A of pipeline-as-data phase 1.

**Architecture:** Three pure, synchronous modules — no Temporal, no I/O, no clocks, no async. `validate(graph, registry, *, roles)` accumulates code-keyed `Problem`s over five tiers and returns a `Topology` only for a clean graph; `GraphRouter(topology)` routes tokens through per-edge slots, invalidates `REGION(target)` on a loop traversal, snapshots unavailable ports at issue, and ends `COMPLETED | REJECTED | ESCALATED`. Nothing outside `sdlc/graph/` imports any of it until E-74.

**Tech Stack:** Python ≥ 3.11, pydantic v2, pytest, ruff, mypy. Standard library only for the property tier (no `hypothesis`).

**Spec:** `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md` (reviewer-approved, user gate passed, commit `d4fcb15`). This plan implements the spec, not the planner brief. Read both documents. Where this plan quotes the spec, the spec wins, **except for the named deviations below**, which the reviewer must judge explicitly.

## Global Constraints

- **Python.** `py311` syntax (`[tool.ruff] target-version = "py311"`); ruff `line-length = 100`, lint `select = ["E", "F", "I", "UP", "B"]`.
- **File size.** Hard ceiling of 1000 physical lines per file (`scripts/check_file_size.py`). Largest files after this plan: `validate.py` 589, `router.py` 481, `tests/graph/test_graph_router.py` 398.
- **Purity** (spec §4). No I/O, no clock, no async, no Temporal in `topology.py`, `validate.py`, `router.py`. Module-level imports, pinned by `tests/graph/test_graph_purity.py`:
  - `topology.py`: stdlib, `sdlc.graph.model`.
  - `validate.py`: stdlib, `pydantic`, `sdlc.core.models`, `sdlc.graph.model`, `sdlc.graph.node_types`, `sdlc.graph.topology`, and (Task 8) `sdlc.graph.router`. `sdlc.agents.loader` is imported **inside `_adr6_problems` only**. Never import `sdlc.agents.roles` (it loads the registry from disk at import).
  - `router.py`: stdlib, `pydantic`, `sdlc.core.models` (`gate_key`), `sdlc.graph.topology`.
- **Determinism** (NFR-10). Iterate sorted everywhere. `RouterState` and `Topology` hold no set types: sorted tuples, or dicts built in sorted-key order (pydantic validators normalise `RouterState`).
- **Untouched** (spec §9). `PipelineConfig`, `src/sdlc/agents/*`, `src/sdlc/core/*`, every `src/sdlc/stages/*`, `src/sdlc/benchmarks/*`, E-72's `model.py`, `node_types.py`, `payloads.py` and the stored schema. The only E-72 file changed is `io.py` (Task 1, behaviour-preserving).
- **Out of scope** (spec §9). No interpreter, dispatch, handler rules, `default.graph.yaml`, API, canvas, store or subflows. Do **not** decide E73-OQ-1…E73-OQ-8.
- **Commit message files are UTF-8 without BOM.** Create `.workspace/tmp/e73-task-commit.txt` with a file-writing tool or `python -c "from pathlib import Path; Path('.workspace/tmp/e73-task-commit.txt').write_text(msg, encoding='utf-8')"`. Never with PowerShell `>`, `Out-File` or `Set-Content`: Windows PowerShell 5.1 writes UTF-16LE or a BOM, and `git commit -F` then fails or records the BOM (plan skeptic P2).
- **Commits.** Subject and body only. **No attribution trailers of any kind**: no `Co-Authored-By:` in any form, no session links, no generated-by footers. Commit with `git commit -F <msgfile>` (message files under `.workspace/tmp/`, which is not committed) and use one path per `git add` invocation.
- **Test runs.** Never chain two `pytest` runs in one shell call. `pytest` resolves `sdlc.graph` and `tests.graph.fixtures` through `pythonpath = [".", "src"]`; if a plain `python -c "import sdlc.graph.router"` fails with `ModuleNotFoundError`, run `pip install -e .` (AGENTS.md). `tests/graph/fixtures/` deliberately has no `__init__.py`: `tests.graph.fixtures.registries` resolves as a PEP 420 namespace package through `pythonpath = [".", "src"]`, like E-72's `tests/graph/` layout; that is also why the typecheck gate is `mypy src/sdlc/graph`, not `mypy tests/` (plan skeptic P6).

## Named deviations from the spec (reviewer: judge these explicitly)

1. **Invariant I is stated over FORWARD slots; back-edge slots satisfy I-back.** Spec §6.7 says every occupied slot's producer is `done` with the matching `taken_port` and came from its latest activation. That is false for a back-edge slot: step 5b resets the emitter (which lies in `REGION(target)`) to `pending` *before* 5c delivers its token, and the token stays after the emitter re-runs. Exhaustive exploration (Task 8) measured 0 violations on forward slots and hundreds on back slots (e.g. 287 on the pre-code fixture). The property checked for back slots — **I-back** — is: the producer's node lies in `REGION(target)`, and no `one` port ever holds two tokens. The corollaries the spec draws (delivery into an occupied slot is unreachable; no stale guidance carries into a later generation) still hold and are checked. **The spec erratum to §6.7 lands in this plan (Task 9, Step 1) — plan review R1.**
2. **T2 confluence compares states modulo issue-time `unavailable_ports` snapshots.** A `target_dead` snapshot legitimately depends on which of two forward emissions arrived first (spec §6.5, advisor Q3 script B); on `running_target_graph(dead_target_variant=True)` two emission pairs yield equal states except for one live activation's snapshot. Everything else — nodes, slots, counters, retired ids, emissions, live ids — is literally equal, and the issued activation sets match. **The spec erratum to §6.7 T2 lands in this plan (Task 9, Step 1) — plan review R1.** Operator-visible consequence, for E-74 (plan skeptic P3): `target_dead` at issue is best-effort under a race. A gate issued just before a peer branch kills its revise target offers REVISE; if the operator takes it, the router spends one traversal, finds the target dead, and re-issues the gate with `target_dead`, so the operator is asked once more, without REVISE. This is the bounded extra ask spec §6.5 already accepts; E-74's gate UI should say why the second ask has no REVISE.
3. **`RouterState.emissions` is stored** (applied emissions, sorted by activation id), and **`dropped` is sorted** by `(activation_id, port, reason)` rather than kept in arrival order (plan skeptic P1), so every `RouterState` collection is order-normalised. Spec §4 says finished ids are derived, not stored; but its F3 rule ("an emission from a finished id identical to the one applied → `dropped(duplicate)`, a conflicting one → `RouterError`") needs the applied `(port, payload_ref)`. The log is sorted, not ordered by application, so T2 holds on literal state equality (an application-ordered log broke confluence in 923 pairs on the disjoint-loops graph). The `emissions` field is recorded by the Task 9 erratum.
4. **`validate.py` imports `sdlc.graph.router` at module level** for `from_graph` (spec §4's allow-set omits it; the spec's advisor record placed `from_graph` in `validate.py`). `router.py` never imports `validate.py`, so there is no cycle.
5. **`topology.py` uses frozen dataclasses and no pydantic** (spec §4 allows pydantic; the dataclasses are narrower). `ValidationReport` holds `Topology` via `arbitrary_types_allowed` and excludes it from dumps.
6. **When a loop port is both `exhausted` and targets a dead node, `exhausted` wins** (spec §6.5 is silent on precedence; the tiebreak is recorded by the Task 9 erratum).
7. **Test files are split for reviewable tasks.** Spec §8's `test_graph_validate.py` becomes `test_graph_validate.py` (T1/T2/T5, suppression, degenerate rows, `from_graph`), `test_graph_validate_config.py` (T3, ADR-6, reserved names), `test_graph_validate_wiring.py` (T4) and `test_graph_validate_catalogue.py` (one row per `ProblemCode` + meta-test). Spec §8's `test_graph_router.py` becomes `test_graph_router.py` (forward semantics, activation checks, backstops) and `test_graph_router_loops.py` (loops). A test driver `tests/graph/fixtures/routing.py` is added. Every spec §8 row maps to a test; see the traceability table below.
8. **The property tier is stronger than spec §8 lists.** Beyond Invariant I / T1–T5 it checks, on every transition of every explored state: a COMPLETED run leaves no node `pending`; every forward in-edge of an issued node is resolved; each issued snapshot equals an independent recomputation of §6.5; an applied loop traversal leaves its token in the slot; and re-delivering any retired id or applied emission is dropped, never raised, and changes nothing but `dropped`. These were added after a mutation survey (below) showed invariants alone let five semantic mutants survive.
9. **The §7.2 T3 kind-consistency rows are per-override, not cumulative** (plan review R3). `_node_config_problems` reports `role_kind_mismatch` alone when `node.role.kind` disagrees with the registry kind, and checks `role_harness_missing` / `research_provider_missing` only on a kind-consistent override — so a kind-mismatched override yields exactly one T3 problem, where the spec's literal table rows could be read as firing two. Every reading rejects the graph; this fixes the report shape. Recorded by the Task 9 erratum.

## Provenance of the code in this plan

Every code block below was executed before the plan was written, in a scratch copy of `src/` plus `tests/graph/` on `main` at `d4fcb15`:
- **275 tests pass** on Python 3.14.3 (the repo's dev interpreter) after Task 8; `ruff check`, `ruff format --check` and `mypy src/sdlc/graph --follow-imports=silent` are clean.
- **The TDD order is proven per task.** Each task's tree was rebuilt from `main` plus Tasks 1…k, and each task's tests were run against the tree of Tasks 1…k−1: every "Expected" below is what was observed (Tasks 2–6 fail at collection, Task 7 with 10 failures, Task 8 with 3; Task 1 pins existing behaviour and passes). Every task's tree passed the full `tests/graph` run plus ruff, format and mypy.
- **Mutation survey.** Ten semantic mutants of `router.py` (5c before 5b; no slot clearing; no cancellation; activation clears slots; collect fires on the first token; `exhausted` off by one; no `target_dead`; rounds reset; stale emission raises; optional ports do not wait) are each killed by the table tests **and**, independently, by the property tier.
- **Edit blocks are mechanically checked.** Each "replace exactly … with …" block was re-applied to the previous version of its file and asserted to reproduce the next version byte-for-byte.
- **Re-proved after the plan skeptic round** (P1 sorted `dropped`, P5 `as_posix()`): the per-task TDD carve, the 275-test run, ruff/format/mypy per task and the mutation survey were all re-run on the final code in this document.
- **Plan reviewer round 1** (`.workspace/tmp/e73-plan-reviewer-r1.md`, CHANGES REQUESTED): R1 — the spec erratum is now Task 9 Step 1, landing in the same branch; R2 — Tasks 2/3/6 red-step text reports the purity-coverage failure; R3 — recorded as deviation 9 and one erratum sentence. All eight deviation rulings were ACCEPT; the reviewer re-derived deviations 1 and 2 independently.
- Slowest tests: `test_seed_registry_is_healthy` 2.9 s (E-72, first import of benchmarks), `test_report_and_router_json_are_hash_seed_independent` 2.3 s (three subprocesses), exhaustive exploration of the nested-loops graph 1.6 s.

Not run on Python 3.11 (this machine's 3.11 has no test dependencies); no syntax newer than 3.11 is used (`StrEnum` is 3.11).

## Plan skeptic round (`.workspace/tmp/e73-plan-skeptic.md`)

| ID | Sev. | Finding | Disposition |
|---|---|---|---|
| P1 | Important | `dropped` kept arrival order while every other collection is sorted | **Accepted.** `RouterState` sorts `dropped` by `(activation_id, port, reason)`; four table assertions now check exact sorted contents instead of `dropped[-1]` (deviation 3). |
| P2 | Important | PowerShell writes commit message files as UTF-16LE / BOM | **Accepted.** Global Constraints: UTF-8 without BOM, written by a file tool or Python. |
| P3 | Important | Deviation 2's operator-visible consequence (an extra ask without REVISE) is undocumented | **Accepted.** Stated under deviation 2 as an E-74 note; the behaviour itself is spec §6.5's accepted bounded extra ask. |
| P4 | Minor | Property tier explores only a 2-branch collect | **Rejected — premise incorrect.** `collect_graph()` fans three branches into the collector (`fast.out`, `slow.out`, `br.left`, where the brancher can take `right` and kill its edge); every interleaving of all three is explored. |
| P5 | Minor | Windows path `repr` embedded in a `-c` script | **Accepted.** `fixture.as_posix()` (Task 8 purity test). The subprocess is argv-based with no shell, so this is hygiene, not a live bug. |
| P6 | Minor | `tests/graph/fixtures/` relies on namespace packaging | **Accepted as a note.** Global Constraints explain the PEP 420 resolution and why `mypy` targets `src/sdlc/graph`; no `__init__.py`, to keep E-72's layout. |

## Spec §8 traceability

| spec §8 item | test |
|---|---|
| fixture registries `fix_loop`, `adr6`, `harness_type`, `fanout`, roles helper | `fixtures/registries.py`: `FIX_LOOP` + `fix_loop_graph`; `GENERIC` types `builder` (dev) / `critic` (reviewer) for ADR-6 and the harness type; `brancher`, `collect` for fan-out and the exclusive merge; `roles()` |
| topology: SCCs, forward reach, region | `test_graph_topology.py`; regions in `test_graph_validate.py::test_e72_fixture_is_clean_against_the_seed_registry` |
| one row per `ProblemCode` + meta-test | `test_graph_validate_catalogue.py` |
| suppression rows, two-root row (R3) | `test_graph_validate.py` (`test_port_typo_does_not_hide_a_forward_cycle`, `test_ambiguous_node_or_edge_sets_suppress_the_topology_tier`, `test_two_roots_report_entry_count_and_no_unreachable_node`) |
| degenerate rows | `test_zero_nodes_is_entry_count_zero`, `test_lone_start_node_is_legal`, `test_lone_gate_yields_exactly_one_problem`, `test_bounded_self_loop_is_legal`; unconnected approve/reject in `test_graph_router.py` |
| E-72 fixture clean, also with `plan.revise → architect` | `test_e72_fixture_is_clean_against_the_seed_registry`, `test_plan_revise_to_architect_is_legal` |
| ADR-6 one breach / two breaches / cap | `test_graph_validate_config.py` ADR-6 section |
| `role: {}` on proposer / research / harness | `test_empty_role_on_proposer_or_research_type_is_a_kind_mismatch`, `test_empty_role_on_harness_type_is_harness_missing` |
| `from_graph` raises `InvalidGraph` | `test_from_graph_raises_invalid_graph_with_every_problem` |
| router rows (1) happy path | `test_e72_fixture_happy_path`, `test_chain_runs_to_completed_and_passes_payload_refs` |
| (2) revise ×2 → exhausted | `test_architecture_revise_twice_then_final_gate` |
| (3) fix loop reproduction | `test_fix_loop_reproduces_max_fix_attempts_and_task_gate_rounds` |
| (4) `plan.revise → architect` | `test_plan_revise_to_architect_invalidates_planner_but_not_clarifier_tokens` |
| (5) nested concurrent loops | `test_outer_loop_cancels_the_inner_loop_and_its_late_emission_is_stale` |
| (6)/(14) `target_dead`, snapshot | `test_snapshot_available_port_into_a_now_dead_target_is_processed_then_reissued` |
| (7)/(11) fan-out, `many` collect | `test_many_collector_*`, `test_optional_ports_wait_for_every_live_edge` |
| (8) self-loop | `test_self_loop_emitter_is_not_cancelled_and_its_token_survives` |
| (9) stale / raises / ESCALATED / (9a) / (9b) | `test_outer_loop_cancels…` (stale), `test_never_issued_ids_raise`, `test_port_not_on_the_type_raises`, `test_conflicting_second_emission_raises`, `test_emission_on_an_exhausted_port_escalates_and_late_redelivery_is_dropped`, `test_backstop_delivery_into_an_occupied_slot`, `test_backstop_two_tokens_on_a_one_port` |
| (10) upstream-input survival | `test_architecture_revise_twice_then_final_gate` |
| (12) post-terminal, duplicate | `test_late_emission_after_rejected_is_post_terminal`, `test_identical_duplicate_is_dropped`, exhausted-port test |
| (13) back token into running target | `test_back_token_into_a_running_target_retires_and_reruns_it` |
| (15) disjoint loops | `test_disjoint_loops_revise_independently` |
| (16) known limitation | `test_reentered_spent_inner_loop_starts_at_its_final_gate` |
| (17) exclusive merge | `test_exclusive_merge_into_a_one_port[left-right/right-left]` |
| properties (Invariant I, T1–T5) | `test_graph_router_properties.py` (deviations 1, 2, 8) |
| NFR-10 hash seed, permutations | `test_graph_determinism.py` |
| purity pin extension | `test_graph_purity.py` (Tasks 1, 2, 3, 6, 8) |
| `_SCHEMA_VERSION`, `NodePort.name` | `test_graph_io.py`, `test_graph_model.py` (Task 1) |

## File Structure

| path | responsibility | task |
|---|---|---|
| `src/sdlc/graph/io.py` | `_SCHEMA_VERSION` derived from the model | 1 |
| `src/sdlc/graph/topology.py` | edge ids, back-edge marker, forward adjacency / reach / SCCs, `PortWiring`, `Topology` | 2 |
| `src/sdlc/graph/validate.py` | `ProblemCode`, `Problem`, `ValidationReport`, `InvalidGraph`, `validate` (T1/T2/T5 → T3 → T4), `RESERVED_GATE_NAMES`, `from_graph` | 3, 4, 5, 8 |
| `src/sdlc/graph/router.py` | `GraphRouter`, `RouterState` and its parts, `Emitted`, `Activation`, `Step`, `RouterError` | 6, 7 |
| `src/sdlc/graph/__init__.py` | re-exports the validator and router surface | 8 |
| `tests/graph/fixtures/registries.py` | builders, `roles()`, `GENERIC`, `FIX_LOOP`, `fix_loop_graph` | 3 |
| `tests/graph/fixtures/routing.py` | `Run` driver (6); scenario graph builders (7) | 6, 7 |
| `tests/graph/test_graph_topology.py` | topology algorithms | 2 |
| `tests/graph/test_graph_validate.py` | T1/T2/T5, suppression, degenerate, `from_graph` | 3, 8 |
| `tests/graph/test_graph_validate_config.py` | T3, ADR-6, reserved names | 4 |
| `tests/graph/test_graph_validate_wiring.py` | T4 | 5 |
| `tests/graph/test_graph_validate_catalogue.py` | one row per code + meta-test | 5 |
| `tests/graph/test_graph_router.py` | forward semantics, activation checks, backstops | 6 |
| `tests/graph/test_graph_router_loops.py` | loops, reproductions, snapshots | 7 |
| `tests/graph/test_graph_router_properties.py` | exhaustive property tier | 8 |
| `tests/graph/test_graph_determinism.py` | NFR-10 | 8 |
| `tests/graph/test_graph_purity.py` | import pins (grows per task) | 1, 2, 3, 6, 8 |
| `tests/graph/test_graph_io.py`, `test_graph_model.py` | E-72 review minors | 1 |
| `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md`, `docs/roadmap/pipeline-as-data.md`, `ROADMAP.md`, `ARCHITECTURE.md` | landing docs and spec erratum (docs describe `main`) | 9 |

Work on a feature branch cut from `main` at or after `d4fcb15`, the spec commit. The orchestrator's exec phase names the branch and worktree. Before any full-suite run, read `.workspace/tasks/` for known host hazards.

---

### Task 1: E-72 review minors — derived schema version, `NodePort.name` pin, purity walker

**Files:**
- Modify: `src/sdlc/graph/io.py`
- Modify: `tests/graph/test_graph_io.py`, `tests/graph/test_graph_model.py`
- Modify: `tests/graph/test_graph_purity.py`

**Interfaces:**
- Consumes: `PipelineGraph.model_fields["schema_version"]` (E-72).
- Produces: `tests/graph/test_graph_purity.py` with `ALLOWED: dict[str, set[str]]` keyed by path relative to `src/sdlc/graph/` (every later task adds its module there), `_module_level_imports(source: str) -> set[str]` (walks every AST node except function/lambda bodies), and `rglob` coverage.

- [ ] **Step 1: Write the tests (and test fixtures)**

In `tests/graph/test_graph_io.py` (edit 1 of 1), replace exactly:

```python
    assert issubclass(GraphSchemaError, ValueError)
```

with:

```python
    assert issubclass(GraphSchemaError, ValueError)


def test_schema_version_is_derived_from_the_model_literal():
    """E-72 review minor 1: the version is encoded once, in the model."""
    from typing import get_args

    from sdlc.graph import io as io_module

    literal = get_args(PipelineGraph.model_fields["schema_version"].annotation)
    assert literal == (1,)
    assert io_module._SCHEMA_VERSION == literal[0]
```

In `tests/graph/test_graph_model.py` (edit 1 of 1), replace exactly:

```python
    assert port.multiplicity == "many"
```

with:

```python
    assert port.multiplicity == "many"


@pytest.mark.parametrize("bad_name", ["Bad", "1port", "port-name", "port.name", "port#1", ""])
def test_node_port_name_shape(bad_name):
    """E-72 review roll-up: NodePort.name shares the id pattern."""
    with pytest.raises(ValidationError):
        NodePort(name=bad_name, direction="in", payload=None)
```

In `tests/graph/test_graph_purity.py` (edit 1 of 3), replace exactly:

```python
"""E-72 import rules (spec §4): sdlc.graph must not open a new route into the
benchmarks <-> stages import cycle, so its MODULE-LEVEL imports are pinned.
Function-local imports (check_node_types) are legal and not inspected."""

from __future__ import annotations
```

with:

```python
"""Import rules for sdlc.graph (E-72 spec §4, E-73 spec §4): the package must
not open a new route into the benchmarks <-> stages import cycle, so its
MODULE-LEVEL imports are pinned. Function-local imports (check_node_types,
validate's ADR-6 check) are legal and not inspected; imports guarded by
`if TYPE_CHECKING:`, `try:` or `with` ARE module-level and are inspected."""

from __future__ import annotations
```

In `tests/graph/test_graph_purity.py` (edit 2 of 3), replace exactly:

```python
}


def _classify(module: str) -> str:
```

with:

```python
}

_SKIPPED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _classify(module: str) -> str:
```

In `tests/graph/test_graph_purity.py` (edit 3 of 3), replace exactly:

```python


def _top_level_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            found |= {_classify(a.name) for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = "sdlc.graph".split(".")[: 2 - (node.level - 1)]
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            found.add(_classify(module))
    return found


def test_every_module_is_covered():
    assert {p.name for p in GRAPH_DIR.glob("*.py")} == set(ALLOWED)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_module_level_imports_are_pinned(name):
    imported = _top_level_imports(GRAPH_DIR / name)
    assert imported <= ALLOWED[name], sorted(imported - ALLOWED[name])
```

with:

```python


def _module_level_imports(source: str) -> set[str]:
    """Every import outside a function or lambda body, at any nesting depth
    (so `if TYPE_CHECKING:`, `try:` and `with` blocks are included)."""
    found: set[str] = set()

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _SKIPPED_SCOPES):
                continue
            if isinstance(child, ast.Import):
                found.update(_classify(a.name) for a in child.names)
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    base = "sdlc.graph".split(".")[: 2 - (child.level - 1)]
                    module = ".".join(base + ([child.module] if child.module else []))
                else:
                    module = child.module or ""
                found.add(_classify(module))
            visit(child)

    visit(ast.parse(source))
    return found


def test_every_module_is_covered():
    found = {p.relative_to(GRAPH_DIR).as_posix() for p in GRAPH_DIR.rglob("*.py")}
    assert found == set(ALLOWED)


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_module_level_imports_are_pinned(name):
    imported = _module_level_imports((GRAPH_DIR / name).read_text(encoding="utf-8"))
    assert imported <= ALLOWED[name], sorted(imported - ALLOWED[name])


def test_walker_sees_guarded_imports_but_not_function_bodies():
    source = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    import sdlc.agents.roles\n"
        "try:\n"
        "    import temporalio\n"
        "except ImportError:\n"
        "    pass\n"
        "class K:\n"
        "    import yaml\n"
        "    def method(self):\n"
        "        import sdlc.benchmarks.heatmap\n"
        "def f():\n"
        "    from sdlc.stages import plan\n"
        "g = lambda: __import__('os')\n"
    )
    assert _module_level_imports(source) == {STDLIB, "sdlc.agents.roles", "temporalio", "yaml"}
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_io.py tests/graph/test_graph_model.py tests/graph/test_graph_purity.py -q`

Expected: **PASS** — this task pins existing behaviour (`.workspace/tasks/2026-09-14-e72-whole-branch-review-minors.md` items owned by E-73): the version is already 1, the port-name regex already exists, and the new walker is test-only. The refactor in Step 3 must keep them green. `test_walker_sees_guarded_imports_but_not_function_bodies` is the pin the old `.body`-only walk could not satisfy.

- [ ] **Step 3: Implement**

In `src/sdlc/graph/io.py` (edit 1 of 2), replace exactly:

```python

import yaml
```

with:

```python

from typing import get_args

import yaml
```

In `src/sdlc/graph/io.py` (edit 2 of 2), replace exactly:

```python

_SCHEMA_VERSION = 1
```

with:

```python

# Derived from the model's Literal[1] so the version is encoded once (E-72
# whole-branch review minor 1, owned by E-73).
_SCHEMA_VERSION: int = get_args(PipelineGraph.model_fields["schema_version"].annotation)[0]
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_io.py tests/graph/test_graph_model.py tests/graph/test_graph_purity.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **113 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
refactor(graph): E-73 derive schema version, widen the purity walker

E-72 whole-branch review minors owned by E-73: io._SCHEMA_VERSION is
derived from PipelineGraph's Literal[1]; NodePort.name gets a regex pin;
the purity pin walks every AST node except function bodies (so
TYPE_CHECKING / try / with imports are inspected) and covers the package
by rglob.
```

```bash
git add tests/graph/test_graph_io.py
git add tests/graph/test_graph_model.py
git add tests/graph/test_graph_purity.py
git add src/sdlc/graph/io.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 2: Loop structure — `topology.py`

**Files:**
- Create: `src/sdlc/graph/topology.py`
- Create: `tests/graph/test_graph_topology.py`
- Modify: `tests/graph/test_graph_purity.py`

**Interfaces:**
- Consumes: `GraphEdge` (E-72 `model.py`).
- Produces: `EdgeKey = tuple[str, str, str, str]`; `edge_key(edge) -> EdgeKey`; `edge_id(edge) -> str` (`"source.source_port->target.target_port"`); `is_back_edge(edge) -> bool` (`max_traversals is not None`, spec U3); `forward_adjacency(node_ids, edges) -> dict[str, tuple[str, ...]]`; `forward_reach(adjacency, start) -> tuple[str, ...]` (includes `start`, sorted); `forward_cycles(adjacency) -> tuple[tuple[str, ...], ...]` (non-trivial SCCs); frozen dataclasses `PortWiring(required, multiplicity, forward_edges, back_edges)` and `Topology(entry, node_ids, gate_nodes, edges, bounds, out_ports, in_ports, regions)`.

- [ ] **Step 1: Write the tests (and test fixtures)**

Create `tests/graph/test_graph_topology.py`:

```python
"""E-73 topology algorithms (spec §4-§5): pure, registry-free, sorted."""

from __future__ import annotations

import itertools

from sdlc.graph.model import GraphEdge
from sdlc.graph.topology import (
    edge_id,
    edge_key,
    forward_adjacency,
    forward_cycles,
    forward_reach,
    is_back_edge,
)


def _e(source: str, target: str, bound: int | None = None, sp: str = "out", tp: str = "in"):
    return GraphEdge(
        source=source, source_port=sp, target=target, target_port=tp, max_traversals=bound
    )


def test_edge_id_and_key():
    e = _e("plan", "planner", 2, sp="revise", tp="guidance")
    assert edge_id(e) == "plan.revise->planner.guidance"
    assert edge_key(e) == ("plan", "revise", "planner", "guidance")
    assert is_back_edge(e)
    assert not is_back_edge(_e("a", "b"))


def test_edge_id_string_order_equals_endpoint_tuple_order():
    names = ["a", "a1", "a_b", "ab", "b", "z9"]
    edges = [
        _e(s, t, sp=sp, tp=tp)
        for s, sp, t, tp in itertools.product(names, ["x", "x_y", "xy"], names[:3], ["p", "p_q"])
    ]
    assert sorted(edges, key=edge_id) == sorted(edges, key=edge_key)


def test_forward_adjacency_ignores_bounded_and_dangling_edges():
    edges = [_e("a", "b"), _e("a", "b", sp="other"), _e("b", "a", 2), _e("a", "ghost")]
    assert forward_adjacency(["b", "a"], edges) == {"a": ("b",), "b": ()}


def test_forward_reach_includes_start_and_is_sorted():
    adj = {"e": ("c", "a"), "a": ("d",), "c": (), "d": (), "x": ("e",)}
    assert forward_reach(adj, "e") == ("a", "c", "d", "e")
    assert forward_reach(adj, "d") == ("d",)


def test_forward_cycles_on_a_dag_is_empty():
    assert forward_cycles({"a": ("b", "c"), "b": ("c",), "c": ()}) == ()


def test_forward_cycles_reports_each_scc_once_sorted():
    adj = {
        "a": ("b",),
        "b": ("c",),
        "c": ("a", "d"),  # {a, b, c}
        "d": ("e",),
        "e": ("d",),  # {d, e}
        "f": ("f",),  # self edge
        "g": (),
    }
    assert forward_cycles(adj) == (("a", "b", "c"), ("d", "e"), ("f",))


def test_forward_cycles_is_independent_of_mapping_order():
    adj = {"a": ("b",), "b": ("a", "c"), "c": ("d",), "d": ("c",)}
    expected = forward_cycles(adj)
    for order in itertools.permutations(adj):
        assert forward_cycles({k: adj[k] for k in order}) == expected


def test_bounded_loop_is_not_a_forward_cycle():
    edges = [_e("a", "b"), _e("b", "a", 2)]
    assert forward_cycles(forward_adjacency(["a", "b"], edges)) == ()
```

In `tests/graph/test_graph_purity.py` (edit 1 of 1), replace exactly:

```python
    "io.py": {STDLIB, "yaml", "sdlc.graph.model"},
    "__init__.py": {
```

with:

```python
    "io.py": {STDLIB, "yaml", "sdlc.graph.model"},
    "topology.py": {STDLIB, "sdlc.graph.model"},
    "__init__.py": {
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_topology.py tests/graph/test_graph_purity.py -q`

Expected: FAIL at collection with `ModuleNotFoundError: No module named 'sdlc.graph.topology'` (also expected: `test_every_module_is_covered` fails until the module exists in Step 3).

- [ ] **Step 3: Implement**

Create `src/sdlc/graph/topology.py`:

```python
"""Loop structure of a pipeline graph (E-73, FR-1202).

Spec: docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
§4-§5.

Pure graph algorithms over node ids and edge endpoints -- no registry, no
roles. A BACK edge is exactly an edge carrying `max_traversals` (spec U3);
every other edge is FORWARD. `Topology` is the precomputed structure the
router runs on. Its only producer is validate.py (spec U7), so a router is
only ever built over a legal graph.

No set types are stored: every collection is a sorted tuple or a mapping
built in sorted-key order (NFR-10, skeptic F8).

Edge ids are "source.source_port->target.target_port". Ids and port names
match ^[a-z][a-z0-9_]*$, and '-' and '.' sort below every character an id
can contain, so sorting edge ids as strings sorts their endpoint 4-tuples.

Module-level imports stay within stdlib and sdlc.graph.model (spec §4;
pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from .model import GraphEdge

EdgeKey = tuple[str, str, str, str]


def edge_key(edge: GraphEdge) -> EdgeKey:
    return (edge.source, edge.source_port, edge.target, edge.target_port)


def edge_id(edge: GraphEdge) -> str:
    return f"{edge.source}.{edge.source_port}->{edge.target}.{edge.target_port}"


def is_back_edge(edge: GraphEdge) -> bool:
    """Spec U3: an edge is a back (loop) edge iff it carries a bound."""
    return edge.max_traversals is not None


def forward_adjacency(
    node_ids: Iterable[str], edges: Iterable[GraphEdge]
) -> dict[str, tuple[str, ...]]:
    """node -> sorted distinct forward successors. Bounded edges and edges
    whose endpoints are not in `node_ids` are ignored."""
    targets: dict[str, set[str]] = {n: set() for n in sorted(set(node_ids))}
    for edge in edges:
        if not is_back_edge(edge) and edge.source in targets and edge.target in targets:
            targets[edge.source].add(edge.target)
    return {n: tuple(sorted(succ)) for n, succ in targets.items()}


def forward_reach(adjacency: Mapping[str, tuple[str, ...]], start: str) -> tuple[str, ...]:
    """`start` plus every node reachable from it, sorted."""
    seen = {start}
    stack = [start]
    while stack:
        for succ in adjacency.get(stack.pop(), ()):
            if succ not in seen:
                seen.add(succ)
                stack.append(succ)
    return tuple(sorted(seen))


def forward_cycles(adjacency: Mapping[str, tuple[str, ...]]) -> tuple[tuple[str, ...], ...]:
    """Non-trivial strongly connected components (size > 1, or one node with
    a self edge): members sorted, components sorted. Iterative Tarjan over
    sorted roots, so the result never depends on dict or DFS order."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[tuple[str, ...]] = []
    counter = 0

    for root in sorted(adjacency):
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(adjacency.get(root, ())))]
        while work:
            node, successors = work[-1]
            descended = False
            for succ in successors:
                if succ not in index:
                    index[succ] = low[succ] = counter
                    counter += 1
                    stack.append(succ)
                    on_stack.add(succ)
                    work.append((succ, iter(adjacency.get(succ, ()))))
                    descended = True
                    break
                if succ in on_stack:
                    low[node] = min(low[node], index[succ])
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in adjacency.get(node, ()):
                    components.append(tuple(sorted(component)))
    return tuple(sorted(components))


@dataclass(frozen=True)
class PortWiring:
    """One CONNECTED in-port of one node, resolved against the registry."""

    required: bool
    multiplicity: Literal["one", "many"]
    forward_edges: tuple[str, ...]  # edge ids, sorted
    back_edges: tuple[str, ...]  # edge ids, sorted


@dataclass(frozen=True)
class Topology:
    """Everything the router needs, resolved once from a LEGAL graph.

    Built only by sdlc.graph.validate (spec U7). Mappings are built in
    sorted-key order; tuples are sorted."""

    entry: str
    node_ids: tuple[str, ...]
    gate_nodes: tuple[str, ...]  # nodes whose type kind is "gate"
    edges: Mapping[str, EdgeKey]  # edge id -> endpoints
    bounds: Mapping[str, int]  # back edge id -> max_traversals
    out_ports: Mapping[str, Mapping[str, tuple[str, ...]]]  # node -> EVERY out-port -> edge ids
    in_ports: Mapping[str, Mapping[str, PortWiring]]  # node -> connected in-port -> wiring
    regions: Mapping[str, tuple[str, ...]]  # back-edge target v -> REGION(v)
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_topology.py tests/graph/test_graph_purity.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **122 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 topology -- back edges, forward reach, SCCs

Pure, registry-free loop structure: a back edge is exactly an edge
carrying max_traversals (spec U3); forward adjacency, reach and
algorithm-independent SCCs over sorted ids; the frozen Topology and
PortWiring the router will run on (built only by validate.py).
```

```bash
git add tests/graph/test_graph_topology.py
git add tests/graph/test_graph_purity.py
git add src/sdlc/graph/topology.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 3: Validator skeleton — identity, references, topology tier, `Topology` construction

**Files:**
- Create: `src/sdlc/graph/validate.py`
- Create: `tests/graph/fixtures/registries.py`, `tests/graph/test_graph_validate.py`
- Modify: `tests/graph/test_graph_purity.py`

**Interfaces:**
- Consumes: Task 2's `topology` names; E-72 `NODE_TYPES`, `NodeTypeSpec`, `find_port`, `ports_compatible`; `RoleConfig`.
- Produces: `ProblemCode(StrEnum)` (T1/T2/T5 members here; Tasks 4–5 add T3/T4); `Problem(code, message, node=None, edge=None, port=None)` with `sort_key()`; `ValidationReport(problems: tuple[Problem, ...], topology: Topology | None)` (`topology` excluded from dumps) with `.ok`; `InvalidGraph(ValueError)` carrying `.problems`; `validate(graph, registry=NODE_TYPES, *, roles) -> ValidationReport`. Test helpers in `tests/graph/fixtures/registries.py`: `port_in`, `port_out`, `stage`, `gate`, `registry`, `node`, `edge("a.out", "b.in", bound=None)`, `graph`, `roles(**overrides)`, `GENERIC`, `FIX_LOOP`, `fix_loop_graph(max_fix_attempts, max_gate_rounds)` — complete here, consumed unchanged by Tasks 4–8.

- [ ] **Step 1: Write the tests (and test fixtures)**

Create `tests/graph/fixtures/registries.py`:

```python
"""Test-only registries, roles and graph builders for E-73 (spec §8).

Injected through `registry=` / `roles=` -- never through the seed catalog.
Payload names here are fixture strings: validate.py compares payload names
with `ports_compatible` and never resolves them through PAYLOAD_TYPES.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sdlc.core.models import HarnessKind, RoleConfig
from sdlc.graph.model import GraphEdge, GraphNode, NodePort, PipelineGraph
from sdlc.graph.node_types import NodeTypeSpec


def port_in(
    name: str, payload: str | None, *, required: bool = True, many: bool = False
) -> NodePort:
    return NodePort(
        name=name,
        direction="in",
        payload=payload,
        required=required,
        multiplicity="many" if many else "one",
    )


def port_out(name: str, payload: str | None) -> NodePort:
    return NodePort(name=name, direction="out", payload=payload)


def stage(type_: str, *ports: NodePort, role: str | None = None) -> NodeTypeSpec:
    return NodeTypeSpec(type=type_, kind="stage", role=role, canonical_stage=None, ports=ports)


def gate(type_: str, payload: str) -> NodeTypeSpec:
    return NodeTypeSpec(
        type=type_,
        kind="gate",
        role=None,
        canonical_stage=None,
        ports=(
            port_in("artifact", payload),
            port_out("approve", payload),
            port_out("revise", "GateDecision"),
            port_out("reject", None),
        ),
    )


def registry(*specs: NodeTypeSpec) -> Mapping[str, NodeTypeSpec]:
    return MappingProxyType({s.type: s for s in specs})


def node(id_: str, type_: str, **kw: object) -> GraphNode:
    return GraphNode.model_validate({"id": id_, "type": type_, **kw})


def edge(source: str, target: str, bound: int | None = None) -> GraphEdge:
    """edge("a.out", "b.in", bound=2)"""
    s, sp = source.split(".")
    t, tp = target.split(".")
    return GraphEdge(source=s, source_port=sp, target=t, target_port=tp, max_traversals=bound)


def graph(nodes: list[GraphNode], edges: list[GraphEdge]) -> PipelineGraph:
    return PipelineGraph(schema_version=1, nodes=nodes, edges=edges)


def roles(**overrides: RoleConfig | None) -> dict[str, RoleConfig]:
    """A minimal load_registry()-shaped mapping that passes ADR-6: dev and
    reviewer in different model families. `name=None` removes a role."""
    base: dict[str, RoleConfig] = {
        "architect": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "clarify": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "dev": RoleConfig(
            kind="harness", harness=HarnessKind.OPENCODE, model="zai-coding-plan/glm-5.2"
        ),
        "planner": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
        "research": RoleConfig(kind="research", model="anthropic:glm-5.2", provider="fake"),
        "reviewer": RoleConfig(kind="proposer", model="anthropic:glm-5.2"),
    }
    for name, cfg in overrides.items():
        if cfg is None:
            base.pop(name, None)
        else:
            base[name] = cfg
    return dict(sorted(base.items()))


# GENERIC: small composable types for validator and router tables.
GENERIC = registry(
    stage("start", port_out("ok", None)),
    stage(
        "work",
        port_in("trigger", None),
        port_in("guidance", "GateDecision", required=False),
        port_out("out", "Art"),
    ),
    stage("sink", port_in("art", "Art"), port_out("done", None)),
    stage("collect", port_in("items", "Art", many=True), port_out("done", None)),
    stage("brancher", port_in("trigger", None), port_out("left", "Art"), port_out("right", "Art")),
    stage(
        "opt2",
        port_in("a", "Art", required=False),
        port_in("b", "Art", required=False),
        port_out("done", None),
    ),
    stage(
        "retry",
        port_in("trigger", None),
        port_in("again", "GateDecision", required=False),
        port_out("out", "Art"),
        port_out("redo", "GateDecision"),
    ),
    stage(
        "refine",
        port_in("art", "Art"),
        port_in("guidance", "GateDecision", required=False),
        port_out("out", "Art"),
    ),
    stage(
        "join",
        port_in("req", "Art"),
        port_in("opt", "Art", required=False),
        port_out("out", "Art"),
    ),
    stage(
        "fixer",
        port_in("trigger", None),
        port_in("opt", "Art", required=False),
        port_out("fix", "GateDecision"),
    ),
    stage("builder", port_in("trigger", None), port_out("out", "Art"), role="dev"),
    stage("critic", port_in("art", "Art"), port_out("done", None), role="reviewer"),
    gate("gate.art", "Art"),
)

# FIX_LOOP: the code stage's fix loop as topology (spec §8, router table 3).
FIX_LOOP = registry(
    stage("start", port_out("ok", None)),
    stage(
        "coder",
        port_in("task", None),
        port_in("guidance", "GateDecision", required=False),
        port_out("patch", "Patch"),
    ),
    stage(
        "qa",
        port_in("patch", "Patch"),
        port_out("pass", "Patch"),
        port_out("fail", "GateDecision"),
        port_out("escalate", "Patch"),
    ),
    gate("gate.task", "Patch"),
)


def fix_loop_graph(max_fix_attempts: int, max_gate_rounds: int) -> PipelineGraph:
    """start -> coder -> qa; qa.fail -> coder (bound M); qa.escalate ->
    task gate; gate.revise -> coder (bound R). qa.pass and gate.approve are
    sinks; gate.reject is unconnected (REJECTED)."""
    return graph(
        [
            node("start", "start"),
            node("coder", "coder"),
            node("qa", "qa"),
            node("task", "gate.task"),
        ],
        [
            edge("start.ok", "coder.task"),
            edge("coder.patch", "qa.patch"),
            edge("qa.fail", "coder.guidance", bound=max_fix_attempts),
            edge("qa.escalate", "task.artifact"),
            edge("task.revise", "coder.guidance", bound=max_gate_rounds),
        ],
    )
```

Create `tests/graph/test_graph_validate.py`:

```python
"""E-73 validate.py (spec §7): one table row per ProblemCode, suppression,
degenerate graphs, and the Topology a clean graph yields."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.validate import Problem, ProblemCode, ValidationReport, validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"
C = ProblemCode


def _codes(report: ValidationReport) -> list[str]:
    return [p.code.value for p in report.problems]


def _check(g, registry=GENERIC, **role_overrides) -> ValidationReport:
    return validate(g, registry, roles=roles(**role_overrides))


def _chain(*extra_edges, extra_nodes=()):
    """start -> w (work) -> s (sink): the smallest clean GENERIC graph."""
    return graph(
        [node("start", "start"), node("w", "work"), node("s", "sink"), *extra_nodes],
        [edge("start.ok", "w.trigger"), edge("w.out", "s.art"), *extra_edges],
    )


# ---- clean graphs and the Topology they carry ------------------------------


def test_clean_chain_has_no_problems_and_a_topology():
    report = _check(_chain())
    assert report.problems == ()
    assert report.ok
    topo = report.topology
    assert topo is not None
    assert topo.entry == "start"
    assert topo.node_ids == ("s", "start", "w")
    assert topo.gate_nodes == ()
    assert topo.bounds == {}
    assert topo.regions == {}
    assert topo.out_ports["w"] == {"out": ("w.out->s.art",)}
    assert topo.out_ports["s"] == {"done": ()}  # unconnected out-ports are listed
    assert set(topo.in_ports["w"]) == {"trigger"}  # unconnected `guidance` is not


def test_e72_fixture_is_clean_against_the_seed_registry():
    report = validate(from_yaml(FIXTURE.read_text(encoding="utf-8")), roles=roles())
    assert report.problems == ()
    topo = report.topology
    assert topo is not None
    assert topo.entry == "intake"
    assert topo.gate_nodes == ("architecture", "plan", "research")
    assert topo.bounds == {
        "architecture.revise->architect.guidance": 2,
        "plan.revise->planner.guidance": 2,
        "research.revise->researcher.guidance": 2,
    }
    # REGION(v) = v plus its forward reach (spec D2).
    assert topo.regions["architect"] == ("architect", "architecture", "plan", "planner")
    assert topo.regions["planner"] == ("plan", "planner")
    wiring = topo.in_ports["architect"]["guidance"]
    assert wiring.forward_edges == ()
    assert wiring.back_edges == ("architecture.revise->architect.guidance",)


def test_plan_revise_to_architect_is_legal():
    """Dominance would reject this edge (spec U3); the marker rule accepts it."""
    g = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    extra = edge("plan.revise", "architect.guidance", bound=1)
    g2 = graph(list(g.nodes), [e for e in g.edges if e.source != "plan"] + [extra])
    report = validate(g2, roles=roles())
    assert report.problems == ()
    assert report.topology is not None
    assert "plan.revise->architect.guidance" in report.topology.bounds


def test_report_json_excludes_topology():
    report = _check(_chain())
    assert report.model_dump(mode="json") == {"problems": []}


# ---- T1 identity ------------------------------------------------------------


def test_duplicate_node_id():
    g = _chain(extra_nodes=(node("w", "sink"),))
    assert C.DUPLICATE_NODE_ID in _codes(_check(g))
    [p] = [p for p in _check(g).problems if p.code is C.DUPLICATE_NODE_ID]
    assert p.node == "w"


def test_duplicate_edge_even_when_bounds_disagree():
    g = _chain(edge("w.out", "s.art", bound=2))
    report = _check(g)
    [p] = [p for p in report.problems if p.code is C.DUPLICATE_EDGE]
    assert p.edge == ("w", "out", "s", "art")
    assert report.topology is None


# ---- T2 references ------------------------------------------------------------


def test_dangling_endpoint_names_each_missing_side():
    g = _chain(edge("ghost.out", "phantom.art"))
    dangling = [p for p in _check(g).problems if p.code is C.DANGLING_ENDPOINT]
    assert [p.message.split(": ")[1] for p in dangling] == [
        "source 'ghost' names no node",
        "target 'phantom' names no node",
    ]


def test_unknown_node_type():
    g = _chain(extra_nodes=(node("x", "nope"),))
    [p] = [p for p in _check(g).problems if p.code is C.UNKNOWN_NODE_TYPE]
    assert p.node == "x"


@pytest.mark.parametrize(
    ("bad", "node_id", "port"),
    [
        (edge("w.nope", "s.art"), "w", "nope"),  # no such out-port
        (edge("w.out", "s.nope"), "s", "nope"),  # no such in-port
        (edge("w.guidance", "s.art"), "w", "guidance"),  # an in-port used as a source
        (edge("w.out", "s.done"), "s", "done"),  # an out-port used as a target
    ],
)
def test_unknown_port_including_wrong_direction(bad, node_id, port):
    g = graph(
        [node("start", "start"), node("w", "work"), node("s", "sink")],
        [edge("start.ok", "w.trigger"), bad],
    )
    unknown = [p for p in _check(g).problems if p.code is C.UNKNOWN_PORT]
    assert [(p.node, p.port) for p in unknown] == [(node_id, port)]


def test_incompatible_ports_on_forward_and_back_edges():
    g = graph(
        [node("start", "start"), node("w", "work"), node("g", "gate.art"), node("s", "sink")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.approve", "s.art"),
            edge("start.ok", "s.art"),  # None -> Art
            edge("g.reject", "w.guidance", bound=1),  # back edge: None -> GateDecision
        ],
    )
    bad = [p.edge for p in _check(g).problems if p.code is C.INCOMPATIBLE_PORTS]
    assert bad == [("g", "reject", "w", "guidance"), ("start", "ok", "s", "art")]


# ---- T5 topology ----------------------------------------------------------------


def test_forward_cycle_reported_once_per_scc():
    g = graph(
        [node("start", "start"), node("a", "retry")],
        [edge("start.ok", "a.trigger"), edge("a.redo", "a.again")],  # unbounded self loop
    )
    [p] = [p for p in _check(g).problems if p.code is C.FORWARD_CYCLE]
    assert p.node == "a"


def test_bounded_edge_not_a_loop():
    g = _chain(extra_nodes=(node("x", "work"),))
    g = graph(list(g.nodes), [*g.edges, edge("start.ok", "x.trigger", bound=2)])
    report = _check(g)
    assert [p.edge for p in report.problems if p.code is C.BOUNDED_EDGE_NOT_A_LOOP] == [
        ("start", "ok", "x", "trigger")
    ]


def test_bounded_self_loop_is_legal():
    g = graph(
        [node("start", "start"), node("a", "retry")],
        [edge("start.ok", "a.trigger"), edge("a.redo", "a.again", bound=3)],
    )
    report = _check(g)
    assert report.problems == ()
    assert report.topology is not None
    assert report.topology.regions == {"a": ("a",)}


def test_zero_nodes_is_entry_count_zero():
    assert _codes(_check(graph([], []))) == [C.ENTRY_COUNT]


def test_two_roots_report_entry_count_and_no_unreachable_node():
    """Spec §7.2 T5 (reviewer R3): no arbitrary anchor when entries != 1."""
    g = _chain(extra_nodes=(node("start2", "start"),))
    report = _check(g)
    assert C.ENTRY_COUNT in _codes(report)
    assert C.UNREACHABLE_NODE not in _codes(report)
    [p] = [p for p in report.problems if p.code is C.ENTRY_COUNT]
    assert "'start', 'start2'" in p.message


def test_unreachable_node():
    """With exactly one entry, a node is unreachable only inside a forward
    cycle the entry never enters: both members have forward in-edges."""
    g = _chain(
        edge("a.out", "b.art"),
        edge("b.done", "a.trigger"),
        extra_nodes=(node("a", "work"), node("b", "sink")),
    )
    report = _check(g)
    assert [p.node for p in report.problems if p.code is C.UNREACHABLE_NODE] == ["a", "b"]
    assert C.FORWARD_CYCLE in _codes(report)
    assert C.ENTRY_COUNT not in _codes(report)


# ---- suppression (spec §7.1) ----------------------------------------------------


def test_port_typo_does_not_hide_a_forward_cycle():
    g = graph(
        [node("start", "start"), node("a", "retry")],
        [edge("start.ok", "a.triggr"), edge("a.redo", "a.again")],
    )
    codes = _codes(_check(g))
    assert C.UNKNOWN_PORT in codes
    assert C.FORWARD_CYCLE in codes


@pytest.mark.parametrize(
    "g",
    [
        _chain(edge("ghost.out", "s.art")),  # dangling endpoint
        _chain(edge("w.out", "s.art")),  # duplicate edge
        _chain(extra_nodes=(node("s", "work"),)),  # duplicate node id
    ],
)
def test_ambiguous_node_or_edge_sets_suppress_the_topology_tier(g):
    g = graph(list(g.nodes), [*g.edges, edge("s.done", "s.done")])  # would be a forward cycle
    codes = _codes(_check(g))
    assert C.FORWARD_CYCLE not in codes
    assert C.ENTRY_COUNT not in codes


# ---- degenerate graphs ----------------------------------------------------------


def test_lone_start_node_is_legal():
    report = _check(graph([node("start", "start")], []))
    assert report.problems == ()


def test_problems_are_sorted_and_none_safe():
    g = graph(
        [node("start", "start"), node("x", "nope"), node("y", "nope")],
        [edge("ghost.ok", "x.in"), edge("start.ok", "phantom.in")],
    )
    problems = _check(g).problems
    assert list(problems) == sorted(problems, key=Problem.sort_key)
    assert len(problems) >= 4
```

In `tests/graph/test_graph_purity.py` (edit 1 of 1), replace exactly:

```python
    "topology.py": {STDLIB, "sdlc.graph.model"},
    "__init__.py": {
```

with:

```python
    "topology.py": {STDLIB, "sdlc.graph.model"},
    "validate.py": {
        STDLIB,
        "pydantic",
        "sdlc.core.models",
        "sdlc.graph.model",
        "sdlc.graph.node_types",
        "sdlc.graph.topology",
    },
    "__init__.py": {
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_validate.py tests/graph/test_graph_purity.py -q`

Expected: FAIL at collection with `ModuleNotFoundError: No module named 'sdlc.graph.validate'` (also expected: `test_every_module_is_covered` fails until the module exists in Step 3).

- [ ] **Step 3: Implement**

Create `src/sdlc/graph/validate.py`:

```python
"""Graph legality -- the single validator (E-73, FR-1202).

Spec: docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
§7.

Every consumer (interpreter, CLI, canvas via E-75, tests) calls `validate`;
legality is never reimplemented elsewhere. All checks run and accumulate so
the canvas sees every error at once. A clean report carries the `Topology`
the router runs on; this module is its only producer (spec U7).

Pure: no I/O, no clock. `roles` is passed in (a load_registry()-shaped
mapping) because loading it is I/O. The ADR-6 check imports
sdlc.agents.loader INSIDE its body (sdlc/agents/__init__.py is empty, so that
import runs no registry load).

Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph.{model,node_types,topology} (spec §4; pinned by
tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from ..core.models import RoleConfig
from .model import GraphEdge, GraphNode, PipelineGraph
from .node_types import NODE_TYPES, NodeTypeSpec, find_port, ports_compatible
from .topology import (
    EdgeKey,
    PortWiring,
    Topology,
    edge_id,
    edge_key,
    forward_adjacency,
    forward_cycles,
    forward_reach,
    is_back_edge,
)


class ProblemCode(StrEnum):
    # T1 identity
    DUPLICATE_NODE_ID = "duplicate_node_id"
    DUPLICATE_EDGE = "duplicate_edge"
    # T2 references
    DANGLING_ENDPOINT = "dangling_endpoint"
    UNKNOWN_NODE_TYPE = "unknown_node_type"
    UNKNOWN_PORT = "unknown_port"
    INCOMPATIBLE_PORTS = "incompatible_ports"
    # T5 topology
    FORWARD_CYCLE = "forward_cycle"
    BOUNDED_EDGE_NOT_A_LOOP = "bounded_edge_not_a_loop"
    ENTRY_COUNT = "entry_count"
    UNREACHABLE_NODE = "unreachable_node"


class Problem(BaseModel):
    """One legality problem. Tests and the canvas key on `code`, never on
    `message` text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ProblemCode
    message: str
    node: str | None = None
    edge: EdgeKey | None = None
    port: str | None = None

    def sort_key(self) -> tuple[str, str, EdgeKey | tuple[()], str, str]:
        # None-safe: None never meets a str in a comparison.
        return (self.code.value, self.node or "", self.edge or (), self.port or "", self.message)


class ValidationReport(BaseModel):
    """`topology` is present iff `problems` is empty, and is excluded from
    the JSON dump (E-75 serialises the problems only)."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    problems: tuple[Problem, ...]
    topology: Topology | None = Field(default=None, exclude=True)

    @property
    def ok(self) -> bool:
        return not self.problems


class InvalidGraph(ValueError):
    """Raised by from_graph() when validate() reports problems."""

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        self.problems = problems
        super().__init__("; ".join(f"{p.code.value}: {p.message}" for p in problems))


def _names(items: Iterable[str]) -> str:
    return ", ".join(repr(i) for i in sorted(items))


def _identity_problems(graph: PipelineGraph) -> list[Problem]:
    problems: list[Problem] = []
    for node_id, count in sorted(Counter(n.id for n in graph.nodes).items()):
        if count > 1:
            problems.append(
                Problem(
                    code=ProblemCode.DUPLICATE_NODE_ID,
                    node=node_id,
                    message=f"node id {node_id!r} is used by {count} nodes",
                )
            )
    for key, count in sorted(Counter(edge_key(e) for e in graph.edges).items()):
        if count > 1:
            problems.append(
                Problem(
                    code=ProblemCode.DUPLICATE_EDGE,
                    edge=key,
                    message=f"edge {key[0]}.{key[1]}->{key[2]}.{key[3]} appears {count} times",
                )
            )
    return problems


def _first_nodes(graph: PipelineGraph) -> dict[str, GraphNode]:
    """id -> the first node with that id (nodes are already sorted, so this
    is deterministic even for an illegal duplicate-id draft)."""
    first: dict[str, GraphNode] = {}
    for n in graph.nodes:
        first.setdefault(n.id, n)
    return first


def _reference_problems(
    graph: PipelineGraph,
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
) -> list[Problem]:
    problems: list[Problem] = []
    for node_id, n in nodes.items():
        if n.type not in registry:
            problems.append(
                Problem(
                    code=ProblemCode.UNKNOWN_NODE_TYPE,
                    node=node_id,
                    message=f"node {node_id!r} has unknown type {n.type!r}",
                )
            )
    for e in graph.edges:
        key = edge_key(e)
        for role, endpoint in (("source", e.source), ("target", e.target)):
            if endpoint not in nodes:
                problems.append(
                    Problem(
                        code=ProblemCode.DANGLING_ENDPOINT,
                        edge=key,
                        message=f"edge {edge_id(e)}: {role} {endpoint!r} names no node",
                    )
                )
        source_spec = _spec_of(nodes, registry, e.source)
        target_spec = _spec_of(nodes, registry, e.target)
        out_port = find_port(source_spec, e.source_port, "out") if source_spec else None
        in_port = find_port(target_spec, e.target_port, "in") if target_spec else None
        if source_spec is not None and out_port is None:
            problems.append(
                Problem(
                    code=ProblemCode.UNKNOWN_PORT,
                    edge=key,
                    node=e.source,
                    port=e.source_port,
                    message=f"edge {edge_id(e)}: {source_spec.type!r} has no out-port "
                    f"{e.source_port!r}",
                )
            )
        if target_spec is not None and in_port is None:
            problems.append(
                Problem(
                    code=ProblemCode.UNKNOWN_PORT,
                    edge=key,
                    node=e.target,
                    port=e.target_port,
                    message=f"edge {edge_id(e)}: {target_spec.type!r} has no in-port "
                    f"{e.target_port!r}",
                )
            )
        if out_port is not None and in_port is not None and not ports_compatible(out_port, in_port):
            problems.append(
                Problem(
                    code=ProblemCode.INCOMPATIBLE_PORTS,
                    edge=key,
                    message=f"edge {edge_id(e)}: payload {out_port.payload!r} does not "
                    f"connect to {in_port.payload!r}",
                )
            )
    return problems


def _spec_of(
    nodes: Mapping[str, GraphNode], registry: Mapping[str, NodeTypeSpec], node_id: str
) -> NodeTypeSpec | None:
    n = nodes.get(node_id)
    return registry.get(n.type) if n is not None else None


def _topology_problems(graph: PipelineGraph, node_ids: list[str]) -> list[Problem]:
    problems: list[Problem] = []
    adjacency = forward_adjacency(node_ids, graph.edges)
    for component in forward_cycles(adjacency):
        problems.append(
            Problem(
                code=ProblemCode.FORWARD_CYCLE,
                node=component[0],
                message=f"unbounded cycle through {_names(component)}; "
                f"set max_traversals on the loop edge",
            )
        )
    for e in graph.edges:
        if is_back_edge(e) and e.source not in forward_reach(adjacency, e.target):
            problems.append(
                Problem(
                    code=ProblemCode.BOUNDED_EDGE_NOT_A_LOOP,
                    edge=edge_key(e),
                    message=f"edge {edge_id(e)} carries max_traversals but closes no cycle",
                )
            )
    has_forward_in = {e.target for e in graph.edges if not is_back_edge(e)}
    entries = [n for n in node_ids if n not in has_forward_in]
    if len(entries) != 1:
        problems.append(
            Problem(
                code=ProblemCode.ENTRY_COUNT,
                message=f"a graph needs exactly one entry node (no forward in-edge); "
                f"found {len(entries)}: {_names(entries)}",
            )
        )
    else:
        reached = set(forward_reach(adjacency, entries[0]))
        for n in node_ids:
            if n not in reached:
                problems.append(
                    Problem(
                        code=ProblemCode.UNREACHABLE_NODE,
                        node=n,
                        message=f"node {n!r} is not reachable from entry {entries[0]!r}",
                    )
                )
    return problems


def _build_topology(
    graph: PipelineGraph,
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
) -> Topology:
    """Called only on a clean graph: every lookup below is known to succeed."""
    node_ids = sorted(nodes)
    adjacency = forward_adjacency(node_ids, graph.edges)
    entry = next(
        n for n in node_ids if n not in {e.target for e in graph.edges if not is_back_edge(e)}
    )
    by_id: dict[str, GraphEdge] = {edge_id(e): e for e in graph.edges}
    out_ports: dict[str, dict[str, tuple[str, ...]]] = {}
    in_ports: dict[str, dict[str, PortWiring]] = {}
    for node_id in node_ids:
        spec = registry[nodes[node_id].type]
        outs: dict[str, tuple[str, ...]] = {}
        ins: dict[str, PortWiring] = {}
        for port in sorted(spec.ports, key=lambda p: (p.direction, p.name)):
            if port.direction == "out":
                outs[port.name] = tuple(
                    i
                    for i, e in sorted(by_id.items())
                    if e.source == node_id and e.source_port == port.name
                )
                continue
            incoming = [
                (i, e)
                for i, e in sorted(by_id.items())
                if e.target == node_id and e.target_port == port.name
            ]
            if incoming:
                ins[port.name] = PortWiring(
                    required=port.required,
                    multiplicity=port.multiplicity,
                    forward_edges=tuple(i for i, e in incoming if not is_back_edge(e)),
                    back_edges=tuple(i for i, e in incoming if is_back_edge(e)),
                )
        out_ports[node_id] = dict(sorted(outs.items()))
        in_ports[node_id] = dict(sorted(ins.items()))
    bounds = {i: e.max_traversals for i, e in sorted(by_id.items()) if e.max_traversals is not None}
    targets = sorted({by_id[i].target for i in bounds})
    return Topology(
        entry=entry,
        node_ids=tuple(node_ids),
        gate_nodes=tuple(n for n in node_ids if registry[nodes[n].type].kind == "gate"),
        edges={i: edge_key(e) for i, e in sorted(by_id.items())},
        bounds=bounds,
        out_ports=out_ports,
        in_ports=in_ports,
        regions={v: forward_reach(adjacency, v) for v in targets},
    )


def validate(
    graph: PipelineGraph,
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
    *,
    roles: Mapping[str, RoleConfig],
) -> ValidationReport:
    """Every legality problem of `graph`, sorted; plus its Topology iff none."""
    nodes = _first_nodes(graph)
    identity = _identity_problems(graph)
    references = _reference_problems(graph, nodes, registry)
    problems = identity + references
    suppress_topology = any(
        p.code
        in (
            ProblemCode.DUPLICATE_NODE_ID,
            ProblemCode.DUPLICATE_EDGE,
            ProblemCode.DANGLING_ENDPOINT,
        )
        for p in problems
    )
    if not suppress_topology:
        problems += _topology_problems(graph, sorted(nodes))
    ordered = tuple(sorted(problems, key=Problem.sort_key))
    if ordered:
        return ValidationReport(problems=ordered)
    return ValidationReport(problems=(), topology=_build_topology(graph, nodes, registry))
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_validate.py tests/graph/test_graph_purity.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **148 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 validate -- identity, references, topology tier

validate() accumulates sorted, code-keyed Problems: duplicate ids and
edges, dangling endpoints, unknown types and ports (wrong direction
included), incompatible ports on every edge; forward-cycle SCCs, bounded
edges that close no loop, exactly one entry, reachability from it.
Duplicate ids/edges and dangling endpoints suppress the topology tier
(skeptic F6). A clean report carries the Topology. Test-only registries,
roles and builders live in tests/graph/fixtures/registries.py.
```

```bash
git add tests/graph/fixtures/registries.py
git add tests/graph/test_graph_validate.py
git add tests/graph/test_graph_purity.py
git add src/sdlc/graph/validate.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 4: Validator T3 — node configuration, ADR-6 cross-product, reserved gate names

**Files:**
- Modify: `src/sdlc/graph/validate.py`
- Create: `tests/graph/test_graph_validate_config.py`

**Interfaces:**
- Consumes: Task 3's `validate.py`; `sdlc.agents.loader.validate_run_roles` and `RegistryError` (imported **inside** `_adr6_problems` only).
- Produces: `ProblemCode` T3 members; `RESERVED_GATE_NAMES: frozenset[str]`; `ADR6_COMBINATION_CAP = 256`.

- [ ] **Step 1: Write the tests (and test fixtures)**

Create `tests/graph/test_graph_validate_config.py`:

```python
"""E-73 validate.py T3 node configuration (spec §7.2-§7.4): role/gate
placement, loader-owned fields, kind consistency (the `role: {}` traps),
registry presence, ADR-6 over graphs, reserved gate names."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.core.models import HarnessKind, RoleConfig
from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.graph.validate import (
    ADR6_COMBINATION_CAP,
    RESERVED_GATE_NAMES,
    ProblemCode,
    ValidationReport,
    validate,
)
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"
C = ProblemCode


def _problems(report: ValidationReport, code: ProblemCode) -> list[tuple[str | None, str]]:
    return [(p.node, p.message) for p in report.problems if p.code is code]


def _nodes(report: ValidationReport, code: ProblemCode) -> list[str | None]:
    return [p.node for p in report.problems if p.code is code]


def _generic(*nodes, **role_overrides) -> ValidationReport:
    return validate(
        graph([node("start", "start"), *nodes], []), GENERIC, roles=roles(**role_overrides)
    )


def _seed(*nodes, **role_overrides) -> ValidationReport:
    return validate(
        graph([node("intake", "intake"), *nodes], []), NODE_TYPES, roles=roles(**role_overrides)
    )


def test_role_on_roleless_type():
    assert _nodes(
        _generic(node("w", "work", role={"kind": "proposer"})), C.ROLE_ON_ROLELESS_TYPE
    ) == ["w"]


def test_gate_on_non_gate():
    assert _nodes(_generic(node("w", "work", gate={})), C.GATE_ON_NON_GATE) == ["w"]
    assert _nodes(_generic(node("g", "gate.art", gate={})), C.GATE_ON_NON_GATE) == []


@pytest.mark.parametrize(
    "role",
    [
        {"kind": "harness", "harness": "opencode", "instructions": "you are dev"},
        {"kind": "harness", "harness": "opencode", "tool_files": ["tools/x.py"]},
    ],
)
def test_loader_owned_field(role):
    assert _nodes(_generic(node("b", "builder", role=role)), C.LOADER_OWNED_FIELD) == ["b"]


def test_role_not_in_registry_with_and_without_override():
    """E-72 §5's OPTIONAL_ROLES clause: `research` on a tree without
    agents/research/ -- a problem, never a KeyError."""
    report = _seed(
        node("plain", "research"),
        node("tuned", "research", role={"kind": "research", "provider": "fake"}),
        research=None,
    )
    assert _nodes(report, C.ROLE_NOT_IN_REGISTRY) == ["plain", "tuned"]
    assert _nodes(report, C.ROLE_KIND_MISMATCH) == []


@pytest.mark.parametrize("type_", ["architect", "clarify", "plan", "research"])
def test_empty_role_on_proposer_or_research_type_is_a_kind_mismatch(type_):
    report = _seed(node("n", type_, role={}))
    assert _nodes(report, C.ROLE_KIND_MISMATCH) == ["n"]
    assert _nodes(report, C.ROLE_HARNESS_MISSING) == []


def test_empty_role_on_harness_type_is_harness_missing():
    report = _generic(node("b", "builder", role={}))
    assert _nodes(report, C.ROLE_HARNESS_MISSING) == ["b"]
    assert _nodes(report, C.ROLE_KIND_MISMATCH) == []


def test_research_override_without_provider():
    report = _seed(node("r", "research", role={"kind": "research"}))
    assert _nodes(report, C.RESEARCH_PROVIDER_MISSING) == ["r"]


def _wired(*builders) -> ValidationReport:
    """start fans out to each builder: a CLEAN graph apart from T3."""
    g = graph(
        [node("start", "start"), *builders],
        [edge("start.ok", f"{b.id}.trigger") for b in builders],
    )
    return validate(g, GENERIC, roles=roles())


def test_well_formed_overrides_are_clean():
    b = node(
        "b",
        "builder",
        role={"kind": "harness", "harness": "claude_code", "model": "zai-coding-plan/x"},
    )
    assert _wired(b).problems == ()


def test_reserved_gate_names_are_exactly_the_verified_handler_gates():
    assert RESERVED_GATE_NAMES == {
        "budget",
        "clarify",
        "crew_question",
        "deploy",
        "deploy_failed",
        "merge",
        "readiness",
        "risk",
        "tidy_up",
        "tool_approval",
    }
    assert not RESERVED_GATE_NAMES & {"research", "architecture", "plan"}


def test_reserved_gate_name_applies_to_gate_nodes_only():
    report = _generic(node("clarify", "gate.art"), node("merge", "work"))
    assert _nodes(report, C.RESERVED_GATE_NAME) == ["clarify"]


# ---- ADR-6 over graphs (spec U4, §7.4) ---------------------------------------


def _builder(id_: str, model: str):
    return node(id_, "builder", role={"kind": "harness", "harness": "opencode", "model": model})


def _critic(id_: str, model: str):
    return node(id_, "critic", role={"kind": "proposer", "model": model})


def test_adr6_same_family_override_is_a_violation():
    report = _generic(_builder("b", "anthropic:claude-x"))  # registry reviewer is anthropic
    [(_, message)] = _problems(report, C.ADR6_VIOLATION)
    assert "ADR-6 violation" in message


def test_adr6_cross_product_catches_one_divergent_dev_model():
    report = _generic(
        _builder("b1", "zai-coding-plan/glm-5.2"), _builder("b2", "anthropic:claude-x")
    )
    assert len(_problems(report, C.ADR6_VIOLATION)) == 1


def test_adr6_reports_each_distinct_breach_once():
    report = _generic(
        _builder("b1", "zai-coding-plan/glm-5.2"),
        _builder("b2", "anthropic:claude-x"),
        _critic("c1", "zai-coding-plan/other"),
        _critic("c2", "anthropic:other"),
    )
    messages = [m for _, m in _problems(report, C.ADR6_VIOLATION)]
    assert len(messages) == 2
    assert messages == sorted(messages)
    assert all(n is None for n, _ in _problems(report, C.ADR6_VIOLATION))


def test_adr6_divergence_that_respects_the_rule_is_legal():
    report = _wired(_builder("b1", "zai-coding-plan/glm-5.2"), _builder("b2", "openai:gpt-x"))
    assert report.problems == ()


def test_adr6_cap_fails_closed():
    builders = [_builder(f"b{i}", f"fam{i}:m") for i in range(17)]
    critics = [_critic(f"c{i}", f"other{i}:m") for i in range(16)]
    assert 17 * 16 > ADR6_COMBINATION_CAP
    report = _generic(*builders, *critics)
    assert _nodes(report, C.ADR6_COMBINATIONS_EXCEEDED) == [None]
    assert _problems(report, C.ADR6_VIOLATION) == []


def test_adr6_missing_reviewer_is_a_problem_not_a_crash():
    report = _generic(reviewer=None)
    [(_, message)] = _problems(report, C.ADR6_VIOLATION)
    assert "requires both" in message


def test_adr6_unused_roles_keep_their_registry_model():
    """A graph with no builder still checks the registry dev against a
    critic override (mirrors cli_roles)."""
    report = _generic(_critic("c", "zai-coding-plan/other"))
    assert len(_problems(report, C.ADR6_VIOLATION)) == 1


def test_seed_fixture_stays_clean_with_node_config_checks():
    report = validate(from_yaml(FIXTURE.read_text(encoding="utf-8")), roles=roles())
    assert report.problems == ()


def test_harness_kind_role_config_is_the_default_trap():
    """Pins the premise of role_harness_missing: RoleConfig() is harness-kind
    with no harness (core/models.py), so `role: {}` is not `role` absent."""
    empty = RoleConfig()
    assert empty.kind == "harness"
    assert empty.harness is None
    assert HarnessKind.OPENCODE.value == "opencode"
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_validate_config.py -q`

Expected: FAIL at collection with `ImportError: cannot import name 'ADR6_COMBINATION_CAP' from 'sdlc.graph.validate'`.

- [ ] **Step 3: Implement**

In `src/sdlc/graph/validate.py` (edit 1 of 5), replace exactly:

```python

from collections import Counter
```

with:

```python

import itertools
import math
from collections import Counter
```

In `src/sdlc/graph/validate.py` (edit 2 of 5), replace exactly:

```python
    INCOMPATIBLE_PORTS = "incompatible_ports"
    # T5 topology
```

with:

```python
    INCOMPATIBLE_PORTS = "incompatible_ports"
    # T3 node configuration
    ROLE_ON_ROLELESS_TYPE = "role_on_roleless_type"
    GATE_ON_NON_GATE = "gate_on_non_gate"
    LOADER_OWNED_FIELD = "loader_owned_field"
    ROLE_NOT_IN_REGISTRY = "role_not_in_registry"
    ROLE_KIND_MISMATCH = "role_kind_mismatch"
    ROLE_HARNESS_MISSING = "role_harness_missing"
    RESEARCH_PROVIDER_MISSING = "research_provider_missing"
    ADR6_VIOLATION = "adr6_violation"
    ADR6_COMBINATIONS_EXCEEDED = "adr6_combinations_exceeded"
    RESERVED_GATE_NAME = "reserved_gate_name"
    # T5 topology
```

In `src/sdlc/graph/validate.py` (edit 3 of 5), replace exactly:

```python
    UNREACHABLE_NODE = "unreachable_node"
```

with:

```python
    UNREACHABLE_NODE = "unreachable_node"


# Gate names that handlers use OUTSIDE graphs (spec §3, §7.3). A gate node's
# name is its id (E-72 D7) and shares PipelineConfig.gates[...] and the signal
# namespace with these, so a graph gate may not take one. E-74 removes
# "merge"/"deploy" when those gates become nodes. "research", "architecture"
# and "plan" are deliberately absent: graph gate nodes take them over.
RESERVED_GATE_NAMES: frozenset[str] = frozenset(
    {
        "budget",
        "clarify",
        "crew_question",
        "deploy",
        "deploy_failed",
        "merge",
        "readiness",
        "risk",
        "tidy_up",
        "tool_approval",
    }
)

# Fail closed past this many role->model combinations (spec §7.4).
ADR6_COMBINATION_CAP = 256
```

In `src/sdlc/graph/validate.py` (edit 4 of 5), replace exactly:

```python

def _topology_problems(graph: PipelineGraph, node_ids: list[str]) -> list[Problem]:
```

with:

```python

def _node_config_problems(
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
    roles: Mapping[str, RoleConfig],
) -> list[Problem]:
    """T3 (spec §7.2): E-72 §5's deferred node-configuration list."""
    problems: list[Problem] = []

    def add(code: ProblemCode, node_id: str, message: str) -> None:
        problems.append(Problem(code=code, node=node_id, message=message))

    for node_id, n in nodes.items():
        spec = registry.get(n.type)
        if spec is None:
            continue  # unknown_node_type already reported; nothing to resolve against
        if spec.kind == "gate" and node_id in RESERVED_GATE_NAMES:
            add(
                ProblemCode.RESERVED_GATE_NAME,
                node_id,
                f"gate node id {node_id!r} is a gate name handlers use outside graphs",
            )
        if n.gate is not None and spec.kind != "gate":
            add(ProblemCode.GATE_ON_NON_GATE, node_id, f"{n.type!r} is not a gate type")
        if n.role is not None and (n.role.instructions is not None or n.role.tool_files):
            add(
                ProblemCode.LOADER_OWNED_FIELD,
                node_id,
                "role.instructions and role.tool_files are loaded from agents/<role>/, "
                "never set on a node",
            )
        if spec.role is None:
            if n.role is not None:
                add(ProblemCode.ROLE_ON_ROLELESS_TYPE, node_id, f"{n.type!r} has no role")
            continue
        if spec.role not in roles:
            add(
                ProblemCode.ROLE_NOT_IN_REGISTRY,
                node_id,
                f"{n.type!r} needs role {spec.role!r}, which the loaded registry lacks",
            )
            continue
        if n.role is None:
            continue
        expected = roles[spec.role].kind
        if n.role.kind != expected:
            add(
                ProblemCode.ROLE_KIND_MISMATCH,
                node_id,
                f"role override kind {n.role.kind!r} != registry {spec.role!r} kind "
                f"{expected!r} (an empty `role: {{}}` defaults to 'harness')",
            )
        elif n.role.kind == "harness" and n.role.harness is None:
            add(
                ProblemCode.ROLE_HARNESS_MISSING,
                node_id,
                "a harness-kind role override must name a harness",
            )
        elif n.role.kind == "research" and n.role.provider is None:
            add(
                ProblemCode.RESEARCH_PROVIDER_MISSING,
                node_id,
                "a research-kind role override must name a provider",
            )
    return problems + _adr6_problems(nodes, registry, roles)


def _adr6_problems(
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
    roles: Mapping[str, RoleConfig],
) -> list[Problem]:
    """ADR-6 over graphs (spec U4, §7.4): the registry's role->model map with
    every graph-used role replaced by the SET of its nodes' effective models
    (mirrors cli_roles.build_role_overrides), then the existing
    validate_run_roles over every combination."""
    from ..agents.loader import RegistryError, validate_run_roles

    models: dict[str, set[str]] = {r: {c.model} for r, c in roles.items() if c.model is not None}
    used: dict[str, set[str]] = {}
    for n in nodes.values():
        spec = registry.get(n.type)
        if spec is None or spec.role is None or spec.role not in roles:
            continue
        model = (n.role.model if n.role is not None else None) or roles[spec.role].model
        if model is not None:
            used.setdefault(spec.role, set()).add(model)
    models.update(used)
    names = sorted(models)
    choices = [sorted(models[r]) for r in names]
    total = math.prod(len(c) for c in choices)
    if total > ADR6_COMBINATION_CAP:
        return [
            Problem(
                code=ProblemCode.ADR6_COMBINATIONS_EXCEEDED,
                message=f"{total} role->model combinations exceed the ADR-6 check cap "
                f"of {ADR6_COMBINATION_CAP}",
            )
        ]
    messages: set[str] = set()
    for combo in itertools.product(*choices):
        try:
            validate_run_roles(dict(zip(names, combo, strict=True)))
        except RegistryError as exc:
            messages.add(str(exc))
    return [Problem(code=ProblemCode.ADR6_VIOLATION, message=m) for m in sorted(messages)]


def _topology_problems(graph: PipelineGraph, node_ids: list[str]) -> list[Problem]:
```

In `src/sdlc/graph/validate.py` (edit 5 of 5), replace exactly:

```python
    references = _reference_problems(graph, nodes, registry)
    problems = identity + references
    suppress_topology = any(
```

with:

```python
    references = _reference_problems(graph, nodes, registry)
    problems = identity + references + _node_config_problems(nodes, registry, roles)
    suppress_topology = any(
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_validate_config.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **171 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 validate -- node config, ADR-6 over graphs

T3: role/gate placement, loader-owned fields, registry presence (a
problem, never KeyError), kind consistency including both role: {}
traps, research provider. ADR-6 over graphs (E72-OQ-1, cross-product):
the registry role->model map with graph-used roles replaced by the set
of effective models, validate_run_roles over every combination, capped
at 256. Reserved handler gate names (E72-OQ-2, E-73 half).
```

```bash
git add tests/graph/test_graph_validate_config.py
git add src/sdlc/graph/validate.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 5: Validator T4 — wiring rules and the `ProblemCode` catalogue

**Files:**
- Modify: `src/sdlc/graph/validate.py`
- Create: `tests/graph/test_graph_validate_wiring.py`, `tests/graph/test_graph_validate_catalogue.py`

**Interfaces:**
- Consumes: Task 4's `validate.py`.
- Produces: `ProblemCode` T4 members (the enum is now closed and complete: 25 members); the catalogue meta-test that fails for any future code without a table row.

- [ ] **Step 1: Write the tests (and test fixtures)**

Create `tests/graph/test_graph_validate_wiring.py`:

```python
"""E-73 validate.py T4 wiring (spec §7.2): the preconditions the router's
readiness, invalidation and exclusive-merge semantics rely on."""

from __future__ import annotations

from sdlc.graph.validate import ProblemCode, ValidationReport, validate
from tests.graph.fixtures.registries import (
    FIX_LOOP,
    GENERIC,
    edge,
    fix_loop_graph,
    graph,
    node,
    roles,
)

C = ProblemCode


def _check(nodes, edges) -> ValidationReport:
    return validate(graph([node("start", "start"), *nodes], edges), GENERIC, roles=roles())


def _hits(report: ValidationReport, code: ProblemCode) -> list[tuple]:
    return [(p.node, p.port, p.edge) for p in report.problems if p.code is code]


def test_fix_loop_fixture_is_clean():
    report = validate(fix_loop_graph(2, 2), FIX_LOOP, roles=roles())
    assert report.problems == ()
    assert report.topology is not None
    wiring = report.topology.in_ports["coder"]["guidance"]
    assert wiring.back_edges == ("qa.fail->coder.guidance", "task.revise->coder.guidance")


def test_required_in_port_unconnected():
    report = _check([node("s", "sink")], [])
    assert _hits(report, C.REQUIRED_IN_PORT_UNCONNECTED) == [("s", "art", None)]


def test_required_in_port_fed_only_by_a_loop_edge_is_unconnected():
    """A back edge alone would deadlock at round 1 (spec §7.2 T4)."""
    report = _check(
        [node("w", "work"), node("r", "retry")],
        [edge("start.ok", "w.trigger"), edge("r.redo", "r.again", bound=2)],
    )
    assert ("r", "trigger", None) in _hits(report, C.REQUIRED_IN_PORT_UNCONNECTED)


def test_lone_gate_yields_exactly_one_problem():
    report = validate(graph([node("g", "gate.art")], []), GENERIC, roles=roles())
    assert [p.code for p in report.problems] == [C.REQUIRED_IN_PORT_UNCONNECTED]


def test_mixed_in_port():
    report = _check(
        [node("w", "work"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revise", "w.guidance", bound=2),
            edge("g.approve", "w.guidance"),  # incompatible AND forward: mixes with the loop
        ],
    )
    assert _hits(report, C.MIXED_IN_PORT) == [("w", "guidance", None)]


def test_back_port_not_exclusive():
    report = _check(
        [node("w", "work"), node("g", "gate.art"), node("x", "work")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revise", "w.guidance", bound=2),
            edge("g.revise", "x.guidance"),
            edge("start.ok", "x.trigger"),
        ],
    )
    assert _hits(report, C.BACK_PORT_NOT_EXCLUSIVE) == [("g", "revise", None)]


def test_back_edge_into_many():
    report = _check(
        [node("w", "work"), node("c", "collect"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "c.items"),
            edge("c.done", "g.artifact"),  # incompatible; irrelevant here
            edge("g.approve", "c.items", bound=1),
        ],
    )
    assert _hits(report, C.BACK_EDGE_INTO_MANY) == [(None, None, ("g", "approve", "c", "items"))]


def test_one_port_multiple_sources_rejects_two_nodes():
    report = _check(
        [node("a", "work"), node("b", "work"), node("s", "sink")],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "s.art"),
            edge("b.out", "s.art"),
        ],
    )
    assert _hits(report, C.ONE_PORT_MULTIPLE_SOURCES) == [("s", "art", None)]


def test_one_port_fed_by_distinct_ports_of_one_node_is_legal():
    """The §6.4 exclusive merge: mutually exclusive by one-port-per-activation."""
    report = _check(
        [node("br", "brancher"), node("m", "sink")],
        [edge("start.ok", "br.trigger"), edge("br.left", "m.art"), edge("br.right", "m.art")],
    )
    assert report.problems == ()


def test_many_port_accepts_several_sources():
    report = _check(
        [node("a", "work"), node("b", "work"), node("c", "collect")],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "c.items"),
            edge("b.out", "c.items"),
        ],
    )
    assert report.problems == ()


def test_duplicated_edge_is_reported_once():
    """Spec §7.1 (skeptic F6): a duplicate is skipped by T4, yet still counts
    as connecting its required in-port."""
    report = _check(
        [node("w", "work"), node("s", "sink")],
        [edge("start.ok", "w.trigger"), edge("w.out", "s.art"), edge("w.out", "s.art", bound=2)],
    )
    assert [p.code for p in report.problems] == [C.DUPLICATE_EDGE]


def test_unresolved_out_port_does_not_trip_back_port_exclusivity():
    report = _check(
        [node("w", "work"), node("g", "gate.art")],
        [
            edge("start.ok", "w.trigger"),
            edge("w.out", "g.artifact"),
            edge("g.revize", "w.guidance", bound=2),
            edge("g.revize", "g.artifact"),
        ],
    )
    assert _hits(report, C.BACK_PORT_NOT_EXCLUSIVE) == []
    assert C.UNKNOWN_PORT in [p.code for p in report.problems]
```

Create `tests/graph/test_graph_validate_catalogue.py`:

```python
"""E-73 ProblemCode catalogue (spec §7.2, §8): ONE table row per code, plus a
meta-test that the table covers the whole closed enum. A new code without a
row fails here, so E-76 never renders a code no test can produce."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sdlc.graph import NODE_TYPES
from sdlc.graph.model import PipelineGraph
from sdlc.graph.validate import ProblemCode, validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

C = ProblemCode
_START = node("start", "start")


def _g(*nodes, edges=()) -> PipelineGraph:
    return graph([_START, *nodes], list(edges))


def _builder(id_: str, model: str):
    return node(id_, "builder", role={"kind": "harness", "harness": "opencode", "model": model})


# code -> (graph, registry, roles)
ROWS: dict[ProblemCode, Callable[[], tuple]] = {
    C.DUPLICATE_NODE_ID: lambda: (_g(node("start", "sink")), GENERIC, roles()),
    C.DUPLICATE_EDGE: lambda: (
        _g(node("w", "work"), edges=[edge("start.ok", "w.trigger")] * 2),
        GENERIC,
        roles(),
    ),
    C.DANGLING_ENDPOINT: lambda: (_g(edges=[edge("start.ok", "ghost.trigger")]), GENERIC, roles()),
    C.UNKNOWN_NODE_TYPE: lambda: (_g(node("x", "nope")), GENERIC, roles()),
    C.UNKNOWN_PORT: lambda: (
        _g(node("w", "work"), edges=[edge("start.nope", "w.trigger")]),
        GENERIC,
        roles(),
    ),
    C.INCOMPATIBLE_PORTS: lambda: (
        _g(node("s", "sink"), edges=[edge("start.ok", "s.art")]),
        GENERIC,
        roles(),
    ),
    C.ROLE_ON_ROLELESS_TYPE: lambda: (
        _g(node("w", "work", role={"kind": "proposer"})),
        GENERIC,
        roles(),
    ),
    C.GATE_ON_NON_GATE: lambda: (_g(node("w", "work", gate={})), GENERIC, roles()),
    C.LOADER_OWNED_FIELD: lambda: (
        _g(
            node(
                "b",
                "builder",
                role={"kind": "harness", "harness": "opencode", "tool_files": ["t.py"]},
            )
        ),
        GENERIC,
        roles(),
    ),
    C.ROLE_NOT_IN_REGISTRY: lambda: (
        graph([node("intake", "intake"), node("r", "research")], []),
        NODE_TYPES,
        roles(research=None),
    ),
    C.ROLE_KIND_MISMATCH: lambda: (
        graph([node("intake", "intake"), node("a", "architect", role={})], []),
        NODE_TYPES,
        roles(),
    ),
    C.ROLE_HARNESS_MISSING: lambda: (_g(node("b", "builder", role={})), GENERIC, roles()),
    C.RESEARCH_PROVIDER_MISSING: lambda: (
        graph([node("intake", "intake"), node("r", "research", role={"kind": "research"})], []),
        NODE_TYPES,
        roles(),
    ),
    C.ADR6_VIOLATION: lambda: (_g(_builder("b", "anthropic:x")), GENERIC, roles()),
    C.ADR6_COMBINATIONS_EXCEEDED: lambda: (
        _g(*(_builder(f"b{i}", f"f{i}:m") for i in range(300))),
        GENERIC,
        roles(),
    ),
    C.RESERVED_GATE_NAME: lambda: (_g(node("merge", "gate.art")), GENERIC, roles()),
    C.REQUIRED_IN_PORT_UNCONNECTED: lambda: (_g(node("s", "sink")), GENERIC, roles()),
    C.MIXED_IN_PORT: lambda: (
        _g(
            node("w", "work"),
            node("g", "gate.art"),
            edges=[
                edge("start.ok", "w.trigger"),
                edge("w.out", "g.artifact"),
                edge("g.revise", "w.guidance", bound=1),
                edge("g.approve", "w.guidance"),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.BACK_PORT_NOT_EXCLUSIVE: lambda: (
        _g(
            node("w", "work"),
            node("g", "gate.art"),
            edges=[
                edge("start.ok", "w.trigger"),
                edge("w.out", "g.artifact"),
                edge("g.revise", "w.guidance", bound=1),
                edge("g.revise", "g.artifact"),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.BACK_EDGE_INTO_MANY: lambda: (
        _g(
            node("w", "work"),
            node("c", "collect"),
            edges=[
                edge("start.ok", "w.trigger"),
                edge("w.out", "c.items"),
                edge("c.done", "c.items", bound=1),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.ONE_PORT_MULTIPLE_SOURCES: lambda: (
        _g(
            node("a", "work"),
            node("b", "work"),
            node("s", "sink"),
            edges=[
                edge("start.ok", "a.trigger"),
                edge("start.ok", "b.trigger"),
                edge("a.out", "s.art"),
                edge("b.out", "s.art"),
            ],
        ),
        GENERIC,
        roles(),
    ),
    C.FORWARD_CYCLE: lambda: (
        _g(node("r", "retry"), edges=[edge("start.ok", "r.trigger"), edge("r.redo", "r.again")]),
        GENERIC,
        roles(),
    ),
    C.BOUNDED_EDGE_NOT_A_LOOP: lambda: (
        _g(node("w", "work"), edges=[edge("start.ok", "w.trigger", bound=1)]),
        GENERIC,
        roles(),
    ),
    C.ENTRY_COUNT: lambda: (graph([], []), GENERIC, roles()),
    C.UNREACHABLE_NODE: lambda: (
        _g(
            node("a", "work"),
            node("b", "sink"),
            edges=[edge("a.out", "b.art"), edge("b.done", "a.trigger")],
        ),
        GENERIC,
        roles(),
    ),
}


def test_every_problem_code_has_a_row():
    assert set(ROWS) == set(ProblemCode)


@pytest.mark.parametrize("code", sorted(ROWS, key=lambda c: c.value), ids=lambda c: c.value)
def test_row_produces_its_code(code):
    g, registry, role_map = ROWS[code]()
    report = validate(g, registry, roles=role_map)
    assert code in {p.code for p in report.problems}
    assert report.topology is None


def test_codes_are_stable_snake_case_strings():
    """E-76 generates its TypeScript union from these values."""
    for code in ProblemCode:
        assert code.value == code.name.lower()
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_validate_wiring.py tests/graph/test_graph_validate_catalogue.py -q`

Expected: FAIL at collection with `AttributeError: type object 'ProblemCode' has no attribute 'REQUIRED_IN_PORT_UNCONNECTED'`.

- [ ] **Step 3: Implement**

In `src/sdlc/graph/validate.py` (edit 1 of 4), replace exactly:

```python
from enum import StrEnum
```

with:

```python
from enum import StrEnum
from typing import Literal
```

In `src/sdlc/graph/validate.py` (edit 2 of 4), replace exactly:

```python
    RESERVED_GATE_NAME = "reserved_gate_name"
    # T5 topology
```

with:

```python
    RESERVED_GATE_NAME = "reserved_gate_name"
    # T4 wiring (router preconditions)
    REQUIRED_IN_PORT_UNCONNECTED = "required_in_port_unconnected"
    MIXED_IN_PORT = "mixed_in_port"
    BACK_PORT_NOT_EXCLUSIVE = "back_port_not_exclusive"
    BACK_EDGE_INTO_MANY = "back_edge_into_many"
    ONE_PORT_MULTIPLE_SOURCES = "one_port_multiple_sources"
    # T5 topology
```

In `src/sdlc/graph/validate.py` (edit 3 of 4), replace exactly:

```python

def _topology_problems(graph: PipelineGraph, node_ids: list[str]) -> list[Problem]:
```

with:

```python

def _wiring_problems(
    graph: PipelineGraph,
    nodes: Mapping[str, GraphNode],
    registry: Mapping[str, NodeTypeSpec],
) -> list[Problem]:
    """T4 (spec §7.2): the preconditions the router's semantics rely on.

    An edge takes part on a side only where that side's port resolves.
    Duplicated 4-tuples (already `duplicate_edge`) never take part in the
    classification rules -- their bounds may disagree -- but they still
    count as connecting a required in-port, so a duplicate is reported once."""
    counts = Counter(edge_key(e) for e in graph.edges)
    duplicated = {k for k, c in counts.items() if c > 1}

    def resolves(node_id: str, port: str, direction: Literal["in", "out"]) -> bool:
        spec = _spec_of(nodes, registry, node_id)
        return spec is not None and find_port(spec, port, direction) is not None

    problems: list[Problem] = []
    for node_id, n in nodes.items():
        spec = registry.get(n.type)
        if spec is None:
            continue
        for port in sorted((p for p in spec.ports if p.direction == "in"), key=lambda p: p.name):
            incoming = [
                e for e in graph.edges if e.target == node_id and e.target_port == port.name
            ]
            classified = [e for e in incoming if edge_key(e) not in duplicated]
            forward = [e for e in classified if not is_back_edge(e)]
            back = [e for e in classified if is_back_edge(e)]
            connected_by_duplicate = len(classified) < len(incoming)
            if port.required and not forward and not connected_by_duplicate:
                problems.append(
                    Problem(
                        code=ProblemCode.REQUIRED_IN_PORT_UNCONNECTED,
                        node=node_id,
                        port=port.name,
                        message=f"required in-port {node_id}.{port.name} has no forward "
                        f"(unbounded) in-edge",
                    )
                )
            if forward and back:
                problems.append(
                    Problem(
                        code=ProblemCode.MIXED_IN_PORT,
                        node=node_id,
                        port=port.name,
                        message=f"in-port {node_id}.{port.name} mixes forward and loop in-edges",
                    )
                )
            if port.multiplicity == "many":
                for e in back:
                    problems.append(
                        Problem(
                            code=ProblemCode.BACK_EDGE_INTO_MANY,
                            edge=edge_key(e),
                            message=f"loop edge {edge_id(e)} targets a collect (many) port",
                        )
                    )
            elif len({e.source for e in forward}) > 1:
                problems.append(
                    Problem(
                        code=ProblemCode.ONE_PORT_MULTIPLE_SOURCES,
                        node=node_id,
                        port=port.name,
                        message=f"in-port {node_id}.{port.name} takes one token but is fed by "
                        f"{_names({e.source for e in forward})}; only distinct out-ports of "
                        f"ONE node are mutually exclusive",
                    )
                )
    by_out_port: dict[tuple[str, str], list[GraphEdge]] = {}
    for e in graph.edges:
        if edge_key(e) not in duplicated and resolves(e.source, e.source_port, "out"):
            by_out_port.setdefault((e.source, e.source_port), []).append(e)
    for (source, source_port), edges in sorted(by_out_port.items()):
        if len(edges) > 1 and any(is_back_edge(e) for e in edges):
            problems.append(
                Problem(
                    code=ProblemCode.BACK_PORT_NOT_EXCLUSIVE,
                    node=source,
                    port=source_port,
                    message=f"out-port {source}.{source_port} carries a loop edge, so it must "
                    f"carry no other edge",
                )
            )
    return problems


def _topology_problems(graph: PipelineGraph, node_ids: list[str]) -> list[Problem]:
```

In `src/sdlc/graph/validate.py` (edit 4 of 4), replace exactly:

```python
    references = _reference_problems(graph, nodes, registry)
    problems = identity + references + _node_config_problems(nodes, registry, roles)
    suppress_topology = any(
```

with:

```python
    references = _reference_problems(graph, nodes, registry)
    problems = (
        identity
        + references
        + _node_config_problems(nodes, registry, roles)
        + _wiring_problems(graph, nodes, registry)
    )
    suppress_topology = any(
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_validate_wiring.py tests/graph/test_graph_validate_catalogue.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **210 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 validate -- wiring rules, ProblemCode catalogue

T4 router preconditions: required in-ports need a forward edge, no
port mixes forward and loop edges, a loop out-port carries only its loop
edge, no loop edge into a collect port, a one-port takes several forward
edges only from distinct ports of one node. Duplicates count as
connecting but never classify. One catalogue row per ProblemCode plus a
coverage meta-test.
```

```bash
git add tests/graph/test_graph_validate_wiring.py
git add tests/graph/test_graph_validate_catalogue.py
git add src/sdlc/graph/validate.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 6: Router — state, forward semantics, collect, exclusive merge, REJECTED, activation checks

**Files:**
- Create: `src/sdlc/graph/router.py`
- Create: `tests/graph/fixtures/routing.py`, `tests/graph/test_graph_router.py`
- Modify: `tests/graph/test_graph_purity.py`

**Interfaces:**
- Consumes: `Topology`, `PortWiring` (Task 2); `gate_key` (`sdlc.core.models`); `validate` (Task 3, tests only).
- Produces: `RouterError`; frozen models `NodeState(round, status, taken_port)`, `Token(payload_ref, producer)`, `LiveActivation(activation_id, node_id, unavailable_ports)`, `Emission`, `Dropped(activation_id, port, reason)`, `RouterState(nodes, slots, traversals, live, retired, emissions, dropped, outcome, reason)`, `Emitted(kind="emitted", activation_id, port, payload_ref)`, `Activation(activation_id, node_id, round, inputs, unavailable_ports)`, `Step(state, activations, cancelled, outcome, reason)`; `GraphRouter(topology)` with `.topology`, `start() -> Step`, `advance(state, event) -> Step`. Private helpers Task 7 extends: `_Work`, `_terminate`, `_settle`, `_edge_dead`. Test driver `tests.graph.fixtures.routing.Run(graph, registry, role_map=None)` with `.state`, `.last`, `.emit(activation_id, port, ref=None) -> Step`, `.issued()`, `.activation(id)`, `.live()`.

> In this task a bounded edge is not yet special: `advance` delivers into its slot like a forward edge and `unavailable_ports` is always `{}`. No test in this task uses a bounded edge; Task 7 replaces both.

- [ ] **Step 1: Write the tests (and test fixtures)**

Create `tests/graph/fixtures/routing.py`:

```python
"""A scripted driver for GraphRouter table tests (spec §8).

`Run` validates a graph, starts a router over its Topology, and threads the
state through each `emit`. It records every Step so tables can assert on the
sequence of issued activations, cancellations and outcomes.
"""

from __future__ import annotations

from collections.abc import Mapping

from sdlc.core.models import RoleConfig
from sdlc.graph.model import PipelineGraph
from sdlc.graph.node_types import NodeTypeSpec
from sdlc.graph.router import Activation, Emitted, GraphRouter, RouterState, Step
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import roles


class Run:
    def __init__(
        self,
        graph: PipelineGraph,
        registry: Mapping[str, NodeTypeSpec],
        role_map: Mapping[str, RoleConfig] | None = None,
    ) -> None:
        report = validate(graph, registry, roles=role_map if role_map is not None else roles())
        assert report.topology is not None, [p.message for p in report.problems]
        self.router = GraphRouter(report.topology)
        self.steps: list[Step] = [self.router.start()]

    @property
    def state(self) -> RouterState:
        return self.steps[-1].state

    @property
    def last(self) -> Step:
        return self.steps[-1]

    def emit(self, activation_id: str, port: str, ref: str | None = None) -> Step:
        event = Emitted(
            activation_id=activation_id,
            port=port,
            payload_ref=ref if ref is not None else f"{activation_id}:{port}",
        )
        step = self.router.advance(self.state, event)
        self.steps.append(step)
        return step

    def issued(self) -> list[str]:
        return [a.activation_id for s in self.steps for a in s.activations]

    def activation(self, activation_id: str) -> Activation:
        return next(
            a
            for s in reversed(self.steps)
            for a in s.activations
            if a.activation_id == activation_id
        )

    def live(self) -> list[str]:
        return [a.activation_id for a in self.state.live]
```

Create `tests/graph/test_graph_router.py`:

```python
"""E-73 GraphRouter forward semantics (spec §6.1-§6.4, §6.6): branching,
static fan-out/collect, exclusive merge, readiness, sinks, REJECTED and the
activation-check taxonomy. Loops live in test_graph_router_loops.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.graph import from_yaml
from sdlc.graph.node_types import NODE_TYPES
from sdlc.graph.router import (
    Emitted,
    GraphRouter,
    NodeState,
    RouterError,
    RouterState,
    Token,
)
from tests.graph.fixtures.registries import GENERIC, edge, graph, node
from tests.graph.fixtures.routing import Run

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _chain() -> Run:
    return Run(
        graph(
            [node("start", "start"), node("w", "work"), node("s", "sink")],
            [edge("start.ok", "w.trigger"), edge("w.out", "s.art")],
        ),
        GENERIC,
    )


# ---- (1) happy paths -----------------------------------------------------------


def test_start_issues_the_entry_at_round_one():
    run = _chain()
    step = run.last
    assert [a.activation_id for a in step.activations] == ["start#1"]
    assert step.activations[0].round == 1
    assert step.activations[0].inputs == {}
    assert step.outcome == "running"


def test_chain_runs_to_completed_and_passes_payload_refs():
    run = _chain()
    run.emit("start#1", "ok", "r0")
    assert run.activation("w#1").inputs == {"trigger": "r0"}
    run.emit("w#1", "out", "art1")
    assert run.activation("s#1").inputs == {"art": "art1"}
    step = run.emit("s#1", "done")  # edgeless out-port: a sink
    assert step.activations == ()
    assert step.outcome == "completed"
    assert run.issued() == ["start#1", "w#1", "s#1"]


def test_e72_fixture_happy_path():
    from tests.graph.fixtures.registries import roles

    run = Run(from_yaml(FIXTURE.read_text(encoding="utf-8")), NODE_TYPES, roles())
    run.emit("intake#1", "ok")
    run.emit("researcher#1", "brief")
    assert run.live() == ["research#1"]
    assert run.activation("research#1").unavailable_ports == {}
    run.emit("research#1", "approve")
    run.emit("clarifier#1", "requirements", "reqs")
    assert run.activation("architect#1").inputs == {"requirements": "reqs"}
    run.emit("architect#1", "spec", "spec1")
    run.emit("architecture#1", "approve", "spec1")
    assert run.activation("planner#1").inputs == {"requirements": "reqs", "spec": "spec1"}
    run.emit("planner#1", "plan")
    step = run.emit("plan#1", "approve")  # plan.approve is a sink in the fixture
    assert step.outcome == "completed"


def test_state_is_json_round_trippable():
    run = _chain()
    run.emit("start#1", "ok")
    state = run.state
    assert RouterState.model_validate_json(state.model_dump_json()) == state


# ---- branching: one out-port per activation --------------------------------------


def _branch() -> Run:
    return Run(
        graph(
            [
                node("start", "start"),
                node("br", "brancher"),
                node("l", "sink"),
                node("r", "sink"),
                node("after", "opt2"),
            ],
            [
                edge("start.ok", "br.trigger"),
                edge("br.left", "l.art"),
                edge("br.right", "r.art"),
                edge("br.left", "after.a"),
                edge("br.right", "after.b"),
            ],
        ),
        GENERIC,
    )


def test_untaken_branch_dies_and_optional_ports_do_not_wait_for_dead_edges():
    run = _branch()
    run.emit("start#1", "ok")
    step = run.emit("br#1", "left", "L")
    assert [a.activation_id for a in step.activations] == ["after#1", "l#1"]
    assert run.state.nodes["r"].status == "dead"
    assert run.activation("after#1").inputs == {"a": "L"}  # port b is DEAD, not waited for


def test_optional_ports_wait_for_every_live_edge():
    """Spec §6.3: optional means 'may be absent', not 'don't wait'."""
    run = Run(
        graph(
            [node("start", "start"), node("a", "work"), node("b", "work"), node("j", "opt2")],
            [
                edge("start.ok", "a.trigger"),
                edge("start.ok", "b.trigger"),
                edge("a.out", "j.a"),
                edge("b.out", "j.b"),
            ],
        ),
        GENERIC,
    )
    step = run.emit("start#1", "ok")
    assert [a.activation_id for a in step.activations] == ["a#1", "b#1"]  # static fan-out
    assert run.emit("a#1", "out", "A").activations == ()
    step = run.emit("b#1", "out", "B")
    assert [a.activation_id for a in step.activations] == ["j#1"]
    assert run.activation("j#1").inputs == {"a": "A", "b": "B"}


def test_node_with_all_fed_ports_dead_is_dead_and_run_completes():
    run = _branch()
    run.emit("start#1", "ok")
    run.emit("br#1", "left")
    run.emit("l#1", "done")
    step = run.emit("after#1", "done")
    assert step.outcome == "completed"
    assert run.state.nodes["r"].status == "dead"


# ---- (7)/(11) static fan-out and many-collect -------------------------------------


def _collect() -> Run:
    return Run(
        graph(
            [
                node("start", "start"),
                node("fast", "work"),
                node("slow", "work"),
                node("br", "brancher"),
                node("c", "collect"),
            ],
            [
                edge("start.ok", "fast.trigger"),
                edge("start.ok", "slow.trigger"),
                edge("start.ok", "br.trigger"),
                edge("fast.out", "c.items"),
                edge("slow.out", "c.items"),
                edge("br.left", "c.items"),
            ],
        ),
        GENERIC,
    )


def test_many_collector_waits_for_the_slow_branch():
    """Skeptic F2: FILLED on a many port needs EVERY forward in-edge resolved."""
    run = _collect()
    run.emit("start#1", "ok")
    assert run.emit("fast#1", "out", "F").activations == ()
    assert run.emit("br#1", "left", "L").activations == ()
    step = run.emit("slow#1", "out", "S")
    assert [a.activation_id for a in step.activations] == ["c#1"]


def test_many_inputs_are_ordered_by_edge_id_not_arrival():
    run = _collect()
    run.emit("start#1", "ok")
    run.emit("slow#1", "out", "S")
    run.emit("br#1", "left", "L")
    run.emit("fast#1", "out", "F")
    # br.left->c.items < fast.out->c.items < slow.out->c.items
    assert run.activation("c#1").inputs == {"items": ("L", "F", "S")}


def test_many_collector_skips_a_dead_branch():
    run = _collect()
    run.emit("start#1", "ok")
    run.emit("br#1", "right")  # br.left edge is dead
    run.emit("fast#1", "out", "F")
    run.emit("slow#1", "out", "S")
    assert run.activation("c#1").inputs == {"items": ("F", "S")}


def test_many_collector_with_every_edge_dead_is_dead():
    run = Run(
        graph(
            [node("start", "start"), node("br", "brancher"), node("c", "collect")],
            [edge("start.ok", "br.trigger"), edge("br.left", "c.items")],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok")
    step = run.emit("br#1", "right")
    assert run.state.nodes["c"].status == "dead"
    assert step.outcome == "completed"


# ---- (17) exclusive merge into a one port (reviewer R1) ---------------------------


@pytest.mark.parametrize(("taken", "other"), [("left", "right"), ("right", "left")])
def test_exclusive_merge_into_a_one_port(taken, other):
    run = Run(
        graph(
            [node("start", "start"), node("br", "brancher"), node("m", "sink")],
            [edge("start.ok", "br.trigger"), edge("br.left", "m.art"), edge("br.right", "m.art")],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok")
    step = run.emit("br#1", taken, "T")
    assert [a.activation_id for a in step.activations] == ["m#1"]
    assert run.activation("m#1").inputs == {"art": "T"}
    assert f"br.{taken}->m.art" in run.state.slots
    assert f"br.{other}->m.art" not in run.state.slots
    assert run.state.nodes["br"].taken_port == taken  # the sibling edge is dead via taken_port
    assert step.outcome == "running"
    assert run.emit("m#1", "done").outcome == "completed"  # no backstop fired


# ---- REJECTED: an emission on a gate's unconnected reject -------------------------


def _gated() -> Run:
    return Run(
        graph(
            [
                node("start", "start"),
                node("w", "work"),
                node("x", "work"),
                node("g", "gate.art"),
                node("s", "sink"),
            ],
            [
                edge("start.ok", "w.trigger"),
                edge("start.ok", "x.trigger"),
                edge("w.out", "g.artifact"),
                edge("g.approve", "s.art"),
            ],
        ),
        GENERIC,
    )


def test_gate_reject_unconnected_rejects_and_cancels_live_work():
    run = _gated()
    run.emit("start#1", "ok")
    run.emit("w#1", "out")
    step = run.emit("g#1", "reject")
    assert step.outcome == "rejected"
    assert step.reason == "g.reject"
    assert step.cancelled == ("x#1",)
    assert run.state.retired == ("x#1",)
    assert run.state.live == ()
    assert run.state.nodes["g"].status == "done"  # the rejecting emission was applied


def test_unconnected_non_reject_port_is_a_sink():
    run = _gated()
    run.emit("start#1", "ok")
    run.emit("x#1", "out")  # x.out has no edges
    assert run.last.outcome == "running"


# ---- (9)/(12) the activation-check taxonomy (skeptic F3, F9) ----------------------


def test_never_issued_ids_raise():
    run = _chain()
    for bad in ["w#1", "start#2", "start#0", "start", "ghost#1", "start#x"]:
        with pytest.raises(RouterError, match="never issued"):
            run.emit(bad, "ok")


def test_port_not_on_the_type_raises():
    run = _chain()
    with pytest.raises(RouterError, match="not an out-port"):
        run.emit("start#1", "nope")


def test_identical_duplicate_is_dropped():
    run = _chain()
    run.emit("start#1", "ok", "r0")
    step = run.emit("start#1", "ok", "r0")
    assert step.activations == ()
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [("start#1", "duplicate")]
    assert run.live() == ["w#1"]


def test_conflicting_second_emission_raises():
    run = _branch()
    run.emit("start#1", "ok")
    run.emit("br#1", "left", "L")
    with pytest.raises(RouterError, match="conflicting"):
        run.emit("br#1", "right", "L")
    with pytest.raises(RouterError, match="conflicting"):
        run.emit("br#1", "left", "other-ref")


def test_late_emission_after_rejected_is_post_terminal():
    run = _gated()
    run.emit("start#1", "ok")
    run.emit("w#1", "out")
    run.emit("g#1", "reject")
    step = run.emit("x#1", "out")
    assert step.outcome == "rejected"
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [("x#1", "post_terminal")]
    run.emit("g#1", "reject")
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [
        ("g#1", "duplicate"),  # dropped is sorted by activation id, not arrival
        ("x#1", "post_terminal"),
    ]


def test_unsupported_event_raises():
    run = _chain()
    with pytest.raises(RouterError, match="unsupported event"):
        run.router.advance(run.state, object())  # type: ignore[arg-type]


# ---- (9a)/(9b) router_invariant backstops on hand-built illegal states -------------


def test_backstop_delivery_into_an_occupied_slot():
    run = _chain()
    run.emit("start#1", "ok")
    illegal = run.state.model_copy(
        update={"slots": {"w.out->s.art": Token(payload_ref="ghost", producer="w#1")}}
    )
    step = run.router.advance(illegal, Emitted(activation_id="w#1", port="out", payload_ref="x"))
    assert step.outcome == "escalated"
    assert step.reason == "router_invariant: delivery into occupied slot w.out->s.art"


def test_backstop_two_tokens_on_a_one_port():
    run = Run(
        graph(
            [node("start", "start"), node("br", "brancher"), node("m", "sink"), node("x", "work")],
            [
                edge("start.ok", "br.trigger"),
                edge("start.ok", "x.trigger"),
                edge("br.left", "m.art"),
                edge("br.right", "m.art"),
            ],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok")
    illegal = run.state.model_copy(
        update={
            "nodes": {
                **run.state.nodes,
                "br": NodeState(round=1, status="done", taken_port="left"),
            },
            "live": tuple(a for a in run.state.live if a.node_id != "br"),
            "slots": {
                "br.left->m.art": Token(payload_ref="L", producer="br#1"),
                "br.right->m.art": Token(payload_ref="R", producer="br#1"),
            },
        }
    )
    step = run.router.advance(illegal, Emitted(activation_id="x#1", port="out", payload_ref="x"))
    assert step.outcome == "escalated"
    assert step.reason == "router_invariant: m holds two tokens on a one port"
    assert step.activations == ()


def test_router_is_pure_same_input_same_step():
    run = _chain()
    event = Emitted(activation_id="start#1", port="ok", payload_ref="r")
    a = run.router.advance(run.state, event)
    b = GraphRouter(run.router.topology).advance(run.state, event)
    assert a == b
    assert a.model_dump_json() == b.model_dump_json()
```

In `tests/graph/test_graph_purity.py` (edit 1 of 1), replace exactly:

```python
    },
    "__init__.py": {
```

with:

```python
    },
    "router.py": {STDLIB, "pydantic", "sdlc.core.models", "sdlc.graph.topology"},
    "__init__.py": {
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_router.py tests/graph/test_graph_purity.py -q`

Expected: FAIL at collection with `ModuleNotFoundError: No module named 'sdlc.graph.router'` (also expected: `test_every_module_is_covered` fails until the module exists in Step 3).

- [ ] **Step 3: Implement**

Create `src/sdlc/graph/router.py`:

```python
"""GraphRouter -- the pure control-flow core of pipeline-as-data (E-73, FR-1202).

Spec: docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
§4, §6.

A reducer: `advance(state, event) -> Step`. No Temporal, no I/O, no clock, no
async. The router never inspects payloads; `payload_ref` is opaque. It runs
only over a `Topology`, which only sdlc.graph.validate produces (spec U7).

Semantics in one breath (spec §6): an activation emits on exactly one
out-port; forward edges deliver a token into a per-edge SLOT; a back edge
(one carrying `max_traversals`) counts a traversal, invalidates REGION(target)
-- clearing every slot whose producer lies in it, cancelling live activations
in it, resetting its nodes -- and only then delivers (5b before 5c). Slots are
never cleared by activation; node status stops a second activation per
generation. Rounds and counters never reset (spec U5).

Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph.topology (spec §4; pinned by tests/graph/test_graph_purity.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..core.models import gate_key
from .topology import PortWiring, Topology

Outcome = Literal["running", "completed", "rejected", "escalated"]
Unavailable = Literal["exhausted", "target_dead"]
DropReason = Literal["stale", "duplicate", "post_terminal"]
NodeStatus = Literal["pending", "running", "done", "dead"]

_FROZEN = ConfigDict(frozen=True, extra="forbid")
_TERMINAL: tuple[Outcome, ...] = ("rejected", "escalated")


class RouterError(Exception):
    """An interpreter bug -- never an async-delivery race (spec §4, skeptic F3)."""


def _sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return dict(sorted(value.items()))


class NodeState(BaseModel):
    model_config = _FROZEN

    round: int = 0  # monotonic activation count (spec D1)
    status: NodeStatus = "pending"
    taken_port: str | None = None


class Token(BaseModel):
    model_config = _FROZEN

    payload_ref: str
    producer: str  # activation id


class LiveActivation(BaseModel):
    """An issued, unfinished activation and its issue-time snapshot of
    unavailable ports -- the contract its emission is judged by (spec §6.5)."""

    model_config = _FROZEN

    activation_id: str
    node_id: str
    unavailable_ports: dict[str, Unavailable]

    _sort = field_validator("unavailable_ports")(_sorted_dict)


class Emission(BaseModel):
    model_config = _FROZEN

    activation_id: str
    port: str
    payload_ref: str


class Dropped(BaseModel):
    model_config = _FROZEN

    activation_id: str
    port: str
    reason: DropReason


class RouterState(BaseModel):
    """Frozen, JSON-serialisable, no timestamps, no set types (spec §4)."""

    model_config = _FROZEN

    nodes: dict[str, NodeState]
    slots: dict[str, Token] = {}  # edge id -> token (occupied slots only)
    traversals: dict[str, int] = {}  # back edge id -> count
    live: tuple[LiveActivation, ...] = ()
    retired: tuple[str, ...] = ()
    emissions: tuple[Emission, ...] = ()  # applied emissions, sorted by activation id
    dropped: tuple[Dropped, ...] = ()  # sorted audit of dropped emissions
    outcome: Outcome = "running"
    reason: str | None = None

    _sort_maps = field_validator("nodes", "slots", "traversals")(_sorted_dict)

    @field_validator("live")
    @classmethod
    def _sort_live(cls, value: tuple[LiveActivation, ...]) -> tuple[LiveActivation, ...]:
        return tuple(sorted(value, key=lambda a: a.activation_id))

    @field_validator("emissions")
    @classmethod
    def _sort_emissions(cls, value: tuple[Emission, ...]) -> tuple[Emission, ...]:
        # A lookup table, not a history: sorted so that forward emissions
        # applied in either order yield equal states (spec §6.7 T2).
        return tuple(sorted(value, key=lambda e: e.activation_id))

    @field_validator("dropped")
    @classmethod
    def _sort_dropped(cls, value: tuple[Dropped, ...]) -> tuple[Dropped, ...]:
        # Sorted like every other collection (plan skeptic P1): late emissions
        # arriving in either order leave equal states.
        return tuple(sorted(value, key=lambda d: (d.activation_id, d.port, d.reason)))

    @field_validator("retired")
    @classmethod
    def _sort_retired(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))


class Emitted(BaseModel):
    """A handler's single emission. `kind` makes room for E72-OQ-4's
    `Failed` in a discriminated union without breaking this one."""

    model_config = _FROZEN

    kind: Literal["emitted"] = "emitted"
    activation_id: str
    port: str
    payload_ref: str


class Activation(BaseModel):
    model_config = _FROZEN

    activation_id: str  # gate_key(node_id, round)
    node_id: str
    round: int
    inputs: dict[str, str | tuple[str, ...]]  # in-port -> payload ref(s)
    unavailable_ports: dict[str, Unavailable]

    _sort = field_validator("inputs", "unavailable_ports")(_sorted_dict)


class Step(BaseModel):
    model_config = _FROZEN

    state: RouterState
    activations: tuple[Activation, ...]  # sorted by node id
    cancelled: tuple[str, ...]  # activation ids, sorted
    outcome: Outcome
    reason: str | None


@dataclass
class _Work:
    """Mutable scratch copy of a RouterState for one advance()."""

    nodes: dict[str, NodeState]
    slots: dict[str, Token]
    traversals: dict[str, int]
    live: dict[str, LiveActivation]
    retired: set[str]
    emissions: list[Emission]
    dropped: list[Dropped]
    outcome: Outcome
    reason: str | None

    @classmethod
    def of(cls, state: RouterState) -> _Work:
        return cls(
            nodes=dict(state.nodes),
            slots=dict(state.slots),
            traversals=dict(state.traversals),
            live={a.activation_id: a for a in state.live},
            retired=set(state.retired),
            emissions=list(state.emissions),
            dropped=list(state.dropped),
            outcome=state.outcome,
            reason=state.reason,
        )

    def freeze(self) -> RouterState:
        return RouterState(
            nodes=self.nodes,
            slots=self.slots,
            traversals=self.traversals,
            live=tuple(self.live.values()),
            retired=tuple(self.retired),
            emissions=tuple(self.emissions),
            dropped=tuple(self.dropped),
            outcome=self.outcome,
            reason=self.reason,
        )


class GraphRouter:
    def __init__(self, topology: Topology) -> None:
        self._t = topology

    @property
    def topology(self) -> Topology:
        return self._t

    # ---- public reducer ---------------------------------------------------

    def start(self) -> Step:
        """Issue `entry#1` (spec §6.1)."""
        state = RouterState(nodes={n: NodeState() for n in self._t.node_ids})
        return self._settle(_Work.of(state), cancelled=[])

    def advance(self, state: RouterState, event: Emitted) -> Step:
        """Apply one emission (spec §6.2)."""
        if not isinstance(event, Emitted):
            raise RouterError(f"unsupported event {type(event).__name__}")
        w = _Work.of(state)
        node_id = self._issued_node(w, event.activation_id)
        if event.port not in self._t.out_ports[node_id]:
            raise RouterError(
                f"{event.activation_id}: {event.port!r} is not an out-port of {node_id!r}"
            )

        # 1. activation check
        live = w.live.get(event.activation_id)
        if live is None:
            return self._not_live(w, event)

        # 2. unavailable port (issue-time snapshot): ESCALATED, emission not applied
        why = live.unavailable_ports.get(event.port)
        if why is not None:
            return self._terminate(
                w, "escalated", f"{node_id}.{event.port}: {why}", emitter=event.activation_id
            )

        # 3. done
        del w.live[event.activation_id]
        w.emissions.append(
            Emission(
                activation_id=event.activation_id, port=event.port, payload_ref=event.payload_ref
            )
        )
        w.nodes[node_id] = NodeState(
            round=w.nodes[node_id].round, status="done", taken_port=event.port
        )
        token = Token(payload_ref=event.payload_ref, producer=event.activation_id)
        edges = self._t.out_ports[node_id][event.port]

        # 4. no edges: a gate's unconnected reject ends the run; anything else is a sink
        if not edges:
            if event.port == "reject" and node_id in self._t.gate_nodes:
                return self._terminate(w, "rejected", f"{node_id}.reject", emitter=None)
            return self._settle(w, cancelled=[])

        # 6. forward edges
        for eid in edges:
            if eid in w.slots:
                return self._terminate(
                    w,
                    "escalated",
                    f"router_invariant: delivery into occupied slot {eid}",
                    emitter=None,
                )
            w.slots[eid] = token
        return self._settle(w, cancelled=[])

    # ---- step 1: ids that are not live --------------------------------------

    def _issued_node(self, w: _Work, activation_id: str) -> str:
        node_id, sep, k = activation_id.rpartition("#")
        issued = (
            sep == "#"
            and node_id in w.nodes
            and k.isdigit()
            and 1 <= int(k) <= w.nodes[node_id].round
        )
        if not issued:
            raise RouterError(f"{activation_id!r} was never issued")
        return node_id

    def _not_live(self, w: _Work, event: Emitted) -> Step:
        aid = event.activation_id
        if aid in w.retired:
            reason: DropReason = "post_terminal" if w.outcome in _TERMINAL else "stale"
            return self._drop(w, event, reason)
        applied = next((e for e in w.emissions if e.activation_id == aid), None)
        if applied is None:
            raise RouterError(f"{aid!r} is issued but neither live, retired nor finished")
        if (applied.port, applied.payload_ref) == (event.port, event.payload_ref):
            return self._drop(w, event, "duplicate")
        raise RouterError(
            f"{aid!r} already emitted {applied.port!r}/{applied.payload_ref!r}; "
            f"got a conflicting {event.port!r}/{event.payload_ref!r}"
        )

    def _drop(self, w: _Work, event: Emitted, reason: DropReason) -> Step:
        w.dropped.append(Dropped(activation_id=event.activation_id, port=event.port, reason=reason))
        return Step(
            state=w.freeze(), activations=(), cancelled=(), outcome=w.outcome, reason=w.reason
        )

    # ---- terminal outcomes -------------------------------------------------

    def _terminate(
        self,
        w: _Work,
        outcome: Outcome,
        reason: str,
        *,
        emitter: str | None,
        cancelled: list[str] | None = None,
    ) -> Step:
        others = sorted(a for a in w.live if a != emitter)
        w.retired.update(w.live)  # includes an escalating emitter: its emission was not applied
        w.live.clear()
        w.outcome = outcome
        w.reason = reason
        return Step(
            state=w.freeze(),
            activations=(),
            cancelled=tuple(sorted({*(cancelled or []), *others})),
            outcome=outcome,
            reason=reason,
        )

    # ---- step 7: readiness, deadness, issue ---------------------------------

    def _edge_dead(self, w: _Work, eid: str) -> bool:
        source, source_port = self._t.edges[eid][:2]
        ns = w.nodes[source]
        return ns.status == "dead" or (ns.status == "done" and ns.taken_port != source_port)

    def _port_state(self, w: _Work, wiring: PortWiring) -> Literal["filled", "dead", "empty"]:
        dead = [self._edge_dead(w, e) for e in wiring.forward_edges]
        filled = [e in w.slots for e in wiring.forward_edges]
        if all(dead):
            return "dead"
        if wiring.multiplicity == "one":
            return "filled" if any(filled) else "empty"
        resolved = all(f or d for f, d in zip(filled, dead, strict=True))
        return "filled" if resolved and any(filled) else "empty"

    def _fed_port_states(self, w: _Work, node_id: str) -> list[tuple[PortWiring, str]]:
        return [
            (wiring, self._port_state(w, wiring))
            for _, wiring in sorted(self._t.in_ports[node_id].items())
            if wiring.forward_edges
        ]

    def _is_dead(self, w: _Work, node_id: str) -> bool:
        states = self._fed_port_states(w, node_id)
        if not states:
            return False
        if any(wiring.required and s == "dead" for wiring, s in states):
            return True
        return all(s == "dead" for _, s in states)

    def _is_ready(self, w: _Work, node_id: str) -> bool:
        return all(
            s == "filled" if wiring.required else s in ("filled", "dead")
            for wiring, s in self._fed_port_states(w, node_id)
        )

    def _inputs(self, w: _Work, node_id: str) -> dict[str, str | tuple[str, ...]] | None:
        """None when a `one` port holds two tokens (spec §6.4 backstop)."""
        inputs: dict[str, str | tuple[str, ...]] = {}
        for name, wiring in sorted(self._t.in_ports[node_id].items()):
            occupied = sorted(
                e for e in (*wiring.forward_edges, *wiring.back_edges) if e in w.slots
            )
            if not occupied:
                continue
            if wiring.multiplicity == "many":
                inputs[name] = tuple(w.slots[e].payload_ref for e in occupied)
            elif len(occupied) > 1:
                return None
            else:
                inputs[name] = w.slots[occupied[0]].payload_ref
        return inputs

    def _settle(self, w: _Work, cancelled: list[str]) -> Step:
        # Phase A: deadness to a fixpoint (activation never changes deadness).
        changed = True
        while changed:
            changed = False
            for n in self._t.node_ids:
                if w.nodes[n].status == "pending" and self._is_dead(w, n):
                    w.nodes[n] = NodeState(round=w.nodes[n].round, status="dead")
                    changed = True
        # Phase B: every ready node, judged against the same post-A state.
        ready: list[tuple[str, dict[str, str | tuple[str, ...]]]] = []
        for n in self._t.node_ids:
            if w.nodes[n].status == "pending" and self._is_ready(w, n):
                inputs = self._inputs(w, n)
                if inputs is None:
                    return self._terminate(
                        w,
                        "escalated",
                        f"router_invariant: {n} holds two tokens on a one port",
                        emitter=None,
                        cancelled=cancelled,
                    )
                ready.append((n, inputs))
        issued: list[Activation] = []
        for n, inputs in ready:
            unavailable: dict[str, Unavailable] = {}
            round_ = w.nodes[n].round + 1
            aid = gate_key(n, round_)
            w.nodes[n] = NodeState(round=round_, status="running")
            w.live[aid] = LiveActivation(
                activation_id=aid, node_id=n, unavailable_ports=unavailable
            )
            issued.append(
                Activation(
                    activation_id=aid,
                    node_id=n,
                    round=round_,
                    inputs=inputs,
                    unavailable_ports=unavailable,
                )
            )
        w.outcome = "running" if w.live else "completed"
        w.reason = None
        return Step(
            state=w.freeze(),
            activations=tuple(issued),
            cancelled=tuple(sorted(cancelled)),
            outcome=w.outcome,
            reason=None,
        )
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_router.py tests/graph/test_graph_purity.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **235 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 router -- forward semantics and activation checks

A pure reducer over Topology: per-edge slots never cleared by
activation (skeptic F1), per-multiplicity port states with a collect
waiting for every forward edge (F2), one-port-per-activation branching
with dead-path elimination, static fan-out, exclusive merge, sinks,
REJECTED on a gate's unconnected reject. The activation-check taxonomy
is total on async races: stale / duplicate / post_terminal drops, and
RouterError only for interpreter bugs (F3). router_invariant backstops.
Loop edges are Task 7.
```

```bash
git add tests/graph/fixtures/routing.py
git add tests/graph/test_graph_router.py
git add tests/graph/test_graph_purity.py
git add src/sdlc/graph/router.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 7: Router — loops: region invalidation, counters, unavailable-port snapshots, ESCALATED

**Files:**
- Modify: `src/sdlc/graph/router.py`, `tests/graph/fixtures/routing.py`
- Create: `tests/graph/test_graph_router_loops.py`

**Interfaces:**
- Consumes: Task 6's router and `Run`.
- Produces: `GraphRouter._traverse_back`, `GraphRouter._unavailable`; scenario builders in `tests/graph/fixtures/routing.py`: `nested_loops_graph()`, `disjoint_loops_graph()`, `self_loop_graph()`, `collect_graph()`, `running_target_graph(*, dead_target_variant=False)` (all over `GENERIC`).

- [ ] **Step 1: Write the tests (and test fixtures)**

In `tests/graph/fixtures/routing.py` (edit 1 of 2), replace exactly:

```python
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import roles
```

with:

```python
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import edge, graph, node, roles
```

In `tests/graph/fixtures/routing.py` (edit 2 of 2), replace exactly:

```python
        return [a.activation_id for a in self.state.live]
```

with:

```python
        return [a.activation_id for a in self.state.live]


# ---- scenario graphs over GENERIC (spec §8 router tables and property tier) ----


def nested_loops_graph() -> PipelineGraph:
    """a -> ga (revise -> a); a -> r -> gr (revise -> r): REGION(a) contains
    the inner loop, REGION(r) does not contain ga."""
    return graph(
        [
            node("start", "start"),
            node("a", "work"),
            node("ga", "gate.art"),
            node("r", "refine"),
            node("gr", "gate.art"),
        ],
        [
            edge("start.ok", "a.trigger"),
            edge("a.out", "ga.artifact"),
            edge("a.out", "r.art"),
            edge("ga.revise", "a.guidance", bound=2),
            edge("r.out", "gr.artifact"),
            edge("gr.revise", "r.guidance", bound=2),
        ],
    )


def disjoint_loops_graph() -> PipelineGraph:
    """Two independent revise loops whose approvals meet at an optional join."""
    return graph(
        [
            node("start", "start"),
            node("a", "work"),
            node("ga", "gate.art"),
            node("b", "work"),
            node("gb", "gate.art"),
            node("j", "opt2"),
        ],
        [
            edge("start.ok", "a.trigger"),
            edge("start.ok", "b.trigger"),
            edge("a.out", "ga.artifact"),
            edge("b.out", "gb.artifact"),
            edge("ga.revise", "a.guidance", bound=1),
            edge("gb.revise", "b.guidance", bound=1),
            edge("ga.approve", "j.a"),
            edge("gb.approve", "j.b"),
        ],
    )


def self_loop_graph() -> PipelineGraph:
    """A bounded self-loop: REGION(r) = {r}."""
    return graph(
        [node("start", "start"), node("r", "retry")],
        [edge("start.ok", "r.trigger"), edge("r.redo", "r.again", bound=2)],
    )


def collect_graph() -> PipelineGraph:
    """Static fan-out to fast, slow and a brancher, collected by a many port."""
    return graph(
        [
            node("start", "start"),
            node("fast", "work"),
            node("slow", "work"),
            node("br", "brancher"),
            node("c", "collect"),
        ],
        [
            edge("start.ok", "fast.trigger"),
            edge("start.ok", "slow.trigger"),
            edge("start.ok", "br.trigger"),
            edge("fast.out", "c.items"),
            edge("slow.out", "c.items"),
            edge("br.left", "c.items"),
        ],
    )


def running_target_graph(*, dead_target_variant: bool = False) -> PipelineGraph:
    """Spec §6.7 T1 counterexample: u can become ready while v runs. The
    variant makes v wait on y behind gate g1, so v can die after u is issued
    (advisor Q3 script B, spec §6.5)."""
    nodes = [
        node("e", "start"),
        node("a", "work"),
        node("g0", "gate.art"),
        node("q", "join"),
        node("z", "work"),
        node("u", "fixer"),
    ]
    edges = [
        edge("e.ok", "a.trigger"),
        edge("e.ok", "u.trigger"),
        edge("a.out", "g0.artifact"),
        edge("g0.approve", "q.req"),
        edge("g0.reject", "z.trigger"),
        edge("v.out", "q.opt"),
        edge("q.out", "u.opt"),
        edge("u.fix", "v.guidance", bound=2),
    ]
    if not dead_target_variant:
        nodes.append(node("v", "work"))
        edges.append(edge("e.ok", "v.trigger"))
    else:  # V waits on Y, Y on gate G1 (advisor Q3 script B)
        nodes += [node("v", "refine"), node("b", "work"), node("g1", "gate.art")]
        nodes += [node("y", "refine"), node("z2", "work")]
        edges += [
            edge("e.ok", "b.trigger"),
            edge("b.out", "g1.artifact"),
            edge("g1.approve", "y.art"),
            edge("g1.reject", "z2.trigger"),
            edge("y.out", "v.art"),
        ]
    return graph(nodes, edges)
```

Create `tests/graph/test_graph_router_loops.py`:

```python
"""E-73 GraphRouter loop semantics (spec §6.2 step 5, §6.5, §6.7): region
invalidation, slot survival, traversal counters, issue-time unavailable-port
snapshots, ESCALATED, and the two reproduction claims (`_revisable_stage`,
the code fix loop)."""

from __future__ import annotations

from pathlib import Path

from sdlc.graph import from_yaml
from sdlc.graph.node_types import NODE_TYPES
from tests.graph.fixtures.registries import (
    FIX_LOOP,
    GENERIC,
    edge,
    fix_loop_graph,
    graph,
    node,
    roles,
)
from tests.graph.fixtures.routing import (
    Run,
    disjoint_loops_graph,
    nested_loops_graph,
    running_target_graph,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"


def _pre_code(*, plan_revises_architect: bool = False) -> Run:
    g = from_yaml(FIXTURE.read_text(encoding="utf-8"))
    if plan_revises_architect:
        edges = [e for e in g.edges if (e.source, e.source_port) != ("plan", "revise")]
        g = graph(list(g.nodes), [*edges, edge("plan.revise", "architect.guidance", bound=1)])
    return Run(g, NODE_TYPES, roles())


def _to_architecture_gate(run: Run) -> None:
    run.emit("intake#1", "ok")
    run.emit("researcher#1", "brief")
    run.emit("research#1", "approve")
    run.emit("clarifier#1", "requirements", "reqs")
    run.emit("architect#1", "spec", "spec1")


# ---- (2) + (10): _revisable_stage reproduction, upstream slot survival -----------


def test_architecture_revise_twice_then_final_gate():
    """max_traversals == max_gate_rounds == 2 reproduces role_host.py:237-271:
    rounds 1..2 may revise; round 3 is the final gate (revise exhausted)."""
    run = _pre_code()
    _to_architecture_gate(run)
    assert run.activation("architecture#1").unavailable_ports == {}

    step = run.emit("architecture#1", "revise", "g1")
    assert [a.activation_id for a in step.activations] == ["architect#2"]
    # Skeptic F1: clarifier's requirements survive the invalidation.
    assert run.activation("architect#2").inputs == {"guidance": "g1", "requirements": "reqs"}
    run.emit("architect#2", "spec", "spec2")
    assert run.activation("architecture#2").unavailable_ports == {}

    run.emit("architecture#2", "revise", "g2")
    assert run.activation("architect#3").inputs == {"guidance": "g2", "requirements": "reqs"}
    run.emit("architect#3", "spec", "spec3")
    assert run.activation("architecture#3").unavailable_ports == {"revise": "exhausted"}
    assert run.state.traversals == {"architecture.revise->architect.guidance": 2}

    step = run.emit("architecture#3", "approve", "spec3")
    assert run.activation("planner#1").inputs == {"requirements": "reqs", "spec": "spec3"}
    assert step.outcome == "running"


def test_emission_on_an_exhausted_port_escalates_and_late_redelivery_is_dropped():
    run = _pre_code()
    _to_architecture_gate(run)
    run.emit("architecture#1", "revise")
    run.emit("architect#2", "spec")
    run.emit("architecture#2", "revise")
    run.emit("architect#3", "spec")
    step = run.emit("architecture#3", "revise")
    assert step.outcome == "escalated"
    assert step.reason == "architecture.revise: exhausted"
    assert step.cancelled == ()  # the emitter is retired, not cancelled
    assert "architecture#3" in run.state.retired
    assert run.state.traversals == {"architecture.revise->architect.guidance": 2}  # not applied
    step = run.emit("architecture#3", "revise")
    assert step.outcome == "escalated"
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [
        ("architecture#3", "post_terminal")
    ]


# ---- (3): the code fix loop (stages/code/step.py:548-947) -------------------------


def test_fix_loop_reproduces_max_fix_attempts_and_task_gate_rounds():
    run = Run(fix_loop_graph(max_fix_attempts=2, max_gate_rounds=2), FIX_LOOP)
    run.emit("start#1", "ok", "task")

    def qa_fails(k: int) -> None:
        """The qa handler: `fail` while available, else `escalate` (spec §6.5)."""
        run.emit(f"coder#{k}", "patch", f"p{k}")
        qa = run.activation(f"qa#{k}")
        port = "escalate" if "fail" in qa.unavailable_ports else "fail"
        run.emit(qa.activation_id, port, f"issues{k}")

    # budget = max_fix_attempts + 1 = 3 attempts, then the task gate
    for k in (1, 2, 3):
        qa_fails(k)
    assert run.activation("qa#3").unavailable_ports == {"fail": "exhausted"}
    assert run.live() == ["task#1"]
    assert run.activation("coder#2").inputs == {"guidance": "issues1", "task": "task"}

    # a gate REVISE grants exactly ONE more attempt (step.py:914), twice
    for gate_round, attempt in ((1, 4), (2, 5)):
        assert run.activation(f"task#{gate_round}").unavailable_ports == {}
        run.emit(f"task#{gate_round}", "revise", f"operator{gate_round}")
        assert run.activation(f"coder#{attempt}").inputs == {
            "guidance": f"operator{gate_round}",
            "task": "task",
        }
        qa_fails(attempt)
        assert f"task#{gate_round + 1}" in run.live()

    # round 3 is past max_gate_rounds: revise is exhausted, so the handler maps
    # an operator REVISE to `reject` (spec §6.5) -- REJECTED, not ESCALATED
    assert run.activation("task#3").unavailable_ports == {"revise": "exhausted"}
    step = run.emit("task#3", "reject")
    assert step.outcome == "rejected"
    assert [a for a in run.issued() if a.startswith("coder#")] == [
        f"coder#{k}" for k in range(1, 6)
    ]


# ---- (4): an outer loop invalidates a downstream consumer --------------------------


def test_plan_revise_to_architect_invalidates_planner_but_not_clarifier_tokens():
    run = _pre_code(plan_revises_architect=True)
    _to_architecture_gate(run)
    run.emit("architecture#1", "approve", "spec1")
    run.emit("planner#1", "plan", "plan1")
    step = run.emit("plan#1", "revise", "wrong-spec")
    assert [a.activation_id for a in step.activations] == ["architect#2"]
    assert run.activation("architect#2").inputs == {
        "guidance": "wrong-spec",
        "requirements": "reqs",
    }
    slots = run.state.slots
    assert "clarifier.requirements->planner.requirements" in slots  # producer outside the region
    assert "architecture.approve->planner.spec" not in slots  # superseded artifact dropped
    assert run.state.nodes["planner"].status == "pending"
    assert run.state.nodes["planner"].round == 1  # rounds never reset


# ---- (16): the documented known limitation (spec §6.5, skeptic F4) -----------------


def test_reentered_spent_inner_loop_starts_at_its_final_gate():
    run = _pre_code(plan_revises_architect=True)
    _to_architecture_gate(run)
    for k in (1, 2):
        run.emit(f"architecture#{k}", "revise")
        run.emit(f"architect#{k + 1}", "spec")
    run.emit("architecture#3", "approve")
    run.emit("planner#1", "plan")
    run.emit("plan#1", "revise")
    run.emit("architect#4", "spec")
    assert run.activation("architecture#4").unavailable_ports == {"revise": "exhausted"}
    step = run.emit("architecture#4", "reject")  # an operator REVISE, mapped by the handler
    assert step.outcome == "rejected"
    assert step.reason == "architecture.reject"


# ---- (8): a bounded self-loop -------------------------------------------------------


def test_self_loop_emitter_is_not_cancelled_and_its_token_survives():
    run = Run(
        graph(
            [node("start", "start"), node("r", "retry")],
            [edge("start.ok", "r.trigger"), edge("r.redo", "r.again", bound=2)],
        ),
        GENERIC,
    )
    run.emit("start#1", "ok", "t")
    step = run.emit("r#1", "redo", "x1")
    assert step.cancelled == ()
    assert run.activation("r#2").inputs == {"again": "x1", "trigger": "t"}
    run.emit("r#2", "redo", "x2")
    assert run.activation("r#3").inputs == {"again": "x2", "trigger": "t"}
    assert run.activation("r#3").unavailable_ports == {"redo": "exhausted"}
    assert run.emit("r#3", "out").outcome == "completed"


# ---- (5) + stale drop: nested concurrent loops ------------------------------------


def test_outer_loop_cancels_the_inner_loop_and_its_late_emission_is_stale():
    run = Run(nested_loops_graph(), GENERIC)
    run.emit("start#1", "ok")
    run.emit("a#1", "out", "A1")
    assert run.live() == ["ga#1", "r#1"]
    run.emit("r#1", "out", "R1")
    step = run.emit("gr#1", "revise", "fix-r")
    assert step.cancelled == ()  # ga is outside REGION(r)
    assert run.live() == ["ga#1", "r#2"]

    step = run.emit("ga#1", "revise", "fix-a")
    assert step.cancelled == ("r#2",)
    assert [a.activation_id for a in step.activations] == ["a#2"]
    assert run.state.traversals == {"ga.revise->a.guidance": 1, "gr.revise->r.guidance": 1}

    step = run.emit("r#2", "out", "late")
    assert step.activations == ()
    assert [(d.activation_id, d.reason) for d in run.state.dropped] == [("r#2", "stale")]
    assert step.outcome == "running"


# ---- (15): disjoint concurrent loops (skeptic F7) ----------------------------------


def test_disjoint_loops_revise_independently():
    run = Run(disjoint_loops_graph(), GENERIC)
    run.emit("start#1", "ok")
    run.emit("a#1", "out")
    run.emit("b#1", "out")
    assert run.emit("ga#1", "revise").cancelled == ()
    step = run.emit("gb#1", "revise")
    assert step.cancelled == ()
    assert run.live() == ["a#2", "b#2"]


# ---- (13): a back token into a RUNNING target (revised T1, advisor A1) -------------


def test_back_token_into_a_running_target_retires_and_reruns_it():
    run = Run(running_target_graph(), GENERIC)
    run.emit("e#1", "ok", "go")
    assert run.live() == ["a#1", "v#1"]
    run.emit("a#1", "out")
    step = run.emit("g0#1", "reject")  # q dies -> u's optional port dies -> u ready
    assert [a.activation_id for a in step.activations] == ["u#1", "z#1"]
    assert "v#1" in run.live()  # the old T1 claimed this could not happen

    step = run.emit("u#1", "fix", "guide")
    assert step.cancelled == ("v#1",)
    assert [a.activation_id for a in step.activations] == ["u#2", "v#2"]
    assert run.activation("v#2").inputs == {"guidance": "guide", "trigger": "go"}
    assert run.state.nodes["q"].status == "dead"


# ---- (14): snapshot-available port into a target that died after issue (A2) ---------


def test_snapshot_available_port_into_a_now_dead_target_is_processed_then_reissued():
    run = Run(running_target_graph(dead_target_variant=True), GENERIC)
    run.emit("e#1", "ok")
    run.emit("a#1", "out")
    run.emit("g0#1", "reject")
    assert run.activation("u#1").unavailable_ports == {}  # v is pending, not dead, at issue
    run.emit("b#1", "out")
    run.emit("g1#1", "reject")
    assert run.state.nodes["v"].status == "dead"  # died after u#1 was issued

    step = run.emit("u#1", "fix")
    assert step.outcome == "running"  # T5: never ESCALATED on a snapshot-available port
    assert run.state.traversals == {"u.fix->v.guidance": 1}
    assert run.activation("u#2").unavailable_ports == {"fix": "target_dead"}
    assert run.state.nodes["v"].status == "dead"

    step = run.emit("u#2", "fix")
    assert step.outcome == "escalated"
    assert step.reason == "u.fix: target_dead"
    assert set(step.cancelled) == {"z#1", "z2#1"}
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_router_loops.py -q`

Expected: **10 failed** (every test in `test_graph_router_loops.py`: with Task 6's router a revise token lands in a slot without invalidating anything, so e.g. `architect#2` is never issued and no port is ever `exhausted`).

- [ ] **Step 3: Implement**

In `src/sdlc/graph/router.py` (edit 1 of 5), replace exactly:

```python
def _sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return dict(sorted(value.items()))
```

with:

```python
def _sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return dict(sorted(value.items()))


def _node_of(activation_id: str) -> str:
    return activation_id.rpartition("#")[0]
```

In `src/sdlc/graph/router.py` (edit 2 of 5), replace exactly:

```python
            return self._settle(w, cancelled=[])

        # 6. forward edges
        for eid in edges:
```

with:

```python
            return self._settle(w, cancelled=[])

        # 5. back edge: the port carries exactly this edge (validate T4)
        if edges[0] in self._t.bounds:
            cancelled = self._traverse_back(w, edges[0], token)
            return self._settle(w, cancelled=cancelled)

        # 6. forward edges
        for eid in edges:
```

In `src/sdlc/graph/router.py` (edit 3 of 5), replace exactly:

```python
            state=w.freeze(), activations=(), cancelled=(), outcome=w.outcome, reason=w.reason
        )

    # ---- terminal outcomes -------------------------------------------------
```

with:

```python
            state=w.freeze(), activations=(), cancelled=(), outcome=w.outcome, reason=w.reason
        )

    # ---- step 5: region invalidation ----------------------------------------

    def _traverse_back(self, w: _Work, eid: str, token: Token) -> list[str]:
        w.traversals[eid] = w.traversals.get(eid, 0) + 1
        target = self._t.edges[eid][2]
        region = set(self._t.regions[target])
        for slot in [s for s, tok in w.slots.items() if _node_of(tok.producer) in region]:
            del w.slots[slot]
        cancelled = sorted(a for a, live in w.live.items() if live.node_id in region)
        for aid in cancelled:
            del w.live[aid]
            w.retired.add(aid)
        for n in region:
            w.nodes[n] = NodeState(round=w.nodes[n].round)
        w.slots[eid] = token  # 5c after 5b: a self-loop's new token survives
        return cancelled

    # ---- terminal outcomes -------------------------------------------------
```

In `src/sdlc/graph/router.py` (edit 4 of 5), replace exactly:

```python
        return inputs

    def _settle(self, w: _Work, cancelled: list[str]) -> Step:
        # Phase A: deadness to a fixpoint (activation never changes deadness).
```

with:

```python
        return inputs

    def _unavailable(self, w: _Work, node_id: str) -> dict[str, Unavailable]:
        out: dict[str, Unavailable] = {}
        for port, eids in sorted(self._t.out_ports[node_id].items()):
            if len(eids) != 1 or eids[0] not in self._t.bounds:
                continue
            eid = eids[0]
            if w.traversals.get(eid, 0) >= self._t.bounds[eid]:
                out[port] = "exhausted"
            elif w.nodes[self._t.edges[eid][2]].status == "dead":
                out[port] = "target_dead"
        return out

    def _settle(self, w: _Work, cancelled: list[str]) -> Step:
        # Phase A: deadness to a fixpoint (activation never changes deadness).
```

In `src/sdlc/graph/router.py` (edit 5 of 5), replace exactly:

```python
        issued: list[Activation] = []
        for n, inputs in ready:
            unavailable: dict[str, Unavailable] = {}
            round_ = w.nodes[n].round + 1
            aid = gate_key(n, round_)
```

with:

```python
        issued: list[Activation] = []
        for n, inputs in ready:
            unavailable = self._unavailable(w, n)
            round_ = w.nodes[n].round + 1
            aid = gate_key(n, round_)
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_router_loops.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **245 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 router -- loops, counters, snapshots, ESCALATED

A loop traversal counts, invalidates REGION(target) -- clearing slots
by producer, cancelling live activations there (a running target
included, advisor A1), resetting its nodes -- and only then delivers
(5b before 5c, A3). Issue-time unavailable_ports snapshots (exhausted,
target_dead) are the contract (F5, A2). Table tests reproduce
_revisable_stage and the code fix loop, pin upstream-token survival,
the documented never-reset limitation, nested and disjoint loops.
```

```bash
git add tests/graph/fixtures/routing.py
git add tests/graph/test_graph_router_loops.py
git add src/sdlc/graph/router.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 8: Wiring up — `from_graph`, package exports, property tier, NFR-10 determinism

**Files:**
- Modify: `src/sdlc/graph/validate.py`, `src/sdlc/graph/__init__.py`
- Modify: `tests/graph/test_graph_validate.py`, `tests/graph/test_graph_purity.py`
- Create: `tests/graph/test_graph_router_properties.py`, `tests/graph/test_graph_determinism.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `from_graph(graph, registry=NODE_TYPES, *, roles) -> GraphRouter` (raises `InvalidGraph`); `sdlc.graph` re-exports `RESERVED_GATE_NAMES`, `Activation`, `Emitted`, `GraphRouter`, `InvalidGraph`, `Problem`, `ProblemCode`, `RouterError`, `RouterState`, `Step`, `Topology`, `ValidationReport`, `from_graph`, `validate` — the surface E-74/E-75 import.

- [ ] **Step 1: Write the tests (and test fixtures)**

In `tests/graph/test_graph_validate.py` (edit 1 of 1), replace exactly:

```python
    assert len(problems) >= 4
```

with:

```python
    assert len(problems) >= 4


# ---- from_graph ---------------------------------------------------------------


def test_from_graph_returns_a_router_over_a_clean_graph():
    from sdlc.graph import GraphRouter, from_graph

    router = from_graph(_chain(), GENERIC, roles=roles())
    assert isinstance(router, GraphRouter)
    assert [a.activation_id for a in router.start().activations] == ["start#1"]


def test_from_graph_raises_invalid_graph_with_every_problem():
    from sdlc.graph import InvalidGraph, from_graph

    g = _chain(extra_nodes=(node("x", "nope"), node("s2", "sink")))
    with pytest.raises(InvalidGraph) as excinfo:
        from_graph(g, GENERIC, roles=roles())
    assert excinfo.value.problems == _check(g).problems
    assert isinstance(excinfo.value, ValueError)
```

In `tests/graph/test_graph_purity.py` (edit 1 of 3), replace exactly:

```python
        "sdlc.graph.topology",
    },
```

with:

```python
        "sdlc.graph.topology",
        "sdlc.graph.router",
    },
```

In `tests/graph/test_graph_purity.py` (edit 2 of 3), replace exactly:

```python
        "sdlc.graph.payloads",
    },
```

with:

```python
        "sdlc.graph.payloads",
        "sdlc.graph.router",
        "sdlc.graph.topology",
        "sdlc.graph.validate",
    },
```

In `tests/graph/test_graph_purity.py` (edit 3 of 3), replace exactly:

```python
    assert proc.stdout.strip() == "[]", proc.stdout + proc.stderr
```

with:

```python
    assert proc.stdout.strip() == "[]", proc.stdout + proc.stderr


def test_validate_loads_only_the_agents_loader_at_call_time():
    """validate()'s ADR-6 check imports sdlc.agents.loader inside its body.
    Calling it must never pull in sdlc.agents.roles (which loads the
    registry from disk at import), benchmarks, stages or temporalio."""
    fixture = GRAPH_DIR.parents[2] / "tests" / "graph" / "fixtures" / "pre_code.graph.yaml"
    code = "\n".join(
        [
            "import sys",
            "from pathlib import Path",
            "from sdlc.core.models import RoleConfig",
            "from sdlc.graph import from_graph, from_yaml",
            "roles = {",
            "    'architect': RoleConfig(kind='proposer', model='anthropic:m'),",
            "    'clarify': RoleConfig(kind='proposer', model='anthropic:m'),",
            "    'dev': RoleConfig(kind='harness', harness='opencode', model='zai-coding-plan/m'),",
            "    'planner': RoleConfig(kind='proposer', model='anthropic:m'),",
            "    'research': RoleConfig(kind='research', model='anthropic:m', provider='fake'),",
            "    'reviewer': RoleConfig(kind='proposer', model='anthropic:m'),",
            "}",
            f"g = from_yaml(Path({fixture.as_posix()!r}).read_text(encoding='utf-8'))",
            "from_graph(g, roles=roles).start()",
            "heavy = ('sdlc.benchmarks', 'sdlc.stages', 'sdlc.agents', 'temporalio')",
            "print(sorted(m for m in sys.modules",
            "    if any(m == h or m.startswith(h + '.') for h in heavy)))",
        ]
    )
    src_root = str(GRAPH_DIR.parents[1])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([src_root, os.environ.get("PYTHONPATH", "")]),
    }
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    )
    loaded = proc.stdout.strip()
    assert loaded == "['sdlc.agents', 'sdlc.agents.loader']", loaded + proc.stderr
```

Create `tests/graph/test_graph_router_properties.py`:

```python
"""E-73 router property tier (spec §6.7, §8, D4): EXHAUSTIVE exploration of
every reachable RouterState of small graphs -- stdlib only, no hypothesis.

From each state the explorer applies every out-port of every live activation
(unavailable ports included, so ESCALATED paths are explored too), with a
deterministic payload ref per (activation, port) so equal states converge.
After every transition it checks the invariants and theorems below.

Two statements are narrowed from the spec's wording (plan deviations 1-2):
- Invariant I is checked on FORWARD slots. A back-edge slot's producer is
  reset to pending by its own traversal (step 5b before 5c), so for back
  slots the checked property is I-back: the producer lies in REGION(target)
  and a port never holds two tokens.
- T2 compares states with live-activation snapshots projected out: a
  `target_dead` snapshot legitimately depends on arrival order (§6.5).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from pathlib import Path

import pytest

from sdlc.graph import NODE_TYPES, from_yaml
from sdlc.graph.model import PipelineGraph
from sdlc.graph.router import (
    Emitted,
    GraphRouter,
    LiveActivation,
    RouterState,
    Step,
    _Work,
)
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import FIX_LOOP, GENERIC, fix_loop_graph, roles
from tests.graph.fixtures.routing import (
    collect_graph,
    disjoint_loops_graph,
    nested_loops_graph,
    running_target_graph,
    self_loop_graph,
)

FIXTURE = Path(__file__).parent / "fixtures" / "pre_code.graph.yaml"

GRAPHS: dict[str, Callable[[], tuple[PipelineGraph, object]]] = {
    "pre_code": lambda: (from_yaml(FIXTURE.read_text(encoding="utf-8")), NODE_TYPES),
    "fix_loop": lambda: (fix_loop_graph(2, 2), FIX_LOOP),
    "nested": lambda: (nested_loops_graph(), GENERIC),
    "disjoint": lambda: (disjoint_loops_graph(), GENERIC),
    "collect": lambda: (collect_graph(), GENERIC),
    "running_target": lambda: (running_target_graph(), GENERIC),
    "self_loop": lambda: (self_loop_graph(), GENERIC),
    "dead_target": lambda: (running_target_graph(dead_target_variant=True), GENERIC),
}
MAX_STATES = 5000


def _router(name: str) -> GraphRouter:
    g, registry = GRAPHS[name]()
    report = validate(g, registry, roles=roles())  # type: ignore[arg-type]
    assert report.topology is not None
    return GraphRouter(report.topology)


def _event(live: LiveActivation, port: str) -> Emitted:
    return Emitted(
        activation_id=live.activation_id, port=port, payload_ref=f"{live.activation_id}:{port}"
    )


def _check_invariant_i(router: GraphRouter, state: RouterState) -> None:
    t = router.topology
    for slot, token in state.slots.items():
        source, source_port, target, _ = t.edges[slot]
        producer_node, _, k = token.producer.rpartition("#")
        assert producer_node == source, slot
        if slot in t.bounds:  # I-back
            assert source in t.regions[target], slot
        else:  # Invariant I
            ns = state.nodes[source]
            assert ns.status == "done", slot
            assert ns.taken_port == source_port, slot
            assert ns.round == int(k), slot
    for node_id, ports in t.in_ports.items():
        for wiring in ports.values():
            if wiring.multiplicity == "one":
                occupied = [
                    e for e in (*wiring.forward_edges, *wiring.back_edges) if e in state.slots
                ]
                assert len(occupied) <= 1, (node_id, occupied)


def _check_transition(
    router: GraphRouter, before: RouterState, live: LiveActivation, port: str, step: Step
) -> None:
    t = router.topology
    assert not (step.reason or "").startswith("router_invariant"), step.reason
    # T5: never ESCALATED on a snapshot-available port.
    if step.outcome == "escalated" and before.outcome == "running":
        assert port in live.unavailable_ports, (live.activation_id, port, step.reason)
    # T1 (revised): a back token into a live target retires that activation.
    edges = t.out_ports[live.node_id][port]
    if port not in live.unavailable_ports and edges and edges[0] in t.bounds:
        target = t.edges[edges[0]][2]
        for other in before.live:
            if other.node_id == target and other.activation_id != live.activation_id:
                assert other.activation_id in step.cancelled
                assert other.activation_id in step.state.retired
    # A back traversal that was applied leaves the emitted token in its slot
    # (5b before 5c).
    if step.outcome == "running" and edges and edges[0] in t.bounds:
        token = step.state.slots.get(edges[0])
        assert token is not None and token.producer == live.activation_id, edges[0]
    # At issue: every forward in-edge of the node is resolved (FILLED or dead),
    # and the unavailable-ports snapshot matches the post-step state.
    work = _Work.of(step.state)
    for activation in step.activations:
        for wiring in t.in_ports[activation.node_id].values():
            for e in wiring.forward_edges:
                assert e in step.state.slots or router._edge_dead(work, e), (activation, e)
        assert activation.unavailable_ports == _expected_unavailable(t, step, activation)
    # Issued activations are exactly the new live ones, sorted by node id.
    new_live = {a.activation_id for a in step.state.live} - {a.activation_id for a in before.live}
    assert {a.activation_id for a in step.activations} == new_live
    assert [a.node_id for a in step.activations] == sorted(a.node_id for a in step.activations)


def _expected_unavailable(t, step: Step, activation) -> dict[str, str]:
    """Spec §6.5, recomputed independently of the router: a port carrying a
    back edge is `exhausted` at its bound, else `target_dead` if the target
    is dead in the state the activation was issued into."""
    expected: dict[str, str] = {}
    for port, eids in sorted(t.out_ports[activation.node_id].items()):
        if len(eids) == 1 and eids[0] in t.bounds:
            target = t.edges[eids[0]][2]
            if step.state.traversals.get(eids[0], 0) >= t.bounds[eids[0]]:
                expected[port] = "exhausted"
            elif step.state.nodes[target].status == "dead":
                expected[port] = "target_dead"
    return expected


def _check_redelivery(router: GraphRouter, state: RouterState) -> None:
    """Async races (skeptic F3): re-delivering a retired id or an applied
    emission is dropped -- never raised -- and changes nothing but `dropped`."""
    replays = [
        Emitted(
            activation_id=aid,
            port=sorted(router.topology.out_ports[aid.rpartition("#")[0]])[0],
            payload_ref="late",
        )
        for aid in state.retired
    ] + [
        Emitted(activation_id=e.activation_id, port=e.port, payload_ref=e.payload_ref)
        for e in state.emissions
    ]
    for event in replays:
        step = router.advance(state, event)
        assert step.activations == () and step.cancelled == ()
        assert step.state.model_copy(update={"dropped": state.dropped}) == state
        assert len(step.state.dropped) == len(state.dropped) + 1


def _ends_run(t, live: LiveActivation, port: str) -> bool:
    return port == "reject" and live.node_id in t.gate_nodes


def _explore(router: GraphRouter) -> dict[str, RouterState]:
    seen: dict[str, RouterState] = {}
    frontier = [router.start().state]
    while frontier:
        state = frontier.pop()
        key = state.model_dump_json()
        if key in seen:
            continue
        seen[key] = state
        assert len(seen) <= MAX_STATES, "state space larger than expected"
        _check_invariant_i(router, state)
        # T4 (quiescence): no live activation means a final outcome, and a
        # COMPLETED run leaves no node pending (nothing starved).
        if not state.live:
            assert state.outcome != "running"
        if state.outcome == "completed":
            assert all(ns.status in ("done", "dead") for ns in state.nodes.values())
        _check_redelivery(router, state)
        for live in state.live:
            for port in sorted(router.topology.out_ports[live.node_id]):
                step = router.advance(state, _event(live, port))
                _check_transition(router, state, live, port, step)
                frontier.append(step.state)
    return seen


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_exhaustive_exploration_terminates_and_holds_invariants(name):
    """T4: the reachable state space is finite (the explorer terminates) and
    every quiescent state is final; Invariant I / I-back, T1, T5 on every
    transition; router_invariant never fires on a legal graph."""
    states = _explore(_router(name))
    assert any(s.outcome != "running" for s in states.values())


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_forward_emissions_are_confluent(name):
    """T2: two live activations whose emissions touch no back edge and end
    nothing, applied in either order, reach equal states (modulo issue-time
    snapshots) and issue the same activation set."""
    router = _router(name)
    t = router.topology
    checked = 0
    for state in _explore(router).values():
        candidates = [
            (live, port)
            for live in state.live
            for port, edges in sorted(t.out_ports[live.node_id].items())
            if port not in live.unavailable_ports
            and (edges[0] not in t.bounds if edges else not _ends_run(t, live, port))
        ]
        for (l1, p1), (l2, p2) in itertools.combinations(candidates, 2):
            if l1.activation_id == l2.activation_id:
                continue
            e1, e2 = _event(l1, p1), _event(l2, p2)
            a = router.advance(state, e1)
            ab = router.advance(a.state, e2)
            b = router.advance(state, e2)
            ba = router.advance(b.state, e1)
            strip = {
                "live": tuple(x.model_copy(update={"unavailable_ports": {}}) for x in ab.state.live)
            }
            strip_ba = {
                "live": tuple(x.model_copy(update={"unavailable_ports": {}}) for x in ba.state.live)
            }
            assert ab.state.model_copy(update=strip) == ba.state.model_copy(update=strip_ba)
            issued_ab = {x.activation_id for x in (*a.activations, *ab.activations)}
            issued_ba = {x.activation_id for x in (*b.activations, *ba.activations)}
            assert issued_ab == issued_ba
            checked += 1
    if name in {"collect", "disjoint", "nested", "dead_target"}:
        assert checked > 0  # the property is exercised, not vacuous


@pytest.mark.parametrize("name", sorted(GRAPHS))
def test_same_script_same_bytes(name):
    """T3: determinism -- replaying one event script yields byte-identical
    state JSON at every step."""

    def replay() -> list[str]:
        router = _router(name)
        step = router.start()
        out = [step.state.model_dump_json()]
        for _ in range(40):
            if not step.state.live:
                break
            live = step.state.live[-1]
            port = sorted(router.topology.out_ports[live.node_id])[0]
            step = router.advance(step.state, _event(live, port))
            out.append(step.state.model_dump_json())
        return out

    assert replay() == replay()
```

Create `tests/graph/test_graph_determinism.py`:

```python
"""E-73 NFR-10 determinism (spec §8): hash-seed independence of the report
and of a router state sequence, and order independence of validate() under
permuted registry / roles insertion order and permuted port declarations."""

from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import sdlc.graph
from sdlc.graph.validate import validate
from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles

REPO = Path(sdlc.graph.__file__).parents[3]

# Validates a graph with many problems, then drives nested loops until at
# least two activations are live and two ids are retired, printing every JSON.
_SCRIPT = "\n".join(
    [
        "from sdlc.graph.router import Emitted, GraphRouter",
        "from sdlc.graph.validate import validate",
        "from tests.graph.fixtures.registries import GENERIC, edge, graph, node, roles",
        "from tests.graph.fixtures.routing import nested_loops_graph",
        "bad = graph([node('start', 'start'), node('x', 'nope'), node('merge', 'gate.art'),",
        "    node('b', 'builder', role={}), node('a', 'work'), node('c', 'sink')],",
        "    [edge('ghost.ok', 'x.in'), edge('a.out', 'c.art'), edge('c.done', 'a.trigger')])",
        "print(validate(bad, GENERIC, roles=roles()).model_dump_json())",
        "report = validate(nested_loops_graph(), GENERIC, roles=roles())",
        "router = GraphRouter(report.topology)",
        "step = router.start()",
        "script = [('start#1', 'ok'), ('a#1', 'out'), ('r#1', 'out'), ('gr#1', 'revise'),",
        "    ('ga#1', 'revise'), ('r#2', 'out'), ('a#2', 'out'), ('ga#2', 'reject')]",
        "for aid, port in script:",
        "    event = Emitted(activation_id=aid, port=port, payload_ref=aid)",
        "    step = router.advance(step.state, event)",
        "    print(step.model_dump_json())",
    ]
)


def _run_with_seed(seed: str) -> str:
    env = {
        **os.environ,
        "PYTHONHASHSEED": seed,
        "PYTHONPATH": os.pathsep.join(
            [str(REPO / "src"), str(REPO), os.environ.get("PYTHONPATH", "")]
        ),
    }
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        cwd=REPO,
    )
    return proc.stdout


def test_report_and_router_json_are_hash_seed_independent():
    outputs = [_run_with_seed(seed) for seed in ("0", "1", "4242")]
    assert outputs[0] == outputs[1] == outputs[2]
    lines = outputs[0].splitlines()
    report = json.loads(lines[0])
    assert "unknown_node_type" in {p["code"] for p in report["problems"]}
    # The script really exercises the set-backed fields (skeptic F8).
    states = [json.loads(line)["state"] for line in lines[1:]]
    assert max(len(s["live"]) for s in states) >= 2
    assert max(len(s["retired"]) for s in states) >= 2


def _bad_graph():
    return graph(
        [
            node("start", "start"),
            node("x", "nope"),
            node("merge", "gate.art"),
            node("b", "builder", role={}),
            node("a", "work"),
            node("c", "sink"),
            node("br", "brancher"),
            node("m", "sink"),
        ],
        [
            edge("ghost.ok", "x.in"),
            edge("a.out", "c.art"),
            edge("c.done", "a.trigger"),
            edge("start.ok", "br.trigger"),
            edge("br.left", "m.art"),
            edge("br.right", "m.art"),
        ],
    )


def test_report_is_independent_of_registry_and_roles_insertion_order():
    g = _bad_graph()
    baseline = validate(g, GENERIC, roles=roles())
    specs = list(GENERIC.values())
    role_items = list(roles().items())
    for k in range(6):
        shuffled_specs = specs[k:] + specs[:k]
        shuffled_roles = dict(role_items[k:] + role_items[:k])
        report = validate(
            g, MappingProxyType({s.type: s for s in shuffled_specs}), roles=shuffled_roles
        )
        assert report == baseline


def test_report_and_topology_are_independent_of_port_declaration_order():
    clean = graph(
        [node("start", "start"), node("br", "brancher"), node("m", "sink"), node("g", "gate.art")],
        [
            edge("start.ok", "br.trigger"),
            edge("br.left", "m.art"),
            edge("br.right", "g.artifact"),
        ],
    )
    for g in (clean, _bad_graph()):
        baseline = validate(g, GENERIC, roles=roles())
        for type_ in ("brancher", "gate.art"):
            spec = GENERIC[type_]
            for ports in itertools.permutations(spec.ports):
                permuted = MappingProxyType(
                    {**GENERIC, type_: spec.model_copy(update={"ports": ports})}
                )
                assert validate(g, permuted, roles=roles()) == baseline
                if baseline.topology is not None:
                    assert validate(g, permuted, roles=roles()).topology == baseline.topology
```

- [ ] **Step 2: Run them to see the expected result before the code**

Run: `python -m pytest tests/graph/test_graph_validate.py tests/graph/test_graph_purity.py tests/graph/test_graph_router_properties.py tests/graph/test_graph_determinism.py -q`

Expected: **3 failed** — `test_from_graph_returns_a_router_over_a_clean_graph` and `test_from_graph_raises_invalid_graph_with_every_problem` (`ImportError: cannot import name 'GraphRouter' / 'InvalidGraph' from 'sdlc.graph'`), and `test_validate_loads_only_the_agents_loader_at_call_time` (no `from_graph` export). The property and determinism files **pass** on Task 7's code: they pin Tasks 6–7 behaviour exhaustively and are the regression tier E-74 inherits.

- [ ] **Step 3: Implement**

In `src/sdlc/graph/validate.py` (edit 1 of 3), replace exactly:

```python
Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph.{model,node_types,topology} (spec §4; pinned by
tests/graph/test_graph_purity.py).
"""
```

with:

```python
Module-level imports stay within stdlib, pydantic, sdlc.core.models and
sdlc.graph.{model,node_types,topology,router} (spec §4 plus router for
from_graph; pinned by tests/graph/test_graph_purity.py).
"""
```

In `src/sdlc/graph/validate.py` (edit 2 of 3), replace exactly:

```python
from .node_types import NODE_TYPES, NodeTypeSpec, find_port, ports_compatible
from .topology import (
```

with:

```python
from .node_types import NODE_TYPES, NodeTypeSpec, find_port, ports_compatible
from .router import GraphRouter
from .topology import (
```

In `src/sdlc/graph/validate.py` (edit 3 of 3), replace exactly:

```python
    return ValidationReport(problems=(), topology=_build_topology(graph, nodes, registry))
```

with:

```python
    return ValidationReport(problems=(), topology=_build_topology(graph, nodes, registry))


def from_graph(
    graph: PipelineGraph,
    registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
    *,
    roles: Mapping[str, RoleConfig],
) -> GraphRouter:
    """A router over `graph`, or InvalidGraph carrying every problem."""
    report = validate(graph, registry, roles=roles)
    if report.topology is None:
        raise InvalidGraph(report.problems)
    return GraphRouter(report.topology)
```

Replace the whole of `src/sdlc/graph/__init__.py` with:

```python
"""Pipeline as data -- the graph schema, node-type registry, validator and
router (E-72 FR-1201, E-73 FR-1202).

Specs: docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md,
docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md.
Nothing outside this package imports it until E-74.
"""

from __future__ import annotations

from .io import GraphSchemaError, from_yaml, to_yaml
from .model import (
    GraphEdge,
    GraphNode,
    NodePort,
    NodePosition,
    PipelineGraph,
    canonical_json,
)
from .node_types import (
    NODE_TYPES,
    NodeTypeSpec,
    check_node_types,
    find_port,
    ports_compatible,
)
from .payloads import PAYLOAD_TYPES
from .router import (
    Activation,
    Emitted,
    GraphRouter,
    RouterError,
    RouterState,
    Step,
)
from .topology import Topology
from .validate import (
    RESERVED_GATE_NAMES,
    InvalidGraph,
    Problem,
    ProblemCode,
    ValidationReport,
    from_graph,
    validate,
)

__all__ = [
    "NODE_TYPES",
    "PAYLOAD_TYPES",
    "RESERVED_GATE_NAMES",
    "Activation",
    "Emitted",
    "GraphEdge",
    "GraphNode",
    "GraphRouter",
    "GraphSchemaError",
    "InvalidGraph",
    "NodePort",
    "NodePosition",
    "NodeTypeSpec",
    "PipelineGraph",
    "Problem",
    "ProblemCode",
    "RouterError",
    "RouterState",
    "Step",
    "Topology",
    "ValidationReport",
    "canonical_json",
    "check_node_types",
    "find_port",
    "from_graph",
    "from_yaml",
    "ports_compatible",
    "to_yaml",
    "validate",
]
```

- [ ] **Step 4: Run the task's tests**

Run: `python -m pytest tests/graph/test_graph_validate.py tests/graph/test_graph_purity.py tests/graph/test_graph_router_properties.py tests/graph/test_graph_determinism.py -q`

Expected: PASS.

- [ ] **Step 5: Lint, format, typecheck, whole graph suite**

```bash
ruff check src/sdlc/graph tests/graph
ruff format --check src/sdlc/graph tests/graph
mypy src/sdlc/graph --follow-imports=silent
python -m pytest tests/graph -q
```

Expected: ruff `All checks passed!`, format `... files already formatted`, mypy `Success: no issues found`, pytest **275 passed**. Run the four commands as separate calls (never chain two pytest runs).

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
feat(graph): E-73 from_graph, exports, property and determinism tiers

from_graph builds a router or raises InvalidGraph with every problem;
sdlc.graph re-exports the validator and router surface. The property tier
exhaustively explores every reachable state of eight small graphs (stdlib
only) and checks Invariant I / I-back, revised T1, T2 confluence, T4
quiescence, T5, resolution and snapshot correctness at issue, and async
re-delivery. NFR-10: hash-seed-independent report and router JSON;
report and Topology invariant under registry, roles and port order.
```

```bash
git add tests/graph/test_graph_validate.py
git add tests/graph/test_graph_purity.py
git add tests/graph/test_graph_router_properties.py
git add tests/graph/test_graph_determinism.py
git add src/sdlc/graph/validate.py
git add src/sdlc/graph/__init__.py
git commit -F .workspace/tmp/e73-task-commit.txt
```

---

### Task 9: Landing docs + full verification gate

**Files:**
- Modify: `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md` (dated erratum)
- Modify: `docs/roadmap/pipeline-as-data.md`, `ROADMAP.md`, `ARCHITECTURE.md`

**Interfaces:**
- Consumes: Tasks 1–8 landed on the branch.
- Produces: docs that describe `main` once the branch is fast-forwarded (docs-describe-main convention: nothing here before the code is on the branch), and a spec whose §6.7 records the dated errata matching the shipped code (plan review R1/R3: the erratum lands in the same branch as the code, never as a "recommended" orphan).

Decisions encoded here (reviewer: judge): E-73's roadmap row is ticked. **FR-1202 becomes `[ ] ⚠️` partial, not `[x]`**: ROADMAP's legend defines ⚠️ as "mechanism exists but incomplete or not fully wired", and FR-1202's "every consumer (interpreter, CLI, canvas, tests) calls" is wired by E-74/E-75/E-76. **FR-1201 stays ⚠️** with its note updated: incompatible edges are now rejected, but "registry validation, ADR-6 and `PROMPT_SHAS` keep working" still depends on E-74 projecting `node.role` into the run config (E-72 spec §9 obligation 1).

- [ ] **Step 1: Record spec §6.7 errata in the design spec** (plan review R1/R3)

In `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md`, replace exactly:

```
- **T4** Termination: every event script is finite — each back edge is bounded, the forward subgraph is a DAG, and the §6.5 re-issue path increments a counter.
- **T5** Never ESCALATED on a snapshot-available port.

### 6.8 Deliberately not in the router
```

with:

```
- **T4** Termination: every event script is finite — each back edge is bounded, the forward subgraph is a DAG, and the §6.5 re-issue path increments a counter.
- **T5** Never ESCALATED on a snapshot-available port.

**Erratum (2026-09-14, plan review R1/R3 / E-73 implementation):**
- **Invariant I holds on forward slots, with I-back for back-edge slots** (producer node in `REGION(target)`; no `one` port holds two tokens) exactly as the plan's deviation 1 states (step 5b resets the emitter to `pending` before 5c delivers its token; occupied-slot delivery remains unreachable and no stale token carries into a later generation).
- **T2 equality is modulo issue-time `unavailable_ports` snapshots** exactly as deviation 2 states (`target_dead` at issue legitimately depends on forward-emission arrival order under races).
- **Section 6.5 precedence:** when a loop port is both `exhausted` and targets a dead node, `exhausted` takes precedence over `target_dead` (deviation 6).
- **Section 4 `RouterState.emissions` field:** applied emissions are stored, sorted by activation id, to support rule F3 duplicate-vs-conflicting checks while preserving deterministic state equality (deviation 3).
- **Section 7.2 T3 rows are per-override:** kind-consistent overrides are checked for harness/provider requirements (yielding at most one diagnostic per override; plan review R3 / deviation 9).

### 6.8 Deliberately not in the router
```

- [ ] **Step 2: Tick E-73 in the pipeline-as-data roadmap**

In `docs/roadmap/pipeline-as-data.md`, replace exactly:

```
- [ ] **E-73 — `GraphRouter` + `validate.py`** → FR-1202. **The bug budget lives
```

with:

```
- [x] **E-73 — `GraphRouter` + `validate.py`** → FR-1202. **The bug budget lives
```

Then replace exactly:

```
  one entry node) and is never reimplemented in TypeScript.
- [ ] **E-74 — `GraphWorkflow` replaces `_pipeline`** → FR-1203. Thin Temporal
```

with:

```
  one entry node) and is never reimplemented in TypeScript.

  **Landed** (spec `docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md`,
  plan `docs/superpowers/plans/2026-09-14-graph-router-and-validator.md`): `sdlc/graph/`
  gains `topology.py`, `validate.py` (25 `ProblemCode`s; the only producer of `Topology`)
  and `router.py` (a pure reducer). A loop edge is exactly an edge carrying
  `max_traversals`; the literal "invalidate inputs at lower rounds" is superseded by
  REGION invalidation, because it would starve `architect` of upstream inputs. Exhaustion
  is ESCALATED at the router, and each activation's `unavailable_ports` snapshot lets a
  gate run as today's final gate (E-74 handler rule). Open questions E73-OQ-1…8 live in
  the spec §10; E73-OQ-3 (never-reset counters) is a documented limitation.
- [ ] **E-74 — `GraphWorkflow` replaces `_pipeline`** → FR-1203. Thin Temporal
```

- [ ] **Step 3: Update the FR-1201 / FR-1202 mirror in ROADMAP**

In `ROADMAP.md`, replace exactly:

```
Partial: E-72 landed the schema, `content_sha()`, YAML io and the seed registry with the `ports_compatible` rule; *rejecting* incompatible edges is enforced by FR-1202's `validate.py` (E-73).
- [ ] **FR-1202** pure `GraphRouter` + single-source `validate.py` — branching, round-based stale-input invalidation, per-edge `max_traversals` → ESCALATED; legality never reimplemented in the frontend (E-73).
```

with:

```
Partial: E-72 landed the schema, `content_sha()`, YAML io and the seed registry with the `ports_compatible` rule, and E-73's `validate.py` rejects incompatible edges; registry validation, ADR-6 and `PROMPT_SHAS` keep working only once E-74 projects `node.role` into the run config.
- [ ] ⚠️ **FR-1202** pure `GraphRouter` + single-source `validate.py` — branching, round-based stale-input invalidation, per-edge `max_traversals` → ESCALATED; legality never reimplemented in the frontend (E-73). Partial: E-73 landed `sdlc/graph/topology.py`, `validate.py` and `router.py`; the interpreter (E-74), API (E-75) and canvas (E-76) are the consumers that must call them.
```

- [ ] **Step 4: Add the new modules to ARCHITECTURE's repository layout**

In `ARCHITECTURE.md`, replace exactly:

```
│   ├── graph/                 # PipelineGraph schema, node-type registry, content_sha, YAML io (E-72)
```

with:

```
│   ├── graph/                 # PipelineGraph schema, node-type registry, content_sha, YAML io (E-72);
│   │                          #   topology.py, validate.py (legality), router.py — pure GraphRouter (E-73)
```

- [ ] **Step 5: Full verification gate** (separate calls; never chain two pytest runs)

```bash
ruff check .
```

```bash
ruff format --check .
```

```bash
mypy
```

Expected: no **new** mypy errors in `src/sdlc/graph/` (`mypy src/sdlc/graph --follow-imports=silent` → `Success`); the repo-wide count of known deferred errors is unchanged.

```bash
python scripts/check_file_size.py
```

```bash
python -m pytest tests/graph -q
```

Expected: **275 passed**.

```bash
python -m pytest -q
```

Expected: the default fast tier passes with no new failures versus `main`. (Read `.workspace/tasks/` first for known host hazards; do not run the `temporal` tier for this change — nothing here touches Temporal.)

- [ ] **Step 6: Commit** (no attribution trailers of any kind; one path per `git add`)

Write `.workspace/tmp/e73-task-commit.txt` containing exactly:

```text
docs: E-73 landed -- GraphRouter, validate.py, topology

Tick E-73 in the pipeline-as-data roadmap with pointers to its spec and
plan, mark FR-1202 partial in ROADMAP (its consumers are E-74/E-75/E-76)
and update FR-1201's partial note, and add topology.py, validate.py and
router.py to the ARCHITECTURE repository layout.

Also land a dated erratum in the E-73 spec (plan review R1/R3): §6.7
Invariant I holds on forward slots with I-back for loop slots; T2
confluence is modulo issue-time snapshots; §4 records RouterState.emissions
and the sorted dropped log; §6.5 fixes exhausted-over-target_dead
precedence; §7.2 T3 kind-consistency rows are per-override.
```

```bash
git add docs/superpowers/specs/2026-09-14-graph-router-and-validator-design.md
git add docs/roadmap/pipeline-as-data.md
git add ROADMAP.md
git add ARCHITECTURE.md
git commit -F .workspace/tmp/e73-task-commit.txt
```
