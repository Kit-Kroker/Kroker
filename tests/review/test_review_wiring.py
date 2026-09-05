import pathlib

FEATURE_SRC = pathlib.Path("src/sdlc/workflows/feature.py")
TASK_HOST_SRC = pathlib.Path("src/sdlc/workflows/task_host.py")
REVIEW_SRC = pathlib.Path("src/sdlc/stages/review/step.py")
MERGE_SRC = pathlib.Path("src/sdlc/stages/merge/step.py")


class _Source:
    def read_text(self, encoding="utf-8") -> str:
        return (
            FEATURE_SRC.read_text(encoding=encoding)
            + "\n"
            + TASK_HOST_SRC.read_text(encoding=encoding)
            + "\n"
            + REVIEW_SRC.read_text(encoding=encoding)
            + "\n"
            + MERGE_SRC.read_text(encoding=encoding)
        )


SRC = _Source()


def test_dev_task_runs_reviewer_on_clean_inputs():
    src = SRC.read_text(encoding="utf-8")
    # the reviewer call may wrap across lines; find the run_role call whose
    # arguments name the "reviewer" role
    idx = src.find("run_role(")
    while idx != -1 and '"reviewer"' not in src[idx : idx + 160]:
        idx = src.find("run_role(", idx + 1)
    assert idx != -1, "_dev_task must run the clean-context reviewer (FR-204)"
    # Reviewer must see the diff patch — the same materialized diff QA sees,
    # never the implementer's narrative.
    call = src[idx : idx + 400]
    assert "patch" in call or "diff['patch']" in call or 'diff["patch"]' in call


def test_review_gated_on_config_flag():
    src = SRC.read_text(encoding="utf-8")
    assert "cfg.review_enabled" in src, (
        "reviewer must be skippable via PipelineConfig.review_enabled"
    )


def test_pass_condition_requires_review_approval():
    src = SRC.read_text(encoding="utf-8")
    assert "review is None or review.approve" in src, (
        "the task success path must require reviewer approval when review ran"
    )


def test_task_result_carries_review():
    src = SRC.read_text(encoding="utf-8")
    assert "review=review" in src, "TaskResult must carry the ReviewReport as merge-gate evidence"


def test_reviewer_imported():
    src = SRC.read_text(encoding="utf-8")
    assert "t_reviewer" in src


def test_merge_gate_has_review_severity_check():
    src = SRC.read_text(encoding="utf-8")
    assert '"review_severity"' in src, (
        "the deterministic merge gate must consume ReviewReport evidence as "
        "an advisory check (FR-106)"
    )
    idx = src.find('"review_severity"')
    block = src[idx : idx + 220]
    assert "CheckClass.ADVISORY" in block, "review check must be advisory"
    assert "r.review is None or r.review.approve" in block, (
        "review check passes iff every task was approved or had review off"
    )
