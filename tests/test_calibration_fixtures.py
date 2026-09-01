from sdlc.benchmarks.calibration import (
    CalibrationFixture,
    load_scored_fixtures,
    make_capture_fixture,
    rubric_sha_of,
    write_fixture,
)


def test_make_capture_fixture_pins_sha_and_nulls_score():
    fx = make_capture_fixture(
        '{"a":1}', "zai/glm-5.2", "cat-cafe/architect", "score soundness 0..1"
    )
    assert fx.human_score is None
    assert fx.rubric_sha == rubric_sha_of("score soundness 0..1")
    assert fx.author_model == "zai/glm-5.2"


def test_load_skips_unscored_and_malformed(tmp_path):
    d = tmp_path / "architect"
    scored = CalibrationFixture(
        artifact_json="{}",
        rubric_ref="c/architect",
        rubric_text="r",
        rubric_sha=rubric_sha_of("r"),
        author_model="m",
        human_score=0.8,
    )
    unscored = make_capture_fixture("{}", "m", "c/architect", "r")
    write_fixture(scored, d, "fixt-0001")
    write_fixture(unscored, d, "fixt-0002")
    (d / "fixt-0003.json").write_text("{ not json", encoding="utf-8")
    loaded = load_scored_fixtures(d)
    assert len(loaded) == 1 and loaded[0].human_score == 0.8


def test_load_missing_dir_is_empty(tmp_path):
    assert load_scored_fixtures(tmp_path / "nope") == []
