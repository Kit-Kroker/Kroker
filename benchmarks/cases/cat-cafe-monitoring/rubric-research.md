# Research rubric — cat-cafe-monitoring

Score the ResearchBrief artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

This kata has one fact genuinely worth grounding: what feline breathing rate
indicates a health risk. The risk analysis and the red marking both depend on
it, and a model that invents the number will invent a plausible wrong one.

- **threshold_grounded (0.4):** a resting respiratory rate range and a
  danger threshold for cats, each supported by a cited source. An
  unsourced number scores 0 on this component
- **citations_support_claims (0.3):** each finding's citation actually
  supports the claim made. A citation that is real but does not support its
  claim is worse than none
- **budget_focus (0.3):** search budget went to decisions that needed
  grounding. Searches spent on things the model already knows (how to
  compute distance, SSE vs WebSocket) score badly — a brief that researched
  only the vital-sign threshold and stopped scores full marks
