# Feature Specification: Research Retain Path

**Feature Branch**: `009-research-retain-path` (spec directory only; the branch is cut in the `D:\own\Kroker-007` worktree at exec)

**Created**: 2026-10-04

**Status**: GATE 1 cleared 2026-10-04; all four questions ruled A (see [GATE 1 rulings](#gate-1-rulings)); consult amendments A1-A7 added the same day

**Input**: M-2 of assessment `research-budget-enforcement`: defect H5, register row C10. Source of truth: `.specify/assessments/research-budget-enforcement/decide.md` (M-2 row; "M-2: I move toward the skeptic"). The user scheduled it on 2026-10-04, superseding "queued, not scheduled". Measured evidence: E5 (this spec phase) in `.workspace/tmp/research-retain-path-e5.md`.

**Base**: main `d51eef5`.

## Context and verified findings

When the research stage has an approved, verified brief, it writes the brief's grounded findings to memory. To decide which findings to write, the workflow re-runs the verifier itself: it reads the fetched page files from disk, in workflow code. The number of memory writes it schedules therefore depends on what is on the disk of whichever host runs the workflow. A workflow must make the same decisions when it is replayed; this one does not.

The re-read is also redundant. The workflow reaches the retain step only after an activity has verified that same brief and reported no violations.

Every claim below was checked by reading the code on main `d51eef5`. E5 was run in `kroker-dev`; nothing else was run. `R/` = `src/sdlc/stages/research/`.

| # | Claim (from the brief or decide.md) | Verified state | Consequence for this spec |
|---|---|---|---|
| V1 | Retain re-runs the verifier | **True.** `verified_findings_to_retain` calls `verify_brief(brief, run_id)` (`R/retain.py:19`), which calls `Path.is_file` and `Path.read_text` per grounded finding (`R/verify.py:74,80`). | FR-001. |
| V2 | The call is in workflow code and decides how many activities are scheduled | **True.** `R/step.py:346-347` loops over the returned items and awaits `ctx.retain` for each. `ctx.retain` schedules one `retain` activity per item when memory is enabled, and nothing when it is not (`src/sdlc/workflows/memory_host.py:59-76`). | FR-002. With memory off the read still happens but decides nothing. |
| V3 | The workflow already holds the verification result | **True.** `verify_brief_activity` runs at `R/step.py:273-275` (first brief) and `:333-337` (each refine round). The retain step runs only when `brief_digest_val` is non-empty (`:345`), and that value is set only directly after a verification that returned no violations (`:297`, `:342`). | FR-001, FR-003. |
| V4 | The brief retained is the brief that was verified | **True, by reading, and it depends on statement order.** In a refine round the new brief is assigned at `:321`; the only await between that and its verification is `_fold_research_usage` (`:330`), which swallows pricing errors (`:143-156`). If the synthesis raises, the old brief and its old digest are kept together. So at `:346` the held result for the brief in hand is always "no violations". | FR-003. The pairing is an invariant the change must not loosen: see EC2. |
| V5 | A replay without the page files fails | **Measured (E5).** A run with two grounded findings and memory on replays cleanly with the pages present, and fails with a nondeterminism error (`retain` in history, `recall_snapshot` issued) when the runs root is empty. decide.md held this as a hypothesis. | US1, SC-001. This is the failing test the feature starts from. |
| V6 | The sandbox does not block the read | **Measured (E5).** The capture and the passing replay both ran under the sandboxed runner. decide.md held the reason as a hypothesis; the reason is still not established, only the fact. | None beyond V5: the sandbox is not a safeguard here. |
| V7 | A replay also fails if the files exist but changed | **Measured (E5).** Overwriting the two pages in place before replay gives the same nondeterminism error. | EC1. Not in the brief. |
| V8 | The unit contract pins "only verified findings are retained" | **True.** `tests/research/test_research_grounding.py:24-50`: two tests call `verified_findings_to_retain(brief, "r1")` and expect an unfetched source to be dropped. The invariant itself is stated in the `R/retain.py` docstring. | FR-004, Q1. |
| V9 | The function's name is pinned elsewhere | **True.** `tests/research/test_research_stage_wiring.py:44` asserts the name appears in the step's source; `tests/research/test_research_slice_contract.py:141` lists it. Neither pins the parameters. | FR-005. |
| V10 | `verify_brief` has callers other than the retain path | **True.** `verify_brief_activity` (`R/verify.py:136`) is its only other production caller. Tests call it directly 12 times (`test_research_verify.py` 11, `test_research_grounding.py` 1). No memory-recall re-grounding caller exists anywhere in `src/`. | Q4. |
| V11 | No replay fixture covers research with grounded findings | **True.** `research_greenfield` records the degraded planner path (an empty plan, so no sub-question and no synthesis) with memory off. `architect_research_tool` covers the architect's tool, not the stage. | US2, FR-007. |
| V12 | File sizes at baseline | `R/step.py` 387, `R/retain.py` 32, `R/verify.py` 136, `R/stage.py` 473. `tests/replay/scenarios.py` is **906** against the hard ceiling of 1000. | FR-010. A new scenario with its fakes may not fit in `scenarios.py`. |

**Additional findings (not in the brief).**

- **N1 — the slice's own notes will be wrong after this lands.** `R/AGENTS.md` ends its "Verifier rules" with "Retention re-runs the verifier: `retain.py` calls `verify_brief` — real page I/O, from workflow context". The `R/retain.py` module docstring describes the contract but not who supplies the verification. FR-009. Edits to `AGENTS.md` need the orchestrator's approval.
- **N2 — today's re-read can retain fewer findings than were verified.** If a refine round fetches again (rewriting a page for a URL already used) and then its synthesis fails, the stage keeps the previous verified brief and re-reads the rewritten pages at retain time. Findings whose quote is no longer on the page are then dropped. After this feature they are retained, because they were verified against the bytes fetched at the time. Read, not run. See Q2.
- **N3 — a third `retain` in E5.** E5 recorded three `retain` activities for a brief with two grounded findings. The third was not traced and is assumed to come from outside the research retain loop.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A research run replays on a host that never fetched its pages (Priority: P1)

An operator restarts a worker, or a second worker picks up a research run, while that run is somewhere after its retain step. The workflow is replayed from its history. The replay schedules the same memory writes the original run did, whether or not the page files are on this host.

**Why this priority**: This is the defect. E5 shows a replay without the pages fails today.

**Independent Test**: Replay a recorded history of a research run with grounded findings and memory on, with the runs root pointing at an empty directory; assert the replay completes without a replay failure.

**Acceptance Scenarios**:

1. **Given** a recorded research run with N grounded findings and memory on, **When** it is replayed with no page files present, **Then** the replay succeeds.
2. **Given** the same history, **When** it is replayed with the page files present but overwritten with other content, **Then** the replay succeeds.
3. **Given** the same history, **When** it is replayed with the original page files present, **Then** the replay succeeds (as today).
4. **Given** every replay history already committed, **When** the replay suite runs, **Then** every one replays as before.

---

### User Story 2 - Only verified findings reach memory (Priority: P1)

Someone later recalls research findings from memory and treats them as leads. Nothing that failed verification in the run that produced it is among them. This holds today and must hold after the change, including for a future caller of the retain function who has a brief that was not verified.

**Why this priority**: The naive fix (stop calling the verifier) keeps US1 and silently breaks this. The assessment's skeptic named that failure shape; it has the same priority as the defect.

**Independent Test**: Give the retain function a brief with one verified and one unverified finding, together with the verification result for that brief; assert exactly the verified finding is returned. Do it with file access made to fail, and assert the same result.

**Acceptance Scenarios**:

1. **Given** a brief with one finding whose page was fetched and one whose source was never fetched, and the verification result for that brief, **When** items to retain are computed, **Then** exactly one item is returned, for the fetched source.
2. **Given** a brief whose only grounded finding was never fetched, and its verification result, **When** items to retain are computed, **Then** none are returned.
3. **Given** any brief and its verification result, **When** items to retain are computed with no page files and file reads failing, **Then** the result is the same as with the files present.
4. **Given** a caller that has no verification result for a brief, **When** it tries to compute items to retain, **Then** it cannot do so by leaving the result out: there is no default that means "verified".

---

### User Story 3 - A run that fails verification behaves exactly as today (Priority: P2)

A research brief fails verification, on the first pass or in a refine round. Nothing is written to memory, the stage is recorded as failed with the same error text, and the run continues as it does today.

**Why this priority**: The change is next to the failure path and must not move it.

**Independent Test**: Run the existing research tests for the grounding-violation path unchanged; they pass.

**Acceptance Scenarios**:

1. **Given** a first brief with violations, **When** the stage ends, **Then** no memory write is scheduled, the row is FAIL with `rejected:research.grounding: …`, and the outcome carries an empty digest.
2. **Given** a refine round whose brief has violations, **When** the stage ends, **Then** no memory write is scheduled and the row is FAIL with `rejected:research.grounding (refine)`.
3. **Given** a human rejection at the research gate, **When** the stage ends, **Then** nothing is retained and nothing is recorded (as today).

---

### Edge Cases

- **EC1 — pages changed after verification.** Covered by US1 scenario 2. The retain decision follows the verification the activity made, not the current disk.
- **EC2 — a brief paired with another brief's verification result.** Must not be possible in the stage: the result used at the retain step is the one returned for the brief being retained (FR-003). The plan must keep that pairing visible in the code rather than resting on statement order alone (V4).
- **EC3 — memory off.** No `retain` activity is scheduled, as today, and no file is read.
- **EC4 — a verified brief with no grounded findings** (every degraded brief). Nothing to retain; zero memory writes, as today.
- **EC5 — refine ended by an exception or by the round limit.** The last verified brief is retained in full. Today this is also the usual result; N2 is the exception.
- **EC6 — two findings that share a source and quote but differ in claim.** A violation is identified by source and quote, so both are dropped or both kept, as today.
- **EC7 — an old history from a run where the workflow and the activities saw different page directories** (different hosts or working directories). Such a run recorded fewer retains than it had findings. It replays today only on a host with that same view of the disk. After the change it does not replay. See Q2.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The research stage MUST decide what to retain from the verification result that `verify_brief_activity` returned for that brief. It MUST NOT verify again.
- **FR-002**: No file read, directory lookup or environment lookup may be reachable from the research step's workflow code outside an activity. This covers the retain path and anything the change introduces.
- **FR-003**: The verification result used at the retain step MUST be the one returned for the brief being retained. A brief that has not had a violations-free verification MUST NOT reach the retain step (today's guard, kept).
- **FR-004**: Only verified findings are retained. Given a brief and its verification result, a finding named by a violation MUST NOT produce a retain item. The rule MUST be enforced where retain items are built, not only at the call site (Q1).
- **FR-005**: The function that builds retain items keeps its name, `verified_findings_to_retain`, and its place in `R/retain.py`. It MUST NOT keep a parameter it no longer uses.
- **FR-006**: The text, kind, bank and metadata of each retain item, and their order, MUST be unchanged.
- **FR-007**: A replay test MUST exist for a research run with grounded findings and memory on. It MUST fail on `d51eef5` and pass after the change, with the page files absent on the replaying host. Its history fixture is new content. No existing history or golden file is re-recorded.
- **FR-008**: Every existing replay history MUST replay unchanged. On the failure path (US3) the activities scheduled, the benchmark row and the stage outcome MUST be unchanged.
- **FR-009**: The notes that this change makes false MUST be corrected in the same feature: the last "Verifier rules" bullet in `R/AGENTS.md` and the `R/retain.py` module docstring.
- **FR-010**: No file may exceed 1000 lines. `tests/replay/scenarios.py` is at 906; the plan MUST say where the new scenario and its fakes live.
- **FR-011**: What `verify_brief_activity` verifies, what it returns and how it is called MUST NOT change.

### Key Entities

- **Research brief**: the stage's output; its grounded findings each carry a source URL, a verbatim quote and a claim.
- **Verification result**: the list of violations the verify activity returns for one brief. Empty means every grounded finding was found on a page fetched this run. Each violation names a source and a quote.
- **Retain item**: one memory write: a finding's claim and source, marked as a research finding.
- **Page file**: the text of a fetched page, stored per run. Read by the verify activity only.
- **Replay history**: a recorded run, replayed by the test suite to prove the workflow still makes the same decisions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The new replay test fails on `d51eef5` with a nondeterminism error and passes after the change, with the runs root empty. (E5 already shows the failure.)
- **SC-002**: The same history also replays with the pages present and with the pages overwritten: three of three pass, against one of three today.
- **SC-003**: All existing replay histories still replay: zero new replay failures.
- **SC-004**: With file reads made to fail, building retain items for a verified brief returns the same items as with files present.
- **SC-005**: A brief with one verified and one unverified finding yields exactly one retain item. A brief with only an unverified finding yields none.
- **SC-006**: The research test directory and the replay suite pass in `kroker-dev`, with no test deleted or skipped. Any edit to an existing test is listed in the plan with the assertion it keeps.
- **SC-007**: No file is over 1000 lines.

## Assumptions

- No research run with memory on is in flight across the deployment of this change in a shape covered by EC7 or N2. Research is off by default and memory is off by default; research is on in two benchmark cases.
- The third `retain` in E5 comes from outside the research retain loop (N3).
- The replay test reuses the existing replay harness and replayer, so it runs under the same sandboxed runner as production.
- Tests run in `kroker-dev` only. The register file is updated by the orchestrator, not by this feature.
- Out of scope, binding: the cap handling shipped in 008; the H2 salvage residual; the architect research surface (6.2, N2, N3 of the assessment; D1 in force); what the verifier checks; cap values; the register file. The other fail-and-continue behaviours listed in `R/AGENTS.md` are not touched.

## GATE 1 rulings

User rulings, confirmed by the user on 2026-10-04. No open questions remain.

- **Q1 = A, the verification result is a required argument.** `verified_findings_to_retain` takes it in place of `run_id`. The edits to `tests/research/test_research_grounding.py` are approved as contract-preserving: every assertion stays.
- **Q2 = A, no patch marker.** The N2 and EC7 shapes are accepted as not replayable. The new fixture is recorded from the workflow code **before** the change.
- **Q3 = A, the failure path changes nothing.**
- **Q4 = A, `verify_brief` stays as it is.**
- **FR-009 is pre-approved**, bounded to the one "Verifier rules" bullet in `R/AGENTS.md` that turns false and the `R/retain.py` module docstring. Nothing else in `AGENTS.md` is edited.
- **FR-010 stands as written**: `tests/replay/scenarios.py` is at 906 of 1000 and the plan names where the new scenario lives.

## Post-GATE-1 consult amendments

From the advisor (`.workspace/tmp/advisor-009-1.md`) and skeptic (`.workspace/tmp/skeptic-009-1.md`) consults, each re-checked in code by the spec lead. They correct facts and wording. No GATE 1 ruling changes. A1 narrows a residual the Q1 ruling was described as accepting and is carried to GATE 2.

- **A1 (V4, EC2, FR-003) — the stage retains the brief that was verified, not the brief in hand.** V4's "always" rests on nothing raising between a refine round's synthesis (`R/step.py:321`) and its verification (`:334`). If something did, the stage would leave the loop holding a new, unverified brief beside the previous brief's empty result and digest. Today's re-read would drop that brief's unfetched findings; passing the held result would retain them all. The only statement in that window is `_fold_research_usage`, which swallows pricing errors and otherwise only adds integers, so the path is not known to be reachable. It is closed anyway: the verification call returns the brief it verified together with its result, and the retain step uses that pair. The skeptic asked for more (do not rebind `brief` until it verifies). Not adopted: it changes which brief the stage returns on that path, which is outside this feature. On that path the stage still returns the new brief with the old digest, as today.
- **A2 (V9) — the retain function's call shape is pinned.** V9 was wrong. `tests/research/test_research_slice_contract.py:139-150` replaces the function with a three-parameter lambda (`brief, run_id, bank`). The step therefore passes the verification result as the second positional argument and `bank` by keyword, and that test stays untouched.
- **A3 (N3, Q2) — the third `retain` in E5 is the research gate's feedback.** Each research gate round writes one gate-feedback memory when memory is on (`src/sdlc/workflows/run_host.py:74-84`; a gate with policy off still decides, `src/sdlc/workflows/gates.py:204-208,247`), before the retain loop. So an ordinary old history holds one gate-feedback `retain` per research gate round plus one research-finding `retain` per grounded finding. This feature changes only the second count. Q2's "exactly that many retains" is read per kind. In E5 the gate-feedback `retain` matched on replay and the divergence was at the second `retain`. Read, not run; the new fixture pins it (A5).
- **A4 (FR-002) — what "no read reachable" is proved for.** FR-002 is read as its second sentence: the retain path and anything this change introduces. It is proved by a run with file and environment access made to fail, and by a check that the step and the retain module do not name the verifier's file helpers. It is not a claim about every function the step calls.
- **A5 (FR-007) — the replay test must not pass for the wrong reason.** The scenario sets memory on explicitly (the shared research config leaves it off, and then no retain is scheduled at all). The test points the runs root at its own empty directory. It asserts that the committed history holds exactly one gate-feedback and two research-finding `retain` activities, so a fixture that degraded to an empty brief cannot pass. The history is recorded before the source change (Q2 = A).
- **A6 (FR-010) — the new scenario stays out of the shared scenario list.** Joining it would require a golden file, would edit two existing pin tests (`tests/replay/test_fixtures_present.py`, `tests/replay/test_notify_registration_chaos.py`), and would add an unverified GraphWorkflow parity claim. The scenario lives in its own module with its own history file and no golden.
- **A7 (N2) — confirmed by a second reading.** The skeptic traced the same path independently. Still not run.

## Open Questions — GATE 1 (as asked)

Kept for the record. Each was written at its recommended answer (option A) and each was ruled at that answer on 2026-10-04.

### Q1 — Where is "only verified findings" enforced after the change?

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | `verified_findings_to_retain` takes the verification result as a required argument in place of `run_id`. It drops the findings the result names. | The contract stays in `R/retain.py`, next to its docstring. A caller cannot omit the result. `run_id` goes, so there is no phantom parameter. `test_research_grounding.py` is edited: its two tests obtain the result from `verify_brief` and pass it in; every assertion stays. Residual: a caller can still pass an empty list for a brief nobody verified. The signature makes that a visible claim; it cannot prove it. |
| B | The step filters with the violations it holds; the retain function becomes a plain mapper. | Smallest diff in `retain.py`, but the contract moves to the call site and the function's name stops being true. The two tests would have to change meaning. This is the silent-leak shape the skeptic named. |
| C | Keep the signature byte-for-byte and move the call into an activity. | `test_research_grounding.py` stays untouched. Adds an activity to every research run with a verified brief, so every such old history stops replaying unless a patch marker is added. Verifies twice. |
| D | The verify activity returns a "verified brief" value that the retain function requires. | Strongest guarantee. Changes the activity's return shape and the wire, which the brief puts out of scope (FR-011). |

### Q2 — What do old and unusual histories do?

After A in Q1 the stage retains every grounded finding of the verified brief. An old history recorded on a host where the workflow saw the same pages as the verifier has exactly that many retains, so it replays unchanged. Two shapes differ: N2 (pages rewritten by a failed refine round) and EC7 (workflow and activities saw different page directories).

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | No patch marker. Ordinary old histories replay unchanged. The N2 and EC7 shapes are accepted as not replayable, and said so. The new fixture is recorded from the workflow code **before** the change, so the test proves an old history replays under the new code. | Meets "no page read reachable from the step". The two lost shapes replay today only on a host with the very same files, which is the defect. No committed history has either shape. For new runs, N2 changes from "retain what still matches the disk" to "retain what was verified". |
| B | Add a patch marker: old histories keep the page-reading path, new runs take the new one. | Old histories of both shapes keep replaying on their original host. The page read stays reachable from the step for as long as the marker lives, so the assessment's success metric is not met, and the old path stays host-dependent. |
| C | As A, but record the new fixture from the code after the change. | Simpler ordering of commits. Proves only that the new code replays itself; says nothing about old histories. |

### Q3 — Does anything on the failure path change?

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | Nothing. A brief with violations is not retained today, on either path, and the retain step is not reached. FR-008 and US3 pin it; the existing tests for the violation path run unchanged. | Confirmed by reading `R/step.py:276-295` and `:338-341,368-385`. Nothing was run for this question. |
| B | Also retain the verified part of a brief that has violations. | A behaviour change: today a brief with any violation retains nothing. Out of this feature's scope as briefed. |

### Q4 — What happens to `verify_brief`?

| Option | Answer | Implications |
|---|---|---|
| **A (recommended)** | It stays as it is: the body of `verify_brief_activity` and a function tests call directly. `R/retain.py` stops importing it. | Not orphaned: one production caller and 12 test calls remain. No recall re-grounding caller exists today, so nothing else needs it. |
| B | Fold it into the activity and make it private. | Rewrites 12 test calls for no behavioural gain, and touches the verifier, which is out of scope. |
