"""020 T013 (US5, contract §5): the CLI maps a legacy FeatureWorkflow run to a
stderr message and exit 1, never a traceback.

Drives sdlc.cli.main() through its real argparse dispatch; only the Temporal
client is replaced, so the query -> describe -> LegacyRunError chain runs for
real (transport.fail_legacy_if_closed_feature).
"""

from __future__ import annotations

import asyncio
import sys

import pytest

import sdlc.cli as cli

LEGACY_MESSAGE = "legacy FeatureWorkflow run; it can no longer be queried"


class _Described:
    workflow_type = "FeatureWorkflow"


class _LegacyHandle:
    id = "legacy-run"

    async def query(self, name):
        raise RuntimeError("not registered")

    async def describe(self):
        return _Described()


class _FakeTemporal:
    def get_workflow_handle_for(self, run, run_id):
        return _LegacyHandle()


class _FakeClientType:
    @staticmethod
    async def connect(*args, **kwargs):
        return _FakeTemporal()


@pytest.fixture
def fake_temporal(monkeypatch):
    monkeypatch.setattr(cli, "Client", _FakeClientType)


def _run_cli(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["sdlc", *argv])
    asyncio.run(cli.main())


def test_approve_on_a_legacy_run_prints_the_contract_message_and_exits_1(
    fake_temporal, monkeypatch, capsys
):
    with pytest.raises(SystemExit) as e:
        _run_cli(monkeypatch, ["approve", "--id", "legacy-run"])
    assert e.value.code == 1
    assert LEGACY_MESSAGE in capsys.readouterr().err


def test_status_on_a_legacy_run_prints_the_contract_message_and_exits_1(
    fake_temporal, monkeypatch, capsys
):
    with pytest.raises(SystemExit) as e:
        _run_cli(monkeypatch, ["status", "--id", "legacy-run"])
    assert e.value.code == 1
    assert LEGACY_MESSAGE in capsys.readouterr().err
