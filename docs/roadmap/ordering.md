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
7. **§14 (E-72…E-77) is deliberately unsequenced; ruled *record only* at the
   2026-09-11 user gate.** It is the only tier that rewrites a core code path
   rather than extending one, and it competes with nothing above it for
   invariants: the factory ships fine without it. A 2026-09-11 external analysis
   ranked it first (register §H1/H2); the gate recorded that as priority
   pressure, not a sequencing change. Sequencing waits on three prerequisites:
   **(a)** ~~a PRD line for FR-1200~~ **cleared 2026-09-12** (PRD v1.2 admits
   FR-1200…FR-1206); **(b)** ~~OQ-10 settled~~ **cleared 2026-09-12**
   (resolved: grace-retention — new starts move to `GraphWorkflow`
   immediately, the old type is retained registered to drain in-flight
   executions, removed when none remain Running); **(c)** P2's exit
   demonstrated — **cleared 2026-09-12**
   (brownfield run `merged-not-deployed:PR #16`, operator-merged `45aa2b8`;
   the diff-scoped gates it needed landed the same day). The
   big-bang rewrite of
   `_pipeline` no longer sits on an undemonstrated claim. The
   old arguments for pulling it earlier have weakened. "E-72 → E-73 before §1
   grows is the cheap moment" matters less now that the B0 migration has made the
   stage bodies modular `step()` functions (`src/sdlc/stages/<stage>/step.py`),
   and §1 has four unbuilt stages, not eight. "E-75 closes P2's dashboard-backend
   half" was superseded 2026-08-18 by E-10. **All three prerequisites are now
   cleared (2026-09-12)**; the considered entry point stands: E-72 + E-73
   first, E-74's cutover under grace-retention (spec
   `docs/superpowers/specs/2026-09-11-roadmap-platform-analysis-design.md` §6).

**Deliberate:** §10 ships before §11 even though §11 is the more impressive
product. Triage is what tells you whether the audit is worth running (FR-903),
its findings are the ones that are mechanically fixable, and it is the only tier
that works on the repositories most likely to arrive first.

---
