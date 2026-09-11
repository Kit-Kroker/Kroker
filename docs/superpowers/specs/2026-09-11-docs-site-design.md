# Generated documentation site — replacing the hand-maintained schema pages

| | |
|---|---|
| Date | 2026-09-11 |
| Status | Reviewer-approved. The r1 FIXES-NEEDED were four one-line folds, applied here; the reviewer ruled that no re-review was needed. Advisor consensus on F1–F7 and D2 (`.workspace/tmp/advisor-docs-site-1.md`, `-2.md`). D1 is overridden with evidence (§2). Awaiting the user gate on Q1–Q2 (§10). |
| Supersedes | The hand-sync plan in `2026-09-11-html-schema-sync-design.md` (its §9 records the pivot) |
| Scope | Docs tooling, CI, the ROADMAP US-6/US-8 restoration, and retiring `docs/schemas/`. No product behaviour changes. |

## 1. Why

The six `docs/schemas/*.html` pages were hand copies of the living docs, and
they rotted. Their last content sync was 2026-08-16..19, and a 2026-09-02
move was mistaken for a sync. They carried three kinds of error: claims that
were never true (FR-107/305/915, "16-role registry"), design-era module names
that never existed in git (`workflows/factory.py`, `activities/*.py`), and
lag behind every stage-slice move. All of this is catalogued in
`2026-09-11-html-schema-sync-design.md` §§2–3, 6. Each of those failures
comes from a human copying data by hand. The user gate ruled that the copying
stops and a site generated from the sources replaces it.

Ruled constraints, carried in from that gate:
- **R2.** The site mirrors the living docs only. Register-only landings (C2,
  C3, C4, B4, E4, C7, C8, F2, F4) appear when the living docs describe them,
  never from `docs/reports/external-ideas-2026-09.md`.
- **R3.** US-6/US-8 are restored in `ROADMAP.md` §5 as part of this work.
  The generator cannot render what ROADMAP lacks.

## 2. Decisions

| Fork | Decision | Deciding reason |
|---|---|---|
| Generator | **mkdocs-material + mkdocs-gen-files.** `mkdocs.yml` uses only standard options, so it stays readable by zensical, the Material team's pre-1.0 successor. | Python-native like the repo; native mermaid (ARCHITECTURE.md uses it); built-in search; `--strict` fails on broken links. zensical 0.0.60 is pre-1.0; the compatible config is the migration path. |
| Publishing | **CI builds; GitHub Pages hosts; nothing built is committed.** | A committed build is a generated copy in git, and generated copies rot the same way the hand pages did. |
| Page set (v1) | Living markdown **plus three generated pages**: roadmap status board, agent registry, benchmark analysis. **No** Pydantic JSON-schema pages. | Stage contracts (`<stage>.md`) already state what the models promise, and raw JSON schema adds build surface without adding a reader (YAGNI). |
| Absent benchmark data | Build never fails. The page renders an explicit empty state, and the 2026-08-15 snapshot moves to `docs/reports/` as a dated artifact. | `runs/benchmarks/` is gitignored and never exists in CI. |
| Code paths in links | A build hook classifies each relative link. A target that is a site page is left for mkdocs to resolve. A target that is a repo file not on the site (e.g. `src/…/*.py`) is rewritten to a GitHub `blob/main` URL. A target that exists nowhere in the repo **fails the build**. Fail mode is safe from day one: across the 51 living source files at `93e29d3` there are 27 relative links, and none is dead. The advisor proposed starting in warn mode (`advisor-docs-site-2.md` D1). Its premise, dead links to `models.py` / `feature.py:1726`, confuses backticked prose paths with links, and the scan disproves it. So fail mode stays. If it trips, the error names every offender. | `--strict` would otherwise reject every link to `src/…`. Failing on missing targets closes the link half of the dead-path class that sank the hand pages. |
| Backticked (non-link) paths | Out of scope; follow-up inbox task. | A prose path linter is a separate tool with its own false-positive surface. |

## 3. Architecture

Everything is repo tooling, not product code. The product/harness boundary in
`docs/documentation-rules.md` keeps it out of `src/sdlc/`.

```
mkdocs.yml                      site config: theme, nav, markdown extensions,
                                exclude_docs, plugins (search, gen-files), hooks
scripts/docs/
  gen_pages.py                  gen-files entry point: pulls out-of-tree living
                                sources in as virtual pages; emits generated pages
  roadmap_board.py              parse ROADMAP.md + docs/roadmap/*.md checkboxes → board
  agent_registry.py             read agents/*/agent.yaml (+ instructions.md presence) → table
  link_hook.py                  mkdocs hook: rewrite out-of-site repo links; fail on missing targets
scripts/aggregate_benchmarks.py existing; gains an empty-state render
.github/workflows/docs.yml      build --strict on push/PR; deploy on push to main
tests/docs_site/                unit tests for the parser, registry reader, link hook,
                                and the aggregator empty state
```

**Source → page map.**
- **`docs_dir` is `docs/`.** `exclude_docs` (gitignore syntax) removes
  `superpowers/`, `reports/*`, `schemas/` and every `AGENTS.md`. `reports/`
  is excluded file by file, because it holds immutable snapshots and the
  register that R2 keeps out, with one negated exception:
  `!reports/2026-08-15-benchmark-analysis.html`. The pattern is written as
  `reports/*`, not `reports/`, because gitignore cannot re-include a file
  inside a directory that is itself excluded. That single dated snapshot
  is copied to the site as a static file, so the benchmark empty state can
  link to it relatively and it renders with its charts. A GitHub blob link
  would show raw HTML.
- **Links resolve against each source's repo path.** Virtual pages keep
  their repo-relative paths, so a link inside
  `src/sdlc/stages/qa/qa.md` resolves exactly as it does on GitHub. The
  hook classifies the resolved target; it never guesses from the link text.
- **`docs/schemas/` during P1–P2.** It is excluded from the site but still
  in the repo. Links to its pages (`README.md:133-140`) are therefore
  "repo file not on the site" and are rewritten to GitHub URLs. The P3
  cutover commit deletes the pages and rewrites those README links to the
  generated pages in the same commit, so no build ever sees a link to a
  deleted page.
- **In-tree pages**: `docs/framework.md`, `docs/documentation-rules.md`,
  `docs/features/`, `docs/modes/`, `docs/roadmap/`, `docs/reference/` and
  `docs/templates/`.
- **Virtual pages pulled in by `gen_pages.py`.** The files stay where
  co-location requires them to be. Mkdocs sees virtual copies placed at
  their repo-relative paths (e.g. `ARCHITECTURE.md`,
  `src/sdlc/stages/qa/qa.md`). Existing relative links between them
  therefore keep resolving. `site/` is mkdocs' build output and is
  gitignored.
  - Root: `README.md`, `PRD.md`, `ARCHITECTURE.md`, `ROADMAP.md`,
    `BENCHMARK.md`, `SDLC-spec-v2.md`.
  - The 13 stage contracts: `src/sdlc/stages/<s>/<s>.md`.
  - The UI clause docs, **contingent on Q2** (§10): `interfaces/ui/app.md`,
    `interfaces/ui/src/components/*/<name>.md`, `interfaces/ui/src/tokens/tokens.md`.
    If Q2 rules them out, this bullet and the Interfaces nav section below
    are dropped.
- **Nav** follows the durability table in `documentation-rules.md`:
  Overview (README, PRD, SDLC-spec) · Architecture (ARCHITECTURE, framework,
  features, stage contracts) · Roadmap (ROADMAP, board, docs/roadmap) ·
  Benchmark (BENCHMARK, analysis) · Agents (registry) · Interfaces (UI
  clauses; contingent on Q2) · Contributing (documentation-rules, modes, templates, reference).
- **Never on the site**: `docs/superpowers/**`, `docs/reports/**`,
  `AGENTS.md`/`CLAUDE.md` files, `.claude/`, `.agents/`, `records/`,
  `benchmarks/cases/`, `agents/*/instructions.md`. The last are product
  prompts: the registry page reports whether each is present, not what it says.

**Generated pages.**
1. *Roadmap status board* (`roadmap_board.py`).
   - The parsing rule is the one the old page documented: `[x]`→done,
     `[ ] ⚠️`→partial, `[ ]`→notstarted, `—`→notmeasurable, keyed by the bold
     id.
   - It emits per-section tables (id · status · title · source file:line
     link) and a status-totals summary.
   - The old page's client-side filter UI is not rebuilt; site search covers
     lookup.
   - The parser reports ids it cannot classify, and the build fails on
     them, so a malformed checkbox is caught at build time instead of
     silently dropped.
2. *Agent registry* (`agent_registry.py`).
   - It reads `agents/<role>/agent.yaml` as plain YAML: kind, harness, model.
   - It flags `instructions.md` presence per role and emits a role table
     with a count.
   - It deliberately does **not** import `src/sdlc/agents/loader.py`. The
     loader drags the runtime dependency set into the docs build, and the
     boundary rule forbids using product runtime machinery as dev tooling.
   - Crew roles (`crew/roles/*.yaml`) get a second table, because
     ARCHITECTURE §4 documents them.
3. *Benchmark analysis.*
   - `aggregate_benchmarks.py` gains a missing/empty-`runs/benchmarks/`
     branch. `aggregate()` returns an empty dataset, and `build_html()`
     renders "No benchmark runs are available to this build" with a link to
     the dated snapshot.
   - `gen_pages.py` calls it and places the output under the site.
   - Local builds that have runs render the real analysis. The public site
     will always show the empty state, because runs are never committed. That
     is a known limit, not a defect; see §7.

## 4. Build and publish

- `pyproject.toml` gains a `docs` extra: `mkdocs-material`, `mkdocs-gen-files`.
  Resolved clean on Python 3.14 (dry-run at `93e29d3`).
- `.github/workflows/docs.yml` has two jobs:
  - **`build`** runs on every push and PR: `pip install -e ".[docs]"`, then
    `mkdocs build --strict`.
  - **`deploy`** runs on push to `main` only, `needs: build`. It uses
    `actions/upload-pages-artifact` + `actions/deploy-pages`, with the
    `pages: write` / `id-token: write` permissions.
- "Refreshes itself" means every push to `main` rebuilds from the sources.
  There is no other refresh path, because the sources only change by commit.
- **User action at cutover:** enable GitHub Pages with source "GitHub
  Actions" on Kit-Kroker/Kroker (public repo; Pages currently 404). This is
  an outward-facing setting, so the plan stops for the user rather than
  doing it.
- The site's local preview is `mkdocs serve`. `scripts/verify.py` does not
  gain the docs build, which stays a CI job of its own.

## 5. Cutover and retirement

The cutover comes only after the site builds strict, deploys, and has been
checked by the user.
1. **Unique-content audit** (advisor F5). Before deleting, list each hand
   page's prose sections whose substance no living doc carries (e.g. the
   research page's gotchas list, the agents page's per-role "contract"
   blocks). Each goes into one `.workspace/tasks/` item as a living-doc gap.
   Nothing is hand-ported into the site; per R2 it appears when a living doc
   carries it.
2. **Move** `docs/schemas/benchmark-analysis.html` →
   `docs/reports/2026-08-15-benchmark-analysis.html` (dated snapshot, immutable).
3. **Delete** the other five pages and the `docs/schemas/` directory.
4. **Rewrite every inbound reference:**
   - `README.md:133-140`: point to the site URL and the `mkdocs serve`
     command.
   - `AGENTS.md:175`.
   - `docs/documentation-rules.md:46`: the `docs/schemas/` row is replaced
     by a row for the site, "`mkdocs.yml` + `scripts/docs/` — generated in
     CI, never committed".
   - `scripts/aggregate_benchmarks.py`: `--out` default, and the usage
     docstring at line 9.
   - `scripts/check_file_size.py:47-56`: retire both the `docs/schemas/*`
     exemption (line 56) and its pre-move sibling `docs/*.html` (line 55),
     which is equally dead once the pages are gone. Both test lines go with
     them: `tests/test_check_file_size.py:48` (`docs/roadmap.html`) and `:49`
     (`docs/schemas/roadmap.html`).
   - `src/sdlc/stages/architecture/models.py:33`: a docstring-only edit,
     citing `ARCHITECTURE.md` / the architecture `<stage>.md` instead of the
     deleted page.
5. Historical references inside `docs/superpowers/**` are left untouched
   (`documentation-rules.md`: history is not rewritten).

## 6. ROADMAP US-6/US-8 restoration (R3)

Re-insert the two lines that `9bfe73e` removed into `ROADMAP.md` §5, in id
order around US-7, using their last source wording (`git show
a806ae3:ROADMAP.md`). Re-verify each claim against main before restoring:
- US-6 cites `GET /api/runs` and the `/api/events` SSE stream (E-10).
- US-8 cites `sdlc triage` and `mechanical_backlog` on `TidyUpReport`.

A claim that no longer holds is restored with its corrected wording and a
dated correction note, the way FR-704 was. This is a separate commit and
rides the normal gates.

## 7. Known limits

- The public site's benchmark page always shows the empty state. Publishing
  real results would mean committing run summaries: a different decision,
  not this spec.
- Prose (backticked) paths are not checked; follow-up task. Link targets
  are checked (§2).
- The site reproduces whatever the living docs say, including their lag
  (e.g. ARCHITECTURE §14's stale tree). The fix belongs in the living docs.
  It is filed as the "living docs lag main" task from the prior spec §6, not
  worked around in the generator.

## 8. Phasing (for the plan)

- **P1: skeleton.**
  - `docs` extra, `mkdocs.yml`, `gen_pages.py` pulling the living sources,
    `link_hook.py`, `docs.yml` `build` job.
  - Exit: `mkdocs build --strict` green locally and in CI.
- **P2: generated pages.**
  - `roadmap_board.py`, `agent_registry.py`, the aggregator empty state,
    each with unit tests.
  - Exit: all three pages render. The board's totals equal an independent
    re-count of the source checkboxes. The registry count equals the number
    of `agents/` role dirs.
- **P3: restore, publish, cut over.**
  - US-6/US-8 restoration.
  - `deploy` job, after the user enables Pages.
  - Unique-content audit, then the cutover commit.
  - Exit: the site is live, `docs/schemas/` is gone, no inbound reference
    points at it (`git grep docs/schemas -- ':!docs/superpowers'` is empty
    apart from the dated snapshot's own report path, if any), and the full
    CI suite plus the file-size test pass.

## 9. Acceptance checks (mechanical)

1. `mkdocs build --strict` exits 0 locally and in CI.
2. `tests/docs_site/` passes:
   - the board parser against fixture markdown covering all four statuses,
     plus an unparseable line, which must raise;
   - the link hook rewriting an existing path and raising on a missing one;
   - the registry reader;
   - the aggregator rendering its empty state when `runs/benchmarks/` is
     absent.
3. The built site contains no page sourced from `docs/superpowers/`,
   `docs/reports/`, or any `AGENTS.md`. Check: a test builds the site and
   asserts that no source path in the built file list starts with
   `superpowers/` or `reports/` or ends with `AGENTS.md`, apart from the
   check-7 snapshot.
4. Board parity: an independent count of source checkboxes per status
   equals the board's totals.
5. `ROADMAP.md` contains `**US-6**` and `**US-8**`.
6. After cutover, `git grep -n 'docs/schemas' -- ':!docs/superpowers'`
   returns nothing, and `docs/reports/2026-08-15-benchmark-analysis.html`
   exists.
7. The built `site/reports/` holds exactly one file,
   `2026-08-15-benchmark-analysis.html`, which the `exclude_docs` negation
   let through. The benchmark empty-state page links to it relatively.
8. `ruff`, `mypy` (scope unchanged), `pytest` and
   `scripts/check_file_size.py` all pass.

## 10. Open questions for the user gate

- **Q1. Pages hosting.** Enabling GitHub Pages publishes the living docs of
  this public repo at a public URL. Confirm (recommended), or build-only in
  CI with no hosting, as a CI artifact.
- **Q2. Site scope beyond `docs/`.** Include the UI clause docs
  (`interfaces/ui/**.md`) on the site (recommended, since they are the
  living WHAT documents for the component library), or keep v1 to root +
  `docs/` + stage contracts.
