from sdlc.models import (
    MemoryConfig, MemoryKind, PipelineConfig, RecallSnapshot, RetainItem,
)


def test_recall_snapshot_defaults_not_degraded():
    snap = RecallSnapshot(query_hash="abc", bank="project:x", watermark="3")
    assert snap.items == []
    assert snap.degraded is False


def test_retain_item_requires_kind_bank_text():
    item = RetainItem(kind=MemoryKind.GOTCHA, bank="org", text="did a thing",
                      metadata={"run_id": "r1"})
    assert item.kind is MemoryKind.GOTCHA
    assert item.metadata["run_id"] == "r1"


def test_pipeline_config_has_disabled_memory_by_default(monkeypatch):
    # MemoryConfig reads SDLC_MEMORY_* from os.environ at construction time;
    # .env leaks into the environment when other tests import load_dotenv, so
    # strip the vars this test asserts defaults for.
    for var in ("SDLC_MEMORY_ENABLED", "SDLC_MEMORY_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    cfg = PipelineConfig()
    assert cfg.memory.enabled is False
    assert cfg.memory.backend == "fake"
    assert cfg.memoization_enabled is False


def test_memory_config_project_bank_default_matches_org_default_shape():
    cfg = MemoryConfig()
    assert cfg.org_bank == "org"
    assert cfg.project_bank.startswith("project:")
