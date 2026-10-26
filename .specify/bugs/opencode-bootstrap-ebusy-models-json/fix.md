# Bug Fix: drop the single-file models.json bind mount (opencode bootstrap EBUSY)

- **Slug**: opencode-bootstrap-ebusy-models-json
- **Fixed**: 2026-10-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Removed the single-file, read-only bind mount of the host's
`models.json` from both the machine-local `docker-compose.override.yml` and
the tracked `docker-compose.override.example.yml` (cause-gate ruling: "drop
the models.json mount"). The mounted path was a 9p mount point inside the
container, so opencode's bootstrap cache refresh (fetch models.dev → write
tmp → atomic rename onto `/root/.cache/opencode/models.json`) failed EBUSY
deterministically and killed every coding attempt. The auth.json single-file
ro mount stays (opencode only reads it); the worker now fetches models.dev
itself into its own writable layer.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `docker-compose.override.yml` | modified | dropped the models.json mount line; comment records why it must never come back (EBUSY mechanism + bug slug) |
| `docker-compose.override.example.yml` | modified | dropped the documented models.json mount; comment warns future copiers with the reason; auth.json sharing unchanged |
| `tests/test_compose_opencode_cache_mount.py` | added (qa-happy) | happy-path regression over the real compose files |
| `tests/test_compose_opencode_cache_mount_chaos.py` | added (qa-chaos) | adversarial checker variants (Windows colon host paths, mode suffixes, long syntax, comments, auth.json non-flagging, absent local override) |

## Diff Highlights (optional)

The functional change is two deleted lines; the rest is comment guidance:

```yaml
# removed from docker-compose.override.yml:
- C:/Users/start/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro
# removed from docker-compose.override.example.yml:
- ~/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro
```

## Tests Added or Updated

- `tests/test_compose_opencode_cache_mount.py::test_example_override_does_not_mount_opencode_models_json` — the tracked example must not mount `/root/.cache/opencode/models.json`
- `tests/test_compose_opencode_cache_mount.py::test_local_override_does_not_mount_opencode_models_json` — same for the machine-local override when present (skips if absent)
- `tests/test_compose_opencode_cache_mount.py::test_parser_flags_active_mounts_but_not_comments_or_auth_json` — parser self-check
- `tests/test_compose_opencode_cache_mount_chaos.py` (18 tests) — checker robustness across short/long compose syntax, access modes, Windows colon host paths; no false positives on auth.json / directory mounts / comments; RED drivers over both real files

## Local Verification

- RED verified by bug lead before the fix: 4 real-file tests failed, each citing the exact offending mount line.
- Commands run after the fix:
  - `.venv\Scripts\python.exe -m pytest tests/test_compose_opencode_cache_mount.py tests/test_compose_opencode_cache_mount_chaos.py -q` → 23 passed (GREEN)
  - `ruff check` / `ruff format` on both test files → clean
  - `docker compose config --quiet` → OK (both override files still parse)
- mypy: not applicable — `[tool.mypy] files = ["src"]` and no `src/` file changed.
- Live container verification (mount gone, rename succeeds) is the bug-test step's job; the compose stack must be recreated for the mount change to take effect.

## Deviations from Assessment

The assessment's *Preferred* remediation was the shared-host-dir rw mount;
the cause gate ruled the "drop the models.json mount" alternative instead.
That is the applied shape — not a deviation from the assessed cause, only
the selection among the assessment's listed alternatives.

## Follow-ups

- Recreate the worker (`docker compose up -d worker`) so the running stack picks up the removed mount; then re-verify the rename probe inside the container.
- Optional (separate bug/rule, not this fix): fail bootstrap-class harness errors loud (distinct infra-misconfig verdict) so a config-level cell-killer never reads as 15 silent model-zero attempts.
- Round 017 pre-flight rerun is the orchestrator's call.
