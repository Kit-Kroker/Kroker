import os
from pathlib import Path

import pytest
import yaml

from sdlc.benchmarks.corpus import load_corpus, smoke_case
from sdlc.benchmarks.matrix import expand_matrix
from sdlc.benchmarks.models import CaseRole, CaseVisibility

CASES_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "cases"

# 016 D-12: the machine's real store binding, captured at import BEFORE the
# autouse fixture clears the variable; the two iterate-all tests re-apply it.
REAL_PRIVATE_ROOT = os.environ.get("SDLC_PRIVATE_CASES_ROOT")

CORPUS_WEAK_CELL_IDS = {
    "cat-cafe-monitoring": "cat-cafe-monitoring#opencode#zai-coding-plan-glm-5.3-flash",
    "deveval-geotext": "deveval-geotext#opencode#zai-coding-plan-glm-5.3-flash",
    "deveval-hone": "deveval-hone#opencode#zai-coding-plan-glm-5.3-flash",
    "deveval-lice": "deveval-lice#opencode#zai-coding-plan-glm-5.3-flash",
    "deveval-particle-swarm-optimization": (
        "deveval-particle-swarm-optimization#opencode#zai-coding-plan-glm-5.3-flash"
    ),
    "deveval-readtime": "deveval-readtime#opencode#zai-coding-plan-glm-5.3-flash",
    "deveval-stocktrends": "deveval-stocktrends#opencode#zai-coding-plan-glm-5.3-flash",
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
        assert by_id[cid].visibility == CaseVisibility.PUBLIC

    # T020 role moves: hone / stocktrends parked (saturated / degenerate)
    # and pso parked (lost ×2 at plan-validation) by the R1 screen.
    for cid in deveval_ids:
        if cid in ("deveval-hone", "deveval-stocktrends", "deveval-particle-swarm-optimization"):
            assert by_id[cid].role == CaseRole.PARKED
        else:
            assert by_id[cid].role == CaseRole.CORPUS

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

    for cid, weak_cell_id in CORPUS_WEAK_CELL_IDS.items():
        spec = by_id[cid]
        # R019 (2026-10-27): arms re-paired - glm-5.3 strong, glm-5.3-flash
        # weak (glm-5.2 retired, catalog-deprecated). Cell ids come from arm
        # names (matrix.py:136), not from models:.
        assert spec.strong_arm == "zai-coding-plan-glm-5.3"
        assert spec.weak_arm == "zai-coding-plan-glm-5.3-flash"

        arm_map = {a.name: a for a in spec.arms}
        assert set(arm_map.keys()) == {
            "zai-coding-plan-glm-5.3",
            "zai-coding-plan-glm-5.3-flash",
        }
        for arm in spec.arms:
            assert set(arm.role_models.keys()) == {"dev", "test", "devops"}

        cells = expand_matrix(spec)
        assert len(cells) == 2
        strong_cell = next(c for c in cells if c.arm_name == spec.strong_arm)
        weak_cell = next(c for c in cells if c.arm_name == spec.weak_arm)
        assert weak_cell.cell_id == weak_cell_id
        assert strong_cell.cell_id.endswith("#zai-coding-plan-glm-5.3")


def test_reference_isolation_fr031(monkeypatch):
    import ast
    import inspect

    from sdlc.benchmarks.paths import iter_case_dirs
    from sdlc.benchmarks.workflow import BenchmarkWorkflow

    # 016 T003 (sanctioned conversion): iterate BOTH roots under the real
    # env (D-12) -- the store carries the same isolation duty.
    if REAL_PRIVATE_ROOT:
        monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", REAL_PRIVATE_ROOT)
    for _root, case_dir in iter_case_dirs():
        ref_dir = case_dir / "reference"
        if not ref_dir.is_dir():
            continue
        case_yaml_text = (case_dir / "case.yaml").read_text(encoding="utf-8")
        assert "reference/" not in case_yaml_text
        # 016 T003: verification/ and review/ are held out the same way.
        assert "verification/" not in case_yaml_text
        assert "review/" not in case_yaml_text

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


def test_committed_records_match_their_cases(monkeypatch):
    """SC-007: Every corpus case has an acceptance.yaml whose oracle_id
    equals oracle_identity of its oracle/. 016 T003 (sanctioned
    conversion): iterates BOTH roots under the real env (D-12)."""
    from sdlc.benchmarks.acceptance import load_acceptance
    from sdlc.benchmarks.models import CaseRole
    from sdlc.benchmarks.oracle_id import oracle_identity
    from sdlc.benchmarks.paths import iter_case_dirs

    if REAL_PRIVATE_ROOT:
        monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", REAL_PRIVATE_ROOT)
    for _root, case_dir in iter_case_dirs():
        if not (case_dir / "case.yaml").exists():
            continue
        spec_text = (case_dir / "case.yaml").read_text(encoding="utf-8")
        raw = yaml.safe_load(spec_text)
        if raw.get("role") != CaseRole.CORPUS.value:
            continue

        rec = load_acceptance(case_dir)
        assert rec is not None, f"missing acceptance.yaml in corpus case {case_dir.name}"

        oracle_dir = case_dir / "oracle"
        assert oracle_dir.is_dir(), f"missing oracle/ in corpus case {case_dir.name}"
        expected_oid = oracle_identity(oracle_dir)
        assert rec.oracle_id == expected_oid, (
            f"mismatched oracle_id in {case_dir.name}: {rec.oracle_id} != {expected_oid}"
        )


# --- 016 T003 (RED): the private store beside the primary root ----------------


def _make_spec_case(cdir: Path, cid: str, *, role: str, visibility: str | None) -> Path:
    """Minimal corpus-status case, the same shape make_case builds above."""
    cdir.mkdir(parents=True)
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
    odir = cdir / "oracle"
    odir.mkdir()
    (odir / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    return cdir


def _two_root_corpus(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A tmp primary root and a tmp private root, each holding one fresh
    (non-stale) accepted corpus case: 'pub-corp' (public, primary root)
    and 'priv-corp' (private, store root). Returns (primary, private)."""
    from sdlc.benchmarks.acceptance import AcceptanceRecord, Verdict, save_acceptance
    from sdlc.benchmarks.oracle_id import oracle_identity

    primary = tmp_path / "primary-cases"
    private = tmp_path / "store" / "cases"
    pub = _make_spec_case(primary / "pub-corp", "pub-corp", role="corpus", visibility="public")
    priv = _make_spec_case(private / "priv-corp", "priv-corp", role="corpus", visibility="private")
    for cid, cdir, exposure in (
        ("pub-corp", pub, "repo_public"),
        ("priv-corp", priv, "isolated"),
    ):
        save_acceptance(
            AcceptanceRecord(
                case_id=cid,
                verdict=Verdict.ACCEPTED,
                oracle_id=oracle_identity(cdir / "oracle"),
                role=CaseRole.CORPUS,
                exposure=exposure,
                kroker_commit="abc",
                updated="2026-10-17",
            ),
            cdir,
        )
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))
    return primary, private


def test_corpus_status_without_argument_walks_both_roots(tmp_path, monkeypatch):
    """Names: corpus_status(cases_root=None) walks iter_case_dirs(), so a
    case that exists only in the private store is listed beside the
    primary-root cases, and its row's exposure comes from its root (D-4):
    'isolated' under the store, 'repo_public' under the primary root."""
    from sdlc.benchmarks.corpus import corpus_status

    _two_root_corpus(tmp_path, monkeypatch)
    rows = corpus_status()
    by_id = {r.case_id: r for r in rows}
    assert set(by_id) == {"pub-corp", "priv-corp"}
    assert by_id["priv-corp"].exposure == "isolated"
    assert by_id["pub-corp"].exposure == "repo_public"
    assert by_id["priv-corp"].stale is False
    assert by_id["pub-corp"].stale is False


def test_corpus_status_tally_counts_the_store_case_in_both_numbers(tmp_path, monkeypatch):
    """D-4: the tally keeps counting by visibility, so a fresh accepted
    private store case counts in BOTH numbers of the line."""
    from sdlc.benchmarks.corpus import corpus_status, render_corpus_status

    _two_root_corpus(tmp_path, monkeypatch)
    rendered = render_corpus_status(corpus_status())
    assert "priv-corp" in rendered
    assert "2 of 8 accepted or provisional, 1 of 2 private" in rendered


def test_render_corpus_status_without_store_note_prints_no_note(tmp_path, monkeypatch):
    """Names: with store_note=None the render stays byte-identical to
    today's output -- no note line at all (the existing render test pins
    the rest of the format)."""
    from sdlc.benchmarks.corpus import corpus_status, render_corpus_status

    _two_root_corpus(tmp_path, monkeypatch)
    rendered = render_corpus_status(corpus_status())
    assert "private store" not in rendered


@pytest.mark.parametrize(
    "note",
    [
        "private store: not configured",
        "private store: absent at /srv/private-cases",
        "private store: 2 case(s) at /srv/private-cases",
    ],
    ids=["not-configured", "absent", "cases"],
)
def test_render_corpus_status_prints_each_store_note(note):
    """Names: render_corpus_status takes store_note and prints it; the
    three shapes are exactly the ones dispatch_corpus may pass."""
    from sdlc.benchmarks.corpus import CorpusRow, render_corpus_status

    row = CorpusRow(
        case_id="c1",
        role=CaseRole.CORPUS,
        visibility=CaseVisibility.PUBLIC,
        exposure="repo_public",
        verdict=None,
        reason=None,
        stale="not assessed",
    )
    rendered = render_corpus_status([row], store_note=note)
    assert note in rendered


# --- R019 T007 (RED): arm-drift staleness (FR-009) ---


def _arm_case(
    cases_root,
    cid,
    role,
    strong,
    weak,
    rec_strong,
    rec_weak,
    separation=True,
    verdict="provisional",
):
    """A corpus-status case whose case.yaml carries explicit arms and whose
    acceptance record names the arms the oracle actually ran (FR-009)."""
    from sdlc.benchmarks.acceptance import (
        AcceptanceRecord,
        ArmEvidence,
        SeparationCheck,
        Verdict,
        save_acceptance,
    )
    from sdlc.benchmarks.models import CaseRole
    from sdlc.benchmarks.oracle_id import oracle_identity

    cdir = Path(cases_root) / cid
    cdir.mkdir(parents=True)
    arms = [strong] + ([weak] if weak is not None else [])
    arm_blocks = "".join(
        f"  - name: {arm}\n    role_models:\n      dev: m\n      test: m\n      devops: m\n"
        for arm in arms
    )
    weak_line = f"weak_arm: {weak}\n" if weak is not None else ""
    (cdir / "case.yaml").write_text(
        f"case_id: {cid}\n"
        f"idea_summary: summary of {cid}\n"
        f"role: {role}\n"
        f"harnesses: [opencode]\n"
        f"judge_model: j\n"
        f"models: [m]\n"
        f"strong_arm: {strong}\n"
        f"{weak_line}"
        f"arms:\n"
        f"{arm_blocks}",
        encoding="utf-8",
    )
    odir = cdir / "oracle"
    odir.mkdir()
    (odir / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    if separation:
        sep = SeparationCheck(
            strong=ArmEvidence(arm=rec_strong) if rec_strong else None,
            weak=ArmEvidence(arm=rec_weak) if rec_weak else None,
        )
    else:
        sep = None
    save_acceptance(
        AcceptanceRecord(
            case_id=cid,
            verdict=Verdict(verdict),
            oracle_id=oracle_identity(cdir / "oracle"),
            role=CaseRole(role),
            exposure="repo_public",
            kroker_commit="abc",
            updated="2026-10-27",
            separation=sep,
        ),
        cdir,
    )
    return cdir


def test_arm_drift_t1_strong_changed(tmp_path):
    """T1 (contract §1): the record's separation ran strong 'A' / weak 'B',
    but the case now declares strong_arm 'C' -- arm drift must mark the row
    stale and drop it from the tally, even though the oracle is unchanged."""
    from sdlc.benchmarks.corpus import corpus_status, render_corpus_status

    cases_root = tmp_path / "cases"
    _arm_case(cases_root, "drift-t1", "corpus", "C", "B", "A", "B")

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t1"].stale is True

    # Not counted: alone and provisional, a fresh case would read 1 of 8;
    # a drifted one must not.
    rendered = render_corpus_status(rows)
    assert "1 of 8 accepted or provisional" not in rendered


def test_arm_drift_t7_unchanged_is_fresh_and_counted(tmp_path):
    """T7 (contract §1): record separation (A, B) against case (A, B) --
    unchanged arms stay fresh AND the tally counts the provisional row.
    Built alone (orchestrator ruling on the R019 T007 stop-and-report):
    with T1 beside it the pre-fix tally would read 2 of 8 and the test
    could not pin unchanged behaviour at RED. The "not T1's row" negative
    is pinned by test_arm_drift_t1_strong_changed."""
    from sdlc.benchmarks.corpus import corpus_status, render_corpus_status

    cases_root = tmp_path / "cases"
    _arm_case(cases_root, "drift-t7", "corpus", "A", "B", "A", "B")

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t7"].stale is False

    # T7's provisional row is counted: the tally reads one of eight.
    rendered = render_corpus_status(rows)
    assert "1 of 8 accepted or provisional" in rendered


def test_arm_drift_t2_weak_changed(tmp_path):
    """T2 (contract §1): record separation ran weak 'B', but the case now
    declares weak_arm 'C' -- the weak arm alone drifting must mark it stale."""
    from sdlc.benchmarks.corpus import corpus_status

    cases_root = tmp_path / "cases"
    _arm_case(cases_root, "drift-t2", "corpus", "A", "C", "A", "B")

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t2"].stale is True


def test_arm_drift_t3_weak_newly_declared(tmp_path):
    """T3 (contract §1): record separation ran strong 'A' with no weak arm,
    but the case now declares weak_arm 'B' -- a newly declared weak arm is
    arm drift and must mark the row stale."""
    from sdlc.benchmarks.corpus import corpus_status

    cases_root = tmp_path / "cases"
    _arm_case(cases_root, "drift-t3", "corpus", "A", "B", "A", None)

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t3"].stale is True


def test_arm_drift_t4_no_strong_record_now_declared(tmp_path):
    """T4 (contract §1): record separation carries no strong or weak evidence
    (the record was written before any strong_arm was configured), but the
    case now declares (A, B) -- arm drift must mark the row stale."""
    from sdlc.benchmarks.corpus import corpus_status

    cases_root = tmp_path / "cases"
    _arm_case(cases_root, "drift-t4", "corpus", "A", "B", None, None)

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t4"].stale is True


def test_arm_drift_t5_null_separation_never_arm_stale(tmp_path):
    """T5 (contract §1): a record with separation null has no arm evidence to
    drift from, so totally different arms (C, D) must not mark it stale --
    the oracle id still matches, so no other staleness cause fires."""
    from sdlc.benchmarks.corpus import corpus_status

    cases_root = tmp_path / "cases"
    _arm_case(cases_root, "drift-t5", "corpus", "C", "D", "A", "B", separation=False)

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t5"].stale is False


def test_arm_drift_t6_parked_not_arm_stale(tmp_path):
    """T6 (contract §1): a parked case whose record carries the sentinel
    separation (not assessed for parked) has no arm evidence to drift from,
    so declared arms (A, B) must not mark it stale. Written inline because
    _arm_case cannot express the sentinel's passed and detail fields."""
    from sdlc.benchmarks.acceptance import (
        AcceptanceRecord,
        SeparationCheck,
        Verdict,
        save_acceptance,
    )
    from sdlc.benchmarks.corpus import corpus_status
    from sdlc.benchmarks.models import CaseRole
    from sdlc.benchmarks.oracle_id import oracle_identity

    cases_root = tmp_path / "cases"
    cdir = cases_root / "drift-t6"
    cdir.mkdir(parents=True)
    (cdir / "case.yaml").write_text(
        "case_id: drift-t6\n"
        "idea_summary: summary of drift-t6\n"
        "role: parked\n"
        "harnesses: [opencode]\n"
        "judge_model: j\n"
        "models: [m]\n"
        "strong_arm: A\n"
        "weak_arm: B\n"
        "arms:\n"
        "  - name: A\n"
        "    role_models:\n"
        "      dev: m\n"
        "      test: m\n"
        "      devops: m\n"
        "  - name: B\n"
        "    role_models:\n"
        "      dev: m\n"
        "      test: m\n"
        "      devops: m\n",
        encoding="utf-8",
    )
    odir = cdir / "oracle"
    odir.mkdir()
    (odir / "test_sample.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    save_acceptance(
        AcceptanceRecord(
            case_id="drift-t6",
            verdict=Verdict.NOT_ASSESSED,
            oracle_id=oracle_identity(odir),
            role=CaseRole.PARKED,
            exposure="repo_public",
            kroker_commit="abc",
            updated="2026-10-27",
            separation=SeparationCheck(
                passed=None,
                detail="separation not assessed for parked case",
            ),
        ),
        cdir,
    )

    rows = corpus_status(cases_root)
    by_id = {r.case_id: r for r in rows}
    assert by_id["drift-t6"].stale is False
