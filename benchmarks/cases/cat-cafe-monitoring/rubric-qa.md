# QA rubric — cat-cafe-monitoring

Score the QAReport artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

Score only what the QAReport actually carries: `tests_passed` (bool),
`coverage_pct` (float or null), `failing_tests` (list of names), `issues`
(list of strings), `stack_mismatch` (bool). `report_ref` is a pointer, not
content — do not score the report body you cannot see. Do not infer test
strategy, seeding, or boundary coverage: none of that is in the artifact, and
guessing at it is a scoring error.

- **internal_consistency (0.35):** the fields do not contradict each other.
  `tests_passed: true` alongside a non-empty `failing_tests` or a non-empty
  `issues` list is a contradiction and scores 0 on this component.
  `tests_passed: false` with an empty `failing_tests` and empty `issues` is
  also inconsistent — a failure with nothing naming it
- **issue_specificity (0.3):** each entry in `issues` is specific and
  actionable — names a file, symbol, or concrete behavior — rather than vague
  ("some tests are flaky", "needs work"). An empty `issues` list on a passing
  report scores full marks here; a populated list of vague strings scores low
- **failing_tests_named (0.2):** entries in `failing_tests` are precise test
  identifiers (a test path or node id), not prose. Empty on a passing report
  is full marks
- **coverage_reported (0.15):** `coverage_pct` is populated with a plausible
  0..100 value when `tests_passed` is true. Null coverage on a green run is a
  reporting gap and scores low
