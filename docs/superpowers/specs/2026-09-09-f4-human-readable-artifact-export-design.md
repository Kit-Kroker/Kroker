# F4 — human-readable artifact export

**Date:** 2026-09-09
**Status:** design, pending user + reviewer sign-off
**Scope:** one row from the external-ideas register (`docs/reports/external-ideas-2026-09.md:93`, section F, F4). A new, small build: a pure renderer that turns each of the board's three typed artifacts into Markdown, plus two read routes on the existing board API that serve it.
**Satisfies:** no FR moves. Nothing in `PRD.md`, `ROADMAP.md`, or `src/` renders a board artifact for a human today; the register's Status for this row is `New` ("a real build with no existing seam") and that is confirmed below.
**Baseline:** `main` at `7cdc14c`.
**Does not cover:** any Vue/dashboard UI work; any new CLI subcommand; writing `.md` files to disk; publishing `IdeaBrief` to the board; rendering task evidence or harness sessions; auth on the board API. See §8.

---

## 1. Problem

A human standing at a gate has no readable view of what they are approving.

The pipeline publishes exactly three typed artifacts to the board.
`workflows/feature.py:560`, `:585`, and `:602` call
`BoardHost._board_publish` (`workflows/board_host.py:49`) with
`model_dump_json()` of, respectively, `ClarifiedRequirements`
(`stages/clarify/models.py:30`), `ArchitectureSpec`
(`stages/architecture/models.py:18`), and `ImplementationPlan`
(`stages/plan/models.py:67`). SQLite stores only the pointer —
`artifact_version(uri, sha256, n, run_id, created_at)`
(`board/schema.py`); the body is a JSON blob in the claim-check store
(`artifacts/store.py`, under `runs/<run_id>/artifacts/<key>-v<n>.json`,
written at `board/store.py:182`).

Every existing way to read one of those bodies hands back raw JSON:

- `GET /projects/{p}/artifacts/{key}/versions/{id}` (`board/api.py:119`)
  returns a `VersionContent` envelope whose `.content` is the JSON source as
  a string, truncated at 512 KB (`board/api.py:35`, `:142`).
- The operator tool `read_artifact` (`operator/tools.py:244`) pages the same
  raw bytes, and its docstring is explicit that its reader is a model, not a
  person: "Summarize what you read; do not quote it whole."
- The Vue dashboard never touches artifacts at all. Grepping `artifact`
  across `interfaces/dashboard/frontend/src/` returns exactly one hit,
  `constants.test.ts:5`, which is about stage counts and unrelated.
- `src/sdlc/cli.py` has no board or artifact subcommand of any kind. Its
  full top-level set is `start`, `status`, `inbox`, the gate verbs
  (`approve` / `reject` / `revise` / `answer`), `schedules`, `benchmark`,
  `eval`, `calibrate`, `triage`, `tidyup`, and `assess` — a Temporal-client
  CLI throughout. Nothing in it opens the board's SQLite file.

So the register's framing is exact: the adoption blocker is that "a human
standing at a gate currently reads SQLite through an unauthenticated
localhost API" (`docs/reports/external-ideas-2026-09.md:131-133`). A product
owner asked to approve an `ArchitectureSpec` is handed a single-line JSON
object with escaped newlines.

**The register's own constraint governs the fix**: *render from the typed
artifact — typed and readable are not in tension*. The output is a
projection of the stored model, generated on read. It is never a second,
hand-maintained document, and it never becomes a source of truth.

## 2. Markdown rendering is an existing house idiom, not a new capability

Nothing new needs inventing for the rendering itself. The repo already
renders typed models to Markdown in four places — `benchmarks/report.py:64`
(`render_markdown(summaries) -> str`),
`benchmarks/calibration.py:283`, `benchmarks/experiments.py:167`, and
`benchmarks/sc_rollup.py:197` — and to compact ASCII text in
`operator/render.py` and `context/render.py`. All six are the same shape: a
pure function that builds `lines: list[str]` and returns `"\n".join(...)`.

**There is no template engine in this repo and this spec does not add one.**
The load-bearing evidence is `pyproject.toml`: no `jinja2`, `mako`, or any
other templating package appears in its dependencies. Grepping
`jinja|mako|template` across `src/sdlc` corroborates it — every hit is
either prose (`crew/activities.py:373`, `observability/export.py:4`), an
`.env.template` filename string (`triage/signals/baseline.py:40`,
`triage/signals/secrets.py:33`), or a `str.format` call building a URL or
a fixture string (`memory/hindsight_client.py:170-171`,
`benchmarks/importers/deveval.py:175`, `:196`). None is a document
templating engine. (An exact hit count is deliberately not quoted here:
the count drifted three times while this spec was under review, and the
conclusion does not depend on it.)

Two constraints inherited from that idiom:

- **ASCII only in emitted Markdown.** `benchmarks/report.py:80-82` records
  why: a Windows console's cp1252 codepage mangles an em dash into a
  replacement character when the text is printed, not merely when it is
  written to a file. `channels/transport.py:12` states the same rule. Gate
  readers on Windows hit exactly this, so the renderers use `-`, `--`, and
  `->` rather than typographic dashes and arrows.
- **The renderer is framework-free.** `operator/tools.py:1-12` states the
  rule for its own layer: "no pydantic_ai, no fastapi — anything
  framework-shaped belongs in the adapter". The renderer takes a parsed
  model and returns a string; it never touches FastAPI, the store, or a
  filesystem path.

## 3. Where the renderer lives

**One new module, `src/sdlc/board/render.py`**, holding the three render
functions and the key registry. Not one `render.py` per stage package.

`AGENTS.md` bans cross-stage *calls* and states that "importing a *type*
another stage produces is not a call". A renderer only imports types, and
**`board/` already does exactly this, twice**: `board/store.py:30` and
`board/activities.py:21` both import `stages.plan.models.DevTask`
(`workflows/board_host.py:29` is a third instance, one layer up). Adding
three more type imports to this package breaks no rule it is not already
living under. `board/` is one of the horizontal packages `AGENTS.md` names
as deliberately not forced into the stage shape, and it already owns every
artifact read path, so the projection belongs beside them.

The alternative — a producer-owned `render.py` in each of the three stage
packages — was considered and rejected. It is more literally faithful to
"the producer owns its artifacts", but the routes must dispatch on `key`,
so a registry in `board/` is unavoidable under *either* placement; the
per-stage split therefore buys nothing while scattering three ~40-line
modules and making the whole render harder to review as one artifact. One
~200-line module matches how `benchmarks/report.py` handles the same
problem.

### 3.1 Shape

```python
# key -> (model type, renderer)
RENDERERS: dict[str, tuple[type[BaseModel], Callable[[Any], list[str]]]] = {
    "requirements": (ClarifiedRequirements, _requirements_body),
    "architecture": (ArchitectureSpec, _architecture_body),
    "plan":         (ImplementationPlan,  _plan_body),
}

def render_version_markdown(
    key: str, raw: bytes, *, project: str, version: ArtifactVersion
) -> str: ...
```

`render_version_markdown` parses, renders the provenance banner, appends the
body, and returns the document. It raises the typed errors of §5; it does
not know about HTTP. The `_*_body` functions are pure
`(model) -> list[str]`.

**The module carries the artifact-boundary obligation as a header comment.**
`AGENTS.md` requires that whoever changes a stage's behaviour updates its
clauses in the same diff; the analogous obligation here is that whoever adds
a field to one of the three artifact models updates its renderer in the same
diff. §6.2 makes that obligation a failing test rather than only a comment.

## 4. What the render contains

### 4.1 Provenance banner

Every document opens with a heading and a metadata table, in the two-column
style the repo already uses for document headers
(`docs/reports/external-ideas-2026-09.md:3-10`):

```markdown
# Architecture -- acme-checkout

| | |
|---|---|
| artifact | architecture |
| version | 3 (id 41) |
| run | feature-acme-checkout-20260909-1 |
| published | 2026-09-09T08:14:02Z |
| sha256 | 9f2c... |
```

This is not decoration. A `.md` that a non-engineer forwards to a colleague
must say which version of which run it is, or a stale render is
indistinguishable from the current one — and staleness is the specific
failure mode that "generated, never hand-maintained" is meant to prevent.

### 4.2 Per-artifact bodies

**requirements** (`ClarifiedRequirements`): summary as prose; functional
requirements, non-functional requirements, and out-of-scope as lists; open
questions as a subsection per question showing `question`,
`why_it_matters`, `suggested_answer`, and `answer`, with answered and
unanswered visually distinguished — an unanswered open question is the thing
a human at a gate must act on. Each question also carries a one-line
provenance suffix built from `id`, `dimension`, `asked_by`, `materiality`,
and `evidence`: `materiality` tells a gate reader how much the question
matters and `evidence` is the repo path grounding it, so neither is
plumbing. `dropped` renders under its own heading
labelled as questions the cap cut, because that field exists precisely so
that "capping and being incurious are indistinguishable in the record" stays
false (`stages/clarify/models.py:37-39`); a render that hid it would defeat
the field. `dimensions_probed` renders as a one-line list.

**architecture** (`ArchitectureSpec`): overview; `confidence` as a
percentage when present; one subsection per `ArchitectureDecision`
(`id`, `decision`, `rationale`, `alternatives_considered`); `risks`;
`affected_modules` / `new_components`; and `delta` (`BrownfieldDelta`,
`stages/context/models.py:8`) as three labelled lists — added / modified /
removed — since those three "have OPPOSITE grounding rules" and a flat list
cannot carry the distinction.

**plan** (`ImplementationPlan`): `confidence`; a task count; then one
subsection per `DevTask` with `id`, `title`, `role`, `description`,
`depends_on`, `acceptance_criteria`, `files_hint`, `overlaps`, and the
frozen `ValidationContract` (`assertions`, `test_commands`, `lint_commands`,
`stack`) when present.

### 4.3 Deliberate omissions

`_OMITTED: dict[type, set[str]]` in the module holds five `(model, field)`
entries for three reasons, and that is the whole list — verified by walking
`model_fields` on all eight artifact models. §6.2 makes any *future* silent
omission a test failure.

- `ClarifiedRequirements.spec_ref`, `ArchitectureSpec.spec_ref`, and
  `ImplementationPlan.plan_ref` (all `ArtifactRef`): claim-check plumbing, a
  `file://` URI and a hash, with nothing a non-engineer can act on. The
  banner already carries provenance.
- `ValidationContract.task_id`: it repeats the `DevTask.id` of the
  subsection the contract is already nested inside.
- `ValidationContract.frozen`: documented as set at the plan gate and
  immutable after (`stages/architecture/models.py:61`), so it is `True` on
  every artifact a reader will ever see and carries no information. Should
  a `frozen=False` contract become reachable, the omission entry is where
  that gets reconsidered.

## 5. Failure modes: hard errors with Markdown bodies, never a degraded render

A non-engineer cannot tell a degraded render from a good one, so the
renderer never produces one. Four cases, none of which may reach a 500:

1. **Unknown key** -> `404`. `publish_artifact_version` accepts an arbitrary
   `key` string, so a key with no registered renderer is reachable. The body
   names the keys that do render.
2. **Blob pruned from the claim-check store** -> `410`, preserving the
   status and reasoning the JSON route already uses (`board/api.py:130-140`:
   "Metadata outlives the blob"). The body names the `sha256` and `uri` so
   the history is still traceable.
3. **Stored bytes do not yield a valid model** -> `422`, with a body
   stating that the render failed, naming the expected model, listing the
   error messages, and pointing at the raw-JSON route as the escape hatch.

   **Parsing is `Model.model_validate_json(raw_bytes)`, not
   `json.loads` followed by `model_validate`.** This is a load-bearing
   choice, not a style preference: verified empirically, Pydantic v2's
   JSON parser raises `ValidationError` with `type="json_invalid"` for
   malformed JSON *and* for invalid UTF-8, so the one-step form collapses
   all three failure classes — unparseable bytes, undecodable bytes, and
   schema mismatch — into a single `except ValidationError`. The two-step
   form would instead leak `json.JSONDecodeError` and `UnicodeDecodeError`
   past a `ValidationError` handler and into a `500`, breaking this
   section's "none of which may reach a 500" invariant. Nothing validates
   JSON-ness at write time — `publish_artifact_version` accepts arbitrary
   bytes, and the existing cap test publishes `b"x" * (MAX + 10)` — so
   unparseable blobs are reachable, not hypothetical:
   `tests/test_board_api_reads.py:129` already publishes
   `b"x" * (MAX_CONTENT_BYTES + 10)` as a `plan` artifact. `500` stays
   reserved for genuine infrastructure failure.

   One residual condition on the no-500 invariant, recorded because it is
   invisible from the handler: Pydantic wraps `ValueError` and
   `AssertionError` raised inside a custom validator into
   `ValidationError`, but any other exception type propagates out of
   `model_validate_json` untouched and past `except ValidationError`.
   There is no live path today — the only custom validator across all
   eight artifact models is
   `ArchitectureSpec._affected_modules_follow_the_delta`
   (`stages/architecture/models.py:28-42`), which mutates and never
   raises — so the invariant holds as specified. It would break silently
   if a future validator on any of those models raised something else,
   which is a constraint on those models, not on this renderer.
4. **Blob exceeds `MAX_CONTENT_BYTES`** -> `413`, pointing at the paged
   JSON route. This deliberately differs from the JSON route, which
   truncates and sets `truncated: true` (`board/api.py:142-150`). Truncated
   JSON never parses, and a truncated *render* would hand a human a
   silently incomplete spec with no way to know it. Refusing is the only
   honest option. These artifacts are KB-scale, so this should never fire.

**Case 4 is checked before case 3** — size first, then parse. The two
overlap in practice: the blob at `tests/test_board_api_reads.py:129` is
both oversize *and* unparseable, so check order decides which status it
returns. Size wins because it is the cheaper and more specific answer —
`413` tells the caller the document is too large to render and names the
paged route, whereas parsing 512 KB of `x` to report `json_invalid` costs
more and tells them less. It also means the renderer never parses an
unbounded blob.

**A "partial render with a warning banner" was considered and rejected.** It
is the obvious middle path, and the argument against it is decisive: gate
readers copy sections out of these documents into chat and tickets, and a
banner at the top of the file does not survive a copied section. An
unlabelled fragment of a degraded render is worse than an error.

The accepted cost is that case 3 leaves the human with no *rendered*
document. It is tolerable for two reasons, the second stronger than the
first.

First, schema drift should be uncommon — but "impossible by construction"
would overstate it, and this spec does not claim that. Only one thing is
construction: Pydantic ignores unknown fields by default, so a purely
additive change keeps old blobs valid. The rest is convention, and thinner
than it looks: the "additive only -- a pre-E-85 artifact must still
validate" commitment (`stages/clarify/models.py:23`) is a *comment* scoped
to the clarify models, backed by envelope-compat tests only under
`tests/clarify`. `ArchitectureSpec`, `ImplementationPlan`, `DevTask`, and
`ValidationContract` carry no such commitment at all. A new required field,
a tightened `ge`/`le` bound, or a type change on any of them is one
ordinary refactor away from producing a `422`.

Second — and this is what makes the cost acceptable — **the `422` body
names the raw-JSON route**, so the reader is handed an explicit fallback
rather than a dead end. The degraded-render option offers no such
signposting; it offers a document that looks complete and is not. A loud
`422` on a genuine backward-compatibility break is a feature: it surfaces
a real defect at the moment a human hits it, instead of hiding it behind
a partial render.

## 6. HTTP surface

Two routes on the existing board app (`board/api.py`), which
`interfaces/dashboard/api/main.py` already composes into the dashboard
process:

```
GET /projects/{project}/artifacts/{key}/current/markdown
GET /projects/{project}/artifacts/{key}/versions/{version_id}/markdown
```

Both return `text/markdown; charset=utf-8` as a bare body (a
`PlainTextResponse`), not a JSON envelope. Both reuse the existing guards
verbatim: `_require_project`, the version-belongs-to-key check, and the
pruned-blob branch.

**A literal trailing segment, not a `.md` suffix.** The existing route
declares `version_id: int`, so a `/versions/{version_id}.md` pattern makes
FastAPI try to coerce `"41.md"` to `int`. Verified empirically against
`fastapi.testclient`, not merely reasoned: with the int route declared
first, `GET /v/41.md` returns `422 int_parsing`; move the suffixed route
above it and both resolve correctly. So a `.md` suffix works, but only
under a declaration-order constraint that nothing in the file would remind
a later editor of. A literal `/markdown` segment resolves correctly
regardless of order. The cost is a URL ending in
`/markdown` rather than `.md`; the download filename is set explicitly
instead, via `Content-Disposition: inline; filename="<project>-<key>-v<n>.md"`,
which gives a better filename than a URL suffix would.

`current/markdown` resolves `BoardArtifact.current_version` and returns
`404` with a clear message when it is `None` — which is the real case where
a gate was rejected, since `_board_publish` writes `REJECTED` history
without moving the pointer (`workflows/board_host.py:52-53`). A human
reading a *rejected* architecture is exactly the audience for the versioned
route, so both routes are needed; neither is a convenience alias for the
other.

**An acknowledged gap: that reader has no readable way to find the version
id.** A rejected artifact has no current version, so there is no
`current/markdown` document to carry a link, and the only route that lists
the lineage is the raw-JSON `/artifacts/{key}` one — which is the surface
F4 exists to spare a non-engineer. This spec does not fix it, because the
natural fix is a link handed to the reader rather than a new discovery UI,
which is open question 1. It is recorded here so that resolving OQ-1
resolves this too, and so nobody reads §6 as claiming the versioned route
is reachable today without engineer help.

**Caching: `ETag` plus explicit revalidation.** Both routes set
`ETag: W/"<RENDER_VERSION>-<version_id>-<sha256[:16]>"` and
`Cache-Control: no-cache`.

The cache key is complete: every input to the document — `project`, `key`,
`n`, `run_id`, `created_at`, `sha256` — is a function of the immutable
`artifact_version` row, so `version_id` plus `sha256` pins the content.
`RENDER_VERSION` is a module constant, bumped when a renderer changes its
output; without it a cache would keep serving the old render after the
renderer is edited, since neither `sha256` nor `version_id` moves.

**The handler must compare `If-None-Match` and return `304` itself.**
FastAPI and Starlette do not do this for you — an `ETag` response header
with no server-side comparison is decoration, and every request still
returns `200` with the full body. So each route reads the `If-None-Match`
request header, and returns a bodyless `304` when it matches the computed
tag, before rendering. `Cache-Control: no-cache` is what makes that
worthwhile: it instructs clients to revalidate on every request rather
than serve a stale copy from cache without asking, which is the correct
posture for a document whose `current` version can move under it.

### 6.1 What stays out of the workflow

The renderer runs in the FastAPI process only. It is **not** an activity and
is never called from `FeatureWorkflow`. Adding it as an activity would drag
three stage model modules through the workflow sandbox's
`imports_passed_through` list for no benefit; this is a read-path
projection, exactly as `benchmarks/report.py` is, not pipeline state.
Temporal determinism is therefore unaffected.

### 6.2 Testing

Following the `tests/test_*_render.py` convention already used by
`test_operator_render.py`, `test_calibration_render.py`, and five others:

- **`tests/test_board_render.py`** — unit tests over the pure functions: one
  fully-populated fixture per artifact type asserting every field reaches
  the output; empty-collection cases (a plan with no tasks, requirements
  with no open questions) producing valid Markdown rather than dangling
  headings; the ASCII-only assertion (`out.isascii()`); `dropped` questions
  rendering under their own heading; answered vs unanswered open questions
  being distinguishable.
- **The no-silent-field-drop test.** For each entry in `RENDERERS`, walk
  `model_fields` **recursively through nested artifact models**
  (`OpenQuestion`, `ArchitectureDecision`, `BrownfieldDelta`, `DevTask`,
  `ValidationContract`) and assert every field is either present in the
  rendered output for a fully-populated fixture or listed in `_OMITTED`.
  Recursion matters because most fields are only reachable through it:
  `DevTask`'s nine and `OpenQuestion`'s nine never appear in a top-level
  walk, and two of the three omissions (`ValidationContract.task_id`,
  `.frozen`) are nested two levels down.

  **Presence must be asserted against a labelled anchor, not a bare
  substring.** Sentinel values work only for free-text fields. Two fields
  have closed vocabularies — `DevTask.role` (`Literal["dev","test",
  "devops"]`) and `ClarificationDimension` (`C1`-`C6`, reached via
  `OpenQuestion.dimension` and `dimensions_probed`) — and their values
  occur incidentally elsewhere in the output: `"test"` appears in
  `test_commands`, `"dev"` inside `"devops"` and in prose. A bare
  substring check would pass even if the renderer dropped `role`
  entirely, which is exactly the failure this test exists to catch. So
  each such field renders under an explicit label and the test asserts the
  labelled form (`f"role: {task.role}"`), or supplies a per-field presence
  predicate. Free-text fields keep distinctive sentinels.

  This is what makes "render *from* the typed artifact" enforceable
  instead of aspirational: adding a field to `ClarifiedRequirements` or to
  `DevTask` fails this test until someone either renders it or records the
  omission deliberately.
- **`tests/test_board_api_markdown.py`** — route tests over
  `create_app`, following the `tmp_path` + seeded `BoardStore` fixture in
  `tests/test_board_api_reads.py:14-44`: content type and status for both
  routes; `404` unknown key; `404` no current version; `410` pruned blob;
  `422` schema drift; `422` unparseable bytes (§5 case 3's one-step parse);
  `413` oversize blob (§5 case 4); `ETag` presence; and a `304` on a
  matching `If-None-Match`. The drift case needs no contrivance —
  that file's own fixture already seeds `architecture` as
  `b'{"overview":"first"}'` (`test_board_api_reads.py:21`), which fails
  `ArchitectureSpec` validation because `decisions` is required.

## 7. Documentation

`README.md:73-78` lists the board API's routes; the two Markdown routes are
added there, with the existing localhost/no-auth warning extended to say
that these URLs are designed to be pasted around and still carry no
authentication (`ROADMAP` OQ-11).

No stage contract clause changes and no `scripts/check_clauses.py` work: no
stage's behaviour changes. No `docs/schemas/` regeneration: the renderer is
a projection, not a schema. `ARCHITECTURE.md` and `ROADMAP.md` track `main`
and are updated at merge, not here.

## 8. Explicitly out of scope

- **Dashboard UI.** The register says non-engineers should read intent and
  spec "*without* the dashboard", and the Vue app has no artifact surface to
  extend. A URL is the deliverable.
- **A CLI subcommand.** `cli.py` has no board seam; adding one means a
  second SQLite reader path beside the API's.
- **Writing `.md` files to disk.** "Export" here means a retrievable
  document, not a generated file. Files beside the run would be a second
  source of truth with their own staleness and claim-check GC lifecycle, and
  there is no consumer for them.
- **Publishing `IdeaBrief` to the board.** `core/models.py:108` is pipeline
  input and nothing publishes it, so the register's word "intent" can only
  mean `ClarifiedRequirements.summary` and its FR/NFR lists today. Making
  the raw idea a board artifact is a real gap but a different change. Named
  as an open question below.
- **Task evidence and harness sessions.** `TaskEvidence` bodies and
  `harness_session` blobs are also claim-check JSON, but they are agent
  inputs, not gate reading, and their kinds are open-ended.
- **Auth.** Inherited unchanged from the board API (`OQ-11`).

## 9. Open questions for the user gate

1. **Should the gate notification link the render?** The routes are useless
   to a non-engineer who is never given the URL. Linking
   `current/markdown` from the gate notification is a one-line change at the
   notification call site. It is left out of this spec's scope because the
   board API is documented as *optional* (`README.md:66`) and the pipeline
   can run with nothing serving it — a notification linking a dead URL is
   worse than none. Making this work properly needs a decision about whether
   a configured board base URL becomes a precondition for the link. **This
   is the question that decides whether F4 is adopted or merely available.**
   It also subsumes the §6 discovery gap: a link in the gate notification
   is what gives a reader of a *rejected* artifact its version id without
   sending them to the raw-JSON lineage route.
2. **`/markdown` or `.md`?** §6 recommends the literal segment for the
   routing reason given. A `.md`-suffixed URL is achievable — confirmed
   working when the suffixed route is declared above the int-typed one —
   so if it is judged materially friendlier for the target audience, the
   only cost is a declaration-order constraint that needs a comment to keep
   a later editor from silently breaking it by reordering.
3. **Is `IdeaBrief` in or out?** A non-engineer's "intent" is arguably the
   raw idea, not the clarified requirements. Publishing it as a fourth board
   artifact key is a small change to `feature.py` but it is a pipeline
   change, not a read-path one, so it is excluded here rather than
   smuggled in.
