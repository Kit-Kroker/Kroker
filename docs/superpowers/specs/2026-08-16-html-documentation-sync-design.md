# Design Doc: HTML Documentation Synchronization (2026-08-16)

## 1. Objective

Synchronize all HTML documentation files in `docs/` (`roadmap.html`, `agents-schema.html`, `architecture-schema.html`, `benchmark.html`, `benchmark-analysis.html`, `research-stage-schema.html`) to fully reflect recent landings in the codebase, specifically:
1. **E-84 (Brownfield intake, context, and checked delta)**: Stage 0 (`intake`) and Stage 2 (`context`) are live (11/15 stages live), `FR-102` is closed.
2. **E-48 (Discover proposers)**: `FR-913` and `FR-914` are closed; the complete Scan + Discover pipeline is wired into `AssessmentWorkflow`.
3. **Agent Registry**: 16 roles in total (13 proposers/helpers + 3 harness roles), including the newly added `discover` proposer (`agents/discover/`).
4. **Benchmark Suite**: 9 benchmark cases (with DevEval E-79) and updated aggregation across all benchmark runs in `runs/benchmarks`.

## 2. Detailed File Updates

### 2.1 `docs/roadmap.html`
- **Metadata**: Set snapshot date to `2026-08-15`, add landing summary notes for E-84 and E-48.
- **Stage DAG (Section 1)**:
  - `0 · intake`: Set status `done`, note E-84 D3 `classify_repo` activity against git tree.
  - `2 · context (Cartographer)`: Set status `done`, note E-84 `CodebaseMap` projected from scan tree, bounded prompt rendering (`render_for_prompt`), and `check_brownfield_delta` grounding check with 1 retry.
  - Stage count header: Set to **11 of 15 stages live**.
- **Functional Requirements (Section 2)**:
  - `FR-102`: Set status `done`, note E-84 landing (2026-08-15) with `classify()` pure rule, `classify_repo` activity, `CodebaseMap` projection from 13 Tier 2 scan signals, bounded prompt rendering, typed `BrownfieldDelta`, and git grounding check in architecture stage.
  - `FR-913`: Set status `done` (E-47a/b/c and E-48 landed 2026-08-15).
  - `FR-914`: Set status `done` (E-43 and E-48 plan 3 landed 2026-08-15 with `verify_discover_refs` and citation guard).
- **Epics (Section 10 & 11)**:
  - Add `E-84` as `done` (Brownfield intake, context, and checked delta → FR-102).
  - Mark `E-48` as `done` (discover proposers → FR-913/FR-914).
  - Update next-step list and phase notes (FR-102 unblocks P2 brownfield feature runs; Discover phase unblocks E-49 assess phase).

### 2.2 `docs/agents-schema.html`
- **Header & Stats**: Update role counts to 16 total roles (13 proposers/helpers + 3 harness roles).
- **Table of Contents & Index**: Add entry for `discover` proposer.
- **Discover Proposer Deep Dive Section**:
  - Identity: Role `discover`, Activity `discover_agent`, Stage `discover` (`AssessmentWorkflow`), Output `DiscoverProposals`, Model `anthropic:claude-sonnet-4-5`.
  - Files: `agents/discover/{agent.py, agent.yaml, instructions.md}`.
  - Sub-contracts: `DiscoverProposals` containing `CapabilityProposal`, `RefinementProposal`, `AttributionProposal`.
  - Grounding & Guard: Quotes and evidence paths byte-verified against pinned commit (`Profile.VERBATIM_BYTES`), citation guard failing closed if fabrication rate > 0.10.
  - Context & Blueprint: Receives scan signals and loads reference blueprints (BIAN/TM Forum/ACORD/HL7).

### 2.3 `docs/architecture-schema.html`
- **Feature Pipeline DAG**: Reflect Stage 0 (intake) and Stage 2 (context) as live; update live stage count to 11/15.
- **Brownfield Context Architecture**: Detail the flow from `classify_repo` → Scan tree → `CodebaseMap` projection → `render_for_prompt` → `BrownfieldDelta` (added/modified/removed) → `check_brownfield_delta` git check.
- **Assessment Pipeline (EDCR)**: Detail Scan stage (13 pure signals) and Discover stage (E-47a identity `BC-NNN`, E-47b attribution/orphans, E-47c L2 operations/ownership, E-48 proposers, verification, citation guard, blueprint comparison, derived domain model).

### 2.4 `docs/benchmark-analysis.html`
- Regenerate using `python scripts/aggregate_benchmarks.py --runs runs/benchmarks --out docs/benchmark-analysis.html`.
- Incorporates all 21 runs and 556 records with updated Chart.js graphs.

### 2.5 `docs/benchmark.html`
- Update header snapshot to `2026-08-15`.
- Update corpus table to 9 cases (including DevEval E-79).
- Update SC-7 grounding integrity status (enforced by E-43 / E-48 citation guard).
- Update toolchain adapter statuses (ADR-15, E-30).

### 2.6 `docs/research-stage-schema.html`
- Synchronize navigation headers, cross-document links, and stage index.

## 3. Verification Plan
1. Validate HTML structure, markup validity, and visual rendering across all updated files.
2. Confirm that all links between `roadmap.html`, `agents-schema.html`, `architecture-schema.html`, `benchmark.html`, `benchmark-analysis.html`, and `research-stage-schema.html` resolve cleanly.
3. Run `python scripts/aggregate_benchmarks.py` to confirm clean generation.
4. Run `git diff` to ensure precision and lack of unintended formatting breaks.
