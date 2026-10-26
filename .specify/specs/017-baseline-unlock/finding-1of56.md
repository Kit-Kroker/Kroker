# Finding: R1 theatre-box-office 1/56 score (FR-027)

Date: 2026-10-25
Investigation: T003 (read-only)
Runs analyzed:
- `bench-theatre-box-office-1792347162` (arm `zai-coding-plan-glm-5.3-flash`, oracle score 1/56, 0.018)
- `bench-theatre-box-office-1792359046` (arm `zai-coding-plan-glm-5.2`, oracle score 1/56, 0.018)

---

## 1. Sources tried and findings

1. **Scratch repositories in worker host (`D:/own/sdlc-scratch-repos/theatre-box-office`)**:
   - Both integration branches survived:
     - `sdlc/bench-theatre-box-office-1792347162/theatre-box-office#opencode#zai-coding-plan-glm-5.3-flash/integration` (commit `a6dbd12`)
     - `sdlc/bench-theatre-box-office-1792359046/theatre-box-office#opencode#zai-coding-plan-glm-5.2/integration` (commit `67f19d3`)
   - Both heads were checked out into isolated temporary worktrees and graded against the case oracle (`/srv/private-cases/theatre-box-office/oracle`) using `B/offline_checks.py` tree mode in `kroker-dev`.

2. **Case specification vs oracle contract**:
   - `theatre-box-office/case.yaml` `description` states the contract:
     `POST /productions {title} -> 2xx {production_id}`
   - `BenchmarkWorkflow` passes `spec.description` into `IdeaBrief`.
   - The oracle's shared test helper `make_performance` in `oracle/conftest.py:45-54` tests this exact contract:
     ```python
     r = await client.post("/productions", json={"title": "an evening show"})
     assert 200 <= r.status_code < 300, r.text
     production_id = r.json()["production_id"]
     ```

3. **Hand-grading execution results**:
   - Both runs executed pytest cleanly:
     - Exit code: **1** (normal pytest test failure, not a collection or setup crash).
     - JUnit totals: **tests=56, failures=55, errors=0, skips=0**.
     - Score: **1/56 = 0.018** (matches stored records exactly).
   - In both runs, exactly 55 of 56 tests call the shared helper `make_performance`, and all 55 failed at that call site:
     - **glm-5.3-flash (`1792347162`)**: `app.py:412` required `"name"` and rejected `"title"` with 400 Bad Request (`{"error":{"code":"invalid_name","message":"name is required"}}`).
     - **glm-5.2 (`1792359046`)**: `app.py:628` returned `{"id": production_id}` instead of `{"production_id": ...}`, causing `KeyError: 'production_id'`.
   - In both runs, the only passing test was the one that requests the seats of an unknown performance id, which does not call `make_performance` and correctly received a 404/refusal response.

4. **Pipeline stage localization**:
   - Inspected run pipeline artifacts under `runs/pipeline/bench-theatre-box-office-*`:
     - Requirements stage captured the contract correctly:
       - flash: `requirements-v35.json` specifies `POST /productions {title} ... returns 2xx {production_id}`.
       - 5.2: `requirements-v36.json` specifies `POST /productions {title} ... returns 2xx {production_id}`.
     - Drift occurred at the architecture and plan stages:
       - flash: `plan-v31.json` drifted to `POST /productions {"name":"Hamlet","tiers":[...]} returns 200 ... id 1`.
       - 5.2: `plan-v32.json` drifted to `POST /productions ... returns 200 with an integer id` (citing ADR-7).
   - The coding harness accurately implemented the drifted plan.

---

## 2. Root cause classification

- **(a) Model result (produced code is broken / contract mismatch by the model): CONFIRMED.**
- **(b) Case or oracle defect: RULED OUT.** Case description and oracle contract agree.
- **(c) Harness defect: RULED OUT.** The brief was passed faithfully to the pipeline; requirements captured it; the planner/architect model drifted the schema contract.

This is NOT a harness cause (SG-5 does not fire). The R1 result is a genuine model outcome.

---

## 3. FR-025 signal evaluation

- **FR-025 rule**: Flag collection/import errors when `exit_code in (2, 4)` or `errors * 2 >= total > 0`.
- **Observed signal**: `exit_code = 1`, `errors = 0`, `failures = 55`, `total = 56`.
- **Would FR-025 have flagged it? NO.**
  - `make_performance` is an `async def` helper called within test bodies, not a pytest `@pytest.fixture`. Failures in test helpers count as test **failures**, not test setup/collection **errors**.
  - FR-025 is designed specifically to detect unimportable or uncollectable trees (syntax errors, broken imports, missing top-level dependencies, pytest collection aborts).
  - Because collection succeeded and all 56 tests executed, FR-025 did not flag it, which is correct for its defined scope.
  - Research decision **D-8** is amended to record this distinction and clarify that FR-025 guards collection/import failures, not shared test-helper assertion failures.
