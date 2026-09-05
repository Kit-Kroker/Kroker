# HTML Documentation Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronize all 6 HTML documentation files in `docs/` to reflect recent landings of E-84 (Brownfield mode), E-48 (Discover proposers), the 16-agent registry, and benchmark aggregation.

**Architecture:** Update each HTML file with accurate status data, contracts, DAG diagrams, role cards, and interactive visualizations, keeping them strictly consistent with `ROADMAP.md`, `ARCHITECTURE.md`, and code.

**Tech Stack:** HTML5, Vanilla JavaScript, CSS custom properties, Chart.js, Python (`scripts/aggregate_benchmarks.py`).

## Global Constraints

- Preserve vanilla CSS and GitHub-inspired dark/light theme styling in all HTML documents.
- Keep all interactive filtering, search, and navigation widgets fully functional.
- Maintain exact terminology, contract names, and epic numbers matching `ROADMAP.md` and `ARCHITECTURE.md`.
- No external runtime dependencies beyond what is already bundled or loaded via CDN (e.g. IBM Plex / Chart.js).

---

### Task 1: Synchronize `docs/roadmap.html`

**Files:**
- Modify: `docs/roadmap.html`

**Interfaces:**
- Consumes: `ROADMAP.md` status, stage definitions, requirements, and epic entries.
- Produces: Updated interactive HTML roadmap with 11/15 live stages, closed FR-102/FR-913/FR-914, and E-84/E-48 epics.

- [ ] **Step 1: Update metadata, header summary, and stage list in `docs/roadmap.html`**

Update the header meta text to snapshot `2026-08-15`, detailing the landing of E-84 and E-48.
Update stage 0 (`intake`) and stage 2 (`context`) statuses to `"done"`, and update the stage count banner to `"11 of 15 stages live"`.

- [ ] **Step 2: Update requirements array in `docs/roadmap.html`**

Update:
- `FR-102`: `status: "done"`, title: `"greenfield/brownfield classify + CodebaseMap + delta"`, note detailing E-84 landing (2026-08-15).
- `FR-913`: `status: "done"`, note detailing all 3 plans of E-48 landed (2026-08-15).
- `FR-914`: `status: "done"`, note detailing `verify_discover_refs` and citation guard.

- [ ] **Step 3: Update epics array and priorities in `docs/roadmap.html`**

Add `E-84` (`status: "done"`, `title: "Brownfield intake, context, and checked delta"`, `note: "Landed 2026-08-15."`) under Section 10.
Update `E-48` (`status: "done"`, note detailing landing on 2026-08-15).
Update Next Priorities list to reflect that FR-102 and Discover are done.

- [ ] **Step 4: Verify `docs/roadmap.html` in browser/syntax check**

Run a Python one-liner to verify that the inline JSON/JS data in `docs/roadmap.html` parses cleanly:
`python -c "import re, json; html=open('docs/roadmap.html', encoding='utf-8').read(); print('Roadmap HTML length:', len(html))"`
Expected: Output showing valid length with no syntax errors.

- [ ] **Step 5: Commit `docs/roadmap.html`**

```bash
git add docs/roadmap.html
git commit -m "docs(roadmap): update roadmap.html with E-84 and E-48 landings"
```

---

### Task 2: Synchronize `docs/agents-schema.html`

**Files:**
- Modify: `docs/agents-schema.html`

**Interfaces:**
- Consumes: `agents/` registry (`config/agents.yaml`, `agents/discover/`, `sdlc/agents/loader.py`).
- Produces: Up-to-date agents documentation including all 16 roles and dedicated deep-dive for the `discover` proposer.

- [ ] **Step 1: Update total role counts and summary stats in `docs/agents-schema.html`**

Update role counts: 16 roles total (13 proposers/helpers + 3 harness roles). Update legend badges, TOC, and summary table.

- [ ] **Step 2: Add `discover` Proposer section in `docs/agents-schema.html`**

Add the complete deep-dive section for `discover`:
- Header: `<h2 id="discover">discover <span class="pill proposer">proposer</span></h2>`
- Agent banner: name `discover`, activity `discover_agent`, stage `discover`, output `DiscoverProposals`, model `anthropic:claude-sonnet-4-5`, files `agents/discover/{agent.py, agent.yaml, instructions.md}`.
- Payload descriptions: `DiscoverProposals`, `CapabilityProposal`, `RefinementProposal`, `AttributionProposal`.
- Grounding & citation guard cards: `verify_discover_refs`, `Profile.VERBATIM_BYTES`, citation guard threshold (`0.10`).

- [ ] **Step 3: Verify `docs/agents-schema.html`**

Run verification check to ensure all anchor targets and tags are well-formed:
`python -c "html=open('docs/agents-schema.html', encoding='utf-8').read(); assert 'id=\"discover\"' in html; assert 'discover_agent' in html; print('Agents schema valid')"`
Expected: PASS with `'Agents schema valid'`

- [ ] **Step 4: Commit `docs/agents-schema.html`**

```bash
git add docs/agents-schema.html
git commit -m "docs(agents): document discover proposer in agents-schema.html"
```

---

### Task 3: Synchronize `docs/architecture-schema.html`

**Files:**
- Modify: `docs/architecture-schema.html`

**Interfaces:**
- Consumes: `ARCHITECTURE.md`, `SDLC-spec-v2.md`, E-84 and E-48 architecture specs.
- Produces: Updated architecture schema with 11/15 live stages, Cartographer context flow, and Discover assessment stage.

- [ ] **Step 1: Update Feature Pipeline stage count and live statuses in `docs/architecture-schema.html`**

Update stage 0 (intake) and stage 2 (context) to live (`done`). Update header to reflect **11 of 15 live stages**.

- [ ] **Step 2: Update Brownfield Context & Cartographer flow**

Add the Cartographer flow card: `classify_repo` → Scan tree → `CodebaseMap` projection → `render_for_prompt` → `BrownfieldDelta` → `check_brownfield_delta`.

- [ ] **Step 3: Update Assessment Workflow EDCR pipeline section**

Update Scan stage (13 pure signals) and Discover stage (E-47a/b/c + E-48 proposers, verification, citation guard, blueprint, domain model).

- [ ] **Step 4: Verify `docs/architecture-schema.html`**

Run verification check:
`python -c "html=open('docs/architecture-schema.html', encoding='utf-8').read(); assert '11 of 15' in html or '11/15' in html; print('Architecture schema valid')"`
Expected: PASS with `'Architecture schema valid'`

- [ ] **Step 5: Commit `docs/architecture-schema.html`**

```bash
git add docs/architecture-schema.html
git commit -m "docs(architecture): update architecture-schema.html for E-84 and E-48"
```

---

### Task 4: Regenerate `docs/benchmark-analysis.html` and Update Supporting Docs

**Files:**
- Modify: `docs/benchmark-analysis.html`
- Modify: `docs/benchmark.html`
- Modify: `docs/research-stage-schema.html`

**Interfaces:**
- Consumes: `runs/benchmarks`, `scripts/aggregate_benchmarks.py`, `BENCHMARK.md`.
- Produces: Freshly generated benchmark analysis report, synchronized benchmark foundation doc, and updated research stage schema.

- [ ] **Step 1: Regenerate `docs/benchmark-analysis.html`**

Run:
`python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out docs/benchmark-analysis.html`
Expected: Output showing generated HTML file (`wrote docs/benchmark-analysis.html ...`).

- [ ] **Step 2: Update `docs/benchmark.html`**

Update header date to `2026-08-15`, reflect 9 corpus benchmark cases (including DevEval E-79), SC-7 grounding integrity status (enforced by citation guard), and toolchain adapter status.

- [ ] **Step 3: Update `docs/research-stage-schema.html`**

Sync navigation header, cross-links, and verify all relative links resolve.

- [ ] **Step 4: Verify all 6 HTML files**

Run a script that validates all 6 HTML files exist, are non-empty, and contain valid UTF-8:
`python -c "import pathlib; files=['roadmap.html', 'agents-schema.html', 'architecture-schema.html', 'benchmark.html', 'benchmark-analysis.html', 'research-stage-schema.html']; [assert (pathlib.Path('docs')/f).stat().st_size > 10000 for f in files]; print('All 6 HTML docs verified')"`
Expected: PASS with `'All 6 HTML docs verified'`

- [ ] **Step 5: Commit all remaining documentation files**

```bash
git add docs/benchmark-analysis.html docs/benchmark.html docs/research-stage-schema.html
git commit -m "docs(benchmarks): refresh benchmark analysis, foundation doc, and research schema"
```
