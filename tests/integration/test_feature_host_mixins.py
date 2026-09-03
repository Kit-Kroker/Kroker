from sdlc.workflows.benchmark_host import BenchmarkHost
from sdlc.workflows.board_host import BoardHost
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.memory_host import MemoryHost
from sdlc.workflows.report_host import ReportHost
from sdlc.workflows.role_host import RoleHost


def test_feature_workflow_inherits_the_hosts():
    assert issubclass(FeatureWorkflow, ReportHost)
    assert issubclass(FeatureWorkflow, BoardHost)


def test_methods_resolve_through_the_mro():
    for name in ("_emit", "_stage", "_track_usage", "_board_publish", "_board_evidence"):
        assert hasattr(FeatureWorkflow, name), name


def test_hosts_define_no_handlers():
    # Rule 1: handlers stay where they already are. A host that grows one
    # silently changes the workflow's wire contract.
    for host in (ReportHost, BoardHost, BenchmarkHost, MemoryHost, RoleHost):
        for attr in vars(host).values():
            assert not hasattr(attr, "__temporal_signal_definition"), host
            assert not hasattr(attr, "__temporal_query_definition"), host


def test_cooperative_init_initializes_all_owned_attributes():
    w = FeatureWorkflow()
    expected_attributes = (
        # GateHost
        "_gate_decisions",
        "_pending",
        "_parent_run_id",
        # ReportHost
        "_trace",
        "_seq",
        "_status",
        "_role_usage",
        # BoardHost
        "_plan_version",
        # QuestionHost
        "_question_answers",
        "_pending_questions",
        "_memory_watermark",
        "_cfg",
        "_idea",
        "_started_at",
        "_run_id",
        "_integration_head",
        "_integration_wt",
        "_run_summary",
        "_session_refs",
        "_budget_threshold",
        "_budget_crossings",
        "_escalation_round",
        "_codebase_map",
    )
    for attr in expected_attributes:
        assert hasattr(w, attr), f"Missing instance attribute: {attr}"


def test_benchmark_and_memory_hosts_are_on_the_mro():
    from sdlc.workflows.benchmark_host import BenchmarkHost
    from sdlc.workflows.memory_host import MemoryHost

    assert issubclass(FeatureWorkflow, BenchmarkHost)
    assert issubclass(FeatureWorkflow, MemoryHost)
    for name in ("_benchmarking", "_stage_record", "_record", "_judge", "_recall", "_retain"):
        assert hasattr(FeatureWorkflow, name), name


def test_record_assembles_the_benchmark_record_for_the_stage():
    # ctx.record must accept stage metrics, never a pre-built BenchmarkRecord:
    # a step must not know how one is assembled (_stage_record is 47 lines).
    import inspect

    assert "record" in inspect.signature(BenchmarkHost._record).parameters


def test_role_host_is_on_the_mro():
    from sdlc.workflows.role_host import RoleHost

    assert issubclass(FeatureWorkflow, RoleHost)
    for name in ("_run_role", "_cached_stage", "_revisable_stage", "_check_budget"):
        assert hasattr(FeatureWorkflow, name), name
