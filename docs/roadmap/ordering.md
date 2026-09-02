# Suggested ordering across §§10–14

Not a commitment. Ranked by what each item unblocks and by which invariants get
harder to install later:

1. **E-40 + E-43** — the two invariants. **Designed and planned 2026-08-06; next
   to implement.** Both are small, both land in *existing* code paths, and both
   improve the current pipeline on their own (`Measurement` closes the
   malformed-SARIF-reads-as-clean hole on the absolute floor; the verifier is
   shared with FR-107's research stage and with two live consumers — handoff
   claims and deep-review integrity flags — that carry unverified quotes today).
   Installing "no unverified claim may be labelled grounded" before any
   finding-producing stage exists is far cheaper than retrofitting it across
   four of them.
2. ~~**E-41 → E-42 → E-44**~~ — triage and tidy-up. **Landed.** The chain is
   closed: E-44's `TidyUpWorkflow` is the first item that proves the whole
   assess → fix → prove claim end to end, almost entirely deterministic, needing
   neither tenancy nor containment because it is operator-run. (Verification
   debt: the `TidyUpWorkflow` temporal e2e is deferred — see P5's note.)
3. **E-47a → E-47b/E-47c** — `CapabilityMap`. Unblocks P2 brownfield
   whether or not the audit ships, which makes it the highest-leverage item in
   §11. **OQ-6 settled 2026-08-08** — the blocker is cleared and the item is
   ready to plan. **E-46 landed 2026-08-13**, so the pairing is now just
   E-47b/E-47c. Take **E-47a first**: it resolves identity, the other two
   attach findings to it, and it is the only one of the three that needs no
   proposer (pure matcher, synthetic-fingerprint tests). FR-102 still needs all
   three.
4. **E-67** — `DeployPlan`/`DeployReport`. Closes stage 13 for ordinary feature
   runs; the outcome loop needs it, but so does P1's own deploy stage.
5. **E-57 + E-58** — the moment an external, self-serve tenant is on the table
   these stop being optional. Not required for operator-run delivery, so their
   position depends entirely on whether P7 is the near-term goal.
6. Then audit depth (**E-48 → E-49 → E-50 → E-51 → E-52 → E-53 → E-54 → E-55 →
   E-56**), service (**E-59…E-63**), and the outcome loop (**E-64 → E-65 →
   E-66 → E-68/E-69 → E-70 → E-71**).
7. **§14 (E-72…E-77) is deliberately unsequenced.** It is the only tier that
   rewrites a core code path rather than extending one, and it competes with
   nothing above it for invariants — the factory ships fine without it. Two
   things argue for pulling it earlier anyway: **E-75 closes P2's outstanding
   dashboard-backend half** regardless of whether the interpreter lands, and the
   longer `_pipeline` accretes stages (§1 has 8 unbuilt ones), the more imperative
   wiring the big-bang rewrite has to absorb. If §14 is wanted at all, **E-72 →
   E-73 before §1 grows** is the cheap moment; E-75 can be lifted out and shipped
   on its own.

**Deliberate:** §10 ships before §11 even though §11 is the more impressive
product. Triage is what tells you whether the audit is worth running (FR-903),
its findings are the ones that are mechanically fixable, and it is the only tier
that works on the repositories most likely to arrive first.

---
