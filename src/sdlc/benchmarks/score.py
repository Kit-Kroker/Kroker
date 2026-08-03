"""The one writer. Turns an Evidence bundle into a score directory.

Every grid module stays pure (build_* + render_*); this module owns the
filesystem. Missing inputs degrade with a note in report.md and exit 0 --
a gap in the corpus is not a crash.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .evidence import Evidence
from .models import CompositeWeights

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BENCH_CONFIG = _REPO_ROOT / "benchmarks" / "config.yaml"


def parse_weights(s: str) -> CompositeWeights:
    """'0.6,0.2,0.2' -> CompositeWeights. Need not sum to 1: scoring.py
    renormalises over whichever axes have data in each group."""
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"--weights takes three floats as quality,cost,speed; got {s!r}")
    try:
        q, c, sp = (float(p) for p in parts)
    except ValueError as e:
        raise ValueError(
            f"--weights takes three floats as quality,cost,speed; got {s!r}"
        ) from e
    return CompositeWeights(quality=q, cost=c, speed=sp)


def load_config_weights(path: Path | None = None) -> CompositeWeights:
    """benchmarks/config.yaml has declared `weights:` since E-27 and nothing
    has ever read them. This is where they start mattering."""
    p = path if path is not None else _BENCH_CONFIG
    if not Path(p).is_file():
        return CompositeWeights()
    try:
        data = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
    except Exception:                                        # noqa: BLE001
        return CompositeWeights()
    w = data.get("weights") or {}
    return CompositeWeights(
        quality=float(w.get("quality", 0.6)),
        cost=float(w.get("cost", 0.2)),
        speed=float(w.get("speed", 0.2)))


def default_out_dir(selector: str, root: str | None = None) -> Path:
    from .recorder import _root
    base = Path(root if root is not None else _root())
    return base / selector / "score"


def write_score(ev: Evidence, out_dir: Path,
                weights: CompositeWeights) -> list[Path]:
    """Write every grid the evidence supports. Returns the paths written."""
    from .calibration import load_calibration_reports, render_calibration_html
    from .report import (aggregate, render_markdown, resolve_language_map,
                         write_heatmap)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    notes = list(ev.notes)

    calibration = load_calibration_reports()
    summaries = aggregate("", weights, _records=ev.records)

    lang = resolve_language_map(sorted({r.case_id for r in ev.records}))
    html_p, json_p = write_heatmap(ev.records, out_dir, lang,
                                   render_calibration_html(calibration))
    written += [html_p, json_p]

    written += _write_case_matrices(ev, out_dir, notes)

    md = render_markdown(summaries, calibration=calibration)
    md += _render_notes(notes)
    report_p = out_dir / "report.md"
    report_p.write_text(md, encoding="utf-8")
    written.append(report_p)
    return written


def _render_notes(notes: list[str]) -> str:
    """ASCII only (report.py:70-74)."""
    if not notes:
        return ""
    lines = ["", "## Notes", ""]
    lines += [f"- {n}" for n in notes]
    return "\n".join(lines) + "\n"


def _write_case_matrices(ev: Evidence, out_dir: Path,
                         notes: list[str]) -> list[Path]:
    """Per-case task and error matrices. A case with no tasks.yaml is
    skipped with a note -- today dispatch_history raises here (cli.py:92),
    and only todo-api-greenfield has the file."""
    from .error_matrix import (build_error_matrix, render_error_matrix_html,
                               render_error_matrix_json)
    from .task_matrix import (build_task_matrix, render_task_matrix_html,
                              render_task_matrix_json)
    from .tasks import load_task_suite

    written: list[Path] = []
    cases = sorted({r.case_id for r in ev.records})
    for case_id in cases:
        try:
            suite = load_task_suite(case_id)
        except Exception as e:                               # noqa: BLE001
            notes.append(f"case {case_id}: malformed tasks.yaml, task and "
                         f"error matrices skipped ({e})")
            continue
        if suite is None:
            notes.append(f"case {case_id}: no tasks.yaml, task and error "
                         f"matrices skipped")
            continue
        d = out_dir if len(cases) == 1 else out_dir / case_id
        d.mkdir(parents=True, exist_ok=True)
        tm = build_task_matrix(case_id, ev.records, suite)
        em = build_error_matrix(case_id, ev.records, suite)
        for name, text in (
            ("task-matrix.html", render_task_matrix_html(tm)),
            ("task-matrix.json", render_task_matrix_json(tm)),
            ("error-matrix.html", render_error_matrix_html(em)),
            ("error-matrix.json", render_error_matrix_json(em)),
        ):
            p = d / name
            p.write_text(text, encoding="utf-8")
            written.append(p)
    return written
