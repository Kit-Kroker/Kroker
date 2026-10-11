import pytest

from sdlc.benchmarks.oracle_id import oracle_identity


def test_oracle_identity_format_and_reproducibility(tmp_path):
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir()
    (oracle_dir / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (oracle_dir / "test_b.py").write_text("def test_two(): pass\n", encoding="utf-8")

    ident1 = oracle_identity(oracle_dir)
    assert ident1.startswith("sha256:")
    assert len(ident1) == 7 + 64
    assert int(ident1[7:], 16) >= 0  # valid hex

    # same tree gives exact same value
    ident2 = oracle_identity(oracle_dir)
    assert ident1 == ident2


def test_oracle_identity_changes_on_byte_add_or_rename(tmp_path):
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (base_dir / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (base_dir / "test_b.py").write_text("def test_two(): pass\n", encoding="utf-8")
    base_ident = oracle_identity(base_dir)

    # changed byte
    changed_dir = tmp_path / "changed"
    changed_dir.mkdir()
    (changed_dir / "test_a.py").write_text("def test_one(): pass!\n", encoding="utf-8")
    (changed_dir / "test_b.py").write_text("def test_two(): pass\n", encoding="utf-8")
    assert oracle_identity(changed_dir) != base_ident

    # added file
    added_dir = tmp_path / "added"
    added_dir.mkdir()
    (added_dir / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (added_dir / "test_b.py").write_text("def test_two(): pass\n", encoding="utf-8")
    (added_dir / "test_c.py").write_text("def test_three(): pass\n", encoding="utf-8")
    assert oracle_identity(added_dir) != base_ident

    # renamed file
    renamed_dir = tmp_path / "renamed"
    renamed_dir.mkdir()
    (renamed_dir / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    (renamed_dir / "test_renamed.py").write_text("def test_two(): pass\n", encoding="utf-8")
    assert oracle_identity(renamed_dir) != base_ident


def test_oracle_identity_ignores_caches_and_pyc(tmp_path):
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    (clean_dir / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    clean_ident = oracle_identity(clean_dir)

    dirty_dir = tmp_path / "dirty"
    dirty_dir.mkdir()
    (dirty_dir / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")

    # add __pycache__ directory
    pycache = dirty_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "test_a.cpython-313.pyc").write_bytes(b"dummy bytecode")

    # add .pytest_cache directory
    pytest_cache = dirty_dir / ".pytest_cache"
    pytest_cache.mkdir()
    (pytest_cache / "README.md").write_text("cache info\n", encoding="utf-8")

    # add *.pyc at root
    (dirty_dir / "standalone.pyc").write_bytes(b"bytecode")

    assert oracle_identity(dirty_dir) == clean_ident


def test_oracle_identity_normalizes_crlf(tmp_path):
    crlf_dir = tmp_path / "crlf"
    crlf_dir.mkdir()
    (crlf_dir / "test.py").write_bytes(b"line 1\r\nline 2\r\n")

    lf_dir = tmp_path / "lf"
    lf_dir.mkdir()
    (lf_dir / "test.py").write_bytes(b"line 1\nline 2\n")

    assert oracle_identity(crlf_dir) == oracle_identity(lf_dir)


def test_oracle_identity_missing_dir_raises(tmp_path):
    nonexistent = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        oracle_identity(nonexistent)
