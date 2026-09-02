# Product outcome (`E-64`…`E-71`) → FR-1100

**The framing.** The factory measures *itself* very well — SC-1..6, the
benchmark matrix, rubric calibration (FR-110), capture-always transcripts
(FR-109). It measures **the product it ships: nothing**. FR-1100 closes that,
and the reason it is tractable rather than a second company is NG7: hosting,
feature flagging and analytics are *adapters over what the customer already
runs*, following FR-108's pattern. What remains is squarely this codebase's
competence — a frozen contract, a traceability check, a durable timer, and a gate.

- [ ] **E-64 — `Hypothesis` contracts + intake gate** → FR-1101. Metric,
  expected direction, minimum effect worth shipping, decision rule, kill
  condition, observation window — gated before any code is written.
- [ ] **E-65 — pre-registration freeze** → FR-1102. The decision rule is frozen
  and hashed at approval, reusing `ValidationContract.frozen` semantics
  (FR-803). A post-hoc change is a new audited gate round with both versions
  retained. **This is the differentiating mechanic**: the owner commits to how
  they will decide before they see the data, and the factory is what makes that
  commitment structural rather than cultural.
- [ ] **E-66 — metric traceability** → FR-1103, FR-106. Every hypothesis metric
  must trace to ≥1 instrumentation task and ≥1 emitted event, enforced by the
  same deterministic mechanism as criterion→test traceability. An
  uninstrumented hypothesis cannot reach deploy — which is the single most
  common way a "measured" feature ships unmeasurable.
- [x] **E-67 — `DeployPlan` / `DeployReport`** → FR-1104. Environment, flag and
  cohort, rollback, smoke-tested deployment vs. PR merge. **Closes DAG stage 13
  for all runs**, not only experiments: previously the stage was a single
  hardcoded `make deploy` shell-out with no plan/report split. Delivered on
  `feat/deploy-contract`; spec `docs/superpowers/specs/2026-08-06-deploy-contract-design.md`.
- [x] **E-68 — deployment target adapters** → FR-1105, NG7. Resolved from
  config, one reference adapter, no hosting substrate of our own. Delivered on `feat/deploy-contract` (`src/sdlc/deploy/adapters.py`, compose + script).
- [ ] **E-69 — analytics source adapters** → FR-1105, NG7. One reference
  adapter. See **OQ-9**: the factory would read a metric from a
  customer-controlled source to decide keep/kill, which is FR-914's grounding
  problem inside a system we do not control and currently has no good answer.
- [ ] **E-70 — durable observation + verdict gate** → FR-1106, FR-1108. A
  Temporal timer spans the observation window — the one thing Temporal is
  uniquely suited to here, since a 14-day wait is exactly what NFR-1 already
  guarantees. On expiry: collect, evaluate the pre-registered rule, open a
  keep / kill / extend gate. Insufficient data yields `inconclusive`, never a
  favourable read (FR-915 applied to product metrics).
- [ ] **E-71 — PoC mode** → FR-1107. Bounded budget, explicitly disposable
  output, preview deployment, recorded decision, and marked so it never silently
  accrues as production debt.
