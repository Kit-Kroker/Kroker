# Bug Assessment: graph store roots itself at the process CWD

- **Slug**: root-store-write
- **Created**: 2026-09-20
- **Source**: pasted text — TASK BRIEF `D:/own/Kroker/.workspace/tmp/root-store-write-bug-brief.md` (orchestrator-supplied)
- **Verdict**: valid — reproduced locally, 6/6 probes (see Reproduction)
- **Severity**: high — silent wrong-placement of persistent store state on every client-side run start that has no env pin; cross-CWD store splits; worktree litter. No corruption (content-addressed files verify by hash), so not critical.

## Report (verbatim, condensed)

> SYMPTOM: the graph store silently roots itself at wherever the process happens to start. Store content (graphs, registry snapshots, run pointers) lands in random directories and two runs from different CWDs silently get two different stores.

Evidence named in the brief (treated as data, re-verified locally):

- memo-cache-root session (worktree `D:/own/Kroker-bug`, 4 seats): untracked `x/registry/<64-hex>.json` appeared and RESPAWNED twice after deletion — a concurrent seat writing registry snapshots into it (also noted by qa-chaos, `.specify/bugs/memo-cache-root/chaos-qa-findings.md:13`, and assessment.md:89 "cleanup or ignore").
- E-77 run T043 (2026-09-19/20): store wrote a registry snapshot to relative `x/` — first documented occurrence (tasks.md:229 records the T043 runs; the `x/` observation is carried by the brief).
- `default_root()` `src/sdlc/graph/store.py:54-61` and `GraphStore.__init__` `store.py:191-192` resolve relative inputs against CWD.

## Symptom

Every relative root input — `SDLC_GRAPH_STORE`, `SDLC_ARTIFACT_ROOT`, `SDLC_EXPORT_ROOT`, the `./runs` fallback, and an explicit relative `root=` — resolves against the process CWD, so the store silently lands at `<wherever-the-process-started>/...`. Expected: a run's store writes land at one stable, CWD-independent location per checkout, and unstable (relative) root inputs are refused loudly rather than silently honored.

## Reproduction (local, 2026-09-20; probe script + output)

Probe: `C:\Users\start\AppData\Local\Temp\opencode\rootstore-repro.py`, run via `uv run --frozen python` against this worktree. Writes only under `%TEMP%\opencode\rootstore-repro\{A,B}`. Result: **DEFECT_REPRODUCED**, 6/6:

1. No env, CWD=A vs CWD=B → `A\graphs` vs `B\graphs` — two different stores from the same checkout, silently. This is the headline symptom.
2. `SDLC_GRAPH_STORE=x` (relative) from CWD=A → `GraphStore().root == A\x`; `put_registry()` writes `A\x\registry\8e9ab8...414.json` — **byte-for-byte the observed artifact shape** (`x/registry/<64-hex>.json` respawning in the worktree: any later start re-materializes it; `put_registry` is per-hash idempotent, the *directory* is not guarded).
3. Same relative env from CWD=B → root `B\x`; `get_registry(A's sha)` → None — cross-CWD blindness between "the same" store.
4. `SDLC_ARTIFACT_ROOT=runs` (relative) → `A\graphs` — the derived-sibling path is equally CWD-anchored.
5. Blank env values (`""`) are falsy → skipped, fall through to `./runs` — the memo-cache blank-env scatter footgun does **not** apply here (`store.py:57-60` truthiness checks). Negative finding; pin it with a chaos test.
6. Explicit relative `root="r"` → `GraphStore("r").root == B\r` (`store.py:192`).

Provenance of the literal `x` value in the session evidence is environmental (a seat's shell/probe exporting a relative `SDLC_GRAPH_STORE` or equivalent scratch root; nothing in-repo sets it — see consumer map). Unproven and unnecessary: every relative-input path produces the observed shapes.

## Consumer map — who supplies the root (binding constraint)

**Writers of the store (prod, all bare `GraphStore()` → `default_root()`; none set any env):**
- `src/sdlc/graph/start.py:35` — the E-77 start chokepoint (`put` identity+layout, `put_registry`, `put_pointer` before `client.start_workflow`), reached from:
  - `src/sdlc/cli.py:463` — human CLI `start` (runs from wherever the human's shell is);
  - `interfaces/dashboard/api/main.py:59` — dashboard start button (uvicorn process CWD).
- `src/sdlc/dashboard/run_graph.py:79` — backfill + save/load routes (E-77 US4/US5), dashboard process CWD.

**`SDLC_GRAPH_STORE`:** set ONLY by tests — `tests/conftest.py:26` `os.environ.setdefault(..., %TEMP%/sdlc-test-graphs)` (absolute, but **pass-through**: a pre-exported relative value survives it) and `tests/graph/test_graph_store.py:89` (absolute tmp_path). NOT set by any production code, `docker-compose.yml`, `.env.example` (the var is entirely undocumented), crew, or scripts. **In prod it is always unset** → fallback chain.

**`SDLC_ARTIFACT_ROOT` / `SDLC_EXPORT_ROOT`:** set ONLY in tests, always absolute tmp_path. Prod readers: `artifacts/store.py:44-45` (LocalFileStore, default `./runs`), `observability/activities.py:28` (export activity, default `./runs`), `benchmarks/evidence.py:30,49` (`DEFAULT_EXPORT_ROOT = "./runs"`). These sibling readers share the CWD-anchoring **pattern** but are NOT the reported symptom — changing them is out of scope (drive-by).

**Explicit `root=`:** only tests, always absolute `tmp_path`. No prod caller passes `root=`.

**What the `./runs` default is FOR:** human CLI UX — artifacts land beside the checkout (`docs/superpowers/specs/2026-09-17-graph-queries-design.md:254-257`, decision **F7 "accepted"**: *"a relative default shares the anchoring of today's SDLC_ARTIFACT_ROOT/SDLC_EXPORT_ROOT"*). Docker-compose does not set the vars either; it mounts `worker-runs:/app/runs` (compose line 46) and relies on the worker container's CWD `/app` — but the worker never writes the graph store (client-side only), so the store default in Docker is moot; only the runs-dir consumers matter there. **Conclusion: the `./runs`-anchored store default has no consumer that needs CWD sensitivity; the design doc accepted it as an alias for "beside the checkout", which CWD-anchoring only approximates when the process happens to start at the checkout root — exactly what broke in multi-seat use.**

**No consumer anywhere depends on cross-checkout store sharing**, and no E-75 read path depends on a store hit (routes serve from history, spec §6.2) — the store is content-addressed and regenerable (identity/layout from graph content, registry from `NODE_TYPES`, backfill from history). The only contracted reuse is the same-checkout kind (DD10-analog: same checkout, any CWD, one store).

## Suspected Code Paths

- `src/sdlc/graph/store.py:54-61` — `default_root()`: every relative input resolves via `Path(...).resolve()` against CWD; `./runs` fallback is relative by design.
- `src/sdlc/graph/store.py:191-192` — `GraphStore.__init__`: explicit relative `root=` resolved against CWD the same way.
- `src/sdlc/graph/start.py:35,42` — the write chokepoint that turns an unstable root into actual litter (`put_registry` → `<root>/registry/<sha>.json`, the observed artifact).
- `tests/conftest.py:26` — `setdefault` guard is pass-through for a pre-set relative value (test-hygiene contributor, not a cause).

## Root Cause Hypothesis

**Confidence: high (reproduced).** `default_root()` and `GraphStore.__init__` accept arbitrary relative paths and anchor them at the process CWD (`Path.resolve()` semantics), and the production default (`./runs` fallback) is itself relative; because no production surface pins `SDLC_GRAPH_STORE` (or the artifact/export roots) to an absolute location, the effective production store root is `<CWD>/graphs` — a function of where the process happens to start, not of the checkout. This was an explicit design acceptance (spec F7) that first proved wrong in real multi-seat usage (T043; memo-cache-root session). The observed `x/registry/<sha>.json` respawn is `start.py:42 put_registry()` under any relative root value (`x` being an environmental scratch value), and the "two runs, two stores" symptom is probe 1.

## Proposed Remediation

**Preferred — fail-closed relative refusal + checkout-anchored default (the memo-cache-root precedent, `src/sdlc/memoization/cache.py`, applied to the store):**

1. `default_root()`:
   - `SDLC_GRAPH_STORE` set: absolute → use as-is (unchanged); relative → raise `ValueError` naming the var (fail-closed, per the E-77 follow-up card's direction); blank already behaves as unset (truthiness) — pin by test.
   - else `SDLC_ARTIFACT_ROOT`/`SDLC_EXPORT_ROOT` set: absolute → `<root>.parent / "graphs"` (unchanged); relative → refuse identically (store-side only; the sibling readers are out of scope).
   - else default: resolve the **checkout** by walking up from CWD to the first `.git` (dir *or* file, worktree-aware — the `memoization/cache.py` `_checkout_root` technique, re-implemented locally in stdlib because `store.py` imports are purity-pinned to stdlib + `sdlc.graph` + `sdlc.core.models` by `tests/graph/test_graph_purity.py`); store root = `%TEMP%/sdlc/graph_store/<sha256(checkout)[:16]>/`. Outside any repo: namespace by the digest of the resolved absolute CWD (hermetic, never bare CWD — memo-cache ruling pattern). The store deliberately stays **out of the checkout**: in-tree `graphs/` would re-create the respawning-untracked-directory nuisance this bug opened with, and every store file is derived/regenerable.
2. `GraphStore.__init__`: explicit relative `root=` → `ValueError` (all existing callers pass absolute tmp_path — verified). Absolute unchanged.
3. Doc duty in the same diff: `store.py` docstring root clause; erratum on spec §257 F7 (`docs/superpowers/specs/2026-09-17-graph-queries-design.md`); a root-anchoring clause in `.specify/specs/001-canonical-stage-graph-sha/contracts/records-and-store.md` (store files section).

This satisfies: DD10-analog (same checkout → one store regardless of CWD — digest is of the checkout, not the CWD); hermetic across checkouts (no uncontracted sharing); zero CWD-dependent behavior; every existing green test stays meaningful (all test roots are absolute); E-77 contracts untouched (they govern file formats/write discipline, not root resolution); docker unaffected (worker never writes the store).

**Alternatives:**
- *(a) Refuse relative everywhere, keep `./runs` fallback but resolve it against the checkout* → store at `<checkout>/graphs`: keeps the "graphs beside runs" mental model but re-introduces an untracked directory inside every worktree/checkout (the `x/` nuisance class) and needs a not-in-a-repo story anyway. Trade-off: operator-visible placement vs. tree hygiene.
- *(b) Fail-closed refusal only, default unchanged* (refuse relative env inputs, keep CWD-anchored `./runs` default): smallest diff, does NOT fix the headline symptom — the default itself is relative. **Reject as incomplete.**

**Files likely to change:** `src/sdlc/graph/store.py` (`default_root`, `__init__`, local `_checkout_root`-style helper, docstring); `tests/graph/test_graph_store.py` (extend `test_default_root_resolution`); new RED regression files (qa seats); `contracts/records-and-store.md` root clause; spec §257 erratum.

**Tests to add or update (RED first; deterministic on any machine — no dependence on the tester's CWD or pre-existing dirs; git-repo fixtures via tmp_path + `git init`):**
- happy: two different CWDs inside one tmp git checkout → identical `default_root()` (DD10-analog core).
- happy: the start chokepoint still writes identity+layout+registry+pointer at the anchored root (E-77 contract restated under the new policy).
- chaos: relative `SDLC_GRAPH_STORE=x` → loud refusal; **no directory materializes as a direct child of CWD** (the litter edge, both directions like memo-cache).
- chaos: relative `SDLC_ARTIFACT_ROOT`/`SDLC_EXPORT_ROOT` refused for store derivation; blank values remain "unset" semantics (never `Path("") == "."`).
- chaos: explicit relative `root=` refused; absolute `tmp_path` roots unchanged (suite stays green).
- chaos: outside any git repo → absolute, digest-namespaced, no bare-CWD anchoring, no CWD-child litter.
- chaos: two different checkouts → two different stores (hermeticity).

## Risks & Considerations

- **Purity pin:** `store.py` module-level imports are pinned (`tests/graph/test_graph_purity.py`); the checkout walk-up must be re-implemented locally (stdlib `os`/`pathlib`), not imported from `sdlc.memoization`.
- **Behavior change for humans** who deliberately started the CLI from a scratch CWD to get `./graphs` there: the escape hatch remains `SDLC_GRAPH_STORE` (absolute). The var is currently undocumented in `.env.example` — adding it there is cheap and arguably part of the fix (open question 5).
- **Windows `Path.resolve()` quirks** (strict/non-strict, drive-relative paths like `\graphs` or `C:graphs`): the refusal rule must treat drive-relative as relative; test on Windows (this worktree is Windows).
- **`latest` and pointer mutability contracts** (`contracts/records-and-store.md`) are root-agnostic — no migration needed; an existing store at any old location simply becomes invisible under the new default (content regenerates; `latest` hints are advisory-only per E-77).
- **conftest `setdefault` pass-through** (a pre-exported relative value would survive into test runs): fail-closed refusal turns this from silent litter into a loud collection-time error — acceptable and desirable; hardening conftest is optional (open question 6).

## Open Questions (for the CAUSE GATE ruling)

1. Default location: `%TEMP%/sdlc/graph_store/<checkout-digest>/` (recommended; memo-cache precedent, no tree litter) vs `<checkout>/graphs` in-tree (alternative a; operator-visible)?
2. Explicit relative `root=`: refuse (recommended) vs checkout-anchor?
3. Relative `SDLC_ARTIFACT_ROOT`/`SDLC_EXPORT_ROOT` in the derivation: refuse for the store (recommended) vs checkout-anchor the sibling `graphs`?
4. Not-inside-a-repo fallback: digest-namespaced temp (recommended) vs hard refusal?
5. Document `SDLC_GRAPH_STORE` in `.env.example` in this fix, or leave to a docs pass?
6. Harden `tests/conftest.py:26` from `setdefault` to an absolute-value guard in the same diff?

## Environment readiness (post-clearance)

Worktree venv was missing; rebuilt via `uv sync --frozen --extra dev` (pytest 9.1.1 present; `uv.lock` untouched — `git status` clean). Static gates remain via `uv run --frozen` (ruff/mypy/check_file_size), per TASK BRIEF rule 4.
