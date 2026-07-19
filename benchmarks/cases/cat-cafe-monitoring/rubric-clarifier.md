# Clarifier rubric — cat-cafe-monitoring

Score the ClarifiedRequirements artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **questions_material (0.3):** every open question materially changes the
  design — activity thresholds, what counts as a health risk numerically,
  zone geometry and proximity radius, history retention. No filler; each has
  a "why_it_matters"
- **scope_preserved (0.3):** all six activities (sleeping, eating, drinking,
  litter box, playing, fighting) and both tasks survive. Silently dropping an
  activity, the risk analysis, the red marking, or the 24h history scores 0
  on this component regardless of how good the rest is
- **suggested_answers (0.2):** each open question has a concrete suggested
  answer the human could accept in one click
- **scope_discipline (0.2):** out_of_scope is explicit and reasonable (e.g.
  no real collar hardware, no auth, no multi-café) and adds no requirement
  the kata did not ask for
