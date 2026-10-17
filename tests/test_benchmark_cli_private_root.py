"""016 T003: cross-root case resolution at the benchmark CLI.

Split out of tests/test_benchmark_cli.py when the 016 additions crossed
the 1000-line ceiling (the file-size ratchet is the authority) — the
process seam is exact: every test here exercises accept / verify-case /
corpus behaviour that exists only with the private store configured
(plan 016 D-2/D-3/D-4, Names "Corpus" and "CLI"). The parent file keeps
the single-root CLI contract tests.
"""

from pathlib import Path

import pytest

# --- 016 T003 (RED): cross-root resolution at the CLI --------------------------


def _write_min_case(cdir: Path, cid: str, *, visibility: str = "private") -> Path:
    """Minimal case dir with no language (so accept takes the cheap
    not_assessed branch) and no reference/ (so verify-case fails fast)."""
    cdir.mkdir(parents=True)
    (cdir / "case.yaml").write_text(
        f"case_id: {cid}\n"
        f"idea_summary: summary of {cid}\n"
        f"harnesses: [opencode]\n"
        f"models: [m]\n"
        f"judge_model: j\n"
        f"role: corpus\n"
        f"visibility: {visibility}\n",
        encoding="utf-8",
    )
    return cdir


def test_dispatch_accept_resolves_a_private_only_case_and_writes_isolated(
    tmp_path, capsys, monkeypatch
):
    """Names/D-2: accept --case <id> (no --cases-root) resolves across the
    roots; a case found only in the store is accepted in place (the
    acceptance.yaml lands in the store) and its record carries exposure
    'isolated' (D-4)."""
    from sdlc.benchmarks.acceptance import Verdict, load_acceptance
    from sdlc.benchmarks.cli import dispatch_accept

    primary = tmp_path / "primary-cases"
    primary.mkdir()
    private = tmp_path / "store" / "cases"
    c_dir = _write_min_case(private / "store-accept", "store-accept")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))

    dispatch_accept(case="store-accept", offline=True)

    out = capsys.readouterr().out
    assert "store-accept" in out
    assert "not_assessed" in out
    rec = load_acceptance(c_dir)
    assert rec is not None
    assert rec.verdict == Verdict.NOT_ASSESSED
    assert rec.exposure == "isolated"


def test_dispatch_accept_primary_root_case_writes_repo_public(tmp_path, monkeypatch):
    """The control of the pair: a case under the primary root, resolved
    through the same no-cases_root call form, keeps exposure
    'repo_public' (D-4)."""
    from sdlc.benchmarks.acceptance import load_acceptance
    from sdlc.benchmarks.cli import dispatch_accept

    primary = tmp_path / "primary-cases"
    c_dir = _write_min_case(primary / "primary-accept", "primary-accept", visibility="public")
    private = tmp_path / "store" / "cases"
    private.mkdir(parents=True)
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))

    dispatch_accept(case="primary-accept", offline=True)

    rec = load_acceptance(c_dir)
    assert rec is not None
    assert rec.exposure == "repo_public"


def test_dispatch_verify_case_resolves_a_private_only_case(tmp_path, monkeypatch):
    """verify-case --case <id> (no --cases-root) must resolve the id in
    the store too; with no reference/ it FAILs naming the resolved
    private path (the cheap observation, no oracle run)."""
    from sdlc.benchmarks.cli import dispatch_verify_case

    primary = tmp_path / "primary-cases"
    primary.mkdir()
    private = tmp_path / "store" / "cases"
    c_dir = _write_min_case(private / "store-verify", "store-verify")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))

    out = dispatch_verify_case(case="store-verify")
    assert "FAIL" in out
    assert str(c_dir) in out


def test_dispatch_corpus_prints_the_store_note(tmp_path, monkeypatch):
    """Names: dispatch_corpus passes the store note to the render, so the
    note line is part of the returned text."""
    from sdlc.benchmarks.cli import dispatch_corpus

    primary = tmp_path / "primary-cases"
    primary.mkdir()
    private = tmp_path / "store" / "cases"
    _write_min_case(private / "store-corp", "store-corp")
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))

    out = dispatch_corpus()
    assert f"private store: 1 case(s) at {private}" in out


# --- 016 T003 (RED, chaos): CLI error edges across the two roots ---------------


def _two_roots_cli(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    primary = tmp_path / "primary-cases"
    private = tmp_path / "store" / "cases"
    primary.mkdir()
    private.mkdir(parents=True)
    monkeypatch.setenv("SDLC_CASES_ROOT", str(primary))
    monkeypatch.setenv("SDLC_PRIVATE_CASES_ROOT", str(private))
    return primary, private


def test_dispatch_accept_duplicate_id_exits_naming_both_case_dirs(tmp_path, monkeypatch):
    """D-2: DuplicateCase becomes a one-line SystemExit, no traceback."""
    from sdlc.benchmarks.cli import dispatch_accept

    primary, private = _two_roots_cli(tmp_path, monkeypatch)
    pub = _write_min_case(primary / "dup-case", "dup-case", visibility="public")
    priv = _write_min_case(private / "dup-case", "dup-case")
    with pytest.raises(SystemExit) as exc:
        dispatch_accept(case="dup-case", offline=True)
    message = str(exc.value)
    assert str(pub) in message
    assert str(priv) in message


def test_dispatch_verify_case_duplicate_id_exits_naming_both_case_dirs(tmp_path, monkeypatch):
    from sdlc.benchmarks.cli import dispatch_verify_case

    primary, private = _two_roots_cli(tmp_path, monkeypatch)
    pub = _write_min_case(primary / "dup-case", "dup-case", visibility="public")
    priv = _write_min_case(private / "dup-case", "dup-case")
    with pytest.raises(SystemExit) as exc:
        dispatch_verify_case(case="dup-case")
    message = str(exc.value)
    assert str(pub) in message
    assert str(priv) in message


def test_dispatch_accept_absent_id_exits_naming_every_searched_root(tmp_path, monkeypatch):
    """Strict form at the CLI: CaseNotFound names every root searched."""
    from sdlc.benchmarks.cli import dispatch_accept

    primary, private = _two_roots_cli(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as exc:
        dispatch_accept(case="absent-case", offline=True)
    message = str(exc.value)
    assert str(primary) in message
    assert str(private) in message


def test_dispatch_accept_explicit_cases_root_wins_over_the_private_root(tmp_path, monkeypatch):
    """An explicit --cases-root keeps today's behaviour: the private root
    is not consulted, so a store-only case is 'not found'."""
    from sdlc.benchmarks.cli import dispatch_accept

    primary, private = _two_roots_cli(tmp_path, monkeypatch)
    _write_min_case(private / "store-only", "store-only")
    with pytest.raises(SystemExit, match="case directory not found"):
        dispatch_accept(case="store-only", offline=True, cases_root=str(primary))
