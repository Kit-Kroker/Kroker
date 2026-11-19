# Org-Bank Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `org_bank` curated writers — the nightly ReflectWorkflow promotes gotchas recurring in ≥2 project banks into org, then consolidates org — closing FR-404's org half (E-25).

**Architecture:** Pure grouping logic in a new `memory/promote.py`; a new `promote_org_learnings` activity beside the existing memory activities; ReflectWorkflow runs it between project reflects and the org reflect. Schedule assets carry two new defaulted fields, so old schedules decode unchanged. No stage is touched.

**Tech Stack:** Python 3.13, Temporalio (workflow + activities + time-skipping test env), Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-11-19-org-bank-promotion-design.md`

## Global Constraints

- Build: `uv sync --frozen --extra dev`. Plain `pytest` runs the fast tier only; workflow tests need `pytest -m temporal tests/retro/test_reflect_workflow.py`. Never run `-m live` / `-m prompt_eval` tiers.
- 1000-line ceiling per file — all touched files are far under; keep them that way.
- Wire contracts, never renamed: the `ReflectWorkflow` class name, the `reflect` activity name, the `nightly-reflect` schedule id.
- Schedules are server-side state, applied only via `sdlc schedules apply` — this plan ships the asset file and its tests; nothing auto-applies.
- `ruff check .`, `ruff format .`, `mypy` must be clean at every commit.
- Historical records (`docs/superpowers/`, `.specify/`, dated `docs/reports/`) are immutable — Task 6 touches only living docs.

## Review Focus

1. **Same-bank recurrence** — a gotcha appearing twice in one bank and nowhere else must NOT promote (distinct banks counted, not occurrences). → Task 2, `test_one_bank_twice_does_not_promote`.
2. **Near-duplicate texts** — same gotcha with different casing/punctuation/whitespace in two banks must group as one. → Task 2, `test_normalization_groups_case_and_punctuation_variants`.
3. **Threshold of 1** — `promote_min_projects=1` in an asset must fail validation at load (else org mirrors a single project). → Task 5, `test_reflect_action_rejects_min_projects_below_two`.
4. **Pre-existing live schedule** — a server-side schedule whose recorded args predate the new fields must still validate (org_bank defaults to None). → Task 5, `test_from_temporal_tolerates_legacy_args_without_org_fields`.
5. **Backend outage during promotion** — a raised recall must fail the nightly workflow visibly, never silently skip org. → Task 4, `test_promotion_failure_fails_the_run`.

---

### Task 1: FakeMemory keeps kind and honors kind-filtered recall

**Files:**
- Modify: `src/sdlc/memory/fake.py:17-53`
- Test: `tests/test_memory_fake.py`

**Interfaces:**
- Consumes: `RetainItem.kind` (exists, `MemoryKind`).
- Produces: `FakeMemory.recall(bank, query, filters, watermark)` matches Hindsight's filterable set: `filters["kind"]` filters on the retained item's kind; other filter keys keep matching metadata. `_Entry` retains the kind.

- [ ] **Step 1: Write the failing tests** in `tests/test_memory_fake.py`

```python
@pytest.mark.asyncio
async def test_recall_filters_by_kind():
    mem = FakeMemory()
    await mem.retain(RetainItem(kind=MemoryKind.GOTCHA, bank="b", text="uv runs tests via uv run pytest", metadata={}))
    await mem.retain(RetainItem(kind=MemoryKind.STAGE_SUMMARY, bank="b", text="clarify done", metadata={}))
    snap = await mem.recall("b", "query", {"kind": "gotcha"}, None)
    assert snap.items == ["uv runs tests via uv run pytest"]


@pytest.mark.asyncio
async def test_recall_without_kind_filter_returns_all_kinds():
    # retained a gotcha + a stage_summary as above
    snap = await mem.recall("b", "query", {}, None)
    assert len(snap.items) == 2
```

Use fresh bank names per test (the double is a module singleton in activity tests; here instances are local but keep names distinct anyway).

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_memory_fake.py -q` → FAIL (kind filter matches nothing today: `_Entry` drops kind, so the filter checks metadata it never has).
- [ ] **Step 3: Implement** — `_Entry` gains a `kind` field stored from `item.kind`; `recall` keeps existing metadata matching and additionally honors `filters["kind"]` compared against `e.kind.value`. Match Hindsight semantics: kind filters are exact string equality.
- [ ] **Step 4: Run** — `pytest tests/test_memory_fake.py -q` → PASS. Then `pytest tests/ -q -k memory` → no regressions in the memory suites.
- [ ] **Step 5: Commit** — `git add src/sdlc/memory/fake.py tests/test_memory_fake.py && git commit -m "fix(memory): FakeMemory keeps kind and honors kind-filtered recall (E-25)"`

### Task 2: Pure promotion grouping logic

**Files:**
- Create: `src/sdlc/memory/promote.py`
- Test: `tests/test_memory_promote.py` (new)

**Interfaces:**
- Produces (Task 3 consumes all three):
  - `GOTCHA_QUERY: str` — the pinned recall query, value exactly `"recurring cross-project gotchas and stack knowledge"`.
  - `normalize_gotcha(text: str) -> str` — lowercase, strip every non-alphanumeric, collapse runs of whitespace to one space, strip ends.
  - `promotions(items_by_bank: Mapping[str, Sequence[str]], *, org_bank: str, min_projects: int = 2) -> list[RetainItem]` — every group whose **distinct bank count** ≥ `min_projects` becomes one `RetainItem(kind=MemoryKind.GOTCHA, bank=org_bank, text=<lexicographically smallest raw text in the group>, metadata={"promoted_from": ",".join(sorted(banks))})`; result sorted by `text`.

- [ ] **Step 1: Write the failing tests** in `tests/test_memory_promote.py` — pure sync tests, no async:

```python
def test_same_gotcha_in_two_banks_promotes_once():
    items = promotions(
        {"project:a": ["uv run pytest, not pytest"], "project:b": ["uv run pytest, not pytest"]},
        org_bank="org",
    )
    assert len(items) == 1
    assert items[0].bank == "org"
    assert items[0].kind is MemoryKind.GOTCHA
    assert items[0].metadata == {"promoted_from": "project:a,project:b"}


def test_one_bank_twice_does_not_promote():
    assert promotions({"project:a": ["x", "x"]}, org_bank="org") == []


def test_normalization_groups_case_and_punctuation_variants():
    items = promotions(
        {"project:a": ["UV run pytest!"], "project:b": ["uv run pytest"]}, org_bank="org"
    )
    assert len(items) == 1
    assert items[0].text == "UV run pytest!"  # lexicographically smallest RAW text


def test_single_project_never_promotes():
    assert promotions({"project:a": ["x"], "project:b": []}, org_bank="org") == []


def test_min_projects_three_requires_three_banks():
    two = {"project:a": ["x"], "project:b": ["x"]}
    assert promotions(two, org_bank="org", min_projects=3) == []


def test_identical_input_yields_identical_output():
    src = {"project:b": ["zeta", "alpha"], "project:a": ["alpha", "zeta"]}
    assert promotions(src, org_bank="org") == promotions(src, org_bank="org")


def test_result_is_sorted_by_text():
    items = promotions(
        {"project:a": ["b-item", "a-item"], "project:b": ["a-item", "b-item"]}, org_bank="org"
    )
    assert [i.text for i in items] == ["a-item", "b-item"]


def test_gotcha_query_is_pinned():
    assert GOTCHA_QUERY == "recurring cross-project gotchas and stack knowledge"
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_memory_promote.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement `src/sdlc/memory/promote.py`** — module docstring stating the prior-art rule (org = stack knowledge recurring in 2+ projects; project facts stay project-side) with a link to the spec. Normalize via `re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()` (this handles both the non-alphanumeric strip and whitespace collapse in one pass — note it maps punctuation to a single space, which is the intended normalization). Group with `dict[str, tuple[set[str], list[str]]]` keyed by `normalize_gotcha(text)`.
- [ ] **Step 4: Run** — `pytest tests/test_memory_promote.py -q` → PASS.
- [ ] **Step 5: Commit** — `git add src/sdlc/memory/promote.py tests/test_memory_promote.py && git commit -m "feat(memory): cross-project gotcha promotion grouping (E-25)"`

### Task 3: The promote_org_learnings activity

**Files:**
- Modify: `src/sdlc/memory/activities.py` (append after `reflect`)
- Modify: `src/sdlc/worker.py:91-96` (import) and the activities list at `worker.py:215` (register beside `reflect`)
- Test: `tests/test_memory_promote.py` (extend)

**Interfaces:**
- Consumes: Task 2's `promotions`, `GOTCHA_QUERY`; existing `_backend`, `scrub`, `RetainItem`.
- Produces (Task 4 consumes): activity `promote_org_learnings(inp: PromoteInput) -> int` and

```python
@dataclass
class PromoteInput:
    project_banks: list[str]
    org_bank: str
    min_projects: int = 2
    backend: str = "fake"
    base_url: str = "http://localhost:8888"
```

Behavior: for each project bank, `memory.recall(bank, GOTCHA_QUERY, {"kind": MemoryKind.GOTCHA.value}, None)` — recall exceptions **propagate** (fail-visible, unlike the `recall_snapshot` activity's degrade: this is the nightly job, whose contract is no silent no-op). Then `promotions(...)` over the collected per-bank items; each promoted item is retained with `scrub(item.text)` (same boundary policy as the `retain` activity). Returns the number retained.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_memory_promote.py`; direct activity calls on the fake backend, unique bank names per test — the fake is a module singleton):

```python
def test_promote_is_a_temporal_activity():
    assert getattr(promote_org_learnings, "__temporal_activity_definition", None) is not None


def test_promote_is_registered_on_the_worker():
    # test_triage_registry.py's source-grep convention: the original FR-404
    # bug was a registered-looking activity nobody called or served.
    src = pathlib.Path("src/sdlc/worker.py").read_text(encoding="utf-8")
    assert "promote_org_learnings" in src, "not registered in worker.py"


@pytest.mark.asyncio
async def test_promote_end_to_end_on_fake_backend():
    await retain(RetainInput(item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:e2e-a", text="uv run pytest", metadata={})))
    await retain(RetainInput(item=RetainItem(kind=MemoryKind.GOTCHA, bank="project:e2e-b", text="uv run pytest", metadata={})))
    n = await promote_org_learnings(PromoteInput(project_banks=["project:e2e-a", "project:e2e-b"], org_bank="org:e2e"))
    assert n == 1
    snap = await recall_snapshot(RecallInput(bank="org:e2e", query="q", backend="fake"))
    assert snap.items == ["uv run pytest"]


@pytest.mark.asyncio
async def test_promote_scrubs_before_retain():
    # gotcha text "key sk-<40 alnum chars> fix" retained into two banks;
    # promoted org text contains "[REDACTED_API_KEY]" and not the raw key


@pytest.mark.asyncio
async def test_promote_with_no_recurrence_returns_zero():
    # one gotcha in one bank only → returns 0, org recall empty
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_memory_promote.py -q` → FAIL (no `PromoteInput`).
- [ ] **Step 3: Implement** the dataclass + activity in `memory/activities.py`; register in `worker.py` (import block at :91, list entry beside `reflect` at :215).
- [ ] **Step 4: Run** — `pytest tests/test_memory_promote.py tests/test_memory_activities.py -q` → PASS.
- [ ] **Step 5: Commit** — `git add src/sdlc/memory/activities.py src/sdlc/worker.py tests/test_memory_promote.py && git commit -m "feat(memory): promote_org_learnings activity, registered on the worker (E-25)"`

### Task 4: ReflectWorkflow org path

**Files:**
- Modify: `src/sdlc/workflows/reflect.py`
- Test: `tests/retro/test_reflect_workflow.py` (extend; follows its fake-activity + `EVENTS`-list pattern)

**Interfaces:**
- Consumes: Task 3's `promote_org_learnings`/`PromoteInput`.
- Produces (Task 5 consumes): `ReflectScheduleInput` gains `org_bank: str | None = None` and `promote_min_projects: int = 2`. When `org_bank` is set, after the project-bank loop: run `promote_org_learnings` (its own try block; failure appends `f"promote:{inp.org_bank}"` to `failed`), then reflect the org bank (failure appends the bank name, same as project banks). Both are attempted even if one fails. Return value stays `len(inp.banks)`. Imports join the existing `imports_passed_through` block. Activity config: reuse `REFLECT_ACT`.

- [ ] **Step 1: Write the failing tests** — add a `PROMOTED: list[PromoteInput]` recorder and a `fake_promote` activity def (name `"promote_org_learnings"`), plus an `ORDER: list[str]` both fakes append to; extend the `_reset` fixture and the `Worker(activities=[...])` list:

```python
async def test_org_path_promotes_then_reflects_org():
    # banks=["project:a","project:b"], org_bank="org"
    count = await _run(env, ReflectScheduleInput(banks=["project:a", "project:b"], org_bank="org"))
    assert count == 2                      # return stays len(banks)
    assert PROMOTED[0].org_bank == "org"
    assert ORDER[-2:] == ["promote:org", "reflect:org"]


async def test_no_org_bank_runs_no_promotion():
    # org_bank unset → REFLECTED == banks, PROMOTED == []
    # (back-compat shape: pre-change schedules decode to exactly this input)


async def test_promotion_failure_fails_the_run():
    # fake promote raises → WorkflowFailureError whose message names "promote:org"


async def test_org_reflect_failure_fails_the_run():
    # fake promote fine, FAIL_BANKS={"org"} → WorkflowFailureError naming "org"
```

- [ ] **Step 2: Run to verify failure** — `pytest -m temporal tests/retro/test_reflect_workflow.py -q` → new tests FAIL (no org field).
- [ ] **Step 3: Implement** the two fields and the org block in `workflows/reflect.py` per Interfaces. Update the module docstring: project banks reflect, then (when configured) gotchas promote to org and org reflects — one job, FR-404 whole.
- [ ] **Step 4: Run** — `pytest -m temporal tests/retro/test_reflect_workflow.py -q` → PASS, including the two pre-existing tests unchanged.
- [ ] **Step 5: Commit** — `git add src/sdlc/workflows/reflect.py tests/retro/test_reflect_workflow.py && git commit -m "feat(workflows): ReflectWorkflow promotes gotchas to org and reflects it (FR-404 org half)"`

### Task 5: Schedule assets carry the org fields; nightly-reflect gains org

**Files:**
- Modify: `src/sdlc/schedules/models.py:24-30` (`ReflectAction`)
- Modify: `src/sdlc/schedules/apply.py:44-103` (`to_temporal`, `from_temporal`)
- Modify: `schedules/nightly-reflect.yaml`
- Test: `tests/test_schedule_apply.py`, `tests/test_nightly_reflect_asset.py`

**Interfaces:**
- Consumes: Task 4's `ReflectScheduleInput` fields.
- Produces: `ReflectAction` gains `org_bank: str | None = None` and `promote_min_projects: int = Field(default=2, ge=2)`; `to_temporal` passes both into `ReflectScheduleInput`; `from_temporal` reconstructs both. The shipped asset sets `org_bank: "org"` under `action`.

- [ ] **Step 1: Write the failing tests** —
  - `tests/test_schedule_apply.py`: round-trip `from_temporal(a.id, to_temporal(asset_with_org)) == asset_with_org`; `test_reflect_action_rejects_min_projects_below_two` (`ReflectAction(banks=["project:default"], promote_min_projects=1)` raises `ValidationError`); `test_from_temporal_tolerates_legacy_args_without_org_fields` (build a `ReflectScheduleInput` from a dict lacking both new fields, feed it through the `from_temporal` reconstruction path, expect `org_bank is None`, `promote_min_projects == 2`).
  - `tests/test_nightly_reflect_asset.py`: rework `test_nightly_reflect_is_project_scoped_only` — `banks` entries still all start with `project:` (org never rides `banks`), and add `test_nightly_reflect_promotes_to_org`: `a.action.org_bank == "org"`; extend `test_shipped_asset_translates_to_a_temporal_schedule` to assert the first workflow arg carries `org_bank == "org"`. Update the module docstring: the guard now pins that org reaches the job via the promotion field, not `banks`.
- [ ] **Step 2: Run to verify failure** — `pytest tests/test_schedule_apply.py tests/test_nightly_reflect_asset.py tests/test_schedule_loader.py tests/maintenance/test_schedules.py -q` → new tests FAIL.
- [ ] **Step 3: Implement** the model fields, the `to_temporal`/`from_temporal` plumbing, and the asset: add `org_bank: "org"` under `action:` and rewrite the YAML header comment — org gets writers via nightly promotion (E-25), applied with `sdlc schedules apply`.
- [ ] **Step 4: Run** — the Step 2 command → PASS. Then `pytest -q` (fast suite) → green.
- [ ] **Step 5: Commit** — `git add src/sdlc/schedules/models.py src/sdlc/schedules/apply.py schedules/nightly-reflect.yaml tests/test_schedule_apply.py tests/test_nightly_reflect_asset.py && git commit -m "feat(schedules): reflect assets carry org_bank + threshold; nightly-reflect promotes to org (E-25)"`

### Task 6: Docs sweep and close-out

**Files:**
- Modify: `ROADMAP.md:338` (FR-404), `ROADMAP.md:302` (stage-14 note), `ROADMAP.md:612` (§9 pointer) — refresh stale sentences only
- Modify: `docs/roadmap/filesystem-first.md:79` (E-25 → `[x]`), `docs/roadmap/agent-architecture-plan.md:81` (AP-5.5 annotation)
- Modify: `BENCHMARK.md:215-216, 337, 420, 825-826` (stale "org has no writers" / "stage 14 never runs" notes)
- Test: none — verification is grep + full gates

**Interfaces:**
- Consumes: everything landed in Tasks 1–5.
- Produces: the tracker telling the truth.

- [ ] **Step 1: Flip FR-404 to `[x]`** at `ROADMAP.md:338` — follow the FR-303 close-out style: dated `*Landed …*` note naming the mechanism (nightly promotion via `promote_org_learnings`, org reflect, spec link `docs/superpowers/specs/2026-11-19-org-bank-promotion-design.md`) and the honest caveat: only `project:default` exists today, so promotion first fires when a second project bank runs with memory on.
- [ ] **Step 2: Close E-25** at `docs/roadmap/filesystem-first.md:79` — `[x]`, dated note, spec link. Fix `ROADMAP.md:302` (drop "The `org_bank`-writer half stays unbuilt (E-25); retro is project scope only" → org promotion is the nightly job's, retro stays project-scope per run) and the E-25 sentence in `ROADMAP.md:612`. Annotate AP-5.5 (`agent-architecture-plan.md:81`): promotion landed 2026-11-19; verified-only retention and pruning-by-use still open.
- [ ] **Step 3: Refresh BENCHMARK.md** — the four stale passages say org has no writers and/or stage 14 never runs; both false now. Rewrite each to current truth: retro built (E-32), org has promotion writers, the SC-4/SC-6 *mechanism* is complete — numbers still pending real runs.
- [ ] **Step 4: Verify no stale claims remain** — `grep -rn "no writers" ROADMAP.md BENCHMARK.md docs/roadmap/` → empty; `grep -n "E-25" ROADMAP.md` → only the closed-out entries. Historical specs/reports stay untouched.
- [ ] **Step 5: Full gates** — `pytest -q && pytest -m temporal tests/retro/test_reflect_workflow.py -q && ruff check . && ruff format --check . && mypy` → all green.
- [ ] **Step 6: Commit** — `git add ROADMAP.md BENCHMARK.md docs/roadmap/ && git commit -m "docs: close FR-404/E-25 — org bank gets promotion writers (nightly reflect)"`
