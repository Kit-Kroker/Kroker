# Bug Verification: graph store roots itself at the process CWD

- **Slug**: root-store-write
- **Tested**: 2026-09-20
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom no longer reproduces: two CWDs of one checkout now resolve the ONE store (checkout-anchored, temp-digest namespaced), every relative root input is refused loudly with the variable named, no directory ever materializes as a CWD child, and all 23 RED regression tests are green with zero regressions in the full fast tier.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | probe `%TEMP%\opencode\rootstore-postfix.py` (assessment probes restated under the ruled expectations; writes only under temp) | pass | 12/12 PASS: one root per checkout from every CWD with the ruled location shape; cross-CWD store visibility; loud refusals naming `SDLC_GRAPH_STORE` / `SDLC_ARTIFACT_ROOT` / `SDLC_EXPORT_ROOT`; blank-as-unset; `root=` refusal; non-repo digest namespacing; zero CWD litter |
| New / updated tests | `.venv\Scripts\python.exe -m pytest tests\graph\test_graph_store_root.py tests\graph\test_graph_store_root_chaos.py tests\graph\test_graph_store.py tests\test_graph_start.py tests\graph\test_graph_start.py -q` | pass | exit=0, 51 tests — the 23 pre-fix RED (6 happy + 17 chaos, lead-verified RED pre-fix) now green; 6 green-by-design guards stayed green; location-shape pin and E-75/E-77 store contracts green; purity pin (`test_graph_purity`) green |
| Regression suite | `.venv\Scripts\python.exe -m pytest -q --tb=no` (fast tier, marker-excluded opt-in tiers per pyproject) | pass | exit=0, 100% |
| Lint / type-check | `uv run --frozen ruff check .` / `ruff format --check .` / `mypy` / `scripts/check_file_size.py` | pass | exit=0 each ("All checks passed", 1425 files formatted, 375 files no issues, size ceiling clean) |

## Output Excerpts

- Post-fix probe: `OVERALL: ALL-PASS` (all 12 checks)
- Pre-fix RED (lead-verified, same commands): 23 failed / 6 passed in the two regression files; `tests\graph\test_graph_store.py` 12 passed
- Post-fix: `regression_exit=0`, `fasttier_exit=0`, `ruff_exit=0`, `fmt_exit=0`, `mypy_exit=0`, `size_exit=0`
- Refusal shape (from the chaos file, post-fix green): `ValueError: SDLC_GRAPH_STORE must be an absolute path, got 'x': relative store roots anchor at the process CWD and are refused`

## Residual Risks

- The sibling `./runs` readers (`observability/activities.py`, `artifacts/store.py`, `benchmarks/evidence.py`) still anchor their own defaults at the CWD — same pattern, deliberately out of ruled scope; recorded as a follow-up in fix.md.
- Windows drive-letter case differences reaching the same checkout (`D:\x` vs `d:\x`) digest differently — pre-existing behavior of the memo-cache precedent's identity scheme, mirrored here for consistency, not introduced by this fix.
- Opt-in tiers (`slow`, `temporal`, `live`, `docker`, `crew`) not run: the surface is pure filesystem with no Temporal dependency (brief rule 3); no test in those tiers exercises `default_root()` (consumer map: no `SDLC_GRAPH_STORE`/`root=` suppliers outside the fast tier's tests).

## Recommendation

Close the bug — verified end-to-end: symptom does not reproduce under the ruled expectations, the full RED regression chain is green, no regressions in the fast tier or static gates, and the change stayed exactly inside the cause-gate ruling.
