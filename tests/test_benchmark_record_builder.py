"""012 T007 (RED): the record builder carries provenance (FR-014..FR-018).

stage_record is the one code path every stage and task-attempt record
goes through. Contract §2.1–2.5: a benchmark config carrying provenance
has it copied onto the record; a missing commit becomes the explicit
`unknown`; outside a benchmark run the four provenance fields stay None
while prompt_sha is still derived (the in-memory record of an ordinary
run is never persisted — contract §2.8).
"""

from datetime import UTC, datetime, timedelta

from sdlc.benchmarks.models import BenchmarkOutcome
from sdlc.benchmarks.provenance import UNKNOWN_COMMIT, prompt_sha_for
from sdlc.benchmarks.record_builder import stage_record
from sdlc.core.models import BenchmarkConfig, PipelineConfig

_ARCHITECT_MODEL = "anthropic:claude-sonnet-4-6"


def _cfg(**bench_kw) -> PipelineConfig:
    return PipelineConfig(benchmark=BenchmarkConfig(**bench_kw))


def _record(cfg: PipelineConfig, *, role="architect", model=_ARCHITECT_MODEL, **kw):
    t0 = datetime(2026, 7, 23, tzinfo=UTC)
    base = dict(
        stage="architecture",
        role=role,
        started=t0,
        ended=t0 + timedelta(seconds=5),
        quality_score=0.8,
        judge="contract",
        outcome=BenchmarkOutcome.PASS,
        model=model,
    )
    base.update(kw)
    return stage_record(cfg, **base)


# --- contract §2.1–2.4: provenance copied, prompt hashed ---------------------


def test_stage_record_copies_provenance_and_hashes_the_prompt():
    cfg = _cfg(
        case_id="add-login",
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=False,
        arm="a1",
        cell_id="add-login#opencode#a1",
    )
    r = _record(cfg)
    assert r.kroker_commit == "abc"
    assert r.tree_dirty is False
    assert r.arm == "a1"
    assert r.cell_id == "add-login#opencode#a1"
    # prompted proposer role: the real registry-instruction hash
    assert r.prompt_sha == prompt_sha_for("architect", _ARCHITECT_MODEL)
    # contract §2.4: model stays exactly what did the work
    assert r.model == _ARCHITECT_MODEL


def test_stage_record_prompt_sha_sentinels():
    cfg = _cfg(
        case_id="add-login",
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=None,
        arm="a1",
        cell_id="add-login#opencode#a1",
    )
    det = _record(cfg, role="architect", model="deterministic")
    assert det.prompt_sha == "none:deterministic"
    assert det.model == "deterministic"
    dev = _record(cfg, role="dev", model="openai/gpt-5.2")
    assert dev.prompt_sha == "none:no-registry-prompt"
    assert dev.model == "openai/gpt-5.2"


# --- contract §2.1: a missing commit is explicitly unknown -------------------


def test_stage_record_unknown_commit_when_config_commit_missing():
    cfg = _cfg(case_id="add-login", bench_run_id="b1")
    r = _record(cfg)
    assert r.kroker_commit == UNKNOWN_COMMIT
    assert r.kroker_commit == "unknown"
    assert r.kroker_commit  # never None, never ""
    # an empty string in the config maps to unknown too
    blank = _cfg(case_id="add-login", bench_run_id="b1", kroker_commit="")
    assert _record(blank).kroker_commit == "unknown"


# --- contract §2.8: an ordinary run records no provenance ---------------------


def test_stage_record_outside_benchmark_run_has_no_provenance():
    r = _record(PipelineConfig())  # benchmark.case_id is None
    assert r.kroker_commit is None
    assert r.tree_dirty is None
    assert r.arm is None
    assert r.cell_id is None
    # ... apart from prompt_sha, which is derived on every in-memory record
    assert r.prompt_sha == prompt_sha_for("architect", _ARCHITECT_MODEL)


# --- chaos seat: adversarial edges (012 T007) ---------------------------------


def test_stage_record_ignores_stray_provenance_on_a_non_benchmark_config():
    """Contract §2.8, adversarial shape: outside a benchmark run nothing of
    section 2 is written WHATEVER the config carries -- case_id None but
    arm/cell_id/kroker_commit/tree_dirty all set must still leave all four
    record fields None. Benchmarking keys on case_id alone."""
    cfg = _cfg(
        case_id=None,
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=True,
        arm="a1",
        cell_id="add-login#opencode#a1",
    )
    r = _record(cfg)
    assert r.kroker_commit is None
    assert r.tree_dirty is None
    assert r.arm is None
    assert r.cell_id is None


def test_stage_record_passes_tree_dirty_true_and_none_through():
    """Contract §2.2: tree_dirty is copied verbatim when benchmarking --
    including the True and None values the happy-path test (False) skipped."""
    on = _cfg(
        case_id="add-login",
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=True,
        arm="a1",
        cell_id="c1",
    )
    assert _record(on).tree_dirty is True
    undetermined = _cfg(
        case_id="add-login",
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=None,
        arm="a1",
        cell_id="c1",
    )
    assert _record(undetermined).tree_dirty is None


def test_stage_record_task_attempt_scope_still_gets_prompt_sha():
    """Contract §2.5 applies to every record a benchmark run writes, the
    task-attempt scope included: a record built with task_id (scope
    TASK_ATTEMPT) carries the same role+model hash as a stage record."""
    cfg = _cfg(
        case_id="add-login",
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=False,
        arm="a1",
        cell_id="add-login#opencode#a1",
    )
    r = _record(cfg, role="planner", task_id="t01", attempt=1)
    from sdlc.benchmarks.models import BenchmarkScope

    assert r.scope is BenchmarkScope.TASK_ATTEMPT
    assert r.task_id == "t01"
    assert r.attempt == 1
    assert r.prompt_sha == prompt_sha_for("planner", _ARCHITECT_MODEL)


def test_stage_record_prompt_sha_matches_instructions_file_on_disk():
    """Angle independent of the module under test: the hash equals sha256
    of agents/architect/instructions.md's TEXT, read straight from the
    checkout. Newlines are normalized CRLF->LF the way universal newlines
    does (loader.py reads the file with read_text for exactly this: a CRLF
    checkout must hash as LF -- tests/test_prompt_migration.py pins it), so
    the pin holds on a Windows or Linux checkout alike."""
    import hashlib
    from pathlib import Path

    cfg = _cfg(
        case_id="add-login",
        bench_run_id="b1",
        kroker_commit="abc",
        tree_dirty=False,
        arm="a1",
        cell_id="c1",
    )
    r = _record(cfg)
    instructions = Path(__file__).resolve().parents[1] / "agents" / "architect" / "instructions.md"
    text = instructions.read_bytes().decode("utf-8")
    expected = hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode()).hexdigest()
    assert r.prompt_sha == expected
