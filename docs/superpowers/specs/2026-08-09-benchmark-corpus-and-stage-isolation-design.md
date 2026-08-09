# Benchmark Corpus and Stage Isolation — Design

| | |
|---|---|
| Date | 2026-08-09 |
| Work items | **E-79** (DevEval corpus import), **E-80** (stage pinning), **E-81** (completeness + test-quality metrics) |
| Requirements | `BENCHMARK.md` §2 Tier A, §4.1, §5; touches FR-106, ADR-15, ADR-16, OQ-B1 |
| Scope input | Five ACL/COLING/NAACL papers (§1); `BENCHMARK.md`; `ROADMAP.md` §9.8 |
| Status | Approved design, not yet implemented |

The benchmark instrument works but measures three cases, in one language, on a
corpus we authored ourselves, one run per cell. Every number it produces is
therefore about prompts we tuned against cases we wrote. This design imports an
external, published corpus, adds the ability to grade a single stage in
isolation, and adds three metrics the current instrument cannot express.

---

## 1. What the papers actually contain

Five papers were surveyed. They are not equally useful and the design says so.

**DevEval** (COLING 2025, `2025.coling-main.502`) is the load-bearing one. A
full-lifecycle benchmark over 22 curated repositories in four languages, graded
across five stages: software design, environment setup, implementation,
acceptance testing, unit testing. Two ideas we do not have:

- A **modular evaluation protocol** — each stage is fed *reference* upstream
  artifacts, so the stage is graded alone rather than as the tail of a cascade.
- **Task types we do not grade at all** — environment setup (does the generated
  dependency file install, and do the usage examples then run), and **Oracle
  Test** for test authoring (run the model's own tests against the *reference*
  implementation and check its predicted outputs against real behaviour).

**RTADev** (Findings ACL 2025, `2025.findings-acl.80`) contributes its metric
set rather than its framework: **functional completeness**, the ratio of
fulfilled requirements to total requirements, and a placeholder scan for
`TODO`/`PASS` stubs. Its **FSD-Bench** corpus (120 tasks, 1,195 test cases)
lives in the RTADev repository with **no visible LICENSE**.

**SeDev** (ACL 2026, `2026.acl-long.1641`) extends that corpus to
**FSD-Bench++** by hand-adding 256 boundary and corner-case tests, because the
original suite was loose enough to *overestimate* functional completeness. That
is the maintenance lesson for any imported oracle, and it is the argument for
E-31a. FSD-Bench++ does not appear to be released yet.

**MASTER** (NAACL 2025, `2025.naacl-long.476`) is MCTS-driven multi-agent
coordination on HotpotQA and WebShop — not software development. One point
transfers and it is sharp: reward estimation without ground truth needs >30
simulations to be statistically significant. We run **one** run per cell and
read `mean_quality` with no confidence interval anywhere. Filed, not scheduled
(§6).

**`2025.acl-srw.31`** is a student-workshop survey on requirements engineering
with language models. No benchmark, no dataset, no metric. It is listed here so
that its absence from the rest of the document is a decision rather than an
oversight.

---

## 2. What the code looks like today

Four things established by reading the code before designing against it.

**The requirement-to-test mapping already exists.** `benchmarks/cases/*/tasks.yaml`
(`benchmarks/tasks.py:24`) declares numbered tasks, each carrying an
`error_class` and either explicit `oracle_tests` JUnit node-ids or a rubric.
`grade_tasks` already emits a `TaskGrade` per task. Functional completeness is
therefore an aggregation over records we already write — not a format change.
It is simply never rolled up, and cat-café has no `tasks.yaml`.

**`SC` is taken.** `benchmarks/sc_rollup.py` means *Success Criteria*. The
placeholder metric must not be called structural completeness or `SC` in this
codebase; it is `stub_density` throughout.

**There is a clean seam for pinning.** `FeatureWorkflow._cached_stage`
(`workflows/feature.py:766`) already substitutes a stored artifact for a
stage's execution, keyed by
`content_key(stage, input_json, prompt_sha, model, watermark)`. A pinned
reference artifact is a pre-seeded cache entry — no new dispatch path. The seam
wraps **proposer stages only** (clarify, architect, plan), which is where the
reference artifacts are anyway; coding stages would need a different lever and
are out of scope.

**The oracle grader is the model for every new grader.** `grade_oracle`
(`benchmarks/oracle.py:178`) copies a held-out suite into a detached checkout of
the produced head, runs it through the ADR-15 adapter, and is fail-safe on every
path: a broken grader returns `score=None` with a detail and never fails a cell.

---

## 3. E-79 — DevEval corpus import

`open-compass/DevEval` is Apache-2.0 code with a **CC BY 4.0 dataset**, so it is
redistributable with attribution.

### 3.1 The corpus is manifest-driven

Every repository ships `repo_config.json` naming each artifact by path:

```json
{ "PRD": "docs/PRD.md", "UML_class": "docs/UML_class.md",
  "UML_sequence": "docs/UML_sequence.md",
  "architecture_design": "docs/architecture_design.md",
  "dependencies": "docs/requirements.txt", "unit_tests": "unit_tests",
  "acceptance_tests": "acceptance_tests", "usage_examples": "examples",
  "unit_test_linking": { "unit_tests/test_check_date.py": ["query_arxiv.py"] },
  "code_file_DAG": { "query_arxiv.py": [] } }
```

Conversion is a manifest read, not a scrape. `unit_test_linking` supplies
test-to-source traceability at no cost.

### 3.2 Imported cases are not gradeable from the PRD alone

The oracles bind to exact names. Unit tests import `readtime/result.py`,
`lice/core.py`, and `query_arxiv.check_date`; the acceptance test shells out to
`python query_arxiv.py --category ...`. A run that invents a sensible but
different file tree scores approximately zero on a *correct* implementation.

This is intrinsic to DevEval, whose modular protocol always feeds reference
design as input — not a defect to engineer around. The consequence for
sequencing is that a free-form architect makes the imported grade meaningless.
Two resolutions, and the repository already uses one:

- **Contract-frozen.** The importer inlines the reference architecture tree and
  UML class diagram into the generated `case.yaml` `description`, exactly as
  cat-café freezes its `app:app` interface contract. Zero new machinery.
- **Pinned (E-80).** The architect stage is genuinely skipped and its output
  *is* the reference artifact.

**E-79 ships contract-frozen** and is independently useful. E-80 later upgrades
the same cases from "told the answer in the prompt" to a real stage skip.

### 3.3 The converter

`benchmarks/importers/deveval.py` — pure functions plus a thin CLI, run once,
output committed. No Temporal, no network at benchmark time.

| DevEval source | Kroker destination |
|---|---|
| `docs/PRD.md` | `case.yaml` `description` + frozen architecture contract |
| `unit_tests/` + `acceptance_tests/` | `oracle/` |
| `unit_test_linking` | draft `tasks.yaml` `oracle_tests` mapping |
| repository sources (everything but `docs/`, test dirs, `examples/`) | `reference/` *(new dir)* |
| `code_file_DAG` | not imported — our planner does its own decomposition, and importing DevEval's file order would hand it the answer |
| `docs/UML_*.md`, `architecture_design.md` | `reference_artifacts/` *(new dir)* |
| `docs/requirements.txt`, `examples/` | `reference_env/` *(new dir)* |
| — | `ATTRIBUTION.md` (CC BY 4.0 notice) |

`reference/` has exactly one consumer (E-81's Oracle Test), `reference_artifacts/`
exactly one (E-80's pinning), and `reference_env/` none yet — it is imported
because it is free at import time and is the input to a future environment-setup
metric (§6).

### 3.4 Two things the importer cannot do

**`tasks.yaml` cannot be fully mechanical.** PRD features are prose bullets with
no identifiers, and `unit_test_linking` maps tests to *source files*, not to
requirements. The importer emits a **draft** `tasks.yaml` at test-file
granularity with a guessed `error_class`; a human confirms it once per case.
This mirrors FSD-Bench's own construction (hand-author the core features,
generate the rest). Automating it would produce confident and wrong functional-
completeness numbers.

**Imported oracles need vetting.** `ArXiv_digest`'s acceptance test opens
`reference_output.txt` twice and compares it against itself, so that entire
assertion block is vacuous; it also `os.system`s into the working directory and
calls the live ArXiv API. This is precisely the FSD-Bench++ lesson. Each
imported oracle gets a review pass and the defects found are recorded.

### 3.5 Network is a hard filter

Several repositories (`ArXiv_digest`, `chakin`) require live network in their
oracles, colliding with NFR-5 and the E-21 network tier. The importer sets
`network_required: true` per case; those cases are **excluded from the default
corpus** and quarantined until E-21. The usable corpus will be meaningfully
smaller than the 10 Python repositories, and the plan must discover the exact
count rather than assume it.

Non-Python repositories (5 C/C++, 5 Java, 2 JavaScript) are blocked on the
E-30a/b/c adapters and are out of scope here.

---

## 4. E-80 — stage pinning

A benchmark-only `pinned_stages: dict[str, Path]` on `BenchmarkConfig`. Before
the cell's child workflow starts, an activity computes the `content_key` for
each pinned stage and `cache_put`s the reference artifact under it.
`_cached_stage` then hits naturally: its logic is unchanged and the production
path gains one config-gated pre-seed call.

Scope is the three proposer stages. Records carry `BenchmarkScope.STAGE` entries
marked `judge="pinned"`, so a pinned stage can never be read as an earned score.

Partial pinning falls out for free — pinning only clarify, and leaving architect
and plan live, measures how sensitive the downstream stages are to upstream
quality. That is the diagnostic the current end-to-end-only instrument cannot
produce.

**Pinning fails closed.** A missing or unparseable reference artifact aborts the
cell. A silently-unpinned cell would produce a plausible, wrong, and
un-diagnosable number.

---

## 5. E-81 — completeness and test-quality metrics

**Functional completeness** — new pure module `benchmarks/completeness.py`. A
task counts fulfilled iff *all* its mapped oracle tests pass;
`FC = fulfilled / total`, with `None`-scored tasks dropped from the denominator,
following the measured-versus-`not_collected` discipline of `grade_from_junit`
and `measurement.py`. Reported *beside* the test-weighted oracle pass rate,
never instead of it: the gap between them reveals a lopsided oracle. Requires a
`tasks.yaml` on every case, so cat-café gets one authored.

**Stub density** — a deterministic scan of the produced diff for placeholder
markers (`TODO`, `FIXME`, `NotImplementedError`, empty `pass` bodies, `...`
stubs), scoped to non-test source paths, with a pattern table keyed by
`ToolchainKind`. Computed from the `base...HEAD` diff already fetched at grade
time. **Reported, never gated:** `NotImplementedError` in an abstract base class
is legitimate, and a gate here is satisfiable by deleting the marker instead of
writing the code.

**Oracle Test** — new module `benchmarks/test_quality.py`, deliberately not more
weight on `oracle.py`. It takes the tests the QA stage produced, runs them
against `reference/`, and reports two numbers:

- **correctness** — the fraction of the factory's own tests that pass against
  the gold implementation. A test that fails on correct code is a wrong test.
- **reference coverage** — statement coverage those tests achieve on gold code,
  through the adapter's existing Cobertura normalisation.

Together these measure `BENCHMARK.md` §4.1's traceability gap directly rather
than by proxy. Direction matters for anti-cheat: produced *tests* are copied
into a clean checkout of `reference/`, never gold code into the worktree, so
gold code never becomes reachable by the factory.

`QualityScore.judge` gains `"pinned"` and `"reference_test"`;
`tests/test_judge_literal.py` pins that set and changes with it. Results surface
in the existing `sdlc benchmark score` output as added columns plus **one** new
grid — five grids is already near the limit of what stays readable.

---

## 6. Deliberately out of scope

Each of these is filed, not scheduled.

- **FSD-Bench / FSD-Bench++** — no visible licence on FSD-Bench, and ++ appears
  unreleased. Contingent on the authors clarifying terms.
- **Reproducing published baseline numbers** (MetaGPT, ChatDev, RTADev, SeDev).
  Matching their protocol would measure their pipeline shape, not ours.
- **SeDev's parallel-exploration arms and MASTER's MCTS** — pipeline variants,
  not benchmark types.
- **Variance and confidence intervals.** MASTER's point lands: n=1 per cell with
  no CI is not a defensible basis for a phase-exit decision. It is orthogonal to
  all three items here and folding it in would double this design.
- **The environment-setup metric** (does the generated dependency file install,
  and do the usage examples then run). `reference_env/` is imported for it, but
  the metric itself needs a sandboxed installer and belongs with E-21.
- **Non-Python DevEval repositories** — blocked on E-30a/b/c.

---

## 7. Failure handling and testing

Failure discipline differs by who is watching:

- **Graders fail safe.** Every new grader returns `score=None` plus a detail and
  never raises past its boundary, as `grade_oracle` does. `None` renders blank,
  never `0` — an unmeasured stage and a failed stage must not be confusable.
- **The importer fails loud.** It is offline, human-run, and one-shot; a
  malformed `repo_config.json` stops it, matching `load_task_suite`.
- **Pinning fails closed** (§4).
- **Network-required cases are refused at matrix expansion**, in the same place
  and style as the ADR-6 judge-family check, so rejection lands before any cell
  runs.

Tests:

| Unit | Test |
|---|---|
| importer | fixture DevEval-shaped tree in, asserted case dir out; no network |
| pinning | `content_key` determinism; Temporal test asserting a pinned stage makes zero proposer calls |
| FC, stub density | table-driven pure tests, with explicit `None`-versus-zero cases |
| Oracle Test | fixture reference implementation with known-good and known-wrong test sets |

One gate earns more than the rest: **every imported case's oracle must score 1.0
against its own `reference/`.** If the gold implementation cannot pass the suite
shipped with it, the case is broken. That single check catches the
`ArXiv_digest` self-comparison bug class, network flakiness, and any path or
import damage introduced by conversion. It runs during import and again in CI.

---

## 8. Sequencing

1. **E-79** — importer, contract-frozen cases, vetting pass, the
   reference-passes-its-own-oracle gate. Independently useful: the corpus grows
   from 3 cases to 3 + however many of the 10 Python repositories survive the
   network filter and the vetting pass (`OQ-B8`), and `OQ-B1` gets a real
   number for the first time.
2. **E-80** and **E-81** — both depend only on E-79 and are independent of each
   other.

The implementation plan that follows this spec covers **E-79 only**.

---

## 9. Open questions

- **OQ-B8 — usable corpus size.** How many of the 10 Python repositories survive
  the network filter and the vetting pass? Determined during E-79, not assumed.
- **OQ-B9 — draft `tasks.yaml` granularity.** Test-file granularity is
  mechanical but coarse; PRD-feature granularity is what functional completeness
  actually means. Is the human confirmation pass a light edit or a rewrite? The
  first two cases decide it for the rest.
- **OQ-B10 — contract-frozen versus pinned as the default.** Once E-80 lands,
  should imported cases keep the frozen contract in the description, run pinned,
  or run both as separate arms? Running both measures how much the architect
  stage contributes when it is given the answer in prose rather than skipped.

---

*Scope note, per `BENCHMARK.md`'s convention. The corpus import is anticipated
by §5 ("public anchors (external validity)") and adds no scope. Stage-isolated
evaluation (E-80) and the three metrics (E-81) are **(new scope)** measurement
capabilities and need a PRD line before they become real requirements.*
