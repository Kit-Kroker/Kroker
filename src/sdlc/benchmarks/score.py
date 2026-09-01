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
        raise ValueError(f"--weights takes three floats as quality,cost,speed; got {s!r}")
    try:
        q, c, sp = (float(p) for p in parts)
    except ValueError as e:
        raise ValueError(f"--weights takes three floats as quality,cost,speed; got {s!r}") from e
    return CompositeWeights(quality=q, cost=c, speed=sp)


def load_config_weights(path: Path | None = None) -> CompositeWeights:
    """benchmarks/config.yaml has declared `weights:` since E-27 and nothing
    has ever read them. This is where they start mattering."""
    p = path if path is not None else _BENCH_CONFIG
    if not Path(p).is_file():
        return CompositeWeights()
    try:
        data = yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return CompositeWeights()
    w = data.get("weights") or {}
    return CompositeWeights(
        quality=float(w.get("quality", 0.6)),
        cost=float(w.get("cost", 0.2)),
        speed=float(w.get("speed", 0.2)),
    )


def default_out_dir(selector: str, root: str | None = None) -> Path:
    from .recorder import _root

    base = Path(root if root is not None else _root())
    return base / selector / "score"


# The judge kinds that produce a rubric SCORE on one comparable scale. The
# lenses and the deterministic instruments are excluded: they are different
# instruments, not two versions of one scale, and flagging them would raise
# a warning on every corpus.
_SCORING_JUDGES = {"llm_judge", "staged_rubric"}


def judge_mix_notes(records) -> list[str]:
    """One note per case whose scored records span more than one scoring
    judge kind (E-83 spec 2.1).

    E-83 replaced the single-shot rubric judge with a staged one, which moves
    the scale quality_score is measured on. The `judge` field makes the
    boundary queryable; this makes averaging across it visible in report.md
    instead of implicit. Pure -- score.py owns the filesystem, not this.
    """
    from collections import defaultdict

    by_case = defaultdict(set)
    for r in records:
        if r.quality.score is None:
            continue
        if r.quality.judge in _SCORING_JUDGES:
            by_case[r.case_id].add(r.quality.judge)
    return [
        f"case {case}: quality scores span {len(kinds)} judge instruments "
        f"({', '.join(sorted(kinds))}) - E-83 changed the judge, so means "
        f"across this boundary mix two scales"
        for case, kinds in sorted(by_case.items())
        if len(kinds) > 1
    ]


def write_score(ev: Evidence, out_dir: Path, weights: CompositeWeights) -> list[Path]:
    """Write every grid the evidence supports. Returns the paths written."""
    from .calibration import load_calibration_reports, render_calibration_html
    from .report import aggregate, render_markdown, resolve_language_map, write_heatmap
    from .sc_rollup import (
        build_sc_rollup,
        render_sc_rollup_html,
        render_sc_rollup_json,
        render_sc_rollup_markdown,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    notes = list(ev.notes)
    notes += judge_mix_notes(ev.records)

    calibration = load_calibration_reports()
    summaries = aggregate("", weights, _records=ev.records)

    lang = resolve_language_map(sorted({r.case_id for r in ev.records}))
    html_p, json_p = write_heatmap(ev.records, out_dir, lang, render_calibration_html(calibration))
    written += [html_p, json_p]

    written += _write_case_matrices(ev, out_dir, notes)

    rollup = build_sc_rollup(ev.summaries, ev.records)
    for name, text in (
        ("sc-rollup.html", render_sc_rollup_html(rollup)),
        ("sc-rollup.json", render_sc_rollup_json(rollup)),
    ):
        p = out_dir / name
        p.write_text(text, encoding="utf-8")
        written.append(p)

    md = render_markdown(summaries, calibration=calibration)
    md += render_sc_rollup_markdown(rollup)
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


def _write_case_matrices(ev: Evidence, out_dir: Path, notes: list[str]) -> list[Path]:
    """Per-case grids. The waste matrix takes no tasks.yaml dependency and
    is written for every case; the task and error matrices need the suite
    and are skipped with a note when it is absent (today dispatch_history
    raises here, cli.py:92)."""
    from .agreement_matrix import (
        build_agreement_matrix,
        render_agreement_matrix_html,
        render_agreement_matrix_json,
    )
    from .error_matrix import build_error_matrix, render_error_matrix_html, render_error_matrix_json
    from .task_matrix import build_task_matrix, render_task_matrix_html, render_task_matrix_json
    from .tasks import load_task_suite
    from .waste_matrix import build_waste_matrix, render_waste_matrix_html, render_waste_matrix_json

    written: list[Path] = []
    cases = sorted({r.case_id for r in ev.records})
    for case_id in cases:
        d = out_dir if len(cases) == 1 else out_dir / case_id
        d.mkdir(parents=True, exist_ok=True)

        try:
            suite = load_task_suite(case_id)
        except Exception as e:  # noqa: BLE001
            notes.append(
                f"case {case_id}: malformed tasks.yaml, task and error matrices skipped ({e})"
            )
            suite = None

        wm = build_waste_matrix(case_id, ev.records, suite)
        for name, text in (
            ("waste-matrix.html", render_waste_matrix_html(wm)),
            ("waste-matrix.json", render_waste_matrix_json(wm)),
        ):
            p = d / name
            p.write_text(text, encoding="utf-8")
            written.append(p)
        if not wm.cells:
            notes.append(
                f"case {case_id}: no harness waste recorded "
                f"(runs predating waste capture, or no coding tasks)"
            )

        am = build_agreement_matrix(case_id, ev.records, suite)
        for name, text in (
            ("agreement-matrix.html", render_agreement_matrix_html(am)),
            ("agreement-matrix.json", render_agreement_matrix_json(am)),
        ):
            p = d / name
            p.write_text(text, encoding="utf-8")
            written.append(p)

        if suite is None:
            if not any(f"case {case_id}: malformed" in n for n in notes):
                notes.append(f"case {case_id}: no tasks.yaml, task and error matrices skipped")
            continue

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
