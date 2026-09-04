"""schedules/*.yaml loader (E-12). Mirrors agents/loader.py's fail-closed
idiom: a malformed asset must never reach the Temporal client."""

from __future__ import annotations

import pytest

from sdlc.schedules.loader import ScheduleError, load_schedules
from sdlc.schedules.models import ScheduleAsset

VALID = """\
spec:
  cron: "0 3 * * *"
  timezone: UTC
action:
  workflow: ReflectWorkflow
  banks: ["project:default"]
  backend: hindsight
  base_url: "http://localhost:8088"
"""


def _write(tmp_path, name: str, body: str):
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_loads_valid_asset_and_takes_id_from_filename(tmp_path):
    _write(tmp_path, "nightly-reflect.yaml", VALID)
    assets = load_schedules(tmp_path)
    assert len(assets) == 1
    a = assets[0]
    assert isinstance(a, ScheduleAsset)
    assert a.id == "nightly-reflect"  # filename is the API
    assert a.spec.cron == "0 3 * * *"
    assert a.spec.timezone == "UTC"
    assert a.action.workflow == "ReflectWorkflow"
    assert a.action.banks == ["project:default"]
    assert a.action.backend == "hindsight"


def test_timezone_defaults_to_utc(tmp_path):
    _write(
        tmp_path,
        "s.yaml",
        """\
spec:
  cron: "0 3 * * *"
action:
  workflow: ReflectWorkflow
  banks: ["project:default"]
""",
    )
    assert load_schedules(tmp_path)[0].spec.timezone == "UTC"


def test_bad_cron_field_count_raises(tmp_path):
    _write(tmp_path, "bad.yaml", VALID.replace('"0 3 * * *"', '"0 3 * *"'))
    with pytest.raises(ScheduleError, match="cron"):
        load_schedules(tmp_path)


def test_unknown_workflow_raises(tmp_path):
    _write(tmp_path, "bad.yaml", VALID.replace("ReflectWorkflow", "NopeWorkflow"))
    with pytest.raises(ScheduleError, match="NopeWorkflow"):
        load_schedules(tmp_path)


def test_empty_banks_raises(tmp_path):
    _write(tmp_path, "bad.yaml", VALID.replace('["project:default"]', "[]"))
    with pytest.raises(ScheduleError):
        load_schedules(tmp_path)


def test_missing_banks_raises(tmp_path):
    _write(
        tmp_path,
        "bad.yaml",
        """\
spec:
  cron: "0 3 * * *"
action:
  workflow: ReflectWorkflow
""",
    )
    with pytest.raises(ScheduleError):
        load_schedules(tmp_path)


def test_error_names_the_offending_file(tmp_path):
    _write(tmp_path, "nightly-reflect.yaml", VALID.replace("ReflectWorkflow", "Nope"))
    with pytest.raises(ScheduleError, match="nightly-reflect.yaml"):
        load_schedules(tmp_path)


def test_empty_directory_returns_empty_list(tmp_path):
    assert load_schedules(tmp_path) == []


def test_missing_directory_returns_empty_list(tmp_path):
    assert load_schedules(tmp_path / "does-not-exist") == []


def test_assets_are_sorted_by_id(tmp_path):
    _write(tmp_path, "b-two.yaml", VALID)
    _write(tmp_path, "a-one.yaml", VALID)
    assert [a.id for a in load_schedules(tmp_path)] == ["a-one", "b-two"]


def test_env_var_overrides_default_dir(tmp_path, monkeypatch):
    _write(tmp_path, "s.yaml", VALID)
    monkeypatch.setenv("SDLC_SCHEDULES_DIR", str(tmp_path))
    assert len(load_schedules()) == 1


def test_yaml_syntax_error_raises_schedule_error(tmp_path):
    _write(tmp_path, "broken.yaml", "spec: [unclosed")
    with pytest.raises(ScheduleError, match="broken.yaml"):
        load_schedules(tmp_path)


def test_non_mapping_body_raises_schedule_error(tmp_path):
    _write(tmp_path, "list.yaml", "- just\n- a\n- list\n")
    with pytest.raises(ScheduleError, match="list.yaml"):
        load_schedules(tmp_path)
