# Bug Assessment: opencode bootstrap EBUSY on models.json — every code attempt dies on a worker with the override's single-file cache mount

- **Slug**: opencode-bootstrap-ebusy-models-json
- **Created**: 2026-10-26
- **Source**: pasted text (orchestrator card `.workspace/tasks/2026-10-26-opencode-bootstrap-ebusy-models-json.md`, run `bench-todo-api-greenfield-1793006961`, pin `b23f2514`)
- **Verdict**: valid (mechanism reproduced live in the running worker container)
- **Severity**: high (whole paid benchmark cells die reading as model zeros; propagates to every machine via the example override)

## Report (verbatim or summarized)

Card quote (worker logs):

```
Failed to fetch models.dev
cause=Cause([Fail(PlatformError: Busy: FileSystem.rename
(/root/.cache/opencode/models.json...tmp)
(cause: Error: EBUSY: resource busy or locked, rename ... ->
/root/.cache/opencode/models.json))])
```

All 15 code attempts across 5 tasks exited 1 after ~5.1 s; harness never
started; no task files authored; cell graded 0.0 ("language mismatch:
manifest=python detected=None"). Run record:
`runs/benchmarks/bench-todo-api-greenfield-1793006961/` (report.md, stages
table: code n=15, 0/15, wall 5.685 s).

## Symptom

On the round-017 pre-flight (worker image rebuilt at `b23f2514`, compose stack
force-recreated), every `opencode run` invocation died at bootstrap with
`EBUSY` renaming its models.dev cache refresh onto
`/root/.cache/opencode/models.json`, so all 15 code attempts (5 tasks × 3
Temporal activity retries) failed without the harness ever starting. Expected:
opencode bootstraps (fetch or cache-read) and authors task files.

## Reproduction

Live-reproduced in the running worker container (2026-10-26, this machine):

1. `docker compose exec worker sh -c "mount | grep opencode"` shows
   `/root/.cache/opencode/models.json` is a **9p (drvfs) read-only mount
   point** — the host file bind-mounted as a single file:
   `C:\ on /root/.cache/opencode/models.json type 9p (ro,...)`.
2. The exact syscall opencode's bootstrap performs:
   `echo probe > /root/.cache/opencode/models.json.probe.tmp && mv
   /root/.cache/opencode/models.json.probe.tmp /root/.cache/opencode/models.json`
   → **`mv: cannot move ... Device or resource busy`** (EBUSY), deterministically.

Config source of the mount: `docker-compose.override.yml:20` (machine-local)
and `docker-compose.override.example.yml:18` (the documented, product-facing
copy):

```yaml
- C:/Users/start/.cache/opencode/models.json:/root/.cache/opencode/models.json:ro
```

## Suspected Code Paths

Not a source defect. The failing code is opencode's own bootstrap cache write
(fetch models.dev → write `<path>...tmp` → atomic `rename` onto models.json),
and the configuration that turns it into a deterministic failure:

- `docker-compose.override.yml:20` — single-file, read-only bind mount of the
  host's models.json onto exactly the rename target. The mounted path is a
  mount point; `rename(2)` onto a mount point returns EBUSY, always.
- `docker-compose.override.example.yml:18` — documents the same broken shape
  for every machine ("share the result read-only ... without clobbering host
  state" — the comment's intent is fine for auth.json, which opencode only
  reads; models.json is a file opencode must be able to REPLACE).
- `Dockerfile:15` — installs `opencode-ai@1.18.4`; no cache pre-warm
  (irrelevant while the runtime mount shadows the path, see below).
- `src/sdlc/harness/base.py:231` (`CodingHarness.run`) — single exec, no
  adapter-level retry; exit 1 propagates as a failed attempt.
- `src/sdlc/stages/code/step.py:63-66` (`ACT`, `RetryPolicy(maximum_attempts=3)`)
  — the 15 = 5 tasks × 3 activity retries; each retry re-hit the same
  deterministic failure (~5 s each ≈ the models.dev fetch, which SUCCEEDS —
  only the cache write fails).

## Root Cause Hypothesis

The machine-local compose override (and the example that propagates it)
bind-mounts the host's `models.json` as a **single file, read-only**, at
exactly `/root/.cache/opencode/models.json`. A single-file bind mount makes
that path a mount point inside the container, so opencode's bootstrap cache
refresh — fetch models.dev, write a sibling tmp file, then atomically `rename`
it onto models.json — deterministically fails with EBUSY ("Device or resource
busy"), killing the process at startup. This is NOT the concurrency race the
card suspected: 15/15 attempts failed, including Temporal retries spaced
seconds apart — under a race, the first winner's write would unblock every
later attempt; under a mount-point target, nobody can ever win. The trigger
for "why now": the mounted host copy's staleness decides whether container
bootstrap attempts a refresh at all — a fresh host copy is read as-is (rounds
since R0 worked), a stale one demands a write and dies. The "freshly
recreated container" framing is coincidental; a fresh recreate merely pairs
with a stale-by-then host cache. Confidence: HIGH on the mechanism (reproduced
live); MEDIUM on the host-staleness trigger detail (host file's current mtime
is post-run; its state at run time is inferred).

Why each candidate fix shape from the card fails against this cause:

- **Serialize the bootstrap fetch per container** — assumes a race; there is
  none. No effect.
- **Pre-warm `/root/.cache/opencode/models.json` in the worker image** — the
  runtime bind mount shadows the image-baked file; opencode still sees the
  stale mounted copy and still cannot rename onto it. No effect.
- **Retry-on-EBUSY in the harness adapter** — retries a deterministic
  failure; Temporal's RetryPolicy already proved this (3×/task, 15/15 dead).
  Burns the cell slightly more slowly.

## Proposed Remediation

**Preferred**: fix the mount shape — the cache must be a regular file inside a
writable directory (so the atomic rename targets a file, not a mount point):

1. `docker-compose.override.yml`: replace the single-file line with a
   directory-level mount of the host cache dir, read-write:
   `C:/Users/start/.cache/opencode:/root/.cache/opencode:rw`. Rename then
   lands on a regular file; host and container share one live cache; a stale
   cache refreshes in place.
2. `docker-compose.override.example.yml:18`: same correction with the "why"
   (single-file mounts make the path a mount point; opencode REPLACES
   models.json via rename; auth.json stays single-file `:ro` — opencode only
   reads it, and R0 proved that mount works).

**Alternatives**:

- Dedicated cache dir (`<host-dir>:/root/.cache/opencode:rw` where the host
  dir is NOT the live host cache): cleanest isolation — no host plugin/package
  state (`~/.cache/opencode/bin`, `packages/`) leaks into the container, and
  the cache survives container recreates. Cost: one extra host path to create.
- Drop the models.json mount entirely (keep auth.json only): the worker
  fetches models.dev itself on first bootstrap (egress demonstrably works —
  today's fetch succeeded, only the write failed) and caches in its writable
  layer. Cost: one ~5 s bootstrap per container recreate; no host sharing.

**Files likely to change**:

- `docker-compose.override.yml` (machine-local, gitignored — the live defect)
- `docker-compose.override.example.yml` (the documented shape)

**Tests to add or update**:

- A compose-lint regression test: parse `docker-compose.override.example.yml`
  (and `docker-compose.override.yml` when present) and FAIL on any single-file
  mount whose container path is a file opencode replaces by rename
  (`/root/.cache/opencode/models.json`). Locks the shape in regardless of
  which mount alternative is chosen.

## Risks & Considerations

- Directory-level rw mount shares the host's `~/.cache/opencode/bin` and
  `packages/` (host plugin cache) with the container; mitigated by the
  adapter's `--pure` flag (skips external plugins, verified in
  `src/sdlc/harness/opencode.py:45`), but it is a behavior delta — the
  dedicated-dir alternative avoids it.
- rw mount means the container can now write host cache state (that is the
  point); auth.json stays read-only.
- No source-code change intended; if the orchestrator also wants
  bootstrap-class failures to fail loud (distinct "infra misconfig" verdict
  instead of 15 silent model-zero attempts), that is a separate follow-up —
  the run's instruments already localized this one correctly.
- The fix is ops-config + docs; a worker image rebuild is NOT required for the
  mount fix (compose recreates the mount), but the stack must be recreated
  for it to take effect.

## Open Questions

- [NEEDS CLARIFICATION: which alternative does the orchestrator rule — shared
  host dir rw, dedicated dir rw, or drop the models.json mount? The cause gate
  owns this call; assessment recommends shared-dir rw as minimal change.]
- [NEEDS CLARIFICATION: is cross-recreate cache persistence wanted (favors
  directory mounts) or is a 5 s per-recreate bootstrap acceptable (favors
  dropping the mount)?]
