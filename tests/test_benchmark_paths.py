"""012 T003 (RED): one cases location for every reader (FR-001, R-1).

The module under test, ``sdlc.benchmarks.paths``, does not exist yet --
its absence fails collection of this file, which IS this task's red
state. After ``paths.py`` lands every test here must pass: the env
variable is set with monkeypatch AFTER the module import (read at call
time, never importlib tricks), and every reader named in contract §1.1
resolves under the override.
"""

import os
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from sdlc.benchmarks import paths

# --- the leaf module itself -------------------------------------------------


def test_cases_dir_returns_override_when_set_read_at_call_time(tmp_path, monkeypatch):
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "cases"))
    assert paths.cases_dir() == Path(os.environ["SDLC_CASES_ROOT"])


def test_cases_dir_default_is_the_checkout_corpus(monkeypatch):
    monkeypatch.delenv("SDLC_CASES_ROOT", raising=False)
    expected = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"
    assert paths.cases_dir() == expected


def test_calibration_dir_is_the_override_cases_sibling(tmp_path, monkeypatch):
    cases = tmp_path / "cases"
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases))
    assert paths.calibration_dir() == cases.parent / "calibration"


def test_calibration_dir_default_is_the_checkout_calibration(monkeypatch):
    monkeypatch.delenv("SDLC_CASES_ROOT", raising=False)
    expected = Path(__file__).resolve().parents[1] / "benchmarks" / "calibration"
    assert paths.calibration_dir() == expected


# --- shared corpus fixture: a minimal case dir shaped like the real ones ----


def _write_case(root: Path, case_id: str, *, language: str | None = "python") -> Path:
    """Minimal case dir copied from the real corpus shapes
    (benchmarks/cases/todo-api-greenfield/): case.yaml, one rubric file,
    one tasks.yaml, an oracle/ dir."""
    case_dir = root / case_id
    case_dir.mkdir(parents=True)
    manifest = {
        "case_id": case_id,
        "idea_summary": "s",
        "mode": "greenfield",
        "rubrics": {"architect": "rubric-architect.md"},
    }
    if language is not None:
        manifest["language"] = language
    (case_dir / "case.yaml").write_text(yaml.safe_dump(manifest), encoding="utf-8")
    (case_dir / "rubric-architect.md").write_text("ARCHITECT RUBRIC TEXT", encoding="utf-8")
    (case_dir / "tasks.yaml").write_text(
        yaml.safe_dump(
            {
                "tasks": [
                    {
                        "id": "create",
                        "error_class": "functional",
                        "oracle_tests": ["test_crud.py::test_create"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "oracle").mkdir()
    (case_dir / "oracle" / "test_crud.py").write_text(
        "def test_create():\n    assert True\n", encoding="utf-8"
    )
    return case_dir


# --- contract §1.1: each reader resolves through the override ---------------


@pytest.mark.asyncio
async def test_load_case_assets_reads_under_the_override(tmp_path, monkeypatch):
    from sdlc.benchmarks import judge

    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    case = _write_case(tmp_path, "paths-case")
    out = await judge.load_case_assets("paths-case", {"architect": "rubric-architect.md"})
    assert out == {"architect": (case / "rubric-architect.md").read_text(encoding="utf-8")}


def test_resolve_language_map_reads_under_the_override(tmp_path, monkeypatch):
    from sdlc.benchmarks import report

    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    _write_case(tmp_path, "paths-case")
    # no explicit directory argument: the default must be the override
    got = report.resolve_language_map(["paths-case", "absent-case"])
    assert got == {"paths-case": "python", "absent-case": ""}


def test_load_task_suite_reads_under_the_override(tmp_path, monkeypatch):
    from sdlc.benchmarks import tasks as bench_tasks

    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    _write_case(tmp_path, "paths-case")
    suite = bench_tasks.load_task_suite("paths-case")  # no explicit directory
    assert suite is not None
    assert [t.id for t in suite.tasks] == ["create"]
    assert suite.tasks[0].oracle_tests == ["test_crud.py::test_create"]


@pytest.mark.asyncio
async def test_oracle_case_lookup_reads_under_the_override(tmp_path, monkeypatch):
    """grade_oracle resolves <cases_root>/<case>/oracle before anything
    else (oracle.py). The case exists ONLY under the override, and the
    language has no toolchain adapter, so the grade returns before any
    git or shell work: finding the oracle dir proves the lookup went
    through the override, and the control (env unset) proves the default
    corpus does not contain it."""
    from sdlc.benchmarks.oracle import OracleInput, grade_oracle

    case_id = "zz-override-only-case"
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    _write_case(tmp_path, case_id)
    grade = await grade_oracle(
        OracleInput(case_id=case_id, repo_url="unused", run_id="r", language="ruby")
    )
    assert grade.detail == "no toolchain adapter for 'ruby'"

    monkeypatch.delenv("SDLC_CASES_ROOT", raising=False)
    control = await grade_oracle(
        OracleInput(case_id=case_id, repo_url="unused", run_id="r", language="ruby")
    )
    assert control.detail == "no oracle dir for case"


def test_load_calibration_reports_default_root_is_the_override_sibling(tmp_path, monkeypatch):
    from sdlc.benchmarks.calibration import CalibrationReport, load_calibration_reports

    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "cases"))
    # load_calibration_reports() takes no explicit root here; its default
    # must be calibration_dir() == the sibling of the overridden cases dir.
    bucket = tmp_path / "calibration" / "clarifier"
    bucket.mkdir(parents=True)
    rep = CalibrationReport(
        rubric="clarifier",
        judge_model="openai/gpt-5.2",
        n_fixtures=3,
        epsilon=0.1,
        threshold=0.8,
        agreement_rate=0.9,
        mae=0.05,
        spearman=0.95,
        verdict="pass",
        computed_at=datetime(2026, 10, 7),
    )
    (bucket / "calibration.json").write_text(rep.model_dump_json(), encoding="utf-8")
    got = load_calibration_reports()
    assert set(got) == {"clarifier"}
    assert got["clarifier"].agreement_rate == 0.9


def test_dispatch_verify_case_default_root_reads_under_the_override(tmp_path, monkeypatch):
    from sdlc.benchmarks import cli

    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    # A case dir with no reference/: verify_case fails fast naming the
    # path it resolved, so the default (cases_root=None) resolution is
    # observed without running any real oracle suite.
    (tmp_path / "verify-case").mkdir()
    out = cli.dispatch_verify_case(case="verify-case")
    assert "FAIL" in out
    assert str(tmp_path / "verify-case") in out


def test_dispatch_import_deveval_default_dest_is_the_override(tmp_path, monkeypatch):
    """The default ``out`` of dispatch_import_deveval must be the override.
    convert_repo does a full corpus conversion, so the smallest honest
    observation point is a stub in its place that records the dest_root it
    would have been handed (the function imports it locally from
    sdlc.benchmarks.importers.deveval at call time)."""
    from sdlc.benchmarks import cli
    from sdlc.benchmarks.importers.deveval import ImportReport

    captured: dict[str, Path] = {}

    def fake_convert_repo(src, dest_root, *, judge_model):
        captured["dest_root"] = Path(dest_root)
        return ImportReport(
            case_id="deveval-x",
            source_repo=str(src),
            network_required=False,
            n_tasks=1,
            n_oracle_tests=1,
            reference_files=1,
        )

    monkeypatch.setattr("sdlc.benchmarks.importers.deveval.convert_repo", fake_convert_repo)
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path / "cases"))
    # src is the DevEval benchmark_data/<language> dir: its children are the
    # repositories, so point it at devcorpus/ holding somerepo/.
    src = tmp_path / "devcorpus" / "somerepo"
    src.mkdir(parents=True)
    cli.dispatch_import_deveval(src=str(src.parent), out=None)
    assert captured["dest_root"] == paths.cases_dir()
    assert captured["dest_root"] == tmp_path / "cases"


# --- chaos seat: adversarial cases (012 T003) --------------------------------


def test_cases_dir_follows_a_mid_test_env_change(tmp_path, monkeypatch):
    """Call-time read means the SAME imported module follows the variable
    when it changes between two calls -- not just once after import."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    monkeypatch.setenv("SDLC_CASES_ROOT", str(first))
    assert paths.cases_dir() == Path(first)
    monkeypatch.setenv("SDLC_CASES_ROOT", str(second))
    assert paths.cases_dir() == Path(second)


def test_explicit_cases_dir_beats_the_override_for_task_suite(tmp_path, monkeypatch):
    from sdlc.benchmarks import tasks as bench_tasks

    explicit = tmp_path / "explicit"
    _write_case(explicit, "paths-case")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("SDLC_CASES_ROOT", str(elsewhere))
    suite = bench_tasks.load_task_suite("paths-case", cases_dir=explicit)
    assert suite is not None
    assert [t.id for t in suite.tasks] == ["create"]


def test_explicit_cases_dir_beats_the_override_for_language_map(tmp_path, monkeypatch):
    from sdlc.benchmarks import report

    explicit = tmp_path / "explicit"
    _write_case(explicit, "paths-case")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("SDLC_CASES_ROOT", str(elsewhere))
    got = report.resolve_language_map(["paths-case"], cases_dir=explicit)
    assert got == {"paths-case": "python"}


def test_explicit_calib_root_beats_the_override(tmp_path, monkeypatch):
    from sdlc.benchmarks.calibration import CalibrationReport, load_calibration_reports

    explicit = tmp_path / "explicit-calib"
    bucket = explicit / "clarifier"
    bucket.mkdir(parents=True)
    rep = CalibrationReport(
        rubric="clarifier",
        judge_model="openai/gpt-5.2",
        n_fixtures=1,
        epsilon=0.1,
        threshold=0.8,
        agreement_rate=0.7,
        mae=0.1,
        spearman=0.9,
        verdict="pass",
        computed_at=datetime(2026, 10, 7),
    )
    (bucket / "calibration.json").write_text(rep.model_dump_json(), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("SDLC_CASES_ROOT", str(elsewhere))
    got = load_calibration_reports(calib_root=explicit)
    assert set(got) == {"clarifier"}
    assert got["clarifier"].agreement_rate == 0.7


def test_override_with_trailing_slash_resolves_as_path_of_the_string(tmp_path, monkeypatch):
    value = str(tmp_path / "corpus") + "/"
    monkeypatch.setenv("SDLC_CASES_ROOT", value)
    assert paths.cases_dir() == Path(value)


def test_relative_override_resolves_as_path_of_the_string(monkeypatch):
    monkeypatch.setenv("SDLC_CASES_ROOT", "some-relative-corpus")
    assert paths.cases_dir() == Path("some-relative-corpus")


@pytest.mark.parametrize("shape", ["nested", "bare"], ids=["nested", "bare-dir"])
def test_calibration_dir_is_cases_parent_sibling_on_both_override_shapes(
    tmp_path, monkeypatch, shape
):
    """Names 2.1: calibration_dir() == cases_dir().parent / 'calibration',
    asserted as that exact expression for a nested override (.../x/cases)
    and a bare override (the corpus dir itself)."""
    cases = tmp_path / "x" / "cases" if shape == "nested" else tmp_path / "corpus"
    monkeypatch.setenv("SDLC_CASES_ROOT", str(cases))
    assert paths.calibration_dir() == paths.cases_dir().parent / "calibration"


# --- sixth site, added by orchestrator ruling (T003): the eval CLI ----------


def test_eval_cli_run_gate_receives_the_override(tmp_path, monkeypatch):
    """The prompt-eval CLI is a reader of case files (case.yaml + seeds),
    so FR-001's letter routes it through paths.cases_dir() too: with
    SDLC_CASES_ROOT set AFTER import, run_gate must be handed the override
    (call-time read), not the module-import-time checkout default."""
    from sdlc.eval import cli
    from sdlc.eval.verdict import GateVerdict, JudgeStatus, PromptGateResult

    captured: dict[str, Path] = {}

    def fake_run_gate(role, case, *, cases_root, **kw):
        captured["cases_root"] = Path(cases_root)
        return PromptGateResult(
            verdict=GateVerdict.PASS,
            judge_status=JudgeStatus.MEASURED,
            reason="stubbed",
            role=role,
            case=case,
        )

    monkeypatch.setattr("sdlc.eval.cli.run_gate", fake_run_gate)
    monkeypatch.setenv("SDLC_CASES_ROOT", str(tmp_path))
    out = cli.run_eval(
        "clarify", case="paths-case", against="HEAD", k=1, judge_model="openai/gpt-5.2", gate=False
    )
    assert "stubbed" in out
    assert captured["cases_root"] == tmp_path


# --- T004 (chaos seat): check_case_assets pre-flight -------------------------


def test_check_case_assets_all_present_returns_empty_list(tmp_path):
    from sdlc.benchmarks.paths import check_case_assets

    (tmp_path / "rubric-architect.md").write_text("RUBRIC", encoding="utf-8")
    (tmp_path / "veto-qa.md").write_text("VETO", encoding="utf-8")
    assert (
        check_case_assets({"architect": "rubric-architect.md"}, {"qa": "veto-qa.md"}, tmp_path)
        == []
    )


def test_check_case_assets_missing_rubric_message(tmp_path):
    from sdlc.benchmarks.paths import check_case_assets

    # Contract 1.2 verbatim: <kind> '<key>': <path> is missing
    got = check_case_assets({"architect": "rubric-architect.md"}, {}, tmp_path)
    assert got == [f"rubric 'architect': {tmp_path / 'rubric-architect.md'} is missing"]


def test_check_case_assets_whitespace_only_rubric_is_empty_variant(tmp_path):
    from sdlc.benchmarks.paths import check_case_assets

    (tmp_path / "rubric-architect.md").write_text("  \n\t\n", encoding="utf-8")
    # Contract 1.2 verbatim: <kind> '<key>': <path> is empty
    got = check_case_assets({"architect": "rubric-architect.md"}, {}, tmp_path)
    assert got == [f"rubric 'architect': {tmp_path / 'rubric-architect.md'} is empty"]


def test_check_case_assets_missing_veto_uses_veto_kind(tmp_path):
    from sdlc.benchmarks.paths import check_case_assets

    got = check_case_assets({}, {"qa": "veto-qa.md"}, tmp_path)
    assert got == [f"veto 'qa': {tmp_path / 'veto-qa.md'} is missing"]


def test_check_case_assets_absolute_registered_path_checked_as_given(tmp_path):
    from sdlc.benchmarks.paths import check_case_assets

    absent = tmp_path / "elsewhere" / "never-written.md"
    got = check_case_assets({"architect": str(absent)}, {}, tmp_path / "case")
    assert got == [f"rubric 'architect': {absent} is missing"]


def test_check_case_assets_empty_maps_return_empty_list(tmp_path):
    from sdlc.benchmarks.paths import check_case_assets

    assert check_case_assets({}, {}, tmp_path) == []


def test_check_case_assets_rubric_problem_before_veto_problem(tmp_path):
    """Order assumption (contract 1.2 / Names 2.1): problems are reported
    across the two maps in registration order -- every rubrics-map problem
    first, then every vetoes-map problem. The two-problem case here is the
    minimal lock on that cross-map order."""
    from sdlc.benchmarks.paths import check_case_assets

    got = check_case_assets({"architect": "absent-rubric.md"}, {"qa": "absent-veto.md"}, tmp_path)
    assert got == [
        f"rubric 'architect': {tmp_path / 'absent-rubric.md'} is missing",
        f"veto 'qa': {tmp_path / 'absent-veto.md'} is missing",
    ]


def test_check_case_assets_within_a_map_insertion_order_holds(tmp_path):
    """Order assumption: within one map, dict insertion order (not sorted
    order) -- 'zstage' is registered before 'astage' and must be reported
    first."""
    from sdlc.benchmarks.paths import check_case_assets

    rubrics = {"zstage": "rubric-z.md", "astage": "rubric-a.md"}
    got = check_case_assets(rubrics, {}, tmp_path)
    assert got == [
        f"rubric 'zstage': {tmp_path / 'rubric-z.md'} is missing",
        f"rubric 'astage': {tmp_path / 'rubric-a.md'} is missing",
    ]


def test_shipped_corpus_passes_check_case_assets():
    """The shipped corpus is clean and must stay clean: every
    benchmarks/cases/*/case.yaml passes the pre-flight with no problems."""
    from sdlc.benchmarks.cli import load_case_spec
    from sdlc.benchmarks.paths import check_case_assets

    cases_root = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"
    case_dirs = sorted(p for p in cases_root.iterdir() if (p / "case.yaml").is_file())
    assert case_dirs, "expected shipped cases under benchmarks/cases"
    for case_dir in case_dirs:
        spec = load_case_spec(str(case_dir / "case.yaml"))
        problems = check_case_assets(spec.rubrics, spec.vetoes, case_dir)
        assert problems == [], f"{case_dir.name}: {problems}"
