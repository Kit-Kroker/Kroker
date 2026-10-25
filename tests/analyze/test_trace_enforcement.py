"""Tests for pure trace enforcement and analyze models (017 T006, US1, C-2)."""

from __future__ import annotations

from sdlc.stages.analyze.models import (
    AnalysisReport,
    CriterionTrace,
    Evidence,
    KeyedCriterion,
    TraceInventory,
    criterion_keys,
    enforce_traces,
)


def _inventory(**kwargs) -> TraceInventory:
    return TraceInventory(**kwargs)


def _report(*traces: CriterionTrace) -> AnalysisReport:
    return AnalysisReport(traceability=list(traces))


def _kc(key: str, task_id: str, criterion: str) -> KeyedCriterion:
    return KeyedCriterion(key=key, task_id=task_id, criterion=criterion)


def test_criterion_keys_assigns_1_based_keys_per_task():
    authoritative = [
        ("T01", "first criterion"),
        ("T01", "second criterion"),
        ("T02", "task2 only criterion"),
        ("T01", "third criterion"),
    ]
    keyed = criterion_keys(authoritative)
    assert len(keyed) == 4
    assert keyed[0] == KeyedCriterion(key="T01#1", task_id="T01", criterion="first criterion")
    assert keyed[1] == KeyedCriterion(key="T01#2", task_id="T01", criterion="second criterion")
    assert keyed[2] == KeyedCriterion(key="T02#1", task_id="T02", criterion="task2 only criterion")
    assert keyed[3] == KeyedCriterion(key="T01#3", task_id="T01", criterion="third criterion")


# --- US1 Scenario 1: Test name tracing ---
def test_scenario_1_test_tracing():
    kc = _kc("T1#1", "T1", "API returns 200")
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="API returns 200",
            tests=["tests/test_api.py::test_ok"],
        )
    )
    inv = _inventory(tests=["tests/test_api.py::test_ok"])

    res = enforce_traces([kc], report, inv)
    assert res.buckets == {"test": 1, "file": 0, "command": 0, "empty": 0}
    assert res.untraced == []
    assert len(res.criteria_trace) == 1
    assert res.criteria_trace[0].bucket == "test"
    assert res.criteria_trace[0].evidence[0].valid is True


# --- US1 Scenario 2: File present on unchanged base file ---
def test_scenario_2_file_present_unchanged_base():
    kc = _kc("T1#1", "T1", "LICENSE is MIT")
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="LICENSE is MIT",
            evidence=[Evidence(kind="file", ref="LICENSE", expect="present")],
        )
    )
    inv = _inventory(tree=["LICENSE", "src/main.py"], changed_files=["src/main.py"])

    res = enforce_traces([kc], report, inv)
    assert res.buckets["file"] == 1
    assert res.untraced == []
    assert res.criteria_trace[0].bucket == "file"
    assert res.criteria_trace[0].evidence[0].valid is True


# --- US1 Scenario 3: File absent with containment and without containment ---
def test_scenario_3_file_absent_containment():
    kc = _kc("T1#1", "T1", "no pyproject.toml is created")
    # Valid citation: pyproject.toml is in the criterion text and NOT in changed_files
    report_valid = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="no pyproject.toml is created",
            evidence=[Evidence(kind="file", ref="pyproject.toml", expect="absent")],
        )
    )
    inv = _inventory(tree=["setup.py"], changed_files=["setup.py"])
    res_valid = enforce_traces([kc], report_valid, inv)
    assert res_valid.buckets["file"] == 1
    assert res_valid.untraced == []
    assert res_valid.criteria_trace[0].evidence[0].valid is True

    # Invalid citation: foo/bar.txt is not contained in criterion text
    report_invalid = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="no pyproject.toml is created",
            evidence=[Evidence(kind="file", ref="foo/bar.txt", expect="absent")],
        )
    )
    res_invalid = enforce_traces([kc], report_invalid, inv)
    assert res_invalid.buckets["empty"] == 1
    assert res_invalid.untraced == ["T1: no pyproject.toml is created"]
    assert res_invalid.criteria_trace[0].evidence[0].valid is False


# --- US1 Scenario 4: Task unchanged ---
def test_scenario_4_task_unchanged():
    kc = _kc("T6#1", "T6", "T-06: This task adds NO files to the repo")
    report = _report(
        CriterionTrace(
            key="T6#1",
            task_id="T6",
            criterion="T-06: This task adds NO files to the repo",
            evidence=[Evidence(kind="task_unchanged")],
        )
    )
    # Valid when task_changed count is 0
    inv_zero = _inventory(task_changed={"T6": 0})
    res_zero = enforce_traces([kc], report, inv_zero)
    assert res_zero.buckets["file"] == 1
    assert res_zero.untraced == []
    assert res_zero.criteria_trace[0].evidence[0].valid is True

    # Invalid when task_changed count > 0
    inv_changed = _inventory(task_changed={"T6": 2})
    res_changed = enforce_traces([kc], report, inv_changed)
    assert res_changed.buckets["empty"] == 1
    assert res_changed.untraced == ["T6: T-06: This task adds NO files to the repo"]
    assert res_changed.criteria_trace[0].evidence[0].valid is False

    # Invalid when task_changed count is None (unknown)
    inv_unknown = _inventory(task_changed={"T6": None})
    res_unknown = enforce_traces([kc], report, inv_unknown)
    assert res_unknown.buckets["empty"] == 1
    assert res_unknown.untraced == ["T6: T-06: This task adds NO files to the repo"]


# --- US1 Scenario 5: Command-only ---
def test_scenario_5_command_only():
    kc = _kc("T1#1", "T1", "Run migrations")
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="Run migrations",
            evidence=[Evidence(kind="command", ref="alembic upgrade head")],
        )
    )
    inv = _inventory()
    res = enforce_traces([kc], report, inv)
    assert res.buckets["command"] == 1
    assert res.untraced == ["T1: Run migrations"]
    assert res.criteria_trace[0].bucket == "command"
    assert res.criteria_trace[0].evidence[0].valid is False


# --- US1 Scenario 6: Inexpressible / empty criterion ---
def test_scenario_6_inexpressible_empty():
    kc = _kc("T1#1", "T1", "no other files are created")
    # Analyst provided no trace or an empty trace
    report = _report()
    inv = _inventory()
    res = enforce_traces([kc], report, inv)
    assert res.buckets["empty"] == 1
    assert res.untraced == ["T1: no other files are created"]
    assert res.criteria_trace[0].bucket == "empty"
    assert res.criteria_trace[0].evidence == []


# --- US1 Scenario 7: Test name normalization ---
def test_scenario_7_test_name_normalization():
    inv = _inventory(tests=["tests/test_x.py::TestC::test_y"])
    kc = _kc("T1#1", "T1", "Feature Y works")

    # 1. Full node id exact
    r1 = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="Feature Y works",
            tests=["tests/test_x.py::TestC::test_y"],
        )
    )
    assert enforce_traces([kc], r1, inv).buckets["test"] == 1

    # 2. Bare name (unique)
    r2 = _report(
        CriterionTrace(key="T1#1", task_id="T1", criterion="Feature Y works", tests=["test_y"])
    )
    assert enforce_traces([kc], r2, inv).buckets["test"] == 1

    # 3. Parametrized bare name
    r3 = _report(
        CriterionTrace(
            key="T1#1", task_id="T1", criterion="Feature Y works", tests=["test_y[param]"]
        )
    )
    assert enforce_traces([kc], r3, inv).buckets["test"] == 1

    # 4. Parametrized full node id
    r4 = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="Feature Y works",
            tests=["tests/test_x.py::TestC::test_y[param-1]"],
        )
    )
    assert enforce_traces([kc], r4, inv).buckets["test"] == 1

    # 5. Ambiguous bare name when multiple tests end with ::test_y
    inv_ambiguous = _inventory(
        tests=["tests/test_x.py::TestC::test_y", "tests/test_z.py::TestD::test_y"]
    )
    assert enforce_traces([kc], r2, inv_ambiguous).buckets["empty"] == 1


# --- Additional required cases: mixed evidence, precedence, fallbacks, truncation ---


def test_mixed_evidence_precedence():
    """Precedence test > file > command > empty."""
    kc = _kc("T1#1", "T1", "check feature and file")
    # Invalid test, valid file, command present -> file bucket
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="check feature and file",
            tests=["test_nonexistent"],
            evidence=[
                Evidence(kind="file", ref="README.md", expect="present"),
                Evidence(kind="command", ref="pytest"),
            ],
        )
    )
    inv = _inventory(tree=["README.md"], tests=[])
    res = enforce_traces([kc], report, inv)
    assert res.buckets["file"] == 1
    assert res.criteria_trace[0].bucket == "file"


def test_failed_validation_evidence_falling_to_next_bucket():
    """Invalid test and invalid file fall to command bucket."""
    kc = _kc("T1#1", "T1", "c1")
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="c1",
            tests=["test_missing"],
            evidence=[
                Evidence(kind="file", ref="missing.py", expect="present"),
                Evidence(kind="command", ref="python -m mypy"),
            ],
        )
    )
    inv = _inventory(tree=["app.py"], tests=[])
    res = enforce_traces([kc], report, inv)
    assert res.buckets["command"] == 1
    assert res.untraced == ["T1: c1"]
    assert res.criteria_trace[0].bucket == "command"


def test_key_versus_text_fallback():
    kc1 = _kc("T1#1", "T1", "Authoritative text 1")
    kc2 = _kc("T1#2", "T1", "Authoritative text 2")

    report = _report(
        # Matches by key even though text drifted
        CriterionTrace(key="T1#1", task_id="T1", criterion="Drifted text", tests=["test_a"]),
        # Matches by text fallback because key is absent
        CriterionTrace(key=None, task_id="T1", criterion="Authoritative text 2", tests=["test_b"]),
    )
    inv = _inventory(tests=["tests/test.py::test_a", "tests/test.py::test_b"])
    res = enforce_traces([kc1, kc2], report, inv)
    assert res.buckets["test"] == 2
    assert res.untraced == []


def test_truncated_tree_invalidates_missing_present_file():
    kc = _kc("T1#1", "T1", "config exists")
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="config exists",
            evidence=[Evidence(kind="file", ref="missing_cfg.json", expect="present")],
        )
    )
    inv = _inventory(tree=["existing.py"], truncated={"tree": True})
    res = enforce_traces([kc], report, inv)
    assert res.buckets["empty"] == 1
    assert res.untraced == ["T1: config exists"]
    assert res.criteria_trace[0].evidence[0].valid is False


def test_criteria_trace_cap_and_ref_shortening():
    # 305 criteria
    criteria = [_kc(f"T{i}#1", f"T{i}", f"Criterion {i}") for i in range(305)]
    # All are empty/untraced
    report = _report()
    inv = _inventory()
    res = enforce_traces(criteria, report, inv)
    assert len(res.criteria_trace) == 300
    assert res.truncated is True
    assert res.buckets["empty"] == 305
    assert len(res.untraced) == 305
    # Untraced list includes items beyond the 300 cap
    assert "T304: Criterion 304" in res.untraced

    # Ref shortening
    long_ref = "a" * 250
    kc_long = _kc("T1#1", "T1", "long ref")
    rep_long = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="long ref",
            evidence=[Evidence(kind="command", ref=long_ref)],
        )
    )
    res_long = enforce_traces([kc_long], rep_long, inv)
    assert res_long.truncated is True
    assert len(res_long.criteria_trace[0].evidence[0].ref) == 200


def test_command_only_populated_and_untraced():
    kc1 = _kc("T1#1", "T1", "command criterion")
    kc2 = _kc("T1#2", "T1", "empty criterion")
    report = _report(
        CriterionTrace(
            key="T1#1",
            task_id="T1",
            criterion="command criterion",
            evidence=[Evidence(kind="command", ref="pytest tests/")],
        )
    )
    inv = _inventory()
    res = enforce_traces([kc1, kc2], report, inv)
    assert res.buckets["command"] == 1
    assert res.buckets["empty"] == 1
    assert res.untraced == ["T1: command criterion", "T1: empty criterion"]
    assert res.command_only == ["T1: command criterion"]


def test_analysis_report_json_schema_contains_evidence_and_no_workflow_fields():
    """D-1 schema check: AnalysisReport has evidence and key, but no workflow-computed fields."""
    schema = AnalysisReport.model_json_schema()
    schema_str = str(schema)

    # Analyst-facing fields must be present
    assert "key" in schema_str
    assert "evidence" in schema_str

    # Workflow-computed fields must NOT be in the Analyst schema
    assert "TraceEnforcement" not in schema_str
    assert "AuditEvidence" not in schema_str
    assert "valid" not in schema.get("properties", {})
    assert "bucket" not in schema.get("properties", {})
    assert "untraced" not in schema.get("properties", {})
    assert "buckets" not in schema.get("properties", {})
