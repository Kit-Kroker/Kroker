# Research: Research Retain Path (009)

Baseline main `d51eef5`. `R/` = `src/sdlc/stages/research/`.

Evidence tiers: **measured** (probe run in `kroker-dev`), **read** (seen in code, not run), **inferred**.

Probe: E5 `.workspace/tmp/research-retain-path-e5.md`; its script sits beside it and is not committed.

## R1 — The contract mechanism (FR-001, FR-004, FR-005; Q1 = A)

- **Decision**: `verified_findings_to_retain(brief, violations, bank=...)`. `violations` is required and replaces `run_id`. The function filters by the `(source, quote)` pairs the result names and reads nothing.
- **Rationale**:
  - The contract stays where its docstring and its tests are, and the name stays true: the function still drops unverified findings, given the verifier's answer.
  - A required argument cannot be forgotten. `run_id` disappears, so no parameter is left that means nothing.
  - At the stage's call site the result is empty by construction (the retain step is guarded by a digest that is set only after a clean verification, `R/step.py:297,342,345`). The filter matters for any other caller and is what the unit tests exercise (read).
- **Call shape**: the step passes the result as the second positional argument and `bank` by keyword. `tests/research/test_research_slice_contract.py:139-150` replaces the function with `lambda brief, run_id, bank`; a positional second argument keeps that test untouched (read; advisor false-claim 1).
- **Alternatives considered**: filtering in the step (the contract leaves `retain.py`; ruled out at GATE 1); a new activity (changes every research history; ruled out); a "verified brief" type returned by the activity (changes the wire; out of scope).

## R2 — Binding the result to its brief (FR-003, EC2; A1)

- **Decision**: a small coroutine `_verify(brief, run_id)` in `R/step.py` returns `(brief, violations)`. Both verification sites assign `verified_brief, violations` from it, and the retain call uses that pair.
- **Rationale**:
  - Passing the live `violations` beside the live `brief` rests on statement order: in a refine round `brief` is rebound at `:321` and verified at `:334`, with `_fold_research_usage` between. If that call raised, `except Exception: break` would leave a new unverified brief beside the previous brief's empty result. Today the workflow-side re-read would drop such a brief's unfetched findings; a bare pass-through would retain them (read; both seats).
  - `_fold_research_usage` swallows pricing errors and otherwise adds integers (`:138-163`), so the path is not known to be reachable. The helper closes it without relying on that.
  - The helper issues the identical `execute_activity` call, awaited in place, so the command sequence is unchanged (read).
- **Alternatives considered**:
  - Holding a `(brief, violations)` tuple updated by hand: every rebind site must remember both halves.
  - The skeptic's proposal: assign the refine synthesis to a candidate and rebind `brief`, `violations` and the digest together only after a clean verification. It fixes the same hole and also changes which brief the stage returns and judges on that path. Not adopted: that is a behaviour change outside this feature's scope. Named as a residual.

## R3 — Old histories (FR-008; Q2 = A; A3)

- **Finding**: with memory on, a research stage schedules one `gate_feedback` retain per research gate round (`src/sdlc/workflows/run_host.py:74-84`; a gate with policy off still decides and calls it, `src/sdlc/workflows/gates.py:204-208,247`), then one `research_finding` retain per retained finding. With memory off it schedules none (`src/sdlc/workflows/memory_host.py:62`). Read.
- **Decision**: no patch marker. After the change the stage schedules one `research_finding` retain per grounded finding of the verified brief. A history recorded where the workflow saw the same page bytes as the verifier has exactly that, so it replays unchanged.
- **What stops replaying** (accepted at GATE 1): N2 (a refine round rewrote a page and then failed, so the old run retained fewer findings) and EC7 (the workflow saw a different page directory from the activities). Both replay today only on a host with the same files. No committed history has either shape: `research_greenfield` has no grounded finding and memory off; `architect_research_tool` does not run the stage (read).
- **Alternative considered**: a patch marker keeping the old path for old histories. It leaves the page read reachable from the step, which is the defect.

## R4 — Where the scenario lives (FR-010; A6)

- **Decision**: a standalone module `tests/replay/research_retain.py` with its own test module and its own history file. Not a member of `SCENARIOS`. No golden file.
- **Rationale** (each read in code):
  - `tests/replay/scenarios.py` is 906 lines; the scenario and three fakes would take it to about 970.
  - `test_fixtures_present.py:35-45` requires a golden file and an `EXPECTED_CLOSES` entry for every member.
  - `test_notify_registration_chaos.py:67-71` loads a golden for every member at import time, whatever its `golden` flag, and `:206-213` pins the set of golden files.
  - `test_graph_golden.py` would require GraphWorkflow to reproduce the scenario sandboxed and unsandboxed. Nothing has shown that for a memory-on research run.
  - `test_capture_feature.py` re-records every member when `SDLC_CAPTURE_HISTORIES=1`.
  - A standalone test uses the same replayer and the same harness `capture`, which is all FR-007 needs.
- **Consequence**: the capture test has its own switch (`SDLC_CAPTURE_RESEARCH_RETAIN=1`) and writes the history only. `write_fixtures` is not used because it also writes a golden.

## R5 — Recording before the change without a red commit (FR-007; Q2 = A)

- **Decision**: on the branch, with `src/` still equal to `d51eef5`, write the scenario and tests uncommitted, capture the history once, run the three replay rows and keep the output as the RED evidence in `.workspace/tmp/009-red.txt` (`present` passes, `absent` and `overwritten` fail). Then apply the source change. The fixture, the new tests, the test edits and the source change land in one commit.
- **Rationale**: repo practice pairs a RED test with its fix in one commit, so no commit is red. The fixture's `source_commit` is the branch tip at capture: not `d51eef5` itself, but a commit whose `src/` is identical to it, checkable with `git diff d51eef5 <source_commit> -- src`. The commit message states this.
- **Alternative considered**: capturing in a detached worktree at `d51eef5`. Same guarantee, more ceremony.

## R6 — Proving no read is reachable (FR-002; A4)

- **Decision**: two pins. A runtime one: the retain function, and the step with the real retain function, run with the verifier's file helpers and the `Path` read methods patched to raise. A static one: `R/step.py` and `R/retain.py` do not name the verifier's file helpers, `Path`, `open` or `os`.
- **Rationale**: the runtime pin catches a read reached through the function body; the static pin catches an import creeping back. Neither claims anything about other functions the step calls. Patching `os.environ` itself is avoided: pytest writes to it during the test.
- **Alternative considered**: adding `R/step.py` to the graph determinism lint. It would flag the step's `asyncio.gather` and change that lint's pinned counts (advisor; not re-checked by running).

## Consult disposition

Advisor `.workspace/tmp/advisor-009-1.md`, skeptic `.workspace/tmp/skeptic-009-1.md`. Each adopted point was re-checked in code.

| Point | Disposition |
|---|---|
| Advisor D1: `_verify` helper returning the pair; result passed positionally | Adopted (R2, plan D2). |
| Advisor D2: standalone scenario, own history, no golden | Adopted (R4). Consumers re-read: `test_fixtures_present.py`, `test_notify_registration_chaos.py:67-71,206-213`, `test_capture_feature.py`. |
| Advisor D3: record uncommitted on unmodified source, one commit | Adopted (R5). |
| Advisor D4: one history, three rows, pages staged with `write_page` under the history's workflow id | Adopted (plan D3). |
| Advisor D5: runtime pin plus a narrow static pin | Adopted, without patching `os.environ` (R6). |
| Advisor D6: the third retain is the research gate's feedback | Adopted (spec A3); pinned by decoding the fixture's retain inputs. |
| Advisor: V9 is false (slice-contract lambda pins the arity) | Upheld (spec A2). |
| Advisor: FR-002 is broader than can be proved | Upheld (spec A4). |
| Advisor: anti-vacuity guard on the fixture | Adopted (plan D3 test 2). |
| Advisor: stage-level pin for the pairing | Adopted (pairing tests 3, 4). |
| Skeptic 1.1: an unverified brief can meet a stale empty result | Upheld as a hole in a bare pass-through; the trigger (`_fold_research_usage` raising) is not known to be reachable. Closed for retention by R2. |
| Skeptic 1.1 mitigation: never rebind `brief` before verification | Not adopted (R2): changes the returned brief on that path. Residual 4. |
| Skeptic 1.2: an empty list proves nothing | Upheld; it is the residual Q1 = A accepted. Stated in the docstring. Residual 3. |
| Skeptic 2.1: retain count is gate rounds plus findings | Upheld as a wording error (spec A3). No ruling changes: the gate retains are untouched. |
| Skeptic 2.2: N2 is real | Upheld (spec A7). Read by two seats, not run. |
| Skeptic 3: E5 is valid; divergence is at the second retain | Upheld (spec A3; the E5 record is corrected). |
| Skeptic 4, 5: Q3 and Q4 hold | Upheld; no change. |
| Skeptic 6: five ways the replay test could pass for the wrong reason | Adopted (spec A5; plan D3 rules and stop-guards 3, 4). |

## Residuals (reported at GATE 2)

1. An old history of the N2 or EC7 shape no longer replays. Accepted at GATE 1 (Q2 = A).
2. For new runs, N2 changes from "retain what still matches the disk" to "retain what was verified".
3. A caller can pass an empty result for a brief nobody verified. The signature makes it a visible claim; nothing proves it. Accepted at GATE 1 (Q1 = A).
4. If an error were raised between a refine round's synthesis and its verification, the stage would still return and judge the new, unverified brief with the previous digest, as today. Retention no longer follows it. Not known to be reachable.
5. No GraphWorkflow parity is claimed or tested for the new scenario.
6. The new history ends at `awaiting:clarify` (`partial` mode). It covers the research stage and nothing after it.
7. Why the sandbox does not block the page read is not established; only that it does not (E5).
8. N2 and EC7 are read, not run.
