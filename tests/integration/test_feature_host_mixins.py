# tests/integration/test_feature_host_mixins.py
from sdlc.workflows.board_host import BoardHost
from sdlc.workflows.feature import FeatureWorkflow
from sdlc.workflows.report_host import ReportHost


def test_feature_workflow_inherits_the_hosts():
    assert issubclass(FeatureWorkflow, ReportHost)
    assert issubclass(FeatureWorkflow, BoardHost)


def test_methods_resolve_through_the_mro():
    for name in ("_emit", "_stage", "_track_usage", "_board_publish", "_board_evidence"):
        assert hasattr(FeatureWorkflow, name), name


def test_hosts_define_no_handlers():
    # Rule 1: handlers stay where they already are. A host that grows one
    # silently changes the workflow's wire contract.
    for host in (ReportHost, BoardHost):
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
        # FeatureWorkflow
        "_question_answers",
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
