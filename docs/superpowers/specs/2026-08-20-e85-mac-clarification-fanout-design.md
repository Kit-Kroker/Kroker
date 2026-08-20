# E-85 — MAC-style clarification fan-out for the clarify stage

| | |
|---|---|
| Status | Design — approved, awaiting spec review |
| Date | 2026-08-20 |
| Roadmap item | `E-85` (new) |
| Requirements served | Pipeline item 5 (clarify), SC-4 (repeat-clarification), US-1 |
| Scope guard | **Phase 1 only: inside the clarify stage boundary.** No change to the DAG, the human protocol, the CLI, or any downstream role. Phase 2 (downstream escalation) is designed for and explicitly not built. |
| Sources | Acikgoz et al., *MAC: A Multi-Agent Framework for Interactive User Clarification in Multi-turn Conversations*, IWSDS 2026. Zhou et al., *SWE-RPG*, arXiv:2608.09072. |

## 1. Problem

The clarify stage is the pipeline's thinnest proposer. Its entire system prompt
is one sentence (`agents/clarify/instructions.md`), and its user prompt is
`idea_json + memory` and nothing else (`prompts.py:33`). It runs once, at
`feature.py:2069`, and emits `ClarifiedRequirements` with a flat
`list[OpenQuestion]` carrying no notion of *what kind* of ambiguity each
question resolves.

Two consequences.

**We cannot measure whether it is any good.** `OpenQuestion` (`models.py:232`)
has no category, so "did clarify cover the things that actually decide the
implementation?" is not a question this codebase can currently ask. SC-4
(`sc_rollup.py:121-126`) counts clarifications and how many a human answered.
It cannot count what was never asked.

**It is structurally unable to ask the questions that matter most.** SWE-RPG
evaluated 18 coding-agent × model configurations on 163 real repository tasks
and attributed each failure to its earliest deviating stage. Requirement
clarification was the largest bucket at **24.5–46.0%** of failures, against
planning at 5.5–17.8%. The shape of the gap is specific: agents cover
high-level functional intent reliably and collapse on the implementation-facing
dimensions, scoring **42–54% coverage on interface specifications and
data-structure semantics**. Those dimensions are repo-grounded. Our clarifier
has no repo access, so it cannot reach them even in principle.

### 1.1 What MAC actually demonstrates

MAC is the architecture this design ports. On MultiWOZ 2.4 it compared four
configurations of the same multi-agent system (their Table 2):

| Configuration | Clarification by | Success Max@5 | Success Avg@5 | Avg. turns |
|---|---|---|---|---|
| MAC w/o clarification | — | 54.5 | 53.72 ± 0.92 | 6.53 |
| MAC_expert | expert | 55.6 | 54.88 ± 1.04 | 5.53 |
| MAC_supervisor | supervisor | 57.1 | 55.50 ± 1.86 | 5.11 |
| **MAC** | **both** | **62.3** | **58.40 ± 2.10** | **4.86** |

Three findings shape this spec:

1. **Both levels beat either alone**, by more than their sum — +7.8 success
   over baseline, where supervisor-only gets +2.6 and expert-only +1.1.
2. **Success went up while dialogue got shorter** (6.53 → 4.86 turns). MAC is
   not "ask more questions"; it is *ask the right question from the right
   agent*. A port that raises question volume has failed to reproduce it.
3. **Scope separation is the mechanism.** Their supervisor handles only
   domain-agnostic ambiguity and holds no domain database; experts hold the
   schemas and ask immediately before executing.

Their Algorithm 1 design note — "Only one clarification is issued per turn to
limit latency" — is the constraint we must translate, because our latency unit
is not a chat turn but a human blocking on `gate_timeout_hours`.

### 1.2 The two papers play different roles

MAC supplies the architecture. SWE-RPG supplies **the taxonomy**, because MAC's
five MultiWOZ domains (restaurant, hotel, train, taxi, attraction) have no
analogue here — "implement a software feature" is a single domain in MAC's
terms. SWE-RPG's practitioner-derived clarification dimensions, drawn from
interviews with ten engineers, are the axis along which our experts specialise:

| | Dimension | Resolves |
|---|---|---|
| C1 | Functional intent | The core behaviour change needed |
| C2 | Business semantics | Domain rules and constraints |
| C3 | Technical context | Architectural and dependency considerations |
| C4 | Interface / protocol | API contracts and signatures |
| C5 | Code structure / naming | Repository patterns and conventions |
| C6 | Data-structure semantics | Data invariants and constraints |

SWE-RPG is a benchmark, not an architecture. It contributes this table and the
evidence in §1; nothing else in it is portable.

## 2. Non-goals

- **No DAG change.** The clarify stage keeps its position, its `_cached_stage`
  call, its `ClarifiedRequirements` output type, and its gate.
- **No human-protocol change.** Still one batched round-trip through
  `clarify_pending` and `answer_question`. The CLI is untouched.
- **No downstream escalation.** Architect, planner and dev do not gain the
  right to ask. That is Phase 2 (§11), deliberately deferred so the taxonomy
  gain and the timing gain can be measured separately.
- **No new registered role.** The registry stays at 15 roles.
- **No tools on any agent.** Repo grounding arrives as a pre-computed packet,
  not as agent tool calls (D3).

## 3. Architecture

Three phases inside the existing stage boundary, mirroring the research
fan-out (`research/stage.py:110/242/338`):

```
clarify stage  (feature.py:2069, gated by cfg.clarify_probes_enabled)
│
├─ 1. clarify_route        SUPERVISOR
│      in : idea, memory snapshot, codebase-map digest
│      out: requirements body + C1/C2 questions + live dimension set
│      MAC's is_ambiguous() + select_domain(), fused into one call.
│      Holds no repo detail. Does NOT author expert questions.
│
├─ 2. clarify_probe × N    EXPERTS, concurrent, one per live dimension
│      in : idea, requirements body, the dimension's scope block,
│           and the same full `render_for_prompt` grounding packet for
│           every probe — there is no per-dimension slicer. Each probe's
│           scope block, not its input, is what narrows it.
│      out: zero or more OpenQuestion, each with evidence
│      Each runs its own is_ambiguous(); abstaining is a valid answer.
│
└─ 3. clarify_merge        PURE CODE — no model call
       dedup → rank by materiality → apply cap → assemble
       ClarifiedRequirements(open_questions=kept, dropped=cut)
```

**Why the supervisor does not author expert questions.**
`agents/discover/instructions.md` states the house rule for a proposer over a
computed packet: "You judge; you do not author." MAC splits the same way — its
supervisor routes and clarifies only what commonsense reasoning resolves, then
delegates. Fusing the two would recreate the single undifferentiated pass we
are replacing.

**Why merge is pure code.** Ranking and truncation are policy, not judgement,
and a model call there would be a third opinion with no grounding. Pure code
also makes the cap unit-testable without a model (§10).

## 4. Routing and the greenfield/brownfield split

`self._codebase_map` is populated at `feature.py:1881` — **before** clarify —
and is `None` for greenfield (`feature.py:1878`). Clarify currently ignores it
entirely. Three dimensions depend on it, and two of those differ in kind rather
than degree between modes:

| Dimension | Asked by | Greenfield | Brownfield |
|---|---|---|---|
| C1 functional intent | supervisor | always | always |
| C2 business semantics | supervisor | always | always |
| C3 technical context | probe | **skipped** | probed, map-grounded |
| C4 interface / protocol | probe | probed | probed, map-grounded |
| C5 code structure / naming | probe | **skipped** | probed, map-grounded |
| C6 data-structure semantics | probe | probed | probed, map-grounded |

C3 and C5 are skipped in greenfield because there is no existing architecture
or convention for a requirement to be ambiguous *against*. A C5 probe on an
empty tree would necessarily ask "what naming conventions should we adopt?" —
which authors a decision rather than resolving an ambiguity, and belongs to the
architect. This is the same boundary `discover` polices.

C4 and C6 survive greenfield because a contract or an invariant can be
underspecified before any code exists.

The supervisor narrows further: it returns the live subset of the
mode-permitted dimensions. A one-line CSS tweak should route to zero probes.
Probes are per-run cost, so routing is the primary cost control.

## 5. Data model

All changes additive with defaults. `benchmark score --all` re-parses
`BenchmarkRecord`s off disk and `RunSummary.clarifications` (`models.py:1190`)
feeds the SC-4 rollup, so a required field would break stored runs.

```python
class ClarificationDimension(StrEnum):
    """SWE-RPG's practitioner-derived clarification taxonomy."""
    FUNCTIONAL_INTENT  = "C1"
    BUSINESS_SEMANTICS = "C2"
    TECHNICAL_CONTEXT  = "C3"
    INTERFACE_SPEC     = "C4"
    CODE_STRUCTURE     = "C5"
    DATA_SEMANTICS     = "C6"


class OpenQuestion(BaseModel):           # models.py:232 -- additive only
    id: str
    question: str
    why_it_matters: str
    suggested_answer: str | None = None
    answer: str | None = None
    # E-85:
    dimension:   ClarificationDimension | None = None
    asked_by:    str | None = None    # "supervisor" | "probe:C4"
    materiality: float | None = None  # ranking key; None sorts last
    evidence:    str | None = None    # repo path/symbol this is grounded in


class ClarifiedRequirements(BaseModel):  # models.py:240 -- additive only
    ...
    # E-85:
    dimensions_probed: list[ClarificationDimension] = Field(default_factory=list)
    dropped:           list[OpenQuestion]           = Field(default_factory=list)


class ClarifyRoute(BaseModel):
    """clarify_route's output. Internal to the stage: never persisted, never
    reaches the human. Merge folds it into ClarifiedRequirements."""
    summary: str
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    out_of_scope: list[str]
    questions: list[OpenQuestion]              # C1/C2 only, asked_by="supervisor"
    live_dimensions: list[ClarificationDimension]   # which probes to run


class ProbeResult(BaseModel):
    """One probe's answer. An empty `questions` list is a valid, expected
    result -- it means is_ambiguous() returned 0 for this dimension."""
    dimension: ClarificationDimension
    questions: list[OpenQuestion]
```

**Who assigns `materiality`.** Whoever authors the question — the supervisor
for C1/C2, each probe for its own dimension — on a 0.0–1.0 scale defined
identically in both prompts, since `PROBE_PREFIX` is shared (§6). Merge never
re-scores; it only orders. Cross-dimension comparability is therefore a
prompt-consistency property, and §13 records it as a risk rather than a
guarantee: a probe that inflates its own scores captures the batch. The
per-dimension distribution of `materiality` in benchmark runs is the signal
that this has happened.

`dropped` is what makes the cap honest. A question that lost the ranking cut is
retained on the artifact, so the benchmark can score "material question that was
never asked" instead of it disappearing. Without it, capping and being
incurious are indistinguishable in the record.

`dimensions_probed` records what actually ran, so a degraded probe (§8) is
visible by its absence rather than being confused with a probe that ran and
abstained.

`ClarificationOutcome` gains the same optional `dimension`, so per-dimension
coverage reaches `RunSummary` and the SC-4 rollup without a schema break.

## 6. Prompts and prompt caching

`agents/clarify/instructions.md` stays the supervisor's system prompt:
registry-governed, loaded by `loader.py:163`, SHA-pinned by
`tests/test_prompt_migration.py`.

The six probe scope blocks go in a new `src/sdlc/clarify/prompts.py`, mirroring
`src/sdlc/research/prompts.py`. Two reasons:

1. **The loader would not read them anywhere else.** It reads exactly
   `instructions.md` per role, and `tools/` is hard-restricted to
   `kind: research` (`loader.py:178`, "the only role that may").
   `agents/clarify/experts/*.md` would be silently dead config — the precise
   failure the loader's `elif` at `loader.py:186` was written to prevent.
2. **Precedent.** Research's *tools* live under `agents/research/tools/`, but
   research's *fan-out prompts* already live in `src/sdlc/research/prompts.py`.

Probe prompts follow that file's caching discipline exactly, and it is not
stylistic. Its header warns that fan-out "multiplies input cost by N, which
makes this the largest cost lever here", and that a prefix under ~512 tokens is
"silently not cached — `cache_creation_input_tokens` simply stays 0, with no
error and no warning."

So: one `PROBE_PREFIX`, byte-identical across every probe in a burst, carrying
the shared method (what counts as material, what evidence to cite, that
abstaining is valid, the output contract). The per-dimension scope block is
appended *after* the prefix, never interpolated into it.

**What that actually buys, precisely.** Probes are dispatched together via
`asyncio.gather`, so no probe can read a cache entry a sibling writes in the
same burst — a cache entry is not visible until the write that creates it
completes, and all N requests are in flight at once. Within a single run the
first burst therefore pays full input price on the prefix N times. The saving
accrues **across runs**, whenever a later burst starts inside the cache TTL of
an earlier one: those probes read the prefix at ~0.1× instead of writing it.
So the shared prefix is a cross-run amortisation, not a within-burst 4×→1.3×
collapse, and §10's cost measurement must compare warm runs against cold ones
rather than reading a single run's numbers.

## 7. Memoization correctness

The trap: `_cached_stage` builds its key as `content_key(stage, input_json,
PROMPT_SHAS[stage], model, watermark)` (`feature.py:819`), and
`PROMPT_SHAS["clarify"]` hashes **only** `agents/clarify/instructions.md`
(`roles.py:111-119`). Probe prompts in `src/` are invisible to it. Edit a probe
and every prior run serves a stale memo, with no error.

**Fix:** fold the probe prompt bytes into `_STAGE_PROMPTS["clarify"]` so the
existing hash covers supervisor + probes in a fixed, sorted order. This keeps
`content_key`'s signature and every other stage untouched, and it is
semantically honest — the clarify stage's prompt genuinely is supervisor plus
probes now. It also matches the established pattern noted at
`assessment/scan/rules.py:5`: hash the real bytes.

Consequence to land deliberately:
`test_prompt_migration.py::test_prompt_shas_did_not_move` pins clarify's SHA.
That pin changes, with a comment recording that E-85 widened clarify's prompt
identity. The test's invariant (the E-2 migration was byte-identical) is
unaffected for every other role.

Second key term: the codebase-map digest joins `input_json` alongside
`idea_json + brief_digest_val` (`feature.py:2083`), for the same reason E-47a
added `identity_registry_version` to the `CapabilityMap` key — a clarification
grounded in a tree must not survive that tree changing. The digest is canonical
and coarse: same tree, same digest, memo hit.

## 8. Failure and degradation

Probes run concurrently through `run_or_degrade` (`workflows/fanout.py`), which
exists for exactly this guarantee: "a timeout, a lost worker or an exhausted
retry becomes not_collected for THAT signal while every other one still
reports. The activity's own try/except cannot keep it, because these failures
happen outside the activity."

- **Probe fails** → zero questions from that dimension; it is absent from
  `dimensions_probed`; the stage completes. A clarifier that cannot ask about
  data semantics is degraded, not broken.
- **Supervisor fails** → the stage fails and retries as today. It authors the
  requirements body; there is nothing to degrade to.
- **All probes fail** → equivalent to `clarify_probes_enabled=False`. The
  supervisor's C1/C2 output is exactly today's behaviour class.

Fail-open is right here because clarify is advisory input to a human gate, not
a floor. This is the opposite of the security floor's fail-closed rule
(FR-915), and deliberately so.

## 9. The human gate and the cap

Unchanged: all surviving questions enter the single existing `clarify_pending`
batch (`feature.py:2097`), one round-trip, same signals. `GatePolicy.OFF` still
falls back to `suggested_answer` per question (`feature.py:2089-2094`), so
unattended benchmark cells behave as they do today.

**The cap is load-bearing.** Today's prompt says to list "ONLY the open
questions whose answers materially change the design". Six dimensions sweeping
in parallel is a direct assault on that bar, and a naive port produces the
inverse of MAC's result: better coverage, worse dialogue. MAC held the line
with "one clarification per turn"; our unit is a human blocking for
`gate_timeout_hours`, so ours is a hard cap on the batch.

`clarify_question_cap: int = 5` on `PipelineConfig`. Merge ranks all candidates
by materiality and emits the top N; the remainder go to `dropped`. Dropping,
not deferring — a deferred question would need a second round-trip, which is
the cost we are protecting.

Ranking is deterministic: materiality descending, then dimension order
(C1…C6), then question id, so a tie never reorders between runs and memo
replays are stable.

**Known metric interaction.** SC-4 measures human-answered clarifications as a
*rate* (`sc_rollup.py:121-126`). Today's clarifier typically asks few
questions; a cap of 5 can raise the absolute count and move SC-4 even where
coverage improves. The cap is therefore the first knob the benchmark tunes, and
SC-4 must be read next to dimension coverage, never alone.

## 10. Testing and measurement

`clarify_probes_enabled: bool = False` on `PipelineConfig`, matching
`research_enabled` / `deep_review_enabled` (`models.py:1112-1124`). Off by
default means the default pipeline is byte-identical to today and the benchmark
can run both arms — the point of the staged path.

Following the `test_research_*` precedent:

| Test | Guards |
|---|---|
| `test_clarify_merge.py` | dedup, ranking, cap, `dropped` population, tie-break determinism. Pure functions, no model. |
| `test_clarify_prompt_cacheable.py` | `PROBE_PREFIX` ≥ ~512 tokens and byte-identical across probes. Direct analogue of `test_research_prompt_cacheable.py`; without it the cost lever fails silently. |
| `test_clarify_routing.py` | greenfield skips C3/C5; brownfield permits all six; supervisor narrowing is honoured. |
| `test_clarify_degradation.py` | one probe raises → stage completes, dimension absent from `dimensions_probed`. |
| `test_clarify_memo_key.py` | editing a probe prompt moves `PROMPT_SHAS["clarify"]`; a changed tree moves the content key. |
| `test_clarify_models.py` | additive-only: a stored pre-E-85 `ClarifiedRequirements` JSON still validates. |
| `test_clarify_stage_wiring.py` | flag off → one call, today's shape; flag on → route + probes + merge. |

**Benchmark A/B**, flag off vs on, on the existing harness:

- **Dimension coverage** — SWE-RPG's own metric, the primary one.
- **Questions surfaced vs `dropped`** — is the cap discarding material work?
- **SC-4 human-answered rate** — the regression guard from §9.
- **Stage cost** — validates the shared-prefix caching claim in §6.

MAC's own evidence sets the bar: it reported both success *and* turn count, and
would not have been persuasive with either alone. A coverage gain that lands
with a worse SC-4 rate is not a win.

## 11. Phase 2 — designed for, not built

MAC's expert clarifications fire immediately before execution, which is why
turns *fell*: nobody spends a turn on a question that turns out not to matter.
Phase 1 keeps all questioning up front and therefore captures the taxonomy gain
but not the timing gain.

Phase 2 adds an `is_ambiguous` check at architect, planner and dev, reusing the
same probe prompts and the same `OpenQuestion` shape, plus a mid-run pending
gate. `asked_by` already distinguishes `supervisor` from `probe:C4`; extending
it to `architect` is the whole seam.

Nothing in Phase 1 changes for Phase 2 to land. That is what makes the two
gains separately attributable — and given MAC's numbers (supervisor-only +2.6,
expert-only +1.1, both +7.8), knowing which half paid is the point.

## 12. Decisions

| | Decision | Rationale |
|---|---|---|
| D1 | Fan-out over one registered role, not N roles | Registry stays 15; probes are data, not folders. Mirrors `research`. Cost: no per-probe model pin. |
| D2 | Supervisor routes and asks C1/C2 only; never authors probe questions | MAC's scope separation is the mechanism, not decoration. `discover`'s "judge, do not author". |
| D3 | Repo grounding as a pre-computed packet, not agent tools | No agent in `agents/` has tools; `loader.py:178` restricts `tools/` to `kind: research`. The map is already built at `feature.py:1881`. |
| D4 | Merge is pure code | Ranking is policy, not judgement; makes the cap testable without a model. |
| D5 | C3 and C5 skipped in greenfield | With no tree, they would author conventions rather than resolve ambiguity — the architect's job. |
| D6 | All model fields additive with defaults | Stored records re-parse off disk for `benchmark score --all`. |
| D7 | Probe prompts in `src/sdlc/clarify/prompts.py`, not `agents/clarify/experts/` | The loader would never read them; follows `research/prompts.py`. |
| D8 | Fold probe bytes into `_STAGE_PROMPTS["clarify"]` | Only way the existing memo key covers them without changing `content_key`'s signature for every stage. |
| D9 | Hard cap with `dropped` retained | Protects today's materiality bar; keeps capping distinguishable from incuriosity. |
| D10 | Probes fail open, supervisor fails closed | Clarify is advisory input to a human gate; the supervisor authors the body. |
| D11 | Flag off by default | Default pipeline unchanged; enables the A/B the staged plan requires. |

## 13. Risks

**The port inverts MAC's result.** MAC cut turns; six parallel probes naturally
raise question volume. Mitigated by D9's cap, supervisor narrowing (§4), and
SC-4 as an explicit regression guard (§10) — but this is the risk that decides
whether E-85 was worth building, and the benchmark must be run before the flag
defaults on.

**Probes ask plausible but immaterial questions.** A C6 probe with nothing real
to ask may manufacture a question rather than abstain. Mitigated by making
abstention explicit in `PROBE_PREFIX`, and by requiring `evidence` for
map-grounded dimensions: a question that cannot cite a path or symbol is
dropped in merge.

**Materiality is not comparable across probes.** Each probe scores its own
questions and never sees the others', so a probe that grades itself generously
wins slots at the expense of a stricter one — and with a hard cap, that
directly decides what the human sees. The shared `PROBE_PREFIX` (§6) is the
only thing holding the scale together, which makes this a prompt-consistency
property rather than a structural guarantee. Watch the per-dimension
distribution of `materiality` across benchmark runs: a dimension whose mean
sits well above the others is inflating, not more important. If the prefix
cannot hold the scale, the fallback is round-robin selection across live
dimensions rather than a global ranking.

**Cost.** Four probes plus a supervisor against today's one call. Mitigated by
the shared cached prefix (§6), supervisor narrowing, and the existing serial
budget check after clarify (`feature.py:2130`). Measured, not assumed (§10).

**Transfer from MultiWOZ is unproven.** MAC's numbers come from task-oriented
dialogue with a user simulator across five booking domains — short turns, slot
filling, a database oracle. Software requirements are not slots, and our
"turns" are human gate round-trips measured in hours. The architecture
transfers; the magnitudes should not be assumed to. This is why the flag is off
by default and why §10 measures rather than confirms.

**SWE-RPG's taxonomy came from ten interviews.** It is the best available
practitioner grounding for code-specific clarification, not a settled ontology.
If a dimension proves consistently empty across benchmark runs, drop it from
routing rather than defending the table.
