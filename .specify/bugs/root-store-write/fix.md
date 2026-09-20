# Bug Fix: graph store roots itself at the process CWD

- **Slug**: root-store-write
- **Fixed**: 2026-09-20
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Implemented the cause-gate ruling exactly: `default_root()` and `GraphStore.__init__` now refuse every relative root input with a `ValueError` naming the variable (Windows drive-relative shapes included), and the no-env default anchors to the enclosing checkout (`.git` dir or file, worktree-aware) and materializes under `<tempdir>/sdlc/graph_store/<sha256(anchor)[:16]>/` — outside any repo, the anchor is the resolved CWD. One checkout resolves one root from every CWD; two checkouts never share a store.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `src/sdlc/graph/store.py` | modified | `_absolute_env` (refusal, names the var), `_checkout_anchor` (stdlib-local walk-up — purity pin respected; twin of `memoization/cache.py`, not an import), `_anchored_root` (temp-digest namespace); `default_root()` rewritten (absolute envs verbatim / sibling rule unchanged; relative refused; anchored default replaces `./runs` fallback); `GraphStore.__init__` refuses relative `root=`; module docstring root clause |
| `tests/conftest.py` | modified | Ruling item 6: the `SDLC_GRAPH_STORE` pin no longer `setdefault` — a pre-exported non-absolute value is overridden, so a shell-exported relative root can never re-create the CWD litter inside test runs |
| `tests/test_graph_start.py` | modified | `test_a_store_failure_never_blocks_the_start` passed `_Broken("x")` — an incidental relative root now refused at construction; switched to absolute `tmp_path / "g"`. Intent unchanged (store failure never blocks the start); still exercises the guarded `put` |
| `tests/graph/test_graph_store.py` | modified | Added `test_the_unset_default_is_checkout_anchored_under_the_graph_store_namespace` — pins the ruled LOCATION shape (temp `sdlc/graph_store` namespace, digest computed in-test the same way; deterministic on any machine). Refusal edges deliberately not duplicated (chaos file owns them) |
| `.specify/specs/001-canonical-stage-graph-sha/contracts/records-and-store.md` | modified | Root-anchoring clause added to Store files (the compatibility contract for root resolution) |
| `docs/superpowers/specs/2026-09-17-graph-queries-design.md` | modified | Dated erratum on §6.1 F7 (line 257): CWD-shared anchoring superseded by fail-closed + checkout-anchored; pointer to the bug dir and contract |
| `.env.example` | modified | Ruling item 5: `SDLC_GRAPH_STORE` documented (must be absolute; refusal and default-anchoring behavior stated) |

RED regression files (committed in this chain, unchanged by the fix): `tests/graph/test_graph_store_root.py` (adopted per ruling, commit 386941d) and `tests/graph/test_graph_store_root_chaos.py` (qa-chaos, commit 6ba51ab; findings 732b3df).

## Diff Highlights

```python
def default_root() -> Path:
    if os.environ.get("SDLC_GRAPH_STORE"):
        return _absolute_env("SDLC_GRAPH_STORE")
    if os.environ.get("SDLC_ARTIFACT_ROOT"):
        return (_absolute_env("SDLC_ARTIFACT_ROOT").parent / "graphs").resolve()
    if os.environ.get("SDLC_EXPORT_ROOT"):
        return (_absolute_env("SDLC_EXPORT_ROOT").parent / "graphs").resolve()
    return _anchored_root()


def _anchored_root() -> Path:
    digest = hashlib.sha256(str(_checkout_anchor()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "sdlc" / "graph_store" / digest
```

## Tests Added or Updated

- `tests/graph/test_graph_store_root.py` (qa-happy, adopted) — 6 RED turned green: one root per checkout from every CWD (incl. this linked worktree), two runs one store, agree-or-refuse on relative envs; 4 guards stayed green (env hatch, absolute sibling derivation, DD10-style rerun).
- `tests/graph/test_graph_store_root_chaos.py` (qa-chaos) — 17 RED turned green: loud refusal naming the var (env + ctor + drive-relative + `.`, `..`, `./graphs`), blank-as-unset, no CWD-child litter (respawn + squatter), cross-PROCESS convergence (real subprocesses), non-repo digest namespacing; 2 hermeticity guards stayed green.
- `tests/graph/test_graph_store.py::test_the_unset_default_is_checkout_anchored_under_the_graph_store_namespace` — the ruled location shape.
- `tests/test_graph_start.py::test_a_store_failure_never_blocks_the_start` — incidental relative root made absolute; intent preserved.

## Local Verification

- RED (pre-fix, lead-verified): `pytest tests\graph\test_graph_store_root.py tests\graph\test_graph_store_root_chaos.py -q --tb=no` → 23 failed, 6 passed (matches both seats' independent reports); `pytest tests\graph\test_graph_store.py -q` → 12 passed.
- Post-fix: `pytest tests\graph\ tests\test_graph_start.py -q` → exit=0; consumers (`test_dashboard_run_graph_routes.py`, `test_dashboard_graph_state_wire.py`, `test_artifact_store.py`) → exit=0.
- Full fast tier: `pytest -q --tb=no` → exit=0 (100%).
- Static gates (uv run --frozen): `ruff check .` exit=0; `ruff format --check .` exit=0 (1424 files); `mypy` exit=0 (375 files, no issues); `scripts/check_file_size.py` exit=0.

## Deviations from Assessment

None from the assessed preferred remediation. Scope additions are all explicitly ruled items (`.env.example` documentation, conftest hardening — ruling items 5 and 6). One test update beyond the assessment's file list (`tests/test_graph_start.py`): its `_Broken("x")` construction violated the ruled refusal; fixed to absolute without changing what it tests. No Temporal tier needed (pure filesystem surface, per brief rule 3).

## Follow-ups

- The sibling readers (`observability/activities.py`, `artifacts/store.py`, `benchmarks/evidence.py`) still anchor their own `./runs` defaults at the CWD — same pattern, different symptom, deliberately untouched (out of ruled scope). Worth a card if it bites.
- `docs/superpowers/plans/2026-09-17-graph-queries.md` embeds the old default_root source verbatim (historical plan record; exempt from updating — no erratum needed beyond the design spec).
