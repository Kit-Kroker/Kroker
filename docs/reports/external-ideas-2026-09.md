# External ideas — candidates from two 2026-09 sources

| | |
|---|---|
| Status | Input list — **not scope**. Nothing below is committed work until it gets a PRD line (same rule as BENCHMARK's "new scope" items). |
| Date | 2026-09-01 |
| Sources | [`addyosmani/factory`](https://github.com/addyosmani/factory) (reference software factory for Claude Code / Codex); Anthropic, "The AI-Native SDLC playbook" (blog, 2026-08-21) |
| Method | Each candidate is mapped to where it would land in this codebase. Verified anchors (FR/E/ADR numbers) are cited; everything else is described behaviourally until specced. |
| Verification | **Pass run 2026-09-01 against `main`** (E-88 landed at `c308856`). Every candidate now carries a **Status**: the anchor it names was checked against `src/`, not against the PRD. Anchors re-confirmed 2026-09-01 after the merge. Rendered register: [Factory Candidate Register](https://claude.ai/code/artifact/233aa568-fc5b-4297-88ed-8f51d3049678). |

**Context.** Both sources were assessed against the 15-stage DAG and found to
be coarser-grained implementations of the same model this repo already runs
(committed artifacts as stage handoff, humans at gates, deterministic checks
behind advisory LLM passes, loop closure through production signals). The
factory repo is prompt/policy-only over stock Claude Code; the playbook is
org-level process guidance around `.md` artifacts and Claude Code primitives.
Neither replaces anything here; each contributes point improvements below.

**What Status means.** `Gap verified` — the gap was confirmed in code, and the
landing site exists. `Extends` — the mechanism is here; the candidate widens
it. `New` — a real build with no existing seam. `Blocked` — it lands on a
component that does not exist. `Needs an owner` / `Product decision` — not
buildable as written until someone settles what it means.

---

## A. External loop — how work enters the factory

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| A1 | **GitHub Issues as an intake queue** — an adapter that triages labeled issues into intake/clarify, and closes the issue when the run finishes | factory | New | new intake channel alongside CLI / MCP / Slack |
| A2 | **Intent home for non-git contributors** — product owners and support submit intents in natural language, committed under their own authorship with write permissions per home | playbook | Extends | intake via MCP/Slack already possible; missing piece is a durable, permissioned intents home with attribution |
| A3 | **Incident channel as audit trail** — request, diagnosis, human authorization, and fix stay in one thread that is itself the record | playbook | Extends | Slack operator surface over `channels/inbox.py`; make the channel self-sufficient as evidence |
| A4 | **Signal → intent artifact** — a breached control band writes a new intent and enters the pipeline like any other work | both | ⛔ **Blocked · FR-501** | DAPER Detect — **not implemented**; there is no `MaintenanceWorkflow` to raise the signal |

## B. Risk budget and graduated autonomy

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| B1 | **Human-owned charter** — a per-project doc (only humans may change it) stating autonomy tiers, protected paths, and what may run unattended | factory | Extends | formalize over `PipelineConfig.gates` + existing risk classes (worktrees are already risk-classed) |
| B2 | **σ-bands (`bands.yaml`)** — graduated maintenance response: 1σ log / 2σ diagnose read-only / 3σ propose PR; Western Electric rules; config in VCS, fully deterministic detection | playbook | ⛔ **Blocked · FR-501** | reads as "swap a binary confidence gate for tiered classes", but the gate it tiers does not exist — this requires building the DAPER loop first |
| B3 | **Autonomy per environment** — dev acts freely, staging partial, production only up to the gate | playbook | New | `PipelineConfig.deploy`: permission tiers per environment |
| B4 | **Fleet back-pressure (STOP_IF)** — a cap on decisions pending human review; new runs refuse to start while the queue is over the cap | both | ✅ Gap verified | fleet level (dashboard / scheduler). FR-303 holds a *single* run for a human; nothing caps the fleet's pending-decision total |

## C. Verification and quality

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| C1 | **Revert-proof verifier** — revert the fix and prove the test fails without it (the test catches *this* regression, not any regression) | factory | New | QA/verifier stage, on top of the frozen Validation Contract |
| C2 | **Test freeze during fix loops** — the harness session repairing code may not edit or weaken the contract's tests; protected paths per task | both | ✅ **Fixed** | `harness/containment.py` gains a `phase: repair` field; the fence is an ordinary `deny` rule in `policy/containment.yaml` and the overlay is a `repair: bool` parameter on `HarnessRequest` (the `write_root` pattern) — nothing is synthesized, so the enforced policy is the file in git. Paired with a deterministic backstop (`vcs/git.py:check_test_drift`) that measures content drift under the same globs against an anchor commit, closing the Bash channel (`PATH_MATCHES` can never fire on Bash — `target_of` returns the command string) and the `git update-index --skip-worktree` evasion. A human at the fix-loop gate can thaw for exactly one attempt, which also re-anchors. **Rides `containment_enabled`, which is off by default.** Residual, named not fixed: the QA venv (`.sdlc-venv`, inside the worktree — manifest-declared installs are caught via the drift set, undeclared `pip install` and site-packages patching are not), and gitignored paths, which `git diff` cannot see. A task whose attempt 1 never checkpoints has no backstop for its whole life — every later gate carries "TEST-FREEZE BACKSTOP UNAVAILABLE" (skip-and-record by design, never a `branch_point` fallback). Slack has no thaw affordance; operators use the dashboard or CLI for that one reply. |
| C3 | **Fail-closed on a missing gate** — an absent/unconfigured required check yields `MISCONFIGURED` and a failing verdict, never a quiet green run | factory | ✅ Gap verified | `gate.py`: `evaluate_quality_gate` judges only the checks it is handed. Generalize `ABSOLUTE_FLOOR` (`:57`) + `build_check` (`:66`) with a required-checks manifest — no new verdict enum needed |
| C4 | **Advisory + deterministic pairing rule** — every LLM check ships with a deterministic enforcement path behind it (the playbook's "skill makes violations rare, hook makes them near-impossible") | playbook | ⚠️ Needs an owner | a principle with no completion criterion. Make it an audit — adversary / deep_review / MergeVerdict → what deterministic check stands behind each — or drop it |
| C5 | **Reviewer tuning from feedback** — rate findings, cap nit volume, periodically recalibrate thresholds | playbook | Extends | reviewer + retro (confidence calibration is already retained and fed back — extend the same loop to findings) |
| C6 | **Kill the whole process tree on timeout** — a timed-out or cancelled harness must terminate every process it started, not just the one it spawned | *found in review* | ✅ **Fixed** | `harness/adapters.py:265,271` plus `activities.py:706,816,1015` all call `proc.kill()`, and no `start_new_session` / `killpg` / `CREATE_NEW_PROCESS_GROUP` / `taskkill /T` exists anywhere in the tree. Already worked around rather than fixed: `activities.py:202` names "an orphan coding-agent subprocess whose CWD is the worktree" and falls back to `path.1`, `path.2`. Independent of E-88 — fixed via `src/sdlc/process.py`: `kill_process_tree`, wired into all 5 spawn sites (the 4 named here plus `deploy/activities.py:65`, found during implementation) |

> **C6 is not from a source.** It is a defect in this repo that assessing the
> sources exposed. Orphans keep burning tokens against an activity that already
> failed, hold the worktree open, and can write into a tree whose diff was
> already measured against the running integration head (ADR-14). POSIX:
> `start_new_session=True` + `os.killpg`. Windows: `taskkill /F /T` from the root
> pid. Fixed 2026-09-02: see `src/sdlc/process.py`.

## D. Learning and the quality cycle

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| D1 | **Eval per incident** — every DAPER incident becomes a permanent benchmark/eval regression case | playbook | ⛔ **Blocked · FR-501** | `MaintenanceWorkflow` → `benchmarks/cases/` — there is no source of incidents yet |
| D2 | **CI gate on the whole steering config** — evals run on changes to any agent-steering input (constitution, risk classes, containment), not only `agents/<role>/instructions.md` (E-82); plus scheduled runs | playbook | Extends | widen E-82's scope beyond role instructions |
| D3 | **Committed baseline + CI check** — golden artifacts per stage; drift is a reviewed event, not a silent change | both | New | already designed and explicitly unbuilt — BENCHMARK.md calls the "committed-baseline-plus-CI-check half" the missing half |

## E. Deploy and the post-PR cycle

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| E1 | **Rollback rehearsal** — auto-rollback exists (stage 13); add regularly exercised rollback drills in staging so the path is proven before it is needed | playbook | Extends | deploy stage + `schedules/`. Drills can run without DAPER; *band-triggered* rollback cannot |
| E2 | **Deploy as allowlisted tools** — deploy/status/rollback exposed as scoped per-environment tools (MCP), not a shell with credentials | playbook | New | deploy adapter seam (`compose` / `script`) |
| E3 | **PR babysitting** — after the merge gate, an agent sweeps unresolved review comments and failing checks and pushes fixes until green; a human only approves | playbook | New | a new bounded stage between merge gate and deploy |
| E4 | **Plan drift requires plan amendment** — drift without a committed plan amendment is a review flag; plan↔diff sync enforced | playbook | ✅ Gap verified | `compute_plan_drift` (`models.py:401`) is wired at `feature.py:1722` — the number is computed every run and **nothing reads it**. The cheapest item in the register: turn an existing signal into a review condition |

## F. Operator UX and the meta-loop

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| F1 | **"What needs you now"** — a single prioritized entry point: review queue first, ordered by urgency | factory | Extends | decision inbox (E-10 dashboard). Needs a definition of urgency before it can be built |
| F2 | **Doctor** — setup diagnosis: placeholders, missing labels/remotes/keys/config gaps | factory | ✅ Gap verified | `python -m sdlc.cli doctor` — no such subcommand today |
| F3 | **Monthly constraint-tune** — a meta-loop that *proposes only* changes to the factory's own constraints from run statistics | factory | New | analyst over board statistics (ADR-21). The board data exists; the maintenance host does not |
| F4 | **Human-readable artifact export** — generated `.md` renders of typed artifacts so non-engineers can read intent/spec without the dashboard | playbook | New | board API / dashboard. Render *from* the typed artifact — typed and readable are not in tension |

## G. Distribution

| # | Candidate | Source | Status | Where it lands |
|---|---|---|---|---|
| G1 | **Factory-lite mode** — install a policy pack (charter + gates + skills) into an existing repo *without* the Temporal stack; full orchestrator when needed | factory | ⚠️ Product decision | not a backlog row. It is a fork in the product that every other candidate raises the cost of, so it wants a yes/no before the list is executed |

---

## Already covered — do not take

These source ideas are implemented here at equal or greater strength; listed so
nobody re-adopts them as regressions:

- **`.md` artifacts as stage handoff** → typed, schema-validated, hashed artifacts with lineage and claim-check.
- **Manual prompt chaining → loop** → deterministic state machine (Temporal) from the start.
- **Verifier subagent with fresh context** → clean-context Reviewer/QA judging against a Validation Contract frozen before code exists.
- **Branch-claim concurrency (`claude/fq-<n>` first-push-wins)** → per-task worktrees + run integration branch (ADR-14).
- **"Merge is never automated"** → hard merge gate + branch protection as enforcement boundary.

## Priority shortlist (effect / effort)

**Corrected 2026-09-01**, after checking each landing site. Three items from the
first shortlist moved: two were blocked on a component that does not exist, and
one was priced as a bigger job than it is.

1. **C6** — kill the whole process tree on timeout. The only item with evidence
   of harm *already happening*, and the smallest diff. The repo has diagnosed
   the symptom and shipped a workaround instead of a fix.
2. **C2** — test freeze in fix loops (*was #1*): cheap, closes an integrity
   hole; the containment vocabulary is already there.
3. **C3** — fail closed on a missing gate (*new to list*): the pattern to copy
   sits one file over, in `ABSOLUTE_FLOOR`.
4. **E4** — plan drift demands an amendment (*new to list*): the signal is
   computed every run and read by nothing.
5. **B4** — fleet back-pressure (*was #2*): both sources named it
   independently; human attention is the resource that does not scale.
6. **F4** — human-readable artifact export (*new to list*): the adoption
   blocker — a human standing at a gate currently reads SQLite through an
   unauthenticated localhost API.

**Dropped from the shortlist, and why.** **B2** (σ-bands) sat at #5 as if it
swapped a binary confidence gate for tiered response classes; it in fact
requires building the DAPER loop first, so it is an order of magnitude larger
than it was priced. **D1** (incident → eval) has no source of incidents until
the same loop exists. Both, with **A4**, are blocked on FR-501 —
`grep -rniE "MaintenanceWorkflow|DetectionReport|RepairPlan|DAPER" src/ --include=*.py`
returns **0 hits**, and ARCHITECTURE §7 is a design, not a description. **F2**
(doctor) stays a verified gap and a good afternoon's work, but it is
convenience rather than integrity, so it drops below the six above.
