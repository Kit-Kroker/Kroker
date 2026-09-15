# E-73 — `GraphRouter` + `validate.py` (FR-1202) — design

| | |
|---|---|
| Epic | E-73 (pipeline-as-data, Phase 1, Track A) → FR-1202 |
| Date | 2026-09-14 |
| Status | reviewer-approved (2026-09-14, round 2); sections 1–5 user-approved; skeptic round dispositioned (§11); pending user gate on E73-OQ-1..E73-OQ-8 (E73-OQ-3 flagged) |
| Normative text | `PRD.md` §6 FR-1202 (FR-1201/FR-1203 for boundary only) |
| Frozen contract | `src/sdlc/graph/` + `docs/superpowers/specs/2026-09-13-graph-model-node-registry-design.md` (E-72) |
| Consultation log | All under `.workspace/tmp/` (uncommitted scratch). **Advisor:** `e73-consult-q1.md` → `advisor-e73-q1.md` (router core), `e73-consult-q2.md` → `advisor-e73-q2.md` (validator), `e73-consult-q3.md` → `advisor-e73-q3.md` (skeptic dispositions check). **Skeptic:** one formal round on the full design, brief `e73-skeptic-brief.md`, critique **`e73-skeptic-full.md`** (F1–F9), every finding dispositioned in §11. **Reviewer:** brief `e73-reviewer-brief.md`; round 1 `e73-reviewer-r1.md` (CHANGES REQUESTED: R1 Important — router row for §6.4 exclusive merge; R2/R3 Minor — cross-reference, `unreachable_node` with ≠1 entry; all applied); round 2 `e73-reviewer-r2.md` (**APPROVED**, riding Minor R4 — §5 cross-reference — applied in this copy). |

## 1. Purpose and deliverable

E-73 is the control-flow core of FR-1200 and carries the group's bug budget. It
ships three pure, synchronous modules — no Temporal, no I/O, no clocks, no
async — so every hard case is a table test:

1. `topology.py` — the loop structure of a graph (`Topology`).
2. `validate.py` — the **single** source of graph legality; the only producer of `Topology`.
3. `router.py` — `GraphRouter`, a pure reducer from `(RouterState, event)` to `Step`.

It changes no existing behaviour. Nothing outside `sdlc/graph/` imports it until E-74.

## 2. Decisions (user-approved)

| # | Decision |
|---|---|
| U1 | **Fan-out/collect is static.** An out-port with N edges broadcasts; a `multiplicity: many` in-port collects over its static forward in-edges. Data-dependent map-over-list is E73-OQ-7. |
| U2 | **Exhaustion.** An emission onto an exhausted edge terminates the run ESCALATED (PRD literal). Each `Activation` also carries `unavailable_ports` so a handler avoids them (§6.5). |
| U3 | **Back edge ⇔ `max_traversals` is set.** Unbounded edges form the forward subgraph, which must be a DAG; each bounded edge must close a cycle; exactly one entry (the node with no forward in-edge). Dominance was rejected: it rejects `plan.revise → architect` on the E-72 fixture (`clarifier → planner` bypasses `architect`) because it treats joins as OR-joins. DFS classification was rejected as traversal-order dependent. |
| U4 | **E72-OQ-1 ADR-6 → cross-product** over distinct effective models per role (§7.4). |
| U5 | **Counters and rounds never reset.** Monotonic for the whole run. |
| U6 | **E72-OQ-2 (E-73 half) → reserved handler gate names** (§7.3 `reserved_gate_name`). No field; nothing asserted across graph versions. |
| U7 | **Shape: reducer over a validated `Topology`** (§4). Rejected: a stateful router object (hidden state, classification computed twice); compiling to a Petri-net IR (tables stop matching what the author drew). |
| D1 | Round = monotonic per-node activation count; `activation_id = gate_key(node_id, round)`. |
| D2 | A back-edge traversal into v invalidates REGION(v) = v ∪ forward-reach(v). Natural-loop body rejected: a forward consumer outside it (e.g. an ungated `architect.spec → doc_writer`) would keep a superseded artifact. |
| D3 | Outcomes `RUNNING \| COMPLETED \| REJECTED \| ESCALATED`; an emission on a gate's unconnected `reject` → REJECTED. |
| D4 | Property tier uses stdlib (exhaustive interleaving enumeration + seeded `random.Random`), not `hypothesis` — **corrected hypothesis:** `hypothesis` is not a dependency and no test uses it. |

## 3. Verified anchors (and corrected hypotheses)

- `gate_key(gate, round) = f"{gate}#{round}"` (`core/models.py:228`); pending keys and decisions key on it (`pending.py:133`, `workflows/gates.py:106,199`).
- **Correction:** `_revisable_stage` (`workflows/role_host.py:219-271`) does NOT terminate on exhaustion. Rounds are per gate `1..max_gate_rounds`; on exhaustion it re-runs the producer and holds a final gate at `max_gate_rounds+1` with no `auto_decision` (policy unchanged — an OFF gate still auto-approves, `gates.py:201`). A final-gate REVISE returns not-approved → `rejected:<gate>` (`feature.py:592,609`).
- **Correction:** the code fix loop (`stages/code/step.py:548-947`) does NOT terminate on exhaustion. `budget = max_fix_attempts + 1`; at budget a `task:<id>` gate (own `gate_round`); REVISE with `gate_round <= max_gate_rounds` sets `budget = attempt + 1` — exactly ONE more attempt (`:914`); otherwise `done`/`quarantined`.
- A literal "invalidate buffered inputs at lower rounds" starves the fixture: `clarifier.requirements → architect` is produced once, upstream of the architecture loop. Hence D2's region.
- `validate_run_roles` / `check_adr6_families` / `check_adversary_model` (`agents/loader.py:219-273`) take `dict[str, str]` and raise `RegistryError` on the first breach. `cli_roles.build_role_overrides` (`cli_roles.py:36-43`) builds that map as registry models ∪ overrides.
- `sdlc.agents.roles` loads the registry at import (`REGISTRY = load_registry()`, `:53`); `sdlc/agents/__init__.py` is empty, so a function-local `from ..agents.loader import …` does no I/O.
- Harness inequality (`loader.py:302-305`) is enforced only at boot, not by `validate_run_roles` (E73-OQ-6).
- Handler gate names in use outside graphs: `budget` (`role_host.py:183`), `clarify` (`stages/clarify/step.py:199` reads `cfg.gates`), `crew_question` (`workflows/crew.py:400`), `deploy` (`stages/deploy/step.py:162`), `deploy_failed` (`:212`), `merge` (`stages/merge/step.py:523,588`), `readiness` (`workflows/triage.py:230`), `risk` (`workflows/assessment.py:750`), `tidy_up` (`workflows/tidyup.py:293`), `tool_approval` (`stages/code/step.py:636`, `workflows/crew.py:265`). `research` (`stages/research/step.py:300`), `architecture`, `plan` are the gates graph nodes take over.
- The purity pin walks only `ast.parse(...).body` (`tests/graph/test_graph_purity.py:45`) — blind to `TYPE_CHECKING`/`try`/`with` imports.

## 4. Modules and API

| module | contents | module-level imports |
|---|---|---|
| `topology.py` | `Topology` (frozen): entry, back-edge set, `region: Mapping[str, tuple[str, ...]]` (sorted) per back-edge target — like `RouterState`, `Topology` holds no set types, resolved port spec per connected port (`required`, `multiplicity`, `forward_edges`, `back_edges`), per-node out-port → edges, edge sort keys. Pure algorithms: forward-subgraph SCCs (Tarjan over sorted ids), forward reach. | stdlib, pydantic, `sdlc.graph.model` |
| `validate.py` | `validate()`, `ValidationReport`, `Problem`, `ProblemCode` (`StrEnum`), `RESERVED_GATE_NAMES`, `InvalidGraph`, `from_graph()` | stdlib, pydantic, `sdlc.core.models`, `sdlc.graph.{model,node_types,topology}`; function-local `sdlc.agents.loader` |
| `router.py` | `GraphRouter`, `RouterState`, `Activation`, `Emitted`, `Step`, `Outcome` | stdlib, pydantic, `sdlc.core.models`, `sdlc.graph.topology` |

```python
def validate(graph: PipelineGraph, registry: Mapping[str, NodeTypeSpec] = NODE_TYPES,
             *, roles: Mapping[str, RoleConfig]) -> ValidationReport
class ValidationReport(BaseModel):      # frozen
    problems: tuple[Problem, ...]       # sorted
    topology: Topology | None = Field(default=None, exclude=True)  # present iff problems == ()
class Problem(BaseModel):               # frozen
    code: ProblemCode
    message: str
    node: str | None = None
    edge: tuple[str, str, str, str] | None = None
    port: str | None = None
def from_graph(graph, registry=NODE_TYPES, *, roles) -> GraphRouter   # raises InvalidGraph(problems)

class GraphRouter:
    def __init__(self, topology: Topology) -> None
    def start(self) -> Step
    def advance(self, state: RouterState, event: Emitted) -> Step
class Emitted(BaseModel):               # discriminated union member; kind="emitted"
    activation_id: str
    port: str
    payload_ref: str
class Activation(BaseModel):
    activation_id: str                  # gate_key(node_id, round)
    node_id: str
    round: int
    inputs: Mapping[str, str | tuple[str, ...]]      # port -> payload_ref(s)
    unavailable_ports: Mapping[str, Literal["exhausted", "target_dead"]]
class Step(BaseModel):
    state: RouterState
    activations: tuple[Activation, ...]  # sorted by node_id
    cancelled: tuple[str, ...]           # activation ids, sorted
    outcome: Literal["running", "completed", "rejected", "escalated"]
    reason: str | None
```

- `roles` is a `load_registry()`-shaped mapping, required, no default (a default forces I/O). Env/API-key checks are not the validator's (E-74 run start).
- `RouterState` (frozen, JSON-serialisable, no timestamps, **no set types** — every collection is a sorted tuple or a mapping built in sorted-key order, normalised by a model validator; skeptic F8):
  - per node: `round`, `status ∈ {pending, running, done, dead}`, `taken_port`;
  - per in-edge **slot**: at most one token `(payload_ref, producer_activation_id)` (§6.3);
  - per back edge: `traversals`;
  - `live: tuple[LiveActivation, ...]` sorted by id, each `(activation_id, node_id, unavailable_ports)` — the snapshot taken at issue (skeptic F5, §6.5);
  - `retired: tuple[str, ...]` — ids cancelled by an invalidation or a terminal outcome, plus the emitter whose emission caused ESCALATED;
  - `dropped: tuple[(activation_id, port, reason), ...]`, `reason ∈ {stale, duplicate, post_terminal}` (audit);
  - `outcome`, `reason`.
  - "Finished" ids are not stored: `n#k` was issued ⇔ `k <= round[n]` (node ids cannot contain `#`); finished ⇔ issued ∧ ∉ live ∧ ∉ retired.
- `payload_ref` is opaque; the router never inspects payloads.
- `advance` is total on legal input — including every async-delivery race — and loud only on interpreter bugs (skeptic F3):
  - emission from a `retired` id → `dropped(stale)` (or `post_terminal` if the outcome is terminal), no-op Step, outcome unchanged;
  - emission from a finished id identical to the one applied (same port and `payload_ref`) → `dropped(duplicate)` (at-least-once tolerance);
  - `RouterError` only for: a never-issued id; a port that is not an out-port of the node's type; a finished id emitting a *conflicting* (different port or payload) second emission.
  - Judged per activation id, never by node status (an emitter reset by its own back edge is `pending` again).
- `Emitted` sits in a discriminated union so E72-OQ-4 can add `Failed` without breaking it.
- E-72 review minors folded in: `io._SCHEMA_VERSION = get_args(PipelineGraph.model_fields["schema_version"].annotation)[0]`; a `NodePort.name` regex test; purity pin extended (§8).

## 5. Terms

- **forward edge**: `max_traversals is None`. **back edge**: `max_traversals` set.
- **forward-fed in-port**: ≥1 forward in-edge. **back-only in-port**: only back in-edges (mixing is illegal, §7.2 T4 `mixed_in_port`).
- **REGION(v)** = {v} ∪ nodes forward-reachable from v.
- **generation** of a node: the span between two resets of that node (start, or a REGION invalidation containing it).

## 6. Router semantics

### 6.1 Start

`start()` issues `entry#1`.

### 6.2 Emission processing (`advance`)

1. **Activation check.** Classify `activation_id` as live / retired / finished / never-issued and apply §4's rules; only a live id proceeds.
2. **Unavailable port.** `port ∈ live_activation.unavailable_ports` (the issue-time snapshot) → outcome ESCALATED, reason `f"{node}.{port}: exhausted|target_dead"`; the emitter and every other live activation → `retired` (all but the emitter also → `cancelled`). The emission is not applied.
3. **Done.** Node → `done`, `taken_port = port`, activation leaves `live`; the forward edges of every other out-port are dead.
4. **No edges.** Gate-kind node and `port == "reject"` with no edges → REJECTED, all live → `cancelled` + `retired`. Any other edgeless port is a sink.
5. **Back edge u→v** (the port carries exactly this edge, §7.2 T4 `back_port_not_exclusive`): (a) `traversals += 1`; (b) invalidate REGION(v): clear every slot (anywhere in the graph) whose token's producer node ∈ REGION(v); move live activations of region nodes other than the emitter into `cancelled` + `retired` — **including a live activation of v itself** (a back token can reach a running target, §6.7); reset region nodes to `pending`, `taken_port = None` (`round` kept); (c) deliver the back token into its slot. **5b before 5c is load-bearing** (a self-loop's new token must survive its own invalidation).
   - A snapshot-available port whose target is now dead is processed normally: count, reset, v re-evaluates to dead (its dead input lies outside the region), u is re-issued if ready with a fresh snapshot saying `target_dead`. Never ESCALATED on a snapshot-available port (§6.5).
6. **Forward edges.** Deliver the token into the slot of every forward edge of `port`. Delivery into an occupied slot → ESCALATED, reason `router_invariant` (unreachable by Invariant I, §6.7).
7. **Re-evaluate** readiness/deadness to a fixpoint in sorted node-id order; issue activations; compute outcome (§6.6).

### 6.3 Readiness and deadness (E72-OQ-5)

**Token lifecycle (revised per skeptic F1).** Every in-edge has a **slot** holding at most one token. Activation does **not** clear slots — node status (`pending → running → done`) is what prevents a second activation in one generation. A slot is cleared only by §6.2 step 5b (its token's producer lies in an invalidated region). Tokens from producers outside a region therefore survive every invalidation of it: `clarifier.requirements` stays in `architect`'s slot across all architecture revise rounds. A terminal outcome clears nothing — the frozen final state is the post-mortem record of what each node last consumed (E-75 `graph_state()`, FR-1205).

**Edge state.** An edge is **dead** ⇔ source `dead`, or source `done` with `taken_port ≠ edge.source_port`. It is **resolved** ⇔ its slot holds a token, or it is dead.

**Port state** — one definition over forward in-edges (revised per skeptic F2); unconnected and back-only ports are ignored for readiness and deadness:

| multiplicity | FILLED | DEAD | else |
|---|---|---|---|
| `one` | some forward in-edge slot holds a token | every forward in-edge dead | EMPTY |
| `many` | every forward in-edge resolved and ≥1 slot holds a token | every forward in-edge dead | EMPTY (some edge unresolved) |

- Node **dead** ⇔ some connected required forward-fed port DEAD, or it has ≥1 forward-fed port and all are DEAD.
- Node **ready** ⇔ `pending`, every connected required port FILLED, every connected optional forward-fed port FILLED or DEAD. *Optional means "may be absent", not "don't wait"* — `clarify` with both `codebase_map` and `research` connected waits for both.
- Entry node: ready at start (no forward-fed ports).
- On activation: `round += 1`, status `running`, a `LiveActivation` added. Inputs: a `one` port → the token in its (single) occupied slot; a `many` port → tuple of the tokens in occupied slots, ordered by edge sort key (never arrival order); a back-only port → the token in its occupied back-edge slot, if any.

### 6.4 `multiplicity: one` with several edges

- Forward: legal only when all sources are distinct out-ports of ONE node (mutually exclusive by one-port-per-activation). A delivery into an occupied slot, or a second occupied forward slot on a `one` port → ESCALATED, reason `router_invariant` (backstop; unreachable by Invariant I).
- Back-only: at most one occupied slot — every back-edge source lies in its target's region (U3 rule 2), so each traversal clears any competitor's token (step 5b) before delivering (5c). Latest guidance wins (matches `role_host.py:261`). This relies on U3 rule 2 and step 5b, not on any claim about running targets.

### 6.5 Unavailable ports (U2 generalised)

On issuing an activation, for each out-port carrying a back edge u→v: `exhausted` if `traversals == max_traversals`; `target_dead` if v is `dead` at issue time (else a revise into a dead target would re-ask a human on identical inputs until exhaustion).

**The issue-time snapshot is the contract** (skeptic F5). A handler — and a human at a gate — acts on what it was told, so the router judges the emission against the snapshot stored in `LiveActivation`, never a recomputation. `exhausted` cannot change while u is live (only u's own emission moves that counter, and u has at most one live activation). `target_dead` can: v may die through another required input after u was issued. That case is processed normally (§6.2 step 5, second bullet): one extra, bounded ask, then a re-issue whose snapshot says `target_dead`.

Normative handler rules (E-74 obligation 1): a gate seeing `revise` unavailable runs as the final gate — no `auto_decision`, configured policy unchanged — and maps a REVISE decision to a `reject` emission. With U5 this reproduces `_revisable_stage` (`max_traversals == max_gate_rounds`) and `step.py:912-914` exactly.

**Known limitation (U5, E73-OQ-3; skeptic F4 dispositioned).** Counters never reset, so an outer loop that re-enters a region containing a spent inner loop reaches that inner gate already exhausted. Concretely: with `architecture.revise → architect` (bound 2) spent and approved on its final gate, a later `plan.revise → architect` re-runs `architect`; `architecture#4` is issued with `revise: exhausted`, runs with no `auto_decision`, and an operator REVISE there becomes `reject` → REJECTED (the `rejected:architecture` equivalent). Resetting inner counters was rejected: when `gate.task.revise → coder` invalidates REGION(coder) it would reset `qa.fail → coder` and grant a full `max_fix_attempts` budget, where `step.py:914` grants exactly one attempt. Author mitigation today: size inner bounds with outer re-entry in mind. Scoped counters need per-instance counter namespaces (OQ-14), so that `step.py:914` stays reproduced.

### 6.6 Outcome

REJECTED/ESCALATED are terminal immediately. Else COMPLETED when `live` is empty and no node is ready (remaining `pending`/`dead` nodes are unreached branches). Else RUNNING.

### 6.7 Theorems (property-tested, not error paths)

- **Invariant I** (checked after every `advance`). If an in-edge slot holds a token, its producer node is `done`, its `taken_port == edge.source_port`, and the token came from that node's latest activation. *Proof:* a producer re-activates only after a reset; a reset happens only inside an invalidated region; step 5b clears every token whose producer is in that region, wherever the consumer sits; retired activations never deliver. Corollaries: delivery into an occupied slot is unreachable; a back-only port never carries a stale token into a later generation.
- **T1** (revised — the draft's "a back token never arrives at a running target" is **false**). A back token into a target with a live activation retires that activation and re-runs the target. Counterexample that refutes the old claim (fixture types): `E.ok → A.trigger`, `E.ok → V.trigger`, `A.art → G0.artifact`, `G0.approve → Q.req`, `G0.reject → Z.in`, `V.out → Q.opt`, `Q.out → U.opt`, `E.ok → U.trigger`, `U.fix → V.guidance` (bound 2). Script: E emits; A, V issued; A emits; G0 rejects → Q dead → `U.opt` dead → `U#1` ready while `V#1` runs; U emits `fix` → `V#1` retired, `V#2` issued.
- **T2** Forward-emission confluence: two live activations whose emissions touch no back edge, applied e1;e2 or e2;e1, give equal final `RouterState` and equal activation *sets*.
- **T3** (narrowed per skeptic F7). Where competing back edges target overlapping regions, order is semantic — the first traversal cancels live competitors inside its region; back edges into disjoint regions proceed independently. In all cases the same event script gives byte-identical state JSON.
- **T4** Termination: every event script is finite — each back edge is bounded, the forward subgraph is a DAG, and the §6.5 re-issue path increments a counter.
- **T5** Never ESCALATED on a snapshot-available port.

**Erratum (2026-09-14, plan review R1/R3 / E-73 implementation):**
- **Invariant I holds on forward slots, with I-back for back-edge slots** (producer node in `REGION(target)`; no `one` port holds two tokens) exactly as the plan's deviation 1 states (step 5b resets the emitter to `pending` before 5c delivers its token; occupied-slot delivery remains unreachable and no stale token carries into a later generation).
- **T2 equality is modulo issue-time `unavailable_ports` snapshots** exactly as deviation 2 states (`target_dead` at issue legitimately depends on forward-emission arrival order under races).
- **Section 6.5 precedence:** when a loop port is both `exhausted` and targets a dead node, `exhausted` takes precedence over `target_dead` (deviation 6).
- **Section 4 `RouterState.emissions` field:** applied emissions are stored, sorted by activation id, to support rule F3 duplicate-vs-conflicting checks while preserving deterministic state equality (deviation 3).
- **Section 7.2 T3 rows are per-override:** kind-consistent overrides are checked for harness/provider requirements (yielding at most one diagnostic per override; plan review R3 / deviation 9).

### 6.8 Deliberately not in the router

Payload inspection; retries of failed activities; per-instance (per-task) budgets (E73-OQ-7); handler-local state across activations (E73-OQ-4).

## 7. Validator

### 7.1 Order and suppression

All checks run and accumulate. The **topology tier (T5) runs only if** there is no `duplicate_node_id`, no `duplicate_edge` (duplicates may disagree on `max_traversals`, so edge classification is ambiguous; skeptic F6) and no `dangling_endpoint` (the node/edge set itself is ambiguous). A duplicated edge 4-tuple is also skipped by T4, so mixing/one-port/back-port rules do not double-report it. Topology needs only ids, endpoints, `max_traversals` — a bad type or port never hides a cycle. **Per-element suppression:** unknown-type nodes skip T3/T4; edges with unresolved ports skip compatibility/wiring. Sort key `(code, node or "", edge or (), port or "", message)`; messages use sorted joins, never set/dict reprs. No warnings tier: `topology is None ⇔ problems`.

### 7.2 Catalogue

**T1 identity** — `duplicate_node_id`; `duplicate_edge` (endpoint 4-tuple).

**T2 references** — `dangling_endpoint`; `unknown_node_type`; `unknown_port` (source port not an out-port of the source type / target port not an in-port; wrong direction counts as unknown); `incompatible_ports` (`ports_compatible` false, on EVERY edge including back edges).

**T3 node config** (E-72 §5's list)

| code | rule |
|---|---|
| `role_on_roleless_type` | `role` set, `spec.role is None` |
| `gate_on_non_gate` | `gate` set on kind ≠ gate |
| `loader_owned_field` | `role.instructions is not None` or `role.tool_files != []` |
| `role_not_in_registry` | `spec.role ∉ roles` (with or without `role`) — E-72's OPTIONAL_ROLES clause without the constant; a problem, never `KeyError` |
| `role_kind_mismatch` | `node.role.kind != roles[spec.role].kind` (catches `role: {}` on proposer/research types) |
| `role_harness_missing` | `node.role.kind == "harness"` and `harness is None` (catches `role: {}` on harness types) |
| `research_provider_missing` | `kind == "research"` override without `provider` |
| `adr6_violation` | §7.4; one problem per distinct `RegistryError` message, `node=None` |
| `adr6_combinations_exceeded` | > 256 combinations (fail closed) |
| `reserved_gate_name` | gate-kind node id ∈ `RESERVED_GATE_NAMES` |

**T4 wiring**

| code | rule |
|---|---|
| `required_in_port_unconnected` | required in-port without a FORWARD in-edge |
| `mixed_in_port` | in-port with both forward and back in-edges |
| `back_port_not_exclusive` | an out-port carrying a back edge carries any other edge |
| `back_edge_into_many` | back edge into a `many` port |
| `one_port_multiple_sources` | ≥2 forward edges into a `one` port whose sources are not distinct out-ports of a single node |

Derived lemma (not a check): every back-edge target port is optional with `one`.

**T5 topology**

| code | rule |
|---|---|
| `forward_cycle` | one per non-trivial SCC of the forward subgraph; `node` = min id; message lists members sorted |
| `bounded_edge_not_a_loop` | a bounded edge whose target does not forward-reach its source (self-loops allowed) |
| `entry_count` | nodes with no forward in-edge ≠ 1 (message lists them; zero nodes → 0) |
| `unreachable_node` | not forward-reachable from the single entry — evaluated **only when exactly one entry exists**; otherwise `entry_count` alone reports and no arbitrary anchor is chosen |

Legal degenerate rows: lone `intake`, no edges (runs COMPLETED); gate with `approve` unconnected (sink); gate with `reject` unconnected (REJECTED rule); bounded self-loop. A lone gate yields exactly `required_in_port_unconnected`.

### 7.3 `RESERVED_GATE_NAMES`

`frozenset({"budget", "clarify", "crew_question", "deploy", "deploy_failed", "merge", "readiness", "risk", "tidy_up", "tool_approval"})` — a pure constant in `validate.py`, verified against §3. E-74 removes `merge`/`deploy` when those gates become nodes.

### 7.4 ADR-6 over graphs (U4)

1. Base map `{r: rc.model for r, rc in roles.items() if rc.model is not None}`.
2. For every role some graph node's type maps to: replace its base entry with the SET of effective models across those nodes, effective = `node.role.model or roles[r].model` (mirrors `resolve_role_model`).
3. Roles no node uses keep their registry model (mirrors `cli_roles`; "requires both dev and reviewer" never trips on a real registry).
4. If ∏|models| > 256 → `adr6_combinations_exceeded`. Else for each combination in sorted order, call `validate_run_roles`; collect distinct `RegistryError` messages, sorted.

### 7.5 Deliberately not checked

`KNOWN_ROLES` membership (`check_node_types`); provider API keys (env; E-74 run start); dev/reviewer harness inequality (E73-OQ-6); anything across graph versions (gate rename is E-76's).

## 8. Testing

`tests/graph/`, fast tier, no markers.

| file | pins |
|---|---|
| `fixtures/registries.py` | Test-only registries via `registry=` injection: `fix_loop` (`coder` in `task: None`, opt `guidance: GateDecision`, out `patch: P`; `qa` in `patch: P`, out `pass: P` / `fail: GateDecision` / `escalate: P`; `gate.task` artifact `P`, approve `P`, revise → `coder.guidance`, reject; graph edges `qa.fail → coder.guidance` bounded M, `gate.task.revise → coder.guidance` bounded R; the qa handler script takes `escalate` when `fail` is unavailable), `adr6` (`dev`/`reviewer` types), `harness_type`, `fanout` (two-edge out-port + `many` collector, plus a `one` collector fed by two distinct out-ports of one brancher node); minimal valid `roles` helper. |
| `test_graph_topology.py` | SCCs, forward reach, `region == forward reach`, on hand-built graphs. |
| `test_graph_validate.py` | One table row per `ProblemCode` + meta-test that every member is produced. Suppression rows (port typo still reports the cycle; dangling endpoint and duplicate edge suppress T5; a two-root graph yields `entry_count` and no `unreachable_node`). Degenerate rows. E-72 fixture clean against seed + fixture roles, also with `plan.revise → architect` added. ADR-6 cross-product (1 breach, 2 breaches, cap). `role: {}` on proposer/research/harness types. `from_graph` raises `InvalidGraph`. |
| `test_graph_router.py` | Scripted tables `(event script) → Step sequence`: (1) fixture happy path; (2) architecture revise ×2 → `architecture#3` with `unavailable_ports={"revise": "exhausted"}` (reproduces `_revisable_stage`); (3) `fix_loop` reproduces `step.py:548-947` — M+1 attempts → gate; gate revise → exactly one more attempt; final-gate REVISE → `reject` → REJECTED (stands in for per-task `quarantined`, which is not run-terminal today — per-instance scope is E73-OQ-7); (4) `plan.revise → architect` invalidates planner, clarifier's requirements survive; (5) nested concurrent loops, outer cancels inner gate; (6) `target_dead`; (7) static fan-out + `many` collect ordered by edge key, incl. one dead branch; (8) self-loop emitter not self-cancelled, new self-token survives 5b; (9) stale emission → `dropped(stale)`; never-issued id, non-out-port, and a conflicting second emission from a finished id each raise; ESCALATED on a snapshot-unavailable port; `router_invariant` backstop in **both** forms, each built by hand-constructing an illegal `RouterState` — (9a) forward delivery into an occupied slot (§6.2 step 6), (9b) a second occupied forward slot on a `one` port (§6.4); (10) upstream-input survival: architecture revise ×2 keeps `clarifier.requirements` in `architect`'s slot (skeptic F1); (11) `many` collector with one fast and one slow branch does not fire until the slow edge resolves (F2); (12) late emission after REJECTED and after ESCALATED → `dropped(post_terminal)`, re-delivery of the escalating emission → dropped, identical duplicate from a finished id → `dropped(duplicate)` (F3/F9); (13) the §6.7 T1 counterexample: back token into running `V#1` retires it; (14) snapshot-available `fix` whose target died after issue → processed, U re-issued with `target_dead` (F5); (15) disjoint concurrent loops both revise independently (F7); (16) the §6.5 known-limitation script: re-entered spent `architecture.revise` → final gate → REVISE → REJECTED; (17) §6.4 forward exclusive merge on the `fanout` fixture: brancher emits one of its two ports → that edge's slot fills, the sibling edge is dead via `taken_port`, the `one` port is FILLED, `inputs` carries the single token, no backstop fires — for each of the two ports (reviewer R1). |
| `test_graph_router_properties.py` | Stdlib (D4): exhaustive interleavings over small fixture graphs + seeded random scripts. Invariant I after every `advance`; T1 (revised), T2, T3, T4, T5. |
| `test_graph_determinism.py` | NFR-10: golden JSON of a `ValidationReport` and a `RouterState` sequence — the script must hold ≥2 simultaneously live activations and ≥2 retired ids, so unsorted collections would show (skeptic F8) — byte-identical across 3 `PYTHONHASHSEED` subprocesses; report and `Topology` equal under permuted registry/roles insertion order and permuted `NodeTypeSpec.ports`. |
| `test_graph_purity.py` (extended) | `rglob` coverage; AST walk of everything except function/lambda bodies; allow-sets for the three modules; cold `import sdlc.graph` leaves `sdlc.agents`, `sdlc.benchmarks`, `sdlc.stages`, `temporalio` absent. |
| `test_graph_io.py` / `test_graph_model.py` | `_SCHEMA_VERSION` derived and equal to the `Literal`; `NodePort.name` regex rejection. |

Gates: `ruff check`, `ruff format --check`, `mypy`, `scripts/check_file_size.py`.

## 9. Boundaries

**FR-1202 traceability**

| FR-1202 clause | discharged by |
|---|---|
| control flow owned by a pure, synchronous router — no Temporal, no I/O | §4, §6; purity pin §8 |
| branching | §6.2 step 3 (one port per activation), §6.3 dead edges |
| fan-out and collect | §6.2 step 6, §6.3 `many` (U1 static) |
| round-based stale-input invalidation | §6.2 step 5, D1, D2 |
| per-edge `max_traversals`, exhaustion terminates ESCALATED, reproducing `max_fix_attempts` | U2, U5, §6.5; router table (3) |
| testable as tables | §8 |
| legality (port compatibility, reachability, every cycle bounded, exactly one entry) in a single validator every consumer calls | §7; `Topology` only from `validate` (U7) |
| never reimplemented in the frontend | E-76 consumes `ValidationReport` / `ProblemCode` via E-75 |

**Out of scope:** E-74 interpreter/dispatch/cutover, E-75 API, E-76 canvas, E-77 store, OQ-14 subflows.

**Unchanged:** `PipelineConfig`, `agents/loader.py`, all stages, `benchmarks/`, E-72's stored schema (no stored field added).

**Obligations handed to E-74:** (1) gate handler rules for unavailable `revise` (§6.5); (2) call `validate()` at run start with the run's resolved roles — a run-level role override is a new validation; (3) drop `merge`/`deploy` from `RESERVED_GATE_NAMES` as they become nodes; (4) cancel activities/gate waits in `Step.cancelled` and emit gate-closed events; (5) keep provider-key checks at run start.

**Docs on landing:** tick E-73 in `docs/roadmap/pipeline-as-data.md` and the ROADMAP mirror; add the three modules to ARCHITECTURE's `sdlc/graph/` entry.

## 10. Open questions (user gate)

- **E73-OQ-1** XOR-merge into a `one` port (known static extension via port-dominance on an edge-split graph).
- **E73-OQ-2** Parallel gates on one artifact: first revise wins; the other gate's guidance is lost.
- **E73-OQ-3** Never-reset: a re-entered inner loop starts at its final gate — documented as a known limitation with its exact scenario in §6.5 (challenged by skeptic F4; U5 retained, see §11).
- **E73-OQ-4** Handler-local cross-activation state (`session_id`, C2 anchor, `thawed`). Owner E-74/E72-OQ-3.
- **E73-OQ-5** General terminal-port marker, with E72-OQ-4's `fail` port.
- **E73-OQ-6** Dev/reviewer harness inequality reachable via graph `harness` overrides. Owner E-74; proposed pure `check_harness_inequality`.
- **E73-OQ-7** Dynamic fan-out and per-instance budgets. Owner E-74/OQ-14.
- **E73-OQ-8** Invalidated regions re-run unchanged work. Owner E-74 (memoisation).

## 11. Skeptic dispositions (`.workspace/tmp/e73-skeptic-full.md`)

One formal round on the full draft. Every finding is dispositioned; the advisor checked the revisions (`advisor-e73-q3.md`), which also surfaced A1–A3.

| ID | Sev. | Finding | Disposition | Where |
|---|---|---|---|---|
| F1 | Critical | "Consumed tokens are cleared" + "token this generation" starves a re-activated loop target of upstream inputs | **Accepted.** Per-edge slots; activation never clears; only step 5b clears (by producer ∈ region); terminal clears nothing. Invariant I proves survival and no stale carry-over. | §6.3, §6.7, §8 row (10) |
| F2 | Critical | `many` port FILLED on the first token → premature collect | **Accepted.** Port states defined per multiplicity over edge resolution; `many` waits for every forward in-edge to be resolved. | §6.3 table, §8 row (11) |
| F3 | Critical | `RouterError` on events after a terminal outcome → Temporal workflow-task failure loop | **Accepted, refined.** `retired` ids (cancelled or escalating emitter) → `dropped(stale\|post_terminal)`; identical duplicate → `dropped(duplicate)`; `RouterError` only for never-issued id, non-out-port, conflicting second emission. | §4, §6.2 step 1–2, §8 row (12) |
| F4 | Important | Never-reset counters make a re-entered inner loop start exhausted | **Rejected (U5 retained); limitation documented.** The proposed reset of contained back edges re-breaks `step.py:914` (a task-gate REVISE would grant a full `max_fix_attempts` budget instead of one attempt). Exact scenario, operator-visible effect and mitigation are now normative text; scoped counters deferred to OQ-14 namespaces. **Flagged for the user gate.** | §6.5, §10 E73-OQ-3, §8 row (16) |
| F5 | Important | Step 2 reads `activation.unavailable_ports`, which neither `advance`'s arguments nor `RouterState` carry | **Accepted.** `RouterState.live` stores `LiveActivation` with the issue-time snapshot; the snapshot is the contract (A2). | §4, §6.2 step 2, §6.5 |
| F6 | Important | `duplicate_edge` does not suppress T5 | **Accepted.** Also suppresses T5, and T4 for the duplicated 4-tuple. | §7.1 |
| F7 | Important | T3 overclaims cancellation for disjoint loops | **Accepted.** T3 narrowed to overlapping regions; disjoint loops proceed independently. | §6.7, §8 row (15) |
| F8 | Minor | `frozenset` in `RouterState` breaks the `PYTHONHASHSEED` golden test | **Accepted.** No set types in `RouterState`; sorted tuples / sorted-key mappings, validator-normalised; golden script exercises ≥2 live and ≥2 retired. | §4, §8 determinism row |
| F9 | Minor | No test for emissions after a terminal outcome | **Accepted.** | §8 row (12) |
| A1 | (advisor) | Draft T1 ("a back token never reaches a running target") is false — counterexample graph | **Accepted.** T1 restated as "a back token into a live target retires it"; step 5b cancels a live v explicitly; §6.4's back-only argument re-grounded on U3 rule 2 + 5b, not T1. | §6.2 step 5, §6.4, §6.7, §8 row (13) |
| A2 | (advisor) | Snapshot vs recompute diverge for `target_dead` | **Accepted.** Snapshot is the contract; a snapshot-available port into a now-dead target is processed normally and re-issued with `target_dead`; theorem T5. | §6.2 step 5, §6.5, §8 row (14) |
| A3 | (advisor) | 5b-before-5c ordering is load-bearing for self-loops | **Accepted.** Stated normatively. | §6.2 step 5, §8 row (8) |
