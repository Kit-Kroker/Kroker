# Diff-scoped merge gates

**Date:** 2026-09-11
**Status:** approved design, ready for planning
**Scope:** the architectural blocker recorded against P2 (ROADMAP §0, note of 2026-08-19) — what the merge gate's absolute checks measure
**Satisfies:** SC-5 (preserved, unchanged text), FR-106 (absolute-check definitions amended), FR-108 (adapter additions), FR-915 (fail-closed discipline preserved and extended to lint and tests)
**Depends on:** ADR-14 / FR-104 (integration branch, per-task worktrees — landed), E-30 (`ToolchainAdapter`, `run_integration_checks` — landed), C3 (`MERGE_REQUIRED_CHECKS` — landed), E-40 (`security_scan_collected` — landed)
**Does not cover:** running scoped checks per task (shift-left), fencing lint-policy files in the harness sandbox, triage lint / eval-class signals (E-41 gap), wiring the opt-in semgrep/SARIF path, the other P2 demonstration defects (§DS12)

## Problem

Both 2026-08-19 brownfield demonstration runs against this repository died at
the merge gate, the second with
`rejected:merge:absolute-gate-failed:build_integration_green,lint_clean,security_no_critical`.
The gate's absolute checks measure the **repository**, not the **change**, so
any pre-existing lint debt, scanner hit, or failing test on the base branch
decides the verdict of every brownfield run — and absolute checks are never
overridable, so no operator can pass it.

Re-verified against `main` at `0aeb25e` on 2026-09-11 (several ROADMAP claims
have moved):

- `lint_clean`: `run_integration_checks` runs `adapter.lint_cmd()` =
  `ruff check .` (`toolchain/adapters.py:167`) over the whole integration
  worktree; the no-toolchain fallback is `DEFAULT_LINT_CMD = "ruff check ."`
  (`stages/merge/step.py:60`). **`ruff check .` now passes on `main`** — the
  ROADMAP's "1142 errors" is stale since the dev-tooling baseline (`5903a31`).
  Every other brownfield repository still carries the problem, and so does this
  one the day debt reappears.
- `security_no_critical`: `security_scan` (`stages/qa/activities.py:409`)
  `os.walk`s the whole worktree, untracked files included, against three
  regexes. **Measured today: 4 criticals, all pre-existing** —
  `src/sdlc/stages/qa/activities.py` (the scanner's own rule table — the rule's detail string
  `"use of eval() on untrusted input"` at `:368` matches its own pattern), `tests/test_security_floor.py` (two: the floor's own
  fixtures), `tests/test_triage_misconfig.py`. The floor flags itself.
- `security_scan` also appends **at most one finding per (rule, file)**
  (`if pattern.search(text)`, `:427-431`): the report cannot express "a second
  `eval(` was added to a file that already had one".
- `build_integration_green`: the whole suite runs at the integration head as
  `pytest -q --maxfail=25 --cov=. …` (`adapters.py:162`); the gate reads only
  `tests_passed` (`step.py:275-277`). Pre-existing failures fail it.
- Only `measure_coverage` (`stages/merge/activities.py:42`) is scoped to
  `changed_files`; `run_integration_checks` receives `changed_files` and
  ignores it.
- `changed_files` is `git diff --name-only <idea.base_branch>...HEAD`
  (`workflows/feature.py:723`), resolved at merge time against a branch name.
- Absolute checks are never overridable: `gate.py:7` (docstring),
  `evaluate_quality_gate` (`:146-168`), and `step.py:388-416` returns
  `rejected:merge:absolute-gate-failed:…` before any human gate. The ROADMAP's
  `gate.py:86` citation is stale.
- The integration head is built by `setup_integration_branch` plus serial
  `merge --no-ff` of each landed task (`vcs/integration.py:37-103`).
  `build_verification_branch` is **not** the feature integration head — it is
  E-44's tidy-up verification tree.
- **E-44 tidy-up fix runs are `FeatureWorkflow` children in `BROWNFIELD` mode**
  (`workflows/tidyup.py:228-239`), so they hit this same gate: today a
  one-finding fix PR cannot land on any repository carrying other debt. The
  product's own debt-remediation path is blocked by the same design.
- Triage's signals are `baseline`, `build_probe`, `dependencies`, `misconfig`,
  `outliers`, `scaffold`, `secrets`. None measures lint, and none measures
  `eval`-class code patterns.

For greenfield the whole-tree floor was correct, because the repository *is*
the change. P2 inherited a floor built for P1.

## Decision

Twelve decisions, numbered **DS1–DS12** so a later citation cannot collide with
E-50's GD- or FR-916's RD- vocabulary.

### DS1 — the absolute checks judge the change; SC-5's text does not move

SC-5 — *"zero deploys past a failed absolute gate check; zero unattended
deploys past any failed check"* — is unchanged. What changes is the **subject**
of FR-106's absolute checks: from "the tree is lint-clean / has no critical
security finding / is green" to **"the change introduces no lint finding, no
critical security finding, and no failing test,"** each measured against the
run's pinned base commit (DS2). Absolute stays absolute: never overridable, by
any policy or human.

**No repo-level check survives at the merge gate — not even an advisory one.**
Pre-existing state is **measured and reported** (typed fields, DS7) but decides
nothing. An advisory repo-level check was considered and rejected: it would
fail on every brownfield run, and `step.py:418-445` routes every advisory
failure through the human gate and records the run `BenchmarkOutcome.REVISED`
(`:508`), so it would become a rubber-stamped override per run — laundering
debt through the audited-override channel and turning the override record,
which calibration reads, into noise.

**Who owns pre-existing debt.** The merge gate owns non-regression only.
Measuring debt is triage's (FR-902 / E-41); fixing the mechanical subset, one
PR per finding, is tidy-up's (FR-904 / E-44). This spec does not duplicate
either. It does record the ownership **gap** it found — triage has no lint
signal and no `eval`-class signal, so those two debt classes currently have no
owner — as a roadmap delta against E-41, not as something built here. And it
names the dependency the other way: DS1 is a precondition for E-44's fix runs
to land at all.

**Alternatives rejected.**
- *Keep the repo-level absolute floor, cleared by per-finding audited
  dispositions* (E-50 GD7's store). Every brownfield onboarding would have to
  disposition every pre-existing finding before its first merge; bulk
  disposition makes "absolute" nominal; and it couples the merge gate to the
  dispositions store for a fact it does not need.
- *Mode switch* — repo floor on greenfield, change floor on brownfield. A
  branch on `idea.mode` inside the gate; greenfield falls out of the general
  rule instead (DS8).

### DS2 — "the change" is the composed integration head against a pinned base

**Base point.** `setup_integration_branch` already returns the base commit as
`IntegrationHandle.head_sha` (`feature.py:507`), but `self._integration_head`
then advances after each task merge (`task_host.py:208`). `FeatureWorkflow`
keeps the setup SHA as a separate, immutable run field, **`base_sha`**, and
passes it to `merge.step`. The gate's base is `base_sha`; the integration diff
becomes `get_task_diff(branch_point=base_sha)` instead of `idea.base_branch`.
Resolving a branch name at merge time let a force-push or rebase of the base
branch during a long run silently move the merge-base, and therefore the
baseline. `base_sha` comes from an activity result, so it is replay-safe. It is
the same commit the brownfield context stage is already pinned to
(`feature.py:519-523`), so the capability map and the gate's baseline describe
one tree.

**Composition.** The gate judges only the **composed integration head** — every
landed task, merged `--no-ff` in landing order — against `base_sha`. Per-task
own-branch-point diffs (ADR-14) remain the input of the task-level validators
and play no part in the gate. Quarantined or unmerged task work never lands, so
it is never measured. A finding introduced by task 1 and removed by task 3 nets
out, which is correct: the PR ships the composition, not the history. The
integration diff is still fetched once, after the last merge, before analyze
(`feature.py:719-727`).

**Renames and deletes.** `get_task_diff` gains a `renames` list from
`git diff -M --name-status <base_sha>...HEAD`, used to map base paths to head
paths for finding identity (DS3). A rename beyond git's similarity threshold
reads as delete + add, so its findings read as introduced — a false block, never
a leak. Copies are not mapped: a copied file's findings are introduced because
the copy is new code. A deleted file's base findings have no head counterpart
and count as **resolved**, never introduced.

`changed_files` keeps its one existing consumer, `measure_coverage`, with
unchanged semantics, now sourced from the pinned diff.

### DS3 — two-point measurement, multiset difference, line-independent identity

For lint and security the gate measures the **whole tracked tree at both
points** — `base_sha` and the integration head — and computes
**introduced = head findings − base findings** as a **multiset** difference over
a finding identity. This is the shape of Semgrep's `--baseline-commit`.

**Identity** is `(tool, rule, path, text)`:
- `path` is repo-relative POSIX (`context/delta.py:normalize_path`'s rule), with
  base paths mapped through DS2's rename list;
- `text` is the **full source line** containing the finding, whitespace-
  collapsed and stripped — not the matched span (every `eval(` has the same
  span) and not a line number (which moves when anything above it changes).

Multiset, not set: adding a second identical finding to a file counts as one
introduced. Enclosing-symbol identity was rejected — the regex scanner has no
AST, and `function_spans` exists for Python only (ADR-15 neutrality).

**Identity mutation fails toward blocking.** Editing the line a finding sits on
(or renaming past the threshold) changes its identity, so the finding reads as
introduced. That costs a human a fix, never a silent pass, and is the named
direction for every ambiguity in this spec.

**Where it runs.** A new `vcs/` activity creates a disposable **detached base
worktree** at `base_sha` under `SDLC_WORKTREES_ROOT` (the
`build_verification_branch` / `_ensure_worktree` pattern: idempotent across
retries, `reset --hard base_sha` on reuse, never pushed, never the operator's
checkout). The **composing** activities enumerate each point's tracked content
with `git ls-files` and hand explicit path lists to the measuring code, which
never walks the filesystem (DS4 states why this keeps the scan's
reproducibility property).
The multiset arithmetic is a new **pure** module, `src/sdlc/change_scope.py`
(identity, normalization, `delta(base, head, renames) -> FindingDelta`),
top-level beside `gate.py` because both the qa and merge slices consume it. It
runs inside the activities, and only the **delta** crosses the activity
boundary: introduced findings as a list, pre-existing and resolved as counts.
That keeps Temporal payloads bounded on a repository with thousands of
pre-existing findings.

**Alternatives rejected.**
- *Changed files only* (the `measure_coverage` pattern). A change would inherit
  every pre-existing finding in every file it touches. That directly contradicts
  tidy-up's seeded contract, *"Fix exactly this finding. Change nothing else"*
  (`tidyup/backlog.py:75-81`): a one-finding fix in a legacy file would be
  absolutely blocked by that file's other findings. It also misses cross-file
  effects, cannot count what Q1's reporting needs, and means nothing for tests.
- *Changed files at both points.* Cheaper, but loses cross-file effects and all
  unchanged-file visibility.

### DS4 — the security scan: per match, tracked content, both points

The per-point scan becomes a **pure function over an explicit path list**. It
uses `finditer` and emits **one finding per match**, carrying the matched source
line (`SecurityFinding` gains `line: str`). It reads only the files it is handed:
never `os.walk`, never git. The scan therefore **keeps** `security_scan`'s
docstring property — "pure filesystem read — no network, no git — reproducible
across Temporal retries" (`qa/activities.py:410-412`).

Git moves into one new qa activity, **`scoped_security_scan`**, which:
1. lists tracked files with `git ls-files` in the head worktree and in the base
   worktree;
2. runs the pure scan at each point;
3. applies `change_scope.delta`;
4. returns a **`ScopedSecurityReport`**: `state`, `reason`,
   `introduced: list[SecurityFinding]`, `preexisting: int`, `resolved: int`.

Adding git to this activity is a deliberate amendment, and reproducibility
survives it: both trees are fixed commits — the detached base at `base_sha`, and
the integration head after its last merge — so a retried activity lists and
reads the same bytes.

`SecurityReport` keeps its meaning — one point's scan — so `critical` is not
retyped and the SARIF normalizer (`toolchain/sarif.py`, not wired to any caller
today) is untouched. SARIF findings carry `line` only when the SARIF supplies a
snippet; that path's identity strength, and SARIF `partialFingerprints`, belong
to the semgrep wiring follow-up.

`_SCAN_SKIP_DIRS` stays. It is Kroker-owned, not repository-configurable, and
applies identically at both points, so it cannot create an asymmetric result.
An untracked `.sdlc-venv` is never listed. A venv or vendor tree that a change
actually *commits* is listed but still skipped at both points, so it cannot
flood the delta. Committed generated files ship, so they are measured like any
other file. There is no generated-file exemption.

**The false-negative risk, dispositioned.** Today a pre-existing critical in
unchanged code blocks every merge. After this spec it does not, and that loss is
the point of the spec, so it is dispositioned explicitly. Of the three shapes
available — accept-and-own, compensate with a periodic or every-Nth-merge full
scan, or a hybrid scope — this spec takes **accept-and-own, with full-tree
measurement on every merge**:

- **Visibility, every merge.** The scan is not diff-only. DS3 scans the whole
  tracked tree at both points on every merge gate, so an unchanged vulnerable
  file is measured, classed pre-existing, and reported, with a count in
  `ScopedSecurityReport` and in `security_no_critical`'s detail. Nothing becomes
  invisible. What changes is only that it no longer *decides*.
- **Owner.** Pre-existing findings are measured by triage (FR-902 / E-41) and
  fixed, one PR per finding, by tidy-up (FR-904 / E-44), both invoked by the
  operator. The gap for `eval`-class findings is recorded against E-41 (DS1).
- **Why not compensate.** A periodic full scan that *blocks* reintroduces the
  whole-tree veto on whichever unlucky run it lands on; one that only *reports*
  is what every merge already does. **Why not hybrid** (full scope for the cheap
  regex floor, diff scope only for expensive lenses): for this floor, full
  scope is exactly what P2 cannot pass. The cost argument does not apply either,
  since the two-point regex scan takes seconds.

The residual true false negative is a change that makes a pre-existing finding
**exploitable**, for example routing untrusted input into an existing `eval`. A
pattern scanner cannot see that under any scope. It is a scanner-capability
limit, named here, not a scoping one.

**The security floor stays unweakenable by the change.** The ruleset lives in
Kroker, has no suppression syntax, and reads nothing from the produced
repository (DS9 closes the one remaining vector, a repo-controlled allowlist).

### DS5 — lint: two-point, adapter-declared; policy relaxation is reported, not re-measured

`ToolchainAdapter` gains the adapter-level contract DS3 needs, declaratively so
that adding a language changes no gate code (FR-108):
- a machine-readable lint invocation, plus a parser into `(rule, path, line)`
  findings that distinguishes *findings found* from *tool failed* (for ruff,
  JSON output; exit 0/1 = measured, anything else or unparseable = not
  collected);
- `lint_policy_globs` (for Python: `pyproject.toml`, `ruff.toml`,
  `.ruff.toml`);
- a suppression-marker pattern (for Python: `# noqa`).

`run_integration_checks` lints the head worktree and the base worktree with
**the same tool binary** — the head environment's — so a version difference
cannot manufacture a delta. Each point uses its own tree's lint configuration.
`IntegrationChecks.lint_clean` / `lint_detail` are replaced by a typed
**`ScopedLintReport`**: `state`, `reason`, `introduced`, `preexisting`,
`resolved`, `policy_paths_changed: list[str]`, `suppressions_added: int`.

**Policy relaxation by the change** — disabling the rule it violates, adding an
exclude, or putting `# noqa` on its own new line — passes a two-point diff
under head's policy. Two mechanisms were considered and rejected:
- *Lint head under base's configuration.* This breaks DS8: on an empty greenfield
  base there is no configuration, so head would be linted under tool defaults
  instead of the run's own `[tool.ruff]`. It also misses inline suppression.
  Adding `--ignore-noqa` at both points to catch that would make every `# noqa`
  a greenfield run writes an unoverridable block.
- *A new advisory `gate_policy_unchanged` check.* A new `MERGE_REQUIRED_CHECKS`
  entry that fires whenever a dependency bump touches `pyproject.toml`.

Instead, `policy_paths_changed` and `suppressions_added` are reported, rendered
into `lint_clean`'s detail, and echoed in `GateReport.checks`. The suppression
itself is also visible, as a changed line, in the task diff the clean-context
reviewer lens already reads. Stopping weakening at its source — fencing
lint-policy paths in the harness sandbox, after C2's fence — is a named
follow-up. The stakes are bounded: only lint is exposed; the security floor is
not (DS4).

### DS6 — tests: the whole suite still runs; only attribution is scoped

A change can break an unchanged test, so the head side stays **the whole suite**.
What is scoped is *which failures are the change's*.

- **Head.** The adapter's integration `test_cmd` **drops `--maxfail`** and emits
  JUnit XML. With `--maxfail=25`, a repository with more than 25 pre-existing
  failures stops early and hides an introduced failure later in collection
  order, which is a leak under baseline semantics. Per-task QA keeps its own
  bounded contract command; only the integration command changes. The failing
  set **F** is JUnit failures plus errors, collection errors included (module
  node ids).
- **Base, targeted.** Base runs only if F is non-empty, and only the ids in F.
  Their file part is mapped back through DS2's renames, and they run through a
  new adapter method that runs selected node ids with a JUnit report (the
  existing `oracle_test_cmd` is the precedent). The adapter's environment
  provisioning runs in the base worktree first.
  - an id **absent** at base (a new test) → **introduced**, with zero flake
    tolerance: new tests must pass;
  - an id that **fails** at base → **pre-existing**;
  - an id that **passes** at base → re-run at base up to **3** more times. Any
    failure → **`preexisting_flaky`**. Passing every base attempt (4 of 4) →
    **introduced**.
  - There is **no head retry**. A head retry can only ever waive a failure,
    never convict one, so it only widens the leak.
- **Report.** A typed **`ScopedTestReport`**: `state`, `reason`, `introduced`,
  `preexisting`, `preexisting_flaky` (node-id lists), `head_failed: int`.

Two residuals are named, one in each direction:

- **False block.** A pre-existing test that is flaky at a low rate and happens
  to pass 4 of 4 at base blocks the run. This is the accepted direction.
- **False pass.** A change that genuinely breaks a test which was *already*
  flaky at base reads as `preexisting_flaky` and passes. The failure is
  reported, not blocking. The baseline cannot tell "this change made a flaky
  test fail for real" from the test's own flakiness, and resolving that would
  take a verdict on base flakiness that belongs to the test's owner (triage /
  tidy-up), not to the merge gate. The ROADMAP's in-pipeline-only failure,
`test_checkpoint_survives_dubious_ownership`, fails 5 of 5 inside the worker
environment. Base runs in that same environment, so it classes as pre-existing,
which is the intended outcome, with no flake heuristic involved.

Triage's `build_probe` was rejected as a source of base test results: it runs
in `TriageWorkflow`, not in feature runs, so it does not exist at merge time.

### DS7 — fail closed on the delta, without new checks

Each scoped report carries `state: CollectionState`, following the
`Measurement` / FR-915 discipline. **An absolute check passes only when its
report is `MEASURED` and `introduced` is empty.** Anything that prevents
computing the delta is `NOT_COLLECTED` and therefore an absolute failure. That
covers failing to create or reset the base worktree, a tool failure at either
point, an unreadable tracked file at either point, a head test run that stopped
early, produced no parseable JUnit, or collected no tests (preserving today's
verdict), and base environment provisioning failing when F is non-empty. A
not-collected report **never** reads as zero introduced.

| Check | Passes iff |
|---|---|
| `build_integration_green` | `ScopedTestReport.state is MEASURED` and `introduced == []` |
| `lint_clean` | `ScopedLintReport.state is MEASURED` and `introduced == []` |
| `security_scan_collected` | `ScopedSecurityReport.state is MEASURED`, i.e. **both** points collected |
| `security_no_critical` | no `introduced` finding has severity `critical` |

`security_no_critical` deliberately passes vacuously when the report is
`NOT_COLLECTED` — there are no introduced findings to count. The conjunct that
fails closed is `security_scan_collected`. This is today's split
(`step.py:336-346`), kept as it is. It is not a gap to "fix", and a benchmark
record showing `security_no_critical` passed alongside a failed
`security_scan_collected` means nothing was scanned, not that nothing was
found.

No `lint_collected` or `tests_collected` checks are added. Both checks are
already absolute, so a conjunction gives the identical terminal outcome. The
security split exists because `SecurityReport.critical: int = 0` was
indistinguishable from not-run (FR-915); a typed state removes that ambiguity
at the report itself. Each check's `detail` is **rendered from the typed
fields**, never parsed back out. Example:
`0 introduced; 4 pre-existing; 0 resolved` for security, and
`… ; 1 policy path changed; 2 suppressions added` for lint. The detail names
which conjunct failed and lists the introduced identities, bounded.

### DS8 — greenfield falls out; no mode switch

The merge gate never reads `idea.mode`.

**The equivalence, stated as a property.** When the base tree is empty, the
diff names every tracked file and every base measurement is empty, so
introduced = all head findings and the verdict equals today's. This holds for
all four checks. For tests, every head failure is absent at base, so it is
introduced; a head run that collects no tests stays a failure (DS7).

**Two narrowings, both named.** Untracked files in the integration worktree are
no longer scanned or linted. That is correct: they never reach the pushed branch
or the PR, so they are not part of the change. It also closes structurally the
`.sdlc-venv` false-critical class (`qa/activities.py:379-386`) that
`_SCAN_SKIP_DIRS` closed by enumeration.

**A non-empty greenfield base** is the case where intake warns and proceeds
(`context/classify.py:52-59`, whose warning reads "greenfield declared
against a tree holding N source file(s); the Architect owns the file tree and
will not see them"; the module docstring, `:24-25`, names the trees it expects:
"a README, a licence, CI config, or a previous run's work"). There the scopes diverge and the general rule applies: findings
already in the seeded tree do not block. This *is* a behaviour change, accepted.
The intake warning already tells the operator the run is not accountable for
those files, and a second greenfield run over a previous run's output is the
brownfield situation exactly. If such bases must ever be refused, that is a
Stage-0 intake decision, not a merge one.

Benchmark greenfield cases start from clean scratch repositories. Oracle and
reference trees are copied in only at grading, into a temporary worktree
(`benchmarks/oracle.py:222`), so they never appear in a run's diff.

### DS9 — fixtures: no exemption mechanism

The floor's own fixtures must stay testable without a silent blanket exemption.
**This spec adds no exemption of any kind:**
- *Not by path class* (for example, findings in test files demoted). A real
  secret in a test file is a real leak, and triage's `secrets` signal treats it
  as one.
- *Not by an in-repo allowlist.* An allowlist is repository-controlled, so a
  change could extend it. That is DS5's weakening problem moved onto the security
  floor, which today is immune.

**Pre-existing fixtures are handled by the baseline** —
`tests/test_security_floor.py`, the rule table in `qa/activities.py`, and
`tests/test_triage_misconfig.py` are pre-existing at every base that contains
them, so they are never introduced.

**New fixtures must not match in source form.** Tests assemble trigger text at
runtime (the existing scanner tests already write fixture files into `tmp_path`,
so their content can be concatenated), or keep payloads in extensions the
scanner does not read. This becomes a test-authoring convention in
`stages/qa/AGENTS.md`. The implementation of this spec follows it: the PR that
builds the scoped gate must pass it. The residual — runtime-assembled strings
evade a regex scanner — is true of any code already. It is DS4's
scanner-capability limit, not a new hole.

### DS10 — existing machinery: unchanged by construction

- **`GateConfig`** (`core/models.py:57-68`) holds only policy, threshold and
  timer fields; there is no per-check classification to change. Absolute
  failure returns before `ctx.gate` (`step.py:388-416`), so DS1 binds under
  `HARD`, `SOFT` and `OFF` alike.
- **`MERGE_REQUIRED_CHECKS` and `ABSOLUTE_FLOOR`** are unchanged: the same four
  absolute names and classes, no new entries, and the floor is still re-asserted
  on input.
- **Check names are kept** although their subject changed. They are consumed by
  the terminal status string, benchmark records, `GATE_FEEDBACK` memory, the
  aggregation scripts, and the e2e tests; renaming them is cross-cutting churn
  with no safety gain. Their meaning is recorded in `merge.md` (DS11) and
  FR-106, and the typed fields disambiguate any single record.
- **Overrides.** "Absolute never overridable" survives verbatim, and no override
  path is added. Pre-existing debt no longer fails anything, so there is nothing
  to waive; introduced findings stay unwaivable. Advisory override machinery is
  untouched.
- **Terminal statuses** are unchanged: `rejected:merge:absolute-gate-failed:<names>`,
  the same `FAIL` benchmark record, the same `GATE_FEEDBACK` retain. Only
  `detail` changes (DS7).
- **The no-toolchain fallback** (`step.py:280-299`: contract lint command plus
  the per-task QA aggregate) is **unchanged and named as a limitation**. Without
  an adapter there is no parser or selected-id runner, hence no baseline, so a
  brownfield repository in an unadapted stack still hits whole-tree lint. The
  security scan is language-agnostic and is scoped regardless.
- **Where an introduced finding surfaces.** `security_scan` and `run_lint` are
  called only from `merge/step.py`; per-task QA neither lints nor scans. So an
  introduced finding — a naively written new fixture included — is first seen at
  merge, and is terminal after the whole run's spend. That is correct under
  SC-5. Moving the same scoped checks into the per-task fix loop, so an agent can
  self-correct, is a named follow-up. It is a different placement with its own
  base-point question (task branch point vs `base_sha`).

### DS11 — seams and contracts

- `vcs/`: the base-worktree activity; `get_task_diff` gains `renames`.
- `src/sdlc/change_scope.py`: pure. Pydantic plus `measurement.py`, no
  `temporalio`.
- `stages/qa/`: `security_scan` per match over tracked files;
  `scoped_security_scan`; `ScopedSecurityReport` in `qa/models.py` (the producer
  owns its artifact).
- `stages/merge/`: `run_integration_checks` gains `base_sha` / base-worktree
  inputs and returns `ScopedLintReport` and `ScopedTestReport` (merge-owned
  models); `step` takes `base_sha` as a keyword argument from `FeatureWorkflow`.
  No cross-stage call — the orchestrator stays the sole coordinator.
- `toolchain/adapters.py`: DS5 and DS6's adapter contract; `test_cmd` loses
  `--maxfail`.
- **Replay.** The base-worktree activity inserts a new command into `merge.step`
  for workflows already in flight. The plan gates it with `workflow.patched(...)`
  (or explicitly declares in-flight runs incompatible) — named, not left to
  discovery.
- **Contracts in the same diff** (the artifact-boundary rule in `AGENTS.md`):
  `merge.md` MERGE-1.2 rewritten to state DS1/DS7 semantics, plus a new clause
  for the pinned base and two-point measurement; `qa.md` for the scanner;
  `stages/merge/AGENTS.md` and `stages/qa/AGENTS.md` invariants (the latter
  carrying DS9's convention); the PRD FR-106 amendment (Roadmap deltas).

### DS12 — what P2's demonstration needs from this spec

The exit criterion is *first brownfield feature merged via PR*. The pipeline
opens the PR; the final merge is an operator action (ROADMAP P2).

- **Target: this repository again.** It is the known-hard case: 4 pre-existing
  criticals, including the scanner's own rule table and the floor's own
  fixtures, and pre-existing and environment-only test failures. **Lint is clean
  on `main`**, so the demonstration exercises lint's baseline only as a zero-debt
  case. Lint's non-trivial path is proven by the fixture tier below and must not
  be read off the demonstration.
- **A cheap pre-flight before any multi-hour run.** The 2026-08-19 runs spent
  about nine hours discovering this design at the last stage. First, a
  deterministic fixture-repository tier (Testing) must pass. Second, an operator
  runs a one-shot smoke of the scoped activities on real `main` versus `main`,
  which must report zero introduced and non-zero pre-existing security findings.
- **Success, as observables.** A brownfield `FeatureWorkflow` against this
  repository reaches merge. The four absolute checks pass with introduced empty
  and non-zero pre-existing counts in their detail. `open_pull_request` returns
  a URL, and the operator merges it. A merge rejection on introduced > 0 is the
  gate working, not a failure of this spec. The spec claims only that
  pre-existing state no longer decides the verdict.
- **Not delivered here, and able to kill the run.** These come from the same
  ROADMAP note, with owners elsewhere: retry-prompt diagnostic truncation;
  `QAReport` cannot express "never ran"; contracts written from a false premise
  cannot be retired; `project()` tripping the deadlock detector; and `pytest-cov`
  missing from the worker image. The last is harmless here: coverage degrades to
  `NOT_COLLECTED`, which is an advisory no-op. The demonstration brief should
  pick a small, self-contained feature with its own tests, to reduce exposure to
  those risks. The choice stays with the orchestrator and the user.
- **A side effect, named but not claimed.** The same change is what lets E-44
  fix runs land PRs on a repository with debt. Demonstrating that is outside
  P2's exit criterion.

## Failure modes

| Condition | Behaviour |
|---|---|
| Base worktree cannot be created or reset | all three scoped reports `NOT_COLLECTED` → `build_integration_green`, `lint_clean` and `security_scan_collected` fail, absolute (DS7) |
| Lint tool errors or emits unparseable output at either point | `ScopedLintReport` `NOT_COLLECTED` → `lint_clean` fails (DS5, DS7) |
| A tracked source file is unreadable at either point | scan `NOT_COLLECTED` → `security_scan_collected` fails; never skipped silently (DS7) |
| Head test run stops early, yields no parseable JUnit, or collects no tests | `ScopedTestReport` `NOT_COLLECTED` → `build_integration_green` fails — the last case is today's verdict unchanged (DS6, DS7) |
| Head failure on a test id absent at base | introduced — zero flake tolerance for new tests (DS6) |
| Head failure on an id that fails at base, on any attempt | pre-existing or `preexisting_flaky`; reported, not blocking (DS6) |
| Head failure on an id passing every base attempt (4 of 4) | introduced, absolute; no head retry (DS6) |
| Base environment provisioning fails while F is non-empty | `NOT_COLLECTED` → `build_integration_green` fails (DS6) |
| The change edits the line a finding sits on, or renames past git's threshold | finding reads as introduced — a false block, the named direction (DS2, DS3) |
| The change adds a second identical finding to a file that already has one | introduced (multiset + per-match scan, DS3/DS4) |
| The change deletes a file carrying findings | counted resolved; never introduced (DS2) |
| The change relaxes lint policy or adds a suppression marker | not blocked; `policy_paths_changed` / `suppressions_added` reported in detail (DS5, named residual) |
| The base branch is force-pushed or rebased mid-run | no effect — the gate reads the pinned `base_sha` (DS2) |
| Empty base (greenfield) | verdict identical to today's (DS8) |
| Non-empty greenfield base | general rule; seeded findings do not block; intake already warned (DS8) |
| No toolchain adapter detected | today's whole-tree contract-lint and per-task-aggregate fallback, unchanged (named limitation); security still scoped (DS10) |
| A workflow in flight across the deploy of this change | `workflow.patched` branch, or declared incompatible, per the plan (DS11) |

## Testing

- **`change_scope` (pure):** multiset delta (a duplicated finding counts once
  introduced), rename mapping, the resolved count, normalization (whitespace,
  path separators — the Windows host reports `\`). The order-independence
  assertion, per `test_every_pure_signal_module_is_order_independent`'s
  per-module pattern (NFR-10).
- **Scanner:** one finding per match. The case that pins the leak: a second
  `eval(` added to a file that already has one is introduced. Tracked-only
  enumeration: an untracked file and an untracked `.sdlc-venv` are not scanned,
  structurally rather than through `_SCAN_SKIP_DIRS`. Every new fixture assembles
  its trigger text at runtime (DS9, dogfood).
- **The floor still bites on a planted fixture.** The existing per-point
  detection tests (`test_security_scan_flags_hardcoded_secret`,
  `test_security_scan_flags_eval_of_input`,
  `test_security_scan_still_flags_produced_code_beside_a_venv`) stay green
  against the pure scan. A scoped case plants the same secret and `eval(`
  fixtures as a **new** file at head and asserts `security_no_critical` fails
  with them listed as introduced. So no exemption exists that a planted fixture
  could slip through.
- **Fixture-repository tier (DS12's pre-flight).** A throwaway git repository
  shaped like this one: a pre-existing `eval` in a "rule table" file, a
  secret-shaped fixture string, a pre-existing failing test, and more than 25
  pre-existing failures. The tier's own trigger text is assembled at runtime too
  (DS9), so the tier's files never trip the gate that later lands them. Each
  case asserts both the check verdicts and the typed
  counts:
  - (i) empty change → all four absolute checks pass, with pre-existing counts
    reported;
  - (ii) second `eval(` in the same file → `security_no_critical` fails with 1
    introduced;
  - (iii) a change breaking a base-passing test that sorts after the 25
    pre-existing failures → `build_integration_green` fails (the `--maxfail`
    leak);
  - (iv) rename-only change → 0 introduced;
  - (v) delete a file carrying a finding → resolved 1, check passes;
  - (vi) a new failing test → introduced without flake tolerance;
  - (vii) a base-flaky test (fails 1 of 4 at base) → `preexisting_flaky`,
    check passes;
  - (viii) a test passing 4 of 4 at base and failing at head → introduced;
  - (ix) a lint-policy edit plus an added `# noqa` → check passes,
    `policy_paths_changed` and `suppressions_added` reported;
  - (x) a new lint finding in an untouched file, caused by a change elsewhere →
    introduced (the cross-file case DS3 exists for).
- **Fail-closed:** each `NOT_COLLECTED` row of Failure modes pinned against its
  check, including an unwritable base worktree, a lint-tool crash, unparseable
  JUnit, and a head run that collects no tests. Each is asserted terminal
  through `step`, never reaching `ctx.gate`.
- **Greenfield equivalence (DS8):** on an empty-base repository, the scoped
  verdict equals the pre-change whole-tree verdict across fixture trees (clean,
  lint finding, critical, failing test, no tests). `tests/test_e2e_greenfield.py`
  (P1's exit criterion) passes unchanged.
- **Pinned base (Temporal):** `base_sha` is taken from `setup_integration_branch`.
  Advancing the base branch mid-run leaves the integration diff and the baseline
  unchanged.
- **Manifest unchanged:** `MERGE_REQUIRED_CHECKS` and `ABSOLUTE_FLOOR` are
  byte-identical, and an absolute failure still cannot be overridden (the
  existing `test_quality_gate.py` / `test_security_floor.py` assertions stay
  green).

## Scope

### Not covered

- **Shift-left** — running the scoped checks per task inside the fix loop
  (DS10). Its own design, with its own base point.
- **A lint-policy fence in the harness sandbox**, after C2's test fence (DS5).
- **Triage lint and `eval`-class signals** — the E-41 ownership gap (DS1).
- **Wiring the opt-in semgrep/SARIF path**, and SARIF fingerprint identity
  (DS4). The normalizer is unchanged.
- **Non-Python adapters.** E-30a/b/c inherit DS5/DS6's adapter contract as
  required methods when they land.
- **The other P2 demonstration defects** (DS12), and choosing the
  demonstration feature.
- **Coverage.** `measure_coverage`'s semantics are unchanged; only the diff it
  reads is now pinned.

## Roadmap deltas

| Item | Change |
|---|---|
| P2 | Note of 2026-08-19 corrected: `ruff check .` is clean on `main` (the "1142 errors" is stale), the `gate.py:86` citation is stale, and the 4 criticals include the scanner's own rule table. The blocker becomes "diff-scoped gates specified (this spec)". P2 stays `[ ]` until the demonstration (DS12) |
| FR-106 | Amended: *"Absolute checks — the change introduces no lint finding, no critical security finding, and no failing test, each measured against the run's pinned base commit — SHALL block the merge unconditionally; no policy or human override. Findings pre-existing at the base SHALL be reported, not gated."* |
| FR-108 | Adapter contract gains machine-readable lint with a parser, lint-policy globs, a suppression pattern, selected-id test runs with JUnit, and an integration `test_cmd` without `--maxfail` |
| FR-915 | New consumers: `ScopedLintReport` / `ScopedTestReport` / `ScopedSecurityReport` carry `CollectionState`; a delta that cannot be computed never reads as zero introduced |
| SC-5 | Text unchanged; the invariant's absolute checks are FR-106's amended ones |
| E-41 | Gap recorded: no lint signal, no `eval`-class code signal; pre-existing debt of those classes has no measuring owner |
| E-44 | Unblocked by DS1: fix runs no longer inherit unrelated debt at the merge gate |
| New follow-ups | Shift-left scoped checks per task; lint-policy fence in the harness sandbox; semgrep/SARIF wiring with fingerprint identity |
| NFR-10 | One more pure module (`change_scope.py`) under the order-independence assertion |
