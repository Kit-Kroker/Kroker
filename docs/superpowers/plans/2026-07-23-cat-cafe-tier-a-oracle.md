# Cat-café Tier-A Oracle (E-34) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the cat-café decomposition case a held-out oracle (Tier-A grade) by freezing an interface contract in its case manifest and shipping an oracle suite validated in CI against a reference implementation.

**Architecture:** Assets-only increment — zero `src/` changes. The existing E-31 machinery (`grade_oracle`, `ToolchainAdapter.oracle_test_cmd`, `language:` dispatch) does all grading; this plan only adds the case assets it reads, plus a CI stand-in proving the oracle discriminates. Spec: `docs/superpowers/specs/2026-07-23-cat-cafe-tier-a-oracle-design.md`.

**Tech Stack:** Python 3.14, pytest + pytest-asyncio + httpx (already dev deps), pure-ASGI reference app (no framework), YAML case manifests.

## Global Constraints

- **Zero `src/sdlc/` changes.** If a task seems to need one, stop — the plan is wrong.
- The kata's functional requirements in `case.yaml` `description` must stay byte-identical; the contract is **appended** below them. `tests/test_golden_case_loads.py::test_cat_cafe_description_preserves_every_activity` must keep passing.
- Oracle fairness rule (spec §4): every assertion must hold under *any* reasonable ruleset — extremes only, scenarios crafted against the app's **own** `GET /floorplan` coordinates; ambiguous outcomes accept a set of answers (`playing` or `fighting`).
- Oracle determinism: no sleeps, no randomness, no wall-clock reads; all timestamps supplied by the oracle relative to a fixed base.
- Activity enum strings, exact: `sleeping | eating | drinking | litter_box | playing | fighting` or `null`.
- The reference implementation lives under `tests/fixtures/`, is never shipped to a worktree, and must not auto-start any simulator (it has none at all).
- Repo pytest collects only `tests/` (`testpaths` in `pyproject.toml`); oracle files run exclusively via the tmpdir self-test.
- Run tests from the repo root: `python -m pytest tests/<file> -v` (Windows; `pytest` on PATH also fine).

---

### Task 1: Freeze the interface contract in `case.yaml`

**Files:**
- Modify: `benchmarks/cases/cat-cafe-monitoring/case.yaml`
- Test: `tests/test_golden_case_loads.py` (append two tests)

**Interfaces:**
- Consumes: `sdlc.benchmarks.cli.load_case_spec` (existing), `CaseSpec.language` (existing E-31 field).
- Produces: the frozen contract text that Task 2's oracle asserts against, and `language: python` which opts the case into `grade_oracle` — no code consumes anything new; `BenchmarkWorkflow` picks up `language` automatically.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_golden_case_loads.py` (after `test_cat_cafe_description_preserves_every_activity`):

```python
def test_cat_cafe_declares_python_language():
    """E-34: language set => the case opts into E-31 oracle grading."""
    spec = load_case_spec(str(CAT_CASE))
    assert spec.language == "python"


def test_cat_cafe_description_freezes_the_interface_contract():
    """The oracle grades through this contract; if a marker vanishes the
    oracle is asserting against an interface the case no longer freezes."""
    body = load_case_spec(str(CAT_CASE)).description
    for marker in ("app:app", "POST /telemetry", "GET /floorplan",
                   "GET /cats", "must not auto-start"):
        assert marker in body, f"contract marker {marker!r} missing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_golden_case_loads.py -v -k cat_cafe`
Expected: the two new tests FAIL (`spec.language` is `None`; markers missing); the four existing cat-café tests PASS.

- [ ] **Step 3: Edit `case.yaml`**

In `benchmarks/cases/cat-cafe-monitoring/case.yaml`:

(a) Append to the `description:` block (after the existing last line `movement history for the last 24 hours.`, same indentation, one blank line between):

```yaml
  Interface contract (frozen — graded through it; not a functional
  requirement and it changes none of the tasks above):
  Implement in Python. Expose an ASGI application object importable as
  `app:app` (module `app.py` at the repo root, attribute named `app`).
  Importing `app:app` must not auto-start the random telemetry generator;
  the simulation runs only when launched explicitly (e.g. `python app.py`).
    POST /telemetry {cat_id, x, y, breathing_rate, timestamp} -> 2xx;
      the reading is processed exactly as if a collar emitted it, and a
      reading for a new cat_id begins tracking that cat.
    GET /floorplan -> 200 {"zones": [{kind, x, y}, ...]} with kind one of
      rest_area | litter_box | water_bowl | food_bowl; richer zone shapes
      are allowed and all coordinates are your choice.
    GET /cats -> 200 [{id, x, y, activity, at_risk}, ...]; activity is one
      of sleeping | eating | drinking | litter_box | playing | fighting,
      or null when undetermined; at_risk is a boolean.
    GET /cats/{id} -> 200 detail with the latest reading and history: that
      cat's readings {timestamp, x, y, breathing_rate} from the last 24
      hours relative to the cat's newest reading (never the wall clock);
      unknown id -> 404.
  Timestamps are ISO-8601 strings supplied by the caller; detection and
  the 24-hour window are computed from telemetry timestamps.
```

(b) Add the language line directly under `mode: greenfield`:

```yaml
language: python
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_golden_case_loads.py tests/test_load_case_assets.py -v`
Expected: ALL PASS (including `test_cat_cafe_description_preserves_every_activity` — the functional text is untouched).

- [ ] **Step 5: Commit**

```bash
git add benchmarks/cases/cat-cafe-monitoring/case.yaml tests/test_golden_case_loads.py
git commit -m "feat(benchmarks): freeze cat-cafe interface contract, opt into oracle grading (E-34)"
```

---

### Task 2: Author the held-out oracle suite

**Files:**
- Create: `benchmarks/cases/cat-cafe-monitoring/oracle/conftest.py`
- Create: `benchmarks/cases/cat-cafe-monitoring/oracle/test_activity.py`
- Create: `benchmarks/cases/cat-cafe-monitoring/oracle/test_risk.py`
- Create: `benchmarks/cases/cat-cafe-monitoring/oracle/test_monitoring.py`
- Test: `tests/test_cat_cafe_oracle.py` (files-exist half; the run-it half is Task 3)

**Interfaces:**
- Consumes: the Task 1 contract (`app:app`, `/telemetry`, `/floorplan`, `/cats`, `/cats/{id}`).
- Produces: helper functions in `oracle/conftest.py` used by the three test modules via `from conftest import ...` (pytest inserts the oracle dir into `sys.path` — same mechanism the todo-api oracle relies on): `zone(client, kind) -> (float, float)`, `feed(client, cat_id, readings)` with `readings: list[(offset_s, x, y, bpm)]`, `cat(client, cat_id) -> dict`, `far_from_zones(client) -> (float, float)`, `stationary(x, y, bpm, n=5, step=5) -> list`.

- [ ] **Step 1: Write the failing existence test**

Create `tests/test_cat_cafe_oracle.py`:

```python
"""The cat-cafe held-out oracle exists and discriminates (E-34, spec §6)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ORACLE = (REPO_ROOT / "benchmarks" / "cases" / "cat-cafe-monitoring"
          / "oracle")


def test_oracle_suite_files_exist():
    for name in ("conftest.py", "test_activity.py", "test_risk.py",
                 "test_monitoring.py"):
        assert (ORACLE / name).is_file(), f"missing oracle/{name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cat_cafe_oracle.py -v`
Expected: FAIL — `missing oracle/conftest.py`.

- [ ] **Step 3: Write `oracle/conftest.py`**

```python
"""Held-out oracle fixtures for cat-cafe-monitoring (E-34). Never seen by
the run: copied into the produced worktree only at grade time. Drives the
frozen ASGI contract (app:app) via httpx. Scenarios are crafted against
the app's OWN /floorplan coordinates, so no coordinate or threshold is
pinned and the kata's "rules are up to you" freedom survives (fairness
rule, spec §4). Deterministic: no sleeps, no randomness, no wall clock —
all timestamps derive from a fixed BASE."""
import os
import sys
from datetime import datetime, timedelta, timezone

import httpx
import pytest_asyncio

# The produced repo root is the parent of this oracle/ dir once copied in.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASE = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def client():
    import app as produced          # contract: module app.py exposes `app`
    transport = httpx.ASGITransport(app=produced.app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://testserver") as c:
        yield c


async def zone(client, kind):
    """The app's own coordinates for the first zone of the given kind."""
    r = await client.get("/floorplan")
    assert r.status_code == 200
    zones = r.json()["zones"]
    match = [z for z in zones if z["kind"] == kind]
    assert match, f"floorplan exposes no {kind!r} zone"
    return float(match[0]["x"]), float(match[0]["y"])


async def far_from_zones(client):
    """A spot unambiguously outside every zone the app declared."""
    r = await client.get("/floorplan")
    zs = r.json()["zones"]
    m = max([abs(float(z["x"])) for z in zs]
            + [abs(float(z["y"])) for z in zs])
    return m + 100.0, m + 100.0


async def feed(client, cat_id, readings):
    """POST a timestamped sequence; readings = [(offset_s, x, y, bpm)]."""
    for off, x, y, bpm in readings:
        ts = (BASE + timedelta(seconds=off)).isoformat()
        r = await client.post("/telemetry", json={
            "cat_id": cat_id, "x": x, "y": y,
            "breathing_rate": bpm, "timestamp": ts})
        assert 200 <= r.status_code < 300


async def cat(client, cat_id):
    """The cat's row from GET /cats."""
    r = await client.get("/cats")
    assert r.status_code == 200
    rows = [c for c in r.json() if str(c["id"]) == str(cat_id)]
    assert rows, f"cat {cat_id!r} not tracked"
    return rows[0]


def stationary(x, y, bpm, n=5, step=5):
    """n readings step seconds apart, not moving (collar cadence is 5s)."""
    return [(i * step, x, y, bpm) for i in range(n)]
```

- [ ] **Step 4: Write `oracle/test_activity.py`**

```python
"""Task 1 oracle: activity detection at the app's own zone coordinates.
Extremes only — any reasonable ruleset passes (fairness rule, spec §4)."""
import pytest

from conftest import cat, far_from_zones, feed, stationary, zone


@pytest.mark.asyncio
async def test_stationary_at_food_bowl_is_eating(client):
    x, y = await zone(client, "food_bowl")
    await feed(client, "c-eat", stationary(x, y, bpm=40))
    assert (await cat(client, "c-eat"))["activity"] == "eating"


@pytest.mark.asyncio
async def test_stationary_at_water_bowl_is_drinking(client):
    x, y = await zone(client, "water_bowl")
    await feed(client, "c-drink", stationary(x, y, bpm=40))
    assert (await cat(client, "c-drink"))["activity"] == "drinking"


@pytest.mark.asyncio
async def test_resting_low_bpm_is_sleeping(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-sleep", stationary(x, y, bpm=20))
    assert (await cat(client, "c-sleep"))["activity"] == "sleeping"


@pytest.mark.asyncio
async def test_stationary_at_litter_box_is_litter_box(client):
    x, y = await zone(client, "litter_box")
    await feed(client, "c-litter", stationary(x, y, bpm=40))
    assert (await cat(client, "c-litter"))["activity"] == "litter_box"


@pytest.mark.asyncio
async def test_colocated_fast_high_bpm_is_playing_or_fighting(client):
    """Two cats circling each other away from every zone, fast, high bpm.
    playing vs fighting is genuinely ambiguous — either passes."""
    fx, fy = await far_from_zones(client)
    a = [(i * 5, fx + (1.5 if i % 2 else -1.5), fy, 90) for i in range(6)]
    b = [(i * 5, fx + (-1.5 if i % 2 else 1.5), fy + 0.5, 90)
         for i in range(6)]
    await feed(client, "c-rough1", a)
    await feed(client, "c-rough2", b)
    assert (await cat(client, "c-rough1"))["activity"] in (
        "playing", "fighting")
```

- [ ] **Step 5: Write `oracle/test_risk.py`**

```python
"""Task 2 oracle: life/health risk flag. Extremes only — the research-
grounded floor was >35 bpm at rest, so sustained 180 is unambiguous risk,
~5 bpm is unambiguous risk, and 25 bpm resting is unambiguously normal."""
import pytest

from conftest import cat, feed, stationary, zone


@pytest.mark.asyncio
async def test_sustained_180_bpm_at_rest_is_risk(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-tachy", stationary(x, y, bpm=180))
    assert (await cat(client, "c-tachy"))["at_risk"] is True


@pytest.mark.asyncio
async def test_sustained_5_bpm_is_risk(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-brady", stationary(x, y, bpm=5))
    assert (await cat(client, "c-brady"))["at_risk"] is True


@pytest.mark.asyncio
async def test_calm_resting_cat_is_not_risk(client):
    x, y = await zone(client, "rest_area")
    await feed(client, "c-calm", stationary(x, y, bpm=25))
    assert (await cat(client, "c-calm"))["at_risk"] is False
```

- [ ] **Step 6: Write `oracle/test_monitoring.py`**

```python
"""Task 2 oracle: movement reflection, per-cat history, the 24h window
relative to the cat's newest reading, and 404 on unknown ids."""
import pytest

from conftest import cat, feed

H = 3600


@pytest.mark.asyncio
async def test_post_moves_cat_on_cats_view(client):
    await feed(client, "c-move", [(0, 1.0, 1.0, 40), (5, 3.0, 4.0, 40)])
    row = await cat(client, "c-move")
    assert (float(row["x"]), float(row["y"])) == (3.0, 4.0)


@pytest.mark.asyncio
async def test_history_contains_injected_readings(client):
    await feed(client, "c-hist", [(0, 1.0, 2.0, 40), (5, 1.5, 2.0, 41)])
    r = await client.get("/cats/c-hist")
    assert r.status_code == 200
    hist = r.json()["history"]
    assert len(hist) >= 2
    rates = {float(h["breathing_rate"]) for h in hist}
    assert {40.0, 41.0} <= rates


@pytest.mark.asyncio
async def test_history_window_is_24h_from_newest_reading(client):
    await feed(client, "c-old", [
        (0, 1.0, 1.0, 30),           # 25h before newest -> outside window
        (25 * H, 2.0, 2.0, 44),      # newest reading
        (2 * H, 1.5, 1.5, 33),       # 23h before newest -> inside window
    ])
    r = await client.get("/cats/c-old")
    assert r.status_code == 200
    rates = [float(h["breathing_rate"]) for h in r.json()["history"]]
    assert 30.0 not in rates, "reading older than 24h leaked into history"
    assert 33.0 in rates and 44.0 in rates


@pytest.mark.asyncio
async def test_unknown_cat_is_404(client):
    r = await client.get("/cats/no-such-cat")
    assert r.status_code == 404
```

- [ ] **Step 7: Run the existence test to verify it passes**

Run: `python -m pytest tests/test_cat_cafe_oracle.py -v`
Expected: PASS (1 test). The oracle can't execute yet — nothing satisfies the contract until Task 3's reference app.

- [ ] **Step 8: Commit**

```bash
git add benchmarks/cases/cat-cafe-monitoring/oracle tests/test_cat_cafe_oracle.py
git commit -m "feat(benchmarks): held-out oracle suite for cat-cafe (E-34)"
```

---

### Task 3: Reference implementation + green/red self-test

**Files:**
- Create: `tests/fixtures/cat_cafe_ref/app.py`
- Modify: `tests/test_cat_cafe_oracle.py` (add the run-it half)

**Interfaces:**
- Consumes: the oracle suite from Task 2 (copied into a tmpdir), the Task 1 contract.
- Produces: `tests/fixtures/cat_cafe_ref/app.py` exposing module attribute `app` (pure-ASGI callable) and module global `RISK_ENABLED: bool` read at call time — the red half of the self-test appends `RISK_ENABLED = False` to a copy to produce the broken variant.

- [ ] **Step 1: Write the failing self-tests**

Append to `tests/test_cat_cafe_oracle.py`:

```python
import shutil
import subprocess
import sys

import pytest

REF_APP = REPO_ROOT / "tests" / "fixtures" / "cat_cafe_ref" / "app.py"


def _run_oracle(tmp_path, break_risk=False):
    """Copy oracle + reference app into a fake produced worktree and run
    pytest there — the same shape grade_oracle uses, minus git."""
    wt = tmp_path / "wt"
    wt.mkdir()
    shutil.copytree(ORACLE, wt / "oracle")
    app_text = REF_APP.read_text(encoding="utf-8")
    if break_risk:
        # RISK_ENABLED is read at call time, so appending overrides it.
        app_text += "\nRISK_ENABLED = False\n"
    (wt / "app.py").write_text(app_text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "pytest", "oracle", "-q",
         "-p", "no:cacheprovider"],
        cwd=wt, capture_output=True, text=True, timeout=300)


@pytest.mark.slow
def test_oracle_green_against_reference(tmp_path):
    """Spec §6: the whole suite passes on a sane implementation."""
    proc = _run_oracle(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.slow
def test_oracle_red_when_risk_is_stubbed_out(tmp_path):
    """Spec §6: the oracle discriminates — a reference with risk detection
    disabled must fail, and fail in the risk tests specifically."""
    proc = _run_oracle(tmp_path, break_risk=True)
    assert proc.returncode != 0, "oracle missed the stubbed risk detection"
    assert "test_risk" in proc.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cat_cafe_oracle.py -v`
Expected: the two new tests FAIL (`REF_APP` does not exist → `FileNotFoundError` in `_run_oracle`); `test_oracle_suite_files_exist` PASSES.

- [ ] **Step 3: Write the reference implementation**

Create `tests/fixtures/cat_cafe_ref/app.py`:

```python
"""Reference implementation of the cat-cafe interface contract (spec §3).

Exists ONLY to exercise the held-out oracle in CI
(tests/test_cat_cafe_oracle.py). Never shipped to a worktree, never seen
by any run — it validates the oracle, it is not an answer key. Pure ASGI,
no framework, and no simulator at all (the contract forbids auto-starting
one on import; this module simply has none).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

RISK_ENABLED = True          # the broken-variant self-test flips this
ZONES = [
    {"kind": "rest_area", "x": 0.0, "y": 0.0},
    {"kind": "litter_box", "x": 10.0, "y": 0.0},
    {"kind": "water_bowl", "x": 0.0, "y": 10.0},
    {"kind": "food_bowl", "x": 10.0, "y": 10.0},
]
ZONE_RADIUS = 1.0            # "at" a zone = within this distance
NEAR_CAT = 5.0               # co-located cats = within this distance

_readings: dict[str, list[dict]] = {}


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _dist(ax, ay, bx, by) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _latest(cid: str) -> dict:
    return _readings[cid][-1]


def _history(cid: str) -> list[dict]:
    """Readings within 24h of this cat's newest reading (never wall clock)."""
    rs = sorted(_readings[cid], key=lambda r: _parse_ts(r["timestamp"]))
    lo = _parse_ts(rs[-1]["timestamp"]) - timedelta(hours=24)
    return [r for r in rs if _parse_ts(r["timestamp"]) >= lo]


def _speed(cid: str) -> float:
    rs = _history(cid)
    if len(rs) < 2:
        return 0.0
    a, b = rs[-2], rs[-1]
    dt = (_parse_ts(b["timestamp"]) - _parse_ts(a["timestamp"])).total_seconds()
    if dt <= 0:
        return 0.0
    return _dist(a["x"], a["y"], b["x"], b["y"]) / dt


def _activity(cid: str) -> str | None:
    latest = _latest(cid)
    x, y, bpm = latest["x"], latest["y"], latest["breathing_rate"]
    for z in ZONES:
        if _dist(x, y, z["x"], z["y"]) <= ZONE_RADIUS:
            if z["kind"] == "food_bowl":
                return "eating"
            if z["kind"] == "water_bowl":
                return "drinking"
            if z["kind"] == "litter_box":
                return "litter_box"
            return "sleeping" if bpm <= 30 else None   # rest_area
    for other in _readings:
        if other == cid:
            continue
        o = _latest(other)
        if (_dist(x, y, o["x"], o["y"]) <= NEAR_CAT
                and _speed(cid) > 0.2 and bpm >= 50):
            return "playing"
    return None


def _at_risk(cid: str) -> bool:
    if not RISK_ENABLED:
        return False
    bpm = _latest(cid)["breathing_rate"]
    return bpm > 60 or bpm < 10


async def _read_json(receive) -> dict:
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    return json.loads(body or b"{}")


async def _send_json(send, status: int, payload) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body",
                "body": json.dumps(payload).encode()})


async def app(scope, receive, send):
    assert scope["type"] == "http"
    method, path = scope["method"], scope["path"]
    if method == "POST" and path == "/telemetry":
        r = await _read_json(receive)
        _readings.setdefault(str(r["cat_id"]), []).append({
            "timestamp": r["timestamp"], "x": float(r["x"]),
            "y": float(r["y"]),
            "breathing_rate": float(r["breathing_rate"])})
        return await _send_json(send, 202, {"ok": True})
    if method == "GET" and path == "/floorplan":
        return await _send_json(send, 200, {"zones": ZONES})
    if method == "GET" and path == "/cats":
        return await _send_json(send, 200, [
            {"id": cid, "x": _latest(cid)["x"], "y": _latest(cid)["y"],
             "activity": _activity(cid), "at_risk": _at_risk(cid)}
            for cid in _readings])
    if method == "GET" and path.startswith("/cats/"):
        cid = path[len("/cats/"):]
        if cid not in _readings:
            return await _send_json(send, 404, {"error": "unknown cat"})
        return await _send_json(send, 200, {
            "id": cid, "latest": _latest(cid), "history": _history(cid)})
    return await _send_json(send, 404, {"error": "not found"})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cat_cafe_oracle.py -v`
Expected: ALL 3 PASS. If `test_oracle_green_against_reference` fails, the assertion message contains the oracle run's full stdout/stderr — fix whichever side is wrong (a bug here is as likely in the oracle as in the reference; the fairness rule decides: the oracle only ever moves toward *weaker* assertions, never toward reference-specific ones).

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest tests -q`
Expected: everything green (no existing test touches these paths).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/cat_cafe_ref/app.py tests/test_cat_cafe_oracle.py
git commit -m "test(benchmarks): reference implementation proves cat-cafe oracle discriminates (E-34)"
```

---

### Task 4: Record the decisions — ROADMAP.md + BENCHMARK.md

**Files:**
- Modify: `ROADMAP.md` (E-34, E-29, E-27 note, §9.8 open-questions paragraph)
- Modify: `BENCHMARK.md` (OQ-B3, ~line 449)

**Interfaces:**
- Consumes: nothing from code — records what Tasks 1–3 landed and the pre-existing 2026-07-20 fail-and-continue decision at `src/sdlc/workflows/feature.py:987-1006`.
- Produces: tracker truth for future sessions.

- [ ] **Step 1: Update E-34 in ROADMAP.md**

Replace the `- [ ] **E-34 (new scope)** ...` block (starts near line 440) with:

```markdown
- [x] **E-34 (new scope)** A decomposition-forcing benchmark case. *Landed
  via cat-café (E-27), not a new case* — the "both current cases" text
  predated E-27 landing the kata; the real gap was that the decomposition
  case had no objective grade. Cat-café now freezes an interface contract
  (ASGI `app:app`, `/telemetry` injection, `/floorplan`, `/cats`) and
  ships a held-out `oracle/` graded through the E-31 machinery
  (`language: python`). Assertions are unambiguous extremes crafted
  against the app's **own** floorplan, so the kata's "rules are up to you"
  freedom is intact. Oracle validated in CI against a reference
  implementation (`tests/fixtures/cat_cafe_ref/`): green on the reference,
  red when risk detection is stubbed out. Spec
  `docs/superpowers/specs/2026-07-23-cat-cafe-tier-a-oracle-design.md`,
  plan `docs/superpowers/plans/2026-07-23-cat-cafe-tier-a-oracle.md`.
```

- [ ] **Step 2: Update E-29 in ROADMAP.md**

Replace the `- [ ] **E-29** ...` block (starts near line 298) with:

```markdown
- [x] **E-29** Research grounding was unreachable for a mid-tier author
  model (byte-exact quote verification; glm-5.2 plateaued at 3
  violations). **Closed by the 2026-07-20 fail-and-continue decision**
  (`feature.py:987`): a grounding violation now fails the research *stage*
  (recorded `FAIL`, retain + digest skipped) and the run proceeds on the
  idea alone — of the three options this is (c) advisory, implemented as
  fail-and-continue rather than demote-to-inferred. Rubric judging of the
  brief happens only when grounding passes, so a cell's research grade is
  earnable but not guaranteed. The demote-to-inferred + still-judge
  variant was considered for E-34 and deliberately not built
  (`2026-07-23-cat-cafe-tier-a-oracle-design.md` §2). OQ-B3 answered
  accordingly. The verifier itself is unchanged — no loosening.
```

- [ ] **Step 3: Update the E-27 trailing note in ROADMAP.md**

In the E-27 block (near line 296), replace the sentence `So live judge scoring of research/qa records is unit-tested but unproven end-to-end; it unblocks when E-29 or E-30 lands.` with:

```markdown
So live judge scoring of `research`/`qa` records is unit-tested but unproven end-to-end; E-29's closure (fail-and-continue, 2026-07-20) unblocks the run itself — a live re-run is still pending.
```

- [ ] **Step 4: Update the §9.8 open-questions paragraph in ROADMAP.md**

Near line 520, replace `OQ-B3 research grounding gate for benchmark cells (→ **E-29**, pick advisory / pin model / wait, explicitly);` with:

```markdown
OQ-B3 **answered** (E-29 closed: grounding failure = recorded stage `FAIL`, run continues);
```

- [ ] **Step 5: Update OQ-B3 in BENCHMARK.md**

Replace the `- **OQ-B3 — Research grounding gate for benchmark cells (E-29).** ...` bullet (line 449) with:

```markdown
- **OQ-B3 — Research grounding gate for benchmark cells (E-29). ANSWERED
  2026-07-23.** Benchmark cells run with the hard grounding verifier
  unchanged; a violation is a recorded research-stage `FAIL` in the cell's
  record — retain and digest are skipped and the run continues on the idea
  alone (the 2026-07-20 fail-and-continue decision, `feature.py:987`).
  Research rubric judging happens only on grounded briefs, so a cell's
  research grade is earnable but not guaranteed — never an unearnable
  number silently reported. The demote-to-inferred + still-judge variant
  was considered and deliberately not built
  (`2026-07-23-cat-cafe-tier-a-oracle-design.md` §2).
```

- [ ] **Step 6: Run the full suite once more**

Run: `python -m pytest tests -q`
Expected: green — docs changes can't break tests, but this is the pre-commit gate for the increment's final state.

- [ ] **Step 7: Commit**

```bash
git add ROADMAP.md BENCHMARK.md
git commit -m "docs: mark E-34 landed via cat-cafe oracle, E-29 closed by fail-and-continue, OQ-B3 answered"
```

---

## Not in this plan (spec §8)

Research-advisory knob (demote + judge), E-31a diff-coverage anti-cheat, new language adapters, any change to kata functional requirements, and the **live** benchmark run producing a real oracle grade for cat-café — that last one is a run-time exercise at the user's discretion, same status as E-27's smoke run.
