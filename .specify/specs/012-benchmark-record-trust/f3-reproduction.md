# F3 reproduction (T014, FR-010)

Subject: the audited empty-tree result — run
`bench-cat-cafe-monitoring-1791216395` aborted in research/clarify (3
records, no code stage), yet its oracle record claims **6/12 passed**
(quality 0.5), identical to the score of `bench-cat-cafe-monitoring-1791206153`
— a full implementation graded 20 minutes earlier (16:06 vs 16:25 on
2026-10-05) — while its own record carries
`language mismatch: manifest=python detected=None` (the graded tree held
no detectable toolchain).

Verdict: **not reproduced, tried: the direct sequence plus every
environment seam; the residue hypothesis below explains it but can no
longer be demonstrated** (the suspect state was pruned by a venv re-sync
the day after the runs). No cause outside the oracle's environment was
found — SG-4 does not apply; FR-011/FR-012 (isolation) land regardless,
per the spec.

## What was checked, and the evidence

### (1) Stored records (read in place)

Every cat-cafe oracle record, runs/benchmarks → the two rows above; the
aborted run's neighbours: `1791120640/56/96`, `1791137991/8008`,
`1791140013`, `1791203917` (aborted, detected=None, **0/12**) and
`1791216395` (aborted, detected=None, **6/12**). The empty-tree 6/12 is
unique among the detected=None grades — the others all scored 0/12.

### (2) The scratch repository (host D:/own/sdlc-scratch-repos, the case's
repo_url /srv/scratch-repos/cat-cafe-monitoring)

- `sdlc/bench-cat-cafe-monitoring-1791216395/…/integration` = `b1e11d1
  "init"`, **0 files** — the graded branch was genuinely the empty init
  tree. Wrong-branch-graded and polluted-base are refuted: `main` is the
  same `b1e11d1` init commit with 0 files, and the run's branch points
  at exactly it.
- `sdlc/bench-cat-cafe-monitoring-1791206153/…/integration` = the full
  implementation (app.py, detection.py, simulator.py, state.py, risk.py,
  dashboard.py, pyproject.toml, tests/, .github/workflows/ci.yml).
- Run-id collision: refuted — every run's branch namespace exists and
  holds that run's own content.

### (3) The worker environment (kroker-dev, this tree bound at /app)

- site-packages scan: `__editable__.kroker-0.0.1.pth` (→ /app/src),
  `_virtualenv.pth`, `a1_coverage.pth`. **No `app`/cat-cafe package, no
  .pth pointing at a worktree path.**
- No `PYTHONPATH` in the container env, docker-compose.yml, the
  Dockerfile or the override example.
- The venv volume (`kroker-verify-venv`) was last re-synced
  **2026-10-06 22:47** (the kroker editable install of this round's
  binding) — one day AFTER the runs. An `uv sync` prunes foreign
  packages, so anything installed into the worker venv on 2026-10-05
  would have been removed then, leaving no artifact. Packages dated
  2026-10-05 19:18 (google/opentelemetry) prove ad-hoc installs into
  this venv were happening around the run dates.

### (4) The direct reproduction (in the container, one process)

No `/srv/scratch-repos` bind exists in this container (docker-compose
override absent; only /app, /app/runs and the venv volume are mounted —
flagged to the orchestrator). The scratch repository was copied in with
`docker cp` to /tmp/scratch (original untouched; worktree metadata
pruned afterwards) and the F3 sequence run with the base `grade_oracle`,
one process, the parent's exact OracleInput shape:

- grade `…1791206153/…/integration` (passing tree): **6/12**, detected
  python — matching that run's stored record.
- then grade `…1791216395/…/integration` (the empty init tree):
  **0/12**, detected None — the correct zero. **The empty-tree 6/12 does
  not reproduce in today's environment.**

## Conclusion

The oracle at base runs the case's tests with `env=None` whenever
`detect(worktree)` finds no toolchain marker — which an empty tree never
has — so the tests execute against the WORKER'S interpreter, whose
sys.path includes the worker venv's site-packages. The oracle's
conftest inserts the (empty) worktree root and does `import app`;
nothing in today's venv satisfies that import, but on 2026-10-05
something did — the only 6-of-12 match being the prior run's own
implementation score makes an `app`-shaped residue in the worker venv
the consistent explanation, and the 2026-10-06 venv re-sync is exactly
the kind of event that erases it. That is R-6's hypothesis (i): a
harness-side `pip install` landing in the worker interpreter (every
`_ensure_python_env` call pins its own venv, but any unpinned install —
manual or stray — lands in /app/.venv). It cannot be proven now; the
state is gone.

Not reproduced, tried: scratch-repo branch/content verification (empty
branch confirmed), base-branch pollution check, run-id collision check,
site-packages scan, PYTHONPATH audit, and the pass-then-empty grade in
one process (empty scored a correct 0/12). Nothing outside the oracle's
environment caused it; T015's empty-diff guard and T016's per-grade
environment (env allowlist + own venv, `detect` irrelevant) close the
channel either way.
