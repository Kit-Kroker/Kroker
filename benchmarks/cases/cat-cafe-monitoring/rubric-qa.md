# QA rubric — cat-cafe-monitoring

Score the QAReport artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

The system under test is randomized and real-time, which is what makes its
test strategy worth scoring.

- **determinism (0.35):** telemetry is seeded or injected so tests are
  repeatable. A test that asserts over unseeded random data is a defect, and
  identifying one is worth full marks on this component
- **classification_coverage (0.3):** boundary cases per activity class — a
  cat just inside vs just outside a zone radius, breathing rate either side
  of the risk threshold
- **risk_path (0.2):** the risk flag and its red-marking are asserted, not
  assumed
- **history_window (0.15):** the 24h boundary is tested at its edges
