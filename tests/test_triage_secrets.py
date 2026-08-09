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


@pytest.mark.parametrize("line", [
    'API_SECRET = "ak_live_0123456789abcdefXYZ"',        # compound, quoted
    'DB_PASSWORD = "supersecretvalue12345678"',           # compound, quoted
    'STRIPE_SECRET_KEY = "sk_live_0123456789abcdefAB"',   # compound, quoted
    'AUTH_TOKEN = "tok_live_0123456789abcdefXY"',         # compound, quoted
    # service_role / private_key: the client-bundle vocabulary, now recognised
    # by the generic rule too so a leaked service-role JWT or private key in a
    # NON-.env file (compose, CI, shell) is caught.
    'SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiJ9XYZab"',
    'STRIPE_PRIVATE_KEY = "sk_live_0123456789abcdefAB12"',
])
def test_generic_rule_matches_compound_variable_names(line):
    # The keyword may sit anywhere in the identifier, delimited by _/$/- or the
    # edge, so compound names match.
    found = secrets.scan_text("src/config.py", line)
    assert "generic_secret_assignment" in _rules(found)


@pytest.mark.parametrize("line", [
    'TOKENIZER_MODEL = "sentence-transformers/all-MiniLM"',   # token in tokenizer
    'tokenizer_path = "models/tokenizer-v2-final.json"',
    'jwtSecret = "eyJhbGciOiJIUzI1NiJ9abcdefg"',              # camelCase, no sep
])
def test_generic_rule_ignores_keyword_substrings_and_unsplit_camelcase(line):
    # Segment-delimited matching: `token` inside TOKENIZER is a substring of a
    # larger word, not a segment, so it does not fire (a real false positive in
    # every ML repo). camelCase jwtSecret has no separator before Secret, so it
    # does not fire either -- the accepted recall cost of the precision trade.
    found = secrets.scan_text("src/config.py", line)
    assert "generic_secret_assignment" not in _rules(found), line


def test_generic_rule_matches_unquoted_env_assignment():
    # .env syntax: KEY=value with no quotes. The compound name plus a
    # high-entropy unquoted value is the flagship vibe-code leak shape.
    found = secrets.scan_text(
        "backend/.env", "API_SECRET=ak_live_0123456789abcdefxyz")
    assert "generic_secret_assignment" in _rules(found)


def test_generic_rule_still_ignores_a_compound_name_with_a_placeholder():
    found = secrets.scan_text("s.py", 'DB_PASSWORD = "changeme"')
    assert found == []


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


def test_is_over_size_limit_counts_bytes_not_characters():
    # Moved to gitread (spec D10): one size bound for every consumer of the
    # reader, not one per signal.
    from sdlc.triage.gitread import MAX_BLOB_BYTES, is_over_size_limit
    assert not is_over_size_limit("x" * MAX_BLOB_BYTES)
    assert is_over_size_limit("x" * (MAX_BLOB_BYTES + 1))
    # Three-byte characters exceed the byte limit at a third of the count,
    # even though their character count is well under MAX_BLOB_BYTES.
    assert is_over_size_limit("\uffff" * 333334)


def test_nested_env_files_are_matched():
    # The monorepo shape: backend service + web app each carry a nested .env.
    found = secrets.env_file_findings(["backend/.env", "apps/web/.env.local"])
    by_rule = {f.rule: f for f in found}
    assert set(by_rule) == {"secret_committed", "env_file_tracked"}
    # secret_committed names every matched file so rotation covers all of them.
    assert "backend/.env" in by_rule["secret_committed"].detail
    assert "apps/web/.env.local" in by_rule["secret_committed"].detail


def test_nested_env_example_is_not_flagged():
    assert secrets.env_file_findings(["apps/web/.env.example"]) == []


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
async def test_activity_flags_a_nested_env_in_a_monorepo(tmp_path):
    # The reviewer's flagship: a backend/.env nested under a service dir, holding
    # a service-role JWT on a compound variable name. A nested .env must report
    # secret_committed -- the file itself is the leak, regardless of its lines.
    sha = _commit_repo(tmp_path, {
        "backend/.env":
            "SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\n",
        "src/app.py": "x = 1\n",
    })
    r = await triage_secrets(
        TriageSignalInput(repo_dir=str(tmp_path), commit_sha=sha))
    rules = _rules(r.findings)
    assert "secret_committed" in rules
    assert "env_file_tracked" in rules


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
