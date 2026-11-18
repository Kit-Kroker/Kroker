"""026 T001 (FR-001, research R1): one resolver for both run-evidence roots.

`SDLC_RUNS_ROOT` used to drive neither evidence store, so `benchmark score`
read the fleet only from a CWD whose `runs/` happened to be the fleet root.
`sdlc.runs_paths` is the single resolver; these tests pin its contract:

- precedence: explicit SDLC_BENCHMARKS_ROOT / SDLC_EXPORT_ROOT wins, else
  $SDLC_RUNS_ROOT/benchmarks or $SDLC_RUNS_ROOT/pipeline, else today's CWD
  defaults (runs/benchmarks and ./runs/pipeline);
- parity: what the writers write (recorder, export activity) is exactly what
  the reader (evidence.load_evidence) reads, for every env combination;
- roots_report() names each half's root and how it was chosen;
- explicit_export_root() is the explicit SDLC_EXPORT_ROOT or None;
- source guard: no module but runs_paths.py reads those two vars.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sdlc import runs_paths
from sdlc.benchmarks import evidence, recorder
from sdlc.benchmarks.models import (
    BenchmarkOutcome,
    BenchmarkRecord,
    BenchmarkScope,
    CostBag,
    QualityScore,
    SpeedBag,
)
from sdlc.core.models import HarnessKind, RunSummary
from sdlc.observability.activities import RunExportInput, export_run_artifacts
from sdlc.observability.trace import RunEvent, RunEventKind

T0 = datetime(2026, 11, 18, 10, tzinfo=UTC)

ROOT_VARS = ("SDLC_RUNS_ROOT", "SDLC_EXPORT_ROOT", "SDLC_BENCHMARKS_ROOT", "SDLC_ARTIFACT_ROOT")
GUARDED_VARS = {"SDLC_EXPORT_ROOT", "SDLC_BENCHMARKS_ROOT"}

SRC = Path(__file__).resolve().parents[1] / "src" / "sdlc"


# --- env combinations ------------------------------------------------------
#
# Each case: (set X=SDLC_RUNS_ROOT?, set Y=SDLC_EXPORT_ROOT?, set
# Z=SDLC_BENCHMARKS_ROOT?), then the expected (records root, export root) as
# a function of (cwd, X, Y, Z) and the expected (records_how, export_how).

ENV_CASES = [
    pytest.param(
        (False, False, False),
        lambda cwd, x, y, z: (cwd / "runs" / "benchmarks", cwd / "runs" / "pipeline"),
        ("default", "default"),
        id="none",
    ),
    pytest.param(
        (True, False, False),
        lambda cwd, x, y, z: (x / "benchmarks", x / "pipeline"),
        ("runs_root", "runs_root"),
        id="runs_root_only",
    ),
    pytest.param(
        (True, True, False),
        lambda cwd, x, y, z: (x / "benchmarks", y),
        ("runs_root", "explicit"),
        id="runs_root_plus_explicit_export",
    ),
    pytest.param(
        (True, False, True),
        lambda cwd, x, y, z: (z, x / "pipeline"),
        ("explicit", "runs_root"),
        id="runs_root_plus_explicit_benchmarks",
    ),
    pytest.param(
        (False, True, True),
        lambda cwd, x, y, z: (z, y),
        ("explicit", "explicit"),
        id="explicit_only",
    ),
]


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """A clean env and a fresh CWD; X/Y/Z are distinct dirs under tmp_path."""
    for var in ROOT_VARS:
        monkeypatch.delenv(var, raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    x, y, z = tmp_path / "X", tmp_path / "Y", tmp_path / "Z"

    def apply(flags):
        set_x, set_y, set_z = flags
        if set_x:
            monkeypatch.setenv("SDLC_RUNS_ROOT", str(x))
        if set_y:
            monkeypatch.setenv("SDLC_EXPORT_ROOT", str(y))
        if set_z:
            monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", str(z))
        return cwd, x, y, z

    return apply


def _abs(p) -> Path:
    """Resolve against the (monkeypatched) CWD so relative defaults compare."""
    return Path(p).resolve()


def _record(run_id: str) -> BenchmarkRecord:
    return BenchmarkRecord(
        run_id=run_id,
        bench_run_id="bench-026",
        cell_id="cell-1",
        case_id="c1",
        scope=BenchmarkScope.STAGE,
        stage="code",
        role="dev",
        harness=HarnessKind.OPENCODE,
        model="m",
        quality=QualityScore(score=1.0, judge="contract"),
        cost=CostBag(usd=1.0),
        speed=SpeedBag(wall_clock_s=2.0, started_at=T0, ended_at=T0 + timedelta(seconds=2)),
        outcome=BenchmarkOutcome.PASS,
    )


def _summary(run_id: str) -> RunSummary:
    return RunSummary(
        run_id=run_id,
        mode="greenfield",
        outcome="deployed:pr",
        terminal_stage="deploy",
        started_at=T0,
        ended_at=T0,
        duration_s=0.0,
    )


# --- resolver precedence ---------------------------------------------------


@pytest.mark.parametrize(("flags", "expected", "hows"), ENV_CASES)
def test_resolver_follows_precedence(roots, flags, expected, hows):
    cwd, x, y, z = roots(flags)
    want_records, want_export = expected(cwd, x, y, z)
    assert _abs(runs_paths.benchmarks_root()) == _abs(want_records)
    assert _abs(runs_paths.export_root()) == _abs(want_export)


@pytest.mark.parametrize(("flags", "expected", "hows"), ENV_CASES)
def test_roots_report_names_root_and_how_for_each_half(roots, flags, expected, hows):
    cwd, x, y, z = roots(flags)
    want_records, want_export = expected(cwd, x, y, z)
    report = runs_paths.roots_report()
    assert _abs(report.records) == _abs(want_records)
    assert _abs(report.export) == _abs(want_export)
    assert (report.records_how, report.export_how) == hows


# --- writer/reader parity --------------------------------------------------


@pytest.mark.parametrize(("flags", "expected", "hows"), ENV_CASES)
def test_writer_roots_equal_reader_roots(roots, flags, expected, hows):
    """The recorder's root and the evidence reader's roots are the resolver's."""
    cwd, x, y, z = roots(flags)
    want_records, want_export = expected(cwd, x, y, z)
    # writer, records half
    assert _abs(recorder._root()) == _abs(want_records)
    # reader, summaries half (evidence.export_root with no argument)
    assert _abs(evidence.export_root()) == _abs(want_export)


@pytest.mark.asyncio
@pytest.mark.parametrize(("flags", "expected", "hows"), ENV_CASES)
async def test_what_the_fleet_writes_the_scorer_reads(roots, flags, expected, hows):
    """End to end: record_benchmark + export_run_artifacts write, then
    load_evidence(all_=True) finds both the record and the run summary."""
    cwd, x, y, z = roots(flags)
    want_records, want_export = expected(cwd, x, y, z)

    await recorder.record_benchmark(_record("run-026"))
    out = await export_run_artifacts(
        RunExportInput(
            run_id="run-026",
            summary=_summary("run-026"),
            trace=[RunEvent(seq=0, at=T0, kind=RunEventKind.RUN_FINISHED)],
        )
    )

    # the writers landed under the resolved roots
    assert (want_records / "bench-026").is_dir()
    assert _abs(out) == _abs(want_export / "run-026")
    assert (want_export / "run-026" / "summary.json").is_file()

    # the reader, with no argument overrides, sees exactly that
    ev = evidence.load_evidence(all_=True)
    assert [r.run_id for r in ev.records] == ["run-026"]
    assert [s.run_id for s in ev.summaries] == ["run-026"]
    assert (ev.selection_runs, ev.summary_runs) == (1, 1)


def test_load_evidence_argument_beats_env(roots, tmp_path):
    """The root= / export_root_= test seams still win over any env var."""
    roots((True, True, True))
    seam = tmp_path / "seam"
    assert _abs(evidence.export_root(str(seam))) == _abs(seam)


# --- defaults unchanged ----------------------------------------------------


def test_defaults_are_unchanged(roots):
    roots((False, False, False))
    assert Path(runs_paths.benchmarks_root()) == Path("runs/benchmarks")
    assert Path(runs_paths.export_root()) == Path("./runs/pipeline")


def test_default_constants_still_match_resolver(roots):
    roots((False, False, False))
    assert Path(recorder.DEFAULT_ROOT) == Path(runs_paths.benchmarks_root())
    assert Path(evidence.DEFAULT_EXPORT_ROOT) == Path(runs_paths.export_root())


# --- explicit_export_root (graph/store.py sibling rule) ---------------------


def test_explicit_export_root_none_when_unset(roots):
    roots((False, False, False))
    assert runs_paths.explicit_export_root() is None


def test_explicit_export_root_none_when_only_runs_root_set(roots):
    """SDLC_RUNS_ROOT is not an explicit export root: the graph sibling rule
    must not start firing because a fleet root is exported."""
    roots((True, False, False))
    assert runs_paths.explicit_export_root() is None


def test_explicit_export_root_returns_explicit_value(roots):
    cwd, x, y, z = roots((True, True, False))
    got = runs_paths.explicit_export_root()
    assert got is not None
    assert Path(got) == y


# --- source guard ----------------------------------------------------------


def _env_reads(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, var) for every read of a guarded var from the environment:
    os.environ.get("V"), os.getenv("V"), os.environ["V"] (load), "V" in os.environ."""

    def is_environ(node) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
            isinstance(node, ast.Name) and node.id == "environ"
        )

    def guarded(node) -> str | None:
        if isinstance(node, ast.Constant) and node.value in GUARDED_VARS:
            return node.value
        return None

    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args:
            f = node.func
            reads = (
                (isinstance(f, ast.Attribute) and f.attr == "get" and is_environ(f.value))
                or (isinstance(f, ast.Attribute) and f.attr == "getenv")
                or (isinstance(f, ast.Name) and f.id == "getenv")
            )
            if reads and (v := guarded(node.args[0])):
                hits.append((node.lineno, v))
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            if is_environ(node.value) and (v := guarded(node.slice)):
                hits.append((node.lineno, v))
        elif isinstance(node, ast.Compare) and any(
            isinstance(op, ast.In | ast.NotIn) for op in node.ops
        ):
            if any(is_environ(c) for c in node.comparators) and (v := guarded(node.left)):
                hits.append((node.lineno, v))
    return hits


def test_source_guard_scanner_sees_reads_and_ignores_writes():
    src = (
        "import os\n"
        "a = os.environ.get('SDLC_EXPORT_ROOT')\n"
        "b = os.getenv('SDLC_BENCHMARKS_ROOT')\n"
        "c = os.environ['SDLC_EXPORT_ROOT']\n"
        "d = 'SDLC_EXPORT_ROOT' in os.environ\n"
        "os.environ['SDLC_EXPORT_ROOT'] = '/x'\n"
        "e = os.environ.get('SDLC_ARTIFACT_ROOT')\n"
    )
    assert [line for line, _ in _env_reads(ast.parse(src))] == [2, 3, 4, 5]


def test_only_runs_paths_reads_the_root_env_vars():
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        if path == SRC / "runs_paths.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for line, var in _env_reads(tree):
            offenders.append(f"{path.relative_to(SRC.parent)}:{line} reads {var}")
    assert offenders == [], "route these through sdlc.runs_paths:\n" + "\n".join(offenders)


def test_runs_paths_module_exists_where_the_guard_expects():
    assert Path(runs_paths.__file__).resolve() == (SRC / "runs_paths.py").resolve()


# --- chaos / edge cases (026 T001, chaos QA) --------------------------------
#
# An exported-but-empty variable is UNSET, not "explicit ''": Path("") is the
# CWD, so treating it as explicit would silently score (or write) the CWD.


@pytest.mark.parametrize("var", ["SDLC_RUNS_ROOT", "SDLC_EXPORT_ROOT", "SDLC_BENCHMARKS_ROOT"])
def test_empty_var_alone_behaves_as_unset(roots, monkeypatch, var):
    cwd, *_ = roots((False, False, False))
    monkeypatch.setenv(var, "")
    assert _abs(runs_paths.benchmarks_root()) == _abs(cwd / "runs" / "benchmarks")
    assert _abs(runs_paths.export_root()) == _abs(cwd / "runs" / "pipeline")
    assert runs_paths.explicit_export_root() is None


def test_all_vars_empty_behave_as_unset(roots, monkeypatch):
    cwd, *_ = roots((False, False, False))
    for var in ("SDLC_RUNS_ROOT", "SDLC_EXPORT_ROOT", "SDLC_BENCHMARKS_ROOT"):
        monkeypatch.setenv(var, "")
    report = runs_paths.roots_report()
    assert _abs(report.records) == _abs(cwd / "runs" / "benchmarks")
    assert _abs(report.export) == _abs(cwd / "runs" / "pipeline")
    assert (report.records_how, report.export_how) == ("default", "default")


def test_empty_explicit_vars_defer_to_runs_root(roots, monkeypatch):
    cwd, x, y, z = roots((True, False, False))
    monkeypatch.setenv("SDLC_EXPORT_ROOT", "")
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", "")
    assert _abs(runs_paths.benchmarks_root()) == _abs(x / "benchmarks")
    assert _abs(runs_paths.export_root()) == _abs(x / "pipeline")
    assert runs_paths.explicit_export_root() is None


@pytest.mark.parametrize(
    ("empty", "hows"),
    [
        pytest.param("SDLC_EXPORT_ROOT", ("runs_root", "runs_root"), id="empty_export"),
        pytest.param("SDLC_BENCHMARKS_ROOT", ("runs_root", "runs_root"), id="empty_benchmarks"),
    ],
)
def test_roots_report_never_calls_an_empty_var_explicit(roots, monkeypatch, empty, hows):
    roots((True, False, False))
    monkeypatch.setenv(empty, "")
    report = runs_paths.roots_report()
    assert (report.records_how, report.export_how) == hows


def test_empty_vars_keep_writer_reader_parity(roots, monkeypatch):
    cwd, x, y, z = roots((True, False, False))
    monkeypatch.setenv("SDLC_EXPORT_ROOT", "")
    monkeypatch.setenv("SDLC_BENCHMARKS_ROOT", "")
    assert _abs(recorder._root()) == _abs(runs_paths.benchmarks_root()) == _abs(x / "benchmarks")
    assert _abs(evidence.export_root()) == _abs(runs_paths.export_root()) == _abs(x / "pipeline")


def test_relative_runs_root_resolves_against_cwd_for_both_halves(roots, monkeypatch):
    cwd, *_ = roots((False, False, False))
    monkeypatch.setenv("SDLC_RUNS_ROOT", "fleet/026")
    assert _abs(runs_paths.benchmarks_root()) == (cwd / "fleet" / "026" / "benchmarks").resolve()
    assert _abs(runs_paths.export_root()) == (cwd / "fleet" / "026" / "pipeline").resolve()
    report = runs_paths.roots_report()
    assert (report.records_how, report.export_how) == ("runs_root", "runs_root")
    # parity holds for a relative root too
    assert _abs(recorder._root()) == _abs(runs_paths.benchmarks_root())
    assert _abs(evidence.export_root()) == _abs(runs_paths.export_root())


@pytest.mark.parametrize(("flags", "expected", "hows"), ENV_CASES)
def test_trailing_slash_variants_resolve_the_same(roots, monkeypatch, flags, expected, hows):
    cwd, x, y, z = roots(flags)
    plain = (_abs(runs_paths.benchmarks_root()), _abs(runs_paths.export_root()))
    for var, flag in zip(
        ("SDLC_RUNS_ROOT", "SDLC_EXPORT_ROOT", "SDLC_BENCHMARKS_ROOT"), flags, strict=True
    ):
        if flag:
            monkeypatch.setenv(
                var, str({"SDLC_RUNS_ROOT": x, "SDLC_EXPORT_ROOT": y}.get(var, z)) + "/"
            )
    slashed = (_abs(runs_paths.benchmarks_root()), _abs(runs_paths.export_root()))
    assert slashed == plain
    report = runs_paths.roots_report()
    assert (report.records_how, report.export_how) == hows


def test_source_guard_ignores_the_demo_write():
    """src/sdlc/demo/__main__.py SETS SDLC_EXPORT_ROOT for its child; that
    write is allowed and must not trip the guard."""
    path = SRC / "demo" / "__main__.py"
    text = path.read_text(encoding="utf-8")
    assert 'os.environ["SDLC_EXPORT_ROOT"] =' in text, "the allowed write moved; update this test"
    assert _env_reads(ast.parse(text)) == []


def test_source_guard_catches_reads_with_a_default_argument():
    src = (
        "import os\n"
        "from os import environ, getenv\n"
        "a = os.environ.get('SDLC_EXPORT_ROOT', '')\n"
        "b = os.getenv('SDLC_BENCHMARKS_ROOT', 'runs/benchmarks')\n"
        "c = environ.get('SDLC_EXPORT_ROOT', None)\n"
        "d = getenv('SDLC_EXPORT_ROOT', default='x')\n"
    )
    assert [line for line, _ in _env_reads(ast.parse(src))] == [3, 4, 5, 6]
