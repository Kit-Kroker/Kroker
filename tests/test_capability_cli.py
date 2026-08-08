"""FR-913 identity correction CLI (E-47a)."""
import argparse
import json

import pytest

from sdlc.capability.cli import add_capability_parser, run_capability
from sdlc.capability.models import (
    CapabilityFingerprint, CapabilityIdentity, IdentityStatus, SignalTier,
)
from sdlc.capability.store import BoardIdentityStore
from sdlc.measurement import Measurement


def _fp(*contract) -> CapabilityFingerprint:
    return CapabilityFingerprint(
        tiers={SignalTier.CONTRACT: list(contract)},
        collected=Measurement.measured(1.0))


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "board.sqlite3"
    s = BoardIdentityStore(db=path)
    s.apply("p", [
        CapabilityIdentity(bc_id="BC-001", project="p", first_seen_run="r0",
                           fingerprint=_fp("POST /a")),
        CapabilityIdentity(bc_id="BC-002", project="p", first_seen_run="r0",
                           fingerprint=_fp("POST /b")),
    ], expected_version=0)
    s.close()
    return path


def _parse(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    add_capability_parser(sub)
    return p.parse_args(argv)


def test_merge_applies_and_reports_success(db, capsys):
    args = _parse(["capability", "merge", "--project", "p",
                   "--from", "BC-001", "--into", "BC-002",
                   "--reason", "same thing", "--by", "maks",
                   "--db", str(db)])
    assert run_capability(args) == 0
    assert "BC-001" in capsys.readouterr().out
    store = BoardIdentityStore(db=db)
    rows = {r.bc_id: r for r in store.load("p")}
    store.close()
    assert rows["BC-001"].status is IdentityStatus.MERGED


def test_reattach_applies(db):
    args = _parse(["capability", "reattach", "--project", "p",
                   "--from", "BC-002", "--into", "BC-001",
                   "--reason", "refactor", "--by", "maks", "--db", str(db)])
    assert run_capability(args) == 0


def test_split_requires_members(db):
    args = _parse(["capability", "split", "--project", "p",
                   "--from", "BC-001", "--reason", "two things",
                   "--by", "maks", "--db", str(db)])
    assert run_capability(args) == 2


def test_split_with_members_applies(db):
    seeded = BoardIdentityStore(db=db)
    seeded.apply("p", [CapabilityIdentity(
        bc_id="BC-001", project="p", first_seen_run="r0",
        fingerprint=_fp("POST /a", "POST /a2"))],
        expected_version=seeded.registry_version("p"))
    seeded.close()
    args = _parse(["capability", "split", "--project", "p",
                   "--from", "BC-001", "--member", "POST /a2",
                   "--reason", "two things", "--by", "maks", "--db", str(db)])
    assert run_capability(args) == 0


def test_unknown_capability_exits_nonzero_with_a_message(db, capsys):
    args = _parse(["capability", "merge", "--project", "p",
                   "--from", "BC-404", "--into", "BC-001",
                   "--reason", "x", "--by", "maks", "--db", str(db)])
    assert run_capability(args) == 2
    assert "BC-404" in capsys.readouterr().err


def test_list_prints_every_id_including_retired(db, capsys):
    args = _parse(["capability", "list", "--project", "p", "--db", str(db)])
    assert run_capability(args) == 0
    out = capsys.readouterr().out
    assert "BC-001" in out and "BC-002" in out


def test_export_writes_a_hash_only_file(db, tmp_path, capsys):
    target = tmp_path / ".sdlc" / "capabilities.json"
    args = _parse(["capability", "export", "--project", "p",
                   "--out", str(target), "--db", str(db)])
    assert run_capability(args) == 0
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["capabilities"][0]["fingerprint_sha256"]
    assert "POST /a" not in target.read_text(encoding="utf-8")
