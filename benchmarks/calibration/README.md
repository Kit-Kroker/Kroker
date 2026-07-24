# Rubric calibration fixtures (E-36 / FR-110)

Each `<rubric>/` directory holds hand-scored fixtures for one rubric
(= a proposer role: clarifier, architect, planner, qa, research, reviewer,
analyst). A fixture pins the produced artifact + the rubric text it was
scored against:

    { "artifact_json": "...", "rubric_ref": "cat-cafe-monitoring/architect",
      "rubric_text": "...", "rubric_sha": "...", "author_model": "...",
      "human_score": 0.8, "human_components": {...},
      "scored_by": "you", "notes": "..." }

Workflow:
1. Seed fixtures (operator-runtime live capture, or hand-author them here).
2. Fill each `human_score` (0.0-1.0) by editing the file. Leave `null` to skip.
3. Run `python -m sdlc.cli calibrate <rubric> [--judge-model M]
   [--epsilon 0.15] [--threshold 0.75]`.
4. Read `<rubric>/calibration.json` and the "Rubric calibration" section of
   the benchmark report / heatmap.

The judge model MUST be a different model family than any fixture's
`author_model` (ADR-6); same-family fixtures are skipped with a warning.
Aim for 20-30 scored fixtures before trusting the agreement number.
