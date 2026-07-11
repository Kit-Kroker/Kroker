# Architect rubric — todo-api-greenfield

Score the architecture artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **stack_choice (0.3):** named a boring, mainstream stack (no exotic
  choices for a CRUD API)
- **data_model (0.3):** defined a clear todo item schema (id, title, done
  status, timestamps) and a persistence approach
- **api_surface (0.2):** produced a coherent set of REST endpoints covering
  create/list/update/delete
- **decisions_documented (0.2):** each non-trivial choice has rationale +
  alternatives considered
