"""DevEval (COLING 2025, CC BY 4.0) -> Kroker benchmark cases (E-79).

Every DevEval repository ships a repo_config.json naming each artifact by
path, so conversion is a manifest read rather than a scrape. This module is
pure where it can be and confines its I/O to convert_repo.

Fails loud on every error path: the importer is offline, human-run, and
one-shot, so a malformed manifest should stop it rather than silently emit
a half-built case (the opposite of the graders' fail-safe discipline).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class RepoConfig(BaseModel):
    """The subset of repo_config.json the import consumes. Unknown keys
    (DevEval's per-test prompt blobs) are ignored on purpose."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    prd: str = Field(alias="PRD")
    uml_class: str = Field(alias="UML_class")
    uml_sequence: str = Field(alias="UML_sequence")
    architecture_design: str
    dependencies: str
    language: str
    unit_tests: str
    acceptance_tests: str
    usage_examples: str | None = None
    unit_test_linking: dict[str, list[str]] = Field(default_factory=dict)
    code_file_dag: dict[str, list[str]] = Field(
        default_factory=dict, alias="code_file_DAG")


def load_repo_config(repo_dir: Path) -> RepoConfig:
    """Read <repo_dir>/repo_config.json. Raises FileNotFoundError if absent
    and pydantic.ValidationError if a consumed key is missing."""
    path = Path(repo_dir) / "repo_config.json"
    if not path.is_file():
        raise FileNotFoundError(f"no repo_config.json in {repo_dir}")
    return RepoConfig(**json.loads(path.read_text(encoding="utf-8")))


def collect_node_ids(test_root: Path, prefix: str) -> list[str]:
    """Every `test_*` function and method under test_root, as JUnit node-ids
    relative to the oracle dir: "<prefix>/<relpath>::<name>".

    Parsed with ast rather than imported: these are third-party test files
    and importing them would execute module-level code. The prefix/separator
    shape must match grade_oracle's normalization (oracle.py:231), which
    strips the "oracle/" prefix and converts to forward slashes.

    Raises SyntaxError on an unparseable test file -- fail loud.
    """
    root = Path(test_root)
    out: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test_"):
                    names.append(node.name)
        out.extend(f"{prefix}/{rel}::{n}" for n in sorted(set(names)))
    return sorted(out)


DRAFT_BANNER = (
    "# DRAFT -- REVIEW BEFORE USE (E-79, spec 3.4).\n"
    "# Generated at test-FILE granularity from DevEval's unit_test_linking.\n"
    "# Functional completeness is requirement-weighted, so a human must\n"
    "# regroup these into real requirements and set each error_class.\n"
    "# Valid error_class values: functional, security, performance,\n"
    "# data_integrity, error_handling, api_contract.\n")


def _task_id(rel_file: str) -> str:
    """"unit_tests/test_check_date.py" -> "check_date"; a directory prefix is
    kept only when it is needed to keep ids unique (TaskSuite rejects dupes).
    """
    stem = Path(rel_file).stem
    return stem[len("test_"):] if stem.startswith("test_") else stem


def draft_task_suite(node_ids: list[str]) -> dict:
    """Group node-ids by test file into a draft tasks.yaml structure.

    Every task is emitted as error_class "functional" -- guessing a richer
    classification from a filename would produce confident, wrong error-class
    matrices. The human review pass sets these.
    """
    if not node_ids:
        raise ValueError("no oracle test node-ids; refusing to draft an "
                         "empty task suite")
    by_file: dict[str, list[str]] = {}
    for nid in node_ids:
        by_file.setdefault(nid.split("::", 1)[0], []).append(nid)

    stems = [_task_id(f) for f in sorted(by_file)]
    collide = {s for s in stems if stems.count(s) > 1}

    tasks = []
    for rel_file in sorted(by_file):
        base = _task_id(rel_file)
        if base in collide:
            parent = Path(rel_file).parent.as_posix().replace("/", "-")
            base = f"{parent}-{base}" if parent not in ("", ".") else base
        tasks.append({"id": base, "error_class": "functional",
                      "oracle_tests": sorted(by_file[rel_file])})
    return {"tasks": tasks}


def render_tasks_yaml(suite: dict) -> str:
    return DRAFT_BANNER + yaml.safe_dump(suite, sort_keys=False)
