# Service platform (`E-57`…`E-63`) → FR-1000, NFR-8, NFR-9

**E-57 and E-58 are preconditions for admitting an external tenant, not
hardening.** Everything in §§10–11 can be delivered by an operator on
repositories they are authorised to run; none of it can be offered self-serve
until these land.

- [ ] **E-57 — untrusted-input threat model + adversarial tests** → FR-1002,
  NFR-9; extends **E-21**. E-21 covers the container / restricted-OS-user tier;
  E-57 is the threat model and the tests that prove it — a repository whose test
  suite exfiltrates the environment, whose build script writes outside the
  worktree, whose `postinstall` opens a socket. FR-703's own note concedes the
  gap: egress enforcement is tool-level, so *"a socket opened from inside an
  allowed `Bash` call is not visible to it"*. Running a stranger's
  `npm install` today is arbitrary code execution as the worker user with the
  worker's toolchain and unrestricted network.
- [ ] **E-58 — tenancy by construction** → FR-1001, NFR-8; **resolves OQ-4**.
  Temporal namespace + artifact-store prefix + memory-bank namespace per tenant,
  with an adversarial test that attempts a cross-tenant artifact read and a
  cross-tenant recall. Memory is the sharpest edge: cross-run learning is the
  factory's differentiator and, without a tenant boundary, its first
  data-breach path — client A's gotchas recalled into client B's run.
- [ ] **E-59 — repository connection** → FR-1003, FR-703. VCS app install per
  tenant; short-TTL, repo-scoped tokens minted per run and never persisted
  (FR-703 specifies these and nothing implements them); PR-only delivery;
  webhooks for commit and PR events.
- [ ] **E-60 — identity & authorization** → FR-1004; closes FR-304's gap.
  Authenticated principals on every surface and a real principal recorded in
  every `GateDecision`. FR-304 already records *who approved what* — there is
  simply no principal to record, which is fine for one operator at a CLI and
  void as an audit trail you hand to a client.
- [ ] **E-61 — metered per-tenant cost** → FR-1005, FR-701. The FR-701 counters
  already aggregate harness JSON cost and model usage per run; this attributes
  and exports them per tenant with enforceable ceilings.
- [ ] **E-62 — on-prem packaging + configurable model provider** → FR-1006,
  NFR-7. One artifact, single-tenant on-prem or multi-tenant hosted; the
  customer may supply their own model credentials or gateway.
- [ ] **E-63 — retention & audited purge** → FR-1007. Per-tenant retention for
  evidence, transcripts and memory; a deletion request purges artifacts, banks
  and transcripts, and the purge itself is audited.
