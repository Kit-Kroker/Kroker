"""Aggregate benchmark runs under runs/benchmarks/ into a self-contained HTML page.

Parses both the per-run ``report.md`` summary tables and the richer ``*.jsonl``
per-cell records, merges them by (run, case, stage), and emits an analyzable
HTML report with embedded data + Chart.js visualizations.

Usage:
    python scripts/aggregate_benchmarks.py [--runs runs/benchmarks]
                                            [--out docs/benchmark-analysis.html]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path

TS_RE = re.compile(r"-(\d{10})$")
REPORT_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|")


def run_ts(run_id: str) -> int | None:
    m = TS_RE.search(run_id)
    return int(m.group(1)) if m else None


def ts_to_iso(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, tz=dt.UTC).isoformat()


def parse_report(path: Path) -> list[dict]:
    """Parse a report.md table into rows. Empty / 'No records' -> []."""
    rows: list[dict] = []
    if not path.exists():
        return rows
    in_table = False
    headers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("|") and "---" in s:
            in_table = True
            continue
        if not in_table and s.startswith("|"):
            headers = [h.strip() for h in s.strip("|").split("|")]
            continue
        if in_table and s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            row = dict(zip(headers, cells, strict=False))
            rows.append(row)
        elif in_table and not s.startswith("|"):
            break
    return rows


def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    if s in ("", "n/a", "N/A", "null", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_jsonl(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def aggregate(runs_dir: Path) -> dict:
    run_dirs = sorted([p for p in runs_dir.iterdir() if p.is_dir() and p.name.startswith("bench-")])

    all_records: list[dict] = []
    runs_meta: list[dict] = []

    for rd in run_dirs:
        run_id = rd.name
        ts = run_ts(run_id)
        iso = ts_to_iso(ts) if ts else None

        report_rows = parse_report(rd / "report.md")
        records: list[dict] = []
        for jl in sorted(rd.glob("*.jsonl")):
            records.extend(load_jsonl(jl))
        for rec in records:
            rec["_run_id"] = run_id
            rec["_run_ts"] = ts
        all_records.extend(records)

        # Derive per-run aggregates from records (preferred) then report.
        stage_recs = [r for r in records if r.get("scope") == "stage"]
        task_recs = [r for r in records if r.get("scope") == "task_attempt"]

        case = (
            records[0]["case_id"]
            if records
            else (
                report_rows[0]["case"]
                if report_rows
                else run_id.split("bench-")[1].rsplit("-", 1)[0]
            )
        )

        total_wall = sum((r.get("speed") or {}).get("wall_clock_s") or 0 for r in records)
        stages_seen = sorted({r["stage"] for r in stage_recs if r.get("stage")})
        task_ids = sorted({r["task_id"] for r in task_recs if r.get("task_id")})

        # Per-task final outcome (last attempt).
        per_task_outcome: dict[str, str] = {}
        for r in task_recs:
            tid = r.get("task_id")
            if tid is None:
                continue
            per_task_outcome[tid] = r.get("outcome") or per_task_outcome.get(tid, "unknown")

        code_tasks_passed = sum(1 for o in per_task_outcome.values() if o == "pass")
        code_total = len(per_task_outcome)

        stage_outcomes = {}
        for r in stage_recs:
            st = r.get("stage")
            if st:
                stage_outcomes[st] = r.get("outcome")

        # Overall run outcome: merge stage if present, else whether all code tasks passed.
        if "merge" in stage_outcomes:
            overall = stage_outcomes["merge"]
        elif stage_outcomes:
            overall = "pass" if all(o == "pass" for o in stage_outcomes.values()) else "fail"
        elif code_total:
            overall = "pass" if code_tasks_passed == code_total else "fail"
        elif report_rows:
            # Infer from composite quality column presence of non-zero.
            qs = [num(rr.get("composite")) for rr in report_rows if rr.get("stage") == "merge"]
            overall = "pass" if (qs and qs[0] is not None) else "unknown"
        else:
            overall = "empty"

        # Wall per stage (records preferred, fall back to report).
        wall_by_stage: dict[str, float] = defaultdict(float)
        for r in stage_recs:
            st = r.get("stage")
            w = (r.get("speed") or {}).get("wall_clock_s") or 0
            if st:
                wall_by_stage[st] += w
        for r in task_recs:
            st = r.get("stage") or "code"
            w = (r.get("speed") or {}).get("wall_clock_s") or 0
            wall_by_stage[st] += w
        if not wall_by_stage:
            for rr in report_rows:
                st = rr.get("stage")
                w = num(rr.get("wall (s)"))
                if st and w is not None:
                    wall_by_stage[st] += w

        errors = [
            {"stage": r.get("stage"), "error": r.get("error")} for r in records if r.get("error")
        ]

        runs_meta.append(
            {
                "run_id": run_id,
                "case": case,
                "ts": ts,
                "iso": iso,
                "has_data": bool(
                    records or any(num(rr.get("composite")) is not None for rr in report_rows)
                ),
                "stage_count": len(stages_seen),
                "stages": stages_seen,
                "task_count": code_total,
                "task_ids": task_ids,
                "tasks_passed": code_tasks_passed,
                "total_wall_s": round(total_wall, 1),
                "overall": overall,
                "stage_outcomes": stage_outcomes,
                "wall_by_stage": dict(wall_by_stage),
                "fix_attempts_max": max((r.get("fix_attempts") or 0 for r in task_recs), default=0),
                "errors": errors,
                "record_count": len(records),
            }
        )

    runs_meta.sort(key=lambda r: r["ts"] or 0)

    # Aggregations.
    by_case = defaultdict(
        lambda: {"runs": 0, "with_data": 0, "passed": 0, "wall": 0.0, "tasks": 0, "tasks_passed": 0}
    )
    for r in runs_meta:
        c = by_case[r["case"]]
        c["runs"] += 1
        if r["has_data"]:
            c["with_data"] += 1
        if r["overall"] == "pass":
            c["passed"] += 1
        c["wall"] += r["total_wall_s"]
        c["tasks"] += r["task_count"]
        c["tasks_passed"] += r["tasks_passed"]

    # Stage outcome matrix: case -> stage -> {pass,fail}.
    stage_matrix: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"pass": 0, "fail": 0, "other": 0})
    )
    for r in runs_meta:
        for st, o in r["stage_outcomes"].items():
            bucket = stage_matrix[r["case"]][st]
            if o in ("pass", "fail"):
                bucket[o] += 1
            else:
                bucket["other"] += 1

    # Flatten records for the detail table (lightweight fields only).
    detail = []
    for r in all_records:
        detail.append(
            {
                "run_id": r["_run_id"],
                "run_ts": r["_run_ts"],
                "case": r.get("case_id"),
                "scope": r.get("scope"),
                "stage": r.get("stage"),
                "task_id": r.get("task_id"),
                "attempt": r.get("attempt"),
                "role": r.get("role"),
                "model": r.get("model"),
                "outcome": r.get("outcome"),
                "quality": (r.get("quality") or {}).get("score"),
                "judge": (r.get("quality") or {}).get("judge"),
                "wall_s": (r.get("speed") or {}).get("wall_clock_s"),
                "cost_usd": (r.get("cost") or {}).get("usd"),
                "fix_attempts": r.get("fix_attempts"),
                "error": r.get("error"),
                "started_at": (r.get("speed") or {}).get("started_at"),
            }
        )

    return {
        "generated_at": dt.datetime.now(tz=dt.UTC).isoformat(),
        "totals": {
            "runs": len(runs_meta),
            "with_data": sum(1 for r in runs_meta if r["has_data"]),
            "passed": sum(1 for r in runs_meta if r["overall"] == "pass"),
            "total_wall_s": round(sum(r["total_wall_s"] for r in runs_meta), 1),
            "total_records": len(all_records),
            "total_tasks": sum(r["task_count"] for r in runs_meta),
            "total_tasks_passed": sum(r["tasks_passed"] for r in runs_meta),
            "cases": len(by_case),
        },
        "by_case": {k: v for k, v in by_case.items()},
        "stage_matrix": {k: {s: d for s, d in v.items()} for k, v in stage_matrix.items()},
        "runs": runs_meta,
        "records": detail,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Benchmark Results Analysis</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js" defer></script>
<style>
  :root {
    --bg: #0d1117; --panel: #161b22; --panel2: #1c2330; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff; --green: #3fb950;
    --red: #f85149; --amber: #d29922; --purple: #bc8cff;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  header {
    padding: 24px 32px; border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, #161b22, #0d1117);
  }
  header h1 { margin: 0 0 4px; font-size: 22px; }
  header .sub { color: var(--muted); font-size: 13px; }
  main { max-width: 1400px; margin: 0 auto; padding: 24px 32px 80px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr)); gap: 12px; margin-bottom: 28px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
  .card .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
  .card .value { font-size: 26px; font-weight: 600; margin-top: 4px; }
  .card .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
  section { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 24px; }
  section h2 { margin: 0 0 4px; font-size: 16px; }
  section .desc { color: var(--muted); font-size: 12px; margin-bottom: 16px; }
  .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  @media (max-width: 1000px) { .grid2 { grid-template-columns: 1fr; } }
  .chart-box { position: relative; height: 320px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th { color: var(--muted); font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; cursor: pointer; user-select: none; }
  th:hover { color: var(--text); }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .scroll { overflow-x: auto; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
  .pill.pass { background: rgba(63,185,80,.15); color: var(--green); }
  .pill.fail { background: rgba(248,81,73,.15); color: var(--red); }
  .pill.other { background: rgba(139,148,158,.15); color: var(--muted); }
  .pill.empty { background: rgba(139,148,158,.08); color: var(--muted); }
.pill.case-cafe { background: rgba(188,140,255,.15); color: var(--purple); }
.pill.case-todo { background: rgba(88,166,255,.15); color: var(--accent); }
.pill.case-deveval { background: rgba(210,153,34,.15); color: #d29922; }
  .controls { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; }
  .controls select, .controls input { background: var(--panel2); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 6px 10px; font-size: 13px; }
  .controls label { color: var(--muted); font-size: 12px; display: inline-flex; gap: 6px; align-items: center; }
  .err { color: var(--red); font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; word-break: break-word; white-space: normal; max-width: 600px; }
  .muted { color: var(--muted); }
  .heatmap-cell { width: 100%; height: 22px; border-radius: 3px; min-width: 40px; }
  a.run { color: var(--accent); text-decoration: none; font-family: ui-monospace, monospace; font-size: 12px; }
  footer { color: var(--muted); font-size: 11px; text-align: center; padding: 24px; border-top: 1px solid var(--border); }
</style>
</head>
<body>
<header>
  <h1>Benchmark Results Analysis</h1>
  <div class="sub" id="gen"></div>
</header>
<main>
  <div class="cards" id="cards"></div>

  <section>
    <h2>Per-case summary</h2>
    <div class="desc">Aggregated across all runs. “With data” excludes runs that recorded nothing (aborted/empty).</div>
    <div class="scroll"><table id="caseTable"><thead><tr>
      <th>Case</th><th class="num">Runs</th><th class="num">With data</th>
      <th class="num">End-to-end pass</th><th class="num">Total wall (s)</th>
      <th class="num">Code tasks</th><th class="num">Tasks passed</th>
    </tr></thead><tbody></tbody></table></div>
  </section>

  <section>
    <h2>Wall-clock per run</h2>
    <div class="desc">Total seconds spent per run, stacked by stage. Empty runs (no data) excluded.</div>
    <div class="chart-box"><canvas id="wallChart"></canvas></div>
  </section>

  <div class="grid2">
    <section>
      <h2>Stage outcome heatmap</h2>
      <div class="desc">Pass/fail counts per case × stage across all runs.</div>
      <div class="scroll" id="heatmap"></div>
    </section>
    <section>
      <h2>Run outcomes over time</h2>
      <div class="desc">Each run plotted by start time; height = total wall-clock, color = outcome.</div>
      <div class="chart-box"><canvas id="trendChart"></canvas></div>
    </section>
  </div>

  <section>
    <h2>Run timeline</h2>
    <div class="desc">Click a column header to sort.</div>
    <div class="scroll"><table id="runTable"><thead><tr>
      <th>Run</th><th>Case</th><th>Started (UTC)</th><th class="num">Stages</th>
      <th class="num">Code tasks</th><th class="num">Tasks pass</th>
      <th class="num">Wall (s)</th><th class="num">Max fix</th><th>Overall</th>
    </tr></thead><tbody></tbody></table></div>
  </section>

  <section>
    <h2>Recorded errors</h2>
    <div class="desc">Every non-null error across all runs, with stage attribution.</div>
    <div class="scroll"><table id="errTable"><thead><tr>
      <th>Run</th><th>Case</th><th>Stage</th><th>Error</th>
    </tr></thead><tbody></tbody></table></div>
  </section>

  <section>
    <h2>All records</h2>
    <div class="desc"><span id="recCount"></span> individual records (stage + task attempts).</div>
    <div class="controls">
      <label>Case <select id="fCase"><option value="">all</option></select></label>
      <label>Stage <select id="fStage"><option value="">all</option></select></label>
      <label>Outcome <select id="fOutcome"><option value="">all</option><option>pass</option><option>fail</option></select></label>
      <label>Search <input id="fSearch" type="search" placeholder="error text, model…"></label>
    </div>
    <div class="scroll"><table id="recTable"><thead><tr>
      <th>Run</th><th>Case</th><th>Scope</th><th>Stage</th><th class="num">Task</th>
      <th class="num">Att.</th><th>Model</th><th>Outcome</th>
      <th class="num">Quality</th><th class="num">Wall (s)</th><th class="num">Fix</th><th>Error</th>
    </tr></thead><tbody></tbody></table></div>
  </section>
</main>
<footer>Generated from <code>runs/benchmarks/</code>. Single self-contained HTML; charts via Chart.js CDN.</footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);

function fmt(n, d=1){ return (n==null||isNaN(n)) ? '—' : Number(n).toFixed(d); }
function pct(a, b){ return b ? (100*a/b).toFixed(0)+'%' : '—'; }
function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML; }
function runShort(id){ return id.replace(/^bench-/,'').replace(/-(\\d{10})$/, m=>'…'+m.slice(-5)); }

const caseColors = {'cat-cafe-monitoring':'#bc8cff','todo-api-greenfield':'#58a6ff'};
function casePill(c){ const cls = c.startsWith('cat')?'case-cafe':(c.startsWith('deveval')?'case-deveval':'case-todo'); return '<span class="pill '+cls+'">'+esc(c)+'</span>'; }
function outPill(o){ const cls = ({pass:'pass',fail:'fail'})[o]||'other'; return '<span class="pill '+cls+'">'+esc(o||'—')+'</span>'; }

// Generated timestamp
document.getElementById('gen').textContent = 'Generated ' + D.generated_at.replace('T',' ').slice(0,19) + ' UTC · ' + D.totals.runs + ' runs';

// Summary cards
const t = D.totals;
const cards = [
  ['Runs', t.runs, t.with_data + ' with data'],
  ['End-to-end pass', t.passed, pct(t.passed, t.with_data) + ' of with-data'],
  ['Cases', t.cases, Object.keys(D.by_case).join(', ')],
  ['Total wall', fmt(t.total_wall_s,0)+'s', (t.total_wall_s/3600).toFixed(2)+' h'],
  ['Records', t.total_records, 'stage + task attempts'],
  ['Code tasks', t.tasks_passed + '/' + t.tasks, pct(t.total_tasks_passed, t.total_tasks) + ' passed'],
];
document.getElementById('cards').innerHTML = cards.map(c =>
  '<div class="card"><div class="label">'+c[0]+'</div><div class="value">'+c[1]+'</div><div class="sub">'+c[2]+'</div></div>').join('');

// Per-case table
const caseBody = document.querySelector('#caseTable tbody');
Object.entries(D.by_case).sort().forEach(([c, v]) => {
  caseBody.insertAdjacentHTML('beforeend',
    '<tr><td>'+casePill(c)+'</td><td class="num">'+v.runs+'</td><td class="num">'+v.with_data+
    '</td><td class="num">'+v.passed+'</td><td class="num">'+fmt(v.wall,0)+'</td><td class="num">'+v.tasks+
    '</td><td class="num">'+v.tasks_passed+'</td></tr>');
});

// Run timeline table
const runBody = document.querySelector('#runTable tbody');
D.runs.forEach(r => {
  const started = r.iso ? r.iso.replace('T',' ').slice(0,19) : '—';
  runBody.insertAdjacentHTML('beforeend',
    '<tr><td><span class="run">'+esc(r.run_id)+'</span></td><td>'+casePill(r.case)+'</td>'+
    '<td class="muted">'+started+'</td><td class="num">'+r.stage_count+'</td>'+
    '<td class="num">'+(r.task_count||'—')+'</td><td class="num">'+(r.task_count? r.tasks_passed+'/'+r.task_count : '—')+'</td>'+
    '<td class="num">'+(r.total_wall_s? fmt(r.total_wall_s,0):'—')+'</td>'+
    '<td class="num">'+(r.fix_attempts_max||'—')+'</td><td>'+outPill(r.overall==='empty'?null:r.overall)+'</td></tr>');
});

// Errors table
const errBody = document.querySelector('#errTable tbody');
let errCount = 0;
D.runs.forEach(r => {
  (r.errors||[]).forEach(e => {
    errCount++;
    errBody.insertAdjacentHTML('beforeend',
      '<tr><td><span class="run">'+esc(runShort(r.run_id))+'</span></td><td>'+casePill(r.case)+'</td>'+
      '<td>'+esc(e.stage)+'</td><td class="err">'+esc(e.error)+'</td></tr>');
  });
});
if(!errCount) errBody.insertAdjacentHTML('beforeend','<tr><td colspan="4" class="muted">No errors recorded.</td></tr>');

// Heatmap
const allStages = [...new Set(Object.values(D.stage_matrix).flatMap(Object.keys))];
const casesHM = Object.keys(D.stage_matrix).sort();
let hm = '<table><thead><tr><th>Case \\ Stage</th>';
allStages.forEach(s => hm += '<th class="num">'+esc(s)+'</th>');
hm += '</tr></thead><tbody>';
casesHM.forEach(c => {
  hm += '<tr><td>'+casePill(c)+'</td>';
  allStages.forEach(s => {
    const cell = (D.stage_matrix[c]||{})[s] || {pass:0,fail:0,other:0};
    const total = cell.pass+cell.fail+cell.other;
    if(!total){ hm += '<td class="muted">·</td>'; return; }
    const passFrac = cell.pass/total;
    const bg = passFrac>=0.999 ? 'rgba(63,185,80,'+(0.3+0.5*passFrac)+')'
             : passFrac<=0.001 ? 'rgba(248,81,73,0.7)'
             : 'rgba(210,153,34,'+(0.4)+')';
    const txt = cell.pass+'/'+total;
    hm += '<td class="num" title="'+cell.pass+' pass / '+cell.fail+' fail / '+cell.other+' other"><span class="heatmap-cell" style="background:'+bg+';display:inline-flex;align-items:center;justify-content:center;color:#0d1117;font-weight:600;font-size:11px">'+txt+'</span></td>';
  });
  hm += '</tr>';
});
hm += '</tbody></table>';
document.getElementById('heatmap').innerHTML = hm;

// Filters for records
const fCase = document.getElementById('fCase');
const fStage = document.getElementById('fStage');
[...new Set(D.records.map(r=>r.case))].sort().forEach(c => fCase.insertAdjacentHTML('beforeend','<option>'+esc(c)+'</option>'));
[...new Set(D.records.map(r=>r.stage).filter(Boolean))].sort().forEach(s => fStage.insertAdjacentHTML('beforeend','<option>'+esc(s)+'</option>'));
const recBody = document.querySelector('#recTable tbody');
function renderRecords(){
  const fc=fCase.value, fs=fStage.value, fo=document.getElementById('fOutcome').value, fsr=document.getElementById('fSearch').value.toLowerCase();
  recBody.innerHTML='';
  let n=0;
  for(const r of D.records){
    if(fc && r.case!==fc) continue;
    if(fs && r.stage!==fs) continue;
    if(fo && r.outcome!==fo) continue;
    if(fsr){
      const hay = [r.error,r.model,r.run_id,r.stage].join(' ').toLowerCase();
      if(!hay.includes(fsr)) continue;
    }
    n++;
    if(n>500){ continue; }
    recBody.insertAdjacentHTML('beforeend',
      '<tr><td><span class="run">'+esc(runShort(r.run_id))+'</span></td><td>'+casePill(r.case)+'</td>'+
      '<td>'+esc(r.scope)+'</td><td>'+esc(r.stage||'—')+'</td><td class="num">'+esc(r.task_id||'—')+'</td>'+
      '<td class="num">'+esc(r.attempt??'—')+'</td><td>'+esc(r.model||'—')+'</td>'+
      '<td>'+outPill(r.outcome)+'</td><td class="num">'+(r.quality==null?'—':fmt(r.quality,2))+'</td>'+
      '<td class="num">'+(r.wall_s==null?'—':fmt(r.wall_s,1))+'</td>'+
      '<td class="num">'+esc(r.fix_attempts??'—')+'</td>'+
      '<td class="err">'+(r.error?esc(r.error.slice(0,160)+(r.error.length>160?'…':'')):'')+'</td></tr>');
  }
  document.getElementById('recCount').textContent = n + (n>500?' (showing first 500)':'') + ' / ' + D.records.length;
}
[fCase,fStage,document.getElementById('fOutcome'),document.getElementById('fSearch')].forEach(el=>el.addEventListener('input',renderRecords));
renderRecords();

// Sortable tables
document.querySelectorAll('table').forEach(tbl => {
  tbl.querySelector('thead')?.addEventListener('click', e => {
    if(e.target.tagName!=='TH') return;
    const th = e.target; const idx = [...th.parentNode.children].indexOf(th);
    const tbody = tbl.querySelector('tbody'); const rows=[...tbody.querySelectorAll('tr')];
    if(!rows.length) return;
    const asc = th.dataset.asc === '1' ? -1 : 1; th.dataset.asc = asc>0?'1':'0';
    rows.sort((a,b)=>{
      let va=a.children[idx]?.textContent||'', vb=b.children[idx]?.textContent||'';
      const na=parseFloat(va.replace(/[^0-9.\\-]/g,'')), nb=parseFloat(vb.replace(/[^0-9.\\-]/g,''));
      if(!isNaN(na)&&!isNaN(nb)&&va.match(/\\d/)) return (na-nb)*asc;
      return va.localeCompare(vb)*asc;
    });
    rows.forEach(r=>tbody.appendChild(r));
  });
});

// Charts (wait for Chart.js)
window.addEventListener('load', () => {
  if(typeof Chart==='undefined'){ return; }
  Chart.defaults.color = '#8b949e';
  Chart.defaults.borderColor = '#30363d';

  // Wall-clock stacked bar by stage
  const runsData = D.runs.filter(r=>r.has_data && r.total_wall_s>0);
  const stagesAll = [...new Set(runsData.flatMap(r=>Object.keys(r.wall_by_stage||{})))];
  const palette = ['#58a6ff','#3fb950','#bc8cff','#d29922','#f85149','#56d4dd','#ff7b72','#79c0ff'];
  new Chart(document.getElementById('wallChart'), {
    type:'bar',
    data:{ labels: runsData.map(r=>runShort(r.run_id)),
      datasets: stagesAll.map((s,i)=>({ label:s, backgroundColor:palette[i%palette.length],
        data: runsData.map(r=>+(r.wall_by_stage[s]||0).toFixed(1)) })) },
    options:{ responsive:true, maintainAspectRatio:false, indexAxis:'y',
      scales:{ x:{stacked:true, title:{display:true,text:'seconds'}}, y:{stacked:true} },
      plugins:{ legend:{position:'bottom'} } } });

  // Trend: scatter, x=time, y=wall, color=outcome
  const tr = D.runs.filter(r=>r.ts && r.total_wall_s>0);
  const cmap = {pass:'#3fb950', fail:'#f85149', unknown:'#d29922', empty:'#8b949e'};
  new Chart(document.getElementById('trendChart'), {
    type:'scatter',
    data:{ datasets: ['pass','fail','unknown','empty'].map(o=>({
      label:o, backgroundColor:cmap[o],
      data: tr.filter(r=>(r.overall||'empty')===o).map(r=>({x:r.ts*1000, y:r.total_wall_s}))
    })) },
    options:{ responsive:true, maintainAspectRatio:false,
      scales:{ x:{type:'time', time:{displayFormats:{day:'MMM d'}}, title:{display:true,text:'run start'}},
               y:{title:{display:true,text:'wall (s)'}, beginAtZero:true} },
      plugins:{ legend:{position:'bottom'},
        tooltip:{callbacks:{ label:c=>new Date(c.parsed.x).toISOString().slice(0,16)+': '+c.parsed.y+'s' }} } } });
});
</script>
</body>
</html>
"""


def build_html(data: dict) -> str:
    payload = json.dumps(data, default=str)
    return HTML_TEMPLATE.replace("__DATA__", payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs/benchmarks", type=Path)
    ap.add_argument("--out", default="docs/benchmark-analysis.html", type=Path)
    args = ap.parse_args()

    data = aggregate(args.runs.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_html(data), encoding="utf-8")
    print(f"wrote {args.out}  ({args.out.stat().st_size:,} bytes)")
    print(
        f"  runs={data['totals']['runs']}  with_data={data['totals']['with_data']}  "
        f"passed={data['totals']['passed']}  records={data['totals']['total_records']}"
    )


if __name__ == "__main__":
    main()
