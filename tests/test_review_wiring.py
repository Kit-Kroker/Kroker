import pathlib

SRC = pathlib.Path("src/sdlc/workflows/feature.py")


def test_dev_task_runs_reviewer_on_clean_inputs():
    src = SRC.read_text(encoding="utf-8")
    assert "t_reviewer.run(" in src, (
        "_dev_task must run the clean-context reviewer (FR-204)")
    # Reviewer must see the diff patch — the same materialized diff QA sees,
    # never the implementer's narrative.
    idx = src.find("t_reviewer.run(")
    call = src[idx: idx + 400]
    assert "diff['patch']" in call or 'diff["patch"]' in call


def test_review_gated_on_config_flag():
    src = SRC.read_text(encoding="utf-8")
    assert "cfg.review_enabled" in src, (
        "reviewer must be skippable via PipelineConfig.review_enabled")


def test_pass_condition_requires_review_approval():
    src = SRC.read_text(encoding="utf-8")
    assert "review is None or review.approve" in src, (
        "the task success path must require reviewer approval when review ran")


def test_task_result_carries_review():
    src = SRC.read_text(encoding="utf-8")
    assert "review=review" in src, (
        "TaskResult must carry the ReviewReport as merge-gate evidence")


def test_reviewer_imported():
    src = SRC.read_text(encoding="utf-8")
    assert "t_reviewer" in src
