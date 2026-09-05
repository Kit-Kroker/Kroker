import pathlib

FEATURE_SRC = pathlib.Path("src/sdlc/workflows/feature.py")
TASK_HOST_SRC = pathlib.Path("src/sdlc/workflows/task_host.py")
REVIEW_SRC = pathlib.Path("src/sdlc/stages/review/step.py")
CODE_SRC = pathlib.Path("src/sdlc/stages/code/step.py")


def _src() -> str:
    return (
        FEATURE_SRC.read_text(encoding="utf-8")
        + "\n"
        + TASK_HOST_SRC.read_text(encoding="utf-8")
        + "\n"
        + REVIEW_SRC.read_text(encoding="utf-8")
        + "\n"
        + CODE_SRC.read_text(encoding="utf-8")
    )


def test_deep_review_helper_exists():
    assert "async def _run_deep_review" in _src()


def test_deep_review_gated_on_config_flag():
    src = _src()
    assert "cfg.deep_review_enabled" in src
    assert "t_deep_review is not None" in src


def test_deep_review_reads_via_load_session_only():
    src = _src()
    assert "load_session" in src
    assert "run.session_ref" in src


def test_deep_review_is_advisory_not_in_success_condition():
    # The success PREDICATE must stay exactly the review-only predicate;
    # deep_review must never appear in the gate predicate itself. (The
    # _run_deep_review CALL lives inside the block bodies by design -- that
    # is advisory recording, not gating.)
    src = _src()
    pred = "if task_passed and review_ok:"
    assert pred in src
    idx = src.find(pred)
    line = src[idx : src.find("\n", idx)]
    assert "deep_review" not in line, "deep_review must never gate the task success path"


def test_both_returns_carry_deep_review():
    # _run_deep_review is invoked and its result attached at each exit.
    assert _src().count("deep_review=") >= 2


def test_deep_review_records_its_own_stage():
    src = _src()
    assert 'stage="deep_review"' in src


def test_deep_review_never_resumes_a_session():
    # deep_review is a proposer: it must not pass a session_id to any harness.
    src = _src()
    idx = src.find("async def _run_deep_review")
    body = src[idx : idx + 1600]
    assert "run_coding_task" not in body
    assert "session_id" not in body
