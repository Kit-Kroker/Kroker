# Tasks: FR-041 opencode stream fixture

Single M-sized crew run. Spec: `spec.md` beside this file. Branch
`fr041-waste-fixture` off main; commit per task; reviewer gate per task is
BLOCKING.

- [X] T1 Pin the captured fixture
      Extend `tests/test_opencode_normalise.py` (or add
      `tests/test_opencode_captured_stream.py`) with tests over
      `tests/fixtures/opencode/bench-todo-api-greenfield-1792335476-T-001-a1.jsonl`:
      digest counters, WasteBag.from_digest + waste_measured projection,
      token/cost summation (0.0 measured-zero, not None), scrubbed-field
      robustness (session id `"<session-id>"`, `part.time` values replaced —
      assert the session parses and events survive, do not pin the redacted
      literal unless it is load-bearing). Verify every expected number from
      the fixture itself before pinning.

- [X] T2 `type: error` ruling + pin
      Unit test on the real error shape (top-level `error` object — name,
      data.message, data.ref — no `part` key, no other events in the
      stream): parser returns an empty-event session, no crash, no text.
      Record the ruling in `normalise_session`'s docstring
      (`src/sdlc/harness/opencode.py`).

- [X] T3 Docs + close-out
      BENCHMARK.md §4.3: two-to-four sentence note (counters populate
      end-to-end since 013/014; the pinned fixture is the round-016 R0
      capture of todo-api T-001 attempt 1). File any findings as one `.md`
      per task in `.workspace/tasks/`.

## Phase 2: Convergence

- [X] T004 Pin waste_measured over the fixture-derived bag: a BenchmarkRecord with harness=opencode and waste=WasteBag.from_digest(digest_of(normalise_session(BENCH_CAPTURED))) reads as measured per FR-1 (partial)
- [X] T005 Add the BENCHMARK.md section 4.3 note: waste counters populate end-to-end since 013/014 and the pinned fixture is the round-016 R0 capture of todo-api T-001 attempt 1 per FR-4 (missing; scribe drafts, executor commits)
