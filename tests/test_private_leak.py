"""Unit tests of the private-store leak guard (016 T010, D-10) on a
SYNTHETIC store: every string in this file is invented for the test, and
nothing here comes from the real private store or quotes the spec. The
tracked-file scan over a real store is a separate opt-in test (Names,
Leak guard: REAL_PRIVATE_ROOT), not this file's unit tier.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.check_private_leak import collect_tokens, scan

# 016 D-12: the machine's real store binding, captured at import BEFORE the
# autouse fixture clears the variable (same capture as test_benchmark_corpus).
REAL_PRIVATE_ROOT = os.environ.get("SDLC_PRIVATE_CASES_ROOT")

# The six fixed error-class names (ERROR_CLASSES) must never become tokens.
ERROR_CLASS_NAMES = [
    "functional",
    "security",
    "performance",
    "data_integrity",
    "error_handling",
    "api_contract",
]

# The domain words of spec R5, written into the synthetic description and
# asserted absent from the token set.
DOMAIN_WORDS = ["theatre", "box", "office"]

# Representative 8-word runs, fully inside one sentence of the synthetic
# description / rubric, away from punctuation and from the domain words.
DESCRIPTION_RUN = "the venue releases a held seat when the"
RUBRIC_RUN = "score the plan by how the seams separate"


def _build_synthetic_store(tmp_path: Path) -> Path:
    """One invented case under a tmp cases root: an oracle test, a
    mapping, a reference module, a description and a rubric."""
    cases = tmp_path / "cases"
    case = cases / "synthetic-venue-case"
    (case / "oracle").mkdir(parents=True)
    (case / "reference").mkdir()

    (case / "oracle" / "test_sales.py").write_text(
        "def test_hold_expires_at_caller_time():\n    assert True\n",
        encoding="utf-8",
    )
    (case / "tasks.yaml").write_text(
        "tasks:\n"
        "  - id: release-holds-after-refund\n"
        "    error_class: functional\n"
        "    tier: basic\n"
        "    feature: seat map\n",
        encoding="utf-8",
    )
    (case / "reference" / "pricing.py").write_text(
        "def apply_discount(total):\n    return total\n\n\nclass PriceTiers:\n    pass\n",
        encoding="utf-8",
    )
    (case / "case.yaml").write_text(
        yaml.safe_dump(
            {
                "case_id": "synthetic-venue-case",
                "idea_summary": "an invented case for leak-guard unit tests",
                "description": (
                    "the theatre box office sells tickets for tonight. "
                    f"{DESCRIPTION_RUN} the refund completes. "
                    "nothing here is real."
                ),
                "mode": "greenfield",
            }
        ),
        encoding="utf-8",
    )
    (case / "rubric-planner.md").write_text(
        f"{RUBRIC_RUN} the components. an invented rubric text.\n",
        encoding="utf-8",
    )
    return cases


def test_collect_tokens_covers_oracle_tasks_reference_and_shingles(tmp_path):
    tokens = collect_tokens(_build_synthetic_store(tmp_path))
    # oracle: the node id and the bare test function name
    assert "test_sales.py::test_hold_expires_at_caller_time" in tokens
    assert "test_hold_expires_at_caller_time" in tokens
    # tasks.yaml: the requirement id and the feature value
    assert "release-holds-after-refund" in tokens
    assert "seat map" in tokens
    # reference: the module name and its top-level function and class names
    assert "pricing" in tokens
    assert "apply_discount" in tokens
    assert "PriceTiers" in tokens
    # 8-word shingles of the description and of the rubric
    assert DESCRIPTION_RUN in tokens
    assert RUBRIC_RUN in tokens


def test_collect_tokens_excludes_error_classes_and_domain_words(tmp_path):
    tokens = collect_tokens(_build_synthetic_store(tmp_path))
    for name in ERROR_CLASS_NAMES:
        assert name not in tokens, f"error-class name {name!r} must not be a token"
    for word in DOMAIN_WORDS:
        assert word not in tokens, f"domain word {word!r} must not be a token"


def test_scan_flags_a_reference_name_line_and_a_description_run(tmp_path):
    collect_tokens(_build_synthetic_store(tmp_path))  # seed nothing; scan is self-contained
    findings_ref = scan("we call apply_discount inside the checkout flow\n")
    assert findings_ref, "a line naming a reference function must be flagged"

    findings_shingle = scan(f"proposal says {DESCRIPTION_RUN} refund completes\n")
    assert findings_shingle, "a line carrying an 8-word description run must be flagged"


def test_scan_returns_nothing_for_clean_text(tmp_path):
    _build_synthetic_store(tmp_path)
    assert scan("totally unrelated prose about gardening tools and weather\n") == []


# --- chaos: the CLI surface of scripts/check_private_leak.py -------------------
#
# Subprocess on purpose: the exit code, the note and the git plumbing
# (`--staged` reads `git diff --cached`, `--tracked` reads `git ls-files`)
# are what the pre-commit hook and the opt-in repo test actually run.

GUARD_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_private_leak.py"
REPO_ROOT = Path(__file__).resolve().parents[1]
ABSENT_NOTE = "private store absent; skipped"
# A reference function name of the synthetic store (an id token: has "_").
LEAK = "apply_discount"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """A tmp git repo with one initial commit holding `files`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for name, text in files.items():
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial")
    return repo


def _run_guard(repo: Path, mode: str, private_root: Path | str | None):
    env = dict(os.environ)
    env.pop("SDLC_PRIVATE_CASES_ROOT", None)
    if private_root is not None:
        env["SDLC_PRIVATE_CASES_ROOT"] = str(private_root)
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), mode],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout + proc.stderr


@pytest.mark.parametrize("mode", ["--tracked", "--staged"])
def test_cli_with_the_private_root_unset_skips_with_a_note(tmp_path, mode):
    repo = _git_repo(tmp_path, {"notes.txt": f"call {LEAK} here\n"})
    code, out = _run_guard(repo, mode, None)
    assert code == 0, out
    assert ABSENT_NOTE in out


@pytest.mark.parametrize("mode", ["--tracked", "--staged"])
def test_cli_with_the_private_root_absent_on_disk_skips_with_a_note(tmp_path, mode):
    repo = _git_repo(tmp_path, {"notes.txt": f"call {LEAK} here\n"})
    code, out = _run_guard(repo, mode, tmp_path / "never-created")
    assert code == 0, out
    assert ABSENT_NOTE in out


def test_cli_staged_flags_only_the_added_line_not_the_context(tmp_path):
    """--staged scans the ADDED lines of `git diff --cached`. The committed
    line 1 already carries a token (it is context in the diff); the staged
    change adds line 2, which carries one too. Only line 2 is a finding."""
    store = _build_synthetic_store(tmp_path)
    repo = _git_repo(tmp_path, {"notes.txt": f"CONTEXTLINE uses {LEAK}\n"})
    (repo / "notes.txt").write_text(
        f"CONTEXTLINE uses {LEAK}\nADDEDLINE uses {LEAK}\n", encoding="utf-8"
    )
    _git(repo, "add", "notes.txt")

    code, out = _run_guard(repo, "--staged", store)
    assert code == 1, out
    assert "ADDEDLINE" in out or "notes.txt:2" in out
    assert "CONTEXTLINE" not in out
    assert "notes.txt:1" not in out


def test_cli_staged_with_only_clean_added_lines_passes_over_a_committed_token(tmp_path):
    """The committed history may hold a token; a staged change that adds
    only clean lines is not a finding (--staged is the hook mode)."""
    store = _build_synthetic_store(tmp_path)
    repo = _git_repo(tmp_path, {"notes.txt": f"CONTEXTLINE uses {LEAK}\n"})
    (repo / "notes.txt").write_text(
        f"CONTEXTLINE uses {LEAK}\nunrelated prose about gardening tools\n", encoding="utf-8"
    )
    _git(repo, "add", "notes.txt")

    code, out = _run_guard(repo, "--staged", store)
    assert code == 0, out


def test_cli_staged_ignores_an_unstaged_edit(tmp_path):
    """Only the index counts: a token in the working tree that was never
    `git add`ed is not scanned by --staged."""
    store = _build_synthetic_store(tmp_path)
    repo = _git_repo(tmp_path, {"notes.txt": "clean line\n"})
    (repo / "notes.txt").write_text(f"clean line\nWORKTREE uses {LEAK}\n", encoding="utf-8")

    code, out = _run_guard(repo, "--staged", store)
    assert code == 0, out


def test_cli_tracked_flags_a_committed_file_carrying_a_token(tmp_path):
    store = _build_synthetic_store(tmp_path)
    repo = _git_repo(tmp_path, {"notes.txt": f"call {LEAK} here\n"})
    code, out = _run_guard(repo, "--tracked", store)
    assert code == 1, out
    assert "notes.txt" in out


def test_cli_tracked_ignores_a_token_only_in_an_untracked_file(tmp_path):
    store = _build_synthetic_store(tmp_path)
    repo = _git_repo(tmp_path, {"clean.txt": "nothing to see\n"})
    (repo / "untracked.txt").write_text(f"call {LEAK} here\n", encoding="utf-8")

    code, out = _run_guard(repo, "--tracked", store)
    assert code == 0, out


@pytest.mark.skipif(
    not REAL_PRIVATE_ROOT, reason="needs the real store bound (SDLC_PRIVATE_CASES_ROOT)"
)
def test_cli_tracked_over_this_repository_finds_nothing_with_the_real_store():
    """Rule 1 as a test: with the real store bound, nothing tracked in this
    repository carries a token of it. Opt-in; skipped without the store."""
    code, out = _run_guard(REPO_ROOT, "--tracked", REAL_PRIVATE_ROOT)
    assert code == 0, out


# --- guard-fix regression (T016 finding): manifest boilerplate is not a token --
#
# Names shingles '8-word shingles of description and of each rubric' -- the
# description VALUE, not the whole case.yaml. A private manifest
# structurally mirrors the public one (models, arms role_models blocks,
# extra_args_by_model), so whole-manifest shingling turns that boilerplate
# into tokens and fires on every public file quoting the manifest.

MANIFEST_BOILERPLATE = """models:
  - zai-coding-plan/glm-5.2
  - zai-coding-plan/glm-5.3-flash
arms:
  - name: zai-coding-plan-glm-5.2
    role_models:
      dev: zai-coding-plan/glm-5.2
      test: zai-coding-plan/glm-5.2
      devops: zai-coding-plan/glm-5.2
  - name: zai-coding-plan-glm-5.3-flash
    role_models:
      dev: zai-coding-plan/glm-5.3-flash
      test: zai-coding-plan/glm-5.3-flash
      devops: zai-coding-plan/glm-5.3-flash
extra_args_by_model:
  zai-coding-plan/glm-5.2:
    sandbox_warn: false
"""

# The same wording as ONE inline line, the way a public doc quotes a
# manifest; scan() matches tokens per line, so this is the shape that the
# whole-manifest shingles actually fire on.
MANIFEST_QUOTE_LINE = (
    "supported fields: models: - zai-coding-plan/glm-5.2 - zai-coding-plan/glm-5.3-flash "
    "arms: - name: zai-coding-plan-glm-5.2 role_models: dev: zai-coding-plan/glm-5.2 "
    "test: zai-coding-plan/glm-5.2 devops: zai-coding-plan/glm-5.2"
)


def _build_manifest_shaped_store(tmp_path: Path) -> Path:
    """A synthetic case whose case.yaml carries (a) manifest boilerplate
    identical in wording to MANIFEST_BOILERPLATE and (b) an invented
    description holding DESCRIPTION_RUN."""
    cases = tmp_path / "cases"
    case = cases / "synthetic-manifest-case"
    case.mkdir(parents=True)
    (case / "case.yaml").write_text(
        "case_id: synthetic-manifest-case\n"
        "idea_summary: an invented case for the boilerplate regression\n"
        "description: the staging crew resets the hall between two shows "
        f"and {DESCRIPTION_RUN} the refund completes\n"
        "mode: greenfield\n" + MANIFEST_BOILERPLATE,
        encoding="utf-8",
    )
    return cases


def test_cli_tracked_manifest_boilerplate_is_not_a_token(tmp_path):
    """T016 guard-fix regression: repo A quotes only manifest boilerplate
    (the fields every public manifest also carries) and must PASS;
    the control repo B carrying the description run must still be
    flagged."""
    store = _build_manifest_shaped_store(tmp_path)

    (tmp_path / "a").mkdir()
    repo_a = _git_repo(tmp_path / "a", {"manifest-notes.md": MANIFEST_QUOTE_LINE + "\n"})
    code_a, out_a = _run_guard(repo_a, "--tracked", store)
    assert code_a == 0, (
        f"manifest boilerplate must not be a token (Names shingles the "
        f"description VALUE, not the whole case.yaml); the guard flagged:\n{out_a}"
    )

    (tmp_path / "b").mkdir()
    repo_b = _git_repo(tmp_path / "b", {"notes.md": f"{DESCRIPTION_RUN} refund completes\n"})
    code_b, out_b = _run_guard(repo_b, "--tracked", store)
    assert code_b == 1, out_b
