# Roadmap update for the 2026-09-11 platform analysis: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the third external source in the ideas register as section H, commit the verbatim source, and fix the six tracker defects (T1–T6) the spec found. Documentation only.

**Architecture:** Seven tasks, each a self-contained docs commit a reviewer could reject on its own:
1. the verbatim source file
2. the register
3. the pipeline-as-data group file
4. ordering.md
5. ROADMAP status corrections
6. the dead-path sweep
7. the spec §8 acceptance checks

Every edit is an exact find-and-replace given in full below. Nothing is paraphrased at execution time.

**Tech Stack:** Markdown; git (`core.autocrlf=true` on this host); the repo's pre-commit hooks (trailing-whitespace, end-of-file-fixer, file-size ratchet); `scripts/check_file_size.py`.

**Spec:** `docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md`. Read it with the user-gate rulings in its §10: OQ-1 A (record only); OQ-2 keep the stance; OQ-3 downgrade FR-601; OQ-4 commit the verbatim source; OQ-5 wide path reach.

## Global Constraints

- **Docs-only.** Touch exactly these 8 files and no others:
  - `docs/reports/2026-09-11-external-platform-analysis.md` (new)
  - `docs/reports/external-ideas-2026-09.md`
  - `docs/roadmap/pipeline-as-data.md`
  - `docs/roadmap/ordering.md`
  - `ROADMAP.md`
  - `docs/roadmap/filesystem-first.md`
  - `ARCHITECTURE.md`
  - `README.md`

  Never touch `PRD.md`, `BENCHMARK.md`, `src/`, `tests/`, `agents/`, `policy/`, `interfaces/`, or anything under `docs/superpowers/`.
- **1000 physical lines per file** (`scripts/check_file_size.py`, a newline count). Projected results: register ~180, pipeline-as-data ~135, ordering ~56, ROADMAP 512, the new source file 737.
- **No new E-numbers** (the next free one would be E-90). No PRD lines. Nothing is admitted to scope.
- **Designed ≠ built.** E-72…E-77, `src/sdlc/graph/`, `PipelineGraph`, `GraphRouter`, `validate.py` and `GraphWorkflow` do not exist on `main`. No sentence may describe them as existing code.
- **Real paths only.** Benchmark code is `src/sdlc/benchmarks/…`; root `benchmarks/` holds case data; `BENCHMARK.md` is at the repo root.
- **The verbatim source is never edited after it lands.** Its body is byte-identical to the capture, apart from line endings (see Task 1).
- **The only ROADMAP checkbox changes** are FR-601 (`[x]` → `[ ]` ⚠️) and FR-704 (`[ ]` → `[x]`).
- **Commits:** subject + body only, **no attribution trailers of any kind** (no `Co-Authored-By`, no session links, no generated-by lines). `git commit -F <msgfile>`, with the msgfile written by the Write tool into your scratch dir (never a heredoc). One path per `git add` argument.
- **Branch:** work on `docs/roadmap-platform-analysis`, created from `main` at the plan commit. The orchestrator fast-forwards `main`; you do not push.
- **Shell:** run every shell block in **Git Bash** (`C:\Program Files\Git\bin\bash.exe`, i.e. the Bash tool). A bare `bash` on this host's PATH is a broken WSL shim, and PowerShell cannot run `diff <(…)` process substitution.
- **Edits:** every "Replace" step is an exact-match replacement of the quoted text (use the Edit tool). If an old string does not match exactly, stop and report. Do not improvise a nearby match.

---

### Task 1: Commit the verbatim third source (OQ-4)

**Files:**
- Create: `docs/reports/2026-09-11-external-platform-analysis.md`
- Read-only input: `.workspace/tmp/2026-09-11-external-platform-analysis.md` (gitignored; 738 lines, no trailing whitespace; Step 2 normalizes line endings to LF whatever they are; lines 1–9 are the orchestrator's scratch note, line 10 is `---`, and the analysis itself runs from line 12 to 738)

**Interfaces:**
- Produces: the committed path `docs/reports/2026-09-11-external-platform-analysis.md`. Task 2's Sources row links it relatively as `2026-09-11-external-platform-analysis.md`.

- [ ] **Step 1: Create the file with its provenance header.** Use the Write tool to create `docs/reports/2026-09-11-external-platform-analysis.md` with exactly this content: 8 lines, the last one empty.

~~~markdown
# External platform analysis — 2026-09-11 (third source, verbatim)

| | |
|---|---|
| Status | Verbatim record, **never edited after it lands**. Input, not scope: nothing here is committed work until the user admits it (the register's rule) |
| Source | A third-party analysis of Kroker (a ChatGPT conversation), supplied by the user on 2026-09-11, in Russian. Everything below the rule is reproduced byte-for-byte from the capture; only line endings are normalized to LF |
| Assessed in | [`external-ideas-2026-09.md`](external-ideas-2026-09.md) §H (verdict per candidate, verified against `main`); design `docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md` |

~~~

- [ ] **Step 2: Append the capture from its `---` rule onward, with LF endings.**

Run (Git Bash):
```bash
tail -n +10 .workspace/tmp/2026-09-11-external-platform-analysis.md | tr -d '\r' >> docs/reports/2026-09-11-external-platform-analysis.md
```

- [ ] **Step 3: Verify that the body is byte-identical and the size is right.**

Run:
```bash
diff <(tail -n +10 .workspace/tmp/2026-09-11-external-platform-analysis.md | tr -d '\r') <(tail -n 729 docs/reports/2026-09-11-external-platform-analysis.md | tr -d '\r') && echo BODY-IDENTICAL
wc -l docs/reports/2026-09-11-external-platform-analysis.md
sed -n '8,11p' docs/reports/2026-09-11-external-platform-analysis.md
tr -cd '\r' < docs/reports/2026-09-11-external-platform-analysis.md | wc -c
```
Expected:
- `BODY-IDENTICAL`
- `737` lines
- lines 8–11 are: the empty header-end line, `---`, an empty line, and the line starting `Да. Если собрать всё`
- a CR count of `0`

If the count is 736, the header's empty last line is missing: add it (the file must not have `---` directly under the table) and rerun this step.

- [ ] **Step 4: Commit.** Write this message to `<scratch>/t1-msg.txt`:

~~~text
docs(reports): commit the 2026-09-11 platform analysis verbatim

The third external source for the ideas register, a third-party
analysis of Kroker supplied by the user, lands as a dated verbatim
record so register section H has durable provenance, the way the first
two sources have URLs. Ruled at the 2026-09-11 user gate (OQ-4). The
body is byte-identical to the capture with line endings normalized; the
file is never edited after it lands.
~~~

Run:
```bash
git add docs/reports/2026-09-11-external-platform-analysis.md
git commit -F <scratch>/t1-msg.txt
```
Expected: every hook `Passed`/`Skipped`. If trailing-whitespace or end-of-file-fixer modifies the file, the commit aborts: stop and report, since a verbatim record must not be hook-edited.

---

### Task 2: Register section H, the `Designed` status, and back-links

**Files:**
- Modify: `docs/reports/external-ideas-2026-09.md`: lines 1, 6, 7, 9; the Context paragraph (:11–17); the Status vocabulary (:19–26); row F1 (:90); a new §H after row G1 (:99); an addendum at the end of the file (after :143)

**Interfaces:**
- Consumes: the Task 1 path.
- Produces: the anchors `§H`, rows `H1`…`H10`, and the status `Designed`, which Tasks 3–4 cite.

- [ ] **Step 1: Title.** Replace:
~~~markdown
# External ideas — candidates from two 2026-09 sources
~~~
with:
~~~markdown
# External ideas — candidates from three 2026-09 sources
~~~

- [ ] **Step 2: Header Date row.** Replace:
~~~markdown
| Date | 2026-09-01 |
~~~
with:
~~~markdown
| Date | 2026-09-01 (sources 1–2); 2026-09-11 (source 3, §H) |
~~~

- [ ] **Step 3: Header Sources row.** Replace:
~~~markdown
Anthropic, "The AI-Native SDLC playbook" (blog, 2026-08-21) |
~~~
with:
~~~markdown
Anthropic, "The AI-Native SDLC playbook" (blog, 2026-08-21); a third-party platform analysis of Kroker itself (user-supplied, 2026-09-11), verbatim at [`2026-09-11-external-platform-analysis.md`](2026-09-11-external-platform-analysis.md) |
~~~

- [ ] **Step 4: Header Verification row.** Replace:
~~~markdown
Rendered register: [Factory Candidate Register](https://claude.ai/code/artifact/233aa568-fc5b-4297-88ed-8f51d3049678). |
~~~
with:
~~~markdown
Rendered register: [Factory Candidate Register](https://claude.ai/code/artifact/233aa568-fc5b-4297-88ed-8f51d3049678). **§H pass run 2026-09-11 against `main` @ `5534b16`**: every §H anchor checked against `src/` and the roadmap files; a designed-but-unbuilt item is marked `Designed`, never as code. |
~~~

- [ ] **Step 5: Context paragraph.** Replace:
~~~markdown
Neither replaces anything here; each contributes point improvements below.
~~~
with:
~~~markdown
Neither replaces anything here; each contributes point improvements below.

**The third source is a different kind (2026-09-11).** It is not a comparable
factory but an analysis *of this repo*: ten directions for making Kroker a
platform to design, run, evaluate and optimize delivery workflows. Most of it
lands on mechanisms already built or already designed; §H records where each
one lands.
~~~

- [ ] **Step 6: Status vocabulary.** Replace:
~~~markdown
`New` — a real build with no existing seam.
~~~
with:
~~~markdown
`New` — a real build with no existing seam. `Designed` — an unbuilt roadmap
design already specifies it; the row adds no work of its own, only priority
pressure, and nothing in it is admitted scope.
~~~

- [ ] **Step 7: Row F1 knock-on (T5).** Replace:
~~~markdown
decision inbox (E-10 dashboard). Needs a definition of urgency before it can be built |
~~~
with:
~~~markdown
decision inbox (E-10 dashboard). Needs a definition of urgency before it can be built. **Landing site is a stub (2026-09-11):** the backend `GET /inbox` is live, but `interfaces/dashboard/frontend/src/views/InboxView.vue` has been a "Plan 2" placeholder since `ac9344e` (see H5) |
~~~

- [ ] **Step 8: Insert §H after row G1.** Replace:
~~~markdown
so it wants a yes/no before the list is executed |
~~~
with the same line followed by the new section:
~~~markdown
so it wants a yes/no before the list is executed |

## H. Platform direction — the third source (2026-09-11)

Verdicts per candidate from the platform analysis, each checked against `main`.
The design and its evidence are in
`docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md`.

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| H1 | **Visual workflow builder** — a canvas that edits the workflow rather than holding separate logic | platform analysis | Designed · E-76 | `docs/roadmap/pipeline-as-data.md` E-76 is this design: `@vue-flow/core` + dagre, one renderer in run-state or editable mode, no editing of a running graph. Once E-72 exists, the analysis's node palette would map onto it (Condition = one-output-port branching, Parallel/Merge = fan-out/collect, Retry = `max_traversals`, Gate = a node carrying `GateConfig`); its Tool and Benchmark node types have no counterpart there, and Subflow is H7. Needs E-72 → E-74 first; not sequenced (see the addendum) |
| H2 | **FlowSpec** — workflow-as-code; YAML, CLI, API and GUI run the same spec | platform analysis | Designed · E-72…E-74 | E-72 `PipelineGraph` + node registry, E-73 `validate.py` as the single legality source, and E-74 `GraphWorkflow` *interpreting* a graph pinned as workflow input (no codegen, no per-edit `patched()`). None is built. **Not admitted:** FR-1200…FR-1206 have no line in `PRD.md`. The analysis's untyped YAML is not adopted over E-72's typed ports (objection (b), decided 2026-08-06) |
| H3 | **Benchmark lab** — an experiment as a first-class object; a declared matrix; comparison; a Pareto quality-vs-cost frontier | platform analysis | Extends | Built: `src/sdlc/benchmarks/matrix.py` (case × harness × arm, ADR-6 judge check at expansion), per-role arms (E-37), held-out oracle (E-31), per-role $ (E-33), the five grids of `sdlc benchmark score` (E-36), `src/sdlc/benchmarks/sc_rollup.py`, and `src/sdlc/benchmarks/experiments.py` (`Experiment`: axis, baseline vs candidate deltas, `NOISE_FLOOR = 3`, committed to git, human-written verdict). New: a Pareto view (no precedent in `docs/` or `src/`); an experiment that declares and launches its matrix (today it diffs two existing evidence sets, and the matrix is declared per case in `CaseSpec.arms`); a workflow axis, which needs E-77's `graph_sha`. Limit: `benchmarks/cases/` holds 10 cases, the bottom of OQ-B1's 10–30 estimate |
| H4 | **Evidence / traceability view** — criterion → task → files → tests → evidence → PASS, per run | platform analysis | Extends · data gap first | Built: the frozen `ValidationContract` (FR-803, `src/sdlc/stages/architecture/models.py`), the Analyst's `CriterionTrace` (`src/sdlc/stages/analyze/models.py`: task, criterion, test names; completeness enforced, FR-106), F4 Markdown renders. **Prerequisite:** nothing records a per-test or per-criterion outcome. `QAReport` is task-level and cannot tell failed from never-ran (ROADMAP P2, 2026-08-19), so a PASS column today would present a task-level boolean as a per-criterion verdict, an FR-915-class misstatement. The view belongs on the run-detail page (H5). E-51/E-52 (unbuilt) are the assessment product's bundle, not this landing site |
| H5 | **Run replay** — a per-run timeline; each step opens model, tokens, cost, duration, input/output, tools, diff, tests | platform analysis | Extends · gap verified | The data is built: `events.jsonl`/`report.html` (E-22/E-23 inside E-32, `src/sdlc/observability/export.py`), `RunSummary.roles` (E-33), `HarnessSession` (E-38), dashboard `GET /runs/{id}` and `GET /events` (E-10, `src/sdlc/dashboard/api.py`), board tasks/events (E-78). **The view is missing:** `interfaces/dashboard/frontend/src/views/RunView.vue`, like `InboxView.vue`, has been a "Plan 2" placeholder since `ac9344e`. A linear timeline needs none of E-72…E-77; the graph-shaped replay would later come from E-75 + E-76's run-state mode. Closed runs render only within Temporal retention (OQ-13) |
| H6 | **Workflow simulation / dry-run** — validate before a costly run; forecast cost, time, calls and gates | platform analysis | Extends | Today: `sdlc doctor` (F2: registry, crew layouts, harness CLIs, binaries, env, Temporal) and boot-time `validate_registry`. **When E-73 lands**, its `validate.py` adds reachability, bounded cycles and port types. New: a forecast. Nothing estimates today; FR-701 budgets enforce rather than forecast, and benchmark records already hold per-stage cost and wall time per arm. Bound: the planner decides the task count, so an honest estimate is per-stage before planning and per-task only after the plan gate |
| H7 | **Subflows** — a reusable sub-workflow (e.g. a security review) as one node | platform analysis | New | Not in E-72…E-77. There is precedent for a node that runs a child workflow: `CrewTaskWorkflow` (E-88), `DeploymentWorkflow` (E-67), the `TriageWorkflow` child (E-44/E-45). Recorded as OQ-14 in `docs/roadmap/pipeline-as-data.md`; not before E-74. The analysis's "marketplace" half is out of scope |
| H8 | **Policy engine** — governance separate from workflow; environment and risk rules decide whether a step may run | platform analysis | Extends · see B1, B3 | Built: per-gate `GateConfig` (FR-301), the C7 calibration ledger, `ABSOLUTE_FLOOR` + `MERGE_REQUIRED_CHECKS` fail-closed (C3), `policy/containment.yaml` (ADR-17, C2). The remainder is **B1** (charter) + **B3** (autonomy per environment) + risk-class conditioning, with no separate engine. Its `two_person_approval` is ⛔ blocked: operator identity is the self-asserted `X-Actor` header (OQ-11) until E-60 |
| H9 | **Cost / model router** — pick the model per task by complexity; a cheaper model first on retry | platform analysis | New · not recommended | The static half is built: per-role model per run (`resolve_role_model`, `src/sdlc/agents/roles.py`, E-37), per-role economics (E-33; BENCHMARK.md §3.2), budget gate (FR-701). Dynamic routing lowers the memo hit rate (the FR-103 key carries the model, so results stay correct but the cache runs colder), needs ADR-6 family inequality per routed pair, and needs a deterministic decision. Revisit if H3 shows per-task mixes beating per-role allocation at n ≥ `NOISE_FLOOR` |
| H10 | **Self-optimizing workflows** — the system mutates its own workflow and keeps what scores better | platform analysis | ⚠️ Product decision | **Ruled 2026-09-11: the fixed-instrument stance stands.** BENCHMARK.md §0 (a fixed, versioned instrument, changed by reviewed diff, as ADR-11 treats the DAG) and `src/sdlc/benchmarks/experiments.py` ("the tool computes the delta; the human writes the verdict"). The stance-compatible forms are F3 (proposes only), the E-4 prompt eval loop, and E-36 heatmap-driven iteration; F3 is the path. H10 is recorded as the fork beyond F3, not a duplicate of it |

> **The source's framing is not a candidate.** Its DESIGN / EXECUTE / EVALUATE /
> OPTIMIZE picture, and "workflow + evidence + evaluation" as the primary object,
> is a product thesis, the one FR-1200 was already reaching for. Recorded as
> context; it becomes scope only through the PRD.
~~~

- [ ] **Step 9: Shortlist addendum at the end of the file.** Replace:
~~~markdown
convenience rather than integrity, so it drops below the six above.
~~~
with:
~~~markdown
convenience rather than integrity, so it drops below the six above.

**Section H addendum (2026-09-11)** — ranked by leverage over existing seams; a
recommendation, not a commitment:

1. **H5** — the run-detail / replay view. It fills a stub, every data source
   exists, and it has no E-72 dependency. The same page later hosts H4 and
   E-76's run-state canvas, and the inbox view (F1's landing site) is the same
   kind of work.
2. **H4, data half** — a per-criterion outcome record. An integrity fix that
   must precede any traceability UI; it also closes the P2 "failed vs never ran"
   finding.
3. **H3** — a Pareto view and declared experiments. Honest only at n ≥
   `NOISE_FLOOR` per cell, so corpus growth (OQ-B1) is the real constraint.
4. **H1 / H2 / H7** — section 14, **ruled *record only* at the 2026-09-11 user
   gate**. Sequencing waits on a PRD line for FR-1200, OQ-10 settled, and P2's
   exit demonstrated (`docs/roadmap/ordering.md` item 7).
5. **H8** through B1/B3. **H9** waits behind H3. **H10** is ruled: the
   fixed-instrument stance stands.
~~~

- [ ] **Step 10: Verify.**

Run:
```bash
wc -l docs/reports/external-ideas-2026-09.md
grep -c "^| H[0-9]" docs/reports/external-ideas-2026-09.md
grep -n "Designed" docs/reports/external-ideas-2026-09.md | head -3
python scripts/check_file_size.py docs/reports/external-ideas-2026-09.md; echo "exit=$?"
```
Expected:
- about 180 lines (anything under 1000 passes)
- `10`
- the vocabulary line appears
- `exit=0`

- [ ] **Step 11: Commit.** Write this message to `<scratch>/t2-msg.txt`:

~~~text
docs(register): add section H for the 2026-09-11 platform analysis

Records the third external source as ten verified rows: two Designed
(E-72..E-76, unbuilt and not PRD-admitted), five Extends, one New, one
New but not recommended, and one Product decision already ruled. Adds
the Designed status, links the verbatim source, notes that F1's landing
site is a stub, and appends a section H shortlist addendum carrying the
user-gate rulings. Nothing is admitted to scope and no E-numbers are
minted.
~~~

Run:
```bash
git add docs/reports/external-ideas-2026-09.md
git commit -F <scratch>/t2-msg.txt
```

---

### Task 3: Pipeline-as-data — admission status, anchor refresh, external input, OQ-14 (T1, T2)

**Files:**
- Modify: `docs/roadmap/pipeline-as-data.md`: the framing (:3–9), objection (c) (:22–25), "Cheaper than it looks" (:27–32), "The quiet win" (:34–36), E-72 (:41), E-73 (:51–54), E-76 (:78–80), before "**Open questions.**" (:89), and the end of the file

**Interfaces:**
- Consumes: register §H row ids H1, H2, H3, H5, H6 and H7 (Task 2).
- Produces: `OQ-14`, which register row H7 cites.

**Anchors verified on `main` for this plan** (re-check each with the Step 9 command before committing):
- `_pipeline`: `src/sdlc/workflows/feature.py:469`; the file is 772 lines
- `RoleConfig`: `src/sdlc/core/models.py:176`
- `GateConfig`: `:57`
- `gate_key`: `:228`
- `CANONICAL_STAGES`: `src/sdlc/benchmarks/heatmap.py:25`; the unknown-stage handling is at `:122`
- the fix-attempt budget: `src/sdlc/stages/code/step.py:534`
- `Run.stageIdx`: `interfaces/dashboard/frontend/src/api/types.ts:18`
- `StageDots.vue` now lives in `interfaces/ui/src/components/stage_dots/`
- `handoff_enabled` no longer exists; the handoff guard is `t_handoff is not None` at `src/sdlc/workflows/feature.py:327`

- [ ] **Step 1: Framing anchor.** Replace:
~~~markdown
`feature.py::_pipeline` (line 1625, in a 2,329-line file) hardcodes stage order,
~~~
with:
~~~markdown
`FeatureWorkflow._pipeline` (`src/sdlc/workflows/feature.py:469`) hardcodes stage order,
~~~

- [ ] **Step 2: Not admitted (T1).** Replace:
~~~markdown
generic interpreter, with a canvas to edit it — n8n's model, applied to the SDLC
DAG.
~~~
with:
~~~markdown
generic interpreter, with a canvas to edit it — n8n's model, applied to the SDLC
DAG.

**Not admitted scope.** FR-1200…FR-1206 are cited throughout this file but have
**no line in `PRD.md`**, and ROADMAP §2 has no FR-1200 block: the group was
decided in a brainstorm, not admitted. **Ruled 2026-09-11** (user gate,
`docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md` §10):
record only. Sequencing waits on (a) a PRD line for FR-1200, (b) OQ-10 settled,
and (c) P2's exit demonstrated (`ordering.md` item 7).
~~~

- [ ] **Step 3: Objection (c) anchors.** Replace:
~~~markdown
  graph onto the fixed `CANONICAL_STAGES` list (`benchmarks/heatmap.py:24`), so
  the heatmap and SC rollups survive arbitrary graphs. Unmapped types record as
  `unknown`, which `heatmap.py:96` already handles.
~~~
with:
~~~markdown
  graph onto the fixed `CANONICAL_STAGES` list (`src/sdlc/benchmarks/heatmap.py:25`), so
  the heatmap and SC rollups survive arbitrary graphs. Unmapped types record as
  `unknown`, which `heatmap.py:122` already handles.
~~~

- [ ] **Step 4: "Cheaper than it looks" (T2).** Replace the whole paragraph:
~~~markdown
**Cheaper than it looks.** The node handlers already exist as methods —
`_run_clarify` (:1836), `_run_architect` (:1900), `_fan_out_research` (:803),
`_dev_task` (:1218), `_gate` (:1105), `_run_deep_review` (:876), `_run_adversary`
(:942), `_run_handoff` (:994), `_merge_task` (:1193), `_retro` (:1559). The work
is replacing the *wiring*, not the stage bodies. `_revisable_stage` (:1166)
disappears entirely: wrapping a stage in a gate-and-retry loop becomes topology.
~~~
with:
~~~markdown
**Cheaper than it looks.** The node handlers already exist, and since the B0
stage migration most are module-level functions rather than `FeatureWorkflow`
methods: `src/sdlc/stages/<stage>/step.py` for all 13 stages (clarify as
`_run_clarify_single`/`_run_clarify_fanout`, `_run_architect` inside
`stages/architecture/step.py`, `_fan_out_research` in `stages/research/step.py`,
`_run_deep_review`/`_run_adversary`/`_run_handoff` in `stages/code/step.py`),
with `_dev_task`/`_merge_task` in `workflows/task_host.py`, `_gate` in
`workflows/gates.py`, and `_retro` still in `workflows/feature.py`. The work is
replacing the *wiring*, not the stage bodies, and B0 already moved the bodies
closer to E-74's `(Activation, PipelineConfig) -> Emission` shape.
`_revisable_stage` (`workflows/role_host.py`) disappears entirely: wrapping a
stage in a gate-and-retry loop becomes topology. *Anchors refreshed 2026-09-11;
the earlier line numbers pointed into a 2,329-line `feature.py`.*
~~~

- [ ] **Step 5: "The quiet win".** Replace:
~~~markdown
**The quiet win.** Four boolean flags (`research_enabled`, `deep_review_enabled`,
`adversarial_review_enabled`, `handoff_enabled`) and their scattered
`if cfg.X_enabled and t_X is not None` guards collapse into *is there a node*.
~~~
with:
~~~markdown
**The quiet win.** Three boolean flags on `PipelineConfig` (`research_enabled`,
`deep_review_enabled`, `adversarial_review_enabled`), the handoff stage's
`t_handoff is not None` guard, and their scattered `if cfg.X_enabled and t_X is
not None` checks collapse into *is there a node*.
~~~

- [ ] **Step 6: E-72 anchors.** Replace:
~~~markdown
`RoleConfig` (`models.py:717`) and `GateConfig` (`models.py:53`) **verbatim**
~~~
with:
~~~markdown
`RoleConfig` (`src/sdlc/core/models.py:176`) and `GateConfig` (`:57`) **verbatim**
~~~

- [ ] **Step 7: E-73 anchors.** Replace:
~~~markdown
  per-edge `max_traversals` with exhaustion terminating `ESCALATED` (reproducing
  `feature.py:1464`); fan-out/collect. Rounds are not new — `gate_key(gate,
  round)` (`models.py`) already carries this semantics for gates; the router
~~~
with:
~~~markdown
  per-edge `max_traversals` with exhaustion terminating `ESCALATED` (reproducing
  the per-task `max_fix_attempts` budget, `src/sdlc/stages/code/step.py:534`);
  fan-out/collect. Rounds are not new — `gate_key(gate, round)`
  (`src/sdlc/core/models.py:228`) already carries this semantics for gates; the router
~~~

- [ ] **Step 8: E-76 anchors.** Replace:
~~~markdown
  did. `Run.stageIdx` (`api/types.ts:20`) is a linear index that cannot express
  graph position and becomes `currentNodes: string[]`; `StageDots.vue` survives by
~~~
with:
~~~markdown
  did. `Run.stageIdx` (`interfaces/dashboard/frontend/src/api/types.ts:18`) is a linear index that cannot express
  graph position and becomes `currentNodes: string[]`; `StageDots.vue` (now `interfaces/ui/src/components/stage_dots/`, E-89) survives by
~~~

- [ ] **Step 9: The external-input note and OQ-14.** Replace:
~~~markdown
**Open questions.**
~~~
with:
~~~markdown
**External input (2026-09-11).** A third-party platform analysis (register §H,
verbatim at `docs/reports/2026-09-11-external-platform-analysis.md`)
independently proposed this group's substance and ranked it first:
- its FlowSpec is E-72…E-74 (H2), and its visual builder is E-76 (H1);
- its graph-shaped run replay is E-75 + E-76's run-state mode (H5);
- the validator half of its dry-run is E-73's `validate.py` (H6);
- its workflow-as-experiment axis needs E-77's `graph_sha` (H3).

This adds priority pressure, not scope. Its untyped YAML is not adopted over
E-72's typed ports (objection (b)). The one idea it adds that this group has not
designed, subflows, is OQ-14.

**Open questions.**
~~~
Then append at the very end of the file, after the OQ-12 bullet's last line (`calibrating it needs the corpus SC-8 also needs.`):
~~~markdown
- **OQ-14 — subflows (register H7).** A subgraph node type (one node running
  another graph as a child workflow) is expressible on E-72: the 2026-08-06
  decision rejected composite nodes as the *branching* primitive, not a subgraph
  node. Child-workflow precedent exists in `CrewTaskWorkflow` (E-88),
  `DeploymentWorkflow` (E-67) and the `TriageWorkflow` child (E-44/E-45).
  Unresolved: E-73 round/stale-input semantics across the boundary,
  `canonical_stage` for inner nodes (E-77), and a composite's `graph_sha`. Not
  before E-74.
~~~
(Use an Edit whose old string is `  calibrating it needs the corpus SC-8 also needs.` and whose new string is that line plus the bullet above.)

- [ ] **Step 10: Verify the anchors and the size.**

Run:
```bash
cd "$(git rev-parse --show-toplevel)"
sed -n '469p' src/sdlc/workflows/feature.py | grep -q "async def _pipeline" && echo ok-pipeline
sed -n '176p' src/sdlc/core/models.py | grep -q "class RoleConfig" && echo ok-roleconfig
sed -n '57p' src/sdlc/core/models.py | grep -q "class GateConfig" && echo ok-gateconfig
sed -n '228p' src/sdlc/core/models.py | grep -q "def gate_key" && echo ok-gatekey
sed -n '25p' src/sdlc/benchmarks/heatmap.py | grep -q "CANONICAL_STAGES" && echo ok-canonical
sed -n '122p' src/sdlc/benchmarks/heatmap.py | grep -q "unknown" && echo ok-unknown
sed -n '534p' src/sdlc/stages/code/step.py | grep -q "max_fix_attempts" && echo ok-budget
sed -n '18p' interfaces/dashboard/frontend/src/api/types.ts | grep -q "stageIdx" && echo ok-stageidx
test -f interfaces/ui/src/components/stage_dots/StageDots.vue && echo ok-stagedots
grep -q "def _run_clarify_single" src/sdlc/stages/clarify/step.py && grep -q "def _run_clarify_fanout" src/sdlc/stages/clarify/step.py && echo ok-clarify
grep -q "def _run_architect" src/sdlc/stages/architecture/step.py && echo ok-architect
grep -q "def _fan_out_research" src/sdlc/stages/research/step.py && echo ok-research
for s in _run_deep_review _run_adversary _run_handoff; do grep -q "def $s" src/sdlc/stages/code/step.py && echo ok-$s; done
grep -q "def _dev_task" src/sdlc/workflows/task_host.py && grep -q "def _merge_task" src/sdlc/workflows/task_host.py && echo ok-taskhost
grep -q "def _gate" src/sdlc/workflows/gates.py && echo ok-gate
grep -q "def _retro" src/sdlc/workflows/feature.py && echo ok-retro
grep -q "def _revisable_stage" src/sdlc/workflows/role_host.py && echo ok-revisable
grep -rq "handoff_enabled" src/sdlc && echo STALE-handoff_enabled-exists || echo ok-no-handoff-flag
wc -l docs/roadmap/pipeline-as-data.md
```
Expected: every line prints `ok-…` (20 in total), there is no `STALE` line, and the file is about 135 lines. **If any anchor fails, stop and report. Do not guess a new number.**

- [ ] **Step 11: Commit.** Write this message to `<scratch>/t3-msg.txt`:

~~~text
docs(roadmap): refresh pipeline-as-data anchors and admission status

States that FR-1200..FR-1206 have no PRD line, and records the
2026-09-11 user-gate ruling that section 14 is record-only behind three
prerequisites. Refreshes every code anchor, which pointed into a
2,329-line feature.py that the B0 migration split into per-stage step
modules (so the rewrite is cheaper than the group file said). Corrects
the flag list (handoff_enabled is gone), maps the 2026-09-11 external
analysis onto E-72..E-77, and adds OQ-14 for subflows.
~~~

Run:
```bash
git add docs/roadmap/pipeline-as-data.md
git commit -F <scratch>/t3-msg.txt
```

---

### Task 4: ordering.md item 7 — the ruled section 14 position (T4)

**Files:**
- Modify: `docs/roadmap/ordering.md:36-44` (item 7)

**Interfaces:**
- Consumes: register rows H1/H2 (Task 2); spec §6 and §10.

- [ ] **Step 1: Replace item 7.** Replace:
~~~markdown
7. **§14 (E-72…E-77) is deliberately unsequenced.** It is the only tier that
   rewrites a core code path rather than extending one, and it competes with
   nothing above it for invariants — the factory ships fine without it. Two
   things argue for pulling it earlier anyway: **E-75 closes P2's outstanding
   dashboard-backend half** regardless of whether the interpreter lands, and the
   longer `_pipeline` accretes stages (§1 has 8 unbuilt ones), the more imperative
   wiring the big-bang rewrite has to absorb. If §14 is wanted at all, **E-72 →
   E-73 before §1 grows** is the cheap moment; E-75 can be lifted out and shipped
   on its own.
~~~
with:
~~~markdown
7. **§14 (E-72…E-77) is deliberately unsequenced; ruled *record only* at the
   2026-09-11 user gate.** It is the only tier that rewrites a core code path
   rather than extending one, and it competes with nothing above it for
   invariants: the factory ships fine without it. A 2026-09-11 external analysis
   ranked it first (register §H1/H2); the gate recorded that as priority
   pressure, not a sequencing change. Sequencing waits on three prerequisites:
   **(a)** a PRD line for FR-1200 (none exists); **(b)** OQ-10 settled (in-flight
   runs at cutover); **(c)** P2's exit demonstrated. The pipeline has never
   delivered *first brownfield feature merged via PR*, and a big-bang rewrite of
   `_pipeline` before that moves the ground under an undemonstrated claim. The
   old arguments for pulling it earlier have weakened. "E-72 → E-73 before §1
   grows is the cheap moment" matters less now that the B0 migration has made the
   stage bodies modular `step()` functions (`src/sdlc/stages/<stage>/step.py`),
   and §1 has four unbuilt stages, not eight. "E-75 closes P2's dashboard-backend
   half" was superseded 2026-08-18 by E-10. If the prerequisites clear, the
   fallback considered is E-72 + E-73 first, with E-74 gated on P2 (spec
   `docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md` §6).
~~~

- [ ] **Step 2: Verify.**

Run:
```bash
grep -c "8 unbuilt" docs/roadmap/ordering.md
grep -n "11 of 15 stages live" ROADMAP.md
wc -l docs/roadmap/ordering.md
```
Expected:
- `0`
- the ROADMAP §1 line prints (confirming "four unbuilt")
- about 56 lines

- [ ] **Step 3: Commit.** Write this message to `<scratch>/t4-msg.txt`:

~~~text
docs(roadmap): record the ruled section 14 position in ordering.md

Item 7 now states the 2026-09-11 user-gate ruling that section 14 is
record-only, lists its three prerequisites, and fixes two stale
arguments: section 1 has four unbuilt stages, not eight, and E-10
superseded the E-75 dashboard-backend rationale on 2026-08-18.
~~~

Run:
```bash
git add docs/roadmap/ordering.md
git commit -F <scratch>/t4-msg.txt
```

---

### Task 5: ROADMAP status corrections — FR-601, FR-704, NFR-4, §8 (T3, T5)

**Files:**
- Modify: `ROADMAP.md:6` (Last verified), `:279` (FR-601), `:291` (FR-704), `:387` (NFR-4), `:489` (§8 item 6)

**Interfaces:**
- Consumes: nothing from earlier tasks. Task 6 edits `ROADMAP.md:29`; it's a separate hunk, so order doesn't matter.

- [ ] **Step 1: Last verified.** Replace:
~~~markdown
| Last verified | 2026-09-02 (E-50
~~~
with:
~~~markdown
| Last verified | 2026-09-11 (FR-601, FR-704 and NFR-4 re-checked against `interfaces/dashboard/frontend/src/views/` and `src/sdlc/observability/`); 2026-09-02 (E-50
~~~

- [ ] **Step 2: FR-601 downgrade (T5, OQ-3).** Replace:
~~~markdown
- [x] **FR-601** dashboard fleet/spine/inbox — Vue 3 frontend over a FastAPI backend serving live Temporal state (E-10, 2026-08-18).
~~~
with:
~~~markdown
- [ ] ⚠️ **FR-601** dashboard fleet/spine/inbox — **fleet ✅; the run-detail (spine) and inbox views are not built** (corrected 2026-09-11). `interfaces/dashboard/frontend/src/views/RunView.vue` and `InboxView.vue` have been "implemented in Plan 2" placeholders since dashboard Plan 1 (`ac9344e`), and no Plan 2 landed, although the backend they would read is live (`GET /runs/{id}`, `GET /inbox`, `GET /events` in `src/sdlc/dashboard/api.py`). Vue 3 frontend over a FastAPI backend serving live Temporal state (E-10, 2026-08-18).
~~~
(The rest of that line, from ` Closed runs render from` to the end, is unchanged.)

- [ ] **Step 3: FR-704 (T3).** Replace:
~~~markdown
- [ ] **FR-704** observability export (`events.jsonl` + `report.html`) — no `observability/` module.
~~~
with:
~~~markdown
- [x] **FR-704** observability export (`events.jsonl` + `report.html`) — landed with the retro stage (E-32, folding E-22/E-23): `src/sdlc/observability/export.py` renders both, and the `export_run_artifacts` activity (`src/sdlc/observability/activities.py`) writes them per run. *Corrected 2026-09-11: this row said "no `observability/` module" after the module had landed.*
~~~

- [ ] **Step 4: NFR-4 (T3).** Replace:
~~~markdown
- [ ] ⚠️ **NFR-4** Auditability — Temporal history reconstructs runs; no `events.jsonl`/`report.html` export.
~~~
with:
~~~markdown
- [ ] ⚠️ **NFR-4** Auditability — Temporal history reconstructs runs, and the `events.jsonl`/`report.html` export exists (FR-704, E-32). Still partial: decisions are not a structured, queryable log (FR-304), and claim-check is not load-bearing (FR-702).
~~~

- [ ] **Step 5: §8 item 6 (T3).** Replace:
~~~markdown
observability export (**E-22, E-23**),
~~~
with:
~~~markdown
~~observability export (**E-22, E-23**)~~ (landed in E-32),
~~~

- [ ] **Step 6: Verify.**

Run:
```bash
git diff -U0 -- ROADMAP.md | grep -E "^[-+]- \["
wc -l ROADMAP.md
```
Expected: exactly six lines, three -/+ pairs:
- FR-601: `- [x]` → `+ [ ] ⚠️`
- FR-704: `- [ ]` → `+ [x]`
- NFR-4: `- [ ] ⚠️` → `+ [ ] ⚠️` (the box is unchanged)

The file stays at 512 lines.

- [ ] **Step 7: Commit.** Write this message to `<scratch>/t5-msg.txt`:

~~~text
docs(roadmap): correct FR-601, FR-704 and NFR-4 against main

FR-601 drops to partial: only the fleet view exists, while the run-detail
and inbox views have been Plan-2 placeholders since ac9344e (ruled at
the 2026-09-11 user gate). FR-704 is met by the E-32 export and flips to
done. NFR-4 loses its false no-export clause but stays partial on
FR-304 and FR-702, and section 8 strikes the landed E-22/E-23.
~~~

Run:
```bash
git add ROADMAP.md
git commit -F <scratch>/t5-msg.txt
```

---

### Task 6: The dead `docs/BENCHMARK.md` path, wide reach (T6, OQ-5)

**Files:**
- Modify: `ROADMAP.md:29`, `docs/roadmap/filesystem-first.md:156` and `:370`, `ARCHITECTURE.md:444`, `README.md:37` and `:130`

**Interfaces:**
- Consumes: nothing. `BENCHMARK.md` is at the repo root; `docs/BENCHMARK.md` has never existed (`docs/superpowers/plans/2026-09-02-b0-module-shape-and-docs-architecture.md:1022`).

- [ ] **Step 1: Confirm the six living hits** (the baseline at the plan commit):

Run:
```bash
git grep -n "docs/BENCHMARK.md" -- "*.md" ":!docs/superpowers"
```
Expected: exactly `ARCHITECTURE.md:444`, `README.md:37`, `README.md:130`, `ROADMAP.md:29`, `docs/roadmap/filesystem-first.md:156` and `:370`.

- [ ] **Step 2: Six replacements.**

| File | Replace | With |
|---|---|---|
| `ROADMAP.md` | ``> design (`docs/BENCHMARK.md`) folds`` | ``> design (`BENCHMARK.md`) folds`` |
| `docs/roadmap/filesystem-first.md` | ``Design: `docs/BENCHMARK.md`.`` | ``Design: `BENCHMARK.md` (repo root).`` |
| `docs/roadmap/filesystem-first.md` | ``(tracked in `docs/BENCHMARK.md §7`)`` | ``(tracked in `BENCHMARK.md §7`)`` |
| `ARCHITECTURE.md` | ``is `docs/BENCHMARK.md` (ROADMAP`` | ``is `BENCHMARK.md` (ROADMAP`` |
| `README.md` | `(see docs/BENCHMARK.md)` | `(see BENCHMARK.md)` |
| `README.md` | ``[`docs/BENCHMARK.md`](docs/BENCHMARK.md)`` | ``[`BENCHMARK.md`](BENCHMARK.md)`` |

- [ ] **Step 3: Verify.**

Run:
```bash
git grep -n "docs/BENCHMARK.md" -- "*.md" ":!docs/superpowers"; echo "exit=$?"
test -f BENCHMARK.md && echo ok-target
git diff --stat
```
Expected:
- no hits, then `exit=1`
- `ok-target`
- a diffstat showing exactly the four files, with 6 insertions and 6 deletions

- [ ] **Step 4: Commit.** Write this message to `<scratch>/t6-msg.txt`:

~~~text
docs: point the living docs at root BENCHMARK.md

docs/BENCHMARK.md has never existed; the B0 plan fixed AGENTS.md only.
Six living references in ROADMAP.md, filesystem-first.md, ARCHITECTURE.md
and README.md now point at the root file (wide reach, ruled at the
2026-09-11 user gate). Historical records under docs/superpowers/ are
left as written.
~~~

Run:
```bash
git add ROADMAP.md
git add docs/roadmap/filesystem-first.md
git add ARCHITECTURE.md
git add README.md
git commit -F <scratch>/t6-msg.txt
```

---

### Task 7: Acceptance checks (spec §8)

**Files:** none modified, unless a check fails. A failure is fixed in the task that owns the file, as a new commit, and then this task is re-run.

Shell state does not persist between calls, so start **every** command in this task with `BASE=$(git merge-base HEAD main);`.

- [ ] **Step 1: Ceiling.** Run `python scripts/check_file_size.py --full; echo "exit=$?"`. Expected: `exit=0`.

- [ ] **Step 2: Scope — exactly the 8 files.** Run:
```bash
BASE=$(git merge-base HEAD main)
git diff --name-only "$BASE"..HEAD | sort
```
Expected, exactly:
```
ARCHITECTURE.md
README.md
ROADMAP.md
docs/reports/2026-09-11-external-platform-analysis.md
docs/reports/external-ideas-2026-09.md
docs/roadmap/filesystem-first.md
docs/roadmap/ordering.md
docs/roadmap/pipeline-as-data.md
```

- [ ] **Step 3: Dead path gone.** Run `git grep -n "docs/BENCHMARK.md" -- "*.md" ":!docs/superpowers" | wc -l`. Expected: `0`.

- [ ] **Step 4: No new E-number.** Run `git grep -nE "\bE-9[0-9]\b" -- "*.md" ":!docs/superpowers" | wc -l`. Expected: `0` (the baseline at the plan commit is also 0).

- [ ] **Step 5: Checkbox changes limited to FR-601 and FR-704.** Run `git diff -U0 "$BASE"..HEAD -- ROADMAP.md | grep -E "^[-+]- \["`. Expected: exactly the three -/+ pairs from Task 5 Step 6, with box changes only on FR-601 and FR-704.

- [ ] **Step 6: Designed ≠ built.** Run:
```bash
git diff "$BASE"..HEAD -U0 -- docs ROADMAP.md | grep -E "^\+" | grep -nE "PipelineGraph|GraphRouter|GraphWorkflow|validate\.py|src/sdlc/graph"
```
Read every hit. Each must be phrased as design, future or conditional ("E-72 …", "when E-73 lands", "would map", "not built"), never as present-tense existing code. Report the hits and your judgment of each.

- [ ] **Step 7: The verbatim body is unchanged.** Rerun Task 1 Step 3's `diff … && echo BODY-IDENTICAL`. Expected: `BODY-IDENTICAL`. Then run `git log --format=%h -- docs/reports/2026-09-11-external-platform-analysis.md | wc -l`. Expected: `1` (exactly one commit has touched it).

- [ ] **Step 8: Commit hygiene.** Run `git log --format=%B "$BASE"..HEAD | grep -ciE "co-authored|claude-session|generated with|noreply@anthropic"`. Expected: `0`. Then run `git log --oneline "$BASE"..HEAD`. Expected: 6 commits, one per Task 1–6.

- [ ] **Step 9: Report.** Paste each check's command and output into the final report, and name any deviation from this plan. No commit in this task.
