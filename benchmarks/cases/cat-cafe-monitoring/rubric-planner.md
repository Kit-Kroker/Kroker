# Planner rubric — cat-cafe-monitoring

Score the plan artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

This case exists to measure decomposition. Score the shape of the plan, not
the prose quality.

- **task_independence (0.3):** each task is implementable on its own against
  a frozen contract. A task that cannot start until another is half-finished
  scores badly
- **seam_quality (0.25):** the detection engine is separable from the UI, and
  the contract between them (the shape passed from classification to view) is
  named explicitly
- **task_sizing (0.25):** no task swallows the app ("implement the backend"),
  and none is trivial busywork. Each is sized for one harness attempt
- **ordering (0.2):** dependency-respecting order; nothing depends on a task
  scheduled after it
