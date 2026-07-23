# Error Heatmap + Rubric-Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship E-36 — a `case × stage` rework-density heatmap over existing benchmark records, plus a file-edit rubric-calibration loop that reports judge–human agreement so a rubric score is never read without its trust level.

**Architecture:** Two independent units, both following the established `observability/export.py` shape — pure aggregators/renderers with no `temporalio` and no filesystem, with I/O confined to the existing `finalize_benchmark_report` activity (heatmap) or an offline CLI command (calibration). Nothing changes in the workflow, the deterministic gate, or the on-disk `BenchmarkRecord` schema.

**Tech Stack:** Python 3, Pydantic v2, argparse CLI, pytest. No new third-party dependencies (Spearman is hand-implemented; HTML is a dependency-free inline-CSS template).

## Global Constraints

- Pure core, I/O at the edge: `heatmap.py` and the calibration compute functions contain **no** filesystem or `temporalio` imports. All file writes live in the `finalize_benchmark_report` activity (`report.py`) or in `benchmarks/cli.py` dispatch functions.
- No change to `BenchmarkRecord` (`benchmarks/models.py`) or to any write path.
- ADR-6 / OQ-B2: calibration MUST assert `model_family(judge_model) != model_family(fixture.author_model)` per fixture (via `sdlc.agents.loader.model_family`) and skip a same-family fixture with a loud warning — never silently calibrate a same-family judge.
- Calibration is advisory: it MUST NOT modify any composite score or gate outcome.
- ASCII-only in Markdown output (a Windows cp1252 console mangles non-ASCII), matching the existing `report.py` `fmt` note.
- Records already carry: `case_id`, `stage`, `scope` (`BenchmarkScope.STAGE|TASK_ATTEMPT|ORACLE`), `outcome` (`BenchmarkOutcome.PASS|FAIL|REVISE|ESCALATED`), `fix_attempts: int`, `run_id`, `quality.judge`. The heatmap reads only these.
- Rubric keys (calibration bucket names) are proposer role names: `clarifier`, `architect`, `planner`, `qa`, `research` (and `reviewer`, `analyst` where a rubric exists). These differ from record `stage` values (`clarify`, `architecture`, `planning`, …) — the `STAGE_TO_RUBRIC` map in Task 8 bridges them.

---

### Task 1: Heatmap data model + aggregation

**Files:**
- Create: `src/sdlc/benchmarks/heatmap.py`
- Test: `tests/test_benchmark_heatmap.py`

**Interfaces:**
- Consumes: `BenchmarkRecord`, `BenchmarkOutcome`, `BenchmarkScope` from `sdlc.benchmarks.models`.
- Produces:
  - `class HeatmapCell(BaseModel)` with fields `case: str, stage: str, gate_rejects: int, fix_attempts: int, oracle_fails: int, n_runs: int, density: float`.
  - `class Heatmap(BaseModel)` with fields `cells: list[HeatmapCell], cases: list[str], stages: list[str], max_density: float, language_by_case: dict[str, str]`.
  - `CANONICAL_STAGES: list[str]`, `ORACLE_STAGE: str = "oracle"`, `REWORK_OUTCOMES: set[BenchmarkOutcome]`.
  - `build_heatmap(records: list[BenchmarkRecord], language_by_case: dict[str, str] | None = None) -> Heatmap`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_benchmark_heatmap.py
from datetime import datetime, timedelta

from sdlc.benchmarks.heatmap import (
    ORACLE_STAGE, Heatmap, HeatmapCell, build_heatmap,
)
from sdlc.benchmarks.models import (
    BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag,
)
from sdlc.models import HarnessKind


def _rec(*, case="c1", run="r1", stage="code", scope=BenchmarkScope.STAGE,
         outcome=BenchmarkOutcome.PASS, fix=0):
    t = datetime(2026, 7, 24, 10)
    return BenchmarkRecord(
        run_id=run, bench_run_id="b1", case_id=case, scope=scope, stage=stage,
        role="dev", harness=HarnessKind.CLAUDE_CODE, model="m",
        quality=QualityScore(score=None, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=outcome, fix_attempts=fix)


def test_density_blends_rejects_fixes_and_oracle_over_runs():
    recs = [
        _rec(run="r1", stage="code", outcome=BenchmarkOutcome.REVISED, fix=2),
        _rec(run="r2", stage="code", outcome=BenchmarkOutcome.FAIL, fix=3),
        # oracle failure for the same case, distinct synthetic column
        _rec(run="r1", stage="oracle", scope=BenchmarkScope.ORACLE,
             outcome=BenchmarkOutcome.FAIL),
    ]
    hm = build_heatmap(recs)
    by = {(c.case, c.stage): c for c in hm.cells}
    code = by[("c1", "code")]
    # 2 rework outcomes (REVISED + FAIL) + 5 fix attempts = 7 over 2 runs
    assert code.gate_rejects == 2
    assert code.fix_attempts == 5
    assert code.n_runs == 2
    assert code.density == 3.5
    oracle = by[("c1", ORACLE_STAGE)]
    assert oracle.oracle_fails == 1
    assert oracle.gate_rejects == 0
    assert oracle.density == 0.5   # 1 oracle fail / 2 runs


def test_n_runs_dedups_distinct_run_ids_per_case():
    recs = [_rec(run="r1", stage="qa", outcome=BenchmarkOutcome.FAIL),
            _rec(run="r1", stage="code", outcome=BenchmarkOutcome.FAIL)]
    hm = build_heatmap(recs)
    assert all(c.n_runs == 1 for c in hm.cells)


def test_unknown_stage_appended_before_oracle_not_dropped():
    recs = [_rec(stage="clarify", outcome=BenchmarkOutcome.FAIL),
            _rec(stage="mystery", outcome=BenchmarkOutcome.FAIL),
            _rec(stage="oracle", scope=BenchmarkScope.ORACLE,
                 outcome=BenchmarkOutcome.FAIL)]
    hm = build_heatmap(recs)
    assert hm.stages == ["clarify", "mystery", "oracle"]


def test_language_map_recorded_per_case():
    recs = [_rec(case="py", stage="code", outcome=BenchmarkOutcome.FAIL),
            _rec(case="go", stage="code", outcome=BenchmarkOutcome.FAIL)]
    hm = build_heatmap(recs, language_by_case={"py": "python"})
    assert hm.language_by_case == {"py": "python", "go": ""}


def test_empty_records_give_empty_heatmap():
    hm = build_heatmap([])
    assert hm.cells == [] and hm.cases == [] and hm.stages == []
    assert hm.max_density == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_benchmark_heatmap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.heatmap'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/benchmarks/heatmap.py
"""case x stage rework-density heatmap (E-36).

Pure aggregation + rendering over BenchmarkRecords already on disk. No I/O,
no temporalio -- mirrors observability/export.py. The finalize activity
(report.py) owns the file writes.
"""
from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from .models import BenchmarkOutcome, BenchmarkRecord, BenchmarkScope

# Record-vocabulary stage order (SDLC-spec 15-stage DAG); the synthetic
# ``oracle`` column trails. Only columns with an observed cell are rendered.
CANONICAL_STAGES: list[str] = [
    "intake", "constitution", "context", "requirements", "research",
    "clarify", "architecture", "planning", "code", "review", "analyze",
    "qa", "quality_gate", "deploy", "retro",
]
ORACLE_STAGE = "oracle"

# A revise round re-enters a stage, so REVISED is rework alongside FAIL/ESCALATED.
REWORK_OUTCOMES: set[BenchmarkOutcome] = {
    BenchmarkOutcome.FAIL, BenchmarkOutcome.ESCALATED, BenchmarkOutcome.REVISED,
}


class HeatmapCell(BaseModel):
    case: str
    stage: str
    gate_rejects: int
    fix_attempts: int
    oracle_fails: int
    n_runs: int
    density: float


class Heatmap(BaseModel):
    cells: list[HeatmapCell] = Field(default_factory=list)
    cases: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    max_density: float = 0.0
    language_by_case: dict[str, str] = Field(default_factory=dict)


def build_heatmap(records: list[BenchmarkRecord],
                  language_by_case: dict[str, str] | None = None) -> Heatmap:
    language_by_case = language_by_case or {}

    runs_by_case: dict[str, set[str]] = defaultdict(set)
    for r in records:
        runs_by_case[r.case_id].add(r.run_id)

    acc: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"gate": 0, "fix": 0, "oracle": 0})
    for r in records:
        is_oracle = r.scope is BenchmarkScope.ORACLE
        stage = ORACLE_STAGE if is_oracle else r.stage
        key = (r.case_id, stage)
        if r.outcome in REWORK_OUTCOMES:
            acc[key]["oracle" if is_oracle else "gate"] += 1
        acc[key]["fix"] += r.fix_attempts

    cells: list[HeatmapCell] = []
    for (case, stage), a in acc.items():
        n_runs = max(len(runs_by_case[case]), 1)
        total = a["gate"] + a["fix"] + a["oracle"]
        cells.append(HeatmapCell(
            case=case, stage=stage, gate_rejects=a["gate"],
            fix_attempts=a["fix"], oracle_fails=a["oracle"],
            n_runs=n_runs, density=total / n_runs))

    cases = sorted({c.case for c in cells})
    present = {c.stage for c in cells}
    ordered = [s for s in CANONICAL_STAGES if s in present]
    unknown = sorted(present - set(CANONICAL_STAGES) - {ORACLE_STAGE})
    stages = ordered + unknown + ([ORACLE_STAGE] if ORACLE_STAGE in present else [])
    max_density = max((c.density for c in cells), default=0.0)
    lang = {c: language_by_case.get(c, "") for c in cases}
    return Heatmap(cells=cells, cases=cases, stages=stages,
                   max_density=max_density, language_by_case=lang)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_benchmark_heatmap.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/heatmap.py tests/test_benchmark_heatmap.py
git commit -m "feat(benchmarks): case x stage heatmap aggregation (E-36)"
```

---

### Task 2: Heatmap renderers (JSON + HTML)

**Files:**
- Modify: `src/sdlc/benchmarks/heatmap.py`
- Test: `tests/test_benchmark_heatmap_render.py`

**Interfaces:**
- Consumes: `Heatmap`, `HeatmapCell` (Task 1).
- Produces:
  - `render_heatmap_json(hm: Heatmap) -> str`
  - `render_heatmap_html(hm: Heatmap, calibration_html: str = "") -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_benchmark_heatmap_render.py
import json

from sdlc.benchmarks.heatmap import (
    Heatmap, HeatmapCell, render_heatmap_html, render_heatmap_json,
)


def _hm():
    return Heatmap(
        cells=[HeatmapCell(case="c1", stage="code", gate_rejects=2,
                           fix_attempts=5, oracle_fails=0, n_runs=2,
                           density=3.5),
               HeatmapCell(case="c2", stage="code", gate_rejects=0,
                           fix_attempts=0, oracle_fails=0, n_runs=1,
                           density=0.0)],
        cases=["c1", "c2"], stages=["code"], max_density=3.5,
        language_by_case={"c1": "python", "c2": "go"})


def test_json_round_trips_and_keeps_breakdown():
    data = json.loads(render_heatmap_json(_hm()))
    assert data["max_density"] == 3.5
    cell = next(c for c in data["cells"] if c["case"] == "c1")
    assert cell["gate_rejects"] == 2 and cell["fix_attempts"] == 5


def test_html_is_wellformed_and_escapes_and_has_language_grids():
    html = render_heatmap_html(_hm())
    assert html.startswith("<!doctype html>") and html.rstrip().endswith("</html>")
    assert "python" in html and "go" in html      # per-language grids
    assert "3.5" in html                            # density shown/tooltip


def test_html_escapes_case_names():
    hm = Heatmap(cells=[HeatmapCell(case="<x>", stage="code", gate_rejects=1,
                                    fix_attempts=0, oracle_fails=0, n_runs=1,
                                    density=1.0)],
                 cases=["<x>"], stages=["code"], max_density=1.0,
                 language_by_case={"<x>": ""})
    assert "<x>" not in render_heatmap_html(hm)
    assert "&lt;x&gt;" in render_heatmap_html(hm)


def test_html_handles_empty():
    html = render_heatmap_html(Heatmap())
    assert "No records" in html


def test_calibration_html_is_embedded():
    html = render_heatmap_html(_hm(), calibration_html="<p>CALIB-MARKER</p>")
    assert "CALIB-MARKER" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_benchmark_heatmap_render.py -v`
Expected: FAIL with `ImportError: cannot import name 'render_heatmap_html'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/benchmarks/heatmap.py`:

```python
from html import escape


def render_heatmap_json(hm: Heatmap) -> str:
    return hm.model_dump_json(indent=2)


def _cell_color(density: float, max_density: float) -> str:
    ratio = 0.0 if max_density <= 0 else min(density / max_density, 1.0)
    hue = 120 * (1 - ratio)          # 120=green (low) -> 0=red (high)
    return f"hsl({hue:.0f},70%,{85 - 25 * ratio:.0f}%)"


def _grid(hm: Heatmap, cases: list[str]) -> str:
    by = {(c.case, c.stage): c for c in hm.cells}
    head = "".join(f"<th>{escape(s)}</th>" for s in hm.stages)
    rows = []
    for case in cases:
        tds = [f"<th>{escape(case)}</th>"]
        for stage in hm.stages:
            c = by.get((case, stage))
            if c is None:
                tds.append('<td class="empty"></td>')
                continue
            tip = (f"{case}/{stage}: {c.gate_rejects} rejects, "
                   f"{c.fix_attempts} fix-attempts, {c.oracle_fails} "
                   f"oracle-fails over {c.n_runs} runs = {c.density:.2f}/run")
            tds.append(
                f'<td title="{escape(tip)}" '
                f'style="background:{_cell_color(c.density, hm.max_density)}">'
                f"{c.density:.2f}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return (f"<table><tr><th>case \\ stage</th>{head}</tr>"
            + "".join(rows) + "</table>")


def render_heatmap_html(hm: Heatmap, calibration_html: str = "") -> str:
    if not hm.cells:
        body = "<p>No records.</p>"
    else:
        sections = [f"<h2>All cases</h2>{_grid(hm, hm.cases)}"]
        langs = sorted({v for v in hm.language_by_case.values() if v})
        for lang in langs:
            cases = [c for c in hm.cases if hm.language_by_case.get(c) == lang]
            sections.append(f"<h2>{escape(lang)}</h2>{_grid(hm, cases)}")
        body = "".join(sections)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Benchmark heatmap</title>
<style>
body{{font:14px system-ui,sans-serif;margin:2rem;color:#111}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:1.5rem}}
table{{border-collapse:collapse;margin:.5rem 0}}
td,th{{border:1px solid #ccc;padding:.3rem .6rem;text-align:center}}
th{{background:#f3f3f3}} td.empty{{background:#fafafa}}
</style></head><body>
<h1>Rework-density heatmap</h1>
<p>Cell = (gate rejections + fix-loop attempts + oracle failures) per run.
Greener is cleaner; redder is more rework.</p>
{body}
{calibration_html}
</body></html>"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_benchmark_heatmap_render.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/heatmap.py tests/test_benchmark_heatmap_render.py
git commit -m "feat(benchmarks): heatmap JSON + HTML renderers (E-36)"
```

---

### Task 3: Language-map resolution + wire heatmap into the finalize activity

**Files:**
- Modify: `src/sdlc/benchmarks/report.py`
- Test: `tests/test_benchmark_report.py` (extend)

**Interfaces:**
- Consumes: `build_heatmap`, `render_heatmap_html`, `render_heatmap_json` (Tasks 1–2); `aggregate`, `_read_all`, `_root` (existing `report.py`).
- Produces:
  - `resolve_language_map(case_ids: list[str], cases_dir: Path | None = None) -> dict[str, str]`
  - `write_heatmap(records: list[BenchmarkRecord], out_dir: Path, language_by_case: dict[str, str]) -> tuple[Path, Path]`
  - `finalize_benchmark_report` still returns the `report.md` path; now also writes `heatmap.html` + `heatmap.json` beside it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_benchmark_report.py`:

```python
def test_resolve_language_map_reads_case_manifests(tmp_path):
    from sdlc.benchmarks.report import resolve_language_map
    (tmp_path / "c1").mkdir()
    (tmp_path / "c1" / "case.yaml").write_text(
        "case_id: c1\nlanguage: python\n", encoding="utf-8")
    (tmp_path / "c2").mkdir()          # no case.yaml
    m = resolve_language_map(["c1", "c2"], cases_dir=tmp_path)
    assert m == {"c1": "python", "c2": ""}


def test_write_heatmap_emits_both_files(tmp_path):
    from sdlc.benchmarks.report import write_heatmap
    recs = [_rec("sonnet", 0.9, 1.0, 100)]
    recs[0].outcome  # BenchmarkOutcome.PASS; density 0 is fine
    html_p, json_p = write_heatmap(recs, tmp_path, {"c1": "python"})
    assert html_p.exists() and json_p.exists()
    assert html_p.name == "heatmap.html" and json_p.name == "heatmap.json"
    assert "<!doctype html>" in html_p.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_benchmark_report.py -k "language_map or write_heatmap" -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_language_map'`.

- [ ] **Step 3: Write minimal implementation**

In `src/sdlc/benchmarks/report.py`, add imports at the top:

```python
import yaml

from .heatmap import build_heatmap, render_heatmap_html, render_heatmap_json
from .judge import _CASES_DIR
```

Add these functions (before `finalize_benchmark_report`):

```python
def resolve_language_map(case_ids: list[str],
                         cases_dir: Path | None = None) -> dict[str, str]:
    """Best-effort {case_id: language} from each case's case.yaml. A missing
    manifest or language contributes ""; never raises (a broken manifest just
    means that case is language-unknown)."""
    base = cases_dir if cases_dir is not None else _CASES_DIR
    out: dict[str, str] = {}
    for cid in case_ids:
        lang = ""
        p = Path(base) / cid / "case.yaml"
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                lang = str(data.get("language") or "")
            except Exception:
                lang = ""
        out[cid] = lang
    return out


def write_heatmap(records, out_dir: Path,
                  language_by_case: dict[str, str]) -> tuple[Path, Path]:
    hm = build_heatmap(records, language_by_case)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_p = out_dir / "heatmap.html"
    json_p = out_dir / "heatmap.json"
    html_p.write_text(render_heatmap_html(hm), encoding="utf-8")
    json_p.write_text(render_heatmap_json(hm), encoding="utf-8")
    return html_p, json_p
```

Extend `finalize_benchmark_report` to also write the heatmap:

```python
@activity.defn
async def finalize_benchmark_report(bench_run_id: str) -> str:
    """Activity: read all records, aggregate, write report.md AND the
    heatmap.{html,json} beside it. All file I/O lives here."""
    records = _read_all(bench_run_id, None)
    summaries = aggregate(bench_run_id, CompositeWeights(), _records=records)
    out_dir = Path(_root()) / bench_run_id
    write_report(summaries, str(out_dir / "report.md"))
    lang = resolve_language_map(sorted({r.case_id for r in records}))
    write_heatmap(records, out_dir, lang)
    return str(out_dir / "report.md")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_benchmark_report.py -v`
Expected: PASS (all existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/report.py tests/test_benchmark_report.py
git commit -m "feat(benchmarks): finalize activity emits heatmap.{html,json} (E-36)"
```

---

### Task 4: Emit heatmap from the offline `benchmark report` CLI

**Files:**
- Modify: `src/sdlc/benchmarks/cli.py`
- Test: `tests/test_benchmark_cli.py` (extend)

**Interfaces:**
- Consumes: `write_heatmap`, `resolve_language_map`, `_read_all` (Task 3); `dispatch_report` (existing).
- Produces: `dispatch_report(bench, root=None)` now also writes `heatmap.{html,json}` under `<root>/<bench>/`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_benchmark_cli.py` (mirror its existing record-building helper; if none, use the `_rec` shape from `tests/test_benchmark_report.py`):

```python
def test_dispatch_report_also_writes_heatmap(tmp_path):
    from datetime import datetime, timedelta
    from sdlc.benchmarks.cli import dispatch_report
    from sdlc.benchmarks.models import (
        BenchmarkOutcome, BenchmarkRecord, BenchmarkScope, QualityScore, SpeedBag)
    from sdlc.benchmarks.recorder import RecordStore
    from sdlc.models import HarnessKind
    t = datetime(2026, 7, 24, 10)
    rec = BenchmarkRecord(
        run_id="r1", bench_run_id="b1", case_id="c1",
        scope=BenchmarkScope.STAGE, stage="code", role="dev",
        harness=HarnessKind.CLAUDE_CODE, model="m",
        quality=QualityScore(score=0.9, judge="contract"),
        speed=SpeedBag(wall_clock_s=1.0, started_at=t, ended_at=t + timedelta(seconds=1)),
        outcome=BenchmarkOutcome.FAIL, fix_attempts=1)
    RecordStore(root=str(tmp_path), bench_run_id="b1").append(rec)
    dispatch_report("b1", root=str(tmp_path))
    assert (tmp_path / "b1" / "heatmap.html").exists()
    assert (tmp_path / "b1" / "heatmap.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_benchmark_cli.py -k heatmap -v`
Expected: FAIL — `heatmap.html` does not exist.

- [ ] **Step 3: Write minimal implementation**

Edit `dispatch_report` in `src/sdlc/benchmarks/cli.py`:

`dispatch_report` currently imports `aggregate, render_markdown, write_report`
from `.report` (cli.py top) and `_root` from `.recorder`. Add
`_read_all, resolve_language_map, write_heatmap` to the `.report` import, then:

```python
def dispatch_report(bench: str,
                    root: str | None = None) -> str:
    from .report import (
        _read_all, resolve_language_map, write_heatmap)
    records = _read_all(bench, root)
    summaries = aggregate(bench, CompositeWeights(), root=root, _records=records)
    md = render_markdown(summaries)
    out_dir = Path(root if root is not None else _root()) / bench
    write_report(summaries, str(out_dir / "report.md"))
    lang = resolve_language_map(sorted({r.case_id for r in records}))
    write_heatmap(records, out_dir, lang)
    return md
```

(`_read_all` lives in `report.py`, not `recorder.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_benchmark_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/cli.py tests/test_benchmark_cli.py
git commit -m "feat(benchmarks): offline report CLI emits heatmap (E-36)"
```

---

### Task 5: Calibration fixture model + load/store

**Files:**
- Create: `src/sdlc/benchmarks/calibration.py`
- Test: `tests/test_calibration_fixtures.py`

**Interfaces:**
- Produces:
  - `class CalibrationFixture(BaseModel)`: `artifact_json: str, rubric_ref: str, rubric_text: str, rubric_sha: str, author_model: str, human_score: float | None = None, human_components: dict[str, float] = {}, scored_by: str | None = None, notes: str | None = None`.
  - `rubric_sha_of(text: str) -> str` (sha256 hex).
  - `make_capture_fixture(artifact_json: str, author_model: str, rubric_ref: str, rubric_text: str) -> CalibrationFixture` (human_score None).
  - `write_fixture(fx: CalibrationFixture, rubric_dir: Path, name: str) -> Path`.
  - `load_scored_fixtures(rubric_dir: Path) -> list[CalibrationFixture]` (skips `human_score is None` and unparseable files).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration_fixtures.py
from pathlib import Path

from sdlc.benchmarks.calibration import (
    CalibrationFixture, load_scored_fixtures, make_capture_fixture,
    rubric_sha_of, write_fixture,
)


def test_make_capture_fixture_pins_sha_and_nulls_score():
    fx = make_capture_fixture('{"a":1}', "zai/glm-5.2",
                              "cat-cafe/architect", "score soundness 0..1")
    assert fx.human_score is None
    assert fx.rubric_sha == rubric_sha_of("score soundness 0..1")
    assert fx.author_model == "zai/glm-5.2"


def test_load_skips_unscored_and_malformed(tmp_path):
    d = tmp_path / "architect"
    scored = CalibrationFixture(artifact_json="{}", rubric_ref="c/architect",
                                rubric_text="r", rubric_sha=rubric_sha_of("r"),
                                author_model="m", human_score=0.8)
    unscored = make_capture_fixture("{}", "m", "c/architect", "r")
    write_fixture(scored, d, "fixt-0001")
    write_fixture(unscored, d, "fixt-0002")
    (d / "fixt-0003.json").write_text("{ not json", encoding="utf-8")
    loaded = load_scored_fixtures(d)
    assert len(loaded) == 1 and loaded[0].human_score == 0.8


def test_load_missing_dir_is_empty(tmp_path):
    assert load_scored_fixtures(tmp_path / "nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibration_fixtures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sdlc.benchmarks.calibration'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/sdlc/benchmarks/calibration.py
"""Rubric-judge calibration (E-36, FR-110).

Offline measurement tool: hand-score a sample of rubric fixtures, run the
cross-family judge over the same fixtures, report judge-human agreement.
Advisory only -- never modifies a composite score or a gate outcome.

Pure compute here; the CLI (cli.py) owns file I/O and the live-history seam.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field


class CalibrationFixture(BaseModel):
    artifact_json: str
    rubric_ref: str                       # e.g. "cat-cafe-monitoring/architect"
    rubric_text: str                      # pinned at capture -> reproducible
    rubric_sha: str
    author_model: str
    human_score: float | None = None      # None => unscored, skipped
    human_components: dict[str, float] = Field(default_factory=dict)
    scored_by: str | None = None
    notes: str | None = None


def rubric_sha_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_capture_fixture(artifact_json: str, author_model: str,
                         rubric_ref: str, rubric_text: str) -> CalibrationFixture:
    return CalibrationFixture(
        artifact_json=artifact_json, rubric_ref=rubric_ref,
        rubric_text=rubric_text, rubric_sha=rubric_sha_of(rubric_text),
        author_model=author_model, human_score=None)


def write_fixture(fx: CalibrationFixture, rubric_dir: Path, name: str) -> Path:
    rubric_dir.mkdir(parents=True, exist_ok=True)
    p = rubric_dir / f"{name}.json"
    p.write_text(fx.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_scored_fixtures(rubric_dir: Path) -> list[CalibrationFixture]:
    if not rubric_dir.is_dir():
        return []
    out: list[CalibrationFixture] = []
    for p in sorted(rubric_dir.glob("*.json")):
        if p.name == "calibration.json":
            continue
        try:
            fx = CalibrationFixture.model_validate_json(
                p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if fx.human_score is not None:
            out.append(fx)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibration_fixtures.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/calibration.py tests/test_calibration_fixtures.py
git commit -m "feat(benchmarks): calibration fixture model + load/store (E-36)"
```

---

### Task 6: Agreement statistics (within-ε rate, MAE, Spearman)

**Files:**
- Modify: `src/sdlc/benchmarks/calibration.py`
- Test: `tests/test_calibration_agreement.py`

**Interfaces:**
- Produces:
  - `class AgreementStats(BaseModel)`: `n: int, epsilon: float, threshold: float, agreement_rate: float, mae: float, spearman: float, verdict: Literal["calibrated", "uncalibrated"]`.
  - `compute_agreement(pairs: list[tuple[float, float]], epsilon: float = 0.15, threshold: float = 0.75) -> AgreementStats` — `pairs` are `(human, judge)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration_agreement.py
from sdlc.benchmarks.calibration import AgreementStats, compute_agreement


def test_perfect_agreement():
    s = compute_agreement([(0.2, 0.2), (0.8, 0.8), (0.5, 0.5)])
    assert s.agreement_rate == 1.0
    assert s.mae == 0.0
    assert s.spearman == 1.0
    assert s.verdict == "calibrated"


def test_epsilon_boundary_counts_as_agree():
    # exactly epsilon apart -> within tolerance
    s = compute_agreement([(0.5, 0.65)], epsilon=0.15)
    assert s.agreement_rate == 1.0


def test_beyond_epsilon_is_disagree_and_uncalibrated():
    s = compute_agreement([(0.1, 0.9), (0.2, 0.8)], epsilon=0.15, threshold=0.75)
    assert s.agreement_rate == 0.0
    assert round(s.mae, 3) == 0.7
    assert s.verdict == "uncalibrated"


def test_anti_correlation_spearman_negative():
    s = compute_agreement([(0.1, 0.9), (0.5, 0.5), (0.9, 0.1)])
    assert round(s.spearman, 3) == -1.0


def test_tied_human_scores_do_not_crash_spearman():
    s = compute_agreement([(0.5, 0.4), (0.5, 0.6), (0.5, 0.5)])
    assert s.spearman == 0.0     # zero variance in human ranks -> defined as 0


def test_empty_pairs_safe():
    s = compute_agreement([])
    assert s.n == 0 and s.agreement_rate == 0.0 and s.verdict == "uncalibrated"


def test_single_pair_spearman_zero():
    s = compute_agreement([(0.5, 0.5)])
    assert s.spearman == 0.0     # n<2 undefined -> 0.0
    assert s.agreement_rate == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibration_agreement.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_agreement'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/benchmarks/calibration.py` (add `from typing import Literal` to the imports):

```python
def _ranks(xs: list[float]) -> list[float]:
    """Average ranks (1-based), ties share the mean of their positions."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = sum((a - mx) ** 2 for a in rx)
    deny = sum((b - my) ** 2 for b in ry)
    if denx == 0 or deny == 0:      # zero variance -> correlation undefined
        return 0.0
    return num / (denx ** 0.5 * deny ** 0.5)


class AgreementStats(BaseModel):
    n: int
    epsilon: float
    threshold: float
    agreement_rate: float
    mae: float
    spearman: float
    verdict: Literal["calibrated", "uncalibrated"]


def compute_agreement(pairs: list[tuple[float, float]],
                      epsilon: float = 0.15,
                      threshold: float = 0.75) -> AgreementStats:
    """pairs are (human, judge). Verdict is 'calibrated' iff the within-epsilon
    agreement rate meets the threshold."""
    n = len(pairs)
    if n == 0:
        return AgreementStats(n=0, epsilon=epsilon, threshold=threshold,
                              agreement_rate=0.0, mae=0.0, spearman=0.0,
                              verdict="uncalibrated")
    diffs = [abs(j - h) for h, j in pairs]
    agree = sum(1 for d in diffs if d <= epsilon) / n
    mae = sum(diffs) / n
    sp = _spearman([h for h, _ in pairs], [j for _, j in pairs])
    verdict = "calibrated" if agree >= threshold else "uncalibrated"
    return AgreementStats(n=n, epsilon=epsilon, threshold=threshold,
                          agreement_rate=agree, mae=mae, spearman=sp,
                          verdict=verdict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibration_agreement.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/calibration.py tests/test_calibration_agreement.py
git commit -m "feat(benchmarks): judge-human agreement stats + Spearman (E-36)"
```

---

### Task 7: `run_calibration` — judge the fixtures, assert cross-family, build the report

**Files:**
- Modify: `src/sdlc/benchmarks/calibration.py`
- Test: `tests/test_calibration_run.py`

**Interfaces:**
- Consumes: `CalibrationFixture` (Task 5), `AgreementStats`, `compute_agreement` (Task 6); `JudgeInput`, `judge_artifact` from `sdlc.benchmarks.judge`; `model_family` from `sdlc.agents.loader`.
- Produces:
  - `class CalibrationReport(BaseModel)`: `rubric: str, judge_model: str, n_fixtures: int, epsilon: float, threshold: float, agreement_rate: float, mae: float, spearman: float, verdict: str, computed_at: datetime`.
  - `JudgeScoreFn = Callable[[JudgeInput], QualityScore]` (default `judge_artifact.sync`).
  - `run_calibration(rubric: str, fixtures: list[CalibrationFixture], judge_model: str, *, epsilon: float = 0.15, threshold: float = 0.75, now: datetime | None = None, judge: JudgeScoreFn | None = None) -> CalibrationReport`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration_run.py
from datetime import datetime, timezone

import pytest

from sdlc.benchmarks.calibration import (
    CalibrationFixture, CalibrationReport, run_calibration, rubric_sha_of,
)
from sdlc.benchmarks.models import QualityScore


def _fx(human, author="zai-coding-plan/glm-5.2"):
    return CalibrationFixture(
        artifact_json="{}", rubric_ref="c/architect", rubric_text="r",
        rubric_sha=rubric_sha_of("r"), author_model=author, human_score=human)


def test_run_calibration_scores_and_reports():
    fixtures = [_fx(0.8), _fx(0.6), _fx(0.4)]
    # judge always returns human+0.05 -> all within epsilon
    def judge(inp):
        # the fixture order is preserved; map by identity of rubric not needed
        return QualityScore(score=0.85, judge="llm_judge")
    rep = run_calibration("architect", fixtures, "openai/gpt-5.2",
                          now=datetime(2026, 7, 24, tzinfo=timezone.utc),
                          judge=judge)
    assert isinstance(rep, CalibrationReport)
    assert rep.rubric == "architect"
    assert rep.n_fixtures == 3
    assert rep.judge_model == "openai/gpt-5.2"


def test_run_calibration_skips_same_family_fixture():
    # judge shares family with this fixture's author -> skipped (ADR-6)
    fixtures = [_fx(0.8, author="openai/gpt-4.9"), _fx(0.5, author="zai/glm-5.2")]
    def judge(inp):
        return QualityScore(score=0.5, judge="llm_judge")
    rep = run_calibration("architect", fixtures, "openai/gpt-5.2", judge=judge)
    assert rep.n_fixtures == 1     # the openai-authored fixture was skipped


def test_run_calibration_excludes_judge_errors_from_pairs():
    fixtures = [_fx(0.8), _fx(0.5)]
    calls = {"n": 0}
    def judge(inp):
        calls["n"] += 1
        if calls["n"] == 1:
            return QualityScore(score=None, judge="error")   # judge failed
        return QualityScore(score=0.5, judge="llm_judge")
    rep = run_calibration("architect", fixtures, "openai/gpt-5.2", judge=judge)
    assert rep.n_fixtures == 1     # only the successfully-judged pair counts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibration_run.py -v`
Expected: FAIL with `ImportError: cannot import name 'CalibrationReport'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/benchmarks/calibration.py` (add imports: `import logging`, `from datetime import datetime, timezone`, `from typing import Callable`, `from ..agents.loader import model_family`, `from .judge import JudgeInput`, `from .models import QualityScore`):

```python
_log = logging.getLogger(__name__)

JudgeScoreFn = Callable[[JudgeInput], "QualityScore"]


class CalibrationReport(BaseModel):
    rubric: str
    judge_model: str
    n_fixtures: int
    epsilon: float
    threshold: float
    agreement_rate: float
    mae: float
    spearman: float
    verdict: str
    computed_at: datetime


def _default_judge(inp: JudgeInput) -> QualityScore:
    # judge_artifact.sync is attached in judge.py as a test/sync convenience.
    from .judge import judge_artifact
    return judge_artifact.sync(inp)


def run_calibration(rubric: str, fixtures: list[CalibrationFixture],
                    judge_model: str, *, epsilon: float = 0.15,
                    threshold: float = 0.75, now: datetime | None = None,
                    judge: JudgeScoreFn | None = None) -> CalibrationReport:
    judge = judge or _default_judge
    now = now or datetime.now(timezone.utc)
    pairs: list[tuple[float, float]] = []
    for fx in fixtures:
        if fx.human_score is None:
            continue
        if model_family(judge_model) == model_family(fx.author_model):
            _log.warning(
                "calibration: skipping fixture (judge %s shares family with "
                "author %s; ADR-6)", judge_model, fx.author_model)
            continue
        qs = judge(JudgeInput(artifact_json=fx.artifact_json,
                              rubric=fx.rubric_text,
                              author_model=fx.author_model,
                              judge_model=judge_model))
        if qs.score is None:            # judge errored -> exclude, never crash
            continue
        pairs.append((fx.human_score, qs.score))

    stats = compute_agreement(pairs, epsilon=epsilon, threshold=threshold)
    return CalibrationReport(
        rubric=rubric, judge_model=judge_model, n_fixtures=stats.n,
        epsilon=stats.epsilon, threshold=stats.threshold,
        agreement_rate=stats.agreement_rate, mae=stats.mae,
        spearman=stats.spearman, verdict=stats.verdict, computed_at=now)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibration_run.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/calibration.py tests/test_calibration_run.py
git commit -m "feat(benchmarks): run_calibration judges fixtures, ADR-6 guard (E-36)"
```

---

### Task 8: Trust surfacing — calibration reports in the Markdown + heatmap reports

**Files:**
- Modify: `src/sdlc/benchmarks/calibration.py` (report load + render helpers)
- Modify: `src/sdlc/benchmarks/report.py` (append calibration section; add trust column)
- Test: `tests/test_calibration_render.py`, `tests/test_benchmark_report.py` (extend)

**Interfaces:**
- Produces (in `calibration.py`):
  - `_CALIB_DIR: Path` (= `benchmarks/calibration/`).
  - `STAGE_TO_RUBRIC: dict[str, str]` — record stage -> rubric key.
  - `write_calibration_report(rep: CalibrationReport, rubric_dir: Path) -> Path` (writes `calibration.json`).
  - `load_calibration_reports(calib_root: Path | None = None) -> dict[str, CalibrationReport]` (keyed by rubric).
  - `render_calibration_markdown(reports: dict[str, CalibrationReport]) -> str`.
  - `render_calibration_html(reports: dict[str, CalibrationReport]) -> str`.
  - `trust_for_stage(stage: str, reports: dict[str, CalibrationReport]) -> str`.
- Consumes: `render_markdown` (existing `report.py`) gains an optional `calibration` param.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration_render.py
from datetime import datetime, timezone

from sdlc.benchmarks.calibration import (
    CalibrationReport, load_calibration_reports, render_calibration_html,
    render_calibration_markdown, trust_for_stage, write_calibration_report,
)


def _rep(rubric, rate=0.83, verdict="calibrated"):
    return CalibrationReport(
        rubric=rubric, judge_model="openai/gpt-5.2", n_fixtures=24,
        epsilon=0.15, threshold=0.75, agreement_rate=rate, mae=0.09,
        spearman=0.71, verdict=verdict,
        computed_at=datetime(2026, 7, 24, tzinfo=timezone.utc))


def test_write_then_load_round_trips(tmp_path):
    write_calibration_report(_rep("architect"), tmp_path / "architect")
    reports = load_calibration_reports(tmp_path)
    assert "architect" in reports
    assert reports["architect"].agreement_rate == 0.83


def test_markdown_lists_rubric_stats_and_verdict():
    md = render_calibration_markdown({"architect": _rep("architect")})
    assert "Rubric calibration" in md
    assert "architect" in md and "0.83" in md and "calibrated" in md


def test_html_lists_rubric_stats():
    html = render_calibration_html({"architect": _rep("architect")})
    assert "architect" in html and "0.83" in html


def test_trust_for_stage_maps_record_stage_to_rubric():
    reports = {"architect": _rep("architect", rate=0.83)}
    assert "0.83" in trust_for_stage("architecture", reports)
    assert trust_for_stage("planning", reports) == "uncalibrated"
    assert trust_for_stage("code", reports) == "-"     # no rubric for code
```

Add to `tests/test_benchmark_report.py`:

```python
def test_render_markdown_appends_calibration_when_provided():
    from datetime import datetime, timezone
    from sdlc.benchmarks.calibration import CalibrationReport
    from sdlc.benchmarks.report import aggregate, render_markdown
    from sdlc.benchmarks.models import CompositeWeights
    sums = aggregate("b1", CompositeWeights(),
                     _records=[_rec("sonnet", 0.9, 1.0, 100)])
    rep = CalibrationReport(
        rubric="architect", judge_model="j", n_fixtures=10, epsilon=0.15,
        threshold=0.75, agreement_rate=0.8, mae=0.1, spearman=0.7,
        verdict="calibrated", computed_at=datetime(2026, 7, 24, tzinfo=timezone.utc))
    md = render_markdown(sums, calibration={"architect": rep})
    assert "Rubric calibration" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibration_render.py -v`
Expected: FAIL with `ImportError: cannot import name 'load_calibration_reports'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/benchmarks/calibration.py`:

```python
_CALIB_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "calibration"

# record stage (BenchmarkSummary.stage) -> rubric key (calibration bucket)
STAGE_TO_RUBRIC: dict[str, str] = {
    "clarify": "clarifier",
    "architecture": "architect",
    "planning": "planner",
    "qa": "qa",
    "research": "research",
    "review": "reviewer",
    "analyze": "analyst",
}


def write_calibration_report(rep: CalibrationReport, rubric_dir: Path) -> Path:
    rubric_dir.mkdir(parents=True, exist_ok=True)
    p = rubric_dir / "calibration.json"
    p.write_text(rep.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_calibration_reports(
        calib_root: Path | None = None) -> dict[str, CalibrationReport]:
    root = calib_root if calib_root is not None else _CALIB_DIR
    out: dict[str, CalibrationReport] = {}
    if not Path(root).is_dir():
        return out
    for cj in sorted(Path(root).glob("*/calibration.json")):
        try:
            rep = CalibrationReport.model_validate_json(
                cj.read_text(encoding="utf-8"))
        except Exception:
            continue
        out[rep.rubric] = rep
    return out


def trust_for_stage(stage: str,
                    reports: dict[str, CalibrationReport]) -> str:
    rubric = STAGE_TO_RUBRIC.get(stage)
    if rubric is None:
        return "-"                       # stage has no rubric (e.g. code)
    rep = reports.get(rubric)
    return f"{rep.agreement_rate:.2f}" if rep else "uncalibrated"


def render_calibration_markdown(
        reports: dict[str, CalibrationReport]) -> str:
    if not reports:
        return ""
    lines = ["", "## Rubric calibration", "",
             "| rubric | n | agreement | MAE | spearman | verdict |",
             "|---|---|---|---|---|---|"]
    for rubric in sorted(reports):
        r = reports[rubric]
        lines.append(f"| {rubric} | {r.n_fixtures} | {r.agreement_rate:.2f} | "
                     f"{r.mae:.3f} | {r.spearman:.2f} | {r.verdict} |")
    return "\n".join(lines) + "\n"


def render_calibration_html(
        reports: dict[str, CalibrationReport]) -> str:
    if not reports:
        return ""
    from html import escape
    rows = "".join(
        f"<tr><td>{escape(rubric)}</td><td>{reports[rubric].n_fixtures}</td>"
        f"<td>{reports[rubric].agreement_rate:.2f}</td>"
        f"<td>{reports[rubric].mae:.3f}</td>"
        f"<td>{reports[rubric].spearman:.2f}</td>"
        f"<td>{escape(reports[rubric].verdict)}</td></tr>"
        for rubric in sorted(reports))
    return ("<h2>Rubric calibration</h2><table><tr><th>rubric</th><th>n</th>"
            "<th>agreement</th><th>MAE</th><th>spearman</th><th>verdict</th></tr>"
            + rows + "</table>")
```

Now update `render_markdown` in `src/sdlc/benchmarks/report.py` to take calibration and add a trust column + append the section:

```python
def render_markdown(summaries: list[BenchmarkSummary], calibration=None) -> str:
    from .calibration import render_calibration_markdown, trust_for_stage
    calibration = calibration or {}
    if not summaries:
        return "# Benchmark report\n\nNo records found.\n"
    lines = [
        "# Benchmark report",
        "",
        "| case | stage | harness | model | n | quality | cost ($) | "
        "wall (s) | composite | trust |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summaries:
        def fmt(x):
            return f"{x:.3f}" if isinstance(x, float) else "n/a"
        lines.append(
            f"| {s.case_id} | {s.stage} | "
            f"{s.harness.value if s.harness else 'proposer'} | {s.model} | "
            f"{s.n} | {fmt(s.mean_quality)} | {fmt(s.mean_cost_usd)} | "
            f"{fmt(s.mean_wall_clock_s)} | {fmt(s.composite)} | "
            f"{trust_for_stage(s.stage, calibration)} |"
        )
    errored = [s for s in summaries if s.errors]
    if errored:
        lines += ["", "## Stage failures", ""]
        for s in errored:
            for err in s.errors:
                lines.append(f"- **{s.case_id} / {s.stage}** ({s.model}): {err}")
    return "\n".join(lines) + "\n" + render_calibration_markdown(calibration)
```

Wire the calibration reports into the two report emitters so they load them:

In `finalize_benchmark_report` (report.py) — after computing `summaries`, before `write_report`:

```python
    from .calibration import load_calibration_reports
    calibration = load_calibration_reports()
    write_report_with_calibration(summaries, str(out_dir / "report.md"), calibration)
```

Replace the plain `write_report(...)` calls (in both `finalize_benchmark_report` and `dispatch_report`) with a helper added to report.py:

```python
def write_report_with_calibration(summaries, out_path: str, calibration) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(render_markdown(summaries, calibration),
                              encoding="utf-8")
```

And pass `calibration_html=render_calibration_html(calibration)` into the heatmap write. Update `write_heatmap` signature to accept it:

```python
def write_heatmap(records, out_dir: Path, language_by_case: dict[str, str],
                  calibration_html: str = "") -> tuple[Path, Path]:
    hm = build_heatmap(records, language_by_case)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_p = out_dir / "heatmap.html"
    json_p = out_dir / "heatmap.json"
    html_p.write_text(render_heatmap_html(hm, calibration_html), encoding="utf-8")
    json_p.write_text(render_heatmap_json(hm), encoding="utf-8")
    return html_p, json_p
```

In both `finalize_benchmark_report` and `dispatch_report`, compute `calibration = load_calibration_reports()` once and pass `render_calibration_html(calibration)` to `write_heatmap` and `calibration` to the markdown writer.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibration_render.py tests/test_benchmark_report.py tests/test_benchmark_cli.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/calibration.py src/sdlc/benchmarks/report.py tests/test_calibration_render.py tests/test_benchmark_report.py
git commit -m "feat(benchmarks): surface rubric-calibration trust in reports (E-36)"
```

---

### Task 9: Capture pure core + CLI verbs (`sdlc calibrate` / `sdlc calibrate capture`)

**Files:**
- Modify: `src/sdlc/benchmarks/calibration.py` (pure events->fixtures normalizer)
- Modify: `src/sdlc/benchmarks/cli.py` (dispatch + parser)
- Modify: `src/sdlc/cli.py` (top-level `calibrate` subcommand)
- Test: `tests/test_calibration_capture.py`, `tests/test_calibration_cli.py`

**Interfaces:**
- Consumes: `make_capture_fixture`, `write_fixture`, `load_scored_fixtures`, `run_calibration`, `write_calibration_report`, `_CALIB_DIR` (Tasks 5–8); `default_judge_model` from `sdlc.eval.cli`; `AGENT_TO_ROLE`-style role mapping.
- Produces:
  - `calibration_fixtures_from_events(run_id: str, events: list[dict], role_to_agent: dict[str, str], rubric_ref: str, rubric_text: str, author_model: str, role: str) -> list[CalibrationFixture]` — pure; reads each event's `output` (artifact JSON) for the target role's completion activity.
  - `dispatch_calibrate(rubric: str, *, judge_model: str | None, epsilon: float, threshold: float, calib_root: Path | None = None) -> str` in `benchmarks/cli.py`.

> **Note on capture (honest seam):** calibration fixtures pin the produced
> **artifact** (stage output), unlike `EvalFixture` which pins the **prompt**
> (input). The live Temporal-history→artifact adapter is an operator-runtime
> seam, exactly like `eval.cli._history_to_events` and `benchmarks/drift.py`:
> the pure normalizer below is tested; the live half is documented and
> hand-authoring is the always-available fallback. This task ships the pure
> core + the `calibrate` (judge) command end-to-end; `calibrate capture`'s live
> wiring is a thin documented seam.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calibration_capture.py
from sdlc.benchmarks.calibration import calibration_fixtures_from_events


def test_capture_normalizer_reads_target_role_artifact():
    events = [
        {"activity": "architect_agent__model_request",
         "output": '{"stack": "fastapi"}'},
        {"activity": "planner_agent__model_request",
         "output": '{"tasks": []}'},
    ]
    role_to_agent = {"architect": "architect_agent", "planner": "planner_agent"}
    fx = calibration_fixtures_from_events(
        "run-1", events, role_to_agent, rubric_ref="cat-cafe/architect",
        rubric_text="score soundness 0..1", author_model="zai/glm-5.2",
        role="architect")
    assert len(fx) == 1
    assert fx[0].artifact_json == '{"stack": "fastapi"}'
    assert fx[0].human_score is None
    assert fx[0].rubric_ref == "cat-cafe/architect"


def test_capture_normalizer_empty_when_role_absent():
    events = [{"activity": "planner_agent__model_request", "output": "{}"}]
    fx = calibration_fixtures_from_events(
        "run-1", events, {"architect": "architect_agent"}, rubric_ref="r",
        rubric_text="r", author_model="m", role="architect")
    assert fx == []
```

```python
# tests/test_calibration_cli.py
from datetime import datetime, timezone

from sdlc.benchmarks.calibration import (
    CalibrationFixture, rubric_sha_of, write_fixture)
from sdlc.benchmarks.cli import dispatch_calibrate
import sdlc.benchmarks.calibration as calib


def test_dispatch_calibrate_writes_calibration_json(tmp_path, monkeypatch):
    rubric_dir = tmp_path / "architect"
    for i, human in enumerate([0.8, 0.6, 0.4]):
        fx = CalibrationFixture(
            artifact_json="{}", rubric_ref="c/architect", rubric_text="r",
            rubric_sha=rubric_sha_of("r"), author_model="zai/glm-5.2",
            human_score=human)
        write_fixture(fx, rubric_dir, f"fixt-{i:04d}")
    # stub the judge so no model call happens
    from sdlc.benchmarks.models import QualityScore
    monkeypatch.setattr(
        calib, "_default_judge",
        lambda inp: QualityScore(score=0.7, judge="llm_judge"))
    out = dispatch_calibrate("architect", judge_model="openai/gpt-5.2",
                             epsilon=0.15, threshold=0.75, calib_root=tmp_path)
    assert (rubric_dir / "calibration.json").exists()
    assert "architect" in out and "agreement" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_calibration_capture.py tests/test_calibration_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'calibration_fixtures_from_events'` / `dispatch_calibrate`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/sdlc/benchmarks/calibration.py`:

```python
def calibration_fixtures_from_events(
        run_id: str, events: list[dict], role_to_agent: dict[str, str],
        *, rubric_ref: str, rubric_text: str, author_model: str,
        role: str) -> list[CalibrationFixture]:
    """Pure: normalized history events -> capture fixtures (human_score None)
    for one role. A normalized event is {"activity": str, "output": str}
    where output is the produced artifact JSON. Keeps the FIRST matching
    event, mirroring eval.fixtures_from_events."""
    agent = role_to_agent.get(role)
    if agent is None:
        return []
    wanted = f"{agent}__model_request"
    for ev in events:
        if ev.get("activity") == wanted:
            out = ev.get("output")
            if isinstance(out, str) and out:
                return [make_capture_fixture(out, author_model,
                                             rubric_ref, rubric_text)]
    return []
```

Add to `src/sdlc/benchmarks/cli.py`:

```python
def dispatch_calibrate(rubric: str, *, judge_model: str | None,
                       epsilon: float, threshold: float,
                       calib_root=None) -> str:
    from pathlib import Path
    from .calibration import (
        _CALIB_DIR, load_scored_fixtures, run_calibration,
        write_calibration_report)
    root = Path(calib_root) if calib_root is not None else _CALIB_DIR
    rubric_dir = root / rubric
    fixtures = load_scored_fixtures(rubric_dir)
    if not fixtures:
        return (f"no scored fixtures under {rubric_dir}; capture some with "
                f"`sdlc calibrate capture --case <c> --rubric {rubric}` and "
                f"fill in human_score.")
    if judge_model is None:
        from ..eval.cli import default_judge_model
        judge_model = default_judge_model()
    rep = run_calibration(rubric, fixtures, judge_model,
                          epsilon=epsilon, threshold=threshold)
    write_calibration_report(rep, rubric_dir)
    return (f"calibrate {rubric}: n={rep.n_fixtures} "
            f"agreement={rep.agreement_rate:.2f} mae={rep.mae:.3f} "
            f"spearman={rep.spearman:.2f} -> {rep.verdict}")
```

Extend the benchmarks `build_parser` in `cli.py` with a `calibrate` sibling (used when the benchmarks CLI is invoked standalone):

```python
    cal = sub.add_parser("calibrate")
    cal.add_argument("rubric")
    cal.add_argument("--judge-model", default=None, dest="judge_model")
    cal.add_argument("--epsilon", type=float, default=0.15)
    cal.add_argument("--threshold", type=float, default=0.75)
```

Wire the top-level operator CLI (`src/sdlc/cli.py`), which re-declares subparsers. Add after the `eval` parser block (~line 117):

```python
    cal = sub.add_parser("calibrate")
    cal.add_argument("target", help="a rubric/role name, or 'capture'")
    cal.add_argument("--rubric", default=None,
                     help="rubric/role (capture only)")
    cal.add_argument("--case", default=None, help="case id (capture only)")
    cal.add_argument("--from", dest="from_run", default=None,
                     help="run id (capture only)")
    cal.add_argument("--judge-model", default=None, dest="judge_model")
    cal.add_argument("--epsilon", type=float, default=0.15)
    cal.add_argument("--threshold", type=float, default=0.75)
```

Add `"calibrate"` (non-capture) to the `_local_only` predicate (it makes no
Temporal call in this task's scope):

```python
    _local_only = (args.cmd == "benchmark"
                   or (args.cmd == "schedules" and args.sched_cmd == "list")
                   or (args.cmd == "eval" and args.target != "capture")
                   or (args.cmd == "calibrate" and args.target != "capture"))
```

Add the dispatch branch (near the `eval` branch):

```python
    if args.cmd == "calibrate":
        if args.target == "capture":
            print("calibrate capture requires a live Temporal client and a "
                  "run id; run via the operator CLI. See the E-36 spec: the "
                  "pure normalizer is tested, the live artifact-history adapter "
                  "is operator-runtime. Hand-authoring fixtures under "
                  "benchmarks/calibration/<rubric>/ is the offline path.")
            return
        from .benchmarks.cli import dispatch_calibrate
        print(dispatch_calibrate(args.target, judge_model=args.judge_model,
                                 epsilon=args.epsilon, threshold=args.threshold))
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_calibration_capture.py tests/test_calibration_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sdlc/benchmarks/calibration.py src/sdlc/benchmarks/cli.py src/sdlc/cli.py tests/test_calibration_capture.py tests/test_calibration_cli.py
git commit -m "feat(benchmarks): sdlc calibrate CLI + capture normalizer (E-36)"
```

---

### Task 10: Register the heatmap + calibration activities on the worker

**Files:**
- Modify: `src/sdlc/worker.py` (only if activities/imports are enumerated there)
- Test: `tests/test_worker_registration.py` (if one exists) or a targeted import test

**Interfaces:**
- No new activity is added (heatmap writes ride inside the existing
  `finalize_benchmark_report` activity; calibration is CLI-only). This task is a
  guard: confirm the worker still imports cleanly and the benchmark workflow's
  activity set is unchanged.

- [ ] **Step 1: Write the failing test (guard)**

```python
# tests/test_e36_imports.py
def test_benchmark_and_calibration_modules_import():
    import sdlc.benchmarks.heatmap          # noqa: F401
    import sdlc.benchmarks.calibration      # noqa: F401
    from sdlc.benchmarks.report import (    # noqa: F401
        finalize_benchmark_report, write_heatmap, resolve_language_map)
    from sdlc.benchmarks.cli import dispatch_calibrate  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_e36_imports.py -v`
Expected: PASS if Tasks 1–9 landed cleanly (this is a regression guard, not a new behaviour). If it FAILS, fix the offending import before proceeding.

- [ ] **Step 3: Confirm worker imports**

Run: `python -c "import sdlc.worker"`
Expected: no error. If `worker.py` enumerates activities and errors on a missing symbol, no change is needed here because no activity was added; investigate any error as a real import bug.

- [ ] **Step 4: Run the full benchmark test slice**

Run: `python -m pytest tests/ -k "benchmark or calibration or heatmap or e36" -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add tests/test_e36_imports.py
git commit -m "test(benchmarks): E-36 import guard (heatmap + calibration) (E-36)"
```

---

### Task 11: Docs — FR-110 (PRD), ROADMAP mark, calibration README

**Files:**
- Modify: `PRD.md` (add FR-110)
- Modify: `ROADMAP.md` (mark E-36 landed)
- Create: `benchmarks/calibration/README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Add FR-110 to `PRD.md`**

Insert after the FR-704 block (the observability export bullet, ~line 229):

```markdown
- **FR-110 (new scope) — Rubric-judge calibration.** Before a rubric's
  LLM-judge score is trusted in a phase-exit decision, the factory SHALL
  support calibrating that rubric against a sample of human-scored fixtures
  and SHALL report judge-human agreement (a within-epsilon agreement rate,
  mean absolute error, and rank correlation) per rubric. A rubric's
  calibration verdict and agreement rate SHALL be surfaced alongside every
  score derived from it, so a rubric score is never read without its trust
  level. Calibration is an offline measurement tool; it SHALL NOT modify
  scores or gate outcomes automatically -- low agreement is a rubric defect
  to be fixed, not an automatic adjustment.
```

- [ ] **Step 2: Mark E-36 landed in `ROADMAP.md`**

Change the E-36 line (currently `- [ ] **E-36 (new scope)** Error heatmap ...`) to `- [x]` and append a landed-note sentence mirroring the house style, e.g.:

```markdown
  *Landed:* `src/sdlc/benchmarks/heatmap.py` (case x stage rework-density
  grid) written by `finalize_benchmark_report` as `heatmap.{html,json}`;
  `src/sdlc/benchmarks/calibration.py` + `sdlc calibrate <rubric>` report
  within-epsilon agreement + MAE + Spearman over human-scored fixtures,
  surfaced as a trust level beside every rubric score (PRD FR-110). Session-
  derived waste (E-38) as a heatmap input and calibration-as-CI-gate (OQ-B4)
  deliberately deferred. Spec
  `docs/superpowers/specs/2026-07-24-error-heatmap-and-rubric-calibration-design.md`,
  plan `docs/superpowers/plans/2026-07-24-error-heatmap-and-rubric-calibration.md`.
```

- [ ] **Step 3: Write the calibration README**

```markdown
<!-- benchmarks/calibration/README.md -->
# Rubric calibration fixtures (E-36 / FR-110)

Each `<rubric>/` directory holds hand-scored fixtures for one rubric
(= a proposer role: clarifier, architect, planner, qa, research, reviewer,
analyst). A fixture pins the produced artifact + the rubric text it was
scored against:

    { "artifact_json": "...", "rubric_ref": "cat-cafe-monitoring/architect",
      "rubric_text": "...", "rubric_sha": "...", "author_model": "...",
      "human_score": 0.8, "human_components": {...},
      "scored_by": "you", "notes": "..." }

Workflow:
1. Seed fixtures (operator-runtime live capture, or hand-author them here).
2. Fill each `human_score` (0.0-1.0) by editing the file. Leave `null` to skip.
3. Run `python -m sdlc.cli calibrate <rubric> [--judge-model M]
   [--epsilon 0.15] [--threshold 0.75]`.
4. Read `<rubric>/calibration.json` and the "Rubric calibration" section of
   the benchmark report / heatmap.

The judge model MUST be a different model family than any fixture's
`author_model` (ADR-6); same-family fixtures are skipped with a warning.
Aim for 20-30 scored fixtures before trusting the agreement number.
```

- [ ] **Step 4: Verify docs render / no broken references**

Run: `python -m pytest tests/ -k "benchmark or calibration or heatmap or e36" -q`
Expected: PASS (docs changes don't affect tests; this confirms nothing regressed).

- [ ] **Step 5: Commit**

```bash
git add PRD.md ROADMAP.md benchmarks/calibration/README.md
git commit -m "docs: FR-110, E-36 landed, calibration README (E-36)"
```

---

## Self-Review

**1. Spec coverage:**
- Spec §2 (heatmap data model, density, canonical stages, language slice) → Task 1. ✓
- Spec §2.5 (JSON + HTML renderers) → Task 2. ✓
- Spec §3 (wiring into finalize activity, language map, CLI) → Tasks 3, 4. ✓
- Spec §4 (fixture storage + `capture`/`calibrate` commands) → Tasks 5, 9. ✓
- Spec §5 (agreement metric: within-ε, MAE, Spearman) → Task 6; run_calibration → Task 7. ✓
- Spec §5.1 (trust surfacing: calibration table + per-score annotation) → Task 8 (`render_calibration_markdown/html`, trust column via `STAGE_TO_RUBRIC`). ✓
- Spec §6 (FR-110 PRD line) → Task 11. ✓
- Spec §7 (tests) → each task is TDD; guard in Task 10. ✓
- Spec §9 (out of scope: session waste, CI gate) → recorded in Task 11 ROADMAP note; not built. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to Task N". Every code step shows complete code. ✓

**3. Type consistency:**
- `HeatmapCell`/`Heatmap` fields identical across Tasks 1, 2, 3. ✓
- `build_heatmap(records, language_by_case)` signature matches its callers in Tasks 3, 4. ✓
- `CalibrationFixture` fields identical across Tasks 5, 7, 8, 9. ✓
- `AgreementStats` (Task 6) consumed by `run_calibration` (Task 7) → flattened into `CalibrationReport`; field names (`agreement_rate`, `mae`, `spearman`, `verdict`, `epsilon`, `threshold`, `n`→`n_fixtures`) match. ✓
- `render_markdown(summaries, calibration=None)` — existing callers pass no 2nd arg (backward-compatible default); new callers in Tasks 3/4/8 pass `calibration`. ✓
- `write_heatmap` gains `calibration_html=""` in Task 8; Task 3 introduced it without the arg (default preserves Task 3 tests). ✓
- `trust_for_stage` / `STAGE_TO_RUBRIC` used only in Task 8. ✓
- CLI: `dispatch_calibrate(rubric, *, judge_model, epsilon, threshold, calib_root)` matches its call in `sdlc/cli.py` (Task 9). ✓

**Note for the implementer:** Task 8 revises `finalize_benchmark_report` and `dispatch_report` (first written in Tasks 3/4) to load calibration reports and pass them through. Re-run Tasks 3/4 tests after Task 8 — they are listed in Task 8 Step 4.
