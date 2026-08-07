# Repository Triage — The Remaining Four Hygiene Signals — Design

| | |
|---|---|
| Date | 2026-08-08 |
| Work items | **E-41a** dependency health, **E-41b** dead and generator-scaffold code, **E-41c** framework-default misconfiguration, **E-41d** size and duplication outliers |
| Requirements | FR-902 (completes it), FR-915; extends FR-108/ADR-15; declares a new opt-in egress under FR-703 |
| Scope input | `PRD.md` §FR-900; `ROADMAP.md` §10; `docs/superpowers/specs/2026-08-06-repository-triage-hygiene-signals-design.md` |
| Status | Approved design, not yet implemented |

E-41 built the triage contracts, the signal seam, and three of FR-902's seven
signal families. This increment builds the other four behind the same seam,
taking FR-902 from three of seven to seven of seven. It adds no workflow and no
gate — `TriageWorkflow` and the readiness gate remain **E-42**, fix runs remain
**E-44**.

---

## 1. What exists today

`src/sdlc/triage/` ships `models.py` (`RepoTriage` / `SignalResult` /
`TriageFinding` / `compute_readiness`), `registry.py` (three `SignalSpec`
entries), `activities.py` (three activities), and `signals/` with `build_probe`,
`secrets` and `baseline`. All three activities are registered in `worker.py`.

Four constraints from that increment are load-bearing here and are followed
rather than re-litigated:

- **D3 — one activity per signal.** A signal that crashes or times out yields
  `not_collected` for itself while every other signal still reports.
- **D5 — findings cite `path@commit_sha`, verified through `grounding.py`.**
- **D6 — content is read from the pinned commit through git, never from the
  working checkout.**
- **`compute_readiness` admits exactly one owner per readiness key** and raises
  on a duplicate, rather than silently preferring a producer.

Two facts about the existing reader shape this design. `triage/activities.py`'s
`read_blob()` spawns **two** git subprocesses per file — `cat-file -t` to guard
against a tree path, then `show` — and `secrets` calls it over every tracked
path. Three of the four signals designed here also need whole-tree content, so a
naive extension takes a 5,000-file repository from roughly 10,000 subprocess
spawns to roughly 40,000.

## 2. Decisions

### D9 — Four peer signals, not a shared content pass

Each new signal gets its own module, its own activity, and its own registry
entry, exactly as the first three did. The tree is therefore read once per
signal rather than once in total.

*Rejected:* two composite activities (manifest analysis, source analysis). It
halves the reads by giving up precisely what D3 bought — a hung duplication
scan would report `not_collected` for framework misconfiguration too.

*Rejected:* one reader activity streaming each blob through N pure analyzers.
Strictly one read, and per-analyzer `try/except` preserves *exception*
isolation — but a single Temporal timeout would then bound every content
signal, so a genuine hang still takes all of them down, and one activity
producing four differently-versioned results makes E-46's per-signal
`(tree hash, signal version)` memo key incoherent.

The performance argument that motivated both alternatives is answered directly
instead, by D10.

### D10 — One batched reader, replacing the per-file spawn pair

`triage/gitread.py` wraps a single long-lived `git cat-file --batch` process.
Callers feed `<commit_sha>:<path>` on stdin and read
`<oid> SP <type> SP <size> LF <contents> LF` back; a path that does not resolve
answers `<input> SP missing LF`. Reproducing `read_blob`'s guard is then free
rather than a second spawn: a directory path answers type `tree`, and both
`tree` and `missing` yield `None`, which is exactly today's semantics.

The reader carries `_git`'s `-c safe.directory=*` bypass and its
`stdin`-discipline rationale forward. Both exist for reasons that do not stop
applying because the invocation is long-lived: the ownership check fires
whenever the worker's SID differs from the worktree owner, and this process
genuinely does read stdin, so its pipe must be the one we write paths to and
nothing inherited.

`secrets` migrates onto it in the same step. One reader, not two — the same
rule FR-902 applies to signals, applied to our own helpers. Single-blob
`read_blob` survives for the genuinely single-file case (`baseline`'s
`.gitignore`).

*Rejected:* leaving `read_blob` alone and accepting 4× the spawns. The cost is
not hypothetical on Windows, where process creation is expensive, and triage's
whole claim is that Tier 0 is the *cheap* tier.

### D11 — `AdvisorySource` is a seam whose default collects nothing

Vulnerability data requires an advisory database, which means sending a client
repository's dependency list off-box. That is a trust-boundary decision, not an
implementation detail.

`triage/advisories.py` declares an `AdvisorySource` ABC with one method,
`lookup(ecosystem, packages) -> AdvisoryResult`, where `AdvisoryResult` carries
a `Measurement` beside its advisories. `NoneAdvisorySource` is the **default**
and returns `not_collected("no advisory source configured")`.
`OsvAdvisorySource` is the one reference implementation, opt-in per run, posting
to OSV's `querybatch` endpoint under a hard timeout.

Every failure path in the OSV source — timeout, non-200, malformed JSON,
unrecognised ecosystem — returns `not_collected`. **None returns an empty
advisory list.** A lookup that did not happen reading as *zero vulnerabilities*
is the malformed-SARIF hole E-40 closed on the absolute floor, and installing
the same conflation in a new signal a week later would be indefensible.

The shape mirrors `MemoryConfig.backend` defaulting to `fake` and ADR-19's
adapters-not-substrate rule. It is also a new outbound egress and is recorded
as one under FR-703: declared, opt-in, off by default.

*Rejected:* OSV always-on with no seam — one vendor baked in, and an outbound
call about a client repository on every triage run, before FR-703's
network-level tier exists. *Rejected:* dropping the rule entirely — the
contract makes "we did not look" expressible, so there is no need to pretend
the question does not exist. *Rejected:* shelling `pip-audit` / `npm audit`
through the adapter — it gets transitive resolution for free, but adds a
per-language tool install and a per-language output format to parse.

### D12 — `M_STRUCTURE` ownership moves to `scaffold`

`compute_readiness` raises when two signals report the same readiness key, so
"E-41b sharpens `structure_discernible`" cannot mean "E-41b also reports it".
Ownership moves: `scaffold` reports `M_STRUCTURE`, `baseline` drops it and bumps
to version 2.

The consequence is deliberate. A `scaffold` signal that fails now leaves
`structure_discernible` unmeasured, which forces `INDETERMINATE` — and *"we
could not tell whether this is real code or a generator's output"* is the honest
readiness verdict for that state, not a technicality.

*Rejected:* `baseline` keeps the key and consumes `scaffold`'s result. One
owner on paper, but the two signals stop being independent, and a scaffold
failure degrading baseline is exactly the coupling D3 exists to prevent.
*Rejected:* `scaffold` emits findings only and leaves the floor alone —
cheapest, but an all-scaffolding repository still passes the dimension and
E-41b's roadmap line stays half-open.

### D13 — Scaffold detection is fingerprint-first, history-corroborated

Content fingerprints decide *whether* a file is generator output; git history
decides only *how confident* the report is.

The ordering is what makes it safe. History alone misfires hardest on exactly
the repositories Tier 0 targets: a vibe-coded repo is often one enormous initial
commit, where "untouched since import" is true of every file including the
hand-written ones. As corroboration it is additive and cannot invent a finding —
a file must be fingerprinted first.

Degradation is explicit rather than silent. A repository with a single commit
yields no usable history, so the signal records `history_basis` as
`not_collected` and every severity stays at its fingerprint-only level. The
signal itself remains MEASURED: the fingerprints ran.

Reproducibility (NFR-10) holds — `git log <sha>` is deterministic given the same
repository and commit. What history does not survive is a squash or re-import,
which changes stability across *re-creations* of a repository, not
reproducibility at a pinned commit. Since history only adjusts severity, a
re-import degrades a report's sharpness, never its correctness.

### D14 — Absolute size thresholds, supplied by the adapter

Outlier thresholds are fixed per-language values on the `ToolchainAdapter`, not
percentiles of the repository's own distribution.

Tier 0 asks *what state is this repository in*, not *which file is worst here*.
A percentile rule always finds 5% of files, reports nothing on a uniformly bad
repository, and produces numbers that cannot be compared across repositories or
across E-44's before/after delta. Absolute thresholds report every oversized
file in a repository of oversized files, which is the correct reading, and make
the delta a real measurement.

### D15 — Framework rules live in signals, not on the adapter

The adapter carries language-level facts only. A Python repository may be
Django, Flask or FastAPI, so generator fingerprints and misconfiguration rules
are framework-scoped tables inside their own signal modules, with framework
detection by manifest dependency name or import. Putting them on the adapter
would force a Python adapter to know about Next.js the moment a repository
mixes stacks.

One exception widens the adapter deliberately: `function_spans(text)`, a pure
per-language parser used by the outlier signal. It runs no subprocess and
touches no filesystem, which keeps ADR-15's purity rule intact; it is the same
kind of member as `classify_test_exit` — a per-language *interpretation* rather
than a command string.

### D16 — `not_collected` applies to sub-capabilities, not only to signals

E-41 established that a failing signal reports `not_collected` for itself. This
increment introduces capabilities that can fail *inside* a signal that otherwise
succeeded: the advisory lookup, the duplication analysis when its cap is
exceeded, `oversized_function` on a language with no parser, and scaffold's
history basis.

Each reports a `not_collected` **metric** while its signal stays MEASURED. That
is not a contradiction: the signal genuinely collected — it found what it found,
and it says plainly what it could not look for. `SignalResult`'s existing
validator already blocks the coarser error (findings on a NOT_COLLECTED signal);
this is the same discipline one level down.

## 3. Module layout

```
src/sdlc/triage/
    gitread.py                  # NEW — batched cat-file reader (D10)
    advisories.py               # NEW — AdvisorySource seam + OSV reference (D11)
    activities.py               # +4 activities; secrets migrates onto gitread
    registry.py                 # +4 SignalSpec entries; baseline -> version 2
    signals/
        dependencies.py         # NEW — E-41a
        scaffold.py             # NEW — E-41b, owns M_STRUCTURE
        misconfig.py            # NEW — E-41c
        outliers.py             # NEW — E-41d
        baseline.py             # version 2: drops M_STRUCTURE and its
                                #            extension list
src/sdlc/toolchain/adapters.py  # new pure fields + function_spans
src/sdlc/worker.py              # +4 activity registrations
```

Signal modules stay pure — Pydantic, stdlib, `measurement.py`, `grounding.py`
and the adapter only. No `models.py`, no `temporalio`. Execution and git access
live in `activities.py`, as they do for the first three signals.

## 4. FR-108 adapter extension

All fields carry concrete defaults, so an adapter that has not thought about
triage degrades to *rule skipped, metric `not_collected`* rather than failing to
instantiate — the rule already established for `test_globs` and `lockfiles`.

| member | default | Python | consumer |
|---|---|---|---|
| `manifests` | `()` | `("pyproject.toml", "requirements.txt")` | dependencies |
| `ecosystem` | `None` | `"PyPI"` | dependencies → OSV |
| `source_extensions` | `()` | `(".py",)` | scaffold, outliers, misconfig |
| `max_file_loc` | `0` (disabled) | `800` | outliers |
| `max_function_loc` | `0` (disabled) | `100` | outliers |
| `min_clone_loc` | `30` | `30` | outliers |
| `function_spans(text)` | returns `None` | `ast`-based | outliers |

`baseline._SOURCE_EXTENSIONS` moves onto `source_extensions`, deleting a second
copy of the same list. `function_spans` returns `list[(name, start, end)]` or
`None` for "this language has no parser here"; `None` is what makes the
`oversized_function` metric `not_collected` rather than absent.

## 5. Signal 4 — `dependencies` (E-41a)

Reads the adapter's manifests, the tracked lockfile set, and source text for the
unused check.

| rule | severity | fix_class | trigger |
|---|---|---|---|
| `unpinned_dependency` | medium | MECHANICAL | direct dependency with no version constraint or a floating one; detail records whether a tracked lockfile mitigates |
| `duplicate_dependency` | medium | MECHANICAL | one normalized name declared in two manifests with conflicting constraints |
| `known_vulnerable` | critical / high | JUDGEMENT | advisory hit, severity from the advisory |
| `unused_dependency` | low | MECHANICAL | normalized name absent from every imported top-level module and from the declared tooling table |

`known_vulnerable` is JUDGEMENT for D7's reason: the edit is one line, but the
decision that the upgrade is safe is not, and E-44 promises a MECHANICAL finding
can be closed by a PR without judgement.

`unused_dependency` is the one rule with a real false-positive surface —
distribution names diverge from import names (`pillow` → `PIL`,
`beautifulsoup4` → `bs4`). It ships with a small declared alias table, a tooling
table for packages that are legitimately never imported (`pytest*`, `ruff`,
`mypy`, `coverage`), `low` severity, and no readiness influence. The lookup is
declared-direct-dependencies only; transitive resolution is out of scope (§10).

Metrics: `direct_dependencies` (measured), `known_vulnerable` (`not_collected`
under the default source).

## 6. Signal 5 — `scaffold` (E-41b)

**Fingerprints.** A declared table of `(generator, path glob, content marker)`:
`create-next-app`'s README body, CRA's *"Edit `src/App.js` and save to
reload."*, Vite's `index.html` title, Django's default `manage.py`. A file
matching a glob whose content still contains the marker is generator output
nobody has touched.

**History corroboration (D13).** One bounded `git log --name-only` pass builds a
path → touch-count map. A fingerprinted file whose only touch is its import
commit is reported one severity step higher, with *"untouched since import"* in
the detail. With a single-commit repository, `history_basis` is `not_collected`
and severities stay at their fingerprint-only level.

**Dead code.** `unreferenced_module` (low, JUDGEMENT): a tracked source module
that no import names, excluding entrypoint conventions — `__init__`, `__main__`,
`main`, `manage`, `conftest`, and the adapter's `test_globs`. JUDGEMENT because
deleting code is a decision, not a mechanical patch.

**`M_STRUCTURE` (the new owner, D12):**

- `not_collected` when no toolchain marker resolved — `baseline`'s current
  semantics, preserved verbatim.
- `0.0` when there is no source at all, **or** when the scaffolded share of
  source files is ≥ 0.9.
- `1.0` otherwise.

This **raises the floor, it does not remove it.** A repository that is entirely
untouched output of a generator we hold no fingerprint for still passes the
dimension, exactly as it does today. `ROADMAP.md`'s E-41b line should be
rewritten to say so rather than deleted.

## 7. Signal 6 — `misconfig` (E-41c)

Framework-scoped, file-shaped rules only. Framework detection is by manifest
dependency name or import.

| rule | severity | fix_class | trigger |
|---|---|---|---|
| `permissive_cors` | high (critical with `allow_credentials=True`) | MECHANICAL | `allow_origins=["*"]` / `CORS(app, origins="*")` |
| `debug_enabled` | high | MECHANICAL | Django `DEBUG = True`; Flask `app.run(debug=True)` |
| `allowed_hosts_wildcard` | medium | MECHANICAL | `ALLOWED_HOSTS = ["*"]` |
| `django_insecure_secret_key` | critical | JUDGEMENT | `SECRET_KEY` literal with the `django-insecure-` prefix |
| `world_readable_storage` | critical | MECHANICAL | Firebase rules with `allow read, write: if true`; an IaC policy with `"Principal": "*"` |
| `unauthenticated_app` | high | STRUCTURAL | the application declares no authentication mechanism anywhere **and** has at least one mutating route |

Two boundaries are load-bearing.

**`secrets` owns credential material; `misconfig` owns generator defaults.** The
`django-insecure-` prefix is a default that `django-admin startproject` writes,
so it belongs here, and neither signal double-reports the same line. It is
JUDGEMENT for D7's reason: deleting the literal is mechanical, rotating the key
is not.

**`unauthenticated_app` is whole-application scoped, not per-route.** It fires
once per repository, never once per handler. Deciding whether a *particular*
route should be authenticated is semantic analysis and belongs to E-46/E-49; a
per-route rule computed from decorators would be a false-positive generator, and
a triage report a client cannot trust is worse than a shorter one.

Metrics: `frameworks_detected` (measured). No readiness key.

## 8. Signal 7 — `outliers` (E-41d)

| rule | severity | fix_class | trigger |
|---|---|---|---|
| `oversized_file` | medium | STRUCTURAL | source file LOC > `adapter.max_file_loc` |
| `oversized_function` | medium | STRUCTURAL | span LOC > `adapter.max_function_loc` |
| `duplicated_block` | medium | JUDGEMENT | a clone group ≥ `adapter.min_clone_loc` spanning ≥ 2 files |

Both size rules are STRUCTURAL: splitting a file or a function is design work,
and E-44 must not pick it up as a mechanical PR.

Duplication is normalized 6-line window hashing — whitespace collapsed, comments
and blank lines dropped — grouping windows by hash and merging adjacent matches
into clone groups. Analysis is capped by file count and total lines; exceeding
the cap makes `duplicated_loc_ratio` `not_collected` rather than reporting a
partial ratio as if it covered the tree (D16).

When `function_spans` returns `None`, the `oversized_function` rule is skipped
and its metric is `not_collected` — a language we cannot parse is not a language
with no long functions.

Metrics: `max_file_loc_seen`, `duplicated_loc_ratio`. No readiness key.

## 9. Error handling and evidence

**Signal level (unchanged).** Every activity wraps its body; an escaping
exception becomes `not_collected` for that signal alone, and the other six still
report. The build probe's `maximum_attempts=1` rationale applies to the new
activities too: a deterministic parse failure does not become a success on
attempt two.

**Sub-capability level (D16).** `known_vulnerable`, `duplicated_loc_ratio`,
`oversized_function` and `history_basis` each report a `not_collected` metric
while their signal stays MEASURED.

**Evidence (D5).** Every finding carrying a quote re-verifies it against the
blob it cites through `verify_quote(..., Profile.VERBATIM_BYTES)`, and an
unverifiable quote **drops the finding** rather than emitting it unquoted.
Findings with no natural quote — `no lockfile`, `unused_dependency` — carry
`evidence=""`. As with `secrets`, these remain drift guards rather than
hallucination guards until an LLM proposer cites the same way; that is when the
check becomes load-bearing (FR-914).

## 10. Testing

Pure-unit per signal module over synthetic inputs, matching the four existing
`tests/test_triage_*.py` files.

- `test_triage_dependencies.py`, `test_triage_scaffold.py`,
  `test_triage_misconfig.py`, `test_triage_outliers.py` — each rule's fire and
  no-fire case, plus the false-positive guards that justify the rules: an
  aliased dependency (`pillow`) not reported unused, a hand-edited `App.js` not
  reported as scaffolding, an application with auth declared not reported
  `unauthenticated_app`.
- **Migration regression guard.** `compute_readiness` still raises when two
  signals report `M_STRUCTURE`; `baseline` v2 no longer reports it; `scaffold`
  does. This is the test that catches a botched hand-off, and it is the reason
  the migration is safe to do in one step.
- **Scaffold history.** A single-commit repository yields
  `history_basis = not_collected` with fingerprint-level severities and a
  MEASURED signal; a multi-commit repository escalates an untouched
  fingerprinted file.
- **Advisory seam.** A fake source that raises, one that times out, and one that
  returns hits — asserting the first two yield `not_collected` with zero
  vulnerability findings. `OsvAdvisorySource` is tested against a stubbed
  transport. **No test touches the network.**
- **`gitread`.** Against a real temporary git repository, `TreeReader` matches
  `read_blob` on blob, tree and missing paths. That equivalence is what makes
  the `secrets` migration safe, so it is asserted rather than assumed.
- **Registry.** Seven entries, unique ids, `baseline` at version 2, every
  `activity` name resolvable in `worker.py`'s registration list.

## 11. Out of scope

- **Per-route authentication analysis** — E-46/E-49 (§7).
- **Transitive dependency resolution** — the advisory lookup covers declared
  direct dependencies and says so in its detail text.
- **Non-Python adapters** — Go/TS/Rust remain E-30a/b/c and get the degradation
  path (empty tuples, disabled thresholds, `function_spans` returning `None`),
  not rules.
- **E-46 memoization** — signal versions are numbered for the
  `(tree hash, signal version)` key but this increment does not implement it.
- **`TriageWorkflow`, the readiness verdict gate, and fix runs** — E-42 and
  E-44, unchanged by this design.

## 12. Roadmap consequences

- **FR-902** moves from three of seven signal families to **seven of seven**.
- **E-41a, E-41b, E-41c, E-41d** all close; E-41's own `⚠️` partial mark
  resolves.
- **E-41b's note that `structure_discernible` "ships as a deliberate floor"** is
  rewritten, not removed: the floor is raised by fingerprinting, and an
  unfingerprinted generator still passes (§6).
- **FR-703** gains a declared, opt-in, off-by-default outbound egress in
  `OsvAdvisorySource` — the pipeline's second after research (FR-107), and it
  should be recorded on that line rather than left implicit.
- **FR-108/ADR-15** gains its first pure per-language *parser* member
  (`function_spans`) beside its command strings (D15).
- **NFR-9 is unchanged.** These four signals read bytes and history; none of
  them executes the triaged repository's code. The build probe remains the only
  signal that does, and the operator-authorization trust boundary is neither
  widened nor narrowed here.
