# Real Hindsight memory integration — design

| | |
|---|---|
| Date | 2026-08-02 |
| Status | Design approved; implementation pending |
| Scope | Replace the fabricated `HindsightMemory` client with one written against Hindsight's actual REST API, and verify it against a live container |
| Requirements touched | NFR-6 (reproducibility vs memoization), NFR-7 (portability), FR-400/FR-402/FR-404 |
| Related | `ROADMAP.md` P3 / NFR-6 / NFR-7, `docs/superpowers/plans/2026-07-05-hindsight-memory-and-memoization.md`, `ARCHITECTURE.md` §6/§8 |

## 1. What prompted this

`ROADMAP.md` marks NFR-7 done on the strength of "a real Hindsight client for
self-hosting", and commit `5d302f7` added the `hindsight` service to
`docker-compose.yml` so the factory could run against it. Pointing the two at
each other does not work: `src/sdlc/memory/hindsight_client.py` does not
implement Hindsight's API. It implements an invented one.

| The client calls | Hindsight actually exposes |
|---|---|
| `GET /v1/banks/{bank}/watermark` | nothing — there is no watermark, version or as-of concept in the API |
| `POST /v1/banks/{bank}/retain` with `{kind, text, metadata}` | `POST /v1/{tenant}/banks/{bank}/memories/retain` with `{items: [{content, context, tags, metadata, document_id, timestamp}], async}` |
| `POST /v1/banks/{bank}/recall` → `{query_hash, watermark, items}` | `POST /v1/{tenant}/banks/{bank}/…/recall` with `{query, types, tags, tags_match, budget, max_tokens}` → `{results: [{id, text, tags, mentioned_at, metadata, scores}]}` |
| `POST /v1/banks/{bank}/reflect` | `…/reflect` is an agentic question-answering call taking a `query`; bank consolidation is `…/consolidate` |
| — | the `{tenant}` path segment, `Authorization: Bearer`, and bank creation (`PUT …/banks/{bank}`) have no counterpart in the client at all |

Every request the client can issue would 404.

### 1.1 Why the tests did not catch it

`tests/test_hindsight_client.py` is green. Each of its four tests installs an
`httpx.MockTransport` whose handler asserts the path *the client itself
chose*:

```python
def handler(request):
    assert request.url.path == "/v1/banks/project:x/recall"
    return httpx.Response(200, json={"query_hash": "abc123", ...})
```

The assertion and the code under test share a single source of truth — the
author's assumption — so the suite can only ever confirm that the client is
self-consistent. This is the structural failure the design has to remove, not
merely the wrong paths. Correcting the four mocks against the documentation
would rebuild the same trap one URL to the left.

### 1.2 Two further defects the rewrite must fix

**Filters would silently no-op.** `feature.py` recalls with
`filters={"stage": "clarify"}` (lines 1369, 1433, 1505) and retains with
`metadata={"stage": "clarify", "run_id": …}` (lines 1423, 1496, 1538).
Hindsight filters on **tags**, and its recall documentation states plainly that
metadata is returned on results but cannot be used to filter at query time.
Against a real backend the clarify stage would therefore recall the architect
stage's memories — a wrong answer with no error anywhere.

**`reflect` is the wrong verb.** `schedules/nightly-reflect.yaml` and
`ReflectWorkflow` exist to run nightly *consolidation*. `POST …/reflect` runs an
agent loop and returns prose, which the activity discards. It would cost tokens
every night and consolidate nothing.

## 2. Constraint: Hindsight has no point-in-time read

NFR-6 ("Reproducibility vs memoization — watermark-pinned recall +
content-addressed cache") rests on freezing recall at a watermark. `FakeMemory`
gets this exactly: the per-bank entry count *is* the watermark, and recall
filters `version <= cutoff`. `_cached_stage` mixes `self._memory_watermark`
into the memoization key, so the answer here also decides whether the dev-loop
cache stays sound on the real backend.

Hindsight offers no equivalent. `query_timestamp` looks like one and is not —
the documentation says it "is used as the anchor for resolving relative
temporal expressions in the query and for recency scoring." It does not
restrict results to memories known before that time.

**Decision: enforce the cutoff client-side.** The watermark is an ISO-8601
UTC timestamp; recall over-fetches and drops every result whose `mentioned_at`
exceeds it before assembling the snapshot.

For this comparison to be sound the two timestamps must come from the same
clock, so **retain always sends an explicit `timestamp` taken from the worker
clock**. `mentioned_at` then echoes a value the worker minted, and skew between
the worker and the Hindsight container cannot leak a post-freeze memory into a
pinned recall.

### 2.1 What the guarantee is, precisely

**Holds:** no memory *about* anything after the freeze point can enter a stage
input.

**Does not hold:** byte-identical replay. Two things weaken it, and both are
accepted rather than solved:

1. **Ranking contamination.** Memories retained after the watermark still
   compete for the top-N slots the server returns, so a pinned recall is a
   *subset* of the original result, not the identical list. Over-fetching
   (requesting more results than the snapshot keeps) reduces but does not
   eliminate this.
2. **Post-freeze consolidation.** Consolidation run after a freeze point can
   mint new `observation` rows derived from pre-freeze facts. Their
   `mentioned_at` trails their sources, so they pass the cutoff: new text, old
   timestamp.

Excluding `types: ["observation"]` whenever a watermark is pinned would close
(2) at the cost of discarding Hindsight's consolidated knowledge — the most
valuable thing it produces. Observations stay in; the caveat is documented
here and in `ROADMAP.md` rather than engineered away.

## 3. Client design

Only `hindsight_client.py` and three small plumbing seams change. The `Memory`
protocol, `RecallSnapshot`, `RetainItem`, every `_recall`/`_retain` call site
in `feature.py`, and `ReflectWorkflow` are all untouched.

### 3.1 URL and identity

Base path `{base_url}/v1/{tenant}/banks/{bank_id}/…`, tenant from
`SDLC_MEMORY_TENANT` (default `default`).

Bank ids need sanitizing: the factory uses `project:default` and `org`, and
whether Hindsight validates bank ids as slugs is unknown. A single `_bank_id()`
maps characters outside `[A-Za-z0-9_-]` to `-`, deterministically and in one
place. §6 step 1 confirms against the live service whether the mapping is
needed; the function stays regardless so the answer lives in one function
rather than in string literals.

`Authorization: Bearer {key}` is sent only when a key is configured. Local
containers run open.

### 3.2 retain

The path below is written as the developer guide documents it; the API
reference index gives a different one, and §8 records the conflict. **No path
is hardcoded until §6 step 1 resolves it from the container's own schema** —
what is settled here is the body and its semantics, not the URL.

```
POST /v1/{tenant}/banks/{bank}/memories/retain      # path pinned in §6 step 1
{
  "items": [{
    "content":     item.text,
    "context":     item.kind.value,
    "tags":        ["kind:<kind>", "stage:<stage>", …],
    "metadata":    item.metadata,
    "timestamp":   <worker UTC now, ISO-8601>,
    "document_id": <sha256(bank|kind|text)>
  }],
  "async": true,
  "operation_id": <deterministic UUID from the same hash>
}
```

**Async, deliberately.** Retain triggers LLM fact extraction; run
synchronously it would exceed `MEM_ACT`'s 30-second `start_to_close_timeout`.
Async returns immediately, and the deterministic `operation_id` — documented as
the mechanism for safe async retries — makes Temporal's five retry attempts
idempotent. `document_id` carries the same hash for upsert idempotency.

Nothing of value is given up: `_retain` is already best-effort and swallows
exceptions (`feature.py:474`), and the §2 watermark cutoff means a run cannot
recall its own writes in any case. The cost is that an extraction failure is
invisible to the pipeline, which matches retain's existing best-effort
contract.

### 3.3 Tag promotion, and the loud-failure rule

Retain writes tags so recall can filter on them:

- always `kind:<MemoryKind value>`;
- plus a fixed allowlist promoted from metadata: **`stage`, `gate`**.

`run_id`, `task_id`, `round` and `source_url` stay metadata-only — `run_id`
and `task_id` are unbounded cardinality, and URLs do not belong in a tag
namespace.

Recall maps `filters` to `tags: ["k:v", …]` with `tags_match: "all_strict"`.
The `_strict` variant excludes untagged memories; the permissive default would
reintroduce a filter that matches everything.

**If a caller passes a filter key outside the allowlist, the client raises.**
Hindsight cannot filter on metadata at query time, so the only alternative is
returning unfiltered results under a filtered-looking call — the exact class of
silent wrongness this design exists to remove. All three present call sites use
`stage`, so nothing raises today; the rule is there for the fourth call site.

### 3.4 recall

```
POST /v1/{tenant}/banks/{bank}/…/recall             # path pinned in §6 step 1
{"query": …, "tags": [...], "tags_match": "all_strict", <result bound>}
```

`tags` and `tags_match` are omitted entirely when `filters` is empty. Response
handling:

1. drop results with `mentioned_at > watermark` (when a watermark is pinned);
2. keep the top 10 by score, matching `FakeMemory`'s slice size;
3. `query_hash` is computed client-side — Hindsight returns no such field.

**Over-fetch factor.** Because step 1 discards results, asking for exactly 10
would return fewer than 10 whenever anything was retained after the freeze
point. The client requests **3× the snapshot size** and truncates after
filtering. Which parameter expresses that bound is unsettled — the developer
guide documents `max_tokens` and `budget`, the API reference index documents
`limit` — so the concrete knob is pinned in §6 step 1 alongside the path. The
3× factor is a starting value, not a measured one.

### 3.5 reflect → consolidate

`Memory.reflect(bank)` issues `POST …/consolidate`, takes the returned
`operation_id`, and **polls the operations endpoint to a terminal state**,
raising when it ends `failed` or when polling times out.

Poll every **5 seconds for at most 9 minutes**, sitting just inside
`REFLECT_ACT`'s 10-minute `start_to_close_timeout` so the client raises a
diagnosable error rather than letting Temporal kill the activity on a timeout
that says nothing about consolidation. Both numbers are unmeasured guesses
(§8) and are expected to need tuning against a real bank.

Without the poll, `ReflectWorkflow` reports success for a consolidation that
failed — which its own docstring names as "a silent no-op … the failure mode
this whole feature exists to avoid."

The protocol method keeps the name `reflect`: it is the factory's vocabulary
(FR-404, `ReflectWorkflow`, `nightly-reflect.yaml`), and `ReflectWorkflow`'s
class name is a live Temporal contract that must not be renamed. Only the
meaning behind the seam changes.

### 3.6 Plumbing fixed in the same blast radius

- **The API key never enters Temporal history.** `RecallInput`, `RetainInput`,
  `WatermarkInput` and `ReflectInput` are serialized into workflow history.
  The key is read from the environment inside `_backend()` and is *not* a
  `MemoryConfig` field. `base_url`, `tenant` and `backend` remain on the
  activity inputs as they are today.
- **`ensure_bank`.** Idempotent `PUT /v1/{tenant}/banks/{bank_id}`, called
  lazily before first use per bank and cached in a module-level set. Otherwise
  every run's first recall 404s against a fresh volume.
- **Connection leak.** Today each activity invocation constructs an
  `httpx.AsyncClient` that is never closed. One cached client per
  `(base_url, tenant)` at module level.
- **`query_hash` unified.** `FakeMemory` hashes `bank|query|filters|cutoff`;
  the degraded path in `activities.py:49` omits the watermark. A single
  `recall_query_hash(bank, query, filters, watermark)` serves the fake, the
  real client and the degraded path, so snapshots stay comparable across
  backends.

## 4. Error handling

The existing asymmetry between recall and retain is correct and is preserved.

| Failure | Behaviour |
|---|---|
| recall — any HTTP or parse error | activity catches → empty `RecallSnapshot(degraded=True)`; the run continues (unchanged) |
| retain — any error | propagates → Temporal retries ×5; the deterministic `operation_id` makes that safe |
| `ensure_bank` fails | propagates into whichever call triggered it, inheriting that call's policy |
| consolidate ends `failed`, or polling exceeds budget | raises → `ReflectWorkflow` records the bank in `failed` and the nightly run goes red |
| filter key outside the tag allowlist | raises immediately — a programming error, not a runtime condition |

## 5. Testing

Two layers, because neither alone is sufficient.

### 5.1 Contract test — `tests/test_hindsight_contract.py`

Runs in ordinary CI: no container, no API key, no tokens.

The container's `/openapi.json` is vendored to
`tests/fixtures/hindsight-openapi.json`. The test drives the **real** client
through an `httpx.MockTransport` whose handler, rather than asserting a
hardcoded path, **resolves the outgoing request against the OpenAPI document** —
matching method and path template — and validates the request body against the
referenced schema. A request to a path the spec does not define fails the test.

This is the anti-fabrication layer: the current client cannot pass it, and no
future invented endpoint can either. It is deliberately not a mock that agrees
with the code.

### 5.2 Live test — `tests/test_hindsight_live.py`

Follows `tests/test_containment_live.py`'s convention:

```python
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("SDLC_LIVE_TESTS") != "1", …),
    pytest.mark.skipif(<localhost:8888 not answering>, …),
]
```

Three assertions, each of which mocks structurally cannot make:

1. **Round trip** — `ensure_bank` → retain → consolidate + poll → recall
   returns the retained text.
2. **Filters bite** — retain one `stage:clarify` item and one `stage:architect`
   item; recall with `filters={"stage": "clarify"}`; assert the architect item
   is absent. This is §1.2's defect, and only a live backend can prove it gone.
3. **Watermark cuts** — capture a watermark, retain a new item, recall, assert
   the new item is excluded.

It spends real LLM tokens through `HINDSIGHT_API_LLM_API_KEY`, hence the
opt-in gate.

### 5.3 Deleted

`tests/test_hindsight_client.py` is removed, not repaired. Its four tests
assert the fabricated API; keeping them green means keeping the fiction.

## 6. Implementation order

1. `docker compose up -d hindsight`; `GET :8888/openapi.json`; vendor it to
   `tests/fixtures/`. **Pin every path and body from that document**, including
   whether bank ids tolerate `:`. This settles the documentation contradiction
   noted in §8.
2. `recall_query_hash()` helper; `MemoryConfig.tenant`; env-only API key in
   `_backend()`.
3. Rewrite `HindsightMemory` against the vendored spec.
4. Contract test (§5.1), then live test (§5.2).
5. `ROADMAP.md` edits (§7).

`ReflectWorkflow`, `feature.py` and the `Memory` protocol are not edited.

## 7. ROADMAP edits

- **NFR-6** keeps `[x]` but gains a note: watermark pinning is exact on `fake`
  (entry-count cutoff) and a `mentioned_at` cutoff on `hindsight`, with §2.1's
  two caveats stated.
- **NFR-7** — "real Hindsight client for self-hosting" is the claim this work
  makes true for the first time. §5.2 is opt-in and does not run in CI, so the
  line stays `[x]` only once it has been **run once by hand against a live
  container and the run recorded in the commit message**. A green CI suite is
  not evidence for this line — that is what §1.1 already got wrong once.

## 8. Known unknowns

- **Two documented paths conflict.** `hindsight.vectorize.io/developer/api/retain`
  gives `POST …/memories/retain` while the API reference index lists
  `POST …/memories`; recall is documented as both `…/recall` and
  `…/memories/recall`. §6 step 1 resolves this from the container's own schema.
  No path is hardcoded before that step.
- **Which parameter bounds the result count** on recall — `max_tokens`,
  `budget` or `limit` — is documented inconsistently, so §3.4's over-fetch is
  expressed against whichever the vendored schema exposes.
- **Consolidation latency is unmeasured**, so §3.5's 5s/9min poll budget and
  `REFLECT_ACT`'s 10-minute ceiling may need tuning against a real bank.
- **Bank-id character rules** are unconfirmed (§3.1).
- **Whether `mentioned_at` echoes the `timestamp` we send** on retain is
  assumed by §2, not verified. If Hindsight instead stamps its own receipt
  time, the cutoff still works but reintroduces worker/server clock skew as an
  error term. §5.2's third assertion is what would expose this.

## 9. Out of scope

`/files/retain`; mental models; directives; entity and document endpoints;
memory curation (`PATCH …/memories/{id}`, invalidate/restore); dashboard
surfacing of memory state. None sit on the path to P3's exit criterion.
