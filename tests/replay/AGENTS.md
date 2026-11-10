# `tests/replay/` — capture and golden rules

The replay corpus: scenario histories (`histories/`), their golden
projections (`golden/`), and the tests that capture and replay them.

## Rules

1. **Goldens and histories are written only by the capture tests.**
   `tests/replay/test_capture_graph.py` (behind `SDLC_CAPTURE_HISTORIES=1`)
   and `tests/replay/test_capture_assessment.py` (behind its own switch)
   are the only writers, each under the capture-twice rule: a scenario
   runs twice and the fixtures are written only when both projections
   agree (SG-1). No hand-edited fixture, ever.
2. **Intentional golden changes re-baseline from GraphWorkflow** with the
   projection diff attached to the review. Since 020 T018 every fixture
   carries GraphWorkflow provenance; a re-capture that changes anything
   beyond `workflow`/`source_commit` is a STOP until the diff is
   explained (`scripts/check_golden_rebaseline.py` gates exactly this).
   The FeatureWorkflow-era capture test and replay leg are deleted
   (020 T021); their successor is `tests/replay/test_graph_replay.py`.
3. **SG-2 and SG-3 still apply.** A replay failure means the command
   sequence changed — fix the change or re-baseline deliberately with
   its diff, never re-record a history to turn a red replay green; a
   difference against a golden trace is a STOP (SG-3). The frozen
   durability anchors (`tests/durability/fixtures/`) are never re-recorded
   to silence a live-vs-frozen red — the drift is escalated and ruled on
   (see round 020's §Baseline addendum and the 2026-11-10 ruling).
