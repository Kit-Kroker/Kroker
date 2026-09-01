"""D10: the config-path table is shared, so SS3 must declare it."""

from __future__ import annotations

import pytest

from sdlc.assessment.scan import rules
from sdlc.assessment.scan.configpaths import is_config_path
from sdlc.assessment.scan.models import ScanSignalId
from sdlc.assessment.scan.registry import SCAN_SIGNALS

_CONFIGPATHS = "sdlc.assessment.scan.configpaths"


@pytest.mark.parametrize(
    "path",
    [
        "Dockerfile",
        "svc/Dockerfile.prod",
        "docker-compose.yml",
        ".env",
        ".env.production",
        "appsettings.Development.json",
        "src/main/resources/application-prod.yaml",
        "k8s/deploy.yaml",
        "infra/main.tf",
        "nginx.conf",
    ],
)
def test_config_paths_are_recognized(path):
    assert is_config_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "src/payments/api.py",
        "README.md",
        "tests/test_api.py",
        "app/page.tsx",
    ],
)
def test_non_config_paths_are_not(path):
    assert not is_config_path(path)


def test_ss3_declares_the_shared_table():
    assert _CONFIGPATHS in SCAN_SIGNALS[ScanSignalId.SS3].rule_modules


def test_editing_the_table_moves_ss3s_memo_key(monkeypatch):
    """The declaration is only real if rules_sha actually hashes it."""
    before = rules.rules_sha(ScanSignalId.SS3)
    real = rules.module_sha

    def shifted(dotted: str) -> str:
        return "deadbeef" if dotted == _CONFIGPATHS else real(dotted)

    monkeypatch.setattr(rules, "module_sha", shifted)
    assert rules.rules_sha(ScanSignalId.SS3) != before
