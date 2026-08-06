"""The highest-yield vibe-code signal, and the one where a false positive
costs the most trust.
"""
import subprocess

import pytest

from sdlc.grounding import Profile, verify_quote
from sdlc.measurement import CollectionState
from sdlc.triage.activities import TriageSignalInput, read_blob, triage_secrets
from sdlc.triage.models import FixClass
from sdlc.triage.signals import secrets


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True,
                          encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL)


def _commit_repo(root, files: dict[str, str]) -> str:
    _run(["git", "init", "-q"], root)
    _run(["git", "config", "user.email", "t@example.com"], root)
    _run(["git", "config", "user.name", "T"], root)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _run(["git", "add", "-A"], root)
    _run(["git", "commit", "-q", "-m", "one"], root)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, encoding="utf-8",
                          check=True, stdin=subprocess.DEVNULL).stdout.strip()


def _rules(findings):
    return {f.rule for f in findings}


# ---- provider patterns ------------------------------------------------

@pytest.mark.parametrize("line,rule", [
    ('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"', "aws_access_key_id"),
    ('t = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"', "github_token"),
    ('k = "AIzaSyD-0123456789abcdefghijklmnopqrstu"', "google_api_key"),
    ('s = "xoxb-123456789012-abcdefghijklmnop"', "slack_token"),
    ("-----BEGIN RSA PRIVATE KEY-----", "private_key"),
])
def test_provider_patterns_are_critical(line, rule):
    found = secrets.scan_text("src/config.py", line)
    assert rule in _rules(found)
    f = next(f for f in found if f.rule == rule)
    assert f.severity == "critical"
    assert f.fix_class is FixClass.JUDGEMENT   # rotation is not mechanical


def test_finding_carries_the_matched_line_and_number():
    text = "import os\n\nAWS_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"
    f = next(f for f in secrets.scan_text("c.py", text)
             if f.rule == "aws_access_key_id")
    assert f.line == 3
    assert "AKIAIOSFODNN7EXAMPLE" in f.evidence
    assert f.path == "c.py"


# ---- generic rule + entropy gate --------------------------------------

def test_generic_rule_ignores_a_low_entropy_placeholder():
    assert secrets.scan_text("s.py", 'password = "changeme"') == []


def test_generic_rule_ignores_a_short_value():
    assert secrets.scan_text("s.py", 'api_key = "abc123"') == []


def test_generic_rule_flags_a_high_entropy_value_at_low_severity():
    found = secrets.scan_text(
        "s.py", 'API_KEY = "f3Kq9Zx2Lm7Rv4Tn8Wb1Yc6Hd5Jg0Ps"')
    assert _rules(found) == {"generic_secret_assignment"}
    assert found[0].severity == "low"


# ---- client-bundle reachability ---------------------------------------

@pytest.mark.parametrize("var", [
    "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY",
    "VITE_STRIPE_SECRET_KEY",
    "REACT_APP_PRIVATE_KEY",
    "EXPO_PUBLIC_API_SECRET",
    "GATSBY_SERVICE_ROLE_TOKEN",
])
def test_client_inlined_secret_named_vars_are_critical(var):
    found = secrets.scan_text("src/lib/db.ts", f"const k = process.env.{var};")
    assert "client_bundle_secret" in _rules(found)
    f = next(f for f in found if f.rule == "client_bundle_secret")
    assert f.severity == "critical"
    assert var in f.detail


def test_public_prefixed_but_not_secret_named_var_is_not_flagged():
    found = secrets.scan_text(
        "src/a.ts", "const u = process.env.NEXT_PUBLIC_API_URL;")
    assert "client_bundle_secret" not in _rules(found)


def test_secret_named_but_not_client_prefixed_var_is_not_client_flagged():
    found = secrets.scan_text(
        "server/a.ts", "const k = process.env.SUPABASE_SERVICE_ROLE_KEY;")
    assert "client_bundle_secret" not in _rules(found)


# ---- committed .env ----------------------------------------------------

def test_committed_env_splits_into_two_findings():
    found = secrets.env_file_findings([".env", "src/a.py"])
    by_rule = {f.rule: f for f in found}
    assert by_rule["secret_committed"].fix_class is FixClass.JUDGEMENT
    assert "rotat" in by_rule["secret_committed"].detail.lower()
    assert by_rule["env_file_tracked"].fix_class is FixClass.MECHANICAL


def test_env_rule_names_do_not_collide_with_baseline():
    # baseline owns "gitignore_missing_env" (the .gitignore does not cover
    # .env); secrets owns "env_file_tracked" (a .env is IN the index). Two
    # conditions, two names -- one rule id must mean one thing.
    assert {f.rule for f in secrets.env_file_findings([".env"])} == {
        "secret_committed", "env_file_tracked"}


def test_no_env_tracked_means_no_env_findings():
    assert secrets.env_file_findings(["src/a.py"]) == []


# ---- activity ----------------------------------------------------------

@pytest.mark.asyncio
async def test_activity_finds_the_canonical_vibe_repo_leak(tmp_path):
    sha = _commit_repo(tmp_path, {
        ".env": "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiJ9\n",
        "src/db.ts": "export const k = "
                     "process.env.NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY;\n",
    })
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.collected.state is CollectionState.MEASURED
    assert {"secret_committed", "client_bundle_secret"} <= _rules(r.findings)
    assert r.metrics == {}          # secrets feeds no readiness dimension


@pytest.mark.asyncio
async def test_gitignored_local_env_produces_no_finding(tmp_path):
    # D6: enumeration from the tracked tree, not the worktree.
    sha = _commit_repo(tmp_path, {".gitignore": ".env\n",
                                  "src/a.py": "x = 1\n"})
    (tmp_path / ".env").write_text(
        'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.findings == []


@pytest.mark.asyncio
async def test_every_evidence_quote_verifies_against_the_pinned_bytes(tmp_path):
    # D5: the drift guard, and FR-914's first commit-source caller.
    sha = _commit_repo(tmp_path, {
        "src/config.py": 'import os\nAWS = "AKIAIOSFODNN7EXAMPLE"\n'})
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    assert r.findings
    for f in r.findings:
        if not f.evidence or not f.path:
            continue
        blob = read_blob(str(tmp_path), sha, f.path)
        assert blob is not None
        assert verify_quote(f.evidence, blob, Profile.VERBATIM_BYTES)


@pytest.mark.asyncio
async def test_activity_reports_not_collected_on_a_bad_sha(tmp_path):
    _commit_repo(tmp_path, {"src/a.py": "x = 1\n"})
    r = await triage_secrets(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha="0" * 40))
    assert r.collected.state is CollectionState.NOT_COLLECTED
    assert r.findings == []


@pytest.mark.asyncio
async def test_binary_blob_is_skipped_not_crashed(tmp_path):
    sha = _commit_repo(tmp_path, {"src/a.py": "x = 1\n"})
    (tmp_path / "logo.bin").write_bytes(b"\x00\x01\x02AKIAIOSFODNN7EXAMPLE")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-q", "-m", "two"], tmp_path)
    sha2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                          capture_output=True, encoding="utf-8",
                          check=True, stdin=subprocess.DEVNULL).stdout.strip()
    r = await triage_secrets(TriageSignalInput(
        repo_dir=str(tmp_path), commit_sha=sha2))
    assert r.collected.state is CollectionState.MEASURED
    assert r.findings == []
