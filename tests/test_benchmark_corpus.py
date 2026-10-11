from pathlib import Path

import pytest

from sdlc.benchmarks.corpus import load_corpus, smoke_case
from sdlc.benchmarks.matrix import expand_matrix
from sdlc.benchmarks.models import CaseRole, CaseVisibility

CASES_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"

CORPUS_BASE_CELL_IDS = {
    "cat-cafe-monitoring": "cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.2",
    "deveval-geotext": "deveval-geotext#opencode#zai-coding-plan-glm-5.2",
    "deveval-hone": "deveval-hone#opencode#zai-coding-plan-glm-5.2",
    "deveval-lice": "deveval-lice#opencode#zai-coding-plan-glm-5.2",
    "deveval-particle-swarm-optimization": (
        "deveval-particle-swarm-optimization#opencode#zai-coding-plan-glm-5.2"
    ),
    "deveval-readtime": "deveval-readtime#opencode#zai-coding-plan-glm-5.2",
    "deveval-stocktrends": "deveval-stocktrends#opencode#zai-coding-plan-glm-5.2",
}


def test_load_corpus_returns_ten_specs_with_roles_and_visibilities():
    specs = load_corpus(CASES_ROOT)
    assert len(specs) == 10
    by_id = {s.case_id: s for s in specs}

    assert by_id["todo-api-greenfield"].role == CaseRole.SMOKE
    assert by_id["cat-cafe-monitoring"].role == CaseRole.CORPUS
    assert by_id["cat-cafe-monitoring"].visibility == CaseVisibility.PRIVATE

    deveval_ids = [
        "deveval-geotext",
        "deveval-hone",
        "deveval-lice",
        "deveval-particle-swarm-optimization",
        "deveval-readtime",
        "deveval-stocktrends",
    ]
    for cid in deveval_ids:
        assert by_id[cid].role == CaseRole.CORPUS
        assert by_id[cid].visibility == CaseVisibility.PUBLIC

    assert by_id["add-login-greenfield"].role == CaseRole.PROBE
    assert by_id["add-login-greenfield"].visibility == CaseVisibility.PRIVATE
    assert by_id["crew-probe"].role == CaseRole.PROBE
    assert by_id["crew-probe"].visibility == CaseVisibility.PRIVATE


def test_smoke_case_resolution_and_errors(tmp_path):
    s = smoke_case(CASES_ROOT)
    assert s.case_id == "todo-api-greenfield"

    case_yaml_template = (
        "case_id: {cid}\n"
        "idea_summary: s\n"
        "harnesses: [opencode]\n"
        "models: [m]\n"
        "judge_model: j\n"
        "role: {role}\n"
    )

    # zero smoke cases on tmp_path corpus raises error
    (tmp_path / "case1").mkdir()
    (tmp_path / "case1" / "case.yaml").write_text(
        case_yaml_template.format(cid="case1", role="corpus"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="smoke"):
        smoke_case(tmp_path)

    # two smoke cases on tmp_path corpus raises error
    (tmp_path / "case2").mkdir()
    (tmp_path / "case2" / "case.yaml").write_text(
        case_yaml_template.format(cid="case2", role="smoke"),
        encoding="utf-8",
    )
    (tmp_path / "case1" / "case.yaml").write_text(
        case_yaml_template.format(cid="case1", role="smoke"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="smoke"):
        smoke_case(tmp_path)


def test_seven_corpus_cases_have_two_arms_and_matching_base_cells():
    specs = load_corpus(CASES_ROOT)
    by_id = {s.case_id: s for s in specs}

    for cid, base_cell_id in CORPUS_BASE_CELL_IDS.items():
        spec = by_id[cid]
        assert spec.strong_arm == "zai-coding-plan-glm-5.2"
        assert spec.weak_arm == "zai-coding-plan-glm-5.3-flash"

        arm_map = {a.name: a for a in spec.arms}
        assert set(arm_map.keys()) == {
            "zai-coding-plan-glm-5.2",
            "zai-coding-plan-glm-5.3-flash",
        }
        for arm in spec.arms:
            assert set(arm.role_models.keys()) == {"dev", "test", "devops"}

        cells = expand_matrix(spec)
        assert len(cells) == 2
        strong_cell = next(c for c in cells if c.arm_name == spec.strong_arm)
        assert strong_cell.cell_id == base_cell_id


def test_reference_isolation_fr031():
    import ast
    import inspect

    from sdlc.benchmarks.paths import cases_dir
    from sdlc.benchmarks.workflow import BenchmarkWorkflow

    root = cases_dir()
    for case_dir in root.iterdir():
        if not case_dir.is_dir():
            continue
        ref_dir = case_dir / "reference"
        if not ref_dir.is_dir():
            continue
        case_yaml_text = (case_dir / "case.yaml").read_text(encoding="utf-8")
        assert "reference/" not in case_yaml_text

        # For every file under reference/, no path under reference/ is named in case.yaml
        for p in ref_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(ref_dir).as_posix()
                assert f"reference/{rel}" not in case_yaml_text

    # The function that seeds a run (execute_pipeline_child in BenchmarkWorkflow)
    # is given no path under Cases (seeded=None).
    import textwrap

    source = inspect.getsource(BenchmarkWorkflow.run)
    tree = ast.parse(textwrap.dedent(source))
    found_call = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "execute_pipeline_child"
        ):
            found_call = True
            kw_names = {kw.arg: kw.value for kw in node.keywords}
            assert "seeded" in kw_names
            val = kw_names["seeded"]
            assert isinstance(val, ast.Constant) and val.value is None
    assert found_call


def test_corpus_status_and_render_on_tmp_path_corpus(tmp_path: Path):
    from sdlc.benchmarks.acceptance import AcceptanceRecord, Reason, Verdict, save_acceptance
    from sdlc.benchmarks.corpus import (
        CorpusRow,
        corpus_status,
        render_corpus_status,
    )

    cases_root = tmp_path / "cases"
    cases_root.mkdir()

    def make_case(cid: str, role: str, visibility: str | None = None, with_oracle: bool = True):
        cdir = cases_root / cid
        cdir.mkdir()
        vis_line = f"visibility: {visibility}\n" if visibility else ""
        (cdir / "case.yaml").write_text(
            f"case_id: {cid}\n"
            f"idea_summary: summary of {cid}\n"
            f"role: {role}\n"
            f"{vis_line}"
            f"harnesses: [opencode]\n"
            f"models: [m]\n"
            f"judge_model: j\n",
            encoding="utf-8",
        )
        if with_oracle:
            odir = cdir / "oracle"
            odir.mkdir()
            (odir / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
        return cdir

    # 1. smoke case with no acceptance record
    make_case("c-smoke", "smoke")

    # 2. probe case with no acceptance record
    make_case("c-probe", "probe", "private", with_oracle=False)

    # 3. parked case with acceptance record (reason: saturated)
    c_parked = make_case("c-parked", "parked", "public")
    from sdlc.benchmarks.oracle_id import oracle_identity

    oid_parked = oracle_identity(c_parked / "oracle")
    save_acceptance(
        AcceptanceRecord(
            case_id="c-parked",
            verdict=Verdict.REJECTED,
            reason=Reason.SATURATED,
            oracle_id=oid_parked,
            role=CaseRole.PARKED,
            exposure="repo_public",
            kroker_commit="abc",
            updated="2026-10-11",
        ),
        c_parked,
    )

    # 4. corpus case accepted, private, up-to-date (not stale)
    c_corp1 = make_case("c-corp1", "corpus", "private")
    oid_corp1 = oracle_identity(c_corp1 / "oracle")
    save_acceptance(
        AcceptanceRecord(
            case_id="c-corp1",
            verdict=Verdict.ACCEPTED,
            oracle_id=oid_corp1,
            role=CaseRole.CORPUS,
            exposure="repo_public",
            kroker_commit="abc",
            updated="2026-10-11",
        ),
        c_corp1,
    )

    # 5. corpus case provisional, public, up-to-date (not stale)
    c_corp2 = make_case("c-corp2", "corpus", "public")
    oid_corp2 = oracle_identity(c_corp2 / "oracle")
    save_acceptance(
        AcceptanceRecord(
            case_id="c-corp2",
            verdict=Verdict.PROVISIONAL,
            oracle_id=oid_corp2,
            role=CaseRole.CORPUS,
            exposure="repo_public",
            kroker_commit="abc",
            updated="2026-10-11",
        ),
        c_corp2,
    )

    # 6. corpus case accepted, but stale (oracle changed on disk)
    c_corp3 = make_case("c-corp3", "corpus", "private")
    save_acceptance(
        AcceptanceRecord(
            case_id="c-corp3",
            verdict=Verdict.ACCEPTED,
            oracle_id="sha256:different_hash",
            role=CaseRole.CORPUS,
            exposure="repo_public",
            kroker_commit="abc",
            updated="2026-10-11",
        ),
        c_corp3,
    )

    # 7. corpus case without acceptance record -> stale is "not assessed"
    make_case("c-corp4", "corpus", "public")

    rows = corpus_status(cases_root)
    assert len(rows) == 7
    assert all(isinstance(r, CorpusRow) for r in rows)
    row_map = {r.case_id: r for r in rows}

    assert row_map["c-smoke"].role == CaseRole.SMOKE
    assert row_map["c-smoke"].stale == "not assessed"
    assert row_map["c-smoke"].verdict is None

    assert row_map["c-probe"].role == CaseRole.PROBE
    assert row_map["c-probe"].stale == "not assessed"

    assert row_map["c-parked"].role == CaseRole.PARKED
    assert row_map["c-parked"].verdict == Verdict.REJECTED
    assert row_map["c-parked"].reason == Reason.SATURATED
    assert row_map["c-parked"].stale is False

    assert row_map["c-corp1"].verdict == Verdict.ACCEPTED
    assert row_map["c-corp1"].stale is False

    assert row_map["c-corp2"].verdict == Verdict.PROVISIONAL
    assert row_map["c-corp2"].stale is False

    assert row_map["c-corp3"].verdict == Verdict.ACCEPTED
    assert row_map["c-corp3"].stale is True

    assert row_map["c-corp4"].stale == "not assessed"

    rendered = render_corpus_status(rows)
    # The rendered text must be ASCII
    rendered.encode("ascii")

    # Parked case listed with its reason
    assert "c-parked" in rendered
    assert "saturated" in rendered

    # Tally counts only non-stale accepted/provisional corpus cases:
    # c-corp1 (accepted, private, fresh) and c-corp2 (provisional, public, fresh).
    # c-corp3 is stale, so not counted. c-parked is parked, so not counted.
    # Total accepted or provisional non-stale = 2.
    # Private accepted or provisional non-stale = 1 (c-corp1).
    assert "2 of 8 accepted or provisional, 1 of 2 private" in rendered
