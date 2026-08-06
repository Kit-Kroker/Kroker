# Repository Triage — Hygiene Signals and `RepoTriage` Contracts — Design

| | |
|---|---|
| Date | 2026-08-06 |
| Work items | **E-41** (partial — contracts, seam, three signals), closes the `RepoTriage` half **E-40** deferred |
| Requirements | FR-901, FR-902, FR-915; extends FR-108/ADR-15; first caller of FR-914's commit byte-source |
| Scope input | `PRD.md` §FR-900; `ROADMAP.md` §10, §15 item 2; `docs/superpowers/specs/2026-07-25-brownfield-assessment-and-outcome-measurement-design.md` |
| Status | Approved design, not yet implemented |

Tier 0 answers the question that comes before the audit — *what state is this
repository in?* — deterministically and cheaply. This increment builds the
contracts, the signal seam, and three signals end to end. `TriageWorkflow` and
the readiness gate are E-42; fix runs are E-44.

---

## 1. What exists today

Nothing triage-related: `grep -ri triage src/ tests/ config/` returns no matches.
Four pieces this design builds on already exist and are load-bearing:

- **`measurement.py` (E-40)** — `Measurement` / `CollectionState`, with a model
  validator that makes `Measurement(NOT_COLLECTED, value=0.0)` unconstructable.
  Its own docstring anticipates this increment: *"E-41 reuses this type without
  inheriting `measure_coverage`'s guard."*
- **`grounding.py` (E-43)** — `verify_quote` / `quote_violation` with the
  `VERBATIM_BYTES` profile, which is the correct profile for committed code.
- **`activities.py:818 read_committed_bytes`** — E-43's third byte-source,
  *"tested, registered, no caller until E-41"* (`ROADMAP.md:209`). This design is
  that caller.
- **`toolchain/adapters.py` (E-30/ADR-15)** — marker-file resolution, pure
  adapters that produce command strings and never run a subprocess.

Two structural conventions are followed rather than re-litigated: `deploy/`
demonstrates a subpackage owning its own `activities.py`, and `measurement.py` /
`grounding.py` demonstrate a pure contract module that imports neither
`models.py` nor `temporalio`.

## 2. Decisions

Recorded with alternatives, because each was a real fork.

### D1 — Scope: contracts + seam + three signals, not seven

FR-902 names seven signal families. Building all seven produces one spec with
seven heterogeneous design questions inside it (*what counts as dead code? which
dependency-vulnerability source is authoritative?*), each of which wants its own
discussion. The three chosen here are the ones that are highest-yield and least
ambiguous: the build/run probe (it is the readiness verdict's load-bearing
input), the secret scan (the highest-yield vibe-code finding), and baseline
practice (pure static, feeds two readiness dimensions).

The remaining four become **E-41a** dependency health, **E-41b** dead and
generator-scaffold code, **E-41c** framework-default misconfiguration, **E-41d**
size and duplication outliers — sub-numbered exactly as E-30a/b/c are, each the
N-th signal behind the same seam.

*Rejected:* contracts-only with zero signals. E-40 deferred `RepoTriage` into
E-41 precisely because the signals are what determine the contracts' shape;
designing them against no consumer repeats that mistake one level down.

### D2 — The build probe executes the repository's own code

`install_cmd` runs arbitrary code — `postinstall` hooks, `setup.py`, build
scripts — as the worker user, with network access, and FR-703's egress policy is
tool-level so it does not see a socket opened from inside that call.

We execute anyway. The trust boundary is the operator's authorization, which is
the premise `ROADMAP.md:1105` already rests §10's ordering on: Tier 0 *"needs
neither tenancy nor containment because it can be operator-run"*. The
alternative — static-only, `buildable: not_collected("execution deferred")` —
is honest under FR-915 but leaves the readiness verdict that FR-903 gates Tier 2
on missing its single most load-bearing input, making every triaged repository
identical on the dimension that matters most.

**This is recorded debt, not a solved problem.** E-57 (untrusted-input threat
model) and E-21 (container / restricted-OS-user tier) are what remove it, and
until they land, triage must not be offered self-serve. NFR-9 already says the
factory assumes repositories are its own; this increment is the first stage that
knowingly violates that assumption, so the spec names it rather than letting it
arrive silently.

*Rejected:* an `--execute` opt-in flag defaulting to static. Two readiness code
paths, both needing tests and both needing to stay honest, to defer a decision
the operator-run premise already answers.

### D3 — One activity per signal

Matches `security_scan` / `run_lint` / `measure_coverage`. The reason is not
symmetry: a signal that crashes or times out must yield `not_collected` **for
itself alone** while every other signal still reports. Inside one shared
activity that isolation has to be hand-rolled with per-signal `try/except`
within a single retry boundary — reimplementing, worse, what Temporal gives for
free.

The cost is accepted deliberately: each filesystem signal enumerates the tree
separately. A shared `RepoSnapshot` collected once would avoid it, at the price
of a snapshot contract that must anticipate what four unwritten signals
(E-41a–d) will need. Premature; revisit when a signal is actually slow.

### D4 — Readiness is three-valued, and unmeasured is never `READY`

Any non-`MEASURED` dimension forces `INDETERMINATE`. A boolean verdict collapsing
`not_collected` to not-ready would conflate *"we measured this repository and it
does not build"* with *"we could not tell"* — the exact conflation E-40 spent an
increment removing from `SecurityReport`, reintroduced one tier up. The shape
mirrors `security_scan_collected` + `security_no_critical`, and the stance
mirrors FR-1108's `inconclusive`: insufficient data never reads as favourable.

`INDETERMINATE` does not open the FR-903 gate. An operator may still override
through the standard FR-301/302 machinery, which is an audited decision rather
than a silent pass.

### D5 — Findings cite `path@commit_sha`, verified through `grounding.py`

Triage is pinned at a commit (FR-901). Every `TriageFinding.evidence` is a quote
from that commit's bytes, verifiable with `verify_quote(..., VERBATIM_BYTES)`
against `read_committed_bytes`.

**What this buys, stated precisely.** The three signals here are deterministic,
so their quotes verify by construction — the verifier is a **drift guard** (the
citation still resolves at that path, at that sha, with that content), not a
hallucination guard. It becomes load-bearing when E-48's LLM proposers cite the
same way. Claiming more would be the kind of self-satisfying check FR-918 exists
to eliminate. It does, however, give FR-914's commit byte-source its first
caller, which is what `ROADMAP.md:209` records as the condition for closing it.

### D6 — Secrets are enumerated from the tracked tree, not the worktree

`git ls-tree -r <sha>` + `read_committed_bytes`, never `os.walk`. Three
consequences, all wanted: a gitignored local `.env` cannot produce a false
positive; untracked build output produces no noise; and every evidence citation
is true against `path@sha` by construction rather than by a second lookup.

### D7 — A leaked credential is `JUDGEMENT`, never `MECHANICAL`

Removing `.env` from the tree is mechanical. **Rotating the exposed key is not.**
An E-44 child run that opens a PR deleting `.env` while the credential stays live
has produced the *appearance* of remediation, which is worse than an open
finding. The finding therefore splits: `gitignore_missing_env` (MECHANICAL) and
`secret_committed` (JUDGEMENT, with rotation named in `detail`).

FR-904's `mechanically_fixable` classification is only as good as the cases it
refuses to claim.

## 3. Module layout

```
src/sdlc/triage/
  models.py       # pure: pydantic + measurement only. Contracts + compute_readiness
  registry.py     # SIGNALS: signal_id -> SignalSpec (id, version, activity name)
  activities.py   # three thin @activity.defn wrappers, registered in worker.py
  signals/
    build_probe.py
    secrets.py
    baseline.py
```

`triage/models.py` imports `pydantic` and `measurement` and nothing else — a
dependency on `models.py` or `temporalio` would show up as a reviewable import,
the same discipline `measurement.py` and `grounding.py` carry.

`activities.py` (1,034 lines) and `models.py` (1,054 lines) are not grown.

## 4. Contracts (`triage/models.py`)

```python
class FixClass(str, Enum):
    MECHANICAL = "mechanical"      # FR-904: eligible for an E-44 child run
    JUDGEMENT  = "judgement"       # needs a human decision
    STRUCTURAL = "structural"      # needs design work, not a patch


class Verdict(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    INDETERMINATE = "indeterminate"


class TriageFinding(BaseModel):
    signal: str                        # signal id, e.g. "secrets"
    rule: str                          # which rule inside it
    severity: Literal["critical", "high", "medium", "low"]
    detail: str
    path: str = ""
    line: int | None = None
    evidence: str = ""                 # verbatim quote from path@commit_sha (D5)
    fix_class: FixClass


class SignalResult(BaseModel):
    signal: str
    version: int                       # bump invalidates E-46's (tree hash, signal version) memo
    collected: Measurement             # MEASURED value = finding count
    findings: list[TriageFinding] = Field(default_factory=list)

    # NOT_COLLECTED means the signal produced nothing at all; findings alongside
    # it would be findings from a run that did not happen. Partial output is
    # UNKNOWN, which may carry what it did collect.
    @model_validator(mode="after")
    def _not_collected_has_no_findings(self) -> "SignalResult": ...


class Readiness(BaseModel):
    buildable: Measurement             # 1.0 / 0.0 when measured
    runnable: Measurement
    tests_present: Measurement         # count of discovered test files
    structure_discernible: Measurement
    verdict: Verdict


class RepoTriage(BaseModel):
    repo_dir: str
    commit_sha: str                    # triage is pinned at a commit (FR-901)
    toolchain: str | None              # None is a finding, not an error
    readiness: Readiness
    signals: list[SignalResult] = Field(default_factory=list)
```

`compute_readiness(signals: list[SignalResult], toolchain: str | None) ->
Readiness` is a pure function and the **only** producer of `Verdict`. No caller
sets it; the artifact cannot disagree with its own inputs, and E-44's re-triage
delta and E-52's bundle read one derivation rather than each re-deriving policy
(D4).

`toolchain` is a second parameter rather than being read out of the signal
results because `structure_discernible` needs both the marker resolution (which
`build_probe` performs) and the source-file inventory (which `baseline`
performs). Passing it explicitly keeps the function pure and keeps one signal
from having to reach into another's findings to reconstruct it.

## 5. FR-108 adapter extension

Four additions to `ToolchainAdapter`, all with concrete defaults so E-30a/b/c
remain unblocked:

```python
def install_cmd(self) -> str | None           # Python: pip install into an isolated venv
test_globs: tuple[str, ...]                   # Python: ("test_*.py", "*_test.py", "tests/**/*.py")
lockfiles: tuple[str, ...]                    # Python: ("uv.lock", "poetry.lock", "Pipfile.lock")
def classify_test_exit(self, code: int) -> Literal["ran", "failed_to_run", "no_tests"]
```

`classify_test_exit` carries the design weight. pytest exits `1` for *test
failures* and `2`/`3`/`4` for *collection or internal errors*; "the suite ran and
some tests failed" and "the suite could not run at all" are different readiness
facts, and the mapping is per-language. On the adapter it is one signal; inside
the signal it is Python-specific branching in the exact place ADR-15 exists to
keep language-free.

Adapters stay pure — command strings and identity only. Execution remains in
activities.

## 6. Signal 1 — `build_probe` (feeds `buildable`, `runnable`)

Resolve the toolchain by marker file. No marker resolves ⇒ `toolchain=None`,
`buildable`/`runnable` = `not_collected("no recognized marker file")`, and a
finding is recorded. An unrecognized repository is triaged, not rejected
(FR-901).

Otherwise three bounded steps through `_bounded_shell`:

| step | timeout | maps to |
|---|---|---|
| `install_cmd()` into an isolated venv | 600 s | `buildable` |
| `build_cmd()` when not `None` | 300 s | `buildable` (AND) |
| `test_cmd(coverage=False)` | 600 s | `runnable` via `classify_test_exit` |

Python has no build step (`build_cmd()` returns `None`), so `buildable` derives
from install alone there.

`maximum_attempts=1` on this activity. A ten-minute timeout retried three times
is a thirty-minute triage, and a deterministic build failure does not become a
success on attempt two. Captured output is tail-capped at 16 KB before entering
the artifact.

`classify_test_exit` returning `"no_tests"` maps `runnable` to
`not_collected("no tests to run")`, **not** to a measured `0.0`. A repository
with no test suite has not been shown to be unrunnable; it has not been tested.
The absent suite is `baseline`'s `no_tests` finding (§8), reported once, by the
signal that owns test discovery.

Findings: `install_failed`, `build_failed`, `tests_failed_to_run` (all
`JUDGEMENT` — a broken build is not mechanically fixable), `no_toolchain_marker`
(`STRUCTURAL`).

## 7. Signal 2 — `secrets`

Enumerated per D6. Two rule classes.

**(a) Committed secrets.** Provider-specific patterns — `AKIA…`,
`ghp_`/`github_pat_`, `AIza…`, `xox[baprs]-`, PEM private-key headers — at
`critical`. A generic `SECRET|TOKEN|PASSWORD|API_KEY = "…"` rule at `low`, gated
on a minimal charset-diversity and length filter; without the filter,
`password = "changeme"` floods every report and the signal stops being read. Plus
`.env` present in the tracked tree.

**(b) Client-bundle reachability** — the highest-yield vibe-code finding, and no
generic secret scanner looks for it. Build-time-inlined env prefixes
(`NEXT_PUBLIC_`, `VITE_`, `REACT_APP_`, `NUXT_PUBLIC_`, `EXPO_PUBLIC_`,
`PUBLIC_`, `GATSBY_`) whose **name** is secret-shaped (`*_SECRET*`,
`*_SERVICE_ROLE*`, `*_PRIVATE_KEY*`) are `critical`.
`NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY` is the canonical case: the value looks
like every other JWT, so only the name carries the signal.

**Stated bound:** this is reachability *by convention*, not by dataflow. We do no
taint tracking, so a secret imported into a client component from a
non-prefixed source is a false negative. Naming the false-negative surface is
what keeps the finding trustworthy — an unbounded claim about "secrets reachable
from the client" would be a claim we cannot compute.

Fix classes follow D7.

## 8. Signal 3 — `baseline` (feeds `tests_present`, `structure_discernible`)

Static checks over the tracked tree: CI configuration present
(`.github/workflows/*.y*ml`, `.gitlab-ci.yml`, `Jenkinsfile`,
`.circleci/config.yml`); `.gitignore` present and covering `.env*`; README;
lockfile (adapter-declared); test files (adapter `test_globs`); `.env.example`
when `.env` is referenced.

`baseline.py` owns `find_test_files()`; `build_probe.py` imports it. FR-902's
"exactly one implementation per signal" applies within our own code, not only
across host platforms — BrownKit's bash/PowerShell/Python triplication is the
failure mode being avoided, and a second copy of test discovery inside the probe
is the same failure at smaller scale.

`structure_discernible` is deliberately a **floor**: a toolchain marker resolved
AND ≥1 tracked source file exists. It is not a judgement about whether the
structure is *good*. E-41b's generator-scaffold detection is what sharpens it —
until then, a repository that is entirely untouched scaffolding passes this
dimension, and the spec says so rather than implying the floor is the real
measure.

Fix classes: `gitignore_missing_env` and `gitignore_missing` are `MECHANICAL`;
`no_ci`, `no_readme`, `no_lockfile` are `JUDGEMENT`; `no_tests` is `STRUCTURAL`.

## 9. Error handling

Every signal activity catches its own exceptions into
`SignalResult(collected=not_collected(reason))`. A signal never fails the
triage — that is the whole reason for D3's per-activity isolation, and it is
what lets triage complete on a repository where most signals have nothing to
work with.

Retry policy: `maximum_attempts=1` for `build_probe` (§6);
`maximum_attempts=2` for the two pure-read signals, where a transient
filesystem or git error is worth one retry.

## 10. Testing

Three fixture repositories, built into a temp directory by a helper that runs
`git init` + `git commit` so there is a genuine commit sha to pin — a static
`tests/fixtures/` directory cannot exercise D5 or D6 at all.

- `clean_python/` — builds, tests pass, CI present, `.gitignore` covers `.env`
- `vibe_repo/` — committed `.env`, a `NEXT_PUBLIC_*_SERVICE_ROLE_KEY`, no tests,
  no CI, no lockfile
- `unbuildable/` — unresolvable requirements

Test obligations:

1. Table-driven per-rule tests on each signal's pure functions.
2. `compute_readiness` truth table: every `not_collected`/`unknown` input path
   lands on `INDETERMINATE`, and no such path lands on `READY` (D4).
3. `SignalResult` validator rejects findings alongside `NOT_COLLECTED`.
4. A signal raising an unexpected exception yields `not_collected` and the other
   signals still report (D3).
5. Every `TriageFinding.evidence` emitted against a fixture verifies through
   `verify_quote(..., VERBATIM_BYTES)` against `read_committed_bytes` at the
   pinned sha (D5).
6. A gitignored-but-present local `.env` produces **no** finding, and an
   untracked file containing an `AKIA` string produces none (D6).
7. `classify_test_exit` maps pytest's 0/1/2/3/4/5 to the three outcomes.

## 11. Out of scope

E-41a dependency health · E-41b dead and generator-scaffold code · E-41c
framework-default misconfiguration · E-41d size and duplication outliers ·
`TriageWorkflow` and the readiness gate (E-42) · mechanical fix runs and the
before/after delta (E-44).

**E-41 ships no user-facing surface.** The three activities register in
`worker.py` and are exercised by tests; nothing invokes them until E-42 wires
the workflow. A `sdlc triage <path>` verb running signals outside Temporal was
considered and rejected: it is a second execution path to keep honest, for one
increment's convenience.

## 12. Roadmap consequences

On landing:

- **E-41** moves to partial — three of seven signals, with E-41a–d opened.
- **E-40** closes: its deferred `RepoTriage` half is delivered here.
- **FR-902** partial; **FR-901** gains its artifact but stays open until E-42's
  stage and gate.
- **FR-914** gains its commit-source caller (`ROADMAP.md:209`'s stated
  condition), with D5's honest scope on what that caller proves.
- **NFR-9** gains an explicit note: triage is the first stage that knowingly
  executes a foreign repository's code, and is operator-run only until E-57/E-21.
