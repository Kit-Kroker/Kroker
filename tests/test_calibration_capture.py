from sdlc.benchmarks.calibration import calibration_fixtures_from_events


def test_capture_normalizer_reads_target_role_artifact():
    events = [
        {"activity": "architect_agent__model_request", "output": '{"stack": "fastapi"}'},
        {"activity": "planner_agent__model_request", "output": '{"tasks": []}'},
    ]
    role_to_agent = {"architect": "architect_agent", "planner": "planner_agent"}
    fx = calibration_fixtures_from_events(
        "run-1",
        events,
        role_to_agent,
        rubric_ref="cat-cafe/architect",
        rubric_text="score soundness 0..1",
        author_model="zai/glm-5.2",
        role="architect",
    )
    assert len(fx) == 1
    assert fx[0].artifact_json == '{"stack": "fastapi"}'
    assert fx[0].human_score is None
    assert fx[0].rubric_ref == "cat-cafe/architect"


def test_capture_normalizer_empty_when_role_absent():
    events = [{"activity": "planner_agent__model_request", "output": "{}"}]
    fx = calibration_fixtures_from_events(
        "run-1",
        events,
        {"architect": "architect_agent"},
        rubric_ref="r",
        rubric_text="r",
        author_model="m",
        role="architect",
    )
    assert fx == []
