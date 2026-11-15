# Per-role `agent.yaml` silently ignores unknown keys (FR-202 follow-up)

| | |
|---|---|
| From | FR-202 validation-retries branch (final review follow-up card, 2026-11-14) |
| Size | S |
| Status | done (2026-11-15, round 023a close-out; RED + fix commits on main) |

**The hole.** A typo'd per-role key — e.g. `validation_retry` instead of
`validation_retries` in `agents/<role>/agent.yaml` — is silently ignored:
`RoleConfig` parses with pydantic's default `extra=ignore`, so the misspelled
key vanishes at boot and the role runs with the default value as if the
configuration had never existed. This is the exact silent-dead-config outcome
VR-1's rationale (`docs/superpowers/specs/2026-11-14-validation-retries-knob-design.md`,
VR-1/VR-1b) rejects elsewhere — the `defaults:` block rejects unknown keys and
harness roles reject the key outright — but per-role files get no such check.
Of the sixteen roles carrying the knob, only the four 3-valued ones
(planner, research, constitution, product) are protected by pins that would
notice a silently-dropped 3; the remaining twelve would absorb a typo without
any test failing.

**Proposed fix.** Reject unknown keys in per-role `agent.yaml`: in
`_parse_role` (`src/sdlc/agents/loader.py`), diff each file's key set against
`RoleConfig.model_fields` (plus whatever bookkeeping keys the loader already
admits) and raise `RegistryError` on the surplus — the same fail-closed rule
the `defaults:` block already applies.

**Scope note.** This is main-side, pre-existing semantics, not an FR-202
regression — a typo'd `model:` key behaves the same way today — so it can be
picked up and landed independently of the validation-retries branch.
