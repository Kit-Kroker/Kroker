# Architect rubric — add-login-greenfield

Score the architecture artifact 0.0..1.0 on these components; return
`{"score": <mean>, "components": {...}}`.

- **stack_choice (0.3):** named a boring, mainstream stack (no exotic
  choices for a login page)
- **security (0.3):** explicitly addressed password hashing, session
  management, and at least one auth-specific risk (CSRF / brute-force)
- **file_tree (0.2):** produced a coherent file/module layout matching the
  stack
- **decisions_documented (0.2):** each non-trivial choice has rationale +
  alternatives considered
