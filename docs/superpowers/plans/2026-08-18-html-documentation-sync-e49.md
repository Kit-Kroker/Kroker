# HTML Documentation Synchronization (E-49) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize the HTML docs in `docs/` with the E-49 landing (UnifiedRiskMap + risk proposers, assess phase complete 2026-08-16/17, closing FR-916) and the 17-role agent registry (`agents/risk/`).

**Architecture:** Hand-edit the three affected HTML files (`roadmap.html`, `agents-schema.html`, `architecture-schema.html`) so their embedded status data, role tables, and pipeline cards match `ROADMAP.md` and code exactly. `benchmark-analysis.html` is regenerated mechanically (expected byte-identical — no new runs); `benchmark.html` and `research-stage-schema.html` have no stale E-49 claims and are left untouched.

**Tech Stack:** HTML5, vanilla CSS/JS, Python (`scripts/aggregate_benchmarks.py`).

## Global Constraints

- Preserve vanilla CSS and GitHub-inspired styling; no new external dependencies.
- Keep every interactive widget (filter/search/nav) functional; only add/extend data and sections.
- Terminology, contract names, epic/FR numbers must match `ROADMAP.md` verbatim (source: `git diff f6d4437..HEAD -- ROADMAP.md`, already landed).
- The 15-stage DAG count stays **11 of 15** — `assess` is an AssessmentWorkflow phase, not a DAG stage.
- Benchmark state is unchanged: 21 runs / 556 records / 9 corpus cases; `benchmark.html` snapshot date 2026-08-15 remains truthful.

---

### Task 1: Synchronize `docs/roadmap.html`

**Files:**
- Modify: `docs/roadmap.html`

**Interfaces:**
- Consumes: `ROADMAP.md` (E-49 notes, FR-916/E-49/P6/FR-911/FR-902/NFR-9/NFR-10 current text).
- Produces: roadmap data with `FR-916` done, `E-49` done, P6 at 3/7 bodies, snapshot date 2026-08-17.

- [ ] **Step 1: Update snapshot dates (footer line ~582 and `meta.lastVerified` line ~606)**

In the `<footer>` paragraph, change the leading `Regenerated 2026-08-15` to `Regenerated 2026-08-17` and the `(last verified 2026-08-15;` to `(last verified 2026-08-17;`. Then append the E-49 landing before the paragraph's closing paren by replacing the ASCII-safe anchor:

```
; stages 0 and 2 are live (11 of 15 stages live); OQ-12 (S5 normalization is English-centric) recorded).
```

with:

```
; stages 0 and 2 are live (11 of 15 stages live); on 2026-08-16/17 the assess phase landed (E-49, all three plans — the deterministic UnifiedRiskMap score with criticality, severity from a table, five control families, factors and composites memoized on rules_sha; the judgment layer with the risk role in <code>agents/risk/</code>, <code>render_risk_prompt</code>, <code>apply_judgment</code> with layer-scoped degradation, and <code>verify_risk_refs</code> byte-verification; and the system view with the capability-to-capability projection, shared vulnerabilities, bounded cascades, and trust-boundary + privilege-escalation candidates — closing FR-916; three of seven assessment phase bodies are now live: scan E-46, discover E-48, assess E-49); OQ-12 (S5 normalization is English-centric) recorded).
```

In the `const ROADMAP = {` block, change `lastVerified: "2026-08-15",` to `lastVerified: "2026-08-17",`.

- [ ] **Step 2: Update the P6 phase entry (line ~631)**

Change `pct: 20` to `pct: 45` and replace the note string with:

```
Opened 2026-08-10 with E-45's DAG shell; three of seven phase bodies are now live and measured end-to-end: scan (E-46, 2026-08-13), discover (E-48, 2026-08-15), and assess (E-49, all three plans, 2026-08-16/17). The remaining bodies are owed by E-50…E-52/E-56 (§11). Gated on P5's readiness verdict (FR-903), not merely sequenced after it — and the gate now requires a human approval to admit a tree that is not READY.
```

- [ ] **Step 3: Update FR-911 note (line ~770)**

Replace `Five phase bodies remain stubs reporting not_collected naming the E-item that owes them (discover E-48, assess E-49, finish E-51, report/generate E-52), so an assessment that assessed nothing says so (FR-915). /enrich as a declared stage input remains E-56.` with:

```
Three phase bodies remain stubs reporting not_collected naming the E-item that owes them (finish E-51, report/generate E-52), so an assessment that assessed nothing says so (FR-915). /enrich as a declared stage input remains E-56. 2026-08-16 (E-49 plan 1/2): the stub count dropped from four to three and PHASE_OWNER lost its ASSESS entry — assess is now built and the phase is measured with deterministic score + judged proposer layer. 2026-08-17 (E-49 plan 3): the assess phase is complete; the stub count is unchanged at three (report, generate, finish).
```

- [ ] **Step 4: Close FR-916 (line ~779)**

Replace:

```
    { id: "FR-916", section: "FR", status: "notstarted", title: "STRIDE + vuln classification + control coverage + composites with 1–3 drivers (E-49)",
      note: "", recent: false },
```

with:

```
    { id: "FR-916", section: "FR", status: "done", title: "STRIDE + vuln classification + control coverage + composites with 1–3 drivers (E-49)",
      note: "Per-capability half landed 2026-08-16 (E-49 plans 1 and 2): deterministic baseline composites, severity from a table, factors, rules_sha, memo caching, the quote verifier lifted to assessment/verification.py (RD6), proposer models and contracts, render_risk_prompt, apply_judgment with layer-scoped degradation (RD7), the risk role, and the verify_risk_refs activity. Plan 3 landed 2026-08-17 (the system view): the capability-to-capability projection over attribution.graph.edges, shared vulnerabilities keyed on the path-excluded weakness class, bounded cascades from high-security-composite origins, and trust-boundary and privilege-escalation candidates enumerated by code and dispositioned by the proposer. Known limit, stated and tested: escalation chains are authentication-gated, not authorization-gated, because RD5 leaves Authorization with no scan source.", recent: true },
```

- [ ] **Step 5: Close E-49 (line ~1101)**

Change `status: "notstarted"` to `status: "done"` and `recent: false` to `recent: true` on the `E-49` entry, and append to its existing note (after `...shared vulnerabilities and cascading failures.`):

```
 All three plans landed. Plan 1 (2026-08-16, the deterministic score): PHASE_OWNER loses its ASSESS entry and the phase is measured with no model in the loop; RD3 — defect density and change velocity have no source, so the QA and unified composites are partial on every run; RD5 — SS1 collapses authn/authz and nothing collects monitoring presence, so two of five control families report not_collected. Plan 2 (2026-08-16, the judgment layer): risk proposer role, structured contracts with UnifiedRiskMap.judgment tracking, layer-scoped degradation, and a memo store that refuses to cache degraded judgment under a proposer key. Plan 3 (2026-08-17, the system view): graph projection, shared vulnerabilities, bounded cascades, trust-boundary and privilege-escalation candidates; escalation chains are authentication-gated, not authorization-gated.
```

- [ ] **Step 6: Extend NFR-9 and NFR-10 notes (lines ~856/~858)**

Append to NFR-9's note (after `...the graph is built from blobs already read.`):

```
 E-48 (2026-08-15) adds none either: verify_discover_refs reads committed blobs via git show at the pinned commit and load_blueprint reads a factory-shipped reference file. E-49 plan 1 (2026-08-16) adds no execution and no tree read at all: every input is projected from the CapabilityMap; plan 2 (2026-08-16): verify_risk_refs reads committed blobs via git show at the pinned commit (RD6); plan 3 (2026-08-17): no execution and no tree read — the projection is a re-index of member_paths against a graph discover already built.
```

Append to NFR-10's note (after `...discover/ownership.py do too.`):

```
 E-48 plan 3 (2026-08-15): discover/verify.py, discover/blueprint.py, and discover/domain.py carry their own order-independence assertions. E-49 plan 1 (2026-08-16): risk/severity.py, risk/controls.py, risk/factors.py, risk/composites.py, and risk/build.py; plan 2 (2026-08-16): risk/prompt.py, risk/apply.py, and assessment/verification.py; plan 3 (2026-08-17): risk/crosscap.py — and build()'s own byte-identical assertion now covers the system view.
```

- [ ] **Step 7: Extend FR-902 note (line ~762)**

Append to FR-902's note (after `...cites it by finding_identity and copies nothing.`):

```
 Two follow-ups from E-49 RD5: an SS1 v2 separating authn_authz into distinct authentication and authorization signals, and a monitoring-presence signal so the observability control family has a deterministic source.
```

- [ ] **Step 8: Verify**

Run:
`python -c "html=open('docs/roadmap.html', encoding='utf-8').read(); assert '\"FR-916\", section: \"FR\", status: \"done\"' in html; assert '\"E-49\", section: \"E\", status: \"done\"' in html; assert '2026-08-17' in html; assert html.count('<div') == html.count('</div>'); print('roadmap ok', len(html))"`
Expected: `roadmap ok <length>`

- [ ] **Step 9: Commit**

```bash
git add docs/roadmap.html
git commit -m "docs(roadmap): record the E-49 landing in roadmap.html"
```

---

### Task 2: Synchronize `docs/agents-schema.html`

**Files:**
- Modify: `docs/agents-schema.html`

**Interfaces:**
- Consumes: `agents/risk/{agent.py,agent.yaml}`, `src/sdlc/assessment/risk/models.py` (`RiskProposal`: threats/vulnerabilities/controls/boundaries/escalations), `src/sdlc/agents/loader.py` (17 known roles).
- Produces: 17-role registry doc with a `risk` deep-dive section (`id="risk"`, numbered 16, after `discover`).

- [ ] **Step 1: Update header counts and verified date**

Line ~207: `16 roles total (13 proposers/helpers + 3 harness roles)` → `17 roles total (14 proposers/helpers + 3 harness roles)`.
Line ~211: `Verified <code>2026-08-16</code>` → `Verified <code>2026-08-17</code>`.
Line ~349 (matrix h2): `16 roles &times; key attributes` → `17 roles &times; key attributes`.

- [ ] **Step 2: Add the risk row to the matrix (after the `discover` row, line ~395)**

```
      <tr><td class="mono">risk</td>            <td><span class="pill proposer">proposer</span></td><td class="mono">assess (AssessmentWorkflow)</td><td class="mono">risk_agent</td><td class="mono">anthropic:claude-sonnet-4-5</td><td class="mono">RiskProposal</td><td>&mdash;</td></tr>
```

- [ ] **Step 3: Add the TOC entry (line ~247, after `<a href="#discover">discover</a>`)**

```
  <a href="#risk">risk</a>
```

- [ ] **Step 4: Add the `16. risk` deep-dive section**

Insert between the discover section's closing `</div>` (line ~1600, after the Citation Guard card's `grid-2`) and the `<!-- ####... -->` comment preceding `<h2 id="filemap">`:

```html
<!-- ################################################################ -->
<h2 id="risk">16. risk <span class="pill proposer">proposer</span></h2>

<div class="agent-banner">
  <span class="name">risk</span>
  <span class="kv">activity: <b>risk_agent</b></span>
  <span class="kv">stage: <b>assess (AssessmentWorkflow)</b></span>
  <span class="kv">output: <b>RiskProposal</b></span>
  <span class="kv">model: <b>anthropic:claude-sonnet-4-5</b></span>
  <span class="kv">files: <b>agents/risk/{agent.py, agent.yaml, instructions.md}</b></span>
</div>

<p>
  Risk proposer for the assess phase of <code>AssessmentWorkflow</code> (E-49). Runs over the
  deterministic <code>UnifiedRiskMap</code> baseline &mdash; the proposer never authors a number or
  an edge (RD1): it emits dispositions over rows the deterministic half already produced, tracked
  in <code>UnifiedRiskMap.judgment</code>. Five disposition families and nothing else: STRIDE
  threats, vulnerabilities, control coverage, trust boundaries, and privilege-escalation chains.
</p>

<h3>The contract: <code>RiskProposal</code> <span class="pill asset">sdlc/assessment/risk/models.py</span></h3>
<div class="table-wrap">
  <table>
    <thead><tr><th>field</th><th>type</th><th>rule</th></tr></thead>
    <tbody>
      <tr><td class="mono">threats</td><td class="mono">list[ProposedThreat]</td><td>STRIDE dispositions per capability, with explicit rationale for inapplicable categories.</td></tr>
      <tr><td class="mono">vulnerabilities</td><td class="mono">list[ProposedVulnerability]</td><td>confirmed | probable | potential classifications.</td></tr>
      <tr><td class="mono">controls</td><td class="mono">list[ProposedControl]</td><td>Coverage dispositions across the five control families.</td></tr>
      <tr><td class="mono">boundaries</td><td class="mono">list[ProposedBoundary]</td><td>Trust-boundary dispositions over code-enumerated candidates (plan 3).</td></tr>
      <tr><td class="mono">escalations</td><td class="mono">list[ProposedEscalation]</td><td>Privilege-escalation chain dispositions (authentication-gated, RD5).</td></tr>
    </tbody>
  </table>
</div>

<div class="grid-2">
  <div class="card soft">
    <h4>Grounding &amp; Byte Verification <span class="pill det">verify_risk_refs</span></h4>
    <p style="margin:6px 0 0">
      Every evidence path and quote is byte-verified against the pinned commit via
      <code>verify_risk_refs</code>, using the row-level verifier lifted to
      <code>assessment/verification.py</code> (RD6, shared with discover's
      <code>verify_discover_refs</code>). One fabrication rate over all rows; the citation guard
      fails closed.
    </p>
  </div>
  <div class="card soft">
    <h4>Layer-Scoped Degradation <span class="pill warn">RD7 &middot; P2-D2/D3</span></h4>
    <p style="margin:6px 0 0">
      A failed or fabricating proposer leaves the deterministic baseline composites measured and
      degrades <code>UnifiedRiskMap.judgment</code> with distinct, non-converging reasons; the
      memo store refuses to cache a degraded judgment under a proposer key, so a transient failure
      costs one recompute rather than freezing an unjudged map into cache.
    </p>
  </div>
</div>
```

- [ ] **Step 5: Verify**

Run:
`python -c "html=open('docs/agents-schema.html', encoding='utf-8').read(); assert 'id=\"risk\"' in html; assert 'risk_agent' in html; assert '17 roles' in html; assert html.count('<div') == html.count('</div>'); print('agents ok', len(html))"`
Expected: `agents ok <length>`

- [ ] **Step 6: Commit**

```bash
git add docs/agents-schema.html
git commit -m "docs(agents): document the risk proposer in agents-schema.html"
```

---

### Task 3: Synchronize `docs/architecture-schema.html`

**Files:**
- Modify: `docs/architecture-schema.html`

**Interfaces:**
- Consumes: E-49 module map (`src/sdlc/assessment/risk/{severity,controls,factors,composites,build,prompt,apply,crosscap,models}.py`, `assessment/verification.py`, `assessment/activities.py::assess_risk`).
- Produces: EDCR section covering the assess phase (E-45–E-49, FR-911–FR-916) and 17-role counts.

- [ ] **Step 1: Update the meta line (line ~326)**

`Verified <code>2026-08-15</code>` → `Verified <code>2026-08-17</code>`, and insert `<code>assessment/risk/</code>, ` after `<code>assessment/discover/</code>, ` in the source list.

- [ ] **Step 2: Update role counts (lines ~736–738 and ~900)**

Line ~736 status cell: `16 roles ✅` → `17 roles ✅`.
Line ~738 note: `E-1/E-2/E-48 done. 3 harness + 9 proposers (incl. discover) + 4 optional lenses (research, deep_review, handoff, adversary)` → `E-1/E-2/E-48/E-49 done. 3 harness + 8 required proposers + 6 optional lenses (research, deep_review, handoff, adversary, discover, risk)`.
Line ~900 list item: `16 roles in <code>agents.yaml</code>: 3 harness + 9 proposers (incl. <code>discover</code>) + 4 optional lenses (research, deep_review, handoff, adversary).` → `17 roles in <code>agents/&lt;role&gt;/</code>: 3 harness + 8 required proposers + 6 optional lenses (research, deep_review, handoff, adversary, <code>discover</code>, <code>risk</code>).`

- [ ] **Step 3: Extend the EDCR pipeline section (line ~848)**

Change the section count tag `E-45&ndash;E-48` → `E-45&ndash;E-49` and `FR-911&ndash;FR-915` → `FR-911&ndash;FR-916`. Then append two cards inside the `grid-2` (after the `Blueprints &amp; Domain Model` card's closing `</div>`, line ~890):

```html
  <div class="card tinted">
    <h3>Assess Phase &mdash; Deterministic Score <span class="tag-link">E-49 plan 1 &middot; risk/{severity,controls,factors,composites,build}.py</span></h3>
    <ul class="tight">
      <li><span class="pill done">done</span> <strong>UnifiedRiskMap baseline, no model in the loop:</strong> criticality derived, severity from a table, absence never a rating; <code>PHASE_OWNER</code> loses its <code>ASSESS</code> entry so the phase is measured.</li>
      <li><span class="pill done">done</span> <strong>Composites with sentinels:</strong> five control families (two report <code>not_collected</code> by RD5 decision, not mirroring), factors with 1&ndash;3 drivers, partial propagating (RD3 &mdash; QA/unified composites partial every run), memoized on <code>(map digest, rules_sha)</code>.</li>
    </ul>
  </div>

  <div class="card tinted">
    <h3>Risk Proposer, Judgment &amp; System View <span class="tag-link">E-49 plans 2&ndash;3 &middot; agents/risk/ &middot; risk/{prompt,apply,crosscap}.py</span></h3>
    <ul class="tight">
      <li><span class="pill done">done</span> <strong>Judgment layer:</strong> <code>risk_agent</code> proposer emits <code>RiskProposal</code> (STRIDE, vulnerability, control dispositions); <code>apply_judgment</code> degrades layer-scoped, never the baseline; <code>verify_risk_refs</code> byte-verifies quotes via the lifted <code>assessment/verification.py</code> (RD6); memo refuses degraded judgment under a proposer key (P2-D3).</li>
      <li><span class="pill done">done</span> <strong>System view (plan 3):</strong> capability&rarr;capability projection over <code>attribution.graph.edges</code>, shared vulnerabilities on the path-excluded weakness class, bounded cascades from high-security-composite origins, trust-boundary + privilege-escalation candidates dispositioned by the proposer. Known limit: escalation chains are authentication-gated, not authorization-gated (RD5).</li>
    </ul>
  </div>
```

- [ ] **Step 4: Update the P6 exit text (line ~1018)**

Replace `Assess (E-49), finish (E-51), and report/generate (E-52) phases remain stubs.` with:

```
Assess landed (E-49, 2026-08-16/17: deterministic UnifiedRiskMap score + judged proposer layer + system view, closing FR-916); finish (E-51) and report/generate (E-52) phases remain stubs.
```

- [ ] **Step 5: Verify**

Run:
`python -c "html=open('docs/architecture-schema.html', encoding='utf-8').read(); assert '17 roles' in html; assert 'E-45&ndash;E-49' in html; assert 'assessment/risk/' in html; assert html.count('<div') == html.count('</div>'); print('architecture ok', len(html))"`
Expected: `architecture ok <length>`

- [ ] **Step 6: Commit**

```bash
git add docs/architecture-schema.html
git commit -m "docs(architecture): update architecture-schema.html for E-49"
```

---

### Task 4: Benchmark refresh check + final validation

**Files:**
- Modify (expected no-op): `docs/benchmark-analysis.html`

**Interfaces:**
- Consumes: `scripts/aggregate_benchmarks.py`, `runs/benchmarks`.

- [ ] **Step 1: Regenerate `docs/benchmark-analysis.html`**

Run: `python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out docs/benchmark-analysis.html`
Expected: `wrote docs/benchmark-analysis.html  (309,510 bytes)` with `runs=21  records=556` — byte-identical to HEAD (`git diff --stat docs/benchmark-analysis.html` empty). If a diff appears, commit it as `docs(benchmarks): refresh benchmark analysis`; otherwise skip the commit.

- [ ] **Step 2: Final validation across all six docs**

Run:
`python -c "import pathlib; files=['roadmap.html','agents-schema.html','architecture-schema.html','benchmark.html','benchmark-analysis.html','research-stage-schema.html']; sizes={f:(pathlib.Path('docs')/f).stat().st_size for f in files}; assert all(s>10000 for s in sizes.values()); print('all 6 docs present:', sizes)"`

Then spot-check cross-links resolve (each file's nav hrefs point to existing sibling files):
`python -c "import pathlib,re; docs=pathlib.Path('docs'); [print(f, sorted(set(re.findall(r'href=\"([a-z-]+\.html)', (docs/f).read_text(encoding='utf-8'))))) for f in ['roadmap.html','agents-schema.html','architecture-schema.html','benchmark.html','research-stage-schema.html']]"`

Expected: every listed target exists in `docs/`.

- [ ] **Step 3: Final diff review**

Run `git diff --stat HEAD` and `git log --oneline -4`; confirm only the three intended files changed across three commits (plus benchmark-analysis only if step 1 produced a diff).
