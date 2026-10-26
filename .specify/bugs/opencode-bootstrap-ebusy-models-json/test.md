# Bug Verification: opencode bootstrap EBUSY on models.json (single-file mount)

- **Slug**: opencode-bootstrap-ebusy-models-json
- **Tested**: 2026-10-26
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The assessed reproduction (rename onto `/root/.cache/opencode/models.json` failing
EBUSY because the path was a 9p mount point) no longer reproduces in the
recreated worker container; all 23 regression tests pass (4 of them were
verified RED pre-fix), the compose-adjacent suites pass, and no regressions
were found.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | `docker compose up -d worker` (recreate), then `mount \| grep opencode` + rename probe inside the container | pass | mount table lists only auth.json; `mv models.json.tmp -> models.json` succeeds (content swaps, no "Device or resource busy"); probe artifacts removed afterwards |
| Harness binary sanity | `docker compose exec worker opencode --version` | pass | 1.18.4 (pinned) |
| New / updated tests (pre-fix RED) | `.venv\Scripts\python.exe -m pytest tests/test_compose_opencode_cache_mount.py tests/test_compose_opencode_cache_mount_chaos.py -q` | pass | 23 passed; the 4 real-file drivers were verified RED by the bug lead before the fix, citing the exact mount lines |
| Regression suite (compose-adjacent) | same command + `tests/test_scan_configpaths.py tests/test_scan_ss3_config_infra.py` | pass | 50 passed |
| Compose parse | `docker compose config --quiet` | pass | both override files valid post-edit |
| Lint / format | `ruff check` + `ruff format --check` on the two test files | pass | happy file reformatted once, then clean |
| Type-check | mypy | not-run | `[tool.mypy] files = ["src"]`; no `src/` file changed |
| Live end-to-end coding attempt | real `opencode run` in the worker | skipped | token-spending `live` tier; mechanism-level reproduction above was exercised instead; the orchestrator's pre-flight rerun is the end-to-end confirmation |

## Output Excerpts

Pre-fix RED (bug lead run, 4 failures):

```
FAILED tests/test_compose_opencode_cache_mount.py::test_example_override_does_not_mount_opencode_models_json
FAILED tests/test_compose_opencode_cache_mount.py::test_local_override_does_not_mount_opencode_models_json
FAILED tests/test_compose_opencode_cache_mount_chaos.py::test_example_override_has_no_active_single_file_models_json_mount
FAILED tests/test_compose_opencode_cache_mount_chaos.py::test_machine_local_override_has_no_active_single_file_models_json_mount
  found: ['- C:/Users/start/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro']
```

Post-fix, inside the recreated worker:

```
--- mounts matching opencode:
C:\ on /root/.local/share/opencode/auth.json type 9p (ro,...)   # models.json gone
--- rename probe:
fresh                       # rename succeeded; pre-fix this was "Device or resource busy"
--- opencode:
1.18.4
```

Post-fix tests: `50 passed` across the two new files and the two
compose-adjacent suites.

## Residual Risks

- The worker's models.dev cache now lives in the container's writable layer:
  each freshly recreated container pays one ~5 s models.dev fetch on first
  opencode bootstrap (accepted by the cause-gate ruling; egress proven working).
- Any future contributor re-adding a single-file models.json mount (e.g. to
  "share" the cache) reintroduces the exact EBUSY failure; the two regression
  test files guard the example doc and the local override against precisely
  that shape.
- End-to-end confirmation on a real paid run belongs to the round-017 pre-flight
  rerun (orchestrator's call); this verification covers the mechanism, the
  config, and the regression net.

## Recommendation

Close the bug — verified. The assessed cause (single-file read-only mount made
the rename target a mount point) is removed from both the live override and
the documented example, the symptom no longer reproduces in the recreated
worker, and the regression net is in the default pytest tier.
