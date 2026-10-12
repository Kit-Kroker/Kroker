# Agent architecture plan (`AP-0`…`AP-6`) → ADR-22, ADR-23, ADR-24

**Not built.** Source: `docs/reports/Kroker Agent Architecture & Implementation Plan.md`
(2026-10-04, revised 2026-10-11), the priority document for
`ARCHITECTURE.md`. `AP-n` is that plan's Phase *n*; the prefix exists
because `ROADMAP.md` already tracks phases of the benchmark improvement
plan, written `BIP-n`. Each phase ends in a gate: a benchmark or
prompt-gate result that must hold before the next phase starts.

Rules for every item below: one variable per change (never a model swap
with a prompt change); a role change runs prompt-gate when the role has an
eval set and the benchmark otherwise; new behaviour ships behind a per-role
flag in `agent.yaml`.

## AP-0 — Baseline and harness

- [ ] **AP-0.1** Re-run the benchmark on current `main` (todo-api-greenfield, cat-cafe, 2–3 deveval cases); record task pass, oracle pass, reviewer–oracle agreement, attempts per task. The plan's July–August figures come from pre-012 records, which every report marks untrusted, so this is a first baseline rather than a re-run. The reviewer–oracle view itself landed with BIP-2 (`benchmarks/gate_oracle.py`).
- [ ] **AP-0.2** Per-role tracing in one place: tool calls, retries, tokens, latency.
- [ ] **AP-0.3** Confirm the file paths the plan cites. Known so far: `_TEST_OUTPUT_MAX` is at `src/sdlc/stages/code/step.py:129`, value 1500.
- [ ] **AP-0.4** Benchmark with memory off and on; a degraded recall fails loudly in benchmark runs.

**Gate:** baseline numbers stored and reproducible within noise across two runs.

## AP-1 — Quick wins on lost inputs

- [ ] **AP-1.0** ADR-6 by model, not provider prefix. `check_adr6_families` compares prefixes, and the shipped reviewer (`zai:glm-5.3`) and `dev` (`zai-coding-plan/glm-5.3`) are the same model. Placed here, ahead of any conclusion about the reviewer drawn from the benchmark. Blocked on choosing the reviewer's second model family, because the corrected check fails the shipped registry.
- [ ] ⚠️ **AP-1.1** Pass `requirements` (with clarify answers) into the planner prompt. `stages/plan/step.py` already accepts and forwards `requirements`; whether the prompt renders it is to be confirmed under AP-0.3.
- [ ] **AP-1.2** `test_commands` / `lint_commands` in the dev prompt as the definition of done.
- [ ] **AP-1.3** Raise `_TEST_OUTPUT_MAX` to 6–8k and send the full failures section into the fix loop. Same defect as ROADMAP §0's P2 residual "the retry prompt carries no diagnostic".
- [ ] **AP-1.4** `Field(description=...)` on all output models; evidence fields before status fields. Same item as ROADMAP §7's `ReviewReport` / `MergeVerdict` ordering.
- [ ] **AP-1.5** Thinking on for reviewer, architect and planner through `RoleSpec`.

**Gate:** task pass rate up against the AP-0 baseline; share of tasks exhausting the fix budget down.

## AP-2 — Runtime foundation and topology

- [ ] **AP-2.1** `make_agent` factory, `RoleSpec` in `agent.yaml`, `ModelRouter`.
- [ ] **AP-2.2** `RepoReadTools` with commit pinning, truncation and paging.
- [ ] **AP-2.3** Validators library and evidence schemas (FR-205). Validators that read the tree run in an activity; the role loop runs in workflow code.
- [ ] **AP-2.4** Dev-harness wrapper that refuses hand-off unless the contract's commands exit 0.
- [ ] **AP-2.5** Per-role task queues and worker pools, routed from `RoleSpec` (NFR-2, ADR-9).
- [ ] **AP-2.6** Worker-specific task queue for worktree affinity, with recreate-on-loss; task branches pushed to shared storage at each checkpoint.
- [ ] **AP-2.7** `S3ArtifactStore` and Temporal `ExternalStorage` on every client and worker (FR-702, ADR-10).
- [ ] **AP-2.8** Per-role lifecycle events on `RunEvent`: model, tool start/end, approval, usage.
- [ ] **AP-2.9** `RoleRunner` port with SDK-neutral tool definitions and event schema; pydantic-ai the only adapter, behaviour unchanged (ADR-23).

**Gate:** no metric regression; every existing role runs through the factory.

## AP-3 — Evidence-based QA and reviewer

- [ ] **AP-3.1** Reviewer eval set: historical (diff, oracle fail, review approve) pairs plus seeded mutations; wired into prompt-gate.
- [ ] **AP-3.2** QA as evidence tracer: `AssertionEvidence`, repo tools, `run_single_test`; `tests_passed` computed.
- [ ] **AP-3.3** Reviewer as four lenses on another family, quote-in-file validator, `approve` computed (ADR-24).
- [ ] **AP-3.4** Regression check activity for key assertions.
- [ ] **AP-3.5** Adversary replaced by two samples of the correctness lens; `deep_review` on signals only.
- [ ] **AP-3.6** Validators and verdict functions run as Kroker code after the SDK returns, with Kroker's own retry-with-error loop.
- [ ] **AP-3.7** Task ledger for the fix loop; recall of `gotcha` and `gate_feedback` for dev, QA and reviewer.
- [ ] **AP-3.8** Run UI: evidence view per task.
- [ ] **AP-3.9** Run UI: `RunState` snapshot plus JSON Patch stream, replay scrubber over `RunEvent`, time and cost per role.

**Gate:** reviewer recall on mutations at or above an agreed target with false-block rate under a threshold; reviewer–oracle agreement clearly above the baseline. Both thresholds are open questions in the plan.

## AP-4 — Planner and architect

- [ ] **AP-4.1** Planner split: decompose with repo tools, then compile one contract per task.
- [ ] **AP-4.2** Plan validators (DAG, coverage, size) and the contract dry-run activity. Addresses ROADMAP §0's P2 residuals on false-premise contracts and tests that never ran.
- [ ] **AP-4.3** `devops_planner` folded into decompose.
- [ ] **AP-4.4** Architect with repo tools, delta check as a validator, `requirement_coverage`.
- [ ] **AP-4.5** Architect and plan critics on another family; one revision round.
- [ ] **AP-4.6** Prompt-gate vetoes for planner and architect.

**Gate:** share of tasks exhausting the fix budget and contract errors (exit 127, unverifiable assertions) down against AP-3.

## AP-5 — Test-first, research, cleanup

- [ ] **AP-5.1** Test harness writes tests from the contract before dev; the test freeze locks them. Needs AP-4.2 and the test-integrity lens of AP-3.3 first, or it freezes bad tests.
- [ ] **AP-5.2** Research: numbered-fragment fetch, citations by `fragment_id`, validator.
- [ ] **AP-5.3** Analyst as aggregator; `merge_verdict` becomes the release summary.
- [ ] **AP-5.4** Clarify probes with repo tools, deduplicated and ranked in code; thin prompts rewritten.
- [ ] **AP-5.5** Memory: verified-only retention, promotion to the `org` bank (E-25), pruning by use.

**Gate:** research grounding rejections near zero; end-to-end pass above the AP-0 baseline by a margin agreed in AP-0.

## AP-6 — Second SDK adapter (only when a reason appears)

- [ ] **AP-6.1** Pick the SDK by need.
- [ ] **AP-6.2** Adapter: tool translation, event mapping, model and usage reporting, durability.
- [ ] **AP-6.3** One role on it first, with replay tests for the adapter.

**Gate:** the same role on both SDKs gives comparable prompt-gate and benchmark results with no change to workflow code.

## Open questions carried from the plan

- Which second model family is affordable for reviewer and critics? Blocks AP-1.0.
- What reviewer recall and false-block thresholds pass the AP-3 gate?
- Worktrees on host-affine workers or in a remote sandbox?
- The plan lists a human gate after clarify. `graph/node_types.py` has none; clarify's human step is a Q&A channel. Either the plan drops that gate or it is new work.
