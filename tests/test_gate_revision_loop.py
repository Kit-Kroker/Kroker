import pathlib

from sdlc.models import PipelineConfig, gate_key

SRC = pathlib.Path("src/sdlc/workflows/gates.py")


def test_gate_decisions_keyed_by_round():
    src = SRC.read_text(encoding="utf-8")
    # Signal handler must use gate_key(...) when storing the decision.
    assert "gate_key(" in src, (
        "submit_gate_decision must key by gate_key(gate, round), "
        "not by bare gate name — REVISE needs round-scoped identity"
    )


def test_pipeline_config_has_max_gate_rounds():
    cfg = PipelineConfig()
    assert cfg.max_gate_rounds >= 1, "FR-301: MAX_GATE_ROUNDS default >= 1"


def test_gate_key_is_round_scoped():
    assert gate_key("architecture", 1) == "architecture#1"
    assert gate_key("architecture", 2) == "architecture#2"
